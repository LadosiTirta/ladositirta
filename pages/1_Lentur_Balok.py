"""
=============================================================
pages/1_Lentur_Balok.py
HALAMAN 1 - Evaluasi Kapasitas Lentur, Geser & Torsi Balok Beton Bertulang
Referensi : SNI 2847:2019 (ACI 318-14)
Framework : Streamlit (multipage)

Import dari:
  utils.balok_calc   → semua fungsi hitung
  utils.balok_report → TEXT dict, create_word_balok, create_pdf_balok
=============================================================
"""

import datetime
import streamlit as st
import pandas as pd

from utils.balok_calc import (
    DIAMETER_LIST,
    hitung_lapis_tarik, hitung_lapis_tekan,
    evaluasi_balok,
    hitung_geser, hitung_torsi,
    buat_steps_balok, buat_steps_geser, buat_steps_torsi,
    gambar_penampang, fig_to_png_bytes,
)
from utils.balok_report import TEXT, create_word_balok, create_pdf_balok


# ============================================================
# KONFIGURASI HALAMAN
# ============================================================
st.set_page_config(
    page_title="Evaluasi Lentur, Geser & Torsi Balok | SNI 2847:2019",
    page_icon="🏗",
    layout="wide",
)

st.markdown("""
<style>
  .main-title{font-size:1.6rem;font-weight:600;color:#1a3c5e;margin-bottom:0}
  .sub-title{font-size:.9rem;color:#666;margin-bottom:1.5rem}
  .step-box{background:#f8f9fa;border-left:4px solid #1a3c5e;border-radius:0 8px 8px 0;
            padding:12px 16px;margin-bottom:10px;font-family:monospace;font-size:.85rem}
  .step-hdr{font-weight:700;color:#1a3c5e;font-size:.8rem;
            text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
  .result-ok  {background:#e8f5e9;border-left:4px solid #2e7d32;color:#1b5e20;
               padding:12px 16px;border-radius:8px;font-weight:600;margin-bottom:8px}
  .result-warn{background:#fff8e1;border-left:4px solid #f9a825;color:#5d4037;
               padding:12px 16px;border-radius:8px;font-weight:600;margin-bottom:8px}
  .result-fail{background:#ffebee;border-left:4px solid #c62828;color:#b71c1c;
               padding:12px 16px;border-radius:8px;font-weight:600;margin-bottom:8px}
  .metric-card{background:white;border:1px solid #e0e0e0;border-radius:10px;
               padding:14px;text-align:center}
  .metric-lbl{font-size:.75rem;color:#888;margin-bottom:4px}
  .metric-val{font-size:1.5rem;font-weight:700;color:#1a3c5e}
  .metric-unt{font-size:.75rem;color:#aaa}
  .ref-badge{display:inline-block;background:#e3f2fd;color:#1565c0;
             font-size:.7rem;padding:2px 8px;border-radius:20px;margin-bottom:6px}
  .group-hdr{font-size:.85rem;font-weight:700;color:#1a3c5e;letter-spacing:.5px;
             text-transform:uppercase;margin-top:.6rem;margin-bottom:.3rem}
  hr.divider{border:none;border-top:2px solid #e0e0e0;margin:1.5rem 0}
</style>
""", unsafe_allow_html=True)


# ============================================================
# HELPER SESSION STATE
# ============================================================
def _init_state():
    defaults = {
        "balok_hasil":         None,
        "balok_steps":         None,
        "balok_geser_hasil":   None,
        "balok_geser_steps":   None,
        "balok_geser_inputs":  None,
        "balok_torsi_hasil":   None,
        "balok_torsi_steps":   None,
        "balok_torsi_inputs":  None,
        "balok_word":          None,
        "balok_pdf":           None,
        "balok_fig":           None,
        "balok_last_inputs":   {},
        "balok_nama_file":     "",
        "balok_timestamp":     "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _inputs_changed(snap_now):
    last = st.session_state.balok_last_inputs
    if not last:
        return False
    return any(snap_now.get(k) != last.get(k) for k in snap_now)


# ============================================================
# UI
# ============================================================
_init_state()

# Sidebar: Pilih Bahasa
lang = st.sidebar.selectbox("Language / Bahasa", ["ID", "EN"])
T = TEXT[lang]  # Shortcut ke dictionary

# ============================================================
# PROJECT INFO — sidebar expander
# ============================================================
with st.sidebar.expander(T["proj_info"], expanded=False):
    proj_nama    = st.text_input(T["proj_name"],    value=T["proj_val"],   key="pi_nama")
    proj_lokasi  = st.text_input(T["proj_lokasi"],  value="",              key="pi_lokasi")
    proj_eng     = st.text_input(T["proj_eng"],     value="",              key="pi_eng")
    proj_nodok   = st.text_input(T["proj_nodok"],   value="",              key="pi_nodok")
    proj_tgl     = st.text_input(T["proj_tgl"],
                                 value=datetime.date.today().strftime("%d/%m/%Y"),
                                 key="pi_tgl")
    proj_catatan = st.text_area(T["proj_catatan"],  value="",  height=70,  key="pi_catatan")

proj_info = dict(
    nama=proj_nama, lokasi=proj_lokasi, engineer=proj_eng,
    nodok=proj_nodok, tanggal=proj_tgl, catatan=proj_catatan,
)

# ============================================================
# SISTEM SEISMIK — sidebar
# ============================================================
sistem_list = T["sistem_list"]
sistem_rangka = st.sidebar.selectbox(
    T["sistem_rangka"],
    options=sistem_list,
    index=0,
    key="balok_sistem_rangka",
    help=T["sistem_help"],
)
_sistem_map = {0: "Biasa", 1: "SRPMB", 2: "SRPMM", 3: "SRPMK"}
sistem_kode = _sistem_map[sistem_list.index(sistem_rangka)]

# ============================================================
# JUDUL HALAMAN
# ============================================================
st.markdown(f'<p class="main-title">{T["title"]}</p>', unsafe_allow_html=True)
st.markdown(f'<p class="sub-title">{T["subtitle"]}</p>', unsafe_allow_html=True)
st.markdown('<hr class="divider">', unsafe_allow_html=True)

col_inp, col_out = st.columns([1, 2], gap="large")

with col_inp:
    st.markdown(f"### {T['data_input']}")

    st.markdown(f'<div class="group-hdr">{T["gaya_dalam"]}</div>', unsafe_allow_html=True)
    Mu  = st.number_input(T["mu"],  min_value=0.0,   max_value=10000.0, value=200.0, step=5.0,  format="%.2f", key="balok_inp_mu")
    Vu  = st.number_input(T["vu"],  min_value=0.0,   max_value=5000.0,  value=80.0,  step=5.0,  format="%.2f", key="balok_inp_vu")
    Tu  = st.number_input(T["tu"],  min_value=0.0,   max_value=2000.0,  value=0.0,   step=1.0,  format="%.2f", key="balok_inp_tu", help=T["tu_help"])

    st.markdown(f'<div class="group-hdr">{T["material"]}</div>', unsafe_allow_html=True)
    fc  = st.number_input(T["fc"],  min_value=17.0,  max_value=100.0,   value=30.0,  step=1.0,  format="%.1f", key="balok_inp_fc")
    fy  = st.number_input(T["fy"],  min_value=240.0, max_value=600.0,   value=400.0, step=10.0, format="%.0f", key="balok_inp_fy")
    fyt = st.number_input(T["fyt"], min_value=240.0, max_value=420.0,   value=240.0, step=10.0, format="%.0f", key="balok_inp_fyt", help=T["fyt_help"])

    st.markdown(f'<div class="group-hdr">{T["geometri"]}</div>', unsafe_allow_html=True)
    cb, ch_ = st.columns(2)
    with cb:
        b = st.number_input(T["b"], min_value=100.0, max_value=2000.0, value=300.0, step=10.0, format="%.0f", key="balok_inp_b")
    with ch_:
        h = st.number_input(T["h"], min_value=100.0, max_value=5000.0, value=500.0, step=10.0, format="%.0f", key="balok_inp_h")
    cc_sel = st.number_input(T["cc"], min_value=15.0, max_value=100.0, value=40.0, step=5.0,  format="%.0f", key="balok_inp_cc")
    ds_dia = st.number_input(T["ds"], min_value=6.0,  max_value=16.0,  value=10.0, step=1.0,  format="%.0f", key="balok_inp_ds")

    st.markdown(f'<div class="group-hdr">{T["sengkang"]}</div>', unsafe_allow_html=True)
    cs1, cs2 = st.columns(2)
    with cs1:
        s_seng = st.number_input(T["s"],     min_value=50.0, max_value=600.0, value=150.0, step=10.0, format="%.0f", key="balok_inp_s")
    with cs2:
        n_kaki = st.number_input(T["nkaki"], min_value=2,    max_value=6,     value=2,     step=1,                   key="balok_inp_nkaki", help=T["nkaki_help"])

    st.markdown(f'<div class="group-hdr">{T["torsi_add"]}</div>', unsafe_allow_html=True)
    tipe_torsi    = st.radio(    T["tipe_torsi"], options=["Equilibrium", "Compatibility"], index=0, key="balok_inp_tipe_torsi",    help=T["tipe_torsi_help"], horizontal=True)
    db_long_torsi = st.selectbox(T["db_long"],   options=[10, 13, 16, 19],                 index=1, key="balok_inp_db_long_torsi", help=T["db_long_help"])

    # ---- TULANGAN TARIK (bawah) ----
    st.markdown(f'<div class="group-hdr">{T["tarik"]}</div>', unsafe_allow_html=True)
    st.caption(T["tarik_cap"])
    ct1, ct2 = st.columns(2)
    with ct1:
        n_t1  = st.number_input(f"{T['lapis']}-1: {T['jml']}", min_value=0, max_value=20, value=4, step=1, key="balok_inp_nt1")
        n_t2  = st.number_input(f"{T['lapis']}-2: {T['jml']}", min_value=0, max_value=20, value=0, step=1, key="balok_inp_nt2")
    with ct2:
        db_t1 = st.selectbox(f"{T['lapis']}-1: {T['dia']}", DIAMETER_LIST, index=4, key="balok_inp_dbt1")
        db_t2 = st.selectbox(f"{T['lapis']}-2: {T['dia']}", DIAMETER_LIST, index=4, key="balok_inp_dbt2")

    # ---- TULANGAN TEKAN (atas) ----
    st.markdown(f'<div class="group-hdr">{T["tekan"]}</div>', unsafe_allow_html=True)
    st.caption(T["tekan_cap"])
    cc1, cc2 = st.columns(2)
    with cc1:
        n_c1  = st.number_input(f"{T['lapis']}-1: {T['jml']}", min_value=0, max_value=20, value=2, step=1, key="balok_inp_nc1")
        n_c2  = st.number_input(f"{T['lapis']}-2: {T['jml']}", min_value=0, max_value=20, value=0, step=1, key="balok_inp_nc2")
    with cc2:
        db_c1 = st.selectbox(f"{T['lapis']}-1: {T['dia']}", DIAMETER_LIST, index=3, key="balok_inp_dbc1")
        db_c2 = st.selectbox(f"{T['lapis']}-2: {T['dia']}", DIAMETER_LIST, index=3, key="balok_inp_dbc2")

    st.markdown("")
    tombol = st.button(T["btn_hitung"], use_container_width=True, type="primary", key="balok_btn_hitung")


# ============================================================
# PROSES HITUNG & UI HASIL
# ============================================================
if tombol:
    valid = True
    if n_t1 == 0 and n_t2 == 0:
        st.error(T["err_tarik"]); valid = False
    if Mu <= 0:
        st.error(T["err_mu"]); valid = False
    if Vu < 0:
        st.error(T["err_vu"]); valid = False
    if Tu < 0:
        st.error(T["err_tu"]); valid = False

    if valid:
        now        = datetime.datetime.now()
        ts_file    = now.strftime("%Y%m%d_%H%M")
        ts_display = now.strftime("%d %B %Y  %H:%M")

        lapis_tarik, d_tarik, As_tarik = hitung_lapis_tarik(h, cc_sel, ds_dia, n_t1, db_t1, n_t2, db_t2)
        lapis_tekan, d_tekan, As_tekan = hitung_lapis_tekan(cc_sel, ds_dia, n_c1, db_c1, n_c2, db_c2)

        if d_tarik >= h or d_tarik <= 0:
            st.error(T["err_d"].format(d=d_tarik))
        else:
            R = evaluasi_balok(fc, fy, b, h, cc_sel, ds_dia,
                               lapis_tarik, lapis_tekan, d_tarik, As_tarik, d_tekan, As_tekan, Mu)
            steps = buat_steps_balok(fc, fy, b, h, cc_sel, ds_dia, lapis_tarik, lapis_tekan, R)

            G = hitung_geser(fc, fyt, b, d_tarik, Vu, ds_dia, s_seng, int(n_kaki), 1.0)
            steps_geser  = buat_steps_geser(fc, fyt, b, d_tarik, Vu, ds_dia, s_seng, int(n_kaki), G)
            geser_inputs = dict(Vu=Vu, fyt=fyt, s_seng=s_seng, n_kaki=int(n_kaki))

            Tor = hitung_torsi(fc, fy, fyt, b, h, cc_sel, ds_dia, s_seng,
                               Tu, Vu, G["Vc"], d_tarik, G["Av_pasang"],
                               tipe_torsi, float(db_long_torsi), 1.0)
            steps_torsi  = buat_steps_torsi(fc, fyt, fy, b, h, cc_sel, ds_dia, s_seng, Tu, Vu, d_tarik, Tor)
            torsi_inputs = dict(Tu=Tu, tipe_torsi=tipe_torsi, db_long_torsi=float(db_long_torsi))

            fig     = gambar_penampang(b, h, cc_sel, ds_dia, lapis_tarik, lapis_tekan, c=R["c"], torsi_data=Tor)
            png_buf = fig_to_png_bytes(fig)

            w_buf = create_word_balok(
                fc, fy, b, h, cc_sel, ds_dia, Mu, lapis_tarik, lapis_tekan,
                R, steps, proj_info=proj_info, png_buf=png_buf, lang=lang,
                G=G, steps_geser=steps_geser, geser_inputs=geser_inputs,
                Tor=Tor, steps_torsi=steps_torsi, torsi_inputs=torsi_inputs,
                timestamp_str=ts_display,
            )
            png_buf.seek(0)
            p_buf = create_pdf_balok(
                fc, fy, b, h, cc_sel, ds_dia, Mu, lapis_tarik, lapis_tekan,
                R, steps, proj_info=proj_info, png_buf=png_buf, lang=lang,
                G=G, steps_geser=steps_geser, geser_inputs=geser_inputs,
                Tor=Tor, steps_torsi=steps_torsi, torsi_inputs=torsi_inputs,
                timestamp_str=ts_display,
            )

            snap = dict(
                proj_nama=proj_nama, Mu=Mu, Vu=Vu, Tu=Tu,
                fc=fc, fy=fy, fyt=fyt, b=b, h=h, cc=cc_sel, ds=ds_dia,
                s_seng=s_seng, n_kaki=int(n_kaki),
                tipe_torsi=tipe_torsi, db_long_torsi=float(db_long_torsi),
                n_t1=n_t1, db_t1=db_t1, n_t2=n_t2, db_t2=db_t2,
                n_c1=n_c1, db_c1=db_c1, n_c2=n_c2, db_c2=db_c2,
                sistem_kode=sistem_kode,
            )

            st.session_state.balok_hasil        = R
            st.session_state.balok_steps        = steps
            st.session_state.balok_geser_hasil  = G
            st.session_state.balok_geser_steps  = steps_geser
            st.session_state.balok_geser_inputs = geser_inputs
            st.session_state.balok_torsi_hasil  = Tor
            st.session_state.balok_torsi_steps  = steps_torsi
            st.session_state.balok_torsi_inputs = torsi_inputs
            st.session_state.balok_word         = w_buf.getvalue()
            st.session_state.balok_pdf          = p_buf.getvalue()
            st.session_state.balok_fig          = fig
            st.session_state.balok_last_inputs  = snap
            st.session_state.balok_timestamp    = ts_display
            st.session_state.balok_nama_file    = (
                f"Laporan_Lentur_Geser_Torsi_"
                f"fc{int(fc)}_Mu{int(Mu)}_Vu{int(Vu)}_Tu{int(Tu)}_{ts_file}"
            )

with col_out:
    if st.session_state.balok_hasil is not None:
        R   = st.session_state.balok_hasil
        G   = st.session_state.balok_geser_hasil
        Tor = st.session_state.balok_torsi_hasil

        snap_now = dict(
            proj_nama=proj_nama, Mu=Mu, Vu=Vu, Tu=Tu,
            fc=fc, fy=fy, fyt=fyt, b=b, h=h, cc=cc_sel, ds=ds_dia,
            s_seng=s_seng, n_kaki=int(n_kaki),
            tipe_torsi=tipe_torsi, db_long_torsi=float(db_long_torsi),
            n_t1=n_t1, db_t1=db_t1, n_t2=n_t2, db_t2=db_t2,
            n_c1=n_c1, db_c1=db_c1, n_c2=n_c2, db_c2=db_c2,
            sistem_kode=sistem_kode,
        )
        if _inputs_changed(snap_now):
            st.warning(T["warn_ubah"])

        # LENTUR
        st.markdown(f"### {T['res_lentur']}")
        m1, m2, m3, m4 = st.columns(4)
        for col, lbl, val, unt in [
            (m1, "Phi.Mn", f"{R['phiMn']:.2f}", "kN.m"),
            (m2, "Mu",     f"{R['Mu']:.2f}",    "kN.m"),
            (m3, "D/C",    f"{R['DC']:.3f}",    "-"),
            (m4, "et",     f"{R['et']:.4f}",    "-"),
        ]:
            with col:
                st.markdown(f'<div class="metric-card"><div class="metric-lbl">{lbl}</div>'
                            f'<div class="metric-val">{val}</div>'
                            f'<div class="metric-unt">{unt}</div></div>', unsafe_allow_html=True)

        if R["ok_dc"] and R["et"] >= 0.005 and R["ok_rho_min"] and R["ok_rho_max"]:
            st.markdown(f'<div class="result-ok">{T["ok_lentur"].format(dc=R["DC"])}</div>', unsafe_allow_html=True)
        elif R["ok_dc"]:
            st.markdown(f'<div class="result-warn">{T["warn_lentur"].format(dc=R["DC"], note="Cek Rho/Transisi")}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="result-fail">{T["fail_lentur"].format(dc=R["DC"])}</div>', unsafe_allow_html=True)

        # GESER
        st.markdown(f"### {T['res_geser']}")
        g1, g2, g3, g4 = st.columns(4)
        for col, lbl, val, unt in [
            (g1, "Phi.Vn",    f"{G['PhiVn_efektif']:.2f}",         "kN"),
            (g2, "Vu",        f"{G['Vu']:.2f}",                    "kN"),
            (g3, "D/C",       f"{G['DC_geser']:.3f}",              "-"),
            (g4, "Av/Av_min", f"{G['Av_pasang']:.0f}/{G['Av_min']:.0f}", "mm2"),
        ]:
            with col:
                st.markdown(f'<div class="metric-card"><div class="metric-lbl">{lbl}</div>'
                            f'<div class="metric-val">{val}</div>'
                            f'<div class="metric-unt">{unt}</div></div>', unsafe_allow_html=True)

        if G["ok_total"]:
            st.markdown(f'<div class="result-ok">{T["ok_geser"].format(dc=G["DC_geser"])}</div>', unsafe_allow_html=True)
        elif G["ok_dc"]:
            st.markdown(f'<div class="result-warn">{T["warn_geser"].format(dc=G["DC_geser"], note="Cek Spasi/Av")}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="result-fail">{T["fail_geser"].format(dc=G["DC_geser"])}</div>', unsafe_allow_html=True)

        # TORSI
        st.markdown(f"### {T['res_torsi']}")
        t1, t2, t3, t4 = st.columns(4)
        if Tor is not None and not Tor["abaikan_torsi"]:
            tm = [
                (t1, "Phi.Tn", f"{Tor['PhiTn_cap']:.3f}", "kN.m"),
                (t2, "Tu",     f"{Tor['Tu_desain']:.3f}", "kN.m"),
                (t3, "D/C",   f"{Tor['DC_torsi']:.3f}",  "-"),
                (t4, "Al",     f"{Tor['Al_pakai']:.1f}",  "mm2"),
            ]
        else:
            tm = [
                (t1, "Phi.Tn", "-",         "kN.m"),
                (t2, "Tu",     f"{Tu:.3f}", "kN.m"),
                (t3, "D/C",   "IGNORED",   "-"),
                (t4, "Al",     "-",         "mm2"),
            ]
        for col, lbl, val, unt in tm:
            with col:
                st.markdown(f'<div class="metric-card"><div class="metric-lbl">{lbl}</div>'
                            f'<div class="metric-val">{val}</div>'
                            f'<div class="metric-unt">{unt}</div></div>', unsafe_allow_html=True)

        if Tor is not None and Tor["abaikan_torsi"]:
            st.markdown(f'<div class="result-ok">{T["ign_torsi"]}</div>', unsafe_allow_html=True)
        elif Tor is not None and Tor["ok_torsi_total"]:
            st.markdown(f'<div class="result-ok">{T["ok_torsi"].format(dc=Tor["DC_torsi"])}</div>', unsafe_allow_html=True)
        elif Tor is not None and not Tor["ok_torsi_total"]:
            st.markdown(f'<div class="result-fail">{T["fail_torsi"].format(note="Cek dimensi/sengkang")}</div>', unsafe_allow_html=True)

        # STATUS GABUNGAN
        aman_torsi = True if (Tor is None or Tor["abaikan_torsi"] or Tor["ok_torsi_total"]) else False
        aman_total = R["ok_dc"] and G["ok_total"] and aman_torsi
        css_cls = "result-ok" if aman_total else "result-fail"
        stat_l  = T["aman"] if R["ok_dc"]    else T["tidak_aman"]
        stat_g  = T["aman"] if G["ok_total"] else T["tidak_aman"]
        stat_t  = T["aman"] if aman_torsi    else T["tidak_aman"]
        st.markdown(
            f'<div class="{css_cls}">{T["stat_gabungan"]} | '
            f'Lentur: {stat_l} | Geser: {stat_g} | Torsi: {stat_t}</div>',
            unsafe_allow_html=True,
        )

        # Tampilkan detail steps di expander
        with st.expander("Detail Perhitungan Lentur (b1-b10)", expanded=False):
            steps_l = st.session_state.balok_steps
            if steps_l:
                for s in steps_l:
                    warna = "#2e7d32" if s["ok"] else "#c62828"
                    tanda = "[OK]" if s["ok"] else "[X]"
                    st.markdown(
                        f'<div class="step-box" style="border-left-color:{warna}">'
                        f'<div class="ref-badge">{s["ref"]}</div><br>'
                        f'<div class="step-hdr">{s["no"]} {s["judul"]} &nbsp; {tanda}</div>'
                        f'<pre style="margin:0;font-size:.82rem;white-space:pre-wrap;'
                        f'font-family:monospace">{s["isi"]}</pre></div>',
                        unsafe_allow_html=True,
                    )

        with st.expander("Detail Perhitungan Geser (b11-b18)", expanded=False):
            steps_g = st.session_state.balok_geser_steps
            if steps_g:
                for s in steps_g:
                    warna = "#2e7d32" if s["ok"] else "#c62828"
                    tanda = "[OK]" if s["ok"] else "[X]"
                    st.markdown(
                        f'<div class="step-box" style="border-left-color:{warna}">'
                        f'<div class="ref-badge">{s["ref"]}</div><br>'
                        f'<div class="step-hdr">{s["no"]} {s["judul"]} &nbsp; {tanda}</div>'
                        f'<pre style="margin:0;font-size:.82rem;white-space:pre-wrap;'
                        f'font-family:monospace">{s["isi"]}</pre></div>',
                        unsafe_allow_html=True,
                    )

        with st.expander("Detail Perhitungan Torsi (b19-b28)", expanded=False):
            steps_t = st.session_state.balok_torsi_steps
            if steps_t:
                for s in steps_t:
                    warna = "#2e7d32" if s["ok"] else "#c62828"
                    tanda = "[OK]" if s["ok"] else "[X]"
                    st.markdown(
                        f'<div class="step-box" style="border-left-color:{warna}">'
                        f'<div class="ref-badge">{s["ref"]}</div><br>'
                        f'<div class="step-hdr">{s["no"]} {s["judul"]} &nbsp; {tanda}</div>'
                        f'<pre style="margin:0;font-size:.82rem;white-space:pre-wrap;'
                        f'font-family:monospace">{s["isi"]}</pre></div>',
                        unsafe_allow_html=True,
                    )

        # Download
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        dl_w, dl_p = st.columns(2)
        with dl_w:
            st.download_button(
                label=T["dl_word"],
                data=st.session_state.balok_word,
                file_name=f"{st.session_state.balok_nama_file}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key="balok_dl_word",
            )
        with dl_p:
            st.download_button(
                label=T["dl_pdf"],
                data=st.session_state.balok_pdf,
                file_name=f"{st.session_state.balok_nama_file}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="balok_dl_pdf",
            )

# Footer
st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;font-size:.75rem;color:#aaa'>"
    "Referensi: SNI 2847:2019 | ACI 318-14 | "
    "Untuk keperluan profesional - verifikasi mandiri tetap diperlukan"
    "</p>",
    unsafe_allow_html=True,
)
