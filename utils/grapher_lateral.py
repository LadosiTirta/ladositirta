# utils/grapher_lateral.py
# Grafik hasil perhitungan gaya lateral tiang
# Broms: summary bar chart + defleksi elastis
# P-Y curve: 4 subplot (defleksi, momen, geser, kurva p-y)

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np


def buat_grafik_broms(hasil_broms: dict) -> plt.Figure:
    """
    Grafik ringkasan hasil Broms:
    - Kiri: diagram gaya lateral dan momen
    - Kanan: profil defleksi elastis sepanjang tiang

    Mengembalikan Figure matplotlib.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 6))

    tanah   = hasil_broms.get("tanah", "lempung")
    kondisi = hasil_broms.get("kondisi", "bebas")
    H       = hasil_broms.get("H_input", 0.0)
    Hu      = hasil_broms["Hu"]
    Hijin   = hasil_broms["Hijin"]
    Mmax    = hasil_broms["Mmax"]
    defl    = hasil_broms["defleksi_mm"]

    # ---- Grafik kiri: Kapasitas & Momen ----
    kategori = ["H input", "H ijin", "H ulimit"]
    nilai    = [H if H > 0 else Hijin * 0.5, Hijin, Hu]
    warna    = ["#5DADE2", "#27AE60", "#E74C3C"]

    bars = ax1.bar(kategori, nilai, color=warna, alpha=0.82, edgecolor="white", linewidth=0.5)
    for bar, val in zip(bars, nilai):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + Hu * 0.01,
                 f"{val:.1f} kN", ha="center", va="bottom", fontsize=9, fontweight="bold")

    ax1.set_ylabel("Gaya Lateral (kN)", fontsize=10)
    ax1.set_title(f"Kapasitas Lateral — Broms\n({tanah.title()}, kepala {kondisi})", fontsize=10, fontweight="bold")
    ax1.grid(axis="y", alpha=0.3, linewidth=0.5)

    # Anotasi momen maks
    ax1.text(0.5, 0.05,
             f"Mmax = {Mmax:.1f} kN·m\nDefleksi = {defl:.1f} mm",
             transform=ax1.transAxes, ha="center", va="bottom",
             fontsize=9, color="#555555",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="#F8F9FA", alpha=0.8))

    # ---- Grafik kanan: Profil defleksi linear (elastis) ----
    L    = hasil_broms.get("L", 20.0)
    D    = hasil_broms.get("D", 0.35)
    EI   = hasil_broms.get("EpIp", 1.0)
    H_plot = H if H > 0 else Hijin

    # Rekonstruksi profil defleksi linear sederhana (pendekatan)
    z_plot = np.linspace(0, L, 100)
    if tanah == "lempung":
        beta = hasil_broms.get("beta", 0.1)
        L_beta = hasil_broms.get("L_beta", beta * L)
        if L_beta >= 2.0 and kondisi == "bebas":
            # Persamaan Hetenyi — tiang panjang kepala bebas
            bz  = beta * z_plot
            y_z = (H_plot / (EI * beta**3)) * (np.exp(-bz) * (np.cos(bz) + np.sin(bz)))
            y_z = np.clip(y_z, -defl/1000 * 5, defl/1000 * 5)
        else:
            # Tiang pendek — parabola sederhana
            y_z = defl/1000 * (1 - z_plot/L)**2
    else:
        T_fak = hasil_broms.get("T_faktor", 2.0)
        z_T   = z_plot / T_fak
        # Matlock & Reese (1956) — tiang panjang pasir
        y_z = (H_plot * T_fak**3 / EI) * (2.435 - 1.623 * z_T - 0.3 * z_T**2) * np.exp(-z_T)
        y_z = np.clip(y_z, -abs(y_z[0])*2, abs(y_z[0])*2)

    y_z_mm = y_z * 1000  # konversi ke mm

    ax2.plot(y_z_mm, -z_plot, "b-", linewidth=2, label="Defleksi")
    ax2.fill_betweenx(-z_plot, 0, y_z_mm, alpha=0.15, color="#2980B9")
    ax2.axvline(x=0, color="k", linewidth=0.8)
    ax2.axhline(y=0, color="gray", linewidth=0.5, linestyle="--")

    # Tandai titik momen maks
    if tanah == "pasir":
        z_mm = hasil_broms.get("z_mmax", L/4)
        ax2.axhline(y=-z_mm, color="red", linewidth=1, linestyle="--",
                    label=f"z Mmax = {z_mm:.2f} m")

    ax2.set_xlabel("Defleksi (mm)", fontsize=10)
    ax2.set_ylabel("Kedalaman (m)", fontsize=10)
    ax2.set_title("Profil Defleksi Lateral\n(Pendekatan Elastis)", fontsize=10, fontweight="bold")
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{abs(y):.0f}"))
    ax2.grid(alpha=0.3, linewidth=0.5)
    ax2.legend(fontsize=8)

    fig.tight_layout()
    return fig


def buat_grafik_py(hasil_py: dict, param_tiang: dict, df_tanah) -> plt.Figure:
    """
    Grafik hasil analisis p-y curve: 4 subplot.
    1. Profil defleksi y(z)
    2. Momen lentur M(z)
    3. Gaya geser V(z)
    4. Kurva p-y di 3 kedalaman representatif

    Mengembalikan Figure matplotlib.
    """
    from calculations.lateral import (
        _kurva_py_lempung_lunak, _kurva_py_lempung_keras,
        _kurva_py_pasir, GAMMA_AIR
    )
    from calculations.soil_profile import hitung_profil_tanah
    from calculations.bearing_capacity import phi_dari_spt

    z_nodes = np.array(hasil_py["z_nodes"])
    y_mm    = np.array(hasil_py["y_m"]) * 1000   # m → mm
    M_kNm   = np.array(hasil_py["M_kNm"])
    V_kN    = np.array(hasil_py["V_kN"])
    L       = hasil_py["L"]
    H       = hasil_py["H"]

    fig = plt.figure(figsize=(12, 8))
    gs  = gridspec.GridSpec(2, 2, figure=fig, hspace=0.40, wspace=0.35)

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, 0])
    ax4 = fig.add_subplot(gs[1, 1])

    # ---- Subplot 1: Defleksi ----
    ax1.plot(y_mm, -z_nodes, "b-", linewidth=2)
    ax1.fill_betweenx(-z_nodes, 0, y_mm, alpha=0.15, color="#2980B9")
    ax1.axvline(x=0, color="k", linewidth=0.8)
    ax1.set_xlabel("Defleksi y (mm)", fontsize=9)
    ax1.set_ylabel("Kedalaman (m)", fontsize=9)
    ax1.set_title("Defleksi Lateral y(z)", fontsize=10, fontweight="bold")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{abs(y):.0f}"))
    ax1.grid(alpha=0.3, linewidth=0.5)
    ax1.text(0.97, 0.97, f"y₀ = {hasil_py['y0_mm']:.2f} mm",
             transform=ax1.transAxes, ha="right", va="top",
             fontsize=8, bbox=dict(boxstyle="round,pad=0.2", facecolor="#EBF5FB"))

    # ---- Subplot 2: Momen Lentur ----
    ax2.plot(M_kNm, -z_nodes, "r-", linewidth=2)
    ax2.fill_betweenx(-z_nodes, 0, M_kNm, alpha=0.15, color="#C0392B")
    ax2.axvline(x=0, color="k", linewidth=0.8)
    ax2.set_xlabel("Momen M (kN·m)", fontsize=9)
    ax2.set_ylabel("Kedalaman (m)", fontsize=9)
    ax2.set_title("Momen Lentur M(z)", fontsize=10, fontweight="bold")
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{abs(y):.0f}"))
    ax2.grid(alpha=0.3, linewidth=0.5)
    ax2.axhline(y=-hasil_py["z_Mmax"], color="orange", linestyle="--", linewidth=1,
                label=f"z_Mmax={hasil_py['z_Mmax']:.1f}m")
    ax2.text(0.97, 0.97, f"Mmax = {hasil_py['Mmax']:.1f} kN·m",
             transform=ax2.transAxes, ha="right", va="top",
             fontsize=8, bbox=dict(boxstyle="round,pad=0.2", facecolor="#FDEDEC"))
    ax2.legend(fontsize=7)

    # ---- Subplot 3: Gaya Geser ----
    ax3.plot(V_kN, -z_nodes, "g-", linewidth=2)
    ax3.fill_betweenx(-z_nodes, 0, V_kN, alpha=0.15, color="#27AE60")
    ax3.axvline(x=0, color="k", linewidth=0.8)
    ax3.set_xlabel("Gaya Geser V (kN)", fontsize=9)
    ax3.set_ylabel("Kedalaman (m)", fontsize=9)
    ax3.set_title("Gaya Geser V(z)", fontsize=10, fontweight="bold")
    ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{abs(y):.0f}"))
    ax3.grid(alpha=0.3, linewidth=0.5)
    ax3.text(0.97, 0.97, f"H input = {H:.1f} kN",
             transform=ax3.transAxes, ha="right", va="top",
             fontsize=8, bbox=dict(boxstyle="round,pad=0.2", facecolor="#EAFAF1"))

    # ---- Subplot 4: Kurva p-y di 3 kedalaman ----
    maw       = param_tiang["muka_air"]
    D         = param_tiang["diameter"]
    semua_lap = hitung_profil_tanah(df_tanah, maw)

    def cari_lap(z):
        for lap in semua_lap:
            if lap["z_atas"] <= z <= lap["z_bawah"]:
                return lap
        return semua_lap[-1]

    kedalaman_py = [L * 0.1, L * 0.3, L * 0.6]
    warna_py     = ["#E74C3C", "#F39C12", "#2980B9"]
    y_range      = np.linspace(0, hasil_py.get("y0_mm", 10) / 1000 * 3, 200)

    for z_py, warna_py_i in zip(kedalaman_py, warna_py):
        lap  = cari_lap(z_py)
        kat  = lap["kategori"]
        geff = max(lap["gamma"] - GAMMA_AIR if z_py > maw else lap["gamma"], 8.0)

        if kat == "lempung":
            cu = lap["cu"] if lap["cu"] > 0 else lap["spt"] * 5.0
            cu = max(cu, 5.0)
            pfunc, pu = (_kurva_py_lempung_lunak(max(z_py, 0.01), D, cu, geff)
                         if cu < 96 else
                         _kurva_py_lempung_keras(max(z_py, 0.01), D, cu))
        else:
            phi = lap["phi_deg"] if lap["phi_deg"] > 0 else phi_dari_spt(lap["spt"], kat)
            pfunc, pu = _kurva_py_pasir(max(z_py, 0.01), D, phi, geff)

        p_vals = [pfunc(y_i) for y_i in y_range]
        ax4.plot(y_range * 1000, p_vals,
                 color=warna_py_i, linewidth=1.8,
                 label=f"z = {z_py:.1f} m (pu={pu:.1f} kN/m)")

    ax4.set_xlabel("Defleksi y (mm)", fontsize=9)
    ax4.set_ylabel("Resistansi tanah p (kN/m)", fontsize=9)
    ax4.set_title("Kurva p-y (3 Kedalaman)", fontsize=10, fontweight="bold")
    ax4.grid(alpha=0.3, linewidth=0.5)
    ax4.legend(fontsize=7)
    ax4.set_xlim(left=0)
    ax4.set_ylim(bottom=0)

    # Judul keseluruhan
    fig.suptitle(
        f"Analisis Gaya Lateral — P-Y Curve\n"
        f"H = {H:.1f} kN  |  L = {L:.1f} m  |  D = {param_tiang['diameter']*100:.0f} cm  |  "
        f"Kepala {hasil_py['kondisi']}",
        fontsize=11, fontweight="bold", y=1.01
    )

    return fig
