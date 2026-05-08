# calculations/bearing_capacity.py
# Perhitungan kapasitas daya dukung pondasi tiang dalam
# Daya dukung tekan (Qc) dan tarik (Qt)
#
# Acuan utama:
#   - SNI 8460:2017 Persyaratan Perancangan Geoteknik
#   - Meyerhof, G.G. (1976). Bearing capacity and settlement of pile foundations.
#     ASCE J. Geotech. Eng. Div., 102(3), 197-228.
#   - Tomlinson, M.J. (2008). Pile Design and Construction Practice, 5th Ed.
#   - API RP 2A-WSD (2014) untuk pasir (metode β)

import numpy as np
from calculations.soil_profile import (
    hitung_profil_tanah, spt_rata_ujung, lapisan_dalam_tiang
)


# ==============================================================
# KOEFISIEN ALPHA (α) — SKIN FRICTION TANAH LEMPUNG
# Tomlinson (2008) Table 4.4
# ==============================================================

def alpha_tomlinson(cu: float, is_displacement: bool) -> float:
    """
    Koefisien adhesi α untuk metode α (tanah lempung).
    Nilai α berbeda antara tiang displacement (pancang) vs non-displacement (boredpile).

    Parameter:
        cu              : kuat geser undrained (kPa)
        is_displacement : True jika tiang pancang (displacement pile)

    Mengembalikan nilai α (dimensionless)
    """
    if is_displacement:
        # Tiang pancang — Tomlinson (2008), konservatif untuk spun/square pile
        if cu <= 25:    return 1.00
        elif cu <= 50:  return 0.90
        elif cu <= 75:  return 0.75
        elif cu <= 100: return 0.55
        elif cu <= 150: return 0.45
        else:           return 0.35
    else:
        # Boredpile — reduksi karena efek pengeboran (Tomlinson 2008, API 2014)
        if cu <= 25:    return 0.90
        elif cu <= 50:  return 0.75
        elif cu <= 75:  return 0.60
        elif cu <= 100: return 0.45
        elif cu <= 150: return 0.35
        else:           return 0.25


# ==============================================================
# KOEFISIEN BETA (β) — SKIN FRICTION TANAH PASIR/LANAU
# Metode β (Burland 1973, dimodifikasi)
# ==============================================================

def beta_factor(phi_deg: float, is_displacement: bool, z: float) -> float:
    """
    Koefisien β untuk metode β (tanah pasir/lanau).
    β = K × tan(δ)

    Parameter:
        phi_deg         : sudut geser dalam tanah (°)
        is_displacement : True jika tiang pancang
        z               : kedalaman lapisan (m)

    Mengembalikan nilai β (dimensionless)
    """
    phi_rad = np.radians(phi_deg)

    if is_displacement:
        # Tiang displacement: K = 1.0–1.5 (Vesic 1977)
        K = 1.0 + 0.5 * min(z / 20.0, 1.0)  # meningkat dengan kedalaman, maks 1.5
        delta_ratio = 0.75  # δ/φ = 0.75 untuk tiang baja/beton
    else:
        # Boredpile: K lebih rendah karena dinding lubang bor rileks
        K = 0.5 + 0.2 * min(z / 20.0, 1.0)   # 0.5–0.7
        delta_ratio = 0.67  # δ/φ = 0.67

    delta_rad = delta_ratio * phi_rad
    beta = K * np.tan(delta_rad)

    # Batasi β agar tidak berlebihan (praktis maks 0.5 untuk pasir)
    beta = min(beta, 0.50)
    return round(beta, 4)


# ==============================================================
# KOEFISIEN Nq — END BEARING DARI SPT (Meyerhof 1976)
# ==============================================================

def nq_meyerhof(phi_deg: float) -> float:
    """
    Faktor kapasitas dukung Nq berdasarkan sudut geser dalam φ.
    Untuk tiang, Meyerhof (1976) merekomendasikan nilai yang lebih konservatif
    dari tabel bearing capacity klasik.

    Mengembalikan Nq (dimensionless)
    """
    # Interpolasi tabel Meyerhof untuk tiang
    phi_tabel = [0,  5, 10, 15, 20, 25, 30, 35, 40, 45]
    nq_tabel  = [1,  1,  3,  6, 10, 20, 40, 80,150,250]
    return float(np.interp(phi_deg, phi_tabel, nq_tabel))


def phi_dari_spt(spt: float, kategori: str) -> float:
    """
    Estimasi sudut geser dalam φ dari SPT-N (Peck et al. 1974, dimodifikasi).
    Digunakan ketika data phi tidak diisi user.

    Parameter:
        spt     : nilai SPT-N
        kategori: 'pasir' atau 'lanau'
    """
    if kategori == "pasir":
        # Peck et al. 1974
        if spt < 4:    return 25.0
        elif spt < 10: return 27.0
        elif spt < 30: return 30.0 + (spt - 10) * 0.25
        elif spt < 50: return 35.0 + (spt - 30) * 0.15
        else:          return 40.0
    else:  # lanau
        if spt < 4:    return 20.0
        elif spt < 10: return 23.0
        elif spt < 30: return 26.0 + (spt - 10) * 0.15
        else:          return 30.0


# ==============================================================
# FUNGSI UTAMA: HITUNG KAPASITAS TIANG
# ==============================================================

def hitung_kapasitas_tiang(
    df_tanah,
    param_tiang: dict,
    z_ujung: float = None
) -> dict:
    """
    Menghitung kapasitas daya dukung tiang: tekan dan tarik.

    Parameter:
        df_tanah    : DataFrame data tanah
        param_tiang : dict dari render_input_tiang()
        z_ujung     : kedalaman ujung tiang (m). Jika None, pakai param_tiang["kedalaman"]

    Mengembalikan dict hasil lengkap dengan langkah perhitungan.
    """
    if z_ujung is None:
        z_ujung = param_tiang["kedalaman"]

    muka_air        = param_tiang["muka_air"]
    keliling        = param_tiang["keliling"]
    area_ujung      = param_tiang["area_ujung"]
    is_displacement = param_tiang["is_displacement"]
    is_bored        = param_tiang["is_bored"]
    D               = param_tiang["diameter"]

    # Proses profil tanah
    semua_lapisan   = hitung_profil_tanah(df_tanah, muka_air)
    lapisan_tiang   = lapisan_dalam_tiang(semua_lapisan, z_ujung)

    if not lapisan_tiang:
        return {"error": "Kedalaman tiang melebihi data tanah yang tersedia."}

    # ---- LANGKAH 1: END BEARING (Qpoint) -------------------------
    langkah_qpoint  = []
    lapisan_ujung   = lapisan_tiang[-1]
    kategori_ujung  = lapisan_ujung["kategori"]

    langkah_qpoint.append("=" * 55)
    langkah_qpoint.append("1. PERHITUNGAN END BEARING (Qpoint)")
    langkah_qpoint.append("=" * 55)
    langkah_qpoint.append(f"   Kedalaman ujung tiang     : L = {z_ujung:.2f} m")
    langkah_qpoint.append(f"   Jenis tanah di ujung      : {lapisan_ujung['jenis']}")
    langkah_qpoint.append(f"   Luas ujung tiang          : Ab = {area_ujung:.4f} m²")
    langkah_qpoint.append("")

    if kategori_ujung == "lempung":
        # End bearing lempung: Qp = 9 × Cu × Ab (Skempton 1959)
        cu_ujung = lapisan_ujung["cu"]
        if cu_ujung <= 0:
            cu_ujung = max(lapisan_ujung["spt"] * 5.0, 10.0)  # estimasi Cu dari SPT
            langkah_qpoint.append(f"   Cu tidak diinput → estimasi: Cu ≈ SPT × 5 = {cu_ujung:.1f} kPa")

        Nc  = 9.0  # Skempton 1959 untuk tiang dalam
        Qpoint = Nc * cu_ujung * area_ujung

        langkah_qpoint.append("   Metode: Skempton (1959) untuk lempung")
        langkah_qpoint.append(f"   Qpoint = Nc × Cu × Ab")
        langkah_qpoint.append(f"          = {Nc:.1f} × {cu_ujung:.1f} × {area_ujung:.4f}")
        langkah_qpoint.append(f"          = {Qpoint:.2f} kN")

    else:
        # End bearing pasir/lanau: Qp = Nq × σ'v × Ab (Meyerhof 1976)
        # Batasi σ'v efektif di ujung (critical depth = 20D)
        z_kritis = min(20.0 * D, z_ujung)
        sigma_v_eff_ujung = lapisan_ujung["sigma_v_eff"]

        # Sudut geser: pakai input user, atau estimasi dari SPT
        phi_ujung = lapisan_ujung["phi_deg"]
        if phi_ujung <= 0:
            phi_ujung = phi_dari_spt(lapisan_ujung["spt"], kategori_ujung)
            langkah_qpoint.append(f"   φ tidak diinput → estimasi dari SPT-N={lapisan_ujung['spt']}: φ = {phi_ujung:.1f}°")

        Nq     = nq_meyerhof(phi_ujung)
        SPT_avg= spt_rata_ujung(semua_lapisan, z_ujung, D)

        # Meyerhof (1976): Qp = 0.4 × SPT_avg × Ab × (L/D) untuk pasir, maks 4×SPT_avg×Ab
        # Alternatif dengan Nq untuk konsistensi dengan metode klasik
        Qpoint_nq  = Nq * sigma_v_eff_ujung * area_ujung

        # Metode SPT langsung Meyerhof: qp = 0.4 × N_SPT × (L/D) kPa (batas 4N kPa)
        rasio_LD   = min(z_ujung / D, 50.0)
        qp_spt     = 0.4 * SPT_avg * rasio_LD  # kPa
        qp_spt_max = 4.0 * SPT_avg             # kPa (batas Meyerhof)
        qp_spt     = min(qp_spt, qp_spt_max)
        Qpoint_spt = qp_spt * area_ujung

        # Pilih nilai yang lebih konservatif
        Qpoint = min(Qpoint_nq, Qpoint_spt) if Qpoint_nq > 0 else Qpoint_spt

        langkah_qpoint.append("   Metode: Meyerhof (1976) untuk pasir/lanau")
        langkah_qpoint.append(f"   SPT-N rata-rata ±4D ujung  : N_avg = {SPT_avg:.1f} pukulan")
        langkah_qpoint.append(f"   Sudut geser dalam           : φ = {phi_ujung:.1f}°")
        langkah_qpoint.append(f"   Faktor Nq (Meyerhof)        : Nq = {Nq:.1f}")
        langkah_qpoint.append(f"   Tegangan efektif ujung      : σ'v = {sigma_v_eff_ujung:.2f} kPa")
        langkah_qpoint.append(f"")
        langkah_qpoint.append(f"   Cara 1 (Nq):")
        langkah_qpoint.append(f"   Qpoint = Nq × σ'v × Ab = {Nq:.1f} × {sigma_v_eff_ujung:.2f} × {area_ujung:.4f}")
        langkah_qpoint.append(f"          = {Qpoint_nq:.2f} kN")
        langkah_qpoint.append(f"")
        langkah_qpoint.append(f"   Cara 2 (SPT langsung Meyerhof):")
        langkah_qpoint.append(f"   L/D = {z_ujung:.1f} / {D:.2f} = {rasio_LD:.1f}")
        langkah_qpoint.append(f"   qp  = 0.4 × N_avg × (L/D) = 0.4 × {SPT_avg:.1f} × {rasio_LD:.1f} = {0.4*SPT_avg*rasio_LD:.2f} kPa")
        langkah_qpoint.append(f"   qp_max = 4 × N_avg = {qp_spt_max:.2f} kPa → qp dipakai = {qp_spt:.2f} kPa")
        langkah_qpoint.append(f"   Qpoint = {qp_spt:.2f} × {area_ujung:.4f} = {Qpoint_spt:.2f} kN")
        langkah_qpoint.append(f"")
        langkah_qpoint.append(f"   Dipakai nilai lebih konservatif: Qpoint = {Qpoint:.2f} kN")

    # Reduksi untuk boredpile (efek pengeboran mengurangi end bearing)
    if is_bored:
        faktor_bored = 0.75
        Qpoint_raw   = Qpoint
        Qpoint       = Qpoint_raw * faktor_bored
        langkah_qpoint.append(f"")
        langkah_qpoint.append(f"   Reduksi boredpile (faktor = {faktor_bored}):")
        langkah_qpoint.append(f"   Qpoint = {Qpoint_raw:.2f} × {faktor_bored} = {Qpoint:.2f} kN")

    langkah_qpoint.append(f"")
    langkah_qpoint.append(f"   >>> Qpoint = {Qpoint:.2f} kN")

    # ---- LANGKAH 2: SKIN FRICTION (Qskin) per lapisan ---------------
    langkah_qskin = []
    langkah_qskin.append("=" * 55)
    langkah_qskin.append("2. PERHITUNGAN SKIN FRICTION (Qskin) PER LAPISAN")
    langkah_qskin.append("=" * 55)
    langkah_qskin.append(f"   Keliling tiang : p = {keliling:.4f} m")
    langkah_qskin.append("")

    detail_lapisan = []
    Qskin_total    = 0.0

    for i, lap in enumerate(lapisan_tiang):
        ks = {}  # hasil per lapisan
        ks["no"]      = i + 1
        ks["jenis"]   = lap["jenis"]
        ks["z_atas"]  = lap["z_atas"]
        ks["z_bawah"] = lap["z_bawah"]
        ks["tebal"]   = lap["tebal"]
        ks["kategori"]= lap["kategori"]
        ks["sigma_v_eff"] = lap["sigma_v_eff"]

        langkah_qskin.append(f"   Lapisan {i+1}: {lap['jenis']} (z = {lap['z_atas']:.1f}–{lap['z_bawah']:.1f} m, tebal = {lap['tebal']:.1f} m)")

        if lap["kategori"] == "lempung":
            # Metode α (Tomlinson 2008)
            cu = lap["cu"]
            if cu <= 0:
                cu = max(lap["spt"] * 5.0, 10.0)
                langkah_qskin.append(f"      Cu tidak diinput → estimasi: Cu ≈ SPT × 5 = {cu:.1f} kPa")

            alpha = alpha_tomlinson(cu, is_displacement)
            fs    = alpha * cu          # friction per satuan luas (kPa)
            Qs_i  = fs * keliling * lap["tebal"]

            ks["metode"]  = "α-method (lempung)"
            ks["cu"]      = cu
            ks["alpha"]   = alpha
            ks["phi_deg"] = 0.0
            ks["beta"]    = 0.0
            ks["fs"]      = round(fs, 3)
            ks["Qs"]      = round(Qs_i, 2)

            tipe_str = "displacement" if is_displacement else "boredpile"
            langkah_qskin.append(f"      Metode α (Tomlinson 2008) — tipe: {tipe_str}")
            langkah_qskin.append(f"      α  = f(Cu={cu:.1f} kPa, {tipe_str}) = {alpha:.2f}")
            langkah_qskin.append(f"      fs = α × Cu = {alpha:.2f} × {cu:.1f} = {fs:.3f} kPa")
            langkah_qskin.append(f"      Qs = fs × p × h = {fs:.3f} × {keliling:.4f} × {lap['tebal']:.2f} = {Qs_i:.2f} kN")

        else:
            # Metode β (pasir/lanau) — Burland 1973, API 2014
            phi_deg = lap["phi_deg"]
            if phi_deg <= 0:
                phi_deg = phi_dari_spt(lap["spt"], lap["kategori"])
                langkah_qskin.append(f"      φ tidak diinput → estimasi dari SPT-N={lap['spt']:.0f}: φ = {phi_deg:.1f}°")

            beta  = beta_factor(phi_deg, is_displacement, lap["z_tengah"])
            fs    = beta * lap["sigma_v_eff"]
            fs    = max(fs, 0.0)
            Qs_i  = fs * keliling * lap["tebal"]

            ks["metode"]  = "β-method (pasir/lanau)"
            ks["cu"]      = 0.0
            ks["alpha"]   = 0.0
            ks["phi_deg"] = phi_deg
            ks["beta"]    = beta
            ks["fs"]      = round(fs, 3)
            ks["Qs"]      = round(Qs_i, 2)

            tipe_str = "displacement" if is_displacement else "boredpile"
            langkah_qskin.append(f"      Metode β (Burland 1973/API 2014) — tipe: {tipe_str}")
            langkah_qskin.append(f"      φ = {phi_deg:.1f}°, σ'v = {lap['sigma_v_eff']:.2f} kPa")
            langkah_qskin.append(f"      β  = K × tan(δ) = {beta:.4f}  (z={lap['z_tengah']:.1f} m)")
            langkah_qskin.append(f"      fs = β × σ'v = {beta:.4f} × {lap['sigma_v_eff']:.2f} = {fs:.3f} kPa")
            langkah_qskin.append(f"      Qs = fs × p × h = {fs:.3f} × {keliling:.4f} × {lap['tebal']:.2f} = {Qs_i:.2f} kN")

        Qskin_total += Qs_i
        detail_lapisan.append(ks)
        langkah_qskin.append("")

    langkah_qskin.append(f"   >>> ΣQskin = {Qskin_total:.2f} kN")

    # ---- LANGKAH 3: KAPASITAS TOTAL TEKAN & TARIK ---------------
    langkah_total = []
    langkah_total.append("=" * 55)
    langkah_total.append("3. KAPASITAS TOTAL DAYA DUKUNG")
    langkah_total.append("=" * 55)

    sf_tekan = param_tiang["sf_tekan"]
    sf_tarik = param_tiang["sf_tarik"]

    # Faktor reduksi tarik (skin friction saat tarik lebih rendah)
    faktor_tarik = 0.70 if is_bored else 0.85
    Qult_tekan   = Qpoint + Qskin_total
    Qult_tarik   = Qskin_total * faktor_tarik
    Qijin_tekan  = Qult_tekan / sf_tekan
    Qijin_tarik  = Qult_tarik / sf_tarik

    langkah_total.append(f"   Kapasitas TEKAN:")
    langkah_total.append(f"   Qult  = Qpoint + ΣQskin")
    langkah_total.append(f"         = {Qpoint:.2f} + {Qskin_total:.2f}")
    langkah_total.append(f"         = {Qult_tekan:.2f} kN")
    langkah_total.append(f"   Qijin = Qult / SF = {Qult_tekan:.2f} / {sf_tekan:.1f}")
    langkah_total.append(f"         = {Qijin_tekan:.2f} kN")
    langkah_total.append("")
    langkah_total.append(f"   Kapasitas TARIK:")
    langkah_total.append(f"   Faktor reduksi tarik = {faktor_tarik}  ({'boredpile' if is_bored else 'tiang pancang'})")
    langkah_total.append(f"   Qult_tarik  = ΣQskin × {faktor_tarik} = {Qskin_total:.2f} × {faktor_tarik}")
    langkah_total.append(f"              = {Qult_tarik:.2f} kN")
    langkah_total.append(f"   Qijin_tarik = Qult_tarik / SF = {Qult_tarik:.2f} / {sf_tarik:.1f}")
    langkah_total.append(f"              = {Qijin_tarik:.2f} kN")
    langkah_total.append("")
    langkah_total.append(f"   >>> Qijin tekan = {Qijin_tekan:.2f} kN")
    langkah_total.append(f"   >>> Qijin tarik = {Qijin_tarik:.2f} kN")

    # ---- LANGKAH 4: KAPASITAS STRUKTUR TIANG --------------------
    langkah_struktur = []
    langkah_struktur.append("=" * 55)
    langkah_struktur.append("4. KAPASITAS STRUKTUR TIANG")
    langkah_struktur.append("=" * 55)

    fc_prime = param_tiang.get("fc_prime")
    if fc_prime and not param_tiang["is_hpile"]:
        # SNI 2847:2019 untuk beton
        phi_beton = 0.65  # faktor reduksi tekan aksial
        reduksi_instalasi = 0.85 if is_bored else 1.0  # reduksi boredpile
        Pn = phi_beton * 0.85 * fc_prime * 1000 * area_ujung * reduksi_instalasi  # kN

        langkah_struktur.append(f"   Material: Beton, fc' = {fc_prime:.1f} MPa")
        langkah_struktur.append(f"   Luas penampang: Ag = {area_ujung:.4f} m² = {area_ujung*1e4:.2f} cm²")
        langkah_struktur.append(f"   Pn = φ × 0.85 × fc' × Ag × faktor_instalasi")
        langkah_struktur.append(f"      = {phi_beton} × 0.85 × {fc_prime:.1f}×10³ × {area_ujung:.4f} × {reduksi_instalasi}")
        langkah_struktur.append(f"      = {Pn:.2f} kN")
    elif param_tiang["is_hpile"]:
        fy = 250.0  # MPa, baja A36
        phi_baja = 0.90
        # Estimasi luas profil dari input (perlu disempurnakan)
        Ag_hpile = area_ujung * 0.15  # estimasi ~15% dari box area
        Pn = phi_baja * fy * 1000 * Ag_hpile
        langkah_struktur.append(f"   Material: Baja, fy = {fy:.0f} MPa")
        langkah_struktur.append(f"   Pn ≈ φ × fy × Ag = {phi_baja} × {fy:.0f}×10³ × {Ag_hpile:.4f}")
        langkah_struktur.append(f"      = {Pn:.2f} kN")
    else:
        Pn = float("inf")
        langkah_struktur.append("   Kapasitas struktur tidak dihitung untuk tipe ini.")

    if Pn < float("inf"):
        kontrol = "OK ✓" if Qijin_tekan <= Pn else "TIDAK OK ✗"
        langkah_struktur.append(f"   Kontrol: Qijin_tekan ({Qijin_tekan:.2f} kN) ≤ Pn ({Pn:.2f} kN) → {kontrol}")

    # ---- RANGKUM SEMUA HASIL ------------------------------------
    return {
        # Nilai utama
        "Qpoint":       round(Qpoint, 2),
        "Qskin":        round(Qskin_total, 2),
        "Qult_tekan":   round(Qult_tekan, 2),
        "Qult_tarik":   round(Qult_tarik, 2),
        "Qijin_tekan":  round(Qijin_tekan, 2),
        "Qijin_tarik":  round(Qijin_tarik, 2),
        "Pn_struktur":  round(Pn, 2) if Pn < float("inf") else None,
        "sf_tekan":     sf_tekan,
        "sf_tarik":     sf_tarik,
        "z_ujung":      z_ujung,

        # Detail per lapisan untuk tabel
        "detail_lapisan": detail_lapisan,

        # Langkah perhitungan (string) untuk ditampilkan
        "langkah_qpoint":   langkah_qpoint,
        "langkah_qskin":    langkah_qskin,
        "langkah_total":    langkah_total,
        "langkah_struktur": langkah_struktur,
        "semua_lapisan":    semua_lapisan,
    }


def hitung_variasi_kedalaman(
    df_tanah,
    param_tiang: dict,
    z_min: float,
    z_max: float,
    n_titik: int = 20
) -> list[dict]:
    """
    Menghitung kapasitas tiang untuk berbagai kedalaman.
    Digunakan untuk membuat grafik Qtotal vs kedalaman tiang.

    Mengembalikan list dict: [{z, Qijin_tekan, Qijin_tarik, Qpoint, Qskin}, ...]
    """
    from utils.input_handler import KOLOM_TANAH as KT
    z_maks_data = float(df_tanah[KT["z_bawah"]].max())

    z_list  = np.linspace(z_min, min(z_max, z_maks_data * 0.99), n_titik)
    hasil   = []

    for z in z_list:
        try:
            res = hitung_kapasitas_tiang(df_tanah, param_tiang, z_ujung=z)
            if "error" not in res:
                hasil.append({
                    "z":            round(z, 2),
                    "Qijin_tekan":  res["Qijin_tekan"],
                    "Qijin_tarik":  res["Qijin_tarik"],
                    "Qpoint":       res["Qpoint"],
                    "Qskin":        res["Qskin"],
                    "Qult_tekan":   res["Qult_tekan"],
                })
        except Exception:
            pass

    return hasil
