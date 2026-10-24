from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from io import BytesIO
from pathlib import Path
import base64
import os
import urllib.error
import urllib.request
import csv
import json
import re
import streamlit.components.v1 as components
import streamlit as st
from typing import Any

import streamlit as st
from PIL import Image

from db import get_connection
from scripts.data.duration_estimator_service import estimate_duration
from scripts.data.quote_readiness import assess_quote_readiness
from scripts.data.historical_retrieval import retrieve_historical_cases

st.set_page_config(page_title="Star Handyman | Leo", page_icon="🛠️", layout="centered")

# --- ADD THIS HIDE HEADER CODE HERE ---
hide_streamlit_style = """
    <style>
    /* Hides the top header toolbar (Share, GitHub, three-dots menu, etc.) */
    header {visibility: hidden;}
    
    /* Optional: Hides the "Made with Streamlit" footer at the bottom */
    footer {visibility: hidden;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)
# ---------------------------------------

st.markdown("""
<style>
.block-container {max-width: 820px; padding-top: 1rem; padding-bottom: 2rem;}
.hero {padding: 1.1rem 1.25rem; border-radius: 16px; color: white;
       background: linear-gradient(130deg,#172554,#0f766e); margin-bottom: 1rem;}
.hero h1 {font-size: 1.45rem; margin: 0 0 .35rem 0;}
.hero p {margin: 0; opacity: .92; line-height: 1.5;}
.chat-intro {padding: .35rem 0 .7rem 0;}
.small-note {font-size: .88rem; opacity: .8;}
div[data-testid="stChatMessage"] {border: 1px solid rgba(128,128,128,.13); border-radius: 14px; padding: .55rem;}
div.stButton > button {border-radius: 12px; min-height: 2.55rem;}
/* Compact photo strip: avoid tall previews taking over the conversation. */
.photo-strip {display:flex; flex-wrap:wrap; gap:10px; margin:.45rem 0 .2rem;}
.photo-chip {width:94px; min-width:0;}
.photo-chip img {width:88px; height:68px; object-fit:cover; border-radius:9px; display:block; border:1px solid rgba(128,128,128,.25);}
.photo-name {font-size:11px; line-height:1.25; opacity:.78; margin-top:4px; overflow-wrap:anywhere; max-width:88px;}
.upload-status {font-size:.9rem; opacity:.82; padding:.3rem 0;}
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="hero"><h1>🛠️ Leo · Star Handyman</h1>'
    '<p>Your home-service assistant for repairs, installations, and improvements.</p></div>',
    unsafe_allow_html=True,
)

# -------------------- DATABASE-DRIVEN SERVICE CATALOG --------------------
# Read-only: only SELECT queries are issued. No conversation or business data
# is inserted/updated by this prototype.
@st.cache_data(ttl=60, show_spinner=False)
def load_catalog() -> dict[str, Any]:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, name, slug, description
                FROM categories
                WHERE is_active = 1 AND deleted_at IS NULL
                ORDER BY name
            """)
            categories_raw = cursor.fetchall()
            categories = []
            for row in categories_raw:
                if isinstance(row, dict):
                    categories.append({
                        "id": int(row["id"]), "name": str(row["name"]),
                        "slug": row.get("slug"), "description": row.get("description") or "",
                    })
                else:
                    categories.append({
                        "id": int(row[0]), "name": str(row[1]),
                        "slug": row[2], "description": row[3] or "",
                    })

            cursor.execute("""
                SELECT id, name, slug, category_id, description,
                       duration_minutes, service_type, included_items, exclusions
                FROM services
                WHERE is_active = 1 AND deleted_at IS NULL
                ORDER BY name
            """)
            services_raw = cursor.fetchall()
            services = []
            for row in services_raw:
                if isinstance(row, dict):
                    get = row.get
                else:
                    keys = ["id", "name", "slug", "category_id", "description",
                            "duration_minutes", "service_type", "included_items", "exclusions"]
                    record = dict(zip(keys, row))
                    get = record.get
                raw_category_id = str(get("category_id") or "").strip()
                try:
                    numeric_category_id = int(float(raw_category_id)) if raw_category_id else None
                except (TypeError, ValueError):
                    numeric_category_id = None
                services.append({
                    "id": int(get("id")), "name": str(get("name")),
                    "slug": get("slug"), "category_id": numeric_category_id,
                    "category_id_raw": raw_category_id,
                    "description": get("description") or "",
                    "duration_minutes": get("duration_minutes"),
                    "service_type": get("service_type") or "",
                    "included_items": get("included_items") or "",
                    "exclusions": get("exclusions") or "",
                })
            return {"categories": categories, "services": services}
    finally:
        conn.close()


try:
    CATALOG = load_catalog()
    DB_ERROR = None
except Exception as exc:
    CATALOG = {"categories": [], "services": []}
    DB_ERROR = str(exc)

CATEGORIES: list[dict[str, Any]] = CATALOG["categories"]
SERVICES: list[dict[str, Any]] = CATALOG["services"]
CATEGORY_BY_ID = {c["id"]: c for c in CATEGORIES}
CATEGORY_BY_NAME = {c["name"].casefold(): c for c in CATEGORIES}


def normalize_category_reference(value: Any) -> str:
    """Normalize numeric IDs while preserving nonnumeric references."""
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    try:
        return str(int(float(raw)))
    except (TypeError, ValueError):
        # Category name/slug references are normalized locally here because
        # normalize_text is defined later in the file.
        return re.sub(r"[^a-z0-9]+", " ", raw.casefold()).strip()


# Resolve service.category_id against the real active categories.
# Numeric IDs are preferred. If a nonnumeric value is stored, only match it
# against an exact category name or slug; never guess by partial name.
CATEGORY_REFERENCE_LOOKUP: dict[str, int] = {}
for category in CATEGORIES:
    CATEGORY_REFERENCE_LOOKUP[normalize_category_reference(category["id"])] = category["id"]
    CATEGORY_REFERENCE_LOOKUP[normalize_category_reference(category["name"])] = category["id"]
    if category.get("slug"):
        CATEGORY_REFERENCE_LOOKUP[normalize_category_reference(category["slug"])] = category["id"]

SERVICES_BY_CATEGORY: dict[int, list[dict[str, Any]]] = {}
UNMAPPED_SERVICES: list[dict[str, Any]] = []
for service in SERVICES:
    raw_ref = service.get("category_id_raw", service.get("category_id"))
    mapped_category_id = CATEGORY_REFERENCE_LOOKUP.get(normalize_category_reference(raw_ref))
    if mapped_category_id is not None:
        service["mapped_category_id"] = mapped_category_id
        SERVICES_BY_CATEGORY.setdefault(mapped_category_id, []).append(service)
    else:
        service["mapped_category_id"] = None
        UNMAPPED_SERVICES.append(service)

# This is a generic icon mapping only; actual service/category names and IDs
# come from the database.
def category_icon(name: str) -> str:
    text = name.lower()
    if any(word in text for word in ("plumb", "pipe", "drain", "faucet")): return "🚰"
    if any(word in text for word in ("electric", "light", "fan", "wiring")): return "💡"
    if any(word in text for word in ("mount", "tv", "hang")): return "📺"
    if any(word in text for word in ("carpentry", "wood", "door", "cabinet")): return "🪚"
    if any(word in text for word in ("hvac", "heating", "cooling", "air condition")): return "🌬️"
    if any(word in text for word in ("clean", "wash", "pressure")): return "🧽"
    return "🛠️"


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


TERM_GROUPS = {
    "plumbing": {"plumbing", "pipe", "pipes", "leak", "leaking", "faucet", "tap", "toilet", "sink", "drain", "clogged", "water heater", "shower"},
    "electrical": {"electrical", "electric", "wiring", "outlet", "socket", "switch", "light", "lights", "ceiling fan", "power", "breaker"},
    "hvac": {"hvac", "air conditioner", "ac", "cooling", "heating", "thermostat"},
    "carpentry": {"carpentry", "wood", "cabinet", "door", "drawer", "shelf", "hinge"},
    "mounting": {"mount", "mounting", "hang", "hanging", "tv mount", "wall mount"},
    "cleaning": {"clean", "cleaning", "wash", "washing", "stain", "pressure wash"},
    "painting": {"paint", "painting", "repaint", "wall color"},
    "appliance": {"appliance", "refrigerator", "fridge", "dishwasher", "oven", "washer", "dryer"},
}
GROUP_ALIASES = {
    "plumbing": ("plumb", "pipe", "drain", "water", "faucet", "tap"),
    "electrical": ("electric", "wiring", "light", "power", "outlet", "fan"),
    "hvac": ("hvac", "air condition", "cool", "heat", "ac"),
    "carpentry": ("carpent", "wood", "cabinet", "door", "drawer"),
    "mounting": ("mount", "hang", "tv"), "cleaning": ("clean", "wash", "stain"),
    "painting": ("paint", "wall"),
    "appliance": ("appliance", "refrigerator", "washer", "dryer", "oven"),
}


def _term_hits(text: str, field: str) -> int:
    query, target = normalize_text(text), normalize_text(field)
    if not query or not target:
        return 0
    if target in query:
        return 5 if target == query else 3
    stop = {"and", "the", "for", "with", "work", "service", "repair", "install", "installation"}
    words = {w for w in target.split() if len(w) > 2 and w not in stop}
    return min(sum(1 for w in words if w in query.split()), 3)


def _customer_groups(text: str) -> list[str]:
    query = f" {normalize_text(text)} "
    return [group for group, terms in TERM_GROUPS.items()
            if any(f" {normalize_text(term)} " in query for term in terms)]


def detect_service_matches(text: str) -> list[dict[str, Any]]:
    """Rank a small set of active services using deterministic rules and DB fields."""
    ranked = []
    groups = _customer_groups(text)
    for service in SERVICES:
        fields = [service["name"], service.get("slug") or "", service.get("description") or "", service.get("service_type") or ""]
        score = max((_term_hits(text, str(field)) for field in fields), default=0)
        category = CATEGORY_BY_ID.get(service.get("category_id"))
        catalog_text = normalize_text(" ".join([
            str((category or {}).get("name") or ""), str((category or {}).get("slug") or ""),
            str((category or {}).get("description") or ""), *[str(x or "") for x in fields]
        ]))
        if any(any(alias in catalog_text for alias in GROUP_ALIASES[group]) for group in groups):
            score = max(score, 2)
        if score >= 2:
            ranked.append((score, service))
    ranked.sort(key=lambda item: (-item[0], item[1]["name"].casefold()))
    return [service for score, service in ranked[:5]]


def detect_category_from_text(text: str) -> list[dict[str, Any]]:
    """Rank live DB categories using deterministic text rules."""
    groups = _customer_groups(text)
    scores: dict[int, int] = {}
    for service in detect_service_matches(text):
        cid = service.get("mapped_category_id", service.get("category_id"))
        if cid in CATEGORY_BY_ID:
            scores[cid] = max(scores.get(cid, 0), 5)
    for category in CATEGORIES:
        fields = [category["name"], category.get("slug") or "", category.get("description") or ""]
        score = max((_term_hits(text, str(field)) for field in fields), default=0)
        catalog_text = normalize_text(" ".join(str(x or "") for x in fields))
        if any(any(alias in catalog_text for alias in GROUP_ALIASES[group]) for group in groups):
            score = max(score, 3)
        if score:
            scores[category["id"]] = max(scores.get(category["id"], 0), score)
    ranked = sorted(scores, key=lambda cid: (-scores[cid], CATEGORY_BY_ID[cid]["name"].casefold()))
    return [CATEGORY_BY_ID[cid] for cid in ranked]


def baseline_category_matches(category_id: int | None, category_name: str | None) -> bool:
    """Prevent displaying a historical estimate when IDs point to another category.

    If the baseline file is unavailable, let the estimator's own safeguards decide.
    If the ID exists in the baseline, its category label must match the live catalog.
    """
    baseline_path = Path(__file__).resolve().parent / "datasets" / "prepared" / "automatically_clean_duration_baseline.csv"
    if not baseline_path.exists() or category_id is None or not category_name:
        return True
    try:
        with baseline_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        id_rows = []
        for row in rows:
            raw_id = (row.get("category_id") or "").strip()
            try:
                if int(float(raw_id)) == int(category_id):
                    id_rows.append(row)
            except (TypeError, ValueError):
                continue
        if not id_rows:
            return True  # The estimator will report that no baseline is available.
        target = normalize_text(category_name)
        return any(
            normalize_text(str(row.get("detected_category") or row.get("category") or "")) == target
            for row in id_rows
        )
    except (OSError, csv.Error):
        return True


# Historical conversation-driven follow-ups. We reuse question wording from
# retrieved conversations when it is available, then use conservative local
# fallback questions. We never copy historical quotes as guaranteed answers.
GENERIC_SCOPE_QUESTIONS = [
    ("When does the problem happen?", ["All the time", "Only when using it", "Intermittently", "Not sure"]),
    ("Can you see the damaged or leaking part clearly?", ["Yes, it is visible", "Partly visible", "No, it is hidden", "Not sure"]),
    ("Do you already have the replacement part or materials?", ["Yes", "No", "Not sure"]),
    ("Is there anything else about the job our team should know?", None),
]

CATEGORY_QUESTIONS = {
    "plumbing": [
        ("When does the leak happen?", ["Only when water is running", "Even when water is off", "All the time", "Not sure"]),
        ("Where is the leak coming from?", ["Pipe or joint", "Faucet or tap", "Under the sink", "Toilet", "Another area", "Not sure"]),
        ("What type of pipe or line is involved?", ["Hot-water line", "Cold-water line", "Drain pipe", "Not sure"]),
        ("Can you safely access the leaking area?", ["Yes, it is easy to reach", "Somewhat difficult", "It is concealed", "Not sure"]),
        ("Do you have the replacement fitting or materials?", ["Yes", "No", "Not sure"]),
    ],
    "electrical": [
        ("What electrical work is needed?", ["Outlet or switch", "Light or fan", "Wiring", "Breaker or electrical panel", "Other", "Not sure"]),
        ("Is the affected electrical item currently working?", ["Yes", "No", "Works intermittently", "Not sure"]),
        ("Is this a replacement of an existing item or a new installation?", ["Replace existing", "New installation", "Repair only", "Not sure"]),
        ("Can you safely access the work area?", ["Yes", "Somewhat difficult", "No", "Not sure"]),
    ],
    "mounting": [
        ("What would you like to mount?", ["TV", "Shelf", "Mirror or picture", "Other item"]),
        ("Is a mounting bracket already available?", ["Yes", "No", "Not sure"]),
        ("What type of wall is it?", ["Drywall", "Brick or concrete", "Wood", "Not sure"]),
        ("Would you like the cables hidden?", ["Yes, inside the wall", "Yes, with a cable cover", "No", "Not applicable"]),
    ],
}


def _message_text(message: dict[str, Any]) -> str:
    value = message.get("text", message.get("content", ""))
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "").strip()


def _historical_question_candidates(matches: list[dict[str, Any]]) -> list[tuple[str, list[str] | None]]:
    """Extract actual assistant questions from retrieved historical sessions."""
    candidates: list[tuple[str, list[str] | None]] = []
    seen: set[str] = set()
    # Start with the best-ranked case only. Mixing question sequences from
    # several different jobs can create a nonsensical conversation.
    for match in matches[:1]:
        messages = match.get("conversation") or []
        if not isinstance(messages, list):
            continue
        for message in messages:
            if not isinstance(message, dict) or str(message.get("role", "")).lower() not in {"assistant", "ai"}:
                continue
            text = _message_text(message)
            if not text or len(text) > 2500:
                continue
            # Parse simple explicit suggested replies when stored in message text.
            options: list[str] = []
            option_mode = False
            question_lines: list[str] = []
            for raw_line in text.splitlines():
                line = raw_line.strip().strip("-*• ")
                if not line:
                    continue
                if re.search(r"suggested\s*(repl|answer|option)|choose one|options?:", line, re.I):
                    option_mode = True
                    inline = re.split(r":", line, maxsplit=1)
                    if len(inline) == 2 and inline[1].strip():
                        options.extend([x.strip(" -*•") for x in re.split(r"\s*[|;]\s*|\s{2,}", inline[1]) if x.strip()])
                    continue
                if option_mode and len(line) < 100 and not "?" in line:
                    options.append(line)
                    continue
                if "?" in line:
                    question_lines.extend(re.findall(r"[^?]{4,180}\?", line))
            # If there is one clean question in a message, use it. Avoid assistant
            # messages with many questions because historical extraction can pair
            # one customer answer with several questions incorrectly.
            if len(question_lines) == 1:
                question = clean_historical_question(re.sub(r"\s+", " ", question_lines[0]).strip())
                key = normalize_text(question)
                if key and key not in seen:
                    clean_options = []
                    for option in options:
                        option = re.sub(r"\s+", " ", option).strip()
                        if 1 < len(option) < 70 and normalize_text(option) not in {normalize_text(x) for x in clean_options}:
                            clean_options.append(option)
                    candidates.append((question, clean_options[:6] or None))
                    seen.add(key)
    return candidates


def make_followups(category: dict[str, Any] | None, matches: list[dict[str, Any]], job_text: str) -> list[tuple[str, list[str] | None]]:
    """Build a context-aware local question plan from the request and prior answers.

    Historical cases inform the initial task interpretation, but their question
    sequences are not blindly copied: that previously caused questions/options
    from a different job to leak into the current conversation.
    """
    context = normalize_text(job_text)
    category_name = normalize_text((category or {}).get("name", ""))
    groups = _customer_groups(job_text)
    asked = {
        normalize_text(q) for q in st.session_state.get("asked_question_texts", [])
    }
    answered = st.session_state.get("answers", [])
    answered_topics = " ".join(
        normalize_text(f"{item.get('question', '')} {item.get('answer', '')}")
        for item in answered if isinstance(item, dict)
    )
    all_context = f"{context} {answered_topics}"

    def has_any(*terms: str) -> bool:
        return any(normalize_text(term) in all_context for term in terms)

    candidates: list[tuple[str, list[str] | None]] = []

    is_plumbing = "plumbing" in category_name or "plumbing" in groups or any(
        term in all_context for term in ("leak", "pipe", "faucet", "tap", "drain", "toilet", "water heater")
    )
    is_electrical = "electric" in category_name or "electrical" in groups or any(
        term in all_context for term in ("wiring", "outlet", "breaker", "electrical panel", "light fixture", "ceiling fan")
    )
    is_mounting = "mount" in category_name or "mounting" in groups or any(
        term in all_context for term in ("tv", "television", "wall mount", "mounting", "mount a")
    )

    if is_plumbing:
        # Ask for the highest-value missing detail first. Answer wording and
        # earlier answers suppress questions whose topic is already covered.
        if any(x in all_context for x in ("leak", "leaking", "drip", "water coming")):
            if not has_any("only when water is running", "when water runs", "water is turned off", "leaks all the time", "leak happens", "leak occur", "intermittently"):
                candidates.append(("When does the leak happen?", ["Only when water is running", "Even when water is turned off", "It leaks continuously", "Intermittently", "I'm not sure"]))
            if not has_any("from the joint", "connection or joint", "pipe joint", "joint is leaking", "pipe is cracked", "crack or hole", "from a crack", "faucet", "under the sink", "toilet", "drain", "water heater", "leak source", "coming from"):
                candidates.append(("Where does the water appear to be coming from?", ["A pipe connection or joint", "A crack or hole in the pipe", "A faucet or tap", "Under the sink", "Another area", "I'm not sure"]))
            # Branch based on what the customer said about the source.
            if any(x in all_context for x in ("crack or hole", "pipe is cracked", "from a crack", "cracked pipe")):
                if not has_any("visible", "hidden", "concealed", "easy to reach", "access the", "accessible"):
                    candidates.append(("Can you see and safely reach the cracked section?", ["Yes, it's visible and easy to reach", "I can see it but access is difficult", "It's hidden or concealed", "I'm not sure"]))
            elif any(x in all_context for x in ("from the joint", "connection or joint", "pipe connection", "fitting")):
                if not has_any("hot water", "cold water", "drain pipe", "supply line", "hot-water line", "cold-water line"):
                    candidates.append(("Which type of pipe or line is leaking?", ["Hot-water line", "Cold-water supply line", "Drain pipe", "I'm not sure"]))
            else:
                if not has_any("hot water", "cold water", "drain pipe", "supply line", "hot-water line", "cold-water line"):
                    candidates.append(("Do you know what type of pipe or line it is?", ["Hot-water line", "Cold-water supply line", "Drain pipe", "I'm not sure"]))
            if not has_any("easy to access", "difficult to access", "hidden or concealed", "can safely access", "access is", "easy to reach", "access difficult"):
                candidates.append(("Is the leaking area easy to reach?", ["Yes, easy to reach", "Somewhat difficult to reach", "Hidden behind a wall or cabinet", "I'm not sure"]))
            if not has_any("have the parts", "have the materials", "need them supplied", "replacement fitting", "materials available", "parts/materials"):
                candidates.append(("Do you already have the replacement parts or materials?", ["Yes, I have them", "No, they need to be supplied", "I'm not sure"]))
        else:
            candidates.extend([
                ("Which plumbing item needs attention?", ["Pipe or joint", "Faucet or tap", "Sink or drain", "Toilet", "Water heater", "Another item"]),
                ("Can you describe what is happening with it?", None),
                ("Is the work area easy to access?", ["Yes", "Somewhat difficult", "Hidden or concealed", "I'm not sure"]),
            ])

    elif is_mounting:
        if not has_any("tv", "television", "mount a tv", "mount tv", "mount the tv", "mounting a tv", "mount television", "television mounted", "mount a television", "tv mounting"):
            candidates.append(("What would you like to mount?", ["TV", "Shelf", "Mirror or picture", "Other item", "I'm not sure"]))
        if not has_any("living room", "bedroom", "kitchen", "office", "another room", "in the room", "which room"):
            candidates.append(("Which room should the item be installed in?", ["Living room", "Bedroom", "Office", "Another room", "I'm not sure"]))
        if not has_any("bracket already", "existing mount", "have a mount", "mount is available", "no mount", "mounting bracket"):
            candidates.append(("Do you already have a compatible mounting bracket?", ["Yes, I have one", "No, I need one", "I'm not sure"]))
        if not has_any("drywall", "plasterboard", "brick", "concrete", "wooden wall", "wood wall", "wall material", "type of wall"):
            candidates.append(("What is the wall made of, if you know?", ["Drywall or plasterboard", "Brick or concrete", "Wood", "I'm not sure"]))
        if not has_any("hide the cables", "hide cables", "cables hidden", "cable concealment", "inside the wall", "cable cover", "visible cables", "cables behind"):
            candidates.append(("Would you like the cables concealed?", ["Yes, inside the wall", "Yes, using a cable cover", "No, visible cables are fine", "Not applicable", "I'm not sure"]))

    elif is_electrical:
        if not has_any("outlet", "socket", "switch", "light", "fan", "wiring", "breaker", "electrical panel", "circuit panel"):
            candidates.append(("What electrical item or area needs work?", ["Outlet or switch", "Light or fan", "Wiring", "Breaker or electrical panel", "Other", "I'm not sure"]))
        if any(x in all_context for x in ("panel", "breaker", "wiring", "sparks", "burning smell", "power keeps")):
            candidates.append(("Is there any immediate safety concern, such as sparks, smoke, or a burning smell?", ["Yes", "No", "I'm not sure"]))
        if not has_any("replace existing", "new installation", "repair only", "already installed", "replacement"):
            candidates.append(("Is this a repair, replacement, or new installation?", ["Repair existing equipment", "Replace existing equipment", "Install something new", "I'm not sure"]))
        if not has_any("easy to access", "difficult to access", "access the", "accessible"):
            candidates.append(("Can the work area be accessed easily?", ["Yes", "Somewhat difficult", "No", "I'm not sure"]))

    else:
        candidates.extend([
            ("What exactly needs to be repaired, installed, or improved?", None),
            ("How many items or areas are involved?", ["One", "Two", "Three or more", "Not sure"]),
            ("How easy is it to access the work area?", ["Easy to access", "Somewhat restricted", "Difficult or concealed", "Not sure"]),
            ("Are any parts or materials already available?", ["Yes", "No", "Not sure"]),
        ])

    # Keep only unanswered questions. Don't pull questions from unrelated
    # historical cases into this job; retrieved cases are evidence, not scripts.
    result: list[tuple[str, list[str] | None]] = []
    for question, options in candidates:
        key = normalize_text(question)
        if not key or key in asked:
            continue
        result.append((question, options))
    return result[:5]



def clean_historical_question(question: str) -> str:
    """Remove numbering/markdown fragments accidentally retained from chat JSON."""
    value = re.sub(r"^\s*(?:question\s*)?\d+\s*/\s*\d+\s*[:.)\-*]*\s*", "", str(question), flags=re.I)
    value = re.sub(r"^\s*[*_`#]+\s*", "", value)
    value = re.sub(r"\s*[*_`]+\s*$", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def infer_answer_options(question: str, category: dict[str, Any] | None, job_text: str) -> list[str] | None:
    """Return choices that answer the actual question, not merely its topic."""
    q = normalize_text(question)
    category_name = normalize_text((category or {}).get("name", ""))
    combined = f"{q} {normalize_text(job_text)}"

    # Specific question intent must be checked before broad topic keywords.
    # For example, a question about WHICH WALL must not offer item types.
    if any(phrase in q for phrase in (
        "which wall", "what wall", "where on the wall", "which part of the wall",
    )):
        return [
            "The wall opposite the seating area",
            "The wall above existing furniture",
            "A different wall — I'll describe it",
            "I'm not sure yet",
        ]

    if any(phrase in q for phrase in (
        "which room", "what room", "where would you like the tv installed",
        "where would you like it installed", "which room is it in",
    )):
        return ["Living room", "Bedroom", "Another room", "I'm not sure"]

    if any(phrase in q for phrase in (
        "what would you like to mount", "what item needs mounting",
        "what item would you like to mount", "what are you mounting",
    )):
        return ["TV", "Shelf", "Mirror or picture", "Other item", "I'm not sure"]

    if any(phrase in q for phrase in ("type of wall", "wall made of", "wall material")):
        return ["Drywall/plasterboard", "Brick or concrete", "Wood", "I'm not sure"]

    if "safety concern" in q or "sparks" in q or "burning smell" in q:
        return ["Yes", "No", "I'm not sure"]

    if any(phrase in q for phrase in (
        "connection", "fitting", "joint", "crack", "hole in the pipe",
        "where is the leak coming from", "where is the leak coming",
    )):
        return [
            "From the connection or joint",
            "From a crack or hole in the pipe",
            "From somewhere else",
            "I'm not sure",
        ]

    if "when" in q and any(term in combined for term in ("leak", "water", "drip", "pipe")):
        return ["Only when water is running", "Even when water is turned off", "It leaks all the time", "I'm not sure"]

    if any(term in q for term in ("type of pipe", "which pipe", "pipe or line")):
        return ["Hot-water line", "Cold-water line", "Drain pipe", "I'm not sure"]

    if any(term in q for term in ("access", "reach", "accessible", "work area")):
        return ["Easy to access", "Somewhat difficult to access", "Hidden or concealed", "I'm not sure"]

    if any(term in q for term in ("material", "replacement part", "parts available", "already have")):
        return ["Yes, I have the parts/materials", "No, I need them supplied", "I'm not sure"]

    if any(term in q for term in ("hide the cables", "cable hidden", "cables hidden", "hide cables", "cable concealment")):
        return ["Yes, inside the wall", "Yes, with a cable cover", "No, visible cables are fine", "Not applicable", "I'm not sure"]

    if any(term in q for term in ("replace", "repair", "install", "new or existing")):
        return ["Repair an existing item", "Replace an existing item", "Install something new", "I'm not sure"]

    if "plumb" in category_name or "plumb" in combined:
        return ["Pipe or joint", "Faucet or tap", "Sink or drain", "Toilet", "Another area", "I'm not sure"]

    if "electric" in category_name or "electric" in combined:
        return ["Outlet or switch", "Light or fan", "Wiring", "Electrical panel or breaker", "Other", "I'm not sure"]

    if any(term in q for term in ("what", "which", "where", "how many", "does", "do you", "is there", "can you")):
        return ["Yes", "No", "I'm not sure"]
    return None


def init_state():
    defaults = {
        "stage": "intake", "chat_history": [], "job_text": "",
        "attached_images": [], "pending_images": [], "vision_results": [], "vision_warning": "",
        "category_id": None, "category_confirmed": False, "question_index": 0,
        "answers": [], "scope_notes": "", "duration_result": None,
        "readiness_result": None, "selected_service_id": None,
        "historical_matches": [], "history_query": "",
        "adaptive_questions": [], "asked_question_texts": [],
        "other_answer_mode": False,
        "pending_text_category_id": None, "pending_vision_category_id": None,
        "pending_text_group": "", "pending_vision_group": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def add_message(role: str, content: str, images: list[dict] | None = None):
    st.session_state.chat_history.append({"role": role, "content": content, "images": images or []})


def reset_flow():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_state()


def current_category():
    return CATEGORY_BY_ID.get(st.session_state.category_id)


def current_services():
    category = current_category()
    return SERVICES_BY_CATEGORY.get(category["id"], []) if category else []


def current_questions():
    questions = st.session_state.get("adaptive_questions", [])
    if questions:
        return questions
    return make_followups(
        current_category(),
        st.session_state.get("historical_matches", []),
        st.session_state.get("job_text", ""),
    )


def build_scope():
    parts = [st.session_state.job_text.strip()]
    category = current_category()
    if category:
        parts.append(f"Customer-confirmed category: {category['name']}.")
    service_id = st.session_state.selected_service_id
    service = next((s for s in SERVICES if s["id"] == service_id), None)
    if service:
        parts.append(f"Selected database service: {service['name']}.")
        if service.get("description"):
            parts.append("Service description: " + service["description"])
    for item in st.session_state.answers:
        if item["answer"].strip():
            parts.append(f"{item['question']} {item['answer']}")
    if st.session_state.scope_notes.strip():
        parts.append("Additional details: " + st.session_state.scope_notes.strip())
    return "\n".join(p for p in parts if p)


def render_photo_strip(images: list[dict[str, Any]], *, use_uploaded_files: bool = False):
    """Render small, consistent photo previews without large vertical images."""
    if not images:
        return
    chips = []
    for item in images:
        try:
            if use_uploaded_files:
                name = item.name
                preview = Image.open(BytesIO(item.getvalue())).convert("RGB")
                preview.thumbnail((176, 136))
                preview_buffer = BytesIO()
                preview.save(preview_buffer, format="JPEG", quality=78, optimize=True)
                raw = preview_buffer.getvalue()
            else:
                raw = item.get("thumbnail", b"")
                name = item.get("name", "Photo")
            if not raw:
                continue
            encoded = base64.b64encode(raw).decode("ascii")
            safe_name = (str(name).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))
            chips.append(
                '<div class="photo-chip"><img src="data:image/jpeg;base64,' + encoded +
                '" alt="Uploaded photo"><div class="photo-name">' + safe_name + '</div></div>'
            )
        except Exception:
            continue
    if chips:
        st.markdown('<div class="photo-strip">' + ''.join(chips) + '</div>', unsafe_allow_html=True)


def add_images(files):
    existing = {item["name"] + str(item["size"]) for item in st.session_state.attached_images}
    added = []
    for file in files or []:
        key = file.name + str(file.size)
        if key in existing:
            continue
        try:
            image = Image.open(BytesIO(file.getvalue())).convert("RGB")
            thumb = image.copy()
            thumb.thumbnail((180, 130))
            buf = BytesIO()
            thumb.save(buf, format="JPEG", quality=82)
            item = {"name": file.name, "size": file.size, "image": image, "thumbnail": buf.getvalue()}
            st.session_state.attached_images.append(item)
            added.append(item)
            existing.add(key)
        except Exception:
            st.warning(f"Sorry, I couldn't open {file.name}. Please try another image.")
    return added



@st.cache_resource(show_spinner=False)
def load_local_clip_classifier():
    """Load the local Hugging Face CLIP model once per Streamlit process."""
    from transformers import pipeline
    return pipeline(
        task="zero-shot-image-classification",
        model="openai/clip-vit-base-patch32",
        device=-1,  # This project currently uses CPU-only PyTorch.
    )


VISION_LABELS = [
    "a photo of a leaking water pipe or plumbing joint",
    "a photo of a leaking faucet or sink",
    "a photo of a floor drain with standing water",
    "a photo of a toilet, shower, or bathroom plumbing problem",
    "a photo of an electrical panel or circuit breaker",
    "a photo of electrical wiring, an outlet, or a light fixture",
    "a photo of a television mounted on a wall",
    "a photo of a shelf, mirror, or other item being mounted on a wall",
    "a photo of furniture assembly, a cabinet, or carpentry work",
    "a photo of a damaged wall, ceiling, door, or general home repair",
    "a photo of painting or repainting a wall",
    "a photo of an air conditioner or HVAC equipment",
    "a photo of a household appliance needing repair",
    "a photo of a kitchen or bathroom renovation",
    "a photo unrelated to home repair",
]


def _follow_up_for_visual_label(label: str) -> str:
    value = normalize_text(label)
    if any(word in value for word in ("pipe", "plumbing", "faucet", "sink", "drain", "toilet", "bathroom")):
        return "Where does the water appear to be coming from?"
    if any(word in value for word in ("electrical", "wiring", "outlet", "panel", "breaker", "light fixture")):
        return "What electrical item or area needs work?"
    if any(word in value for word in ("television", "shelf", "mirror", "mounted", "mounting")):
        return "What would you like to mount, and is the mounting bracket already available?"
    if any(word in value for word in ("air conditioner", "hvac")):
        return "What problem are you noticing with the air conditioner or HVAC equipment?"
    if "appliance" in value:
        return "Which appliance needs attention, and what is it doing?"
    if any(word in value for word in ("painting", "wall")):
        return "What repair or improvement would you like done to the wall?"
    return "What would you like our handyman team to repair, install, or inspect?"


def analyze_uploaded_images_with_gemini(images: list[dict[str, Any]], customer_description: str = "") -> dict[str, Any]:
    """Backward-compatible function name; performs local CLIP inference, no API key."""
    valid_images = [item.get("image") for item in images[:4] if item.get("image") is not None]
    if not valid_images:
        return {"ok": False, "reason": "no_valid_images", "message": "No readable photos were available for image analysis."}
    try:
        classifier = load_local_clip_classifier()
        # Classify each photo separately. Keep the first result as the primary
        # result for backward compatibility, while exposing every photo's result
        # so mixed-service uploads are not silently treated as one job.
        per_image_results = []
        for image_index, image in enumerate(valid_images, start=1):
            image_predictions = classifier(image.convert("RGB"), candidate_labels=VISION_LABELS)
            if not image_predictions:
                continue
            image_top = image_predictions[0]
            image_label = str(image_top.get("label", "")).strip()
            image_score = float(image_top.get("score", 0.0))
            per_image_results.append({
                "image_index": image_index,
                "label": image_label,
                "score": image_score,
                "top_predictions": [
                    {"label": str(pred.get("label", "")), "score": float(pred.get("score", 0.0))}
                    for pred in image_predictions[:3]
                ],
            })
        if not per_image_results:
            return {"ok": False, "reason": "empty_predictions", "message": "The image model did not return a usable suggestion. You can continue by text."}
        top = {"label": per_image_results[0]["label"], "score": per_image_results[0]["score"]}
        predictions = [{"label": x["label"], "score": x["score"]} for x in per_image_results[0]["top_predictions"]]
        label = str(top["label"]).strip()
        score = float(top["score"])
        # Scores are relative to the candidate labels, not calibrated probabilities.
        if not label or normalize_text(label) == normalize_text("a photo unrelated to home repair"):
            likely_area = ""
            confidence = "low"
        else:
            likely_area = label
            confidence = "medium" if score >= 0.30 else "low"
        summary = label.replace("a photo of ", "The photo appears to show ").replace("a photo unrelated to home repair", "a scene that may not clearly match a home-repair category")
        observations = [summary]
        if len(valid_images) > 1:
            observations.append(f"Analysed {len(per_image_results)} photo(s) separately. If they show different jobs, please tell Leo which job to focus on.")
        return {
            "ok": True,
            "provider": "Local Hugging Face CLIP",
            "model": "openai/clip-vit-base-patch32",
            "image_summary": summary,
            "visible_observations": observations,
            "likely_service_area": likely_area,
            "confidence": confidence,
            "score": score,
            "top_predictions": [{"label": str(p.get("label", "")), "score": float(p.get("score", 0.0))} for p in predictions[:5]],
            "per_image_results": per_image_results,
            "limitations": "This is relative image-label matching, not a diagnosis. It cannot confirm the source of damage, hidden faults, safety, price, or labour time.",
            "suggested_follow_up": _follow_up_for_visual_label(likely_area or label),
        }
    except Exception as exc:
        return {
            "ok": False,
            "reason": "local_model_error",
            "message": f"Local image analysis failed ({type(exc).__name__}: {exc}). Check model download and Transformers/PyTorch compatibility; the customer can continue by text.",
        }


def _category_id_from_vision(result: dict[str, Any]) -> int | None:
    """Only accept a vision category that exactly matches an active database category."""
    proposed = normalize_text(str(result.get("likely_service_area", "")))
    if not proposed:
        return None
    for category in CATEGORIES:
        if proposed in {normalize_text(str(category.get("name", ""))), normalize_text(str(category.get("slug", "")))}:
            return category["id"]
    # CLIP labels are descriptions, not database category names. Match only clear
    # service-family words to a live category's name/slug/description.
    cue_groups = {
        "plumbing": ("pipe", "plumbing", "faucet", "sink", "drain", "toilet", "water heater"),
        "electrical": ("electrical", "wiring", "outlet", "circuit breaker", "electrical panel", "light fixture"),
        "hvac": ("air conditioner", "hvac", "heating", "cooling"),
        "mounting": ("television", "tv mounted", "mounted on a wall", "mounting on a wall", "shelf", "mirror"),
        "carpentry": ("carpentry", "furniture assembly", "cabinet"),
        "painting": ("painting", "repainting"),
        "appliance": ("appliance",),
    }
    group = next((name for name, cues in cue_groups.items() if any(cue in proposed for cue in cues)), None)
    if group:
        for category in CATEGORIES:
            cat_text = normalize_text(" ".join(str(category.get(k) or "") for k in ("name", "slug", "description")))
            aliases = GROUP_ALIASES.get(group, (group,))
            if any(alias in cat_text for alias in aliases) or group in normalize_text(category.get("name", "")):
                return category["id"]
    return None


def _vision_context_text(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return ""
    label = str(result.get("likely_service_area", "")).strip()
    parts = ["Local CLIP visual suggestion (not a confirmed diagnosis): " + label] if label else []
    observations = result.get("visible_observations", [])
    if observations:
        parts.append("Visual description (not a confirmed diagnosis): " + "; ".join(observations))
    if result.get("limitations"):
        parts.append("Image limitations: " + str(result["limitations"]))
    return "\n".join(x for x in parts if x.strip())

def retrieve_context_for_request(text: str) -> list[dict[str, Any]]:
    """Retrieve historical examples locally; never treat them as verified truth."""
    query = (text or "").strip()
    if not query:
        return []
    try:
        return retrieve_historical_cases(query, limit=5)
    except FileNotFoundError:
        return []
    except Exception as exc:
        # Retrieval is optional; it must not prevent a customer from continuing.
        st.session_state["retrieval_warning"] = str(exc)
        return []



def greeting_message() -> str:
    hour_now = datetime.now(ZoneInfo("Asia/Kolkata")).hour

    salutation = (
        "Good morning" if 5 <= hour_now < 12
        else "Good afternoon" if 12 <= hour_now < 17
        else "Good evening"
    )

    return (
        f"{salutation}, and welcome to Star Handyman! 👋\n\n"
        "I’m Leo, your service assistant. I can help you describe a repair, installation, "
        "or home-improvement job, find the closest service, and gather the details our team "
        "needs to review your request.\n\n"
        "**How can I help today?** Tell me what you need done, or upload a photo and add a short note. "
        "I’ll ask a few relevant follow-up questions as we go."
    )


def _service_group_from_label(value: str) -> str:
    """Map a category/vision label to a broad service family for conflict checks."""
    text = normalize_text(value)
    checks = [
        ("plumbing", ("plumbing", "pipe", "leak", "faucet", "tap", "sink", "drain", "toilet", "water heater")),
        ("electrical", ("electrical", "electric", "wiring", "outlet", "socket", "breaker", "circuit", "light fixture")),
        ("hvac", ("hvac", "air conditioner", "air conditioning", "heating", "cooling", "thermostat")),
        ("mounting", ("mounting", "mount", "television", "tv", "shelf", "mirror", "picture hanging")),
        ("carpentry", ("carpentry", "cabinet", "woodwork", "furniture assembly", "door repair")),
        ("painting", ("painting", "paint", "repainting")),
        ("appliance", ("appliance", "refrigerator", "washer", "dryer", "dishwasher", "oven")),
        ("cleaning", ("cleaning", "pressure washing", "stain removal")),
    ]
    for group, cues in checks:
        if any(cue in text for cue in cues):
            return group
    return ""


def _primary_text_group(text: str, category_matches: list[dict[str, Any]]) -> str:
    """Infer the main group from customer-authored text only, never from image notes."""
    if category_matches:
        group = _service_group_from_label(" ".join([
            str(category_matches[0].get("name", "")),
            str(category_matches[0].get("slug", "")),
            str(category_matches[0].get("description", "")),
        ]))
        if group:
            return group
    groups = _customer_groups(text)
    return groups[0] if groups else ""


def _vision_group(result: dict[str, Any]) -> str:
    """Infer a broad service group from the top local image label."""
    if not result.get("ok"):
        return ""
    return _service_group_from_label(str(result.get("likely_service_area", "")))


def _start_selected_category(category_id: int | None) -> None:
    """Continue the normal flow after the customer resolves an image/text conflict."""
    st.session_state.category_id = category_id if category_id in CATEGORY_BY_ID else None
    st.session_state.category_confirmed = False
    st.session_state.answers = []
    st.session_state.asked_question_texts = []
    st.session_state.question_index = 0
    st.session_state.selected_service_id = None
    if st.session_state.category_id is None:
        st.session_state.stage = "choose_service"
        return
    st.session_state.adaptive_questions = make_followups(
        current_category(), st.session_state.get("historical_matches", []),
        st.session_state.get("job_text", ""),
    )
    st.session_state.stage = "confirm_category"


def process_customer_message():
    text = st.session_state.get("message_input", "").strip()
    with st.spinner("Preparing your photo(s)…"):
        new_images = add_images(st.session_state.get("image_upload_widget", []))
    if not text and not st.session_state.attached_images:
        st.warning("Please describe the work or attach a photo.")
        return

    if text:
        add_message("user", text)
        st.session_state.job_text = (st.session_state.job_text + "\n" + text).strip()
    if new_images:
        add_message("user", f"I've attached {len(new_images)} photo(s).", [
            {"name": i["name"], "thumbnail": i["thumbnail"]} for i in new_images
        ])

    # Analyse newly uploaded photos, but keep image labels separate from customer text.
    # This prevents image-derived words from contaminating text-based category matching.
    st.session_state.vision_results = []
    if new_images:
        with st.spinner("Leo is analysing the uploaded photo(s) locally..."):
            vision_result = analyze_uploaded_images_with_gemini(new_images, text)
        st.session_state.vision_results = [vision_result]
        if not vision_result.get("ok"):
            st.session_state["vision_warning"] = vision_result.get(
                "message", "Image analysis is currently unavailable."
            )
        else:
            st.session_state["vision_warning"] = ""

    customer_text = st.session_state.job_text.strip()
    st.session_state.historical_matches = retrieve_context_for_request(customer_text)
    st.session_state.history_query = customer_text

    # Both text matching and service matching use customer-authored text only.
    text_matches = detect_category_from_text(customer_text)
    service_matches = detect_service_matches(customer_text)
    text_ids = [c["id"] for c in text_matches]
    text_category_id = text_ids[0] if text_ids else None

    vision_result = next(
        (v for v in st.session_state.vision_results if v.get("ok")), None
    )
    vision_category_id = _category_id_from_vision(vision_result) if vision_result else None
    text_group = _primary_text_group(text, text_matches) if text else ""
    vision_group = _vision_group(vision_result) if vision_result else ""

    # If text and image point to different service families, do not silently choose.
    if text and vision_result and text_group and vision_group and text_group != vision_group:
        st.session_state.pending_text_category_id = text_category_id
        st.session_state.pending_vision_category_id = vision_category_id
        st.session_state.pending_text_group = text_group
        st.session_state.pending_vision_group = vision_group
        add_message(
            "assistant",
            "Your written description and photo may refer to different jobs. "
            f"Your text suggests **{text_group.replace('_', ' ')}**, while the photo's initial visual suggestion is **{vision_group.replace('_', ' ')}**. "
            "The photo is only a suggestion, not a confirmed diagnosis. Which should we focus on?"
        )
        st.session_state.category_id = None
        st.session_state.category_confirmed = False
        st.session_state.stage = "resolve_conflict"
        return

    # If multiple photos appear to show different service families and the
    # customer gave no written description, ask which job to focus on instead
    # of silently using only the first photo.
    if not text and vision_result:
        image_groups = []
        for image_result in vision_result.get("per_image_results", []):
            group = _service_group_from_label(image_result.get("label", ""))
            if group:
                image_groups.append((image_result.get("image_index", 0), group, image_result.get("label", "")))
        unique_groups = list(dict.fromkeys(group for _, group, _ in image_groups))
        if len(unique_groups) > 1:
            st.session_state.pending_image_groups = image_groups
            st.session_state.stage = "resolve_image_conflict"
            add_message(
                "assistant",
                "The photos may show different types of work. I checked each photo separately, but I don't want to assume they belong to one job. Please choose the photo/service you want to discuss first."
            )
            return

    # Prefer a category found from customer text. Use the photo only if text is absent/ambiguous.
    proposed_id = text_category_id
    if proposed_id is None and vision_result:
        proposed_id = vision_category_id
    if proposed_id is None and service_matches:
        linked_ids = [
            item.get("mapped_category_id", item.get("category_id"))
            for item in service_matches
            if item.get("mapped_category_id", item.get("category_id")) in CATEGORY_BY_ID
        ]
        if linked_ids:
            proposed_id = linked_ids[0]

    if proposed_id:
        category = CATEGORY_BY_ID[proposed_id]
        st.session_state.category_id = proposed_id
        similar = st.session_state.historical_matches
        context_hint = " I’ll use similar past requests as reference while we clarify the details." if similar else ""
        vision_hint = (
            " I also reviewed your photo; that visual suggestion is not a confirmed diagnosis."
            if vision_result else ""
        )
        add_message(
            "assistant",
            f"Thanks for explaining that! This sounds like **{category['name']}** work.{context_hint}{vision_hint} "
            "Is that the right service area, or should we look at another one?"
        )
    else:
        st.session_state.category_id = None
        add_message(
            "assistant",
            "Thanks for reaching out! I’d like to understand the job before suggesting a service. "
            "What needs to be repaired, installed, assembled, cleaned, or improved? If you’re not sure how to describe it, a photo and a short note are a great start."
        )

    st.session_state.category_confirmed = False
    st.session_state.adaptive_questions = make_followups(
        CATEGORY_BY_ID.get(proposed_id) if proposed_id else None,
        st.session_state.historical_matches,
        customer_text,
    )
    # Add a useful visual follow-up only as a question; do not add visual labels to the customer's job text.
    vision_followups = [
        v.get("suggested_follow_up", "").strip()
        for v in st.session_state.vision_results if v.get("ok")
    ]
    for vision_question in vision_followups:
        if vision_question and "?" in vision_question:
            known_text = normalize_text(customer_text)
            question_terms = set(normalize_text(vision_question).split())
            meaningful_terms = {word for word in question_terms if len(word) > 3}
            if meaningful_terms and not meaningful_terms.issubset(set(known_text.split())):
                already_present = any(
                    normalize_text(q) == normalize_text(vision_question)
                    for q, _ in st.session_state.adaptive_questions
                )
                if not already_present:
                    st.session_state.adaptive_questions.insert(0, (vision_question, None))
            break

    st.session_state.asked_question_texts = []
    st.session_state.answers = []
    st.session_state.question_index = 0
    st.session_state.stage = "confirm_category"


init_state()
if not st.session_state.chat_history:
    add_message("assistant", greeting_message())

if st.session_state.get("retrieval_warning"):
    with st.expander("Historical retrieval diagnostic"):
        st.caption("Historical search could not be completed; the chat can still continue.")
        st.code(st.session_state["retrieval_warning"])

if st.session_state.get("vision_warning"):
    st.warning(st.session_state["vision_warning"])

if st.session_state.get("vision_results"):
    for vision_result in st.session_state["vision_results"]:
        if vision_result.get("ok"):
            with st.expander("Photo analysis · Leo's visual observations", expanded=False):
                st.write("**Summary:**", vision_result.get("image_summary") or "No summary returned.")
                if vision_result.get("visible_observations"):
                    st.write("**Visible observations:**")
                    for observation in vision_result["visible_observations"]:
                        st.write(f"- {observation}")
                st.write("**Suggested service area (first photo):**", vision_result.get("likely_service_area") or "Not confident enough to suggest one")
                per_image = vision_result.get("per_image_results", [])
                if len(per_image) > 1:
                    st.write("**Photo-by-photo suggestions:**")
                    for image_result in per_image:
                        st.write(f"Photo {image_result['image_index']}: {image_result['label']} · {image_result['score']:.1%} relative score")
                st.write("**Confidence band:**", vision_result.get("confidence", "low"))
                if vision_result.get("top_predictions"):
                    st.write("**Other possible visual matches:**")
                    for prediction in vision_result["top_predictions"][:5]:
                        st.write(f"- {prediction['label']}: {prediction['score']:.1%} relative score")
                st.caption("Scores are relative to candidate labels, not calibrated probabilities. Visual analysis is only an initial suggestion; it cannot confirm hidden damage, exact cause, safety, price, or labour time.")

if DB_ERROR:
    st.error("I couldn't load the service catalog from the database. Please check the database connection and try again.")
    with st.expander("Technical details"):
        st.code(DB_ERROR)
elif not CATEGORIES:
    st.warning("No active categories were returned by the database. Please check the categories table.")
else:
    st.caption(f"Using live service catalog · {len(CATEGORIES)} active categories · {len(SERVICES)} active services")

# Render current session conversation. It is not persisted to the DB.
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"], avatar="🛠️" if msg["role"] == "assistant" else "🙂"):
        st.markdown(msg["content"])
        render_photo_strip(msg.get("images", []))

if st.session_state.stage == "intake":
    st.markdown("### How can we help today?")
    st.caption("Describe the job in your own words, choose a starting point below, or upload a photo. You can edit any suggested text before sending it.")

    quick_starts = [
        ("🚰 Plumbing or leak", "I need help with a plumbing issue or leak."),
        ("💡 Electrical", "I need help with an electrical issue."),
        ("📺 TV or wall mounting", "I need help mounting a TV or another item on a wall."),
        ("🛠️ General repair", "I need help repairing something at home."),
    ]
    quick_cols = st.columns(2)
    for i, (label, prompt) in enumerate(quick_starts):
        with quick_cols[i % 2]:
            if st.button(label, key=f"quick_start_{i}", use_container_width=True):
                st.session_state["message_input"] = prompt
                st.rerun()

    with st.container(border=True):
        st.file_uploader("Add photos (optional)", type=["jpg", "jpeg", "png", "webp"],
                         accept_multiple_files=True, key="image_upload_widget")
        pending = st.session_state.get("image_upload_widget", [])
        if pending:
            st.caption(f"{len(pending)} photo(s) selected · previews are kept compact")
            render_photo_strip(pending, use_uploaded_files=True)
            st.caption("Photo analysis starts when you select **Send to Leo**. A loading indicator will appear while the photos are prepared and analysed.")
        st.text_area("Your message", placeholder="For example: A hot-water pipe is leaking near a joint, and I need help getting it repaired.",
                     height=90, key="message_input")
        if st.button("Send to Leo ➤", type="primary", use_container_width=True):
            process_customer_message()
            st.rerun()

elif st.session_state.stage == "resolve_image_conflict":
    st.markdown("### Which job should we focus on?")
    st.caption("The image labels are suggestions only. Select the photo that best represents the job you want help with.")
    for image_index, group, label in st.session_state.get("pending_image_groups", []):
        if st.button(f"Photo {image_index}: {group.replace('_', ' ').title()}", key=f"choose_image_job_{image_index}_{group}", use_container_width=True):
            selected_label = label
            selected_group = group
            add_message("user", f"Please focus on photo {image_index}: {selected_group.replace('_', ' ')}.")
            st.session_state.job_text = (st.session_state.job_text + f"\nCustomer selected photo {image_index} for {selected_group.replace('_', ' ')} work.").strip()
            st.session_state.vision_results = [dict(st.session_state.vision_results[0], likely_service_area=selected_label)]
            st.session_state.pending_image_groups = []
            st.session_state.stage = "intake"
            st.session_state["message_input"] = f"I need help with {selected_group.replace('_', ' ')} work shown in photo {image_index}."
            st.rerun()
    if st.button("These photos are part of one job / something else", key="image_conflict_other", use_container_width=True):
        st.session_state.pending_image_groups = []
        st.session_state.stage = "intake"
        st.session_state["message_input"] = "The photos are part of one job or need a different service. Please help me identify it."
        st.rerun()

elif st.session_state.stage == "resolve_conflict":
    text_group = st.session_state.get("pending_text_group", "your written description").replace("_", " ")
    vision_group = st.session_state.get("pending_vision_group", "the photo suggestion").replace("_", " ")
    st.markdown("### Let's clarify the service")
    st.write(f"Your message suggests **{text_group}**. The photo's initial suggestion is **{vision_group}**.")
    st.caption("Image labels can be wrong. Choose the job you actually need help with; we won't treat the photo as a confirmed diagnosis.")
    text_col, photo_col = st.columns(2)
    with text_col:
        if st.button(f"Use my text: {text_group.title()}", type="primary", use_container_width=True, key="resolve_use_text"):
            add_message("user", f"Please focus on my written description: {text_group}.")
            _start_selected_category(st.session_state.get("pending_text_category_id"))
            st.session_state.pending_text_category_id = None
            st.session_state.pending_vision_category_id = None
            st.rerun()
    with photo_col:
        if st.button(f"Use photo suggestion: {vision_group.title()}", use_container_width=True, key="resolve_use_photo"):
            add_message("user", f"Please focus on the service suggested by the photo: {vision_group}.")
            _start_selected_category(st.session_state.get("pending_vision_category_id"))
            st.session_state.pending_text_category_id = None
            st.session_state.pending_vision_category_id = None
            st.rerun()
    if st.button("Neither / both / something else", use_container_width=True, key="resolve_neither"):
        add_message("user", "Neither suggestion fully describes the job; help me choose the correct service.")
        st.session_state.category_id = None
        st.session_state.category_confirmed = False
        st.session_state.pending_text_category_id = None
        st.session_state.pending_vision_category_id = None
        st.session_state.stage = "choose_service"
        st.rerun()

elif st.session_state.stage == "confirm_category":
    category = current_category()
    if category:
        st.markdown(f"**Based on what you've shared, this appears to be {category['name'].lower()} work. Is that correct?**")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Yes, that's right", type="primary", use_container_width=True):
                st.session_state.category_confirmed = True
                add_message("user", f"Yes, {category['name']} is correct.")
                # Do not force a customer into the catalog list. Service category
                # mappings are incomplete, so ask scope questions first instead.
                service_matches = detect_service_matches(st.session_state.job_text)
                if service_matches:
                    exact_named = [item for item in service_matches if _term_hits(st.session_state.job_text, item["name"]) >= 3]
                    if exact_named:
                        st.session_state.selected_service_id = exact_named[0]["id"]
                add_message("assistant", "Thanks for confirming. I'll ask a few focused questions, using similar past requests where available, so we can describe the job clearly.")
                st.session_state.stage = "questions"
                st.rerun()
        with col2:
            if st.button("Other service", use_container_width=True):
                st.session_state.category_id = None
                st.session_state.category_confirmed = False
                add_message("user", "I'd like to choose another service.")
                add_message("assistant", "Of course. Please choose the closest match from our available services.")
                st.session_state.stage = "choose_service"
                st.rerun()
    else:
        st.markdown("**Which service best matches your request?**")
        st.session_state.stage = "choose_service"
        st.rerun()

elif st.session_state.stage == "choose_service":
    category = current_category()
    if category:
        options_services = current_services()
        st.markdown(f"### Services in {category['name']}")
        if not options_services:
            st.warning(f"No services are explicitly linked to {category['name']} in the database.")
            st.info(
                "Your current catalog has services without a usable category link. "
                "You can search the active service catalog below; the app will not assume a category relationship."
            )
            search_text = st.text_input(
                "Search all active services",
                value=st.session_state.job_text,
                placeholder="For example: leaking pipe, AC installation, appliance repair..."
            )
            # Search the live service catalog with deterministic rules. If the
            # user's text is not enough, use a literal catalog-name/description
            # filter; do not dump all services or choose the first result.
            matched_services = detect_service_matches(search_text)
            q = normalize_text(search_text)
            literal_matches = [
                item for item in SERVICES
                if q and (
                    q in normalize_text(item["name"])
                    or q in normalize_text(str(item.get("description") or ""))
                    or q in normalize_text(str(item.get("slug") or ""))
                )
            ]
            seen_ids = set()
            candidates = []
            for item in matched_services + literal_matches:
                if item["id"] not in seen_ids:
                    candidates.append(item)
                    seen_ids.add(item["id"])
            if candidates:
                st.markdown("**Possible service matches**")
                for item in candidates[:5]:
                    mapped_cid = item.get("mapped_category_id")
                    linked_category = CATEGORY_BY_ID.get(mapped_cid)
                    with st.container(border=True):
                        st.markdown(f"**{item['name']}**")
                        if linked_category:
                            st.caption(f"Category: {linked_category['name']}")
                        if item.get("description"):
                            st.caption(str(item["description"])[:180])
                        if st.button("Choose this service", key=f"fallback_service_pick_{item['id']}", type="primary", use_container_width=True):
                            st.session_state.selected_service_id = item["id"]
                            st.session_state.category_id = mapped_cid if mapped_cid in CATEGORY_BY_ID else category["id"]
                            st.session_state.category_confirmed = True
                            add_message("user", f"I selected {item['name']}.")
                            add_message("assistant", f"Thank you. I'll ask a few questions to understand the scope of {item['name'].lower()}.")
                            st.session_state.question_index = 0
                            st.session_state.answers = []
                            st.session_state.stage = "questions"
                            st.rerun()
            else:
                st.caption("No confident match yet. Try a shorter service name, such as 'pipe', 'plumbing', or 'repair'.")
            with st.expander("Catalog mapping diagnostics"):
                st.write(f"Active categories: {len(CATEGORIES)} · Active services: {len(SERVICES)} · Services without a category mapping: {len(UNMAPPED_SERVICES)}")
                if UNMAPPED_SERVICES:
                    st.dataframe(
                        [{"service_id": x["id"], "service": x["name"], "stored_category_id": x.get("category_id_raw", "")}
                         for x in UNMAPPED_SERVICES[:30]],
                        use_container_width=True,
                        hide_index=True,
                    )
            labels = {c["name"]: c for c in CATEGORIES if c["id"] != category["id"]}
            if labels:
                picked = st.selectbox("Or choose another category", list(labels), index=None, placeholder="Select a category...")
                if picked and st.button("View services", type="primary", use_container_width=True):
                    st.session_state.category_id = labels[picked]["id"]
                    st.rerun()
        else:
            filter_text = st.text_input("Filter services (optional)", placeholder="Type a service name...")
            filtered = options_services
            if filter_text.strip():
                q = normalize_text(filter_text)
                filtered = [item for item in options_services if q in normalize_text(
                    item["name"] + " " + str(item.get("description") or "") + " " + str(item.get("slug") or ""))]
            if not filtered:
                st.info("No service matches that filter. Try another term.")
            for item in filtered[:8]:
                with st.container(border=True):
                    st.markdown(f"**{item['name']}**")
                    if item.get("description"):
                        st.caption(str(item["description"])[:180])
                    if st.button("Choose this service", key=f"service_pick_{item['id']}", type="primary", use_container_width=True):
                        st.session_state.selected_service_id = item["id"]
                        st.session_state.category_confirmed = True
                        add_message("user", f"I need {item['name']}.")
                        add_message("assistant", f"Thank you. I'll ask a few questions to understand the scope of {item['name'].lower()}.")
                        st.session_state.question_index = 0
                        st.session_state.answers = []
                        st.session_state.stage = "questions"
                        st.rerun()
    else:
        st.markdown("### Let's find the closest service")
        st.caption("We couldn't confidently identify a service. Search the live catalog or choose a category to narrow the options.")
        search_text = st.text_input("Describe or search for the service", value=st.session_state.job_text,
                                    placeholder="For example: leaking pipe, install a ceiling fan, mount a TV...")
        matches = detect_service_matches(search_text)
        if matches:
            st.markdown("**Possible matches**")
            for item in matches:
                cat = CATEGORY_BY_ID.get(item.get("mapped_category_id", item.get("category_id")))
                with st.container(border=True):
                    st.markdown(f"**{item['name']}**")
                    if cat:
                        st.caption(f"Category: {cat['name']}")
                    if item.get("description"):
                        st.caption(str(item["description"])[:180])
                    if st.button("Choose this service", key=f"unlinked_service_pick_{item['id']}", type="primary", use_container_width=True):
                        st.session_state.selected_service_id = item["id"]
                        mapped_cid = item.get("mapped_category_id", item.get("category_id"))
                        st.session_state.category_id = mapped_cid if mapped_cid in CATEGORY_BY_ID else None
                        st.session_state.category_confirmed = st.session_state.category_id is not None
                        add_message("user", f"I need {item['name']}.")
                        add_message("assistant", f"Thank you. I'll ask a few questions to understand the scope of {item['name'].lower()}.")
                        st.session_state.question_index = 0
                        st.session_state.answers = []
                        st.session_state.stage = "questions"
                        st.rerun()
        else:
            st.info("No clear catalog match was found. Choose a category to narrow the service list.")
            category_matches = detect_category_from_text(search_text)
            category_options = {c["name"]: c for c in (category_matches or CATEGORIES)}
            picked_name = st.selectbox("Available categories", list(category_options), index=None, placeholder="Select a category...")
            if picked_name and st.button("View services", type="primary", use_container_width=True):
                st.session_state.category_id = category_options[picked_name]["id"]
                st.session_state.stage = "choose_service"
                st.rerun()

elif st.session_state.stage == "questions":
    questions = current_questions()
    if not questions:
        questions = list(GENERIC_SCOPE_QUESTIONS)
        st.session_state.adaptive_questions = questions
    idx = min(st.session_state.question_index, len(questions) - 1)
    question, choices = questions[idx]
    question = clean_historical_question(question)
    if not choices:
        choices = infer_answer_options(question, current_category(), st.session_state.job_text)
    st.caption(f"Job details · Question {idx + 1} of {len(questions)}")
    # Render the active question only here; don't also add it to chat history.
    with st.chat_message("assistant", avatar="🛠️"):
        st.markdown(question)

    def save_answer(answer: str):
        answer = answer.strip()
        if not answer:
            return False
        if idx == 0 and current_services():
            service = next((item for item in current_services() if item["name"] == answer), None)
            if service:
                st.session_state.selected_service_id = service["id"]
        st.session_state.answers.append({"question": question, "answer": answer})
        add_message("user", answer)
        st.session_state.asked_question_texts.append(question)

        # Re-run local retrieval using the initial request plus the new answer.
        # This can change which historical case is most relevant for the next
        # question; no external AI call is made.
        context_parts = [st.session_state.job_text]
        context_parts.extend(
            f"{item['question']} {item['answer']}"
            for item in st.session_state.answers
            if item.get("question") and item.get("answer")
        )
        updated_context = "\n".join(context_parts)
        updated_matches = retrieve_context_for_request(updated_context)
        if updated_matches:
            st.session_state.historical_matches = updated_matches
        new_questions = make_followups(
            current_category(),
            st.session_state.historical_matches,
            updated_context,
        )
        asked_keys = {
            normalize_text(item) for item in st.session_state.asked_question_texts
        }
        remaining_questions = [
            item for item in new_questions
            if normalize_text(item[0]) not in asked_keys
        ]

        st.session_state.adaptive_questions = remaining_questions
        st.session_state.question_index = 0
        if remaining_questions:
            # The next question is selected from the refreshed historical
            # context (or the category-specific fallback if no clean historic
            # question is available).
            pass
        else:
            add_message("assistant", "Thank you. Is there anything else our team should know about the work?")
            st.session_state.stage = "scope_notes"
        return True

    # Show suggested answers as buttons, but always let the customer type
    # a different answer instead of forcing them to choose a predefined option.
    # Historical options are used only when explicitly present in the record;
    # otherwise infer_answer_options supplies local question-specific suggestions.
    if choices:
        st.caption("Choose an answer, or enter your own below.")
        cols = st.columns(2)
        for i, choice in enumerate(choices):
            with cols[i % 2]:
                if st.button(choice, key=f"answer_{idx}_{i}", use_container_width=True):
                    st.session_state[f"other_answer_mode_{idx}"] = False
                    save_answer(choice)
                    st.rerun()

        other_key = f"other_answer_mode_{idx}"
        if st.button(
            "Other — I’ll type my answer",
            key=f"open_other_answer_{idx}",
            use_container_width=True,
        ):
            st.session_state[other_key] = True

        if st.session_state.get(other_key, False):
            with st.form(key=f"other_answer_form_{idx}", clear_on_submit=True):
                custom_answer = st.text_input(
                    "Tell Leo in your own words",
                    placeholder="Type your answer here...",
                )
                other_submitted = st.form_submit_button(
                    "Send answer ➤", type="primary", use_container_width=True
                )
            if other_submitted:
                if save_answer(custom_answer):
                    st.session_state[other_key] = False
                    st.rerun()
                else:
                    st.warning("Please enter an answer before continuing.")
    else:
        with st.form(key=f"answer_form_{idx}", clear_on_submit=True):
            answer = st.text_input("Your answer", placeholder="Type your answer here...")
            submitted = st.form_submit_button("Submit answer ➤", type="primary", use_container_width=True)
        if submitted:
            if save_answer(answer):
                st.rerun()
            else:
                st.warning("Please enter an answer before continuing.")

elif st.session_state.stage == "scope_notes":
    notes = st.text_area("Additional details (optional)", placeholder="Measurements, access, materials, or other relevant details...", key="final_notes")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Skip", use_container_width=True):
            st.session_state.scope_notes = ""
            st.session_state.stage = "review"
            add_message("user", "No additional details.")
            add_message("assistant", "Thank you. I'll summarize your request.")
            st.rerun()
    with col2:
        if st.button("Send details", type="primary", use_container_width=True):
            st.session_state.scope_notes = notes.strip()
            if notes.strip():
                add_message("user", notes.strip())
            add_message("assistant", "Thank you. I'll summarize your request.")
            st.session_state.stage = "review"
            st.rerun()

elif st.session_state.stage == "review":
    st.markdown("### Summary of your request")
    st.markdown("> " + build_scope().replace("\n", "\n> "))
    st.caption("This is a summary for review. No appointment has been booked and no final price has been provided.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Review answers", use_container_width=True):
            st.session_state.stage = "questions"
            st.session_state.question_index = 0
            st.rerun()
    with col2:
        if st.button("Check duration readiness", type="primary", use_container_width=True):
            scope = build_scope()
            category = current_category()
            category_id = category["id"] if category else None
            try:
                if category and not baseline_category_matches(category_id, category["name"]):
                    # Fail safely: never show hours from a different category because
                    # a live database ID happens to collide with an old baseline ID.
                    duration = {
                        "estimated_hours": None,
                        "category_id": category_id,
                        "category": category["name"],
                        "support_count": 0,
                        "support_level": "unverified_category_mapping",
                        "method": "blocked_category_id_mismatch",
                        "needs_scope_review": True,
                        "scope_review_reasons": ["The live category ID does not match the historical baseline category label."],
                        "warning": "No duration reference is shown because the historical category mapping could not be verified.",
                        "is_production_ready": False,
                    }
                else:
                    duration = estimate_duration(category_id=category_id, job_description=scope)
                readiness = assess_quote_readiness(
                    estimate=duration, job_description=scope,
                    category_confirmed=bool(st.session_state.category_confirmed),
                    scope_details={"answers": st.session_state.answers},
                )
                st.session_state.duration_result = duration
                st.session_state.readiness_result = readiness
                st.session_state.stage = "result"
                st.rerun()
            except Exception as exc:
                st.error("The duration check could not be completed. No duration reference will be shown.")
                with st.expander("Technical details"):
                    st.exception(exc)

elif st.session_state.stage == "result":
    readiness = st.session_state.readiness_result or {}
    st.markdown("### Initial job assessment")
    decision = readiness.get("decision", "manual_review_required")
    if decision == "estimate_available":
        st.success("The current checks allow an initial duration reference from historical jobs.")
    elif decision == "ask_for_more_details":
        st.warning("We need a little more information before providing a useful duration reference.")
    else:
        st.warning("Our team would need to review this request before a duration reference can be provided.")
    if readiness.get("can_show_preliminary_duration") and readiness.get("duration_estimate_hours") is not None:
        st.metric("Preliminary time reference", f"{readiness['duration_estimate_hours']:.2f} hours")
    else:
        st.info("We can't provide a reliable duration reference from the available details yet.")
    st.caption("This is not a confirmed completion time, price quote, or appointment confirmation. Actual time may vary with site conditions and scope.")
    if st.session_state.get("historical_matches"):
        with st.expander("Similar historical requests used as reference"):
            st.caption("Local historical records only. These examples are unverified and are not guarantees of scope, price, or duration.")
            for example in st.session_state.historical_matches[:3]:
                title = example.get("task_title") or "Historical request"
                category_name = example.get("category") or "Category not recorded"
                st.markdown(f"**{title}** · {category_name}")
                if example.get("final_scope"):
                    st.write(str(example["final_scope"])[:350])
                if example.get("estimated_hours") is not None:
                    st.caption(f"Recorded estimate: {example['estimated_hours']} hours · session {example.get('session_id', 'unknown')}")
    for reason in readiness.get("reasons", []):
        st.write(f"- {reason}")
    for question in readiness.get("questions_to_ask", []):
        st.write(f"**To help us assess the job:** {question}")
    if st.button("Start a new request", type="primary", use_container_width=True):
        reset_flow()
        st.rerun()

st.divider()
st.caption("Leo helps organize your request using Star Handyman’s service catalog and relevant past requests. This demo does not book appointments or save chat history to the database. Uploaded photos are analysed locally with CLIP for initial service suggestions; results are not a confirmed diagnosis.")
