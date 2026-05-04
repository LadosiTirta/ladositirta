"""
================================================================================
stability.py
================================================================================
Modul analisis stabilitas turap / sheet pile.

Metode yang diimplementasikan:
    1. Free Earth Support Method  — turap dengan angkur (anchored sheet pile)
    2. Fixed Earth Support Method — turap kantilever (cantilever sheet pile)
    3. Equivalent Beam Method     — koreksi momen Rowe (moment reduction)
    4. Stabilitas Heave           — Terzaghi (1943) dan Bjerrum-Eide (1956)
    5. Stabilitas Piping          — Lane Weighted Creep Ratio (1935)
    6. Rangkuman Stabilitas       — tabel semua SF vs syarat minimum

Referensi utama:
    [R1]  SNI 8460:2017   — Persyaratan Perancangan Geoteknik, Pasal 9, 10
    [R2]  NAVFAC DM-7.02  — Foundations & Earth Structures, Ch. 3 & 7
    [R3]  NAVFAC DM-7.01  — Soil Mechanics, Ch. 4 & 6
    [R4]  USS Sheet Pile  — Design Manual (1975), Ch. 3-5
    [R5]  Das, B.M.       — Principles of Foundation Engineering, 8th Ed., Ch. 9
    [R6]  Terzaghi (1943) — Theoretical Soil Mechanics
    [R7]  Bjerrum & Eide  — Stability of strutted excavations (1956)
    [R8]  Lane (1935)     — Security from under-seepage, Trans. ASCE 100

Konvensi:
    Satuan  : kN, m, kPa, kN.m/m
    Variabel: kata bahasa teknik (tidak menggunakan simbol Yunani)
    Teks    : plain text kompatibel Word & PDF

Penulis  : Structural Civil Engineer — Pabrik Beton Pracetak, Jabodetabek
Versi    : 1.0.0
================================================================================
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import optimize

# ── impor dari modul Tahap 1 ─────────────────────────────────────────────────
from earth_pressure import (
    hitung_distribusi_tekanan,
    hitung_Ka_rankine,
    hitung_Kp_rankine,
    format_langkah,
    GAMMA_W_DEFAULT,
)


# ─────────────────────────────────────────────────────────────────────────────
# KONSTANTA SYARAT MINIMUM FAKTOR KEAMANAN
# ─────────────────────────────────────────────────────────────────────────────

SF_GULING_MIN    : float = 1.5   # SF guling minimum (NAVFAC DM-7.02)
SF_HEAVE_MIN     : float = 1.5   # SF heave minimum (SNI 8460:2017 Ps. 10.6.3)
SF_HEAVE_MIN_SOFT: float = 2.0   # SF heave minimum untuk tanah sangat lunak
SF_PIPING_MIN    : float = 1.5   # SF piping minimum (NAVFAC DM-7.01)
FAKTOR_D_DESIGN  : float = 1.2   # D_design = D_min * 1.2 (USS Sheet Pile Manual)
FAKTOR_D_KANTILEVER: float = 1.3 # D_design = D_min * 1.3 untuk kantilever


# ─────────────────────────────────────────────────────────────────────────────
# FUNGSI PEMBANTU FORMAT
# ─────────────────────────────────────────────────────────────────────────────

def _garis(karakter: str = "-", lebar: int = 64) -> str:
    return karakter * lebar


def _header(judul: str) -> list[str]:
    lebar = 64
    return [_garis("=", lebar), f"  {judul.upper()}", _garis("=", lebar)]


def _sub(label: str, nilai: str) -> str:
    return f"  {label:<14}: {nilai}"


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


def _status_sf(sf: float, sf_min: float) -> str:
    return "AMAN" if sf >= sf_min else "TIDAK AMAN"


# ─────────────────────────────────────────────────────────────────────────────
# FUNGSI INTI: HITUNG TEKANAN NETO DARI DISTRIBUSI
# ─────────────────────────────────────────────────────────────────────────────

def _siapkan_distribusi(
    lapisan_tanah: list[dict],
    H            : float,
    D_coba       : float,
    muka_air     : float,
    surcharge    : float,
    metode_Ka    : str   = "rankine",
    delta        : float = 0.0,
    gamma_w      : float = GAMMA_W_DEFAULT,
    dz           : float = 0.05,
) -> dict:
    """
    Panggil hitung_distribusi_tekanan dari earth_pressure.py dengan D_coba.
    Return dict nilai dari modul earth_pressure.
    """
    hasil = hitung_distribusi_tekanan(
        lapisan_tanah = lapisan_tanah,
        H             = H,
        D             = D_coba,
        muka_air      = muka_air,
        surcharge     = surcharge,
        gamma_w       = gamma_w,
        dz            = dz,
        metode_Ka     = metode_Ka,
        delta         = delta,
    )
    return hasil["nilai"]


def _integrasikan_trapz(z_arr: np.ndarray, q_arr: np.ndarray) -> float:
    """Integrasi numerik luas diagram tekanan (trapesium)."""
    return float(np.trapezoid(q_arr, z_arr))


def _momen_terhadap_titik(
    z_arr  : np.ndarray,
    q_arr  : np.ndarray,
    z_pivot: float,
) -> float:
    """
    Hitung momen resultan terhadap titik z_pivot.
    Momen = integral(q * (z_pivot - z) dz)
    Positif = searah jarum jam (cenderung memutar ke arah pasif).
    """
    lengan = z_pivot - z_arr
    return float(np.trapezoid(q_arr * lengan, z_arr))


def _titik_nol_tekanan(
    z_arr: np.ndarray,
    p_neto: np.ndarray,
) -> float:
    """
    Cari kedalaman pertama di mana tekanan neto berubah dari positif ke negatif
    (dari aktif ke pasif mendominasi). Digunakan untuk kantilever.
    Interpolasi linear antara dua titik yang mengapit perubahan tanda.
    """
    for i in range(len(p_neto) - 1):
        if p_neto[i] >= 0 and p_neto[i + 1] < 0:
            # Interpolasi linear
            dz    = z_arr[i + 1] - z_arr[i]
            frac  = p_neto[i] / (p_neto[i] - p_neto[i + 1])
            return float(z_arr[i] + frac * dz)
    # Jika tidak ditemukan (pasif selalu mendominasi) kembalikan ujung array
    return float(z_arr[-1])


# ─────────────────────────────────────────────────────────────────────────────
# 1. FREE EARTH SUPPORT METHOD (turap dengan angkur / strutted)
# ─────────────────────────────────────────────────────────────────────────────

def free_earth_support(
    H             : float,
    lapisan_tanah : list[dict],
    surcharge     : float,
    muka_air      : float,
    tinggi_angkur : float,
    metode_Ka     : str   = "rankine",
    delta         : float = 0.0,
    gamma_w       : float = GAMMA_W_DEFAULT,
    faktor_D      : float = FAKTOR_D_DESIGN,
    SF_min        : float = SF_GULING_MIN,
    dz            : float = 0.05,
    D_maks        : float = 30.0,
) -> dict:
    """
    Analisis Free Earth Support Method untuk turap dengan angkur (anchored).

    Prinsip:
        Turap dianggap bebas berotasi di ujung bawah (free to rotate at tip).
        Kondisi keseimbangan: jumlah momen terhadap titik angkur = 0.
        D_min ditentukan secara iteratif hingga syarat momen terpenuhi.

    Urutan langkah:
        1. Hitung distribusi tekanan neto (aktif - pasif) vs kedalaman D
        2. Hitung resultan gaya neto (Fnet) = integral(p_neto dz)
        3. Hitung momen neto terhadap titik angkur (Mo)
        4. Iterasi D hingga Mo = 0  -->  D_min
        5. D_design = D_min * faktor_D
        6. Hitung gaya angkur Ra = Fnet_di_D_design

    Referensi:
        [R2] NAVFAC DM-7.02, Ch. 3, Section 3.2, Hal. 3-11 s/d 3-20
        [R4] USS Sheet Pile Design Manual (1975), Ch. 3, Hal. 3-2 s/d 3-15
        [R5] Das, B.M., Principles of Foundation Engineering, 8th Ed., Ch. 9.5

    Parameter:
        H             : tinggi galian / tinggi turap di atas galian [m]
        lapisan_tanah : list[dict] data lapisan tanah
        surcharge     : beban merata di permukaan belakang turap [kPa]
        muka_air      : kedalaman muka air tanah [m]
        tinggi_angkur : jarak angkur dari permukaan tanah [m]
        metode_Ka     : "rankine" atau "coulomb"
        delta         : sudut gesek tanah-dinding [derajat] (Coulomb)
        gamma_w       : berat volume air [kN/m3]
        faktor_D      : faktor keamanan untuk D_design (default 1.2)
        SF_min        : SF momen minimum yang disyaratkan (default 1.5)
        dz            : interval komputasi [m]
        D_maks        : batas atas pencarian D [m]

    Return:
        dict standar; "nilai" berisi:
            {D_min, D_design, Ra, Mmax, z_Mmax, SF_momen,
             z_array, p_neto, p_aktif, p_pasif, u_array}
    """
    # ── Validasi input ────────────────────────────────────────────────────────
    if H <= 0:
        raise ValueError(f"H harus > 0, diberikan: {H}")
    if tinggi_angkur >= H:
        raise ValueError(
            f"Tinggi angkur ({tinggi_angkur} m) harus lebih kecil dari H ({H} m)"
        )
    if not lapisan_tanah:
        raise ValueError("Minimal satu lapisan tanah harus ada.")

    z_angkur = tinggi_angkur   # kedalaman angkur dari permukaan [m]

    langkah: list[str] = [
        *_header("Free Earth Support Method — Turap dengan Angkur"),
        "",
        "  Prinsip:",
        "    Ujung bawah turap bebas berotasi (free to rotate at tip).",
        "    Syarat keseimbangan: Jumlah momen terhadap titik angkur = 0.",
        "    D_min dicari iteratif hingga syarat momen terpenuhi.",
        "",
        "  Data input:",
        _sub("  H",             f"{H:.2f} m  (tinggi galian)"),
        _sub("  Tinggi angkur", f"{tinggi_angkur:.2f} m dari permukaan"),
        _sub("  z_angkur",      f"{z_angkur:.2f} m  (=tinggi_angkur)"),
        _sub("  muka_air",      f"{muka_air:.2f} m dari permukaan"),
        _sub("  surcharge",     f"{surcharge:.2f} kPa"),
        _sub("  metode_Ka",     metode_Ka.upper()),
        _sub("  faktor_D",      f"{faktor_D:.2f}  (D_design = D_min x faktor_D)"),
        _sub("  SF_min",        f"{SF_min:.2f}"),
        "",
        "  Lapisan tanah:",
    ]
    for i, lyr in enumerate(lapisan_tanah):
        langkah.append(
            f"    [{i+1}] {lyr.get('nama',''):<18} "
            f"tebal={lyr['tebal']:.1f}m  "
            f"gamma={lyr['gamma']:.1f} kN/m3  "
            f"phi={lyr['phi']:.1f} deg  "
            f"c={lyr['cohesion']:.1f} kPa"
        )

    # ── Fungsi bantu: hitung Mo_aktif dan Mo_pasif terhadap angkur ──────────
    def _mo_aktif_pasif(D_coba: float):
        """
        Hitung momen aktif dan pasif terhadap titik angkur secara TERPISAH.
        Rumus FES yang benar (NAVFAC DM-7.02, §3.2):
            Mo_aktif = integral[ Pa(z) * (z - z_angkur) dz ]  dari 0 ke H+D
            Mo_pasif = integral[ Pp(z) * (z - z_angkur) dz ]  dari H ke H+D
            SF_momen = Mo_pasif / Mo_aktif
            D_min    = D agar SF_momen = SF_min
        """
        dist = _siapkan_distribusi(
            lapisan_tanah, H, D_coba, muka_air, surcharge,
            metode_Ka, delta, gamma_w, dz,
        )
        z  = dist["z_array"]
        pa = dist["tekanan_aktif"]
        pp = dist["tekanan_pasif"]

        lengan_a  = z - z_angkur   # positif di bawah angkur, negatif di atas
        Mo_aktif  = float(np.trapezoid(pa * lengan_a, z))

        mask_pen  = z >= H - dz / 2
        lengan_p  = z[mask_pen] - z_angkur
        Mo_pasif  = float(np.trapezoid(pp[mask_pen] * lengan_p, z[mask_pen]))

        # Ra dari keseimbangan gaya horisontal
        Fa = float(np.trapezoid(pa, z))
        Fp = float(np.trapezoid(pp[mask_pen], z[mask_pen]))
        Ra = Fa - Fp   # positif = angkur tarik; negatif = pasif overdominasi

        SF = Mo_pasif / Mo_aktif if Mo_aktif > 1e-9 else 999.0
        return SF, Ra, Mo_aktif, Mo_pasif

    # Fungsi objektif: SF(D) - SF_min = 0 saat keseimbangan
    def fungsi_objek_SF(D_coba: float) -> float:
        SF, _, _, _ = _mo_aktif_pasif(D_coba)
        return SF - SF_min

    # ── Iterasi cari D_min ────────────────────────────────────────────────────
    langkah += [
        "",
        _garis("-"),
        "  LANGKAH 1 — Iterasi mencari D_min",
        _garis("-"),
        "  Metode  : Cari D agar SF_momen = SF_min",
        "  Rumus   : SF_momen = Mo_pasif / Mo_aktif terhadap titik angkur",
        "            Mo_aktif = integral[ Pa(z) * (z - z_angkur) dz ]   (0 ke H+D)",
        "            Mo_pasif = integral[ Pp(z) * (z - z_angkur) dz ]   (H ke H+D)",
        "  Syarat  : SF_momen = SF_min (D terkecil yang memenuhi SF)",
        f"  Ref     : NAVFAC DM-7.02, Ch.3, §3.2; USS Sheet Pile Manual Ch.3",
        "",
        f"  {'Iterasi':>8} {'D_coba (m)':>12} {'SF_momen':>12} {'Mo_aktif':>12} {'Mo_pasif':>12}",
        "  " + "-" * 60,
    ]

    D_bawah = max(0.1, H * 0.05)
    D_atas  = D_maks

    fo_bawah = fungsi_objek_SF(D_bawah)
    fo_atas  = fungsi_objek_SF(D_atas)

    if fo_bawah >= 0 and fo_atas >= 0:
        # SF selalu >= SF_min bahkan di D kecil → D_min = D_bawah (sudah aman)
        D_min = D_bawah
        SF_at_Dmin, Ra_at_Dmin, Mo_a, Mo_p = _mo_aktif_pasif(D_min)
        langkah += [
            f"  SF sudah memenuhi di D_min = {D_bawah:.2f} m (SF = {fo_bawah+SF_min:.3f})",
            f"  D_min = {D_min:.4f} m  (batas minimum praktis)",
        ]
    elif fo_bawah * fo_atas <= 0:
        # Zero crossing ada dalam rentang [D_bawah, D_atas] — bisection
        for it in range(1, 12):
            D_coba = (D_bawah + D_atas) / 2.0
            fo     = fungsi_objek_SF(D_coba)
            SF_c, _, Mo_a_c, Mo_p_c = _mo_aktif_pasif(D_coba)
            ket = "SF > SF_min, perlu D lebih kecil" if fo > 0 else "SF < SF_min, perlu D lebih besar"
            langkah.append(
                f"  {it:>8} {D_coba:>12.4f} {SF_c:>12.4f} {Mo_a_c:>12.3f} {Mo_p_c:>12.3f}"
            )
            if fo > 0:
                D_atas = D_coba
            else:
                D_bawah = D_coba
            if abs(D_atas - D_bawah) < 1e-3:
                break
        try:
            D_min = float(optimize.brentq(fungsi_objek_SF, D_bawah, D_atas, xtol=1e-5))
        except (ValueError, Exception):
            D_min = (D_bawah + D_atas) / 2.0
        SF_at_Dmin, Ra_at_Dmin, Mo_a, Mo_p = _mo_aktif_pasif(D_min)
    else:
        # fo_atas < 0: SF tidak pernah mencapai SF_min bahkan di D_maks
        # Coba perbesar D_maks sampai SF tercapai
        D_coba_besar = D_maks
        for mul in [2, 4, 8]:
            D_coba_besar = D_maks * mul
            fo_besar = fungsi_objek_SF(D_coba_besar)
            if fo_bawah * fo_besar <= 0:
                D_atas = D_coba_besar
                try:
                    D_min = float(optimize.brentq(fungsi_objek_SF, D_bawah, D_atas, xtol=1e-5))
                except (ValueError, Exception):
                    D_min = D_maks
                break
        else:
            D_min = D_maks
        SF_at_Dmin, Ra_at_Dmin, Mo_a, Mo_p = _mo_aktif_pasif(D_min)
        langkah.append(f"  PERINGATAN: SF_min tidak tercapai dalam D <= {D_maks:.1f} m")

    langkah += [
        "  " + "-" * 60,
        f"  --> D_min     = {D_min:.4f} m",
        f"  --> SF_momen  = {SF_at_Dmin:.4f}  (syarat = {SF_min:.2f})",
        f"  --> Mo_aktif  = {Mo_a:.3f} kN.m/m",
        f"  --> Mo_pasif  = {Mo_p:.3f} kN.m/m",
    ]

    # ── D_design ──────────────────────────────────────────────────────────────
    D_design = D_min * faktor_D

    langkah += [
        "",
        _garis("-"),
        "  LANGKAH 2 — Hitung D_design",
        _garis("-"),
        "  Rumus  : D_design = D_min x faktor_D",
        f"  Nilai  : D_min = {D_min:.4f} m",
        f"           faktor_D = {faktor_D:.2f}  (USS Sheet Pile Manual, Ch. 3)",
        f"  Hitung : D_design = {D_min:.4f} x {faktor_D:.2f}",
        f"  Hasil  : D_design = {D_design:.4f} m",
        _sub("  Satuan", "m"),
        _sub("  Standar", "USS Sheet Pile Design Manual (1975), Ch. 3, Hal. 3-5"),
        _sub("  ",        "NAVFAC DM-7.02, Ch. 3, Hal. 3-13"),
    ]

    # ── Distribusi akhir pada D_design ───────────────────────────────────────
    dist_d = _siapkan_distribusi(
        lapisan_tanah, H, D_design, muka_air, surcharge,
        metode_Ka, delta, gamma_w, dz,
    )
    z_d  = dist_d["z_array"]
    pn_d = dist_d["tekanan_neto"]
    pa_d = dist_d["tekanan_aktif"]
    pp_d = dist_d["tekanan_pasif"]
    u_d  = dist_d["tekanan_air_pori"]

    # ── Gaya angkur Ra ────────────────────────────────────────────────────────
    # Ra = Fa_total - Fp_total  (keseimbangan gaya horizontal)
    # Positif = angkur menahan tarikan (normal)
    # Ra dari hasil iterasi D_min sudah ada: Ra_at_Dmin
    # Hitung ulang di D_design
    Fa_total = _integrasikan_trapz(z_d, pa_d)
    Fp_total = _integrasikan_trapz(z_d[z_d >= H], pp_d[z_d >= H])
    Ra = max(0.0, Fa_total - Fp_total)  # jika negatif, angkur tidak dibutuhkan (SF sangat tinggi)

    langkah += [
        "",
        _garis("-"),
        "  LANGKAH 3 — Hitung Gaya Angkur (Ra)",
        _garis("-"),
        "  Prinsip: keseimbangan gaya horizontal",
        "  Rumus  : Ra = Fa_total - Fp_total  (harus >= 0)",
        "  di mana:",
        "    Fa_total = integral(Pa dz)  [seluruh tinggi turap H+D]",
        "    Fp_total = integral(Pp dz)  [zona penetrasi D saja]",
        "",
        f"  Fa_total = {Fa_total:.3f} kN/m",
        f"  Fp_total = {Fp_total:.3f} kN/m",
        f"  Hitung  : Ra = max(0, {Fa_total:.3f} - {Fp_total:.3f})",
        f"  Hasil   : Ra = {Ra:.3f} kN/m",
        _sub("  Satuan",  "kN/m (per meter lebar turap)"),
        _sub("  Standar", "NAVFAC DM-7.02, Ch. 3, Hal. 3-12"),
        _sub("  ",        "USS Sheet Pile Design Manual (1975), Ch. 3, Hal. 3-6"),
    ]

    # ── Momen lentur maksimum ─────────────────────────────────────────────────
    # Mmax terjadi di mana gaya geser = 0
    # Geser V(z) = Ra - integral(p_neto, 0..z)  dengan asal dari permukaan
    V_arr     = np.zeros(len(z_d))
    V_arr[0]  = Ra
    for i in range(1, len(z_d)):
        # Gaya geser = gaya angkur dikurangi akumulasi tekanan neto
        V_arr[i] = Ra - float(np.trapezoid(pn_d[:i+1], z_d[:i+1]))

    # Cari z di mana V berubah tanda (Mmax)
    z_Mmax = z_d[np.argmin(np.abs(V_arr))]
    idx_z  = np.argmin(np.abs(V_arr))

    # Momen pada z_Mmax = integral momen dari atas sampai z_Mmax
    M_arr     = np.zeros(len(z_d))
    for i in range(1, len(z_d)):
        # Momen = Ra*(z-z_angkur) - integral(p_neto * (z - z') dz')
        M_arr[i] = (
            Ra * (z_d[i] - z_angkur)
            - float(np.trapezoid(pn_d[:i+1] * (z_d[i] - z_d[:i+1]), z_d[:i+1]))
        )

    Mmax = float(np.max(np.abs(M_arr)))
    idx_Mmax = int(np.argmax(np.abs(M_arr)))
    z_Mmax   = float(z_d[idx_Mmax])

    langkah += [
        "",
        _garis("-"),
        "  LANGKAH 4 — Hitung Momen Lentur Maksimum (Mmax)",
        _garis("-"),
        "  Mmax terjadi di mana gaya geser V = 0",
        "  Rumus geser  : V(z) = Ra - integral(p_neto, 0 .. z)",
        "  Rumus momen  : M(z) = Ra*(z - z_angkur) - integral(p_neto*(z-z') dz')",
        "",
        f"  Ra                = {Ra:.3f} kN/m",
        f"  z_angkur          = {z_angkur:.2f} m",
        f"  Kedalaman V=0     = {z_d[np.argmin(np.abs(V_arr))]:.3f} m",
        f"  Kedalaman Mmax    = {z_Mmax:.3f} m dari permukaan tanah",
        f"  Hasil  : Mmax     = {Mmax:.3f} kN.m/m",
        _sub("  Satuan",  "kN.m/m (per meter lebar turap)"),
        _sub("  Standar", "NAVFAC DM-7.02, Ch. 3, Hal. 3-14"),
        _sub("  ",        "USS Sheet Pile Design Manual (1975), Ch. 4, Hal. 4-2"),
    ]

    # ── SF momen pada D_design — verifikasi akhir ─────────────────────────────
    # Rumus benar: lengan = z - z_angkur (positif ke bawah dari angkur)
    lengan_a   = z_d - z_angkur
    Mo_aktif_angkur = float(np.trapezoid(pa_d * lengan_a, z_d))
    mask_p     = z_d >= H
    Mo_pasif_angkur = float(np.trapezoid(pp_d[mask_p] * (z_d[mask_p] - z_angkur), z_d[mask_p]))
    SF_momen = Mo_pasif_angkur / Mo_aktif_angkur if Mo_aktif_angkur > 1e-6 else 999.0
    status_sf = _status_sf(SF_momen, SF_min)

    langkah += [
        "",
        _garis("-"),
        "  LANGKAH 5 — Cek Faktor Keamanan Momen (SF_momen)",
        _garis("-"),
        "  Rumus   : SF_momen = Mo_pasif / Mo_aktif",
        "  di mana momen dihitung terhadap titik angkur",
        "",
        f"  Mo_aktif (terhadap angkur) = {Mo_aktif_angkur:.3f} kN.m/m",
        f"  Mo_pasif (terhadap angkur) = {Mo_pasif_angkur:.3f} kN.m/m",
        f"  Hitung  : SF_momen = {Mo_pasif_angkur:.3f} / {Mo_aktif_angkur:.3f}",
        f"  Hasil   : SF_momen = {SF_momen:.3f}",
        f"  SF_min  = {SF_min:.2f}  (NAVFAC DM-7.02)",
        f"  Status  : {status_sf}",
        _sub("  Standar", "NAVFAC DM-7.02, Ch. 3, Section 3.2, Hal. 3-13"),
        _sub("  ",        "SNI 8460:2017, Pasal 9.6.2"),
        "",
        _garis("-"),
        "  RANGKUMAN FREE EARTH SUPPORT",
        _garis("-"),
        f"  D_min     = {D_min:.4f} m",
        f"  D_design  = {D_design:.4f} m  (=D_min x {faktor_D:.2f})",
        f"  Ra        = {Ra:.3f} kN/m  (gaya angkur per meter)",
        f"  Mmax      = {Mmax:.3f} kN.m/m  (z = {z_Mmax:.3f} m)",
        f"  SF_momen  = {SF_momen:.3f}  --> {status_sf}",
        _garis("="),
    ]

    referensi = [
        "NAVFAC DM-7.02, Ch. 3, Section 3.2, Hal. 3-11 s/d 3-20",
        "USS Sheet Pile Design Manual (1975), Ch. 3, Hal. 3-2 s/d 3-15",
        "Das, B.M., Principles of Foundation Engineering, 8th Ed., Ch. 9.5",
        "SNI 8460:2017, Pasal 9.6.2",
    ]

    return _hasil_dict(
        nilai={
            "D_min"    : round(D_min,    4),
            "D_design" : round(D_design, 4),
            "Ra"       : round(Ra,       3),
            "Mmax"     : round(Mmax,     3),
            "z_Mmax"   : round(z_Mmax,   3),
            "SF_momen" : round(SF_momen, 3),
            "z_array"  : z_d,
            "p_neto"   : pn_d,
            "p_aktif"  : pa_d,
            "p_pasif"  : pp_d,
            "u_array"  : u_d,
            "V_array"  : V_arr,
            "M_array"  : M_arr,
        },
        langkah   = langkah,
        referensi = referensi,
        satuan    = "m, kN/m, kN.m/m",
        status    = status_sf,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. FIXED EARTH SUPPORT METHOD (turap kantilever)
# ─────────────────────────────────────────────────────────────────────────────

def fixed_earth_support_cantilever(
    H            : float,
    lapisan_tanah: list[dict],
    surcharge    : float,
    muka_air     : float,
    metode_Ka    : str   = "rankine",
    delta        : float = 0.0,
    gamma_w      : float = GAMMA_W_DEFAULT,
    faktor_D     : float = FAKTOR_D_KANTILEVER,
    dz           : float = 0.05,
    D_maks       : float = 30.0,
) -> dict:
    """
    Analisis Fixed Earth Support Method untuk turap kantilever.

    Prinsip:
        Ujung bawah turap dianggap terjepit (fixed end).
        Titik zero tekanan neto (z0) ada di antara H dan H+D.
        Di bawah z0, tekanan pasif berbalik menjadi penyangga (reaksi jepit).
        Kondisi: jumlah momen terhadap titik z0 = 0 --> menentukan D.

    Urutan langkah:
        1. Tentukan Ka, Kp dari lapisan tanah di dasar galian
        2. Hitung distribusi tekanan neto
        3. Cari titik zero pressure (z0) di dalam zona penetrasi
        4. Hitung momen terhadap z0 dari seluruh tekanan di atas z0
        5. Iterasi D hingga keseimbangan momen terpenuhi
        6. D_design = D_min * faktor_D

    Referensi:
        [R2] NAVFAC DM-7.02, Ch. 3, Section 3.1, Hal. 3-4 s/d 3-10
        [R4] USS Sheet Pile Design Manual (1975), Ch. 3, Hal. 3-16 s/d 3-25
        [R5] Das, B.M., Principles of Foundation Engineering, 8th Ed., Ch. 9.3

    Parameter:
        H             : tinggi galian [m]
        lapisan_tanah : list[dict]
        surcharge     : beban merata [kPa]
        muka_air      : kedalaman MAT [m]
        metode_Ka     : "rankine" atau "coulomb"
        delta         : sudut gesek tanah-dinding [derajat]
        gamma_w       : berat volume air [kN/m3]
        faktor_D      : faktor D_design (default 1.3 untuk kantilever)
        dz            : interval kedalaman [m]
        D_maks        : batas atas pencarian [m]

    Return:
        dict standar; "nilai" berisi:
            {D_min, D_design, z0, Mmax, z_Mmax, SF_momen,
             z_array, p_neto, p_aktif, p_pasif, u_array, M_array}
    """
    if H <= 0:
        raise ValueError(f"H harus > 0, diberikan: {H}")

    langkah: list[str] = [
        *_header("Fixed Earth Support Method — Turap Kantilever"),
        "",
        "  Prinsip:",
        "    Ujung bawah turap terjepit (fixed end / fixed earth support).",
        "    Ada titik zero tekanan neto (z0) di dalam zona penetrasi.",
        "    Di bawah z0, tekanan pasif berbalik menjadi reaksi jepit.",
        "    Syarat: Jumlah momen terhadap z0 = 0.",
        "",
        "  Data input:",
        _sub("  H",         f"{H:.2f} m"),
        _sub("  muka_air",  f"{muka_air:.2f} m"),
        _sub("  surcharge", f"{surcharge:.2f} kPa"),
        _sub("  metode_Ka", metode_Ka.upper()),
        _sub("  faktor_D",  f"{faktor_D:.2f}  (D_design = D_min x faktor_D)"),
        "",
        "  Lapisan tanah:",
    ]
    for i, lyr in enumerate(lapisan_tanah):
        langkah.append(
            f"    [{i+1}] {lyr.get('nama',''):<18} "
            f"tebal={lyr['tebal']:.1f}m  "
            f"phi={lyr['phi']:.1f} deg  "
            f"c={lyr['cohesion']:.1f} kPa"
        )

    # ── Fungsi objektif: momen semua gaya terhadap ujung bawah turap ──────────
    # Metode Blum / Fixed Earth yang benar (Das, 8th Ed, Ch.9.3;  NAVFAC DM-7.02, §3.1):
    # D_min = D di mana momen total terhadap ujung bawah = 0
    # M_ujung(D) = integral[Pa*(H+D-z)dz] - integral[Pp*(H+D-z)dz, H ke H+D]
    #            = Ma_ujung - Mp_ujung = 0

    def momen_terhadap_ujung(D_coba: float):
        dist = _siapkan_distribusi(
            lapisan_tanah, H, D_coba, muka_air, surcharge,
            metode_Ka, delta, gamma_w, dz,
        )
        z   = dist["z_array"]
        pa  = dist["tekanan_aktif"]
        pp  = dist["tekanan_pasif"]
        z_ujung = H + D_coba
        # Momen aktif terhadap ujung bawah
        Ma = float(np.trapezoid(pa * (z_ujung - z), z))
        # Momen pasif terhadap ujung bawah (zona penetrasi saja)
        mask = z >= H - dz / 2
        Mp = float(np.trapezoid(pp[mask] * (z_ujung - z[mask]), z[mask]))
        return Ma - Mp   # = 0 saat keseimbangan; positif = aktif mendominasi

    # ── Iterasi bisection ────────────────────────────────────────────────────
    langkah += [
        "",
        _garis("-"),
        "  LANGKAH 1 — Iterasi mencari D_min",
        _garis("-"),
        "  Prinsip : Cari D agar momen semua gaya terhadap ujung bawah turap = 0",
        "  Rumus   : Ma_ujung = integral[ Pa(z) * (H+D - z) dz ]   (0 ke H+D)",
        "            Mp_ujung = integral[ Pp(z) * (H+D - z) dz ]   (H ke H+D)",
        "  Syarat  : Ma_ujung - Mp_ujung = 0",
        "  Ref     : Das, B.M., 8th Ed., Ch. 9.3; NAVFAC DM-7.02, §3.1",
        "",
        f"  {'Iterasi':>8} {'D_coba (m)':>12} {'Ma (kN.m/m)':>14} {'Mp (kN.m/m)':>14} {'Mo_net':>12}",
        "  " + "-" * 66,
    ]

    D_bawah = max(0.1, H * 0.05)
    D_atas  = D_maks

    mo_b = momen_terhadap_ujung(D_bawah)
    mo_a = momen_terhadap_ujung(D_atas)

    # Jika tanda sama, scan lebih lebar
    if mo_b * mo_a > 0:
        for mul in [2, 3, 4]:
            D_atas = D_maks * mul
            mo_a   = momen_terhadap_ujung(D_atas)
            if mo_b * mo_a <= 0:
                break

    D_coba = D_bawah
    for it in range(1, 12):
        D_coba = (D_bawah + D_atas) / 2.0
        mo     = momen_terhadap_ujung(D_coba)
        # Hitung Ma dan Mp terpisah untuk log
        dist_c = _siapkan_distribusi(lapisan_tanah, H, D_coba, muka_air, surcharge, metode_Ka, delta, gamma_w, dz)
        z_c=dist_c["z_array"]; pa_c=dist_c["tekanan_aktif"]; pp_c=dist_c["tekanan_pasif"]
        z_u = H + D_coba
        Ma_c = float(np.trapezoid(pa_c*(z_u-z_c), z_c))
        mask_c = z_c>=H-dz/2
        Mp_c = float(np.trapezoid(pp_c[mask_c]*(z_u-z_c[mask_c]), z_c[mask_c]))

        langkah.append(
            f"  {it:>8} {D_coba:>12.4f} {Ma_c:>14.3f} {Mp_c:>14.3f} {mo:>12.3f}"
        )
        if mo > 0:
            D_bawah = D_coba
        else:
            D_atas = D_coba
        if abs(D_atas - D_bawah) < 1e-3:
            break

    try:
        D_min = float(optimize.brentq(momen_terhadap_ujung, D_bawah, D_atas, xtol=1e-5))
    except (ValueError, Exception):
        D_min = D_coba

    langkah += [
        "  " + "-" * 66,
        f"  --> D_min = {D_min:.4f} m  (momen terhadap ujung bawah = 0)",
    ]

    # ── D_design ─────────────────────────────────────────────────────────────
    D_design = D_min * faktor_D

    # ── Distribusi akhir pada D_design ───────────────────────────────────────
    dist_d = _siapkan_distribusi(
        lapisan_tanah, H, D_design, muka_air, surcharge,
        metode_Ka, delta, gamma_w, dz,
    )
    z_d  = dist_d["z_array"]
    pn_d = dist_d["tekanan_neto"]
    pa_d = dist_d["tekanan_aktif"]
    pp_d = dist_d["tekanan_pasif"]
    u_d  = dist_d["tekanan_air_pori"]

    # Titik z0 (zero pressure neto) pada D_design
    mask_pen = z_d >= H - dz / 2
    z0 = _titik_nol_tekanan(z_d[mask_pen], pn_d[mask_pen])
    if z0 <= H:
        z0 = H + 0.5  # fallback

    langkah += [
        "",
        _garis("-"),
        "  LANGKAH 2 — Hitung D_design dan titik zero pressure (z0)",
        _garis("-"),
        "  Rumus  : D_design = D_min x faktor_D",
        f"  Hitung : D_design = {D_min:.4f} x {faktor_D:.2f}",
        f"  Hasil  : D_design = {D_design:.4f} m",
        "",
        f"  Titik zero pressure (z0) pada D_design:",
        f"  z0 = {z0:.4f} m dari permukaan tanah",
        f"  z0 = {z0 - H:.4f} m dari dasar galian",
        _sub("  Standar", "NAVFAC DM-7.02, Ch. 3, Section 3.1, Hal. 3-6"),
        _sub("  ",        "Das, B.M., 8th Ed., Ch. 9.3, Gambar 9.15"),
    ]

    # ── Diagram momen ─────────────────────────────────────────────────────────
    # Kantilever: momen dihitung dari ujung bawah ke atas
    # M(z) = integral dari z ke H+D dari p_neto * (z' - z) dz'
    M_arr = np.zeros(len(z_d))
    for i in range(len(z_d) - 2, -1, -1):
        M_arr[i] = float(
            np.trapezoid(
                pn_d[i:] * (z_d[i:] - z_d[i]),
                z_d[i:],
            )
        )

    Mmax     = float(np.max(np.abs(M_arr)))
    idx_Mmax = int(np.argmax(np.abs(M_arr)))
    z_Mmax   = float(z_d[idx_Mmax])

    # SF momen = Mo_pasif / Mo_aktif terhadap ujung bawah turap di D_design
    z_ujung_d   = H + D_design
    Mo_aktif_ujung = float(np.trapezoid(pa_d * (z_ujung_d - z_d), z_d))
    mask_p_d    = z_d >= H - dz/2
    Mo_pasif_ujung = float(np.trapezoid(pp_d[mask_p_d] * (z_ujung_d - z_d[mask_p_d]), z_d[mask_p_d]))
    SF_momen    = Mo_pasif_ujung / Mo_aktif_ujung if Mo_aktif_ujung > 1e-6 else 999.0
    status_sf   = _status_sf(SF_momen, SF_GULING_MIN)

    langkah += [
        "",
        _garis("-"),
        "  LANGKAH 3 — Momen Lentur Maksimum (Mmax)",
        _garis("-"),
        "  Rumus  : M(z) = integral[ p_neto(z') * (z' - z) dz' ]",
        "           dihitung dari ujung bawah ke atas",
        f"  Hasil  : Mmax    = {Mmax:.3f} kN.m/m",
        f"           z_Mmax  = {z_Mmax:.3f} m dari permukaan",
        _sub("  Satuan",  "kN.m/m"),
        _sub("  Standar", "USS Sheet Pile Design Manual (1975), Ch. 3, Hal. 3-22"),
        "",
        _garis("-"),
        "  LANGKAH 4 — Faktor Keamanan Momen (SF_momen)",
        _garis("-"),
        "  Rumus  : SF_momen = Mo_pasif / Mo_aktif  (terhadap ujung bawah turap)",
        f"  Mo_aktif (ujung bawah) = {Mo_aktif_ujung:.3f} kN.m/m",
        f"  Mo_pasif (ujung bawah) = {Mo_pasif_ujung:.3f} kN.m/m",
        f"  Hitung : SF_momen = {Mo_pasif_ujung:.3f} / {Mo_aktif_ujung:.3f}",
        f"  Hasil  : SF_momen = {SF_momen:.3f}",
        f"  SF_min = {SF_GULING_MIN:.2f}",
        f"  Status : {status_sf}",
        _sub("  Standar", "NAVFAC DM-7.02, Ch. 3, Hal. 3-9"),
        _sub("  ",        "SNI 8460:2017, Pasal 9.6.2"),
        "",
        _garis("-"),
        "  RANGKUMAN FIXED EARTH SUPPORT",
        _garis("-"),
        f"  D_min      = {D_min:.4f} m",
        f"  D_design   = {D_design:.4f} m  (=D_min x {faktor_D:.2f})",
        f"  z0         = {z0:.4f} m dari permukaan  ({z0-H:.4f} m dari dasar galian)",
        f"  Mmax       = {Mmax:.3f} kN.m/m  (z = {z_Mmax:.3f} m)",
        f"  SF_momen   = {SF_momen:.3f}  --> {status_sf}",
        _garis("="),
    ]

    referensi = [
        "NAVFAC DM-7.02, Ch. 3, Section 3.1, Hal. 3-4 s/d 3-10",
        "USS Sheet Pile Design Manual (1975), Ch. 3, Hal. 3-16 s/d 3-25",
        "Das, B.M., Principles of Foundation Engineering, 8th Ed., Ch. 9.3",
        "SNI 8460:2017, Pasal 9.6.2",
    ]

    return _hasil_dict(
        nilai={
            "D_min"    : round(D_min,    4),
            "D_design" : round(D_design, 4),
            "z0"       : round(z0,       4),
            "Mmax"     : round(Mmax,     3),
            "z_Mmax"   : round(z_Mmax,   3),
            "SF_momen" : round(SF_momen, 3),
            "z_array"  : z_d,
            "p_neto"   : pn_d,
            "p_aktif"  : pa_d,
            "p_pasif"  : pp_d,
            "u_array"  : u_d,
            "M_array"  : M_arr,
        },
        langkah   = langkah,
        referensi = referensi,
        satuan    = "m, kN.m/m",
        status    = status_sf,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. EQUIVALENT BEAM METHOD — KOREKSI MOMEN ROWE
# ─────────────────────────────────────────────────────────────────────────────

def koreksi_momen_rowe(
    Mmax_teoritis : float,
    H             : float,
    D_design      : float,
    Ra            : float,
    phi_rata      : float,
    tipe_material : str   = "baja",
    kekakuan_turap: float | None = None,
) -> dict:
    """
    Koreksi momen lentur dengan Rowe's Moment Reduction (Equivalent Beam Method).

    Rowe (1952) menunjukkan bahwa momen lentur aktual lebih kecil dari
    momen teoritis akibat fleksibilitas turap dan redistribusi tegangan.

    Rumus:
        rho   = H_total^4 / (EI)         [parameter fleksibilitas Rowe]
        Md    = alpha_r * Mmax_teoritis   [momen desain setelah reduksi]

    Faktor reduksi alpha_r:
        - Bergantung pada rho dan jenis tanah (loose/dense, soft/stiff)
        - Diambil dari kurva Rowe (1952), disederhanakan sebagai:

          Tanah pasir lepas (phi < 30): alpha_r ~ 0.6 - 0.75
          Tanah pasir padat (phi 30-40): alpha_r ~ 0.5 - 0.65
          Tanah lempung lunak (phi < 15): alpha_r ~ 0.55 - 0.70
          Tanah lempung kaku (phi 15-25): alpha_r ~ 0.50 - 0.65

    Catatan:
        Koreksi Rowe hanya berlaku untuk turap baja dengan angkur.
        Untuk turap beton pracetak (kaku), alpha_r = 1.0 (tanpa reduksi).

    Referensi:
        Rowe, P.W. (1952). Anchored sheet pile walls.
            Proc. Institution of Civil Engineers, Part 1, Vol. 1, No. 1.
        [R4] USS Sheet Pile Design Manual (1975), Ch. 4, Hal. 4-3 s/d 4-10
        [R5] Das, B.M., 8th Ed., Ch. 9.6

    Parameter:
        Mmax_teoritis : momen maksimum teoritis dari free/fixed earth [kN.m/m]
        H             : tinggi galian [m]
        D_design      : kedalaman penetrasi desain [m]
        Ra            : gaya angkur [kN/m]
        phi_rata      : sudut geser rata-rata tanah [derajat]
        tipe_material : "baja" atau "beton"
        kekakuan_turap: EI turap [kN.m2/m] (opsional; untuk hitung rho)

    Return:
        dict standar; "nilai": {Md, alpha_r, rho}
    """
    H_total = H + D_design

    # Untuk beton pracetak: tidak ada reduksi
    if tipe_material.lower() in ("beton", "beton pracetak", "precast", "concrete"):
        alpha_r = 1.0
        catatan = "Turap beton pracetak: tidak ada reduksi momen (kaku)"
    else:
        # Perkiraan alpha_r berdasarkan phi_rata (tabel Rowe yang disederhanakan)
        if phi_rata < 15.0:
            alpha_r = 0.60   # lempung sangat lunak
            keterangan_tanah = "lempung sangat lunak (phi < 15 derajat)"
        elif phi_rata < 25.0:
            alpha_r = 0.55   # lempung lunak-medium
            keterangan_tanah = "lempung lunak-medium (phi 15-25 derajat)"
        elif phi_rata < 30.0:
            alpha_r = 0.65   # pasir lepas / lempung kaku
            keterangan_tanah = "pasir lepas / lempung kaku (phi 25-30 derajat)"
        else:
            alpha_r = 0.70   # pasir padat
            keterangan_tanah = "pasir padat (phi >= 30 derajat)"
        catatan = f"Tanah: {keterangan_tanah}"

    Md = alpha_r * Mmax_teoritis

    # Parameter fleksibilitas rho (jika EI diberikan)
    if kekakuan_turap is not None and kekakuan_turap > 0:
        rho = (H_total ** 4) / kekakuan_turap
        info_rho = f"rho = H_total^4 / EI = {H_total:.2f}^4 / {kekakuan_turap:.1f} = {rho:.5f} m3/kN"
    else:
        rho = None
        info_rho = "EI tidak diberikan, rho tidak dihitung"

    langkah: list[str] = [
        *_header("Koreksi Momen Rowe — Equivalent Beam Method"),
        "",
        "  Prinsip:",
        "    Turap fleksibel mendistribusi ulang momen sehingga momen",
        "    desain aktual lebih kecil dari nilai teoritis.",
        "    Rumus: Md = alpha_r x Mmax_teoritis",
        "",
        "  Data input:",
        _sub("  Mmax_teoritis", f"{Mmax_teoritis:.3f} kN.m/m"),
        _sub("  H",             f"{H:.2f} m"),
        _sub("  D_design",      f"{D_design:.4f} m"),
        _sub("  H_total",       f"{H_total:.4f} m  (= H + D_design)"),
        _sub("  Ra",            f"{Ra:.3f} kN/m"),
        _sub("  phi_rata",      f"{phi_rata:.1f} derajat"),
        _sub("  tipe_material", tipe_material),
        "",
        "  Langkah 1 — Tentukan faktor reduksi momen (alpha_r):",
        "  Rumus  : alpha_r dari kurva Rowe (1952) berdasarkan jenis tanah",
        f"  Tanah  : {catatan}",
        f"  Hasil  : alpha_r = {alpha_r:.2f}",
        "",
        f"  {info_rho}",
        "",
        "  Langkah 2 — Hitung momen desain (Md):",
        "  Rumus  : Md = alpha_r x Mmax_teoritis",
        f"  Hitung : Md = {alpha_r:.2f} x {Mmax_teoritis:.3f}",
        f"  Hasil  : Md = {Md:.3f} kN.m/m",
        f"  Reduksi: {(1-alpha_r)*100:.1f}%  ({Mmax_teoritis - Md:.3f} kN.m/m lebih kecil)",
        _sub("  Satuan",  "kN.m/m"),
        "",
        _sub("  Standar", "Rowe, P.W. (1952) — Proc. ICE, Part 1, Vol. 1, No. 1"),
        _sub("  ",        "USS Sheet Pile Design Manual (1975), Ch. 4, Hal. 4-3"),
        _sub("  ",        "Das, B.M., Principles of Foundation Engineering, 8th Ed., Ch. 9.6"),
        _garis(),
    ]

    referensi = [
        "Rowe, P.W. (1952) — Anchored sheet pile walls, Proc. ICE",
        "USS Sheet Pile Design Manual (1975), Ch. 4, Hal. 4-3 s/d 4-10",
        "Das, B.M., Principles of Foundation Engineering, 8th Ed., Ch. 9.6",
    ]

    return _hasil_dict(
        nilai={
            "Md"      : round(Md,      3),
            "alpha_r" : round(alpha_r, 2),
            "rho"     : rho,
        },
        langkah   = langkah,
        referensi = referensi,
        satuan    = "kN.m/m",
        status    = "",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4A. STABILITAS HEAVE — METODE TERZAGHI
# ─────────────────────────────────────────────────────────────────────────────

def hitung_SF_heave_terzaghi(
    H           : float,
    B_galian    : float,
    cohesion_dasar : float,
    gamma       : float,
    surcharge   : float = 0.0,
    gamma_w     : float = GAMMA_W_DEFAULT,
) -> dict:
    """
    Hitung faktor keamanan heave dengan metode Terzaghi (1943).

    Heave adalah pengangkatan dasar galian akibat tegangan vertikal
    yang melebihi kapasitas dukung tanah dasar galian.

    Rumus Terzaghi (galian persegi panjang, tanah kohesif):
        q_ult     = Nc * cohesion_dasar
        Nc        = 5.7  (untuk B/L = 0, galian panjang tak terbatas)
        q_applied = gamma * H + surcharge
        SF_heave  = q_ult / q_applied

    Batas validitas:
        - Berlaku untuk tanah lempung jenuh (phi = 0, undrained)
        - H/B <= 1 : berlaku langsung (lihat Bjerrum-Eide untuk H/B > 1)

    Referensi:
        [R6] Terzaghi, K. (1943). Theoretical Soil Mechanics. Wiley.
        [R1] SNI 8460:2017, Pasal 10.6.3
        [R2] NAVFAC DM-7.02, Ch. 7, Hal. 7-3

    Parameter:
        H              : kedalaman galian [m]
        B_galian       : lebar galian [m]
        cohesion_dasar : kohesi tanah tak-drainase di dasar galian [kPa]
        gamma          : berat volume tanah di dalam galian [kN/m3]
        surcharge      : beban tambahan di permukaan [kPa]
        gamma_w        : berat volume air [kN/m3]

    Return:
        dict standar; "nilai": {SF_heave, q_ult, q_applied, Nc, H_kritis}
    """
    if H <= 0:
        raise ValueError(f"H harus > 0, diberikan: {H}")
    if B_galian <= 0:
        raise ValueError(f"B_galian harus > 0, diberikan: {B_galian}")
    if cohesion_dasar < 0:
        raise ValueError(f"cohesion_dasar harus >= 0, diberikan: {cohesion_dasar}")
    if gamma <= 0:
        raise ValueError(f"gamma harus > 0, diberikan: {gamma}")

    rasio_HB   = H / B_galian
    Nc         = 5.7      # faktor kapasitas dukung Terzaghi (Nc = 2+pi ~ 5.14 Skempton, 5.7 Terzaghi)
    q_ult      = Nc * cohesion_dasar
    q_applied  = gamma * H + surcharge
    SF_heave   = q_ult / q_applied if q_applied > 1e-9 else 999.0

    # Kedalaman kritis (H di mana SF = 1.0)
    H_kritis = (Nc * cohesion_dasar - surcharge) / gamma if gamma > 0 else 999.0

    status = _status_sf(SF_heave, SF_HEAVE_MIN)

    langkah: list[str] = [
        *_header("Stabilitas Heave — Metode Terzaghi (1943)"),
        "",
        "  Prinsip:",
        "    Heave = pengangkatan dasar galian akibat beban vertikal",
        "    melebihi kapasitas dukung tanah lempung di dasar galian.",
        "    Berlaku untuk tanah kohesif, kondisi tak-drainase (phi = 0).",
        "",
        "  Data input:",
        _sub("  H",              f"{H:.2f} m  (kedalaman galian)"),
        _sub("  B_galian",       f"{B_galian:.2f} m  (lebar galian)"),
        _sub("  H/B",            f"{rasio_HB:.3f}"),
        _sub("  cohesion_dasar", f"{cohesion_dasar:.2f} kPa  (Su tak-drainase di dasar)"),
        _sub("  gamma",          f"{gamma:.2f} kN/m3"),
        _sub("  surcharge",      f"{surcharge:.2f} kPa"),
        "",
        "  Langkah 1 — Kapasitas dukung batas dasar galian (q_ult):",
        "  Rumus  : q_ult = Nc x cohesion_dasar",
        "  Nilai  : Nc = 5.7  (Terzaghi, galian memanjang tak terbatas)",
        f"           cohesion_dasar = {cohesion_dasar:.2f} kPa",
        f"  Hitung : q_ult = 5.7 x {cohesion_dasar:.2f}",
        f"  Hasil  : q_ult = {q_ult:.3f} kPa",
        _sub("  Satuan",  "kPa"),
        "",
        "  Langkah 2 — Tekanan terapan di dasar galian (q_applied):",
        "  Rumus  : q_applied = gamma x H + surcharge",
        f"  Nilai  : gamma = {gamma:.2f} kN/m3",
        f"           H     = {H:.2f} m",
        f"           surcharge = {surcharge:.2f} kPa",
        f"  Hitung : q_applied = {gamma:.2f} x {H:.2f} + {surcharge:.2f}",
        f"           = {gamma*H:.3f} + {surcharge:.2f}",
        f"  Hasil  : q_applied = {q_applied:.3f} kPa",
        _sub("  Satuan",  "kPa"),
        "",
        "  Langkah 3 — Faktor keamanan heave:",
        "  Rumus  : SF_heave = q_ult / q_applied",
        f"  Hitung : SF_heave = {q_ult:.3f} / {q_applied:.3f}",
        f"  Hasil  : SF_heave = {SF_heave:.3f}",
        f"  SF_min = {SF_HEAVE_MIN:.2f}  (SNI 8460:2017, Pasal 10.6.3)",
        f"  Status : {status}",
        "",
        "  Informasi tambahan:",
        f"  H/B     = {rasio_HB:.3f}  ({'Metode Terzaghi OK' if rasio_HB <= 1 else 'Gunakan Bjerrum-Eide untuk H/B > 1'})",
        f"  H_kritis = {H_kritis:.3f} m  (kedalaman di mana SF_heave = 1.0)",
        "",
        _sub("  Standar", "Terzaghi, K. (1943). Theoretical Soil Mechanics. Wiley."),
        _sub("  ",        "SNI 8460:2017, Pasal 10.6.3"),
        _sub("  ",        "NAVFAC DM-7.02, Ch. 7, Hal. 7-3"),
        _garis(),
    ]

    referensi = [
        "Terzaghi, K. (1943). Theoretical Soil Mechanics. Wiley.",
        "SNI 8460:2017, Pasal 10.6.3",
        "NAVFAC DM-7.02, Ch. 7, Hal. 7-3",
    ]

    return _hasil_dict(
        nilai={
            "SF_heave"  : round(SF_heave,  3),
            "q_ult"     : round(q_ult,     3),
            "q_applied" : round(q_applied, 3),
            "Nc"        : Nc,
            "H_kritis"  : round(H_kritis,  3),
            "rasio_HB"  : round(rasio_HB,  3),
        },
        langkah   = langkah,
        referensi = referensi,
        satuan    = "SF (tak berdimensi)",
        status    = status,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4B. STABILITAS HEAVE — METODE BJERRUM-EIDE (H/B > 1)
# ─────────────────────────────────────────────────────────────────────────────

# Tabel faktor Nc Bjerrum-Eide (1956) berdasarkan rasio H/B
# Kolom: H/B → Nc untuk galian bujur sangkar (B/L = 1) dan memanjang (B/L = 0)
_TABEL_NC_BE: list[tuple] = [
    # (H/B, Nc_memanjang, Nc_bujursangkar)
    (0.00, 5.14, 6.17),
    (0.25, 5.35, 6.48),
    (0.50, 5.51, 6.74),
    (0.75, 5.81, 7.16),
    (1.00, 6.20, 7.63),
    (1.50, 7.01, 8.45),
    (2.00, 7.43, 8.92),
    (2.50, 7.64, 9.17),
    (3.00, 7.75, 9.33),
    (4.00, 7.97, 9.66),
    (5.00, 8.14, 9.89),
]


def _interpolasi_Nc_bjerrum(rasio_HB: float, rasio_BL: float) -> float:
    """
    Interpolasi Nc Bjerrum-Eide dari tabel.
    rasio_BL = B/L (0 = memanjang, 1 = bujur sangkar)
    """
    # Klem rasio_HB ke batas tabel
    rasio_HB = max(0.0, min(rasio_HB, 5.0))
    rasio_BL = max(0.0, min(rasio_BL, 1.0))

    # Interpolasi kolom
    Nc_vals = []
    for hb_tabel, nc_panjang, nc_bujur in _TABEL_NC_BE:
        nc_interp = nc_panjang + rasio_BL * (nc_bujur - nc_panjang)
        Nc_vals.append((hb_tabel, nc_interp))

    # Interpolasi baris berdasarkan H/B
    for i in range(len(Nc_vals) - 1):
        hb0, nc0 = Nc_vals[i]
        hb1, nc1 = Nc_vals[i + 1]
        if hb0 <= rasio_HB <= hb1:
            frac = (rasio_HB - hb0) / (hb1 - hb0)
            return nc0 + frac * (nc1 - nc0)

    return Nc_vals[-1][1]


def hitung_SF_heave_bjerrum_eide(
    H              : float,
    B_galian       : float,
    L_galian       : float,
    cohesion_dasar : float,
    gamma          : float,
    surcharge      : float = 0.0,
) -> dict:
    """
    Hitung faktor keamanan heave dengan metode Bjerrum & Eide (1956).

    Metode ini lebih akurat dari Terzaghi untuk H/B > 1.
    Mempertimbangkan bentuk galian (B/L ratio).

    Rumus:
        SF_heave = (Nc * cohesion_dasar) / (gamma * H + surcharge)
        Nc = f(H/B, B/L)   [dari tabel Bjerrum-Eide]

    Referensi:
        [R7] Bjerrum, L. & Eide, O. (1956). Stability of strutted excavations
             in clay. Geotechnique, 6(1), 32-47.
        [R1] SNI 8460:2017, Pasal 10.6.3
        [R2] NAVFAC DM-7.02, Ch. 7, Hal. 7-4

    Parameter:
        H              : kedalaman galian [m]
        B_galian       : lebar galian [m]
        L_galian       : panjang galian [m]
        cohesion_dasar : kohesi tak-drainase di dasar galian [kPa]
        gamma          : berat volume tanah [kN/m3]
        surcharge      : beban permukaan [kPa]

    Return:
        dict standar
    """
    if H <= 0 or B_galian <= 0 or L_galian <= 0:
        raise ValueError("H, B_galian, dan L_galian harus > 0")

    rasio_HB = H / B_galian
    rasio_BL = B_galian / L_galian
    Nc       = _interpolasi_Nc_bjerrum(rasio_HB, rasio_BL)

    q_ult     = Nc * cohesion_dasar
    q_applied = gamma * H + surcharge
    SF_heave  = q_ult / q_applied if q_applied > 1e-9 else 999.0

    status = _status_sf(SF_heave, SF_HEAVE_MIN)

    langkah: list[str] = [
        *_header("Stabilitas Heave — Metode Bjerrum-Eide (1956)"),
        "",
        "  Berlaku untuk: H/B > 1, mempertimbangkan bentuk galian.",
        "",
        "  Data input:",
        _sub("  H",              f"{H:.2f} m"),
        _sub("  B_galian",       f"{B_galian:.2f} m"),
        _sub("  L_galian",       f"{L_galian:.2f} m"),
        _sub("  H/B",            f"{rasio_HB:.3f}"),
        _sub("  B/L",            f"{rasio_BL:.3f}  ({'memanjang' if rasio_BL < 0.3 else 'persegi'})"),
        _sub("  cohesion_dasar", f"{cohesion_dasar:.2f} kPa"),
        _sub("  gamma",          f"{gamma:.2f} kN/m3"),
        _sub("  surcharge",      f"{surcharge:.2f} kPa"),
        "",
        "  Langkah 1 — Faktor Nc dari tabel Bjerrum-Eide:",
        "  Rumus  : Nc = f(H/B, B/L)  [interpolasi dari tabel Bjerrum-Eide 1956]",
        f"  H/B    = {rasio_HB:.3f}",
        f"  B/L    = {rasio_BL:.3f}",
        f"  Hasil  : Nc = {Nc:.4f}  (interpolasi dari tabel)",
        "",
        "  Tabel Nc Bjerrum-Eide (nilai acuan):",
        "  H/B    | Nc (memanjang) | Nc (bujur sangkar)",
        "  -------|----------------|-------------------",
        *[
            f"  {hb:>5.2f}  | {nc_p:>14.2f} | {nc_b:>18.2f}"
            for hb, nc_p, nc_b in _TABEL_NC_BE
        ],
        "",
        "  Langkah 2 — Kapasitas dukung dasar galian:",
        "  Rumus  : q_ult = Nc x cohesion_dasar",
        f"  Hitung : q_ult = {Nc:.4f} x {cohesion_dasar:.2f}",
        f"  Hasil  : q_ult = {q_ult:.3f} kPa",
        "",
        "  Langkah 3 — Beban yang bekerja di dasar galian:",
        "  Rumus  : q_applied = gamma x H + surcharge",
        f"  Hitung : q_applied = {gamma:.2f} x {H:.2f} + {surcharge:.2f}",
        f"  Hasil  : q_applied = {q_applied:.3f} kPa",
        "",
        "  Langkah 4 — Faktor keamanan heave:",
        "  Rumus  : SF_heave = q_ult / q_applied",
        f"  Hitung : SF_heave = {q_ult:.3f} / {q_applied:.3f}",
        f"  Hasil  : SF_heave = {SF_heave:.3f}",
        f"  SF_min = {SF_HEAVE_MIN:.2f}  (SNI 8460:2017, Pasal 10.6.3)",
        f"  Status : {status}",
        "",
        _sub("  Standar", "Bjerrum & Eide (1956). Geotechnique, 6(1), 32-47."),
        _sub("  ",        "SNI 8460:2017, Pasal 10.6.3"),
        _sub("  ",        "NAVFAC DM-7.02, Ch. 7, Hal. 7-4"),
        _garis(),
    ]

    referensi = [
        "Bjerrum, L. & Eide, O. (1956). Geotechnique, 6(1), 32-47.",
        "SNI 8460:2017, Pasal 10.6.3",
        "NAVFAC DM-7.02, Ch. 7, Hal. 7-4",
    ]

    return _hasil_dict(
        nilai={
            "SF_heave"  : round(SF_heave,  3),
            "q_ult"     : round(q_ult,     3),
            "q_applied" : round(q_applied, 3),
            "Nc"        : round(Nc,        4),
            "rasio_HB"  : round(rasio_HB,  3),
            "rasio_BL"  : round(rasio_BL,  3),
        },
        langkah   = langkah,
        referensi = referensi,
        satuan    = "SF (tak berdimensi)",
        status    = status,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. STABILITAS PIPING — LANE'S WEIGHTED CREEP RATIO
# ─────────────────────────────────────────────────────────────────────────────

# Nilai aman Lane's Weighted Creep Ratio (Cw_min) berdasarkan jenis tanah
_TABEL_LANE_CW: dict = {
    "pasir sangat halus / lanau": 8.5,
    "pasir halus"               : 7.0,
    "pasir sedang"              : 6.0,
    "pasir kasar"               : 5.0,
    "kerikil halus"             : 4.0,
    "kerikil sedang s/d kasar"  : 3.5,
    "bongkahan dan kerikil"     : 3.0,
    "lempung lunak s/d medium"  : 3.0,
    "lempung kaku"              : 2.0,
    "lempung sangat kaku/keras" : 1.6,
}


def hitung_SF_piping(
    H_total     : float,
    D           : float,
    delta_H     : float,
    jenis_tanah : str = "lempung lunak s/d medium",
    panjang_vert: float | None = None,
    panjang_hor : float | None = None,
) -> dict:
    """
    Hitung faktor keamanan terhadap piping menggunakan metode Lane (1935).

    Lane's Weighted Creep Ratio (Cw):
        Cw = (Lv + Lh/3) / delta_H
        di mana:
            Lv      = panjang jalur aliran vertikal [m]
            Lh      = panjang jalur aliran horizontal [m]
            delta_H = beda tinggi air (head difference) [m]

        Untuk turap sederhana (tanpa toe berm):
            Lv = 2 * D  (turun + naik melewati ujung turap)
            Lh ~ 0      (jalur horizontal minimal)

        SF_piping = Cw_hitung / Cw_min  (Cw_min dari tabel Lane)

    Referensi:
        [R8] Lane, E.W. (1935). Security from under-seepage.
             Trans. ASCE, Vol. 100, Hal. 1235-1272.
        [R3] NAVFAC DM-7.01, Ch. 6, Section 6.3, Hal. 6-8

    Parameter:
        H_total     : tinggi total turap = H galian + D [m]
        D           : kedalaman penetrasi [m]
        delta_H     : beda tinggi muka air di kedua sisi turap [m]
        jenis_tanah : jenis tanah (kunci dari _TABEL_LANE_CW)
        panjang_vert: panjang jalur vertikal [m] (default = 2*D)
        panjang_hor : panjang jalur horizontal [m] (default = 0)

    Return:
        dict standar; "nilai": {SF_piping, Cw_hitung, Cw_min, Lv, Lh}
    """
    if H_total <= 0:
        raise ValueError(f"H_total harus > 0, diberikan: {H_total}")
    if D <= 0:
        raise ValueError(f"D harus > 0, diberikan: {D}")
    if delta_H <= 0:
        raise ValueError(f"delta_H harus > 0, diberikan: {delta_H}")

    # Panjang jalur aliran
    Lv = panjang_vert if panjang_vert is not None else 2.0 * D
    Lh = panjang_hor  if panjang_hor  is not None else 0.0

    Cw_hitung = (Lv + Lh / 3.0) / delta_H

    # Cw_min dari tabel
    jenis_key  = jenis_tanah.lower().strip()
    Cw_min     = None
    for k, v in _TABEL_LANE_CW.items():
        if jenis_key in k.lower() or k.lower() in jenis_key:
            Cw_min = v
            break
    if Cw_min is None:
        # default lempung lunak
        Cw_min = 3.0
        jenis_tanah = "lempung lunak s/d medium (default)"

    SF_piping = Cw_hitung / Cw_min
    status    = _status_sf(SF_piping, SF_PIPING_MIN)

    langkah: list[str] = [
        *_header("Stabilitas Piping — Lane's Weighted Creep Ratio (1935)"),
        "",
        "  Prinsip:",
        "    Piping = kerusakan akibat aliran air di bawah turap",
        "    yang mengikis butiran tanah (internal erosion).",
        "    Lane's method: membandingkan panjang jalur aliran",
        "    terhadap beda head air (delta_H).",
        "",
        "  Data input:",
        _sub("  H_total",    f"{H_total:.2f} m  (tinggi total turap = H + D)"),
        _sub("  D",          f"{D:.2f} m  (kedalaman penetrasi)"),
        _sub("  delta_H",    f"{delta_H:.2f} m  (beda muka air dua sisi)"),
        _sub("  jenis_tanah",jenis_tanah),
        _sub("  Lv",         f"{Lv:.2f} m  (panjang jalur vertikal, default = 2D)"),
        _sub("  Lh",         f"{Lh:.2f} m  (panjang jalur horizontal)"),
        "",
        "  Langkah 1 — Hitung Lane's Weighted Creep Ratio (Cw):",
        "  Rumus  : Cw = (Lv + Lh/3) / delta_H",
        f"  Nilai  : Lv = {Lv:.2f} m",
        f"           Lh = {Lh:.2f} m",
        f"           delta_H = {delta_H:.2f} m",
        f"  Hitung : Cw = ({Lv:.2f} + {Lh:.2f}/3) / {delta_H:.2f}",
        f"              = ({Lv:.2f} + {Lh/3:.4f}) / {delta_H:.2f}",
        f"              = {Lv + Lh/3:.4f} / {delta_H:.2f}",
        f"  Hasil  : Cw = {Cw_hitung:.4f}",
        "",
        "  Langkah 2 — Nilai Cw minimum (dari tabel Lane):",
        "  Tabel Lane's Safe Weighted Creep Ratio (Cw_min):",
        "  Jenis Tanah                     | Cw_min",
        "  -------------------------------|-------",
        *[f"  {k:<32} | {v:.1f}" for k, v in _TABEL_LANE_CW.items()],
        "",
        f"  Tanah yang digunakan : {jenis_tanah}",
        f"  Cw_min               : {Cw_min:.1f}",
        "",
        "  Langkah 3 — Faktor keamanan piping:",
        "  Rumus  : SF_piping = Cw_hitung / Cw_min",
        f"  Hitung : SF_piping = {Cw_hitung:.4f} / {Cw_min:.1f}",
        f"  Hasil  : SF_piping = {SF_piping:.3f}",
        f"  SF_min = {SF_PIPING_MIN:.2f}  (NAVFAC DM-7.01)",
        f"  Status : {status}",
        "",
        _sub("  Standar", "Lane, E.W. (1935). Trans. ASCE, Vol. 100, Hal. 1235-1272"),
        _sub("  ",        "NAVFAC DM-7.01, Ch. 6, Section 6.3, Hal. 6-8"),
        _garis(),
    ]

    referensi = [
        "Lane, E.W. (1935). Security from under-seepage. Trans. ASCE 100.",
        "NAVFAC DM-7.01, Ch. 6, Section 6.3, Hal. 6-8",
    ]

    return _hasil_dict(
        nilai={
            "SF_piping" : round(SF_piping,  3),
            "Cw_hitung" : round(Cw_hitung,  4),
            "Cw_min"    : Cw_min,
            "Lv"        : round(Lv,         3),
            "Lh"        : round(Lh,         3),
            "delta_H"   : delta_H,
        },
        langkah   = langkah,
        referensi = referensi,
        satuan    = "SF (tak berdimensi)",
        status    = status,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. RANGKUMAN STABILITAS
# ─────────────────────────────────────────────────────────────────────────────

def rangkuman_stabilitas(
    hasil_analisis: dict,
    nama_proyek   : str = "Analisis Turap",
) -> dict:
    """
    Buat tabel rangkuman semua faktor keamanan vs persyaratan minimum.

    Parameter:
        hasil_analisis : dict berisi kunci-kunci berikut (semua opsional):
            "free_earth"     : hasil dari free_earth_support()
            "fixed_earth"    : hasil dari fixed_earth_support_cantilever()
            "rowe"           : hasil dari koreksi_momen_rowe()
            "heave_terzaghi" : hasil dari hitung_SF_heave_terzaghi()
            "heave_bjerrum"  : hasil dari hitung_SF_heave_bjerrum_eide()
            "piping"         : hasil dari hitung_SF_piping()
        nama_proyek    : label proyek untuk header tabel

    Return:
        dict standar; "nilai": dict ringkasan semua SF
    """
    def _ambil(kunci_luar: str, kunci_dalam: str, default=None):
        bagian = hasil_analisis.get(kunci_luar)
        if bagian is None:
            return default
        return bagian.get("nilai", {}).get(kunci_dalam, default)

    def _status_baris(sf, sf_min) -> str:
        if sf is None:
            return "tidak dihitung"
        return "AMAN        [OK]" if sf >= sf_min else "TIDAK AMAN  [!!]"

    # Kumpulkan semua nilai
    items: list[tuple] = []

    # ── Analisis gaya dalam ───────────────────────────────────────────────────
    tipe = None
    if "free_earth" in hasil_analisis:
        tipe     = "free_earth"
        D_min    = _ambil("free_earth",  "D_min")
        D_design = _ambil("free_earth",  "D_design")
        SF_mom   = _ambil("free_earth",  "SF_momen")
        Ra       = _ambil("free_earth",  "Ra")
        Mmax     = _ambil("free_earth",  "Mmax")

        if "rowe" in hasil_analisis:
            Md = _ambil("rowe", "Md")
            alpha_r = _ambil("rowe", "alpha_r")
        else:
            Md = Mmax
            alpha_r = 1.0

        items += [
            ("Metode",             "Free Earth Support",          "",     "",   ""),
            ("D_min",              D_min,                         "m",    None, ""),
            ("D_design",           D_design,                      "m",    None, ""),
            ("Ra (gaya angkur)",   Ra,                            "kN/m", None, ""),
            ("Mmax teoritis",      Mmax,                          "kN.m/m",None,""),
            ("Md (setelah Rowe)",  Md,                            "kN.m/m",None,f"alpha_r={alpha_r}"),
            ("SF momen",           SF_mom,                        "-",    SF_GULING_MIN, ""),
        ]

    elif "fixed_earth" in hasil_analisis:
        tipe     = "fixed_earth"
        D_min    = _ambil("fixed_earth", "D_min")
        D_design = _ambil("fixed_earth", "D_design")
        SF_mom   = _ambil("fixed_earth", "SF_momen")
        Mmax     = _ambil("fixed_earth", "Mmax")
        z0       = _ambil("fixed_earth", "z0")

        items += [
            ("Metode",             "Fixed Earth Support (Kantilever)", "", "",  ""),
            ("D_min",              D_min,    "m",    None,          ""),
            ("D_design",           D_design, "m",    None,          ""),
            ("z0 (titik jepit)",   z0,       "m",    None,          "dari permukaan"),
            ("Mmax",               Mmax,     "kN.m/m",None,         ""),
            ("SF momen",           SF_mom,   "-",    SF_GULING_MIN, ""),
        ]

    # ── Heave ─────────────────────────────────────────────────────────────────
    sf_heave_t = _ambil("heave_terzaghi", "SF_heave")
    sf_heave_b = _ambil("heave_bjerrum",  "SF_heave")

    if sf_heave_t is not None:
        items.append(("SF heave (Terzaghi)",   sf_heave_t, "-", SF_HEAVE_MIN, ""))
    if sf_heave_b is not None:
        items.append(("SF heave (Bjerrum-Eide)",sf_heave_b, "-", SF_HEAVE_MIN, ""))

    # ── Piping ────────────────────────────────────────────────────────────────
    sf_piping = _ambil("piping", "SF_piping")
    if sf_piping is not None:
        items.append(("SF piping (Lane)",       sf_piping, "-", SF_PIPING_MIN, ""))

    # ── Susun tabel ──────────────────────────────────────────────────────────
    lebar_nama   = 26
    lebar_nilai  = 12
    lebar_satuan = 10
    lebar_sfmin  = 10
    lebar_status = 20

    baris_header = (
        f"  {'Parameter':<{lebar_nama}} "
        f"{'Nilai':>{lebar_nilai}} "
        f"{'Satuan':<{lebar_satuan}} "
        f"{'SF_min':>{lebar_sfmin}} "
        f"{'Status / Keterangan':<{lebar_status}}"
    )
    garis_tabel = "  " + "-" * (lebar_nama + lebar_nilai + lebar_satuan + lebar_sfmin + lebar_status + 5)

    langkah: list[str] = [
        *_header(f"Rangkuman Stabilitas — {nama_proyek}"),
        "",
        baris_header,
        garis_tabel,
    ]

    all_aman = True
    ringkasan_nilai: dict = {}

    for item in items:
        nama_par, nilai_par, satuan_par, sf_min_par, ket_par = item

        if nilai_par is None:
            nilai_str  = "  -"
            status_str = "tidak dihitung"
        elif isinstance(nilai_par, str):
            # baris judul (bukan angka)
            langkah.append("")
            langkah.append(f"  *** {nilai_par} ***")
            continue
        elif isinstance(nilai_par, float):
            nilai_str = f"{nilai_par:>{lebar_nilai}.3f}"
            if sf_min_par is not None:
                status_str = _status_baris(nilai_par, sf_min_par)
                if nilai_par < sf_min_par:
                    all_aman = False
                ringkasan_nilai[nama_par] = {
                    "nilai" : nilai_par,
                    "sf_min": sf_min_par,
                    "aman"  : nilai_par >= sf_min_par,
                }
            else:
                status_str = ket_par if ket_par else ""
        else:
            nilai_str  = str(nilai_par)
            status_str = ket_par if ket_par else ""

        sfmin_str = f"{sf_min_par:.2f}" if sf_min_par is not None else "  -"

        langkah.append(
            f"  {nama_par:<{lebar_nama}} "
            f"{nilai_str:>{lebar_nilai}} "
            f"{satuan_par:<{lebar_satuan}} "
            f"{sfmin_str:>{lebar_sfmin}} "
            f"{status_str:<{lebar_status}}"
        )

    langkah += [
        garis_tabel,
        "",
        f"  KESIMPULAN KESELURUHAN: {'SEMUA AMAN  [OK]' if all_aman else 'ADA YANG TIDAK AMAN  [!!] -- PERLU REVISI'}",
        "",
        "  Persyaratan minimum:",
        f"    SF momen (guling)    >= {SF_GULING_MIN:.2f}  (NAVFAC DM-7.02, SNI 8460:2017 Ps. 9.6.2)",
        f"    SF heave             >= {SF_HEAVE_MIN:.2f}  (SNI 8460:2017, Pasal 10.6.3)",
        f"    SF piping (Lane)     >= {SF_PIPING_MIN:.2f}  (NAVFAC DM-7.01, Ch. 6)",
        "",
        _sub("  Standar", "SNI 8460:2017, Pasal 9.6.2 dan 10.6.3"),
        _sub("  ",        "NAVFAC DM-7.02, Ch. 3 dan 7"),
        _sub("  ",        "NAVFAC DM-7.01, Ch. 6, Section 6.3"),
        _garis("="),
    ]

    status_keseluruhan = "SEMUA AMAN" if all_aman else "TIDAK AMAN — PERLU REVISI"

    referensi = [
        "SNI 8460:2017, Pasal 9.6.2 dan 10.6.3",
        "NAVFAC DM-7.02, Ch. 3 dan 7",
        "NAVFAC DM-7.01, Ch. 6, Section 6.3",
    ]

    return _hasil_dict(
        nilai=ringkasan_nilai,
        langkah=langkah,
        referensi=referensi,
        satuan="-",
        status=status_keseluruhan,
    )


# ─────────────────────────────────────────────────────────────────────────────
# FUNGSI UTILITAS TAMBAHAN
# ─────────────────────────────────────────────────────────────────────────────

def phi_rata_lapisan(
    lapisan_tanah: list[dict],
    H_tinjauan   : float,
) -> float:
    """
    Hitung sudut geser rata-rata tertimbang berdasarkan ketebalan lapisan
    sampai kedalaman H_tinjauan.

    Digunakan sebagai input untuk koreksi momen Rowe.
    """
    total_tebal = 0.0
    total_phi   = 0.0
    z_cursor    = 0.0
    for lyr in lapisan_tanah:
        if z_cursor >= H_tinjauan:
            break
        dz_efektif = min(lyr["tebal"], H_tinjauan - z_cursor)
        total_tebal += dz_efektif
        total_phi   += lyr["phi"] * dz_efektif
        z_cursor    += lyr["tebal"]
    return total_phi / total_tebal if total_tebal > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# CONTOH PENGGUNAAN — jalankan: python stability.py
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 64)
    print("  CONTOH PERHITUNGAN STABILITAS TURAP")
    print("  Data: lempung berlapis, khas Jabodetabek")
    print("=" * 64 + "\n")

    # ── Data tanah ────────────────────────────────────────────────────────────
    LAPISAN = [
        {"nama": "Lempung lunak",  "tebal": 3.0,
         "gamma": 16.0, "gamma_sat": 17.0, "phi": 10.0, "cohesion": 10.0},
        {"nama": "Lempung medium", "tebal": 5.0,
         "gamma": 17.0, "gamma_sat": 18.5, "phi": 20.0, "cohesion": 20.0},
        {"nama": "Lempung kaku",   "tebal": 8.0,
         "gamma": 18.5, "gamma_sat": 19.5, "phi": 25.0, "cohesion": 35.0},
    ]

    H        = 4.0    # m
    MAT      = 1.5    # m
    SURCHARGE= 10.0   # kPa
    B_GALIAN = 6.0    # m
    L_GALIAN = 20.0   # m
    DELTA_H  = 3.5    # m (beda muka air dua sisi)

    # 1. Free Earth Support (angkur di z=0.5 m dari permukaan)
    print(">>> Free Earth Support Method ...")
    res_fes = free_earth_support(
        H             = H,
        lapisan_tanah = LAPISAN,
        surcharge     = SURCHARGE,
        muka_air      = MAT,
        tinggi_angkur = 0.5,
    )
    print(format_langkah(res_fes["langkah"]))

    # 2. Fixed Earth Support (kantilever)
    print(">>> Fixed Earth Support Method ...")
    res_fix = fixed_earth_support_cantilever(
        H             = H,
        lapisan_tanah = LAPISAN,
        surcharge     = SURCHARGE,
        muka_air      = MAT,
    )
    print(format_langkah(res_fix["langkah"]))

    # 3. Koreksi momen Rowe (untuk turap baja dengan angkur)
    phi_r = phi_rata_lapisan(LAPISAN, H + res_fes["nilai"]["D_design"])
    res_rowe = koreksi_momen_rowe(
        Mmax_teoritis  = res_fes["nilai"]["Mmax"],
        H              = H,
        D_design       = res_fes["nilai"]["D_design"],
        Ra             = res_fes["nilai"]["Ra"],
        phi_rata       = phi_r,
        tipe_material  = "baja",
    )
    print(format_langkah(res_rowe["langkah"]))

    # 4a. Heave Terzaghi
    cohesion_dasar = LAPISAN[1]["cohesion"]
    res_heave_t = hitung_SF_heave_terzaghi(
        H              = H,
        B_galian       = B_GALIAN,
        cohesion_dasar = cohesion_dasar,
        gamma          = LAPISAN[0]["gamma"],
        surcharge      = SURCHARGE,
    )
    print(format_langkah(res_heave_t["langkah"]))

    # 4b. Heave Bjerrum-Eide
    res_heave_b = hitung_SF_heave_bjerrum_eide(
        H              = H,
        B_galian       = B_GALIAN,
        L_galian       = L_GALIAN,
        cohesion_dasar = cohesion_dasar,
        gamma          = LAPISAN[0]["gamma"],
        surcharge      = SURCHARGE,
    )
    print(format_langkah(res_heave_b["langkah"]))

    # 5. Piping
    res_piping = hitung_SF_piping(
        H_total     = H + res_fes["nilai"]["D_design"],
        D           = res_fes["nilai"]["D_design"],
        delta_H     = DELTA_H,
        jenis_tanah = "lempung lunak s/d medium",
    )
    print(format_langkah(res_piping["langkah"]))

    # 6. Rangkuman
    res_rangkuman = rangkuman_stabilitas(
        hasil_analisis={
            "free_earth"     : res_fes,
            "rowe"           : res_rowe,
            "heave_terzaghi" : res_heave_t,
            "heave_bjerrum"  : res_heave_b,
            "piping"         : res_piping,
        },
        nama_proyek = "Galian Basement Lempung Jabodetabek",
    )
    print(format_langkah(res_rangkuman["langkah"]))
    print(f"\nStatus keseluruhan: {res_rangkuman['status']}")
