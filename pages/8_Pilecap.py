"""
pages/8_Pilecap.py — VERSI FINAL FIXED
========================================
Perbaikan dari versi sebelumnya:
  1. Import report_pilecap LAZY — hanya dimuat saat tombol download ditekan
     (mencegah halaman kosong akibat python-docx/reportlab gagal import)
  2. try/except di setiap import untuk pesan error yang jelas
  3. sys.path lebih robust untuk Streamlit Cloud

Standar: SNI 2847:2019, SNI 8460:2017
"""

import streamlit as st
import pandas as pd
import math, sys, os, datetime

# --- Path setup yang robust untuk Streamlit Cloud ---
# __file__ = /mount/src/ladositirta-pawon/pages/8_Pilecap.py
# Kita butuh /mount/src/ladositirta-pawon/ ada di sys.path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# --- Import modul pilecap (satu per satu untuk error yang jelas) ---
_import_error = None
try:
    from pilecap.geometry import PilecapGeometry, DataKolom, KondisiGalian
    from pilecap.pile_forces import hitung_beban_total, hitung_gaya_tiang, ringkasan_gaya_tiang
    from pilecap.group_efficiency import hitung_efisiensi_grup
    from pilecap.shear_check import hitung_d_efektif, hitung_semua_geser, ringkasan_geser
    from pilecap.reinforcement import hitung_penulangan
    # report_pilecap TIDAK diimpor di sini — diimpor lazy saat tombol download ditekan
except Exception as e:
    _import_error = str(e)

# ==========================================================================
# KONFIGURASI HALAMAN
# ==========================================================================
st.set_page_config(
    page_title="Pilecap — Ladosi Engineering",
    page_icon="🏗️",
    layout="wide",
)

# Tampilkan error import jika ada
if _import_error:
    st.error(f"❌ Gagal memuat modul pilecap: `{_import_error}`")
    st.info(
        "Pastikan folder `pilecap/` ada di root repository dan semua file modul ada:\n"
        "- `pilecap/geometry.py`\n"
        "- `pilecap/pile_forces.py`\n"
        "- `pilecap/group_efficiency.py`\n"
        "- `pilecap/shear_check.py`\n"
        "- `pilecap/reinforcement.py`\n"
        "- `pilecap/report_pilecap.py`"
    )
    st.stop()

st.markdown("""
<style>
  .ladosi-header {
    background: linear-gradient(135deg, #1e3a5f 0%, #1e40af 100%);
    color:white; padding:1.2rem 1.6rem; border-radius:10px; margin-bottom:1.2rem;
  }
  .ladosi-header h2 { margin:0; font-size:1.4rem; }
  .ladosi-header p  { margin:0.2rem 0 0; font-size:0.85rem; opacity:0.85; }
  .section-header {
    background:#eff6ff; border-left:4px solid #1e40af;
    padding:0.5rem 0.9rem; border-radius:0 6px 6px 0;
    margin:1rem 0 0.7rem; font-weight:600; color:#1e3a5f;
  }
  .info-box {
    background:#fffbeb; border:1px solid #fcd34d;
    border-radius:6px; padding:0.6rem 0.9rem;
    font-size:0.85rem; color:#78350f; margin-bottom:0.8rem;
  }
  .konvensi-box {
    background:#f0fdf4; border:2px solid #16a34a;
    border-radius:8px; padding:0.9rem 1.1rem;
    font-size:0.88rem; color:#14532d; margin:0.8rem 0;
  }
  .calc-box {
    background:#f8fafc; border:1px solid #cbd5e1;
    border-radius:8px; padding:1rem 1.2rem;
    font-family:'Courier New',monospace; font-size:0.80rem;
    color:#1e293b; line-height:1.7; white-space:pre-wrap;
    max-height:500px; overflow-y:auto;
  }
  .result-ok   { background:#dcfce7; border-left:4px solid #16a34a;
                 padding:0.5rem 0.8rem; border-radius:0 6px 6px 0; margin:0.3rem 0; }
  .result-ng   { background:#fee2e2; border-left:4px solid #dc2626;
                 padding:0.5rem 0.8rem; border-radius:0 6px 6px 0; margin:0.3rem 0; }
  .result-warn { background:#fef9c3; border-left:4px solid #d97706;
                 padding:0.5rem 0.8rem; border-radius:0 6px 6px 0; margin:0.3rem 0; }
  .tul-card {
    background:#f8fafc; border:1px solid #bfdbfe;
    border-radius:10px; padding:1rem 1.2rem; margin:0.5rem 0;
  }
  .tul-label { font-size:1.5rem; font-weight:700; color:#1e40af; font-family:monospace; }
  .dl-card {
    background:linear-gradient(135deg,#f0fdf4,#dcfce7);
    border:2px solid #16a34a; border-radius:12px;
    padding:1.4rem; text-align:center; margin:0.5rem;
  }
  .dl-card h3 { color:#14532d; margin:0 0 0.5rem; font-size:1.15rem; }
  .dl-card p  { color:#374151; font-size:0.83rem; margin:0; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="ladosi-header">
  <h2>🏗️ Perhitungan Pondasi Pilecap</h2>
  <p>Ladosi Engineering Portal &nbsp;|&nbsp; SNI 2847:2019 &amp; SNI 8460:2017
     &nbsp;|&nbsp; v4.1 — Input + Gaya Tiang + Penulangan + Laporan Word/PDF</p>
</div>
""", unsafe_allow_html=True)

# ==========================================================================
# SESSION STATE
# ==========================================================================
def _init_state():
    defaults = {
        "pc_Lx":3.0,"pc_Ly":3.0,"pc_t":0.80,"pc_cover":75.0,"pc_fc":30.0,"pc_fy":400.0,
        "pc_D":500.0,"pc_jenis_tiang":"Spun pile (beton prategang)",
        "pc_P_ijin_tekan":800.0,"pc_P_ijin_tarik":300.0,"pc_P_ijin_lateral":80.0,
        "pc_tiang_df":pd.DataFrame({
            "No.":[1,2,3,4],
            "x (m)":[0.75,2.25,0.75,2.25],
            "y (m)":[0.75,0.75,2.25,2.25]
        }),
        "pc_kolom_list":[{
            "id":1,"xk":1.5,"yk":1.5,"bk":0.5,"hk":0.5,
            "Nu":1500.0,"Vux":50.0,"Vuy":50.0,"Mux":80.0,"Muy":80.0
        }],
        "pc_h_galian":1.5,"pc_gamma":17.0,"pc_h_air":3.0,
        "pc_ada_sloof":False,"pc_h_bot_sloof":0.0,"pc_b_sloof":0.3,"pc_h_sloof":0.5,
        "pc_L_tiang":10.0,"pc_cu":0.0,"pc_jenis_tanah":"Pasir",
        "pc_Dtul_x":16,"pc_Dtul_y":16,"pc_Dtul_atas":13,"pc_alpha_s":40,
        "pc_nama_proyek":"","pc_no_dokumen":"",
        "sudah_hitung":False,"sudah_hitung_gaya":False,"sudah_hitung_tul":False,
        "laporan_siap":False,
    }
    for k,v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
_init_state()

# ==========================================================================
# TAB NAVIGASI
# ==========================================================================
tab1, tab2, tab3, tab4 = st.tabs([
    "📐 Input Data",
    "⚡ Gaya Tiang",
    "🔩 Penulangan",
    "📄 Laporan Word & PDF",
])

# ══════════════════════════════════════════════════════════════════════════
# TAB 1 — INPUT DATA
# ══════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown('<div class="section-header">📐 Bagian A — Dimensi & Material Pilecap</div>', unsafe_allow_html=True)
    cA1, cA2, cA3 = st.columns(3)
    with cA1:
        Lx = st.number_input("Lx — Panjang arah X (m)", 0.5, 30.0, st.session_state["pc_Lx"], 0.1, format="%.2f", key="inp_Lx")
        Ly = st.number_input("Ly — Lebar arah Y (m)", 0.5, 30.0, st.session_state["pc_Ly"], 0.1, format="%.2f", key="inp_Ly")
        t  = st.number_input("t — Tebal pilecap (m)", 0.3, 5.0, st.session_state["pc_t"], 0.05, format="%.2f", key="inp_t")
    with cA2:
        fc    = st.number_input("f'c (MPa)", 17.0, 100.0, st.session_state["pc_fc"], 1.0, format="%.1f", key="inp_fc")
        fy    = st.number_input("fy (MPa)", 240.0, 600.0, st.session_state["pc_fy"], 10.0, format="%.0f", key="inp_fy")
        cover = st.number_input("Selimut beton (mm)", 40.0, 150.0, st.session_state["pc_cover"], 5.0, format="%.0f", key="inp_cover")
    with cA3:
        st.metric("Volume pilecap", f"{Lx*Ly*t:.3f} m³")
        st.metric("Berat sendiri", f"{Lx*Ly*t*25:.1f} kN",
                  help=f"W = {Lx}×{Ly}×{t}×25 = {Lx*Ly*t*25:.1f} kN")
        if t * 1000 > 900:
            st.warning(f"⚠️ t = {t*1000:.0f} mm > 900 mm → perlu tulangan badan")

    st.markdown('<div class="section-header">🪨 Bagian B — Data Tiang Pancang</div>', unsafe_allow_html=True)
    st.markdown('<div class="info-box">💡 Kapasitas ijin diambil dari output program <b>pile-capacity</b> (tiang tunggal) — setelah faktor keamanan.</div>', unsafe_allow_html=True)
    cB1, cB2, cB3 = st.columns(3)
    with cB1:
        D_pile     = st.number_input("Diameter D (mm)", 150.0, 2000.0, st.session_state["pc_D"], 50.0, format="%.0f", key="inp_D")
        jenis_tiang = st.selectbox("Jenis tiang", ["Spun pile (beton prategang)", "Bored pile", "Square pile (beton pracetak)", "Mini pile"], key="inp_jenis_tiang")
    with cB2:
        P_tekan  = st.number_input("Kapasitas ijin tekan (kN)",  1.0, 20000.0, st.session_state["pc_P_ijin_tekan"],  10.0, key="inp_P_tekan")
        P_tarik  = st.number_input("Kapasitas ijin tarik (kN)",  0.0, 10000.0, st.session_state["pc_P_ijin_tarik"],  10.0, key="inp_P_tarik")
    with cB3:
        P_lateral = st.number_input("Kapasitas ijin lateral (kN)", 0.0, 5000.0, st.session_state["pc_P_ijin_lateral"], 5.0, key="inp_P_lateral")
        D_m = D_pile / 1000.0
        st.markdown(f"**Syarat SNI 8460:2017:**\n- Antar tiang ≥ **{2.5*D_m:.3f} m** (= 2.5D)\n- Ke tepi ≥ **{1.25*D_m:.3f} m** (= 1.25D)")

    st.markdown('<div class="section-header">📍 Bagian C — Posisi Tiang Pancang</div>', unsafe_allow_html=True)
    st.caption("Origin (0,0) = sudut kiri-bawah pilecap. Semua koordinat dalam meter.")
    cC1, cC2, _ = st.columns([1, 1, 4])
    with cC1:
        if st.button("➕ Tambah Tiang"):
            df_c = st.session_state["pc_tiang_df"]
            st.session_state["pc_tiang_df"] = pd.concat([
                df_c,
                pd.DataFrame({"No.": [len(df_c)+1], "x (m)": [round(Lx/2,3)], "y (m)": [round(Ly/2,3)]})
            ], ignore_index=True)
            st.rerun()
    with cC2:
        if st.button("➖ Hapus Terakhir"):
            df_c = st.session_state["pc_tiang_df"]
            if len(df_c) > 1:
                st.session_state["pc_tiang_df"] = df_c.iloc[:-1].reset_index(drop=True)
                st.rerun()

    df_tiang = st.data_editor(
        st.session_state["pc_tiang_df"], use_container_width=True, num_rows="fixed",
        column_config={
            "No."  : st.column_config.NumberColumn("No.", disabled=True, width="small"),
            "x (m)": st.column_config.NumberColumn("x (m)", min_value=0.0, format="%.3f"),
            "y (m)": st.column_config.NumberColumn("y (m)", min_value=0.0, format="%.3f"),
        }, key="editor_tiang"
    )
    st.session_state["pc_tiang_df"] = df_tiang
    pile_coords = list(zip(df_tiang["x (m)"].tolist(), df_tiang["y (m)"].tolist()))

    st.markdown('<div class="section-header">🏛️ Bagian D — Kolom & Beban Terfaktor</div>', unsafe_allow_html=True)
    st.markdown('<div class="info-box">⚠️ Semua beban adalah <b>BEBAN TERFAKTOR (LRFD)</b> sesuai SNI 2847:2019 Ps. 5.3.<br>Nu tekan = positif, tarik = negatif.</div>', unsafe_allow_html=True)

    if st.button("➕ Tambah Kolom"):
        id_b = len(st.session_state["pc_kolom_list"]) + 1
        st.session_state["pc_kolom_list"].append({
            "id": id_b, "xk": round(Lx/2, 3), "yk": round(Ly/2, 3),
            "bk": 0.5, "hk": 0.5, "Nu": 0.0, "Vux": 0.0, "Vuy": 0.0, "Mux": 0.0, "Muy": 0.0
        })
        st.rerun()

    kolom_obj_list = []
    for idx, kol in enumerate(st.session_state["pc_kolom_list"]):
        with st.expander(f"Kolom {kol['id']} — posisi ({kol['xk']:.2f}, {kol['yk']:.2f}) m", expanded=(idx == 0)):
            cd1, cd2, cd3 = st.columns(3)
            with cd1:
                xk = st.number_input(f"xk (m) K{kol['id']}", value=float(kol['xk']), step=0.05, format="%.3f", key=f"xk_{idx}")
                yk = st.number_input(f"yk (m) K{kol['id']}", value=float(kol['yk']), step=0.05, format="%.3f", key=f"yk_{idx}")
                bk = st.number_input(f"bk (m) K{kol['id']}", value=float(kol['bk']), min_value=0.1, step=0.05, format="%.2f", key=f"bk_{idx}")
                hk = st.number_input(f"hk (m) K{kol['id']}", value=float(kol['hk']), min_value=0.1, step=0.05, format="%.2f", key=f"hk_{idx}")
            with cd2:
                Nu  = st.number_input(f"Nu (kN) K{kol['id']}",  value=float(kol['Nu']),  step=10.0, key=f"Nu_{idx}", help="Tekan (+), Tarik (−)")
                Vux = st.number_input(f"Vux (kN) K{kol['id']}", value=float(kol['Vux']), step=5.0,  key=f"Vux_{idx}")
                Vuy = st.number_input(f"Vuy (kN) K{kol['id']}", value=float(kol['Vuy']), step=5.0,  key=f"Vuy_{idx}")
            with cd3:
                Mux = st.number_input(f"Mux (kNm) K{kol['id']}", value=float(kol['Mux']), step=5.0, key=f"Mux_{idx}")
                Muy = st.number_input(f"Muy (kNm) K{kol['id']}", value=float(kol['Muy']), step=5.0, key=f"Muy_{idx}")
                if len(st.session_state["pc_kolom_list"]) > 1:
                    if st.button(f"🗑️ Hapus Kolom {kol['id']}", key=f"del_{idx}"):
                        st.session_state["pc_kolom_list"].pop(idx)
                        for ii, k in enumerate(st.session_state["pc_kolom_list"]):
                            k["id"] = ii + 1
                        st.rerun()
            st.session_state["pc_kolom_list"][idx].update({
                "xk": xk, "yk": yk, "bk": bk, "hk": hk,
                "Nu": Nu, "Vux": Vux, "Vuy": Vuy, "Mux": Mux, "Muy": Muy
            })
            kolom_obj_list.append(DataKolom(
                id_kolom=kol["id"], xk=xk, yk=yk, bk=bk, hk=hk,
                Nu=Nu, Vux=Vux, Vuy=Vuy, Mux=Mux, Muy=Muy
            ))

    st.markdown('<div class="section-header">🌍 Bagian E — Kondisi Galian & Level Sloof</div>', unsafe_allow_html=True)
    cE1, cE2 = st.columns(2)
    with cE1:
        h_galian    = st.number_input("Kedalaman top pilecap dari muka tanah (m)", 0.0, 20.0, st.session_state["pc_h_galian"], 0.1, format="%.2f", key="inp_h_galian")
        gamma_tanah = st.number_input("Berat jenis tanah γ (kN/m³)", 10.0, 25.0, st.session_state["pc_gamma"], 0.5, key="inp_gamma")
        h_muka_air  = st.number_input("Kedalaman muka air tanah (m dari muka tanah)", 0.0, 50.0, st.session_state["pc_h_air"], 0.1, key="inp_h_air")
    with cE2:
        ada_sloof = st.checkbox("Ada sloof yang bertumpu pada pilecap?", value=st.session_state["pc_ada_sloof"], key="inp_ada_sloof")
        h_bot_sloof = 0.0; b_sloof = 0.3; h_sloof = 0.5
        if ada_sloof:
            st.markdown('<div class="info-box">📌 Sloof TIDAK mengurangi luas beban tanah, namun memengaruhi distribusi gaya lateral.</div>', unsafe_allow_html=True)
            h_bot_sloof = st.number_input("h bottom sloof dari top pilecap (m)", 0.0, 5.0, 0.0, 0.05, key="inp_hbs")
            cs1, cs2 = st.columns(2)
            with cs1: b_sloof = st.number_input("b sloof (m)", 0.1, 2.0, 0.3, 0.05, key="inp_bs")
            with cs2: h_sloof = st.number_input("h sloof (m)", 0.1, 3.0, 0.5, 0.05, key="inp_hs")

    # Buat objek geometri dan simpan ke session_state
    galian_obj = KondisiGalian(h_galian=h_galian, gamma_tanah=gamma_tanah, h_muka_air=h_muka_air,
                                ada_sloof=ada_sloof, h_bottom_sloof=h_bot_sloof, b_sloof=b_sloof, h_sloof=h_sloof)
    geom = PilecapGeometry(Lx=Lx, Ly=Ly, t=t, diameter_pile=D_pile, cover=cover, fc=fc, fy=fy,
                            pile_coords=pile_coords, kolom_list=kolom_obj_list, galian=galian_obj)
    st.session_state["pilecap_input"] = {
        "geom": geom, "P_ijin_tekan": P_tekan,
        "P_ijin_tarik": P_tarik, "P_ijin_lateral": P_lateral,
    }

    st.markdown("---")
    if st.button("🔍 Validasi & Tampilkan Denah", type="primary"):
        st.session_state["sudah_hitung"] = True

    if st.session_state["sudah_hitung"]:
        rv = geom.ringkasan_validasi()
        icon = {"AMAN": "✅", "PERLU DITINJAU": "⚠️", "TIDAK AMAN": "❌"}
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Status", f"{icon.get(rv['status'],'')} {rv['status']}")
        c2.metric("Total Cek", rv["total_cek"])
        c3.metric("OK ✓", rv["OK"])
        c4.metric("Warn / Error", f"{rv['WARNING']} / {rv['ERROR']}")

        # Tabel xi, yi
        x_bar, y_bar = geom.centroid_grup()
        jarak_rel    = geom.jarak_tiang_ke_centroid()
        df_rel = pd.DataFrame({
            "No.": range(1, geom.jumlah_tiang+1),
            "x (m)": [c[0] for c in pile_coords],
            "y (m)": [c[1] for c in pile_coords],
            "xi (m)": [round(r[0],4) for r in jarak_rel],
            "yi (m)": [round(r[1],4) for r in jarak_rel],
            "xi² (m²)": [round(r[0]**2,4) for r in jarak_rel],
            "yi² (m²)": [round(r[1]**2,4) for r in jarak_rel],
        })
        st.dataframe(df_rel, use_container_width=True, hide_index=True)
        cIx, cIy = st.columns(2)
        cIx.metric("Iy = Σxi² (m²)", f"{geom.Iy_grup():.4f}")
        cIy.metric("Ix = Σyi² (m²)", f"{geom.Ix_grup():.4f}")

        try:
            buf = geom.plot_denah(judul=f"Denah {Lx:.2f}×{Ly:.2f} m — {geom.jumlah_tiang} Tiang")
            st.image(buf, use_container_width=True)
        except Exception as e:
            st.error(f"Gagal menampilkan denah: {e}")

        if rv["ERROR"] > 0:
            st.error("⛔ Ada pelanggaran jarak tiang — perbaiki sebelum melanjutkan.")
        else:
            st.success("✅ Data tersimpan. Lanjutkan ke tab **Gaya Tiang**.")

# ══════════════════════════════════════════════════════════════════════════
# TAB 2 — GAYA TIANG & EFISIENSI GRUP
# ══════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown('<div class="section-header">⚙️ Parameter Tambahan — Efisiensi Grup</div>', unsafe_allow_html=True)
    cP1, cP2, cP3 = st.columns(3)
    with cP1:
        L_tiang = st.number_input("Panjang tiang tertanam L (m)", 1.0, 100.0, st.session_state["pc_L_tiang"], 0.5, key="inp_L_tiang")
    with cP2:
        jenis_tanah = st.selectbox("Jenis tanah dominan", ["Pasir", "Lempung", "Campuran"], key="inp_jenis_tanah")
    with cP3:
        cu = 0.0
        if jenis_tanah == "Lempung":
            cu = st.number_input("cu — kohesi undrained (kN/m²)", 0.0, 500.0, 0.0, 5.0, key="inp_cu")
        else:
            st.info("Tanah pasir/campuran: kapasitas blok tidak dihitung.")

    st.markdown("---")
    if st.button("⚡ Hitung Gaya Tiang & Efisiensi Grup", type="primary", use_container_width=True):
        st.session_state["sudah_hitung_gaya"] = True

    if st.session_state.get("sudah_hitung_gaya"):
        inp = st.session_state.get("pilecap_input")
        if not inp or inp["geom"].jumlah_tiang == 0:
            st.warning("⚠️ Isi Tab Input terlebih dahulu."); st.stop()

        geom_g      = inp["geom"]
        P_tekan_g   = inp["P_ijin_tekan"]
        P_tarik_g   = inp["P_ijin_tarik"]
        P_lateral_g = inp["P_ijin_lateral"]

        beban, db       = hitung_beban_total(geom_g, P_tekan_g, P_tarik_g, P_lateral_g)
        hasil_tiang, dt = hitung_gaya_tiang(geom_g, beban, P_tekan_g, P_tarik_g, P_lateral_g)
        ring            = ringkasan_gaya_tiang(hasil_tiang)
        hasil_grup, dg  = hitung_efisiensi_grup(
            geom_g, P_ijin_tekan=P_tekan_g, Pmax=ring["Pmax"],
            SigmaPtekan=ring["SigmaPtekan"], L_tiang=L_tiang,
            cu=cu, jenis_tanah=jenis_tanah.lower()
        )

        st.session_state["pilecap_gaya"] = {
            "beban": beban, "hasil_tiang": hasil_tiang,
            "hasil_grup": hasil_grup, "ringkasan": ring,
        }

        # [A] Beban total
        st.markdown("## [A] Beban Total ke Pilecap")
        df_b = pd.DataFrame([
            ["Nu kolom",           f"{sum(beban.Nu_kolom_list):.2f}", "kN"],
            ["W_pc (berat pilecap)", f"{beban.W_pilecap:.2f}", "kN"],
            ["W_tanah (tanah urug)", f"{beban.W_tanah:.2f}", "kN"],
            ["F_uplift (−)",        f"{beban.F_uplift:.2f}", "kN"],
            ["ΣNu TOTAL",          f"{beban.SigmaNu:.2f}", "kN"],
            ["ΣMuy_total",         f"{beban.SigmaMuy:.2f}", "kNm"],
            ["ΣMux_total",         f"{beban.SigmaMux:.2f}", "kNm"],
            ["ΣVux_total",         f"{beban.SigmaVux:.2f}", "kN"],
            ["ΣVuy_total",         f"{beban.SigmaVuy:.2f}", "kN"],
        ], columns=["Komponen", "Nilai", "Satuan"])
        st.dataframe(df_b, use_container_width=True, hide_index=True)

        # [B] Gaya per tiang
        st.markdown("## [B] Gaya Reaksi Per Tiang")
        rows = []; warna_peta = {}
        for h in hasil_tiang:
            if h.status_global == "NG": warna_peta[h.no_tiang-1] = "#f97316"
            elif h.status_aksial == "TARIK": warna_peta[h.no_tiang-1] = "#ef4444"
            else: warna_peta[h.no_tiang-1] = "#1e40af"
            rows.append({
                "No.": h.no_tiang, "x (m)": round(h.x, 3), "y (m)": round(h.y, 3),
                "Pi (kN)": round(h.Pi, 2), "Hx (kN)": round(h.Hxi, 2),
                "Hy (kN)": round(h.Hyi, 2), "H (kN)": round(h.Hi, 2),
                "Aksial": h.status_aksial,
                "Cek Aksial": "✅" if h.status_aksial_cek == "OK" else "❌",
                "Cek Lateral": "✅" if h.status_lateral == "OK" else "❌",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # [C] Ringkasan
        st.markdown("## [C] Ringkasan & Efisiensi Grup")
        rc1, rc2, rc3, rc4 = st.columns(4)
        rc1.metric("Pmax", f"{ring['Pmax']:.2f} kN")
        rc2.metric("Pmin", f"{ring['Pmin']:.2f} kN")
        rc3.metric("Hi maks", f"{ring['Hi_max']:.2f} kN")
        rc4.metric("Tiang TARIK", str(ring["tiang_tarik"]) if ring["tiang_tarik"] else "Tidak ada")

        rd1, rd2, rd3 = st.columns(3)
        rd1.metric("η Converse-Labarre", f"{hasil_grup.eta_CL:.4f}")
        rd2.metric("η Feld (pembanding)", f"{hasil_grup.eta_Feld:.4f}")
        rd3.metric("P_grup efektif", f"{hasil_grup.P_grup_efektif:.2f} kN")

        cek1_ok = hasil_grup.cek_Pmax == "OK"
        cek2_ok = hasil_grup.cek_grup == "OK"
        st.markdown(f'<div class="result-{"ok" if cek1_ok else "ng"}">Cek 1 — Pmax ≤ η×P_ijin: {"✅ AMAN" if cek1_ok else "❌ TIDAK AMAN"}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="result-{"ok" if cek2_ok else "ng"}">Cek 2 — ΣPtekan ≤ P_grup: {"✅ AMAN" if cek2_ok else "❌ TIDAK AMAN"}</div>', unsafe_allow_html=True)

        # Denah dengan warna status
        try:
            buf2 = geom_g.plot_denah(judul="Denah — Status Gaya Tiang", warna_tiang=warna_peta)
            st.image(buf2, use_container_width=True)
        except Exception as e:
            st.error(f"Gagal plot: {e}")

        with st.expander("📋 Detail Perhitungan (semua langkah)"):
            st.markdown('<div class="calc-box">' + "\n".join(db + dt + dg) + '</div>', unsafe_allow_html=True)

        st.success("✅ Lanjutkan ke tab **Penulangan**.")

# ══════════════════════════════════════════════════════════════════════════
# TAB 3 — PENULANGAN
# ══════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("""
    <div class="konvensi-box">
      <b>⚠️ KONVENSI NOTASI TULANGAN — Program Ini</b><br><br>
      <b>"Tulangan bawah arah X : D16-200"</b><br>
      &nbsp;→ Batang Ø16 mm <b>MEMBENTANG ke arah SUMBU X</b> (panjang ≈ Lx)<br>
      &nbsp;→ Dipasang <b>BERBARIS ke arah Y</b> jarak 200 mm antar batang<br><br>
      <b>"Tulangan bawah arah Y : D16-150"</b><br>
      &nbsp;→ Batang Ø16 mm <b>MEMBENTANG ke arah SUMBU Y</b> (panjang ≈ Ly)<br>
      &nbsp;→ Dipasang <b>BERBARIS ke arah X</b> jarak 150 mm antar batang
    </div>
    """, unsafe_allow_html=True)

    cT1, cT2, cT3, cT4 = st.columns(4)
    with cT1: Dtul_x    = st.selectbox("Ø tul. bawah arah X (mm)", [10,13,16,19,22,25,29,32], index=2, key="inp_Dtul_x")
    with cT2: Dtul_y    = st.selectbox("Ø tul. bawah arah Y (mm)", [10,13,16,19,22,25,29,32], index=2, key="inp_Dtul_y")
    with cT3: Dtul_atas = st.selectbox("Ø tulangan atas (mm)",     [10,13,16,19,22,25],       index=1, key="inp_Dtul_atas")
    with cT4: alpha_s   = st.selectbox("αs kolom (40=interior, 30=tepi, 20=sudut)", [40,30,20], key="inp_alpha_s")

    st.markdown("---")
    if st.button("🔩 Hitung Penulangan Pilecap", type="primary", use_container_width=True):
        st.session_state["sudah_hitung_tul"] = True

    if st.session_state.get("sudah_hitung_tul"):
        inp  = st.session_state.get("pilecap_input")
        gaya = st.session_state.get("pilecap_gaya")
        if not inp:  st.warning("⚠️ Isi Tab Input terlebih dahulu."); st.stop()
        if not gaya: st.warning("⚠️ Jalankan perhitungan di Tab Gaya Tiang dulu."); st.stop()

        geom_t      = inp["geom"]
        hasil_tiang = gaya["hasil_tiang"]

        # d efektif
        d_eff, det_d = hitung_d_efektif(geom_t.t*1000, geom_t.cover, float(Dtul_x), float(Dtul_y), float(Dtul_atas))
        c_dx, c_dy, c_dp = st.columns(3)
        c_dx.metric("dx — arah X (mm)", f"{d_eff.dx:.1f}")
        c_dy.metric("dy — arah Y (mm)", f"{d_eff.dy:.1f}")
        c_dp.metric("d_pakai cek geser (mm)", f"{d_eff.d_pakai:.1f}")

        # Cek geser
        geser_x, geser_y, list_pons, det_geser = hitung_semua_geser(geom_t, hasil_tiang, d_eff, alpha_s)
        rg = ringkasan_geser(geser_x, geser_y, list_pons)

        cg1, cg2, cg3 = st.columns(3)
        cg1.metric("Geser 1 arah X", "✅ AMAN" if geser_x.status=="OK" else "❌ NG",
                    f"Vu={geser_x.Vu:.1f} / φVn={geser_x.phi_Vn:.1f} kN")
        cg2.metric("Geser 1 arah Y", "✅ AMAN" if geser_y.status=="OK" else "❌ NG",
                    f"Vu={geser_y.Vu:.1f} / φVn={geser_y.phi_Vn:.1f} kN")
        pons_ok = all(p.status=="OK" for p in list_pons)
        cg3.metric(f"Pons ({len(list_pons)} kolom)", "✅ AMAN" if pons_ok else "❌ NG",
                    f"rasio maks = {max(p.rasio for p in list_pons):.3f}")

        df_pons = pd.DataFrame([{
            "Kolom": p.id_kolom, "bo (mm)": f"{p.bo:.1f}",
            "Vu_pons (kN)": f"{p.Vu_pons:.2f}", "Vc_min (kN)": f"{p.Vc_min:.2f}",
            "φVn (kN)": f"{p.phi_Vn:.2f}", "Rasio": f"{p.rasio:.3f}", "Status": p.status
        } for p in list_pons])
        st.dataframe(df_pons, use_container_width=True, hide_index=True)

        # Penulangan
        hasil_tul, det_tul = hitung_penulangan(geom_t, hasil_tiang, d_eff, Dtul_x, Dtul_y, Dtul_atas)

        URUTAN = ["Bawah-X","Bawah-Y","Atas-X","Atas-Y","Badan-X","Badan-Y"]
        for pos in URUTAN:
            if pos not in hasil_tul: continue
            h = hasil_tul[pos]
            warna_border = "#16a34a" if h.OK else "#dc2626"
            st.markdown(f"""
            <div class="tul-card" style="border-left:5px solid {warna_border};">
              <div class="tul-label">{"✅" if h.OK else "❌"} {h.label_notasi}</div>
              <div style="font-size:0.75rem;color:#6b7280;font-weight:600;text-transform:uppercase">{pos}</div>
              <div style="font-size:0.82rem;color:#374151;margin:0.3rem 0">{h.penjelasan}</div>
              <div style="font-size:0.82rem;color:#6b7280">
                As_perlu: <b>{h.As_perlu:.1f} mm²</b> &nbsp;|&nbsp;
                As_pasang: <b>{h.As_pasang:.1f} mm²</b> &nbsp;|&nbsp;
                Rasio: <b>{h.rasio_As:.3f}</b>
                {"&nbsp;|&nbsp; Mu: <b>" + f"{h.Mu:.2f} kNm</b>" if h.Mu > 0 else ""}
              </div>
            </div>
            """, unsafe_allow_html=True)

        # Rekap tabel
        rekap = []
        for pos in URUTAN:
            if pos not in hasil_tul: continue
            h = hasil_tul[pos]
            arah = pos.split("-")[1]
            berbaris = {"X": "ke arah Y", "Y": "ke arah X"}.get(arah, "ke arah Z (tinggi)")
            rekap.append({
                "Posisi": pos, "Notasi": h.label_notasi,
                "Arah batang": f"Membentang {arah}", "Berbaris": berbaris,
                "As_perlu (mm²)": f"{h.As_perlu:.1f}",
                "As_pasang (mm²)": f"{h.As_pasang:.1f}",
                "Rasio As": f"{h.rasio_As:.3f}",
                "Status": "✅ OK" if h.OK else "❌ NG",
            })
        st.dataframe(pd.DataFrame(rekap), use_container_width=True, hide_index=True)

        ada_ng_tul = any(not h.OK for h in hasil_tul.values())
        if ada_ng_tul:
            st.markdown('<div class="result-ng">❌ Ada tulangan yang tidak memenuhi — tinjau ulang dimensi atau diameter.</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="result-ok">✅ Semua penulangan memenuhi SNI 2847:2019</div>', unsafe_allow_html=True)

        with st.expander("📋 Detail Perhitungan Penulangan"):
            st.markdown('<div class="calc-box">' + "\n".join(det_tul) + '</div>', unsafe_allow_html=True)

        st.session_state["pilecap_tul"] = {
            "d_efektif": d_eff, "geser_x": geser_x, "geser_y": geser_y,
            "list_pons": list_pons, "hasil_tul": hasil_tul,
        }
        st.success("✅ Lanjutkan ke tab **Laporan Word & PDF**.")

# ══════════════════════════════════════════════════════════════════════════
# TAB 4 — DOWNLOAD LAPORAN
# ══════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("## 📄 Generate & Download Laporan")

    st.markdown('<div class="section-header">📋 Identitas Laporan (Opsional)</div>', unsafe_allow_html=True)
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        nama_proyek = st.text_input("Nama Proyek",
                                     value=st.session_state["pc_nama_proyek"],
                                     placeholder="contoh: Gedung Parkir LTC Glodok",
                                     key="inp_nama_proyek")
    with col_m2:
        no_dokumen = st.text_input("Nomor Dokumen",
                                    value=st.session_state["pc_no_dokumen"],
                                    placeholder="contoh: STR-PC-001",
                                    key="inp_no_dokumen")
    st.session_state["pc_nama_proyek"] = nama_proyek
    st.session_state["pc_no_dokumen"]  = no_dokumen

    # Cek kelengkapan
    inp  = st.session_state.get("pilecap_input")
    gaya = st.session_state.get("pilecap_gaya")
    tul  = st.session_state.get("pilecap_tul")
    siap = bool(inp and gaya and tul)

    if not siap:
        yang_kurang = []
        if not inp:  yang_kurang.append("Tab 1 — Input Data (tekan tombol Validasi)")
        if not gaya: yang_kurang.append("Tab 2 — Gaya Tiang (tekan tombol Hitung)")
        if not tul:  yang_kurang.append("Tab 3 — Penulangan (tekan tombol Hitung)")
        st.markdown(f'<div class="result-warn">⚠️ Lengkapi terlebih dahulu:<br>{"<br>".join("• " + k for k in yang_kurang)}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="result-ok">✅ Semua data tersedia — siap generate laporan</div>', unsafe_allow_html=True)
        st.markdown("---")

        if st.button("🚀 Generate Laporan Word & PDF", type="primary", use_container_width=True):
            with st.spinner("Membuat laporan... mohon tunggu 10–20 detik..."):
                try:
                    # LAZY IMPORT — hanya dimuat saat tombol ditekan
                    from pilecap.report_pilecap import buat_laporan

                    buf_word, buf_pdf = buat_laporan(
                        geom        = inp["geom"],
                        beban       = gaya["beban"],
                        hasil_tiang = gaya["hasil_tiang"],
                        hasil_grup  = gaya["hasil_grup"],
                        d_efektif   = tul["d_efektif"],
                        geser_x     = tul["geser_x"],
                        geser_y     = tul["geser_y"],
                        list_pons   = tul["list_pons"],
                        hasil_tul   = tul["hasil_tul"],
                        nama_proyek = nama_proyek,
                        no_dokumen  = no_dokumen,
                    )
                    st.session_state["laporan_word"] = buf_word
                    st.session_state["laporan_pdf"]  = buf_pdf
                    st.session_state["laporan_siap"] = True
                    st.success("✅ Laporan berhasil dibuat!")

                except ImportError as e:
                    st.error(
                        f"❌ Gagal memuat modul laporan: `{e}`\n\n"
                        "Pastikan `python-docx` dan `reportlab` ada di `requirements.txt` "
                        "dan Streamlit Cloud sudah me-rebuild environment."
                    )
                except Exception as e:
                    st.error(f"❌ Gagal membuat laporan: {e}")
                    import traceback
                    st.code(traceback.format_exc())

        # Tombol download
        if st.session_state.get("laporan_siap"):
            tgl       = datetime.date.today().strftime("%Y%m%d")
            nama_file = (nama_proyek.replace(" ","_") or "Pilecap") + f"_{tgl}"

            st.markdown("---")
            st.markdown("### ⬇️ Download Laporan")
            col_w, col_p = st.columns(2)

            with col_w:
                st.markdown("""<div class="dl-card">
                  <h3>📝 Microsoft Word (.docx)</h3>
                  <p>Dapat diedit — tambahkan logo, kop surat, atau catatan tambahan</p>
                </div>""", unsafe_allow_html=True)
                buf_w = st.session_state["laporan_word"]
                buf_w.seek(0)
                st.download_button(
                    label="⬇️ Download Word",
                    data=buf_w,
                    file_name=f"{nama_file}_Pilecap.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True, type="primary",
                )

            with col_p:
                st.markdown("""<div class="dl-card">
                  <h3>📑 PDF</h3>
                  <p>Siap cetak dan distribusi ke klien / pemilik proyek</p>
                </div>""", unsafe_allow_html=True)
                buf_p = st.session_state["laporan_pdf"]
                buf_p.seek(0)
                st.download_button(
                    label="⬇️ Download PDF",
                    data=buf_p,
                    file_name=f"{nama_file}_Pilecap.pdf",
                    mime="application/pdf",
                    use_container_width=True, type="primary",
                )

            st.markdown("""
            <div class="info-box" style="margin-top:1rem;">
              📌 <b>Catatan:</b> Isi Word dan PDF adalah IDENTIK.<br>
              Gunakan <b>Word</b> untuk pengeditan lanjutan.<br>
              Gunakan <b>PDF</b> untuk pengarsipan dan pengiriman ke klien.
            </div>""", unsafe_allow_html=True)

# ==========================================================================
# FOOTER
# ==========================================================================
st.markdown("---")
st.caption(
    "Ladosi Engineering Portal — Pilecap v4.1  |  "
    "SNI 2847:2019 & SNI 8460:2017  |  "
    "github.com/LadosiTirta/ladositirta-pawon"
)
