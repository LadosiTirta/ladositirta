import streamlit as st
import pandas as pd
import math

# =============================================================================
# Fungsi Perhitungan Utama
# =============================================================================
def hitung_kapasitas_wf(d, bf, tw, tf, r, Fy, E, Lb, Cb):
    """
    Menghitung properti penampang, klasifikasi, tekuk lateral, kapasitas momen,
    dan kapasitas geser profil WF sesuai SNI 1729:2020 & AISC 360-16.

    Semua satuan input dalam mm dan MPa, output dalam N, mm, kN·m, dll.
    """
    hasil = {}

    # -------------------------------------------------------------------------
    # 1. PROPERTIES PENAMPANG
    # -------------------------------------------------------------------------
    h = d - 2 * (tf + r)                 # tinggi bersih badan (clear height)
    A = 2 * bf * tf + (d - 2 * tf) * tw  # luas penampang (abaikan radius)

    # Momen inersia (pendekatan penampang persegi, abaikan radius sudut)
    Ix = (1/12) * bf * d**3 - (1/12) * (bf - tw) * (d - 2*tf)**3
    Iy = 2 * (1/12) * tf * bf**3 + (1/12) * (d - 2*tf) * tw**3

    Sx = Ix / (d / 2)                    # modulus elastis
    Zx = bf * tf * (d - tf) + 0.25 * tw * (d - 2*tf)**2  # modulus plastis

    rx = math.sqrt(Ix / A)
    ry = math.sqrt(Iy / A)

    # Konstanta torsi (St. Venant) – pendekatan
    J = (1/3) * (2 * bf * tf**3 + (d - 2*tf) * tw**3)

    # Konstanta warping (profil I simetri ganda)
    ho = d - tf
    Cw = Iy * ho**2 / 4

    hasil['properti'] = {
        'h (tinggi bersih badan)': (h, 'mm', 'h = d - 2(tf+r)'),
        'A (luas penampang)': (A, 'mm²', 'A = 2·bf·tf + (d-2tf)·tw'),
        'Ix (momen inersia)': (Ix, 'mm⁴', '1/12·bf·d³ - 1/12·(bf-tw)(d-2tf)³'),
        'Iy (momen inersia)': (Iy, 'mm⁴', '2·(1/12)tf·bf³ + (1/12)(d-2tf)·tw³'),
        'Sx (modulus elastis)': (Sx, 'mm³', 'Sx = Ix / (d/2)'),
        'Zx (modulus plastis)': (Zx, 'mm³', 'bf·tf(d-tf) + ¼·tw(d-2tf)²'),
        'rx (radius girasi)': (rx, 'mm', '√(Ix/A)'),
        'ry (radius girasi)': (ry, 'mm', '√(Iy/A)'),
        'J (konstanta torsi)': (J, 'mm⁴', '⅓(2·bf·tf³ + (d-2tf)·tw³)'),
        'Cw (konstanta warping)': (Cw, 'mm⁶', 'Iy·ho² / 4, ho = d-tf'),
    }

    # -------------------------------------------------------------------------
    # 2. KLASIFIKASI PENAMPANG (SNI B4.1 / AISC B4.1b)
    # -------------------------------------------------------------------------
    lambda_f = bf / (2 * tf)
    lambda_pf = 0.38 * math.sqrt(E / Fy)
    lambda_rf = 1.00 * math.sqrt(E / Fy)
    if lambda_f <= lambda_pf:
        kl_sayap = 'Kompak'
    elif lambda_f <= lambda_rf:
        kl_sayap = 'Non-Kompak'
    else:
        kl_sayap = 'Langsing'

    lambda_w = h / tw
    lambda_pw = 3.76 * math.sqrt(E / Fy)
    lambda_rw = 5.70 * math.sqrt(E / Fy)
    if lambda_w <= lambda_pw:
        kl_badan = 'Kompak'
    elif lambda_w <= lambda_rw:
        kl_badan = 'Non-Kompak'
    else:
        kl_badan = 'Langsing'

    hasil['klasifikasi'] = {
        'Sayap: λ = bf/(2tf)': (lambda_f, '-', f'λpf = 0.38√(E/Fy) = {lambda_pf:.3f}, λrf = 1.0√(E/Fy) = {lambda_rf:.3f}'),
        'Sayap → Klasifikasi': (kl_sayap, '-', ''),
        'Badan: λ = h/tw': (lambda_w, '-', f'λpw = 3.76√(E/Fy) = {lambda_pw:.3f}, λrw = 5.70√(E/Fy) = {lambda_rw:.3f}'),
        'Badan → Klasifikasi': (kl_badan, '-', ''),
    }

    # -------------------------------------------------------------------------
    # 3. PARAMETER TEKUK LATERAL
    # -------------------------------------------------------------------------
    Mp = Fy * Zx                # momen plastis (N·mm)
    Mr = 0.7 * Fy * Sx          # momen batas inelastis (N·mm)
    Lp = 1.76 * ry * math.sqrt(E / Fy)  # panjang plastis penuh (mm)
    r_ts = math.sqrt(math.sqrt(Iy * Cw) / Sx)   # radius girasi efektif (mm)
    c = 1.0                     # untuk profil I simetri ganda

    # Suku dalam akar Lr
    term1 = (J * c) / (Sx * ho)
    sqrt_term = math.sqrt(term1 + math.sqrt(term1**2 + 6.76 * ((0.7 * Fy) / E)**2))
    Lr = 1.95 * r_ts * (E / (0.7 * Fy)) * sqrt_term  # panjang batas elastis (mm)

    # Klasifikasi kondisi tekuk lateral & Mn
    if Lb <= Lp:
        kondisi = 'Plastis (Lb ≤ Lp)'
        Mn = Mp
        Fcr = None  # tidak digunakan
    elif Lb <= Lr:
        kondisi = 'Inelastis (Lp < Lb ≤ Lr)'
        Mn = Cb * (Mp - (Mp - Mr) * ((Lb - Lp) / (Lr - Lp)))
        if Mn > Mp:
            Mn = Mp
        Fcr = None
    else:
        kondisi = 'Elastis (Lb > Lr)'
        # Fcr menurut AISC F2-4
        Lb_rts = Lb / r_ts
        Fcr = (Cb * math.pi**2 * E) / (Lb_rts**2) * math.sqrt(
            1 + 0.078 * (J * c) / (Sx * ho) * Lb_rts**2
        )
        Mn = Fcr * Sx
        if Mn > Mp:
            Mn = Mp

    # Konversi momen ke kN·m
    Mp_kNm = Mp * 1e-6
    Mr_kNm = Mr * 1e-6
    Mn_kNm = Mn * 1e-6

    hasil['tekuk_lateral'] = {
        'Mp (momen plastis)': (Mp_kNm, 'kN·m', 'Fy · Zx'),
        'Mr (momen batas inelastis)': (Mr_kNm, 'kN·m', '0.7 Fy · Sx'),
        'Lp (panjang plastis)': (Lp, 'mm', '1.76 ry √(E/Fy)'),
        'Lr (panjang batas elastis)': (Lr, 'mm', '1.95 rts E/(0.7Fy) √(…)'),
        'rts (radius girasi efektif)': (r_ts, 'mm', '√(√(Iy Cw) / Sx)'),
        'ho (jarak pusat sayap)': (ho, 'mm', 'd - tf'),
        'c (koefisien)': (c, '-', '1.0 untuk profil I ganda'),
        'Fcr (tegangan kritis)': (f'{Fcr:.3f}' if Fcr is not None else 'N/A', 'MPa', 'Digunakan jika Lb > Lr'),
        'Kondisi tekuk lateral': (kondisi, '-', ''),
    }

    # -------------------------------------------------------------------------
    # 4. KAPASITAS MOMEN (LRFD & ASD)
    # -------------------------------------------------------------------------
    phi_b = 0.9
    Omega_b = 1.67
    Mn_LRFD = phi_b * Mn_kNm
    Mn_ASD = Mn_kNm / Omega_b

    hasil['kapasitas_momen'] = {
        'Mn (momen nominal)': (Mn_kNm, 'kN·m', 'Lihat kondisi tekuk lateral'),
        f'φMn (LRFD, φ={phi_b})': (Mn_LRFD, 'kN·m', 'φ · Mn'),
        f'Mn/Ω (ASD, Ω={Omega_b})': (Mn_ASD, 'kN·m', 'Mn / Ω'),
        'Cb digunakan': (Cb, '-', 'Faktor modifikasi momen'),
    }

    # -------------------------------------------------------------------------
    # 5. KAPASITAS GESER
    # -------------------------------------------------------------------------
    Aw = d * tw  # luas badan (AISC menggunakan tinggi total)
    kv = 5.34    # koefisien tekuk geser, web tanpa pengaku
    lam_h_tw = h / tw
    limit1 = 1.10 * math.sqrt(kv * E / Fy)
    limit2 = 1.37 * math.sqrt(kv * E / Fy)

    if lam_h_tw <= limit1:
        Cv = 1.0
    elif lam_h_tw <= limit2:
        Cv = limit1 / lam_h_tw
    else:
        Cv = (1.51 * E * kv) / (lam_h_tw**2 * Fy)

    Vn = 0.6 * Fy * Aw * Cv  # N
    Vn_kN = Vn * 1e-3
    phi_v = 1.0
    Omega_v = 1.5
    Vn_LRFD = phi_v * Vn_kN
    Vn_ASD = Vn_kN / Omega_v

    hasil['geser'] = {
        'Aw (luas badan)': (Aw, 'mm²', 'd · tw'),
        'kv': (kv, '-', '5.34 (web tanpa pengaku)'),
        'h/tw': (lam_h_tw, '-', 'h = d - 2(tf+r)'),
        '1.10 √(kv E/Fy)': (limit1, '-', 'Batas Cv=1.0'),
        '1.37 √(kv E/Fy)': (limit2, '-', 'Batas transisi'),
        'Cv': (Cv, '-', 'Koefisien geser'),
        'Vn (geser nominal)': (Vn_kN, 'kN', '0.6 Fy Aw Cv'),
        f'φVn (LRFD, φ={phi_v})': (Vn_LRFD, 'kN', 'φ · Vn'),
        f'Vn/Ω (ASD, Ω={Omega_v})': (Vn_ASD, 'kN', 'Vn / Ω'),
    }

    return hasil


# =============================================================================
# ANTARMUKA STREAMLIT
# =============================================================================
st.title("🔩 Kapasitas Penampang Baja Profil WF (DeepSeek)")
st.markdown("Standar: **SNI 1729:2020 & AISC 360-16** (Metode LRFD dan ASD)")
st.markdown("---")

# ---------------------------
# SIDEBAR: Input Parameter
# ---------------------------
st.sidebar.header("📐 Parameter Material")
Fy = st.sidebar.number_input("Tegangan leleh Fy (MPa)", value=250.0, step=5.0)
Fu = st.sidebar.number_input("Tegangan putus Fu (MPa)", value=410.0, step=5.0)
E = st.sidebar.number_input("Modulus elastisitas E (MPa)", value=200000.0, step=1000.0)

st.sidebar.header("📐 Dimensi Penampang WF")
d = st.sidebar.number_input("Tinggi total d (mm)", value=400.0, step=5.0)
bf = st.sidebar.number_input("Lebar sayap bf (mm)", value=200.0, step=5.0)
tw = st.sidebar.number_input("Tebal badan tw (mm)", value=8.0, step=0.5)
tf = st.sidebar.number_input("Tebal sayap tf (mm)", value=13.0, step=0.5)
r = st.sidebar.number_input("Radius sudut r (mm)", value=16.0, step=1.0)

st.sidebar.header("📐 Parameter Bentang")
Lb = st.sidebar.number_input("Panjang tanpa penopang Lb (mm)", value=3000.0, step=100.0)
Cb = st.sidebar.number_input("Faktor Cb", value=1.0, step=0.1)

# Eksekusi Otomatis
hasil = hitung_kapasitas_wf(d, bf, tw, tf, r, Fy, E, Lb, Cb)

# ---------------------------
# Format Data untuk 5 Tabel
# ---------------------------
def ubah_ke_df(bagian_dict):
    data_rows = []
    for param, (nilai, satuan, ket) in bagian_dict.items():
        if isinstance(nilai, float):
            if abs(nilai) >= 1e6:
                nilai_str = f"{nilai/1e6:.4f} ×10⁶"
            else:
                nilai_str = f"{nilai:.3f}"
        else:
            nilai_str = str(nilai)
            
        data_rows.append({
            "Parameter": param,
            "Nilai": nilai_str,
            "Satuan": satuan,
            "Keterangan / Rumus": ket
        })
    return pd.DataFrame(data_rows)

df1 = ubah_ke_df(hasil['properti'])
df2 = ubah_ke_df(hasil['klasifikasi'])
df3 = ubah_ke_df(hasil['tekuk_lateral'])
df4 = ubah_ke_df(hasil['kapasitas_momen'])
df5 = ubah_ke_df(hasil['geser'])

# ---------------------------
# Tampilan Hasil di Layar
# ---------------------------
st.subheader("1️⃣ Properties Penampang")
st.dataframe(df1, use_container_width=True, hide_index=True)

st.subheader("2️⃣ Klasifikasi Penampang")
st.dataframe(df2, use_container_width=True, hide_index=True)

st.subheader("3️⃣ Parameter Tekuk Lateral")
st.dataframe(df3, use_container_width=True, hide_index=True)

st.subheader("4️⃣ Kapasitas Momen")
st.dataframe(df4, use_container_width=True, hide_index=True)

st.subheader("5️⃣ Kapasitas Geser")
st.dataframe(df5, use_container_width=True, hide_index=True)

st.markdown("---")
st.caption("selalu cek hasil yang diberikan.")
