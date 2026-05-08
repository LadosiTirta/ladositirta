# calculations/soil_profile.py
# Pengolahan profil tanah: interpolasi SPT, tegangan efektif, klasifikasi lapisan
# Acuan: SNI 8460:2017, Meyerhof (1976), Tomlinson (2008)

import numpy as np
import pandas as pd
from utils.input_handler import KOLOM_TANAH

GAMMA_AIR = 9.81  # kN/m³


def klasifikasi_tanah(jenis: str) -> str:
    """
    Mengklasifikasikan jenis tanah menjadi kategori dasar:
    'lempung', 'pasir', atau 'lanau'
    """
    jenis_lower = jenis.lower()
    if any(k in jenis_lower for k in ["lempung", "clay", "kohesif"]):
        return "lempung"
    elif any(k in jenis_lower for k in ["pasir", "sand", "kerikil", "gravel"]):
        return "pasir"
    else:
        return "lanau"


def hitung_profil_tanah(df_tanah: pd.DataFrame, muka_air: float) -> list[dict]:
    """
    Memproses DataFrame data tanah menjadi list dict per lapisan dengan:
    - Tebal lapisan
    - Tegangan total dan efektif di tengah lapisan
    - SPT-N rata-rata
    - Klasifikasi tanah

    Parameter:
        df_tanah  : DataFrame data tanah hasil input_handler
        muka_air  : kedalaman muka air tanah dari permukaan (m)

    Mengembalikan list dict, satu dict per lapisan:
        {z_atas, z_bawah, z_tengah, tebal, jenis, kategori,
         spt, cu, phi, gamma, sigma_v, sigma_v_eff, u}
    """
    lapisan = []
    sigma_v_kum = 0.0  # tegangan total kumulatif (kPa)

    for _, baris in df_tanah.iterrows():
        z_atas  = float(baris[KOLOM_TANAH["z_atas"]])
        z_bawah = float(baris[KOLOM_TANAH["z_bawah"]])
        tebal   = z_bawah - z_atas
        z_tengah= (z_atas + z_bawah) / 2.0

        gamma   = float(baris[KOLOM_TANAH["gamma"]])
        spt     = float(baris[KOLOM_TANAH["spt"]])
        cu      = float(baris[KOLOM_TANAH["cu"]])
        phi_deg = float(baris[KOLOM_TANAH["phi"]])
        jenis   = str(baris[KOLOM_TANAH["jenis"]])

        # Tegangan total di tengah lapisan
        sigma_v_atas    = sigma_v_kum
        sigma_v_tengah  = sigma_v_kum + gamma * (tebal / 2.0)
        sigma_v_bawah   = sigma_v_kum + gamma * tebal

        # Tekanan air pori di tengah lapisan
        if z_tengah > muka_air:
            u = GAMMA_AIR * (z_tengah - muka_air)
        else:
            u = 0.0

        sigma_v_eff = max(sigma_v_tengah - u, 0.0)

        # Akumulasi tegangan total ke bawah lapisan
        sigma_v_kum += gamma * tebal

        # Koreksi SPT untuk kedalaman (Liao & Whitman 1986) — opsional
        # Digunakan untuk referensi, perhitungan utama pakai SPT terkoreksi
        cn = min(np.sqrt(100.0 / max(sigma_v_tengah, 10.0)), 2.0)
        spt60 = spt * cn  # SPT(N1)60 — koreksi overburden + efisiensi 60%

        lapisan.append({
            "z_atas":       z_atas,
            "z_bawah":      z_bawah,
            "z_tengah":     z_tengah,
            "tebal":        tebal,
            "jenis":        jenis,
            "kategori":     klasifikasi_tanah(jenis),
            "spt":          spt,
            "spt60":        round(spt60, 1),
            "cu":           cu,
            "phi_deg":      phi_deg,
            "phi_rad":      np.radians(phi_deg),
            "gamma":        gamma,
            "sigma_v":      round(sigma_v_tengah, 2),
            "sigma_v_eff":  round(sigma_v_eff, 2),
            "u":            round(u, 2),
        })

    return lapisan


def spt_rata_ujung(lapisan: list[dict], z_ujung: float, D: float) -> float:
    """
    Menghitung SPT-N rata-rata di zona ujung tiang.
    Zona: 4D di atas ujung hingga 1D di bawah ujung (Meyerhof 1976).

    Parameter:
        lapisan : list dict profil tanah dari hitung_profil_tanah()
        z_ujung : kedalaman ujung tiang (m)
        D       : diameter/lebar tiang (m)

    Mengembalikan SPT-N rata-rata (float)
    """
    z_atas_zona  = z_ujung - 4.0 * D
    z_bawah_zona = z_ujung + 1.0 * D

    nilai_spt = []
    bobot     = []

    for lap in lapisan:
        # Cek irisan antara lapisan dan zona ujung tiang
        z_irisan_atas  = max(lap["z_atas"],  z_atas_zona)
        z_irisan_bawah = min(lap["z_bawah"], z_bawah_zona)
        tebal_irisan   = z_irisan_bawah - z_irisan_atas

        if tebal_irisan > 0:
            nilai_spt.append(lap["spt"])
            bobot.append(tebal_irisan)

    if not nilai_spt:
        # Fallback: ambil lapisan terdekat dengan ujung tiang
        spt_terdekat = min(lapisan, key=lambda l: abs(l["z_tengah"] - z_ujung))["spt"]
        return float(spt_terdekat)

    # Rata-rata tertimbang berdasarkan tebal lapisan
    spt_avg = np.average(nilai_spt, weights=bobot)
    return float(round(spt_avg, 1))


def lapisan_dalam_tiang(lapisan: list[dict], z_ujung: float) -> list[dict]:
    """
    Menyaring lapisan tanah yang dilewati tiang (dari permukaan hingga z_ujung).
    Memotong lapisan terakhir jika ujung tiang berada di tengah lapisan.

    Parameter:
        lapisan : list dict profil tanah
        z_ujung : kedalaman ujung tiang (m)

    Mengembalikan list lapisan yang dilewati tiang (sudah dipotong).
    """
    hasil = []

    for lap in lapisan:
        if lap["z_atas"] >= z_ujung:
            break  # sudah melewati ujung tiang

        # Potong lapisan jika ujung tiang berada di tengah lapisan
        if lap["z_bawah"] > z_ujung:
            lap_potong = lap.copy()
            tebal_baru  = z_ujung - lap["z_atas"]
            z_tengah_baru = lap["z_atas"] + tebal_baru / 2.0
            lap_potong["z_bawah"]  = z_ujung
            lap_potong["tebal"]    = tebal_baru
            lap_potong["z_tengah"] = z_tengah_baru
            hasil.append(lap_potong)
        else:
            hasil.append(lap)

    return hasil
