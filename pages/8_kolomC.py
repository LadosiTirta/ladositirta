"""
app.py - Perhitungan Kapasitas Kolom Beton Bertulang
Diagram Interaksi P-M | SNI 2847:2019
Author: Ladosi
v2.0 - Fixed: diagram interaksi, cek kapasitas, TypeError phi_Pn_kapasitas
"""

import streamlit as st
import numpy as np
import math
import io
import pandas as pd

# ============================================================
# BAGIAN 1: LOGIKA KALKULASI
# ============================================================

def hitung_properties(b, h, c, dia_s, D, n_b, n_h, fc, fy, Es):
    Ag = b * h
    Ig = (1.0/12.0) * b * h**3
    Ec = 4700.0 * math.sqrt(fc)
    d_prime = c + dia_s + D / 2.0
    d = h - d_prime
    n_total = 2 * n_b + 2 * (n_h - 2)
    Ast = n_total * math.pi * D**2 / 4.0
    rho_g = Ast / Ag * 100.0
    cek_rasio = "OK" if 1.0 <= rho_g <= 8.0 else "NOT OK"
    return {
        "Ag": Ag, "Ig": Ig, "Ec": Ec,
        "d": d, "d_prime": d_prime,
        "n_total": n_total, "Ast": Ast,
        "rho_g": rho_g, "cek_rasio": cek_rasio
    }


def hitung_kekakuan_elemen(fc,
                            bb_al, hb_al, Lb_al,
                            bb_ar, hb_ar, Lb_ar,
                            bk_a,  hk_a,  Lk_a,
                            bb_bl, hb_bl, Lb_bl,
                            bb_br, hb_br, Lb_br,
                            bk_b,  hk_b,  Lk_b,
                            b_kol, h_kol, Lu):
    Ec = 4700.0 * math.sqrt(fc)

    def ei_l(b_e, h_e, L_e):
        if L_e <= 0:
            return 0.0
        return Ec * (1.0/12.0 * b_e * h_e**3) / L_e

    v = {
        "bal_atas_kiri":   ei_l(bb_al, hb_al, Lb_al),
        "bal_atas_kanan":  ei_l(bb_ar, hb_ar, Lb_ar),
        "kol_atas":        ei_l(bk_a,  hk_a,  Lk_a),
        "bal_bawah_kiri":  ei_l(bb_bl, hb_bl, Lb_bl),
        "bal_bawah_kanan": ei_l(bb_br, hb_br, Lb_br),
        "kol_bawah":       ei_l(bk_b,  hk_b,  Lk_b),
        "kol_ditinjau":    ei_l(b_kol, h_kol, Lu),
    }

    sum_kol_atas    = v["kol_atas"]  + v["kol_ditinjau"]
    sum_bal_atas    = v["bal_atas_kiri"] + v["bal_atas_kanan"]
    sum_kol_bawah   = v["kol_bawah"] + v["kol_ditinjau"]
    sum_bal_bawah   = v["bal_bawah_kiri"] + v["bal_bawah_kanan"]

    psi_A = sum_kol_atas  / sum_bal_atas  if sum_bal_atas  > 0 else 10.0
    psi_B = sum_kol_bawah / sum_bal_bawah if sum_bal_bawah > 0 else 10.0

    v.update({
        "sum_kol_atas": sum_kol_atas, "sum_bal_atas": sum_bal_atas,
        "sum_kol_bawah": sum_kol_bawah, "sum_bal_bawah": sum_bal_bawah,
        "psi_A": psi_A, "psi_B": psi_B,
    })
    return v


def hitung_k_kelangsingan(psi_A, psi_B, kondisi, Lu, h, M1, M2):
    psi_m = (psi_A + psi_B) / 2.0

    k_br1 = min(0.7 + 0.05 * (psi_A + psi_B), 1.0)
    k_br2 = min(0.85 + 0.05 * min(psi_A, psi_B), 1.0)
    k_braced = min(k_br1, k_br2)

    if psi_m < 2.0:
        k_unbraced = (20.0 - psi_m) / 20.0 * math.sqrt(1.0 + psi_m)
    else:
        k_unbraced = 0.9 * math.sqrt(1.0 + psi_m)

    k = k_braced if kondisi == "Braced" else k_unbraced
    r = 0.3 * h
    kLu = k * Lu
    rasio = kLu / r

    if kondisi == "Braced":
        batas = 34.0 - 12.0 * (M1 / M2) if abs(M2) > 0 else 34.0
    else:
        batas = 22.0

    klasifikasi = "Short Column" if rasio <= batas else "Slender Column"
    return {
        "k_braced": k_braced, "k_unbraced": k_unbraced,
        "k": k, "psi_m": psi_m,
        "r": r, "kLu": kLu, "rasio": rasio,
        "batas": batas, "klasifikasi": klasifikasi
    }


def hitung_pembesaran(fc, Ig, k, Lu, Pu, M2, M1, beta_dns):
    Ec = 4700.0 * math.sqrt(fc)
    EI_eff = (0.4 * Ec * Ig) / (1.0 + beta_dns)
    kLu = k * Lu
    Pc = (math.pi**2 * EI_eff) / (kLu**2) / 1000.0  # kN
    Cm = max(0.6 + 0.4 * (M1 / M2), 0.4) if abs(M2) > 0 else 1.0
    denom = 1.0 - Pu / (0.75 * Pc)
    if denom <= 0:
        denom = 1e-6
    delta_ns = max(Cm / denom, 1.0)
    Mc = delta_ns * abs(M2)
    return {
        "Ec": Ec, "EI_eff": EI_eff, "Pc": Pc,
        "Cm": Cm, "beta_dns": beta_dns,
        "delta_ns": delta_ns, "Mc": Mc
    }


def susun_layers(h, d_prime, n_b, n_h, D):
    """3 layer tulangan: tekan, tengah, tarik."""
    A_bar = math.pi * D**2 / 4.0
    n_layer1 = n_b
    n_layer2 = 2 * (n_h - 2)
    n_layer3 = n_b
    return [
        {"nama": "Layer 1 (Tekan)",  "yi": d_prime,       "n": n_layer1, "A": n_layer1 * A_bar},
        {"nama": "Layer 2 (Tengah)", "yi": h / 2.0,       "n": n_layer2, "A": n_layer2 * A_bar},
        {"nama": "Layer 3 (Tarik)",  "yi": h - d_prime,   "n": n_layer3, "A": n_layer3 * A_bar},
    ]


def phi_dinamis(eps_t, eps_y):
    if eps_t >= 0.005:
        return 0.90
    elif eps_t <= eps_y:
        return 0.65
    else:
        return 0.65 + (eps_t - eps_y) / (0.005 - eps_y) * 0.25


def hitung_diagram_interaksi(b, h, fc, fy, Es, layers, n_titik=50):
    """
    Hitung 50 titik c/h + titik 51 (tekan murni) + titik 52 (tarik murni).
    Acuan: SNI 2847:2019.
    Mn dihitung terhadap TITIK TENGAH penampang.
    """
    eps_cu = 0.003
    eps_y  = fy / Es

    # beta1
    if fc <= 28.0:
        beta1 = 0.85
    else:
        beta1 = max(0.85 - 0.05 * (fc - 28.0) / 7.0, 0.65)

    Ag  = b * h
    Ast = sum(lyr["A"] for lyr in layers)

    hasil = []
    ch_values = np.linspace(0.02, 1.20, n_titik)

    for i, ch in enumerate(ch_values):
        c = ch * h
        a = min(beta1 * c, h)

        # Gaya beton (tekan positif)
        Cc = 0.85 * fc * b * a / 1000.0  # kN
        # Lengan Cc terhadap tengah penampang
        arm_Cc = h / 2.0 - a / 2.0       # mm

        # Tulangan
        Psteel = 0.0
        Msteel = 0.0
        for lyr in layers:
            yi   = lyr["yi"]
            Ai   = lyr["A"]
            # Regangan tulangan
            eps_si = eps_cu * (c - yi) / c
            # Tegangan (dibatasi fy)
            fs_i   = max(min(eps_si * Es, fy), -fy)
            # Net: kurangi tegangan beton pada zona tekan
            if yi <= a:
                fs_net = fs_i - 0.85 * fc
            else:
                fs_net = fs_i
            Fi = fs_net * Ai / 1000.0     # kN
            Psteel += Fi
            # Lengan terhadap tengah penampang (positif ke atas)
            arm_i = h / 2.0 - yi         # mm
            Msteel += Fi * arm_i / 1000.0  # kN.m

        Pn = Cc + Psteel                  # kN  (+ = tekan)
        Mn = Cc * arm_Cc / 1000.0 + Msteel   # kN.m (selalu positif sisi tekan)
        Mn = abs(Mn)

        # Regangan tarik terluar (layer 3)
        d_tarik = layers[-1]["yi"]
        eps_t   = eps_cu * (d_tarik - c) / c

        phi    = phi_dinamis(eps_t, eps_y)
        phi_Pn = phi * Pn
        phi_Mn = phi * Mn

        hasil.append({
            "No":     i + 1,
            "c/h":    round(ch, 4),
            "c":      round(c, 2),
            "a":      round(a, 2),
            "eps_t":  round(eps_t, 5),
            "Pn":     round(Pn, 2),
            "Mn":     round(Mn, 2),
            "phi":    round(phi, 2),
            "phi_Pn": round(phi_Pn, 2),
            "phi_Mn": round(phi_Mn, 2),
        })

    # Titik 51: Tekan Murni (Po)
    Po = (0.85 * fc * (Ag - Ast) + fy * Ast) / 1000.0
    phi_51 = 0.65
    hasil.append({
        "No": 51, "c/h": "inf", "c": "inf", "a": "-", "eps_t": "-",
        "Pn": round(Po, 2), "Mn": 0,
        "phi": phi_51, "phi_Pn": round(phi_51 * Po, 2), "phi_Mn": 0,
    })

    # Titik 52: Tarik Murni (To)
    To = -fy * Ast / 1000.0
    phi_52 = 0.90
    hasil.append({
        "No": 52, "c/h": 0.0, "c": 0, "a": "-", "eps_t": "-",
        "Pn": round(To, 2), "Mn": 0,
        "phi": phi_52, "phi_Pn": round(phi_52 * To, 2), "phi_Mn": 0,
    })

    return hasil, beta1, eps_y


def data_grafik(hasil_interaksi):
    """Kembalikan list (phi_Mn, phi_Pn) untuk plotting - urut dari tekan murni ke tarik murni."""
    pts = []
    for row in hasil_interaksi:
        try:
            pts.append((float(row["phi_Mn"]), float(row["phi_Pn"])))
        except Exception:
            pass
    # Urut berdasarkan phi_Pn descending (dari atas ke bawah)
    pts.sort(key=lambda x: -x[1])
    return pts


def cek_kapasitas(hasil_interaksi, Pu, Mu):
    """
    Cek apakah (Pu, Mu) berada di dalam kurva interaksi.
    Menggunakan metode: titik di dalam polygon tertutup kurva interaksi.
    Juga hitung phi_Pn_kap dan phi_Mn_kap via interpolasi.
    """
    # Kumpulkan titik numerik kurva
    pts = []
    for row in hasil_interaksi:
        try:
            pts.append((float(row["phi_Mn"]), float(row["phi_Pn"])))
        except Exception:
            pass

    if not pts:
        return {"phi_Pn_kapasitas": None, "phi_Mn_kapasitas": None,
                "ratio_Pu": None, "ratio_Mu": None, "status": "ERROR"}

    # --- Cari phi_Mn_kapasitas saat phi_Pn = Pu ---
    # Kelompokkan titik berdasarkan phi_Pn naik
    pts_by_pn = sorted(pts, key=lambda x: x[1])  # urut phi_Pn ascending
    phi_Mn_kap = None
    # Cari interval phi_Pn yang mengapit Pu, ambil phi_Mn maksimum di sekitar itu
    # Metode lebih robust: untuk setiap level Pu, cari phi_Mn pada kurva
    # Kurva interaksi punya dua sisi: sisi kanan (phi_Mn naik s/d max) dan sisi kiri (phi_Mn turun)
    # Kita cari semua pasangan (phi_Mn, phi_Pn) yang phi_Pn mengapit Pu
    candidates_Mn = []
    for j in range(len(pts_by_pn) - 1):
        p1n, p1p = pts_by_pn[j][0], pts_by_pn[j][1]
        p2n, p2p = pts_by_pn[j+1][0], pts_by_pn[j+1][1]
        if min(p1p, p2p) <= Pu <= max(p1p, p2p):
            if abs(p2p - p1p) > 1e-9:
                t = (Pu - p1p) / (p2p - p1p)
                mn_interp = p1n + t * (p2n - p1n)
                candidates_Mn.append(mn_interp)
    phi_Mn_kap = max(candidates_Mn) if candidates_Mn else None

    # --- Cari phi_Pn_kapasitas saat phi_Mn = Mu ---
    pts_by_mn = sorted(pts, key=lambda x: x[0])  # urut phi_Mn ascending
    candidates_Pn = []
    for j in range(len(pts_by_mn) - 1):
        p1n, p1p = pts_by_mn[j][0], pts_by_mn[j][1]
        p2n, p2p = pts_by_mn[j+1][0], pts_by_mn[j+1][1]
        if min(p1n, p2n) <= Mu <= max(p1n, p2n):
            if abs(p2n - p1n) > 1e-9:
                t = (Mu - p1n) / (p2n - p1n)
                pn_interp = p1p + t * (p2p - p1p)
                candidates_Pn.append(pn_interp)
    # Ambil nilai phi_Pn kapasitas yang relevan (terbesar yang masih di sisi tekan > Pu)
    phi_Pn_kap = max(candidates_Pn) if candidates_Pn else None

    # --- Hitung rasio ---
    ratio_Pu = (Pu / phi_Pn_kap) if (phi_Pn_kap and abs(phi_Pn_kap) > 1e-6) else None
    ratio_Mu = (Mu / phi_Mn_kap) if (phi_Mn_kap and abs(phi_Mn_kap) > 1e-6) else None

    # --- Status ---
    ok_Pu = (ratio_Pu is None) or (ratio_Pu <= 1.0)
    ok_Mu = (ratio_Mu is None) or (ratio_Mu <= 1.0)
    status = "OK - AMAN" if (ok_Pu and ok_Mu) else "NOT OK - TIDAK AMAN"

    return {
        "phi_Pn_kapasitas": phi_Pn_kap,
        "phi_Mn_kapasitas": phi_Mn_kap,
        "ratio_Pu": ratio_Pu,
        "ratio_Mu": ratio_Mu,
        "status": status,
    }


# ============================================================
# BAGIAN 2: UI STREAMLIT
# ============================================================

st.set_page_config(
    page_title="Kolom Beton Bertulang | SNI 2847:2019",
    page_icon="🏛️",
    layout="wide",
)

st.title("🏛️ Perhitungan Kapasitas Kolom Beton Bertulang")
st.markdown("**Diagram Interaksi P-M | SNI 2847:2019** | Dibuat oleh: Ladosi")
st.divider()

# ---- SIDEBAR ----
with st.sidebar:
    st.header("📋 Data Input")

    st.subheader("1. Material")
    fc    = st.number_input("Mutu Beton fc' (MPa)", value=30.0,     step=1.0,    min_value=17.0)
    fy    = st.number_input("Mutu Baja fy (MPa)",   value=400.0,    step=10.0,   min_value=200.0)
    Es    = st.number_input("Modulus Baja Es (MPa)", value=200000.0, step=1000.0, min_value=100000.0)

    st.subheader("2. Dimensi Kolom")
    b      = st.number_input("Lebar b (mm)",          value=400.0, step=10.0, min_value=100.0)
    h      = st.number_input("Tinggi h (mm)",          value=500.0, step=10.0, min_value=100.0)
    c_sel  = st.number_input("Selimut Beton c (mm)",   value=40.0,  step=5.0,  min_value=20.0)
    dia_s  = st.number_input("Diameter Sengkang Øs (mm)", value=10.0, step=2.0, min_value=6.0)

    st.subheader("3. Tulangan Longitudinal")
    D   = st.number_input("Diameter Tulangan D (mm)", value=22.0, step=2.0,  min_value=10.0)
    n_b = st.number_input("Tulangan Sisi b (n_b)",    value=4,    step=1,    min_value=2)
    n_h = st.number_input("Tulangan Sisi h (n_h, incl. sudut)", value=3, step=1, min_value=2)

    st.subheader("4. Panjang & Kondisi Rangka")
    Lu             = st.number_input("Panjang Tak Tertahan Lu (mm)", value=6000.0, step=100.0, min_value=500.0)
    kondisi_rangka = st.selectbox("Kondisi Rangka", ["Braced", "Unbraced"])
    kelengkungan   = st.selectbox("Kelengkungan", ["Single", "Double"])

    st.subheader("5. Kekakuan Elemen Penghubung")
    st.markdown("**Balok Atas** *(0 jika tidak ada)*")
    bb_al = st.number_input("Bal. Atas-Kiri b (mm)",  value=300.0, key="bbal_b")
    hb_al = st.number_input("Bal. Atas-Kiri h (mm)",  value=500.0, key="bbal_h")
    Lb_al = st.number_input("Bal. Atas-Kiri L (mm)",  value=6000.0, key="bbal_L")
    bb_ar = st.number_input("Bal. Atas-Kanan b (mm)", value=300.0, key="bbar_b")
    hb_ar = st.number_input("Bal. Atas-Kanan h (mm)", value=500.0, key="bbar_h")
    Lb_ar = st.number_input("Bal. Atas-Kanan L (mm)", value=6000.0, key="bbar_L")

    st.markdown("**Kolom Atas** *(L=0 jika lantai atap)*")
    bk_a = st.number_input("Kol. Atas b (mm)", value=400.0, key="ka_b")
    hk_a = st.number_input("Kol. Atas h (mm)", value=500.0, key="ka_h")
    Lk_a = st.number_input("Kol. Atas L (mm) [0=tidak ada]", value=3500.0, key="ka_L")

    st.markdown("**Balok Bawah** *(0 jika tidak ada)*")
    bb_bl = st.number_input("Bal. Bawah-Kiri b (mm)",  value=300.0, key="bbbl_b")
    hb_bl = st.number_input("Bal. Bawah-Kiri h (mm)",  value=500.0, key="bbbl_h")
    Lb_bl = st.number_input("Bal. Bawah-Kiri L (mm)",  value=6000.0, key="bbbl_L")
    bb_br = st.number_input("Bal. Bawah-Kanan b (mm)", value=300.0, key="bbbr_b")
    hb_br = st.number_input("Bal. Bawah-Kanan h (mm)", value=500.0, key="bbbr_h")
    Lb_br = st.number_input("Bal. Bawah-Kanan L (mm)", value=6000.0, key="bbbr_L")

    st.markdown("**Kolom Bawah** *(L=0 jika langsung pondasi)*")
    bk_b = st.number_input("Kol. Bawah b (mm)", value=400.0, key="kb_b")
    hk_b = st.number_input("Kol. Bawah h (mm)", value=500.0, key="kb_h")
    Lk_b = st.number_input("Kol. Bawah L (mm) [0=pondasi]", value=3500.0, key="kb_L")
    st.caption("ℹ️ Kolom bawah L=0 → ΨB = 0 (jepit di pondasi)")

    st.subheader("6. Beban Terfaktor")
    Pu  = st.number_input("Gaya Aksial Pu (kN)",             value=1500.0, step=10.0)
    M1  = st.number_input("Momen Ujung 1 M1 (kN.m) - lebih kecil", value=80.0, step=5.0)
    M2  = st.number_input("Momen Ujung 2 M2 (kN.m) - lebih besar", value=150.0, step=5.0, min_value=0.1)

    st.subheader("7. Faktor Tambahan")
    beta_dns = st.number_input("βdns (rasio beban tetap/total)", value=0.60, step=0.05,
                               min_value=0.0, max_value=1.0)

    st.divider()
    btn_hitung = st.button("🔴 HITUNG SEKARANG", use_container_width=True, type="primary")


# ============================================================
# PROSES KALKULASI
# ============================================================

if btn_hitung:
    # Tanda M1: Double curvature = berlawanan arah (positif), Single = searah (negatif untuk rumus Cm)
    M1_signed = M1 if kelengkungan == "Double" else -M1

    props = hitung_properties(b, h, c_sel, dia_s, D, n_b, n_h, fc, fy, Es)

    kekakuan = hitung_kekakuan_elemen(
        fc,
        bb_al, hb_al, Lb_al,
        bb_ar, hb_ar, Lb_ar,
        bk_a,  hk_a,  Lk_a,
        bb_bl, hb_bl, Lb_bl,
        bb_br, hb_br, Lb_br,
        bk_b,  hk_b,  Lk_b,
        b,     h,     Lu,
    )

    kelangsingan = hitung_k_kelangsingan(
        kekakuan["psi_A"], kekakuan["psi_B"],
        kondisi_rangka, Lu, h, M1_signed, M2,
    )

    pembesaran = hitung_pembesaran(
        fc, props["Ig"], kelangsingan["k"],
        Lu, Pu, M2, M1_signed, beta_dns,
    )

    is_slender = (kelangsingan["klasifikasi"] == "Slender Column")
    Mu_desain  = pembesaran["Mc"] if (is_slender and kondisi_rangka == "Braced") else abs(M2)

    layers = susun_layers(h, props["d_prime"], n_b, n_h, D)

    hasil_interaksi, beta1, eps_y = hitung_diagram_interaksi(b, h, fc, fy, Es, layers)

    cek = cek_kapasitas(hasil_interaksi, Pu, Mu_desain)

    st.session_state["R"] = {
        "props":           props,
        "kekakuan":        kekakuan,
        "kelangsingan":    kelangsingan,
        "pembesaran":      pembesaran,
        "layers":          layers,
        "hasil_interaksi": hasil_interaksi,
        "cek":             cek,
        "beta1":           beta1,
        "eps_y":           eps_y,
        "Mu_desain":       Mu_desain,
        "is_slender":      is_slender,
        "inp": {
            "fc": fc, "fy": fy, "Es": Es,
            "b": b, "h": h, "c_sel": c_sel, "dia_s": dia_s,
            "D": D, "n_b": n_b, "n_h": n_h,
            "Lu": Lu, "kondisi_rangka": kondisi_rangka, "kelengkungan": kelengkungan,
            "Pu": Pu, "M1": M1, "M2": M2, "beta_dns": beta_dns,
            # Elemen kekakuan
            "bb_al": bb_al, "hb_al": hb_al, "Lb_al": Lb_al,
            "bb_ar": bb_ar, "hb_ar": hb_ar, "Lb_ar": Lb_ar,
            "bk_a":  bk_a,  "hk_a":  hk_a,  "Lk_a":  Lk_a,
            "bb_bl": bb_bl, "hb_bl": hb_bl, "Lb_bl": Lb_bl,
            "bb_br": bb_br, "hb_br": hb_br, "Lb_br": Lb_br,
            "bk_b":  bk_b,  "hk_b":  hk_b,  "Lk_b":  Lk_b,
        },
    }


# ============================================================
# TAMPILKAN HASIL
# ============================================================

if "R" not in st.session_state:
    st.info("👈 Isi data input di sidebar, lalu klik **HITUNG SEKARANG**")
    st.stop()

R            = st.session_state["R"]
props        = R["props"]
kekakuan     = R["kekakuan"]
kelangsingan = R["kelangsingan"]
pembesaran   = R["pembesaran"]
layers       = R["layers"]
hasil_interaksi = R["hasil_interaksi"]
cek          = R["cek"]
beta1        = R["beta1"]
eps_y        = R["eps_y"]
Mu_desain    = R["Mu_desain"]
is_slender   = R["is_slender"]
inp          = R["inp"]

# --- STATUS BANNER ---
is_ok = ("NOT" not in cek["status"])
banner_color = "#1a7a1a" if is_ok else "#c0392b"
st.markdown(
    f'<div style="background:{banner_color};padding:16px;border-radius:10px;text-align:center;">'
    f'<h2 style="color:white;margin:0;">🏛️ {cek["status"]}</h2></div>',
    unsafe_allow_html=True,
)
st.write("")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📐 Properties", "📏 Kelangsingan", "📈 Diagram Interaksi",
    "✅ Cek Kapasitas", "📄 Laporan",
])


# ============================================================
# TAB 1: PROPERTIES
# ============================================================
with tab1:
    st.subheader("7. Properti Penampang (SNI 2847:2019 Pasal 19.2.2)")
    col_a, col_b = st.columns(2)

    with col_a:
        df_p = pd.DataFrame({
            "Parameter": ["Ag", "Ig", "Ec", "d'", "d", "n_total", "Ast", "ρg"],
            "Rumus": [
                "b × h",
                "(1/12) × b × h³",
                "4700 × √fc'",
                "c + Øs + D/2",
                "h - d'",
                "2×n_b + 2×(n_h-2)",
                "n_total × π × D²/4",
                "Ast/Ag × 100",
            ],
            "Nilai": [
                f"{props['Ag']:,.2f}",
                f"{props['Ig']:,.2f}",
                f"{props['Ec']:,.2f}",
                f"{props['d_prime']:.2f}",
                f"{props['d']:.2f}",
                f"{props['n_total']}",
                f"{props['Ast']:,.2f}",
                f"{props['rho_g']:.2f}",
            ],
            "Satuan": ["mm²", "mm⁴", "MPa", "mm", "mm", "bh", "mm²", "%"],
        })
        st.dataframe(df_p, use_container_width=True, hide_index=True)

        cek_color = "green" if props["cek_rasio"] == "OK" else "red"
        st.markdown(
            f"**Cek Rasio Tulangan (SNI Ps.10.6.1):** "
            f"1% ≤ ρg = **{props['rho_g']:.2f}%** ≤ 8% → "
            f"<span style='color:{cek_color};font-weight:bold;'>{props['cek_rasio']}</span>",
            unsafe_allow_html=True,
        )

    with col_b:
        st.code(
            f"Ag  = {inp['b']:.0f} × {inp['h']:.0f}\n"
            f"    = {props['Ag']:,.2f} mm²\n\n"
            f"Ig  = (1/12) × {inp['b']:.0f} × {inp['h']:.0f}³\n"
            f"    = {props['Ig']:,.2f} mm⁴\n\n"
            f"Ec  = 4700 × √{inp['fc']:.0f}\n"
            f"    = {props['Ec']:,.2f} MPa\n\n"
            f"d'  = {inp['c_sel']:.0f} + {inp['dia_s']:.0f} + {inp['D']:.0f}/2\n"
            f"    = {props['d_prime']:.2f} mm\n\n"
            f"d   = {inp['h']:.0f} - {props['d_prime']:.2f}\n"
            f"    = {props['d']:.2f} mm\n\n"
            f"n   = 2×{inp['n_b']} + 2×({inp['n_h']}-2) = {props['n_total']} bh\n\n"
            f"Ast = {props['n_total']} × π × {inp['D']:.0f}²/4\n"
            f"    = {props['Ast']:,.2f} mm²\n\n"
            f"ρg  = {props['Ast']:.2f}/{props['Ag']:.2f} × 100\n"
            f"    = {props['rho_g']:.2f}%  → {props['cek_rasio']}",
            language="text",
        )

    st.divider()
    st.subheader("9. Kekakuan Elemen (EI/L) — SNI 2847:2019 Pasal 6.6.3")
    df_kek = pd.DataFrame({
        "Elemen": [
            "Balok Atas - Kiri", "Balok Atas - Kanan", "Kolom Atas",
            "Balok Bawah - Kiri", "Balok Bawah - Kanan", "Kolom Bawah",
            "Kolom Ditinjau",
        ],
        "b (mm)": [inp["bb_al"], inp["bb_ar"], inp["bk_a"],
                   inp["bb_bl"], inp["bb_br"], inp["bk_b"], inp["b"]],
        "h (mm)": [inp["hb_al"], inp["hb_ar"], inp["hk_a"],
                   inp["hb_bl"], inp["hb_br"], inp["hk_b"], inp["h"]],
        "L (mm)": [inp["Lb_al"], inp["Lb_ar"], inp["Lk_a"],
                   inp["Lb_bl"], inp["Lb_br"], inp["Lk_b"], inp["Lu"]],
        "EI/L (N.mm)": [
            f"{kekakuan['bal_atas_kiri']:,.2f}",
            f"{kekakuan['bal_atas_kanan']:,.2f}",
            f"{kekakuan['kol_atas']:,.2f}",
            f"{kekakuan['bal_bawah_kiri']:,.2f}",
            f"{kekakuan['bal_bawah_kanan']:,.2f}",
            f"{kekakuan['kol_bawah']:,.2f}",
            f"{kekakuan['kol_ditinjau']:,.2f}",
        ],
    })
    st.dataframe(df_kek, use_container_width=True, hide_index=True)


# ============================================================
# TAB 2: KELANGSINGAN
# ============================================================
with tab2:
    st.subheader("10. Faktor Ψ (Psi) — SNI 2847:2019 Pasal 6.6.4.4")
    col_a, col_b = st.columns(2)
    with col_a:
        df_psi = pd.DataFrame({
            "Parameter": [
                "Σ(EI/L) Kolom Atas", "Σ(EI/L) Balok Atas", "ΨA",
                "Σ(EI/L) Kolom Bawah", "Σ(EI/L) Balok Bawah", "ΨB", "Ψm",
            ],
            "Nilai": [
                f"{kekakuan['sum_kol_atas']:,.2f}",
                f"{kekakuan['sum_bal_atas']:,.2f}",
                f"{kekakuan['psi_A']:.4f}",
                f"{kekakuan['sum_kol_bawah']:,.2f}",
                f"{kekakuan['sum_bal_bawah']:,.2f}",
                f"{kekakuan['psi_B']:.4f}",
                f"{kelangsingan['psi_m']:.4f}",
            ],
            "Satuan": ["N.mm", "N.mm", "-", "N.mm", "N.mm", "-", "-"],
        })
        st.dataframe(df_psi, use_container_width=True, hide_index=True)

    with col_b:
        st.code(
            f"ΨA = Σ(EI/L)kolom / Σ(EI/L)balok\n"
            f"   = {kekakuan['sum_kol_atas']:,.2f}\n"
            f"     / {kekakuan['sum_bal_atas']:,.2f}\n"
            f"   = {kekakuan['psi_A']:.4f}\n\n"
            f"ΨB = {kekakuan['sum_kol_bawah']:,.2f}\n"
            f"     / {kekakuan['sum_bal_bawah']:,.2f}\n"
            f"   = {kekakuan['psi_B']:.4f}\n\n"
            f"Ψm = (ΨA + ΨB) / 2\n"
            f"   = ({kekakuan['psi_A']:.4f} + {kekakuan['psi_B']:.4f}) / 2\n"
            f"   = {kelangsingan['psi_m']:.4f}",
            language="text",
        )

    st.divider()
    st.subheader("11 & 12. Faktor k dan Cek Kelangsingan — SNI 2847:2019 Pasal 6.6.4.4 & 6.2.5")
    col_a, col_b = st.columns(2)
    with col_a:
        df_k = pd.DataFrame({
            "Parameter": [
                "k (Braced)", "k (Unbraced)", "k Dipakai",
                "r = 0.3h", "k×Lu", "k×Lu/r",
                "Batas Kelangsingan", "Klasifikasi",
            ],
            "Nilai": [
                f"{kelangsingan['k_braced']:.6f}",
                f"{kelangsingan['k_unbraced']:.6f}",
                f"{kelangsingan['k']:.6f}",
                f"{kelangsingan['r']:.2f} mm",
                f"{kelangsingan['kLu']:.2f} mm",
                f"{kelangsingan['rasio']:.2f}",
                f"{kelangsingan['batas']:.2f}",
                kelangsingan["klasifikasi"],
            ],
        })
        st.dataframe(df_k, use_container_width=True, hide_index=True)

    with col_b:
        st.code(
            f"k_Braced  = min(\n"
            f"  0.7 + 0.05(ΨA+ΨB) = {0.7+0.05*(kekakuan['psi_A']+kekakuan['psi_B']):.4f} → ≤1.0\n"
            f"  0.85 + 0.05×Ψmin  = {0.85+0.05*min(kekakuan['psi_A'],kekakuan['psi_B']):.4f} → ≤1.0\n"
            f") = {kelangsingan['k_braced']:.6f}\n\n"
            f"r   = 0.3 × {inp['h']:.0f} = {kelangsingan['r']:.2f} mm\n\n"
            f"k×Lu = {kelangsingan['k']:.6f} × {inp['Lu']:.0f}\n"
            f"     = {kelangsingan['kLu']:.2f} mm\n\n"
            f"k×Lu/r = {kelangsingan['kLu']:.2f} / {kelangsingan['r']:.2f}\n"
            f"       = {kelangsingan['rasio']:.2f}\n\n"
            f"Batas ({inp['kondisi_rangka']}) = {kelangsingan['batas']:.2f}\n"
            f"→ {kelangsingan['klasifikasi']}",
            language="text",
        )

    st.divider()
    st.subheader("13. Pembesaran Momen — SNI 2847:2019 Pasal 6.6.4")
    if is_slender and inp["kondisi_rangka"] == "Braced":
        col_a, col_b = st.columns(2)
        with col_a:
            df_pem = pd.DataFrame({
                "Parameter": ["(EI)eff", "Pc", "Cm", "βdns", "δns", "Mc"],
                "Nilai": [
                    f"{pembesaran['EI_eff']:,.2f}",
                    f"{pembesaran['Pc']:,.2f}",
                    f"{pembesaran['Cm']:.4f}",
                    f"{pembesaran['beta_dns']:.2f}",
                    f"{pembesaran['delta_ns']:.4f}",
                    f"{pembesaran['Mc']:,.4f}",
                ],
                "Satuan": ["N.mm²", "kN", "-", "-", "-", "kN.m"],
                "Referensi SNI": [
                    "Pers. 6.6.4.4.4", "Pers. 6.6.4.4.2",
                    "Pers. 6.6.4.5.3", "-",
                    "Pers. 6.6.4.5.2", "Mc = δns×M2",
                ],
            })
            st.dataframe(df_pem, use_container_width=True, hide_index=True)
        with col_b:
            st.code(
                f"(EI)eff = 0.4×Ec×Ig / (1+βdns)\n"
                f"        = 0.4×{pembesaran['Ec']:,.0f}×{props['Ig']:,.0f}\n"
                f"          / (1+{pembesaran['beta_dns']:.2f})\n"
                f"        = {pembesaran['EI_eff']:,.2f} N.mm²\n\n"
                f"Pc      = π²×(EI)eff / (k×Lu)²\n"
                f"        = {pembesaran['Pc']:,.2f} kN\n\n"
                f"Cm      = 0.6 + 0.4×(M1/M2)\n"
                f"        = 0.6 + 0.4×({inp['M1']:.0f}/{inp['M2']:.0f})\n"
                f"        = {pembesaran['Cm']:.4f}  [≥0.4]\n\n"
                f"δns     = Cm / (1 - Pu/(0.75×Pc))\n"
                f"        = {pembesaran['Cm']:.4f} / (1 - {inp['Pu']:.0f}/(0.75×{pembesaran['Pc']:.2f}))\n"
                f"        = {pembesaran['delta_ns']:.4f}  [≥1.0]\n\n"
                f"Mc      = δns × M2\n"
                f"        = {pembesaran['delta_ns']:.4f} × {inp['M2']:.0f}\n"
                f"        = {pembesaran['Mc']:,.4f} kN.m",
                language="text",
            )
    else:
        st.info(
            f"**Short Column** → Tidak perlu pembesaran momen.\n\n"
            f"Momen Desain Mu = M2 = **{abs(inp['M2']):.2f} kN.m**"
        )


# ============================================================
# TAB 3: DIAGRAM INTERAKSI
# ============================================================
with tab3:
    st.subheader("14 & 15. Parameter & Layer Tulangan")
    col_a, col_b = st.columns(2)

    with col_a:
        df_layer = pd.DataFrame({
            "Layer": [lyr["nama"] for lyr in layers],
            "yi dari tepi tekan (mm)": [lyr["yi"] for lyr in layers],
            "Jarak dari tengah (mm)": [round(lyr["yi"] - h/2, 2) for lyr in layers],
            "Jumlah (bh)": [lyr["n"] for lyr in layers],
            "Luas (mm²)": [f"{lyr['A']:,.2f}" for lyr in layers],
        })
        st.dataframe(df_layer, use_container_width=True, hide_index=True)

    with col_b:
        st.info(
            f"**β1** = {beta1:.6f}  (fc'={inp['fc']} MPa)\n\n"
            f"**εcu** = 0.003  (SNI 2847:2019 Ps. 22.2.2.1)\n\n"
            f"**εy** = fy/Es = {inp['fy']:.0f}/{inp['Es']:.0f} = {eps_y:.4f}\n\n"
            f"**d'** = {props['d_prime']:.2f} mm  |  **d** = {props['d']:.2f} mm\n\n"
            f"**Momen Desain Mu** = {Mu_desain:.4f} kN.m"
        )

    st.divider()
    st.subheader("16. Tabel Diagram Interaksi P-M (52 Titik) — SNI 2847:2019")
    df_int = pd.DataFrame(hasil_interaksi)
    st.dataframe(df_int, use_container_width=True, hide_index=True, height=500)

    st.divider()
    st.subheader("20. Diagram Interaksi P-M (φPn vs φMn)")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pts = data_grafik(hasil_interaksi)
    phi_Mn_k = [p[0] for p in pts]
    phi_Pn_k = [p[1] for p in pts]

    fig, ax = plt.subplots(figsize=(9, 8))
    ax.plot(phi_Mn_k, phi_Pn_k, "b-o", lw=2, ms=3, label="Kurva φPn-φMn")
    ax.plot(
        Mu_desain, inp["Pu"], "r*", ms=14,
        label=f"Beban Aktual (Mu={Mu_desain:.2f} kN.m, Pu={inp['Pu']:.0f} kN)",
    )
    ax.axhline(0, color="k", lw=0.7, ls="--")
    ax.axvline(0, color="k", lw=0.7, ls="--")
    ax.set_xlabel("φMn (kN.m)", fontsize=12)
    ax.set_ylabel("φPn (kN)", fontsize=12)
    ax.set_title("DIAGRAM INTERAKSI P-M\nSNI 2847:2019", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)

    stxt_color = "green" if is_ok else "red"
    ax.annotate(
        cek["status"],
        xy=(Mu_desain, inp["Pu"]),
        xytext=(Mu_desain + 5, inp["Pu"] + 150),
        fontsize=11, color=stxt_color, fontweight="bold",
        arrowprops=dict(arrowstyle="->", color=stxt_color),
    )
    st.pyplot(fig)
    plt.close()


# ============================================================
# TAB 4: CEK KAPASITAS
# ============================================================
with tab4:
    st.subheader("19. Ringkasan & Cek Kapasitas — SNI 2847:2019")

    def fmt_val(v, decimals=2):
        if v is None:
            return "-"
        return f"{v:.{decimals}f}"

    ratio_Pu_val = cek["ratio_Pu"]
    ratio_Mu_val = cek["ratio_Mu"]
    phi_Pn_kap   = cek["phi_Pn_kapasitas"]
    phi_Mn_kap   = cek["phi_Mn_kapasitas"]

    ok_pn = "-" if ratio_Pu_val is None else ("OK" if ratio_Pu_val <= 1.0 else "NOT OK")
    ok_mn = "-" if ratio_Mu_val is None else ("OK" if ratio_Mu_val <= 1.0 else "NOT OK")

    df_cek = pd.DataFrame({
        "Parameter": [
            "Klasifikasi Kolom",
            "Gaya Aksial (Pu)",
            "Momen Desain (Mc/M2)",
            "φPn Kapasitas (pada Mu=Mc)",
            "φMn Kapasitas (pada Pu)",
            "Rasio Pu / φPn",
            "Rasio Mu / φMn",
            "STATUS AKHIR",
        ],
        "Nilai": [
            kelangsingan["klasifikasi"],
            f"{inp['Pu']:.2f}",
            f"{Mu_desain:.4f}",
            fmt_val(phi_Pn_kap),
            fmt_val(phi_Mn_kap),
            fmt_val(ratio_Pu_val),
            fmt_val(ratio_Mu_val),
            cek["status"],
        ],
        "Satuan": ["-", "kN", "kN.m", "kN", "kN.m", "-", "-", "-"],
        "Status": ["-", "OK", "OK", "-", "-", ok_pn, ok_mn, cek["status"]],
    })
    st.dataframe(df_cek, use_container_width=True, hide_index=True)

    st.write("")
    if is_ok:
        pn_txt = f"φPn = {phi_Pn_kap:.2f} kN" if phi_Pn_kap else "φPn = (kurva di sisi tarik)"
        mn_txt = f"φMn = {phi_Mn_kap:.2f} kN.m" if phi_Mn_kap else "φMn = tidak terhitung"
        st.success(
            f"### ✅ {cek['status']}\n\n"
            f"Titik beban **(Pu={inp['Pu']:.0f} kN, Mu={Mu_desain:.2f} kN.m)** "
            f"berada **DI DALAM** kurva interaksi φPn-φMn.\n\n"
            f"- Pu = {inp['Pu']:.0f} kN  |  {pn_txt}\n"
            f"- Mu = {Mu_desain:.2f} kN.m  |  {mn_txt}"
        )
    else:
        st.error(
            f"### ❌ {cek['status']}\n\n"
            f"Titik beban berada **DI LUAR** kurva interaksi.\n\n"
            f"Perlu revisi: perbesar dimensi atau tambah tulangan!"
        )


# ============================================================
# TAB 5: LAPORAN
# ============================================================
with tab5:
    st.subheader("📄 Generator Laporan Profesional")
    nama_eng = st.text_input("Nama Engineer", value="Ladosi")
    nama_prj = st.text_input("Nama Proyek", value="Perhitungan Kolom Beton Bertulang")
    tgl_lpr  = st.text_input("Tanggal Laporan", value="2025")

    col_w, col_p = st.columns(2)
    with col_w:
        if st.button("📄 Buat Laporan Word", use_container_width=True):
            try:
                docx_bytes = buat_word(R, nama_eng, nama_prj, tgl_lpr, Mu_desain)
                st.download_button(
                    "⬇️ Download Word (.docx)",
                    data=docx_bytes,
                    file_name="laporan_kolom.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
            except Exception as ex:
                st.error(f"Error Word: {ex}")

    with col_p:
        if st.button("📋 Buat Laporan PDF", use_container_width=True):
            try:
                pdf_bytes = buat_pdf(R, nama_eng, nama_prj, tgl_lpr, Mu_desain)
                st.download_button(
                    "⬇️ Download PDF (.pdf)",
                    data=pdf_bytes,
                    file_name="laporan_kolom.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            except Exception as ex:
                st.error(f"Error PDF: {ex}")


# ============================================================
# BAGIAN 3: GENERATOR LAPORAN
# ============================================================

@st.cache_data
def buat_word(R, nama_eng, nama_prj, tgl_lpr, Mu_desain):
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    props        = R["props"]
    kekakuan     = R["kekakuan"]
    kelangsingan = R["kelangsingan"]
    pembesaran   = R["pembesaran"]
    layers       = R["layers"]
    hasil_interaksi = R["hasil_interaksi"]
    cek          = R["cek"]
    inp          = R["inp"]
    is_slender   = R["is_slender"]

    doc = Document()
    sec = doc.sections[0]
    sec.page_width    = Cm(21);  sec.page_height  = Cm(29.7)
    sec.left_margin   = Cm(2.5); sec.right_margin = Cm(2)
    sec.top_margin    = Cm(2.5); sec.bottom_margin= Cm(2)

    def heading(txt, lvl=1):
        p = doc.add_heading(txt, level=lvl)
        clr = RGBColor(0, 70, 127)
        for run in p.runs:
            run.font.color.rgb = clr; run.bold = True

    def tbl(headers, rows, col_widths=None):
        t = doc.add_table(rows=1, cols=len(headers))
        t.style = "Table Grid"
        for i, h in enumerate(headers):
            c = t.rows[0].cells[i]
            c.text = h
            for p in c.paragraphs:
                for r in p.runs: r.bold = True; r.font.size = Pt(9)
        for row in rows:
            rc = t.add_row().cells
            for i, val in enumerate(row):
                rc[i].text = str(val)
                for p in rc[i].paragraphs:
                    for r in p.runs: r.font.size = Pt(9)
        return t

    def code_para(txt):
        p = doc.add_paragraph()
        r = p.add_run(txt); r.font.name = "Courier New"; r.font.size = Pt(8.5)

    # -- Cover --
    doc.add_paragraph()
    pt = doc.add_paragraph(); pt.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rt = pt.add_run("LAPORAN PERHITUNGAN STRUKTUR")
    rt.bold = True; rt.font.size = Pt(18); rt.font.color.rgb = RGBColor(0,70,127)
    p2 = doc.add_paragraph(); p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.add_run("KAPASITAS KOLOM BETON BERTULANG — DIAGRAM INTERAKSI P-M").bold = True
    p3 = doc.add_paragraph(); p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p3.add_run("SNI 2847:2019")
    doc.add_paragraph()
    for k, v in [("Proyek", nama_prj), ("Engineer", nama_eng), ("Tanggal", tgl_lpr), ("Standar", "SNI 2847:2019")]:
        pi = doc.add_paragraph(); pi.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pi.add_run(f"{k}: ").bold = True; pi.add_run(v)
    doc.add_page_break()

    # -- BAB 1 --
    heading("BAB 1: DATA INPUT PARAMETER", 1)
    heading("1.1 Material", 2)
    tbl(["Parameter", "Simbol", "Nilai", "Satuan"], [
        ["Mutu Beton",  "fc'", str(inp["fc"]), "MPa"],
        ["Mutu Baja",   "fy",  str(inp["fy"]), "MPa"],
        ["Mod. Elastisitas Baja", "Es", str(inp["Es"]), "MPa"],
    ])
    doc.add_paragraph()
    heading("1.2 Dimensi & Tulangan", 2)
    tbl(["Parameter", "Simbol", "Nilai", "Satuan"], [
        ["Lebar Kolom",          "b",  str(inp["b"]),     "mm"],
        ["Tinggi Kolom",         "h",  str(inp["h"]),     "mm"],
        ["Selimut Beton",        "c",  str(inp["c_sel"]), "mm"],
        ["Dia. Sengkang",        "Os", str(inp["dia_s"]), "mm"],
        ["Dia. Tulangan",        "D",  str(inp["D"]),     "mm"],
        ["Tul. Sisi b",          "n_b",str(inp["n_b"]),   "bh"],
        ["Tul. Sisi h",          "n_h",str(inp["n_h"]),   "bh"],
        ["Total Tulangan",       "nt", str(props["n_total"]), "bh"],
        ["Panjang Tak Tertahan", "Lu", str(inp["Lu"]),    "mm"],
    ])
    doc.add_paragraph()
    heading("1.3 Beban Terfaktor", 2)
    tbl(["Parameter", "Simbol", "Nilai", "Satuan"], [
        ["Gaya Aksial",   "Pu", str(inp["Pu"]), "kN"],
        ["Momen Ujung 1", "M1", str(inp["M1"]), "kN.m"],
        ["Momen Ujung 2", "M2", str(inp["M2"]), "kN.m"],
        ["Momen Desain",  "Mc", f"{Mu_desain:.4f}", "kN.m"],
    ])
    doc.add_page_break()

    # -- BAB 2 --
    heading("BAB 2: PROSES PERHITUNGAN STEP-BY-STEP", 1)
    heading("2.1 Properti Penampang", 2)
    code_para(
        f"Ag  = {inp['b']:.0f} x {inp['h']:.0f} = {props['Ag']:,.2f} mm2\n"
        f"Ig  = (1/12)x{inp['b']:.0f}x{inp['h']:.0f}3 = {props['Ig']:,.2f} mm4\n"
        f"Ec  = 4700 x sqrt({inp['fc']:.0f}) = {props['Ec']:,.2f} MPa\n"
        f"d'  = {inp['c_sel']:.0f}+{inp['dia_s']:.0f}+{inp['D']:.0f}/2 = {props['d_prime']:.2f} mm\n"
        f"d   = {inp['h']:.0f}-{props['d_prime']:.2f} = {props['d']:.2f} mm\n"
        f"nt  = 2x{inp['n_b']}+2x({inp['n_h']}-2) = {props['n_total']} bh\n"
        f"Ast = {props['n_total']}xpix{inp['D']:.0f}2/4 = {props['Ast']:,.2f} mm2\n"
        f"rho = {props['rho_g']:.2f}%  -> {props['cek_rasio']}"
    )
    heading("2.2 Kekakuan & Psi", 2)
    code_para(
        f"EI/L Bal.Atas Kiri  = {kekakuan['bal_atas_kiri']:,.2f} N.mm\n"
        f"EI/L Bal.Atas Kanan = {kekakuan['bal_atas_kanan']:,.2f} N.mm\n"
        f"EI/L Kol.Atas       = {kekakuan['kol_atas']:,.2f} N.mm\n"
        f"EI/L Kol.Ditinjau   = {kekakuan['kol_ditinjau']:,.2f} N.mm\n"
        f"PSI_A = {kekakuan['psi_A']:.4f}\n"
        f"PSI_B = {kekakuan['psi_B']:.4f}\n"
        f"k({inp['kondisi_rangka']}) = {kelangsingan['k']:.6f}\n"
        f"r = 0.3x{inp['h']:.0f} = {kelangsingan['r']:.2f} mm\n"
        f"kLu/r = {kelangsingan['rasio']:.2f}  Batas={kelangsingan['batas']:.2f}  -> {kelangsingan['klasifikasi']}"
    )
    if is_slender and inp["kondisi_rangka"] == "Braced":
        heading("2.3 Pembesaran Momen", 2)
        code_para(
            f"(EI)eff = 0.4xEcxIg/(1+beta) = {pembesaran['EI_eff']:,.2f} N.mm2\n"
            f"Pc      = pi2x(EI)eff/(kxLu)2 = {pembesaran['Pc']:,.2f} kN\n"
            f"Cm      = 0.6+0.4x({inp['M1']}/{inp['M2']}) = {pembesaran['Cm']:.4f}\n"
            f"delta   = {pembesaran['delta_ns']:.4f}\n"
            f"Mc      = {pembesaran['delta_ns']:.4f} x {inp['M2']:.0f} = {pembesaran['Mc']:.4f} kN.m"
        )
    heading("2.4 Tabel Diagram Interaksi (52 Titik)", 2)
    rows_int = []
    for row in hasil_interaksi:
        def sv(k, d=2):
            try: return f"{float(row[k]):,.{d}f}"
            except: return str(row.get(k, "-"))
        rows_int.append([str(row["No"]), str(row["c/h"]),
                         sv("Pn"), sv("Mn"), str(row["phi"]),
                         sv("phi_Pn"), sv("phi_Mn")])
    tbl(["No","c/h","Pn(kN)","Mn(kN.m)","phi","phiPn(kN)","phiMn(kN.m)"], rows_int)
    doc.add_page_break()

    # -- BAB 3 --
    heading("BAB 3: KESIMPULAN & HASIL AKHIR", 1)
    def fv(v):
        return f"{v:.2f}" if v is not None else "-"
    tbl(["Parameter","Nilai","Satuan","Status"], [
        ["Klasifikasi Kolom",   kelangsingan["klasifikasi"],     "-",    "-"],
        ["Pu",                  f"{inp['Pu']:.2f}",              "kN",   "INPUT"],
        ["Momen Desain Mc",     f"{Mu_desain:.4f}",              "kN.m", "INPUT"],
        ["phi.Pn Kapasitas",    fv(cek["phi_Pn_kapasitas"]),     "kN",   "-"],
        ["phi.Mn Kapasitas",    fv(cek["phi_Mn_kapasitas"]),     "kN.m", "-"],
        ["Rasio Pu/phi.Pn",     fv(cek["ratio_Pu"]),             "-",    "OK" if (cek["ratio_Pu"] or 0)<=1 else "NOT OK"],
        ["Rasio Mu/phi.Mn",     fv(cek["ratio_Mu"]),             "-",    "OK" if (cek["ratio_Mu"] or 0)<=1 else "NOT OK"],
        ["STATUS AKHIR",        cek["status"],                   "-",    cek["status"]],
    ])
    doc.add_paragraph()
    doc.add_paragraph(
        f"Perhitungan sesuai SNI 2847:2019. Diagram 52 titik. "
        f"Dibuat: {nama_eng} | {tgl_lpr}"
    )

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()


@st.cache_data
def buat_pdf(R, nama_eng, nama_prj, tgl_lpr, Mu_desain):
    from fpdf import FPDF

    props        = R["props"]
    kekakuan     = R["kekakuan"]
    kelangsingan = R["kelangsingan"]
    pembesaran   = R["pembesaran"]
    hasil_interaksi = R["hasil_interaksi"]
    cek          = R["cek"]
    inp          = R["inp"]
    is_slender   = R["is_slender"]

    def sc(text):
        """Sanitasi ke latin-1."""
        subs = {
            "φ":"phi","Φ":"Phi","²":"2","³":"3","√":"sqrt","·":".",
            "Ø":"O","ε":"eps","β":"beta","δ":"delta","ρ":"rho",
            "Ψ":"Psi","ψ":"psi","≤":"<=","≥":">=","×":"x","π":"pi",
            "∞":"inf","–":"-","—":"-","'":"'","'":"'",
        }
        for k, v in subs.items():
            text = text.replace(k, v)
        return text.encode("latin-1", errors="replace").decode("latin-1")

    class PDF(FPDF):
        def header(self):
            self.set_font("Helvetica","B",8)
            self.set_text_color(0,70,127)
            self.cell(0,7,sc("LAPORAN KAPASITAS KOLOM BETON BERTULANG | SNI 2847:2019"),align="C")
            self.ln(3)
            self.set_draw_color(0,70,127)
            self.line(10,self.get_y(),200,self.get_y())
            self.ln(2)
            self.set_text_color(0,0,0)

        def footer(self):
            self.set_y(-13)
            self.set_font("Helvetica","I",7)
            self.set_text_color(120,120,120)
            self.cell(0,8,sc(f"{nama_eng} | {tgl_lpr} | Hal. {self.page_no()}"),align="C")
            self.set_text_color(0,0,0)

        def sec(self, txt, lvl=1):
            if lvl==1:
                self.set_font("Helvetica","B",11)
                self.set_fill_color(0,70,127)
                self.set_text_color(255,255,255)
                self.cell(0,7,sc(txt),fill=True,ln=True)
                self.set_text_color(0,0,0)
            else:
                self.set_font("Helvetica","B",9)
                self.set_text_color(0,70,127)
                self.cell(0,6,sc(txt),ln=True)
                self.set_text_color(0,0,0)
            self.ln(1)

        def th(self, cols, ws):
            self.set_font("Helvetica","B",8)
            self.set_fill_color(210,225,245)
            for col,w in zip(cols,ws):
                self.cell(w,6,sc(col),border=1,fill=True)
            self.ln()

        def tr(self, vals, ws):
            self.set_font("Helvetica","",7.5)
            for val,w in zip(vals,ws):
                self.cell(w,5.5,sc(str(val)),border=1)
            self.ln()

        def code(self, txt):
            self.set_font("Courier","",8)
            for line in txt.split("\n"):
                self.cell(0,5,sc(line),ln=True)
            self.ln(1)

    pdf = PDF()
    pdf.set_auto_page_break(True,15)
    pdf.set_margins(12,15,12)

    # Cover
    pdf.add_page()
    pdf.ln(20)
    pdf.set_font("Helvetica","B",18)
    pdf.set_text_color(0,70,127)
    pdf.cell(0,12,"LAPORAN PERHITUNGAN STRUKTUR",align="C",ln=True)
    pdf.set_font("Helvetica","B",13)
    pdf.cell(0,9,"KAPASITAS KOLOM BETON BERTULANG",align="C",ln=True)
    pdf.set_font("Helvetica","",10)
    pdf.cell(0,7,"Diagram Interaksi P-M | SNI 2847:2019",align="C",ln=True)
    pdf.set_text_color(0,0,0)
    pdf.ln(12)
    for k,v in [("Proyek",nama_prj),("Engineer",nama_eng),("Tanggal",tgl_lpr),("Standar","SNI 2847:2019")]:
        pdf.set_font("Helvetica","B",10); pdf.cell(45,7,sc(k+" :"),align="R")
        pdf.set_font("Helvetica","",10);  pdf.cell(0,7,sc(v),ln=True)

    # BAB 1
    pdf.add_page()
    pdf.sec("BAB 1: DATA INPUT PARAMETER")
    pdf.sec("1.1 Material",2)
    pdf.th(["Parameter","Simbol","Nilai","Satuan"],[70,25,35,56])
    for r in [["Mutu Beton","fc'",str(inp["fc"]),"MPa"],
               ["Mutu Baja","fy",str(inp["fy"]),"MPa"],
               ["Mod.Elastisitas Baja","Es",str(inp["Es"]),"MPa"]]:
        pdf.tr(r,[70,25,35,56])
    pdf.ln(3)
    pdf.sec("1.2 Dimensi & Tulangan",2)
    pdf.th(["Parameter","Simbol","Nilai","Satuan"],[70,25,35,56])
    for r in [["Lebar","b",str(inp["b"]),"mm"],["Tinggi","h",str(inp["h"]),"mm"],
               ["Selimut","c",str(inp["c_sel"]),"mm"],["Dia.Sengkang","Os",str(inp["dia_s"]),"mm"],
               ["Dia.Tulangan","D",str(inp["D"]),"mm"],["Tul.Sisi b","n_b",str(inp["n_b"]),"bh"],
               ["Tul.Sisi h","n_h",str(inp["n_h"]),"bh"],["Total Tul","nt",str(props["n_total"]),"bh"],
               ["Panjang Lu","Lu",str(inp["Lu"]),"mm"]]:
        pdf.tr(r,[70,25,35,56])
    pdf.ln(3)
    pdf.sec("1.3 Beban Terfaktor",2)
    pdf.th(["Parameter","Simbol","Nilai","Satuan"],[70,25,35,56])
    for r in [["Gaya Aksial","Pu",str(inp["Pu"]),"kN"],["Momen M1","M1",str(inp["M1"]),"kN.m"],
               ["Momen M2","M2",str(inp["M2"]),"kN.m"],["Momen Desain","Mc",f"{Mu_desain:.4f}","kN.m"]]:
        pdf.tr(r,[70,25,35,56])

    # BAB 2
    pdf.add_page()
    pdf.sec("BAB 2: PROSES PERHITUNGAN STEP-BY-STEP")
    pdf.sec("2.1 Properti Penampang",2)
    pdf.code(
        f"Ag  = {inp['b']:.0f} x {inp['h']:.0f} = {props['Ag']:,.2f} mm2\n"
        f"Ig  = (1/12)x{inp['b']:.0f}x{inp['h']:.0f}3 = {props['Ig']:,.2f} mm4\n"
        f"Ec  = 4700 x sqrt({inp['fc']:.0f}) = {props['Ec']:,.2f} MPa\n"
        f"d'  = {props['d_prime']:.2f} mm  |  d = {props['d']:.2f} mm\n"
        f"Ast = {props['Ast']:,.2f} mm2  |  rho = {props['rho_g']:.2f}%  -> {props['cek_rasio']}"
    )
    pdf.sec("2.2 Kekakuan & Psi",2)
    pdf.code(
        f"PSI_A = {kekakuan['psi_A']:.4f}  |  PSI_B = {kekakuan['psi_B']:.4f}\n"
        f"k({inp['kondisi_rangka']}) = {kelangsingan['k']:.6f}\n"
        f"kLu/r = {kelangsingan['rasio']:.2f}  Batas={kelangsingan['batas']:.2f}  -> {kelangsingan['klasifikasi']}"
    )
    if is_slender and inp["kondisi_rangka"]=="Braced":
        pdf.sec("2.3 Pembesaran Momen",2)
        pdf.code(
            f"(EI)eff = {pembesaran['EI_eff']:,.2f} N.mm2\n"
            f"Pc      = {pembesaran['Pc']:,.2f} kN\n"
            f"Cm      = {pembesaran['Cm']:.4f}  |  delta = {pembesaran['delta_ns']:.4f}\n"
            f"Mc      = {pembesaran['Mc']:.4f} kN.m"
        )
    pdf.sec("2.4 Tabel Diagram Interaksi (52 Titik)",2)
    ws2=[10,18,24,24,12,24,24]
    pdf.th(["No","c/h","Pn(kN)","Mn(kN.m)","phi","phiPn(kN)","phiMn(kN.m)"],ws2)
    for row in hasil_interaksi:
        def sv(k,d=2):
            try: return f"{float(row[k]):,.{d}f}"
            except: return str(row.get(k,"-"))
        pdf.tr([str(row["No"]),str(row["c/h"]),sv("Pn"),sv("Mn"),str(row["phi"]),sv("phi_Pn"),sv("phi_Mn")],ws2)

    # BAB 3
    pdf.add_page()
    pdf.sec("BAB 3: KESIMPULAN & HASIL AKHIR")
    def fv(v):
        return f"{v:.2f}" if v is not None else "-"
    ws3=[75,35,20,56]
    pdf.th(["Parameter","Nilai","Satuan","Status"],ws3)
    for r in [
        ["Klasifikasi",       kelangsingan["klasifikasi"], "-", "-"],
        ["Pu",                f"{inp['Pu']:.2f}",          "kN","INPUT"],
        ["Momen Desain Mc",   f"{Mu_desain:.4f}",          "kN.m","INPUT"],
        ["phi.Pn Kapasitas",  fv(cek["phi_Pn_kapasitas"]), "kN", "-"],
        ["phi.Mn Kapasitas",  fv(cek["phi_Mn_kapasitas"]), "kN.m","-"],
        ["Rasio Pu/phi.Pn",   fv(cek["ratio_Pu"]),         "-",   "OK" if (cek["ratio_Pu"] or 0)<=1 else "NOT OK"],
        ["Rasio Mu/phi.Mn",   fv(cek["ratio_Mu"]),         "-",   "OK" if (cek["ratio_Mu"] or 0)<=1 else "NOT OK"],
        ["STATUS AKHIR",      cek["status"],                "-",   cek["status"]],
    ]:
        pdf.tr(r, ws3)
    pdf.ln(5)
    pdf.set_font("Helvetica","",8.5)
    pdf.multi_cell(0,5,sc(
        f"Catatan: Perhitungan berdasarkan SNI 2847:2019. Diagram 52 titik. "
        f"Dibuat: {nama_eng} | {tgl_lpr}"
    ))

    return bytes(pdf.output())


# ============================================================
# FOOTER
# ============================================================
st.divider()
st.markdown(
    "<div style='text-align:center;color:gray;font-size:11px;'>"
    "🏛️ Kolom Beton Bertulang | SNI 2847:2019 | Ladosi</div>",
    unsafe_allow_html=True,
)
