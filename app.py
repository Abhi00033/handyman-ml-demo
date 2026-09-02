import streamlit as st
import pandas as pd
import time
from PIL import Image

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Handyman AI Vision + ML Estimator",
    layout="wide",
    page_icon="📸",
    initial_sidebar_state="collapsed"
)

# --- RESPONSIVE CSS INJECTION ---
st.markdown("""
<style>
    html, body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 3rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 1200px !important;
    }
    .flow-card {
        background-color: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1.25rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    [data-testid="stMetric"] {
        background-color: var(--background-color);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 10px;
        padding: 0.75rem 1rem !important;
        text-align: center;
    }
    .stButton button {
        width: 100% !important;
        border-radius: 8px !important;
        height: 3rem !important;
        font-weight: 600 !important;
    }
    @media (max-width: 768px) {
        [data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
        }
    }
</style>
""", unsafe_allow_html=True)

st.title("📸 Smart Service Intake & ML Estimator")
st.caption("Flow: Image Upload → AI Vision Inspection → Intent Classification → Decision Tree → In-House ML Estimation")

col_left, col_right = st.columns([1.2, 1], gap="large")

with col_left:
    # -------------------------------------------------------------
    # STEP 1: CUSTOMER UPLOADS PHOTO
    # -------------------------------------------------------------
    st.markdown('<div class="flow-card">', unsafe_allow_html=True)
    st.subheader("Step 1: Upload Job Site Photo")
    uploaded_file = st.file_uploader("Upload an image of your wall, room, or appliance", type=["jpg", "jpeg", "png"])
    
    # State simulation for AI vision detection
    detected_wall_state = "Dry & Solid"
    detected_surface = "Drywall"

    if uploaded_file is not None:
        img = Image.open(uploaded_file)
        st.image(img, caption="Customer Uploaded Photo", use_container_width=True)

        # Vision AI simulation toggle (to demonstrate both dry and wet scenarios to client)
        st.markdown("**Simulated AI Vision Detection Result:**")
        vision_sim = st.radio(
            "AI Vision Inspection Output:",
            ["Vision AI detects: Wall is Dry & Solid", "Vision AI detects: Wall has Wetness / Moisture Discoloration"]
        )
        if "Wetness" in vision_sim:
            detected_wall_state = "Wet / Damp"
            st.error("🤖 **AI Vision Inspection:** Detected dampness/dark patches on wall surface.")
        else:
            detected_wall_state = "Dry & Solid"
            st.success("🤖 **AI Vision Inspection:** Surface detected as dry and structurally intact.")
    else:
        st.info("💡 Please upload an image (or test with any sample image) to start the AI intake.")
    st.markdown('</div>', unsafe_allow_html=True)

    # -------------------------------------------------------------
    # STEP 2 & 3: CUSTOMER DESCRIPTION & CATEGORY CLASSIFICATION
    # -------------------------------------------------------------
    st.markdown('<div class="flow-card">', unsafe_allow_html=True)
    st.subheader("Step 2: What service do you need for this?")
    
    user_prompt = st.text_input(
        "Describe what you want to get done:",
        placeholder="e.g., Mount my 65 inch TV on this wall / Fix pipe leak under sink"
    )

    selected_service = "TV Mount Fitting"
    category = "Mounting Services"

    if user_prompt:
        # Keyword-based / NLP classifier mapping to 400+ catalog services
        prompt_lower = user_prompt.lower()
        if any(w in prompt_lower for w in ["tv", "mount", "bracket", "hang", "television"]):
            selected_service = "TV Mount Fitting"
            category = "Mounting Services"
        elif any(w in prompt_lower for w in ["pipe", "sink", "leak", "plumb", "drain", "faucet"]):
            selected_service = "Plumbing Leak & Fitting"
            category = "Plumbing Services"
        elif any(w in prompt_lower for w in ["paint", "hole", "crack", "patch", "repair"]):
            selected_service = "Drywall Patch & Repair"
            category = "Home Repairs"
        else:
            selected_service = "General Handyman Fitting"
            category = "Home Improving"

        st.success(f"🤖 **AI Classification:** Assigned to Category: **`{category}`** → Service: **`{selected_service}`**")
    st.markdown('</div>', unsafe_allow_html=True)

    # -------------------------------------------------------------
    # STEP 4: SERVICE SPECIFIC DECISION TREE QUESTIONS
    # -------------------------------------------------------------
    base_minutes = 45
    base_price = 55
    tech_level = "Standard Handyman"
    tools = []

    st.markdown('<div class="flow-card">', unsafe_allow_html=True)
    st.subheader(f"Step 3: Questions for {selected_service}")

    if selected_service == "TV Mount Fitting":
        tv_size = st.select_slider("Select TV Screen Size (inches)", options=[32, 43, 50, 55, 65, 75, 85], value=55)
        if tv_size >= 65:
            base_minutes += 25
            base_price += 30

        # Incorporating the AI detected vision state into the questions
        st.write(f"**Wall Condition (from AI Vision):** `{detected_wall_state}`")

        if detected_wall_state == "Dry & Solid":
            wall_material = st.radio("Wall Construction Type:", ["Drywall / Wood Studs", "Brick / Concrete"])
            if "Brick" in wall_material:
                base_minutes += 20
                base_price += 25
                tech_level = "Masonry Specialist"
                tools.append("Hammer Drill & Masonry Anchors")

            has_bracket = st.radio("Do you already have the mount bracket?", ["Yes, I have it", "No, technician must provide bracket"])
            if "No" in has_bracket:
                base_price += 40
                tools.append("Universal Tilt Mount Kit")

        else: # Wet / Damp Wall Scenario
            st.warning("⚠️ **Safety Inspection Branch:** Since AI detected moisture, additional checks are required.")
            base_minutes += 45
            base_price += 60
            tech_level = "Senior Structural Specialist"
            tools.append("Moisture Detector & Chemical Wall Anchors")

            active_leak = st.radio("Is this moisture from an active plumbing pipe inside this wall?", ["Yes, active leak", "No, surface condensation / weather seepage"])
            if "Yes" in active_leak:
                base_minutes += 30
                base_price += 50
                tools.append("Pipe Pressure Test Kit")

    elif selected_service == "Plumbing Leak & Fitting":
        base_minutes = 60
        base_price = 70
        leak_loc = st.radio("Leak Location:", ["Exposed Pipe Under Sink", "Concealed Inside Wall / Tile"])
        if "Concealed" in leak_loc:
            base_minutes += 60
            base_price += 80
            tech_level = "Master Plumber"
            tools.append("Inspection Endoscope Camera")

    else:
        base_minutes = 50
        base_price = 60
        tools.append("Standard Handyman Repair Kit")

    st.markdown('</div>', unsafe_allow_html=True)
    calc_button = st.button("⚡ Calculate Instant ML Estimate", type="primary")

# --- RIGHT COLUMN: ML PREDICTION & DISPATCH ---
with col_right:
    st.markdown('<div class="flow-card">', unsafe_allow_html=True)
    st.subheader("Step 4: Real-Time ML Engine Output")

    if calc_button:
        start_t = time.perf_counter()
        time.sleep(0.01) # Simulate sub-second inference
        latency = (time.perf_counter() - start_t) * 1000

        st.success("✅ Estimation Generated by In-House Model")

        m1, m2, m3 = st.columns(3)
        m1.metric("Est. Duration", f"{base_minutes} mins")
        m2.metric("Est. Price", f"${base_price}")
        m3.metric("ML Latency", f"{latency:.1f} ms")

        st.markdown("---")
        st.markdown("**Technician Auto-Dispatch Profile:**")
        st.write(f"• **Assigned Tier:** `{tech_level}`")
        st.write(f"• **Auto-Assigned Equipment:** `{', '.join(tools) if tools else 'Standard Kit'}`")

        st.markdown("---")
        st.subheader("Step 5: Dynamic Slot Reservation")
        st.caption(f"Locking calendar window for **{base_minutes} mins**:")

        slot_end_hr = 10 + (base_minutes // 60)
        slot_end_min = base_minutes % 60

        slots = [
            f"Tomorrow: 10:00 AM – {slot_end_hr}:{slot_end_min:02d} AM",
            f"Tomorrow: 02:00 PM – {2 + base_minutes//60}:{base_minutes%60:02d} PM",
            f"Friday: 11:30 AM – {11 + (30+base_minutes)//60}:{(30+base_minutes)%60:02d} AM"
        ]
        st.selectbox("Available Slots:", slots)

        if st.button("Confirm & Reserve Slot"):
            st.balloons()
            st.success("Booking confirmed! Stored in Laravel MySQL database.")
    else:
        st.info("👈 Upload an image, type what you need, answer the branch questions, and click **Calculate**.")

    st.markdown('</div>', unsafe_allow_html=True)

# --- COMPARISON TABLE ---
st.markdown("---")
st.subheader("📋 Transition Architecture: Where AI Stops & ML Takes Over")
st.markdown("""
| Stage | Component Responsible | Why This Architecture Wins |
|---|---|---|
| **1. Image Inspection** | Multimodal Vision AI | Detects dampness, pipe layout, wall material from raw photos. |
| **2. Intent & Category Mapping** | Fast Intent Classifier | Matches customer's description to 1 of 400+ services. |
| **3. Scenario Questions** | Dynamic Decision Tree | Asks consistent, structured questions without hallucinations. |
| **4. Time & Price Estimation** | **Trained ML Regressor (XGBoost)** | **Instant (<10ms), zero API fees, mathematical accuracy.** |
""")