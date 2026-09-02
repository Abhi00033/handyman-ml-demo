import streamlit as st
import time
from PIL import Image

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Leo — Star Handyman Project Coordinator",
    layout="wide",
    page_icon="🛠️",
    initial_sidebar_state="collapsed"
)

# --- RESPONSIVE & MOBILE-FRIENDLY CSS ---
st.markdown("""
<style>
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 3rem !important;
        max-width: 900px !important;
    }
    .chat-bubble-leo {
        background-color: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-radius: 12px;
        padding: 1rem 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 6px rgba(0,0,0,0.03);
    }
    .quote-box {
        background-color: var(--background-color);
        border: 2px solid #ffaa00;
        border-radius: 12px;
        padding: 1.25rem;
        margin-top: 1rem;
        font-family: monospace;
        white-space: pre-wrap;
    }
    .stButton button {
        width: 100% !important;
        border-radius: 8px !important;
        height: 3rem !important;
        font-weight: 600 !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("🛠️ Star Handyman — Leo Coordinator Demo")
st.caption("Faithful recreation of Leo's 7-Stage Workflow, Master Task Times & Dynamic Scoping")

# --- MASTER TASK LIBRARY BASE TIMES (SECTION 4 REFERENCE) ---
TASK_DATABASE = {
    "Plumbing": {
        "Kitchen faucet replacement": {"time": 45, "licensed": False, "diff": 2},
        "Bathroom faucet replacement": {"time": 45, "licensed": False, "diff": 2},
        "Kitchen sink P-trap replacement": {"time": 30, "licensed": False, "diff": 2},
        "Toilet installation": {"time": 60, "licensed": False, "diff": 3},
        "Toilet wax ring replacement": {"time": 45, "licensed": False, "diff": 3},
    },
    "Electrical": {
        "Light fixture replacement": {"time": 35, "licensed": False, "diff": 3},
        "Ceiling fan installation": {"time": 75, "licensed": False, "diff": 4},
        "GFCI safety outlet replacement": {"time": 30, "licensed": False, "diff": 4},
        "New 240V heavy outlet (Dryer/EV)": {"time": 90, "licensed": True, "diff": 6},
    },
    "Home Repairs": {
        "TV mount installation": {"time": 60, "licensed": False, "diff": 3},
        "Hide wires/cables behind drywall": {"time": 90, "licensed": False, "diff": 4},
        "Drywall hole patch": {"time": 60, "licensed": False, "diff": 4},
    }
}

# --- SESSION STATE INITIALIZATION ---
if "step" not in st.session_state:
    st.session_state.step = 1
    st.session_state.answers = {}

# --- STAGE 1 & 2: GREETING, PHOTO INTAKE & GOAL ---
st.markdown('<div class="chat-bubble-leo">', unsafe_allow_html=True)
st.write("**Leo:** Hi! I'm Leo, your project coordinator at Star Handyman. I help figure out what needs to be done and connect you with the right Tasker for the job.")
st.write("To get started, please upload a photo and describe what you'd like done.")
st.markdown('</div>', unsafe_allow_html=True)

uploaded_file = st.file_uploader("Upload job photo:", type=["jpg", "jpeg", "png"])
user_desc = st.text_input("Describe your project:", placeholder="e.g., My bathroom faucet is leaking and needs replacement")

if uploaded_file and user_desc and st.session_state.step == 1:
    if st.button("Submit Project Details", type="primary"):
        st.session_state.step = 2
        st.rerun()

# --- STAGE 3: CLARIFICATION (ONE AT A TIME, NUMBERED) ---
if st.session_state.step >= 2:
    # Classify project category based on user prompt
    desc_lower = user_desc.lower()
    if "tv" in desc_lower or "mount" in desc_lower:
        cat = "Home Repairs"
        task_name = "TV mount installation"
    elif "light" in desc_lower or "fan" in desc_lower or "outlet" in desc_lower:
        cat = "Electrical"
        task_name = "Ceiling fan installation"
    else:
        cat = "Plumbing"
        task_name = "Bathroom faucet replacement"

    st.markdown("---")
    st.markdown('<div class="chat-bubble-leo">', unsafe_allow_html=True)
    st.write(f"**Leo:** Thanks for the photo and details. I can see the setup clearly.")
    st.write(f"I have **4 quick questions** to prepare your accurate labour estimate.")
    st.markdown('</div>', unsafe_allow_html=True)

    # QUESTION 1/4: THE GOAL (Rule 5: Ask goal first)
    st.markdown('<div class="chat-bubble-leo">', unsafe_allow_html=True)
    st.write("**Question 1/4:** Before diving into details, what is your primary goal with this project?")
    q1_choice = st.radio(
        "Choose an option:",
        ["Full Replacement with new hardware", "Repair / Fix the existing one", "Complete Redo / Relocate"],
        key="q1"
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # QUESTION 2/4: SURFACE / TECHNICAL CONDITION
    st.markdown('<div class="chat-bubble-leo">', unsafe_allow_html=True)
    st.write("**Question 2/4:** What is the condition of the working area?")
    if cat == "Home Repairs":
        q2_choice = st.radio(
            "Wall structure type:",
            ["Standard Drywall / Wood Studs (Dry & Solid)", "Solid Brick / Concrete Wall", "Wall has dampness / peeling paint"],
            key="q2"
        )
    elif cat == "Plumbing":
        q2_choice = st.radio(
            "Water shut-off condition:",
            ["Water is shut off / Valve turns smoothly", "Shut-off valve is stuck / leaking itself", "Main water shut-off required"],
            key="q2"
        )
    else:
        q2_choice = st.radio(
            "Wiring condition:",
            ["Existing wiring is intact in junction box", "Fresh wire run required from circuit breaker"],
            key="q2"
        )
    st.markdown('</div>', unsafe_allow_html=True)

    # QUESTION 3/4: STAGE 4 MATERIALS CHECK
    st.markdown('<div class="chat-bubble-leo">', unsafe_allow_html=True)
    st.write("**Question 3/4:** Do you already have the materials needed, or would you like the Tasker to bring them?")
    q3_choice = st.radio(
        "Materials responsibility:",
        ["I already have the hardware / materials", "Tasker should supply standard materials"],
        key="q3"
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # QUESTION 4/4: STAGE 4.5 DISPOSAL CHECK
    st.markdown('<div class="chat-bubble-leo">', unsafe_allow_html=True)
    st.write("**Question 4/4:** Would you like the Tasker to handle the disposal of the old parts, or dispose of them yourself?")
    q4_choice = st.radio(
        "Disposal handling:",
        ["Tasker should handle disposal", "I will dispose of old parts myself"],
        key="q4"
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # --- STAGE 5 & 6: CALCULATION ENGINE & QUOTE DELIVERY ---
    if st.button("Generate Leo's Official Project Estimate", type="primary"):
        # 1. Base Task Time
        base_info = TASK_DATABASE[cat][task_name]
        total_minutes = base_info["time"]
        is_licensed = base_info["licensed"]

        # 2. Material pickup buffer (Rule 7: +30 min if Tasker sources)
        tasker_brings_materials = "Tasker should supply" in q3_choice
        if tasker_brings_materials:
            total_minutes += 30

        # 3. Complexity buffer
        if "Brick" in q2_choice or "stuck" in q2_choice or "Fresh wire" in q2_choice:
            total_minutes += 30

        # 4. Enforce 1-Hour Minimum (Rule 5)
        if total_minutes < 60:
            total_minutes = 60

        # 5. Round Up to Nearest 15 Minutes (Rule 6)
        remainder = total_minutes % 15
        if remainder != 0:
            total_minutes += (15 - remainder)

        # 6. Format Display Time (Rule 4)
        hrs = total_minutes // 60
        mins = total_minutes % 60
        time_str = f"{hrs} hour{'s' if hrs > 1 else ''}"
        if mins > 0:
            time_str += f" {mins} minutes"

        tasker_type = "1 Licensed Trade Specialist" if is_licensed else "1 General Tasker"

        # --- OFFICIAL STAGE 8 QUOTE TEMPLATE ---
        quote_text = f"""PROJECT ESTIMATE — STAR HANDYMAN LABOUR ONLY COST

📋 Project Scope:
Execute {task_name.lower()} according to verified specifications ({q1_choice.lower()}). 

👷 Tasker Needed: {tasker_type}

📦 Materials: {"Tasker will bring everything and confirm the details with you in the chatbox after you accept." if tasker_brings_materials else "No materials needed for this project."}

⏱️ Labour Time: {time_str}

This estimate covers labour only. Material details will be arranged with your Tasker in the chatbox, and material costs (with receipts) will be added upon project completion.

{"Disposal is not included in this estimate. Please arrange the details with your Tasker in the chatbox." if "Tasker should handle" in q4_choice else "Disposal will be handled by the Client."}

Do you accept this estimate?"""

        st.markdown('<div class="quote-box">', unsafe_allow_html=True)
        st.text(quote_text)
        st.markdown('</div>', unsafe_allow_html=True)

        col_acc1, col_acc2 = st.columns(2)
        with col_acc1:
            if st.button("Accept Estimate"):
                st.balloons()
                st.success("Perfect! We'll match you with the right Tasker(s) and connect you in the chatbox shortly.")
        with col_acc2:
            if st.button("Start Over"):
                st.session_state.step = 1
                st.rerun()