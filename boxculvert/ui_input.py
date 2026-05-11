# boxculvert/ui_input.py

import streamlit as st
from boxculvert.lang_dict import lang_dict

def t(key):
    return lang_dict[st.session_state.get("lang", "EN")].get(key, key)

def input_page():
    if "bc_inputs" not in st.session_state:
        st.session_state.bc_inputs = {
            "clear_span": 3000,
            "clear_height": 2000,
            "t_top_slab": 250,
            "t_bottom_slab": 300,
            "t_wall": 250,
            "fc": 30,
            "fy": 420,
            "soil_density": 18,
            "friction_angle": 30,
            "cohesion": 0,
            "Bd": 3000,
            "H": 2000,
            "install_condition": "Trench",
            "surcharge_uniform": 10,
            "use_wheel_loads": False,
            "wheel_load": 70,
            "wheel_spacing": 1800,
            "tire_contact_length": 250,
            "tire_contact_width": 500,
            "water_level_fraction": 0.0,
        }

    def update_setting(key, value):
        st.session_state.bc_inputs[key] = value

    tabs = st.tabs([
        t("geometry_section"),
        t("material_section") + " & " + t("soil_arching_section"),
        t("loading_section"),
        t("soil_arching_section") + " Detail",
        "Internal Water",
    ])

    # Tab 1: Geometry
    with tabs[0]:
        st.subheader("Box Culvert Cross‑Section Dimensions")
        col1, col2 = st.columns(2)
        with col1:
            clear_span = st.number_input(
                "Clear Span (B) [mm]",
                min_value=500, max_value=20000, step=100,
                value=st.session_state.bc_inputs["clear_span"],
                key="in_clear_span",
            )
            update_setting("clear_span", clear_span)

            t_top = st.number_input(
                "Top Slab Thickness [mm]",
                min_value=100, max_value=2000, step=10,
                value=st.session_state.bc_inputs["t_top_slab"],
                key="in_t_top_slab",
            )
            update_setting("t_top_slab", t_top)

            t_wall = st.number_input(
                "Wall Thickness [mm]",
                min_value=100, max_value=2000, step=10,
                value=st.session_state.bc_inputs["t_wall"],
                key="in_t_wall",
            )
            update_setting("t_wall", t_wall)

        with col2:
            clear_height = st.number_input(
                "Clear Height (Hc) [mm]",
                min_value=500, max_value=20000, step=100,
                value=st.session_state.bc_inputs["clear_height"],
                key="in_clear_height",
            )
            update_setting("clear_height", clear_height)

            t_bottom = st.number_input(
                "Bottom Slab Thickness [mm]",
                min_value=100, max_value=2000, step=10,
                value=st.session_state.bc_inputs["t_bottom_slab"],
                key="in_t_bottom_slab",
            )
            update_setting("t_bottom_slab", t_bottom)

            st.markdown("---")
            st.metric("Overall Width (outside)", f"{clear_span + 2*t_wall} mm")
            st.metric("Overall Height (outside)", f"{clear_height + t_top + t_bottom} mm")

    # Tab 2: Materials & Soil
    with tabs[1]:
        st.subheader("Concrete & Reinforcement")
        col1, col2 = st.columns(2)
        with col1:
            fc = st.number_input(
                "Concrete Strength (f'c) [MPa]",
                min_value=10.0, max_value=100.0, step=2.5,
                value=float(st.session_state.bc_inputs["fc"]),
                key="in_fc",
            )
            update_setting("fc", fc)

        with col2:
            fy = st.number_input(
                "Rebar Yield Strength (fy) [MPa]",
                min_value=200.0, max_value=800.0, step=10.0,
                value=float(st.session_state.bc_inputs["fy"]),
                key="in_fy",
            )
            update_setting("fy", fy)

        st.subheader("Backfill Soil Properties")
        col1, col2, col3 = st.columns(3)
        with col1:
            gamma = st.number_input(
                "Soil Density (γ) [kN/m³]",
                min_value=10.0, max_value=25.0, step=0.5,
                value=float(st.session_state.bc_inputs["soil_density"]),
                key="in_gamma",
            )
            update_setting("soil_density", gamma)

        with col2:
            phi = st.number_input(
                "Friction Angle (φ) [°]",
                min_value=0.0, max_value=60.0, step=1.0,
                value=float(st.session_state.bc_inputs["friction_angle"]),
                key="in_phi",
            )
            update_setting("friction_angle", phi)

        with col3:
            cohesion = st.number_input(
                "Cohesion (c) [kPa]",
                min_value=0.0, max_value=200.0, step=1.0,
                value=float(st.session_state.bc_inputs["cohesion"]),
                key="in_cohesion",
            )
            update_setting("cohesion", cohesion)

        Ka = (1 - st.session_state.bc_inputs["friction_angle"]/90)
        st.caption(f"Approx. lateral earth pressure coefficient Ka ≈ {Ka:.3f}")

    # Tab 3: Loads (Surcharge / Wheel)
    with tabs[2]:
        st.subheader("Traffic / Surface Surcharge")
        q_surch = st.number_input(
            "Uniform Live Load Surcharge [kPa]",
            min_value=0.0, max_value=100.0, step=0.5,
            value=float(st.session_state.bc_inputs["surcharge_uniform"]),
            key="in_surcharge_uniform",
        )
        update_setting("surcharge_uniform", q_surch)

        st.markdown("---")
        st.subheader("Wheel / Axle Loads (optional)")
        use_wheel = st.checkbox(
            "Consider concentrated wheel loads",
            value=st.session_state.bc_inputs["use_wheel_loads"],
            key="in_use_wheel",
        )
        update_setting("use_wheel_loads", use_wheel)

        if use_wheel:
            col1, col2 = st.columns(2)
            with col1:
                wheel_load = st.number_input(
                    "Wheel Load [kN]",
                    min_value=0.0, max_value=500.0, step=5.0,
                    value=float(st.session_state.bc_inputs["wheel_load"]),
                    key="in_wheel_load",
                )
                update_setting("wheel_load", wheel_load)

                tire_len = st.number_input(
                    "Tire Contact Length (along traffic) [mm]",
                    min_value=100, max_value=1000, step=10,
                    value=st.session_state.bc_inputs["tire_contact_length"],
                    key="in_tire_len",
                )
                update_setting("tire_contact_length", tire_len)

            with col2:
                wheel_spacing = st.number_input(
                    "Longitudinal Wheel Spacing [mm]",
                    min_value=500, max_value=10000, step=100,
                    value=st.session_state.bc_inputs["wheel_spacing"],
                    key="in_wheel_spacing",
                )
                update_setting("wheel_spacing", wheel_spacing)

                tire_width = st.number_input(
                    "Tire Contact Width [mm]",
                    min_value=100, max_value=2000, step=10,
                    value=st.session_state.bc_inputs["tire_contact_width"],
                    key="in_tire_width",
                )
                update_setting("tire_contact_width", tire_width)

            if tire_len > 0 and tire_width > 0:
                contact_area = (tire_len * tire_width) / 1e6
                contact_pressure = wheel_load / contact_area if contact_area > 0 else 0
                st.caption(f"Tire contact pressure ≈ {contact_pressure:.1f} kPa")

    # Tab 4: Soil Arching (Installation Detail)
    with tabs[3]:
        st.subheader("Installation Condition for Soil Arching (Marston's Theory)")
        col1, col2 = st.columns(2)
        with col1:
            Bd = st.number_input(
                "Trench Width at top of culvert (Bd) [mm]",
                min_value=500, max_value=20000, step=100,
                value=st.session_state.bc_inputs["Bd"],
                key="in_Bd",
            )
            update_setting("Bd", Bd)

        with col2:
            H = st.number_input(
                "Depth of fill over culvert (H) [mm]",
                min_value=0, max_value=30000, step=100,
                value=st.session_state.bc_inputs["H"],
                key="in_H",
            )
            update_setting("H", H)

        install_condition = st.radio(
            "Installation Type",
            options=["Trench", "Embankment"],
            index=["Trench", "Embankment"].index(st.session_state.bc_inputs["install_condition"]),
            key="in_install_condition",
        )
        update_setting("install_condition", install_condition)

        if install_condition == "Trench":
            st.info("Trench condition: Friction between backfill and trench walls reduces vertical load on culvert. "
                    "Arching factor will be computed based on Bd, H, and soil friction.")
        else:
            st.info("Embankment condition: Full weight of soil column is considered (no reduction from trench walls).")

        if install_condition == "Trench" and Bd > 0 and H > 0:
            ratio = H / Bd
            if ratio > 1.5:
                st.success("High H/Bd ratio → arching effect significant.")
            else:
                st.warning("Low H/Bd ratio → arching effect minimal. Consider full soil load.")

    # Tab 5: Internal Water Level
    with tabs[4]:
        st.subheader("Internal Water Condition")
        water_level = st.slider(
            "Water height inside culvert (fraction of clear height)",
            min_value=0.0, max_value=1.0, step=0.05,
            value=float(st.session_state.bc_inputs["water_level_fraction"]),
            key="in_water_level",
        )
        update_setting("water_level_fraction", water_level)
        water_depth_mm = water_level * st.session_state.bc_inputs["clear_height"]
        st.write(f"Water depth: {water_depth_mm:.0f} mm")
        if water_level == 0.0:
            st.info("Culvert is EMPTY (no internal water).")
        elif water_level >= 1.0:
            st.info("Culvert is FULL of water (surcharge pressure applies).")
        else:
            st.info(f"Partial water level ({water_level*100:.0f}% of height).")

    st.markdown("---")
    if st.button("💾 Save Inputs & Proceed to Analysis", type="primary"):
        st.success("Inputs saved successfully! Navigate to the 'Analysis & Design' page.")
