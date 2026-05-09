# calculations/buckling.py
# Pemeriksaan Kelangsingan & Tekuk Tiang Pancang
#
# Acuan:
#   - SNI 2847:2019  Persyaratan Beton Struktural untuk Bangunan Gedung, Pasal 6.2 & 6.6
#   - SNI 8460:2017  Persyaratan Perancangan Geoteknik, Pasal 8 & Lampiran B
#   - Davisson, M.T. & Robinson, K.E. (1965). Bending and Buckling of Partially
#     Embedded Piles. Proc. 6th ICSMFE, Montreal, Vol. 2, pp. 243-246.
#   - Tomlinson, M.J. (2008). Pile Design and Construction Practice, 5th Ed.
#     Taylor & Francis. Tabel 3.1 & 3.2.
#   - Euler, L. (1744). Methodus Inveniendi Lineas Curvas — rumus tekuk kolom.
#   - ACI 318-19 / SNI 2847:2019 Pasal 6.2.5 — kolom langsing.

import numpy as np
from calculations.lateral import _Ep_Ip
from calculations.soil_profile import hitung_profil_tanah, lapisan_dalam_tiang


# ══════════════════════════════════════════════════════════════
# KONSTANTA
# ══════════════════════════════════════════════════════════════

# Batas L/D praktis per tipe tiang (Tomlinson 2008, Tabel 3.2)
BATAS_LD = {
    "Spun pile":   80,
    "Square pile": 60,
    "Boredpile":   40,
    "H-pile":     120,
}

# Koefisien reaksi subgrade horizontal nh untuk pasir (kN/m³)
# Davisson & Robinson (1965), Terzaghi (1955)
NH_PASIR = {
    "Pasir lepas":          2_500,
    "Pasir sedang":         7_500,
    "Pasir padat":         20_000,
    "Pasir sangat padat":  50_000,
}

# Modulus reaksi subgrade k untuk lempung (kN/m³)
# Vesic (1961): k ≈ 67 × Cu
KS_LEMPUNG_FAKTOR = 67.0   # k = 67 × Cu (kPa/m)

# Faktor panjang tekuk efektif (k) per kondisi kepala-ujung
# SNI 2847:2019 Tabel 6.2.6.1 / ACI 318-19 Fig. R6.2.6
FAKTOR_K = {
    "Kepala bebas  – Ujung bebas":  2.00,
    "Kepala jepit  – Ujung bebas":  1.20,
    "Kepala bebas  – Ujung jepit":  0.70,
    "Kepala jepit  – Ujung jepit":  0.50,
}

# SF minimum untuk tekuk Euler (praktik geoteknik)
SF_TEKUK_MIN = 3.0

# Batas kLu/r SNI 2847:2019 Pasal 6.2.5(a)
KLU_R_BATAS_DIABAIKAN = 22   # rangka terkekang (braced)
KLU_R_BATAS_ORDE2     = 100  # perlu analisis orde kedua


# ══════════════════════════════════════════════════════════════
# HELPER: PANJANG TEKUK EFEKTIF (DAVISSON & ROBINSON 1965)
# ══════════════════════════════════════════════════════════════

def _panjang_tekuk_pasir(EI: float, nh: float) -> tuple[float, float]:
    """
    Menghitung panjang tekuk relatif T untuk tanah pasir/granular.

    Metode: Davisson & Robinson (1965)
    Rumus : T = (EI / nh)^(1/5)

    Parameter:
        EI : kekakuan lentur tiang (kN·m²)
        nh : koefisien reaksi subgrade horizontal (kN/m³)

    Mengembalikan (T, Le_bebas):
        T       = panjang relatif (m)
        Le_bebas= panjang tekuk elastis kepala bebas = 1.8 × T (m)
    """
    T  = (EI / nh) ** 0.20
    Le = 1.80 * T   # tiang panjang L/T ≥ 4 (Davisson 1965)
    return T, Le


def _panjang_tekuk_lempung(EI: float, k: float) -> tuple[float, float]:
    """
    Menghitung panjang tekuk relatif R untuk tanah lempung/kohesif.

    Metode: Davisson & Robinson (1965)
    Rumus : R = (EI / k)^(1/4)

    Parameter:
        EI : kekakuan lentur tiang (kN·m²)
        k  : modulus reaksi subgrade (kN/m²) = ks × D

    Mengembalikan (R, Le_bebas):
        R       = panjang relatif (m)
        Le_bebas= 1.4 × R (m) — tiang panjang L/R ≥ 3.5
    """
    R  = (EI / max(k, 1.0)) ** 0.25
    Le = 1.40 * R
    return R, Le


# ══════════════════════════════════════════════════════════════
# FUNGSI UTAMA
# ══════════════════════════════════════════════════════════════

def hitung_kelangsingan(
    param_tiang: dict,
    hasil_tekan: dict,
    df_tanah,
    kondisi_kepala_atas: str  = "Kepala jepit  – Ujung bebas",
    Q_aksial: float | None    = None,
    M_lateral: float          = 0.0,
) -> dict:
    """
    Pemeriksaan kelangsingan dan stabilitas tekuk tiang pancang.

    Pemeriksaan yang dilakukan:
      1. Rasio kelangsingan geometri (L/D)
      2. Panjang tekuk efektif — metode Davisson & Robinson (1965)
      3. Beban tekuk kritis Euler & safety factor
      4. Kolom langsing SNI 2847:2019 Pasal 6.2.5 (kLu/r)
      5. Interaksi aksial-momen (P-M) — beam-column check

    Parameter:
        param_tiang         : dict dari input_handler
        hasil_tekan         : dict dari bearing_capacity.hitung_kapasitas_tiang()
        df_tanah            : DataFrame data tanah
        kondisi_kepala_atas : pilihan dari FAKTOR_K
        Q_aksial            : beban aksial kerja (kN); default = Qijin tekan
        M_lateral           : momen dari gaya lateral (kN·m); 0 jika tidak ada

    Mengembalikan dict hasil lengkap + list langkah perhitungan (step-by-step).
    """
    langkah = []

    def L(teks): langkah.append(teks)   # helper singkat

    L("=" * 60)
    L("PEMERIKSAAN KELANGSINGAN & TEKUK TIANG PANCANG")
    L("=" * 60)
    L("")
    L("Acuan:")
    L("  • SNI 2847:2019 Pasal 6.2.5 — Kolom Langsing")
    L("  • SNI 8460:2017 Pasal 8 — Perencanaan Geoteknik Tiang")
    L("  • Davisson & Robinson (1965) — Panjang Tekuk Efektif")
    L("  • Tomlinson (2008) Tabel 3.2 — Batas L/D Praktis")
    L("  • Euler (1744) — Beban Tekuk Kritis")
    L("")

    # ── Ambil parameter dasar ─────────────────────────────────
    D   = param_tiang["diameter"]         # m
    L_  = param_tiang["kedalaman"]        # m
    Ab  = param_tiang["area_ujung"]       # m²
    fc  = param_tiang.get("fc_prime", 33.2)  # MPa
    maw = param_tiang["muka_air"]
    tipe = param_tiang["tipe"]

    if Q_aksial is None:
        Q_aksial = hasil_tekan["Qijin_tekan"]

    EI = _Ep_Ip(D, fc, param_tiang["is_hpile"])   # kN·m²
    Ep = EI / (np.pi / 64 * D**4) if not param_tiang["is_hpile"] else 200_000_000.0
    # Ec dalam kPa → MPa
    Ep_MPa = Ep / 1000.0

    L(f"  Tipe tiang        : {tipe}")
    L(f"  Diameter (D)      : {D:.4f} m")
    L(f"  Kedalaman (L)     : {L_:.2f} m")
    L(f"  Luas ujung (Ab)   : {Ab:.4f} m²")
    L(f"  fc' beton         : {fc:.1f} MPa")
    L(f"  Ec beton          : 4700 × √{fc:.1f} = {4700*fc**0.5:.0f} MPa")
    L(f"  EI tiang          : {EI:,.0f} kN·m²")
    L(f"  Q aksial kerja    : {Q_aksial:.2f} kN")
    L(f"  Momen lateral     : {M_lateral:.2f} kN·m")
    L(f"  Kondisi kepala    : {kondisi_kepala_atas}")
    L("")

    # ── PEMERIKSAAN 1: RASIO KELANGSINGAN L/D ────────────────
    L("─" * 60)
    L("PEMERIKSAAN 1 — RASIO KELANGSINGAN GEOMETRI (L/D)")
    L("  Acuan: Tomlinson (2008) Tabel 3.2")
    L("─" * 60)

    LD = L_ / D

    # Tentukan batas L/D berdasarkan tipe
    batas_LD = BATAS_LD["Square pile"]
    for k, v in BATAS_LD.items():
        if k.lower() in tipe.lower():
            batas_LD = v; break

    L(f"  Rumus : λ = L / D")
    L(f"  λ     = {L_:.2f} / {D:.4f}")
    L(f"  λ     = {LD:.2f}")
    L(f"  Batas λ izin ({tipe.split('(')[0].strip()}) = {batas_LD}")

    if LD <= batas_LD * 0.75:
        kontrol_LD = "OK ✓ — Tidak langsing"
    elif LD <= batas_LD:
        kontrol_LD = "OK ✓ — Mendekati batas, perlu perhatian"
    else:
        kontrol_LD = "TIDAK OK ✗ — Melampaui batas praktis"

    L(f"  Kontrol: λ = {LD:.2f} ≤ {batas_LD} → {kontrol_LD}")
    L("")

    # ── PEMERIKSAAN 2: PANJANG TEKUK EFEKTIF ─────────────────
    L("─" * 60)
    L("PEMERIKSAAN 2 — PANJANG TEKUK EFEKTIF (Le)")
    L("  Acuan: Davisson & Robinson (1965)")
    L("  Metode: Tiang sebagai balok di atas fondasi elastis (Winkler)")
    L("─" * 60)
    L("")

    semua_lap  = hitung_profil_tanah(df_tanah, maw)
    lap_tiang  = lapisan_dalam_tiang(semua_lap, L_)

    # Tentukan lapisan dominan (tebal terbesar)
    if not lap_tiang:
        lap_tiang = semua_lap

    lap_dominan = max(lap_tiang, key=lambda x: x["tebal"])
    kat_dom     = lap_dominan["kategori"]
    cu_dom      = lap_dominan["cu"]
    spt_dom     = lap_dominan["spt"]

    L(f"  Lapisan dominan: {lap_dominan['jenis']} "
      f"(tebal = {lap_dominan['tebal']:.2f} m, z = {lap_dominan['z_atas']:.1f}–{lap_dominan['z_bawah']:.1f} m)")
    L(f"  Kategori tanah : {kat_dom}")
    L("")

    # Hitung Le per kategori
    if kat_dom == "lempung":
        # Modulus reaksi subgrade: k = 67 × Cu × D (Vesic 1961)
        Cu_eff = max(cu_dom, 5.0)
        ks     = KS_LEMPUNG_FAKTOR * Cu_eff   # kPa/m
        k_sub  = ks * D                         # kN/m² (k = ks × D)

        L(f"  === Tanah LEMPUNG — metode R (Davisson 1965) ===")
        L(f"  Kuat geser undrained   : Cu = {Cu_eff:.1f} kPa")
        L(f"  Modulus subgrade (Vesic 1961):")
        L(f"    ks = 67 × Cu = 67 × {Cu_eff:.1f} = {ks:.1f} kPa/m")
        L(f"    k  = ks × D = {ks:.1f} × {D:.4f} = {k_sub:.2f} kN/m²")
        L(f"  Panjang relatif:")
        L(f"    R = (EI / k)^(1/4)")
        L(f"    R = ({EI:,.0f} / {k_sub:.2f})^0.25")
        R, Le_dom = _panjang_tekuk_lempung(EI, k_sub)
        L(f"    R = {R:.3f} m")
        L(f"  Panjang tekuk elastis (kepala bebas):")
        L(f"    Le₀ = 1.4 × R = 1.4 × {R:.3f} = {Le_dom:.3f} m")
        T_ref = R

        # Cek apakah tiang panjang (L/R ≥ 3.5)
        tiang_panjang = L_ / R >= 3.5
        L(f"  Cek tiang panjang: L/R = {L_:.2f}/{R:.3f} = {L_/R:.2f} "
          f"({'≥' if tiang_panjang else '<'} 3.5 → tiang {'PANJANG ✓' if tiang_panjang else 'PENDEK'})")

    else:  # pasir/lanau
        # Tentukan nh dari jenis tanah
        nh = NH_PASIR["Pasir sedang"]  # default
        for kj, v in NH_PASIR.items():
            if kj.lower() in lap_dominan["jenis"].lower():
                nh = v; break
        # Koreksi dari SPT jika belum cocok
        if spt_dom < 10:
            nh = NH_PASIR["Pasir lepas"]
        elif spt_dom < 30:
            nh = NH_PASIR["Pasir sedang"]
        elif spt_dom < 50:
            nh = NH_PASIR["Pasir padat"]
        else:
            nh = NH_PASIR["Pasir sangat padat"]

        L(f"  === Tanah PASIR/GRANULAR — metode T (Davisson 1965) ===")
        L(f"  SPT-N lapisan dominan  : N = {spt_dom:.0f} pukulan")
        L(f"  Koefisien nh (Terzaghi 1955):")
        L(f"    nh = {nh:,} kN/m³")
        L(f"  Panjang relatif:")
        L(f"    T = (EI / nh)^(1/5)")
        L(f"    T = ({EI:,.0f} / {nh:,})^0.20")
        T_ref, Le_dom = _panjang_tekuk_pasir(EI, nh)
        L(f"    T = {T_ref:.3f} m")
        L(f"  Panjang tekuk elastis (kepala bebas):")
        L(f"    Le₀ = 1.8 × T = 1.8 × {T_ref:.3f} = {Le_dom:.3f} m")
        R = T_ref

        tiang_panjang = L_ / T_ref >= 4.0
        L(f"  Cek tiang panjang: L/T = {L_:.2f}/{T_ref:.3f} = {L_/T_ref:.2f} "
          f"({'≥' if tiang_panjang else '<'} 4.0 → tiang {'PANJANG ✓' if tiang_panjang else 'PENDEK'})")

    # Faktor kondisi kepala × Le₀
    k_faktor = FAKTOR_K.get(kondisi_kepala_atas, 1.20)
    Le_final  = k_faktor * Le_dom

    L("")
    L(f"  Faktor kondisi kepala-ujung:")
    L(f"    k = {k_faktor} ({kondisi_kepala_atas})")
    L(f"    Sumber: SNI 2847:2019 Tabel 6.2.6.1")
    L(f"  Panjang tekuk efektif final:")
    L(f"    Le = k × Le₀ = {k_faktor} × {Le_dom:.3f}")
    L(f"    Le = {Le_final:.3f} m")
    L("")

    # ── PEMERIKSAAN 3: BEBAN TEKUK EULER ─────────────────────
    L("─" * 60)
    L("PEMERIKSAAN 3 — BEBAN TEKUK KRITIS EULER")
    L("  Acuan: Euler (1744) — Methodus Inveniendi Lineas Curvas")
    L("         SNI 2847:2019 Pasal 6.6.4 (EI efektif)")
    L("─" * 60)
    L("")

    # EI efektif untuk kolom beton (SNI 2847:2019 Pasal 6.6.4.4.4 — Persamaan 6.6.4.4.4b)
    # (EI)eff = 0.40 × Ec × Ig  (nilai konservatif)
    Ec_kPa = 4700 * fc**0.5 * 1000   # kPa
    if param_tiang["is_hpile"]:
        Ig = Ab * (D**2 / 12)   # approx
        EI_eff = 200_000_000 * Ig
    else:
        Ig = np.pi / 64 * D**4  # m⁴ (penampang solid)
        EI_eff = 0.40 * Ec_kPa * Ig

    Pcr = (np.pi**2 * EI_eff) / (Le_final**2)
    SF_euler = Pcr / max(Q_aksial, 0.001)

    L(f"  EI efektif (SNI 2847:2019 Ps. 6.6.4.4.4, Pers. 6.6.4.4.4b):")
    L(f"    (EI)eff = 0.40 × Ec × Ig")
    L(f"    Ec  = 4700 × √fc' = 4700 × √{fc:.1f} = {Ec_kPa/1000:.0f} MPa = {Ec_kPa:.0f} kPa")
    L(f"    Ig  = π/64 × D⁴ = π/64 × {D:.4f}⁴ = {Ig:.6f} m⁴")
    L(f"    (EI)eff = 0.40 × {Ec_kPa:.0f} × {Ig:.6f}")
    L(f"    (EI)eff = {EI_eff:,.0f} kN·m²")
    L("")
    L(f"  Beban tekuk kritis Euler:")
    L(f"    Pcr = π² × (EI)eff / Le²")
    L(f"    Pcr = π² × {EI_eff:,.0f} / {Le_final:.3f}²")
    L(f"    Pcr = {np.pi**2:.4f} × {EI_eff:,.0f} / {Le_final**2:.4f}")
    L(f"    Pcr = {Pcr:,.2f} kN")
    L("")
    L(f"  Safety factor tekuk:")
    L(f"    SF_tekuk = Pcr / Q_aksial")
    L(f"    SF_tekuk = {Pcr:,.2f} / {Q_aksial:.2f}")
    L(f"    SF_tekuk = {SF_euler:.2f}")
    L(f"  Batas minimum SF_tekuk = {SF_TEKUK_MIN:.1f} (praktik geoteknik)")

    if SF_euler >= SF_TEKUK_MIN:
        kontrol_euler = f"OK ✓ (SF = {SF_euler:.2f} ≥ {SF_TEKUK_MIN})"
    else:
        kontrol_euler = f"TIDAK OK ✗ (SF = {SF_euler:.2f} < {SF_TEKUK_MIN})"
    L(f"  Kontrol: {kontrol_euler}")
    L("")

    # ── PEMERIKSAAN 4: KOLOM LANGSING SNI 2847:2019 ──────────
    L("─" * 60)
    L("PEMERIKSAAN 4 — KOLOM LANGSING (kLu/r)")
    L("  Acuan: SNI 2847:2019 Pasal 6.2.5")
    L("─" * 60)
    L("")

    # Jari-jari girasi r
    if param_tiang["is_hpile"]:
        r = D * 0.40   # approx untuk H-pile
    elif param_tiang["is_bored"] or "bulat" in tipe.lower() or "spun" in tipe.lower():
        r = 0.25 * D   # penampang lingkaran: r = 0.25D
    else:
        r = 0.30 * D   # penampang kotak: r = 0.30b (SNI 2847:2019 Penjelasan 6.2.5)

    Lu    = L_          # panjang tak tertopang = kedalaman tiang (konservatif)
    kLu_r = k_faktor * Lu / r

    L(f"  Jari-jari girasi (r):")
    if "bulat" in tipe.lower() or "spun" in tipe.lower() or param_tiang["is_bored"]:
        L(f"    r = 0.25 × D = 0.25 × {D:.4f} = {r:.4f} m")
        L(f"    (SNI 2847:2019 Penjelasan Pasal 6.2.5 — penampang lingkaran)")
    else:
        L(f"    r = 0.30 × b = 0.30 × {D:.4f} = {r:.4f} m")
        L(f"    (SNI 2847:2019 Penjelasan Pasal 6.2.5 — penampang persegi)")
    L("")
    L(f"  Panjang tak tertopang (Lu) = {Lu:.2f} m")
    L(f"  Faktor k                   = {k_faktor}")
    L(f"  Rasio kelangsingan kolom:")
    L(f"    kLu/r = k × Lu / r")
    L(f"    kLu/r = {k_faktor} × {Lu:.2f} / {r:.4f}")
    L(f"    kLu/r = {kLu_r:.2f}")
    L("")
    L(f"  Kriteria SNI 2847:2019 Pasal 6.2.5(a):")
    L(f"    • kLu/r < {KLU_R_BATAS_DIABAIKAN} → efek kelangsingan diabaikan")
    L(f"    • {KLU_R_BATAS_DIABAIKAN} ≤ kLu/r < {KLU_R_BATAS_ORDE2} → perlu momen amplifikasi (δns)")
    L(f"    • kLu/r ≥ {KLU_R_BATAS_ORDE2} → perlu analisis orde kedua penuh")

    if kLu_r < KLU_R_BATAS_DIABAIKAN:
        kontrol_kolom = f"OK ✓ — Efek kelangsingan dapat diabaikan (kLu/r = {kLu_r:.1f} < {KLU_R_BATAS_DIABAIKAN})"
        klu_status = "diabaikan"
    elif kLu_r < KLU_R_BATAS_ORDE2:
        kontrol_kolom = f"PERLU MOMEN AMPLIFIKASI ⚠️ (kLu/r = {kLu_r:.1f})"
        klu_status = "amplifikasi"
    else:
        kontrol_kolom = f"PERLU ANALISIS ORDE-2 PENUH ✗ (kLu/r = {kLu_r:.1f} ≥ {KLU_R_BATAS_ORDE2})"
        klu_status = "orde2"

    L(f"  Kontrol: {kontrol_kolom}")
    L("")

    # ── PEMERIKSAAN 5: INTERAKSI AKSIAL-MOMEN (P-M) ──────────
    L("─" * 60)
    L("PEMERIKSAAN 5 — INTERAKSI AKSIAL-MOMEN (P-M)")
    L("  Acuan: SNI 2847:2019 Pasal 22.4 — Kapasitas Aksial-Momen")
    L("         ACI 318-19 Pasal 6.6.5 — Beam-Column Interaction")
    L("─" * 60)
    L("")

    # Kapasitas aksial φPn
    phi_c = 0.65   # faktor reduksi tekan (SNI 2847:2019 Tabel 21.2.2)
    fPn   = phi_c * 0.85 * fc * 1000 * Ab   # kN

    # Momen minimum (eksentrisitas minimum: e_min = 0.03D, SNI 2847 Ps. 22.4.2.1)
    e_min = max(0.03 * D, 0.015)   # m
    # Kapasitas momen φMn (pendekatan — tiang tanpa tulangan eksplisit)
    # φMn ≈ φ × 0.85 × fc' × Ag × e_min (pendekatan Bresler 1960)
    fMn   = phi_c * 0.85 * fc * 1000 * Ab * e_min   # kN·m

    # Momen yang bekerja
    M_total = M_lateral + Q_aksial * e_min   # kN·m

    # Rasio interaksi (SNI 2847:2019 Persamaan 22.4.3.1)
    # Jika Q/φPn ≥ 0.2 → Q/(φPn) + 8/(9) × M/(φMn) ≤ 1.0  (AISC H1-1a / ACI)
    # Jika Q/φPn < 0.2 → Q/(2φPn) + M/(φMn) ≤ 1.0
    rasio_P = Q_aksial / max(fPn, 1.0)
    rasio_M = M_total  / max(fMn, 1.0)

    if rasio_P >= 0.20:
        rasio_PM = rasio_P + (8.0 / 9.0) * rasio_M
        rumus_PM = f"Q/φPn + (8/9)×M/φMn = {rasio_P:.4f} + (8/9)×{rasio_M:.4f}"
    else:
        rasio_PM = rasio_P / 2.0 + rasio_M
        rumus_PM = f"Q/(2φPn) + M/φMn = {rasio_P/2:.4f} + {rasio_M:.4f}"

    L(f"  Kapasitas aksial nominal:")
    L(f"    φPn = φ × 0.85 × fc' × Ag")
    L(f"    φPn = {phi_c} × 0.85 × {fc:.1f}×10³ × {Ab:.4f}")
    L(f"    φPn = {fPn:,.2f} kN")
    L(f"    (φ = {phi_c}, SNI 2847:2019 Tabel 21.2.2 — tekan aksial)")
    L("")
    L(f"  Eksentrisitas minimum (SNI 2847:2019 Pasal 22.4.2.1):")
    L(f"    e_min = max(0.03D, 15 mm) = max(0.03×{D:.4f}, 0.015)")
    L(f"    e_min = {e_min:.4f} m")
    L("")
    L(f"  Kapasitas momen (pendekatan Bresler 1960):")
    L(f"    φMn = φ × 0.85 × fc' × Ag × e_min")
    L(f"    φMn = {phi_c} × 0.85 × {fc:.1f}×10³ × {Ab:.4f} × {e_min:.4f}")
    L(f"    φMn = {fMn:.2f} kN·m")
    L("")
    L(f"  Momen total yang bekerja:")
    L(f"    M_total = M_lateral + Q × e_min")
    L(f"    M_total = {M_lateral:.2f} + {Q_aksial:.2f} × {e_min:.4f}")
    L(f"    M_total = {M_total:.2f} kN·m")
    L("")
    L(f"  Rasio interaksi P-M (SNI 2847:2019 Pasal 22.4.3.1):")
    L(f"    Q/φPn = {Q_aksial:.2f} / {fPn:,.2f} = {rasio_P:.4f}")
    if rasio_P >= 0.20:
        L(f"    Q/φPn ≥ 0.20 → gunakan: Q/φPn + (8/9)×M/φMn ≤ 1.0")
    else:
        L(f"    Q/φPn < 0.20 → gunakan: Q/(2φPn) + M/φMn ≤ 1.0")
    L(f"    {rumus_PM}")
    L(f"    = {rasio_PM:.4f}")

    kontrol_PM = (f"OK ✓ ({rasio_PM:.3f} ≤ 1.0)"
                  if rasio_PM <= 1.0
                  else f"TIDAK OK ✗ ({rasio_PM:.3f} > 1.0 — perlu perkuat tiang)")
    L(f"  Kontrol: {kontrol_PM}")
    L("")

    # ── RINGKASAN ─────────────────────────────────────────────
    L("=" * 60)
    L("RINGKASAN PEMERIKSAAN KELANGSINGAN")
    L("=" * 60)
    L(f"  1. L/D = {LD:.2f}  (batas {batas_LD})          → {kontrol_LD.split('—')[0].strip()}")
    L(f"  2. Le  = {Le_final:.3f} m                         → ─")
    L(f"  3. SF_tekuk = {SF_euler:.2f}  (min {SF_TEKUK_MIN:.1f})      → {('OK ✓' if SF_euler>=SF_TEKUK_MIN else 'TIDAK OK ✗')}")
    L(f"  4. kLu/r = {kLu_r:.1f}                           → {kontrol_kolom.split('(')[0].strip()}")
    L(f"  5. Rasio P-M = {rasio_PM:.3f}                    → {kontrol_PM.split('(')[0].strip()}")

    # Status keseluruhan
    semua_ok = all([
        "OK" in kontrol_LD and "TIDAK" not in kontrol_LD,
        SF_euler >= SF_TEKUK_MIN,
        klu_status in ("diabaikan", "amplifikasi"),
        rasio_PM <= 1.0,
    ])
    status_akhir = "✅ SEMUA PEMERIKSAAN LULUS" if semua_ok else "⚠️ ADA ITEM YANG PERLU DITINJAU"
    L("")
    L(f"  STATUS KESELURUHAN: {status_akhir}")

    return {
        # Rasio L/D
        "LD_ratio":      round(LD, 2),
        "batas_LD":      batas_LD,
        "kontrol_LD":    kontrol_LD,
        # Panjang tekuk
        "T_atau_R":      round(T_ref, 3),
        "Le_dom":        round(Le_dom, 3),
        "k_faktor":      k_faktor,
        "Le_final":      round(Le_final, 3),
        "tiang_panjang": tiang_panjang,
        # Euler
        "EI_eff":        round(EI_eff, 0),
        "Pcr":           round(Pcr, 2),
        "SF_euler":      round(SF_euler, 2),
        "kontrol_euler": kontrol_euler,
        # Kolom langsing
        "r":             round(r, 4),
        "kLu_r":         round(kLu_r, 2),
        "klu_status":    klu_status,
        "kontrol_kolom": kontrol_kolom,
        # Interaksi P-M
        "fPn":           round(fPn, 2),
        "fMn":           round(fMn, 2),
        "M_total":       round(M_total, 2),
        "rasio_PM":      round(rasio_PM, 4),
        "kontrol_PM":    kontrol_PM,
        # Summary
        "status_akhir":  status_akhir,
        "semua_ok":      semua_ok,
        "Q_aksial":      round(Q_aksial, 2),
        "M_lateral":     round(M_lateral, 2),
        # Langkah
        "langkah":       langkah,
    }
