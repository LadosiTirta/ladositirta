"""
Perhitungan Kapasitas Penampang Baja Profil WF
Referensi: SNI 1729:2020 & AISC 360-16 | Metode: LRFD & ASD
File: pages/4_Baja_WF.py
"""

import streamlit as st
import pandas as pd
import numpy as np

# ============================================================
# FUNGSI PERHITUNGAN
# ============================================================

def hitung_properties(d, bf, tw, tf, r):
    """Menghitung properties penampang WF."""
    hw = d - 2 * tf          # Tinggi badan bersih
    h  = d - 2 * (tf + r)   # Tinggi badan bersih (untuk k = tf + r)

    # Luas penampang
    A_sayap = 2 * bf * tf
    A_badan = hw * tw
    # Luas fillet (perkiraan: 2 * 0.8584 * r^2 per sisi → 4 sudut)
    A_fillet = 4 * 0.8584 * r**2
    A = A_sayap + A_badan + A_fillet

    # Inersia Ix
    Ix_sayap = 2 * (bf * tf**3 / 12 + bf * tf * ((d - tf) / 2)**2)
    Ix_badan = tw * hw**3 / 12
    Ix_fillet = 4 * (0.1098 * r**4 + 0.8584 * r**2 * (d/2 - tf - 0.4714*r)**2)
    Ix = Ix_sayap + Ix_badan + Ix_fillet

    # Inersia Iy
    Iy_sayap = 2 * (tf * bf**3 / 12)
    Iy_badan = hw * tw**3 / 12
    Iy = Iy_sayap + Iy_badan

    # Modulus elastis
    Sx = Ix / (d / 2)
    Sy = Iy / (bf / 2)

    # Modulus plastis Zx (WF simetris)
    # Zx = A/2 * jarak antar titik berat setengah penampang
    # Pendekatan praktis untuk profil WF:
    ybar_atas = (bf * tf * (d/2 - tf/2) + hw/2 * tw * hw/4) / (bf * tf + hw/2 * tw)
    Zx = 2 * (bf * tf * (d/2 - tf/2) + tw * (hw/2)**2 / 2)

    # Zy
    Zy = tf * bf**2 / 2 + tw**2 * hw / 4

    # Radius girasi
    rx = np.sqrt(Ix / A)
    ry = np.sqrt(Iy / A)

    # Konstanta torsi J (Saint-Venant)
    # J ≈ (1/3) * [2*bf*tf^3 + hw*tw^3] (tanpa koreksi fillet untuk simplifikasi)
    J = (1/3) * (2 * bf * tf**3 + hw * tw**3)

    # Konstanta warping Cw
    ho = d - tf  # jarak antar titik berat sayap
    Cw = (Iy * ho**2) / 4

    return {
        "hw": hw, "h": h, "A": A,
        "Ix": Ix, "Iy": Iy,
        "Sx": Sx, "Sy": Sy,
        "Zx": Zx, "Zy": Zy,
        "rx": rx, "ry": ry,
        "J": J, "Cw": Cw, "ho": ho
    }


def klasifikasi_penampang(bf, tw, tf, hw, Fy, E):
    """Klasifikasi kompak/non-kompak/langsing untuk sayap dan badan."""
    # Sayap (flanges in flexure): λ = bf/(2*tf)
    lam_f  = bf / (2 * tf)
    lpf    = 0.38 * np.sqrt(E / Fy)           # batas kompak
    lrf    = 1.0  * np.sqrt(E / Fy)           # batas non-kompak (AISC T.B4.1b)

    if lam_f <= lpf:
        klas_f = "Kompak"
    elif lam_f <= lrf:
        klas_f = "Non-Kompak"
    else:
        klas_f = "Langsing"

    # Badan (web in flexure): λ = hw/tw
    lam_w  = hw / tw
    lpw    = 3.76 * np.sqrt(E / Fy)
    lrw    = 5.70 * np.sqrt(E / Fy)

    if lam_w <= lpw:
        klas_w = "Kompak"
    elif lam_w <= lrw:
        klas_w = "Non-Kompak"
    else:
        klas_w = "Langsing"

    return {
        "lam_f": lam_f, "lpf": lpf, "lrf": lrf, "klas_f": klas_f,
        "lam_w": lam_w, "lpw": lpw, "lrw": lrw, "klas_w": klas_w
    }


def hitung_momen(d, bf, tw, tf, r, Fy, Fu, E, Lb, Cb, props, klas):
    """Hitung kapasitas momen Mn per AISC 360-16 Chapter F."""
    Zx  = props["Zx"]
    Sx  = props["Sx"]
    Iy  = props["Iy"]
    J   = props["J"]
    Cw  = props["Cw"]
    ho  = props["ho"]
    ry  = props["ry"]

    # Mp dan Mr
    Mp = Fy * Zx
    Mr = 0.7 * Fy * Sx

    # rts² = √(Iy*Cw) / Sx
    rts = np.sqrt(np.sqrt(Iy * Cw) / Sx)

    # c = 1 untuk profil WF simetri ganda
    c = 1.0

    # Lp = 1.76 * ry * √(E/Fy)
    Lp = 1.76 * ry * np.sqrt(E / Fy)

    # Lr = 1.95 * rts * E/(0.7*Fy) * √(J*c/(Sx*ho) + √((J*c/(Sx*ho))²+6.76*(0.7*Fy/E)²))
    term1 = J * c / (Sx * ho)
    term2 = np.sqrt(term1**2 + 6.76 * (0.7 * Fy / E)**2)
    Lr = 1.95 * rts * (E / (0.7 * Fy)) * np.sqrt(term1 + term2)

    # Tentukan kondisi & Mn
    if Lb <= Lp:
        kondisi = "Plastis (Lb ≤ Lp)"
        Mn = Mp
        Fcr = None
    elif Lb <= Lr:
        kondisi = "Inelastis (Lp < Lb ≤ Lr)"
        Mn = Cb * (Mp - (Mp - Mr) * ((Lb - Lp) / (Lr - Lp)))
        Mn = min(Mn, Mp)
        Fcr = None
    else:
        kondisi = "Elastis (Lb > Lr)"
        # Fcr = Cb*π²*E / (Lb/rts)² * √(1 + 0.078*J*c/(Sx*ho)*(Lb/rts)²)
        ratio_lt = Lb / rts
        Fcr = (Cb * np.pi**2 * E / ratio_lt**2) * np.sqrt(1 + 0.078 * J * c / (Sx * ho) * ratio_lt**2)
        Mn = min(Fcr * Sx, Mp)
        kondisi = "Elastis (Lb > Lr)"

    # Kapasitas akhir (tidak lebih dari Mp untuk kasus non-kompak penampang)
    # Untuk sayap non-kompak: Mn perlu dikurangi (FLB), tapi di sini fokus LTB
    # Catatan: jika sayap non-kompak, perlu cek FLB; di sini asumsi kompak/LTB govern
    Mn_final = min(Mn, Mp)

    return {
        "Mp": Mp, "Mr": Mr, "Lp": Lp, "Lr": Lr,
        "rts": rts, "ho": ho, "c": c,
        "Fcr": Fcr, "kondisi": kondisi,
        "Mn": Mn_final
    }


def hitung_geser(d, tw, tf, hw, Fy, E):
    """Hitung kapasitas geser Vn per AISC 360-16 Chapter G."""
    Aw = d * tw
    kv = 5.34  # untuk badan tanpa pengaku transversal (a/h > 3)

    ratio = hw / tw
    batas_cv1 = 2.24 * np.sqrt(E / Fy)

    # Cv1
    if ratio <= batas_cv1:
        Cv1 = 1.0
        catatan_cv1 = "hw/tw ≤ 2.24√(E/Fy) → Cv1 = 1.0"
    else:
        # Cv1 dari kv
        batas1 = 1.10 * np.sqrt(kv * E / Fy)
        batas2 = 1.37 * np.sqrt(kv * E / Fy)
        if ratio <= batas1:
            Cv1 = 1.0
            catatan_cv1 = f"hw/tw ≤ 1.10√(kv·E/Fy)={batas1:.1f} → Cv1=1.0"
        elif ratio <= batas2:
            Cv1 = batas1 / ratio
            catatan_cv1 = f"1.10√(kv·E/Fy) < hw/tw ≤ 1.37√ → Cv1={Cv1:.3f}"
        else:
            Cv1 = 1.51 * kv * E / (ratio**2 * Fy)
            catatan_cv1 = f"hw/tw > 1.37√(kv·E/Fy) → Cv1={Cv1:.3f}"

    Vn = 0.6 * Fy * Aw * Cv1

    return {
        "Aw": Aw, "kv": kv, "ratio": ratio,
        "batas_cv1": batas_cv1,
        "Cv1": Cv1, "catatan_cv1": catatan_cv1,
        "Vn": Vn
    }


# ============================================================
# HELPER: buat tabel DataFrame
# ============================================================

def buat_df(rows):
    """Buat DataFrame dari list of (Parameter, Nilai, Satuan, Keterangan)."""
    df = pd.DataFrame(rows, columns=["Parameter", "Nilai", "Satuan", "Keterangan / Rumus"])
    return df


def format_val(v, dec=3):
    if v is None:
        return "-"
    if abs(v) >= 1e9:
        return f"{v/1e9:.{dec}f} ×10⁹"
    if abs(v) >= 1e6:
        return f"{v/1e6:.{dec}f} ×10⁶"
    if abs(v) >= 1e3:
        return f"{v/1e3:.{dec}f} ×10³"
    return f"{v:.{dec}f}"


# ============================================================
# MAIN APP
# ============================================================

st.title("🔩 Kapasitas Penampang Baja Profil WF")
st.caption("Referensi: **SNI 1729:2020** & **AISC 360-16** | Metode: **LRFD** & **ASD**")
st.markdown("---")

# ── SIDEBAR INPUT ──────────────────────────────────────────
st.sidebar.header("📐 Input Data")

st.sidebar.subheader("Material")
Fy = st.sidebar.number_input("Fy – Tegangan Leleh (MPa)", value=250.0, step=5.0, min_value=100.0)
Fu = st.sidebar.number_input("Fu – Tegangan Tarik (MPa)", value=410.0, step=5.0, min_value=100.0)
E  = st.sidebar.number_input("E – Modulus Elastisitas (MPa)", value=200000.0, step=1000.0)

st.sidebar.subheader("Dimensi Profil WF")
d  = st.sidebar.number_input("d  – Tinggi Total (mm)",        value=400.0, step=5.0)
bf = st.sidebar.number_input("bf – Lebar Sayap (mm)",         value=200.0, step=5.0)
tw = st.sidebar.number_input("tw – Tebal Badan (mm)",         value=8.0,   step=0.5)
tf = st.sidebar.number_input("tf – Tebal Sayap (mm)",         value=13.0,  step=0.5)
r  = st.sidebar.number_input("r  – Radius Fillet (mm)",       value=16.0,  step=1.0)

st.sidebar.subheader("Parameter Tekuk Lateral")
Lb = st.sidebar.number_input("Lb – Panjang Tidak Terbreis (mm)", value=3000.0, step=100.0)
Cb = st.sidebar.number_input("Cb – Faktor Modifikasi Momen",     value=1.0,    step=0.05, min_value=1.0)

st.sidebar.markdown("---")
st.sidebar.info("Faktor ketahanan:\n- **LRFD Momen:** φ = 0.90\n- **LRFD Geser:** φ = 1.00\n- **ASD Momen:** Ω = 1.67\n- **ASD Geser:** Ω = 1.50")

# ── PERHITUNGAN ────────────────────────────────────────────
props = hitung_properties(d, bf, tw, tf, r)
klas  = klasifikasi_penampang(bf, tw, tf, props["hw"], Fy, E)
mom   = hitung_momen(d, bf, tw, tf, r, Fy, Fu, E, Lb, Cb, props, klas)
gsr   = hitung_geser(d, tw, tf, props["hw"], Fy, E)

phi_m   = 0.90
Omega_m = 1.67
phi_v   = 1.00
Omega_v = 1.50

# ── RINGKASAN KAPASITAS (ATAS) ─────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("φMn (LRFD)", f"{phi_m * mom['Mn']/1e6:.2f} kN·m")
col2.metric("Mn/Ω (ASD)",  f"{mom['Mn']/(Omega_m*1e6):.2f} kN·m")
col3.metric("φVn (LRFD)", f"{phi_v * gsr['Vn']/1e3:.2f} kN")
col4.metric("Vn/Ω (ASD)",  f"{gsr['Vn']/(Omega_v*1e3):.2f} kN")

st.markdown("---")

# ── TABEL 1: PROPERTIES PENAMPANG ─────────────────────────
st.subheader("1️⃣ Properties Penampang")

rows_prop = [
    ("hw", f"{props['hw']:.1f}", "mm", "hw = d − 2·tf  (tinggi badan bersih)"),
    ("A",  f"{props['A']:.2f}",  "mm²","A = 2·bf·tf + hw·tw + koreksi fillet"),
    ("Ix", f"{props['Ix']/1e6:.4f} ×10⁶", "mm⁴", "Ix terhadap sumbu kuat"),
    ("Iy", f"{props['Iy']/1e6:.4f} ×10⁶", "mm⁴", "Iy terhadap sumbu lemah"),
    ("Sx", f"{props['Sx']/1e3:.3f} ×10³",  "mm³", "Sx = Ix / (d/2)"),
    ("Sy", f"{props['Sy']/1e3:.3f} ×10³",  "mm³", "Sy = Iy / (bf/2)"),
    ("Zx", f"{props['Zx']/1e3:.3f} ×10³",  "mm³", "Zx = modulus plastis sumbu kuat"),
    ("rx", f"{props['rx']:.2f}",  "mm", "rx = √(Ix/A)"),
    ("ry", f"{props['ry']:.2f}",  "mm", "ry = √(Iy/A)"),
    ("J",  f"{props['J']/1e3:.3f} ×10³",   "mm⁴", "J ≈ (1/3)[2·bf·tf³ + hw·tw³]  (torsi St. Venant)"),
    ("Cw", f"{props['Cw']/1e9:.4f} ×10⁹",  "mm⁶", "Cw = Iy·ho²/4  (konstanta warping)"),
    ("ho", f"{props['ho']:.1f}",  "mm", "ho = d − tf  (jarak antar titik berat sayap)"),
]
df1 = pd.DataFrame(rows_prop, columns=["Parameter", "Nilai", "Satuan", "Keterangan / Rumus"])
st.dataframe(df1, use_container_width=True, hide_index=True)

# ── TABEL 2: KLASIFIKASI PENAMPANG ─────────────────────────
st.subheader("2️⃣ Klasifikasi Penampang")

rows_klas = [
    ("λf  (sayap)",    f"{klas['lam_f']:.3f}",  "–", "λf = bf / (2·tf)"),
    ("λpf (kompak)",   f"{klas['lpf']:.3f}",    "–", "λpf = 0.38·√(E/Fy)"),
    ("λrf (non-komp)", f"{klas['lrf']:.3f}",    "–", "λrf = 1.00·√(E/Fy)"),
    ("Klasifikasi Sayap", klas['klas_f'],        "–", f"λf={'<' if klas['lam_f']<=klas['lpf'] else '≤' if klas['lam_f']<=klas['lrf'] else '>'} batas {'λpf' if klas['lam_f']<=klas['lpf'] else 'λrf' if klas['lam_f']<=klas['lrf'] else 'λrf'}"),
    ("λw  (badan)",    f"{klas['lam_w']:.3f}",  "–", "λw = hw / tw"),
    ("λpw (kompak)",   f"{klas['lpw']:.3f}",    "–", "λpw = 3.76·√(E/Fy)"),
    ("λrw (non-komp)", f"{klas['lrw']:.3f}",    "–", "λrw = 5.70·√(E/Fy)"),
    ("Klasifikasi Badan", klas['klas_w'],        "–", f"λw={'<' if klas['lam_w']<=klas['lpw'] else '≤' if klas['lam_w']<=klas['lrw'] else '>'} batas {'λpw' if klas['lam_w']<=klas['lpw'] else 'λrw' if klas['lam_w']<=klas['lrw'] else 'λrw'}"),
]
df2 = pd.DataFrame(rows_klas, columns=["Parameter", "Nilai", "Satuan", "Keterangan / Rumus"])

def warnai_klas(val):
    if val == "Kompak":
        return "background-color: #d4edda; color: #155724"
    elif val == "Non-Kompak":
        return "background-color: #fff3cd; color: #856404"
    elif val == "Langsing":
        return "background-color: #f8d7da; color: #721c24"
    return ""

st.dataframe(
    df2.style.applymap(warnai_klas, subset=["Nilai"]),
    use_container_width=True, hide_index=True
)

# ── TABEL 3: PARAMETER TEKUK LATERAL ──────────────────────
st.subheader("3️⃣ Parameter Tekuk Lateral (LTB)")

Fcr_str = f"{mom['Fcr']/1e6:.4f} ×10⁶ N·mm" if mom['Fcr'] is not None else "N/A (bukan zona elastis)"

rows_ltb = [
    ("Mp",      f"{mom['Mp']/1e6:.4f} ×10⁶", "N·mm",  "Mp = Fy · Zx"),
    ("Mr",      f"{mom['Mr']/1e6:.4f} ×10⁶", "N·mm",  "Mr = 0.7 · Fy · Sx"),
    ("rts",     f"{mom['rts']:.3f}",           "mm",    "rts = [√(Iy·Cw)/Sx]^0.5"),
    ("ho",      f"{mom['ho']:.1f}",            "mm",    "ho = d − tf"),
    ("c",       f"{mom['c']:.1f}",             "–",     "c = 1.0 (WF simetris ganda)"),
    ("Lp",      f"{mom['Lp']:.1f}",            "mm",    "Lp = 1.76 · ry · √(E/Fy)"),
    ("Lr",      f"{mom['Lr']:.1f}",            "mm",    "Lr = 1.95·rts·(E/0.7Fy)·√(J·c/(Sx·ho)+...)"),
    ("Lb (input)", f"{Lb:.1f}",               "mm",    "Panjang tanpa breis lateral"),
    ("Cb (input)", f"{Cb:.2f}",               "–",     "Faktor modifikasi momen"),
    ("Fcr",     Fcr_str,                       "MPa",   "Fcr = Cb·π²·E/(Lb/rts)² · √(1+0.078·J·c/(Sx·ho)·(Lb/rts)²)"),
    ("Kondisi", mom['kondisi'],                "–",     f"Lb={Lb:.0f} vs Lp={mom['Lp']:.0f} vs Lr={mom['Lr']:.0f} mm"),
]
df3 = pd.DataFrame(rows_ltb, columns=["Parameter", "Nilai", "Satuan", "Keterangan / Rumus"])

def warnai_kondisi(val):
    if "Plastis" in str(val):
        return "background-color: #d4edda; color: #155724"
    elif "Inelastis" in str(val):
        return "background-color: #fff3cd; color: #856404"
    elif "Elastis" in str(val):
        return "background-color: #f8d7da; color: #721c24"
    return ""

st.dataframe(
    df3.style.applymap(warnai_kondisi, subset=["Nilai"]),
    use_container_width=True, hide_index=True
)

# ── TABEL 4: KAPASITAS MOMEN ───────────────────────────────
st.subheader("4️⃣ Kapasitas Momen")

phi_Mn   = phi_m * mom["Mn"]
Mn_Omega = mom["Mn"] / Omega_m

rows_mom = [
    ("Mn",          f"{mom['Mn']/1e6:.4f} ×10⁶", "N·mm",  f"Mn = f(kondisi LTB) — {mom['kondisi']}"),
    ("Mn",          f"{mom['Mn']/1e6/1000:.3f}",  "kN·m",  "konversi kN·m"),
    ("φ (LRFD)",    f"{phi_m:.2f}",                "–",     "SNI 1729:2020 Pasal F1 / AISC F1"),
    ("φ·Mn (LRFD)", f"{phi_Mn/1e6:.4f} ×10⁶",     "N·mm",  "Kapasitas desain LRFD"),
    ("φ·Mn (LRFD)", f"{phi_Mn/1e6/1000:.3f}",      "kN·m",  "konversi kN·m ← **GUNAKAN INI**"),
    ("Ω (ASD)",     f"{Omega_m:.2f}",              "–",     "SNI 1729:2020 Pasal F1 / AISC F1"),
    ("Mn/Ω (ASD)",  f"{Mn_Omega/1e6:.4f} ×10⁶",   "N·mm",  "Kapasitas ijin ASD"),
    ("Mn/Ω (ASD)",  f"{Mn_Omega/1e6/1000:.3f}",    "kN·m",  "konversi kN·m ← **GUNAKAN INI**"),
]
df4 = pd.DataFrame(rows_mom, columns=["Parameter", "Nilai", "Satuan", "Keterangan / Rumus"])
st.dataframe(df4, use_container_width=True, hide_index=True)

# ── TABEL 5: KAPASITAS GESER ───────────────────────────────
st.subheader("5️⃣ Kapasitas Geser")

phi_Vn   = phi_v * gsr["Vn"]
Vn_Omega = gsr["Vn"] / Omega_v

rows_gsr = [
    ("Aw",          f"{gsr['Aw']:.2f}",            "mm²",  "Aw = d · tw  (luas geser badan)"),
    ("kv",          f"{gsr['kv']:.2f}",             "–",    "kv = 5.34  (tanpa pengaku transversal, a/h > 3)"),
    ("hw/tw",       f"{gsr['ratio']:.3f}",          "–",    "Rasio kelangsingan badan"),
    ("2.24√(E/Fy)", f"{gsr['batas_cv1']:.3f}",      "–",    "Batas untuk Cv1 = 1.0 (AISC G2.1(a))"),
    ("Cv1",         f"{gsr['Cv1']:.4f}",            "–",    gsr["catatan_cv1"]),
    ("Vn",          f"{gsr['Vn']/1e3:.4f} ×10³",   "N",    "Vn = 0.6 · Fy · Aw · Cv1"),
    ("Vn",          f"{gsr['Vn']/1e3:.3f}",         "kN",   "konversi kN"),
    ("φ (LRFD)",    f"{phi_v:.2f}",                 "–",    "AISC G2.1 / SNI 1729:2020"),
    ("φ·Vn (LRFD)", f"{phi_Vn/1e3:.3f}",            "kN",   "Kapasitas geser desain LRFD ← **GUNAKAN INI**"),
    ("Ω (ASD)",     f"{Omega_v:.2f}",               "–",    "AISC G2.1 / SNI 1729:2020"),
    ("Vn/Ω (ASD)",  f"{Vn_Omega/1e3:.3f}",          "kN",   "Kapasitas geser ijin ASD ← **GUNAKAN INI**"),
]
df5 = pd.DataFrame(rows_gsr, columns=["Parameter", "Nilai", "Satuan", "Keterangan / Rumus"])
st.dataframe(df5, use_container_width=True, hide_index=True)

# ── CATATAN FOOTER ─────────────────────────────────────────
st.markdown("---")
with st.expander("📋 Catatan & Asumsi Perhitungan"):
    st.markdown("""
    **Referensi Utama:**
    - SNI 1729:2020 – Spesifikasi untuk Bangunan Gedung Baja Struktural
    - AISC 360-16 – Specification for Structural Steel Buildings

    **Asumsi & Batasan:**
    1. **Properties Penampang**: Luas fillet diperhitungkan dengan pendekatan ≈ 0.8584·r² per sudut (4 sudut total).
    2. **Klasifikasi**: Menggunakan Tabel B4.1b AISC 360-16 (elemen dalam lentur).
    3. **Kapasitas Momen (LTB)**: Menggunakan Pasal F2 AISC 360-16 untuk profil WF kompak simetris ganda.
       - Jika penampang **non-kompak** (FLB), diperlukan cek tambahan Pasal F3.
    4. **Kapasitas Geser**: Menggunakan Pasal G2.1 AISC 360-16.
       - kv = 5.34 (badan tanpa pengaku, a/h > 3.0).
    5. **Warping constant (Cw)**: Cw = Iy·ho²/4 (pendekatan untuk WF simetris ganda).
    6. **Torsional constant (J)**: Tanpa koreksi fillet (konservatif).

    **Konversi Satuan:**
    - 1 kN·m = 10⁶ N·mm
    - Semua input dalam **N** dan **mm**, output dalam **N·mm** dan **kN·m/kN**
    """)

st.caption("Dibuat dengan Python + Streamlit | Untuk keperluan engineering, selalu verifikasi dengan software resmi.")
