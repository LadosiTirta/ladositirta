# utils/soil_converter.py
# Konversi berbagai metode input data tanah ke format lapisan standar
#
# Metode yang didukung:
#   1. Manual per lapisan          (sudah ada — passthrough)
#   2. SPT-N per kedalaman         → auto-layering berdasarkan perubahan N
#   3. Sondir/CPT (qc, fs)         → korelasi Robertson (1990) + Lunne (1997)
#   4. SPT + Sondir (gunakan min)  → konservatif, gabungkan kedua data
#   5. Korelasi langsung           → pilih jenis tanah → parameter tipikal SNI
#
# Semua metode menghasilkan DataFrame dengan kolom KOLOM_TANAH standar
# sehingga langsung bisa dipakai calculations/bearing_capacity.py

import numpy as np
import pandas as pd
import streamlit as st
from utils.input_handler import KOLOM_TANAH, JENIS_TANAH_OPSI, DATA_TANAH_DEFAULT


# ══════════════════════════════════════════════════════════════
# PARAMETER TIPIKAL PER JENIS TANAH (untuk Metode 5)
# Sumber: SNI 8460:2017 Tabel B, Bowles (1996), Das (2010)
# ══════════════════════════════════════════════════════════════
PARAM_TIPIKAL = {
    "Lempung sangat lunak":  {"cu": 12.5, "phi": 0.0, "gamma": 15.5, "spt": 2,  "Eu": 1500},
    "Lempung lunak":         {"cu": 25.0, "phi": 0.0, "gamma": 16.0, "spt": 5,  "Eu": 3000},
    "Lempung sedang":        {"cu": 50.0, "phi": 0.0, "gamma": 17.0, "spt": 10, "Eu": 6000},
    "Lempung kaku":          {"cu": 100., "phi": 0.0, "gamma": 18.0, "spt": 20, "Eu": 15000},
    "Lempung sangat kaku":   {"cu": 200., "phi": 0.0, "gamma": 19.0, "spt": 35, "Eu": 30000},
    "Pasir lepas":           {"cu": 0.0,  "phi": 28., "gamma": 16.5, "spt": 8,  "Es": 10000},
    "Pasir sedang":          {"cu": 0.0,  "phi": 32., "gamma": 18.0, "spt": 22, "Es": 25000},
    "Pasir padat":           {"cu": 0.0,  "phi": 36., "gamma": 19.5, "spt": 45, "Es": 50000},
    "Lanau":                 {"cu": 20.0, "phi": 25., "gamma": 17.0, "spt": 12, "Es": 8000},
    "Kerikil":               {"cu": 0.0,  "phi": 38., "gamma": 20.0, "spt": 50, "Es": 80000},
}

# Modulus elastisitas untuk settlement (kPa)
# Eu = undrained (lempung), Es = drained (pasir)


# ══════════════════════════════════════════════════════════════
# HELPER: FORMAT DATAFRAME STANDAR
# ══════════════════════════════════════════════════════════════
def _df_standar(baris: list[dict]) -> pd.DataFrame:
    """Mengubah list dict menjadi DataFrame format standar KOLOM_TANAH."""
    df = pd.DataFrame(baris)
    # Pastikan semua kolom ada
    for k, nama in KOLOM_TANAH.items():
        if nama not in df.columns:
            df[nama] = 0.0
    df[KOLOM_TANAH["no"]] = range(1, len(df) + 1)
    return df[list(KOLOM_TANAH.values())].reset_index(drop=True)


# ══════════════════════════════════════════════════════════════
# METODE 2: SPT-N PER KEDALAMAN → AUTO LAYERING
# ══════════════════════════════════════════════════════════════

def spt_per_kedalaman_ke_lapisan(
    df_spt: pd.DataFrame,          # kolom: "Kedalaman (m)", "SPT-N"
    gamma_default: float = 17.0,
    threshold_persen: float = 40.0  # % perubahan N untuk batas lapisan baru
) -> pd.DataFrame:
    """
    Mengkonversi data SPT-N per kedalaman ke lapisan tanah.

    Algoritma:
    1. Urutkan berdasarkan kedalaman
    2. Kelompokkan titik-titik SPT yang nilainya mirip (dalam threshold %)
    3. Setiap kelompok = satu lapisan
    4. Estimasi parameter dari SPT-N rata-rata per lapisan

    Parameter:
        df_spt           : DataFrame kolom "Kedalaman (m)" dan "SPT-N"
        gamma_default    : berat volume default (kN/m³)
        threshold_persen : % perubahan SPT-N untuk memulai lapisan baru
    """
    df = df_spt.copy().sort_values("Kedalaman (m)").reset_index(drop=True)
    kedalaman = df["Kedalaman (m)"].values
    spt_vals  = df["SPT-N"].values

    if len(df) < 2:
        return DATA_TANAH_DEFAULT.copy()

    # Auto-layering: pisahkan lapisan jika perubahan N > threshold
    batas_lapisan = [0]  # indeks awal setiap lapisan
    for i in range(1, len(spt_vals)):
        n_prev = max(spt_vals[i-1], 1)
        persen_perubahan = abs(spt_vals[i] - n_prev) / n_prev * 100
        if persen_perubahan > threshold_persen:
            batas_lapisan.append(i)
    batas_lapisan.append(len(spt_vals))  # sentinel akhir

    baris = []
    for idx in range(len(batas_lapisan) - 1):
        i_mulai = batas_lapisan[idx]
        i_akhir = batas_lapisan[idx + 1]

        z_atas  = float(kedalaman[i_mulai])
        z_bawah = float(kedalaman[i_akhir - 1]) if i_akhir < len(kedalaman) else float(kedalaman[-1]) + 1.5
        n_avg   = float(np.mean(spt_vals[i_mulai:i_akhir]))

        # Estimasi parameter dari SPT (Terzaghi & Peck, Stroud)
        jenis, cu, phi, gamma = _param_dari_spt(n_avg, gamma_default)

        baris.append({
            KOLOM_TANAH["no"]:     idx + 1,
            KOLOM_TANAH["z_atas"]: round(z_atas, 2),
            KOLOM_TANAH["z_bawah"]:round(z_bawah, 2),
            KOLOM_TANAH["jenis"]:  jenis,
            KOLOM_TANAH["spt"]:    round(n_avg, 1),
            KOLOM_TANAH["cu"]:     round(cu, 1),
            KOLOM_TANAH["phi"]:    round(phi, 1),
            KOLOM_TANAH["gamma"]:  gamma,
        })

    return _df_standar(baris)


def _param_dari_spt(n: float, gamma_default: float = 17.0) -> tuple:
    """
    Estimasi jenis tanah dan parameter dari SPT-N.
    Menggunakan Stroud (1974) untuk lempung, Peck et al. (1974) untuk pasir.
    Heuristik: N < 15 → lempung, N ≥ 15 → pasir (bisa dikombinasi dengan jenis tanah)
    """
    # Heuristik sederhana: dominan lempung jika N rendah
    if n <= 4:
        return "Lempung sangat lunak", max(n * 6, 5), 0.0, 15.5
    elif n <= 8:
        return "Lempung lunak", n * 5.5, 0.0, 16.0
    elif n <= 15:
        return "Lempung sedang", n * 5.0, 0.0, 17.0
    elif n <= 30:
        # Transisi — bisa pasir sedang atau lempung kaku
        return "Pasir sedang", 0.0, 28 + (n - 15) * 0.27, 18.0
    elif n <= 50:
        return "Pasir padat", 0.0, 34 + (n - 30) * 0.15, 19.0
    else:
        return "Pasir padat", 0.0, 40.0, 20.0


# ══════════════════════════════════════════════════════════════
# METODE 3: SONDIR/CPT → LAPISAN
# Korelasi Robertson (1990), Lunne et al. (1997)
# ══════════════════════════════════════════════════════════════

def sondir_ke_lapisan(
    df_cpt: pd.DataFrame,   # kolom: "Kedalaman (m)", "qc (MPa)", "fs (kPa)"
    muka_air: float = 2.0,
    gamma_air: float = 9.81
) -> pd.DataFrame:
    """
    Mengkonversi data Sondir/CPT ke lapisan tanah.

    Korelasi yang digunakan:
    - Robertson (1990): soil behaviour type (SBT) dari Ic
    - Cu = qc / Nkt  (Nkt = 15 untuk lempung normal)
    - φ  = arctan(0.1 + 0.38 × log(qc/σ'v))  untuk pasir (Robertson & Campanella 1983)
    - γ   = estimasi dari Rf (friction ratio)
    """
    df = df_cpt.copy().sort_values("Kedalaman (m)").reset_index(drop=True)

    if len(df) < 2:
        return DATA_TANAH_DEFAULT.copy()

    kedalaman = df["Kedalaman (m)"].values
    qc_mpa    = df["qc (MPa)"].values
    fs_kpa    = df["fs (kPa)"].values

    Nkt = 15.0  # faktor kapasitas bearing untuk Cu dari CPT

    # Hitung Ic (Robertson 1990) per titik dan kelompokkan
    lapisan_data = []
    sigma_v = 0.0

    for i in range(len(df)):
        z   = kedalaman[i]
        qc  = qc_mpa[i] * 1000  # konversi ke kPa
        fs  = fs_kpa[i]
        dz  = (kedalaman[i] - kedalaman[i-1]) if i > 0 else kedalaman[0]

        # Tegangan efektif
        if i > 0:
            gamma_est = 18.0  # estimasi awal
            sigma_v  += gamma_est * dz
        u0 = max(gamma_air * (z - muka_air), 0)
        sigma_v_eff = max(sigma_v - u0, 1.0)

        # Normalized CPT parameters (Robertson 1990)
        Pa  = 100.0  # atmospheric pressure (kPa)
        Qtn = max((qc - sigma_v) / Pa * (Pa / sigma_v_eff) ** 0.5, 0.1)
        Fr  = fs / max(qc - sigma_v, 1.0) * 100   # %

        # Soil Behaviour Type Index Ic
        Ic  = np.sqrt((3.47 - np.log10(max(Qtn, 0.1)))**2 + (1.22 + np.log10(max(Fr, 0.1)))**2)

        # Klasifikasi SBT → parameter
        if Ic > 3.6:
            jenis = "Lempung sangat lunak"
            cu    = max(qc / Nkt, 5.0)
            phi   = 0.0
            gamma = 15.0 + Fr * 0.3
        elif Ic > 2.95:
            jenis = "Lempung lunak"
            cu    = max(qc / Nkt, 10.0)
            phi   = 0.0
            gamma = 16.0 + Fr * 0.2
        elif Ic > 2.60:
            jenis = "Lempung sedang"
            cu    = max(qc / Nkt, 20.0)
            phi   = 0.0
            gamma = 17.0
        elif Ic > 2.05:
            jenis = "Lanau"
            cu    = max(qc / (Nkt * 1.5), 10.0)
            phi   = 25.0
            gamma = 17.5
        elif Ic > 1.31:
            jenis = "Pasir sedang"
            cu    = 0.0
            phi   = min(48.0, 29.0 + 0.26 * Qtn)
            gamma = 18.0 + 0.5 * min(Fr, 2.0)
        else:
            jenis = "Pasir padat"
            cu    = 0.0
            phi   = min(48.0, 33.0 + 0.26 * Qtn)
            gamma = 19.5

        lapisan_data.append({
            "z":     z, "qc": qc, "fs": fs,
            "Ic":    Ic, "Qtn": Qtn, "Fr": Fr,
            "jenis": jenis, "cu": cu, "phi": phi,
            "gamma": min(max(gamma, 14.0), 22.0)
        })

    # Auto-layering berdasarkan perubahan Ic > 0.5
    batas = [0]
    for i in range(1, len(lapisan_data)):
        if (abs(lapisan_data[i]["Ic"] - lapisan_data[i-1]["Ic"]) > 0.5 or
                lapisan_data[i]["jenis"] != lapisan_data[i-1]["jenis"]):
            batas.append(i)
    batas.append(len(lapisan_data))

    baris = []
    for idx in range(len(batas) - 1):
        blok    = lapisan_data[batas[idx]:batas[idx+1]]
        z_atas  = blok[0]["z"]
        z_bawah = blok[-1]["z"] + (blok[-1]["z"] - blok[0]["z"]) / max(len(blok), 1) + 0.2
        cu_avg  = float(np.mean([b["cu"]  for b in blok]))
        phi_avg = float(np.mean([b["phi"] for b in blok]))
        g_avg   = float(np.mean([b["gamma"] for b in blok]))
        qc_avg  = float(np.mean([b["qc"]  for b in blok]))
        # SPT estimasi dari qc: N ≈ qc(kPa)/400 untuk pasir, /60 untuk lempung
        jenis   = blok[len(blok)//2]["jenis"]
        faktor  = 400 if "Pasir" in jenis or "Kerikil" in jenis else 60
        spt_est = max(int(qc_avg / faktor), 1)

        baris.append({
            KOLOM_TANAH["no"]:     idx + 1,
            KOLOM_TANAH["z_atas"]: round(z_atas, 2),
            KOLOM_TANAH["z_bawah"]:round(min(z_bawah, kedalaman[-1] + 1.0), 2),
            KOLOM_TANAH["jenis"]:  jenis,
            KOLOM_TANAH["spt"]:    spt_est,
            KOLOM_TANAH["cu"]:     round(cu_avg, 1),
            KOLOM_TANAH["phi"]:    round(phi_avg, 1),
            KOLOM_TANAH["gamma"]:  round(g_avg, 1),
        })

    return _df_standar(baris)


# ══════════════════════════════════════════════════════════════
# METODE 4: SPT + SONDIR → NILAI MINIMUM (KONSERVATIF)
# ══════════════════════════════════════════════════════════════

def spt_plus_sondir_ke_lapisan(
    df_spt: pd.DataFrame,
    df_cpt: pd.DataFrame,
    muka_air: float = 2.0,
) -> pd.DataFrame:
    """
    Menggabungkan SPT dan Sondir, mengambil parameter yang lebih konservatif
    (Cu lebih rendah, φ lebih rendah) per lapisan.
    """
    df_dari_spt = spt_per_kedalaman_ke_lapisan(df_spt)
    df_dari_cpt = sondir_ke_lapisan(df_cpt, muka_air)

    # Interpolasi nilai CPT ke kedalaman lapisan SPT
    baris = []
    for _, row_spt in df_dari_spt.iterrows():
        z_mid = (row_spt[KOLOM_TANAH["z_atas"]] + row_spt[KOLOM_TANAH["z_bawah"]]) / 2

        # Cari lapisan CPT yang overlap
        overlap = df_dari_cpt[
            (df_dari_cpt[KOLOM_TANAH["z_atas"]]  <= z_mid) &
            (df_dari_cpt[KOLOM_TANAH["z_bawah"]] >= z_mid)
        ]

        if len(overlap) == 0:
            baris.append(row_spt.to_dict())
            continue

        row_cpt = overlap.iloc[0]
        # Ambil yang lebih konservatif
        cu_min  = min(row_spt[KOLOM_TANAH["cu"]],  row_cpt[KOLOM_TANAH["cu"]])
        phi_min = min(row_spt[KOLOM_TANAH["phi"]], row_cpt[KOLOM_TANAH["phi"]])

        baris.append({
            KOLOM_TANAH["no"]:     row_spt[KOLOM_TANAH["no"]],
            KOLOM_TANAH["z_atas"]: row_spt[KOLOM_TANAH["z_atas"]],
            KOLOM_TANAH["z_bawah"]:row_spt[KOLOM_TANAH["z_bawah"]],
            KOLOM_TANAH["jenis"]:  row_spt[KOLOM_TANAH["jenis"]],
            KOLOM_TANAH["spt"]:    row_spt[KOLOM_TANAH["spt"]],
            KOLOM_TANAH["cu"]:     round(cu_min,  1),
            KOLOM_TANAH["phi"]:    round(phi_min, 1),
            KOLOM_TANAH["gamma"]:  row_spt[KOLOM_TANAH["gamma"]],
        })

    return _df_standar(baris)


# ══════════════════════════════════════════════════════════════
# METODE 5: KORELASI LANGSUNG (PILIH JENIS TANAH)
# ══════════════════════════════════════════════════════════════

def korelasi_langsung_ke_lapisan(
    lapisan_input: list[dict]  # [{"jenis":..., "z_atas":..., "z_bawah":...}, ...]
) -> pd.DataFrame:
    """
    Mengisi parameter tanah secara otomatis berdasarkan jenis tanah yang dipilih.
    Menggunakan nilai tipikal dari PARAM_TIPIKAL.
    """
    baris = []
    for i, lap in enumerate(lapisan_input):
        jenis  = lap.get("jenis", "Lempung sedang")
        p      = PARAM_TIPIKAL.get(jenis, PARAM_TIPIKAL["Lempung sedang"])
        baris.append({
            KOLOM_TANAH["no"]:     i + 1,
            KOLOM_TANAH["z_atas"]: lap.get("z_atas", 0.0),
            KOLOM_TANAH["z_bawah"]:lap.get("z_bawah", 3.0),
            KOLOM_TANAH["jenis"]:  jenis,
            KOLOM_TANAH["spt"]:    p["spt"],
            KOLOM_TANAH["cu"]:     p["cu"],
            KOLOM_TANAH["phi"]:    p["phi"],
            KOLOM_TANAH["gamma"]:  p["gamma"],
        })
    return _df_standar(baris)
