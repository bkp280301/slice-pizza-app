"""
app.py — SLICE: Your Pizza Intelligence Assistant
Run: streamlit run app.py --server.address 0.0.0.0
"""

import re
import uuid
import requests
from datetime import datetime

import streamlit as st

try:
    from streamlit_js_eval import get_geolocation
    _GEO_AVAILABLE = True
except ImportError:
    _GEO_AVAILABLE = False

import config
from agent import run_agent_stream


def _reverse_geocode(lat: float, lon: float) -> str:
    """Convert GPS coordinates to a human-readable city string."""
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json"},
            headers={"User-Agent": config.HTTP_USER_AGENT},
            timeout=6,
        )
        data = r.json()
        addr = data.get("address", {})
        city    = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county", "")
        state   = addr.get("state", "")
        country = addr.get("country", "")
        parts   = [p for p in [city, state, country] if p]
        return ", ".join(parts[:2]) if parts else f"{lat:.4f},{lon:.4f}"
    except Exception:
        return f"{lat:.4f},{lon:.4f}"

st.set_page_config(
    page_title="SLICE — Pizza Intelligence",
    page_icon="🍕",
    layout="wide",
    initial_sidebar_state="expanded",
)

for k, v in [("page", "chat"), ("conversations", []), ("current_conv", None), ("show_settings", False)]:
    if k not in st.session_state:
        st.session_state[k] = v

# ═══════════════════════════════════════════════════════════════════════════════
# MASTER CSS
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
/* ── 1. HARD RESET ── */
html, body { margin:0; padding:0; background:#0a0400 !important; }

.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stAppViewBlockContainer"],
.main, section.main,
div.block-container,
[data-testid="stVerticalBlock"],
[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stHorizontalBlock"],
[data-testid="column"] > div,
[data-testid="stMarkdownContainer"] > div,
div[class*="element-container"],
div[class*="stMarkdown"] {
    background: #0a0400 !important;
    background-color: #0a0400 !important;
}

/* ── 2. SIDEBAR ── */
[data-testid="stSidebar"],
[data-testid="stSidebar"] > div,
[data-testid="stSidebarContent"],
[data-testid="stSidebarContent"] > div {
    background: #110600 !important;
    border-right: 1px solid #2d1500 !important;
}

/* ── 3. HIDE STREAMLIT CHROME ── */
#MainMenu, footer,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"] { display:none !important; }

/* Hide header bar but keep sidebar toggle visible */
[data-testid="stHeader"] {
    background: transparent !important;
    height: 0 !important;
    min-height: 0 !important;
    overflow: visible !important;
}

/* Sidebar open/close toggle — always visible */
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    background: #1c0a00 !important;
    border: 1px solid #3a1a00 !important;
    border-radius: 8px !important;
    color: #f4a261 !important;
    z-index: 9999 !important;
}
[data-testid="stSidebarCollapsedControl"] svg,
[data-testid="collapsedControl"] svg { fill: #f4a261 !important; }

/* ── 4. HIDE RADIO WIDGET ── */
[data-testid="stRadio"] { display:none !important; }

/* ── 5. HIDE EXPANDER ARROW TEXT GLITCH ── */
[data-testid="stExpander"] summary > div:first-child,
details > summary > span:empty,
details > summary > span[data-testid],
[data-testid="stExpanderToggleIcon"],
details summary svg { display:none !important; }
/* Nuke any ▸ _arrow characters that appear */
details > summary::before { content:none !important; }

/* ── 6. FONTS ── */
*, body, button, input, textarea, select, label {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif !important;
    -webkit-font-smoothing: antialiased !important;
}

/* ── 7. MAIN CONTAINER ── */
.main .block-container {
    max-width: 900px !important;
    padding: 2rem 2.5rem 8rem !important;
    margin: 0 auto !important;
}

/* ── 8. BUTTONS — default ── */
.stButton > button {
    background: #1c0a00 !important;
    color: #d4956a !important;
    border: 1px solid #3a1a00 !important;
    border-radius: 10px !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    padding: 9px 16px !important;
    transition: background .15s, color .15s, border-color .15s !important;
    box-shadow: none !important;
    outline: none !important;
}
.stButton > button:hover {
    background: #2d1200 !important;
    border-color: #c0392b !important;
    color: #f5c49a !important;
}
.stButton > button:focus { outline:none !important; box-shadow:none !important; }

/* ── 9. PRIMARY BUTTON ── */
[data-testid="baseButton-primary"] button,
button[kind="primary"] {
    background: linear-gradient(135deg,#c0392b,#e07840) !important;
    border: none !important;
    color: #fff !important;
    font-weight: 700 !important;
    letter-spacing: .3px !important;
    box-shadow: 0 2px 10px rgba(192,57,43,.35) !important;
}
[data-testid="baseButton-primary"] button:hover { opacity:.88 !important; }

/* ── 10. SIDEBAR BUTTONS (nav) ── */
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    border: none !important;
    border-radius: 8px !important;
    color: #8a5030 !important;
    text-align: left !important;
    justify-content: flex-start !important;
    width: 100% !important;
    font-size: 14px !important;
    padding: 9px 12px !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: #1c0a00 !important;
    color: #e8c89a !important;
    border-color: transparent !important;
}

/* ── 11. TEXT INPUTS ── */
.stTextInput input, .stTextArea textarea,
input[type="text"], input[type="password"], textarea {
    background: #160800 !important;
    color: #f0e0cc !important;
    border: 1px solid #3a1a00 !important;
    border-radius: 10px !important;
    font-size: 14px !important;
    outline: none !important;
    box-shadow: none !important;
    transition: border-color .2s !important;
}
.stTextInput input:hover, .stTextArea textarea:hover {
    border-color: #5a2800 !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: #7a3800 !important;
    box-shadow: none !important;
    outline: none !important;
}
label {
    color: #6a3820 !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
}

/* ── 12. CHAT INPUT — no red border, ever ── */
/* Kill ALL borders on the wrapper divs */
[data-testid="stChatInput"],
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] > div > div,
div[class*="stChatInputContainer"],
div[class*="stChatInputContainer"] > div {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
}
/* Style only the actual textarea */
[data-testid="stChatInput"] textarea {
    background: #160800 !important;
    color: #f0e0cc !important;
    border: 1px solid #3a1a00 !important;
    border-radius: 14px !important;
    padding: 14px 56px 14px 18px !important;
    font-size: 14.5px !important;
    line-height: 1.6 !important;
    resize: none !important;
    outline: none !important;
    box-shadow: none !important;
    transition: border-color .2s !important;
}
[data-testid="stChatInput"] textarea:hover {
    border-color: #5a2800 !important;
}
[data-testid="stChatInput"] textarea:focus {
    border-color: #7a3800 !important;
    box-shadow: none !important;
    outline: none !important;
}
/* Remove focus-within red ring from container */
[data-testid="stChatInput"]:focus-within,
[data-testid="stChatInput"]:focus-within > div,
[data-testid="stChatInput"]:focus-within > div > div {
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
}
/* Bottom bar */
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottom"] > div > div,
.stChatFloatingInputContainer,
.stChatFloatingInputContainer > div {
    background: #0a0400 !important;
    border-top: 1px solid #1e0c00 !important;
    box-shadow: none !important;
}
/* Send button */
[data-testid="stChatInputSubmitButton"] button {
    background: linear-gradient(135deg,#c0392b,#e07840) !important;
    border: none !important;
    border-radius: 9px !important;
    color: #fff !important;
    box-shadow: none !important;
}

/* ── 13. CHAT MESSAGES ── */
[data-testid="stChatMessage"],
[data-testid="stChatMessage"] > div,
[data-testid="stChatMessage"] > div > div {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

/* ── HIDE AVATAR ICONS / TEXT (face, smart_t glitches) ── */
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"],
[data-testid="chatAvatarIcon-user"],
[data-testid="chatAvatarIcon-assistant"],
[data-testid="stChatMessage"] img,
[data-testid="stChatMessage"] [data-testid*="Avatar"],
.stChatMessage [class*="avatar"],
[data-testid="stChatMessage"] > div:first-child > div:first-child {
    display: none !important;
}

/* ── HIDE FILE PATH / DEBUG TEXT at bottom ── */
[data-testid="stException"],
[data-testid="stException"] * { display: none !important; }
footer, [class*="footer"] { display: none !important; }
    box-shadow: none !important;
}

/* ── 14. EXPANDER ── */
[data-testid="stExpander"],
[data-testid="stExpander"] > div,
[data-testid="stExpanderDetails"] {
    background: #130700 !important;
    border: 1px solid #3a1a00 !important;
    border-radius: 12px !important;
}
details > summary {
    color: #d4956a !important;
    font-weight: 600 !important;
    font-size: 13.5px !important;
    background: transparent !important;
    padding: 10px 14px !important;
    list-style: none !important;
    cursor: pointer !important;
    border-radius: 12px !important;
}
details > summary::-webkit-details-marker { display:none !important; }

/* ── 15. TABS ── */
[data-baseweb="tab-list"],
[data-baseweb="tab-list"] > div {
    background: #130700 !important;
    border-radius: 12px !important;
    padding: 4px !important;
    gap: 4px !important;
    border: none !important;
}
[data-baseweb="tab"] {
    background: transparent !important;
    color: #6a3820 !important;
    font-weight: 600 !important;
    font-size: 13.5px !important;
    border-radius: 9px !important;
    border: none !important;
    padding: 8px 20px !important;
}
[aria-selected="true"][data-baseweb="tab"] {
    background: linear-gradient(135deg,#c0392b,#e07840) !important;
    color: #fff !important;
}
[data-baseweb="tab-panel"],
[data-baseweb="tab-panel"] > div { background: #0a0400 !important; }

/* ── 16. METRICS ── */
[data-testid="metric-container"] {
    background: #130700 !important;
    border: 1px solid #2d1500 !important;
    border-radius: 14px !important;
    padding: 16px !important;
}
[data-testid="stMetricValue"] > div {
    color: #f4a261 !important;
    font-size: 22px !important;
    font-weight: 800 !important;
}
[data-testid="stMetricLabel"] > div {
    color: #8a5030 !important;
    font-size: 11.5px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: .5px !important;
}

/* ── 17. SELECT ── */
[data-testid="stSelectbox"] > div > div,
[data-baseweb="select"] > div {
    background: #160800 !important;
    color: #f0e0cc !important;
    border-color: #3a1a00 !important;
    border-radius: 10px !important;
}
[data-baseweb="popover"] > div,
[data-baseweb="menu"] { background: #160800 !important; border: 1px solid #3a1a00 !important; }
[data-baseweb="option"] { background: #160800 !important; color: #f0e0cc !important; }
[data-baseweb="option"]:hover { background: #2d1200 !important; }

/* ── 18. MULTISELECT ── */
[data-baseweb="tag"] {
    background: linear-gradient(135deg,#c0392b,#e07840) !important;
    color: #fff !important;
    border-radius: 6px !important;
}

/* ── 19. SLIDER ── */
[data-testid="stSliderTrackFill"] { background: linear-gradient(90deg,#c0392b,#e07840) !important; }
[data-testid="stThumbValue"] { color: #f4a261 !important; }

/* ── 20. NUMBER INPUT ── */
.stNumberInput input {
    background: #160800 !important;
    color: #f0e0cc !important;
    border-color: #3a1a00 !important;
    border-radius: 10px !important;
}
.stNumberInput button {
    background: #1c0a00 !important;
    color: #d4956a !important;
    border-color: #3a1a00 !important;
}

/* ── 21. ALERTS ── */
[data-testid="stAlert"], .stAlert {
    background: #160800 !important;
    border-left: 4px solid #c0392b !important;
    border-radius: 10px !important;
}

/* ── 22. TYPOGRAPHY ── */
p, li, span { color: #f0e0cc; }
.stMarkdown p, .stMarkdown li {
    line-height: 1.9 !important;
    font-size: 14.5px !important;
    color: #f0e0cc !important;
}
.stMarkdown h1 { color: #f4a261 !important; font-size: 26px !important; font-weight: 800 !important; }
.stMarkdown h2 { color: #f4a261 !important; font-size: 21px !important; font-weight: 700 !important; }
.stMarkdown h3 { color: #ffd180 !important; font-size: 17px !important; font-weight: 700 !important; }
.stMarkdown a  { color: #e07840 !important; }
.stMarkdown code {
    background: #1c0a00 !important;
    color: #f4a261 !important;
    border-radius: 5px !important;
    padding: 2px 7px !important;
}
.stMarkdown strong, strong { color: #ffd180 !important; }
hr { border:none !important; border-top: 1px solid #1e0c00 !important; }
.stCaption, small, [data-testid="stCaptionContainer"] p { color: #4a2800 !important; }

/* ── 23. SCROLLBAR ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #3a1a00; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #c0392b; }
</style>
""", unsafe_allow_html=True)


# ── Pizza logo ────────────────────────────────────────────────────────────────
LOGO_HTML = """
<div style="text-align:center; padding:30px 12px 18px;">
  <svg width="70" height="70" viewBox="0 0 80 80" fill="none">
    <circle cx="40" cy="40" r="36" fill="#130700" stroke="#3a1a00" stroke-width="1.5"/>
    <path d="M40 40 L76 30 A36 36 0 0 1 76 50 Z" fill="#f4a261"/>
    <path d="M40 40 L76 30 A36 36 0 0 1 76 50 Z" fill="#c0392b" opacity=".22"/>
    <path d="M76 30 A36 36 0 0 1 76 50" stroke="#f4a261" stroke-width="7" stroke-linecap="round" fill="none"/>
    <circle cx="62" cy="34"  r="4"   fill="#a0291f"/>
    <circle cx="66" cy="42"  r="3.5" fill="#a0291f"/>
    <circle cx="56" cy="44"  r="3"   fill="#a0291f"/>
    <circle cx="59" cy="36"  r="1.8" fill="#a0291f" opacity=".7"/>
    <circle cx="40" cy="40" r="34" fill="none" stroke="#2d1500" stroke-width=".8" opacity=".5"/>
    <line x1="40" y1="6"  x2="40" y2="40" stroke="#2d1500" stroke-width=".7" opacity=".4"/>
    <line x1="6"  y1="40" x2="40" y2="40" stroke="#2d1500" stroke-width=".7" opacity=".4"/>
    <line x1="14" y1="14" x2="40" y2="40" stroke="#2d1500" stroke-width=".7" opacity=".4"/>
    <line x1="66" y1="14" x2="40" y2="40" stroke="#2d1500" stroke-width=".7" opacity=".4"/>
    <line x1="14" y1="66" x2="40" y2="40" stroke="#2d1500" stroke-width=".7" opacity=".4"/>
    <line x1="66" y1="66" x2="40" y2="40" stroke="#2d1500" stroke-width=".7" opacity=".4"/>
  </svg>
  <div style="font-size:28px; font-weight:900; letter-spacing:5px; margin-top:10px;
              background: linear-gradient(135deg,#c0392b 0%,#f4a261 100%);
              -webkit-background-clip:text; -webkit-text-fill-color:transparent;
              background-clip:text;">SLICE</div>
  <div style="font-size:9px; color:#3a1a00; letter-spacing:3.5px;
              text-transform:uppercase; margin-top:4px; font-weight:700;">
    Pizza Intelligence
  </div>
</div>
"""


def _sep():
    st.markdown('<hr style="border-top:1px solid #1e0c00;margin:10px 0;">', unsafe_allow_html=True)


def _inject_location(query: str) -> str:
    """Append or replace location in query using user's saved location."""
    loc = st.session_state.get("user_location", "").strip()
    if not loc:
        return query
    # Replace "near me" phrases exactly — NOT the word "nearest"
    result = re.sub(
        r'\b(near me|nearby|around me|closest to me|near my location|to me|for me)\b',
        f"near {loc}", query, flags=re.IGNORECASE
    )
    # If nothing replaced but query has location intent, append location
    if result == query and re.search(
        r'\b(nearest|closest|find|where is|open now|delivery|restaurant|pizza place|near)\b',
        query, re.IGNORECASE
    ):
        result = f"{query} near {loc}"
    return result


def _label(txt: str):
    st.markdown(
        f'<p style="color:#3a1a00;font-size:10px;font-weight:700;letter-spacing:2px;'
        f'text-transform:uppercase;margin:8px 0 4px;padding-left:12px;">{txt}</p>',
        unsafe_allow_html=True,
    )


# ── Nav button: active one gets accent styling injected via markdown ──────────
def _nav(icon: str, label: str, key: str, target: str):
    active = st.session_state.page == target
    if active:
        st.markdown(f"""
        <div style="
            background:linear-gradient(135deg,#c0392b,#e07840);
            border-radius:9px; padding:10px 14px; margin:1px 0;
            font-size:14px; font-weight:700; color:#fff;
            display:flex; align-items:center; gap:8px; cursor:default;">
          {icon}&nbsp; {label}
        </div>""", unsafe_allow_html=True)
    else:
        if st.button(f"{icon}  {label}", key=key, use_container_width=True):
            st.session_state.page = target
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(LOGO_HTML, unsafe_allow_html=True)
    _sep()

    _nav("🍕", "Pizza Chat",         "nav_chat", "chat")
    _nav("📍", "Find Pizza Near Me", "nav_find", "find")
    _nav("🔢", "Pizza Calculator",   "nav_calc", "calc")

    _sep()
    _label("Chat History")

    if st.button("＋  New Chat", key="new_chat", use_container_width=True):
        cid = str(uuid.uuid4())[:8]
        st.session_state.conversations.insert(0, {
            "id": cid, "title": "New pizza chat",
            "messages": [], "ts": datetime.now().strftime("%b %d, %H:%M"),
        })
        st.session_state.current_conv = cid
        st.session_state.page = "chat"
        st.rerun()

    for conv in st.session_state.conversations[:12]:
        active = conv["id"] == st.session_state.current_conv
        c1, c2 = st.columns([5, 1])
        with c1:
            lbl = ("▶ " if active else "") + conv["title"][:26]
            if st.button(lbl, key=f"oc_{conv['id']}"):
                st.session_state.current_conv = conv["id"]
                st.session_state.page = "chat"
                st.rerun()
        with c2:
            if st.button("✕", key=f"dc_{conv['id']}"):
                st.session_state.conversations = [
                    c for c in st.session_state.conversations if c["id"] != conv["id"]
                ]
                if st.session_state.current_conv == conv["id"]:
                    st.session_state.current_conv = None
                st.rerun()

    if not st.session_state.conversations:
        st.caption("No chats yet")

    _sep()
    # ── My Location ──
    _label("📍 My Location")

    saved_loc = st.session_state.get("user_location", "")

    if saved_loc:
        st.markdown(
            f'<div style="background:#1c0a00;border:1px solid #3a1a00;border-radius:9px;'
            f'padding:9px 12px;margin-bottom:8px;font-size:13px;color:#f4a261;">'
            f'📍 {saved_loc}</div>',
            unsafe_allow_html=True,
        )
        if st.button("🔄  Update Location", key="update_loc", use_container_width=True):
            st.session_state.user_location = ""
            st.session_state.pop("_geo_fetched", None)
            st.rerun()
    else:
        # Try browser GPS automatically
        if _GEO_AVAILABLE and not st.session_state.get("_geo_fetched"):
            st.markdown(
                '<p style="color:#5a2e00;font-size:11px;line-height:1.5;margin:0 0 6px;">'
                'Allow location access for accurate "near me" results.</p>',
                unsafe_allow_html=True,
            )
            geo = get_geolocation()
            st.session_state["_geo_fetched"] = True
            if geo and geo.get("coords"):
                lat = geo["coords"]["latitude"]
                lon = geo["coords"]["longitude"]
                city = _reverse_geocode(lat, lon)
                st.session_state.user_location = city
                st.rerun()

        # Manual fallback input
        st.markdown(
            '<p style="color:#5a2e00;font-size:11px;line-height:1.5;margin:0 0 4px;">'
            'Or type your city / ZIP:</p>',
            unsafe_allow_html=True,
        )
        manual = st.text_input(
            "loc", placeholder="e.g. Chennai, India  or  10001",
            key="loc_manual", label_visibility="collapsed",
        )
        if st.button("📍  Set Location", key="set_loc", use_container_width=True):
            if manual.strip():
                st.session_state.user_location = manual.strip()
                st.rerun()

    _sep()
    # ── Settings ──
    _label("Settings")

    new_key = st.text_input(
        "Groq API Key", type="password",
        value=config.GROQ_API_KEY or "",
        placeholder="gsk_...", key="s_key",
    )
    if new_key and new_key != config.GROQ_API_KEY:
        config.GROQ_API_KEY = new_key
        st.success("Key saved!")

    config.GROQ_MODEL = st.selectbox(
        "Model",
        ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
        key="s_mod",
    )
    if st.button("🗑  Clear All Chats", key="clear_chats", use_container_width=True):
        st.session_state.conversations = []
        st.session_state.current_conv  = None
        st.rerun()

    _sep()
    st.markdown(
        '<div style="text-align:center;padding:4px 0 10px;">'
        '<span style="font-size:11px;color:#2d1500;letter-spacing:1px;">🍕 SLICE AI · Pizza Intelligence</span>'
        '</div>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PIZZA CHAT
# ═══════════════════════════════════════════════════════════════════════════════
def render_chat():
    if not config.GROQ_API_KEY:
        st.markdown("""
        <div style="background:#160800;border:1px solid #c0392b;border-radius:14px;
                    padding:24px 28px;margin:24px 0;max-width:520px;">
          <div style="font-size:18px;font-weight:800;color:#c0392b;margin-bottom:10px;">
            🔑 API Key Required
          </div>
          <div style="font-size:14px;color:#9a6040;line-height:1.85;">
            Paste your free Groq key in <b style="color:#f4a261;">Settings</b> (sidebar).<br>
            Get one free at <b style="color:#f4a261;">console.groq.com</b>
          </div>
        </div>""", unsafe_allow_html=True)
        return

    if not st.session_state.get("current_conv"):
        cid = str(uuid.uuid4())[:8]
        st.session_state.conversations.insert(0, {
            "id": cid, "title": "New pizza chat",
            "messages": [], "ts": datetime.now().strftime("%b %d, %H:%M"),
        })
        st.session_state.current_conv = cid

    conv = next(
        (c for c in st.session_state.conversations if c["id"] == st.session_state.current_conv),
        None,
    )
    if not conv:
        st.markdown(
            '<div style="text-align:center;padding:48px;color:#4a2800;font-size:15px;">'
            'Click <b style="color:#f4a261;">＋ New Chat</b> to begin.</div>',
            unsafe_allow_html=True,
        )
        return

    # Header
    st.markdown(f"""
    <div style="padding-bottom:16px;margin-bottom:20px;border-bottom:1px solid #1e0c00;">
      <div style="font-size:18px;font-weight:800;color:#f4a261;letter-spacing:.3px;">
        {conv['title']}
      </div>
      <div style="font-size:11px;color:#3a1a00;margin-top:3px;letter-spacing:.5px;">
        {conv['ts']}
      </div>
    </div>""", unsafe_allow_html=True)

    # Messages
    for msg in conv["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Empty state
    if not conv["messages"]:
        st.markdown("""
        <div style="text-align:center;padding:52px 10px 32px;">
          <div style="font-size:64px;line-height:1;">🍕</div>
          <div style="font-size:28px;font-weight:900;color:#f4a261;
                      letter-spacing:1px;margin:16px 0 10px;">Welcome to SLICE!</div>
          <div style="font-size:15px;color:#9a6040;max-width:460px;
                      margin:0 auto;line-height:1.85;">
            Your personal pizza expert. Ask me about recipes, pizza chains near you,
            calories, history, toppings — anything pizza!
          </div>
        </div>""", unsafe_allow_html=True)

        suggestions = [
            ("🍅", "How is Margherita pizza made?"),
            ("📍", "Find the nearest Domino's near me"),
            ("🔥", "What are the most popular pizza toppings?"),
            ("📊", "How many calories in a pepperoni pizza?"),
            ("🏪", "Is Pizza Hut open now near me?"),
            ("🇮🇹", "What is the history of pizza?"),
        ]
        cols = st.columns(2)
        for i, (icon, text) in enumerate(suggestions):
            # Use a form-submit pattern so the value is captured reliably
            if cols[i % 2].button(f"{icon}  {text}", key=f"sg{i}", use_container_width=True):
                st.session_state["_q"] = text

    # Pick up suggestion click OR typed message
    _queued = st.session_state.pop("_q", None)
    user_input = _queued or st.chat_input("Ask anything about pizza…")
    if not user_input:
        return

    conv["messages"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    if len(conv["messages"]) == 1:
        conv["title"] = user_input[:46] + ("…" if len(user_input) > 46 else "")

    history = [
        {"role": m["role"], "content": m["content"]}
        for m in conv["messages"][:-1] if m["role"] in ("user", "assistant")
    ]

    with st.chat_message("assistant"):
        status_ph = st.empty()
        answer_ph = st.empty()
        chunks: list[str] = []

        def on_tool(desc):
            status_ph.markdown(
                f'<div style="color:#c0392b;font-size:12px;font-style:italic;'
                f'margin-bottom:8px;">🍕 {desc}…</div>',
                unsafe_allow_html=True,
            )

        # Replace "near me" with the user's actual saved location
        enriched_input = _inject_location(user_input)

        for chunk in run_agent_stream(
            user_message=enriched_input,
            chat_history=history,
            groq_api_key=config.GROQ_API_KEY,
            on_tool_call=on_tool,
        ):
            chunks.append(chunk)
            answer_ph.markdown("".join(chunks))

        status_ph.empty()

    conv["messages"].append({"role": "assistant", "content": "".join(chunks)})
    conv["ts"] = datetime.now().strftime("%b %d, %H:%M")


# ═══════════════════════════════════════════════════════════════════════════════
# FIND PIZZA NEAR ME
# ═══════════════════════════════════════════════════════════════════════════════
def render_find_pizza():
    st.markdown("""
    <div style="padding-bottom:16px;margin-bottom:22px;border-bottom:1px solid #1e0c00;">
      <div style="font-size:22px;font-weight:800;color:#f4a261;letter-spacing:.3px;">
        📍 Find Pizza Near Me
      </div>
      <div style="font-size:14px;color:#9a6040;margin-top:6px;line-height:1.7;">
        Search any pizza chain — get real addresses, phone numbers &amp; opening hours.
      </div>
    </div>""", unsafe_allow_html=True)

    if not config.GROQ_API_KEY:
        st.markdown("""
        <div style="background:#160800;border:1px solid #c0392b;border-radius:14px;
                    padding:18px 22px;max-width:480px;">
          <span style="color:#c0392b;font-weight:700;">🔑 Add Groq API key</span>
          <span style="color:#9a6040;"> in Settings (sidebar) to search.</span>
        </div>""", unsafe_allow_html=True)
        return

    st.markdown(
        '<p style="color:#3a1a00;font-size:11px;font-weight:700;letter-spacing:1.5px;'
        'text-transform:uppercase;margin-bottom:12px;">Popular Chains</p>',
        unsafe_allow_html=True,
    )
    chains = ["Domino's", "Pizza Hut", "Papa John's", "Little Caesars", "Papa Murphy's"]
    cols = st.columns(len(chains))
    for i, chain in enumerate(chains):
        if cols[i].button(f"🍕 {chain}", key=f"ch{i}", use_container_width=True):
            st.session_state["_search"] = f"nearest {chain} near me"

    st.markdown("<br>", unsafe_allow_html=True)
    query = st.text_input(
        "Search any pizza place",
        placeholder="e.g.  Pizza Hut near 10001  or  best pizza near me",
        value=st.session_state.pop("_search", ""),
    )
    if st.button("🍕  Search Now", key="fp_go", type="primary"):
        if query:
            result_box = st.empty()
            chunks: list[str] = []
            with st.spinner("Finding pizza near you…"):
                for chunk in run_agent_stream(user_message=_inject_location(query), groq_api_key=config.GROQ_API_KEY):
                    chunks.append(chunk)
                    result_box.markdown("".join(chunks))


# ═══════════════════════════════════════════════════════════════════════════════
# PIZZA CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════════
TOPPING_CAL = {
    "Extra Cheese": 100, "Pepperoni": 90,  "Sausage": 85,
    "Mushrooms": 15,     "Onions": 10,     "Bell Peppers": 10,
    "Olives": 25,        "Jalapeños": 5,   "Bacon": 95,
    "Chicken": 70,       "Ham": 50,        "Pineapple": 20,
    "Spinach": 8,        "Sun-dried Tomatoes": 30, "Anchovies": 40,
}
CRUST_CAL   = {"Thin Crust": 0, "Regular": 50, "Thick / Pan": 120, "Stuffed Crust": 200, "Gluten-Free": 30}
SIZE_BASE   = {"Personal (6\")": 600, "Small (8\")": 750, "Medium (12\")": 1100, "Large (14\")": 1400, "XL (16\")": 1700}
SIZE_SLICES = {"Personal (6\")": 4,   "Small (8\")": 6,   "Medium (12\")": 8,    "Large (14\")": 10,   "XL (16\")": 12}
SAUCE_CAL   = {"Tomato / Marinara": 60, "BBQ": 100, "Alfredo / White": 140, "Pesto": 120, "Buffalo": 80}


def render_calculator():
    st.markdown("""
    <div style="padding-bottom:16px;margin-bottom:22px;border-bottom:1px solid #1e0c00;">
      <div style="font-size:22px;font-weight:800;color:#f4a261;letter-spacing:.3px;">
        🔢 Pizza Calculator
      </div>
      <div style="font-size:14px;color:#9a6040;margin-top:6px;">
        Calories · Dough ingredients · Cost per slice
      </div>
    </div>""", unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["🔥  Calories", "🧪  Dough", "💰  Cost"])

    # ── Calories ──────────────────────────────────────────────────────────────
    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            size  = st.selectbox("Pizza Size",  list(SIZE_BASE.keys()))
            crust = st.selectbox("Crust Type",  list(CRUST_CAL.keys()))
            sauce = st.selectbox("Sauce",       list(SAUCE_CAL.keys()))
        with c2:
            toppings     = st.multiselect("Toppings", list(TOPPING_CAL.keys()),
                                          default=["Extra Cheese", "Pepperoni"])
            slices_eaten = st.slider("Slices you plan to eat", 1, SIZE_SLICES[size], 2)

        nslices     = SIZE_SLICES[size]
        whole       = SIZE_BASE[size] + CRUST_CAL[crust] + SAUCE_CAL[sauce] + sum(TOPPING_CAL[t] for t in toppings) * nslices // 4
        per_slice   = whole // nslices
        your_cal    = per_slice * slices_eaten
        pct         = your_cal * 100 // 2000

        st.markdown("<br>", unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🍕 Whole Pizza", f"{whole:,} cal")
        m2.metric("📐 Per Slice",   f"{per_slice:,} cal")
        m3.metric("😋 Your Total",  f"{your_cal:,} cal")
        m4.metric("📅 Daily %",     f"{pct}%")

        st.markdown(f"""
        <div style="background:#130700;border:1px solid #2d1500;border-radius:14px;
                    padding:18px 22px;margin-top:18px;">
          <div style="font-size:14px;font-weight:800;color:#f4a261;margin-bottom:14px;
                      letter-spacing:.3px;">📊 Breakdown</div>
          <div style="font-size:13.5px;color:#f0e0cc;line-height:2.4;">
            ▸ Base ({size}) — <b style="color:#ffd180;">{SIZE_BASE[size]} cal</b><br>
            ▸ Crust ({crust}) — <b style="color:#ffd180;">+{CRUST_CAL[crust]} cal</b><br>
            ▸ Sauce ({sauce}) — <b style="color:#ffd180;">+{SAUCE_CAL[sauce]} cal</b><br>
            ▸ Toppings — <b style="color:#ffd180;">+{sum(TOPPING_CAL[t] for t in toppings)} cal/slice</b><br>
            ▸ Per slice — <b style="color:#f4a261;font-size:15px;">{per_slice} cal</b><br>
            ▸ Your {slices_eaten} slice(s) —
              <b style="color:#c0392b;font-size:16px;">{your_cal} cal ({pct}% of daily intake)</b>
          </div>
        </div>""", unsafe_allow_html=True)

    # ── Dough ─────────────────────────────────────────────────────────────────
    with tab2:
        col1, col2 = st.columns(2)
        with col1:
            num_pizzas = st.slider("Number of pizzas", 1, 10, 2)
        with col2:
            d_size = st.selectbox("Size", ["Small (8\")", "Medium (12\")", "Large (14\")"], key="d_sz")

        b = num_pizzas * {"Small (8\")": 0.7, "Medium (12\")": 1.0, "Large (14\")": 1.3}[d_size]
        rows = [
            (round(b*250),  "g",  "🌾", "All-purpose flour"),
            (round(b*160),  "ml", "💧", "Warm water (40°C)"),
            (round(b*7, 1), "g",  "🧫", "Active dry yeast"),
            (round(b*7, 1), "g",  "🧂", "Salt"),
            (round(b*15),   "ml", "🫒", "Olive oil"),
            (round(b*5, 1), "g",  "🍬", "Sugar"),
        ]
        st.markdown(f"""
        <div style="background:#130700;border:1px solid #2d1500;border-radius:14px;
                    padding:22px 24px;margin-top:14px;">
          <div style="font-size:15px;font-weight:800;color:#f4a261;margin-bottom:16px;">
            🧪 {num_pizzas} × {d_size} pizza{"s" if num_pizzas>1 else ""}
          </div>
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;">
            {"".join(f'''<div style="background:#1c0a00;border-radius:10px;padding:14px;
              text-align:center;border:1px solid #2d1500;">
              <div style="font-size:22px;margin-bottom:5px;">{icon}</div>
              <div style="font-size:21px;font-weight:800;color:#f4a261;">{amt}{unit}</div>
              <div style="font-size:11.5px;color:#9a6040;margin-top:4px;">{name}</div>
            </div>''' for amt,unit,icon,name in rows)}
          </div>
          <div style="margin-top:16px;font-size:12.5px;color:#6a3820;line-height:2.1;">
            <b style="color:#f4a261;font-size:13px;">Steps</b><br>
            1. Dissolve yeast + sugar in warm water — wait 5 min until frothy<br>
            2. Mix flour + salt, pour in yeast mixture + olive oil<br>
            3. Knead 8–10 min until smooth and elastic<br>
            4. Cover and rest 1 hour until doubled in size<br>
            5. Shape, top, bake at 250 °C (480 °F) for 10–12 min
          </div>
        </div>""", unsafe_allow_html=True)

    # ── Cost ──────────────────────────────────────────────────────────────────
    with tab3:
        c1, c2 = st.columns(2)
        with c1:
            price  = st.number_input("Pizza price ($)", min_value=1.0, max_value=200.0, value=14.99, step=0.5)
            c_size = st.selectbox("Size", list(SIZE_SLICES.keys()), key="c_sz")
            deliv  = st.number_input("Delivery fee ($)", min_value=0.0, max_value=30.0, value=2.99, step=0.5)
            tip    = st.number_input("Tip ($)", min_value=0.0, max_value=30.0, value=3.0, step=0.5)
        with c2:
            nump   = st.slider("How many pizzas?",       1, 5, 1)
            people = st.slider("Sharing with how many?", 1, 8, 2)

        total_s = SIZE_SLICES[c_size] * nump
        total_c = price * nump + deliv + tip

        st.markdown("<br>", unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("💳 Total",      f"${total_c:.2f}")
        m2.metric("🍕 Per Slice",  f"${total_c/total_s:.2f}")
        m3.metric("👥 Per Person", f"${total_c/people:.2f}")
        m4.metric("🍰 Slices",     str(total_s))


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
page = st.session_state.page
if   page == "chat": render_chat()
elif page == "find": render_find_pizza()
elif page == "calc": render_calculator()
