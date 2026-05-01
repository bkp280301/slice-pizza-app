"""tools/location_tool.py — Find nearby businesses with real distance using Overpass + Nominatim."""

import math
import re
import requests
from datetime import datetime

import config


# ── IP geolocation ─────────────────────────────────────────────────────────────

def get_ip_location() -> str:
    """Return 'City, Region, Country' from IP. Empty string on failure."""
    for url in ("https://ipapi.co/json/", "https://ipinfo.io/json"):
        try:
            data = requests.get(url, timeout=5).json()
            city   = data.get("city", "")
            region = data.get("region", "")
            country= data.get("country_name") or data.get("country", "")
            if city:
                return f"{city}, {region}, {country}"
        except Exception:
            pass
    return ""


def get_ip_coords() -> tuple[float, float] | None:
    """Return (lat, lon) from IP geolocation, or None."""
    for url in ("https://ipapi.co/json/", "https://ipinfo.io/json"):
        try:
            data = requests.get(url, timeout=5).json()
            # ipinfo returns "loc": "lat,lon"
            if "loc" in data:
                lat, lon = data["loc"].split(",")
                return float(lat), float(lon)
            lat = data.get("latitude") or data.get("lat")
            lon = data.get("longitude") or data.get("lon") or data.get("lng")
            if lat and lon:
                return float(lat), float(lon)
        except Exception:
            pass
    return None


# ── Geocoding ──────────────────────────────────────────────────────────────────

def geocode(query: str) -> tuple[float, float, str] | None:
    """Return (lat, lon, display_name) for a query string, or None."""
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": config.HTTP_USER_AGENT},
            timeout=config.HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            r = results[0]
            return float(r["lat"]), float(r["lon"]), r.get("display_name", query)
    except Exception:
        pass
    return None


# ── Distance ───────────────────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in km between two coordinates."""
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


# ── Overpass nearby search ─────────────────────────────────────────────────────

def _overpass_nearby(lat: float, lon: float, keyword: str, radius_m: int = 5000) -> list[dict]:
    """Query Overpass API for OSM nodes/ways matching keyword near lat/lon."""
    # Escape special regex chars in keyword
    safe_kw = re.sub(r'[.*+?^${}()|[\]\\]', '', keyword)
    query = f"""
[out:json][timeout:20];
(
  node(around:{radius_m},{lat},{lon})[name~"{safe_kw}",i];
  way(around:{radius_m},{lat},{lon})[name~"{safe_kw}",i];
);
out body center;
"""
    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=25,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
        results = []
        for el in elements:
            tags = el.get("tags", {})
            # Get coordinates (nodes have lat/lon; ways have center)
            if el.get("type") == "node":
                el_lat, el_lon = el.get("lat"), el.get("lon")
            else:
                center = el.get("center", {})
                el_lat, el_lon = center.get("lat"), center.get("lon")
            if el_lat is None:
                continue
            dist_km = _haversine(lat, lon, float(el_lat), float(el_lon))
            results.append({"tags": tags, "lat": el_lat, "lon": el_lon, "dist_km": dist_km})
        results.sort(key=lambda x: x["dist_km"])
        return results
    except Exception:
        return []


# ── Tool definition ────────────────────────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "find_location",
        "description": (
            "Find nearby places or businesses. Returns real addresses sorted by actual distance. "
            "Use for: restaurants, hospitals, shops, chains like Domino's/Pizza Hut, directions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "place_name": {
                    "type": "string",
                    "description": "Business/place name plus location hint. Example: 'Dominos near 02125' or 'hospitals near me'",
                },
            },
            "required": ["place_name"],
        },
    },
}


# ── Main run function ──────────────────────────────────────────────────────────

def run(place_name: str) -> str:
    """Find places near a location and return results sorted by real distance."""

    query_lower = place_name.lower()

    # ── 1. Determine the reference point ──────────────────────────────────────
    ref_lat = ref_lon = ref_name = None

    # Check for explicit zip code or address in the query
    zip_match = re.search(r'\b(\d{5,6})\b', place_name)

    if any(p in query_lower for p in ["near me", "nearby", "closest to me", "around me", "nearest"]):
        coords = get_ip_coords()
        if coords:
            ref_lat, ref_lon = coords
            ref_name = get_ip_location() or f"{ref_lat:.4f},{ref_lon:.4f}"
        else:
            city = get_ip_location()
            if city:
                gc = geocode(city)
                if gc:
                    ref_lat, ref_lon, ref_name = gc
    elif zip_match or re.search(r'\bnear\s+(.+)', place_name, re.IGNORECASE):
        loc_hint = zip_match.group(1) if zip_match else re.search(r'\bnear\s+(.+)', place_name, re.IGNORECASE).group(1)
        gc = geocode(loc_hint)
        if gc:
            ref_lat, ref_lon, ref_name = gc

    # ── 2. Extract the business keyword (strip filler words) ──────────────────
    keyword = re.sub(
        r'\b(nearest|find|near me|near\s+\S+|nearby|around me|closest to me|to this location|location|'
        r'this location|in \d{5}|near \d{5})\b',
        "", place_name, flags=re.IGNORECASE
    ).strip(" ,")
    # Also strip zip codes from keyword
    keyword = re.sub(r'\b\d{5,6}\b', "", keyword).strip(" ,")
    if not keyword:
        keyword = place_name  # fallback

    # ── 3. Overpass nearby search (if we have coordinates) ────────────────────
    if ref_lat is not None:
        elements = _overpass_nearby(ref_lat, ref_lon, keyword, radius_m=8000)
        if elements:
            lines = [f"Nearest '{keyword}' results near {ref_name} (sorted by distance):\n"]
            for el in elements[:5]:
                tags = el["tags"]
                name     = tags.get("name", keyword)
                street   = tags.get("addr:street", "")
                housenr  = tags.get("addr:housenumber", "")
                city_    = tags.get("addr:city", "")
                postcode = tags.get("addr:postcode", "")
                phone    = tags.get("phone") or tags.get("contact:phone", "N/A")
                website  = tags.get("website") or tags.get("contact:website", "N/A")
                hours    = tags.get("opening_hours", "")
                addr     = " ".join(filter(None, [housenr, street, city_, postcode])) or "Address not listed"
                dist_str = f"{el['dist_km']:.1f} km away"
                status   = _check_open_status(hours) if hours else "Hours not in database"
                lines.append(
                    f"• {name} — {dist_str}\n"
                    f"  Address : {addr}\n"
                    f"  Phone   : {phone}\n"
                    f"  Website : {website}\n"
                    f"  Hours   : {hours or 'Not listed'}\n"
                    f"  Status  : {status}\n"
                )
            return "\n".join(lines)

    # ── 4. Fallback: plain Nominatim text search ───────────────────────────────
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": place_name, "format": "json", "limit": 5, "addressdetails": 1, "extratags": 1},
            headers={"User-Agent": config.HTTP_USER_AGENT},
            timeout=config.HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        places = resp.json()
    except Exception as e:
        return f"Location lookup failed: {e}"

    if not places:
        return f"No location found for '{place_name}'. Try adding a city or country name."

    results = []
    for place in places[:3]:
        name      = place.get("display_name", "Unknown")
        extra     = place.get("extratags") or {}
        phone     = extra.get("phone") or extra.get("contact:phone", "N/A")
        website   = extra.get("website") or extra.get("contact:website", "N/A")
        hours_raw = extra.get("opening_hours", "")
        status    = _check_open_status(hours_raw) if hours_raw else "Hours not listed"
        results.append(
            f"Place   : {name}\n"
            f"Phone   : {phone}\n"
            f"Website : {website}\n"
            f"Hours   : {hours_raw or 'Not listed'}\n"
            f"Status  : {status}"
        )
    return "\n\n---\n\n".join(results)


# ── Hours parsing ──────────────────────────────────────────────────────────────

def _check_open_status(hours_raw: str) -> str:
    h = hours_raw.strip().lower()
    if "24/7" in h:
        return "OPEN 24/7"
    now = datetime.now()
    current_minute = now.hour * 60 + now.minute
    day_map = {0: "mo", 1: "tu", 2: "we", 3: "th", 4: "fr", 5: "sa", 6: "su"}
    today = day_map[now.weekday()]
    for seg in hours_raw.split(";"):
        seg_l = seg.lower()
        if today in seg_l or _day_in_range(today, seg_l):
            match = re.search(r"(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})", seg)
            if match:
                open_min  = int(match.group(1)) * 60 + int(match.group(2))
                close_min = int(match.group(3)) * 60 + int(match.group(4))
                if open_min <= current_minute <= close_min:
                    return f"OPEN now (closes {match.group(3)}:{match.group(4)})"
                return f"CLOSED now (opens {match.group(1)}:{match.group(2)})"
    return f"Check hours: {hours_raw}"


def _day_in_range(today: str, segment: str) -> bool:
    days = ["mo", "tu", "we", "th", "fr", "sa", "su"]
    match = re.search(r"(mo|tu|we|th|fr|sa|su)\s*-\s*(mo|tu|we|th|fr|sa|su)", segment)
    if not match:
        return False
    try:
        si, ei, ti = days.index(match.group(1)), days.index(match.group(2)), days.index(today)
        return si <= ti <= ei
    except ValueError:
        return False
