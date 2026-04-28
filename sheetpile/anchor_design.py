"""
================================================================================
anchor_design.py
================================================================================
Modul desain sistem angkur dan strut / bracing untuk turap (sheet pile).

Tipe sistem yang dihitung:
    1. Tie Rod (batang angkur tarik)      — batang baja bulat / ulir
    2. Waling / Capping Beam              — balok distribusi gaya angkur
    3. Deadman Anchor (angkur pelat)      — pelat / dinding beton / baja di tanah
    4. Strut / Bracing (pengaku tekan)    — batang tekan horizontal / miring

Referensi utama:
    [R1]  AISC Steel Construction Manual, 16th Ed., Ch. E (tekan), Ch. J (sambungan)
    [R2]  SNI 1729:2020 — Spesifikasi Bangunan Gedung Baja Struktural, Ps. E dan J
    [R3]  NAVFAC DM-7.02 — Ch. 3, Section 3.3 (Anchor Systems), Hal. 3-21 s/d 3-35
    [R4]  USS Sheet Pile Design Manual (1975), Ch. 5 (Anchor Design)
    [R5]  Teng, W.C. (1962). Foundation Design. Prentice-Hall. Ch. 5
    [R6]  Ovesen, N.K. & Stromann, H. (1972). Deadman anchors in sand.
          Proc. 5th ECSMFE, Vol. 1, Hal. 543-554.
    [R7]  Das, B.M. — Principles of Foundation Engineering, 8th Ed., Ch. 9.7-9.9
    [R8]  SNI 8460:2017, Pasal 9.7 (angkur turap)

Konvensi variabel (tanpa simbol Yunani):
    Ra              = gaya angkur per meter lebar turap     [kN/m]
    T_angkur        = gaya angkur per titik angkur          [kN]
    spasi_angkur    = jarak antar angkur                    [m]
    fy_batang       = tegangan leleh batang angkur          [MPa]
    sigma_ijin_tarik= tegangan ijin tarik batang            [MPa]
    A_req           = luas penampang batang perlu           [mm2]
    diameter_min    = diameter minimum batang               [mm]
    SF_angkur       = faktor keamanan angkur                [-]
    lambda_langsing = rasio kelangsingan strut              [-]

Satuan: kN, m, mm, MPa, kN.m
Teks  : plain text kompatibel Word & PDF
        pi ditulis 3.14159, akar ditulis sqrt(...)

Penulis  : Structural Civil Engineer — Pabrik Beton Pracetak, Jabodetabek
Versi    : 1.0.0
================================================================================
"""

from __future__ import annotations

import math
import os
from typing import Any

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch


# ─────────────────────────────────────────────────────────────────────────────
# KONSTANTA DESAIN
# ─────────────────────────────────────────────────────────────────────────────

PI                   : float = math.pi        # 3.14159...
PI_TEKS              : str   = "3.14159"      # untuk tampilan teks

SF_ANGKUR_MIN        : float = 2.0    # SF minimum untuk angkur (NAVFAC DM-7.02)
FAKTOR_SIGMA_TARIK   : float = 0.60   # sigma_ijin = 0.60 * fy (ASD, AISC J3)
FAKTOR_SIGMA_TEKAN   : float = 0.60   # sigma_ijin tekan awal (sebelum koreksi lambda)

LAMBDA_MAKS_STRUT    : float = 200.0  # kelangsingan maks strut (AISC E2, SNI 1729)
LAMBDA_MAKS_TARIK    : float = 300.0  # kelangsingan maks tie rod (AISC)
FAKTOR_PANJANG_K     : float = 1.0    # faktor panjang efektif (jepit-jepit = 0.5;
                                       # sendi-sendi = 1.0; konservatif pakai 1.0)

# Mutu baja standar yang digunakan di Indonesia
MUTU_BAJA: dict = {
    "BJ37"        : {"fy": 240, "fu": 370,  "E": 200000, "nama": "SNI BJ37"},
    "BJ41"        : {"fy": 250, "fu": 410,  "E": 200000, "nama": "SNI BJ41"},
    "BJ50"        : {"fy": 290, "fu": 500,  "E": 200000, "nama": "SNI BJ50"},
    "A36"         : {"fy": 250, "fu": 400,  "E": 200000, "nama": "ASTM A36"},
    "A572-Gr50"   : {"fy": 345, "fu": 450,  "E": 200000, "nama": "ASTM A572 Gr.50"},
    "A572-Gr60"   : {"fy": 415, "fu": 520,  "E": 200000, "nama": "ASTM A572 Gr.60"},
    "A193-B7"     : {"fy": 724, "fu": 862,  "E": 200000, "nama": "ASTM A193-B7 (tie rod mutu tinggi)"},
    "Dywidag-1030": {"fy": 835, "fu": 1030, "E": 200000, "nama": "Dywidag Threadbar Gr. 1030"},
}

# Diameter standar batang baja (mm) — sesuai pasaran Indonesia
DIAMETER_STANDAR: list[float] = [
    12, 14, 16, 19, 22, 25, 28, 32, 36, 40,
    45, 50, 56, 63, 70, 75, 80, 90, 100,
]

# Profil WF standar Indonesia untuk waling dan strut (subset)
# Format: tipe -> {Ix, Sx, A, rx, ry, berat, tw, bf, tf}  satuan cm
PROFIL_WF: dict = {
    "WF200x100" : {"Ix":1840,  "Sx":184,  "A":26.7,  "rx":8.29,  "ry":2.24, "berat":21.0, "d_mm":200, "bf_mm":100, "tf_mm":8.0,  "tw_mm":4.5},
    "WF250x125" : {"Ix":4050,  "Sx":324,  "A":36.97, "rx":10.5,  "ry":2.78, "berat":29.0, "d_mm":250, "bf_mm":125, "tf_mm":9.5,  "tw_mm":6.0},
    "WF300x150" : {"Ix":7210,  "Sx":481,  "A":46.78, "rx":12.4,  "ry":3.38, "berat":36.7, "d_mm":300, "bf_mm":150, "tf_mm":9.5,  "tw_mm":6.5},
    "WF350x175" : {"Ix":13600, "Sx":771,  "A":63.14, "rx":14.7,  "ry":3.99, "berat":49.6, "d_mm":350, "bf_mm":175, "tf_mm":11.0, "tw_mm":7.0},
    "WF400x200" : {"Ix":23700, "Sx":1190, "A":84.12, "rx":16.8,  "ry":4.54, "berat":66.0, "d_mm":400, "bf_mm":200, "tf_mm":13.0, "tw_mm":8.0},
    "WF450x200" : {"Ix":33500, "Sx":1490, "A":96.00, "rx":18.7,  "ry":4.20, "berat":75.0, "d_mm":450, "bf_mm":200, "tf_mm":14.0, "tw_mm":9.0},
    "WF500x200" : {"Ix":47800, "Sx":1910, "A":114.2, "rx":20.5,  "ry":4.18, "berat":89.7, "d_mm":500, "bf_mm":200, "tf_mm":16.0, "tw_mm":10.0},
    "WF600x200" : {"Ix":75600, "Sx":2520, "A":134.4, "rx":23.7,  "ry":4.11, "berat":106.0,"d_mm":600, "bf_mm":200, "tf_mm":17.0, "tw_mm":11.0},
    "H250x250"  : {"Ix":10700, "Sx":860,  "A":92.18, "rx":10.8,  "ry":6.26, "berat":72.4, "d_mm":250, "bf_mm":250, "tf_mm":14.0, "tw_mm":9.0},
    "H300x300"  : {"Ix":20400, "Sx":1360, "A":119.8, "rx":13.1,  "ry":7.51, "berat":94.0, "d_mm":300, "bf_mm":300, "tf_mm":15.0, "tw_mm":10.0},
    "H350x350"  : {"Ix":40300, "Sx":2300, "A":173.9, "rx":15.2,  "ry":8.84, "berat":137.0,"d_mm":350, "bf_mm":350, "tf_mm":19.0, "tw_mm":12.0},
}


# ─────────────────────────────────────────────────────────────────────────────
# FUNGSI PEMBANTU FORMAT
# ─────────────────────────────────────────────────────────────────────────────

def _garis(karakter: str = "-", lebar: int = 64) -> str:
    return karakter * lebar


def _header(judul: str) -> list[str]:
    lebar = 64
    return [_garis("=", lebar), f"  {judul.upper()}", _garis("=", lebar)]


def _sub(label: str, nilai: str) -> str:
    return f"  {label:<22}: {nilai}"


def _ok(kondisi: bool) -> str:
    return "OK  [MEMENUHI]" if kondisi else "TIDAK OK  [PERLU REVISI]"


def _hasil_dict(
    nilai    : Any,
    langkah  : list[str],
    referensi: list[str],
    satuan   : str,
    status   : str = "",
) -> dict:
    return {
        "nilai"    : nilai,
        "langkah"  : langkah,
        "referensi": referensi,
        "satuan"   : satuan,
        "status"   : status,
    }


def format_langkah(langkah: list[str]) -> str:
    """Gabungkan list langkah untuk st.code() atau st.text() di Streamlit."""
    return "\n".join(langkah)


def _diameter_standar_berikutnya(diameter_min_mm: float) -> float:
    """
    Pilih diameter standar berikutnya (>=) dari daftar pasaran Indonesia.
    """
    for d in DIAMETER_STANDAR:
        if d >= diameter_min_mm:
            return d
    return math.ceil(diameter_min_mm / 5) * 5   # fallback pembulatan ke atas 5mm


def _luas_lingkaran(diameter_mm: float) -> float:
    """Luas penampang lingkaran [mm2] dari diameter [mm]."""
    return PI * (diameter_mm / 2) ** 2


# ─────────────────────────────────────────────────────────────────────────────
# 1. DESAIN TIE ROD (BATANG ANGKUR TARIK)
# ─────────────────────────────────────────────────────────────────────────────

def desain_tie_rod(
    Ra              : float,
    spasi_angkur    : float,
    fy_batang       : float,
    fu_batang       : float       = 0.0,
    nama_material   : str         = "BJ41",
    faktor_sigma    : float       = FAKTOR_SIGMA_TARIK,
    SF_min          : float       = SF_ANGKUR_MIN,
    panjang_tie_rod : float | None = None,
) -> dict:
    """
    Desain batang angkur tarik (tie rod) untuk turap dengan angkur.

    Prinsip:
        Tie rod bekerja sebagai batang tarik aksial murni.
        Didesain dengan Allowable Stress Design (ASD).

    Rumus utama:
        T_angkur        = Ra x spasi_angkur
        sigma_ijin_tarik= faktor_sigma x fy_batang    [AISC J3, ASD]
        A_req           = T_angkur / sigma_ijin_tarik
        diameter_min    = sqrt(4 x A_req / pi)
        diameter_pakai  = standar terdekat >= diameter_min

    Referensi:
        [R1] AISC Steel Construction Manual, 16th Ed., Table J3.2 (ASD)
        [R2] SNI 1729:2020, Pasal J3.6 (kekuatan tarik batang)
        [R3] NAVFAC DM-7.02, Section 3.3, Hal. 3-23
        [R4] USS Sheet Pile Design Manual (1975), Ch. 5, Hal. 5-2 s/d 5-7

    Parameter:
        Ra               : gaya angkur dari Tahap 2 [kN/m]
        spasi_angkur     : jarak antar angkur [m]
        fy_batang        : tegangan leleh batang [MPa]
        fu_batang        : tegangan tarik ultimate [MPa] (opsional, untuk info)
        nama_material    : label mutu baja
        faktor_sigma     : faktor tegangan ijin (default 0.60)
        SF_min           : faktor keamanan minimum (default 2.0)
        panjang_tie_rod  : panjang tie rod [m] (untuk cek kelangsingan)

    Return:
        dict standar; "nilai" berisi:
            {T_angkur, sigma_ijin_tarik, A_req, diameter_min,
             diameter_pakai, A_pakai, T_kapasitas, SF, aman}
    """
    if Ra <= 0:
        raise ValueError(f"Ra harus > 0, diberikan: {Ra} kN/m")
    if spasi_angkur <= 0:
        raise ValueError(f"spasi_angkur harus > 0, diberikan: {spasi_angkur} m")
    if fy_batang <= 0:
        raise ValueError(f"fy_batang harus > 0, diberikan: {fy_batang} MPa")

    # ── Langkah 1: Gaya angkur per titik ─────────────────────────────────────
    T_angkur = Ra * spasi_angkur    # kN

    # ── Langkah 2: Tegangan ijin tarik ───────────────────────────────────────
    sigma_ijin_tarik = faktor_sigma * fy_batang    # MPa = N/mm2

    # ── Langkah 3: Luas penampang perlu ──────────────────────────────────────
    T_angkur_N = T_angkur * 1000               # N
    A_req      = T_angkur_N / sigma_ijin_tarik  # mm2

    # ── Langkah 4: Diameter minimum ──────────────────────────────────────────
    diameter_min  = math.sqrt(4.0 * A_req / PI)   # mm
    diameter_pakai = _diameter_standar_berikutnya(diameter_min)

    # ── Langkah 5: Verifikasi ────────────────────────────────────────────────
    A_pakai     = _luas_lingkaran(diameter_pakai)  # mm2
    T_kapasitas = A_pakai * sigma_ijin_tarik / 1000   # kN
    SF          = T_kapasitas / T_angkur
    aman        = SF >= SF_min

    # ── Kelangsingan (jika panjang diberikan) ─────────────────────────────────
    r_gir           = diameter_pakai / 4.0          # jari-jari girasi lingkaran = d/4
    lambda_cek_info: list[str] = []
    if panjang_tie_rod is not None and panjang_tie_rod > 0:
        panjang_eff   = FAKTOR_PANJANG_K * panjang_tie_rod * 1000   # mm
        lambda_langsing = panjang_eff / r_gir
        aman_lambda   = lambda_langsing <= LAMBDA_MAKS_TARIK
        lambda_cek_info = [
            "",
            _garis("-"),
            "  KONTROL KELANGSINGAN TIE ROD",
            _garis("-"),
            "  Rumus   : lambda_langsing = (K x L) / r_gir",
            f"  Nilai   : K (faktor panjang efektif) = {FAKTOR_PANJANG_K:.1f}",
            f"            L (panjang tie rod)         = {panjang_tie_rod:.2f} m = {panjang_tie_rod*1000:.1f} mm",
            f"            r_gir (lingkaran)           = diameter / 4",
            f"                                        = {diameter_pakai:.1f} / 4",
            f"                                        = {r_gir:.3f} mm",
            f"  Hitung  : K x L = {FAKTOR_PANJANG_K:.1f} x {panjang_tie_rod*1000:.1f}",
            f"                  = {panjang_eff:.1f} mm",
            f"            lambda_langsing = {panjang_eff:.1f} / {r_gir:.3f}",
            f"  Hasil   : lambda_langsing = {lambda_langsing:.2f}",
            f"  Syarat  : lambda_langsing <= {LAMBDA_MAKS_TARIK:.0f}  (AISC E2, batang tarik)",
            f"  Status  : {_ok(aman_lambda)}",
            _sub("  Standar", "AISC 16th Ed., Pasal D1 (kelangsingan batang tarik)"),
            _sub("  ",        "SNI 1729:2020, Pasal D1"),
        ]

    langkah: list[str] = [
        *_header("Desain Tie Rod — Batang Angkur Tarik"),
        "",
        "  Prinsip: Tie rod bekerja sebagai batang tarik aksial murni.",
        "           Didesain dengan metode Allowable Stress Design (ASD).",
        "",
        "  Data input:",
        _sub("  Ra",             f"{Ra:.4f} kN/m  (gaya angkur per meter lebar dari Tahap 2)"),
        _sub("  spasi_angkur",   f"{spasi_angkur:.3f} m"),
        _sub("  fy_batang",      f"{fy_batang:.1f} MPa"),
        _sub("  fu_batang",      f"{fu_batang:.1f} MPa" if fu_batang > 0 else "tidak diberikan"),
        _sub("  nama_material",  nama_material),
        _sub("  faktor_sigma",   f"{faktor_sigma:.2f}"),
        _sub("  SF_min",         f"{SF_min:.2f}"),
        "",
        _garis("-"),
        "  LANGKAH 1 — Gaya angkur per titik (T_angkur)",
        _garis("-"),
        "  Rumus   : T_angkur = Ra x spasi_angkur",
        f"  Nilai   : Ra           = {Ra:.4f} kN/m",
        f"            spasi_angkur = {spasi_angkur:.3f} m",
        f"  Hitung  : T_angkur = {Ra:.4f} x {spasi_angkur:.3f}",
        f"  Hasil   : T_angkur = {T_angkur:.4f} kN",
        _sub("  Satuan",  "kN"),
        _sub("  Standar", "NAVFAC DM-7.02, Section 3.3, Hal. 3-23"),
        _sub("  ",        "USS Sheet Pile Design Manual (1975), Ch. 5, Hal. 5-2"),
        "",
        _garis("-"),
        "  LANGKAH 2 — Tegangan ijin tarik (sigma_ijin_tarik)",
        _garis("-"),
        "  Rumus   : sigma_ijin_tarik = faktor_sigma x fy_batang",
        f"  Nilai   : faktor_sigma = {faktor_sigma:.2f}  (ASD, AISC Table J3.2)",
        f"            fy_batang    = {fy_batang:.1f} MPa",
        f"  Hitung  : sigma_ijin_tarik = {faktor_sigma:.2f} x {fy_batang:.1f}",
        f"  Hasil   : sigma_ijin_tarik = {sigma_ijin_tarik:.2f} MPa",
        _sub("  Satuan",  "MPa"),
        _sub("  Standar", "AISC Steel Construction Manual, 16th Ed., Table J3.2 (ASD)"),
        _sub("  ",        "SNI 1729:2020, Pasal J3.6"),
        "",
        _garis("-"),
        "  LANGKAH 3 — Luas penampang batang perlu (A_req)",
        _garis("-"),
        "  Rumus   : A_req = T_angkur / sigma_ijin_tarik",
        f"  Nilai   : T_angkur            = {T_angkur:.4f} kN",
        f"            T_angkur [N]        = {T_angkur:.4f} x 1000 = {T_angkur_N:.2f} N",
        f"            sigma_ijin_tarik    = {sigma_ijin_tarik:.2f} N/mm2",
        f"  Hitung  : A_req = {T_angkur_N:.2f} / {sigma_ijin_tarik:.2f}",
        f"  Hasil   : A_req = {A_req:.4f} mm2",
        _sub("  Satuan",  "mm2"),
        "",
        _garis("-"),
        "  LANGKAH 4 — Diameter batang minimum",
        _garis("-"),
        "  Rumus   : A_req = pi x diameter_min^2 / 4",
        "            diameter_min = sqrt(4 x A_req / pi)",
        f"  Nilai   : A_req = {A_req:.4f} mm2",
        f"            pi   = {PI_TEKS}",
        f"  Hitung  : 4 x A_req  = 4 x {A_req:.4f} = {4*A_req:.4f}",
        f"            4 x A_req / pi = {4*A_req:.4f} / {PI_TEKS} = {4*A_req/PI:.4f}",
        f"            diameter_min = sqrt({4*A_req/PI:.4f})",
        f"  Hasil   : diameter_min = {diameter_min:.4f} mm",
        _sub("  Satuan",  "mm"),
        "",
        _garis("-"),
        "  LANGKAH 5 — Pilih diameter standar",
        _garis("-"),
        f"  diameter_min = {diameter_min:.4f} mm",
        "  Daftar diameter standar (mm):",
        f"  {DIAMETER_STANDAR}",
        f"  Pilih diameter standar berikutnya >= {diameter_min:.2f} mm:",
        f"  Hasil   : diameter_pakai = {diameter_pakai:.1f} mm",
        "",
        _garis("-"),
        "  LANGKAH 6 — Verifikasi kapasitas",
        _garis("-"),
        "  Hitung luas penampang pakai:",
        "  Rumus   : A_pakai = pi x (diameter_pakai / 2)^2",
        f"  Hitung  : A_pakai = {PI_TEKS} x ({diameter_pakai:.1f} / 2)^2",
        f"            A_pakai = {PI_TEKS} x {(diameter_pakai/2)**2:.4f}",
        f"  Hasil   : A_pakai = {A_pakai:.4f} mm2",
        "",
        "  Kapasitas tarik batang:",
        "  Rumus   : T_kapasitas = A_pakai x sigma_ijin_tarik",
        f"  Hitung  : T_kapasitas = {A_pakai:.4f} x {sigma_ijin_tarik:.2f}",
        f"            T_kapasitas = {A_pakai*sigma_ijin_tarik:.2f} N",
        f"            T_kapasitas = {A_pakai*sigma_ijin_tarik:.2f} / 1000",
        f"  Hasil   : T_kapasitas = {T_kapasitas:.4f} kN",
        "",
        "  Faktor keamanan:",
        "  Rumus   : SF = T_kapasitas / T_angkur",
        f"  Hitung  : SF = {T_kapasitas:.4f} / {T_angkur:.4f}",
        f"  Hasil   : SF = {SF:.4f}",
        f"  SF_min  = {SF_min:.2f}  (NAVFAC DM-7.02)",
        f"  Status  : {_ok(aman)}",
        *lambda_cek_info,
        "",
        _garis("-"),
        "  RANGKUMAN TIE ROD",
        _garis("-"),
        f"  T_angkur        = {T_angkur:.4f} kN  per titik angkur",
        f"  sigma_ijin_tarik= {sigma_ijin_tarik:.2f} MPa",
        f"  A_req           = {A_req:.4f} mm2",
        f"  diameter_min    = {diameter_min:.4f} mm",
        f"  diameter_pakai  = {diameter_pakai:.1f} mm  (standar)",
        f"  A_pakai         = {A_pakai:.4f} mm2",
        f"  T_kapasitas     = {T_kapasitas:.4f} kN",
        f"  SF              = {SF:.4f}  --> {_ok(aman)}",
        "",
        _sub("  Standar", "AISC Steel Construction Manual, 16th Ed., Table J3.2 dan Pasal J3.6"),
        _sub("  ",        "SNI 1729:2020, Pasal J3.6"),
        _sub("  ",        "NAVFAC DM-7.02, Section 3.3, Hal. 3-23 s/d 3-27"),
        _sub("  ",        "USS Sheet Pile Design Manual (1975), Ch. 5, Hal. 5-2 s/d 5-7"),
        _garis("="),
    ]

    referensi = [
        "AISC Steel Construction Manual, 16th Ed., Table J3.2 dan Pasal J3.6",
        "SNI 1729:2020, Pasal J3.6",
        "NAVFAC DM-7.02, Section 3.3, Hal. 3-23 s/d 3-27",
        "USS Sheet Pile Design Manual (1975), Ch. 5, Hal. 5-2 s/d 5-7",
    ]

    return _hasil_dict(
        nilai={
            "T_angkur"        : round(T_angkur,         4),
            "sigma_ijin_tarik": round(sigma_ijin_tarik,  3),
            "A_req"           : round(A_req,             4),
            "diameter_min"    : round(diameter_min,      4),
            "diameter_pakai"  : diameter_pakai,
            "A_pakai"         : round(A_pakai,           4),
            "T_kapasitas"     : round(T_kapasitas,       4),
            "SF"              : round(SF,                4),
            "aman"            : aman,
        },
        langkah   = langkah,
        referensi = referensi,
        satuan    = "kN (T), mm (diameter), mm2 (A)",
        status    = _ok(aman),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. DESAIN WALING / CAPPING BEAM
# ─────────────────────────────────────────────────────────────────────────────

def desain_waling(
    Ra           : float,
    spasi_angkur : float,
    fy_waling    : float        = 250.0,
    profil_filter: str | None   = None,
    tipe_beban   : str          = "menerus",
    faktor_sigma : float        = FAKTOR_SIGMA_TARIK,
) -> dict:
    """
    Desain profil waling (balok distribusi gaya angkur di sepanjang turap).

    Waling berfungsi mendistribusikan gaya reaksi angkur yang terpusat
    menjadi gaya merata sepanjang turap.

    Model struktural:
        - Beban merata: w = Ra  [kN/m]
        - Tumpuan: pada titik-titik angkur, berjarak spasi_angkur

        Momen lentur maksimum:
            Balok sederhana (satu bentang): M_waling = Ra * spasi^2 / 8
            Balok menerus (lebih dari 2 bentang): M_waling = Ra * spasi^2 / 10
            Konservatif (pakai tumpuan sederhana):  M_waling = Ra * spasi^2 / 8

    Referensi:
        [R3] NAVFAC DM-7.02, Section 3.3.4, Hal. 3-29
        [R4] USS Sheet Pile Design Manual (1975), Ch. 5, Hal. 5-8 s/d 5-12
        [R7] Das, B.M., 8th Ed., Ch. 9.10

    Parameter:
        Ra            : gaya angkur dari Tahap 2 [kN/m]
        spasi_angkur  : jarak antar angkur [m]
        fy_waling     : tegangan leleh waling [MPa]
        profil_filter : filter nama profil WF (misal "WF300", None = semua)
        tipe_beban    : "sederhana" (M = wL2/8) atau "menerus" (M = wL2/10)
        faktor_sigma  : faktor tegangan ijin (default 0.60)

    Return:
        dict standar
    """
    if Ra <= 0 or spasi_angkur <= 0:
        raise ValueError("Ra dan spasi_angkur harus > 0")

    # ── Momen lentur waling ───────────────────────────────────────────────────
    w = Ra     # kN/m (beban merata = gaya angkur per meter)

    if tipe_beban == "menerus":
        faktor_M    = 10.0
        label_model = "balok menerus (lebih dari 2 bentang)"
        rumus_M     = "M_waling = Ra x spasi_angkur^2 / 10"
    else:
        faktor_M    = 8.0
        label_model = "balok sederhana (1 bentang)"
        rumus_M     = "M_waling = Ra x spasi_angkur^2 / 8"

    M_waling = w * spasi_angkur**2 / faktor_M    # kN.m

    # ── Tegangan ijin dan S_req ───────────────────────────────────────────────
    sigma_allow   = faktor_sigma * fy_waling      # MPa
    M_waling_Nmm  = M_waling * 1e6               # N.mm
    S_req_mm3     = M_waling_Nmm / sigma_allow    # mm3
    S_req_cm3     = S_req_mm3 / 1000             # cm3

    # ── Pilih profil WF ───────────────────────────────────────────────────────
    kandidat_waling = []
    for nama, prop in PROFIL_WF.items():
        if profil_filter and profil_filter.upper() not in nama.upper():
            continue
        if prop["Sx"] >= S_req_cm3:
            kandidat_waling.append((nama, prop))
    kandidat_waling.sort(key=lambda x: x[1]["Sx"])

    profil_terpilih = None
    rasio_S         = None
    aman            = False
    if kandidat_waling:
        profil_terpilih = (kandidat_waling[0][0], kandidat_waling[0][1])
        rasio_S         = profil_terpilih[1]["Sx"] / S_req_cm3
        aman            = rasio_S >= 1.0

    langkah: list[str] = [
        *_header("Desain Waling — Balok Distribusi Angkur"),
        "",
        "  Fungsi  : Mendistribusikan gaya angkur terpusat menjadi gaya merata.",
        f"  Model   : {label_model}",
        "  Beban   : merata w = Ra sepanjang waling",
        "",
        "  Data input:",
        _sub("  Ra",           f"{Ra:.4f} kN/m  (gaya angkur per meter turap)"),
        _sub("  spasi_angkur", f"{spasi_angkur:.3f} m"),
        _sub("  fy_waling",    f"{fy_waling:.1f} MPa"),
        _sub("  tipe_beban",   tipe_beban),
        "",
        _garis("-"),
        "  LANGKAH 1 — Momen lentur waling",
        _garis("-"),
        f"  Rumus   : {rumus_M}",
        f"  Nilai   : Ra           = {Ra:.4f} kN/m  (beban merata w = Ra)",
        f"            spasi_angkur = {spasi_angkur:.3f} m",
        f"  Hitung  : M_waling = {w:.4f} x {spasi_angkur:.3f}^2 / {faktor_M:.0f}",
        f"                     = {w:.4f} x {spasi_angkur**2:.4f} / {faktor_M:.0f}",
        f"                     = {w * spasi_angkur**2:.4f} / {faktor_M:.0f}",
        f"  Hasil   : M_waling = {M_waling:.4f} kN.m",
        _sub("  Satuan",  "kN.m"),
        _sub("  Standar", "NAVFAC DM-7.02, Section 3.3.4, Hal. 3-29"),
        _sub("  ",        "USS Sheet Pile Design Manual (1975), Ch. 5, Hal. 5-8"),
        "",
        _garis("-"),
        "  LANGKAH 2 — Tegangan ijin dan modulus penampang perlu (S_req)",
        _garis("-"),
        "  Rumus   : sigma_allow = faktor_sigma x fy_waling",
        f"            S_req = M_waling / sigma_allow",
        f"  Nilai   : faktor_sigma = {faktor_sigma:.2f}",
        f"            fy_waling    = {fy_waling:.1f} MPa",
        f"  Hitung  : sigma_allow  = {faktor_sigma:.2f} x {fy_waling:.1f}",
        f"                         = {sigma_allow:.2f} MPa",
        f"            M_waling [N.mm] = {M_waling:.4f} x 10^6 = {M_waling_Nmm:.2f} N.mm",
        f"            S_req = {M_waling_Nmm:.2f} / {sigma_allow:.2f}",
        f"                  = {S_req_mm3:.2f} mm3",
        f"  Hasil   : S_req = {S_req_cm3:.2f} cm3",
        _sub("  Satuan",  "cm3"),
        _sub("  Standar", "AISC Steel Construction Manual, 16th Ed., Section F11.1"),
        "",
        _garis("-"),
        "  LANGKAH 3 — Pilih profil WF waling",
        _garis("-"),
        f"  S_req = {S_req_cm3:.2f} cm3 — cari profil WF dengan Sx >= S_req",
        "",
    ]

    if kandidat_waling:
        lw_t = 12; lw_s = 10; lw_b = 12; lw_d = 10; lw_bf = 10
        header_w = (
            f"  {'Profil':<{lw_t}} {'Sx(cm3)':>{lw_s}} "
            f"{'Berat(kg/m)':>{lw_b}} {'d(mm)':>{lw_d}} {'bf(mm)':>{lw_bf}}"
        )
        garis_w = "  " + "-" * (len(header_w) - 2)
        langkah += [header_w, garis_w]

        for nm, pr in kandidat_waling[:6]:
            tanda = "  <-- TERPILIH" if nm == profil_terpilih[0] else ""
            langkah.append(
                f"  {nm:<{lw_t}} {pr['Sx']:>{lw_s}.1f} "
                f"{pr['berat']:>{lw_b}.1f} {pr['d_mm']:>{lw_d}.0f} "
                f"{pr['bf_mm']:>{lw_bf}.0f}{tanda}"
            )
        langkah.append(garis_w)

        nm_t = profil_terpilih[0]
        pr_t = profil_terpilih[1]
        M_kap = pr_t["Sx"] * 1000 * sigma_allow / 1e6    # kN.m

        langkah += [
            "",
            _garis("-"),
            "  LANGKAH 4 — Verifikasi profil terpilih",
            _garis("-"),
            f"  Profil terpilih : {nm_t}",
            f"  Sx_pakai        = {pr_t['Sx']:.1f} cm3",
            f"  S_req           = {S_req_cm3:.2f} cm3",
            "  Rumus   : rasio_S = Sx_pakai / S_req",
            f"  Hitung  : rasio_S = {pr_t['Sx']:.1f} / {S_req_cm3:.2f}",
            f"  Hasil   : rasio_S = {rasio_S:.4f}",
            f"  Syarat  : rasio_S >= 1.00",
            f"  Status  : {_ok(aman)}",
            "",
            f"  Kapasitas momen waling:",
            f"  Rumus   : M_kapasitas = Sx_pakai x sigma_allow",
            f"  Hitung  : M_kapasitas = {pr_t['Sx']:.1f} x 1000 mm3 x {sigma_allow:.2f} N/mm2",
            f"                       = {pr_t['Sx'] * 1000 * sigma_allow:.0f} N.mm",
            f"                       = {M_kap:.4f} kN.m",
            f"  M_waling= {M_waling:.4f} kN.m",
            f"  Margin  = {M_kap - M_waling:.4f} kN.m",
        ]

    else:
        langkah += [
            "  Tidak ada profil WF yang memenuhi dalam tabel.",
            f"  S_req = {S_req_cm3:.2f} cm3 — tambahkan profil atau gunakan material lebih kuat.",
        ]
        aman = False

    langkah += [
        "",
        _garis("-"),
        "  RANGKUMAN WALING",
        _garis("-"),
        f"  M_waling    = {M_waling:.4f} kN.m",
        f"  sigma_allow = {sigma_allow:.2f} MPa",
        f"  S_req       = {S_req_cm3:.2f} cm3",
    ]
    if profil_terpilih:
        langkah += [
            f"  Profil      = {profil_terpilih[0]}",
            f"  Sx_pakai    = {profil_terpilih[1]['Sx']:.1f} cm3",
            f"  rasio_S     = {rasio_S:.4f}  --> {_ok(aman)}",
        ]

    langkah += [
        "",
        _sub("  Standar", "NAVFAC DM-7.02, Section 3.3.4, Hal. 3-29"),
        _sub("  ",        "USS Sheet Pile Design Manual (1975), Ch. 5, Hal. 5-8 s/d 5-12"),
        _sub("  ",        "AISC Steel Construction Manual, 16th Ed., Section F11.1"),
        _garis("="),
    ]

    referensi = [
        "NAVFAC DM-7.02, Section 3.3.4, Hal. 3-29",
        "USS Sheet Pile Design Manual (1975), Ch. 5, Hal. 5-8 s/d 5-12",
        "AISC Steel Construction Manual, 16th Ed., Section F11.1",
        "SNI 1729:2020, Pasal F2",
    ]

    return _hasil_dict(
        nilai={
            "M_waling"       : round(M_waling,    4),
            "sigma_allow"    : round(sigma_allow,  3),
            "S_req"          : round(S_req_cm3,    3),
            "profil_terpilih": profil_terpilih,
            "rasio_S"        : round(rasio_S, 4) if rasio_S else None,
            "aman"           : aman,
        },
        langkah   = langkah,
        referensi = referensi,
        satuan    = "kN.m (M), cm3 (S)",
        status    = _ok(aman),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. DESAIN DEADMAN ANCHOR (ANGKUR PELAT)
# ─────────────────────────────────────────────────────────────────────────────

def desain_deadman(
    Ra                 : float,
    gamma_tanah        : float,
    phi_tanah          : float,
    kedalaman_deadman  : float,
    cohesion_tanah     : float  = 0.0,
    spasi_angkur       : float  = 1.0,
    lebar_pelat        : float | None = None,
    tinggi_pelat       : float  = 0.3,
    metode             : str    = "teng",
    SF_min             : float  = SF_ANGKUR_MIN,
) -> dict:
    """
    Desain angkur pelat (deadman anchor) berdasarkan kapasitas tekanan pasif.

    Metode yang tersedia:
        1. Metode Teng (1962)          — sederhana, konservatif, umum dipakai
        2. Metode Ovesen-Stromann (1972) — untuk pasir, memperhitungkan 3D

    Prinsip Metode Teng (1962):
        Pelat deadman menahan gaya dengan tekanan tanah pasif di depannya.
        Kapasitas pasif per satuan lebar:
            Pp = 0.5 * Kp * gamma * H_deadman^2  (tanah non-kohesif)
            Pp = 0.5 * Kp * gamma * H_deadman^2 + 2*c*sqrt(Kp)*H_deadman (c-phi)

        Kp = tan^2(45 + phi/2)

        Panjang pelat minimum (L_deadman):
            L_deadman = T_angkur / (Pp * SF_min)

    Syarat posisi deadman (tidak terganggu zona aktif turap):
        Jarak horisontal deadman dari turap >= 1.5 * H  (NAVFAC DM-7.02)

    Referensi:
        [R5] Teng, W.C. (1962). Foundation Design. Prentice-Hall, Ch. 5.
        [R6] Ovesen, N.K. & Stromann, H. (1972). Proc. 5th ECSMFE, Vol. 1.
        [R3] NAVFAC DM-7.02, Section 3.4, Hal. 3-30 s/d 3-35
        [R4] USS Sheet Pile Design Manual (1975), Ch. 5, Hal. 5-13 s/d 5-22
        [R7] Das, B.M., 8th Ed., Ch. 9.7

    Parameter:
        Ra                : gaya angkur per meter lebar [kN/m]
        gamma_tanah       : berat volume tanah di sekitar deadman [kN/m3]
        phi_tanah         : sudut geser dalam tanah [derajat]
        kedalaman_deadman : kedalaman pusat deadman dari permukaan [m]
        cohesion_tanah    : kohesi tanah [kPa] (default 0)
        spasi_angkur      : spasi antar angkur [m] (untuk gaya per titik)
        lebar_pelat       : lebar (tinggi) pelat deadman [m] (None = dihitung)
        tinggi_pelat      : tinggi pelat deadman [m] (default 0.3 m)
        metode            : "teng" atau "ovesen"
        SF_min            : faktor keamanan minimum (default 2.0)

    Return:
        dict standar
    """
    if Ra <= 0:
        raise ValueError(f"Ra harus > 0, diberikan: {Ra}")
    if gamma_tanah <= 0:
        raise ValueError(f"gamma_tanah harus > 0, diberikan: {gamma_tanah}")
    if not (0 <= phi_tanah < 90):
        raise ValueError(f"phi_tanah harus 0-89 derajat, diberikan: {phi_tanah}")
    if kedalaman_deadman <= 0:
        raise ValueError(f"kedalaman_deadman harus > 0, diberikan: {kedalaman_deadman}")

    T_angkur = Ra * spasi_angkur    # kN per angkur

    # ── Koefisien tekanan pasif (Rankine) ────────────────────────────────────
    Kp       = math.tan(math.radians(45.0 + phi_tanah / 2.0)) ** 2
    sqrt_Kp  = math.sqrt(Kp)
    H_dm     = kedalaman_deadman     # kedalaman pusat deadman

    # ── Metode Teng (1962) ────────────────────────────────────────────────────
    if metode.lower() == "teng":
        # Tekanan pasif rata-rata di kedalaman H_dm, unit kN/m2
        # Asumsi pelat dari muka tanah s/d kedalaman H_dm (konsisten dengan Teng)
        sigma_p_bawah = Kp * gamma_tanah * H_dm + 2 * cohesion_tanah * sqrt_Kp
        sigma_p_atas  = 0.0   # di permukaan = 0 (untuk tanah non-kohesif)
        # Kapasitas pasif per satuan lebar (N/m^2 * m = kN/m)
        Pp_per_m   = 0.5 * Kp * gamma_tanah * H_dm**2 + 2 * cohesion_tanah * sqrt_Kp * H_dm
        # Kapasitas ijin per satuan lebar
        Pp_ijin    = Pp_per_m / SF_min        # kN/m (per meter lebar deadman)

        # Panjang minimum pelat deadman
        L_deadman  = T_angkur / Pp_ijin       # m

        catatan_metode = [
            "  Metode Teng (1962) — deadman sebagai dinding penahan pasif.",
            "  Rumus   : Pp_per_m = 0.5 x Kp x gamma x H^2 + 2 x c x sqrt(Kp) x H",
            f"  Nilai   : Kp           = {Kp:.4f}",
            f"            gamma_tanah  = {gamma_tanah:.2f} kN/m3",
            f"            H_deadman    = {H_dm:.3f} m",
            f"            cohesion     = {cohesion_tanah:.2f} kPa",
            f"            sqrt(Kp)     = {sqrt_Kp:.4f}",
            f"  Hitung  : 0.5 x Kp x gamma x H^2 = 0.5 x {Kp:.4f} x {gamma_tanah:.2f} x {H_dm**2:.4f}",
            f"                                    = {0.5*Kp*gamma_tanah*H_dm**2:.4f} kN/m",
            f"            2 x c x sqrt(Kp) x H    = 2 x {cohesion_tanah:.2f} x {sqrt_Kp:.4f} x {H_dm:.3f}",
            f"                                    = {2*cohesion_tanah*sqrt_Kp*H_dm:.4f} kN/m",
            f"  Hasil   : Pp_per_m = {Pp_per_m:.4f} kN/m",
            f"            Pp_ijin  = {Pp_per_m:.4f} / {SF_min:.2f} = {Pp_ijin:.4f} kN/m  (per meter lebar deadman)",
        ]
        SF_dm = Pp_per_m / (Ra * SF_min / SF_min)   # SF aktual = Pp / Ra (per meter)
        SF_actual = Pp_per_m / Ra if Ra > 0 else 0

    else:
        # Metode Ovesen-Stromann (pasir, phi > 0)
        # Faktor Fc (shape factor) = 1 + (B/H) (Ovesen-Stromann simplifikasi)
        B_pelat = lebar_pelat if lebar_pelat else spasi_angkur
        Fc      = 1.0 + B_pelat / H_dm     # faktor 3D
        Pp_per_m = (0.5 * Kp * gamma_tanah * H_dm**2) * Fc + 2 * cohesion_tanah * sqrt_Kp * H_dm
        Pp_ijin  = Pp_per_m / SF_min
        L_deadman = T_angkur / Pp_ijin

        catatan_metode = [
            "  Metode Ovesen-Stromann (1972) — memperhitungkan efek 3D pelat.",
            "  Rumus   : Pp = (0.5 x Kp x gamma x H^2) x Fc + 2 x c x sqrt(Kp) x H",
            f"            Fc = 1 + B_pelat/H  (faktor 3D)",
            f"  Nilai   : B_pelat = {B_pelat:.3f} m  (lebar pelat = spasi angkur)",
            f"            Fc     = 1 + {B_pelat:.3f}/{H_dm:.3f} = {Fc:.4f}",
            f"  Hasil   : Pp_per_m = {Pp_per_m:.4f} kN/m",
            f"            Pp_ijin  = {Pp_ijin:.4f} kN/m  (per meter lebar deadman)",
        ]
        SF_actual = Pp_per_m / Ra if Ra > 0 else 0

    aman = SF_actual >= SF_min

    langkah: list[str] = [
        *_header(f"Desain Deadman Anchor — Metode {metode.capitalize()}"),
        "",
        "  Fungsi  : Pelat / dinding beton-baja yang menahan gaya angkur",
        "            melalui tekanan pasif tanah di depannya.",
        "",
        "  Data input:",
        _sub("  Ra",                 f"{Ra:.4f} kN/m"),
        _sub("  spasi_angkur",       f"{spasi_angkur:.3f} m"),
        _sub("  T_angkur",           f"{T_angkur:.4f} kN  (= Ra x spasi)"),
        _sub("  gamma_tanah",        f"{gamma_tanah:.2f} kN/m3"),
        _sub("  phi_tanah",          f"{phi_tanah:.2f} derajat"),
        _sub("  cohesion_tanah",     f"{cohesion_tanah:.2f} kPa"),
        _sub("  kedalaman_deadman",  f"{H_dm:.3f} m dari permukaan"),
        _sub("  SF_min",             f"{SF_min:.2f}"),
        "",
        _garis("-"),
        "  LANGKAH 1 — Koefisien tekanan pasif (Kp)",
        _garis("-"),
        "  Rumus   : Kp = tan^2(45 + phi/2)",
        f"  Nilai   : phi_tanah = {phi_tanah:.2f} derajat",
        f"  Hitung  : 45 + phi/2 = 45 + {phi_tanah:.2f}/2 = {45 + phi_tanah/2:.4f} derajat",
        f"            tan({45+phi_tanah/2:.4f} derajat) = {math.tan(math.radians(45+phi_tanah/2)):.6f}",
        f"  Hasil   : Kp = {math.tan(math.radians(45+phi_tanah/2)):.6f}^2 = {Kp:.6f}",
        _sub("  Standar", "SNI 8460:2017, Pasal 5.3.3"),
        "",
        _garis("-"),
        f"  LANGKAH 2 — Kapasitas pasif deadman ({metode.upper()})",
        _garis("-"),
        *catatan_metode,
        "",
        _garis("-"),
        "  LANGKAH 3 — Panjang minimum pelat deadman (L_deadman)",
        _garis("-"),
        "  Rumus   : L_deadman = T_angkur / Pp_ijin",
        f"  Nilai   : T_angkur = {T_angkur:.4f} kN",
        f"            Pp_ijin  = {Pp_ijin:.4f} kN/m",
        f"  Hitung  : L_deadman = {T_angkur:.4f} / {Pp_ijin:.4f}",
        f"  Hasil   : L_deadman = {L_deadman:.4f} m  (panjang minimum pelat deadman)",
        _sub("  Satuan",  "m"),
        "",
        _garis("-"),
        "  LANGKAH 4 — Faktor keamanan aktual",
        _garis("-"),
        "  Rumus   : SF = Pp_per_m / Ra",
        f"  Hitung  : SF = {Pp_per_m:.4f} / {Ra:.4f}",
        f"  Hasil   : SF = {SF_actual:.4f}",
        f"  SF_min  = {SF_min:.2f}  (NAVFAC DM-7.02)",
        f"  Status  : {_ok(aman)}",
        "",
        _garis("-"),
        "  SYARAT POSISI DEADMAN",
        _garis("-"),
        "  Deadman harus ditempatkan di luar zona keruntuhan aktif turap.",
        "  Jarak horisontal minimum dari turap (NAVFAC DM-7.02):",
        "  Rumus   : jarak_min = 1.5 x H_galian",
        "  Catatan : H_galian = tinggi turap di atas galian (diisi dari data proyek)",
        "            Pastikan deadman berada di luar garis 45 derajat dari ujung turap.",
        "",
        _garis("-"),
        "  RANGKUMAN DEADMAN",
        _garis("-"),
        f"  T_angkur      = {T_angkur:.4f} kN",
        f"  Kp            = {Kp:.6f}",
        f"  Pp_per_m      = {Pp_per_m:.4f} kN/m",
        f"  Pp_ijin       = {Pp_ijin:.4f} kN/m",
        f"  L_deadman     = {L_deadman:.4f} m  (panjang minimum)",
        f"  SF aktual     = {SF_actual:.4f}  --> {_ok(aman)}",
        "",
        _sub("  Standar", f"Teng, W.C. (1962). Foundation Design. Ch. 5." if metode=="teng"
             else "Ovesen & Stromann (1972). Proc. 5th ECSMFE, Vol. 1."),
        _sub("  ",        "NAVFAC DM-7.02, Section 3.4, Hal. 3-30 s/d 3-35"),
        _sub("  ",        "USS Sheet Pile Design Manual (1975), Ch. 5, Hal. 5-13 s/d 5-22"),
        _sub("  ",        "Das, B.M., 8th Ed., Ch. 9.7"),
        _garis("="),
    ]

    referensi = [
        "Teng, W.C. (1962). Foundation Design. Prentice-Hall, Ch. 5.",
        "Ovesen, N.K. & Stromann, H. (1972). Proc. 5th ECSMFE, Vol. 1.",
        "NAVFAC DM-7.02, Section 3.4, Hal. 3-30 s/d 3-35",
        "USS Sheet Pile Design Manual (1975), Ch. 5, Hal. 5-13 s/d 5-22",
        "Das, B.M., Principles of Foundation Engineering, 8th Ed., Ch. 9.7",
    ]

    return _hasil_dict(
        nilai={
            "T_angkur"   : round(T_angkur,   4),
            "Kp"         : round(Kp,          6),
            "Pp_per_m"   : round(Pp_per_m,    4),
            "Pp_ijin"    : round(Pp_ijin,     4),
            "L_deadman"  : round(L_deadman,   4),
            "SF_actual"  : round(SF_actual,   4),
            "aman"       : aman,
        },
        langkah   = langkah,
        referensi = referensi,
        satuan    = "m (L_deadman), kN/m (Pp)",
        status    = _ok(aman),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. DESAIN STRUT / BRACING (PENGAKU TEKAN)
# ─────────────────────────────────────────────────────────────────────────────

def desain_strut(
    Ra              : float,
    spasi_strut     : float,
    panjang_strut   : float,
    fy_strut        : float       = 250.0,
    E_baja          : float       = 200000.0,
    profil_filter   : str | None  = None,
    faktor_K        : float       = FAKTOR_PANJANG_K,
    SF_min          : float       = SF_ANGKUR_MIN,
    sudut_derajat   : float       = 0.0,
) -> dict:
    """
    Desain strut (pengaku tekan horisontal / miring) untuk galian.

    Strut bekerja sebagai batang tekan (kolom pendek-menengah).
    Kapasitas tekan perlu memperhitungkan efek kelangsingan (slenderness).

    Rumus AISC Chapter E (ASD — pendekatan):
        F_cr (pendekatan ASD) = sigma_ijin_tekan * faktor_kelangsingan

        Untuk lambda_c <= 1.5 (kelangsingan kecil):
            Fcr = [0.658^(lambda_c^2)] x fy
            Tegangan ijin = Fcr / 1.67  (AISC E1, ASD faktor = 1.67)

        lambda_c = (K x L / r) / (pi x sqrt(E/fy))   [parameter kelangsingan]

        F_cr disederhanakan untuk ASD:
            sigma_ijin_tekan = fy * [1 - (K*L/r)^2 / (2 * (pi^2 * E / fy))]  jika lambda <= lambda_r
            sigma_ijin_tekan = pi^2 * E / (K*L/r)^2                            jika lambda > lambda_r

    Referensi:
        [R1] AISC Steel Construction Manual, 16th Ed., Chapter E (Tekan)
        [R2] SNI 1729:2020, Pasal E3 (Kekuatan tekan batang)
        [R3] NAVFAC DM-7.02, Section 3.3.3, Hal. 3-28
        [R4] USS Sheet Pile Design Manual (1975), Ch. 5, Hal. 5-23

    Parameter:
        Ra             : gaya angkur per meter lebar [kN/m]
        spasi_strut    : jarak antar strut [m]
        panjang_strut  : panjang strut (jarak antar dinding) [m]
        fy_strut       : tegangan leleh strut [MPa]
        E_baja         : modulus elastisitas baja [MPa] (default 200000)
        profil_filter  : filter seri profil (misal "H300", None = semua)
        faktor_K       : faktor panjang efektif (default 1.0 = sendi-sendi)
        SF_min         : faktor keamanan minimum (default 2.0)
        sudut_derajat  : sudut kemiringan strut dari horisontal [derajat] (default 0)

    Return:
        dict standar
    """
    if Ra <= 0 or spasi_strut <= 0 or panjang_strut <= 0:
        raise ValueError("Ra, spasi_strut, panjang_strut harus > 0")

    # ── Gaya tekan strut ──────────────────────────────────────────────────────
    # Jika strut miring, komponen aksial = T / cos(sudut)
    if abs(sudut_derajat) > 1e-6:
        cos_sudut = math.cos(math.radians(sudut_derajat))
        T_aksial  = (Ra * spasi_strut) / cos_sudut
        catatan_sudut = (
            f"Strut miring {sudut_derajat:.1f} derajat, "
            f"T_aksial = T_horisontal / cos({sudut_derajat:.1f}) = "
            f"{Ra*spasi_strut:.4f} / {cos_sudut:.4f}"
        )
    else:
        T_aksial  = Ra * spasi_strut
        catatan_sudut = "Strut horisontal (sudut = 0 derajat)"

    P_strut = T_aksial    # kN (gaya tekan)

    # ── Pilih profil — iterasi dari terkecil ──────────────────────────────────
    profil_memenuhi = []
    for nama, prop in PROFIL_WF.items():
        if profil_filter and profil_filter.upper() not in nama.upper():
            continue

        # Jari-jari girasi minimum (ry untuk sumbu lemah)
        r_min_cm  = prop["ry"]       # cm
        r_min_mm  = r_min_cm * 10    # mm

        # Kelangsingan
        K_L_mm        = faktor_K * panjang_strut * 1000   # mm
        lambda_sr     = K_L_mm / r_min_mm                  # kelangsingan

        if lambda_sr > LAMBDA_MAKS_STRUT:
            continue   # terlalu langsing, skip

        # lambda_c (parameter kelangsingan AISC/SNI)
        lambda_c = (K_L_mm / r_min_mm) * math.sqrt(fy_strut / (PI**2 * E_baja))

        # Fcr dan sigma_ijin
        if lambda_c <= 1.5:
            Fcr         = (0.658 ** (lambda_c**2)) * fy_strut    # MPa
        else:
            Fcr         = (0.877 / lambda_c**2) * fy_strut       # MPa

        sigma_ijin_tekan = Fcr / 1.67       # ASD faktor = 1.67

        # Kapasitas tekan
        A_cm2     = prop["A"]         # cm2
        A_mm2     = A_cm2 * 100       # mm2
        P_kapasitas = (A_mm2 * sigma_ijin_tekan) / 1000   # kN

        SF = P_kapasitas / P_strut if P_strut > 1e-9 else 999.0

        if SF >= SF_min:
            profil_memenuhi.append({
                "nama"            : nama,
                "prop"            : prop,
                "lambda_sr"       : lambda_sr,
                "lambda_c"        : lambda_c,
                "Fcr"             : Fcr,
                "sigma_ijin_tekan": sigma_ijin_tekan,
                "A_mm2"           : A_mm2,
                "P_kapasitas"     : P_kapasitas,
                "SF"              : SF,
            })

    # Urutkan dari paling ringan (berat per meter)
    profil_memenuhi.sort(key=lambda x: x["prop"]["berat"])

    profil_terpilih = profil_memenuhi[0] if profil_memenuhi else None
    aman = profil_terpilih is not None

    # ── Susun langkah ─────────────────────────────────────────────────────────
    langkah: list[str] = [
        *_header("Desain Strut / Bracing — Batang Tekan"),
        "",
        "  Fungsi  : Pengaku tekan horisontal / miring antar dua dinding turap.",
        "            Bekerja sebagai batang tekan (kolom).",
        "",
        "  Data input:",
        _sub("  Ra",             f"{Ra:.4f} kN/m"),
        _sub("  spasi_strut",    f"{spasi_strut:.3f} m"),
        _sub("  panjang_strut",  f"{panjang_strut:.3f} m  (jarak antar dinding)"),
        _sub("  fy_strut",       f"{fy_strut:.1f} MPa"),
        _sub("  E_baja",         f"{E_baja:.0f} MPa"),
        _sub("  faktor_K",       f"{faktor_K:.2f}  (panjang efektif)"),
        _sub("  sudut",          f"{sudut_derajat:.1f} derajat  ({catatan_sudut})"),
        _sub("  SF_min",         f"{SF_min:.2f}"),
        "",
        _garis("-"),
        "  LANGKAH 1 — Gaya tekan per strut (P_strut)",
        _garis("-"),
        "  Rumus   : P_strut = Ra x spasi_strut  (jika horisontal)",
        f"  Nilai   : Ra          = {Ra:.4f} kN/m",
        f"            spasi_strut = {spasi_strut:.3f} m",
        f"            {catatan_sudut}",
        f"  Hitung  : P_strut = {Ra:.4f} x {spasi_strut:.3f}",
        f"                    = {Ra*spasi_strut:.4f} kN",
        f"  Hasil   : P_strut = {P_strut:.4f} kN  (gaya tekan aksial)",
        _sub("  Satuan",  "kN"),
        _sub("  Standar", "NAVFAC DM-7.02, Section 3.3.3, Hal. 3-28"),
        "",
        _garis("-"),
        "  LANGKAH 2 — Evaluasi profil (kelangsingan + kapasitas tekan AISC E)",
        _garis("-"),
        "  Rumus kelangsingan:",
        "    lambda_sr = (K x L) / r_min",
        "    lambda_c  = lambda_sr / (pi x sqrt(E/fy))  [parameter AISC]",
        "",
        "  Rumus kekuatan tekan kritis (Fcr):",
        "    Jika lambda_c <= 1.5:  Fcr = 0.658^(lambda_c^2) x fy",
        "    Jika lambda_c >  1.5:  Fcr = (0.877 / lambda_c^2) x fy",
        "    sigma_ijin_tekan = Fcr / 1.67  (ASD, AISC E1)",
        "",
        f"  K x L = {faktor_K:.2f} x {panjang_strut:.3f} m = {faktor_K*panjang_strut:.3f} m",
        "",
    ]

    # Tabel hasil evaluasi semua profil
    lw_n = 14; lw_sr = 12; lw_lc = 10; lw_fc = 14; lw_si = 14; lw_pk = 14; lw_sf = 10
    header_p = (
        f"  {'Profil':<{lw_n}} {'lambda_sr':>{lw_sr}} {'lambda_c':>{lw_lc}} "
        f"{'Fcr(MPa)':>{lw_fc}} {'sig_ij(MPa)':>{lw_si}} {'P_kap(kN)':>{lw_pk}} {'SF':>{lw_sf}}"
    )
    garis_p  = "  " + "-" * (len(header_p) - 2)
    langkah += [header_p, garis_p]

    # Evaluasi semua profil yang tidak terlalu langsing
    semua_eval = []
    for nama, prop in PROFIL_WF.items():
        if profil_filter and profil_filter.upper() not in nama.upper():
            continue
        r_min_cm = prop["ry"]; r_min_mm = r_min_cm * 10
        K_L_mm   = faktor_K * panjang_strut * 1000
        lambda_sr = K_L_mm / r_min_mm
        if lambda_sr > LAMBDA_MAKS_STRUT:
            semua_eval.append((nama, prop, lambda_sr, None, None, None, None, "TERLALU LANGSING"))
            continue
        lambda_c = (K_L_mm / r_min_mm) * math.sqrt(fy_strut / (PI**2 * E_baja))
        Fcr = (0.658**lambda_c**2)*fy_strut if lambda_c <= 1.5 else (0.877/lambda_c**2)*fy_strut
        sig_ij = Fcr / 1.67
        Pkap   = (prop["A"] * 100 * sig_ij) / 1000
        SF_val = Pkap / P_strut
        semua_eval.append((nama, prop, lambda_sr, lambda_c, Fcr, sig_ij, Pkap, f"SF={SF_val:.2f}"))

    semua_eval.sort(key=lambda x: x[1]["berat"])

    for row in semua_eval[:10]:
        nm, pr, lsr, lc, fcr, sij, pkap, ket = row
        tanda = ""
        if profil_terpilih and nm == profil_terpilih["nama"]:
            tanda = "  <-- TERPILIH"
        if lc is None:
            langkah.append(
                f"  {nm:<{lw_n}} {lsr:>{lw_sr}.1f} {'--':>{lw_lc}} "
                f"{'--':>{lw_fc}} {'--':>{lw_si}} {'--':>{lw_pk}} "
                f"{'LANGSING':>{lw_sf}}"
            )
        else:
            langkah.append(
                f"  {nm:<{lw_n}} {lsr:>{lw_sr}.1f} {lc:>{lw_lc}.4f} "
                f"{fcr:>{lw_fc}.2f} {sij:>{lw_si}.2f} {pkap:>{lw_pk}.2f} "
                f"{ket:>{lw_sf}}{tanda}"
            )

    langkah.append(garis_p)

    if profil_terpilih:
        pt = profil_terpilih
        langkah += [
            "",
            _garis("-"),
            "  LANGKAH 3 — Detail profil terpilih",
            _garis("-"),
            f"  Profil terpilih  : {pt['nama']}",
            f"  Luas (A)         = {pt['prop']['A']:.2f} cm2 = {pt['A_mm2']:.2f} mm2",
            f"  r_min (ry)       = {pt['prop']['ry']:.3f} cm = {pt['prop']['ry']*10:.3f} mm",
            f"  lambda_sr        = {pt['lambda_sr']:.4f}  (harus <= {LAMBDA_MAKS_STRUT:.0f})",
            f"  lambda_c         = {pt['lambda_c']:.6f}",
            f"  Fcr              = {pt['Fcr']:.4f} MPa",
            f"  sigma_ijin_tekan = {pt['sigma_ijin_tekan']:.4f} MPa",
            f"  P_kapasitas      = {pt['P_kapasitas']:.4f} kN",
            f"  P_strut          = {P_strut:.4f} kN",
            f"  SF               = {pt['SF']:.4f}  --> {_ok(pt['SF'] >= SF_min)}",
        ]
    else:
        langkah += [
            "",
            "  TIDAK ADA profil yang memenuhi!",
            f"  P_strut = {P_strut:.4f} kN, SF_min = {SF_min:.2f}",
            "  Saran: kurangi spasi_strut, tambah profil berat, atau pakai pipa baja.",
        ]

    langkah += [
        "",
        _garis("-"),
        "  RANGKUMAN STRUT",
        _garis("-"),
        f"  P_strut         = {P_strut:.4f} kN",
        f"  K x L           = {faktor_K * panjang_strut:.3f} m",
    ]
    if profil_terpilih:
        pt = profil_terpilih
        langkah += [
            f"  Profil          = {pt['nama']}",
            f"  lambda_sr       = {pt['lambda_sr']:.2f}  (batas: {LAMBDA_MAKS_STRUT:.0f})",
            f"  sigma_ijin_tekan= {pt['sigma_ijin_tekan']:.2f} MPa",
            f"  P_kapasitas     = {pt['P_kapasitas']:.2f} kN",
            f"  SF              = {pt['SF']:.4f}  --> {_ok(pt['SF'] >= SF_min)}",
        ]
    langkah += [
        "",
        _sub("  Standar", "AISC Steel Construction Manual, 16th Ed., Chapter E"),
        _sub("  ",        "SNI 1729:2020, Pasal E3"),
        _sub("  ",        "NAVFAC DM-7.02, Section 3.3.3, Hal. 3-28"),
        _sub("  ",        "USS Sheet Pile Design Manual (1975), Ch. 5, Hal. 5-23"),
        _garis("="),
    ]

    referensi = [
        "AISC Steel Construction Manual, 16th Ed., Chapter E",
        "SNI 1729:2020, Pasal E3 (Kekuatan tekan batang)",
        "NAVFAC DM-7.02, Section 3.3.3, Hal. 3-28",
        "USS Sheet Pile Design Manual (1975), Ch. 5, Hal. 5-23",
    ]

    return _hasil_dict(
        nilai={
            "P_strut"        : round(P_strut,          4),
            "profil_terpilih": profil_terpilih,
            "aman"           : aman,
        },
        langkah   = langkah,
        referensi = referensi,
        satuan    = "kN (P), MPa (sigma)",
        status    = _ok(aman),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. RANGKUMAN SISTEM ANGKUR
# ─────────────────────────────────────────────────────────────────────────────

def rangkuman_angkur(
    hasil_tie_rod : dict | None = None,
    hasil_waling  : dict | None = None,
    hasil_deadman : dict | None = None,
    hasil_strut   : dict | None = None,
    nama_proyek   : str         = "Analisis Sistem Angkur Turap",
) -> dict:
    """
    Tabel rangkuman semua komponen sistem angkur.

    Parameter:
        hasil_tie_rod : output dari desain_tie_rod()
        hasil_waling  : output dari desain_waling()
        hasil_deadman : output dari desain_deadman()
        hasil_strut   : output dari desain_strut()
        nama_proyek   : label proyek

    Return:
        dict standar
    """
    lebar_nama  = 28
    lebar_nilai = 18
    lebar_satuan= 14
    lebar_status= 22

    def _baris(label, nilai_str, satuan_str, status_str):
        return (
            f"  {label:<{lebar_nama}} {nilai_str:>{lebar_nilai}} "
            f"{satuan_str:<{lebar_satuan}} {status_str:<{lebar_status}}"
        )

    header = _baris("Komponen", "Nilai", "Satuan", "Status")
    garis  = "  " + "-" * (lebar_nama + lebar_nilai + lebar_satuan + lebar_status + 3)

    langkah: list[str] = [
        *_header(f"Rangkuman Sistem Angkur — {nama_proyek}"),
        "",
        header,
        garis,
    ]

    semua_aman = True

    # ── Tie Rod ───────────────────────────────────────────────────────────────
    if hasil_tie_rod:
        n = hasil_tie_rod["nilai"]
        if not n.get("aman", True):
            semua_aman = False
        langkah.append("")
        langkah.append("  *** TIE ROD ***")
        langkah.append(_baris("T_angkur", f"{n['T_angkur']:.3f}", "kN/titik", ""))
        langkah.append(_baris("diameter_min", f"{n['diameter_min']:.2f}", "mm", ""))
        langkah.append(_baris("diameter_pakai", f"{n['diameter_pakai']:.1f}", "mm", ""))
        langkah.append(_baris("A_pakai", f"{n['A_pakai']:.2f}", "mm2", ""))
        langkah.append(_baris("T_kapasitas", f"{n['T_kapasitas']:.3f}", "kN", ""))
        langkah.append(_baris("SF tie rod", f"{n['SF']:.3f}", "--", _ok(n["SF"] >= SF_ANGKUR_MIN)))

    # ── Waling ────────────────────────────────────────────────────────────────
    if hasil_waling:
        n = hasil_waling["nilai"]
        if not n.get("aman", True):
            semua_aman = False
        pt = n.get("profil_terpilih")
        langkah.append("")
        langkah.append("  *** WALING ***")
        langkah.append(_baris("M_waling", f"{n['M_waling']:.3f}", "kN.m", ""))
        langkah.append(_baris("S_req waling", f"{n['S_req']:.2f}", "cm3", ""))
        if pt:
            langkah.append(_baris("Profil waling", pt[0], "", ""))
            langkah.append(_baris("Sx_pakai", f"{pt[1]['Sx']:.1f}", "cm3", _ok(n.get("aman", False))))

    # ── Deadman ───────────────────────────────────────────────────────────────
    if hasil_deadman:
        n = hasil_deadman["nilai"]
        if not n.get("aman", True):
            semua_aman = False
        langkah.append("")
        langkah.append("  *** DEADMAN ANCHOR ***")
        langkah.append(_baris("Pp_per_m", f"{n['Pp_per_m']:.3f}", "kN/m", ""))
        langkah.append(_baris("L_deadman (min)", f"{n['L_deadman']:.3f}", "m", ""))
        langkah.append(_baris("SF deadman", f"{n['SF_actual']:.3f}", "--", _ok(n["SF_actual"] >= SF_ANGKUR_MIN)))

    # ── Strut ─────────────────────────────────────────────────────────────────
    if hasil_strut:
        n = hasil_strut["nilai"]
        if not n.get("aman", True):
            semua_aman = False
        pt = n.get("profil_terpilih")
        langkah.append("")
        langkah.append("  *** STRUT ***")
        langkah.append(_baris("P_strut", f"{n['P_strut']:.3f}", "kN", ""))
        if pt:
            langkah.append(_baris("Profil strut", pt["nama"], "", ""))
            langkah.append(_baris("lambda_sr", f"{pt['lambda_sr']:.2f}", f"(maks {LAMBDA_MAKS_STRUT:.0f})", ""))
            langkah.append(_baris("P_kapasitas", f"{pt['P_kapasitas']:.3f}", "kN", ""))
            langkah.append(_baris("SF strut", f"{pt['SF']:.3f}", "--", _ok(pt["SF"] >= SF_ANGKUR_MIN)))

    langkah += [
        garis,
        "",
        f"  KESIMPULAN: {'SEMUA AMAN  [OK]' if semua_aman else 'ADA KOMPONEN TIDAK AMAN  [!!]'}",
        "",
        f"  SF_min yang disyaratkan: {SF_ANGKUR_MIN:.2f}  (NAVFAC DM-7.02)",
        "",
        _sub("  Standar", "NAVFAC DM-7.02, Ch. 3, Section 3.3 dan 3.4"),
        _sub("  ",        "USS Sheet Pile Design Manual (1975), Ch. 5"),
        _sub("  ",        "AISC 16th Ed., Ch. J dan E  |  SNI 1729:2020"),
        _garis("="),
    ]

    return _hasil_dict(
        nilai={"semua_aman": semua_aman},
        langkah=langkah,
        referensi=[
            "NAVFAC DM-7.02, Ch. 3, Section 3.3 dan 3.4",
            "USS Sheet Pile Design Manual (1975), Ch. 5",
            "AISC Steel Construction Manual, 16th Ed., Ch. J dan E",
            "SNI 1729:2020, Pasal E3 dan J3",
        ],
        satuan="-",
        status="SEMUA AMAN" if semua_aman else "TIDAK AMAN — PERLU REVISI",
    )


# ─────────────────────────────────────────────────────────────────────────────
# CONTOH PENGGUNAAN — jalankan: python anchor_design.py
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/home/claude")

    print("\n" + "=" * 64)
    print("  CONTOH DESAIN SISTEM ANGKUR TURAP")
    print("  Data tipikal: H=4m, tanah lempung medium Jabodetabek")
    print("=" * 64)

    # Data dari Tahap 2 (Free Earth Support)
    RA           = 45.2     # kN/m  (gaya angkur per meter lebar)
    SPASI        = 2.5      # m     (jarak antar angkur)
    PANJANG_GALIAN = 8.0    # m     (lebar galian = panjang strut)

    # ── 1. Tie Rod ────────────────────────────────────────────────────────────
    print("\n>>> 1. TIE ROD (BJ41, fy=250 MPa)")
    res_tr = desain_tie_rod(
        Ra              = RA,
        spasi_angkur    = SPASI,
        fy_batang       = 250.0,
        fu_batang       = 410.0,
        nama_material   = "BJ41",
        panjang_tie_rod = 5.0,   # m panjang tie rod
    )
    print(format_langkah(res_tr["langkah"]))

    # ── 2. Waling ─────────────────────────────────────────────────────────────
    print("\n>>> 2. WALING (profil WF, BJ37)")
    res_wal = desain_waling(
        Ra           = RA,
        spasi_angkur = SPASI,
        fy_waling    = 240.0,   # BJ37
        tipe_beban   = "menerus",
    )
    print(format_langkah(res_wal["langkah"]))

    # ── 3. Deadman ────────────────────────────────────────────────────────────
    print("\n>>> 3. DEADMAN ANCHOR (metode Teng)")
    res_dm = desain_deadman(
        Ra                = RA,
        gamma_tanah       = 17.0,
        phi_tanah         = 20.0,
        kedalaman_deadman = 2.0,   # m
        cohesion_tanah    = 10.0,  # kPa
        spasi_angkur      = SPASI,
        metode            = "teng",
    )
    print(format_langkah(res_dm["langkah"]))

    # ── 4. Strut ──────────────────────────────────────────────────────────────
    print("\n>>> 4. STRUT (profil H, BJ41)")
    res_st = desain_strut(
        Ra            = RA,
        spasi_strut   = SPASI,
        panjang_strut = PANJANG_GALIAN,
        fy_strut      = 250.0,
        profil_filter = None,
        faktor_K      = 1.0,
    )
    print(format_langkah(res_st["langkah"]))

    # ── 5. Rangkuman ──────────────────────────────────────────────────────────
    print("\n>>> 5. RANGKUMAN SISTEM ANGKUR")
    res_rk = rangkuman_angkur(
        hasil_tie_rod = res_tr,
        hasil_waling  = res_wal,
        hasil_deadman = res_dm,
        hasil_strut   = res_st,
        nama_proyek   = "Turap H=4m, Jabodetabek",
    )
    print(format_langkah(res_rk["langkah"]))
    print(f"\nStatus keseluruhan: {res_rk['status']}")
    print("\nSelesai.")
