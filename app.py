import streamlit as st
import torch
import re
from PIL import Image
from transformers import CLIPProcessor, CLIPModel

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Star Handyman | Leo Coordinator",
    layout="wide",
    page_icon="👷‍♂️",
    initial_sidebar_state="collapsed"
)

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
    <div style="font-size: 0.88rem; opacity: 0.85;">Pure Local ML Vision & Intake • Zero External AI APIs</div>
</div>
""", unsafe_allow_html=True)

# --- 1. LOCAL ML VISION ENGINE (CLIP ZERO-SHOT MODEL) ---
@st.cache_resource(show_spinner="Loading vision model into memory...")
def load_clip_vision_model():
    model_id = "openai/clip-vit-base-patch32"
    model = CLIPModel.from_pretrained(model_id)
    processor = CLIPProcessor.from_pretrained(model_id)
    return model, processor

def analyze_image_with_ml(image: Image.Image):
    model, processor = load_clip_vision_model()
    image.thumbnail((512, 512))

    candidate_labels = [
        "a photo of a bathroom faucet, washroom tap, or shower fixture",
        "a photo of a television mounted on a wall or a flat tv screen",
        "a photo of a ceiling fan or ceiling light fixture",
        "a photo of a damaged wall, hole in drywall, or sheetrock crack",
        "a photo of a wooden door, door handle, or cabinet hinges"
    ]

    service_map = {
        0: "plumbing_faucet",
        1: "tv_mount",
        2: "electrical_fan",
        3: "drywall_patch",
        4: "carpentry_doors"
    }

    inputs = processor(text=candidate_labels, images=image, return_tensors="pt", padding=True)
    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits_per_image[0]
        probs = logits.softmax(dim=-1).numpy()

    best_idx = int(probs.argmax())
    confidence = float(probs[best_idx])
    return service_map[best_idx], confidence, candidate_labels[best_idx]

# --- 2. TEXT INTENT FALLBACK ENGINE ---
def classify_text_intent(text: str):
    clean = text.lower().strip()
    if not clean:
        return None
    patterns = {
        "plumbing_faucet": [r"\btap\b", r"\bfaucet\b", r"\bshower\b", r"\bwashroom\b", r"\bleak\b", r"\bsink\b", r"\bpipe\b", r"\btoilet\b"],
        "tv_mount": [r"\btv\b", r"\btelevision\b", r"\bmount\b", r"\bbracket\b", r"\bhang tv\b", r"\bscreen\b"],
        "electrical_fan": [r"\bfan\b", r"\bceiling fan\b", r"\blight\b", r"\bchandelier\b", r"\bfixture\b", r"\bswitch\b", r"\bwiring\b"],
        "drywall_patch": [r"\bdrywall\b", r"\bhole\b", r"\bpatch\b", r"\bcrack\b", r"\bsheetrock\b", r"\bpaint\b"],
        "carpentry_doors": [r"\bdoor\b", r"\block\b", r"\bcabinet\b", r"\bhinge\b", r"\bhandle\b", r"\bwood\b", r"\bfurniture\b"]
    }
    for key, regexes in patterns.items():
        if any(re.search(p, clean) for p in regexes):
            return key
    return None

# --- 3. MASTER TASK LIBRARY (Section 4 Reference) ---
MASTER_SERVICES = {
    "tv_mount": {
        "title": "TV Mount Installation",
        "category": "Home Repairs [HR]",
        "difficulty": 3,
        "base_time": 60,
        "tasker": "1 General Tasker",
        "multi_visit": False,
        "questions": [
            {
                "num": "Question 1/4",
                "text": "What size is your TV, and what type of mount bracket are you planning to use?",
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
                    "Wall has dampness or peeling paint (Needs structural inspection)",
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
                    "No, external surface cable channel or hanging cords are fine",
                    "Yes, cut drywall pass-throughs and conceal wires inside wall (+30 min)",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 30, 15]
            }
        ]
    },
    "plumbing_faucet": {
        "title": "Bathroom / Kitchen Faucet Replacement",
        "category": "Plumbing [PL]",
        "difficulty": 2,
        "base_time": 45,
        "tasker": "1 General Tasker",
        "multi_visit": False,
        "questions": [
            {
                "num": "Question 1/4",
                "text": "What is the primary goal for this plumbing fixture?",
                "options": [
                    "Full replacement with a new faucet / fixture",
                    "Repair existing fixture (replace cartridge or stop dripping)",
                    "Replace both fixture and under-sink curved P-trap drainage pipe",
                    "✏️ Type custom answer / Other details..."
                ],
                "impact": [0, 0, 25, 15]
            },
            {
                "num": "Question 2/4",
                "text": "How is the water shut-off valve behaving under the sink?",
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
    "electrical_fan": {
        "title": "Ceiling Fan / Light Fixture Installation",
        "category": "Electrical [EL]",
        "difficulty": 4,
        "base_time": 60,
        "tasker": "1 General Tasker",
        "multi_visit": False,
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
    "drywall_patch": {
        "title": "Drywall Patch & Hole Repair",
        "category": "Home Improvement [HI]",
        "difficulty": 4,
        "base_time": 60,
        "tasker": "1 General Tasker",
        "multi_visit": True,
        "questions": [
            {
                "num": "Question 1/4",
                "text": "What size is the damaged section of the wall?",
                "options": [
                    "Small hole or door-handle dent (under 5 inches)",
                    "Medium opening (6 to 12 inches)",
                    "Large area (over 12 inches)",
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
    "carpentry_doors": {
        "title": "Door Adjustment, Locks & Cabinet Hardware",
        "category": "Carpentry [CR]",
        "difficulty": 2,
        "base_time": 45,
        "tasker": "1 General Tasker",
        "multi_visit": False,
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

# --- STATE MANAGEMENT ---
if "step" not in st.session_state:
    st.session_state.step = "intake"
    st.session_state.detected_key = None
    st.session_state.vision_confidence = None
    st.session_state.current_q_idx = 0
    st.session_state.answers = []
    st.session_state.cumulative_extra_mins = 0

# ==========================================
# STAGE 1: INTAKE WITH ML VISION & TEXT PARSER
# ==========================================
if st.session_state.step == "intake":
    st.markdown("""
    <div class="chat-bubble">
        <span class="step-pill">Stage 1: Greeting & Intake</span>
        <div style="font-size: 1.05rem; font-weight: 500; line-height: 1.5;">
            "Hi! I'm Leo, your project coordinator at Star Handyman. I help figure out what needs to be done and connect you with the right Tasker for the job."
        </div>
        <p style="margin-top: 8px; margin-bottom: 0; font-size: 0.9rem; opacity: 0.85;">
            Upload your photo or describe what you need done. Our local ML model handles pixel inspection automatically.
        </p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns([1.1, 1], gap="medium")
    detected_key = None
    confidence = 0.0

    with c1:
        uploaded_file = st.file_uploader("📸 Upload job photo:", type=["jpg", "jpeg", "png"])
        if uploaded_file:
            img = Image.open(uploaded_file).convert("RGB")
            st.image(img, use_container_width=True)

            with st.spinner("Analyzing image pixels with in-house CLIP Vision ML..."):
                detected_key, confidence, _ = analyze_image_with_ml(img)
            
            st.success(f"🤖 **Vision ML Identification:** `{MASTER_SERVICES[detected_key]['title']}` ({confidence*100:.1f}% confidence)")

    with c2:
        user_text = st.text_area(
            "📝 Job Description / Notes:",
            placeholder="e.g., 'need help installing ceiling fan', 'bathroom tap leaking', 'mount 65 inch tv' (or leave blank if photo is uploaded)...",
            height=140
        )
        submit = st.button("Start Scoping With Leo →", type="primary")

        if submit:
            if not uploaded_file and not user_text.strip():
                st.warning("Please upload a photo or type a short note about the task.")
            else:
                text_key = classify_text_intent(user_text)

                if text_key:
                    st.session_state.detected_key = text_key
                elif detected_key:
                    st.session_state.detected_key = detected_key
                    st.session_state.vision_confidence = confidence
                else:
                    st.session_state.detected_key = "tv_mount"

                # Reset sequential question state
                st.session_state.current_q_idx = 0
                st.session_state.answers = []
                st.session_state.cumulative_extra_mins = 0
                st.session_state.step = "questions"
                st.rerun()

# ==========================================
# STAGE 2: SEQUENTIAL QUESTIONS (ONE BY ONE)
# ==========================================
elif st.session_state.step == "questions":
    srv = MASTER_SERVICES[st.session_state.detected_key]
    total_q = len(srv["questions"])
    curr_idx = st.session_state.current_q_idx
    q = srv["questions"][curr_idx]

    # Service & Context Header
    st.markdown(f"""
    <div class="chat-bubble">
        <span class="step-pill">Verified Category: {srv['category']}</span>
        <div style="font-size: 1.15rem; font-weight: 700;">{srv['title']}</div>
        <div style="margin-top: 6px; font-size: 0.92rem; opacity: 0.9;">
            "Thanks for the details! I have a few clarifying questions to scope the work accurately. Let's take them one by one."
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Show past answered questions in conversation flow
    if st.session_state.answers:
        for past_idx, past_ans in enumerate(st.session_state.answers):
            past_q = srv["questions"][past_idx]
            st.markdown(f"<span style='color: #64748b; font-size: 0.85rem;'>✔ {past_q['num']}: {past_q['text']}</span>", unsafe_allow_html=True)
            st.markdown(f"<div style='background: rgba(100, 116, 139, 0.08); padding: 8px 12px; border-radius: 8px; margin-bottom: 10px; font-size: 0.9rem;'>💬 <strong>You:</strong> {past_ans}</div>", unsafe_allow_html=True)

    st.markdown("---")

    # Present Current Active Question
    st.markdown(f"<span class='step-pill'>{q['num']}</span>", unsafe_allow_html=True)
    st.markdown(f"### {q['text']}")

    chosen_option = st.radio(
        f"Select an option for {q['num']}:",
        q["options"],
        key=f"active_opt_{st.session_state.detected_key}_{curr_idx}",
        label_visibility="collapsed"
    )

    custom_input = ""
    if "✏️ Type custom answer" in chosen_option:
        custom_input = st.text_input(
            f"Enter specific details for {q['num']}:",
            placeholder="Type your details here...",
            key=f"active_custom_{st.session_state.detected_key}_{curr_idx}"
        )

    st.write("")
    is_last_question = (curr_idx == total_q - 1)
    btn_label = "Generate Verified Labour Estimate ⚡" if is_last_question else "Next Question →"

    if st.button(btn_label, type="primary"):
        # Resolve user's answer text and duration delta
        final_answer = custom_input.strip() if ("✏️ Type custom answer" in chosen_option and custom_input.strip()) else chosen_option
        
        if "✏️ Type custom answer" in chosen_option:
            added_time = 15
        else:
            opt_idx = q["options"].index(chosen_option)
            added_time = q["impact"][opt_idx]

        st.session_state.answers.append(final_answer)
        st.session_state.cumulative_extra_mins += added_time

        if is_last_question:
            st.session_state.calculated_duration = srv["base_time"] + st.session_state.cumulative_extra_mins
            st.session_state.step = "estimate"
        else:
            st.session_state.current_q_idx += 1
        st.rerun()

# ==========================================
# STAGE 3: QUOTE DELIVERY (Standard Single-Project Template)
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

    # Section 5, Rule 7: Materials check (+30 min)
    tasker_sourcing_materials = any("Tasker" in a and "pickup" in a for a in answers)

    # Section 7: Disposal handling
    tasker_handles_disposal = any("Tasker handles disposal" in a for a in answers)
    is_minimal_disposal = any("Minimal disposal" in a for a in answers)

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
            st.success("Perfect! We'll match you with the right Tasker(s) and connect you in the chatbox shortly. They'll already have the full picture — the photos, your preferences, and the scope — so you won't need to repeat anything. Thanks for choosing Star Handyman.")
    with c2:
        if st.button("← Start Another Request"):
            st.session_state.step = "intake"
            st.session_state.detected_key = None
            st.session_state.vision_confidence = None
            st.session_state.current_q_idx = 0
            st.session_state.answers = []
            st.session_state.cumulative_extra_mins = 0
            st.rerun()