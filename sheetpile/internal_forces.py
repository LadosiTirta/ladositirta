"""
================================================================================
internal_forces.py
================================================================================
Modul perhitungan gaya dalam turap / sheet pile.

Yang dihitung:
    1. Diagram gaya geser V(z)         [kN/m]
    2. Diagram momen lentur M(z)       [kN.m/m]
    3. Momen maksimum M_max dan lokasi z_Mmax
    4. Titik geser nol (V = 0)
    5. Plot diagram V dan M siap Streamlit

Metode integrasi:
    Aturan trapesium (trapezoid rule) — konsisten dengan Tahap 1 dan 2.

Referensi utama:
    [R1]  SNI 8460:2017   — Persyaratan Perancangan Geoteknik, Pasal 9
    [R2]  NAVFAC DM-7.02  — Foundations & Earth Structures, Ch. 3, Section 3.2.5
    [R4]  USS Sheet Pile  — Design Manual (1975), Ch. 3–4
    [R5]  Das, B.M.       — Principles of Foundation Engineering, 8th Ed., Ch. 9

Konvensi:
    Satuan  : kN/m (geser), kN.m/m (momen), m (panjang)
    Variabel: nama kata, tanpa simbol Yunani
    Teks    : plain text kompatibel Word & PDF
    z       : kedalaman diukur dari permukaan tanah (positif ke bawah)

Tanda konvensi momen:
    Momen positif (+) = tegangan tarik serat kanan turap (konvensional geoteknik)
    Nilai M_max yang dipakai untuk desain = nilai absolut terbesar |M(z)|

Penulis  : Structural Civil Engineer — Pabrik Beton Pracetak, Jabodetabek
Versi    : 1.0.0
================================================================================
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D


# ─────────────────────────────────────────────────────────────────────────────
# FUNGSI PEMBANTU FORMAT
# ─────────────────────────────────────────────────────────────────────────────

def _garis(karakter: str = "-", lebar: int = 64) -> str:
    return karakter * lebar


def _header(judul: str) -> list[str]:
    lebar = 64
    return [_garis("=", lebar), f"  {judul.upper()}", _garis("=", lebar)]


def _sub(label: str, nilai: str) -> str:
    return f"  {label:<16}: {nilai}"


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
    """Gabungkan list langkah menjadi string untuk st.code() atau st.text()."""
    return "\n".join(langkah)


# ─────────────────────────────────────────────────────────────────────────────
# 1. HITUNG GAYA DALAM — TURAP DENGAN ANGKUR (FREE EARTH SUPPORT)
# ─────────────────────────────────────────────────────────────────────────────

def hitung_gaya_dalam(
    z_array       : np.ndarray,
    tekanan_array : np.ndarray,
    Ra            : float,
    z_angkur      : float,
    p_aktif       : np.ndarray | None = None,
    p_pasif       : np.ndarray | None = None,
    u_array       : np.ndarray | None = None,
    interval_log  : float = 0.5,
) -> dict:
    """
    Hitung diagram gaya geser V(z) dan momen lentur M(z) untuk turap
    dengan angkur (Free Earth Support Method).

    Rumus integrasi (aturan trapesium):

        V(z) = Ra - integral[ p_net(z'), z'=0..z ]
        M(z) = Ra * (z - z_angkur) - integral[ p_net(z') * (z - z'), z'=0..z ]

    di mana:
        p_net(z) = tekanan neto = tekanan aktif - tekanan pasif  [kPa]
        Ra       = gaya angkur  [kN/m]
        z_angkur = kedalaman titik angkur dari permukaan  [m]

    Syarat batas:
        V(0) = Ra   (di permukaan, geser = gaya angkur)
        M(z_angkur) = 0  (momen di titik angkur = 0, idealnya)

    Referensi:
        [R2] NAVFAC DM-7.02, Ch. 3, Section 3.2.5, Hal. 3-14
        [R4] USS Sheet Pile Design Manual (1975), Ch. 4, Hal. 4-2
        [R5] Das, B.M., 8th Ed., Ch. 9.5

    Parameter:
        z_array       : array kedalaman dari permukaan [m]
        tekanan_array : array tekanan neto p_net = Pa - Pp [kPa]
        Ra            : gaya angkur [kN/m]
        z_angkur      : kedalaman angkur dari permukaan [m]
        p_aktif       : array tekanan aktif [kPa] (opsional, untuk tabel)
        p_pasif       : array tekanan pasif [kPa] (opsional, untuk tabel)
        u_array       : array tekanan air pori [kPa] (opsional)
        interval_log  : interval z untuk log tabel [m] (default 0.5)

    Return:
        dict standar; "nilai" berisi:
            {V_array, M_array, M_max, z_Mmax, z_V0, V0_interpolasi,
             z_array, tekanan_array}
    """
    # ── Validasi ──────────────────────────────────────────────────────────────
    if len(z_array) < 2:
        raise ValueError("z_array harus memiliki minimal 2 titik.")
    if len(z_array) != len(tekanan_array):
        raise ValueError(
            f"Panjang z_array ({len(z_array)}) dan tekanan_array "
            f"({len(tekanan_array)}) harus sama."
        )
    if z_angkur < 0:
        raise ValueError(f"z_angkur harus >= 0, diberikan: {z_angkur}")

    n   = len(z_array)
    dz  = z_array[1] - z_array[0]   # interval kedalaman (dianggap seragam)

    # ── Inisialisasi array ────────────────────────────────────────────────────
    V_arr = np.zeros(n)
    M_arr = np.zeros(n)

    # Kondisi awal di z=0
    V_arr[0] = Ra    # gaya geser di permukaan = gaya angkur

    # Momen awal di z=0 (relatif terhadap angkur)
    M_arr[0] = Ra * (z_array[0] - z_angkur)

    langkah: list[str] = [
        *_header("Gaya Dalam Turap — Diagram V dan M (Free Earth Support)"),
        "",
        "  Metode: Integrasi numerik aturan trapesium",
        "",
        "  Rumus gaya geser:",
        "    V(z) = Ra - integral[ p_net(z') dz',  z'=0 s/d z ]",
        "",
        "  Rumus momen lentur:",
        "    M(z) = Ra*(z - z_angkur)",
        "           - integral[ p_net(z') * (z - z') dz',  z'=0 s/d z ]",
        "",
        "  Data input:",
        _sub("  Ra",        f"{Ra:.4f} kN/m"),
        _sub("  z_angkur",  f"{z_angkur:.3f} m dari permukaan"),
        _sub("  z_min",     f"{z_array[0]:.3f} m"),
        _sub("  z_max",     f"{z_array[-1]:.3f} m"),
        _sub("  n titik",   f"{n}"),
        _sub("  dz rata",   f"{dz:.4f} m"),
        "",
        "  Kondisi batas:",
        f"    V(z=0)       = Ra = {Ra:.4f} kN/m",
        f"    M(z_angkur)  = 0  (idealnya, z_angkur = {z_angkur:.3f} m)",
        "",
    ]

    # ── Integrasi kumulatif ───────────────────────────────────────────────────
    # integral_p[i] = integral p_net dari z[0] s/d z[i]
    integral_p      = np.zeros(n)
    integral_p_lengan = np.zeros(n)

    for i in range(1, n):
        # Trapesium: area = (p[i-1] + p[i]) / 2 * dz_i
        dz_i            = z_array[i] - z_array[i - 1]
        integral_p[i]   = integral_p[i - 1] + 0.5 * (tekanan_array[i - 1] + tekanan_array[i]) * dz_i

        # integral p*(z_i - z') dari 0 s/d z_i
        # = integral p(z')*(z_i - z') dz'  -- lengan berubah sesuai z_i
        # Dihitung secara akumulatif:
        # Delta_integral = integral dari z[i-1] s/d z[i] dari p*(z_i-z')
        # ~ 0.5*(p[i-1]*(z_i-z[i-1]) + p[i]*(z_i-z[i])) * dz_i
        # = 0.5*(p[i-1]*dz_i + p[i]*0) * dz_i  -- titik kanan lengan = 0
        # lebih akurat: integral dari bawah
        integral_p_lengan[i] = (
            integral_p_lengan[i - 1]
            + integral_p[i - 1] * dz_i
            + 0.5 * (tekanan_array[i - 1] + tekanan_array[i]) * dz_i * dz_i / 2
        )

        V_arr[i] = Ra - integral_p[i]
        M_arr[i] = Ra * (z_array[i] - z_angkur) - integral_p_lengan[i]

    # ── Cari M_max dan V=0 ────────────────────────────────────────────────────
    hasil_mmax = cari_M_max(z_array, V_arr, M_arr)
    M_max    = hasil_mmax["nilai"]["M_max"]
    z_Mmax   = hasil_mmax["nilai"]["z_Mmax"]
    z_V0     = hasil_mmax["nilai"]["z_V0"]
    V0_interp = hasil_mmax["nilai"]["V0_interpolasi"]

    # ── Tabel ringkasan ───────────────────────────────────────────────────────
    # Header tabel
    ada_aktif = p_aktif is not None
    ada_pasif = p_pasif is not None
    ada_u     = u_array is not None

    lebar = {
        "z"   : 7,  "pa": 14, "pp": 14,
        "pnet": 14, "V" : 12, "M" : 14,
    }

    # Susun header kolom
    header_tabel = (
        f"  {'z(m)':>{lebar['z']}} "
    )
    if ada_aktif:
        header_tabel += f"{'Pa(kPa)':>{lebar['pa']}} "
    if ada_pasif:
        header_tabel += f"{'Pp(kPa)':>{lebar['pp']}} "
    header_tabel += (
        f"{'Pnet(kPa)':>{lebar['pnet']}} "
        f"{'V(kN/m)':>{lebar['V']}} "
        f"{'M(kN.m/m)':>{lebar['M']}}"
    )

    garis_tabel = "  " + "-" * (len(header_tabel) - 2)

    langkah += [
        _garis("-"),
        "  TABEL RINGKASAN GAYA DALAM",
        _garis("-"),
        header_tabel,
        garis_tabel,
    ]

    # Isi tabel (setiap interval_log m)
    z_prev_log = -999.0
    for i, z in enumerate(z_array):
        # Tandai titik penting: permukaan, angkur, V=0, M_max, ujung
        ket_list = []
        if abs(z) < 1e-6:
            ket_list.append("permukaan")
        if abs(z - z_angkur) < abs(dz) / 2:
            ket_list.append("ANGKUR")
        if abs(z - z_V0) < abs(dz) * 1.5:
            ket_list.append("V=0")
        if abs(z - z_Mmax) < abs(dz) * 1.5:
            ket_list.append("M_MAX")
        if i == n - 1:
            ket_list.append("ujung")
        ket = " [" + ", ".join(ket_list) + "]" if ket_list else ""

        # Cetak jika interval log terpenuhi atau titik penting
        harus_log = (z - z_prev_log >= interval_log - 1e-9) or bool(ket_list)
        if harus_log:
            baris = f"  {z:>{lebar['z']}.2f} "
            if ada_aktif:
                baris += f"{p_aktif[i]:>{lebar['pa']}.3f} "
            if ada_pasif:
                baris += f"{p_pasif[i]:>{lebar['pp']}.3f} "
            baris += (
                f"{tekanan_array[i]:>{lebar['pnet']}.3f} "
                f"{V_arr[i]:>{lebar['V']}.3f} "
                f"{M_arr[i]:>{lebar['M']}.3f}"
                f"{ket}"
            )
            langkah.append(baris)
            z_prev_log = z

    langkah += [
        garis_tabel,
        "",
    ]

    # ── Log detail contoh perhitungan (3 titik representatif) ────────────────
    langkah += [
        _garis("-"),
        "  CONTOH PERHITUNGAN DETAIL (3 TITIK REPRESENTATIF)",
        _garis("-"),
    ]

    titik_contoh = []
    # Titik 1: z ~ H/4
    idx1 = max(1, n // 4)
    titik_contoh.append(idx1)
    # Titik 2: z ~ z_V0 (sekitar M_max)
    idx2 = int(np.argmin(np.abs(z_array - z_V0)))
    titik_contoh.append(idx2)
    # Titik 3: z ~ 3H/4
    idx3 = min(n - 2, 3 * n // 4)
    titik_contoh.append(idx3)

    for idx in titik_contoh:
        z_i = z_array[idx]
        langkah += [
            "",
            f"  --- z = {z_i:.3f} m ---",
            f"  Rumus  : V({z_i:.3f}) = Ra - integral(p_net, 0..{z_i:.3f})",
            f"  Nilai  : Ra           = {Ra:.4f} kN/m",
            f"           integral_p   = {integral_p[idx]:.4f} kN/m",
            f"  Hitung : V            = {Ra:.4f} - {integral_p[idx]:.4f}",
            f"  Hasil  : V({z_i:.3f}) = {V_arr[idx]:.4f} kN/m",
            "",
            f"  Rumus  : M({z_i:.3f}) = Ra*(z-z_angkur) - integral(p_net*(z-z'), 0..{z_i:.3f})",
            f"  Nilai  : Ra*(z-z_angkur) = {Ra:.4f} * ({z_i:.3f}-{z_angkur:.3f})",
            f"                           = {Ra*(z_i - z_angkur):.4f} kN.m/m",
            f"           integral_momen  = {integral_p_lengan[idx]:.4f} kN.m/m",
            f"  Hitung : M             = {Ra*(z_i-z_angkur):.4f} - {integral_p_lengan[idx]:.4f}",
            f"  Hasil  : M({z_i:.3f}) = {M_arr[idx]:.4f} kN.m/m",
        ]

    langkah += [
        "",
        _garis("-"),
        "  HASIL UTAMA",
        _garis("-"),
        f"  M_max   = {M_max:.4f} kN.m/m",
        f"  z_Mmax  = {z_Mmax:.4f} m dari permukaan",
        f"  z_V0    = {z_V0:.4f} m  (titik geser nol)",
        f"  V(z_V0) = {V0_interp:.4f} kN/m  (interpolasi linear)",
        "",
        _sub("  Standar", "NAVFAC DM-7.02, Ch. 3, Section 3.2.5, Hal. 3-14"),
        _sub("  ",        "USS Sheet Pile Design Manual (1975), Ch. 4, Hal. 4-2"),
        _sub("  ",        "Das, B.M., Principles of Foundation Engineering, 8th Ed., Ch. 9.5"),
        _garis("="),
    ]

    referensi = [
        "NAVFAC DM-7.02, Ch. 3, Section 3.2.5, Hal. 3-14",
        "USS Sheet Pile Design Manual (1975), Ch. 4, Hal. 4-2",
        "Das, B.M., Principles of Foundation Engineering, 8th Ed., Ch. 9.5",
        "SNI 8460:2017, Pasal 9.6.3",
    ]

    return _hasil_dict(
        nilai={
            "V_array"       : V_arr,
            "M_array"       : M_arr,
            "M_max"         : round(M_max,   4),
            "z_Mmax"        : round(z_Mmax,  4),
            "z_V0"          : round(z_V0,    4),
            "V0_interpolasi": round(V0_interp, 6),
            "z_array"       : z_array,
            "tekanan_array" : tekanan_array,
            "integral_p"    : integral_p,
        },
        langkah   = langkah,
        referensi = referensi,
        satuan    = "kN/m (V), kN.m/m (M)",
        status    = "",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. GAYA DALAM KANTILEVER (FIXED EARTH SUPPORT)
# ─────────────────────────────────────────────────────────────────────────────

def hitung_gaya_dalam_kantilever(
    z_array       : np.ndarray,
    tekanan_array : np.ndarray,
    H             : float,
    p_aktif       : np.ndarray | None = None,
    p_pasif       : np.ndarray | None = None,
    u_array       : np.ndarray | None = None,
    interval_log  : float = 0.5,
) -> dict:
    """
    Hitung diagram gaya geser V(z) dan momen lentur M(z) untuk turap
    kantilever (Fixed Earth Support Method).

    Turap kantilever tidak memiliki angkur → Ra = 0.
    Integrasi dilakukan dari BAWAH ke ATAS (ujung bebas di atas).

    Rumus:
        V(z) = integral[ p_net(z') dz',  z'=z s/d z_ujung ]
        M(z) = integral[ p_net(z') * (z' - z) dz',  z'=z s/d z_ujung ]

    Syarat batas ujung bawah:
        V(z_ujung) = 0  (ujung bebas, tidak ada gaya luar)
        M(z_ujung) = 0  (ujung bebas, tidak ada momen luar)

    Referensi:
        [R2] NAVFAC DM-7.02, Ch. 3, Section 3.1.3, Hal. 3-8
        [R4] USS Sheet Pile Design Manual (1975), Ch. 3, Hal. 3-20
        [R5] Das, B.M., 8th Ed., Ch. 9.3

    Parameter:
        z_array       : array kedalaman [m]
        tekanan_array : array tekanan neto p_net [kPa]
        H             : tinggi galian [m] — untuk anotasi
        p_aktif/pasif : opsional, untuk tabel
        interval_log  : interval log [m]

    Return:
        dict standar; "nilai" sama seperti hitung_gaya_dalam()
    """
    if len(z_array) < 2:
        raise ValueError("z_array minimal 2 titik.")
    if len(z_array) != len(tekanan_array):
        raise ValueError("Panjang z_array dan tekanan_array harus sama.")

    n = len(z_array)

    V_arr = np.zeros(n)
    M_arr = np.zeros(n)

    # Integrasi dari bawah (indeks n-1) ke atas (indeks 0)
    # Kondisi batas: V[n-1]=0, M[n-1]=0
    for i in range(n - 2, -1, -1):
        dz_i = z_array[i + 1] - z_array[i]

        # V(i) = V(i+1) + trapesium tekanan dari i ke i+1
        V_arr[i] = V_arr[i + 1] + 0.5 * (tekanan_array[i] + tekanan_array[i + 1]) * dz_i

        # M(i) = M(i+1) + V(i+1)*dz + 1/2 * (p[i]+p[i+1])/2 * dz^2
        # (integral p*(z'-z) dari i ke i+1)
        M_arr[i] = (
            M_arr[i + 1]
            + V_arr[i + 1] * dz_i
            + 0.5 * (tekanan_array[i] + tekanan_array[i + 1]) * dz_i * dz_i / 2
        )

    # Cari M_max dan V=0
    hasil_mmax = cari_M_max(z_array, V_arr, M_arr)
    M_max    = hasil_mmax["nilai"]["M_max"]
    z_Mmax   = hasil_mmax["nilai"]["z_Mmax"]
    z_V0     = hasil_mmax["nilai"]["z_V0"]
    V0_interp = hasil_mmax["nilai"]["V0_interpolasi"]

    dz = z_array[1] - z_array[0]

    # Tabel
    ada_aktif = p_aktif is not None
    ada_pasif = p_pasif is not None

    lebar = {"z": 7, "pa": 14, "pp": 14, "pnet": 14, "V": 12, "M": 14}

    header_tabel = f"  {'z(m)':>{lebar['z']}} "
    if ada_aktif:
        header_tabel += f"{'Pa(kPa)':>{lebar['pa']}} "
    if ada_pasif:
        header_tabel += f"{'Pp(kPa)':>{lebar['pp']}} "
    header_tabel += (
        f"{'Pnet(kPa)':>{lebar['pnet']}} "
        f"{'V(kN/m)':>{lebar['V']}} "
        f"{'M(kN.m/m)':>{lebar['M']}}"
    )
    garis_tabel = "  " + "-" * (len(header_tabel) - 2)

    langkah: list[str] = [
        *_header("Gaya Dalam Turap Kantilever — Diagram V dan M (Fixed Earth)"),
        "",
        "  Metode: Integrasi dari ujung bawah ke atas (syarat batas ujung bebas)",
        "",
        "  Rumus gaya geser (dari bawah):",
        "    V(z) = integral[ p_net(z') dz',  z'=z s/d z_ujung ]",
        "",
        "  Rumus momen lentur (dari bawah):",
        "    M(z) = integral[ p_net(z') * (z' - z) dz',  z'=z s/d z_ujung ]",
        "",
        "  Syarat batas ujung bawah:",
        "    V(z_ujung) = 0  (tidak ada gaya luar di ujung)",
        "    M(z_ujung) = 0  (tidak ada momen luar di ujung)",
        "",
        "  Data input:",
        _sub("  H",       f"{H:.2f} m  (tinggi galian)"),
        _sub("  z_min",   f"{z_array[0]:.3f} m"),
        _sub("  z_max",   f"{z_array[-1]:.3f} m"),
        _sub("  n titik", f"{n}"),
        "",
        _garis("-"),
        "  TABEL RINGKASAN GAYA DALAM",
        _garis("-"),
        header_tabel,
        garis_tabel,
    ]

    z_prev_log = -999.0
    for i, z in enumerate(z_array):
        ket_list = []
        if abs(z) < 1e-6:
            ket_list.append("permukaan")
        if abs(z - H) < abs(dz):
            ket_list.append("dasar galian")
        if abs(z - z_V0) < abs(dz) * 1.5:
            ket_list.append("V=0")
        if abs(z - z_Mmax) < abs(dz) * 1.5:
            ket_list.append("M_MAX")
        if i == n - 1:
            ket_list.append("ujung")
        ket = " [" + ", ".join(ket_list) + "]" if ket_list else ""

        harus_log = (z - z_prev_log >= interval_log - 1e-9) or bool(ket_list)
        if harus_log:
            baris = f"  {z:>{lebar['z']}.2f} "
            if ada_aktif:
                baris += f"{p_aktif[i]:>{lebar['pa']}.3f} "
            if ada_pasif:
                baris += f"{p_pasif[i]:>{lebar['pp']}.3f} "
            baris += (
                f"{tekanan_array[i]:>{lebar['pnet']}.3f} "
                f"{V_arr[i]:>{lebar['V']}.3f} "
                f"{M_arr[i]:>{lebar['M']}.3f}"
                f"{ket}"
            )
            langkah.append(baris)
            z_prev_log = z

    langkah += [
        garis_tabel,
        "",
        _garis("-"),
        "  CONTOH PERHITUNGAN DETAIL (3 TITIK)",
        _garis("-"),
    ]

    for idx in [n - 2, max(1, n // 2), 1]:
        z_i = z_array[idx]
        # Hitung gaya dan momen di titik ini secara eksplisit untuk log
        V_i = V_arr[idx]
        M_i = M_arr[idx]
        integ_seg = float(np.trapezoid(tekanan_array[idx:], z_array[idx:]))
        langkah += [
            "",
            f"  --- z = {z_i:.3f} m ---",
            f"  Rumus  : V({z_i:.3f}) = integral(p_net, {z_i:.3f}..{z_array[-1]:.3f})",
            f"           integral     = {integ_seg:.4f} kN/m",
            f"  Hasil  : V({z_i:.3f}) = {V_i:.4f} kN/m",
            f"  Hasil  : M({z_i:.3f}) = {M_i:.4f} kN.m/m",
        ]

    langkah += [
        "",
        _garis("-"),
        "  HASIL UTAMA",
        _garis("-"),
        f"  M_max  = {M_max:.4f} kN.m/m",
        f"  z_Mmax = {z_Mmax:.4f} m dari permukaan",
        f"  z_V0   = {z_V0:.4f} m  (titik geser nol)",
        "",
        _sub("  Standar", "NAVFAC DM-7.02, Ch. 3, Section 3.1.3, Hal. 3-8"),
        _sub("  ",        "USS Sheet Pile Design Manual (1975), Ch. 3, Hal. 3-20"),
        _sub("  ",        "Das, B.M., 8th Ed., Ch. 9.3"),
        _garis("="),
    ]

    referensi = [
        "NAVFAC DM-7.02, Ch. 3, Section 3.1.3, Hal. 3-8",
        "USS Sheet Pile Design Manual (1975), Ch. 3, Hal. 3-20",
        "Das, B.M., Principles of Foundation Engineering, 8th Ed., Ch. 9.3",
        "SNI 8460:2017, Pasal 9.6.2",
    ]

    return _hasil_dict(
        nilai={
            "V_array"       : V_arr,
            "M_array"       : M_arr,
            "M_max"         : round(M_max,   4),
            "z_Mmax"        : round(z_Mmax,  4),
            "z_V0"          : round(z_V0,    4),
            "V0_interpolasi": round(V0_interp, 6),
            "z_array"       : z_array,
            "tekanan_array" : tekanan_array,
        },
        langkah   = langkah,
        referensi = referensi,
        satuan    = "kN/m (V), kN.m/m (M)",
        status    = "",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. CARI M_MAX DAN TITIK V = 0
# ─────────────────────────────────────────────────────────────────────────────

def cari_M_max(
    z_array : np.ndarray,
    V_array : np.ndarray,
    M_array : np.ndarray,
) -> dict:
    """
    Cari momen lentur maksimum (M_max) dan lokasi titik geser nol (V=0).

    Prinsip:
        M_max terjadi di titik z di mana V berganti tanda (V = 0).
        Lokasi z_V0 diinterpolasi secara linear antara dua titik yang mengapit.

    Referensi:
        [R4] USS Sheet Pile Design Manual (1975), Ch. 4, Hal. 4-2
        [R5] Das, B.M., 8th Ed., Ch. 9.5

    Parameter:
        z_array : array kedalaman [m]
        V_array : array gaya geser [kN/m]
        M_array : array momen lentur [kN.m/m]

    Return:
        dict standar; "nilai" berisi:
            {M_max, z_Mmax, z_V0, V0_interpolasi, idx_Mmax}
    """
    n = len(z_array)

    # Cari semua perpindahan tanda V
    z_V0_candidates   = []
    V0_interp_cands   = []
    M_interp_cands    = []

    for i in range(n - 1):
        if V_array[i] * V_array[i + 1] <= 0:
            # Interpolasi linear untuk mendapat z tepat V=0
            dV  = V_array[i + 1] - V_array[i]
            dz  = z_array[i + 1] - z_array[i]
            if abs(dV) > 1e-12:
                frac = -V_array[i] / dV
            else:
                frac = 0.0
            z_V0_i   = z_array[i] + frac * dz
            # Interpolasi M pada z_V0
            M_V0_i   = M_array[i] + frac * (M_array[i + 1] - M_array[i])
            z_V0_candidates.append(z_V0_i)
            V0_interp_cands.append(0.0)   # V = 0 di titik ini (per definisi)
            M_interp_cands.append(M_V0_i)

    if z_V0_candidates:
        # Pilih titik dengan |M| terbesar di antara semua V=0
        idx_max_M = int(np.argmax([abs(m) for m in M_interp_cands]))
        z_V0      = z_V0_candidates[idx_max_M]
        M_max_interp = M_interp_cands[idx_max_M]
    else:
        # Tidak ada perubahan tanda V → M_max di ujung atau tengah
        z_V0         = float(z_array[0])
        M_max_interp = 0.0

    # M_max dari array (nilai absolut terbesar)
    idx_Mmax  = int(np.argmax(np.abs(M_array)))
    M_max_arr = float(M_array[idx_Mmax])
    z_Mmax    = float(z_array[idx_Mmax])

    # Gunakan nilai interpolasi jika lebih besar
    if abs(M_max_interp) > abs(M_max_arr):
        M_max  = M_max_interp
        z_Mmax = z_V0
    else:
        M_max  = M_max_arr

    langkah: list[str] = [
        *_header("Momen Maksimum dan Titik Geser Nol"),
        "",
        "  M_max terjadi di mana gaya geser V berganti tanda (V = 0).",
        "  Lokasi z_V0 diinterpolasi secara linear antara dua titik.",
        "",
        f"  Jumlah titik V=0 ditemukan : {len(z_V0_candidates)}",
    ]

    for k, (zv, mv) in enumerate(zip(z_V0_candidates, M_interp_cands)):
        langkah.append(f"    Titik {k+1}: z_V0 = {zv:.4f} m,  M(z_V0) = {mv:.4f} kN.m/m")

    langkah += [
        "",
        "  Interpolasi linear:",
        "  Rumus  : z_V0 = z_i + (V_i / (V_i - V_{i+1})) * dz",
        "           M_V0 = M_i + frac * (M_{i+1} - M_i)",
        "",
        f"  z_V0   = {z_V0:.4f} m",
        f"  M_max  = {M_max:.4f} kN.m/m  (|M| terbesar)",
        f"  z_Mmax = {z_Mmax:.4f} m",
        "",
        _sub("  Standar", "USS Sheet Pile Design Manual (1975), Ch. 4, Hal. 4-2"),
        _sub("  ",        "Das, B.M., 8th Ed., Ch. 9.5"),
        _garis(),
    ]

    referensi = [
        "USS Sheet Pile Design Manual (1975), Ch. 4, Hal. 4-2",
        "Das, B.M., Principles of Foundation Engineering, 8th Ed., Ch. 9.5",
    ]

    return _hasil_dict(
        nilai={
            "M_max"         : round(abs(M_max), 4),
            "z_Mmax"        : round(z_Mmax,     4),
            "z_V0"          : round(z_V0,       4),
            "V0_interpolasi": 0.0,
            "idx_Mmax"      : idx_Mmax,
        },
        langkah   = langkah,
        referensi = referensi,
        satuan    = "kN.m/m (M_max), m (z)",
        status    = "",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. PLOT DIAGRAM V DAN M
# ─────────────────────────────────────────────────────────────────────────────

def plot_V_M_diagram(
    z_array   : np.ndarray,
    V_array   : np.ndarray,
    M_array   : np.ndarray,
    M_max     : float,
    z_Mmax    : float,
    H         : float,
    z_angkur  : float | None = None,
    z_V0      : float | None = None,
    D_design  : float | None = None,
    tekanan_neto: np.ndarray | None = None,
    judul     : str = "Diagram Gaya Dalam Turap",
) -> plt.Figure:
    """
    Plot diagram tekanan neto, gaya geser (V), dan momen lentur (M).

    Layout: 3 subplot horizontal
        1. Tekanan neto (kPa)
        2. Gaya geser V (kN/m)
        3. Momen lentur M (kN.m/m)

    Fitur diagram:
        - Sumbu z ke bawah (kedalaman)
        - Garis horizontal: dasar galian, angkur (jika ada), MAT
        - Marker dan anotasi M_max
        - Arsir area positif vs negatif berbeda warna
        - Tandai titik V=0

    Referensi:
        [R4] USS Sheet Pile Design Manual (1975), Ch. 4, Fig. 4-2

    Parameter:
        z_array      : array kedalaman [m]
        V_array      : array gaya geser [kN/m]
        M_array      : array momen lentur [kN.m/m]
        M_max        : nilai M_max [kN.m/m]
        z_Mmax       : kedalaman M_max [m]
        H            : tinggi galian [m]
        z_angkur     : kedalaman angkur [m] (None jika kantilever)
        z_V0         : kedalaman V=0 [m] (None = dicari otomatis)
        D_design     : kedalaman penetrasi desain [m] (untuk anotasi)
        tekanan_neto : array tekanan neto (opsional, subplot kiri)
        judul        : judul figure

    Return:
        matplotlib.Figure
    """
    # ── Konstanta warna ───────────────────────────────────────────────────────
    WARNA_V_POS   = "#C0392B"    # merah — geser positif
    WARNA_V_NEG   = "#2E86C1"    # biru — geser negatif
    WARNA_M_POS   = "#D35400"    # oranye — momen positif
    WARNA_M_NEG   = "#1A5276"    # biru tua — momen negatif
    WARNA_GALIAN  = "#555555"    # abu-abu — batas galian
    WARNA_ANGKUR  = "#1ABC9C"    # hijau tosca — angkur
    WARNA_MMAX    = "#8E44AD"    # ungu — M_max
    WARNA_PNET_P  = "#E8A87C"    # oranye muda — tekanan aktif
    WARNA_PNET_N  = "#85C1E9"    # biru muda — tekanan pasif

    z_max = float(z_array[-1])

    # Jumlah subplot: 2 (tanpa tekanan) atau 3 (dengan tekanan)
    ada_tekanan = tekanan_neto is not None
    n_subplot   = 3 if ada_tekanan else 2
    lebar_rel   = [1.0, 1.2, 1.4] if ada_tekanan else [1.2, 1.4]

    fig, axes = plt.subplots(
        1, n_subplot,
        figsize=(5 * n_subplot + 2, 10),
        sharey=True,
        gridspec_kw={"width_ratios": lebar_rel},
        layout="constrained",
    )
    fig.suptitle(judul, fontsize=12, fontweight="bold")

    ax_idx = 0

    # ── Helper: setup sumbu ───────────────────────────────────────────────────
    def _setup_ax(ax, label_x: str):
        ax.set_xlabel(label_x, fontsize=9)
        ax.invert_yaxis()
        ax.set_ylim(z_max + 0.2, -0.2)
        ax.axvline(0, color="black", linewidth=0.9, linestyle="-")
        ax.grid(axis="both", linestyle=":", linewidth=0.4, alpha=0.6)
        ax.tick_params(labelsize=8)

        # Garis dasar galian
        ax.axhline(H, color=WARNA_GALIAN, linewidth=1.2, linestyle="--",
                   label=f"Dasar galian H={H:.1f}m")

        # Garis angkur
        if z_angkur is not None:
            ax.axhline(z_angkur, color=WARNA_ANGKUR, linewidth=1.2,
                       linestyle="-.", label=f"Angkur z={z_angkur:.2f}m")

    # ── Subplot 1: Tekanan neto ───────────────────────────────────────────────
    if ada_tekanan:
        ax1 = axes[ax_idx]; ax_idx += 1
        nol = np.zeros_like(tekanan_neto)
        ax1.fill_betweenx(z_array, nol, tekanan_neto,
                          where=(tekanan_neto >= 0),
                          color=WARNA_PNET_P, alpha=0.35, label="Aktif > Pasif")
        ax1.fill_betweenx(z_array, nol, tekanan_neto,
                          where=(tekanan_neto < 0),
                          color=WARNA_PNET_N, alpha=0.35, label="Pasif > Aktif")
        ax1.plot(tekanan_neto, z_array, color="#784212", linewidth=1.6)
        _setup_ax(ax1, "Tekanan neto (kPa)")
        ax1.set_ylabel("Kedalaman z (m)", fontsize=9)
        ax1.set_title("Tekanan Neto\n(Pa - Pp)", fontsize=9, fontweight="bold")
        ax1.legend(fontsize=7, loc="lower right")

    # ── Subplot 2: Gaya geser V ───────────────────────────────────────────────
    ax2 = axes[ax_idx]; ax_idx += 1
    nol_V = np.zeros_like(V_array)
    ax2.fill_betweenx(z_array, nol_V, V_array,
                      where=(V_array >= 0),
                      color=WARNA_V_POS, alpha=0.25, label="V positif")
    ax2.fill_betweenx(z_array, nol_V, V_array,
                      where=(V_array < 0),
                      color=WARNA_V_NEG, alpha=0.25, label="V negatif")
    ax2.plot(V_array, z_array, color=WARNA_V_POS, linewidth=1.8)
    _setup_ax(ax2, "Gaya geser V (kN/m)")
    if not ada_tekanan:
        ax2.set_ylabel("Kedalaman z (m)", fontsize=9)
    ax2.set_title("Diagram Gaya\nGeser V", fontsize=9, fontweight="bold")

    # Tandai V=0
    if z_V0 is not None:
        ax2.axhline(z_V0, color=WARNA_MMAX, linewidth=0.9, linestyle=":",
                    label=f"V=0  (z={z_V0:.2f}m)")
        ax2.scatter([0], [z_V0], color=WARNA_MMAX, zorder=5, s=50, marker="D")
        ax2.annotate(f"V=0\nz={z_V0:.2f}m",
                     xy=(0, z_V0),
                     xytext=(max(V_array) * 0.35 + 1e-3, z_V0 + 0.15),
                     fontsize=7.5,
                     color=WARNA_MMAX,
                     arrowprops=dict(arrowstyle="->", lw=0.7, color=WARNA_MMAX))

    ax2.legend(fontsize=7, loc="lower right")

    # ── Subplot 3: Momen lentur M ─────────────────────────────────────────────
    ax3 = axes[ax_idx]
    nol_M = np.zeros_like(M_array)
    ax3.fill_betweenx(z_array, nol_M, M_array,
                      where=(M_array >= 0),
                      color=WARNA_M_POS, alpha=0.25, label="M positif")
    ax3.fill_betweenx(z_array, nol_M, M_array,
                      where=(M_array < 0),
                      color=WARNA_M_NEG, alpha=0.25, label="M negatif")
    ax3.plot(M_array, z_array, color=WARNA_M_POS, linewidth=1.8)
    _setup_ax(ax3, "Momen lentur M (kN.m/m)")
    ax3.set_title("Diagram Momen\nLentur M", fontsize=9, fontweight="bold")

    # Tandai M_max
    idx_mm  = int(np.argmin(np.abs(z_array - z_Mmax)))
    M_at_mm = float(M_array[idx_mm])
    ax3.scatter([M_at_mm], [z_Mmax], color=WARNA_MMAX, zorder=6, s=80, marker="*")

    # Anotasi M_max
    x_annt = M_at_mm * 0.5 if abs(M_at_mm) > 1 else M_at_mm + 1.0
    ax3.annotate(
        f"M_max\n={M_max:.1f} kN.m/m\nz={z_Mmax:.2f}m",
        xy=(M_at_mm, z_Mmax),
        xytext=(x_annt, z_Mmax + 0.4),
        fontsize=7.5,
        color=WARNA_MMAX,
        fontweight="bold",
        arrowprops=dict(arrowstyle="->", lw=0.7, color=WARNA_MMAX),
    )

    # Garis putus-putus vertikal pada M_max (horizontal di z_Mmax)
    ax3.axhline(z_Mmax, color=WARNA_MMAX, linewidth=0.8, linestyle=":")

    ax3.legend(fontsize=7, loc="lower right")

    # ── Legend bersama di bawah ───────────────────────────────────────────────
    legend_items = [
        Line2D([0], [0], color=WARNA_GALIAN, lw=1.2, ls="--",
               label=f"Dasar galian  H={H:.1f} m"),
        Line2D([0], [0], color=WARNA_MMAX,   lw=0.9, ls=":",
               label=f"M_max={M_max:.1f} kN.m/m  z={z_Mmax:.2f} m"),
    ]
    if z_angkur is not None:
        legend_items.append(
            Line2D([0], [0], color=WARNA_ANGKUR, lw=1.2, ls="-.",
                   label=f"Angkur  z={z_angkur:.2f} m")
        )
    if D_design is not None:
        legend_items.append(
            Line2D([0], [0], color="#7D6608", lw=1.0, ls="-",
                   label=f"D_design={D_design:.2f} m")
        )

    fig.legend(
        handles=legend_items,
        loc="outside lower center",
        ncol=2,
        fontsize=8,
        framealpha=0.85,
    )

    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 5. FUNGSI TERPADU — HITUNG + PLOT DARI HASIL TAHAP 2
# ─────────────────────────────────────────────────────────────────────────────

def analisis_gaya_dalam_lengkap(
    hasil_stabilitas : dict,
    tipe_turap       : str = "free_earth",
    interval_log     : float = 0.5,
    judul_plot       : str  = "Diagram Gaya Dalam Turap",
) -> dict:
    """
    Fungsi terpadu: ambil hasil dari Tahap 2 (stability.py) lalu hitung
    dan plot diagram gaya dalam secara otomatis.

    Tipe turap:
        "free_earth"  — turap dengan angkur (menggunakan Ra dan z_angkur)
        "kantilever"  — turap kantilever (Ra = 0)

    Parameter:
        hasil_stabilitas : dict hasil dari free_earth_support() atau
                          fixed_earth_support_cantilever()
        tipe_turap       : "free_earth" atau "kantilever"
        interval_log     : interval z untuk log tabel [m]
        judul_plot       : judul gambar

    Return:
        dict standar; "nilai" berisi:
            {V_array, M_array, M_max, z_Mmax, z_V0,
             z_array, tekanan_neto, fig}
    """
    nilai = hasil_stabilitas.get("nilai", {})

    # Ambil array dari hasil stabilitas
    z_arr  = nilai.get("z_array")
    p_neto = nilai.get("p_neto")
    p_aktif= nilai.get("p_aktif", None)
    p_pasif= nilai.get("p_pasif", None)
    u_arr  = nilai.get("u_array", None)

    if z_arr is None or p_neto is None:
        raise ValueError(
            "hasil_stabilitas tidak memiliki 'z_array' atau 'p_neto'. "
            "Pastikan menggunakan hasil dari stability.py."
        )

    H        = nilai.get("D_min", 0.0)   # placeholder; H diambil dari p_pasif == 0
    D_design = nilai.get("D_design")

    # Perkirakan H dari di mana pasif mulai > 0
    if p_pasif is not None:
        idx_pasif = np.argmax(p_pasif > 0.01)
        H_est     = float(z_arr[idx_pasif]) if idx_pasif > 0 else float(z_arr[0])
    else:
        H_est = float(z_arr[len(z_arr) // 2])

    if tipe_turap == "free_earth":
        Ra       = float(nilai.get("Ra", 0.0))
        z_angkur = float(nilai.get("z_angkur", 0.0))

        # z_angkur mungkin tidak tersimpan — fallback ke 0 (permukaan)
        if "z_angkur" not in nilai:
            z_angkur = 0.0

        hasil_gd = hitung_gaya_dalam(
            z_array       = z_arr,
            tekanan_array = p_neto,
            Ra            = Ra,
            z_angkur      = z_angkur,
            p_aktif       = p_aktif,
            p_pasif       = p_pasif,
            u_array       = u_arr,
            interval_log  = interval_log,
        )
        z_angkur_plot = z_angkur

    else:  # kantilever
        hasil_gd = hitung_gaya_dalam_kantilever(
            z_array       = z_arr,
            tekanan_array = p_neto,
            H             = H_est,
            p_aktif       = p_aktif,
            p_pasif       = p_pasif,
            u_array       = u_arr,
            interval_log  = interval_log,
        )
        z_angkur_plot = None

    V_arr   = hasil_gd["nilai"]["V_array"]
    M_arr   = hasil_gd["nilai"]["M_array"]
    M_max   = hasil_gd["nilai"]["M_max"]
    z_Mmax  = hasil_gd["nilai"]["z_Mmax"]
    z_V0    = hasil_gd["nilai"]["z_V0"]

    # Plot
    fig = plot_V_M_diagram(
        z_array      = z_arr,
        V_array      = V_arr,
        M_array      = M_arr,
        M_max        = M_max,
        z_Mmax       = z_Mmax,
        H            = H_est,
        z_angkur     = z_angkur_plot,
        z_V0         = z_V0,
        D_design     = D_design,
        tekanan_neto = p_neto,
        judul        = judul_plot,
    )

    return _hasil_dict(
        nilai={
            **hasil_gd["nilai"],
            "fig"         : fig,
            "H_estimasi"  : H_est,
        },
        langkah   = hasil_gd["langkah"],
        referensi = hasil_gd["referensi"],
        satuan    = "kN/m (V), kN.m/m (M)",
        status    = "",
    )


# ─────────────────────────────────────────────────────────────────────────────
# CONTOH PENGGUNAAN — jalankan: python internal_forces.py
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/home/claude")

    from earth_pressure import hitung_distribusi_tekanan, GAMMA_W_DEFAULT
    from stability import free_earth_support, fixed_earth_support_cantilever

    print("\n" + "=" * 64)
    print("  CONTOH PERHITUNGAN GAYA DALAM TURAP")
    print("  Data: lempung berlapis, khas Jabodetabek")
    print("=" * 64 + "\n")

    # ── Data tanah ─────────────────────────────────────────────────────────
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
    Z_ANGKUR = 0.5    # m dari permukaan

    # ── (A) Turap dengan angkur — Free Earth Support ───────────────────────
    print("=" * 64)
    print("  KASUS A: TURAP DENGAN ANGKUR (FREE EARTH SUPPORT)")
    print("=" * 64)

    res_fes = free_earth_support(
        H             = H,
        lapisan_tanah = LAPISAN,
        surcharge     = SURCHARGE,
        muka_air      = MAT,
        tinggi_angkur = Z_ANGKUR,
        dz            = 0.1,
    )

    Ra       = res_fes["nilai"]["Ra"]
    D_design = res_fes["nilai"]["D_design"]

    print(f"  Ra       = {Ra:.3f} kN/m")
    print(f"  D_design = {D_design:.3f} m")

    # Hitung gaya dalam
    z_arr  = res_fes["nilai"]["z_array"]
    p_neto = res_fes["nilai"]["p_neto"]
    p_aktif= res_fes["nilai"]["p_aktif"]
    p_pasif= res_fes["nilai"]["p_pasif"]

    res_gd_fes = hitung_gaya_dalam(
        z_array       = z_arr,
        tekanan_array = p_neto,
        Ra            = Ra,
        z_angkur      = Z_ANGKUR,
        p_aktif       = p_aktif,
        p_pasif       = p_pasif,
        interval_log  = 0.5,
    )
    print(format_langkah(res_gd_fes["langkah"]))

    # Plot
    fig_fes = plot_V_M_diagram(
        z_array      = z_arr,
        V_array      = res_gd_fes["nilai"]["V_array"],
        M_array      = res_gd_fes["nilai"]["M_array"],
        M_max        = res_gd_fes["nilai"]["M_max"],
        z_Mmax       = res_gd_fes["nilai"]["z_Mmax"],
        H            = H,
        z_angkur     = Z_ANGKUR,
        z_V0         = res_gd_fes["nilai"]["z_V0"],
        D_design     = D_design,
        tekanan_neto = p_neto,
        judul        = "Diagram V & M — Turap Angkur (Free Earth Support)",
    )
    fig_fes.savefig("/home/claude/diagram_V_M_angkur.png", dpi=150, bbox_inches="tight")
    print("  Plot tersimpan: diagram_V_M_angkur.png")

    # ── (B) Turap kantilever — Fixed Earth Support ────────────────────────
    print("\n" + "=" * 64)
    print("  KASUS B: TURAP KANTILEVER (FIXED EARTH SUPPORT)")
    print("=" * 64)

    res_fix = fixed_earth_support_cantilever(
        H             = H,
        lapisan_tanah = LAPISAN,
        surcharge     = SURCHARGE,
        muka_air      = MAT,
        dz            = 0.1,
    )

    D_design_fix = res_fix["nilai"]["D_design"]
    print(f"  D_design = {D_design_fix:.3f} m")

    z_arr_fix  = res_fix["nilai"]["z_array"]
    p_neto_fix = res_fix["nilai"]["p_neto"]
    p_aktif_fix= res_fix["nilai"]["p_aktif"]
    p_pasif_fix= res_fix["nilai"]["p_pasif"]

    res_gd_fix = hitung_gaya_dalam_kantilever(
        z_array       = z_arr_fix,
        tekanan_array = p_neto_fix,
        H             = H,
        p_aktif       = p_aktif_fix,
        p_pasif       = p_pasif_fix,
        interval_log  = 0.5,
    )
    print(format_langkah(res_gd_fix["langkah"]))

    # Plot kantilever
    fig_fix = plot_V_M_diagram(
        z_array      = z_arr_fix,
        V_array      = res_gd_fix["nilai"]["V_array"],
        M_array      = res_gd_fix["nilai"]["M_array"],
        M_max        = res_gd_fix["nilai"]["M_max"],
        z_Mmax       = res_gd_fix["nilai"]["z_Mmax"],
        H            = H,
        z_angkur     = None,
        z_V0         = res_gd_fix["nilai"]["z_V0"],
        D_design     = D_design_fix,
        tekanan_neto = p_neto_fix,
        judul        = "Diagram V & M — Turap Kantilever (Fixed Earth Support)",
    )
    fig_fix.savefig("/home/claude/diagram_V_M_kantilever.png", dpi=150, bbox_inches="tight")
    print("  Plot tersimpan: diagram_V_M_kantilever.png")

    # ── Ringkasan akhir ───────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  RINGKASAN GAYA DALAM")
    print("=" * 64)
    print(f"\n  KASUS A — Free Earth Support (turap dengan angkur):")
    print(f"    Ra       = {Ra:.3f} kN/m")
    print(f"    D_design = {D_design:.3f} m")
    print(f"    M_max    = {res_gd_fes['nilai']['M_max']:.3f} kN.m/m  "
          f"(z = {res_gd_fes['nilai']['z_Mmax']:.3f} m)")
    print(f"    z_V0     = {res_gd_fes['nilai']['z_V0']:.3f} m")

    print(f"\n  KASUS B — Fixed Earth Support (kantilever):")
    print(f"    D_design = {D_design_fix:.3f} m")
    print(f"    M_max    = {res_gd_fix['nilai']['M_max']:.3f} kN.m/m  "
          f"(z = {res_gd_fix['nilai']['z_Mmax']:.3f} m)")
    print(f"    z_V0     = {res_gd_fix['nilai']['z_V0']:.3f} m")

    print("\nSelesai.")
