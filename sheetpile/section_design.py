"""
================================================================================
section_design.py
================================================================================
Modul desain penampang turap / sheet pile — dua tipe material:
    A. Baja (Steel Sheet Pile)
    B. Beton Pracetak (Precast Concrete Sheet Pile)

Standar yang digunakan:
    BAJA:
    [R1]  AISC Steel Construction Manual, 16th Ed., Chapter F, Section F11
    [R2]  ASTM A328 / A572 / A690 — Sheet Pile Steel Grades
    [R3]  USS Steel Sheet Pile Design Manual (1975), Ch. 4–5
    [R4]  SNI 1729:2020 — Spesifikasi Bangunan Gedung Baja Struktural

    BETON PRACETAK:
    [R5]  SNI 2847:2019 — Persyaratan Beton Struktural (identik ACI 318-19)
    [R6]  SNI 8460:2017 — Persyaratan Perancangan Geoteknik, Pasal 9
    [R7]  PCI Design Handbook, 8th Ed., Ch. 5
    [R8]  ACI 318-19, Chapter 22 (geser), Chapter 24 (lendutan)

Konvensi nama variabel (tanpa simbol Yunani):
    sigma_allow  = tegangan ijin lentur baja           [MPa]
    S_req        = modulus penampang perlu             [cm3/m]
    S_pakai      = modulus penampang profil terpilih   [cm3/m]
    rasio_S      = S_pakai / S_req  (harus >= 1.0)
    phi_lentur   = faktor reduksi kekuatan lentur      [-]
    phi_geser    = faktor reduksi kekuatan geser       [-]
    rho_tulangan = rasio tulangan                      [-]
    rho_min      = rasio tulangan minimum              [-]
    rho_max      = rasio tulangan maksimum             [-]

Satuan output: kN, m, kPa, MPa, cm3, cm4, mm2
Teks output : plain text, kompatibel Word & PDF (tanpa simbol Yunani)

Penulis  : Structural Civil Engineer — Pabrik Beton Pracetak, Jabodetabek
Versi    : 1.0.0
================================================================================
"""

from __future__ import annotations

import math
import csv
import os
from typing import Any

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ─────────────────────────────────────────────────────────────────────────────
# KONSTANTA DESAIN
# ─────────────────────────────────────────────────────────────────────────────

# ── BAJA ─────────────────────────────────────────────────────────────────────
FAKTOR_SIGMA_ALLOW   : float = 0.60    # sigma_allow = 0.60 * fy  (AISC F11)
FAKTOR_BEBAN_BAJA    : float = 1.00    # ASD: tidak ada faktor beban
RASIO_S_MIN          : float = 1.00    # S_pakai / S_req >= 1.0

# ── BETON PRACETAK ────────────────────────────────────────────────────────────
FAKTOR_BEBAN_M       : float = 1.60    # Mu = 1.6 * M_max  (SNI 2847:2019 Ps. 5.3.1c)
FAKTOR_BEBAN_V       : float = 1.60    # Vu = 1.6 * V_max
PHI_LENTUR           : float = 0.90    # SNI 2847:2019, Pasal 21.2.2
PHI_GESER            : float = 0.75    # SNI 2847:2019, Pasal 21.2.1
BETA1_FC_DEFAULT     : float = 0.85    # beta1 untuk fc <= 28 MPa
FAKTOR_0_85_FC       : float = 0.85    # faktor blok tegangan beton
RHO_MIN_ACI          : float = 0.0014  # SNI 2847:2019, Pasal 9.6.1.2
FAKTOR_DELTA_IJIN    : float = 1.0/360.0  # delta_ijin = L/360

# ── MATERIAL STANDAR ──────────────────────────────────────────────────────────
MUTU_BAJA_DEFAULT: dict = {
    "A328"    : {"fy": 270, "fu": 410, "nama": "ASTM A328"},
    "A572-Gr50": {"fy": 345, "fu": 450, "nama": "ASTM A572 Grade 50"},
    "A690"    : {"fy": 345, "fu": 483, "nama": "ASTM A690"},
    "S355GP"  : {"fy": 355, "fu": 480, "nama": "EN S355GP"},
    "S430GP"  : {"fy": 430, "fu": 510, "nama": "EN S430GP"},
    "BJ37"    : {"fy": 240, "fu": 370, "nama": "SNI BJ37"},
    "BJ41"    : {"fy": 250, "fu": 410, "nama": "SNI BJ41"},
    "A36"     : {"fy": 250, "fu": 400, "nama": "ASTM A36"},
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
    return f"  {label:<20}: {nilai}"


def _ok_atau_tidak(kondisi: bool) -> str:
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


# ─────────────────────────────────────────────────────────────────────────────
# MUAT TABEL PROFIL BAJA DARI CSV
# ─────────────────────────────────────────────────────────────────────────────

def muat_tabel_profil(path_csv: str | None = None) -> list[dict]:
    """
    Muat tabel profil baja sheet pile dari file CSV.

    Format CSV (kolom):
        tipe, S_cm3_per_m, luas_cm2_per_m, berat_kg_per_m2,
        Ix_cm4_per_m, tinggi_mm, tebal_badan_mm, material, keterangan

    Parameter:
        path_csv : path ke file CSV (default: steel_sections.csv di folder script)

    Return:
        list[dict] — setiap dict adalah satu profil
    """
    if path_csv is None:
        # Cari di folder yang sama dengan script ini
        path_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "steel_sections.csv")

    if not os.path.exists(path_csv):
        raise FileNotFoundError(
            f"File tabel profil tidak ditemukan: {path_csv}\n"
            "Buat file steel_sections.csv di folder yang sama dengan section_design.py"
        )

    profil_list: list[dict] = []
    with open(path_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for baris in reader:
            try:
                profil_list.append({
                    "tipe"       : baris["tipe"].strip(),
                    "S"          : float(baris["S_cm3_per_m"]),
                    "luas"       : float(baris["luas_cm2_per_m"]),
                    "berat"      : float(baris["berat_kg_per_m2"]),
                    "Ix"         : float(baris["Ix_cm4_per_m"]),
                    "tinggi_mm"  : float(baris["tinggi_mm"]),
                    "tebal_mm"   : float(baris["tebal_badan_mm"]),
                    "material"   : baris["material"].strip(),
                    "keterangan" : baris.get("keterangan", "").strip(),
                })
            except (KeyError, ValueError):
                continue   # Lewati baris yang tidak valid

    return profil_list


def cari_profil_memenuhi(
    profil_list: list[dict],
    S_req      : float,
    material   : str | None = None,
    seri       : str | None = None,
    n_tampil   : int = 5,
) -> list[dict]:
    """
    Cari profil yang memenuhi S_req, urutkan dari yang paling ekonomis
    (S terkecil yang masih >= S_req).

    Parameter:
        profil_list : hasil muat_tabel_profil()
        S_req       : modulus penampang perlu [cm3/m]
        material    : filter material (misal "A572-Gr50", None = semua)
        seri        : filter seri profil (misal "PZ", "AU", None = semua)
        n_tampil    : jumlah profil yang ditampilkan dalam tabel

    Return:
        list[dict] — profil yang memenuhi, diurutkan dari paling ekonomis
    """
    kandidat = []
    for p in profil_list:
        if p["S"] < S_req:
            continue
        if material and material.upper() not in p["material"].upper():
            continue
        if seri and seri.upper() not in p["tipe"].upper():
            continue
        kandidat.append(p)

    # Urutkan berdasarkan S terkecil (paling ekonomis)
    kandidat.sort(key=lambda x: x["S"])
    return kandidat[:n_tampil]


# ─────────────────────────────────────────────────────────────────────────────
# A. DESAIN PENAMPANG BAJA
# ─────────────────────────────────────────────────────────────────────────────

def desain_baja(
    M_max         : float,
    fy            : float,
    fu            : float,
    path_csv      : str  | None = None,
    nama_material : str         = "A572-Gr50",
    seri_profil   : str  | None = None,
    faktor_sigma  : float       = FAKTOR_SIGMA_ALLOW,
    n_kandidat    : int         = 5,
) -> dict:
    """
    Desain penampang baja untuk turap (sheet pile / soldier pile).

    Metode Allowable Stress Design (ASD):
        sigma_allow = faktor_sigma * fy
        S_req       = M_max / sigma_allow

    Referensi:
        [R1] AISC Steel Construction Manual, 16th Ed., Section F11.1
        [R3] USS Steel Sheet Pile Design Manual (1975), Ch. 4, Hal. 4-1 s/d 4-8
        [R4] SNI 1729:2020, Pasal F11

    Parameter:
        M_max         : momen lentur maksimum dari Tahap 3 [kN.m/m]
        fy            : tegangan leleh baja [MPa]
        fu            : tegangan tarik ultimate baja [MPa]
        path_csv      : path ke tabel profil CSV
        nama_material : nama mutu baja (untuk informasi)
        seri_profil   : filter seri profil (misal "PZ", "AU", None = semua)
        faktor_sigma  : faktor tegangan ijin (default 0.60)
        n_kandidat    : jumlah profil kandidat yang ditampilkan

    Return:
        dict standar; "nilai" berisi:
            {sigma_allow, S_req, profil_terpilih, rasio_S,
             kandidat_profil, aman}
    """
    # ── Validasi ──────────────────────────────────────────────────────────────
    if M_max <= 0:
        raise ValueError(f"M_max harus > 0, diberikan: {M_max} kN.m/m")
    if fy <= 0 or fu <= 0:
        raise ValueError(f"fy dan fu harus > 0. fy={fy}, fu={fu} MPa")
    if faktor_sigma <= 0 or faktor_sigma > 1:
        raise ValueError(f"faktor_sigma harus 0 < faktor_sigma <= 1.0")

    # ── Langkah 1: Tegangan ijin ──────────────────────────────────────────────
    sigma_allow = faktor_sigma * fy

    # ── Langkah 2: Modulus penampang perlu ───────────────────────────────────
    # Konversi M_max: kN.m/m -> N.mm/m -> cm3/m
    # 1 kN.m/m = 1e6 N.mm/m
    # sigma_allow dalam N/mm2 = MPa
    # S_req [mm3/m] = M_max [N.mm/m] / sigma_allow [N/mm2]
    # S_req [cm3/m] = S_req [mm3/m] / 1000
    M_max_Nmm = M_max * 1e6          # N.mm/m
    S_req_mm3 = M_max_Nmm / sigma_allow  # mm3/m
    S_req     = S_req_mm3 / 1000         # cm3/m

    langkah: list[str] = [
        *_header("Desain Penampang Baja — Allowable Stress Design (ASD)"),
        "",
        "  Material:",
        _sub("  Nama mutu",    nama_material),
        _sub("  fy",           f"{fy:.1f} MPa  (tegangan leleh)"),
        _sub("  fu",           f"{fu:.1f} MPa  (tegangan tarik ultimate)"),
        _sub("  fu / fy",      f"{fu/fy:.3f}  (harus >= 1.2 per AISC)"),
        "",
        _garis("-"),
        "  LANGKAH 1 — Hitung Tegangan Ijin Lentur (sigma_allow)",
        _garis("-"),
        "  Rumus   : sigma_allow = faktor_sigma x fy",
        f"  Nilai   : faktor_sigma = {faktor_sigma:.2f}  (AISC F11.1, ASD)",
        f"            fy           = {fy:.1f} MPa",
        f"  Hitung  : sigma_allow  = {faktor_sigma:.2f} x {fy:.1f}",
        f"  Hasil   : sigma_allow  = {sigma_allow:.2f} MPa",
        _sub("  Satuan",  "MPa (= N/mm2)"),
        _sub("  Standar", "AISC Steel Construction Manual, 16th Ed., Section F11.1"),
        _sub("  ",        "SNI 1729:2020, Pasal F11"),
        _sub("  ",        "USS Sheet Pile Design Manual (1975), Ch. 4, Hal. 4-1"),
        "",
        _garis("-"),
        "  LANGKAH 2 — Hitung Modulus Penampang Perlu (S_req)",
        _garis("-"),
        "  Rumus   : S_req = M_max / sigma_allow",
        f"  Nilai   : M_max        = {M_max:.4f} kN.m/m",
        f"            M_max        = {M_max:.4f} x 10^6 N.mm/m  (konversi satuan)",
        f"                         = {M_max_Nmm:.2f} N.mm/m",
        f"            sigma_allow  = {sigma_allow:.2f} N/mm2",
        f"  Hitung  : S_req [mm3/m]= {M_max_Nmm:.2f} / {sigma_allow:.2f}",
        f"                         = {S_req_mm3:.2f} mm3/m",
        f"            S_req [cm3/m]= {S_req_mm3:.2f} / 1000",
        f"  Hasil   : S_req        = {S_req:.2f} cm3/m",
        _sub("  Satuan",  "cm3/m"),
        _sub("  Standar", "USS Sheet Pile Design Manual (1975), Ch. 4, Hal. 4-2"),
        _sub("  ",        "AISC Steel Construction Manual, 16th Ed., Table 3-19"),
    ]

    # ── Langkah 3: Cari profil dari tabel ────────────────────────────────────
    langkah += [
        "",
        _garis("-"),
        "  LANGKAH 3 — Pilih Profil dari Tabel",
        _garis("-"),
        f"  S_req = {S_req:.2f} cm3/m — cari profil dengan S >= S_req",
        f"  Seri  = {seri_profil if seri_profil else 'Semua'}",
    ]

    try:
        profil_list = muat_tabel_profil(path_csv)
        kandidat    = cari_profil_memenuhi(profil_list, S_req, seri=seri_profil,
                                           n_tampil=n_kandidat)
    except FileNotFoundError as e:
        langkah += [
            "",
            f"  PERINGATAN: {e}",
            "  Profil tidak dapat dipilih otomatis.",
            "  Lakukan pemilihan manual dari tabel produsen.",
        ]
        kandidat = []

    profil_terpilih = None
    rasio_S         = None
    aman            = False

    if kandidat:
        profil_terpilih = kandidat[0]   # yang paling ekonomis
        rasio_S         = profil_terpilih["S"] / S_req
        aman            = rasio_S >= RASIO_S_MIN

        # Tabel kandidat
        lebar_t  = 12
        lebar_s  = 10
        lebar_b  = 12
        lebar_i  = 14
        lebar_m  = 14
        lebar_kt = 22

        header_t = (
            f"  {'Tipe':<{lebar_t}} "
            f"{'S(cm3/m)':>{lebar_s}} "
            f"{'Berat(kg/m2)':>{lebar_b}} "
            f"{'Ix(cm4/m)':>{lebar_i}} "
            f"{'Material':<{lebar_m}} "
            f"{'Keterangan':<{lebar_kt}}"
        )
        garis_t = "  " + "-" * (len(header_t) - 2)

        langkah += [
            "",
            f"  Profil yang memenuhi S >= {S_req:.2f} cm3/m :",
            header_t,
            garis_t,
        ]
        for p in kandidat:
            tanda = "  <-- TERPILIH" if p is profil_terpilih else ""
            langkah.append(
                f"  {p['tipe']:<{lebar_t}} "
                f"{p['S']:>{lebar_s}.1f} "
                f"{p['berat']:>{lebar_b}.1f} "
                f"{p['Ix']:>{lebar_i}.0f} "
                f"{p['material']:<{lebar_m}} "
                f"{p['keterangan']:<{lebar_kt}}"
                f"{tanda}"
            )
        langkah.append(garis_t)

        langkah += [
            "",
            _garis("-"),
            "  LANGKAH 4 — Verifikasi Profil Terpilih",
            _garis("-"),
            f"  Profil terpilih : {profil_terpilih['tipe']}",
            f"  S_pakai         = {profil_terpilih['S']:.1f} cm3/m",
            f"  S_req           = {S_req:.2f} cm3/m",
            "",
            "  Rumus   : rasio_S = S_pakai / S_req",
            f"  Hitung  : rasio_S = {profil_terpilih['S']:.1f} / {S_req:.2f}",
            f"  Hasil   : rasio_S = {rasio_S:.4f}",
            f"  Syarat  : rasio_S >= {RASIO_S_MIN:.2f}",
            f"  Status  : {_ok_atau_tidak(aman)}",
            "",
            "  Hitung momen kapasitas profil terpilih:",
            "  Rumus   : M_kapasitas = S_pakai x sigma_allow",
            f"  Hitung  : M_kapasitas = {profil_terpilih['S']:.1f} cm3/m x {sigma_allow:.2f} MPa",
            f"            (konversi: {profil_terpilih['S']:.1f} x 1000 mm3/m x {sigma_allow:.2f} N/mm2)",
            f"            M_kapasitas = {profil_terpilih['S'] * 1000 * sigma_allow / 1e6:.3f} kN.m/m",
            f"  M_max   = {M_max:.4f} kN.m/m",
            f"  Margin  = {(profil_terpilih['S'] * 1000 * sigma_allow / 1e6 - M_max):.3f} kN.m/m",
        ]

    else:
        langkah += [
            "",
            "  Tidak ada profil yang memenuhi dalam tabel.",
            f"  S_req = {S_req:.2f} cm3/m — gunakan profil gabungan atau material grade lebih tinggi.",
        ]

    langkah += [
        "",
        _garis("-"),
        "  RANGKUMAN DESAIN BAJA",
        _garis("-"),
        f"  sigma_allow   = {sigma_allow:.2f} MPa",
        f"  S_req         = {S_req:.2f} cm3/m",
    ]

    if profil_terpilih:
        M_kap = profil_terpilih['S'] * 1000 * sigma_allow / 1e6
        langkah += [
            f"  Profil        = {profil_terpilih['tipe']}  ({profil_terpilih['material']})",
            f"  S_pakai       = {profil_terpilih['S']:.1f} cm3/m",
            f"  rasio_S       = {rasio_S:.4f}  --> {_ok_atau_tidak(aman)}",
            f"  M_kapasitas   = {M_kap:.3f} kN.m/m",
            f"  Berat turap   = {profil_terpilih['berat']:.1f} kg/m2",
        ]

    langkah += [
        "",
        _sub("  Standar", "AISC Steel Construction Manual, 16th Ed., Section F11.1"),
        _sub("  ",        "USS Steel Sheet Pile Design Manual (1975), Ch. 4"),
        _sub("  ",        "ASTM A572 / A690 / A328"),
        _sub("  ",        "SNI 1729:2020, Pasal F11"),
        _garis("="),
    ]

    referensi = [
        "AISC Steel Construction Manual, 16th Ed., Section F11.1",
        "USS Steel Sheet Pile Design Manual (1975), Ch. 4, Hal. 4-1 s/d 4-8",
        "ASTM A572 Grade 50 / A690 / A328",
        "SNI 1729:2020, Pasal F11",
    ]

    return _hasil_dict(
        nilai={
            "sigma_allow"     : round(sigma_allow,  3),
            "S_req"           : round(S_req,         3),
            "profil_terpilih" : profil_terpilih,
            "rasio_S"         : round(rasio_S, 4) if rasio_S else None,
            "kandidat_profil" : kandidat,
            "aman"            : aman,
        },
        langkah   = langkah,
        referensi = referensi,
        satuan    = "MPa (sigma), cm3/m (S)",
        status    = _ok_atau_tidak(aman),
    )


# ─────────────────────────────────────────────────────────────────────────────
# B. DESAIN PENAMPANG BETON PRACETAK
# ─────────────────────────────────────────────────────────────────────────────

def desain_beton_pracetak(
    M_max   : float,
    V_max   : float,
    fc      : float,
    fy      : float,
    b       : float,
    d       : float,
    cover   : float  = 50.0,
    L_span  : float  | None = None,
    faktor_beban_M  : float = FAKTOR_BEBAN_M,
    faktor_beban_V  : float = FAKTOR_BEBAN_V,
    phi_lentur_in   : float = PHI_LENTUR,
    phi_geser_in    : float = PHI_GESER,
) -> dict:
    """
    Desain penampang beton pracetak untuk turap — metode kekuatan (LRFD/SNI).

    Urutan perhitungan:
        A. Lentur:
            1. Mu = faktor_beban_M * M_max
            2. Rn = Mu / (phi_lentur * b * d^2)
            3. rho_tulangan = (0.85*fc/fy) * [1 - sqrt(1 - 2*Rn/(0.85*fc))]
            4. As_req = rho_tulangan * b * d
            5. Kontrol rho_min dan rho_max
        B. Geser:
            6. Vu = faktor_beban_V * V_max
            7. Vc = 0.17 * sqrt(fc) * b * d
            8. Cek phi_geser * Vc >= Vu
        C. Lendutan (jika L_span diberikan):
            9. delta_ijin = L_span / 360

    Referensi:
        [R5] SNI 2847:2019, Pasal 9.6.1.2 (rho_min), Pasal 22.5.5.1 (Vc),
                            Pasal 21.2.1 (phi), Pasal 24.2.2 (defleksi)
        [R7] PCI Design Handbook, 8th Ed., Ch. 5
        [R8] ACI 318-19, Section 9.6.1.2, 22.5.5.1, 24.2.2

    Parameter:
        M_max          : momen maks dari Tahap 3 [kN.m/m]
        V_max          : geser maks dari Tahap 3 [kN/m]
        fc             : kuat tekan beton silinder [MPa]
        fy             : tegangan leleh tulangan [MPa]
        b              : lebar penampang [mm]  (per satuan m = per 1000 mm)
        d              : tinggi efektif penampang [mm]
        cover          : selimut beton [mm] (default 50 mm)
        L_span         : panjang bentang untuk cek lendutan [m] (opsional)
        faktor_beban_M : faktor beban momen (default 1.6)
        faktor_beban_V : faktor beban geser (default 1.6)
        phi_lentur_in  : faktor reduksi lentur (default 0.90)
        phi_geser_in   : faktor reduksi geser (default 0.75)

    Return:
        dict standar; "nilai" berisi:
            {Mu, Vu, Rn, rho_tulangan, As_req, As_min, As_maks,
             Vc, phi_Vc, aman_lentur, aman_geser,
             h_total, d, b, fc, fy}
    """
    # ── Validasi ──────────────────────────────────────────────────────────────
    if M_max <= 0:
        raise ValueError(f"M_max harus > 0, diberikan: {M_max}")
    if V_max < 0:
        raise ValueError(f"V_max harus >= 0, diberikan: {V_max}")
    if fc < 17:
        raise ValueError(f"fc terlalu rendah untuk beton struktural: {fc} MPa (min 17 MPa)")
    if fy < 240:
        raise ValueError(f"fy terlalu rendah: {fy} MPa (min 240 MPa)")
    if b <= 0 or d <= 0:
        raise ValueError(f"b dan d harus > 0. b={b} mm, d={d} mm")

    # ── Konversi dan parameter dasar ──────────────────────────────────────────
    # b dalam mm (lebar per meter lebar turap)
    # d dalam mm
    # Mu dalam N.mm/m: M_max [kN.m/m] * faktor_beban * 1e6
    Mu_kNm  = M_max * faktor_beban_M                          # kN.m/m
    Mu      = Mu_kNm * 1e6                                    # N.mm/m
    Vu_kN   = abs(V_max) * faktor_beban_V                    # kN/m
    Vu      = Vu_kN * 1000                                    # N/m

    # beta1 (faktor blok tegangan beton)
    if fc <= 28.0:
        beta1 = 0.85
    elif fc <= 56.0:
        beta1 = 0.85 - 0.05 * (fc - 28.0) / 7.0
        beta1 = max(beta1, 0.65)
    else:
        beta1 = 0.65

    # ── BAGIAN A: LENTUR ──────────────────────────────────────────────────────
    # Langkah A1: Rn
    # Mu [N.mm/m] / (phi * b [mm] * d^2 [mm^2]) = Rn [N/mm2 = MPa]
    Rn = Mu / (phi_lentur_in * b * d ** 2)

    # Langkah A2: rho_tulangan
    dalam_akar = 1.0 - 2.0 * Rn / (FAKTOR_0_85_FC * fc)
    if dalam_akar < 0:
        raise ValueError(
            f"Penampang terlalu kecil! Nilai dalam sqrt negatif: {dalam_akar:.6f}. "
            f"Perbesar b atau d. (Rn={Rn:.4f} MPa, 0.85fc={0.85*fc:.2f} MPa)"
        )
    rho_tulangan = (FAKTOR_0_85_FC * fc / fy) * (1.0 - math.sqrt(dalam_akar))

    # Langkah A3: rho_min dan rho_max
    rho_min = max(RHO_MIN_ACI, 0.25 * math.sqrt(fc) / fy)
    # rho_balanced
    epsilon_u = 0.003   # regangan beton ultimit
    rho_bal   = (FAKTOR_0_85_FC * beta1 * fc / fy) * (
        epsilon_u / (epsilon_u + 0.004)    # batas deformasi SNI 2847:2019
    )
    rho_max   = 0.75 * rho_bal

    # Langkah A4: As_req
    rho_pakai = max(rho_tulangan, rho_min)
    if rho_pakai > rho_max:
        rho_pakai = rho_max   # perlu double reinf. — flag warning
    As_req    = rho_pakai * b * d       # mm2/m
    As_min    = rho_min * b * d         # mm2/m
    As_maks   = rho_max * b * d         # mm2/m

    aman_lentur_rho = rho_min <= rho_pakai <= rho_max

    # ── BAGIAN B: GESER ───────────────────────────────────────────────────────
    # Vc = 0.17 * sqrt(fc) * b * d   [N/m, bw dalam mm, d dalam mm]
    Vc        = 0.17 * math.sqrt(fc) * b * d       # N/m
    phi_Vc    = phi_geser_in * Vc                   # N/m
    Vc_kN     = Vc / 1000                           # kN/m
    phi_Vc_kN = phi_Vc / 1000                       # kN/m
    aman_geser = phi_Vc_kN >= Vu_kN

    # Tinggi total penampang
    h_total = d + cover    # mm (estimasi)

    # ── BAGIAN C: LENDUTAN (opsional) ─────────────────────────────────────────
    lendutan_info: list[str] = []
    if L_span is not None and L_span > 0:
        delta_ijin_mm = (L_span * 1000) * FAKTOR_DELTA_IJIN   # mm
        lendutan_info = [
            "",
            _garis("-"),
            "  BAGIAN C — Kontrol Lendutan",
            _garis("-"),
            "  Rumus   : delta_ijin = L_span / 360",
            f"  Nilai   : L_span = {L_span:.2f} m = {L_span*1000:.1f} mm",
            f"  Hitung  : delta_ijin = {L_span*1000:.1f} / 360",
            f"  Hasil   : delta_ijin = {delta_ijin_mm:.2f} mm",
            "  Catatan : Lendutan aktual perlu dihitung dari analisis struktur.",
            "            Panduan: delta_aktual <= L/360 (SNI 2847:2019, Tabel 24.2.2)",
            _sub("  Standar", "SNI 2847:2019, Pasal 24.2.2"),
            _sub("  ",        "ACI 318-19, Table 24.2.2"),
        ]

    # ── Susun log langkah ─────────────────────────────────────────────────────
    langkah: list[str] = [
        *_header("Desain Penampang Beton Pracetak — Metode Kekuatan (LRFD/SNI)"),
        "",
        "  Data material:",
        _sub("  fc",      f"{fc:.1f} MPa  (kuat tekan beton silinder)"),
        _sub("  fy",      f"{fy:.1f} MPa  (tegangan leleh tulangan)"),
        _sub("  beta1",   f"{beta1:.3f}  (faktor blok tegangan SNI 2847:2019 Ps. 22.2.2.4.3)"),
        "",
        "  Data penampang:",
        _sub("  b",       f"{b:.1f} mm  (lebar per meter lebar turap)"),
        _sub("  d",       f"{d:.1f} mm  (tinggi efektif)"),
        _sub("  cover",   f"{cover:.1f} mm  (selimut beton)"),
        _sub("  h_total", f"{h_total:.1f} mm  (d + cover, estimasi)"),
        "",
        "  Faktor beban dan reduksi:",
        _sub("  faktor_beban_M", f"{faktor_beban_M:.2f}  (SNI 2847:2019, Ps. 5.3.1c)"),
        _sub("  faktor_beban_V", f"{faktor_beban_V:.2f}"),
        _sub("  phi_lentur",     f"{phi_lentur_in:.2f}  (SNI 2847:2019, Ps. 21.2.2)"),
        _sub("  phi_geser",      f"{phi_geser_in:.2f}  (SNI 2847:2019, Ps. 21.2.1)"),
        "",
        _garis("-"),
        "  BAGIAN A — DESAIN LENTUR",
        _garis("-"),
        "",
        "  A1. Hitung momen ultimit (Mu):",
        "  Rumus   : Mu = faktor_beban_M x M_max",
        f"  Nilai   : faktor_beban_M = {faktor_beban_M:.2f}",
        f"            M_max          = {M_max:.4f} kN.m/m",
        f"  Hitung  : Mu = {faktor_beban_M:.2f} x {M_max:.4f}",
        f"  Hasil   : Mu = {Mu_kNm:.4f} kN.m/m",
        f"               = {Mu:.2f} N.mm/m  (konversi untuk formula)",
        _sub("  Satuan",  "kN.m/m"),
        _sub("  Standar", "SNI 2847:2019, Pasal 5.3.1c"),
        "",
        "  A2. Hitung tahanan momen nominal per satuan lebar (Rn):",
        "  Rumus   : Rn = Mu / (phi_lentur x b x d^2)",
        f"  Nilai   : phi_lentur = {phi_lentur_in:.2f}",
        f"            b          = {b:.1f} mm",
        f"            d          = {d:.1f} mm",
        f"  Hitung  : Rn = {Mu:.2f} / ({phi_lentur_in:.2f} x {b:.1f} x {d:.1f}^2)",
        f"               = {Mu:.2f} / ({phi_lentur_in * b * d**2:.2f})",
        f"  Hasil   : Rn = {Rn:.5f} MPa",
        _sub("  Satuan",  "MPa"),
        _sub("  Standar", "SNI 2847:2019, Pasal 22.2 (metode persegi ekuivalen)"),
        "",
        "  A3. Hitung rasio tulangan (rho_tulangan):",
        "  Rumus   : rho_tulangan = (0.85 x fc / fy) x [1 - sqrt(1 - 2 x Rn / (0.85 x fc))]",
        f"  Nilai   : fc = {fc:.1f} MPa,  fy = {fy:.1f} MPa",
        f"            Rn = {Rn:.5f} MPa",
        f"  Hitung  : 0.85 x fc        = {FAKTOR_0_85_FC * fc:.4f} MPa",
        f"            2 x Rn           = {2 * Rn:.5f} MPa",
        f"            2 x Rn / (0.85 x fc) = {2*Rn/(FAKTOR_0_85_FC*fc):.6f}",
        f"            1 - [...]        = {dalam_akar:.6f}",
        f"            sqrt([...])      = {math.sqrt(dalam_akar):.6f}",
        f"            1 - sqrt([...]) = {1 - math.sqrt(dalam_akar):.6f}",
        f"  Hitung  : rho_tulangan     = ({FAKTOR_0_85_FC * fc:.4f} / {fy:.1f}) x {1-math.sqrt(dalam_akar):.6f}",
        f"  Hasil   : rho_tulangan     = {rho_tulangan:.6f}",
        _sub("  Satuan",  "tak berdimensi"),
        _sub("  Standar", "SNI 2847:2019, Pasal 22.2 (metode persegi ekuivalen Whitney)"),
        "",
        "  A4. Batas rasio tulangan:",
        "  rho_min — Rumus  : rho_min = max(0.0014, 0.25 x sqrt(fc) / fy)",
        f"            Hitung : 0.0014",
        f"                     0.25 x sqrt({fc:.1f}) / {fy:.1f} = 0.25 x {math.sqrt(fc):.4f} / {fy:.1f} = {0.25*math.sqrt(fc)/fy:.6f}",
        f"            Hasil  : rho_min = {rho_min:.6f}",
        _sub("  Standar", "SNI 2847:2019, Pasal 9.6.1.2"),
        "",
        "  rho_max — Rumus  : rho_max = 0.75 x rho_balanced",
        f"            beta1       = {beta1:.3f}",
        f"            rho_balanced= (0.85 x beta1 x fc / fy) x (0.003 / (0.003 + 0.004))",
        f"                        = (0.85 x {beta1:.3f} x {fc:.1f} / {fy:.1f}) x (0.003/0.007)",
        f"                        = {rho_bal:.6f}",
        f"            Hasil  : rho_max = 0.75 x {rho_bal:.6f} = {rho_max:.6f}",
        _sub("  Standar", "SNI 2847:2019, Pasal 21.2.2 dan 22.2.2.4"),
        "",
        "  Kontrol:",
        f"    rho_tulangan = {rho_tulangan:.6f}",
        f"    rho_min      = {rho_min:.6f}",
        f"    rho_max      = {rho_max:.6f}",
        f"    rho_pakai    = max(rho_tulangan, rho_min) = {rho_pakai:.6f}",
        f"    rho_min <= rho_pakai <= rho_max  -->  {_ok_atau_tidak(aman_lentur_rho)}",
        "" if rho_pakai <= rho_max else
        "    PERINGATAN: rho_pakai > rho_max! Perbesar penampang atau gunakan tulangan ganda.",
        "",
        "  A5. Hitung luas tulangan perlu (As_req):",
        "  Rumus   : As_req = rho_pakai x b x d",
        f"  Nilai   : rho_pakai = {rho_pakai:.6f}",
        f"            b         = {b:.1f} mm",
        f"            d         = {d:.1f} mm",
        f"  Hitung  : As_req = {rho_pakai:.6f} x {b:.1f} x {d:.1f}",
        f"  Hasil   : As_req = {As_req:.2f} mm2/m",
        f"            As_min = {As_min:.2f} mm2/m  (kontrol minimum)",
        f"            As_max = {As_maks:.2f} mm2/m  (kontrol maksimum)",
        _sub("  Satuan",  "mm2/m"),
        _sub("  Standar", "SNI 2847:2019, Pasal 9.6.1.2 dan 22.2"),
        _sub("  ",        "ACI 318-19, Section 9.6.1.2"),
        "",
        _garis("-"),
        "  BAGIAN B — KONTROL GESER",
        _garis("-"),
        "",
        "  B1. Hitung gaya geser ultimit (Vu):",
        "  Rumus   : Vu = faktor_beban_V x V_max",
        f"  Nilai   : faktor_beban_V = {faktor_beban_V:.2f}",
        f"            V_max          = {abs(V_max):.4f} kN/m",
        f"  Hitung  : Vu = {faktor_beban_V:.2f} x {abs(V_max):.4f}",
        f"  Hasil   : Vu = {Vu_kN:.4f} kN/m",
        _sub("  Satuan",  "kN/m"),
        "",
        "  B2. Hitung kapasitas geser beton (Vc):",
        "  Rumus   : Vc = 0.17 x sqrt(fc) x b x d",
        f"  Nilai   : fc = {fc:.1f} MPa",
        f"            b  = {b:.1f} mm",
        f"            d  = {d:.1f} mm",
        f"  Hitung  : sqrt(fc)  = sqrt({fc:.1f}) = {math.sqrt(fc):.4f}",
        f"            Vc = 0.17 x {math.sqrt(fc):.4f} x {b:.1f} x {d:.1f}",
        f"               = {Vc:.2f} N/m",
        f"  Hasil   : Vc       = {Vc_kN:.4f} kN/m",
        _sub("  Standar", "SNI 2847:2019, Pasal 22.5.5.1"),
        _sub("  ",        "ACI 318-19, Section 22.5.5.1"),
        "",
        "  B3. Kontrol geser:",
        "  Syarat  : phi_geser x Vc >= Vu",
        f"  Hitung  : phi_geser x Vc = {phi_geser_in:.2f} x {Vc_kN:.4f}",
        f"                           = {phi_Vc_kN:.4f} kN/m",
        f"  Vu      = {Vu_kN:.4f} kN/m",
        f"  Status  : {_ok_atau_tidak(aman_geser)}",
        "" if aman_geser else
        f"  PERINGATAN: Vu > phi_geser x Vc  -->  Perlu tulangan geser (sengkang)!",
        "" if aman_geser else
        f"    Vs_perlu = Vu/phi_geser - Vc = {Vu_kN/phi_geser_in:.4f} - {Vc_kN:.4f} = {Vu_kN/phi_geser_in - Vc_kN:.4f} kN/m",
        _sub("  Standar", "SNI 2847:2019, Pasal 22.5.1 dan 22.5.5"),
        *lendutan_info,
        "",
        _garis("-"),
        "  RANGKUMAN DESAIN BETON PRACETAK",
        _garis("-"),
        f"  fc            = {fc:.1f} MPa",
        f"  fy            = {fy:.1f} MPa",
        f"  b             = {b:.1f} mm,  d = {d:.1f} mm,  h_total = {h_total:.1f} mm",
        f"  Mu            = {Mu_kNm:.4f} kN.m/m",
        f"  Rn            = {Rn:.5f} MPa",
        f"  rho_tulangan  = {rho_tulangan:.6f}",
        f"  rho_min       = {rho_min:.6f}",
        f"  rho_max       = {rho_max:.6f}",
        f"  rho_pakai     = {rho_pakai:.6f}",
        f"  As_req        = {As_req:.2f} mm2/m  --> {_ok_atau_tidak(aman_lentur_rho)}",
        f"  Vu            = {Vu_kN:.4f} kN/m",
        f"  phi_geser x Vc= {phi_Vc_kN:.4f} kN/m  --> {_ok_atau_tidak(aman_geser)}",
        "",
        _sub("  Standar", "SNI 2847:2019, Pasal 9.6.1.2, 21.2.1, 21.2.2, 22.5.5.1"),
        _sub("  ",        "ACI 318-19, Section 9.6.1.2, 22.5.5.1"),
        _sub("  ",        "PCI Design Handbook, 8th Ed., Ch. 5"),
        _garis("="),
    ]

    referensi = [
        "SNI 2847:2019, Pasal 9.6.1.2, 21.2.1, 21.2.2, 22.5.5.1",
        "ACI 318-19, Section 9.6.1.2, 22.5.5.1",
        "PCI Design Handbook, 8th Ed., Ch. 5",
        "SNI 8460:2017, Pasal 9",
    ]

    aman_keseluruhan = aman_lentur_rho and aman_geser
    return _hasil_dict(
        nilai={
            "Mu"           : round(Mu_kNm,      4),
            "Vu"           : round(Vu_kN,        4),
            "Rn"           : round(Rn,            6),
            "rho_tulangan" : round(rho_tulangan,  6),
            "rho_pakai"    : round(rho_pakai,     6),
            "rho_min"      : round(rho_min,       6),
            "rho_max"      : round(rho_max,       6),
            "As_req"       : round(As_req,        2),
            "As_min"       : round(As_min,        2),
            "As_maks"      : round(As_maks,       2),
            "Vc"           : round(Vc_kN,         4),
            "phi_Vc"       : round(phi_Vc_kN,     4),
            "aman_lentur"  : aman_lentur_rho,
            "aman_geser"   : aman_geser,
            "h_total"      : round(h_total,       1),
            "d"            : d,
            "b"            : b,
            "fc"           : fc,
            "fy"           : fy,
            "beta1"        : round(beta1,         3),
        },
        langkah   = langkah,
        referensi = referensi,
        satuan    = "mm2/m (As), kN.m/m (Mu), kN/m (Vu)",
        status    = _ok_atau_tidak(aman_keseluruhan),
    )


# ─────────────────────────────────────────────────────────────────────────────
# C. PLOT PERBANDINGAN DAN VISUALISASI PENAMPANG
# ─────────────────────────────────────────────────────────────────────────────

def plot_interaksi_penampang(
    hasil_baja  : dict | None = None,
    hasil_beton : dict | None = None,
    judul       : str         = "Ringkasan Desain Penampang Turap",
) -> plt.Figure:
    """
    Buat figure ringkasan desain — tabel kandidat baja dan/atau diagram
    tulangan beton pracetak.

    Parameter:
        hasil_baja  : output dari desain_baja()
        hasil_beton : output dari desain_beton_pracetak()
        judul       : judul figure

    Return:
        matplotlib.Figure
    """
    n_baris = 1 if bool(hasil_baja) != bool(hasil_beton) else 1
    n_kol   = (1 if hasil_baja is None else 1) + (1 if hasil_beton is None else 1)
    if hasil_baja and hasil_beton:
        n_kol = 2
    elif hasil_baja or hasil_beton:
        n_kol = 1

    fig, axes = plt.subplots(
        1, n_kol,
        figsize=(7 * n_kol, 7),
        layout="constrained",
    )
    if n_kol == 1:
        axes = [axes]

    fig.suptitle(judul, fontsize=11, fontweight="bold")

    ax_idx = 0

    # ── Panel baja: tabel kandidat ─────────────────────────────────────────
    if hasil_baja:
        ax = axes[ax_idx]; ax_idx += 1
        ax.axis("off")

        nilai_b   = hasil_baja["nilai"]
        kandidat  = nilai_b.get("kandidat_profil", [])
        S_req     = nilai_b.get("S_req", 0)
        sigma_all = nilai_b.get("sigma_allow", 0)

        baris_tabel = [["Tipe", "S (cm3/m)", "Berat\n(kg/m2)", "Ix (cm4/m)", "Status"]]
        for p in kandidat[:8]:
            status = "OK" if p["S"] >= S_req else "-"
            tanda  = " (*)" if p is kandidat[0] else ""
            baris_tabel.append([
                p["tipe"] + tanda,
                f"{p['S']:.0f}",
                f"{p['berat']:.0f}",
                f"{p['Ix']:.0f}",
                status,
            ])

        tabel = ax.table(
            cellText    = baris_tabel[1:],
            colLabels   = baris_tabel[0],
            cellLoc     = "center",
            loc         = "center",
        )
        tabel.auto_set_font_size(False)
        tabel.set_fontsize(8.5)
        tabel.scale(1.1, 1.5)

        # Warnai baris terpilih
        for (baris, kol), sel in tabel.get_celld().items():
            if baris == 1:
                sel.set_facecolor("#D5E8D4")   # hijau muda
            elif baris == 0:
                sel.set_facecolor("#DAE8FC")   # biru muda (header)

        profil_t = nilai_b.get("profil_terpilih")
        nama_pr  = profil_t["tipe"] if profil_t else "-"
        S_pakai  = profil_t["S"]    if profil_t else 0

        ax.set_title(
            f"Desain Baja\nS_req={S_req:.0f} cm3/m  |  Profil: {nama_pr}  |  S={S_pakai:.0f} cm3/m\n"
            f"sigma_allow={sigma_all:.0f} MPa  |  {hasil_baja['status']}",
            fontsize=9, pad=12,
        )

    # ── Panel beton: diagram tulangan ────────────────────────────────────────
    if hasil_beton:
        ax = axes[ax_idx]
        nilai_bt = hasil_beton["nilai"]

        b_mm   = nilai_bt["b"]
        d_mm   = nilai_bt["d"]
        h_mm   = nilai_bt["h_total"]
        As_req = nilai_bt["As_req"]

        # Gambar penampang sederhana
        ax.set_xlim(-10, b_mm + 60)
        ax.set_ylim(-20, h_mm + 40)
        ax.set_aspect("equal")
        ax.axis("off")

        # Penampang beton
        from matplotlib.patches import Rectangle, Circle
        beton = Rectangle((0, 0), b_mm, h_mm, linewidth=1.5,
                          edgecolor="gray", facecolor="#F0F0F0")
        ax.add_patch(beton)

        # Garis efektif d
        cover = h_mm - d_mm
        ax.axhline(y=cover, color="red", linewidth=0.8, linestyle="--")
        ax.annotate(f"cover={cover:.0f}mm", xy=(b_mm + 5, cover),
                    fontsize=7, color="red", va="center")
        ax.axhline(y=h_mm - cover, color="blue", linewidth=0.8, linestyle=":")
        ax.annotate(f"d={d_mm:.0f}mm", xy=(b_mm + 5, h_mm - cover),
                    fontsize=7, color="blue", va="center")

        # Tulangan (estimasi jumlah batang D16)
        D_bar   = 16.0   # mm diameter estimasi
        As_D16  = math.pi * D_bar**2 / 4  # mm2 per batang
        n_bar   = max(2, math.ceil(As_req / As_D16))
        spasi   = b_mm / (n_bar + 1)
        for i in range(n_bar):
            x_bar = spasi * (i + 1)
            y_bar = cover + D_bar / 2
            circ = Circle((x_bar, y_bar), D_bar / 2,
                          facecolor="#AA0000", edgecolor="black", linewidth=0.5)
            ax.add_patch(circ)

        ax.set_title(
            f"Penampang Beton Pracetak\n"
            f"b={b_mm:.0f}mm  d={d_mm:.0f}mm  h={h_mm:.0f}mm\n"
            f"As_req={As_req:.0f} mm2/m  |  Estimasi {n_bar} D{D_bar:.0f}\n"
            f"fc={nilai_bt['fc']:.0f}MPa  fy={nilai_bt['fy']:.0f}MPa\n"
            f"{hasil_beton['status']}",
            fontsize=8.5, pad=10,
        )

        # Dimensi
        ax.annotate("", xy=(0, -12), xytext=(b_mm, -12),
                    arrowprops=dict(arrowstyle="<->", lw=0.8))
        ax.text(b_mm / 2, -18, f"b = {b_mm:.0f} mm",
                ha="center", fontsize=7.5)

    return fig


# ─────────────────────────────────────────────────────────────────────────────
# D. TAMPILKAN LANGKAH DESAIN — FUNGSI WRAPPER UNTUK STREAMLIT
# ─────────────────────────────────────────────────────────────────────────────

def tampilkan_langkah_desain(
    hasil_dict   : dict,
    tipe_material: str = "baja",
) -> str:
    """
    Wrapper sederhana — kembalikan string langkah untuk ditampilkan
    di Streamlit dengan st.code() atau st.text().

    Penggunaan:
        teks = tampilkan_langkah_desain(hasil_baja, "baja")
        st.code(teks, language="")

    Parameter:
        hasil_dict    : output dari desain_baja() atau desain_beton_pracetak()
        tipe_material : "baja" atau "beton" (untuk prefix header)

    Return:
        str — teks siap tampil
    """
    header_line = (
        f"{'='*64}\n"
        f"  LANGKAH DESAIN PENAMPANG — {tipe_material.upper()}\n"
        f"{'='*64}\n"
    )
    return header_line + format_langkah(hasil_dict.get("langkah", []))


# ─────────────────────────────────────────────────────────────────────────────
# E. FUNGSI TERPADU — DARI HASIL TAHAP 3
# ─────────────────────────────────────────────────────────────────────────────

def desain_penampang_dari_gaya_dalam(
    hasil_gaya_dalam : dict,
    tipe_material    : str   = "baja",
    fy               : float = 250.0,
    fu               : float = 410.0,
    fc               : float = 30.0,
    b_beton          : float = 1000.0,
    d_beton          : float = 350.0,
    cover_beton      : float = 50.0,
    path_csv         : str | None = None,
    seri_profil      : str | None = None,
) -> dict:
    """
    Fungsi terpadu: ambil M_max dan V_max dari hasil Tahap 3
    (internal_forces.py) lalu lakukan desain penampang langsung.

    Parameter:
        hasil_gaya_dalam : dict hasil dari hitung_gaya_dalam() atau
                          hitung_gaya_dalam_kantilever()
        tipe_material    : "baja" atau "beton"
        fy               : tegangan leleh [MPa]
        fu               : tegangan tarik ultimate [MPa] (untuk baja)
        fc               : kuat tekan beton [MPa] (untuk beton)
        b_beton          : lebar penampang beton [mm]
        d_beton          : tinggi efektif beton [mm]
        cover_beton      : selimut beton [mm]
        path_csv         : path CSV profil baja
        seri_profil      : filter seri profil baja

    Return:
        dict standar hasil desain_baja() atau desain_beton_pracetak()
    """
    nilai = hasil_gaya_dalam.get("nilai", {})
    M_max = nilai.get("M_max", 0.0)
    V_max_arr = nilai.get("V_array")

    if V_max_arr is not None:
        V_max = float(np.max(np.abs(V_max_arr)))
    else:
        V_max = 0.0

    if tipe_material.lower() in ("baja", "steel"):
        return desain_baja(
            M_max         = M_max,
            fy            = fy,
            fu            = fu,
            path_csv      = path_csv,
            nama_material = f"fy={fy:.0f}MPa",
            seri_profil   = seri_profil,
        )
    else:
        return desain_beton_pracetak(
            M_max  = M_max,
            V_max  = V_max,
            fc     = fc,
            fy     = fy,
            b      = b_beton,
            d      = d_beton,
            cover  = cover_beton,
        )


# ─────────────────────────────────────────────────────────────────────────────
# CONTOH PENGGUNAAN — jalankan: python section_design.py
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/home/claude")

    print("\n" + "=" * 64)
    print("  CONTOH DESAIN PENAMPANG TURAP")
    print("=" * 64)

    # ── Data contoh realistis turap baja PSA/PZ ──────────────────────────────
    # Turap H=4m dengan angkur, tanah medium Jabodetabek
    # M_max tipikal 80-250 kN.m/m tergantung H dan kondisi tanah
    M_MAX_BAJA = 185.3    # kN.m/m  (tipikal H=4m, anchored)
    V_MAX_BAJA = 45.2     # kN/m

    # ── Data contoh realistis turap beton pracetak ───────────────────────────
    # Beton pracetak khas pabrik: lebar 350-500mm, tinggi 200-300mm
    # M_max tipikal 40-120 kN.m/m untuk turap beton pracetak
    M_MAX_BETON = 78.5    # kN.m/m  (tipikal H=3m, beton pracetak sedang)
    V_MAX_BETON = 38.2    # kN/m

    # ── A. Desain Baja ──────────────────────────────────────────────────────
    print("\n>>> KASUS A: Baja (A572 Grade 50, M_max=185.3 kN.m/m)")
    res_baja = desain_baja(
        M_max         = M_MAX_BAJA,
        fy            = 345.0,
        fu            = 450.0,
        path_csv      = "/home/claude/steel_sections.csv",
        nama_material = "ASTM A572 Grade 50",
        seri_profil   = None,
        n_kandidat    = 6,
    )
    print(format_langkah(res_baja["langkah"]))

    # ── B. Desain Beton Pracetak ─────────────────────────────────────────────
    print("\n>>> KASUS B: Beton Pracetak K-350 (fc=29.05 MPa), M_max=78.5 kN.m/m")
    res_beton = desain_beton_pracetak(
        M_max   = M_MAX_BETON,
        V_max   = V_MAX_BETON,
        fc      = 29.05,       # K-350 setara fc = 29.05 MPa
        fy      = 390.0,       # BJTD U-39
        b       = 1000.0,      # mm per meter lebar (b per 1m panjang turap)
        d       = 400.0,       # mm tinggi efektif — penampang 460x250mm khas
        cover   = 60.0,        # mm selimut beton (turap di tanah agresif)
        L_span  = 4.0,         # m bentang untuk cek lendutan
    )
    print(format_langkah(res_beton["langkah"]))

    # ── Ringkasan akhir ───────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  RINGKASAN DESAIN PENAMPANG")
    print("=" * 64)
    nb = res_baja["nilai"]
    nc = res_beton["nilai"]

    print(f"\n  A. BAJA (A572 Gr.50, fy=345 MPa)  M_max={M_MAX_BAJA:.1f} kN.m/m :")
    print(f"     sigma_allow = {nb['sigma_allow']:.1f} MPa")
    print(f"     S_req       = {nb['S_req']:.2f} cm3/m")
    if nb["profil_terpilih"]:
        p = nb["profil_terpilih"]
        print(f"     Profil      = {p['tipe']}  |  S={p['S']:.0f} cm3/m  |  "
              f"Berat={p['berat']:.0f} kg/m2")
    print(f"     Status      = {res_baja['status']}")

    M_MAX_BAJA  = M_MAX_BAJA
    print(f"\n  B. BETON PRACETAK (fc=29.05 MPa, fy=390 MPa)  M_max={M_MAX_BETON:.1f} kN.m/m :")
    print(f"     Mu          = {nc['Mu']:.2f} kN.m/m")
    print(f"     Rn          = {nc['Rn']:.5f} MPa")
    print(f"     rho_pakai   = {nc['rho_pakai']:.6f}")
    print(f"     As_req      = {nc['As_req']:.2f} mm2/m")
    print(f"     phi_Vc      = {nc['phi_Vc']:.2f} kN/m  (Vu={nc['Vu']:.2f} kN/m)")
    print(f"     Status      = {res_beton['status']}")

    # ── Plot ─────────────────────────────────────────────────────────────────
    fig = plot_interaksi_penampang(
        hasil_baja  = res_baja,
        hasil_beton = res_beton,
        judul       = (f"Desain Penampang Turap  |  "
                       f"Baja M={M_MAX_BAJA:.1f} kN.m/m  |  "
                       f"Beton M={M_MAX_BETON:.1f} kN.m/m"),
    )
    fig.savefig("/home/claude/desain_penampang.png", dpi=150, bbox_inches="tight")
    print(f"\n  Plot tersimpan: desain_penampang.png")
    print("\nSelesai.")
