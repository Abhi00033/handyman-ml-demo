import streamlit as st
import pandas as pd
import time

st.set_page_config(page_title="Handyman Decision Engine & Auto-Estimator", layout="wide", page_icon="🛠️")

st.title("🛠️ Handyman Dynamic Decision Tree & Auto-Estimator")
st.caption("Heuristic Decision Tree Prototype: Deterministic Q&A → Baseline Estimation → Technician Dispatch")

col_left, col_right = st.columns([1.3, 1])

with col_left:
    st.subheader("Step 1: Customer Service Selection & Scenarios")

    service_category = st.selectbox(
        "Choose Service Category",
        [
            "Mounting Services (TV & Shelves)",
            "Plumbing Services",
            "Home Repairs",
            "Home Improving"
        ]
    )

    st.markdown("---")

    # Initial baseline values (Base time in mins, Base cost in $)
    base_minutes = 30
    base_price = 40
    tech_spec = "Standard Handyman"
    tool_requirements = []

    # ==========================================
    # 1. MOUNTING SERVICES
    # ==========================================
    if service_category == "Mounting Services (TV & Shelves)":
        mount_type = st.radio("What are you mounting?", ["Television (TV)", "Heavy Wall Shelves / Mirrors"])

        if mount_type == "Television (TV)":
            base_minutes = 45
            base_price = 55
            tv_size = st.select_slider("TV Screen Size (inches)", options=[32, 43, 55, 65, 75, 85], value=55)
            if tv_size >= 65:
                base_minutes += 25
                base_price += 30

            # Core Decision Question
            is_wall_dry = st.radio("Is the wall dry and structurally sound?", ["Yes (Dry & Solid)", "No (Wet / Damp / Peeling)"])

            if is_wall_dry == "Yes (Dry & Solid)":
                wall_material = st.radio("Wall Construction:", ["Drywall / Wood Studs", "Brick / Solid Concrete"])
                if "Brick" in wall_material:
                    base_minutes += 20
                    base_price += 25
                    tool_requirements.append("Hammer Drill & Masonry Bits")
                    tech_spec = "Masonry-Equipped Specialist"

                has_bracket = st.radio("Do you already have the mount bracket?", ["Yes, I have it", "No, technician must provide bracket"])
                if "No" in has_bracket:
                    base_price += 40
                    tool_requirements.append("Heavy Duty Tilt Mount Kit")

            else:  # Wall is Wet / Damp
                st.error("⚠️ Wet Wall Scenario: Cannot mount directly into damp drywall without structural assessment.")
                base_minutes += 45
                base_price += 60
                tech_spec = "Senior Structural Specialist"
                tool_requirements.append("Moisture Meter & Heavy Anchors")

                leak_source = st.radio("Is there an active pipe leaking inside the wall?", ["Yes, active leak", "No, dampness / seepage only"])
                if "Yes" in leak_source:
                    base_minutes += 30
                    base_price += 50
                    st.warning("Technician will first isolate moisture source before drilling.")

        else: # Shelves / Mirrors
            base_minutes = 35
            base_price = 45
            shelf_count = st.number_input("How many shelves/items to hang?", min_value=1, max_value=10, value=2)
            base_minutes += (shelf_count - 1) * 20
            base_price += (shelf_count - 1) * 15

    # ==========================================
    # 2. PLUMBING SERVICES
    # ==========================================
    elif service_category == "Plumbing Services":
        plumbing_task = st.radio("Select Plumbing Task", ["Faucet / Tap Repair & Replacement", "Clogged Drain / Toilet", "Pipe Leak Repair"])

        if plumbing_task == "Faucet / Tap Repair & Replacement":
            base_minutes = 40
            base_price = 50
            has_new_faucet = st.radio("Do you have the replacement faucet already?", ["Yes, I bought it", "No, technician must supply standard fixture"])
            if "No" in has_new_faucet:
                base_price += 45

            shutoff_works = st.radio("Does the under-sink water shut-off valve work?", ["Yes, turns off smoothly", "No / Stuck / Leaking itself"])
            if "No" in shutoff_works:
                base_minutes += 30
                base_price += 35
                st.warning("⚠️ Main water shutoff key required. Additional valve replacement factored in.")
                tool_requirements.append("Main Valve Key & Pipe Threader")

        elif plumbing_task == "Clogged Drain / Toilet":
            base_minutes = 45
            base_price = 60
            clog_location = st.radio("Where is the clog located?", ["Single Sink / Basin", "Toilet Bowl", "Main Sewer Line (Multiple drains backing up)"])
            if clog_location == "Single Sink / Basin":
                base_minutes += 15
                tool_requirements.append("Standard Hand Drain Auger")
            elif clog_location == "Toilet Bowl":
                base_minutes += 25
                base_price += 20
                tool_requirements.append("Heavy Toilet Auger")
            else:
                base_minutes += 75
                base_price += 110
                tech_spec = "Master Plumber"
                tool_requirements.append("Electric Motorized Drain Snake (50ft)")

        elif plumbing_task == "Pipe Leak Repair":
            base_minutes = 60
            base_price = 80
            pipe_access = st.radio("Is the leaking pipe exposed or hidden inside wall/ceiling?", ["Exposed (Under sink / Basement)", "Concealed (Inside drywall / tile)"])
            if "Concealed" in pipe_access:
                base_minutes += 60
                base_price += 90
                tech_spec = "Senior Pipe Technician"
                tool_requirements.append("Wall Inspection Camera & Drywall Saw")
                st.warning("Drywall cutting and patching required to reach pipe.")

    # ==========================================
    # 3. HOME REPAIRS
    # ==========================================
    elif service_category == "Home Repairs":
        repair_task = st.radio("Type of Repair", ["Drywall Hole Patching", "Door Alignment / Lock Fix"])

        if repair_task == "Drywall Hole Patching":
            base_minutes = 50
            base_price = 65
            hole_size = st.radio("What size is the damage?", ["Small (Nails / Dents < 2 inches)", "Medium (Doorknob hole 3-6 inches)", "Large (> 12 inches structural patch)"])
            if "Medium" in hole_size:
                base_minutes += 30
                base_price += 35
                tool_requirements.append("Drywall Mesh Patch & Quick-Dry Mud")
            elif "Large" in hole_size:
                base_minutes += 70
                base_price += 80
                tool_requirements.append("Drywall Board, Wood Backer & Joint Tape")

            needs_paint = st.radio("Do you need the technician to paint over the patch?", ["No, I will paint it", "Yes, technician must color-match and paint"])
            if "Yes" in needs_paint:
                base_minutes += 35
                base_price += 40

        elif repair_task == "Door Alignment / Lock Fix":
            base_minutes = 45
            base_price = 55
            issue_type = st.radio("What is the issue?", ["Door scrapes floor/frame (Misaligned)", "Door knob/latch broken", "Deadbolt install on new door"])
            if "Deadbolt" in issue_type:
                base_minutes += 40
                base_price += 45
                tool_requirements.append("Hole Saw & Chisel Kit")

    # ==========================================
    # 4. HOME IMPROVING
    # ==========================================
    elif service_category == "Home Improving":
        improve_task = st.radio("Improvement Project", ["Ceiling Fan / Light Fixture Replacement", "Cabinet Hardware & Handles Installation"])

        if improve_task == "Ceiling Fan / Light Fixture Replacement":
            base_minutes = 60
            base_price = 75
            ceiling_height = st.radio("What is the ceiling height?", ["Standard (8 to 9 feet)", "High Ceiling (10 to 14+ feet)"])
            if "High" in ceiling_height:
                base_minutes += 30
                base_price += 40
                tool_requirements.append("12ft Extension Ladder")

            existing_junction = st.radio("Is electrical wiring and ceiling box already present?", ["Yes, replacing existing fixture", "No, new location wiring required"])
            if "No" in existing_junction:
                base_minutes += 90
                base_price += 120
                tech_spec = "Licensed Electrician Specialist"
                tool_requirements.append("Romex Cable & Conduit Snake")

        elif improve_task == "Cabinet Hardware & Handles Installation":
            base_minutes = 40
            base_price = 50
            handle_count = st.number_input("Number of cabinet doors/drawers to fit:", min_value=2, max_value=50, value=10)
            holes_exist = st.radio("Are holes already drilled in cabinets?", ["Yes, direct screw replacement", "No, fresh drilling required with template"])
            
            if "No" in holes_exist:
                base_minutes += handle_count * 6
                base_price += handle_count * 5
                tool_requirements.append("Cabinet Hardware Drilling Jig")
            else:
                base_minutes += handle_count * 3
                base_price += handle_count * 3

    calc_btn = st.button("Calculate Automated Estimate & Open Slots", type="primary")

# --- RIGHT COLUMN: ESTIMATE OUTPUT & SCHEDULING ---
with col_right:
    st.subheader("Step 2: Auto-Generated Estimate & Slot Assignment")

    if calc_btn:
        start_clock = time.perf_counter()
        time.sleep(0.01) # Simulate tiny compute time
        latency = (time.perf_counter() - start_clock) * 1000

        st.success("✅ Estimation Generated via Deterministic Decision Engine")

        m1, m2, m3 = st.columns(3)
        m1.metric("Predicted Duration", f"{base_minutes} mins")
        m2.metric("Estimated Cost", f"${base_price}")
        m3.metric("Calculation Time", f"{latency:.2f} ms")

        st.markdown("---")
        st.markdown("#### Dynamic Technician Requirements:")
        st.write(f"• **Assigned Level:** `{tech_spec}`")
        if tool_requirements:
            st.write(f"• **Mandatory Tools Dispatched:** `{', '.join(tool_requirements)}`")
        else:
            st.write("• **Mandatory Tools Dispatched:** `Standard Toolkit`")

        st.markdown("---")
        st.subheader("Step 3: Automated Technician Slot Booking")
        st.caption(f"Slots dynamically blocked for **{base_minutes} minutes** of work + 30 min transit buffer:")

        slot_end_hr = 10 + (base_minutes // 60)
        slot_end_min = base_minutes % 60

        slot_options = [
            f"Tomorrow: 10:00 AM – {slot_end_hr}:{slot_end_min:02d} AM (Tech: Sarah M.)",
            f"Tomorrow: 02:00 PM – {2 + base_minutes//60}:{base_minutes%60:02d} PM (Tech: John D.)",
            f"Friday: 11:30 AM – {11 + (30+base_minutes)//60}:{(30+base_minutes)%60:02d} AM (Tech: Alex R.)"
        ]
        st.selectbox("Select Available Time Window:", slot_options)

        if st.button("Confirm Booking"):
            st.balloons()
            st.success("Booking stored in database! Notification sent to technician app.")
    else:
        st.info("Pick a category on the left, navigate the scenario questions, and click Calculate to view the estimate.")

st.markdown("---")

# --- STEP 4: CLIENT PRESENTATION EXPLANATION ---
st.subheader("📋 Executive Walkthrough: How This Transitions to ML")
st.markdown("""
| Stage | Current Claude AI Setup | What This Demo Demonstrates (Current Phase) | Final Production ML (Target) |
|---|---|---|---|
| **Question Flow** | LLM invents open-ended questions | Controlled, branching Decision Trees per service | Structured dynamic JSON forms stored in DB |
| **Duration / Cost** | LLM guesses an estimate | Rule-based baseline heuristic with question deltas | **XGBoost / LightGBM Regression** trained on real invoices |
| **Speed** | 3,000 – 5,000 ms per response | **< 5 ms (Instantaneous)** | **< 10 ms (Instantaneous)** |
| **Cost** | Anthropic API token charges every session | **$0.00** | **$0.00** |
""")