import streamlit as st
import re
from PIL import Image

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Star Handyman | Project Coordinator Leo",
    layout="wide",
    page_icon="👷‍♂️",
    initial_sidebar_state="collapsed"
)

# Custom Styling (Mobile & Desktop Responsive, Zero Tag Leaks)
st.markdown("""
<style>
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 3rem !important;
        max-width: 860px !important;
    }
    .header-banner {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        color: white;
        padding: 1.25rem 1.5rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
    }
    .chat-bubble {
        background-color: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-left: 4px solid #3b82f6;
        border-radius: 10px;
        padding: 1.2rem;
        margin-bottom: 1.2rem;
    }
    .step-pill {
        background: rgba(59, 130, 246, 0.12);
        color: #2563eb;
        border: 1px solid rgba(59, 130, 246, 0.25);
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
        margin-bottom: 6px;
    }
    .stButton button {
        width: 100% !important;
        border-radius: 8px !important;
        height: 3.2rem !important;
        font-weight: 600 !important;
        font-size: 1.05rem !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-banner">
    <div style="font-size: 1.25rem; font-weight: 700;">👷‍♂️ Leo — Star Handyman Project Coordinator</div>
    <div style="font-size: 0.88rem; opacity: 0.85;">Intelligent Project Scoping Engine • Zero Third-Party AI API Dependency</div>
</div>
""", unsafe_allow_html=True)

# --- MASTER CATALOG IMPLEMENTING SECTION 3 & 4 OF SYSTEM PROMPT ---
MASTER_SERVICES = {
    # 1. HOME REPAIRS [HR] (Section 4 Reference)
    "tv_mount": {
        "title": "TV Mount Installation",
        "category": "Home Repairs [HR]",
        "difficulty": 3,
        "base_time": 60,
        "tasker": "1 General Tasker",
        "multi_visit": False,
        "keywords": [r"\btv\b", r"\btelevision\b", r"\bmount\b", r"\bbracket\b", r"\bhang tv\b", r"\bscreen\b"],
        "questions": [
            {
                "num": "Question 1/4",
                "text": "What size is your TV, and what type of mount are you looking to use?",
                "options": [
                    "Under 55 inches (Standard fixed / tilt bracket)",
                    "55 to 65 inches (Standard fixed / tilt bracket)",
                    "65 to 85 inches (Heavy-duty or full-motion swivel arm)",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 15, 30, 15]
            },
            {
                "num": "Question 2/4",
                "text": "What is the wall construction where the TV will be mounted?",
                "options": [
                    "Standard drywall with wood studs (Dry & solid)",
                    "Solid brick or concrete wall (Requires hammer drill & masonry anchors)",
                    "Wall has dampness or peeling paint (Needs structural check)",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 20, 35, 15]
            },
            {
                "num": "Question 3/4",
                "text": "Do you already have the mount bracket and hardware kit ready on site?",
                "options": [
                    "Yes, I have the bracket and wall screws ready",
                    "No, Tasker must supply heavy-duty mount bracket (+30 min pickup)",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 30, 15]
            },
            {
                "num": "Question 4/4",
                "text": "Would you like power and HDMI cables concealed inside the drywall?",
                "options": [
                    "No, external surface cable channel or visible cords are fine",
                    "Yes, cut drywall pass-throughs and conceal wires inside wall (+30 min)",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 30, 15]
            }
        ]
    },

    # 2. PLUMBING [PL] (Section 4 Reference)
    "plumbing_faucet": {
        "title": "Bathroom / Kitchen Faucet Replacement",
        "category": "Plumbing [PL]",
        "difficulty": 2,
        "base_time": 45,
        "tasker": "1 General Tasker",
        "multi_visit": False,
        "keywords": [
            r"\btap\b", r"\bfaucet\b", r"\bshower\b", r"\bwashroom\b",
            r"\bbathroom\b", r"\bleak\b", r"\bsink\b", r"\bwater\b",
            r"\bdrain\b", r"\bpipe\b", r"\btoilet\b", r"\bflush\b", r"\bp-trap\b", r"\bclog\b"
        ],
        "questions": [
            {
                "num": "Question 1/4",
                "text": "What is the primary goal for this plumbing fixture?",
                "options": [
                    "Full replacement with a new faucet / fixture",
                    "Repair the existing fixture (replace cartridge or stop dripping)",
                    "Replace both fixture and under-sink curved P-trap pipe",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 0, 25, 15]
            },
            {
                "num": "Question 2/4",
                "text": "How is the water shut-off valve behaving?",
                "options": [
                    "Turns smoothly and shuts off water completely",
                    "Valve is stiff, stuck, or leaking itself (Needs replacement)",
                    "No isolation valve; requires main home water line shut-off",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 25, 20, 15]
            },
            {
                "num": "Question 3/4",
                "text": "Do you already have the replacement fixture / parts purchased?",
                "options": [
                    "Yes, replacement fixture is on site and unboxed",
                    "No, Tasker must source standard matching fixture (+30 min pickup)",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 30, 15]
            },
            {
                "num": "Question 4/4",
                "text": "Would you like the Tasker to dispose of the old parts?",
                "options": [
                    "Minimal disposal — Tasker will handle during cleanup",
                    "Tasker handles disposal",
                    "I will dispose of old parts myself",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 0, 0, 0]
            }
        ]
    },

    # 3. ELECTRICAL [EL] (Section 4 Reference)
    "electrical_fan": {
        "title": "Ceiling Fan / Light Fixture Installation",
        "category": "Electrical [EL]",
        "difficulty": 4,
        "base_time": 60,
        "tasker": "1 General Tasker",
        "multi_visit": False,
        "keywords": [
            r"\bfan\b", r"\bceiling fan\b", r"\blight\b", r"\bchandelier\b",
            r"\bfixture\b", r"\bbulb\b", r"\bswitch\b", r"\boutlet\b", r"\bwiring\b"
        ],
        "questions": [
            {
                "num": "Question 1/4",
                "text": "Is this replacing an existing fixture, or a brand-new ceiling location?",
                "options": [
                    "Replacing an existing ceiling fan or light (Wires already in junction box)",
                    "Brand-new location (Requires pulling fresh wiring from switch)",
                    "Upgrading existing fan to include remote control receiver",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 45, 20, 20]
            },
            {
                "num": "Question 2/4",
                "text": "What is the ceiling height in this room?",
                "options": [
                    "Standard ceiling height (8 to 9 feet)",
                    "High ceiling (10 to 14 feet, requires tall ladder)",
                    "Vaulted or sloped ceiling",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 25, 25, 15]
            },
            {
                "num": "Question 3/4",
                "text": "Do you have the new fixture ready on site?",
                "options": [
                    "Yes, new fixture is on site and unboxed",
                    "No, Tasker should supply standard unit (+30 min pickup)",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 30, 15]
            },
            {
                "num": "Question 4/4",
                "text": "Do you need disposal of the old fixture?",
                "options": [
                    "Tasker handles disposal",
                    "I will dispose of old fixture myself",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 0, 0]
            }
        ]
    },

    # 4. HOME IMPROVEMENT [HI] (Section 4 Reference)
    "drywall_patch": {
        "title": "Drywall Patch & Hole Repair",
        "category": "Home Improvement [HI]",
        "difficulty": 4,
        "base_time": 60,
        "tasker": "1 General Tasker",
        "multi_visit": True,  # Per Section 4 Master Library: Multi-visit Yes for compound drying
        "keywords": [
            r"\bdrywall\b", r"\bhole\b", r"\bpatch\b", r"\bcrack\b",
            r"\bsheetrock\b", r"\bpaint\b", r"\bplaster\b"
        ],
        "questions": [
            {
                "num": "Question 1/4",
                "text": "What size is the damaged section of the wall?",
                "options": [
                    "Small hole or door-handle dent (under 5 inches)",
                    "Medium opening (6 to 12 inches, requires mesh/support backer)",
                    "Large area (over 12 inches, requires sheetrock cutout)",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 25, 45, 20]
            },
            {
                "num": "Question 2/4",
                "text": "Is the damaged area completely dry, or is there moisture behind it?",
                "options": [
                    "Completely dry wall (Accidental impact or nail damage)",
                    "Damp, soft, or water-stained area (Requires source leak check)",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 30, 15]
            },
            {
                "num": "Question 3/4",
                "text": "Do you have joint compound, mesh tape, and patch board ready?",
                "options": [
                    "I have compound and tape ready",
                    "Tasker should supply patching compound, mesh, and board (+30 min pickup)",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 30, 15]
            },
            {
                "num": "Question 4/4",
                "text": "Would you like paint touch-up applied after the patch is sanded smooth?",
                "options": [
                    "Yes, match and paint over the patch (Client provides paint)",
                    "No, leave smooth sanded patch ready for me to paint",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [20, 0, 10]
            }
        ]
    },

    # 5. CARPENTRY [CR] (Section 4 Reference)
    "carpentry_doors": {
        "title": "Door Adjustment, Locks & Cabinet Hardware",
        "category": "Carpentry [CR]",
        "difficulty": 2,
        "base_time": 45,
        "tasker": "1 General Tasker",
        "multi_visit": False,
        "keywords": [
            r"\bdoor\b", r"\block\b", r"\bcabinet\b", r"\bshelf\b",
            r"\bhinge\b", r"\bhandle\b", r"\bwood\b", r"\bfurniture\b"
        ],
        "questions": [
            {
                "num": "Question 1/4",
                "text": "What is the primary scope of work for this item?",
                "options": [
                    "Realign, adjust, or tighten existing hardware / hinges",
                    "Full hardware, lock, or door replacement with new piece",
                    "Assemble flat-pack furniture",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 15, 30, 15]
            },
            {
                "num": "Question 2/4",
                "text": "What is the condition of the mounting wood or frame?",
                "options": [
                    "Standard wood in solid condition",
                    "Damaged or stripped screw holes (Needs dowels / re-anchoring)",
                    "Hardwood, masonry, or metal frame",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 20, 25, 15]
            },
            {
                "num": "Question 3/4",
                "text": "Do you have all replacement hardware ready on site?",
                "options": [
                    "Yes, all hardware and parts are ready",
                    "Tasker should supply standard hardware / screws (+30 min pickup)",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 30, 15]
            },
            {
                "num": "Question 4/4",
                "text": "Do you need disposal of old parts?",
                "options": [
                    "Minimal disposal — Tasker will handle during cleanup",
                    "Tasker handles disposal",
                    "I will dispose of parts myself",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 0, 0, 0]
            }
        ]
    }
}

# --- SERVICE CLASSIFIER: PRIORITIZES USER TEXT ---
def classify_input(text: str, visual_tag: str):
    clean_text = text.lower().strip()

    # Match User Text First via Regex Word Boundaries
    if clean_text:
        for key, data in MASTER_SERVICES.items():
            for pat in data["keywords"]:
                if re.search(pat, clean_text):
                    return key

    # Match Image Tag if Text has no keywords
    clean_vis = visual_tag.lower().strip()
    if "tv" in clean_vis or "screen" in clean_vis:
        return "tv_mount"
    elif "plumbing" in clean_vis or "tap" in clean_vis or "shower" in clean_vis:
        return "plumbing_faucet"
    elif "fan" in clean_vis or "light" in clean_vis:
        return "electrical_fan"
    elif "drywall" in clean_vis or "wall" in clean_vis:
        return "drywall_patch"
    elif "door" in clean_vis or "cabinet" in clean_vis:
        return "carpentry_doors"

    # Default fallback
    return "tv_mount"

# --- SESSION STATE ---
if "step" not in st.session_state:
    st.session_state.step = "intake"
    st.session_state.user_desc = ""
    st.session_state.detected_key = None

# ==========================================
# STAGE 1: GREETING & INTAKE (Section 6, Stage 1)
# ==========================================
if st.session_state.step == "intake":
    st.markdown("""
    <div class="chat-bubble">
        <span class="step-pill">Stage 1: Greeting & Intake</span>
        <div style="font-size: 1.05rem; font-weight: 500; line-height: 1.5;">
            "Hi! I'm Leo, your project coordinator at Star Handyman. I help figure out what needs to be done and connect you with the right Tasker for the job."
        </div>
        <p style="margin-top: 8px; margin-bottom: 0; font-size: 0.9rem; opacity: 0.85;">
            Please upload a photo of the area and tell me what you'd like done.
        </p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1], gap="medium")
    detected_visual = ""

    with c1:
        uploaded_file = st.file_uploader("📸 Upload project photo (Optional):", type=["jpg", "jpeg", "png"])
        if uploaded_file:
            img = Image.open(uploaded_file)
            st.image(img, use_container_width=True)

            st.markdown("**Image Context:**")
            detected_visual = st.selectbox(
                "Verify area in photo:",
                [
                    "📺 Living Room Wall / TV Mount Area",
                    "🚿 Bathroom / Kitchen Plumbing (Tap, Shower, Sink)",
                    "💡 Ceiling Fan / Light Electrical Fixture",
                    "🧱 Drywall Damage / Wall Hole",
                    "🚪 Door / Cabinet / Wooden Fixture"
                ],
                label_visibility="collapsed"
            )

    with c2:
        user_text = st.text_area(
            "📝 Describe what you'd like done:",
            placeholder="e.g., 'want to install tv', 'my shower tap is leaking', 'install ceiling fan', 'patch drywall hole'...",
            height=140
        )
        submit = st.button("Start Scoping With Leo →", type="primary")

        if submit:
            if not user_text.strip() and not uploaded_file:
                st.warning("Please upload a photo or type a short description of what you need done.")
            else:
                st.session_state.user_desc = user_text
                st.session_state.detected_key = classify_input(user_text, detected_visual)
                st.session_state.step = "questions"
                st.rerun()

# ==========================================
# STAGE 2: CLARIFYING QUESTIONS (Section 6, Stage 3)
# ==========================================
elif st.session_state.step == "questions":
    srv = MASTER_SERVICES[st.session_state.detected_key]

    st.markdown(f"""
    <div class="chat-bubble">
        <span class="step-pill">Category: {srv['category']}</span>
        <div style="font-size: 1.15rem; font-weight: 700;">{srv['title']}</div>
        <div style="margin-top: 6px; font-size: 0.92rem; opacity: 0.9;">
            "Thanks for the details! I have 4 clarifying questions to scope the work accurately. You can tap an option or type a custom answer."
        </div>
    </div>
    """, unsafe_allow_html=True)

    recorded_answers = []
    added_mins = 0

    for idx, q in enumerate(srv["questions"]):
        st.markdown(f"<span class='step-pill'>{q['num']}</span>", unsafe_allow_html=True)
        st.markdown(f"**{q['text']}**")

        chosen_option = st.radio(
            f"Select for {q['num']}:",
            q["options"],
            key=f"opt_{st.session_state.detected_key}_{idx}",
            label_visibility="collapsed"
        )

        final_answer_text = chosen_option
        if "✏️ Type custom answer" in chosen_option:
            custom_input = st.text_input(
                f"Enter your specific details for {q['num']}:",
                placeholder="Type your answer here...",
                key=f"custom_{st.session_state.detected_key}_{idx}"
            )
            if custom_input.strip():
                final_answer_text = custom_input.strip()
            added_mins += 15
        else:
            opt_idx = q["options"].index(chosen_option)
            added_mins += q["impact"][opt_idx]

        recorded_answers.append(final_answer_text)
        st.write("")

    st.markdown("---")
    if st.button("Generate Verified Labour Estimate ⚡", type="primary"):
        st.session_state.answers = recorded_answers
        st.session_state.calculated_duration = srv["base_time"] + added_mins
        st.session_state.step = "estimate"
        st.rerun()

# ==========================================
# STAGE 3: QUOTE DELIVERY (Section 8 Standard Template)
# ==========================================
elif st.session_state.step == "estimate":
    srv = MASTER_SERVICES[st.session_state.detected_key]
    tot_mins = st.session_state.calculated_duration
    answers = st.session_state.answers

    # Section 5, Rule 5: 1-Hour Minimum
    if tot_mins < 60:
        tot_mins = 60

    # Section 5, Rule 6: Round Up to Nearest 15 Minutes
    remainder = tot_mins % 15
    if remainder != 0:
        tot_mins += (15 - remainder)

    # Section 5, Rule 4: Quote Format
    hrs = tot_mins // 60
    mins = tot_mins % 60
    if hrs >= 8:
        duration_str = f"{hrs} hours"
    elif hrs > 0 and mins > 0:
        duration_str = f"{hrs} hour{'s' if hrs > 1 else ''} {mins} minutes"
    elif hrs > 0:
        duration_str = f"{hrs} hour{'s' if hrs > 1 else ''}"
    else:
        duration_str = f"{mins} minutes"

    # Section 5, Rule 7: Materials check
    tasker_sourcing_materials = any("Tasker" in a and "pickup" in a for a in answers)
    
    # Section 7: Disposal handling
    tasker_handles_disposal = any("Tasker handles disposal" in a for a in answers)
    is_minimal_disposal = any("Minimal disposal" in a for a in answers)

    # Output Structured Quote (Section 8 Standard Single-Project Template)
    st.markdown("### PROJECT ESTIMATE — STAR HANDYMAN LABOUR ONLY COST")
    st.markdown("---")

    st.markdown(f"**📋 Project Scope:**  \nExecute {srv['title'].lower()} according to verified specifications ({answers[0]}).")
    st.markdown(f"**👷 Tasker Needed:** {srv['tasker']}")

    if tasker_sourcing_materials:
        st.markdown("**📦 Materials:** Tasker will bring everything and confirm the details with you in the chatbox after you accept.")
    else:
        st.markdown("**📦 Materials:** No materials needed for this project.")

    st.markdown(f"**⏱️ Labour Time:** **{duration_str}**")

    st.info("ℹ️ This estimate covers labour only. Material details will be arranged with your Tasker in the chatbox, and material costs (with receipts) will be added upon project completion.")

    # Section 5, Rule 9: Multi-Visit note
    if srv["multi_visit"]:
        st.warning("⚠️ *This project may require multiple visits due to curing and drying times. Your Tasker will arrange the schedule with you in the chatbox.*")

    # Section 7: Disposal note (Skipped if minimal per Rule 11)
    if not is_minimal_disposal:
        if tasker_handles_disposal:
            st.markdown("🗑️ *Disposal is not included in this estimate. Please arrange the details with your Tasker in the chatbox.*")
        else:
            st.markdown("🗑️ *Disposal will be handled by the Client.*")

    st.markdown("---")
    st.markdown("**Do you accept this estimate?**")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Accept Estimate & Match Tasker", type="primary"):
            st.balloons()
            # Section 6, Stage 7 Handoff
            st.success("Perfect! We'll match you with the right Tasker(s) and connect you in the chatbox shortly. They'll already have the full picture — the photos, your preferences, and the scope — so you won't need to repeat anything. Thanks for choosing Star Handyman.")
    with c2:
        if st.button("← Start Another Request"):
            st.session_state.step = "intake"
            st.session_state.user_desc = ""
            st.session_state.detected_key = None
            st.rerun()