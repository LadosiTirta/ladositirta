"""
================================================================================
earth_pressure.py
================================================================================
Modul perhitungan tekanan tanah lateral untuk desain turap / sheet pile.

Teori yang digunakan:
    1. Rankine (1857)  — kondisi tanah aktif dan pasif, drainase dan tak-drainase
    2. Coulomb (1776)  — pengaruh gesekan dinding (delta) dan kemiringan permukaan
    3. Jaky (1944)     — tekanan at-rest (Ko)

Referensi utama:
    [R1]  SNI 8460:2017   — Persyaratan Perancangan Geoteknik, Pasal 5.2–5.4
    [R2]  NAVFAC DM-7.01  — Soil Mechanics, Chapter 4 (Lateral Earth Pressure)
    [R3]  NAVFAC DM-7.02  — Foundations & Earth Structures, Chapter 3 (Sheet Pile)
    [R4]  USS Sheet Pile  — Design Manual (1975), Chapter 2–3
    [R5]  ASCE 7-22       — §C11.8.2 (Coulomb Active Pressure)
    [R6]  EN 1997-1:2004  — Eurocode 7, Annex C (Ka/Kp Charts)

Konvensi satuan:
    Gaya   : kN
    Panjang: m
    Tegangan / Tekanan: kPa
    Momen  : kN·m/m (per meter lebar)

Konvensi nama variabel (TIDAK menggunakan simbol Yunani):
    gamma      = berat volume tanah total       [kN/m3]
    gamma_sat  = berat volume tanah jenuh       [kN/m3]
    gamma_w    = berat volume air               [kN/m3]
    phi        = sudut geser dalam              [derajat]
    cohesion   = kohesi tanah                   [kPa]
    delta      = sudut gesek tanah-dinding      [derajat]
    Ka         = koefisien tekanan aktif        [-]
    Kp         = koefisien tekanan pasif        [-]
    Ko         = koefisien tekanan at-rest      [-]
    sigma_v    = tegangan vertikal efektif      [kPa]
    sigma_h    = tegangan horizontal            [kPa]
    u          = tekanan air pori               [kPa]
    surcharge  = beban tambahan di permukaan    [kPa]
    z          = kedalaman dari permukaan       [m]
    H          = tinggi turap di atas galian    [m]
    D          = kedalaman penetrasi            [m]

Catatan teks output:
    Seluruh string output menggunakan kata (bukan simbol Yunani)
    sehingga kompatibel dengan ekspor ke Word dan PDF (plain text).

Penulis  : Structural Civil Engineer — Pabrik Beton Pracetak, Jabodetabek
Versi    : 1.0.0
Tanggal  : 2025
================================================================================
"""

from __future__ import annotations

import math
import textwrap
from typing import Any

import numpy as np
import matplotlib
matplotlib.use("Agg")           # backend non-interaktif, aman untuk Streamlit
import matplotlib.pyplot as plt
import matplotlib.patches as patches


# ─────────────────────────────────────────────────────────────────────────────
# KONSTANTA
# ─────────────────────────────────────────────────────────────────────────────

GAMMA_W_DEFAULT: float = 9.81   # berat volume air [kN/m3]


# ─────────────────────────────────────────────────────────────────────────────
# FUNGSI PEMBANTU FORMAT OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

def _baris(teks: str = "") -> str:
    """Kembalikan satu baris teks (untuk menyusun langkah perhitungan)."""
    return teks


def _garis(karakter: str = "-", lebar: int = 64) -> str:
    """Buat garis pemisah."""
    return karakter * lebar


def _header(judul: str) -> list[str]:
    """Buat header kotak untuk setiap blok perhitungan."""
    lebar = 64
    return [
        _garis("=", lebar),
        f"  {judul.upper()}",
        _garis("=", lebar),
    ]


def _sub(label: str, nilai: str) -> str:
    """Format baris '  Label  : nilai' (rata kiri label 12 karakter)."""
    return f"  {label:<12}: {nilai}"


def _hasil_dict(
    nilai: Any,
    langkah: list[str],
    referensi: list[str],
    satuan: str,
) -> dict:
    """
    Buat dict standar yang dikembalikan oleh setiap fungsi perhitungan.

    Struktur:
        {
            "nilai"    : hasil numerik,
            "langkah"  : list string langkah perhitungan,
            "referensi": list referensi standar,
            "satuan"   : string satuan,
        }
    """
    return {
        "nilai"    : nilai,
        "langkah"  : langkah,
        "referensi": referensi,
        "satuan"   : satuan,
    }


def _validasi_positif(nama: str, nilai: float) -> None:
    """Pastikan nilai tidak negatif; raise ValueError jika negatif."""
    if nilai < 0:
        raise ValueError(
            f"Parameter '{nama}' harus >= 0, diberikan: {nilai}"
        )


def _validasi_phi(phi: float) -> None:
    """Pastikan sudut geser phi berada dalam rentang 0–89 derajat."""
    if not (0.0 <= phi < 90.0):
        raise ValueError(
            f"Sudut geser phi harus 0 <= phi < 90 derajat, diberikan: {phi}"
        )


def _deg_to_rad(derajat: float) -> float:
    """Konversi derajat ke radian."""
    return math.radians(derajat)


def _tan(derajat: float) -> float:
    """tan(x) dengan input derajat."""
    return math.tan(_deg_to_rad(derajat))


def _sin(derajat: float) -> float:
    """sin(x) dengan input derajat."""
    return math.sin(_deg_to_rad(derajat))


def _cos(derajat: float) -> float:
    """cos(x) dengan input derajat."""
    return math.cos(_deg_to_rad(derajat))


# ─────────────────────────────────────────────────────────────────────────────
# 1. KOEFISIEN TEKANAN AKTIF RANKINE
# ─────────────────────────────────────────────────────────────────────────────

def hitung_Ka_rankine(phi: float) -> dict:
    """
    Hitung koefisien tekanan aktif Rankine (Ka).

    Rumus:
        Ka = tan^2(45 - phi/2)

    Berlaku untuk:
        - Dinding vertikal, permukaan tanah horizontal
        - Gesekan tanah-dinding diabaikan (delta = 0)
        - Tanah kohesif maupun non-kohesif

    Referensi:
        [R1] SNI 8460:2017, Pasal 5.3.2, Persamaan 5.3
        [R2] NAVFAC DM-7.01, Ch. 4, Tabel 3, Hal. 4-9
        [R4] USS Sheet Pile Design Manual (1975), Ch. 2, Hal. 2-5
        [R6] EN 1997-1:2004, Annex C, C.2

    Parameter:
        phi : float — sudut geser dalam [derajat]

    Return:
        dict standar dengan kunci: nilai, langkah, referensi, satuan
    """
    _validasi_phi(phi)

    sudut_kritis = 45.0 - phi / 2.0       # sudut bidang keruntuhan
    tan_val      = _tan(sudut_kritis)      # tan(45 - phi/2)
    Ka           = tan_val ** 2

    langkah: list[str] = [
        *_header("Koefisien Tekanan Aktif Rankine (Ka)"),
        "",
        _sub("Rumus", "Ka = tan^2(45 - phi/2)"),
        "",
        _sub("Nilai", f"phi = {phi:.1f} derajat"),
        "",
        _sub("Hitung", f"45 - phi/2         = 45 - {phi:.1f}/2"),
        _sub("",        f"                   = {sudut_kritis:.4f} derajat"),
        _sub("",        f"tan({sudut_kritis:.4f} derajat)    = {tan_val:.6f}"),
        _sub("",        f"Ka = ({tan_val:.6f})^2"),
        "",
        _sub("Hasil",   f"Ka = {Ka:.6f}"),
        _sub("",        f"Ka = {Ka:.4f}  (dibulatkan 4 desimal)"),
        _sub("Satuan",  "(tak berdimensi)"),
        "",
        _sub("Standar", "SNI 8460:2017, Pasal 5.3.2, Persamaan 5.3"),
        _sub("",        "NAVFAC DM-7.01, Ch. 4, Tabel 3, Hal. 4-9"),
        _sub("",        "USS Sheet Pile Design Manual (1975), Ch. 2, Hal. 2-5"),
        _sub("",        "EN 1997-1:2004, Annex C, C.2"),
        _garis(),
    ]

    referensi = [
        "SNI 8460:2017, Pasal 5.3.2, Persamaan 5.3",
        "NAVFAC DM-7.01, Ch. 4, Tabel 3, Hal. 4-9",
        "USS Sheet Pile Design Manual (1975), Ch. 2, Hal. 2-5",
        "EN 1997-1:2004, Annex C, C.2",
    ]

    return _hasil_dict(
        nilai     = round(Ka, 6),
        langkah   = langkah,
        referensi = referensi,
        satuan    = "tak berdimensi",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. KOEFISIEN TEKANAN PASIF RANKINE
# ─────────────────────────────────────────────────────────────────────────────

def hitung_Kp_rankine(phi: float) -> dict:
    """
    Hitung koefisien tekanan pasif Rankine (Kp).

    Rumus:
        Kp = tan^2(45 + phi/2)
        Kp = 1 / Ka  (untuk tanah non-kohesif)

    Catatan:
        Kp Rankine cenderung konservatif (lebih kecil dari Coulomb/Log-spiral).
        Untuk desain turap, Kp Rankine umumnya digunakan sebagai nilai aman.

    Referensi:
        [R1] SNI 8460:2017, Pasal 5.3.3, Persamaan 5.4
        [R2] NAVFAC DM-7.01, Ch. 4, Tabel 3, Hal. 4-9
        [R4] USS Sheet Pile Design Manual (1975), Ch. 2, Hal. 2-6

    Parameter:
        phi : float — sudut geser dalam [derajat]

    Return:
        dict standar
    """
    _validasi_phi(phi)

    sudut_kritis = 45.0 + phi / 2.0
    tan_val      = _tan(sudut_kritis)
    Kp           = tan_val ** 2

    # Hubungan Kp = 1/Ka (non-kohesif)
    Ka           = _tan(45.0 - phi / 2.0) ** 2
    Kp_dari_Ka   = 1.0 / Ka if Ka > 1e-9 else float("inf")

    langkah: list[str] = [
        *_header("Koefisien Tekanan Pasif Rankine (Kp)"),
        "",
        _sub("Rumus", "Kp = tan^2(45 + phi/2)"),
        "",
        _sub("Nilai", f"phi = {phi:.1f} derajat"),
        "",
        _sub("Hitung", f"45 + phi/2         = 45 + {phi:.1f}/2"),
        _sub("",        f"                   = {sudut_kritis:.4f} derajat"),
        _sub("",        f"tan({sudut_kritis:.4f} derajat)   = {tan_val:.6f}"),
        _sub("",        f"Kp = ({tan_val:.6f})^2"),
        "",
        _sub("Hasil",  f"Kp = {Kp:.6f}"),
        _sub("",       f"Kp = {Kp:.4f}  (dibulatkan 4 desimal)"),
        "",
        _sub("Kontrol", f"Kp = 1/Ka = 1/{Ka:.4f} = {Kp_dari_Ka:.4f}  [non-kohesif]"),
        _sub("Satuan",  "(tak berdimensi)"),
        "",
        _sub("Standar", "SNI 8460:2017, Pasal 5.3.3, Persamaan 5.4"),
        _sub("",        "NAVFAC DM-7.01, Ch. 4, Tabel 3, Hal. 4-9"),
        _sub("",        "USS Sheet Pile Design Manual (1975), Ch. 2, Hal. 2-6"),
        _garis(),
    ]

    referensi = [
        "SNI 8460:2017, Pasal 5.3.3, Persamaan 5.4",
        "NAVFAC DM-7.01, Ch. 4, Tabel 3, Hal. 4-9",
        "USS Sheet Pile Design Manual (1975), Ch. 2, Hal. 2-6",
    ]

    return _hasil_dict(
        nilai     = round(Kp, 6),
        langkah   = langkah,
        referensi = referensi,
        satuan    = "tak berdimensi",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. KOEFISIEN TEKANAN AKTIF COULOMB
# ─────────────────────────────────────────────────────────────────────────────

def hitung_Ka_coulomb(
    phi       : float,
    delta     : float,
    alpha_wall: float = 90.0,
    beta_slope: float = 0.0,
) -> dict:
    """
    Hitung koefisien tekanan aktif Coulomb (Ka) dengan gesekan dinding.

    Rumus Coulomb (1776):
        Ka = sin^2(alpha_wall + phi)
             ─────────────────────────────────────────────────────────────
             sin^2(alpha_wall) * sin(alpha_wall - delta) *
             [1 + sqrt( sin(phi+delta)*sin(phi-beta_slope) /
                        (sin(alpha_wall-delta)*sin(alpha_wall+beta_slope)) )]^2

    Notasi parameter (semua dalam derajat):
        phi        = sudut geser dalam tanah
        delta      = sudut gesek antara tanah dan dinding (gesekan dinding)
                     umumnya: delta = 0  s/d  2*phi/3
        alpha_wall = sudut dinding dari horizontal
                     dinding vertikal: alpha_wall = 90 derajat
        beta_slope = kemiringan permukaan tanah di belakang dinding
                     permukaan horizontal: beta_slope = 0 derajat

    Batasan:
        delta  <= phi             (syarat fisik)
        beta_slope < phi          (syarat agar rumus valid)
        Jika delta = 0 dan alpha_wall = 90 dan beta_slope = 0
            => Ka Coulomb = Ka Rankine

    Referensi:
        [R1] SNI 8460:2017, Pasal 5.3.4
        [R5] ASCE 7-22, §C11.8.2, Persamaan C11.8-1
        [R2] NAVFAC DM-7.01, Ch. 4, §4.4, Tabel 5, Hal. 4-13
        [R4] USS Sheet Pile Design Manual (1975), Ch. 2, Hal. 2-7

    Parameter:
        phi        : sudut geser dalam [derajat]
        delta      : sudut gesek tanah-dinding [derajat]
        alpha_wall : sudut dinding dari horizontal [derajat], default 90
        beta_slope : kemiringan permukaan tanah [derajat], default 0

    Return:
        dict standar
    """
    _validasi_phi(phi)
    _validasi_positif("delta", delta)
    _validasi_positif("alpha_wall", alpha_wall)
    _validasi_positif("beta_slope", beta_slope)

    if delta > phi:
        raise ValueError(
            f"delta ({delta} derajat) tidak boleh lebih besar dari phi ({phi} derajat)."
        )
    if beta_slope >= phi:
        raise ValueError(
            f"beta_slope ({beta_slope} derajat) harus < phi ({phi} derajat) agar rumus valid."
        )
    if alpha_wall <= 0 or alpha_wall > 180:
        raise ValueError(
            f"alpha_wall harus 0 < alpha_wall <= 180, diberikan: {alpha_wall}"
        )

    # Hitung tiap bagian rumus secara bertahap
    sin2_alpha_phi   = _sin(alpha_wall + phi) ** 2
    sin2_alpha       = _sin(alpha_wall) ** 2
    sin_alpha_delta  = _sin(alpha_wall - delta)
    sin_phi_delta    = _sin(phi + delta)
    sin_phi_beta     = _sin(phi - beta_slope)
    sin_alpha_beta   = _sin(alpha_wall + beta_slope)

    # Nilai di bawah akar
    nilai_bawah_akar = (sin_phi_delta * sin_phi_beta) / (sin_alpha_delta * sin_alpha_beta)

    # Cek nilai bawah akar tidak negatif
    if nilai_bawah_akar < 0:
        raise ValueError(
            "Kombinasi parameter menghasilkan nilai negatif di bawah akar. "
            "Periksa kembali nilai delta, phi, dan beta_slope."
        )

    sqrt_val = math.sqrt(nilai_bawah_akar)
    faktor   = (1.0 + sqrt_val) ** 2
    penyebut = sin2_alpha * sin_alpha_delta * faktor

    if abs(penyebut) < 1e-12:
        raise ZeroDivisionError("Penyebut rumus Coulomb mendekati nol. Periksa parameter input.")

    Ka = sin2_alpha_phi / penyebut

    # Bandingkan dengan Ka Rankine (delta=0, alpha=90, beta=0)
    Ka_rankine = _tan(45.0 - phi / 2.0) ** 2

    langkah: list[str] = [
        *_header("Koefisien Tekanan Aktif Coulomb (Ka)"),
        "",
        _sub("Rumus", "Ka = sin^2(alpha_wall + phi)"),
        _sub("",      "     / { sin^2(alpha_wall) * sin(alpha_wall - delta) *"),
        _sub("",      "         [1 + sqrt(sin(phi+delta)*sin(phi-beta_slope)"),
        _sub("",      "               / (sin(alpha_wall-delta)*sin(alpha_wall+beta_slope)))]^2 }"),
        "",
        "  Parameter:",
        _sub("  phi",        f"{phi:.2f} derajat (sudut geser dalam tanah)"),
        _sub("  delta",      f"{delta:.2f} derajat (gesekan tanah-dinding)"),
        _sub("  alpha_wall", f"{alpha_wall:.2f} derajat (sudut dinding dari horizontal)"),
        _sub("  beta_slope", f"{beta_slope:.2f} derajat (kemiringan permukaan tanah)"),
        "",
        "  Hitung masing-masing suku:",
        _sub("  Hitung",  f"sin^2(alpha_wall + phi)"),
        _sub("",          f"= sin^2({alpha_wall:.2f} + {phi:.2f})"),
        _sub("",          f"= sin^2({alpha_wall + phi:.2f} derajat)"),
        _sub("",          f"= ({_sin(alpha_wall + phi):.6f})^2"),
        _sub("",          f"= {sin2_alpha_phi:.6f}  [PEMBILANG]"),
        "",
        _sub("  Hitung",  f"sin^2(alpha_wall)"),
        _sub("",          f"= sin^2({alpha_wall:.2f} derajat) = {sin2_alpha:.6f}"),
        "",
        _sub("  Hitung",  f"sin(alpha_wall - delta)"),
        _sub("",          f"= sin({alpha_wall:.2f} - {delta:.2f})"),
        _sub("",          f"= sin({alpha_wall - delta:.2f} derajat) = {sin_alpha_delta:.6f}"),
        "",
        _sub("  Hitung",  "Nilai bawah akar = sin(phi+delta)*sin(phi-beta_slope)"),
        _sub("",          f"                   / (sin(alpha_wall-delta)*sin(alpha_wall+beta_slope))"),
        _sub("",          f"sin(phi+delta)     = sin({phi+delta:.2f} derajat) = {sin_phi_delta:.6f}"),
        _sub("",          f"sin(phi-beta_slope)= sin({phi-beta_slope:.2f} derajat) = {sin_phi_beta:.6f}"),
        _sub("",          f"sin(alpha_wall+beta_slope) = sin({alpha_wall+beta_slope:.2f} derajat) = {sin_alpha_beta:.6f}"),
        _sub("",          f"Nilai bawah akar   = ({sin_phi_delta:.6f} x {sin_phi_beta:.6f})"),
        _sub("",          f"                   / ({sin_alpha_delta:.6f} x {sin_alpha_beta:.6f})"),
        _sub("",          f"                   = {nilai_bawah_akar:.6f}"),
        _sub("",          f"sqrt(...)          = {sqrt_val:.6f}"),
        _sub("",          f"(1 + sqrt(...))^2  = (1 + {sqrt_val:.6f})^2 = {faktor:.6f}"),
        "",
        _sub("  Penyebut", f"= {sin2_alpha:.6f} x {sin_alpha_delta:.6f} x {faktor:.6f}"),
        _sub("",           f"= {penyebut:.6f}"),
        "",
        _sub("  Ka",        f"= {sin2_alpha_phi:.6f} / {penyebut:.6f}"),
        "",
        _sub("Hasil",   f"Ka (Coulomb)  = {Ka:.6f}"),
        _sub("",        f"Ka (Rankine)  = {Ka_rankine:.6f}  [pembanding, delta=0]"),
        _sub("",        f"Selisih       = {abs(Ka - Ka_rankine):.6f}"),
        _sub("Satuan",  "(tak berdimensi)"),
        "",
        _sub("Standar", "SNI 8460:2017, Pasal 5.3.4"),
        _sub("",        "ASCE 7-22, Pasal C11.8.2, Persamaan C11.8-1"),
        _sub("",        "NAVFAC DM-7.01, Ch. 4, Pasal 4.4, Tabel 5, Hal. 4-13"),
        _sub("",        "USS Sheet Pile Design Manual (1975), Ch. 2, Hal. 2-7"),
        _garis(),
    ]

    referensi = [
        "SNI 8460:2017, Pasal 5.3.4",
        "ASCE 7-22, Pasal C11.8.2, Persamaan C11.8-1",
        "NAVFAC DM-7.01, Ch. 4, Pasal 4.4, Tabel 5, Hal. 4-13",
        "USS Sheet Pile Design Manual (1975), Ch. 2, Hal. 2-7",
    ]

    return _hasil_dict(
        nilai     = round(Ka, 6),
        langkah   = langkah,
        referensi = referensi,
        satuan    = "tak berdimensi",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. KOEFISIEN TEKANAN AT-REST
# ─────────────────────────────────────────────────────────────────────────────

def hitung_Ko(phi: float, OCR: float = 1.0) -> dict:
    """
    Hitung koefisien tekanan tanah at-rest (Ko).

    Rumus:
        Ko_NC = 1 - sin(phi)                 [Jaky, 1944 — tanah NC]
        Ko    = Ko_NC * OCR^sin(phi)          [Schmidt, 1966 — koreksi OC]

    Keterangan:
        NC  = Normally Consolidated (OCR = 1)
        OC  = Overconsolidated (OCR > 1)
        OCR = Over-Consolidation Ratio = sigma_v_prakonsolidasi / sigma_v_sekarang

    Catatan:
        - Untuk tanah lunak Jabodetabek (lempung muda, aluvial): OCR ~ 1.0–2.0
        - Ko digunakan sebagai kondisi awal sebelum galian dimulai

    Referensi:
        [R2] NAVFAC DM-7.01, Ch. 4, §4.2, Hal. 4-5
        [R1] SNI 8460:2017, Pasal 5.3.1
        Jaky, J. (1944). The coefficient of earth pressure at rest.
        Schmidt, B. (1966). Discussion of Earth pressures at rest related to
            stress history. Canadian Geotechnical Journal, 3(4).

    Parameter:
        phi : float — sudut geser dalam [derajat]
        OCR : float — over-consolidation ratio (default 1.0 = tanah NC)

    Return:
        dict standar
    """
    _validasi_phi(phi)
    if OCR < 1.0:
        raise ValueError(f"OCR harus >= 1.0, diberikan: {OCR}")

    sin_phi = _sin(phi)
    Ko_NC   = 1.0 - sin_phi
    Ko      = Ko_NC * (OCR ** sin_phi)

    langkah: list[str] = [
        *_header("Koefisien Tekanan At-Rest (Ko)"),
        "",
        "  Langkah 1 — Ko untuk tanah Normally Consolidated (NC):",
        _sub("  Rumus",  "Ko_NC = 1 - sin(phi)  [Jaky, 1944]"),
        _sub("  Nilai",  f"phi = {phi:.1f} derajat"),
        _sub("  Hitung", f"sin({phi:.1f} derajat) = {sin_phi:.6f}"),
        _sub("  ",       f"Ko_NC = 1 - {sin_phi:.6f}"),
        _sub("  Hasil",  f"Ko_NC = {Ko_NC:.6f}"),
        "",
    ]

    if abs(OCR - 1.0) < 1e-6:
        langkah += [
            _sub("  OCR",   f"= {OCR:.2f}  (tanah Normally Consolidated)"),
            _sub("  Hasil", f"Ko = Ko_NC = {Ko:.6f}"),
        ]
    else:
        langkah += [
            "  Langkah 2 — Koreksi Over-Consolidation (Schmidt, 1966):",
            _sub("  Rumus",  "Ko = Ko_NC * OCR^sin(phi)"),
            _sub("  Nilai",  f"Ko_NC = {Ko_NC:.6f}"),
            _sub("  ",       f"OCR   = {OCR:.2f}"),
            _sub("  ",       f"sin(phi) = {sin_phi:.6f}  (eksponen)"),
            _sub("  Hitung", f"OCR^sin(phi) = {OCR:.2f}^{sin_phi:.6f}"),
            _sub("  ",       f"           = {OCR ** sin_phi:.6f}"),
            _sub("  ",       f"Ko = {Ko_NC:.6f} x {OCR ** sin_phi:.6f}"),
            _sub("  Hasil",  f"Ko = {Ko:.6f}"),
        ]

    langkah += [
        "",
        _sub("Hasil",   f"Ko = {Ko:.6f}"),
        _sub("",        f"Ko = {Ko:.4f}  (dibulatkan 4 desimal)"),
        _sub("Satuan",  "(tak berdimensi)"),
        "",
        _sub("Standar", "SNI 8460:2017, Pasal 5.3.1"),
        _sub("",        "NAVFAC DM-7.01, Ch. 4, Pasal 4.2, Hal. 4-5"),
        _sub("",        "Jaky, J. (1944) — The coefficient of earth pressure at rest"),
        _sub("",        "Schmidt, B. (1966) — Canadian Geotechnical Journal, 3(4)"),
        _garis(),
    ]

    referensi = [
        "SNI 8460:2017, Pasal 5.3.1",
        "NAVFAC DM-7.01, Ch. 4, Pasal 4.2, Hal. 4-5",
        "Jaky, J. (1944) — Koefisien tekanan at-rest",
        "Schmidt, B. (1966) — Canadian Geotechnical Journal, 3(4)",
    ]

    return _hasil_dict(
        nilai     = round(Ko, 6),
        langkah   = langkah,
        referensi = referensi,
        satuan    = "tak berdimensi",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. TEKANAN AKTIF PADA SATU TITIK KEDALAMAN
# ─────────────────────────────────────────────────────────────────────────────

def hitung_tekanan_aktif(
    z        : float,
    gamma    : float,
    phi      : float,
    cohesion : float,
    surcharge: float,
    muka_air : float,
    gamma_sat: float | None = None,
    gamma_w  : float        = GAMMA_W_DEFAULT,
    Ka       : float | None = None,
) -> dict:
    """
    Hitung tekanan tanah aktif pada kedalaman z (satu titik).

    Urutan perhitungan:
        1. Tegangan vertikal total:
               sigma_v_total = gamma * z_kering + gamma_sat * z_jenuh + surcharge
        2. Tekanan air pori:
               u = gamma_w * hw
               hw = max(0, z - muka_air)
        3. Tegangan vertikal efektif:
               sigma_v = sigma_v_total - u
        4. Tekanan aktif (kondisi drainase, tanah c-phi):
               sigma_h_aktif = Ka * sigma_v - 2 * cohesion * sqrt(Ka)
               (nilai minimum = 0 — zona tarik diabaikan)
        5. Tekanan total (termasuk air pori):
               sigma_h_total = sigma_h_aktif + u

    Kondisi:
        z <= muka_air : tanah di atas MAT, u = 0, gamma = gamma_kering
        z >  muka_air : tanah di bawah MAT, u = gamma_w*(z-muka_air),
                        gamma efektif = gamma_sat - gamma_w

    Referensi:
        [R1] SNI 8460:2017, Pasal 5.2.3 dan 5.4.2
        [R2] NAVFAC DM-7.01, Ch. 4, §4.3(b), Hal. 4-10
        [R4] USS Sheet Pile Design Manual (1975), Ch. 2, §2.4

    Parameter:
        z         : kedalaman dari permukaan tanah [m]
        gamma     : berat volume tanah di atas MAT [kN/m3]
        phi       : sudut geser dalam [derajat]
        cohesion  : kohesi tanah [kPa]
        surcharge : beban tambahan di permukaan [kPa]
        muka_air  : kedalaman muka air tanah dari permukaan [m]
        gamma_sat : berat volume jenuh [kN/m3] (default = gamma + 1.5)
        gamma_w   : berat volume air [kN/m3] (default 9.81)
        Ka        : koefisien aktif (jika None, dihitung Rankine)

    Return:
        dict standar; "nilai" adalah dict:
            {sigma_v, u, sigma_h_aktif, sigma_h_total}
    """
    _validasi_positif("z",         z)
    _validasi_positif("gamma",     gamma)
    _validasi_positif("cohesion",  cohesion)
    _validasi_positif("surcharge", surcharge)
    _validasi_positif("muka_air",  muka_air)
    _validasi_phi(phi)

    # Default gamma_sat jika tidak diberikan
    if gamma_sat is None:
        gamma_sat = gamma + 1.5
        catatan_sat = f"gamma_sat tidak diberikan, diasumsikan gamma + 1.5 = {gamma_sat:.2f} kN/m3"
    else:
        _validasi_positif("gamma_sat", gamma_sat)
        if gamma_sat < gamma:
            raise ValueError(f"gamma_sat ({gamma_sat}) harus >= gamma ({gamma})")
        catatan_sat = f"gamma_sat = {gamma_sat:.2f} kN/m3 (nilai yang diberikan)"

    # Hitung Ka jika tidak diberikan
    ka_dari_input = Ka is not None
    if Ka is None:
        Ka = _tan(45.0 - phi / 2.0) ** 2
        catatan_ka = f"Ka dihitung otomatis (Rankine): Ka = {Ka:.6f}"
    else:
        catatan_ka = f"Ka diberikan sebagai input: Ka = {Ka:.6f}"

    sqrt_Ka = math.sqrt(Ka)

    # ── Hitung tegangan vertikal ─────────────────────────────────────────────
    hw          = max(0.0, z - muka_air)            # tinggi kolom air [m]
    z_kering    = min(z, muka_air)                  # kedalaman di atas MAT [m]
    z_jenuh     = max(0.0, z - muka_air)            # kedalaman di bawah MAT [m]
    gamma_eff   = gamma_sat - gamma_w               # berat volume efektif [kN/m3]

    # Tegangan vertikal total
    sigma_v_total = (
        gamma   * z_kering
        + gamma_sat * z_jenuh   # di bawah MAT pakai gamma_sat
        + surcharge
    )

    # Tekanan air pori
    u = gamma_w * hw

    # Tegangan vertikal efektif
    sigma_v = sigma_v_total - u

    # Tekanan aktif efektif
    sigma_h_aktif_eff = Ka * sigma_v - 2.0 * cohesion * sqrt_Ka
    sigma_h_aktif_eff = max(0.0, sigma_h_aktif_eff)    # zona tarik = 0

    # Tekanan aktif total (tambah tekanan air pori)
    sigma_h_total = sigma_h_aktif_eff + u

    # ── Hitung kedalaman zona tarik (Tension Crack Depth, zt) ───────────────
    # Ka*sigma_v = 2*c*sqrt(Ka)  => sigma_v = 2*c/sqrt(Ka)
    # sigma_v (di atas MAT) = gamma*z + surcharge => zt = (2c/sqrt(Ka) - q) / gamma
    if abs(sqrt_Ka) > 1e-9 and gamma > 1e-9:
        zt_teoritis = (2.0 * cohesion / sqrt_Ka - surcharge) / gamma
        zt = max(0.0, zt_teoritis)
    else:
        zt = 0.0

    langkah: list[str] = [
        *_header(f"Tekanan Tanah Aktif pada Kedalaman z = {z:.2f} m"),
        "",
        "  Data input:",
        _sub("  z",          f"{z:.2f} m  (kedalaman tinjauan)"),
        _sub("  gamma",      f"{gamma:.2f} kN/m3  (berat volume tanah di atas MAT)"),
        _sub("  gamma_sat",  f"{gamma_sat:.2f} kN/m3  ({catatan_sat.split('kN/m3')[0].strip()})"),
        _sub("  gamma_w",    f"{gamma_w:.2f} kN/m3  (berat volume air)"),
        _sub("  phi",        f"{phi:.1f} derajat"),
        _sub("  cohesion",   f"{cohesion:.2f} kPa"),
        _sub("  surcharge",  f"{surcharge:.2f} kPa"),
        _sub("  muka_air",   f"{muka_air:.2f} m dari permukaan"),
        _sub("  Ka",         f"{Ka:.6f}  ({catatan_ka})"),
        "",
        "  Langkah 1 — Hitung tinggi kolom air (hw):",
        _sub("  Rumus",  "hw = max(0, z - muka_air)"),
        _sub("  Hitung", f"hw = max(0, {z:.2f} - {muka_air:.2f})"),
        _sub("  Hasil",  f"hw = {hw:.4f} m"),
        "",
        "  Langkah 2 — Hitung tegangan vertikal total (sigma_v_total):",
        _sub("  Rumus",  "sigma_v_total = gamma * z_kering + gamma_sat * z_jenuh + surcharge"),
        _sub("  Hitung", f"z_kering = min({z:.2f}, {muka_air:.2f}) = {z_kering:.4f} m"),
        _sub("  ",       f"z_jenuh  = max(0, {z:.2f} - {muka_air:.2f}) = {z_jenuh:.4f} m"),
        _sub("  ",       f"sigma_v_total = {gamma:.2f} x {z_kering:.4f}"),
        _sub("  ",       f"              + {gamma_sat:.2f} x {z_jenuh:.4f}"),
        _sub("  ",       f"              + {surcharge:.2f}  (surcharge)"),
        _sub("  ",       f"            = {gamma*z_kering:.4f} + {gamma_sat*z_jenuh:.4f} + {surcharge:.2f}"),
        _sub("  Hasil",  f"sigma_v_total = {sigma_v_total:.4f} kPa"),
        "",
        "  Langkah 3 — Hitung tekanan air pori (u):",
        _sub("  Rumus",  "u = gamma_w * hw"),
        _sub("  Hitung", f"u = {gamma_w:.2f} x {hw:.4f}"),
        _sub("  Hasil",  f"u = {u:.4f} kPa"),
        "",
        "  Langkah 4 — Hitung tegangan vertikal efektif (sigma_v):",
        _sub("  Rumus",  "sigma_v = sigma_v_total - u"),
        _sub("  Hitung", f"sigma_v = {sigma_v_total:.4f} - {u:.4f}"),
        _sub("  Hasil",  f"sigma_v = {sigma_v:.4f} kPa"),
        "",
        "  Langkah 5 — Hitung tekanan aktif efektif:",
        _sub("  Rumus",  "sigma_h_aktif = Ka * sigma_v - 2 * cohesion * sqrt(Ka)"),
        _sub("  ",       "  (nilai minimum = 0, zona tarik diabaikan)"),
        _sub("  Hitung", f"sqrt(Ka) = sqrt({Ka:.6f}) = {sqrt_Ka:.6f}"),
        _sub("  ",       f"Ka * sigma_v = {Ka:.6f} x {sigma_v:.4f} = {Ka*sigma_v:.4f} kPa"),
        _sub("  ",       f"2 * cohesion * sqrt(Ka) = 2 x {cohesion:.2f} x {sqrt_Ka:.6f}"),
        _sub("  ",       f"                       = {2*cohesion*sqrt_Ka:.4f} kPa"),
        _sub("  ",       f"sigma_h_aktif = {Ka*sigma_v:.4f} - {2*cohesion*sqrt_Ka:.4f}"),
        _sub("  ",       f"             = {Ka*sigma_v - 2*cohesion*sqrt_Ka:.4f} kPa  (sebelum min 0)"),
        _sub("  Hasil",  f"sigma_h_aktif (efektif) = {sigma_h_aktif_eff:.4f} kPa"),
        "",
    ]

    # Info zona tarik
    if zt > 0 and z <= muka_air:
        langkah += [
            f"  Catatan — Kedalaman zona tarik (tension crack depth):",
            _sub("  Rumus",  "zt = (2*cohesion/sqrt(Ka) - surcharge) / gamma"),
            _sub("  Hitung", f"zt = (2 x {cohesion:.2f} / {sqrt_Ka:.4f} - {surcharge:.2f}) / {gamma:.2f}"),
            _sub("  Hasil",  f"zt = {zt:.4f} m"),
            _sub("  ",       "Pada kedalaman di atas zt, tekanan aktif = 0"),
            "",
        ]

    langkah += [
        "  Langkah 6 — Hitung tekanan aktif total (termasuk air pori):",
        _sub("  Rumus",  "sigma_h_total = sigma_h_aktif + u"),
        _sub("  Hitung", f"sigma_h_total = {sigma_h_aktif_eff:.4f} + {u:.4f}"),
        _sub("  Hasil",  f"sigma_h_total = {sigma_h_total:.4f} kPa"),
        "",
        _sub("Rangkuman", ""),
        _sub("  sigma_v_total", f"{sigma_v_total:.4f} kPa"),
        _sub("  u",             f"{u:.4f} kPa"),
        _sub("  sigma_v",       f"{sigma_v:.4f} kPa  (efektif)"),
        _sub("  sigma_h_aktif", f"{sigma_h_aktif_eff:.4f} kPa  (efektif)"),
        _sub("  sigma_h_total", f"{sigma_h_total:.4f} kPa  (total termasuk air pori)"),
        _sub("Satuan",  "kPa"),
        "",
        _sub("Standar", "SNI 8460:2017, Pasal 5.2.3 dan 5.4.2"),
        _sub("",        "NAVFAC DM-7.01, Ch. 4, Pasal 4.3(b), Hal. 4-10"),
        _sub("",        "USS Sheet Pile Design Manual (1975), Ch. 2, Pasal 2.4"),
        _garis(),
    ]

    referensi = [
        "SNI 8460:2017, Pasal 5.2.3 dan 5.4.2",
        "NAVFAC DM-7.01, Ch. 4, Pasal 4.3(b), Hal. 4-10",
        "USS Sheet Pile Design Manual (1975), Ch. 2, Pasal 2.4",
    ]

    return _hasil_dict(
        nilai={
            "sigma_v_total"  : round(sigma_v_total,        4),
            "u"              : round(u,                     4),
            "sigma_v"        : round(sigma_v,               4),
            "sigma_h_aktif"  : round(sigma_h_aktif_eff,     4),
            "sigma_h_total"  : round(sigma_h_total,         4),
            "hw"             : round(hw,                    4),
            "zt"             : round(zt,                    4),
        },
        langkah   = langkah,
        referensi = referensi,
        satuan    = "kPa",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. TEKANAN PASIF PADA SATU TITIK KEDALAMAN
# ─────────────────────────────────────────────────────────────────────────────

def hitung_tekanan_pasif(
    z        : float,
    gamma    : float,
    phi      : float,
    cohesion : float,
    muka_air : float  = 0.0,
    gamma_sat: float  | None = None,
    gamma_w  : float         = GAMMA_W_DEFAULT,
    Kp       : float  | None = None,
) -> dict:
    """
    Hitung tekanan tanah pasif pada kedalaman z (satu titik).

    Tekanan pasif dihitung dari permukaan dasar galian ke bawah
    (kedalaman di depan turap).

    Rumus:
        sigma_h_pasif = Kp * sigma_v + 2 * cohesion * sqrt(Kp)
        sigma_h_total = sigma_h_pasif + u

    Catatan:
        Kp Rankine digunakan (konservatif). Tidak menerapkan delta pada Kp
        untuk sisi depan turap karena gesekan dinding di sisi pasif
        meningkatkan Kp — pilihan konservatif mengabaikan ini.

    Referensi:
        [R1] SNI 8460:2017, Pasal 5.3.3
        [R2] NAVFAC DM-7.01, Ch. 4, §4.3(c), Hal. 4-11
        [R4] USS Sheet Pile Design Manual (1975), Ch. 2, §2.5

    Parameter:
        z         : kedalaman dari dasar galian [m]
        gamma     : berat volume tanah [kN/m3]
        phi       : sudut geser dalam [derajat]
        cohesion  : kohesi tanah [kPa]
        muka_air  : kedalaman MAT dari dasar galian [m] (default 0 = MAT di dasar galian)
        gamma_sat : berat volume jenuh [kN/m3]
        gamma_w   : berat volume air [kN/m3]
        Kp        : koefisien pasif (jika None, dihitung Rankine)

    Return:
        dict standar
    """
    _validasi_positif("z",        z)
    _validasi_positif("gamma",    gamma)
    _validasi_positif("cohesion", cohesion)
    _validasi_phi(phi)

    if gamma_sat is None:
        gamma_sat = gamma + 1.5
    else:
        _validasi_positif("gamma_sat", gamma_sat)

    if Kp is None:
        Kp = _tan(45.0 + phi / 2.0) ** 2
        catatan_kp = f"Kp dihitung otomatis (Rankine): Kp = {Kp:.6f}"
    else:
        catatan_kp = f"Kp diberikan sebagai input: Kp = {Kp:.6f}"

    sqrt_Kp = math.sqrt(Kp)

    hw            = max(0.0, z - muka_air)
    z_kering      = min(z, muka_air)
    z_jenuh       = max(0.0, z - muka_air)

    sigma_v_total = gamma * z_kering + gamma_sat * z_jenuh
    u             = gamma_w * hw
    sigma_v       = sigma_v_total - u

    sigma_h_pasif = Kp * sigma_v + 2.0 * cohesion * sqrt_Kp
    sigma_h_total = sigma_h_pasif + u

    langkah: list[str] = [
        *_header(f"Tekanan Tanah Pasif pada Kedalaman z = {z:.2f} m (dari dasar galian)"),
        "",
        "  Data input:",
        _sub("  z",         f"{z:.2f} m  (dari dasar galian)"),
        _sub("  gamma",     f"{gamma:.2f} kN/m3"),
        _sub("  gamma_sat", f"{gamma_sat:.2f} kN/m3"),
        _sub("  gamma_w",   f"{gamma_w:.2f} kN/m3"),
        _sub("  phi",       f"{phi:.1f} derajat"),
        _sub("  cohesion",  f"{cohesion:.2f} kPa"),
        _sub("  muka_air",  f"{muka_air:.2f} m dari dasar galian"),
        _sub("  Kp",        f"{Kp:.6f}  ({catatan_kp})"),
        "",
        "  Langkah 1 — Hitung tekanan air pori (u):",
        _sub("  Rumus",  "hw = max(0, z - muka_air)  ;  u = gamma_w * hw"),
        _sub("  Hitung", f"hw = max(0, {z:.2f} - {muka_air:.2f}) = {hw:.4f} m"),
        _sub("  Hasil",  f"u  = {gamma_w:.2f} x {hw:.4f} = {u:.4f} kPa"),
        "",
        "  Langkah 2 — Hitung tegangan vertikal efektif (sigma_v):",
        _sub("  Hitung", f"sigma_v_total = {gamma:.2f} x {z_kering:.4f} + {gamma_sat:.2f} x {z_jenuh:.4f}"),
        _sub("  ",       f"             = {gamma*z_kering:.4f} + {gamma_sat*z_jenuh:.4f}"),
        _sub("  ",       f"             = {sigma_v_total:.4f} kPa"),
        _sub("  ",       f"sigma_v = {sigma_v_total:.4f} - {u:.4f} = {sigma_v:.4f} kPa"),
        "",
        "  Langkah 3 — Hitung tekanan pasif:",
        _sub("  Rumus",  "sigma_h_pasif = Kp * sigma_v + 2 * cohesion * sqrt(Kp)"),
        _sub("  Hitung", f"sqrt(Kp) = sqrt({Kp:.6f}) = {sqrt_Kp:.6f}"),
        _sub("  ",       f"Kp * sigma_v = {Kp:.6f} x {sigma_v:.4f} = {Kp*sigma_v:.4f} kPa"),
        _sub("  ",       f"2 * cohesion * sqrt(Kp) = 2 x {cohesion:.2f} x {sqrt_Kp:.6f} = {2*cohesion*sqrt_Kp:.4f} kPa"),
        _sub("  Hasil",  f"sigma_h_pasif (efektif) = {sigma_h_pasif:.4f} kPa"),
        "",
        "  Langkah 4 — Tekanan pasif total:",
        _sub("  Rumus",  "sigma_h_total = sigma_h_pasif + u"),
        _sub("  Hasil",  f"sigma_h_total = {sigma_h_pasif:.4f} + {u:.4f} = {sigma_h_total:.4f} kPa"),
        "",
        _sub("Rangkuman", ""),
        _sub("  sigma_v",      f"{sigma_v:.4f} kPa  (efektif)"),
        _sub("  sigma_h_pasif",f"{sigma_h_pasif:.4f} kPa  (efektif)"),
        _sub("  sigma_h_total",f"{sigma_h_total:.4f} kPa  (total)"),
        _sub("Satuan",  "kPa"),
        "",
        _sub("Standar", "SNI 8460:2017, Pasal 5.3.3"),
        _sub("",        "NAVFAC DM-7.01, Ch. 4, Pasal 4.3(c), Hal. 4-11"),
        _sub("",        "USS Sheet Pile Design Manual (1975), Ch. 2, Pasal 2.5"),
        _garis(),
    ]

    referensi = [
        "SNI 8460:2017, Pasal 5.3.3",
        "NAVFAC DM-7.01, Ch. 4, Pasal 4.3(c), Hal. 4-11",
        "USS Sheet Pile Design Manual (1975), Ch. 2, Pasal 2.5",
    ]

    return _hasil_dict(
        nilai={
            "sigma_v"       : round(sigma_v,        4),
            "u"             : round(u,               4),
            "sigma_h_pasif" : round(sigma_h_pasif,   4),
            "sigma_h_total" : round(sigma_h_total,   4),
        },
        langkah   = langkah,
        referensi = referensi,
        satuan    = "kPa",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. DISTRIBUSI TEKANAN SEPANJANG KEDALAMAN (MULTI-LAPISAN)
# ─────────────────────────────────────────────────────────────────────────────

def hitung_distribusi_tekanan(
    lapisan_tanah : list[dict],
    H             : float,
    D             : float,
    muka_air      : float,
    surcharge     : float,
    gamma_w       : float = GAMMA_W_DEFAULT,
    dz            : float = 0.1,
    metode_Ka     : str   = "rankine",
    delta         : float = 0.0,
) -> dict:
    """
    Hitung distribusi tekanan tanah lateral sepanjang kedalaman turap.

    Turap dibagi dua zona:
        Zona AKTIF  (belakang turap): z = 0  ..  H + D
        Zona PASIF  (depan turap)  : z = H   ..  H + D  (tekanan pasif dihitung dari dasar galian)

    Tekanan neto = tekanan aktif - tekanan pasif (pada tiap titik)

    Format lapisan_tanah (list of dict):
        [
          {
            "nama"     : "Lempung lunak",   # nama lapisan (string)
            "tebal"    : 4.0,               # tebal lapisan [m]
            "gamma"    : 16.0,              # berat volume [kN/m3]
            "gamma_sat": 17.0,              # berat volume jenuh [kN/m3]
            "phi"      : 10.0,              # sudut geser [derajat]
            "cohesion" : 15.0,              # kohesi [kPa]
          },
          { ... lapisan 2 ... },
          ...
        ]

    Referensi:
        [R1] SNI 8460:2017, Pasal 5.2–5.4
        [R2] NAVFAC DM-7.02, Ch. 3, §3.1–3.2
        [R4] USS Sheet Pile Design Manual (1975), Ch. 3, §3.3–3.4

    Parameter:
        lapisan_tanah : list[dict] — lapisan tanah dari atas ke bawah
        H             : tinggi turap di atas galian [m]
        D             : kedalaman penetrasi [m]
        muka_air      : kedalaman MAT dari permukaan [m]
        surcharge     : beban merata di belakang turap [kPa]
        gamma_w       : berat volume air [kN/m3]
        dz            : interval kedalaman komputasi [m]
        metode_Ka     : "rankine" atau "coulomb"
        delta         : sudut gesek tanah-dinding [derajat] (untuk Coulomb)

    Return:
        dict standar; "nilai" adalah dict:
            {
                "z_array"           : np.array,   # kedalaman [m]
                "tekanan_aktif"     : np.array,   # [kPa]
                "tekanan_pasif"     : np.array,   # [kPa] (0 di atas galian)
                "tekanan_air_pori"  : np.array,   # [kPa]
                "tekanan_neto"      : np.array,   # aktif - pasif [kPa]
                "batas_lapisan"     : list[float],# kedalaman batas antar lapisan [m]
                "H"                 : H,
                "D"                 : D,
            }
    """
    # ── Validasi ─────────────────────────────────────────────────────────────
    if not lapisan_tanah:
        raise ValueError("Minimal satu lapisan tanah harus ada.")
    if H <= 0:
        raise ValueError(f"H (tinggi galian) harus > 0, diberikan: {H}")
    if D <= 0:
        raise ValueError(f"D (penetrasi) harus > 0, diberikan: {D}")
    _validasi_positif("muka_air",  muka_air)
    _validasi_positif("surcharge", surcharge)

    kunci_wajib = {"tebal", "gamma", "gamma_sat", "phi", "cohesion"}
    for i, lyr in enumerate(lapisan_tanah):
        if not kunci_wajib.issubset(lyr.keys()):
            raise ValueError(
                f"Lapisan ke-{i+1} tidak lengkap. Kunci yang diperlukan: {kunci_wajib}"
            )

    metode_Ka = metode_Ka.lower()
    if metode_Ka not in ("rankine", "coulomb"):
        raise ValueError(f"metode_Ka harus 'rankine' atau 'coulomb', diberikan: {metode_Ka}")

    # ── Batas bawah lapisan ───────────────────────────────────────────────────
    z_total     = H + D
    batas       = []   # kedalaman batas bawah tiap lapisan [m]
    z_cursor    = 0.0
    for lyr in lapisan_tanah:
        z_cursor += lyr["tebal"]
        batas.append(round(z_cursor, 6))
    if batas[-1] < z_total:
        # Perpanjang lapisan terakhir jika perlu
        batas[-1] = z_total

    def _ambil_lapisan(z: float) -> dict:
        """Dapatkan parameter lapisan yang berlaku pada kedalaman z."""
        z_batas = 0.0
        for lyr, b in zip(lapisan_tanah, batas):
            if z <= b + 1e-9:
                return lyr
            z_batas = b
        return lapisan_tanah[-1]   # lapisan paling bawah

    def _hitung_sigma_v_efektif(z: float) -> tuple[float, float, dict]:
        """
        Hitung sigma_v efektif dan u pada kedalaman z
        dengan mempertimbangkan multi-lapisan.
        Mengembalikan: (sigma_v, u, lapisan_aktif)
        """
        sigma_v_total = surcharge
        z_cursor_     = 0.0
        lyr_aktif     = lapisan_tanah[0]

        for lyr, batas_lyr in zip(lapisan_tanah, batas):
            lyr_aktif = lyr
            if z <= batas_lyr + 1e-9:
                # Titik ada di dalam lapisan ini
                dz_lap    = z - z_cursor_
                dz_kering = max(0.0, min(dz_lap, max(0.0, muka_air - z_cursor_)))
                dz_jenuh  = max(0.0, dz_lap - dz_kering)
                sigma_v_total += lyr["gamma"] * dz_kering + lyr["gamma_sat"] * dz_jenuh
                break
            else:
                # Lapisan penuh
                dz_lap    = batas_lyr - z_cursor_
                dz_kering = max(0.0, min(dz_lap, max(0.0, muka_air - z_cursor_)))
                dz_jenuh  = max(0.0, dz_lap - dz_kering)
                sigma_v_total += lyr["gamma"] * dz_kering + lyr["gamma_sat"] * dz_jenuh
                z_cursor_ = batas_lyr

        hw    = max(0.0, z - muka_air)
        u_    = gamma_w * hw
        sv_   = sigma_v_total - u_
        return (sv_, u_, lyr_aktif)

    # ── Array kedalaman ───────────────────────────────────────────────────────
    z_arr = np.arange(0.0, z_total + dz / 2.0, dz)
    z_arr = np.round(z_arr, 6)

    ta_arr  = np.zeros(len(z_arr))   # tekanan aktif efektif
    tp_arr  = np.zeros(len(z_arr))   # tekanan pasif efektif (0 di atas galian)
    u_arr   = np.zeros(len(z_arr))   # tekanan air pori
    tn_arr  = np.zeros(len(z_arr))   # tekanan neto = aktif - pasif

    langkah_distribusi: list[str] = [
        *_header("Distribusi Tekanan Tanah Lateral"),
        "",
        f"  H (tinggi galian)   = {H:.2f} m",
        f"  D (kedalaman penetrasi) = {D:.2f} m",
        f"  Kedalaman total     = {z_total:.2f} m",
        f"  Muka air tanah      = {muka_air:.2f} m dari permukaan",
        f"  Surcharge           = {surcharge:.2f} kPa",
        f"  Metode Ka           = {metode_Ka.upper()}",
        f"  Interval dz         = {dz:.2f} m",
        "",
        "  Lapisan tanah:",
    ]

    for i, lyr in enumerate(lapisan_tanah):
        langkah_distribusi.append(
            f"    Lapisan {i+1}: {lyr.get('nama',''):<20}  "
            f"tebal={lyr['tebal']:.1f}m  "
            f"gamma={lyr['gamma']:.1f} kN/m3  "
            f"phi={lyr['phi']:.1f} derajat  "
            f"c={lyr['cohesion']:.1f} kPa"
        )

    langkah_distribusi += [
        "",
        f"  {'z(m)':>6} {'sigma_v(kPa)':>14} {'u(kPa)':>10} "
        f"{'Pa(kPa)':>10} {'Pp(kPa)':>10} {'Pneto(kPa)':>12} {'Zona':>10}",
        "  " + "-" * 72,
    ]

    for idx, z in enumerate(z_arr):
        sv, u_z, lyr = _hitung_sigma_v_efektif(z)

        # Tentukan Ka untuk lapisan ini
        phi_lyr = lyr["phi"]
        if metode_Ka == "rankine":
            Ka_z = _tan(45.0 - phi_lyr / 2.0) ** 2
        else:
            Ka_r = hitung_Ka_coulomb(phi_lyr, delta)
            Ka_z = Ka_r["nilai"]

        Kp_z     = _tan(45.0 + phi_lyr / 2.0) ** 2
        cohesion_z = lyr["cohesion"]
        sqrt_Ka  = math.sqrt(Ka_z)
        sqrt_Kp  = math.sqrt(Kp_z)

        # Tekanan aktif (belakang turap)
        pa = max(0.0, Ka_z * sv - 2.0 * cohesion_z * sqrt_Ka)

        # Tekanan pasif (depan turap — hanya di bawah dasar galian)
        if z > H - dz / 2.0:
            # Kedalaman dari dasar galian
            z_pasif = z - H
            sv_p, u_p, lyr_p = _hitung_sigma_v_efektif(z)
            # Re-hitung sigma_v dari dasar galian saja (pasif mulai dari 0)
            sv_pasif = max(0.0, Kp_z * (sv_p) + 2.0 * cohesion_z * sqrt_Kp)
            pp = sv_pasif
        else:
            pp = 0.0

        ta_arr[idx] = pa
        tp_arr[idx] = pp
        u_arr[idx]  = u_z
        tn_arr[idx] = pa - pp

        # Log tabel (setiap 0.5 m atau titik penting)
        zona = "aktif" if z <= H + dz/2 else "pasif"
        if abs(z % 0.5) < dz / 2.0 or abs(z - H) < dz / 2.0 or abs(z - muka_air) < dz / 2.0:
            langkah_distribusi.append(
                f"  {z:>6.2f} {sv:>14.3f} {u_z:>10.3f} "
                f"{pa:>10.3f} {pp:>10.3f} {pa-pp:>12.3f} {zona:>10}"
            )

    langkah_distribusi += [
        "  " + "-" * 72,
        "",
        "  Keterangan kolom:",
        "    z(m)        = kedalaman dari permukaan tanah",
        "    sigma_v     = tegangan vertikal efektif",
        "    u           = tekanan air pori",
        "    Pa          = tekanan aktif efektif",
        "    Pp          = tekanan pasif efektif (0 di atas dasar galian)",
        "    Pneto       = Pa - Pp (positif = aktif mendominasi)",
        "",
        _sub("Standar", "SNI 8460:2017, Pasal 5.2–5.4"),
        _sub("",        "NAVFAC DM-7.02, Ch. 3, Pasal 3.1–3.2"),
        _sub("",        "USS Sheet Pile Design Manual (1975), Ch. 3, Pasal 3.3–3.4"),
        _garis(),
    ]

    referensi = [
        "SNI 8460:2017, Pasal 5.2–5.4",
        "NAVFAC DM-7.02, Ch. 3, Pasal 3.1–3.2",
        "USS Sheet Pile Design Manual (1975), Ch. 3, Pasal 3.3–3.4",
    ]

    return _hasil_dict(
        nilai={
            "z_array"          : z_arr,
            "tekanan_aktif"    : ta_arr,
            "tekanan_pasif"    : tp_arr,
            "tekanan_air_pori" : u_arr,
            "tekanan_neto"     : tn_arr,
            "batas_lapisan"    : batas,
            "H"                : H,
            "D"                : D,
            "muka_air"         : muka_air,
        },
        langkah   = langkah_distribusi,
        referensi = referensi,
        satuan    = "kPa",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 8. PLOT DIAGRAM TEKANAN
# ─────────────────────────────────────────────────────────────────────────────

def plot_diagram_tekanan(
    z_array       : np.ndarray,
    tekanan_aktif : np.ndarray,
    tekanan_pasif : np.ndarray,
    tekanan_neto  : np.ndarray,
    H             : float,
    D             : float,
    muka_air      : float,
    batas_lapisan : list[float] | None = None,
    judul         : str                = "Diagram Tekanan Tanah Lateral",
    satuan_label  : str                = "Tekanan (kPa)",
) -> plt.Figure:
    """
    Buat diagram distribusi tekanan tanah lateral.

    Menghasilkan matplotlib.Figure dengan 3 subplot:
        1. Tekanan Aktif
        2. Tekanan Pasif
        3. Tekanan Neto (aktif - pasif)

    Untuk ditampilkan di Streamlit:
        fig = plot_diagram_tekanan(...)
        st.pyplot(fig)

    Untuk ditampilkan standalone:
        fig = plot_diagram_tekanan(...)
        plt.show()

    Referensi:
        [R4] USS Sheet Pile Design Manual (1975), Ch. 3, Fig. 3-1 s/d 3-5

    Parameter:
        z_array        : array kedalaman [m]
        tekanan_aktif  : array tekanan aktif [kPa]
        tekanan_pasif  : array tekanan pasif [kPa]
        tekanan_neto   : array tekanan neto [kPa]
        H              : tinggi galian [m]
        D              : kedalaman penetrasi [m]
        muka_air       : kedalaman MAT dari permukaan [m]
        batas_lapisan  : list kedalaman batas lapisan [m] (opsional)
        judul          : judul diagram
        satuan_label   : label sumbu x

    Return:
        matplotlib.Figure
    """
    # Konstanta tampilan
    WARNA_AKTIF    = "#C0392B"    # merah tua
    WARNA_PASIF    = "#2471A3"    # biru tua
    WARNA_NETO_POS = "#E67E22"    # oranye (aktif mendominasi)
    WARNA_NETO_NEG = "#1ABC9C"    # hijau tosca (pasif mendominasi)
    WARNA_AIR      = "#AED6F1"    # biru muda (MAT)
    WARNA_GALIAN   = "#7F8C8D"    # abu-abu (batas galian)
    WARNA_LAPISAN  = "#BDC3C7"    # abu-abu muda (batas lapisan)

    fig, axes = plt.subplots(
        1, 3,
        figsize=(14, 8),
        sharey=True,
        gridspec_kw={"wspace": 0.08},
        layout="constrained",
    )
    fig.suptitle(judul, fontsize=13, fontweight="bold", y=0.98)

    z_max = H + D

    def _setup_ax(ax, label_x: str, warna: str, tekanan: np.ndarray, fill_atas: bool = True):
        """Konfigurasi dasar setiap subplot."""
        # Isi area tekanan
        nol = np.zeros_like(tekanan)
        if fill_atas:
            ax.fill_betweenx(z_array, nol, tekanan, where=(tekanan >= 0),
                              color=warna, alpha=0.25, label="Tekanan positif")
            ax.fill_betweenx(z_array, nol, tekanan, where=(tekanan < 0),
                              color=WARNA_NETO_NEG, alpha=0.25, label="Tekanan negatif")
        else:
            ax.fill_betweenx(z_array, nol, tekanan, color=warna, alpha=0.25)

        ax.plot(tekanan, z_array, color=warna, linewidth=1.8)
        ax.axvline(0, color="black", linewidth=0.8, linestyle="-")

        # Garis dasar galian
        ax.axhline(H, color=WARNA_GALIAN, linewidth=1.2, linestyle="--",
                    label=f"Dasar galian (H={H:.1f} m)")

        # Garis MAT
        if 0 < muka_air < z_max:
            ax.axhline(muka_air, color=WARNA_AIR, linewidth=1.2, linestyle=":",
                        label=f"MAT ({muka_air:.1f} m)")

        # Batas lapisan
        if batas_lapisan:
            for batas in batas_lapisan[:-1]:
                if 0 < batas < z_max:
                    ax.axhline(batas, color=WARNA_LAPISAN, linewidth=0.8,
                                linestyle="-.", alpha=0.7)

        ax.set_xlabel(label_x, fontsize=9)
        ax.invert_yaxis()
        ax.set_ylim(z_max + 0.2, -0.2)
        ax.grid(axis="both", linestyle=":", linewidth=0.5, alpha=0.6)
        ax.tick_params(labelsize=8)

        # Anotasi nilai maksimum
        idx_max = np.argmax(np.abs(tekanan))
        val_max = tekanan[idx_max]
        z_max_  = z_array[idx_max]
        if abs(val_max) > 0.1:
            ax.annotate(
                f"{val_max:.1f} kPa\nz={z_max_:.1f} m",
                xy=(val_max, z_max_),
                xytext=(val_max * 0.6 if val_max > 0 else val_max * 0.6, z_max_ + 0.5),
                fontsize=7.5,
                ha="center",
                arrowprops=dict(arrowstyle="->", lw=0.8),
            )

    # ── Subplot 1: Tekanan Aktif ─────────────────────────────────────────────
    ax1 = axes[0]
    _setup_ax(ax1, satuan_label, WARNA_AKTIF, tekanan_aktif, fill_atas=False)
    ax1.set_ylabel("Kedalaman z (m)", fontsize=9)
    ax1.set_title("Tekanan Aktif", fontsize=10, fontweight="bold")

    # Label zona
    ax1.text(
        0.97, 0.03, "Aktif",
        transform=ax1.transAxes, ha="right", va="bottom",
        fontsize=8, color=WARNA_AKTIF, fontstyle="italic",
    )

    # ── Subplot 2: Tekanan Pasif ─────────────────────────────────────────────
    ax2 = axes[1]
    _setup_ax(ax2, satuan_label, WARNA_PASIF, tekanan_pasif, fill_atas=False)
    ax2.set_title("Tekanan Pasif", fontsize=10, fontweight="bold")
    ax2.text(
        0.97, 0.03, "Pasif",
        transform=ax2.transAxes, ha="right", va="bottom",
        fontsize=8, color=WARNA_PASIF, fontstyle="italic",
    )

    # ── Subplot 3: Tekanan Neto ──────────────────────────────────────────────
    ax3 = axes[2]
    _setup_ax(ax3, satuan_label, WARNA_NETO_POS, tekanan_neto, fill_atas=True)
    ax3.set_title("Tekanan Neto (Aktif - Pasif)", fontsize=10, fontweight="bold")
    ax3.text(
        0.97, 0.03, "Neto",
        transform=ax3.transAxes, ha="right", va="bottom",
        fontsize=8, color=WARNA_NETO_POS, fontstyle="italic",
    )

    # ── Legend bersama ───────────────────────────────────────────────────────
    from matplotlib.lines import Line2D
    legend_item = [
        Line2D([0], [0], color=WARNA_GALIAN,  lw=1.2, ls="--", label=f"Dasar galian  H={H:.1f} m"),
        Line2D([0], [0], color=WARNA_AIR,     lw=1.2, ls=":",  label=f"Muka air tanah  {muka_air:.1f} m"),
    ]
    if batas_lapisan and len(batas_lapisan) > 1:
        legend_item.append(
            Line2D([0], [0], color=WARNA_LAPISAN, lw=0.8, ls="-.", label="Batas lapisan tanah")
        )

    fig.legend(
        handles=legend_item,
        loc="lower center",
        ncol=3,
        fontsize=8,
        bbox_to_anchor=(0.5, 0.01),
        framealpha=0.8,
    )

    fig.text(
        0.5, 0.96,
        f"H = {H:.1f} m  |  D = {D:.1f} m  |  MAT = {muka_air:.1f} m",
        ha="center", fontsize=8.5, color="#555555",
    )

    return fig


# ─────────────────────────────────────────────────────────────────────────────
# FUNGSI UTILITAS TAMBAHAN
# ─────────────────────────────────────────────────────────────────────────────

def format_langkah(langkah: list[str]) -> str:
    """
    Gabungkan list langkah menjadi satu string untuk ditampilkan.

    Penggunaan di Streamlit:
        teks = format_langkah(hasil["langkah"])
        st.code(teks, language="")          # tampilan monospace rapi
        # atau
        st.text(teks)                        # plain text
    """
    return "\n".join(langkah)


def buat_latex_Ka_rankine(phi: float, Ka: float) -> str:
    """
    Hasilkan string LaTeX persamaan Ka Rankine.

    Penggunaan: st.latex(buat_latex_Ka_rankine(phi, Ka))
    """
    sudut = 45.0 - phi / 2.0
    return (
        r"K_a = \tan^2\!\left(45^{\circ} - \frac{\varphi}{2}\right)"
        rf" = \tan^2\!\left({sudut:.2f}^{{\circ}}\right)"
        rf" = {Ka:.4f}"
    )


def buat_latex_sigma_aktif(
    Ka      : float,
    sigma_v : float,
    cohesion: float,
    u       : float,
    sigma_h : float,
) -> str:
    """
    Hasilkan string LaTeX persamaan tekanan aktif pada satu titik.

    Penggunaan: st.latex(buat_latex_sigma_aktif(...))
    """
    sqrt_Ka = math.sqrt(Ka)
    return (
        r"\sigma_{h,aktif} = K_a \cdot \sigma_v' - 2c\sqrt{K_a} + u"
        rf" = {Ka:.4f} \times {sigma_v:.2f}"
        rf" - 2 \times {cohesion:.2f} \times {sqrt_Ka:.4f}"
        rf" + {u:.2f}"
        rf" = {sigma_h:.2f} \text{{ kPa}}"
    )


def ringkasan_koefisien(phi: float, OCR: float = 1.0) -> dict:
    """
    Hitung Ka, Kp, Ko sekaligus dalam satu panggilan.

    Return:
        dict: {"Ka": float, "Kp": float, "Ko": float,
               "langkah": list[str], "referensi": list[str]}
    """
    res_ka = hitung_Ka_rankine(phi)
    res_kp = hitung_Kp_rankine(phi)
    res_ko = hitung_Ko(phi, OCR)

    Ka = res_ka["nilai"]
    Kp = res_kp["nilai"]
    Ko = res_ko["nilai"]

    langkah = [
        *_header(f"Ringkasan Koefisien Tekanan Tanah  (phi = {phi:.1f} derajat, OCR = {OCR:.1f})"),
        "",
        _sub("Ka (Rankine aktif)",  f"{Ka:.6f}"),
        _sub("Kp (Rankine pasif)",  f"{Kp:.6f}"),
        _sub("Ko (at-rest, Jaky)",  f"{Ko:.6f}"),
        "",
        _sub("Kontrol", f"Kp * Ka = {Kp * Ka:.6f}  (teoritis = 1.0 untuk non-kohesif)"),
        _sub("Kontrol", f"Ka < Ko < Kp : {Ka:.4f} < {Ko:.4f} < {Kp:.4f}  "
                         + ("OK" if Ka < Ko < Kp else "PERIKSA")),
        _garis(),
    ]

    return {
        "Ka"       : Ka,
        "Kp"       : Kp,
        "Ko"       : Ko,
        "langkah"  : langkah,
        "referensi": res_ka["referensi"] + res_ko["referensi"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# CONTOH PENGGUNAAN — jalankan: python earth_pressure.py
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    SEP = "\n" + "=" * 68 + "\n"

    print(SEP + "CONTOH PERHITUNGAN TEKANAN TANAH LATERAL")
    print("Data tipikal: lempung medium Jabodetabek")
    print("=" * 68)

    # ── Data tanah contoh ────────────────────────────────────────────────────
    PHI      = 20.0    # derajat
    COHESION = 15.0    # kPa
    GAMMA    = 17.0    # kN/m3
    GAMMA_S  = 18.5   # kN/m3
    MAT      = 1.5    # m dari permukaan
    H        = 4.0    # m tinggi galian
    D        = 3.0    # m penetrasi
    SURCHARGE= 10.0   # kPa

    # 1. Ka Rankine
    r_ka = hitung_Ka_rankine(PHI)
    print(format_langkah(r_ka["langkah"]))

    # 2. Kp Rankine
    r_kp = hitung_Kp_rankine(PHI)
    print(format_langkah(r_kp["langkah"]))

    # 3. Ka Coulomb
    r_kac = hitung_Ka_coulomb(phi=PHI, delta=PHI * 2 / 3, alpha_wall=90.0, beta_slope=0.0)
    print(format_langkah(r_kac["langkah"]))

    # 4. Ko
    r_ko = hitung_Ko(phi=PHI, OCR=1.5)
    print(format_langkah(r_ko["langkah"]))

    # 5. Tekanan aktif pada z = 3 m
    r_aktif = hitung_tekanan_aktif(
        z=3.0, gamma=GAMMA, phi=PHI, cohesion=COHESION,
        surcharge=SURCHARGE, muka_air=MAT, gamma_sat=GAMMA_S,
    )
    print(format_langkah(r_aktif["langkah"]))

    # 6. Tekanan pasif pada z = 2 m dari dasar galian
    r_pasif = hitung_tekanan_pasif(
        z=2.0, gamma=GAMMA, phi=PHI, cohesion=COHESION,
        muka_air=0.0, gamma_sat=GAMMA_S,
    )
    print(format_langkah(r_pasif["langkah"]))

    # 7. Distribusi tekanan (multi-lapisan)
    lapisan = [
        {"nama": "Lempung lunak",  "tebal": 3.0, "gamma": 16.0, "gamma_sat": 17.0, "phi": 10.0, "cohesion": 10.0},
        {"nama": "Lempung medium", "tebal": 5.0, "gamma": 17.0, "gamma_sat": 18.5, "phi": 20.0, "cohesion": 15.0},
        {"nama": "Lempung kaku",   "tebal": 6.0, "gamma": 18.5, "gamma_sat": 19.5, "phi": 25.0, "cohesion": 30.0},
    ]

    r_dist = hitung_distribusi_tekanan(
        lapisan_tanah = lapisan,
        H             = H,
        D             = D,
        muka_air      = MAT,
        surcharge     = SURCHARGE,
    )
    print(format_langkah(r_dist["langkah"]))

    # 8. Plot diagram
    nilai = r_dist["nilai"]
    fig = plot_diagram_tekanan(
        z_array       = nilai["z_array"],
        tekanan_aktif = nilai["tekanan_aktif"],
        tekanan_pasif = nilai["tekanan_pasif"],
        tekanan_neto  = nilai["tekanan_neto"],
        H             = H,
        D             = D,
        muka_air      = MAT,
        batas_lapisan = nilai["batas_lapisan"],
        judul         = "Diagram Tekanan Tanah Lateral — Contoh Lempung Jabodetabek",
    )
    output_file = "diagram_tekanan.png"
    fig.savefig(output_file, dpi=150, bbox_inches="tight")
    print(f"\n  Diagram tersimpan: {output_file}")
    print("\nSelesai.")

