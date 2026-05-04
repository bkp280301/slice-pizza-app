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


# ── Nominatim bounded search (fast, ~1s) ──────────────────────────────────────

def _nominatim_bounded(lat: float, lon: float, keyword: str, radius_km: float = 8.0) -> str:
    """Search Nominatim for keyword within a bounding box around lat/lon.
    Much faster than Overpass. Returns formatted string or empty string."""
    delta = radius_km / 111.0  # ~1 degree latitude = 111 km
    viewbox = f"{lon-delta},{lat+delta},{lon+delta},{lat-delta}"
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": keyword,
                "format": "json",
                "limit": 5,
                "viewbox": viewbox,
                "bounded": 1,
                "addressdetails": 1,
                "extratags": 1,
            },
            headers={"User-Agent": config.HTTP_USER_AGENT},
            timeout=8,
        )
        resp.raise_for_status()
        places = resp.json()
    except Exception:
        return ""

    if not places:
        return ""

    lines = [f"Nearest '{keyword}' results (sorted by distance):\n"]
    for p in places[:5]:
        name     = p.get("display_name", keyword).split(",")[0]
        address  = ", ".join(p.get("display_name", "").split(",")[1:4]).strip()
        extra    = p.get("extratags") or {}
        phone    = extra.get("phone") or extra.get("contact:phone", "N/A")
        website  = extra.get("website") or extra.get("contact:website", "N/A")
        hours    = extra.get("opening_hours", "")
        status   = _check_open_status(hours) if hours else "Hours not listed"
        plat, plon = float(p.get("lat", lat)), float(p.get("lon", lon))
        dist_km  = _haversine(lat, lon, plat, plon)
        lines.append(
            f"• {name} — {dist_km:.1f} km away\n"
            f"  Address : {address}\n"
            f"  Phone   : {phone}\n"
            f"  Website : {website}\n"
            f"  Hours   : {hours or 'Not listed'}\n"
            f"  Status  : {status}\n"
        )
    return "\n".join(lines)


# ── Overpass nearby search ─────────────────────────────────────────────────────

def _overpass_nearby(lat: float, lon: float, keyword: str, radius_m: int = 5000) -> list[dict]:
    """Query Overpass API for pizza places near lat/lon.
    Searches by name AND by cuisine/amenity tags so generic queries like 'pizza' work well.
    """
    safe_kw = re.sub(r'[.*+?^${}()|[\]\\]', '', keyword)
    is_pizza_generic = re.search(r'\bpizza\b', keyword, re.IGNORECASE) and len(keyword.strip()) < 10

    if is_pizza_generic:
        # Broad search: any restaurant/fast_food with pizza cuisine, OR name matches
        query = f"""
[out:json][timeout:25];
(
  node(around:{radius_m},{lat},{lon})[amenity=restaurant][cuisine~"pizza",i];
  node(around:{radius_m},{lat},{lon})[amenity=fast_food][cuisine~"pizza",i];
  node(around:{radius_m},{lat},{lon})[shop=pizza];
  node(around:{radius_m},{lat},{lon})[name~"{safe_kw}",i][amenity];
  way(around:{radius_m},{lat},{lon})[amenity=restaurant][cuisine~"pizza",i];
  way(around:{radius_m},{lat},{lon})[amenity=fast_food][cuisine~"pizza",i];
  way(around:{radius_m},{lat},{lon})[name~"{safe_kw}",i][amenity];
);
out body center;
"""
    else:
        # Specific chain search: match by name, also try cuisine fallback
        query = f"""
[out:json][timeout:25];
(
  node(around:{radius_m},{lat},{lon})[name~"{safe_kw}",i];
  way(around:{radius_m},{lat},{lon})[name~"{safe_kw}",i];
  node(around:{radius_m},{lat},{lon})[brand~"{safe_kw}",i];
  way(around:{radius_m},{lat},{lon})[brand~"{safe_kw}",i];
);
out body center;
"""
    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=12,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
        results = []
        for el in elements:
            tags = el.get("tags", {})
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


# ── City from coords (reverse geocode, no full address) ───────────────────────

def get_city_from_coords(lat: float, lon: float) -> str:
    """Return 'City, State' from GPS coordinates using Nominatim."""
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json"},
            headers={"User-Agent": config.HTTP_USER_AGENT},
            timeout=6,
        )
        addr = r.json().get("address", {})
        city  = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county", "")
        state = addr.get("state", "")
        return f"{city}, {state}" if city and state else city or f"{lat:.4f},{lon:.4f}"
    except Exception:
        return f"{lat:.4f},{lon:.4f}"


# ── Main run function ──────────────────────────────────────────────────────────

def run(place_name: str, coords: tuple | None = None) -> str:
    """Find places near a location and return results sorted by real distance.

    Args:
        place_name: Natural-language query e.g. "Domino's near Boston"
        coords: Optional (lat, lon) from browser GPS — takes priority over all geocoding.
    """
    query_lower = place_name.lower()

    # ── 1. Determine the reference point ──────────────────────────────────────
    ref_lat = ref_lon = ref_name = None

    # Browser GPS coords take absolute priority — they're the user's real position
    if coords and coords[0] and coords[1]:
        ref_lat, ref_lon = float(coords[0]), float(coords[1])
        ref_name = get_city_from_coords(ref_lat, ref_lon)
    else:
        # Check for explicit zip code or city in query
        zip_match = re.search(r'\b(\d{5,6})\b', place_name)
        if any(p in query_lower for p in ["near me", "nearby", "closest to me", "around me"]):
            # Do NOT use IP geolocation — it returns server datacenter location.
            # Without GPS coords we can't reliably find the user's position.
            pass
        elif zip_match or re.search(r'\bnear\s+(.+)', place_name, re.IGNORECASE):
            loc_hint = zip_match.group(1) if zip_match else re.search(r'\bnear\s+(.+)', place_name, re.IGNORECASE).group(1)
            gc = geocode(loc_hint)
            if gc:
                ref_lat, ref_lon, ref_name = gc

    # ── 2. Extract the business keyword ──────────────────────────────────────
    # Split on "near" and take everything BEFORE it as the business name.
    # This correctly handles "Domino's near Boston, Massachusetts, United States"
    # → keyword = "Domino's"  (the old word-by-word regex left "Massachusetts, United States")
    parts = re.split(r'\bnear\b', place_name, maxsplit=1, flags=re.IGNORECASE)
    keyword = parts[0]
    keyword = re.sub(
        r'\b(nearest|find|closest|get me|show me|where is|is there a|looking for)\s+',
        '', keyword, flags=re.IGNORECASE
    ).strip(" ,")
    keyword = re.sub(r'\b\d{5,6}\b', '', keyword).strip(" ,")
    if not keyword:
        keyword = place_name

    # ── 3. Quick Nominatim bounded search (fast — try before Overpass) ───────
    if ref_lat is not None:
        nominatim_result = _nominatim_bounded(ref_lat, ref_lon, keyword)
        if nominatim_result:
            return nominatim_result

    # ── 4. Overpass nearby search (slower but more complete) ──────────────────
    if ref_lat is not None:
        elements = _overpass_nearby(ref_lat, ref_lon, keyword, radius_m=10000)
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
        # Overpass found nothing near the user — do NOT fall back to global Nominatim
        # (it ignores location and returns any matching place in the world).
        # Return empty so agent.py triggers a targeted web search instead.
        return ""

    # ── 4. No reference coords — return empty to let agent do web search ──────
    return ""


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
