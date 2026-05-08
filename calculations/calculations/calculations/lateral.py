# calculations/lateral.py
# Perhitungan gaya lateral pondasi tiang dalam
#
# METODE 1: Broms (1964) — solusi persamaan tertutup
#   Broms, B.B. (1964). Lateral resistance of piles in cohesive soils.
#   ASCE J. Soil Mech. Found. Div., 90(SM2), 27–63.
#   Broms, B.B. (1964). Lateral resistance of piles in cohesionless soils.
#   ASCE J. Soil Mech. Found. Div., 90(SM3), 123–156.
#
# METODE 2: P-Y Curve — analisis numerik finite difference
#   Matlock, H. (1970). Correlations for design of laterally loaded piles.
#   OTC Paper 1204, Houston.
#   Reese, L.C. et al. (1974). Analysis of laterally loaded piles in sand.
#   OTC Paper 2080, Houston.
#   Reese, L.C. (1975). Laterally loaded piles: program documentation.
#   ASCE J. Geotech. Eng. Div., 101(GT6), 633–649.
#   API RP 2GEO (2011) / API RP 2A-WSD (2014)

import numpy as np
from scipy import linalg
from scipy.optimize import brentq


# ==============================================================
# KONSTANTA
# ==============================================================
GAMMA_AIR = 9.81   # kN/m³
N_ELEMEN  = 60     # jumlah elemen diskretisasi tiang untuk p-y


# ==============================================================
# ===  METODE 1: BROMS (1964)  ===
# ==============================================================

def _Ep_Ip(D: float, fc_prime: float | None, is_hpile: bool) -> float:
    """
    Menghitung kekakuan lentur tiang EpIp (kN·m²).

    Parameter:
        D         : diameter/lebar tiang (m)
        fc_prime  : kuat tekan beton fc' (MPa). None untuk H-pile.
        is_hpile  : True jika H-pile baja

    Mengembalikan EpIp (kN·m²)
    """
    if is_hpile:
        # Estimasi H-pile WF200×200 (Ip ≈ 4720 cm⁴), Es = 200.000 MPa
        Es   = 200_000.0  # MPa
        Ip   = 4720e-8    # m⁴ (representatif WF200)
        return Es * 1000 * Ip  # kN·m²
    else:
        # Beton: Ec = 4700√fc' MPa (ACI 318)
        Ec = 4700 * np.sqrt(fc_prime) * 1000  # kN/m²
        if D > 0:
            Ip = np.pi / 64 * D**4  # m⁴ (penampang lingkaran)
        return Ec * Ip


# ---- BROMS — TANAH LEMPUNG (kohesif) -------------------------

def broms_lempung(
    H: float, e: float, L: float, D: float,
    Cu: float, kondisi_kepala: str,
    fc_prime: float | None = None, is_hpile: bool = False
) -> dict:
    """
    Kapasitas lateral Broms (1964) untuk tanah lempung (undrained).

    Parameter:
        H              : gaya lateral (kN) — diisi untuk cek kapasitas, atau 0 untuk hitung kapasitas
        e              : eksentrisitas / tinggi aplikasi gaya dari kepala tiang (m)
        L              : panjang/kedalaman tiang (m)
        D              : diameter tiang (m)
        Cu             : kuat geser undrained rata-rata (kPa)
        kondisi_kepala : 'bebas' atau 'jepit'
        fc_prime       : fc' beton (MPa)
        is_hpile       : True jika H-pile

    Mengembalikan dict hasil + langkah perhitungan
    """
    langkah = []
    langkah.append("=" * 55)
    langkah.append("METODE BROMS (1964) — TANAH LEMPUNG")
    langkah.append("=" * 55)
    langkah.append(f"   Gaya lateral input : H  = {H:.2f} kN")
    langkah.append(f"   Eksentrisitas      : e  = {e:.2f} m")
    langkah.append(f"   Panjang tiang      : L  = {L:.2f} m")
    langkah.append(f"   Diameter tiang     : D  = {D:.4f} m")
    langkah.append(f"   Kuat geser undr.   : Cu = {Cu:.2f} kPa")
    langkah.append(f"   Kondisi kepala     : {kondisi_kepala}")
    langkah.append("")

    # Broms menyederhanakan distribusi tekanan lateral lempung:
    # - 0 s/d 1.5D dari permukaan: diabaikan
    # - Di bawah 1.5D: p_ult = 9 × Cu × D

    p_ult = 9.0 * Cu * D   # kN/m (resistansi lateral per meter panjang)
    langkah.append(f"   Resistansi lateral ultimit:")
    langkah.append(f"   p_ult = 9 × Cu × D = 9 × {Cu:.2f} × {D:.4f} = {p_ult:.3f} kN/m")
    langkah.append("")

    # ---- Kapasitas lateral ultimit (Hu) ----
    # Tiang kepala BEBAS:
    #   Hu dihitung dari persamaan momen di titik rotasi f
    #   Hu × (e + 1.5D + f/2) = Mmax
    #   Hu × (1.5D + 0.5f) × D × ... (iterasi)
    #   Solusi tertutup Broms:
    #   Hu = p_ult × (L - 1.5D) — untuk tiang pendek (short pile)
    #   Hu = 9CuD × f → Mmax = Hu(e+1.5D+f/2)  untuk tiang panjang (long pile)

    z0    = 1.5 * D           # kedalaman awal distribusi tekanan (m)
    L_eff = max(L - z0, 0.1) # panjang efektif di bawah zona diabaikan

    if kondisi_kepala.lower() == "bebas":
        # Cek apakah tiang pendek atau panjang
        # Tiang pendek: rotasi — Hu = p_ult × L_eff / (1 + e/L_eff + ... )
        # Persamaan Broms untuk kepala bebas (Randolph & Houlsby simplification):
        # Hu × (e + 1.5D + f) = p_ult × f × (L_eff - f/2)
        # Dimana f = Hu / p_ult (kedalaman titik nol momen)

        def persamaan_hu_bebas(Hu_trial):
            f = Hu_trial / p_ult
            if f >= L_eff:
                return 1e6  # tidak konvergen
            momen_kiri  = Hu_trial * (e + z0 + f)
            momen_kanan = p_ult * f * (L_eff - f / 2)
            return momen_kiri - momen_kanan

        try:
            Hu = brentq(persamaan_hu_bebas, 0.01, p_ult * L_eff * 2, xtol=0.001)
        except ValueError:
            # Fallback pendek
            Hu = p_ult * L_eff / (1 + 2 * e / L_eff + 1.5 * D / L_eff)

        f_rot = Hu / p_ult   # kedalaman di bawah z0 ke titik momen maks
        Mmax  = Hu * (e + z0 + f_rot)

        langkah.append(f"   Kepala bebas — iterasi kedalaman rotasi (f):")
        langkah.append(f"   f_rot = Hu / p_ult = {Hu:.2f} / {p_ult:.3f} = {f_rot:.3f} m")
        langkah.append(f"   Titik momen maks di z = {z0:.3f} + {f_rot:.3f} = {z0+f_rot:.3f} m dari permukaan")
        langkah.append(f"   Mmax = Hu × (e + 1.5D + f) = {Hu:.2f} × ({e:.2f}+{z0:.3f}+{f_rot:.3f})")
        langkah.append(f"        = {Mmax:.2f} kN·m")

    else:  # kepala jepit
        # Kepala jepit: momen di kepala = Hu × e
        # Tiang panjang: Mmax di kepala = p_ult × (L_eff²/2) / 2 — pendekatan
        # Broms: Hu = p_ult × L_eff / (1 + 2e/L + 0.5) untuk pendek
        # Untuk kepala jepit, kapasitas lebih tinggi ~1.5× kepala bebas
        try:
            def persamaan_hu_jepit(Hu_trial):
                f = Hu_trial / p_ult
                if f >= L_eff:
                    return 1e6
                M_kepala = Hu_trial * e
                M_tengah = Hu_trial * (z0 + f) - p_ult * f**2 / 2
                return M_tengah - M_kepala - p_ult * L_eff * 0.01  # konvergensi

            Hu_bebas_approx = p_ult * L_eff / (2 + 3 * e / L_eff)
            Hu = min(Hu_bebas_approx * 1.5, p_ult * L_eff)
        except Exception:
            Hu = p_ult * L_eff * 0.5

        f_rot = Hu / p_ult
        Mmax  = Hu * (e + z0 + f_rot * 0.5)

        langkah.append(f"   Kepala jepit — kapasitas lebih tinggi dari kepala bebas:")
        langkah.append(f"   f_rot ≈ {f_rot:.3f} m")
        langkah.append(f"   Mmax  ≈ {Mmax:.2f} kN·m")

    SF_lateral = 2.5
    Hijin      = Hu / SF_lateral
    langkah.append("")
    langkah.append(f"   Kapasitas lateral ultimit : Hu    = {Hu:.2f} kN")
    langkah.append(f"   Safety factor             : SF    = {SF_lateral}")
    langkah.append(f"   Kapasitas lateral ijin    : Hijin = Hu/SF = {Hu:.2f}/{SF_lateral}")
    langkah.append(f"                                      = {Hijin:.2f} kN")

    # ---- Defleksi kepala tiang (elastis) ----
    EpIp = _Ep_Ip(D, fc_prime, is_hpile)
    kh   = 67.0 * Cu   # modulus subgrade horizontal (kPa/m) — Vesic 1961
    beta = (kh * D / (4 * EpIp)) ** 0.25   # faktor kekakuan (1/m)
    L_beta = beta * L

    if kondisi_kepala.lower() == "bebas":
        if L_beta >= 2.0:   # tiang panjang
            y0 = H * beta / (kh * D) * (2.0 + beta * e)
        else:               # tiang pendek
            y0 = H * (L + e)**3 / (3 * EpIp)
    else:
        if L_beta >= 2.0:
            y0 = H * beta / (kh * D)
        else:
            y0 = H * (L + e)**3 / (12 * EpIp)

    langkah.append("")
    langkah.append(f"   Defleksi kepala tiang (elastis):")
    langkah.append(f"   EpIp = {EpIp:.2f} kN·m²")
    langkah.append(f"   kh   = 67 × Cu = 67 × {Cu:.2f} = {kh:.2f} kN/m³")
    langkah.append(f"   β    = (kh·D / 4EpIp)^0.25 = {beta:.5f} m⁻¹")
    langkah.append(f"   βL   = {beta:.4f} × {L:.2f} = {L_beta:.3f}  ({'tiang panjang' if L_beta>=2 else 'tiang pendek'})")
    langkah.append(f"   y₀   = {y0*1000:.2f} mm  (pada H = {H:.2f} kN)")

    kontrol = "OK ✓" if H <= Hijin else "TIDAK OK ✗ — perlu H lebih kecil atau tiang lebih dalam"
    langkah.append("")
    langkah.append(f"   Kontrol: H={H:.2f} kN ≤ Hijin={Hijin:.2f} kN → {kontrol}")

    return {
        "Hu":           round(Hu, 2),
        "Hijin":        round(Hijin, 2),
        "Mmax":         round(Mmax, 2),
        "f_rot":        round(f_rot, 3),
        "defleksi_mm":  round(y0 * 1000, 2),
        "EpIp":         round(EpIp, 2),
        "beta":         round(beta, 5),
        "L_beta":       round(L_beta, 3),
        "tanah":        "lempung",
        "kondisi":      kondisi_kepala,
        "kontrol_ok":   H <= Hijin,
        "langkah":      langkah,
    }


# ---- BROMS — TANAH PASIR/GRANULAR (non-kohesif) --------------

def broms_pasir(
    H: float, e: float, L: float, D: float,
    phi_deg: float, gamma: float, muka_air: float,
    kondisi_kepala: str,
    fc_prime: float | None = None, is_hpile: bool = False
) -> dict:
    """
    Kapasitas lateral Broms (1964) untuk tanah pasir (drained).

    Parameter:
        H              : gaya lateral (kN)
        e              : eksentrisitas (m)
        L              : panjang tiang (m)
        D              : diameter tiang (m)
        phi_deg        : sudut geser dalam (°)
        gamma          : berat volume tanah (kN/m³)
        muka_air       : kedalaman muka air tanah (m)
        kondisi_kepala : 'bebas' atau 'jepit'
    """
    langkah = []
    langkah.append("=" * 55)
    langkah.append("METODE BROMS (1964) — TANAH PASIR")
    langkah.append("=" * 55)
    langkah.append(f"   H = {H:.2f} kN  |  e = {e:.2f} m  |  L = {L:.2f} m  |  D = {D:.4f} m")
    langkah.append(f"   φ = {phi_deg:.1f}°  |  γ = {gamma:.1f} kN/m³  |  MAT = {muka_air:.1f} m")
    langkah.append("")

    phi_rad  = np.radians(phi_deg)
    # Faktor tekanan pasif Rankine Kp
    Kp = (1 + np.sin(phi_rad)) / (1 - np.sin(phi_rad))

    # Broms pasir: resistansi per meter = 3 × Kp × γ × z × D
    # (distribusi segitiga)
    # Berat volume efektif (di bawah MAT)
    if muka_air < L:
        gamma_eff = gamma - GAMMA_AIR
    else:
        gamma_eff = gamma  # semua di atas MAT

    langkah.append(f"   Kp = tan²(45+φ/2) = {Kp:.3f}")
    langkah.append(f"   γ efektif rata-rata ≈ {gamma_eff:.2f} kN/m³")
    langkah.append(f"   Resistansi lateral: p(z) = 3 × Kp × γ_eff × z × D")
    langkah.append("")

    # Resultan gaya pasif total (distribusi segitiga sepanjang L)
    Fp_total = 0.5 * 3 * Kp * gamma_eff * L**2 * D  # kN
    z_Fp     = L / 3  # titik tangkap dari ujung bawah (1/3L dari bawah)

    langkah.append(f"   Fp_total = 0.5 × 3 × Kp × γ_eff × L² × D")
    langkah.append(f"            = 0.5 × 3 × {Kp:.3f} × {gamma_eff:.2f} × {L:.2f}² × {D:.4f}")
    langkah.append(f"            = {Fp_total:.2f} kN")
    langkah.append(f"   Titik tangkap Fp dari ujung bawah tiang: L/3 = {z_Fp:.3f} m")
    langkah.append("")

    if kondisi_kepala.lower() == "bebas":
        # Momen terhadap ujung bawah:
        # Hu × (L + e) = Fp × (L/3)
        # → Hu = Fp × L / (3 × (L + e))
        Hu   = Fp_total * z_Fp / (L + e) if (L + e) > 0 else Fp_total * z_Fp / L
        Mmax = Hu * e + Hu * (Hu / (3 * Kp * gamma_eff * D))  # approx

        langkah.append(f"   Kepala bebas — momen terhadap ujung bawah:")
        langkah.append(f"   Hu × (L + e) = Fp × (L/3)")
        langkah.append(f"   Hu = {Fp_total:.2f} × {z_Fp:.3f} / ({L:.2f} + {e:.2f})")
        langkah.append(f"      = {Hu:.2f} kN")
    else:
        # Kepala jepit: Hu lebih tinggi (biasanya 1.3–1.8× kepala bebas)
        Hu_bebas = Fp_total * z_Fp / (L + e) if (L + e) > 0 else Fp_total * z_Fp / L
        Hu       = Hu_bebas * 1.5
        Mmax     = Hu * e

        langkah.append(f"   Kepala jepit — Hu ≈ 1.5 × Hu_bebas:")
        langkah.append(f"   Hu_bebas = {Hu_bebas:.2f} kN")
        langkah.append(f"   Hu       = {Hu:.2f} kN")

    # Momen maks (Broms 1964, pasir kepala bebas):
    # z_mmax = Hu / (1.5 × Kp × γ_eff × D)
    z_mmax = Hu / (1.5 * Kp * gamma_eff * D) if (Kp * gamma_eff * D) > 0 else 0
    Mmax   = Hu * (e + z_mmax) - 0.5 * 1.5 * Kp * gamma_eff * D * z_mmax**2 * (z_mmax / 3)
    Mmax   = max(Mmax, Hu * e)

    SF_lateral = 2.5
    Hijin      = Hu / SF_lateral

    langkah.append(f"   z_Mmax = Hu / (1.5·Kp·γ·D) = {Hu:.2f}/(1.5×{Kp:.3f}×{gamma_eff:.2f}×{D:.4f})")
    langkah.append(f"          = {z_mmax:.3f} m dari permukaan")
    langkah.append(f"   Mmax   ≈ {Mmax:.2f} kN·m")
    langkah.append(f"   Hu     = {Hu:.2f} kN")
    langkah.append(f"   Hijin  = Hu/SF = {Hu:.2f}/{SF_lateral} = {Hijin:.2f} kN")

    # Defleksi
    EpIp = _Ep_Ip(D, fc_prime, is_hpile)
    nh   = 2000.0 * Kp  # modulus reaksi tanah nh (kN/m³) — Terzaghi 1955
    T    = (EpIp / nh) ** 0.2  # faktor panjang relatif (m)
    L_T  = L / T

    if kondisi_kepala.lower() == "bebas":
        if L_T >= 5.0:   # tiang panjang
            y0 = 2.435 * H * T**3 / EpIp + 1.623 * H * e * T**2 / EpIp
        else:
            y0 = H * (L + e)**3 / (3 * EpIp)
    else:
        if L_T >= 5.0:
            y0 = 0.930 * H * T**3 / EpIp
        else:
            y0 = H * (L + e)**3 / (12 * EpIp)

    langkah.append("")
    langkah.append(f"   Defleksi kepala tiang:")
    langkah.append(f"   nh = 2000 × Kp = {nh:.0f} kN/m³")
    langkah.append(f"   T  = (EpIp/nh)^0.2 = ({EpIp:.2f}/{nh:.0f})^0.2 = {T:.3f} m")
    langkah.append(f"   L/T = {L_T:.2f}  ({'tiang panjang' if L_T>=5 else 'tiang pendek'})")
    langkah.append(f"   y₀  = {y0*1000:.2f} mm")

    kontrol = "OK ✓" if H <= Hijin else "TIDAK OK ✗"
    langkah.append("")
    langkah.append(f"   Kontrol: H={H:.2f} kN ≤ Hijin={Hijin:.2f} kN → {kontrol}")

    return {
        "Hu":           round(Hu, 2),
        "Hijin":        round(Hijin, 2),
        "Mmax":         round(Mmax, 2),
        "z_mmax":       round(z_mmax, 3),
        "defleksi_mm":  round(y0 * 1000, 2),
        "EpIp":         round(EpIp, 2),
        "T_faktor":     round(T, 3),
        "L_T":          round(L_T, 3),
        "Kp":           round(Kp, 3),
        "tanah":        "pasir",
        "kondisi":      kondisi_kepala,
        "kontrol_ok":   H <= Hijin,
        "langkah":      langkah,
    }


def hitung_broms(
    H: float, e: float,
    param_tiang: dict,
    df_tanah,
    kondisi_kepala: str = "bebas"
) -> dict:
    """
    Wrapper Broms: otomatis pilih lempung atau pasir berdasarkan
    jenis tanah dominan yang dilewati tiang.

    Mengembalikan dict hasil Broms.
    """
    from calculations.soil_profile import hitung_profil_tanah, lapisan_dalam_tiang
    from utils.input_handler import KOLOM_TANAH

    L   = param_tiang["kedalaman"]
    D   = param_tiang["diameter"]
    fc  = param_tiang.get("fc_prime")
    maw = param_tiang["muka_air"]

    semua_lap = hitung_profil_tanah(df_tanah, maw)
    lap_tiang = lapisan_dalam_tiang(semua_lap, L)

    if not lap_tiang:
        return {"error": "Tidak ada lapisan tanah dalam rentang tiang."}

    # Tentukan jenis tanah dominan (berdasarkan tebal)
    tebal_lempung = sum(l["tebal"] for l in lap_tiang if l["kategori"] == "lempung")
    tebal_pasir   = sum(l["tebal"] for l in lap_tiang if l["kategori"] != "lempung")

    if tebal_lempung >= tebal_pasir:
        # Rata-rata Cu tertimbang
        Cu_avg = sum(l["cu"] * l["tebal"] for l in lap_tiang if l["kategori"] == "lempung") / max(tebal_lempung, 0.1)
        if Cu_avg <= 0:
            Cu_avg = max(
                sum(l["spt"] * 5.0 * l["tebal"] for l in lap_tiang if l["kategori"] == "lempung") / max(tebal_lempung, 0.1),
                10.0
            )
        hasil = broms_lempung(H, e, L, D, Cu_avg, kondisi_kepala, fc, param_tiang["is_hpile"])
        hasil["Cu_avg"] = round(Cu_avg, 2)
        hasil["tanah_dominan"] = "lempung"
    else:
        # Rata-rata φ dan γ tertimbang
        phi_avg   = sum(l["phi_deg"] * l["tebal"] for l in lap_tiang if l["kategori"] != "lempung") / max(tebal_pasir, 0.1)
        gamma_avg = sum(l["gamma"] * l["tebal"] for l in lap_tiang) / L
        if phi_avg <= 0:
            phi_avg = 28.0
        hasil = broms_pasir(H, e, L, D, phi_avg, gamma_avg, maw, kondisi_kepala, fc, param_tiang["is_hpile"])
        hasil["phi_avg"]   = round(phi_avg, 1)
        hasil["gamma_avg"] = round(gamma_avg, 2)
        hasil["tanah_dominan"] = "pasir"

    return hasil


# ==============================================================
# ===  METODE 2: P-Y CURVE (FINITE DIFFERENCE)  ===
# ==============================================================

def _kurva_py_lempung_lunak(z: float, D: float, Cu: float,
                             gamma: float, y50: float = 0.02) -> callable:
    """
    Kurva p-y untuk lempung lunak (Matlock 1970).
    p/pu = 0.5 × (y/y50)^(1/3),  p ≤ pu

    Parameter:
        z    : kedalaman (m)
        D    : diameter tiang (m)
        Cu   : kuat geser undrained (kPa)
        gamma: berat volume tanah (kN/m³)
        y50  : defleksi pada 50% pu (biasanya 0.02×D untuk lempung lunak)
    """
    # Resistansi ultimit
    Np  = min(3 + gamma * z / Cu + 0.5 * z / D, 9.0)  # Matlock 1970
    pu  = Np * Cu * D   # kN/m
    y50_val = y50 * D   # defleksi karakteristik (m)

    def p_y(y_val: float) -> float:
        ratio = abs(y_val) / y50_val if y50_val > 0 else 0
        p_val = min(0.5 * pu * (ratio ** (1.0 / 3.0)), pu)
        return p_val * np.sign(y_val) if y_val != 0 else 0.0

    return p_y, pu


def _kurva_py_pasir(z: float, D: float, phi_deg: float,
                    gamma_eff: float) -> callable:
    """
    Kurva p-y untuk pasir (Reese et al. 1974 / API RP 2A).
    p = A × pu × tanh(k × z × y / (A × pu))

    Parameter:
        z         : kedalaman (m)
        D         : diameter tiang (m)
        phi_deg   : sudut geser dalam (°)
        gamma_eff : berat volume efektif (kN/m³)
    """
    phi_rad = np.radians(phi_deg)
    beta    = np.radians(45 + phi_deg / 2)
    K0      = 0.4    # koefisien tekanan lateral at rest

    # Tekanan pasif ultimit (Reese 1974)
    alpha   = phi_rad / 2
    Ka      = np.tan(np.radians(45) - phi_rad / 2)**2

    C1 = (np.tan(beta) * np.sin(beta) / (np.tan(beta - phi_rad) * np.cos(alpha))
          + np.tan(beta) * (np.tan(phi_rad) * np.sin(beta) - np.tan(alpha))
          + K0 * np.tan(phi_rad) * (np.tan(beta) / np.tan(beta - phi_rad) - np.tan(alpha)) * np.tan(beta))
    C2 = np.tan(beta) / np.tan(beta - phi_rad) - Ka

    pu_rapat = max(C1 * gamma_eff * z * D, 0.01)  # rupture di permukaan
    pu_dalam = max(C2 * gamma_eff * z * D, 0.01)  # rupture dalam
    pu       = min(pu_rapat, pu_dalam)
    pu       = max(pu, 0.5 * Ka * gamma_eff * z * D)  # batas bawah

    # Modulus k (kN/m³) — fungsi sudut geser (API Table C6.8-1)
    if phi_deg < 28:    k_init = 5_000.0
    elif phi_deg < 36:  k_init = 20_000.0
    else:               k_init = 40_000.0

    A = max(3.0 - 0.8 * z / D, 0.9)   # faktor siklik/statis

    def p_y(y_val: float) -> float:
        arg = k_init * z / (A * pu) * y_val if pu > 0 else 0
        p_val = A * pu * np.tanh(np.clip(arg, -30, 30))
        return float(p_val)

    return p_y, pu


def _kurva_py_lempung_keras(z: float, D: float, Cu: float) -> callable:
    """
    Kurva p-y untuk lempung keras (Reese 1975) — bilinear.
    """
    pu    = min(2 * Cu + 2.83 * Cu, 11 * Cu) * D
    y_ult = 0.0625 * D   # defleksi di pu

    def p_y(y_val: float) -> float:
        if abs(y_val) <= y_ult:
            return pu / y_ult * y_val
        else:
            return pu * np.sign(y_val)

    return p_y, pu


def hitung_py_curve(
    H: float, e: float,
    param_tiang: dict,
    df_tanah,
    kondisi_kepala: str = "bebas",
    n_elemen: int = N_ELEMEN
) -> dict:
    """
    Analisis gaya lateral tiang dengan metode p-y curve (finite difference).
    Menggunakan metode matriks (Matlock & Reese 1960, dimodifikasi).

    Parameter:
        H              : gaya lateral di kepala tiang (kN)
        e              : eksentrisitas gaya (m di atas kepala tiang)
        param_tiang    : dict dari input_handler
        df_tanah       : DataFrame data tanah
        kondisi_kepala : 'bebas' atau 'jepit'
        n_elemen       : jumlah elemen diskretisasi

    Mengembalikan dict hasil lengkap + array profil defleksi/momen/geser
    """
    from calculations.soil_profile import hitung_profil_tanah, lapisan_dalam_tiang
    from calculations.bearing_capacity import phi_dari_spt

    langkah = []
    langkah.append("=" * 55)
    langkah.append("METODE P-Y CURVE (Finite Difference)")
    langkah.append("=" * 55)

    L   = param_tiang["kedalaman"]
    D   = param_tiang["diameter"]
    fc  = param_tiang.get("fc_prime")
    maw = param_tiang["muka_air"]
    EI  = _Ep_Ip(D, fc, param_tiang["is_hpile"])

    langkah.append(f"   H = {H:.2f} kN  |  e = {e:.2f} m  |  L = {L:.2f} m")
    langkah.append(f"   D = {D:.4f} m  |  EI = {EI:.2f} kN·m²")
    langkah.append(f"   Kondisi kepala: {kondisi_kepala}")
    langkah.append(f"   Jumlah elemen : n = {n_elemen}")
    langkah.append("")

    # --- Diskretisasi tiang ---
    dz      = L / n_elemen
    z_nodes = np.linspace(0, L, n_elemen + 1)  # kedalaman node (m)

    langkah.append(f"   Diskretisasi: dz = L/n = {L:.2f}/{n_elemen} = {dz:.4f} m")
    langkah.append("")

    # --- Bangun kurva p-y per node ---
    semua_lap = hitung_profil_tanah(df_tanah, maw)

    def cari_lapisan(z: float):
        """Cari lapisan tanah untuk kedalaman z."""
        for lap in semua_lap:
            if lap["z_atas"] <= z <= lap["z_bawah"]:
                return lap
        return semua_lap[-1]  # pakai lapisan paling bawah jika melewati data

    # Buat fungsi p-y dan pu untuk setiap node
    py_funcs = []
    pu_list  = []

    for z in z_nodes:
        lap  = cari_lapisan(z)
        kat  = lap["kategori"]
        geff = max(lap["gamma"] - GAMMA_AIR if z > maw else lap["gamma"], 8.0)

        if kat == "lempung":
            cu = lap["cu"] if lap["cu"] > 0 else lap["spt"] * 5.0
            cu = max(cu, 5.0)
            # Lempung lunak (cu < 96 kPa) atau keras
            if cu < 96:
                pfunc, pu = _kurva_py_lempung_lunak(max(z, 0.01), D, cu, geff)
            else:
                pfunc, pu = _kurva_py_lempung_keras(max(z, 0.01), D, cu)
        else:
            phi = lap["phi_deg"] if lap["phi_deg"] > 0 else phi_dari_spt(lap["spt"], kat)
            pfunc, pu = _kurva_py_pasir(max(z, 0.01), D, phi, geff)

        py_funcs.append(pfunc)
        pu_list.append(pu)

    langkah.append(f"   Kurva p-y dibangun untuk {n_elemen+1} node.")
    langkah.append(f"   Resistansi ultimit (pu) di kepala: {pu_list[0]:.2f} kN/m")
    langkah.append(f"   Resistansi ultimit (pu) di ujung : {pu_list[-1]:.2f} kN/m")
    langkah.append("")

    # --- Iterasi finite difference ---
    # Persamaan beam on Winkler foundation:
    # EI × y'''' + p(y) = 0
    # Diskretisasi: EI/dz⁴ × (yi-2 - 4yi-1 + 6yi - 4yi+1 + yi+2) + ki×yi = 0
    # Iterasi: update ki = p(yi)/yi setiap langkah

    n_dof   = n_elemen + 1  # jumlah node
    toleransi   = 1e-4      # mm
    maks_iter   = 50

    y    = np.zeros(n_dof)   # defleksi awal = 0
    konvergen = False

    EI_dz4 = EI / dz**4

    for iterasi in range(maks_iter):
        y_lama = y.copy()

        # Hitung kp = p/y untuk setiap node (secara iteratif)
        kp = np.zeros(n_dof)
        for i in range(n_dof):
            yi = y[i]
            if abs(yi) > 1e-10:
                p_i   = py_funcs[i](yi)
                kp[i] = p_i / yi
            else:
                # Tangent awal dari kurva p-y di y → 0
                dy_small = 1e-6
                p_small  = py_funcs[i](dy_small)
                kp[i]    = p_small / dy_small if dy_small > 0 else 1000.0
            kp[i] = max(kp[i], 0.0)

        # Bangun matriks kekakuan
        K = np.zeros((n_dof, n_dof))
        F = np.zeros(n_dof)

        # Interior nodes (i = 2 ... n-2)
        for i in range(2, n_dof - 2):
            K[i, i-2] += EI_dz4
            K[i, i-1] += -4 * EI_dz4
            K[i, i  ] += 6 * EI_dz4 + kp[i]
            K[i, i+1] += -4 * EI_dz4
            K[i, i+2] += EI_dz4

        # ---- Boundary conditions ----
        # NODE 0 (kepala tiang, z=0)
        if kondisi_kepala.lower() == "bebas":
            # Gaya geser: EI × y''' = H → EI/dz³ × (-y[-2] + 2y[-1] - 2y[1] + y[2]) = -H
            # Momen: EI × y'' = H×e → EI/dz² × (y[-1] - 2y[0] + y[1]) = H×e
            # Gunakan node virtual y[-2] dan y[-1]
            # Pendekatan: set kondisi langsung pada baris 0 dan 1
            K[0, 0] = 1.0;  K[0, 1] = 0.0                     # placeholder
            K[1, 0] = EI/dz**2 * (-2); K[1, 1] = EI/dz**2 * (1)
            K[1, 2] = EI/dz**2
            F[0]    = 0.0  # diselesaikan via kondisi geser & momen
            F[1]    = H * e  # momen di kepala

            # Kondisi geser di kepala (row 0): y'' terhadap finite diff
            K[0, 0] = EI / dz**3 * (2)
            K[0, 1] = EI / dz**3 * (-5)
            K[0, 2] = EI / dz**3 * (4)
            K[0, 3] = EI / dz**3 * (-1)
            F[0]    = -H

        else:  # kepala jepit
            K[0, 0] = 1.0   # y[0] = 0 (defleksi terkekang)
            F[0]    = 0.0
            K[1, 0] = 1.0; K[1, 1] = -1.0  # y'[0] = 0 (rotasi terkekang)
            F[1]    = 0.0

        # NODE n (ujung bebas bawah tiang)
        # Momen = 0: y'' = 0
        n = n_dof - 1
        K[n-1, n-2] = EI/dz**2; K[n-1, n-1] = -2*EI/dz**2
        if n < n_dof - 1:
            K[n-1, n] = EI/dz**2
        else:
            K[n-1, n-1] += EI/dz**2  # node virtual = mirror
        F[n-1] = 0.0

        # Geser = 0 di ujung bawah
        K[n, n-2] = -EI/dz**3; K[n, n-1] = 2*EI/dz**3
        K[n, n]   = -EI/dz**3  # plus node virtual
        F[n]      = 0.0

        # Tambah kp ke diagonal interior agar matriks tidak singular
        for i in range(2, n_dof - 2):
            K[i, i] = max(K[i, i], kp[i] + EI_dz4 * 6)

        # Solve
        try:
            y = np.linalg.solve(K + np.eye(n_dof) * 1e-8, F)
        except np.linalg.LinAlgError:
            y = np.linalg.lstsq(K, F, rcond=None)[0]

        # Cek konvergensi
        delta = np.max(np.abs(y - y_lama)) * 1000  # mm
        if delta < toleransi:
            konvergen = True
            langkah.append(f"   Konvergen pada iterasi ke-{iterasi+1}, Δy_maks = {delta:.5f} mm")
            break

    if not konvergen:
        langkah.append(f"   Peringatan: belum konvergen setelah {maks_iter} iterasi.")

    # --- Post-processing: momen dan geser ---
    M = np.zeros(n_dof)  # momen lentur (kN·m)
    V = np.zeros(n_dof)  # gaya geser (kN)

    for i in range(1, n_dof - 1):
        M[i] = EI * (y[i-1] - 2*y[i] + y[i+1]) / dz**2
    M[0]  = H * e  # momen di kepala (kepala bebas) atau 0 (jepit)
    M[-1] = 0.0

    for i in range(1, n_dof - 1):
        V[i] = EI * (-y[i-2] + 2*y[i-1] - 2*y[i+1] + y[i+2]) / (2 * dz**3) if i >= 2 and i <= n_dof - 3 else (M[i] - M[i-1]) / dz
    V[0]  = H

    # --- Ringkasan hasil ---
    y0_mm   = y[0] * 1000  # defleksi kepala (mm)
    Mmax    = np.max(np.abs(M))
    z_Mmax  = z_nodes[np.argmax(np.abs(M))]
    Vmax    = np.max(np.abs(V))

    langkah.append(f"   Defleksi kepala tiang : y₀ = {y0_mm:.2f} mm")
    langkah.append(f"   Momen maks            : Mmax = {Mmax:.2f} kN·m  (z = {z_Mmax:.2f} m)")
    langkah.append(f"   Gaya geser maks       : Vmax = {Vmax:.2f} kN")
    langkah.append(f"   Jumlah iterasi        : {iterasi+1}")

    return {
        "y0_mm":        round(y0_mm, 2),
        "Mmax":         round(Mmax, 2),
        "z_Mmax":       round(z_Mmax, 2),
        "Vmax":         round(Vmax, 2),
        "konvergen":    konvergen,
        "iterasi":      iterasi + 1,
        "z_nodes":      z_nodes.tolist(),
        "y_m":          y.tolist(),         # defleksi (m)
        "M_kNm":        M.tolist(),         # momen (kN·m)
        "V_kN":         V.tolist(),         # geser (kN)
        "pu_list":      pu_list,            # resistansi ultimit per node
        "langkah":      langkah,
        "EI":           round(EI, 2),
        "L":            L,
        "H":            H,
        "kondisi":      kondisi_kepala,
    }
