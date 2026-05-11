# boxculvert/ui_calculation.py

import streamlit as st
from boxculvert.calc_engine import analyze_box_culvert, design_culvert_sections
from boxculvert.lang_dict import lang_dict

def t(key):
    return lang_dict[st.session_state.get("lang", "EN")].get(key, key)

def calculation_page():
    st.header(t("calculation_title"))
    if "bc_inputs" not in st.session_state:
        st.warning("Silakan isi data di halaman Input terlebih dahulu.")
        return

    inputs = st.session_state.bc_inputs

    if st.button("▶️ Jalankan Analisis & Desain", type="primary"):
        with st.spinner("Menganalisis struktur dan mendesain tulangan..."):
            # Analisis struktur
            analysis_res = analyze_box_culvert(inputs)
            st.session_state.analysis_results = analysis_res

            # Simpan model frame untuk plotting di halaman Output
            st.session_state.frame_model_empty = analysis_res["frame_model_empty"]
            st.session_state.frame_model_full = analysis_res["frame_model_full"]

            # Desain penulangan
            design_res = design_culvert_sections(analysis_res, inputs)
            st.session_state.design_results = design_res

        st.success("Analisis dan desain selesai! Silakan ke halaman Reports.")
