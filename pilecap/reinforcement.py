"""
pilecap/reinforcement.py
========================
Modul perhitungan penulangan pilecap sesuai SNI 2847:2019.

Lingkup perhitungan:
  1. Momen lentur desain (Mu) arah X dan Y
  2. Tulangan bawah arah X dan Y (lentur)
  3. Tulangan atas arah X dan Y (jika ada tiang tarik / minimum susut)
  4. Tulangan badan/sisi (jika t > 900 mm)
  5. Rekap tabel penulangan

Konvensi notasi tulangan yang KONSISTEN digunakan di seluruh program:
  ┌─────────────────────────────────────────────────────────────────┐
  │  "Tulangan bawah arah X: D16-200"                              │
  │                                                                 │
  │  Artinya:                                                       │
  │    • Batang tulangan MEMBENTANG ke arah SUMBU X (panjang ≈ Lx) │
  │    • Dipasang BERBARIS ke arah Y dengan JARAK 200 mm           │
  │    • BUKAN tulangan yang dipasang berbaris ke arah X           │
  │                                                                 │
  │  "Tulangan bawah arah Y: D16-150"                              │
  │    • Batang tulangan MEMBENTANG ke arah SUMBU Y (panjang ≈ Ly) │
  │    • Dipasang BERBARIS ke arah X dengan JARAK 150 mm           │
  └─────────────────────────────────────────────────────────────────┘

Standar: SNI 2847:2019
  Ps. 9.6.1   — Tulangan minimum lentur
  Ps. 22.5    — Geser satu arah
  Ps. 22.6    — Geser dua arah
  Ps. 24.4    — Tulangan susut dan suhu
  Ps. 9.7.2.3 — Tulangan badan (skin reinforcement)
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional

from pilecap.geometry import PilecapGeometry, DataKolom
from pilecap.pile_forces import HasilGayaTiang, ringkasan_gaya_tiang
from pilecap.shear_check import DEfektif


# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------
PHI_LENTUR  = 0.90    # faktor reduksi lentur (SNI 2847:2019 Tabel 21.2.1)
GAMMA_BETON = 25.0    # kN/m³

# Pilihan diameter tulangan standar Indonesia (mm)
DIAMETER_STANDAR = [10, 13, 16, 19, 22, 25, 29, 32]

# Jarak tulangan standar yang dicoba (mm)
JARAK_STANDAR = [75, 100, 125, 150, 175, 200, 225, 250, 300]


# ---------------------------------------------------------------------------
# Dataclass hasil tulangan satu komponen
# ---------------------------------------------------------------------------
@dataclass
class HasilTulangan:
    """
    Hasil perhitungan tulangan untuk satu posisi/arah.

    Notasi output WAJIB disertakan:
      label_notasi : misal "D16-200"
      penjelasan   : "Batang Ø16 mm membentang searah X, berbaris ke Y jarak 200 mm"
    """
    posisi       : str     # 'Bawah-X' | 'Bawah-Y' | 'Atas-X' | 'Atas-Y' | 'Badan-X' | 'Badan-Y'
    Mu           : float   # momen desain (kNm), 0 untuk badan
    Rn           : float   # kNm/m² atau N/mm²
    rho          : float   # rasio tulangan hitung
    rho_min      : float   # rasio tulangan minimum
    rho_pakai    : float   # max(rho, rho_min)
    As_perlu     : float   # mm²
    b_mm         : float   # lebar tinjauan (mm)
    d_mm         : float   # tinggi efektif (mm)
    D_tul        : int     # diameter tulangan terpilih (mm)
    s_tul        : int     # jarak tulangan terpilih (mm)
    As_pasang    : float   # mm²
    rasio_As     : float   # As_pasang / As_perlu
    OK           : bool
    label_notasi : str     # "D16-200"
    penjelasan   : str     # keterangan lengkap
    detail_rumus : List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fungsi bantu: pilih diameter & jarak tulangan
# ---------------------------------------------------------------------------
def _pilih_tulangan(As_perlu: float, b_mm: float) -> Tuple[int, int, float]:
    """
    Pilih kombinasi diameter dan jarak tulangan sehingga As_pasang ≥ As_perlu.

    Prioritas: jarak tidak terlalu rapat (≥ 75mm) dan diameter umum.
    Kembalikan (D_tul, s_tul, As_pasang) dalam mm.
    """
    pilihan_terbaik = None
    for D in DIAMETER_STANDAR:
        As_per_batang = math.pi / 4 * D**2
        for s in JARAK_STANDAR:
            n_batang  = b_mm / s
            As_pasang = As_per_batang * n_batang
            if As_pasang >= As_perlu:
                if pilihan_terbaik is None or s > pilihan_terbaik[1]:
                    pilihan_terbaik = (D, s, As_pasang)
                break  # jarak paling besar yang memenuhi untuk D ini

    if pilihan_terbaik is None:
        # Paksa D32-75 sebagai fallback
        D = 32; s = 75
        As_pasang = (math.pi / 4 * D**2) * (b_mm / s)
        return D, s, As_pasang

    return pilihan_terbaik


# ---------------------------------------------------------------------------
# Fungsi: hitung momen desain (Mu) arah X dan Y
# ---------------------------------------------------------------------------
def hitung_momen_desain(
    geom        : PilecapGeometry,
    hasil_tiang : List[HasilGayaTiang],
) -> Tuple[float, float, List[str], List[str]]:
    """
    Hitung momen lentur desain Mu_x dan Mu_y di muka kolom.

    Mu_x = momen pada potongan tegak lurus X (potongan sejajar Y, di muka kolom arah X)
           = ΣPi × ei_x
           ei_x = jarak pusat tiang ke muka kolom arah X
                  (hanya tiang yang berada di LUAR muka kolom)

    Mu_y = momen pada potongan tegak lurus Y
           = ΣPi × ei_y

    Untuk multi-kolom: cari muka kolom yang menghasilkan Mu terbesar (konservatif).

    Catatan:
      Momen Mu_x menyebabkan LENTUR pada bidang tegak lurus X
      → tulangan yang menahan: TULANGAN ARAH X (membentang ke arah X)
      Momen Mu_y → tulangan ARAH Y (membentang ke arah Y)

    Return
    ------
    (Mu_x_max, Mu_y_max, detail_x, detail_y) — kNm
    """
    detail_x = []
    detail_y = []

    detail_x.append("")
    detail_x.append("  MOMEN LENTUR DESAIN ARAH X (Mu_x)")
    detail_x.append("  " + "─"*55)
    detail_x.append("  Mu_x = ΣPi × ei_x")
    detail_x.append("  ei_x = jarak tiang ke muka kolom arah X (hanya tiang di luar muka kolom)")
    detail_x.append("  Momen ini direspon oleh TULANGAN ARAH X (batang membentang ke arah X)")
    detail_x.append("")

    detail_y.append("")
    detail_y.append("  MOMEN LENTUR DESAIN ARAH Y (Mu_y)")
    detail_y.append("  " + "─"*55)
    detail_y.append("  Mu_y = ΣPi × ei_y")
    detail_y.append("  Momen ini direspon oleh TULANGAN ARAH Y (batang membentang ke arah Y)")
    detail_y.append("")

    Mu_x_max = 0.0
    Mu_y_max = 0.0

    # Untuk setiap kolom, hitung momen dan ambil yang terbesar
    for kol in geom.kolom_list:
        muka_kiri  = kol.xk - kol.bk / 2
        muka_kanan = kol.xk + kol.bk / 2
        muka_bawah = kol.yk - kol.hk / 2
        muka_atas  = kol.yk + kol.hk / 2

        detail_x.append(f"  Kolom {kol.id_kolom}: muka kiri x={muka_kiri:.3f}m, muka kanan x={muka_kanan:.3f}m")
        detail_y.append(f"  Kolom {kol.id_kolom}: muka bawah y={muka_bawah:.3f}m, muka atas y={muka_atas:.3f}m")

        # Momen dari kiri (tiang di sebelah kiri muka kiri kolom)
        Mu_x_kiri = 0.0
        for h in hasil_tiang:
            if h.x < muka_kiri:
                ei_x = muka_kiri - h.x
                kontrib = abs(h.Pi) * ei_x
                Mu_x_kiri += kontrib
                detail_x.append(f"    Tiang {h.no_tiang}: x={h.x:.3f}m < {muka_kiri:.3f}m → ei_x={ei_x:.3f}m, Pi={h.Pi:.2f}kN, M={kontrib:.2f}kNm")

        # Momen dari kanan (tiang di sebelah kanan muka kanan kolom)
        Mu_x_kanan = 0.0
        for h in hasil_tiang:
            if h.x > muka_kanan:
                ei_x = h.x - muka_kanan
                kontrib = abs(h.Pi) * ei_x
                Mu_x_kanan += kontrib
                detail_x.append(f"    Tiang {h.no_tiang}: x={h.x:.3f}m > {muka_kanan:.3f}m → ei_x={ei_x:.3f}m, Pi={h.Pi:.2f}kN, M={kontrib:.2f}kNm")

        Mu_x_kol = max(Mu_x_kiri, Mu_x_kanan)
        detail_x.append(f"  Mu_x (kiri)={Mu_x_kiri:.2f} kNm, Mu_x (kanan)={Mu_x_kanan:.2f} kNm")
        detail_x.append(f"  Mu_x Kolom {kol.id_kolom} menentukan = {Mu_x_kol:.2f} kNm")
        detail_x.append("")
        Mu_x_max = max(Mu_x_max, Mu_x_kol)

        # Arah Y — momen dari bawah dan atas
        Mu_y_bawah = 0.0
        for h in hasil_tiang:
            if h.y < muka_bawah:
                ei_y = muka_bawah - h.y
                kontrib = abs(h.Pi) * ei_y
                Mu_y_bawah += kontrib
                detail_y.append(f"    Tiang {h.no_tiang}: y={h.y:.3f}m < {muka_bawah:.3f}m → ei_y={ei_y:.3f}m, M={kontrib:.2f}kNm")

        Mu_y_atas = 0.0
        for h in hasil_tiang:
            if h.y > muka_atas:
                ei_y = h.y - muka_atas
                kontrib = abs(h.Pi) * ei_y
                Mu_y_atas += kontrib
                detail_y.append(f"    Tiang {h.no_tiang}: y={h.y:.3f}m > {muka_atas:.3f}m → ei_y={ei_y:.3f}m, M={kontrib:.2f}kNm")

        Mu_y_kol = max(Mu_y_bawah, Mu_y_atas)
        detail_y.append(f"  Mu_y (bawah)={Mu_y_bawah:.2f} kNm, Mu_y (atas)={Mu_y_atas:.2f} kNm")
        detail_y.append(f"  Mu_y Kolom {kol.id_kolom} menentukan = {Mu_y_kol:.2f} kNm")
        detail_y.append("")
        Mu_y_max = max(Mu_y_max, Mu_y_kol)

    detail_x.append(f"  ➤  Mu_x desain (menentukan) = {Mu_x_max:.2f} kNm")
    detail_y.append(f"  ➤  Mu_y desain (menentukan) = {Mu_y_max:.2f} kNm")

    return Mu_x_max, Mu_y_max, detail_x, detail_y


# ---------------------------------------------------------------------------
# Fungsi: hitung tulangan lentur satu arah
# ---------------------------------------------------------------------------
def _hitung_tul_lentur(
    posisi  : str,
    Mu_kNm  : float,
    b_mm    : float,
    d_mm    : float,
    fc      : float,
    fy      : float,
    arah    : str,   # 'X' atau 'Y'
) -> HasilTulangan:
    """
    Hitung tulangan lentur untuk satu posisi dan arah.

    Rumus:
      Rn  = Mu×10⁶ / (φ × b × d²)        [N/mm²]
      ρ   = 0.85×f'c/fy × [1 − √(1 − 2Rn/(0.85×f'c))]
      ρmin= max(0.25×√f'c/fy, 1.4/fy)   [SNI 2847:2019 Ps. 9.6.1]
      As  = max(ρ, ρmin) × b × d          [mm²]
    """
    detail = []
    detail.append(f"  Tulangan {posisi}:")
    detail.append(f"  b = {b_mm:.1f} mm, d = {d_mm:.1f} mm, Mu = {Mu_kNm:.2f} kNm")
    detail.append(f"  φ = {PHI_LENTUR}, f'c = {fc:.1f} MPa, fy = {fy:.1f} MPa")
    detail.append("")

    Mu_Nmm = Mu_kNm * 1e6   # konversi kNm → N·mm

    # Rn
    Rn = Mu_Nmm / (PHI_LENTUR * b_mm * d_mm**2)
    detail.append(f"  Rn = Mu / (φ × b × d²)")
    detail.append(f"  Rn = {Mu_Nmm:.2e} / ({PHI_LENTUR} × {b_mm:.1f} × {d_mm:.1f}²)")
    detail.append(f"  Rn = {Mu_Nmm:.2e} / {PHI_LENTUR * b_mm * d_mm**2:.2e}")
    detail.append(f"  Rn = {Rn:.4f} N/mm²  (MPa)")
    detail.append("")

    # ρ
    faktor = 2 * Rn / (0.85 * fc)
    if faktor > 1.0:
        # Momen terlalu besar untuk penampang — perlu perkuat
        rho = 0.85 * fc / fy * (1 - 0.0)
        detail.append(f"  ⚠ PERINGATAN: 2Rn/(0.85f'c) = {faktor:.4f} > 1.0")
        detail.append(f"  Penampang mungkin tidak cukup — pertimbangkan perkuatan")
    else:
        rho = 0.85 * fc / fy * (1 - math.sqrt(1 - faktor))

    detail.append(f"  ρ = 0.85×f'c/fy × [1 − √(1 − 2Rn/(0.85×f'c))]")
    detail.append(f"  ρ = 0.85×{fc:.1f}/{fy:.1f} × [1 − √(1 − 2×{Rn:.4f}/(0.85×{fc:.1f}))]")
    detail.append(f"  ρ = {0.85*fc/fy:.6f} × [1 − √(1 − {faktor:.6f})]")
    detail.append(f"  ρ = {rho:.6f}")
    detail.append("")

    # ρmin — SNI 2847:2019 Pasal 9.6.1
    rho_min_1 = 0.25 * math.sqrt(fc) / fy
    rho_min_2 = 1.4 / fy
    rho_min   = max(rho_min_1, rho_min_2)
    detail.append(f"  ρmin = max(0.25√f'c/fy, 1.4/fy)  [SNI 2847:2019 Ps. 9.6.1]")
    detail.append(f"  ρmin = max(0.25×√{fc:.1f}/{fy:.1f}, 1.4/{fy:.1f})")
    detail.append(f"  ρmin = max({rho_min_1:.6f}, {rho_min_2:.6f})")
    detail.append(f"  ρmin = {rho_min:.6f}")
    detail.append("")

    rho_pakai = max(rho, rho_min)
    detail.append(f"  ρ_pakai = max(ρ, ρmin) = max({rho:.6f}, {rho_min:.6f}) = {rho_pakai:.6f}")
    detail.append("")

    # As perlu
    As_perlu = rho_pakai * b_mm * d_mm
    detail.append(f"  As_perlu = ρ_pakai × b × d")
    detail.append(f"  As_perlu = {rho_pakai:.6f} × {b_mm:.1f} × {d_mm:.1f}")
    detail.append(f"  As_perlu = {As_perlu:.2f} mm²")
    detail.append("")

    # Pilih tulangan
    D_tul, s_tul, As_pasang = _pilih_tulangan(As_perlu, b_mm)
    As_per_batang = math.pi / 4 * D_tul**2
    n_batang = b_mm / s_tul

    detail.append(f"  Pilih tulangan: D{D_tul}-{s_tul}")
    detail.append(f"  As per batang = π/4 × D² = π/4 × {D_tul}² = {As_per_batang:.2f} mm²")
    detail.append(f"  Jumlah batang = b/s = {b_mm:.1f}/{s_tul} = {n_batang:.2f} batang")
    detail.append(f"  As_pasang = {As_per_batang:.2f} × {n_batang:.2f} = {As_pasang:.2f} mm²")
    detail.append(f"  Cek: As_pasang ({As_pasang:.2f}) ≥ As_perlu ({As_perlu:.2f}) mm²  → {'OK ✓' if As_pasang >= As_perlu else 'TIDAK OK ✗'}")
    detail.append("")

    rasio_As = As_pasang / As_perlu if As_perlu > 0 else 1.0

    # Notasi dan penjelasan konvensi (WAJIB ditampilkan)
    label = f"D{D_tul}-{s_tul}"
    if arah == 'X':
        penjelasan = (
            f"D{D_tul}-{s_tul}  →  Batang Ø{D_tul} mm MEMBENTANG ke arah X (panjang ≈ Lx = {b_mm/1000:.2f} m ... bukan!, b di sini = Ly), "
            f"dipasang BERBARIS ke arah Y dengan jarak {s_tul} mm antar batang."
        )
        if 'Bawah' in posisi:
            penjelasan = (
                f"D{D_tul}-{s_tul}  →  Batang Ø{D_tul} mm MEMBENTANG ke arah SUMBU X "
                f"(panjang batang ≈ Lx), dipasang BERBARIS ke arah Y jarak {s_tul} mm."
            )
        elif 'Atas' in posisi:
            penjelasan = (
                f"D{D_tul}-{s_tul}  →  Batang Ø{D_tul} mm MEMBENTANG ke arah SUMBU X (atas), "
                f"dipasang BERBARIS ke arah Y jarak {s_tul} mm."
            )
    else:
        if 'Bawah' in posisi:
            penjelasan = (
                f"D{D_tul}-{s_tul}  →  Batang Ø{D_tul} mm MEMBENTANG ke arah SUMBU Y "
                f"(panjang batang ≈ Ly), dipasang BERBARIS ke arah X jarak {s_tul} mm."
            )
        elif 'Atas' in posisi:
            penjelasan = (
                f"D{D_tul}-{s_tul}  →  Batang Ø{D_tul} mm MEMBENTANG ke arah SUMBU Y (atas), "
                f"dipasang BERBARIS ke arah X jarak {s_tul} mm."
            )
        else:
            penjelasan = f"D{D_tul}-{s_tul}  arah Y"

    detail.append(f"  ╔══════════════════════════════════════════════════╗")
    detail.append(f"  ║  HASIL: {label:<40}  ║")
    detail.append(f"  ║  {penjelasan[:48]:<48}  ║")
    detail.append(f"  ╚══════════════════════════════════════════════════╝")

    return HasilTulangan(
        posisi=posisi, Mu=Mu_kNm, Rn=Rn, rho=rho, rho_min=rho_min,
        rho_pakai=rho_pakai, As_perlu=As_perlu, b_mm=b_mm, d_mm=d_mm,
        D_tul=D_tul, s_tul=s_tul, As_pasang=As_pasang, rasio_As=rasio_As,
        OK=(As_pasang >= As_perlu), label_notasi=label, penjelasan=penjelasan,
        detail_rumus=detail,
    )


# ---------------------------------------------------------------------------
# Fungsi: hitung tulangan atas
# ---------------------------------------------------------------------------
def _hitung_tul_atas(
    posisi     : str,
    arah       : str,
    b_mm       : float,
    t_mm       : float,
    d_atas_mm  : float,
    fc         : float,
    fy         : float,
    Pi_tarik   : List[float],
) -> HasilTulangan:
    """
    Hitung tulangan atas.

    Jika ada tiang tarik → As_atas dari gaya tarik total.
    Minimum selalu: As_min = 0.0018 × b × t  (susut & suhu, SNI 2847:2019 Ps. 24.4)
    """
    detail = []
    detail.append(f"  Tulangan {posisi}:")

    # Dari gaya tarik tiang
    Ptarik_total = sum(abs(p) for p in Pi_tarik)
    if Ptarik_total > 0:
        As_tarik = Ptarik_total * 1000 / fy   # mm² (P dalam kN → N = ×1000)
        detail.append(f"  Ada tiang tarik: ΣPtarik = {Ptarik_total:.2f} kN")
        detail.append(f"  As_tarik = ΣPtarik / fy = {Ptarik_total*1000:.2f} / {fy:.1f} = {As_tarik:.2f} mm²")
    else:
        As_tarik = 0.0
        detail.append(f"  Tidak ada tiang tarik → As dari gaya tarik = 0")

    # Minimum susut & suhu — SNI 2847:2019 Ps. 24.4
    rho_susut = 0.0018
    As_min = rho_susut * b_mm * t_mm
    detail.append(f"  As_min susut & suhu = 0.0018 × b × t")
    detail.append(f"  As_min = 0.0018 × {b_mm:.1f} × {t_mm:.1f} = {As_min:.2f} mm²")

    As_perlu = max(As_tarik, As_min)
    detail.append(f"  As_perlu = max(As_tarik, As_min) = max({As_tarik:.2f}, {As_min:.2f}) = {As_perlu:.2f} mm²")

    D_tul, s_tul, As_pasang = _pilih_tulangan(As_perlu, b_mm)
    As_per_batang = math.pi / 4 * D_tul**2
    n_batang = b_mm / s_tul
    rasio_As  = As_pasang / As_perlu if As_perlu > 0 else 1.0

    detail.append(f"  Pilih: D{D_tul}-{s_tul}")
    detail.append(f"  As_pasang = {As_per_batang:.2f} × {n_batang:.2f} = {As_pasang:.2f} mm²  → {'OK ✓' if As_pasang >= As_perlu else 'NG ✗'}")

    label = f"D{D_tul}-{s_tul}"
    if arah == 'X':
        penjelasan = (f"D{D_tul}-{s_tul}  →  Batang Ø{D_tul} mm MEMBENTANG ke arah SUMBU X (bagian atas), "
                      f"dipasang BERBARIS ke arah Y jarak {s_tul} mm.")
    else:
        penjelasan = (f"D{D_tul}-{s_tul}  →  Batang Ø{D_tul} mm MEMBENTANG ke arah SUMBU Y (bagian atas), "
                      f"dipasang BERBARIS ke arah X jarak {s_tul} mm.")

    return HasilTulangan(
        posisi=posisi, Mu=0.0, Rn=0.0, rho=0.0, rho_min=rho_susut,
        rho_pakai=rho_susut, As_perlu=As_perlu, b_mm=b_mm, d_mm=d_atas_mm,
        D_tul=D_tul, s_tul=s_tul, As_pasang=As_pasang, rasio_As=rasio_As,
        OK=(As_pasang >= As_perlu), label_notasi=label, penjelasan=penjelasan,
        detail_rumus=detail,
    )


# ---------------------------------------------------------------------------
# Fungsi: tulangan badan (skin reinforcement)
# ---------------------------------------------------------------------------
def _hitung_tul_badan(
    arah          : str,
    b_mm          : float,    # lebar bidang badan (= Lx atau Ly dalam mm)
    t_mm          : float,    # tebal pilecap (mm)
    d_mm          : float,    # d efektif
    As_pokok      : float,    # As tulangan pokok lentur (mm²)
    fc            : float,
    fy            : float,
) -> Optional[HasilTulangan]:
    """
    Tulangan badan (skin reinforcement) jika t > 900 mm.
    SNI 2847:2019 Pasal 9.7.2.3

    As_sisi = 0.1 × As_pokok  (tiap sisi)
    Spasi maks = min(d/6, 300 mm, 1.5×t)
    """
    if t_mm <= 900:
        return None

    detail = []
    detail.append(f"  Tulangan Badan-{arah} (SNI 2847:2019 Ps. 9.7.2.3):")
    detail.append(f"  t = {t_mm:.0f} mm > 900 mm → DIPERLUKAN tulangan badan")
    detail.append("")

    As_sisi = 0.10 * As_pokok
    s_maks1 = d_mm / 6
    s_maks2 = 300.0
    s_maks3 = 1.5 * t_mm
    s_maks  = min(s_maks1, s_maks2, s_maks3)

    detail.append(f"  As_sisi = 0.10 × As_pokok = 0.10 × {As_pokok:.2f} = {As_sisi:.2f} mm²  (per sisi)")
    detail.append(f"  Spasi maks = min(d/6, 300, 1.5t) = min({s_maks1:.1f}, {s_maks2:.1f}, {s_maks3:.1f}) = {s_maks:.1f} mm")

    D_tul, s_tul, As_pasang = _pilih_tulangan(As_sisi, b_mm)
    s_tul = min(s_tul, int(s_maks))
    # Hitung ulang dengan spasi yang dibatasi
    As_pasang = (math.pi / 4 * D_tul**2) * (b_mm / s_tul)

    detail.append(f"  Pilih: D{D_tul}-{s_tul}")
    detail.append(f"  As_pasang = {As_pasang:.2f} mm²  (per sisi)")

    label = f"D{D_tul}-{s_tul} (tiap sisi)"
    if arah == 'X':
        penjelasan = (
            f"D{D_tul}-{s_tul} tiap sisi  →  Batang Ø{D_tul} mm dipasang di SISI VERTIKAL pilecap, "
            f"MEMBENTANG ke arah X, berbaris ke arah Z (tinggi pilecap) jarak {s_tul} mm. "
            f"Dipasang di kedua sisi (depan & belakang arah Y)."
        )
    else:
        penjelasan = (
            f"D{D_tul}-{s_tul} tiap sisi  →  Batang Ø{D_tul} mm dipasang di SISI VERTIKAL pilecap, "
            f"MEMBENTANG ke arah Y, berbaris ke arah Z (tinggi pilecap) jarak {s_tul} mm. "
            f"Dipasang di kedua sisi (kiri & kanan arah X)."
        )

    return HasilTulangan(
        posisi=f"Badan-{arah}", Mu=0.0, Rn=0.0, rho=0.0, rho_min=0.0,
        rho_pakai=0.0, As_perlu=As_sisi, b_mm=b_mm, d_mm=d_mm,
        D_tul=D_tul, s_tul=s_tul, As_pasang=As_pasang, rasio_As=As_pasang/As_sisi,
        OK=(As_pasang >= As_sisi), label_notasi=label, penjelasan=penjelasan,
        detail_rumus=detail,
    )


# ---------------------------------------------------------------------------
# Fungsi utama: hitung semua penulangan
# ---------------------------------------------------------------------------
def hitung_penulangan(
    geom        : PilecapGeometry,
    hasil_tiang : List[HasilGayaTiang],
    d_efektif   : DEfektif,
    Dtul_x      : int = 16,
    Dtul_y      : int = 16,
    Dtul_atas   : int = 13,
) -> Tuple[Dict[str, HasilTulangan], List[str]]:
    """
    Hitung seluruh penulangan pilecap.

    Return
    ------
    (dict_hasil, all_detail)
      dict_hasil : kunci = posisi (Bawah-X, Bawah-Y, Atas-X, Atas-Y, Badan-X, Badan-Y)
    """
    all_detail = []
    all_detail.append("")
    all_detail.append("=" * 60)
    all_detail.append("PERHITUNGAN PENULANGAN PILECAP — SNI 2847:2019")
    all_detail.append("=" * 60)

    fc  = geom.fc
    fy  = geom.fy
    t_mm = geom.t * 1000
    Lx_mm = geom.Lx * 1000
    Ly_mm = geom.Ly * 1000
    ring  = ringkasan_gaya_tiang(hasil_tiang)

    # --- Catatan konvensi ---
    all_detail.append("")
    all_detail.append("  ╔══════════════════════════════════════════════════════════╗")
    all_detail.append("  ║  KONVENSI NOTASI TULANGAN (program ini)                 ║")
    all_detail.append("  ║                                                          ║")
    all_detail.append("  ║  'Tulangan arah X : D16-200'                            ║")
    all_detail.append("  ║   → Batang Ø16 MEMBENTANG ke SUMBU X (panjang ≈ Lx)   ║")
    all_detail.append("  ║   → Dipasang BERBARIS ke arah Y, jarak 200 mm          ║")
    all_detail.append("  ║                                                          ║")
    all_detail.append("  ║  'Tulangan arah Y : D16-150'                            ║")
    all_detail.append("  ║   → Batang Ø16 MEMBENTANG ke SUMBU Y (panjang ≈ Ly)   ║")
    all_detail.append("  ║   → Dipasang BERBARIS ke arah X, jarak 150 mm          ║")
    all_detail.append("  ╚══════════════════════════════════════════════════════════╝")
    all_detail.append("")

    # --- Momen desain ---
    Mu_x, Mu_y, det_mx, det_my = hitung_momen_desain(geom, hasil_tiang)
    all_detail.extend(det_mx)
    all_detail.extend(det_my)

    # --- Tulangan bawah arah X ---
    all_detail.append("")
    all_detail.append("  " + "─"*55)
    all_detail.append("  TULANGAN BAWAH ARAH X")
    all_detail.append("  " + "─"*55)
    # b untuk momen arah X = Ly (lebar potongan sejajar Y)
    tul_bawah_x = _hitung_tul_lentur("Bawah-X", Mu_x, Ly_mm, d_efektif.dx, fc, fy, 'X')
    all_detail.extend(tul_bawah_x.detail_rumus)

    # --- Tulangan bawah arah Y ---
    all_detail.append("")
    all_detail.append("  " + "─"*55)
    all_detail.append("  TULANGAN BAWAH ARAH Y")
    all_detail.append("  " + "─"*55)
    # b untuk momen arah Y = Lx
    tul_bawah_y = _hitung_tul_lentur("Bawah-Y", Mu_y, Lx_mm, d_efektif.dy, fc, fy, 'Y')
    all_detail.extend(tul_bawah_y.detail_rumus)

    # --- Tulangan atas arah X ---
    all_detail.append("")
    all_detail.append("  " + "─"*55)
    all_detail.append("  TULANGAN ATAS ARAH X")
    all_detail.append("  " + "─"*55)
    Pi_tarik = [h.Pi for h in hasil_tiang if h.Pi < 0]
    tul_atas_x = _hitung_tul_atas("Atas-X", 'X', Ly_mm, t_mm, d_efektif.d_atas, fc, fy, Pi_tarik)
    all_detail.extend(tul_atas_x.detail_rumus)

    # --- Tulangan atas arah Y ---
    all_detail.append("")
    all_detail.append("  " + "─"*55)
    all_detail.append("  TULANGAN ATAS ARAH Y")
    all_detail.append("  " + "─"*55)
    tul_atas_y = _hitung_tul_atas("Atas-Y", 'Y', Lx_mm, t_mm, d_efektif.d_atas, fc, fy, Pi_tarik)
    all_detail.extend(tul_atas_y.detail_rumus)

    # --- Tulangan badan ---
    all_detail.append("")
    all_detail.append("  " + "─"*55)
    all_detail.append("  TULANGAN BADAN / SISI (SNI 2847:2019 Ps. 9.7.2.3)")
    all_detail.append("  " + "─"*55)
    tul_badan_x = _hitung_tul_badan('X', Ly_mm, t_mm, d_efektif.dx, tul_bawah_x.As_pasang, fc, fy)
    tul_badan_y = _hitung_tul_badan('Y', Lx_mm, t_mm, d_efektif.dy, tul_bawah_y.As_pasang, fc, fy)
    if tul_badan_x:
        all_detail.extend(tul_badan_x.detail_rumus)
    else:
        all_detail.append(f"  t = {t_mm:.0f} mm ≤ 900 mm → Tulangan badan TIDAK diperlukan")
    if tul_badan_y:
        all_detail.extend(tul_badan_y.detail_rumus)

    # Kumpulkan hasil
    hasil = {
        "Bawah-X": tul_bawah_x,
        "Bawah-Y": tul_bawah_y,
        "Atas-X" : tul_atas_x,
        "Atas-Y" : tul_atas_y,
    }
    if tul_badan_x: hasil["Badan-X"] = tul_badan_x
    if tul_badan_y: hasil["Badan-Y"] = tul_badan_y

    return hasil, all_detail
