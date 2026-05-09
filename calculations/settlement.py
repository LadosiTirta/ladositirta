# calculations/settlement.py
# Perhitungan penurunan (settlement) pondasi tiang dalam
#
# Metode:
#   1. Vesic (1977)  — penurunan elastis tiang tunggal
#   2. Meyerhof (1976) — dari SPT-N langsung
#   3. Randolph & Wroth (1978) — load transfer analysis
#
# Acuan: SNI 8460:2017, Vesic (1977), Das (2010) "Principles of Foundation Engineering"

import numpy as np


GAMMA_AIR = 9.81  # kN/m³


def hitung_settlement(
    param_tiang: dict,
    hasil_tekan: dict,
    df_tanah,
    Q_kerja: float | None = None,  # beban kerja (kN); jika None pakai Qijin
) -> dict:
    """
    Menghitung penurunan tiang tunggal di bawah beban kerja.

    Komponen penurunan (Vesic 1977):
        s_total = s_e + s_s + s_p
        s_e = penurunan elastis tiang (kompresi batang)
        s_s = penurunan dari transfer beban selimut
        s_p = penurunan dari end bearing

    Parameter:
        param_tiang : dict dari input_handler
        hasil_tekan : dict dari bearing_capacity.hitung_kapasitas_tiang()
        df_tanah    : DataFrame data tanah
        Q_kerja     : beban kerja (kN); default = Qijin tekan

    Mengembalikan dict hasil + langkah perhitungan
    """
    from calculations.soil_profile import hitung_profil_tanah, lapisan_dalam_tiang
    from utils.soil_converter import PARAM_TIPIKAL
    from utils.input_handler import KOLOM_TANAH

    langkah = []
    langkah.append("=" * 55)
    langkah.append("PERHITUNGAN PENURUNAN TIANG (SETTLEMENT)")
    langkah.append("=" * 55)
    langkah.append("Metode: Vesic (1977) + Meyerhof (1976)")
    langkah.append("")

    # ── Parameter dasar ──────────────────────────────────────
    L    = param_tiang["kedalaman"]       # m
    D    = param_tiang["diameter"]        # m
    Ab   = param_tiang["area_ujung"]      # m²
    p    = param_tiang["keliling"]        # m
    fc   = param_tiang.get("fc_prime", 33.2)  # MPa
    maw  = param_tiang["muka_air"]

    # Modulus elastisitas tiang
    if param_tiang["is_hpile"]:
        Ep = 200_000_000.0   # kPa (baja)
    else:
        Ep = 4700 * np.sqrt(fc) * 1000  # kPa (beton, ACI)
    Ap = Ab  # luas penampang = luas ujung (solid)

    # Beban kerja
    Q = Q_kerja if Q_kerja is not None else hasil_tekan["Qijin_tekan"]
    Qp = hasil_tekan["Qpoint"]     # beban di ujung (proporsi)
    Qs = hasil_tekan["Qskin"]      # beban selimut total

    # Proporsi beban di ujung vs selimut
    Qult = hasil_tekan["Qult_tekan"]
    rasio_p = Qp / max(Qult, 1.0)
    rasio_s = Qs / max(Qult, 1.0)

    Qwp = Q * rasio_p   # beban kerja ke ujung
    Qws = Q * rasio_s   # beban kerja ke selimut

    langkah.append(f"   Beban kerja (Q)        : {Q:.2f} kN")
    langkah.append(f"   Qijin tekan            : {hasil_tekan['Qijin_tekan']:.2f} kN")
    langkah.append(f"   Proporsi end bearing   : {rasio_p*100:.1f}%  → Qwp = {Qwp:.2f} kN")
    langkah.append(f"   Proporsi skin friction : {rasio_s*100:.1f}%  → Qws = {Qws:.2f} kN")
    langkah.append(f"   Modulus elastis tiang  : Ep = {Ep/1000:.0f} MPa")
    langkah.append(f"   Panjang tiang          : L  = {L:.2f} m")
    langkah.append(f"   Diameter tiang         : D  = {D:.4f} m")
    langkah.append("")

    # ── Komponen 1: Kompresi elastis batang tiang (se) ───────
    # se = (Qwp + ξ × Qws) × L / (Ap × Ep)
    # ξ = 0.5 untuk distribusi skin friction seragam (Vesic 1977)
    xi = 0.5
    se = (Qwp + xi * Qws) * L / (Ap * Ep) * 1000  # mm

    langkah.append("   ─── Komponen 1: Kompresi Elastis Tiang (se) ───")
    langkah.append(f"   Rumus: se = (Qwp + ξ·Qws) × L / (Ap × Ep)")
    langkah.append(f"   ξ = {xi} (distribusi skin friction seragam, Vesic 1977)")
    langkah.append(f"   se = ({Qwp:.2f} + {xi}×{Qws:.2f}) × {L:.2f} / ({Ap:.4f} × {Ep:.0f})")
    langkah.append(f"      = {se:.3f} mm")
    langkah.append("")

    # ── Komponen 2: Penurunan dari skin friction (ss) ────────
    # ss = (Qws / (p × L)) × (D / Es_avg)
    # Es_avg = modulus tanah rata-rata sepanjang tiang (kPa)
    semua_lap = hitung_profil_tanah(df_tanah, maw)
    lap_tiang = lapisan_dalam_tiang(semua_lap, L)

    Es_vals = []
    for lap in lap_tiang:
        jenis = lap["jenis"]
        # Cari modulus dari PARAM_TIPIKAL
        p_tip = None
        for k, v in PARAM_TIPIKAL.items():
            if k.lower() in jenis.lower() or jenis.lower() in k.lower():
                p_tip = v; break
        if p_tip is None:
            p_tip = PARAM_TIPIKAL["Lempung sedang"]
        # Gunakan Es atau Eu
        Es_lap = p_tip.get("Es", p_tip.get("Eu", 8000))
        # Koreksi dari Cu aktual jika ada
        if lap["cu"] > 0 and "Eu" in p_tip:
            Es_lap = max(lap["cu"] * 200, 1000)  # Eu ≈ 200 × Cu (Ladd 1977)
        Es_vals.append(Es_lap * lap["tebal"])

    Es_avg = sum(Es_vals) / L if L > 0 else 10000

    Cws = 2 + 0.35 * np.sqrt(L / D)  # koefisien Vesic
    ss  = (Qws / (p * L)) * (D / Es_avg) * Cws * 1000  # mm
    ss  = max(ss, 0.0)

    langkah.append("   ─── Komponen 2: Penurunan Skin Friction (ss) ───")
    langkah.append(f"   Es rata-rata sepanjang tiang: Es_avg = {Es_avg:.0f} kPa")
    langkah.append(f"   Koefisien Vesic: Cws = 2 + 0.35√(L/D) = {Cws:.3f}")
    langkah.append(f"   ss = (Qws/p·L) × (D/Es_avg) × Cws")
    langkah.append(f"      = ({Qws:.2f}/{p:.4f}×{L:.2f}) × ({D:.4f}/{Es_avg:.0f}) × {Cws:.3f}")
    langkah.append(f"      = {ss:.3f} mm")
    langkah.append("")

    # ── Komponen 3: Penurunan end bearing (sp) ───────────────
    # sp = (Qwp × Cwp) / (D × qp)
    # qp = unit end bearing (kPa) = Qpoint / Ab
    # Cwp = 0.85 (Vesic 1977)
    Cwp   = 0.85
    qp_unit = max(Qp / Ab, 1.0)   # kPa
    sp    = (Qwp * Cwp) / (D * qp_unit) * 1000  # mm → hati-hati satuan
    # Formula alternatif yang lebih stabil: sp = Cwp × Qwp / (Ab × Es_ujung)
    lap_ujung = lap_tiang[-1] if lap_tiang else None
    if lap_ujung:
        jenis_u = lap_ujung["jenis"]
        p_tip_u = None
        for k, v in PARAM_TIPIKAL.items():
            if k.lower() in jenis_u.lower() or jenis_u.lower() in k.lower():
                p_tip_u = v; break
        Es_ujung = p_tip_u.get("Es", p_tip_u.get("Eu", 10000)) if p_tip_u else 10000
        if lap_ujung["cu"] > 0:
            Es_ujung = max(lap_ujung["cu"] * 200, 2000)
    else:
        Es_ujung = 15000

    sp = Cwp * Qwp / (Ab * Es_ujung) * 1000  # mm
    sp = max(sp, 0.0)

    langkah.append("   ─── Komponen 3: Penurunan End Bearing (sp) ───")
    langkah.append(f"   Modulus tanah ujung: Es_ujung = {Es_ujung:.0f} kPa")
    langkah.append(f"   Koefisien Vesic: Cwp = {Cwp}")
    langkah.append(f"   sp = Cwp × Qwp / (Ab × Es_ujung)")
    langkah.append(f"      = {Cwp} × {Qwp:.2f} / ({Ab:.4f} × {Es_ujung:.0f})")
    langkah.append(f"      = {sp:.3f} mm")
    langkah.append("")

    # ── Metode alternatif: Meyerhof dari SPT ─────────────────
    # s_spt = Q / (N_avg × B × Cs)  (Meyerhof 1976)
    lap_tiang_list = lap_tiang if lap_tiang else semua_lap
    N_avg = np.mean([l["spt"] for l in lap_tiang_list]) if lap_tiang_list else 10
    N_avg = max(N_avg, 1)
    Cs    = 57.5  # koefisien Meyerhof (kN/m/pukulan) untuk tiang bored; 115 untuk driven
    if param_tiang["is_displacement"]:
        Cs = 115.0
    s_spt = Q / (N_avg * D * Cs) * 25.4  # mm (konversi dari inch)
    s_spt = max(s_spt, 0.0)

    langkah.append("   ─── Metode Alternatif: Meyerhof (1976) dari SPT ───")
    langkah.append(f"   N_avg sepanjang tiang     : {N_avg:.1f} pukulan")
    langkah.append(f"   Koefisien Cs              : {Cs:.0f} (tiang {'driven' if param_tiang['is_displacement'] else 'bored'})")
    langkah.append(f"   s_spt = Q / (N_avg × D × Cs) × 25.4")
    langkah.append(f"         = {Q:.2f} / ({N_avg:.1f} × {D:.4f} × {Cs:.0f}) × 25.4")
    langkah.append(f"         = {s_spt:.3f} mm")
    langkah.append("")

    # ── Total penurunan ──────────────────────────────────────
    s_total_vesic = se + ss + sp

    langkah.append("=" * 55)
    langkah.append("   RINGKASAN PENURUNAN")
    langkah.append("=" * 55)
    langkah.append(f"   se (kompresi elastis tiang) = {se:.3f} mm")
    langkah.append(f"   ss (skin friction)          = {ss:.3f} mm")
    langkah.append(f"   sp (end bearing)            = {sp:.3f} mm")
    langkah.append(f"   ─────────────────────────────────────")
    langkah.append(f"   s_total (Vesic)             = {s_total_vesic:.3f} mm")
    langkah.append(f"   s_total (Meyerhof/SPT)      = {s_spt:.3f} mm")
    langkah.append("")

    # Batas penurunan izin (SNI 8460:2017 Pasal 8)
    s_izin_umum   = 25.0   # mm (umum)
    s_izin_rangka = 50.0   # mm (struktur rangka)
    kontrol_vesic  = "OK ✓" if s_total_vesic <= s_izin_umum else "PERLU DIKAJI ⚠️"
    kontrol_spt    = "OK ✓" if s_spt         <= s_izin_umum else "PERLU DIKAJI ⚠️"

    langkah.append(f"   Batas penurunan izin (SNI 8460) : {s_izin_umum} mm (umum)")
    langkah.append(f"   Kontrol Vesic  : {s_total_vesic:.2f} mm ≤ {s_izin_umum} mm → {kontrol_vesic}")
    langkah.append(f"   Kontrol SPT    : {s_spt:.2f} mm ≤ {s_izin_umum} mm → {kontrol_spt}")

    return {
        "Q_kerja":        round(Q, 2),
        "se_mm":          round(se, 3),
        "ss_mm":          round(ss, 3),
        "sp_mm":          round(sp, 3),
        "s_total_vesic":  round(s_total_vesic, 3),
        "s_meyerhof":     round(s_spt, 3),
        "s_izin_umum":    s_izin_umum,
        "Es_avg":         round(Es_avg, 0),
        "Es_ujung":       round(Es_ujung, 0),
        "N_avg":          round(N_avg, 1),
        "kontrol_vesic":  kontrol_vesic,
        "kontrol_spt":    kontrol_spt,
        "langkah":        langkah,
    }
