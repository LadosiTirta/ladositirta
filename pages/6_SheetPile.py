"""
================================================================================
6_SheetPile.py  —  Halaman Streamlit untuk Perhitungan Turap / Sheet Pile
================================================================================
File ini adalah halaman Streamlit (dalam folder pages/) yang memanggil
modul perhitungan dari folder sheetpile/ di root repository.

Struktur GitHub yang benar:
    hitung-lentur-balok/
    ├── app.py                     (main app, daftar menu)
    ├── requirements.txt
    ├── pages/
    │   └── 6_SheetPile.py         (file ini)
    └── sheetpile/
        ├── __init__.py
        ├── earth_pressure.py
        ├── stability.py
        ├── internal_forces.py
        ├── section_design.py
        ├── anchor_design.py
        └── steel_sections.csv

Cara menjalankan lokal:
    streamlit run app.py
================================================================================
"""

from __future__ import annotations

import io
import os
import sys
import math
import datetime
import traceback

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# SETUP PATH — pastikan folder sheetpile/ ditemukan baik lokal maupun Cloud
# ─────────────────────────────────────────────────────────────────────────────

def _setup_path():
    """
    Tambahkan folder sheetpile/ ke sys.path agar modul bisa diimport.
    Berjalan di lokal (Windows/Linux) maupun Streamlit Cloud.
    """
    # Lokasi file ini (pages/6_SheetPile.py)
    this_file = os.path.abspath(__file__)
    pages_dir = os.path.dirname(this_file)          # .../pages/
    root_dir  = os.path.dirname(pages_dir)           # .../hitung-lentur-balok/
    sheetpile_dir = os.path.join(root_dir, "sheetpile")

    for path in [sheetpile_dir, root_dir]:
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)

_setup_path()

# ─────────────────────────────────────────────────────────────────────────────
# IMPORT MODUL PERHITUNGAN
# ─────────────────────────────────────────────────────────────────────────────

try:
    from earth_pressure import (
        hitung_Ka_rankine, hitung_Kp_rankine, hitung_Ko,
        hitung_distribusi_tekanan, plot_diagram_tekanan,
        format_langkah as ep_fmt,
    )
    from stability import (
        free_earth_support, fixed_earth_support_cantilever,
        hitung_SF_heave_terzaghi, hitung_SF_heave_bjerrum_eide,
        hitung_SF_piping, rangkuman_stabilitas,
        format_langkah as st_fmt,
        SF_GULING_MIN, SF_HEAVE_MIN, SF_PIPING_MIN,
    )
    from internal_forces import (
        hitung_gaya_dalam, hitung_gaya_dalam_kantilever,
        plot_V_M_diagram, format_langkah as if_fmt,
    )
    from section_design import (
        desain_baja, desain_beton_pracetak,
        format_langkah as sd_fmt,
        MUTU_BAJA_DEFAULT,
    )
    from anchor_design import (
        desain_tie_rod, desain_waling, desain_deadman, desain_strut,
        rangkuman_angkur, format_langkah as ad_fmt,
        MUTU_BAJA, PROFIL_WF,
    )
    MODUL_OK = True

except ImportError as e:
    MODUL_OK = False
    IMPORT_ERROR = str(e)
    # Tampilkan info debug
    st.error(
        f"**Import Error:** {e}\n\n"
        f"**sys.path saat ini:**\n```\n{chr(10).join(sys.path[:8])}\n```\n\n"
        f"Pastikan folder `sheetpile/` ada di root repository dan berisi semua file `.py`."
    )
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# PATH UNTUK STEEL_SECTIONS.CSV
# ─────────────────────────────────────────────────────────────────────────────

def _cari_csv() -> str | None:
    """Cari file steel_sections.csv di beberapa lokasi yang mungkin."""
    this_file  = os.path.abspath(__file__)
    pages_dir  = os.path.dirname(this_file)
    root_dir   = os.path.dirname(pages_dir)

    kandidat = [
        os.path.join(root_dir, "sheetpile", "steel_sections.csv"),
        os.path.join(root_dir, "steel_sections.csv"),
        os.path.join(pages_dir, "steel_sections.csv"),
        "steel_sections.csv",
    ]
    for p in kandidat:
        if os.path.exists(p):
            return p
    return None

CSV_PATH = _cari_csv()


# ─────────────────────────────────────────────────────────────────────────────
# KONFIGURASI HALAMAN
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Perhitungan Turap / Sheet Pile",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS kustom
st.markdown("""
<style>
.main-title {
    font-size:1.5rem; font-weight:700; color:#1a3a5c;
    border-bottom:3px solid #2196F3; padding-bottom:5px; margin-bottom:4px;
}
.tab-title { font-size:1.1rem; font-weight:600; color:#1565C0; margin-top:4px; }
.status-aman {
    background:#E8F5E9; border-left:5px solid #2E7D32;
    padding:9px 13px; border-radius:5px;
    font-weight:700; color:#1B5E20; margin:5px 0;
}
.status-tidak {
    background:#FFEBEE; border-left:5px solid #C62828;
    padding:9px 13px; border-radius:5px;
    font-weight:700; color:#B71C1C; margin:5px 0;
}
.ref-box {
    background:#E3F2FD; border-left:4px solid #1565C0;
    padding:6px 11px; border-radius:4px;
    font-size:0.81rem; color:#1565C0; margin:3px 0;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# FUNGSI PEMBANTU UI
# ─────────────────────────────────────────────────────────────────────────────

def _status_box(teks: str, aman: bool):
    css = "status-aman" if aman else "status-tidak"
    ikon = "✅" if aman else "❌"
    st.markdown(f'<div class="{css}">{ikon}  {teks}</div>', unsafe_allow_html=True)


def _ref_box(*refs: str):
    teks = "<br>".join([f"📋 {r}" for r in refs])
    st.markdown(f'<div class="ref-box">{teks}</div>', unsafe_allow_html=True)


def _tab_header(nomor: str, judul: str):
    st.markdown(f'<div class="tab-title">Tab {nomor} — {judul}</div>', unsafe_allow_html=True)


def _fig_bytes(fig: plt.Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    buf.seek(0)
    return buf.read()


def _build_lapisan(sesi: list[dict]) -> list[dict]:
    return [{k: lyr[k] for k in ("nama","tebal","gamma","gamma_sat","phi","cohesion")}
            for lyr in sesi]


# ─────────────────────────────────────────────────────────────────────────────
# INISIALISASI SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_LAPISAN = [
    {"nama":"Lempung lunak",  "tebal":3.0,"gamma":16.0,"gamma_sat":17.0,"phi":10.0,"cohesion":10.0},
    {"nama":"Lempung medium","tebal":5.0,"gamma":17.0,"gamma_sat":18.5,"phi":20.0,"cohesion":20.0},
]

def _init():
    for k, v in {
        "lapisan"         : _DEFAULT_LAPISAN.copy(),
        "hasil_ep"        : None,
        "hasil_stability" : None,
        "hasil_gd"        : None,
        "hasil_section"   : None,
        "hasil_anchor"    : None,
        "sudah_hitung"    : False,
        "error_msg"       : "",
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown('<div class="main-title">🏗️ TURAP / SHEET PILE</div>', unsafe_allow_html=True)
    st.caption("Program Perhitungan Geoteknik — SNI & NAVFAC")

    # ── Data Proyek ──────────────────────────────────────────────────────────
    with st.expander("📁 Data Proyek", expanded=True):
        nama_proyek    = st.text_input("Nama Proyek", value="Galian Basement", key="nama_proyek")
        lokasi         = st.text_input("Lokasi",       value="Jakarta",         key="lokasi")
        tgl            = st.date_input("Tanggal",      value=datetime.date.today(), key="tgl")
        dibuat_oleh    = st.text_input("Dibuat oleh",  value="Engineer",        key="dibuat_oleh")
        diperiksa_oleh = st.text_input("Diperiksa",    value="Senior Engineer", key="diperiksa_oleh")

    # ── Tipe ─────────────────────────────────────────────────────────────────
    with st.expander("⚙️ Tipe Turap", expanded=True):
        tipe_turap    = st.radio("Sistem Penahan",
                                  ["Kantilever", "Dengan Angkur", "Dengan Strut"],
                                  key="tipe_turap")
        tipe_material = st.radio("Material",
                                  ["Baja", "Beton Pracetak"],
                                  key="tipe_material")

    # ── Geometri ─────────────────────────────────────────────────────────────
    with st.expander("📐 Geometri & Beban", expanded=True):
        H         = st.number_input("H = Tinggi galian (m)",  1.0, 30.0, 4.0, 0.5, key="H")
        B_galian  = st.number_input("B = Lebar galian (m)",   1.0,100.0, 6.0, 0.5, key="B")
        surcharge = st.number_input("Surcharge (kPa)",        0.0,200.0,10.0, 2.5, key="q")
        MAT       = st.number_input("MAT dari permukaan (m)", 0.0, 30.0, 1.5, 0.25,key="MAT")

        if tipe_turap in ("Dengan Angkur", "Dengan Strut"):
            max_angkur    = max(0.1, H - 0.5)
            tinggi_angkur = st.number_input("Tinggi angkur dari permukaan (m)",
                                             0.0, max_angkur, min(0.5, max_angkur), 0.25,
                                             key="z_angkur")
            spasi_angkur  = st.number_input("Spasi angkur (m)", 0.5, 10.0, 2.5, 0.25, key="spasi")
        else:
            tinggi_angkur = 0.0
            spasi_angkur  = 1.0

    # ── Lapisan Tanah ─────────────────────────────────────────────────────────
    with st.expander("🪨 Lapisan Tanah", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            if st.button("➕ Tambah", use_container_width=True):
                n = len(st.session_state["lapisan"]) + 1
                st.session_state["lapisan"].append(
                    {"nama":f"Lapisan {n}","tebal":3.0,"gamma":17.0,
                     "gamma_sat":18.5,"phi":15.0,"cohesion":15.0}
                )
        with c2:
            if st.button("➖ Hapus", use_container_width=True):
                if len(st.session_state["lapisan"]) > 1:
                    st.session_state["lapisan"].pop()

        for i, lyr in enumerate(st.session_state["lapisan"]):
            with st.expander(f"Lapisan {i+1}: {lyr['nama']}", expanded=(i == 0)):
                lyr["nama"]      = st.text_input("Nama", lyr["nama"],             key=f"n{i}")
                lyr["tebal"]     = st.number_input("Tebal (m)", 0.1,30.0,lyr["tebal"],0.5,key=f"t{i}")
                a, b = st.columns(2)
                with a:
                    lyr["gamma"]     = st.number_input("gamma (kN/m3)", 10.0,25.0,lyr["gamma"],0.5,key=f"g{i}")
                    lyr["phi"]       = st.number_input("phi (deg)",      0.0,45.0,lyr["phi"],  1.0,key=f"p{i}")
                with b:
                    lyr["gamma_sat"] = st.number_input("gamma_sat",     10.0,25.0,lyr["gamma_sat"],0.5,key=f"gs{i}")
                    lyr["cohesion"]  = st.number_input("cohesion (kPa)", 0.0,500.0,lyr["cohesion"],5.0,key=f"c{i}")

    # ── Material ─────────────────────────────────────────────────────────────
    with st.expander("🔩 Material Turap", expanded=True):
        if tipe_material == "Baja":
            mutu_list  = list(MUTU_BAJA.keys())
            mutu_pilih = st.selectbox("Mutu Baja", mutu_list,
                                       index=mutu_list.index("BJ41") if "BJ41" in mutu_list else 0,
                                       key="mutu")
            fy_baja    = st.number_input("fy (MPa)", 200.0, 900.0,
                                          float(MUTU_BAJA[mutu_pilih]["fy"]), 10.0, key="fy")
            fu_baja    = st.number_input("fu (MPa)", 300.0,1100.0,
                                          float(MUTU_BAJA[mutu_pilih]["fu"]), 10.0, key="fu")
            seri_filter = st.selectbox("Seri profil", ["Semua","PZ","AU","PSA","WF","HZ"], key="seri")
            seri_profil = None if seri_filter == "Semua" else seri_filter
        else:
            fc_beton   = st.number_input("fc (MPa)", 17.0, 60.0, 25.0, 1.0, key="fc")
            fy_tulangan= st.number_input("fy tulangan (MPa)", 240.0, 600.0, 390.0, 10.0, key="fyt")
            b_beton    = st.number_input("b penampang (mm)", 200.0,2000.0,1000.0, 50.0, key="bb")
            d_beton    = st.number_input("d efektif (mm)",   100.0,1000.0, 350.0, 25.0, key="db")
            cover_beton= st.number_input("Selimut (mm)",      20.0, 150.0,  60.0,  5.0, key="cov")

    st.markdown("---")
    tombol_hitung = st.button("🔢  HITUNG", type="primary", use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# PROSES PERHITUNGAN
# ─────────────────────────────────────────────────────────────────────────────

if tombol_hitung:
    for k in ("hasil_ep","hasil_stability","hasil_gd","hasil_section","hasil_anchor"):
        st.session_state[k] = None
    st.session_state["sudah_hitung"] = False
    st.session_state["error_msg"]    = ""

    lapisan = _build_lapisan(st.session_state["lapisan"])
    prog    = st.progress(0, text="Memulai perhitungan...")

    try:
        # ── Tahap 1: Tekanan tanah ────────────────────────────────────────────
        prog.progress(10, text="Tahap 1: Tekanan tanah lateral...")
        phi_rata = sum(l["phi"]*l["tebal"] for l in lapisan) / sum(l["tebal"] for l in lapisan)
        r_ka     = hitung_Ka_rankine(phi_rata)
        r_kp     = hitung_Kp_rankine(phi_rata)
        r_ko     = hitung_Ko(phi_rata)

        r_dist = hitung_distribusi_tekanan(lapisan, H=H, D=max(H*0.5, 2.0),
                                            muka_air=MAT, surcharge=surcharge, dz=0.1)
        fig_t  = plot_diagram_tekanan(
            r_dist["nilai"]["z_array"], r_dist["nilai"]["tekanan_aktif"],
            r_dist["nilai"]["tekanan_pasif"], r_dist["nilai"]["tekanan_neto"],
            H, max(H*0.5, 2.0), MAT, r_dist["nilai"]["batas_lapisan"],
            judul=f"Distribusi Tekanan Tanah — {nama_proyek}",
        )
        st.session_state["hasil_ep"] = {
            "Ka": r_ka, "Kp": r_kp, "Ko": r_ko,
            "distribusi": r_dist, "fig": fig_t, "phi_rata": phi_rata,
        }

        # ── Tahap 2: Stabilitas ───────────────────────────────────────────────
        prog.progress(30, text="Tahap 2: Analisis stabilitas...")
        if tipe_turap == "Kantilever":
            r_stab = fixed_earth_support_cantilever(
                H=H, lapisan_tanah=lapisan, surcharge=surcharge,
                muka_air=MAT, dz=0.1,
            )
            Ra_val = 0.0; z_angkur_val = 0.0
        else:
            r_stab = free_earth_support(
                H=H, lapisan_tanah=lapisan, surcharge=surcharge,
                muka_air=MAT, tinggi_angkur=tinggi_angkur, dz=0.1,
            )
            Ra_val = r_stab["nilai"]["Ra"]
            z_angkur_val = tinggi_angkur

        c_dasar   = lapisan[min(1, len(lapisan)-1)]["cohesion"]
        g_atas    = lapisan[0]["gamma"]
        D_design  = r_stab["nilai"]["D_design"]
        r_heave_t = hitung_SF_heave_terzaghi(H, B_galian, c_dasar, g_atas, surcharge)
        r_heave_b = hitung_SF_heave_bjerrum_eide(H, B_galian, max(B_galian*3, 20.0),
                                                   c_dasar, g_atas, surcharge)
        r_piping  = hitung_SF_piping(H + D_design, D_design, max(MAT, 0.5),
                                      "lempung lunak s/d medium")
        r_rk_stab = rangkuman_stabilitas(
            {("free_earth" if tipe_turap != "Kantilever" else "fixed_earth"): r_stab,
             "heave_terzaghi": r_heave_t, "heave_bjerrum": r_heave_b, "piping": r_piping},
            nama_proyek=nama_proyek,
        )
        st.session_state["hasil_stability"] = {
            "stab": r_stab, "heave_t": r_heave_t, "heave_b": r_heave_b,
            "piping": r_piping, "rangkuman": r_rk_stab,
            "Ra": Ra_val, "z_angkur": z_angkur_val,
        }

        # ── Tahap 3: Gaya dalam ───────────────────────────────────────────────
        prog.progress(55, text="Tahap 3: Gaya dalam V dan M...")
        z_arr  = r_stab["nilai"]["z_array"]
        p_neto = r_stab["nilai"]["p_neto"]
        p_aktif= r_stab["nilai"]["p_aktif"]
        p_pasif= r_stab["nilai"]["p_pasif"]

        if tipe_turap == "Kantilever":
            r_gd = hitung_gaya_dalam_kantilever(
                z_arr, p_neto, H, p_aktif, p_pasif)
            z_angkur_plot = None
        else:
            r_gd = hitung_gaya_dalam(
                z_arr, p_neto, Ra_val, z_angkur_val, p_aktif, p_pasif)
            z_angkur_plot = z_angkur_val

        fig_vm = plot_V_M_diagram(
            z_arr, r_gd["nilai"]["V_array"], r_gd["nilai"]["M_array"],
            r_gd["nilai"]["M_max"], r_gd["nilai"]["z_Mmax"],
            H, z_angkur_plot, r_gd["nilai"]["z_V0"], D_design, p_neto,
            judul=f"Diagram V & M — {nama_proyek}",
        )
        st.session_state["hasil_gd"] = {"gd": r_gd, "fig": fig_vm}

        # ── Tahap 4: Desain penampang ─────────────────────────────────────────
        prog.progress(72, text="Tahap 4: Desain penampang...")
        M_max_val = r_gd["nilai"]["M_max"]
        V_max_val = float(np.max(np.abs(r_gd["nilai"]["V_array"])))

        if tipe_material == "Baja":
            r_sec = desain_baja(M_max_val, fy_baja, fu_baja,
                                 path_csv=CSV_PATH,
                                 nama_material=mutu_pilih,
                                 seri_profil=seri_profil)
        else:
            r_sec = desain_beton_pracetak(M_max_val, V_max_val,
                                           fc_beton, fy_tulangan,
                                           b_beton, d_beton, cover_beton, L_span=H)
        st.session_state["hasil_section"] = {"section": r_sec}

        # ── Tahap 5: Angkur / Strut ───────────────────────────────────────────
        prog.progress(87, text="Tahap 5: Desain angkur...")
        anc = {}
        if tipe_turap == "Dengan Angkur" and Ra_val > 0:
            fy_a = fy_baja if tipe_material == "Baja" else 250.0
            fu_a = fu_baja if tipe_material == "Baja" else 400.0
            anc["tie_rod"] = desain_tie_rod(Ra_val, spasi_angkur, fy_a, fu_a,
                                             nama_material=mutu_pilih if tipe_material=="Baja" else "BJ41")
            anc["waling"]  = desain_waling(Ra_val, spasi_angkur,
                                            fy_waling=fy_a if tipe_material=="Baja" else 240.0)
            phi_d = lapisan[-1]["phi"]; g_d = lapisan[-1]["gamma"]
            c_d   = lapisan[-1]["cohesion"]
            anc["deadman"] = desain_deadman(Ra_val, g_d, phi_d, max(H*0.5,1.5), c_d, spasi_angkur)
            anc["rangkuman"] = rangkuman_angkur(anc["tie_rod"], anc["waling"], anc["deadman"])
        elif tipe_turap == "Dengan Strut":
            Ra_strut = max(Ra_val, H * 15.0)
            fy_s = fy_baja if tipe_material == "Baja" else 250.0
            anc["strut"]  = desain_strut(Ra_strut, spasi_angkur, B_galian, fy_s)
            anc["waling"] = desain_waling(Ra_strut, spasi_angkur,
                                           fy_waling=fy_s if tipe_material=="Baja" else 240.0)
            anc["rangkuman"] = rangkuman_angkur(hasil_waling=anc["waling"], hasil_strut=anc["strut"])
        st.session_state["hasil_anchor"] = anc

        prog.progress(100, text="Selesai!")
        st.session_state["sudah_hitung"] = True

    except Exception as exc:
        st.session_state["error_msg"] = str(exc)
        prog.empty()
        st.error(f"❌ **Error:** `{exc}`\n\n```\n{traceback.format_exc()}\n```")


# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="main-title">🏗️ Perhitungan Turap / Sheet Pile</div>',
            unsafe_allow_html=True)

if st.session_state["sudah_hitung"]:
    c1, c2, c3 = st.columns(3)
    D_show = st.session_state["hasil_stability"]["stab"]["nilai"]["D_design"]
    M_show = st.session_state["hasil_gd"]["gd"]["nilai"]["M_max"]
    with c1:
        st.info(f"**Proyek:** {nama_proyek} | **Lokasi:** {lokasi}")
    with c2:
        st.info(f"**D_design:** {D_show:.2f} m  |  **M_max:** {M_show:.1f} kN.m/m")
    with c3:
        st_all = st.session_state["hasil_stability"]["rangkuman"]["status"]
        _status_box(st_all, "SEMUA AMAN" in st_all)
else:
    st.info("👈 Isi data di sidebar lalu tekan **HITUNG**.")

st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "1️⃣ Tekanan Tanah",
    "2️⃣ Stabilitas",
    "3️⃣ Gaya Dalam",
    "4️⃣ Penampang",
    "5️⃣ Angkur/Strut",
    "6️⃣ Ringkasan",
])


# ═══════════════════════════════════════════════════════════════════════════
# TAB 1 — TEKANAN TANAH
# ═══════════════════════════════════════════════════════════════════════════

with tab1:
    _tab_header("1", "Tekanan Tanah Lateral")
    _ref_box("SNI 8460:2017, Pasal 5.2–5.4",
             "NAVFAC DM-7.01, Chapter 4",
             "USS Sheet Pile Design Manual (1975), Chapter 2")

    if not st.session_state["sudah_hitung"]:
        st.warning("Tekan HITUNG untuk melihat hasil.")
    else:
        ep = st.session_state["hasil_ep"]
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("phi rata-rata", f"{ep['phi_rata']:.2f} °")
        k2.metric("Ka (Rankine)",  f"{ep['Ka']['nilai']:.4f}")
        k3.metric("Kp (Rankine)",  f"{ep['Kp']['nilai']:.4f}")
        k4.metric("Ko (Jaky)",     f"{ep['Ko']['nilai']:.4f}")

        cf, ci = st.columns([3, 1])
        with cf:
            st.pyplot(ep["fig"], use_container_width=True)
        with ci:
            st.markdown("**Keterangan:**")
            st.markdown("- **Pa** = tekanan aktif")
            st.markdown("- **Pp** = tekanan pasif")
            st.markdown("- **Pneto** = Pa − Pp")
            st.markdown(f"- MAT = {MAT:.2f} m")

        with st.expander("📋 Langkah Ka Rankine"):
            st.code(ep_fmt(ep["Ka"]["langkah"]), language="")
        with st.expander("📋 Langkah Ko (Jaky)"):
            st.code(ep_fmt(ep["Ko"]["langkah"]), language="")

        with st.expander("📋 Tabel distribusi tekanan"):
            import pandas as pd
            dist = ep["distribusi"]["nilai"]
            z_a = dist["z_array"]
            mask = np.arange(0, len(z_a), max(1, len(z_a)//40))
            st.dataframe(pd.DataFrame({
                "z (m)"     : np.round(z_a[mask], 2),
                "Pa (kPa)"  : np.round(dist["tekanan_aktif"][mask], 3),
                "Pp (kPa)"  : np.round(dist["tekanan_pasif"][mask], 3),
                "Pneto (kPa)": np.round(dist["tekanan_neto"][mask], 3),
                "u (kPa)"   : np.round(dist["tekanan_air_pori"][mask], 3),
            }), use_container_width=True, height=280)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2 — STABILITAS
# ═══════════════════════════════════════════════════════════════════════════

with tab2:
    _tab_header("2", "Stabilitas dan Kedalaman Penetrasi")
    _ref_box("SNI 8460:2017, Pasal 9.6.2 dan 10.6.3",
             "NAVFAC DM-7.02, Chapter 3 dan 7",
             "Terzaghi (1943) | Bjerrum & Eide (1956) | Lane (1935)")

    if not st.session_state["sudah_hitung"]:
        st.warning("Tekan HITUNG untuk melihat hasil.")
    else:
        sd = st.session_state["hasil_stability"]
        sv = sd["stab"]["nilai"]
        ht = sd["heave_t"]["nilai"]
        hb = sd["heave_b"]["nilai"]
        pp = sd["piping"]["nilai"]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("D_min",    f"{sv['D_min']:.3f} m")
        m2.metric("D_design", f"{sv['D_design']:.3f} m")
        sf_v = sv.get("SF_momen", 0)
        delta = "AMAN" if sf_v >= SF_GULING_MIN else "TIDAK AMAN"
        m3.metric("SF Momen", f"{sf_v:.3f}", delta=delta,
                   delta_color="normal" if sf_v >= SF_GULING_MIN else "inverse")
        if tipe_turap != "Kantilever":
            m4.metric("Ra (angkur)", f"{sv.get('Ra',0):.2f} kN/m")
        else:
            m4.metric("z0 (jepit)", f"{sv.get('z0',0):.3f} m")

        import pandas as pd
        SF_ITEMS = [
            ("SF Momen/Guling",        sv.get("SF_momen",0),    SF_GULING_MIN),
            ("SF Heave (Terzaghi)",    ht["SF_heave"],          SF_HEAVE_MIN),
            ("SF Heave (Bjerrum-Eide)",hb["SF_heave"],          SF_HEAVE_MIN),
            ("SF Piping (Lane)",       pp["SF_piping"],          SF_PIPING_MIN),
        ]
        st.dataframe(pd.DataFrame([{
            "Parameter": n, "SF Hitung": f"{v:.3f}", "SF Min": f"{m:.2f}",
            "Status": "✅ AMAN" if v>=m else "❌ TIDAK AMAN",
        } for n,v,m in SF_ITEMS]), use_container_width=True, hide_index=True)

        semua_aman = all(v>=m for _,v,m in SF_ITEMS)
        _status_box(
            "Semua SF memenuhi syarat." if semua_aman else "Ada SF yang tidak memenuhi — perlu revisi.",
            semua_aman,
        )

        with st.expander("📋 Langkah penetrasi"):
            st.code(st_fmt(sd["stab"]["langkah"]), language="")
        c1, c2 = st.columns(2)
        with c1:
            with st.expander("📋 SF Heave — Terzaghi"):
                st.code(st_fmt(sd["heave_t"]["langkah"]), language="")
        with c2:
            with st.expander("📋 SF Heave — Bjerrum-Eide"):
                st.code(st_fmt(sd["heave_b"]["langkah"]), language="")
        with st.expander("📋 SF Piping — Lane"):
            st.code(st_fmt(sd["piping"]["langkah"]), language="")
        with st.expander("📋 Rangkuman stabilitas"):
            st.code(st_fmt(sd["rangkuman"]["langkah"]), language="")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 3 — GAYA DALAM
# ═══════════════════════════════════════════════════════════════════════════

with tab3:
    _tab_header("3", "Diagram Gaya Geser V dan Momen Lentur M")
    _ref_box("NAVFAC DM-7.02, Section 3.2.5",
             "USS Sheet Pile Design Manual (1975), Chapter 4")

    if not st.session_state["sudah_hitung"]:
        st.warning("Tekan HITUNG untuk melihat hasil.")
    else:
        gd = st.session_state["hasil_gd"]
        gv = gd["gd"]["nilai"]
        g1,g2,g3,g4 = st.columns(4)
        g1.metric("M_max",   f"{gv['M_max']:.2f} kN.m/m")
        g2.metric("z_Mmax",  f"{gv['z_Mmax']:.3f} m")
        g3.metric("V_max",   f"{float(np.max(np.abs(gv['V_array']))):.2f} kN/m")
        g4.metric("z_V=0",   f"{gv['z_V0']:.3f} m")

        st.pyplot(gd["fig"], use_container_width=True)

        with st.expander("📋 Tabel V dan M"):
            import pandas as pd
            z_a = gv["z_array"]
            mask = np.arange(0, len(z_a), max(1, len(z_a)//50))
            st.dataframe(pd.DataFrame({
                "z (m)"     : np.round(z_a[mask], 2),
                "Pnet (kPa)": np.round(gv["tekanan_array"][mask], 3),
                "V (kN/m)"  : np.round(gv["V_array"][mask], 3),
                "M (kN.m/m)": np.round(gv["M_array"][mask], 3),
            }), use_container_width=True, height=300)
        with st.expander("📋 Langkah gaya dalam"):
            st.code(if_fmt(gd["gd"]["langkah"]), language="")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 4 — DESAIN PENAMPANG
# ═══════════════════════════════════════════════════════════════════════════

with tab4:
    _tab_header("4", f"Desain Penampang — {tipe_material}")
    if tipe_material == "Baja":
        _ref_box("AISC 16th Ed., Section F11.1",
                 "USS Sheet Pile Design Manual (1975), Chapter 4",
                 "SNI 1729:2020, Pasal F11")
    else:
        _ref_box("SNI 2847:2019, Pasal 9.6.1.2, 21.2.1, 22.5.5.1",
                 "ACI 318-19, Section 9.6.1.2 dan 22.5.5.1")

    if not st.session_state["sudah_hitung"]:
        st.warning("Tekan HITUNG untuk melihat hasil.")
    else:
        sec  = st.session_state["hasil_section"]["section"]
        sv2  = sec["nilai"]
        _status_box(sec["status"], "MEMENUHI" in sec["status"])

        if tipe_material == "Baja":
            s1,s2,s3,s4 = st.columns(4)
            s1.metric("sigma_allow", f"{sv2['sigma_allow']:.1f} MPa")
            s2.metric("S_req",       f"{sv2['S_req']:.2f} cm3/m")
            pt = sv2.get("profil_terpilih")
            s3.metric("Profil",  pt["tipe"] if pt else "—")
            s4.metric("S_pakai", f"{pt['S']:.1f} cm3/m" if pt else "—")
            if sv2.get("kandidat_profil"):
                import pandas as pd
                with st.expander("📋 Kandidat profil"):
                    st.dataframe(pd.DataFrame([{
                        "Tipe":p["tipe"],"S(cm3/m)":p["S"],"Berat(kg/m2)":p["berat"],
                        "Ix(cm4/m)":p["Ix"],"Material":p["material"],
                    } for p in sv2["kandidat_profil"]]), use_container_width=True, hide_index=True)
        else:
            b1,b2,b3 = st.columns(3)
            b1.metric("Mu",      f"{sv2['Mu']:.2f} kN.m/m")
            b2.metric("As_req",  f"{sv2['As_req']:.2f} mm2/m")
            b3.metric("phi_Vc",  f"{sv2['phi_Vc']:.2f} kN/m")
            _status_box(f"Geser: phi_Vc={sv2['phi_Vc']:.2f} >= Vu={sv2['Vu']:.2f} kN/m",
                         sv2["aman_geser"])

        with st.expander("📋 Langkah desain penampang"):
            st.code(sd_fmt(sec["langkah"]), language="")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 5 — ANGKUR / STRUT
# ═══════════════════════════════════════════════════════════════════════════

with tab5:
    _tab_header("5", f"Sistem {tipe_turap}")
    _ref_box("NAVFAC DM-7.02, Section 3.3 dan 3.4",
             "USS Sheet Pile Design Manual (1975), Chapter 5",
             "AISC 16th Ed., Ch. E dan J  |  SNI 1729:2020")

    if not st.session_state["sudah_hitung"]:
        st.warning("Tekan HITUNG untuk melihat hasil.")
    elif tipe_turap == "Kantilever":
        st.info("Turap kantilever tidak memiliki angkur atau strut.")
    elif not st.session_state["hasil_anchor"]:
        st.warning("Data angkur tidak tersedia.")
    else:
        anc = st.session_state["hasil_anchor"]
        if "tie_rod" in anc:
            st.subheader("Tie Rod")
            tr = anc["tie_rod"]["nilai"]
            t1,t2,t3,t4 = st.columns(4)
            t1.metric("T_angkur", f"{tr['T_angkur']:.2f} kN")
            t2.metric("A_req",    f"{tr['A_req']:.2f} mm2")
            t3.metric("Diameter", f"{tr['diameter_pakai']:.0f} mm")
            t4.metric("SF",       f"{tr['SF']:.3f}")
            _status_box(f"Tie Rod D{tr['diameter_pakai']:.0f}mm — SF={tr['SF']:.3f}", tr["aman"])
            with st.expander("📋 Langkah tie rod"):
                st.code(ad_fmt(anc["tie_rod"]["langkah"]), language="")

        if "waling" in anc:
            st.subheader("Waling")
            wv = anc["waling"]["nilai"]
            w1,w2,w3 = st.columns(3)
            w1.metric("M_waling", f"{wv['M_waling']:.3f} kN.m")
            w2.metric("S_req",    f"{wv['S_req']:.2f} cm3")
            pt_w = wv.get("profil_terpilih")
            w3.metric("Profil",   pt_w[0] if pt_w else "—")
            _status_box(f"Waling {pt_w[0] if pt_w else '—'} — rasio={wv.get('rasio_S',0):.3f}",
                         wv.get("aman", False))
            with st.expander("📋 Langkah waling"):
                st.code(ad_fmt(anc["waling"]["langkah"]), language="")

        if "deadman" in anc:
            st.subheader("Deadman Anchor")
            dv = anc["deadman"]["nilai"]
            d1,d2,d3 = st.columns(3)
            d1.metric("Pp_per_m",      f"{dv['Pp_per_m']:.3f} kN/m")
            d2.metric("L_deadman min", f"{dv['L_deadman']:.3f} m")
            d3.metric("SF Deadman",    f"{dv['SF_actual']:.3f}")
            _status_box(f"Deadman — SF={dv['SF_actual']:.3f}", dv["aman"])
            with st.expander("📋 Langkah deadman"):
                st.code(ad_fmt(anc["deadman"]["langkah"]), language="")

        if "strut" in anc:
            st.subheader("Strut / Bracing")
            stv = anc["strut"]["nilai"]
            pt_s = stv.get("profil_terpilih")
            s1,s2,s3 = st.columns(3)
            s1.metric("P_strut",   f"{stv['P_strut']:.2f} kN")
            s2.metric("Profil",    pt_s["nama"] if pt_s else "—")
            if pt_s:
                s3.metric("SF Strut", f"{pt_s['SF']:.3f}")
            _status_box(f"Strut — SF={pt_s['SF']:.3f if pt_s else 0}",
                         stv.get("aman", False))
            with st.expander("📋 Langkah strut"):
                st.code(ad_fmt(anc["strut"]["langkah"]), language="")

        if "rangkuman" in anc:
            with st.expander("📋 Rangkuman sistem angkur"):
                st.code(ad_fmt(anc["rangkuman"]["langkah"]), language="")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 6 — RINGKASAN & DOWNLOAD
# ═══════════════════════════════════════════════════════════════════════════

with tab6:
    _tab_header("6", "Ringkasan Hasil dan Download")

    if not st.session_state["sudah_hitung"]:
        st.warning("Tekan HITUNG untuk melihat ringkasan.")
    else:
        import pandas as pd
        sd = st.session_state["hasil_stability"]
        gd = st.session_state["hasil_gd"]
        sc = st.session_state["hasil_section"]["section"]
        anc= st.session_state["hasil_anchor"]
        sv = sd["stab"]["nilai"]
        gv = gd["gd"]["nilai"]
        sval = sc["nilai"]

        st.subheader("Informasi Proyek")
        st.dataframe(pd.DataFrame([{"Parameter":k,"Nilai":v} for k,v in [
            ("Nama Proyek",nama_proyek),("Lokasi",lokasi),("Tanggal",str(tgl)),
            ("Dibuat",dibuat_oleh),("Diperiksa",diperiksa_oleh),
            ("Tipe Turap",tipe_turap),("Material",tipe_material),
            ("H Galian",f"{H:.2f} m"),("B Galian",f"{B_galian:.2f} m"),
        ]]), use_container_width=True, hide_index=True)

        st.subheader("Parameter Desain Final")
        baris = [
            ("D_min",    f"{sv['D_min']:.4f}","m"),
            ("D_design", f"{sv['D_design']:.4f}","m"),
            ("M_max",    f"{gv['M_max']:.3f}","kN.m/m"),
            ("V_max",    f"{float(np.max(np.abs(gv['V_array']))):.3f}","kN/m"),
        ]
        if tipe_turap != "Kantilever":
            baris.append(("Ra (angkur)",f"{sv.get('Ra',0):.3f}","kN/m"))
        if tipe_material == "Baja":
            pt = sval.get("profil_terpilih")
            baris += [("sigma_allow",f"{sval['sigma_allow']:.2f}","MPa"),
                      ("S_req",f"{sval['S_req']:.2f}","cm3/m"),
                      ("Profil",pt["tipe"] if pt else "—","—"),
                      ("S_pakai",f"{pt['S']:.1f}" if pt else "—","cm3/m")]
        else:
            baris += [("Mu",f"{sval['Mu']:.3f}","kN.m/m"),
                      ("As_req",f"{sval['As_req']:.2f}","mm2/m")]
        st.dataframe(pd.DataFrame([{"Parameter":p,"Nilai":v,"Satuan":s}
                                    for p,v,s in baris]),
                      use_container_width=True, hide_index=True)

        st.subheader("Semua Faktor Keamanan")
        SF_ROWS = [
            ("SF Momen/Guling",       sv.get("SF_momen",0),     SF_GULING_MIN),
            ("SF Heave (Terzaghi)",   sd["heave_t"]["nilai"]["SF_heave"], SF_HEAVE_MIN),
            ("SF Heave (Bjerrum)",    sd["heave_b"]["nilai"]["SF_heave"], SF_HEAVE_MIN),
            ("SF Piping (Lane)",      sd["piping"]["nilai"]["SF_piping"], SF_PIPING_MIN),
        ]
        if anc and "tie_rod" in anc:
            SF_ROWS.append(("SF Tie Rod", anc["tie_rod"]["nilai"]["SF"], 2.0))
        if anc and "deadman" in anc:
            SF_ROWS.append(("SF Deadman", anc["deadman"]["nilai"]["SF_actual"], 2.0))
        if anc and "strut" in anc:
            pt_s = anc["strut"]["nilai"].get("profil_terpilih")
            if pt_s:
                SF_ROWS.append(("SF Strut", pt_s["SF"], 2.0))
        st.dataframe(pd.DataFrame([{
            "Komponen": n, "SF Hitung": f"{v:.3f}", "SF Min": f"{m:.2f}",
            "Status": "✅ AMAN" if v>=m else "❌ TIDAK AMAN",
        } for n,v,m in SF_ROWS]), use_container_width=True, hide_index=True)

        semua_ok = all(v>=m for _,v,m in SF_ROWS)
        _status_box(
            "SEMUA AMAN — DESAIN DAPAT DITERIMA" if semua_ok
            else "ADA YANG TIDAK AMAN — REVISI DIPERLUKAN",
            semua_ok,
        )

        # ── Download ─────────────────────────────────────────────────────────
        st.markdown("---")
        st.subheader("Download Laporan & Diagram")

        def _teks_laporan() -> str:
            baris = [
                "="*70,
                "LAPORAN PERHITUNGAN TURAP / SHEET PILE",
                "="*70,
                f"Proyek  : {nama_proyek}",
                f"Lokasi  : {lokasi}",
                f"Tanggal : {tgl}",
                f"Dibuat  : {dibuat_oleh}",
                f"Periksa : {diperiksa_oleh}",
                f"Tipe    : {tipe_turap} | Material: {tipe_material}",
                "="*70,
            ]
            sesi = st.session_state
            for bagian, kunci, sub in [
                ("TEKANAN TANAH — Ka",  "hasil_ep",        ["Ka","langkah"]),
                ("TEKANAN TANAH — Ko",  "hasil_ep",        ["Ko","langkah"]),
                ("STABILITAS",          "hasil_stability",  ["stab","langkah"]),
                ("SF HEAVE Terzaghi",   "hasil_stability",  ["heave_t","langkah"]),
                ("SF PIPING",           "hasil_stability",  ["piping","langkah"]),
                ("GAYA DALAM",          "hasil_gd",         ["gd","langkah"]),
            ]:
                obj = sesi.get(kunci)
                if obj:
                    val = obj
                    for k in sub:
                        val = val.get(k, {}) if isinstance(val, dict) else {}
                    if isinstance(val, list):
                        baris += ["", bagian, "-"*50] + val

            obj_sec = sesi.get("hasil_section")
            if obj_sec:
                lngk = obj_sec.get("section", {}).get("langkah", [])
                baris += ["", f"DESAIN PENAMPANG — {tipe_material}", "-"*50] + lngk

            return "\n".join(baris)

        dl1, dl2, dl3 = st.columns(3)
        with dl1:
            st.download_button(
                "⬇️ Laporan TXT",
                data=_teks_laporan().encode("utf-8"),
                file_name=f"Turap_{nama_proyek}_{tgl}.txt",
                mime="text/plain", use_container_width=True,
            )
        with dl2:
            st.download_button(
                "⬇️ Diagram Tekanan (PNG)",
                data=_fig_bytes(st.session_state["hasil_ep"]["fig"]),
                file_name=f"tekanan_{tgl}.png",
                mime="image/png", use_container_width=True,
            )
        with dl3:
            st.download_button(
                "⬇️ Diagram V & M (PNG)",
                data=_fig_bytes(st.session_state["hasil_gd"]["fig"]),
                file_name=f"V_M_{tgl}.png",
                mime="image/png", use_container_width=True,
            )

        st.markdown("---")
        st.caption(
            "Standar: SNI 8460:2017 | SNI 2847:2019 | SNI 1729:2020 | "
            "NAVFAC DM-7.01 & DM-7.02 | USS Sheet Pile Design Manual (1975) | "
            "AISC 16th Ed. | ACI 318-19 | Terzaghi (1943) | Lane (1935)"
        )
