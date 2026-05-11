# =============================================================================
# pages/11_UDitch_CU.py  — Tahap C Final
# =============================================================================
import sys, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as st
from uditch.lang_dict   import t
from uditch.ui_input    import render_input
from uditch.calc_engine import run_load_analysis, run_section_design
from uditch.ui_output   import render_output
from uditch.perhitungan import render_perhitungan   # ✅ Tahap C
from uditch.laporan     import build_laporan_docx, build_laporan_pdf  # ✅ Export

st.set_page_config(
    page_title="U-Ditch Analysis",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

for k, v in {
    "lang": "ID", "condition": "Kondisi 1",
    "input_data": {}, "calc_results": None,
    "design_result": None, "calc_done": False,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

lang = st.session_state["lang"]

# ── SIDEBAR ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"**{t('language_label', lang)}**")
    cL, cR = st.columns(2)
    if cL.button("🇮🇩 Indonesia", use_container_width=True,
                 type="primary" if lang=="ID" else "secondary", key="btn_id"):
        st.session_state["lang"] = "ID"; st.rerun()
    if cR.button("🇬🇧 English", use_container_width=True,
                 type="primary" if lang=="EN" else "secondary", key="btn_en"):
        st.session_state["lang"] = "EN"; st.rerun()

    st.divider()
    st.markdown(f"**{t('sidebar_condition', lang)}**")
    cond_map = {
        t("condition_1", lang): "Kondisi 1",
        t("condition_2", lang): "Kondisi 2",
        t("condition_3", lang): "Kondisi 3",
    }
    labels  = list(cond_map.keys())
    inv_map = {v: k for k, v in cond_map.items()}
    saved   = st.session_state["condition"]
    default = labels.index(inv_map.get(saved, labels[0]))

    sel = st.radio("##cond", labels, index=default,
                   label_visibility="collapsed", key="radio_cond")
    if cond_map[sel] != st.session_state["condition"]:
        st.session_state["condition"]    = cond_map[sel]
        st.session_state["calc_done"]    = False
        st.session_state["calc_results"] = None
        st.session_state["design_result"]= None
        st.rerun()

    st.divider()
    st.caption(t("footer", lang))

# ── HEADER ─────────────────────────────────────────────────────────────────────
lang      = st.session_state["lang"]
condition = st.session_state["condition"]

st.title(f"🏗️ {t('app_title', lang)}")
st.markdown(f"*{t('app_subtitle', lang)}*")

badge = {"Kondisi 1":("🟡",t("condition_1",lang)),
         "Kondisi 2":("🟠",t("condition_2",lang)),
         "Kondisi 3":("🔵",t("condition_3",lang))}
ic, lb = badge.get(condition, ("⚪","—"))
st.info(f"{ic} **{lb}**")
st.divider()

# ── TABS ───────────────────────────────────────────────────────────────────────
tab_inp, tab_calc, tab_out = st.tabs([
    t("tab_input", lang),
    t("tab_calculation", lang),
    t("tab_output", lang),
])

# ── TAB 1: INPUT ──────────────────────────────────────────────────────────────
with tab_inp:
    render_input(lang, condition)

# ── TAB 2: CALCULATION — INI YANG UTAMA ───────────────────────────────────────
with tab_calc:
    inp = st.session_state.get("input_data", {})
    if not inp:
        st.warning(t("msg_input_first", lang))
    else:
        # ── Tombol hitung ─────────────────────────────────────────────────────
        col_btn, col_status = st.columns([1, 3])
        with col_btn:
            run_btn = st.button(t("msg_run_calc", lang),
                                type="primary", use_container_width=True,
                                key="btn_run")
        with col_status:
            if st.session_state["calc_done"]:
                fr = st.session_state["calc_results"]
                wb = fr.wall_base if fr else None
                if wb:
                    st.success(
                        f"✅ Selesai — Mu={wb.Mu:.3f}kN·m/m | "
                        f"Vu={wb.Vu:.3f}kN/m | Nu={wb.Nu:.3f}kN/m"
                    )

        if run_btn:
            with st.spinner("⚙️ Menghitung..." if lang=="ID" else "⚙️ Calculating..."):
                try:
                    fr = run_load_analysis(inp)
                    dr = run_section_design(fr, inp)
                    st.session_state["calc_results"]  = fr
                    st.session_state["design_result"] = dr
                    st.session_state["calc_done"]     = True
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {e}")
                    st.exception(e)

        # ── TAMPILAN PERHITUNGAN UTAMA ─────────────────────────────────────────
        if st.session_state["calc_done"]:
            fr = st.session_state["calc_results"]
            dr = st.session_state["design_result"]
            # ▶ INI INTI TAHAP C — tampilkan seluruh rantai perhitungan
            render_perhitungan(fr, dr, inp, lang)

# ── TAB 3: OUTPUT ─────────────────────────────────────────────────────────────
with tab_out:
    if not st.session_state["calc_done"]:
        st.warning(t("msg_calc_first", lang))
        st.info("Jalankan perhitungan di tab Perhitungan terlebih dahulu."
                if lang=="ID" else "Run the calculation in the Calculation tab first.")
    else:
        fr  = st.session_state["calc_results"]
        dr  = st.session_state["design_result"]
        inp_d = st.session_state["input_data"]

        st.markdown(
            "### 📥 Unduh Laporan Perhitungan"
            if lang=="ID" else
            "### 📥 Download Calculation Report"
        )
        st.info(
            "Laporan berisi seluruh rantai perhitungan: "
            "Data → Tekanan (segitiga/kotak/parabola) → Resultan → "
            "Mu/Vu/Nu → Diagram → Kapasitas & Kontrol"
            if lang=="ID" else
            "Report contains the full calculation chain: "
            "Data → Pressure (triangle/rect/parabola) → Resultant → "
            "Mu/Vu/Nu → Diagrams → Capacity & Checks"
        )

        from datetime import datetime
        fname_base = f"UD_{fr.condition.replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}"

        col_w, col_p = st.columns(2)
        with col_w:
            st.markdown("#### 📄 Word (.docx)")
            try:
                with st.spinner("Membuat Word..." if lang=="ID" else "Building Word..."):
                    docx_bytes = build_laporan_docx(fr, dr, inp_d, lang)
                st.download_button(
                    label="📄 " + ("Unduh Word (.docx)" if lang=="ID" else "Download Word (.docx)"),
                    data=docx_bytes,
                    file_name=fname_base + ".docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    type="primary",
                    use_container_width=True,
                    key="dl_docx",
                )
            except Exception as e:
                st.error(f"Error Word: {e}")
                st.exception(e)

        with col_p:
            st.markdown("#### 📑 PDF")
            try:
                with st.spinner("Membuat PDF..." if lang=="ID" else "Building PDF..."):
                    pdf_bytes = build_laporan_pdf(fr, dr, inp_d, lang)
                st.download_button(
                    label="📑 " + ("Unduh PDF" if lang=="ID" else "Download PDF"),
                    data=pdf_bytes,
                    file_name=fname_base + ".pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True,
                    key="dl_pdf",
                )
            except Exception as e:
                st.error(f"Error PDF: {e}")
                st.exception(e)

        st.divider()
        st.caption(
            "Laporan identik dengan tampilan di tab Perhitungan. "
            "SNI 2847:2019 | SNI 8460:2017 | AASHTO LRFD 9th Ed."
            if lang=="ID" else
            "Report matches the Calculation tab display. "
            "SNI 2847:2019 | SNI 8460:2017 | AASHTO LRFD 9th Ed."
        )
