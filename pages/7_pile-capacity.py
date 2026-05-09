# app.py
# Program Perhitungan Kapasitas Pondasi Tiang Dalam
# Versi 1.1 — Sesi 1+2: Daya Dukung + Gaya Lateral
#
# Jalankan dengan: streamlit run app.py
# Struktur: Input → Hitung → Tampilkan Hasil & Grafik

import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime
import matplotlib
matplotlib.use("Agg")  # backend non-interaktif untuk Streamlit

from utils.input_handler import render_input_tanah, render_input_tanah_multi, render_input_tiang, validasi_data_tanah
from calculations.bearing_capacity import hitung_kapasitas_tiang, hitung_variasi_kedalaman
from calculations.lateral import hitung_broms, hitung_py_curve
from utils.grapher import (
    buat_grafik_profil,
    buat_grafik_distribusi_skin,
    buat_grafik_variasi_kedalaman,
)
from utils.grapher_lateral import buat_grafik_broms, buat_grafik_py
from utils.report_generator import buat_laporan_word, konversi_ke_pdf
from utils.export_excel import buat_excel
from utils.export_excel_rumus import buat_excel_rumus
from calculations.settlement import hitung_settlement
from calculations.buckling import hitung_kelangsingan, FAKTOR_K

# ==============================================================
# KONFIGURASI HALAMAN
# ==============================================================
st.set_page_config(
    page_title="Kapasitas Pondasi Tiang",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inisialisasi default — agar tombol Hitung bisa diklik langsung
# tanpa harus mengisi data terlebih dahulu
from utils.input_handler import DATA_TANAH_DEFAULT as _DEFAULT_TANAH
if "df_tanah" not in st.session_state:
    st.session_state["df_tanah"] = _DEFAULT_TANAH.copy()

st.title("🏗️ Perhitungan Kapasitas Pondasi Tiang Dalam")
st.caption(
    "Acuan: SNI 8460:2017 · Meyerhof (1976) · Tomlinson (2008) · API RP 2GEO | "
    "Metode: End Bearing + Skin Friction (α & β)"
)
st.divider()

# ==============================================================
# SIDEBAR: INPUT PARAMETER TIANG
# ==============================================================
param_tiang = render_input_tiang()

# Tombol Hitung di sidebar
st.sidebar.divider()
tombol_hitung = st.sidebar.button(
    "🔢 HITUNG KAPASITAS TIANG",
    type="primary",
    use_container_width=True,
    help="Tekan setelah semua data diisi."
)

# ==============================================================
# TAB UTAMA
# ==============================================================
tab_input, tab_hasil, tab_lateral, tab_settlement, tab_buckling, tab_langkah, tab_laporan = st.tabs([
    "📋 Input Data Tanah",
    "📊 Hasil Tekan & Tarik",
    "↔️ Gaya Lateral",
    "📉 Penurunan (Settlement)",
    "🏗️ Kelangsingan & Tekuk",
    "🔍 Langkah Perhitungan",
    "📄 Cetak Laporan",
])

# ----------------------------------------------------------
# TAB 1: INPUT DATA TANAH
# ----------------------------------------------------------
with tab_input:
    df_tanah = render_input_tanah_multi()

    # Pastikan selalu ada data default (tidak pernah None)
    # sehingga tombol Hitung bisa diklik langsung tanpa mengisi data terlebih dahulu
    if df_tanah is None or len(df_tanah) == 0:
        from utils.input_handler import DATA_TANAH_DEFAULT
        df_tanah = DATA_TANAH_DEFAULT.copy()

    # Simpan ke session state agar bisa diakses tab lain
    st.session_state["df_tanah"] = df_tanah

    # Pratinjau ringkasan input tiang
    st.divider()
    st.subheader("Ringkasan Parameter Tiang")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Tipe Tiang",   param_tiang["tipe"].split(" ")[0])
    col2.metric("Dimensi",      param_tiang["dim_label"])
    col3.metric("Kedalaman",    f"{param_tiang['kedalaman']:.1f} m")
    col4.metric("Muka Air",     f"{param_tiang['muka_air']:.1f} m")

# ----------------------------------------------------------
# TAB 2: HASIL PERHITUNGAN
# ----------------------------------------------------------
with tab_hasil:
    if not tombol_hitung:
        st.info("👈 Tekan **HITUNG KAPASITAS TIANG** di sidebar untuk melihat hasil (data default sudah tersedia). Atau isi data tanah Anda di tab **Input Data Tanah** terlebih dahulu.")
    else:
        # Ambil data tanah dari session state
        df_tanah = st.session_state.get("df_tanah")

        # Validasi dulu sebelum hitung
        valid, pesan_error = validasi_data_tanah(df_tanah)
        if not valid:
            for p in pesan_error:
                st.error(p)
            st.stop()

        # ---- PERHITUNGAN UTAMA ----
        with st.spinner("Menghitung kapasitas tiang..."):
            hasil = hitung_kapasitas_tiang(df_tanah, param_tiang)

        if "error" in hasil:
            st.error(hasil["error"])
            st.stop()

        # ---- KARTU RINGKASAN ----
        st.subheader("Ringkasan Daya Dukung")

        kontrol_ok = (hasil["Pn_struktur"] is None or
                      hasil["Qijin_tekan"] <= hasil["Pn_struktur"])

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(
            "Qijin Tekan",
            f"{hasil['Qijin_tekan']:,.2f} kN",
            delta=f"SF = {hasil['sf_tekan']:.1f}",
            delta_color="off"
        )
        col2.metric(
            "Qijin Tarik",
            f"{hasil['Qijin_tarik']:,.2f} kN",
            delta=f"SF = {hasil['sf_tarik']:.1f}",
            delta_color="off"
        )
        col3.metric(
            "End Bearing (Qpoint)",
            f"{hasil['Qpoint']:,.2f} kN",
            delta=f"{hasil['Qpoint']/hasil['Qult_tekan']*100:.1f}% dari Qult"
            if hasil["Qult_tekan"] > 0 else None,
            delta_color="off"
        )
        col4.metric(
            "Skin Friction (ΣQskin)",
            f"{hasil['Qskin']:,.2f} kN",
            delta=f"{hasil['Qskin']/hasil['Qult_tekan']*100:.1f}% dari Qult"
            if hasil["Qult_tekan"] > 0 else None,
            delta_color="off"
        )

        # Kapasitas struktur
        st.divider()
        col5, col6, col7 = st.columns(3)
        col5.metric("Qultimate Tekan", f"{hasil['Qult_tekan']:,.2f} kN")
        col6.metric("Qultimate Tarik", f"{hasil['Qult_tarik']:,.2f} kN")
        if hasil["Pn_struktur"]:
            col7.metric(
                "Kapasitas Struktur (Pn)",
                f"{hasil['Pn_struktur']:,.2f} kN",
                delta="OK ✓" if kontrol_ok else "Perlu dicek ✗",
                delta_color="normal" if kontrol_ok else "inverse"
            )

        # ---- TABEL DISTRIBUSI PER LAPISAN ----
        st.divider()
        st.subheader("Distribusi Daya Dukung Selimut per Lapisan")

        baris_tabel = []
        for lap in hasil["detail_lapisan"]:
            baris_tabel.append({
                "No.":             lap["no"],
                "Jenis Tanah":     lap["jenis"],
                "z atas (m)":      f"{lap['z_atas']:.2f}",
                "z bawah (m)":     f"{lap['z_bawah']:.2f}",
                "Tebal (m)":       f"{lap['tebal']:.2f}",
                "Metode":          lap["metode"],
                "σ'v (kPa)":       f"{lap['sigma_v_eff']:.2f}",
                "α / β":           f"{lap['alpha']:.2f}" if lap["kategori"] == "lempung"
                                   else f"{lap['beta']:.4f}",
                "fs (kPa)":        f"{lap['fs']:.3f}",
                "Qs (kN)":         f"{lap['Qs']:.2f}",
            })

        df_tabel = pd.DataFrame(baris_tabel)
        st.dataframe(
            df_tabel,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Qs (kN)": st.column_config.TextColumn(
                    "Qs (kN)", help="Kapasitas selimut per lapisan"
                )
            }
        )

        # Baris total
        st.markdown(
            f"**Total ΣQskin = {hasil['Qskin']:.2f} kN** &nbsp;|&nbsp; "
            f"**Qpoint = {hasil['Qpoint']:.2f} kN** &nbsp;|&nbsp; "
            f"**Qult = {hasil['Qult_tekan']:.2f} kN**"
        )

        # ---- GRAFIK ----
        st.divider()
        st.subheader("Grafik")

        gcol1, gcol2 = st.columns([2, 3])

        with gcol1:
            st.markdown("**Profil Tanah**")
            fig_profil = buat_grafik_profil(
                hasil["semua_lapisan"],
                param_tiang["kedalaman"],
                param_tiang["muka_air"],
                param_tiang["diameter"]
            )
            st.pyplot(fig_profil, use_container_width=True)

        with gcol2:
            st.markdown("**Distribusi Daya Dukung**")
            fig_dist = buat_grafik_distribusi_skin(
                hasil["detail_lapisan"],
                hasil["Qpoint"],
                param_tiang["kedalaman"]
            )
            st.pyplot(fig_dist, use_container_width=True)

        # Grafik variasi kedalaman
        if param_tiang["variasi_kedalaman"]:
            st.divider()
            st.subheader("Kapasitas Tiang vs Variasi Kedalaman")
            with st.spinner("Menghitung variasi kedalaman..."):
                hasil_variasi = hitung_variasi_kedalaman(
                    df_tanah, param_tiang,
                    z_min=param_tiang["z_min"],
                    z_max=param_tiang["z_max"],
                )
            if hasil_variasi:
                fig_var = buat_grafik_variasi_kedalaman(hasil_variasi)
                st.pyplot(fig_var, use_container_width=True)

                # Simpan hasil variasi untuk referensi
                df_variasi = pd.DataFrame(hasil_variasi)
                df_variasi.columns = ["L (m)", "Qijin Tekan (kN)", "Qijin Tarik (kN)",
                                       "Qpoint (kN)", "Qskin (kN)", "Qult Tekan (kN)"]
                with st.expander("Tabel Data Variasi Kedalaman"):
                    st.dataframe(df_variasi.round(2), use_container_width=True, hide_index=True)

        # Simpan hasil ke session state untuk dipakai tab Langkah
        st.session_state["hasil"] = hasil

# ----------------------------------------------------------
# TAB 3: LANGKAH PERHITUNGAN
# ----------------------------------------------------------
with tab_langkah:
    hasil_sesi = st.session_state.get("hasil")

    if hasil_sesi is None:
        st.info("Tekan **HITUNG KAPASITAS TIANG** di sidebar terlebih dahulu.")
    else:
        st.subheader("Langkah-Langkah Perhitungan Detail")
        st.caption("Ditampilkan urut dari end bearing → skin friction → total kapasitas.")

        # ---- LANGKAH 1: END BEARING ----
        with st.expander("📌 Langkah 1 — End Bearing (Qpoint)", expanded=True):
            teks = "\n".join(hasil_sesi["langkah_qpoint"])
            st.code(teks, language=None)

        # ---- LANGKAH 2: SKIN FRICTION ----
        with st.expander("📌 Langkah 2 — Skin Friction per Lapisan (Qskin)", expanded=True):
            teks = "\n".join(hasil_sesi["langkah_qskin"])
            st.code(teks, language=None)

        # ---- LANGKAH 3: TOTAL KAPASITAS ----
        with st.expander("📌 Langkah 3 — Kapasitas Total Tekan & Tarik", expanded=True):
            teks = "\n".join(hasil_sesi["langkah_total"])
            st.code(teks, language=None)

        # ---- LANGKAH 4: KAPASITAS STRUKTUR ----
        with st.expander("📌 Langkah 4 — Kapasitas Struktur Tiang", expanded=False):
            teks = "\n".join(hasil_sesi["langkah_struktur"])
            st.code(teks, language=None)

        # Tombol export langkah ke teks
        semua_langkah = (
            hasil_sesi["langkah_qpoint"] +
            [""] +
            hasil_sesi["langkah_qskin"] +
            [""] +
            hasil_sesi["langkah_total"] +
            [""] +
            hasil_sesi["langkah_struktur"]
        )
        teks_export = "\n".join(semua_langkah)
        st.download_button(
            label="⬇️ Download langkah perhitungan (.txt)",
            data=teks_export,
            file_name="langkah_perhitungan_tiang.txt",
            mime="text/plain",
        )

# ----------------------------------------------------------
# TAB 3: GAYA LATERAL
# ----------------------------------------------------------
with tab_lateral:
    st.subheader("Perhitungan Gaya Lateral Tiang")

    if "df_tanah" not in st.session_state:
        st.info("👈 Isi data tanah di tab **Input Data Tanah** terlebih dahulu.")
    else:
        df_tanah_lat = st.session_state["df_tanah"]

        # ---- INPUT GAYA LATERAL ----
        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("**Parameter Gaya Lateral**")
            H_lateral = st.number_input(
                "Gaya lateral H (kN)", min_value=0.0, value=50.0, step=5.0, format="%.2f",
                help="Gaya horizontal di kepala tiang atau di atas permukaan tanah."
            )
            e_lateral = st.number_input(
                "Eksentrisitas e (m)", min_value=0.0, value=0.5, step=0.1, format="%.2f",
                help="Jarak vertikal titik tangkap gaya H dari kepala tiang (atas pile cap)."
            )
            kondisi_kepala = st.radio(
                "Kondisi kepala tiang",
                options=["bebas", "jepit"],
                horizontal=True,
                help="Bebas = pile cap tidak kaku. Jepit = pile cap monolit/kaku."
            )

        with col_b:
            st.markdown("**Metode Perhitungan**")
            metode_lateral = st.radio(
                "Pilih metode",
                options=[
                    "Broms (1964) — solusi cepat",
                    "P-Y Curve — analisis numerik (LPile style)",
                ],
                help=(
                    "Broms: persamaan tertutup, cepat, cocok untuk desain awal.\n"
                    "P-Y Curve: iterasi numerik finite difference, lebih akurat untuk tanah berlapis."
                )
            )

        tombol_hitung_lat = st.button(
            "🔢 HITUNG GAYA LATERAL",
            type="primary",
            use_container_width=False,
            key="btn_lateral"
        )

        if tombol_hitung_lat:
            valid, pesan_err = validasi_data_tanah(df_tanah_lat)
            if not valid:
                for p in pesan_err:
                    st.error(p)
                st.stop()

            # ---- METODE BROMS ----
            if "Broms" in metode_lateral:
                with st.spinner("Menghitung Broms..."):
                    hasil_broms = hitung_broms(
                        H_lateral, e_lateral,
                        param_tiang, df_tanah_lat,
                        kondisi_kepala
                    )

                if "error" in hasil_broms:
                    st.error(hasil_broms["error"])
                    st.stop()

                # Simpan data tambahan untuk grafik
                hasil_broms["H_input"] = H_lateral
                hasil_broms["L"] = param_tiang["kedalaman"]
                hasil_broms["D"] = param_tiang["diameter"]

                # Kartu ringkasan
                st.divider()
                st.subheader("Hasil Broms (1964)")

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("H ultimit (Hu)", f"{hasil_broms['Hu']:.2f} kN")
                c2.metric("H ijin (SF=2.5)", f"{hasil_broms['Hijin']:.2f} kN",
                          delta="OK ✓" if hasil_broms["kontrol_ok"] else "TIDAK OK ✗",
                          delta_color="normal" if hasil_broms["kontrol_ok"] else "inverse")
                c3.metric("Momen maks", f"{hasil_broms['Mmax']:.2f} kN·m")
                c4.metric("Defleksi kepala", f"{hasil_broms['defleksi_mm']:.2f} mm")

                st.markdown(
                    f"**Tanah dominan:** {hasil_broms.get('tanah_dominan','—').title()} &nbsp;|&nbsp; "
                    f"**EI tiang:** {hasil_broms['EpIp']:,.0f} kN·m²"
                )

                # Grafik Broms
                fig_broms = buat_grafik_broms(hasil_broms)
                st.pyplot(fig_broms, use_container_width=True)

                # Langkah perhitungan Broms
                with st.expander("📌 Langkah Perhitungan Broms", expanded=False):
                    st.code("\n".join(hasil_broms["langkah"]), language=None)

                st.session_state["hasil_broms"] = hasil_broms

            # ---- METODE P-Y CURVE ----
            else:
                st.info(
                    "Analisis p-y curve menggunakan iterasi finite difference (~60 elemen). "
                    "Proses mungkin membutuhkan beberapa detik."
                )
                with st.spinner("Iterasi p-y curve... harap tunggu..."):
                    hasil_py = hitung_py_curve(
                        H_lateral, e_lateral,
                        param_tiang, df_tanah_lat,
                        kondisi_kepala
                    )

                if "error" in hasil_py:
                    st.error(hasil_py["error"])
                    st.stop()

                # Kartu ringkasan
                st.divider()
                st.subheader("Hasil P-Y Curve (Finite Difference)")

                status_konv = "Konvergen ✓" if hasil_py["konvergen"] else "Belum konvergen ⚠️"
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Defleksi kepala (y₀)", f"{hasil_py['y0_mm']:.2f} mm")
                c2.metric("Momen maks (Mmax)", f"{hasil_py['Mmax']:.2f} kN·m",
                          delta=f"z = {hasil_py['z_Mmax']:.2f} m", delta_color="off")
                c3.metric("Gaya geser maks", f"{hasil_py['Vmax']:.2f} kN")
                c4.metric("Status iterasi", status_konv,
                          delta=f"{hasil_py['iterasi']} iterasi", delta_color="off")

                st.markdown(f"**EI tiang:** {hasil_py['EI']:,.0f} kN·m²")

                # Grafik p-y
                with st.spinner("Membuat grafik..."):
                    fig_py = buat_grafik_py(hasil_py, param_tiang, df_tanah_lat)
                st.pyplot(fig_py, use_container_width=True)

                # Langkah perhitungan p-y
                with st.expander("📌 Langkah Perhitungan P-Y Curve", expanded=False):
                    st.code("\n".join(hasil_py["langkah"]), language=None)

                # Tabel profil defleksi
                with st.expander("Tabel Profil (Defleksi, Momen, Geser)"):
                    import pandas as pd
                    df_profil = pd.DataFrame({
                        "z (m)":    [f"{z:.2f}" for z in hasil_py["z_nodes"][::3]],
                        "y (mm)":   [f"{v*1000:.3f}" for v in hasil_py["y_m"][::3]],
                        "M (kN·m)": [f"{v:.2f}" for v in hasil_py["M_kNm"][::3]],
                        "V (kN)":   [f"{v:.2f}" for v in hasil_py["V_kN"][::3]],
                    })
                    st.dataframe(df_profil, use_container_width=True, hide_index=True)

                st.session_state["hasil_py"] = hasil_py


# ----------------------------------------------------------
# TAB 4: PENURUNAN (SETTLEMENT)
# ----------------------------------------------------------
with tab_settlement:
    st.subheader("Perhitungan Penurunan Tiang (Settlement)")
    st.caption("Metode: Vesic (1977) — kompresi elastis + skin friction + end bearing | Meyerhof (1976) — dari SPT-N")

    hasil_sesi_stl = st.session_state.get("hasil")
    if hasil_sesi_stl is None:
        st.info("Tekan **HITUNG KAPASITAS TIANG** di sidebar terlebih dahulu.")
    else:
        df_tanah_stl = st.session_state.get("df_tanah")
        st.markdown("**Parameter Beban Kerja**")
        col_stl1, col_stl2 = st.columns(2)
        with col_stl1:
            Q_kerja_input = st.number_input(
                "Beban kerja per tiang (kN)",
                min_value=1.0,
                value=float(hasil_sesi_stl["Qijin_tekan"]),
                step=10.0, format="%.2f",
                help="Default = Qijin tekan. Ubah sesuai beban aktual dari analisis struktur."
            )
        with col_stl2:
            st.metric("Qijin tekan tersedia", f"{hasil_sesi_stl['Qijin_tekan']:.2f} kN")
            rasio = Q_kerja_input / hasil_sesi_stl["Qijin_tekan"] * 100
            warna = "normal" if rasio <= 100 else "inverse"
            st.metric("Rasio beban / kapasitas", f"{rasio:.1f}%",
                      delta="OK ✓" if rasio <= 100 else "Melebihi kapasitas ✗",
                      delta_color=warna)

        if st.button("📉 Hitung Penurunan", type="primary", key="btn_settlement"):
            with st.spinner("Menghitung penurunan..."):
                try:
                    hasil_stl = hitung_settlement(
                        param_tiang = param_tiang,
                        hasil_tekan = hasil_sesi_stl,
                        df_tanah    = df_tanah_stl,
                        Q_kerja     = Q_kerja_input,
                    )
                    st.session_state["hasil_settlement"] = hasil_stl
                except Exception as ex:
                    st.error(f"Gagal hitung settlement: {ex}")

        if st.session_state.get("hasil_settlement"):
            h = st.session_state["hasil_settlement"]
            st.divider()
            st.subheader("Hasil Penurunan")

            # Kartu ringkasan
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Penurunan Vesic", f"{h['s_total_vesic']:.2f} mm",
                      delta=h["kontrol_vesic"], delta_color="normal" if "OK" in h["kontrol_vesic"] else "inverse")
            c2.metric("Penurunan Meyerhof", f"{h['s_meyerhof']:.2f} mm",
                      delta=h["kontrol_spt"], delta_color="normal" if "OK" in h["kontrol_spt"] else "inverse")
            c3.metric("Batas izin (SNI 8460)", f"{h['s_izin_umum']:.0f} mm")
            c4.metric("Beban kerja", f"{h['Q_kerja']:.2f} kN")

            # Breakdown komponen
            st.divider()
            st.markdown("**Komponen Penurunan (Metode Vesic)**")
            df_komponen = pd.DataFrame({
                "Komponen": [
                    "se — Kompresi elastis tiang",
                    "ss — Transfer beban selimut (skin friction)",
                    "sp — Penurunan end bearing",
                    "s_total — Total penurunan"
                ],
                "Nilai (mm)": [
                    f"{h['se_mm']:.3f}",
                    f"{h['ss_mm']:.3f}",
                    f"{h['sp_mm']:.3f}",
                    f"{h['s_total_vesic']:.3f}",
                ],
                "Persentase (%)": [
                    f"{h['se_mm']/max(h['s_total_vesic'],0.001)*100:.1f}%",
                    f"{h['ss_mm']/max(h['s_total_vesic'],0.001)*100:.1f}%",
                    f"{h['sp_mm']/max(h['s_total_vesic'],0.001)*100:.1f}%",
                    "100%",
                ]
            })
            st.dataframe(df_komponen, use_container_width=True, hide_index=True)

            # Parameter tanah yang digunakan
            st.markdown("**Parameter tanah yang digunakan**")
            col_p1, col_p2, col_p3 = st.columns(3)
            col_p1.metric("Es rata-rata", f"{h['Es_avg']:,.0f} kPa")
            col_p2.metric("Es tanah ujung", f"{h['Es_ujung']:,.0f} kPa")
            col_p3.metric("SPT-N rata-rata", f"{h['N_avg']:.1f}")

            # Langkah perhitungan
            with st.expander("📌 Langkah Perhitungan Settlement", expanded=False):
                st.code("\n".join(h["langkah"]), language=None)


# ----------------------------------------------------------
# TAB 5: KELANGSINGAN & TEKUK
# ----------------------------------------------------------
with tab_buckling:
    st.subheader("Pemeriksaan Kelangsingan & Tekuk Tiang")
    st.caption(
        "Acuan: SNI 2847:2019 Pasal 6.2.5 · Davisson & Robinson (1965) · "
        "Tomlinson (2008) Tabel 3.2 · Euler (1744)"
    )

    hasil_sesi_bkl = st.session_state.get("hasil")
    if hasil_sesi_bkl is None:
        st.info("Tekan **HITUNG KAPASITAS TIANG** di sidebar terlebih dahulu.")
    else:
        df_tanah_bkl = st.session_state.get("df_tanah")
        col_bkl1, col_bkl2, col_bkl3 = st.columns(3)
        with col_bkl1:
            kondisi_kepala_bkl = st.selectbox(
                "Kondisi kepala – ujung tiang",
                options=list(FAKTOR_K.keys()),
                index=1,
                help="Kepala jepit = tiang terhubung kaku ke pile cap. "
                     "Ujung bebas = ujung bawah tiang tidak terkekang."
            )
        with col_bkl2:
            Q_bkl = st.number_input(
                "Q aksial kerja (kN)",
                value=float(hasil_sesi_bkl["Qijin_tekan"]),
                min_value=1.0, step=10.0, format="%.2f",
                help="Beban aksial tekan kerja per tiang."
            )
        with col_bkl3:
            hasil_br_bkl = st.session_state.get("hasil_broms")
            hasil_py_bkl = st.session_state.get("hasil_py")
            M_lat_default = 0.0
            if hasil_br_bkl:
                M_lat_default = float(hasil_br_bkl.get("Mmax", 0.0))
            elif hasil_py_bkl:
                M_lat_default = float(hasil_py_bkl.get("Mmax", 0.0))
            M_bkl = st.number_input(
                "Momen lateral Mmax (kN·m)",
                value=M_lat_default, min_value=0.0, step=5.0, format="%.2f",
                help="Momen dari gaya lateral. Otomatis diisi dari tab Gaya Lateral jika sudah dihitung."
            )

        if st.button("🏗️ Periksa Kelangsingan", type="primary", key="btn_buckling"):
            with st.spinner("Memeriksa kelangsingan..."):
                try:
                    hasil_bkl = hitung_kelangsingan(
                        param_tiang         = param_tiang,
                        hasil_tekan         = hasil_sesi_bkl,
                        df_tanah            = df_tanah_bkl,
                        kondisi_kepala_atas = kondisi_kepala_bkl,
                        Q_aksial            = Q_bkl,
                        M_lateral           = M_bkl,
                    )
                    st.session_state["hasil_buckling"] = hasil_bkl
                except Exception as ex:
                    st.error(f"Gagal: {ex}")

        if st.session_state.get("hasil_buckling"):
            h = st.session_state["hasil_buckling"]
            st.divider()

            # Status keseluruhan
            if h["semua_ok"]:
                st.success(h["status_akhir"])
            else:
                st.warning(h["status_akhir"])

            # Kartu 5 pemeriksaan
            c1,c2,c3,c4,c5 = st.columns(5)
            c1.metric("L/D ratio", f"{h['LD_ratio']:.1f}",
                      delta=f"batas {h['batas_LD']}",
                      delta_color="normal" if "TIDAK" not in h["kontrol_LD"] else "inverse")
            c2.metric("Le efektif", f"{h['Le_final']:.3f} m",
                      delta=f"k = {h['k_faktor']}", delta_color="off")
            c3.metric("SF tekuk Euler", f"{h['SF_euler']:.2f}",
                      delta="OK ✓" if h["SF_euler"]>=3.0 else "TIDAK OK ✗",
                      delta_color="normal" if h["SF_euler"]>=3.0 else "inverse")
            c4.metric("kLu/r", f"{h['kLu_r']:.1f}",
                      delta=h["klu_status"],
                      delta_color="normal" if h["klu_status"]=="diabaikan" else "inverse")
            c5.metric("Rasio P-M", f"{h['rasio_PM']:.3f}",
                      delta="OK ✓" if h["rasio_PM"]<=1.0 else "TIDAK OK ✗",
                      delta_color="normal" if h["rasio_PM"]<=1.0 else "inverse")

            # Tabel ringkasan
            st.divider()
            st.markdown("**Tabel Ringkasan Pemeriksaan**")
            df_bkl_tbl = pd.DataFrame([
                {"No.": 1, "Pemeriksaan": "Rasio kelangsingan geometri (L/D)",
                 "Nilai": f"{h['LD_ratio']:.2f}", "Batas": str(h['batas_LD']),
                 "Acuan": "Tomlinson (2008) Tabel 3.2", "Status": h["kontrol_LD"].split("—")[0].strip()},
                {"No.": 2, "Pemeriksaan": "Panjang tekuk efektif (Le)",
                 "Nilai": f"{h['Le_final']:.3f} m", "Batas": "—",
                 "Acuan": "Davisson & Robinson (1965)", "Status": "─"},
                {"No.": 3, "Pemeriksaan": f"Beban tekuk Euler (Pcr = {h['Pcr']:,.0f} kN)",
                 "Nilai": f"SF = {h['SF_euler']:.2f}", "Batas": "≥ 3.0",
                 "Acuan": "Euler (1744)", "Status": "OK ✓" if h["SF_euler"]>=3.0 else "TIDAK OK ✗"},
                {"No.": 4, "Pemeriksaan": "Kolom langsing SNI 2847:2019 Ps. 6.2.5",
                 "Nilai": f"kLu/r = {h['kLu_r']:.1f}", "Batas": "< 22 diabaikan",
                 "Acuan": "SNI 2847:2019 Pasal 6.2.5(a)", "Status": h["kontrol_kolom"].split("(")[0].strip()},
                {"No.": 5, "Pemeriksaan": "Interaksi P-M (beam-column)",
                 "Nilai": f"Rasio = {h['rasio_PM']:.4f}", "Batas": "≤ 1.0",
                 "Acuan": "SNI 2847:2019 Pasal 22.4.3.1", "Status": h["kontrol_PM"].split("(")[0].strip()},
            ])
            st.dataframe(df_bkl_tbl, use_container_width=True, hide_index=True)

            # Detail parameter
            with st.expander("Detail parameter perhitungan"):
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.markdown(f"""
                    | Parameter | Nilai |
                    |-----------|-------|
                    | EI tiang | {h['EI_eff']:,.0f} kN·m² |
                    | T atau R (Davisson) | {h['T_atau_R']:.3f} m |
                    | Le₀ (kepala bebas) | {h['Le_dom']:.3f} m |
                    | k faktor | {h['k_faktor']} |
                    | Le final | {h['Le_final']:.3f} m |
                    """)
                with col_d2:
                    st.markdown(f"""
                    | Parameter | Nilai |
                    |-----------|-------|
                    | r (jari-jari girasi) | {h['r']:.4f} m |
                    | φPn kapasitas aksial | {h['fPn']:,.2f} kN |
                    | φMn kapasitas momen | {h['fMn']:.2f} kN·m |
                    | M total | {h['M_total']:.2f} kN·m |
                    | Pcr Euler | {h['Pcr']:,.2f} kN |
                    """)

            # Langkah detail
            with st.expander("📌 Langkah Perhitungan Kelangsingan (detail runtut)", expanded=False):
                st.code("\n".join(h["langkah"]), language=None)

# ----------------------------------------------------------
# TAB 5: CETAK LAPORAN (Word & PDF)
# ----------------------------------------------------------
with tab_laporan:
    st.subheader("Cetak Laporan Resmi")
    st.caption("Laporan Word dan PDF menghasilkan format yang identik.")

    hasil_sesi_lap = st.session_state.get("hasil")
    if hasil_sesi_lap is None:
        st.info("Tekan **HITUNG KAPASITAS TIANG** di sidebar terlebih dahulu sebelum mencetak laporan.")
    else:
        # ---- INFO PROYEK ----
        st.markdown("**Informasi Proyek**")
        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            nama_proyek    = st.text_input("Nama proyek", value="Proyek Pondasi Gedung")
        with col_p2:
            nama_konsultan = st.text_input("Konsultan / Dibuat oleh", value="")
        with col_p3:
            nomor_laporan  = st.text_input("Nomor laporan", value="LAP-001")

        # Cek apakah ada hasil lateral
        hasil_broms_sesi = st.session_state.get("hasil_broms")
        hasil_py_sesi    = st.session_state.get("hasil_py")

        if hasil_broms_sesi:
            hasil_lateral_lap = hasil_broms_sesi
            metode_lat_lap    = "Broms (1964) — solusi cepat"
            st.success("Data gaya lateral Broms tersedia — akan dimasukkan ke laporan.")
        elif hasil_py_sesi:
            hasil_lateral_lap = hasil_py_sesi
            metode_lat_lap    = "P-Y Curve — analisis numerik (LPile style)"
            st.success("Data gaya lateral P-Y Curve tersedia — akan dimasukkan ke laporan.")
        else:
            hasil_lateral_lap = None
            metode_lat_lap    = "—"
            st.info("Belum ada data gaya lateral. Hitung di tab **↔️ Gaya Lateral** untuk memasukkan ke laporan.")

        st.divider()

        col_w, col_p = st.columns(2)

        # ---- TOMBOL WORD ----
        with col_w:
            st.markdown("**Format Word (.docx)**")
            st.caption("Siap diedit di Microsoft Word / LibreOffice Writer.")
            if st.button("📝 Buat Laporan Word", type="primary", use_container_width=True):
                df_tanah_lap = st.session_state.get("df_tanah")
                with st.spinner("Menyusun laporan Word..."):
                    try:
                        buf_word = buat_laporan_word(
                            param_tiang     = param_tiang,
                            df_tanah        = df_tanah_lap,
                            hasil_tekan     = hasil_sesi_lap,
                            hasil_lateral   = hasil_lateral_lap,
                            metode_lateral  = metode_lat_lap,
                            hasil_buckling  = st.session_state.get("hasil_buckling"),
                            nama_proyek     = nama_proyek,
                            nama_konsultan  = nama_konsultan,
                            nomor_laporan   = nomor_laporan,
                        )
                        st.session_state["buf_word"] = buf_word
                        st.success("Laporan Word berhasil dibuat!")
                    except Exception as ex:
                        st.error(f"Gagal membuat laporan Word: {ex}")

            if st.session_state.get("buf_word"):
                nama_file_word = (
                    f"laporan_tiang_{nama_proyek.replace(' ','_')}_"
                    f"{datetime.now().strftime('%Y%m%d')}.docx"
                )
                st.download_button(
                    label="⬇️ Download Word (.docx)",
                    data=st.session_state["buf_word"].getvalue(),
                    file_name=nama_file_word,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )

        # ---- TOMBOL PDF ----
        with col_p:
            st.markdown("**Format PDF (.pdf)**")
            st.caption("Identik dengan Word — konversi via LibreOffice.")
            if st.button("🖨️ Buat Laporan PDF", type="primary", use_container_width=True):
                df_tanah_lap = st.session_state.get("df_tanah")
                with st.spinner("Menyusun laporan Word lalu mengkonversi ke PDF... (5–15 detik)"):
                    try:
                        buf_word_pdf = buat_laporan_word(
                            param_tiang     = param_tiang,
                            df_tanah        = df_tanah_lap,
                            hasil_tekan     = hasil_sesi_lap,
                            hasil_lateral   = hasil_lateral_lap,
                            metode_lateral  = metode_lat_lap,
                            hasil_buckling  = st.session_state.get("hasil_buckling"),
                            nama_proyek     = nama_proyek,
                            nama_konsultan  = nama_konsultan,
                            nomor_laporan   = nomor_laporan,
                        )
                        buf_pdf = konversi_ke_pdf(buf_word_pdf)
                        if buf_pdf:
                            st.session_state["buf_pdf"] = buf_pdf
                            st.success("Laporan PDF berhasil dibuat (identik dengan Word)!")
                        else:
                            st.warning(
                                "LibreOffice tidak dapat mengkonversi PDF di environment ini. "
                                "Gunakan laporan Word dan konversi manual via Save As PDF."
                            )
                    except Exception as ex:
                        st.error(f"Gagal membuat laporan PDF: {ex}")

            if st.session_state.get("buf_pdf"):
                nama_file_pdf = (
                    f"laporan_tiang_{nama_proyek.replace(' ','_')}_"
                    f"{datetime.now().strftime('%Y%m%d')}.pdf"
                )
                st.download_button(
                    label="⬇️ Download PDF (.pdf)",
                    data=st.session_state["buf_pdf"].getvalue(),
                    file_name=nama_file_pdf,
                    mime="application/pdf",
                    use_container_width=True,
                )

        # ---- RINGKASAN ISI LAPORAN ----
        st.divider()
        st.markdown("**Isi laporan yang akan dicetak:**")
        isi_laporan = [
            "Cover & info proyek (nama proyek, nomor laporan, tanggal, acuan standar)",
            "Data tiang (tipe, dimensi, kedalaman, material, SF)",
            "Profil data SPT per lapisan tanah",
            "Langkah perhitungan daya dukung tekan — step by step (end bearing + skin friction per lapisan)",
            "Tabel distribusi skin friction per lapisan",
            "Ringkasan daya dukung tekan & tarik dengan safety factor",
            "Langkah perhitungan gaya lateral (Broms / P-Y Curve) — jika sudah dihitung",
            "Grafik profil tanah & SPT-N",
            "Grafik distribusi skin friction per lapisan",
            "Grafik kapasitas tiang vs variasi kedalaman",
            "Grafik gaya lateral — jika sudah dihitung",
            "Daftar referensi & disclaimer",
        ]
        for item in isi_laporan:
            st.markdown(f"  ✓ {item}")

        # ---- TOMBOL EXCEL ----
        st.divider()
        st.markdown("**Format Excel (.xlsx) — Nilai saja, tanpa rumus**")
        st.caption(
            "Berisi 5 sheet: Info & Input · Profil Tanah · Hasil Tekan & Tarik · "
            "Gaya Lateral · Grafik. Tidak ada formula — aman untuk distribusi komersial."
        )
        col_ex1, col_ex2 = st.columns([1, 2])
        with col_ex1:
            sertakan_grafik_xl = st.checkbox("Sertakan grafik di Excel", value=True,
                key="xl_grafik",
                help="Grafik menambah ukuran file ~100–200 KB.")

        if st.button("📊 Buat File Excel", use_container_width=False, key="btn_excel"):
            df_tanah_xl = st.session_state.get("df_tanah")
            with st.spinner("Menyusun file Excel..."):
                try:
                    buf_excel = buat_excel(
                        param_tiang      = param_tiang,
                        df_tanah         = df_tanah_xl,
                        hasil_tekan      = hasil_sesi_lap,
                        hasil_lateral    = hasil_lateral_lap,
                        metode_lateral   = metode_lat_lap,
                        nama_proyek      = nama_proyek,
                        nama_konsultan   = nama_konsultan,
                        nomor_laporan    = nomor_laporan,
                        sertakan_grafik  = sertakan_grafik_xl,
                    )
                    st.session_state["buf_excel"] = buf_excel
                    st.success(
                        f"Excel berhasil dibuat! "
                        f"({len(buf_excel.getvalue())//1024} KB · 0 formula)"
                    )
                except Exception as ex:
                    st.error(f"Gagal membuat Excel: {ex}")

        if st.session_state.get("buf_excel"):
            nama_file_xl = (
                f"hasil_tiang_{nama_proyek.replace(' ','_')}_"
                f"{datetime.now().strftime('%Y%m%d')}.xlsx"
            )
            st.download_button(
                label="⬇️ Download Excel (.xlsx)",
                data=st.session_state["buf_excel"].getvalue(),
                file_name=nama_file_xl,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=False,
            )

        # ---- TOMBOL EXCEL DENGAN RUMUS (ADMIN ONLY) ----
        st.divider()
        col_xr_title, col_xr_help = st.columns([8, 1])
        with col_xr_title:
            st.markdown("**Format Excel (.xlsx) — Dengan rumus (khusus pengembang / admin Ladosi)**")
        with col_xr_help:
            st.button("❓", key="btn_help_rumus",
                      help="File ini dilindungi password dan hanya untuk pengembang. "
                           "Hubungi admin Ladosi untuk akses.")

        st.caption(
            "🔒 File ini dilindungi. Untuk mengakses, hubungi **admin / pengembang Ladosi**."
        )

        pw_input = st.text_input(
            "pw_rumus",
            type="password",
            key="pw_excel_rumus",
            label_visibility="collapsed",
            placeholder="Masukkan kode akses dari admin Ladosi...",
        )

        if st.button("📐 Buat & Download Excel + Rumus", key="btn_excel_rumus"):
            # pw tersimpan di kode — tidak tampil di UI
            _PW = "L@d0s1_4dm1n_2025"
            if not pw_input:
                st.warning("Masukkan kode akses terlebih dahulu. Hubungi admin Ladosi untuk mendapatkan kode.")
            elif pw_input != _PW:
                st.error("Kode akses tidak valid. Hubungi admin / pengembang Ladosi.")
            else:
                df_tanah_xr = st.session_state.get("df_tanah")
                with st.spinner("Menyusun file..."):
                    try:
                        buf_xr = buat_excel_rumus(
                            param_tiang    = param_tiang,
                            df_tanah       = df_tanah_xr,
                            nama_proyek    = nama_proyek,
                            nama_konsultan = nama_konsultan,
                        )
                        st.session_state["buf_excel_rumus"] = buf_xr
                        st.success("File siap didownload.")
                    except Exception as ex:
                        st.error(f"Gagal: {ex}")

        if st.session_state.get("buf_excel_rumus") and pw_input == "L@d0s1_4dm1n_2025":
            nama_xr = (
                f"template_rumus_{nama_proyek.replace(' ','_')}_"
                f"{datetime.now().strftime('%Y%m%d')}.xlsx"
            )
            st.download_button(
                label="⬇️ Download Excel + Rumus (.xlsx)",
                data=st.session_state["buf_excel_rumus"].getvalue(),
                file_name=nama_xr,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=False,
            )

        # ═══════════════════════════════════════════
        # CATATAN DEVELOPER — tidak tampil di layar
        # Kode akses Excel rumus : L@d0s1_4dm1n_2025
        # Password sheet Excel   : admin123
        #   → ganti di utils/export_excel_rumus.py baris: PASSWORD = "..."
        # ═══════════════════════════════════════════
