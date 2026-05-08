# utils/grapher.py
# Pembuatan grafik profil tanah dan distribusi daya dukung
# Menggunakan matplotlib

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# Warna per kategori tanah
WARNA_TANAH = {
    "lempung":  "#A0785A",
    "pasir":    "#E8C97A",
    "lanau":    "#B8C4A0",
    "kerikil":  "#A0A0A0",
}

WARNA_QPOINT = "#C0392B"  # merah — end bearing
WARNA_QSKIN  = "#2980B9"  # biru — skin friction


def buat_grafik_profil(semua_lapisan: list[dict], z_ujung: float,
                        muka_air: float, D: float) -> plt.Figure:
    """
    Membuat grafik profil tanah SPT-N vs kedalaman.

    Mengembalikan objek Figure matplotlib.
    """
    fig, ax = plt.subplots(figsize=(4.5, 7))

    z_maks = semua_lapisan[-1]["z_bawah"] + 1.0

    # Gambar lapisan tanah sebagai blok warna
    for lap in semua_lapisan:
        kat    = lap["kategori"]
        warna  = WARNA_TANAH.get(kat, "#D0D0D0")
        ax.barh(
            y      = -(lap["z_atas"] + lap["tebal"] / 2),
            width  = lap["spt"],
            height = lap["tebal"],
            left   = 0,
            color  = warna,
            alpha  = 0.6,
            edgecolor="white",
            linewidth=0.5,
        )
        # Label jenis tanah di dalam blok
        ax.text(
            x=1, y=-(lap["z_tengah"]),
            s=lap["jenis"][:18],
            va="center", ha="left",
            fontsize=7, color="#333333"
        )

    # Plot SPT-N sebagai garis
    spt_vals = [lap["spt"] for lap in semua_lapisan]
    z_vals   = [-lap["z_tengah"] for lap in semua_lapisan]
    ax.plot(spt_vals, z_vals, "ko-", linewidth=1.5, markersize=5, label="SPT-N")

    # Garis muka air tanah
    ax.axhline(y=-muka_air, color="#1E90FF", linestyle="--", linewidth=1.2, label=f"MAT = {muka_air:.1f} m")

    # Garis ujung tiang
    ax.axhline(y=-z_ujung, color="#E74C3C", linestyle="--", linewidth=1.2, label=f"Ujung tiang L = {z_ujung:.1f} m")

    # Legenda warna tanah
    patches = [
        mpatches.Patch(color=WARNA_TANAH["lempung"], alpha=0.7, label="Lempung"),
        mpatches.Patch(color=WARNA_TANAH["pasir"],   alpha=0.7, label="Pasir"),
        mpatches.Patch(color=WARNA_TANAH["lanau"],   alpha=0.7, label="Lanau"),
    ]

    ax.set_xlabel("SPT-N (pukulan)", fontsize=9)
    ax.set_ylabel("Kedalaman (m)", fontsize=9)
    ax.set_title("Profil Tanah & SPT-N", fontsize=10, fontweight="bold")
    ax.set_ylim(-z_maks, 0.5)
    ax.set_xlim(0, max(max(spt_vals) * 1.3, 20))
    ax.legend(handles=patches + [
        plt.Line2D([0],[0],color="k",marker="o",linewidth=1.5,label="SPT-N"),
        plt.Line2D([0],[0],color="#1E90FF",linestyle="--",linewidth=1.2,label=f"MAT"),
        plt.Line2D([0],[0],color="#E74C3C",linestyle="--",linewidth=1.2,label=f"Ujung tiang"),
    ], fontsize=7, loc="lower right")

    # Format sumbu Y sebagai kedalaman positif
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{abs(y):.0f}"))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}"))
    plt.setp(ax.get_xticklabels(), fontsize=8)
    plt.setp(ax.get_yticklabels(), fontsize=8)
    ax.grid(axis="x", alpha=0.3, linewidth=0.5)
    fig.tight_layout()
    return fig


def buat_grafik_distribusi_skin(detail_lapisan: list[dict],
                                 Qpoint: float, z_ujung: float) -> plt.Figure:
    """
    Membuat grafik distribusi unit skin friction (fs) vs kedalaman
    dan diagram batang Qskin per lapisan.

    Mengembalikan objek Figure matplotlib.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7, 6))

    # ---- Grafik kiri: unit skin friction (kPa) vs kedalaman ----
    fs_vals  = []
    z_tengah = []
    for lap in detail_lapisan:
        fs_vals.append(lap["fs"])
        z_tengah.append(-lap["z_atas"] - lap["tebal"] / 2)

    ax1.barh(
        y      = z_tengah,
        width  = fs_vals,
        height = [lap["tebal"] for lap in detail_lapisan],
        color  = WARNA_QSKIN,
        alpha  = 0.7,
        edgecolor="white",
        linewidth=0.5,
    )
    # Titik nilai
    ax1.plot(fs_vals, z_tengah, "bo", markersize=5)
    for fs, z in zip(fs_vals, z_tengah):
        ax1.text(fs + 0.3, z, f"{fs:.1f}", va="center", fontsize=7, color="#1A5276")

    ax1.axhline(y=-z_ujung, color=WARNA_QPOINT, linestyle="--", linewidth=1.2,
                label=f"Ujung tiang ({z_ujung:.1f} m)")
    ax1.set_xlabel("Unit skin friction, fs (kPa)", fontsize=9)
    ax1.set_ylabel("Kedalaman (m)", fontsize=9)
    ax1.set_title("Distribusi fs vs Kedalaman", fontsize=10, fontweight="bold")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{abs(y):.0f}"))
    plt.setp(ax1.get_yticklabels(), fontsize=8)
    ax1.grid(axis="x", alpha=0.3, linewidth=0.5)
    ax1.legend(fontsize=7)

    # ---- Grafik kanan: Qs per lapisan (kN) + Qpoint ----
    labels = [f"L{lap['no']}\n{lap['z_atas']:.0f}–{lap['z_bawah']:.0f}m"
              for lap in detail_lapisan]
    qs_vals = [lap["Qs"] for lap in detail_lapisan]
    labels.append("End\nbearing")
    qs_vals.append(Qpoint)

    warna_bar = [WARNA_QSKIN] * len(detail_lapisan) + [WARNA_QPOINT]
    bars = ax2.bar(labels, qs_vals, color=warna_bar, alpha=0.8, edgecolor="white", linewidth=0.5)

    for bar, val in zip(bars, qs_vals):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                 f"{val:.1f}", ha="center", va="bottom", fontsize=7, fontweight="bold")

    ax2.set_ylabel("Daya dukung per lapisan (kN)", fontsize=9)
    ax2.set_title("Kontribusi per Lapisan", fontsize=10, fontweight="bold")
    ax2.set_xticks(range(len(labels)))
    ax2.set_xticklabels(labels, fontsize=7, rotation=0)
    ax2.grid(axis="y", alpha=0.3, linewidth=0.5)

    patch_skin = mpatches.Patch(color=WARNA_QSKIN, alpha=0.8, label="Skin friction")
    patch_end  = mpatches.Patch(color=WARNA_QPOINT, alpha=0.8, label="End bearing")
    ax2.legend(handles=[patch_skin, patch_end], fontsize=7)

    fig.tight_layout()
    return fig


def buat_grafik_variasi_kedalaman(hasil_variasi: list[dict]) -> plt.Figure:
    """
    Membuat grafik Qijin tekan & tarik vs variasi kedalaman tiang.

    Mengembalikan objek Figure matplotlib.
    """
    fig, ax = plt.subplots(figsize=(6, 5))

    z     = [r["z"] for r in hasil_variasi]
    Qtekan= [r["Qijin_tekan"] for r in hasil_variasi]
    Qtarik= [r["Qijin_tarik"] for r in hasil_variasi]
    Qpoint= [r["Qpoint"] for r in hasil_variasi]
    Qskin = [r["Qskin"] for r in hasil_variasi]

    ax.plot(z, Qtekan, "r-o", linewidth=2, markersize=4, label="Qijin tekan (kN)")
    ax.plot(z, Qtarik, "b--s", linewidth=1.5, markersize=4, label="Qijin tarik (kN)")
    ax.fill_between(z, Qskin, alpha=0.15, color=WARNA_QSKIN, label="Qskin tekan (kN)")
    ax.fill_between(z, Qtekan, alpha=0.10, color=WARNA_QPOINT)

    ax.set_xlabel("Kedalaman tiang, L (m)", fontsize=10)
    ax.set_ylabel("Kapasitas ijin (kN)", fontsize=10)
    ax.set_title("Kapasitas Tiang vs Kedalaman", fontsize=11, fontweight="bold")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, linewidth=0.5)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    return fig
