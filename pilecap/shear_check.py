"""
pilecap/shear_check.py
======================
Modul cek geser pilecap sesuai SNI 2847:2019.

Cek yang dilakukan:
  1. Geser satu arah (beam shear) arah X — SNI 2847:2019 Pasal 22.5
  2. Geser satu arah (beam shear) arah Y — SNI 2847:2019 Pasal 22.5
  3. Geser dua arah / pons (punching shear) per kolom — SNI 2847:2019 Pasal 22.6

Urutan pemakaian:
  shear_check dipanggil SEBELUM reinforcement, karena:
  - d efektif dihitung di sini (perlu untuk cek geser)
  - Hasil cek geser memengaruhi tebal pilecap (jika NG, pilecap perlu dipertebal)

Notasi:
  t      = tebal pilecap (m)
  cover  = selimut beton (mm)
  dx     = d efektif untuk tulangan arah X (mm)
             dx = t×1000 − cover − 0.5×Dtul_x
  dy     = d efektif untuk tulangan arah Y (mm)
             dy = t×1000 − cover − Dtul_x − 0.5×Dtul_y
  φ_v    = faktor reduksi kuat geser = 0.75  (SNI 2847:2019 Tabel 21.2.1)
  λ      = faktor beton ringan = 1.0 (beton normal)
  f'c    = kuat tekan beton (MPa)
  b      = lebar bidang tinjau (m → dikonversi mm)
  αs     = 40 untuk kolom interior, 30 tepi, 20 sudut
  βc     = rasio sisi panjang / sisi pendek kolom

Standar: SNI 2847:2019 Pasal 22.5 & 22.6
"""

import math
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional

from pilecap.geometry import PilecapGeometry, DataKolom
from pilecap.pile_forces import HasilGayaTiang


# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------
PHI_GESER  = 0.75   # faktor reduksi geser (SNI 2847:2019 Tabel 21.2.1)
PHI_LENTUR = 0.90   # faktor reduksi lentur
LAMBDA     = 1.0    # beton normal
D_TUL_X_DEFAULT = 16.0   # mm, asumsi awal diameter tulangan arah X
D_TUL_Y_DEFAULT = 16.0   # mm, asumsi awal diameter tulangan arah Y


# ---------------------------------------------------------------------------
# Dataclass d efektif
# ---------------------------------------------------------------------------
@dataclass
class DEfektif:
    """
    Tinggi efektif (d) pilecap untuk setiap lapisan tulangan.

    Tulangan bawah arah X dipasang di lapisan terbawah (dx lebih besar).
    Tulangan bawah arah Y di atasnya (dy lebih kecil).

    Rumus:
      dx = t×1000 − cover − 0.5×Dtul_x
      dy = t×1000 − cover − Dtul_x − 0.5×Dtul_y
      d_atas = cover + 0.5×Dtul_atas  (untuk tulangan atas)

    Semua nilai dalam mm.
    """
    t_mm       : float   # tebal pilecap (mm)
    cover      : float   # selimut beton (mm)
    Dtul_x     : float   # diameter tulangan arah X (mm)
    Dtul_y     : float   # diameter tulangan arah Y (mm)
    Dtul_atas  : float   # diameter tulangan atas (mm)
    dx         : float   # d efektif arah X (mm)
    dy         : float   # d efektif arah Y (mm)
    d_atas     : float   # d efektif tulangan atas (mm)
    d_pakai    : float   # d yang dipakai untuk cek geser = min(dx, dy)


# ---------------------------------------------------------------------------
# Dataclass hasil cek geser satu arah
# ---------------------------------------------------------------------------
@dataclass
class HasilGeserSatuArah:
    """
    Hasil cek geser satu arah (beam shear) satu arah.

    Atribut
    -------
    arah           : 'X' atau 'Y'
    Vu             : gaya geser desain (kN)
    phi_Vn         : kuat geser nominal tereduksi (kN)
    status         : 'OK' | 'NG'
    rasio          : Vu / φVn  (< 1.0 = aman)
    bidang_kritis_x: posisi bidang kritis dari tepi pilecap (m) — arah X
    bidang_kritis_y: posisi bidang kritis dari tepi pilecap (m) — arah Y
    tiang_di_luar  : list nomor tiang yang berada di luar bidang kritis
    Pi_di_luar     : list gaya Pi tiang di luar bidang kritis (kN)
    d_pakai        : d efektif yang dipakai (mm)
    b_pakai        : lebar potongan (mm)
    detail_rumus   : list string langkah perhitungan
    """
    arah            : str
    Vu              : float
    phi_Vn          : float
    status          : str
    rasio           : float
    tiang_di_luar   : List[int]
    Pi_di_luar      : List[float]
    d_pakai         : float
    b_pakai         : float
    detail_rumus    : List[str]


# ---------------------------------------------------------------------------
# Dataclass hasil cek pons
# ---------------------------------------------------------------------------
@dataclass
class HasilPons:
    """
    Hasil cek geser dua arah (pons / punching shear) satu kolom.

    αs = 40 kolom interior, 30 tepi, 20 sudut
    βc = rasio sisi panjang/pendek kolom
    bo = keliling bidang kritis (mm)
    """
    id_kolom    : int
    bk_mm       : float    # lebar kolom (mm)
    hk_mm       : float    # tinggi kolom (mm)
    bo          : float    # keliling bidang kritis (mm)
    beta_c      : float    # rasio sisi panjang/pendek kolom
    alpha_s     : int      # 40/30/20 sesuai posisi kolom
    Vu_pons     : float    # gaya geser pons desain (kN)
    Vc1         : float    # kN
    Vc2         : float    # kN
    Vc3         : float    # kN
    Vc_min      : float    # kN (nilai terkecil dari Vc1,Vc2,Vc3)
    phi_Vn      : float    # φ × Vc_min (kN)
    status      : str      # 'OK' | 'NG'
    rasio       : float    # Vu / φVn
    detail_rumus: List[str]


# ---------------------------------------------------------------------------
# Fungsi hitung d efektif
# ---------------------------------------------------------------------------
def hitung_d_efektif(
    t_mm       : float,
    cover      : float,
    Dtul_x     : float = D_TUL_X_DEFAULT,
    Dtul_y     : float = D_TUL_Y_DEFAULT,
    Dtul_atas  : float = 13.0,
) -> Tuple[DEfektif, List[str]]:
    """
    Hitung tinggi efektif (d) pilecap untuk setiap lapisan tulangan.

    Susunan tulangan dari bawah ke atas (selimut beton di bawah):
      ↓ bawah pilecap
      [cover]
      [tulangan arah X — di lapisan pertama, d lebih besar]
      [tulangan arah Y — di lapisan kedua, d lebih kecil]
      [inti beton]
      [tulangan atas]
      [cover]
      ↑ atas pilecap

    Parameter
    ---------
    t_mm     : tebal pilecap dalam mm
    cover    : selimut beton (mm), diukur ke sisi luar tulangan
    Dtul_x   : diameter tulangan arah X (mm)
    Dtul_y   : diameter tulangan arah Y (mm)
    Dtul_atas: diameter tulangan atas (mm)

    Return
    ------
    (DEfektif, List[str])
    """
    detail = []
    detail.append("=" * 60)
    detail.append("TINGGI EFEKTIF (d) PILECAP")
    detail.append("=" * 60)
    detail.append("")
    detail.append("  Susunan lapisan tulangan (dari bawah pilecap):")
    detail.append("  ┌─────────────────────────────────────────────────┐")
    detail.append("  │  [selimut beton = cover]                        │")
    detail.append("  │  ── tulangan arah X (Ø tul_x) ──               │")
    detail.append("  │  ── tulangan arah Y (Ø tul_y) ──               │")
    detail.append("  │  [inti beton]                                   │")
    detail.append("  │  ── tulangan atas ──                            │")
    detail.append("  │  [selimut beton = cover]                        │")
    detail.append("  └─────────────────────────────────────────────────┘")
    detail.append("")
    detail.append("  Rumus d efektif:")
    detail.append("  dx = t − cover − 0.5×Dtul_x")
    detail.append("  dy = t − cover − Dtul_x − 0.5×Dtul_y")
    detail.append("")

    dx = t_mm - cover - 0.5 * Dtul_x
    dy = t_mm - cover - Dtul_x - 0.5 * Dtul_y
    d_atas = cover + 0.5 * Dtul_atas
    d_pakai = min(dx, dy)

    detail.append(f"  dx = {t_mm:.0f} − {cover:.0f} − 0.5×{Dtul_x:.0f}")
    detail.append(f"  dx = {t_mm:.0f} − {cover:.0f} − {0.5*Dtul_x:.1f}")
    detail.append(f"  dx = {dx:.1f} mm")
    detail.append("")
    detail.append(f"  dy = {t_mm:.0f} − {cover:.0f} − {Dtul_x:.0f} − 0.5×{Dtul_y:.0f}")
    detail.append(f"  dy = {t_mm:.0f} − {cover:.0f} − {Dtul_x:.0f} − {0.5*Dtul_y:.1f}")
    detail.append(f"  dy = {dy:.1f} mm")
    detail.append("")
    detail.append(f"  d_atas = cover + 0.5×Dtul_atas = {cover:.0f} + {0.5*Dtul_atas:.1f} = {d_atas:.1f} mm")
    detail.append(f"  d_pakai (untuk cek geser) = min(dx, dy) = min({dx:.1f}, {dy:.1f}) = {d_pakai:.1f} mm")

    d_efektif = DEfektif(
        t_mm=t_mm, cover=cover, Dtul_x=Dtul_x, Dtul_y=Dtul_y,
        Dtul_atas=Dtul_atas, dx=dx, dy=dy, d_atas=d_atas, d_pakai=d_pakai,
    )
    return d_efektif, detail


# ---------------------------------------------------------------------------
# Geser satu arah — satu arah
# ---------------------------------------------------------------------------
def _cek_geser_satu_arah(
    arah          : str,
    geom          : PilecapGeometry,
    hasil_tiang   : List[HasilGayaTiang],
    d_mm          : float,
    fc            : float,
    kolom_list    : List[DataKolom],
) -> HasilGeserSatuArah:
    """
    Hitung dan cek geser satu arah (beam shear) untuk satu arah (X atau Y).

    Bidang kritis berada pada jarak d dari muka kolom.
    Tiang yang berada di LUAR bidang kritis memberikan gaya geser ke pilecap.

    Untuk multi-kolom, bidang kritis diambil dari kolom yang paling menentukan
    (bidang kritis terdekat dengan tiang — kolom terluar).

    Catatan penting tentang bidang kritis:
      - Arah X: potongan tegak lurus arah X, sejajar sumbu Y
        Bidang kritis di: x_muka_kolom − d  (sisi kiri)  dan
                          x_muka_kolom + d  (sisi kanan)
      - Vu_x = ΣPi tiang yang x-koordinatnya di LUAR kedua bidang kritis

    Parameter
    ---------
    arah        : 'X' atau 'Y'
    d_mm        : d efektif yang relevan (dx atau dy) dalam mm
    fc          : f'c beton (MPa)
    """
    d_m   = d_mm / 1000.0   # konversi ke meter
    detail = []
    detail.append("")
    detail.append(f"  CEK GESER SATU ARAH ARAH {arah} (SNI 2847:2019 Ps. 22.5)")
    detail.append(f"  {'─'*55}")
    detail.append(f"  Rumus: φVn = φ × 0.17 × λ × √f'c × b × d")
    detail.append(f"  φ = {PHI_GESER}, λ = {LAMBDA} (beton normal), f'c = {fc:.1f} MPa")
    detail.append(f"  d = d{'x' if arah=='X' else 'y'} = {d_mm:.1f} mm = {d_m:.4f} m")

    # Tentukan lebar b dan arah tinjau
    if arah == 'X':
        b_m   = geom.Ly    # lebar potongan arah Y (m)
        b_mm  = b_m * 1000
        detail.append(f"  b = Ly = {b_m:.3f} m = {b_mm:.1f} mm  (lebar potongan arah Y)")
    else:
        b_m   = geom.Lx
        b_mm  = b_m * 1000
        detail.append(f"  b = Lx = {b_m:.3f} m = {b_mm:.1f} mm  (lebar potongan arah X)")

    # Kuat geser nominal
    phi_Vn_N = PHI_GESER * 0.17 * LAMBDA * math.sqrt(fc) * b_mm * d_mm   # Newton
    phi_Vn   = phi_Vn_N / 1000.0   # kN

    detail.append(f"  φVn = {PHI_GESER} × 0.17 × {LAMBDA} × √{fc:.1f} × {b_mm:.1f} × {d_mm:.1f}")
    detail.append(f"  φVn = {PHI_GESER} × 0.17 × {LAMBDA} × {math.sqrt(fc):.4f} × {b_mm:.1f} × {d_mm:.1f}")
    detail.append(f"  φVn = {phi_Vn_N:.2f} N = {phi_Vn:.2f} kN")

    # Tentukan bidang kritis (dari muka kolom ± d)
    # Untuk multi-kolom: cari batas terluar bidang kritis
    detail.append("")
    detail.append(f"  Bidang kritis (jarak d = {d_m:.4f} m dari muka kolom):")

    batas_luar_min = +999.0   # batas kritis sisi kiri/bawah (paling kecil)
    batas_luar_max = -999.0   # batas kritis sisi kanan/atas (paling besar)

    for kol in kolom_list:
        if arah == 'X':
            muka_kiri  = kol.xk - kol.bk / 2
            muka_kanan = kol.xk + kol.bk / 2
            kritis_kiri  = muka_kiri  - d_m
            kritis_kanan = muka_kanan + d_m
            detail.append(f"  Kolom {kol.id_kolom}: muka kiri={muka_kiri:.3f}m, muka kanan={muka_kanan:.3f}m")
            detail.append(f"             bidang kritis: x={kritis_kiri:.3f}m (kiri) dan x={kritis_kanan:.3f}m (kanan)")
            batas_luar_min = min(batas_luar_min, kritis_kiri)
            batas_luar_max = max(batas_luar_max, kritis_kanan)
        else:
            muka_bawah = kol.yk - kol.hk / 2
            muka_atas  = kol.yk + kol.hk / 2
            kritis_bawah = muka_bawah - d_m
            kritis_atas  = muka_atas  + d_m
            detail.append(f"  Kolom {kol.id_kolom}: muka bawah={muka_bawah:.3f}m, muka atas={muka_atas:.3f}m")
            detail.append(f"             bidang kritis: y={kritis_bawah:.3f}m (bawah) dan y={kritis_atas:.3f}m (atas)")
            batas_luar_min = min(batas_luar_min, kritis_bawah)
            batas_luar_max = max(batas_luar_max, kritis_atas)

    detail.append(f"  Gabungan bidang kritis (multi-kolom): {batas_luar_min:.3f} m s/d {batas_luar_max:.3f} m")

    # Identifikasi tiang di luar bidang kritis
    tiang_luar = []
    Pi_luar    = []
    detail.append("")
    detail.append("  Tiang di luar bidang kritis (berkontribusi ke Vu):")

    for h in hasil_tiang:
        if arah == 'X':
            koord = h.x
            di_luar = (koord < batas_luar_min) or (koord > batas_luar_max)
        else:
            koord = h.y
            di_luar = (koord < batas_luar_min) or (koord > batas_luar_max)

        if di_luar:
            tiang_luar.append(h.no_tiang)
            Pi_luar.append(h.Pi)
            detail.append(f"    Tiang {h.no_tiang}: {'x' if arah=='X' else 'y'} = {koord:.3f} m → DI LUAR → Pi = {h.Pi:.2f} kN")
        else:
            detail.append(f"    Tiang {h.no_tiang}: {'x' if arah=='X' else 'y'} = {koord:.3f} m → di dalam bidang kritis")

    Vu = sum(abs(p) for p in Pi_luar)   # geser = jumlah mutlak Pi tiang di luar

    Pi_str = " + ".join(f"|{p:.2f}|" for p in Pi_luar) if Pi_luar else "0"
    detail.append(f"  Vu_{arah} = Σ|Pi| tiang di luar = {Pi_str}")
    detail.append(f"  Vu_{arah} = {Vu:.2f} kN")
    detail.append("")
    detail.append(f"  CEK: Vu_{arah} ≤ φVn ?")
    detail.append(f"       {Vu:.2f} ≤ {phi_Vn:.2f} kN")

    rasio  = Vu / phi_Vn if phi_Vn > 0 else 999.0
    status = 'OK' if Vu <= phi_Vn else 'NG'

    if status == 'OK':
        detail.append(f"       → AMAN ✓  (rasio = {rasio:.3f} < 1.0)")
    else:
        detail.append(f"       → TIDAK AMAN ✗  (rasio = {rasio:.3f} > 1.0)")
        detail.append(f"       → Pertimbangkan menambah tebal pilecap atau menambah sengkang")

    return HasilGeserSatuArah(
        arah=arah, Vu=Vu, phi_Vn=phi_Vn, status=status, rasio=rasio,
        tiang_di_luar=tiang_luar, Pi_di_luar=Pi_luar,
        d_pakai=d_mm, b_pakai=b_mm, detail_rumus=detail,
    )


# ---------------------------------------------------------------------------
# Geser dua arah / pons
# ---------------------------------------------------------------------------
def _cek_pons_satu_kolom(
    kol         : DataKolom,
    geom        : PilecapGeometry,
    hasil_tiang : List[HasilGayaTiang],
    d_mm        : float,
    fc          : float,
    alpha_s     : int = 40,
) -> HasilPons:
    """
    Cek geser dua arah (pons) untuk satu kolom.

    Bidang kritis berbentuk persegi panjang pada jarak d/2 dari muka kolom.
    Vu_pons = ΣNu − ΣPi tiang yang berada DI DALAM bidang kritis.

    Tiga persamaan Vc (SNI 2847:2019 Ps. 22.6.5.2):
      Vc1 = [0.17(1 + 2/βc)]      × λ × √f'c × bo × d
      Vc2 = [0.083(αs×d/bo + 2)]  × λ × √f'c × bo × d
      Vc3 = 0.33                   × λ × √f'c × bo × d
      Vc_pakai = min(Vc1, Vc2, Vc3)
      φVn = φ × Vc_pakai  (φ = 0.75)
    """
    d_m   = d_mm / 1000.0
    bk_mm = kol.bk * 1000
    hk_mm = kol.hk * 1000

    detail = []
    detail.append(f"  PONS KOLOM {kol.id_kolom} (SNI 2847:2019 Ps. 22.6)")
    detail.append(f"  {'─'*55}")
    detail.append(f"  Dimensi kolom: bk = {bk_mm:.0f} mm, hk = {hk_mm:.0f} mm")
    detail.append(f"  d = {d_mm:.1f} mm")

    # Bidang kritis
    bo = 2 * (bk_mm + d_mm) + 2 * (hk_mm + d_mm)
    detail.append(f"  bo = 2×(bk+d) + 2×(hk+d)")
    detail.append(f"  bo = 2×({bk_mm:.0f}+{d_mm:.1f}) + 2×({hk_mm:.0f}+{d_mm:.1f})")
    detail.append(f"  bo = 2×{bk_mm+d_mm:.1f} + 2×{hk_mm+d_mm:.1f}")
    detail.append(f"  bo = {bo:.2f} mm")

    # Batas bidang kritis (dalam satuan meter)
    x_kritis_kiri  = kol.xk - kol.bk/2 - d_m/2
    x_kritis_kanan = kol.xk + kol.bk/2 + d_m/2
    y_kritis_bawah = kol.yk - kol.hk/2 - d_m/2
    y_kritis_atas  = kol.yk + kol.hk/2 + d_m/2

    detail.append(f"  Bidang kritis: x=[{x_kritis_kiri:.3f}, {x_kritis_kanan:.3f}] m")
    detail.append(f"                 y=[{y_kritis_bawah:.3f}, {y_kritis_atas:.3f}] m")

    # Tiang dalam bidang kritis
    Pi_dalam = []
    detail.append("")
    detail.append("  Tiang dalam bidang kritis (TIDAK masuk Vu_pons):")
    for h in hasil_tiang:
        dalam = (x_kritis_kiri <= h.x <= x_kritis_kanan and
                 y_kritis_bawah <= h.y <= y_kritis_atas)
        if dalam:
            Pi_dalam.append(h.Pi)
            detail.append(f"    Tiang {h.no_tiang}: ({h.x:.3f}, {h.y:.3f}) m → DALAM → Pi = {h.Pi:.2f} kN")
        else:
            detail.append(f"    Tiang {h.no_tiang}: ({h.x:.3f}, {h.y:.3f}) m → di luar")

    # Vu pons = Nu kolom + beban merata (diabaikan konservatif) − Pi dalam
    SigmaPi_dalam = sum(Pi_dalam)
    Vu_pons = kol.Nu - SigmaPi_dalam

    Pi_dalam_str = " + ".join(f"{p:.2f}" for p in Pi_dalam) if Pi_dalam else "0"
    detail.append(f"  Vu_pons = Nu_kolom − ΣPi_dalam")
    detail.append(f"  Vu_pons = {kol.Nu:.2f} − ({Pi_dalam_str})")
    detail.append(f"  Vu_pons = {kol.Nu:.2f} − {SigmaPi_dalam:.2f}")
    detail.append(f"  Vu_pons = {Vu_pons:.2f} kN")
    detail.append("")

    # βc = rasio sisi panjang / sisi pendek
    beta_c = max(bk_mm, hk_mm) / min(bk_mm, hk_mm)
    detail.append(f"  βc = sisi panjang / sisi pendek = {max(bk_mm,hk_mm):.0f}/{min(bk_mm,hk_mm):.0f} = {beta_c:.4f}")
    detail.append(f"  αs = {alpha_s}  (40=interior, 30=tepi, 20=sudut)")

    # Tiga persamaan Vc (dalam N, lalu konversi ke kN)
    faktor1 = 0.17 * (1 + 2.0 / beta_c)
    Vc1_N   = faktor1 * LAMBDA * math.sqrt(fc) * bo * d_mm
    Vc1     = Vc1_N / 1000.0

    faktor2 = 0.083 * (alpha_s * d_mm / bo + 2.0)
    Vc2_N   = faktor2 * LAMBDA * math.sqrt(fc) * bo * d_mm
    Vc2     = Vc2_N / 1000.0

    faktor3 = 0.33
    Vc3_N   = faktor3 * LAMBDA * math.sqrt(fc) * bo * d_mm
    Vc3     = Vc3_N / 1000.0

    Vc_min  = min(Vc1, Vc2, Vc3)
    phi_Vn  = PHI_GESER * Vc_min

    sqrt_fc = math.sqrt(fc)
    detail.append("")
    detail.append("  Tiga persamaan Vc (SNI 2847:2019 Ps. 22.6.5.2):")
    detail.append(f"  √f'c = √{fc:.1f} = {sqrt_fc:.4f} MPa^0.5")
    detail.append("")
    detail.append(f"  Vc1 = [0.17(1 + 2/βc)] × λ × √f'c × bo × d")
    detail.append(f"  Vc1 = [0.17×(1 + 2/{beta_c:.4f})] × {LAMBDA} × {sqrt_fc:.4f} × {bo:.2f} × {d_mm:.1f}")
    detail.append(f"  Vc1 = [{faktor1:.4f}] × {LAMBDA} × {sqrt_fc:.4f} × {bo:.2f} × {d_mm:.1f}")
    detail.append(f"  Vc1 = {Vc1_N:.2f} N = {Vc1:.2f} kN")
    detail.append("")
    detail.append(f"  Vc2 = [0.083(αs×d/bo + 2)] × λ × √f'c × bo × d")
    detail.append(f"  Vc2 = [0.083×({alpha_s}×{d_mm:.1f}/{bo:.2f} + 2)] × {LAMBDA} × {sqrt_fc:.4f} × {bo:.2f} × {d_mm:.1f}")
    detail.append(f"  Vc2 = [{faktor2:.4f}] × {LAMBDA} × {sqrt_fc:.4f} × {bo:.2f} × {d_mm:.1f}")
    detail.append(f"  Vc2 = {Vc2_N:.2f} N = {Vc2:.2f} kN")
    detail.append("")
    detail.append(f"  Vc3 = 0.33 × λ × √f'c × bo × d")
    detail.append(f"  Vc3 = 0.33 × {LAMBDA} × {sqrt_fc:.4f} × {bo:.2f} × {d_mm:.1f}")
    detail.append(f"  Vc3 = {Vc3_N:.2f} N = {Vc3:.2f} kN")
    detail.append("")
    detail.append(f"  Vc_pakai = min(Vc1, Vc2, Vc3) = min({Vc1:.2f}, {Vc2:.2f}, {Vc3:.2f}) = {Vc_min:.2f} kN")
    detail.append(f"  φVn = φ × Vc_pakai = {PHI_GESER} × {Vc_min:.2f} = {phi_Vn:.2f} kN")
    detail.append("")
    detail.append(f"  CEK: Vu_pons ≤ φVn ?")
    detail.append(f"       {Vu_pons:.2f} ≤ {phi_Vn:.2f} kN")

    rasio  = Vu_pons / phi_Vn if phi_Vn > 0 else 999.0
    status = 'OK' if Vu_pons <= phi_Vn else 'NG'

    if status == 'OK':
        detail.append(f"       → AMAN ✓  (rasio = {rasio:.3f})")
    else:
        detail.append(f"       → TIDAK AMAN ✗  (rasio = {rasio:.3f} > 1.0)")

    return HasilPons(
        id_kolom=kol.id_kolom, bk_mm=bk_mm, hk_mm=hk_mm, bo=bo,
        beta_c=beta_c, alpha_s=alpha_s, Vu_pons=Vu_pons,
        Vc1=Vc1, Vc2=Vc2, Vc3=Vc3, Vc_min=Vc_min, phi_Vn=phi_Vn,
        status=status, rasio=rasio, detail_rumus=detail,
    )


# ---------------------------------------------------------------------------
# Fungsi utama: cek semua geser
# ---------------------------------------------------------------------------
def hitung_semua_geser(
    geom          : PilecapGeometry,
    hasil_tiang   : List[HasilGayaTiang],
    d_efektif     : DEfektif,
    alpha_s       : int = 40,
) -> Tuple[HasilGeserSatuArah, HasilGeserSatuArah, List[HasilPons], List[str]]:
    """
    Jalankan semua cek geser pilecap.

    Return
    ------
    (geser_x, geser_y, list_pons, all_detail)
    """
    all_detail = []
    all_detail.append("")
    all_detail.append("=" * 60)
    all_detail.append("CEK GESER PILECAP — SNI 2847:2019")
    all_detail.append("=" * 60)

    # Geser satu arah X
    geser_x = _cek_geser_satu_arah(
        'X', geom, hasil_tiang, d_efektif.dx, geom.fc, geom.kolom_list
    )
    all_detail.extend(geser_x.detail_rumus)

    # Geser satu arah Y
    geser_y = _cek_geser_satu_arah(
        'Y', geom, hasil_tiang, d_efektif.dy, geom.fc, geom.kolom_list
    )
    all_detail.extend(geser_y.detail_rumus)

    # Pons per kolom
    all_detail.append("")
    all_detail.append("  CEK GESER DUA ARAH / PONS")
    list_pons = []
    for kol in geom.kolom_list:
        hp = _cek_pons_satu_kolom(
            kol, geom, hasil_tiang, d_efektif.d_pakai, geom.fc, alpha_s
        )
        list_pons.append(hp)
        all_detail.extend(hp.detail_rumus)
        all_detail.append("")

    return geser_x, geser_y, list_pons, all_detail


# ---------------------------------------------------------------------------
# Fungsi ringkasan status geser
# ---------------------------------------------------------------------------
def ringkasan_geser(
    geser_x    : HasilGeserSatuArah,
    geser_y    : HasilGeserSatuArah,
    list_pons  : List[HasilPons],
) -> Dict:
    """
    Ringkasan status semua cek geser.
    Return: dict {semua_ok, status_x, status_y, status_pons_list, ada_ng}
    """
    status_pons = [p.status for p in list_pons]
    ada_ng = (geser_x.status == 'NG' or geser_y.status == 'NG' or 'NG' in status_pons)
    return {
        'semua_ok'        : not ada_ng,
        'ada_ng'          : ada_ng,
        'status_x'        : geser_x.status,
        'status_y'        : geser_y.status,
        'status_pons_list': status_pons,
        'rasio_x'         : geser_x.rasio,
        'rasio_y'         : geser_y.rasio,
        'rasio_pons_max'  : max(p.rasio for p in list_pons) if list_pons else 0.0,
    }
