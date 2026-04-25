"""
=============================================================
APLIKASI WEB — KAPASITAS LENTUR BALOK BETON BERTULANG
Referensi : SNI 2847:2019 (ACI 318-14)
Framework  : Streamlit
Jalankan   : streamlit run app_lentur_balok.py
=============================================================
"""

import math
import streamlit as st

# ─── KONFIGURASI HALAMAN ────────────────────────────────────
st.set_page_config(
    page_title="Lentur Balok Beton | SNI 2847:2019",
    page_icon="🏗️",
    layout="wide",
)

# ─── CSS KUSTOM ─────────────────────────────────────────────
st.markdown("""
<style>
    .main-title {
        font-size: 1.6rem; font-weight: 600;
        color: #1a3c5e; margin-bottom: 0;
    }
    .sub-title {
        font-size: 0.9rem; color: #666;
        margin-bottom: 1.5rem;
    }
    .step-box {
        background: #f8f9fa;
        border-left: 4px solid #1a3c5e;
        border-radius: 0 8px 8px 0;
        padding: 12px 16px;
        margin-bottom: 10px;
        font-family: monospace;
        font-size: 0.85rem;
    }
    .step-header {
        font-weight: 700;
        color: #1a3c5e;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 4px;
    }
    .result-ok    { background:#e8f5e9; border-color:#2e7d32; color:#1b5e20; padding:12px 16px; border-radius:8px; border-left:4px solid; font-weight:600; }
    .result-warn  { background:#fff8e1; border-color:#f9a825; color:#5d4037; padding:12px 16px; border-radius:8px; border-left:4px solid; font-weight:600; }
    .result-fail  { background:#ffebee; border-color:#c62828; color:#b71c1c; padding:12px 16px; border-radius:8px; border-left:4px solid; font-weight:600; }
    .metric-card {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 14px;
        text-align: center;
    }
    .metric-label { font-size: 0.75rem; color: #888; margin-bottom: 4px; }
    .metric-value { font-size: 1.5rem; font-weight: 700; color: #1a3c5e; }
    .metric-unit  { font-size: 0.75rem; color: #aaa; }
    .section-divider {
        border: none;
        border-top: 2px solid #e0e0e0;
        margin: 1.5rem 0;
    }
    .ref-badge {
        display: inline-block;
        background: #e3f2fd;
        color: #1565c0;
        font-size: 0.7rem;
        padding: 2px 8px;
        border-radius: 20px;
        margin-bottom: 6px;
    }
    code { background: #eef; padding: 2px 6px; border-radius: 4px; font-size: 0.82rem; }
</style>
""", unsafe_allow_html=True)


# ─── FUNGSI PERHITUNGAN ─────────────────────────────────────
def hitung_lentur_balok(fc, fy, b, h, d, As, Asp=0.0):
    hasil = {}

    # Langkah 1 — beta1
    if fc <= 28:
        beta1 = 0.85
        beta1_cara = f"f'c = {fc} MPa ≤ 28 MPa  →  β₁ = 0.85"
    elif fc >= 56:
        beta1 = 0.65
        beta1_cara = f"f'c = {fc} MPa ≥ 56 MPa  →  β₁ = 0.65"
    else:
        beta1 = 0.85 - 0.05 * (fc - 28) / 7
        beta1 = max(0.65, min(0.85, beta1))
        beta1_cara = f"β₁ = 0.85 − 0.05 × (f'c − 28) / 7\n   = 0.85 − 0.05 × ({fc} − 28) / 7"
    hasil['beta1'] = beta1
    hasil['beta1_cara'] = beta1_cara

    # Langkah 2 — Gaya tarik
    As_net = As - Asp
    T = As_net * fy
    hasil['As_net'] = As_net
    hasil['T'] = T

    # Langkah 3 — a
    a = (As_net * fy) / (0.85 * fc * b)
    hasil['a'] = a

    # Langkah 4 — c
    c = a / beta1
    hasil['c'] = c

    # Langkah 5 — rho aktual
    rho_actual = As / (b * d)
    hasil['rho'] = rho_actual

    # Langkah 6 — rho_min
    rho_min_a = 0.25 * math.sqrt(fc) / fy
    rho_min_b = 1.4 / fy
    rho_min = max(rho_min_a, rho_min_b)
    hasil['rho_min'] = rho_min
    hasil['rho_min_a'] = rho_min_a
    hasil['rho_min_b'] = rho_min_b

    # Langkah 7 — rho_max
    rho_bal = (0.85 * beta1 * fc / fy) * (600 / (600 + fy))
    rho_max = 0.75 * rho_bal
    hasil['rho_bal'] = rho_bal
    hasil['rho_max'] = rho_max

    # Langkah 8 — et
    et = 0.003 * (d - c) / c
    hasil['et'] = et

    # Langkah 9 — phi
    if et >= 0.005:
        phi = 0.90
        phi_cara = "εt ≥ 0.005 → Tension-controlled → φ = 0.90"
    elif et <= 0.002:
        phi = 0.65
        phi_cara = "εt ≤ 0.002 → Compression-controlled → φ = 0.65"
    else:
        phi = 0.65 + (et - 0.002) * (250 / 3)
        phi_cara = f"φ = 0.65 + (εt − 0.002) × 250/3\n  = 0.65 + ({et:.5f} − 0.002) × 83.333"
    hasil['phi'] = phi
    hasil['phi_cara'] = phi_cara

    # Langkah 10 — Mn, phiMn
    Mn    = As_net * fy * (d - a / 2) / 1_000_000
    phiMn = phi * Mn
    hasil['Mn'] = Mn
    hasil['phiMn'] = phiMn

    # Kontrol
    hasil['ok_rho_min'] = rho_actual >= rho_min
    hasil['ok_rho_max'] = rho_actual <= rho_max
    hasil['ok_et']      = et >= 0.004

    return hasil


# ─── HEADER ────────────────────────────────────────────────
st.markdown('<p class="main-title">🏗️ Kapasitas Lentur Balok Beton Bertulang</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">Referensi: SNI 2847:2019 (setara ACI 318-14) | Urutan perhitungan sesuai urutan pasal</p>', unsafe_allow_html=True)

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# ─── LAYOUT: INPUT KIRI | HASIL KANAN ──────────────────────
col_input, col_hasil = st.columns([1, 2], gap="large")

with col_input:
    st.markdown("### 📋 Data Input Penampang")

    st.markdown("**Material**")
    fc  = st.number_input("f'c — Kuat tekan beton (MPa)",  min_value=17.0, max_value=100.0, value=30.0, step=1.0, format="%.1f")
    fy  = st.number_input("fy — Kuat leleh tulangan (MPa)", min_value=240.0, max_value=600.0, value=400.0, step=10.0, format="%.0f")

    st.markdown("**Geometri Penampang**")
    col_b, col_h = st.columns(2)
    with col_b:
        b = st.number_input("b (mm)\nLebar", min_value=100.0, max_value=2000.0, value=300.0, step=10.0, format="%.0f")
    with col_h:
        h = st.number_input("h (mm)\nTinggi total", min_value=100.0, max_value=5000.0, value=500.0, step=10.0, format="%.0f")

    d = st.number_input("d (mm) — Tinggi efektif (h − selimut − ½D)", min_value=50.0, max_value=4900.0, value=440.0, step=5.0, format="%.0f")

    st.markdown("**Tulangan**")
    As  = st.number_input("As (mm²) — Tulangan tarik",  min_value=0.0, value=1520.0, step=10.0, format="%.0f",
                          help="Contoh: 4D22 = 4 × 380.1 = 1520 mm²")
    Asp = st.number_input("As' (mm²) — Tulangan tekan", min_value=0.0, value=0.0,    step=10.0, format="%.0f",
                          help="Isi 0 jika tidak ada tulangan tekan")

    st.markdown("")
    tombol = st.button("⚡ HITUNG KAPASITAS LENTUR", use_container_width=True, type="primary")

    # Info singkat tulangan umum
    with st.expander("📌 Referensi luas tulangan (mm²)"):
        st.markdown("""
        | Diameter | 1 batang | 2 | 3 | 4 | 5 | 6 |
        |---|---|---|---|---|---|---|
        | D10 | 78.5 | 157 | 236 | 314 | 393 | 471 |
        | D13 | 132.7 | 265 | 398 | 531 | 663 | 796 |
        | D16 | 201.1 | 402 | 603 | 804 | 1005 | 1206 |
        | D19 | 283.5 | 567 | 851 | 1134 | 1418 | 1701 |
        | D22 | 380.1 | 760 | 1140 | 1520 | 1901 | 2281 |
        | D25 | 490.9 | 982 | 1473 | 1964 | 2454 | 2945 |
        | D29 | 660.5 | 1321 | 1981 | 2642 | 3302 | 3963 |
        | D32 | 804.2 | 1608 | 2413 | 3217 | 4021 | 4825 |
        """)


# ─── HASIL ─────────────────────────────────────────────────
with col_hasil:
    if tombol:
        if d >= h:
            st.error("⚠️ Tinggi efektif d harus lebih kecil dari tinggi total h!")
        elif As <= 0:
            st.error("⚠️ Luas tulangan tarik As harus lebih besar dari 0!")
        else:
            R = hitung_lentur_balok(fc, fy, b, h, d, As, Asp)

            # ── RINGKASAN METRIK ────────────────────────────
            st.markdown("### 📊 Hasil Utama")
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.markdown(f"""<div class="metric-card">
                    <div class="metric-label">Momen Nominal Mn</div>
                    <div class="metric-value">{R['Mn']:.2f}</div>
                    <div class="metric-unit">kN·m</div></div>""", unsafe_allow_html=True)
            with m2:
                st.markdown(f"""<div class="metric-card">
                    <div class="metric-label">φMn (Momen Rencana)</div>
                    <div class="metric-value">{R['phiMn']:.2f}</div>
                    <div class="metric-unit">kN·m</div></div>""", unsafe_allow_html=True)
            with m3:
                st.markdown(f"""<div class="metric-card">
                    <div class="metric-label">Faktor Reduksi φ</div>
                    <div class="metric-value">{R['phi']:.3f}</div>
                    <div class="metric-unit">—</div></div>""", unsafe_allow_html=True)
            with m4:
                st.markdown(f"""<div class="metric-card">
                    <div class="metric-label">Regangan εt</div>
                    <div class="metric-value">{R['et']:.4f}</div>
                    <div class="metric-unit">—</div></div>""", unsafe_allow_html=True)

            st.markdown("")

            # ── STATUS KESELURUHAN ───────────────────────────
            all_ok = R['ok_rho_min'] and R['ok_rho_max'] and R['ok_et']
            if all_ok and R['et'] >= 0.005:
                st.markdown('<div class="result-ok">✅ PENAMPANG OK — Tension-controlled, memenuhi seluruh syarat SNI 2847:2019</div>', unsafe_allow_html=True)
            elif all_ok:
                st.markdown('<div class="result-warn">⚠️ PERLU TINJAUAN — Zona transisi (0.004 ≤ εt &lt; 0.005), pertimbangkan tambah tulangan</div>', unsafe_allow_html=True)
            else:
                masalah = []
                if not R['ok_rho_min']: masalah.append("ρ &lt; ρ_min → tambah tulangan")
                if not R['ok_rho_max']: masalah.append("ρ > ρ_max → kurangi tulangan")
                if not R['ok_et']:      masalah.append("εt &lt; 0.004 → tidak memenuhi syarat")
                st.markdown(f'<div class="result-fail">❌ TIDAK OK — {" | ".join(masalah)}</div>', unsafe_allow_html=True)

            st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

            # ── URUTAN LANGKAH PERHITUNGAN ───────────────────
            st.markdown("### 📐 Urutan Perhitungan")

            steps = [
                {
                    "no": "Langkah 1",
                    "judul": "Faktor blok tegangan ekivalen β₁",
                    "ref": "SNI 2847:2019 Pasal 22.2.2.4.3",
                    "isi": (
                        f"{R['beta1_cara']}\n"
                        f"► β₁ = {R['beta1']:.4f}"
                    ),
                    "ok": True
                },
                {
                    "no": "Langkah 2",
                    "judul": "Gaya tarik tulangan (T)",
                    "ref": "SNI 2847:2019 Pasal 22.2.1",
                    "isi": (
                        f"T = As_net × fy\n"
                        f"  = ({As:.0f} − {Asp:.0f}) × {fy:.0f}\n"
                        f"► T = {R['T']:,.0f} N  =  {R['T']/1000:.1f} kN"
                    ),
                    "ok": True
                },
                {
                    "no": "Langkah 3",
                    "judul": "Kedalaman blok tegangan ekivalen (a)",
                    "ref": "SNI 2847:2019 Pasal 22.2.2.4",
                    "isi": (
                        f"a = As_net × fy / (0.85 × f'c × b)\n"
                        f"  = {R['As_net']:.0f} × {fy:.0f} / (0.85 × {fc} × {b:.0f})\n"
                        f"► a = {R['a']:.2f} mm"
                    ),
                    "ok": True
                },
                {
                    "no": "Langkah 4",
                    "judul": "Kedalaman sumbu netral (c)",
                    "ref": "SNI 2847:2019 Pasal 22.2.2.4.1",
                    "isi": (
                        f"c = a / β₁  =  {R['a']:.2f} / {R['beta1']:.4f}\n"
                        f"► c = {R['c']:.2f} mm"
                    ),
                    "ok": True
                },
                {
                    "no": "Langkah 5",
                    "judul": "Rasio tulangan aktual (ρ)",
                    "ref": "SNI 2847:2019 Pasal 9.6.1",
                    "isi": (
                        f"ρ = As / (b × d)  =  {As:.0f} / ({b:.0f} × {d:.0f})\n"
                        f"► ρ = {R['rho']:.6f}  =  {R['rho']*100:.4f}%"
                    ),
                    "ok": R['ok_rho_min'] and R['ok_rho_max']
                },
                {
                    "no": "Langkah 6",
                    "judul": "Rasio tulangan minimum (ρ_min)",
                    "ref": "SNI 2847:2019 Pasal 9.6.1.2",
                    "isi": (
                        f"ρ_min = max( 0.25√f'c/fy  ,  1.4/fy )\n"
                        f"      = max( {R['rho_min_a']:.6f}  ,  {R['rho_min_b']:.6f} )\n"
                        f"► ρ_min = {R['rho_min']:.6f}  =  {R['rho_min']*100:.4f}%\n"
                        f"  Kontrol: ρ = {R['rho']*100:.4f}% {'≥' if R['ok_rho_min'] else '<'} ρ_min = {R['rho_min']*100:.4f}%  "
                        f"{'✓' if R['ok_rho_min'] else '✗'}"
                    ),
                    "ok": R['ok_rho_min']
                },
                {
                    "no": "Langkah 7",
                    "judul": "Rasio tulangan maksimum (ρ_max)",
                    "ref": "SNI 2847:2019 Pasal 21.2.2",
                    "isi": (
                        f"ρ_bal = 0.85 × β₁ × f'c/fy × 600/(600+fy)\n"
                        f"      = 0.85 × {R['beta1']:.4f} × {fc}/{fy:.0f} × 600/{600+fy:.0f}\n"
                        f"ρ_bal = {R['rho_bal']:.6f}  =  {R['rho_bal']*100:.4f}%\n"
                        f"ρ_max = 0.75 × ρ_bal = {R['rho_max']:.6f}  =  {R['rho_max']*100:.4f}%\n"
                        f"  Kontrol: ρ = {R['rho']*100:.4f}% {'≤' if R['ok_rho_max'] else '>'} ρ_max = {R['rho_max']*100:.4f}%  "
                        f"{'✓' if R['ok_rho_max'] else '✗'}"
                    ),
                    "ok": R['ok_rho_max']
                },
                {
                    "no": "Langkah 8",
                    "judul": "Regangan tarik tulangan (εt)",
                    "ref": "SNI 2847:2019 Pasal 21.2.2",
                    "isi": (
                        f"εt = 0.003 × (d − c) / c\n"
                        f"   = 0.003 × ({d:.0f} − {R['c']:.2f}) / {R['c']:.2f}\n"
                        f"► εt = {R['et']:.5f}\n"
                        f"  {'εt ≥ 0.005 → Tension-controlled ✓' if R['et'] >= 0.005 else '0.004 ≤ εt < 0.005 → Zona transisi ⚠️' if R['et'] >= 0.004 else 'εt < 0.004 → Tidak memenuhi syarat ✗'}"
                    ),
                    "ok": R['ok_et']
                },
                {
                    "no": "Langkah 9",
                    "judul": "Faktor reduksi kekuatan (φ)",
                    "ref": "SNI 2847:2019 Tabel 21.2.2",
                    "isi": (
                        f"{R['phi_cara']}\n"
                        f"► φ = {R['phi']:.4f}"
                    ),
                    "ok": R['et'] >= 0.004
                },
                {
                    "no": "Langkah 10",
                    "judul": "Momen nominal dan momen rencana",
                    "ref": "SNI 2847:2019 Pasal 22.3.2",
                    "isi": (
                        f"Mn = As_net × fy × (d − a/2)\n"
                        f"   = {R['As_net']:.0f} × {fy:.0f} × ({d:.0f} − {R['a']/2:.2f})\n"
                        f"   = {R['As_net'] * fy * (d - R['a']/2):,.0f} N·mm\n"
                        f"► Mn   = {R['Mn']:.3f} kN·m\n"
                        f"\n"
                        f"φMn  = φ × Mn = {R['phi']:.4f} × {R['Mn']:.3f}\n"
                        f"► φMn = {R['phiMn']:.3f} kN·m"
                    ),
                    "ok": True
                },
            ]

            border_color = {"ok": "#2e7d32", "warn": "#f9a825", "fail": "#c62828"}

            for s in steps:
                warna = "#2e7d32" if s['ok'] else "#c62828"
                tanda = "✓" if s['ok'] else "✗"
                st.markdown(f"""
                <div class="step-box" style="border-left-color:{warna}">
                    <div class="ref-badge">{s['ref']}</div><br>
                    <div class="step-header">{s['no']} — {s['judul']} &nbsp; {tanda}</div>
                    <pre style="margin:0;font-size:0.82rem;white-space:pre-wrap;font-family:monospace;">{s['isi']}</pre>
                </div>
                """, unsafe_allow_html=True)

            # ── TABEL RANGKUMAN ──────────────────────────────
            st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
            st.markdown("### 📋 Tabel Rangkuman Hasil")

            import pandas as pd
            df = pd.DataFrame({
                "Parameter": ["β₁", "a (mm)", "c (mm)", "εt", "φ", "ρ (%)", "ρ_min (%)", "ρ_max (%)", "Mn (kN·m)", "φMn (kN·m)"],
                "Nilai": [
                    f"{R['beta1']:.4f}",
                    f"{R['a']:.2f}",
                    f"{R['c']:.2f}",
                    f"{R['et']:.5f}",
                    f"{R['phi']:.4f}",
                    f"{R['rho']*100:.4f}",
                    f"{R['rho_min']*100:.4f}",
                    f"{R['rho_max']*100:.4f}",
                    f"{R['Mn']:.3f}",
                    f"{R['phiMn']:.3f}",
                ],
                "Status": [
                    "—", "—", "—",
                    "✅ OK" if R['et'] >= 0.005 else ("⚠️ Transisi" if R['et'] >= 0.004 else "❌ Tidak OK"),
                    "—",
                    "✅ OK" if (R['ok_rho_min'] and R['ok_rho_max']) else "❌ Tidak OK",
                    "✅ OK" if R['ok_rho_min'] else "❌ Tidak OK",
                    "✅ OK" if R['ok_rho_max'] else "❌ Tidak OK",
                    "—",
                    "—",
                ]
            })
            st.dataframe(df, use_container_width=True, hide_index=True)

    else:
        # Placeholder sebelum hitung
        st.info("👈  Isi data di panel kiri, lalu klik **HITUNG KAPASITAS LENTUR**")
        st.markdown("""
        **Yang akan dihitung secara runtut:**
        1. Faktor β₁ (blok tegangan Whitney)
        2. Gaya tarik tulangan T
        3. Kedalaman blok tegangan **a**
        4. Kedalaman sumbu netral **c**
        5. Rasio tulangan aktual ρ
        6. Batas ρ_min (SNI Pasal 9.6.1.2)
        7. Batas ρ_max (0.75 ρ_bal)
        8. Regangan tarik εt
        9. Faktor reduksi φ
        10. Momen nominal **Mn** dan momen rencana **φMn**
        """)


# ─── FOOTER ─────────────────────────────────────────────────
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;font-size:0.75rem;color:#aaa;'>"
    "Referensi: SNI 2847:2019 | ACI 318-14 | Untuk keperluan profesional — verifikasi mandiri tetap diperlukan"
    "</p>",
    unsafe_allow_html=True
)