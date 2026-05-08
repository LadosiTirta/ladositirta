"""
pilecap/geometry.py
===================
Modul geometri pilecap: layout posisi tiang, validasi jarak,
perhitungan centroid grup, momen inersia grup, dan plot denah.

Standar acuan:
  SNI 8460:2017 Pasal 7.4  — Jarak antar tiang & jarak ke tepi
  SNI 2847:2019             — Umum beton struktural

Notasi:
  Lx  = panjang pilecap arah X (m)
  Ly  = lebar  pilecap arah Y (m)
  t   = tebal  pilecap (m)
  D   = diameter tiang (mm)
  s   = jarak antar tiang (pusat ke pusat, mm)
"""

import math
import itertools
import matplotlib
matplotlib.use("Agg")          # mode non-interaktif untuk Streamlit
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
import numpy as np
from io import BytesIO
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional


# ---------------------------------------------------------------------------
# Konstanta geometri tiang (SNI 8460:2017 Pasal 7.4)
# ---------------------------------------------------------------------------
JARAK_MIN_ANTAR_TIANG_FAKTOR = 2.5   # s_min = 2.5 × D  (pusat ke pusat)
JARAK_MIN_KE_TEPI_FAKTOR     = 1.25  # e_min = 1.25 × D (pusat tiang ke tepi pilecap)


# ---------------------------------------------------------------------------
# Struktur data posisi kolom
# ---------------------------------------------------------------------------
@dataclass
class DataKolom:
    """
    Data geometri dan beban satu kolom.

    Koordinat (xk, yk) diukur dari titik acuan yang sama
    dengan koordinat tiang pancang.

    Beban terfaktor sesuai SNI 2847:2019 kombinasi LRFD:
      Nu  — gaya aksial terfaktor (kN), tekan positif
      Vux — gaya geser terfaktor arah X (kN)
      Vuy — gaya geser terfaktor arah Y (kN)
      Mux — momen lentur terfaktor sumbu X (kNm), searah SNI
      Muy — momen lentur terfaktor sumbu Y (kNm)
    """
    id_kolom : int
    xk       : float          # posisi pusat kolom arah X (m)
    yk       : float          # posisi pusat kolom arah Y (m)
    bk       : float          # lebar kolom arah X (m)
    hk       : float          # tinggi kolom arah Y (m)
    Nu       : float = 0.0    # kN, tekan +
    Vux      : float = 0.0    # kN
    Vuy      : float = 0.0    # kN
    Mux      : float = 0.0    # kNm
    Muy      : float = 0.0    # kNm


# ---------------------------------------------------------------------------
# Struktur data kondisi galian & level
# ---------------------------------------------------------------------------
@dataclass
class KondisiGalian:
    """
    Parameter kondisi galian, beban tanah, dan level sloof.

    h_galian       — kedalaman top pilecap dari muka tanah asli (m)
                     h_galian = 0  →  top pilecap setara muka tanah
    gamma_tanah    — berat jenis tanah urug (kN/m³), default 17
    h_muka_air     — kedalaman muka air tanah dari muka tanah asli (m)
                     jika > h_galian + t → tidak ada uplift
    ada_sloof      — True jika ada sloof yang bertumpu pada pilecap
    h_bottom_sloof — jarak bottom sloof dari top pilecap (m), positif ke bawah
    b_sloof        — lebar sloof (m)
    h_sloof        — tinggi sloof (m)
    """
    h_galian       : float = 0.0
    gamma_tanah    : float = 17.0
    h_muka_air     : float = 100.0   # default jauh di bawah
    ada_sloof      : bool  = False
    h_bottom_sloof : float = 0.0
    b_sloof        : float = 0.3
    h_sloof        : float = 0.5


# ---------------------------------------------------------------------------
# Kelas utama: PilecapGeometry
# ---------------------------------------------------------------------------
class PilecapGeometry:
    """
    Kelas utama yang menyimpan seluruh geometri pilecap dan
    menyediakan fungsi kalkulasi serta validasi.

    Parameter
    ---------
    Lx            : panjang pilecap arah X (m)
    Ly            : lebar  pilecap arah Y (m)
    t             : tebal  pilecap (m)
    diameter_pile : diameter tiang pancang (mm)
    cover         : selimut beton pilecap (mm)
    fc            : mutu beton f'c (MPa)
    fy            : mutu baja fy (MPa)
    pile_coords   : list of (x, y) — koordinat pusat setiap tiang (m)
                    sistem koordinat: origin di sudut kiri-bawah pilecap,
                    atau origin bebas asal konsisten.
    kolom_list    : list of DataKolom
    galian        : KondisiGalian
    """

    def __init__(
        self,
        Lx            : float,
        Ly            : float,
        t             : float,
        diameter_pile : float,
        cover         : float = 75.0,
        fc            : float = 30.0,
        fy            : float = 400.0,
        pile_coords   : Optional[List[Tuple[float, float]]] = None,
        kolom_list    : Optional[List[DataKolom]] = None,
        galian        : Optional[KondisiGalian]   = None,
    ):
        # --- dimensi pilecap ---
        self.Lx = Lx                    # m
        self.Ly = Ly                    # m
        self.t  = t                     # m

        # --- material ---
        self.fc    = fc                 # MPa
        self.fy    = fy                 # MPa
        self.cover = cover              # mm

        # --- tiang ---
        self.diameter_pile = diameter_pile          # mm
        self.pile_coords   = pile_coords or []      # list (x, y) dalam meter

        # --- kolom ---
        self.kolom_list = kolom_list or []

        # --- kondisi galian ---
        self.galian = galian or KondisiGalian()

    # -----------------------------------------------------------------------
    # PROPERTI TURUNAN
    # -----------------------------------------------------------------------
    @property
    def jumlah_tiang(self) -> int:
        """Jumlah total tiang pancang."""
        return len(self.pile_coords)

    @property
    def D_m(self) -> float:
        """Diameter tiang dalam meter (konversi dari mm)."""
        return self.diameter_pile / 1000.0

    @property
    def s_min_m(self) -> float:
        """Jarak minimum antar tiang pusat ke pusat (meter)."""
        return JARAK_MIN_ANTAR_TIANG_FAKTOR * self.D_m

    @property
    def e_min_m(self) -> float:
        """Jarak minimum pusat tiang ke tepi pilecap (meter)."""
        return JARAK_MIN_KE_TEPI_FAKTOR * self.D_m

    # -----------------------------------------------------------------------
    # CENTROID GRUP TIANG
    # -----------------------------------------------------------------------
    def centroid_grup(self) -> Tuple[float, float]:
        """
        Hitung centroid (titik berat) posisi grup tiang.

        Rumus:
            x̄ = ΣXi / n
            ȳ = ΣYi / n

        Return
        ------
        (x_bar, y_bar) dalam meter
        """
        if self.jumlah_tiang == 0:
            return (0.0, 0.0)

        n    = self.jumlah_tiang
        x_bar = sum(x for x, y in self.pile_coords) / n
        y_bar = sum(y for x, y in self.pile_coords) / n
        return (x_bar, y_bar)

    # -----------------------------------------------------------------------
    # MOMEN INERSIA GRUP TIANG
    # -----------------------------------------------------------------------
    def Ix_grup(self) -> float:
        """
        Momen inersia posisi tiang terhadap sumbu X melalui centroid grup.

        Rumus:
            Ix = Σ yi²   (yi = jarak tiang ke-i terhadap centroid arah Y)

        Digunakan untuk:
            Mi_x = Mu_y × xi / Iy   (gaya aksial akibat momen sumbu Y)

        Return: Ix dalam m²
        """
        _, y_bar = self.centroid_grup()
        return sum((y - y_bar) ** 2 for _, y in self.pile_coords)

    def Iy_grup(self) -> float:
        """
        Momen inersia posisi tiang terhadap sumbu Y melalui centroid grup.

        Rumus:
            Iy = Σ xi²   (xi = jarak tiang ke-i terhadap centroid arah X)

        Digunakan untuk:
            Mi_y = Mu_x × yi / Ix

        Return: Iy dalam m²
        """
        x_bar, _ = self.centroid_grup()
        return sum((x - x_bar) ** 2 for x, _ in self.pile_coords)

    def jarak_tiang_ke_centroid(self) -> List[Tuple[float, float]]:
        """
        Hitung jarak setiap tiang terhadap centroid grup.

        Return
        ------
        List of (xi, yi) — jarak relatif tiang ke-i terhadap centroid (m)
        Positif ke kanan (X) dan ke atas (Y).
        """
        x_bar, y_bar = self.centroid_grup()
        return [(x - x_bar, y - y_bar) for x, y in self.pile_coords]

    # -----------------------------------------------------------------------
    # VALIDASI GEOMETRI
    # -----------------------------------------------------------------------
    def validasi_jarak(self) -> List[Dict]:
        """
        Validasi jarak antar tiang dan jarak tiang ke tepi pilecap.

        Aturan SNI 8460:2017 Pasal 7.4:
          s_min  = 2.5 × D   (jarak antar tiang, pusat ke pusat)
          e_min  = 1.25 × D  (jarak pusat tiang ke tepi pilecap)

        Return
        ------
        List of dict dengan kunci:
          {
            'tipe'    : 'antar_tiang' | 'ke_tepi',
            'level'   : 'OK' | 'WARNING' | 'ERROR',
            'pesan'   : str,
            'nilai'   : float,   # nilai aktual (m)
            'minimum' : float,   # nilai minimum yang disyaratkan (m)
          }
        """
        hasil = []
        n     = self.jumlah_tiang
        D_m   = self.D_m
        s_min = self.s_min_m
        e_min = self.e_min_m

        if n == 0:
            hasil.append({
                'tipe'    : 'umum',
                'level'   : 'ERROR',
                'pesan'   : 'Belum ada tiang yang diinput.',
                'nilai'   : 0.0,
                'minimum' : 0.0,
            })
            return hasil

        # --- (1) Cek jarak antar tiang ---
        for i, j in itertools.combinations(range(n), 2):
            xi, yi = self.pile_coords[i]
            xj, yj = self.pile_coords[j]
            s_aktual = math.hypot(xj - xi, yj - yi)

            if s_aktual < s_min * 0.999:    # toleransi 1 mm
                level = 'ERROR'
                pesan = (
                    f"Jarak tiang {i+1}–{j+1} = {s_aktual:.3f} m  "
                    f"< s_min = 2.5×D = 2.5×{D_m:.3f} = {s_min:.3f} m  "
                    f"→ TIDAK MEMENUHI SNI 8460:2017 Ps. 7.4"
                )
            elif s_aktual < s_min * 1.05:   # dalam 5 % dari minimum → warning
                level = 'WARNING'
                pesan = (
                    f"Jarak tiang {i+1}–{j+1} = {s_aktual:.3f} m  "
                    f"≈ s_min = {s_min:.3f} m  (margin sempit, perlu cek lapangan)"
                )
            else:
                level = 'OK'
                pesan = (
                    f"Jarak tiang {i+1}–{j+1} = {s_aktual:.3f} m  "
                    f"≥ s_min = {s_min:.3f} m  ✓"
                )

            hasil.append({
                'tipe'    : 'antar_tiang',
                'level'   : level,
                'pesan'   : pesan,
                'nilai'   : round(s_aktual, 4),
                'minimum' : round(s_min, 4),
                'tiang_i' : i + 1,
                'tiang_j' : j + 1,
            })

        # --- (2) Cek jarak tiang ke tepi pilecap ---
        # Asumsi: tepi pilecap di x=[0, Lx] dan y=[0, Ly]
        # Jika koordinat tiang tidak dimulai dari 0,
        # hitung terhadap boundary Lx×Ly dengan origin di centroid pilecap.
        # Untuk fleksibilitas, kita cek terhadap bounding box tiang + e_min.
        for i, (xi, yi) in enumerate(self.pile_coords):
            # Jarak ke tepi kiri, kanan, bawah, atas (dari posisi tiang)
            # Kita pakai asumsi: centroid pilecap = (Lx/2, Ly/2) relatif terhadap
            # sudut kiri-bawah pilecap. Tapi karena pengguna bebas memilih origin,
            # kita gunakan jarak minimum ke tepi pilecap berdasarkan batas absolut.
            # Batas pilecap ditentukan dari posisi tiang + e_min di luar = error.

            # Hitung batas pilecap dari bounding box tiang + sedikit margin:
            # Ini dicek di halaman 7_Pilecap.py ketika origin ditetapkan.
            # Di sini: validasi jarak xi dan yi terhadap batas [0, Lx] × [0, Ly]
            # Asumsikan koordinat tiang sudah dalam sistem (0,0) = sudut kiri-bawah pilecap.
            tepi_kiri  = xi
            tepi_kanan = self.Lx - xi
            tepi_bawah = yi
            tepi_atas  = self.Ly - yi
            e_aktual   = min(tepi_kiri, tepi_kanan, tepi_bawah, tepi_atas)
            arah_kritis = {
                tepi_kiri  : 'kiri',
                tepi_kanan : 'kanan',
                tepi_bawah : 'bawah',
                tepi_atas  : 'atas',
            }[e_aktual]

            if e_aktual < e_min * 0.999:
                level = 'ERROR'
                pesan = (
                    f"Tiang {i+1}: jarak ke tepi {arah_kritis} = {e_aktual:.3f} m  "
                    f"< e_min = 1.25×D = 1.25×{D_m:.3f} = {e_min:.3f} m  "
                    f"→ TIDAK MEMENUHI SNI 8460:2017 Ps. 7.4"
                )
            elif e_aktual < e_min * 1.05:
                level = 'WARNING'
                pesan = (
                    f"Tiang {i+1}: jarak ke tepi {arah_kritis} = {e_aktual:.3f} m  "
                    f"≈ e_min = {e_min:.3f} m  (margin sempit)"
                )
            else:
                level = 'OK'
                pesan = (
                    f"Tiang {i+1}: jarak ke tepi {arah_kritis} = {e_aktual:.3f} m  "
                    f"≥ e_min = {e_min:.3f} m  ✓"
                )

            hasil.append({
                'tipe'         : 'ke_tepi',
                'level'        : level,
                'pesan'        : pesan,
                'nilai'        : round(e_aktual, 4),
                'minimum'      : round(e_min, 4),
                'tiang'        : i + 1,
                'arah_kritis'  : arah_kritis,
            })

        return hasil

    def ringkasan_validasi(self) -> Dict:
        """
        Ringkasan hasil validasi: total OK / WARNING / ERROR.

        Return
        ------
        {
          'total_cek': int,
          'OK'       : int,
          'WARNING'  : int,
          'ERROR'    : int,
          'status'   : 'AMAN' | 'PERLU DITINJAU' | 'TIDAK AMAN',
        }
        """
        hasil = self.validasi_jarak()
        ok      = sum(1 for h in hasil if h['level'] == 'OK')
        warning = sum(1 for h in hasil if h['level'] == 'WARNING')
        error   = sum(1 for h in hasil if h['level'] == 'ERROR')

        if error > 0:
            status = 'TIDAK AMAN'
        elif warning > 0:
            status = 'PERLU DITINJAU'
        else:
            status = 'AMAN'

        return {
            'total_cek' : len(hasil),
            'OK'        : ok,
            'WARNING'   : warning,
            'ERROR'     : error,
            'status'    : status,
        }

    # -----------------------------------------------------------------------
    # PLOT DENAH PILECAP
    # -----------------------------------------------------------------------
    def plot_denah(
        self,
        judul        : str  = "Denah Pilecap",
        tampilkan_id : bool = True,
        warna_tiang  : dict = None,   # {idx: 'blue'|'red'|...} override per tiang
    ) -> BytesIO:
        """
        Gambar denah pilecap dengan posisi tiang dan kolom.

        Elemen yang ditampilkan:
          - Batas pilecap (persegi panjang tebal)
          - Tiang: lingkaran bernomor, warna default biru
          - Kolom: kotak abu-abu
          - Centroid grup tiang: tanda (+) berwarna hijau
          - Dimensi Lx & Ly dengan panah
          - Jarak antar tiang (hanya pasangan terdekat)
          - Label sumbu X dan Y

        Konvensi sumbu (PENTING untuk penulangan):
          Arah X → horizontal (kanan)
          Arah Y → vertikal   (atas)
          "Tulangan arah X" = batang membentang ke arah X,
                              berbaris ke arah Y dengan jarak s
          "Tulangan arah Y" = batang membentang ke arah Y,
                              berbaris ke arah X dengan jarak s

        Return
        ------
        BytesIO buffer gambar PNG
        """
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.set_aspect('equal')

        # ---- Batas pilecap ----
        rect = plt.Rectangle(
            (0, 0), self.Lx, self.Ly,
            linewidth=2.0, edgecolor='#1a1a2e', facecolor='#f0f4f8',
            zorder=1
        )
        ax.add_patch(rect)

        # ---- Kolom ----
        for kol in self.kolom_list:
            x0 = kol.xk - kol.bk / 2
            y0 = kol.yk - kol.hk / 2
            rect_kol = plt.Rectangle(
                (x0, y0), kol.bk, kol.hk,
                linewidth=1.5, edgecolor='#374151', facecolor='#9ca3af',
                zorder=3
            )
            ax.add_patch(rect_kol)
            ax.text(
                kol.xk, kol.yk,
                f"K{kol.id_kolom}\n{kol.bk*100:.0f}×{kol.hk*100:.0f}",
                ha='center', va='center',
                fontsize=7, color='white', fontweight='bold',
                zorder=4
            )

        # ---- Tiang pancang ----
        r_tiang = self.D_m / 2
        warna_tiang = warna_tiang or {}
        for i, (xi, yi) in enumerate(self.pile_coords):
            warna = warna_tiang.get(i, '#1e40af')
            lingkaran = plt.Circle(
                (xi, yi), r_tiang,
                linewidth=1.5, edgecolor='#1e3a5f', facecolor=warna,
                alpha=0.85, zorder=5
            )
            ax.add_patch(lingkaran)
            if tampilkan_id:
                ax.text(
                    xi, yi, str(i + 1),
                    ha='center', va='center',
                    fontsize=8, color='white', fontweight='bold', zorder=6
                )

        # ---- Centroid grup tiang ----
        if self.jumlah_tiang > 0:
            x_bar, y_bar = self.centroid_grup()
            ax.plot(
                x_bar, y_bar, marker='+',
                markersize=14, markeredgewidth=2.5,
                color='#16a34a', zorder=7, label=f"Centroid ({x_bar:.3f}, {y_bar:.3f})"
            )

        # ---- Dimensi Lx ----
        offset_dim = max(self.Ly * 0.08, 0.15)
        ax.annotate(
            '', xy=(self.Lx, -offset_dim), xytext=(0, -offset_dim),
            arrowprops=dict(arrowstyle='<->', color='#374151', lw=1.2)
        )
        ax.text(
            self.Lx / 2, -offset_dim - 0.05,
            f"Lx = {self.Lx:.2f} m",
            ha='center', va='top', fontsize=9, color='#374151'
        )

        # ---- Dimensi Ly ----
        offset_dim_y = max(self.Lx * 0.08, 0.15)
        ax.annotate(
            '', xy=(-offset_dim_y, self.Ly), xytext=(-offset_dim_y, 0),
            arrowprops=dict(arrowstyle='<->', color='#374151', lw=1.2)
        )
        ax.text(
            -offset_dim_y - 0.05, self.Ly / 2,
            f"Ly = {self.Ly:.2f} m",
            ha='right', va='center', fontsize=9, color='#374151', rotation=90
        )

        # ---- Arah X dan Y ----
        margin_ax = 0.12
        ax.annotate(
            'X (+)', xy=(self.Lx + margin_ax + 0.2, 0.1),
            xytext=(self.Lx + margin_ax, 0.1),
            arrowprops=dict(arrowstyle='->', color='#dc2626', lw=1.5),
            fontsize=8, color='#dc2626', fontweight='bold'
        )
        ax.annotate(
            'Y (+)', xy=(0.1, self.Ly + margin_ax + 0.2),
            xytext=(0.1, self.Ly + margin_ax),
            arrowprops=dict(arrowstyle='->', color='#dc2626', lw=1.5),
            fontsize=8, color='#dc2626', fontweight='bold'
        )

        # ---- Keterangan konvensi tulangan ----
        keterangan = (
            "Konvensi tulangan:\n"
            "  Arah X: batang membentang → arah X, berbaris ke arah Y\n"
            "  Arah Y: batang membentang ↑ arah Y, berbaris ke arah X"
        )
        ax.text(
            0.01, 0.01, keterangan,
            transform=ax.transAxes,
            fontsize=7.5, color='#374151',
            verticalalignment='bottom',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#fffbeb', alpha=0.8)
        )

        # ---- Legenda & info ----
        patch_pc    = mpatches.Patch(facecolor='#f0f4f8', edgecolor='#1a1a2e', label=f'Pilecap {self.Lx:.2f}×{self.Ly:.2f}×{self.t:.2f} m')
        patch_tiang = mpatches.Patch(facecolor='#1e40af', label=f'Tiang Ø{self.diameter_pile:.0f} mm (n={self.jumlah_tiang})')
        patch_kol   = mpatches.Patch(facecolor='#9ca3af', edgecolor='#374151', label='Kolom')
        patch_cen   = mpatches.Patch(facecolor='#16a34a', label='Centroid grup tiang')
        ax.legend(
            handles=[patch_pc, patch_tiang, patch_kol, patch_cen],
            loc='upper right', fontsize=7.5, framealpha=0.9
        )

        # ---- Pengaturan axes ----
        pad = max(self.Lx, self.Ly) * 0.20 + 0.3
        ax.set_xlim(-pad, self.Lx + pad)
        ax.set_ylim(-pad, self.Ly + pad)
        ax.set_xlabel("Arah X (m)", fontsize=10)
        ax.set_ylabel("Arah Y (m)", fontsize=10)
        ax.set_title(judul, fontsize=12, fontweight='bold', pad=12)
        ax.grid(True, linestyle='--', alpha=0.4, color='#94a3b8')
        ax.tick_params(labelsize=8)

        plt.tight_layout()

        # ---- Simpan ke buffer ----
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        return buf

    # -----------------------------------------------------------------------
    # RINGKASAN TABEL GEOMETRI
    # -----------------------------------------------------------------------
    def ringkasan_dimensi(self) -> Dict:
        """
        Ringkasan dimensi dan properti geometri pilecap.

        Return: dict berisi semua nilai penting untuk ditampilkan di UI.
        """
        x_bar, y_bar = self.centroid_grup()
        return {
            'Lx (m)'               : self.Lx,
            'Ly (m)'               : self.Ly,
            't (m)'                : self.t,
            'f\'c (MPa)'           : self.fc,
            'fy (MPa)'             : self.fy,
            'Cover (mm)'           : self.cover,
            'D tiang (mm)'         : self.diameter_pile,
            'Jumlah tiang'         : self.jumlah_tiang,
            'Centroid X (m)'       : round(x_bar, 4),
            'Centroid Y (m)'       : round(y_bar, 4),
            'Ix grup (m²)'         : round(self.Ix_grup(), 4),
            'Iy grup (m²)'         : round(self.Iy_grup(), 4),
            's_min antar tiang (m)': round(self.s_min_m, 4),
            'e_min ke tepi (m)'    : round(self.e_min_m, 4),
        }
