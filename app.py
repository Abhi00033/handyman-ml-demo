import streamlit as st
import time
from PIL import Image

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Leo | Star Handyman Coordinator",
    layout="wide",
    page_icon="👷‍♂️",
    initial_sidebar_state="collapsed"
)

# --- MODERN DESIGN SYSTEM & RESPONSIVE CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Container fluid constraints */
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 3rem !important;
        max-width: 880px !important;
    }

    /* Top Brand Bar */
    .brand-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        color: white;
        padding: 1rem 1.25rem;
        border-radius: 16px;
        margin-bottom: 1.25rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
    }
    .coordinator-info {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .avatar-icon {
        background: #3b82f6;
        color: white;
        font-size: 1.5rem;
        width: 48px;
        height: 48px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 2px 8px rgba(59,130,246,0.4);
    }
    .status-dot {
        height: 10px;
        width: 10px;
        background-color: #22c55e;
        border-radius: 50%;
        display: inline-block;
        margin-right: 5px;
    }

    /* Progress Stepper */
    .step-badge {
        background: rgba(59, 130, 246, 0.1);
        color: #2563eb;
        border: 1px solid rgba(59, 130, 246, 0.2);
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
        margin-bottom: 8px;
    }

    /* Chat Bubbles */
    .bubble-leo {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-left: 4px solid #3b82f6;
        border-radius: 12px;
        padding: 1.15rem 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02);
    }
    
    @media (prefers-color-scheme: dark) {
        .bubble-leo {
            background: #1e293b;
            border-color: #334155;
            border-left: 4px solid #3b82f6;
            color: #f1f5f9;
        }
    }

    /* Interactive Quote Voucher */
    .quote-ticket {
        background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
        border: 2px solid #e2e8f0;
        border-top: 6px solid #f59e0b;
        border-radius: 16px;
        padding: 1.5rem;
        margin-top: 1.5rem;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05);
    }
    @media (prefers-color-scheme: dark) {
        .quote-ticket {
            background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
            border-color: #334155;
            border-top: 6px solid #f59e0b;
            color: #f8fafc;
        }
    }

    /* Stats Grid */
    .stats-card {
        background: var(--background-color);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 12px;
        padding: 1rem;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }

    /* Touch & Mobile Specific Rules */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
        }
        .brand-header {
            flex-direction: column;
            align-items: flex-start;
            gap: 8px;
        }
        .stButton button {
            height: 3.2rem !important;
            font-size: 1.05rem !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# --- TOP BRAND / COORDINATOR HEADER ---
st.markdown("""
<div class="brand-header">
    <div class="coordinator-info">
        <div class="avatar-icon">👷‍♂️</div>
        <div>
            <div style="font-size: 1.15rem; font-weight: 700; letter-spacing: -0.01em;">Leo • Star Handyman</div>
            <div style="font-size: 0.85rem; opacity: 0.85;">
                <span class="status-dot"></span>Project Coordinator (Scoping & Dispatch)
            </div>
        </div>
    </div>
    <div style="font-size: 0.8rem; background: rgba(255,255,255,0.15); padding: 4px 10px; border-radius: 8px;">
        Zero-LLM ML Engine
    </div>
</div>
""", unsafe_allow_html=True)

# --- MASTER TASK LIBRARY (Section 4 Reference) ---
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

# --- SESSION STATE ---
if "step" not in st.session_state:
    st.session_state.step = 1

# --- STAGE 1: INTAKE & PHOTO CAPTURE ---
if st.session_state.step == 1:
    st.markdown("""
    <div class="bubble-leo">
        <span class="step-badge">Stage 1: Intake</span>
        <div style="font-size: 1.05rem; font-weight: 500; line-height: 1.5;">
            "Hi! I'm Leo, your project coordinator at Star Handyman. I help figure out what needs to be done and connect you with the right Tasker for the job."
        </div>
        <p style="margin-top: 8px; margin-bottom: 0; font-size: 0.9rem; opacity: 0.85;">
            Send me a clear photo of the area and a quick note on what you need help with.
        </p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1], gap="medium")
    with c1:
        uploaded_file = st.file_uploader("📸 Upload project photo", type=["jpg", "jpeg", "png"])
        if uploaded_file:
            img = Image.open(uploaded_file)
            st.image(img, use_container_width=True)
    with c2:
        user_desc = st.text_area(
            "📝 Tell me what's happening:",
            placeholder="e.g., Faucet leaking under the bathroom sink / Need a 65-inch TV mounted on brick wall",
            height=130
        )
        submit_btn = st.button("Start Scoping With Leo →", type="primary", use_container_width=True)
        if submit_btn and user_desc:
            st.session_state.user_desc = user_desc
            st.session_state.step = 2
            st.rerun()

# --- STAGE 2: ADAPTIVE QUESTION SEQUENCE ---
elif st.session_state.step == 2:
    desc = st.session_state.user_desc.lower()
    
    # Classify Category
    if "tv" in desc or "mount" in desc:
        cat = "Home Repairs"
        task_name = "TV mount installation"
    elif "light" in desc or "fan" in desc or "outlet" in desc:
        cat = "Electrical"
        task_name = "Ceiling fan installation"
    else:
        cat = "Plumbing"
        task_name = "Bathroom faucet replacement"

    st.markdown(f"""
    <div class="bubble-leo">
        <span class="step-badge">Identified: {cat} • {task_name}</span>
        <div style="font-weight: 500; font-size: 1rem;">
            "Thanks for the details! I have 4 clarifying questions so I can match the right Tasker and calculate your labour estimate accurately."
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Question 1/4 (Goal First)
    st.markdown("""
    <div class="bubble-leo">
        <span class="step-badge">Question 1/4</span>
        <div style="font-weight: 600; margin-bottom: 8px;">What is your primary goal for this project?</div>
    """, unsafe_allow_html=True)
    q1 = st.radio("Goal:", ["Full Replacement with new hardware", "Repair / Fix existing fixture", "Complete Redo / Relocate"], label_visibility="collapsed")
    st.markdown("</div>", unsafe_allow_html=True)

    # Question 2/4 (Physical Condition)
    st.markdown("""
    <div class="bubble-leo">
        <span class="step-badge">Question 2/4</span>
        <div style="font-weight: 600; margin-bottom: 8px;">What is the working area condition?</div>
    """, unsafe_allow_html=True)
    if cat == "Home Repairs":
        q2 = st.radio("Condition:", ["Drywall with Wood Studs (Dry & Solid)", "Solid Brick or Concrete", "Wall is damp or soft"], label_visibility="collapsed")
    elif cat == "Plumbing":
        q2 = st.radio("Condition:", ["Shut-off valve turns smoothly", "Shut-off valve stuck / leaking", "Main line shut-off needed"], label_visibility="collapsed")
    else:
        q2 = st.radio("Condition:", ["Existing wires present in junction box", "Need new line pulled from panel"], label_visibility="collapsed")
    st.markdown("</div>", unsafe_allow_html=True)

    # Question 3/4 (Materials Check)
    st.markdown("""
    <div class="bubble-leo">
        <span class="step-badge">Question 3/4</span>
        <div style="font-weight: 600; margin-bottom: 8px;">Do you have the hardware, or should the Tasker bring it?</div>
    """, unsafe_allow_html=True)
    q3 = st.radio("Materials:", ["I already have the hardware/materials", "Tasker should bring standard materials (+30 min pickup)"], label_visibility="collapsed")
    st.markdown("</div>", unsafe_allow_html=True)

    # Question 4/4 (Disposal Check)
    st.markdown("""
    <div class="bubble-leo">
        <span class="step-badge">Question 4/4</span>
        <div style="font-weight: 600; margin-bottom: 8px;">How should disposal of old parts be handled?</div>
    """, unsafe_allow_html=True)
    q4 = st.radio("Disposal:", ["Tasker should handle disposal", "I will dispose of old parts myself"], label_visibility="collapsed")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Generate Verified Labour Estimate ⚡", type="primary", use_container_width=True):
        st.session_state.q1 = q1
        st.session_state.q2 = q2
        st.session_state.q3 = q3
        st.session_state.q4 = q4
        st.session_state.cat = cat
        st.session_state.task_name = task_name
        st.session_state.step = 3
        st.rerun()

# --- STAGE 3: QUOTE TICKET & SCHEDULING ---
elif st.session_state.step == 3:
    cat = st.session_state.cat
    task_name = st.session_state.task_name
    q1 = st.session_state.q1
    q2 = st.session_state.q2
    q3 = st.session_state.q3
    q4 = st.session_state.q4

    # Calculation logic (Master Task Library + Leo Operating Rules)
    base_info = TASK_DATABASE[cat][task_name]
    total_minutes = base_info["time"]
    is_licensed = base_info["licensed"]

    # Material pickup buffer
    tasker_brings_mat = "Tasker should bring" in q3
    if tasker_brings_mat:
        total_minutes += 30

    # Complexity condition buffer
    if any(k in q2 for k in ["Brick", "stuck", "new line"]):
        total_minutes += 30

    # Rule 5: 1-hour minimum
    if total_minutes < 60:
        total_minutes = 60

    # Rule 6: Round up to nearest 15 mins
    rem = total_minutes % 15
    if rem != 0:
        total_minutes += (15 - rem)

    hrs = total_minutes // 60
    mins = total_minutes % 60
    time_str = f"{hrs} hr{'s' if hrs > 1 else ''}" + (f" {mins} mins" if mins > 0 else "")

    tasker_type = "1 Licensed Trade Specialist" if is_licensed else "1 General Tasker"

    # Modern Quote Voucher UI
    st.markdown(f"""
    <div class="quote-ticket">
        <div style="display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid rgba(128,128,128,0.2); padding-bottom: 12px; margin-bottom: 16px;">
            <span style="font-weight: 700; font-size: 1.1rem; letter-spacing: 0.05em; color: #f59e0b;">PROJECT LABOUR ESTIMATE</span>
            <span style="font-size: 0.85rem; opacity: 0.7;">STAR HANDYMAN VERIFIED</span>
        </div>
        
        <div style="margin-bottom: 12px;">
            <div style="font-size: 0.85rem; font-weight: 600; opacity: 0.7;">PROJECT SCOPE</div>
            <div style="font-size: 1rem; font-weight: 500;">Execute {task_name.lower()} according to verified specifications ({q1.lower()}).</div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 16px 0;">
            <div class="stats-card">
                <div style="font-size: 0.75rem; font-weight: 600; opacity: 0.7;">ASSIGNED TASKER</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: #3b82f6;">{tasker_type}</div>
            </div>
            <div class="stats-card">
                <div style="font-size: 0.75rem; font-weight: 600; opacity: 0.7;">QUOTED LABOUR TIME</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: #10b981;">{time_str}</div>
            </div>
        </div>

        <div style="font-size: 0.85rem; line-height: 1.5; opacity: 0.85; border-top: 1px solid rgba(128,128,128,0.2); padding-top: 12px;">
            • <b>Materials:</b> {'Tasker will bring everything and confirm details in the chatbox.' if tasker_brings_mat else 'No materials needed for this project.'}<br>
            • <b>Disposal:</b> {'Disposal not included in labour estimate. Tasker arranges in chatbox.' if "Tasker" in q4 else 'Disposal handled by Client.'}<br>
            • <i>This estimate covers labour only. Material receipts are billed upon job completion.</i>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        if st.button("Accept Estimate & Book Slot", type="primary", use_container_width=True):
            st.balloons()
            st.success("🎉 Estimate Confirmed! We are pairing you with your Tasker now.")
    with c2:
        if st.button("← Modify Project", use_container_width=True):
            st.session_state.step = 1
            st.rerun()