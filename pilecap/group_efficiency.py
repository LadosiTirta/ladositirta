"""
pilecap/group_efficiency.py
============================
Modul perhitungan efisiensi grup tiang pancang.

Metode yang tersedia:
  1. Converse-Labarre (default, SNI / umum Indonesia)
  2. Feld (alternatif, untuk perbandingan)

Serta cek kapasitas:
  - Kapasitas grup  : P_grup = η × n × P_ijin_tekan
  - Kapasitas blok  : P_blok berdasarkan kuat geser tanah lempung (cu)
  - Nilai yang menentukan: min(P_grup, P_blok)

Standar acuan:
  SNI 8460:2017  — Persyaratan Perancangan Geoteknik
  Bowles, J.E.  — Foundation Analysis & Design
  Das, B.M.     — Principles of Foundation Engineering

Catatan penggunaan:
  - Efisiensi grup SELALU ≤ 1.0
  - Untuk tiang dalam pasir padat, η bisa mendekati 1.0 atau > 1.0
    (SNI memperbolehkan η = 1.0 untuk pasir padat dengan s ≥ 3D)
  - Kapasitas blok hanya relevan untuk tiang dalam tanah lempung (kohesif)
"""

import math
import itertools
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional

from pilecap.geometry import PilecapGeometry


# ---------------------------------------------------------------------------
# Dataclass hasil efisiensi grup
# ---------------------------------------------------------------------------
@dataclass
class HasilEfisiensiGrup:
    """
    Hasil perhitungan efisiensi grup tiang.

    Atribut
    -------
    metode_CL       : hasil Converse-Labarre
    eta_CL          : nilai efisiensi η metode Converse-Labarre
    metode_Feld     : hasil Feld
    eta_Feld        : nilai efisiensi η metode Feld
    eta_pakai       : η yang dipakai (= eta_CL, default)
    P_grup          : kapasitas grup = η × n × P_ijin_tekan (kN)
    P_blok          : kapasitas blok (kN), hanya berlaku lempung
    P_grup_efektif  : min(P_grup, P_blok) — yang menentukan
    Pmax            : gaya tiang maksimum aktual (kN)
    SigmaPtekan     : total gaya tekan semua tiang (kN)
    cek_Pmax        : 'OK' | 'NG'  (Pmax ≤ η × P_ijin_tekan)
    cek_grup        : 'OK' | 'NG'  (ΣPtekan ≤ P_grup_efektif)
    peringatan      : list pesan peringatan
    ada_peringatan  : bool
    """
    metode_CL       : str
    eta_CL          : float
    metode_Feld     : str
    eta_Feld        : float
    eta_pakai       : float
    P_grup          : float
    P_blok          : float
    P_blok_berlaku  : bool          # False jika tanah pasir (P_blok tidak dipakai)
    P_grup_efektif  : float
    Pmax            : float
    SigmaPtekan     : float
    cek_Pmax        : str
    cek_grup        : str
    peringatan      : List[str]
    ada_peringatan  : bool


# ---------------------------------------------------------------------------
# Fungsi bantu: deteksi susunan grid tiang
# ---------------------------------------------------------------------------
def _deteksi_grid(pile_coords: List[Tuple[float, float]], toleransi: float = 0.05) -> Dict:
    """
    Coba deteksi apakah tiang disusun dalam pola grid (n_baris × n_kolom).

    Parameter
    ---------
    pile_coords : list (x, y) posisi tiang
    toleransi   : toleransi jarak untuk dianggap segaris (m)

    Return
    ------
    dict dengan:
      'is_grid'      : bool
      'n_baris'      : int  (jumlah baris arah Y)
      'n_kolom'      : int  (jumlah kolom arah X)
      's_x'          : float  (jarak antar tiang arah X, m)
      's_y'          : float  (jarak antar tiang arah Y, m)
      's_rata'       : float  (jarak rata-rata untuk Converse-Labarre)
      'peringatan'   : str
    """
    if len(pile_coords) == 0:
        return {'is_grid': False, 'peringatan': 'Tidak ada tiang'}

    x_vals = sorted(set(round(x / toleransi) * toleransi for x, _ in pile_coords))
    y_vals = sorted(set(round(y / toleransi) * toleransi for _, y in pile_coords))

    n_x = len(x_vals)   # unik X → jumlah kolom
    n_y = len(y_vals)   # unik Y → jumlah baris

    # Cek apakah jumlah tiang = n_x × n_y
    is_grid = (n_x * n_y == len(pile_coords))

    # Hitung jarak antar tiang
    if n_x > 1:
        sx_list = [x_vals[i+1] - x_vals[i] for i in range(len(x_vals)-1)]
        s_x = sum(sx_list) / len(sx_list)
    else:
        s_x = 0.0

    if n_y > 1:
        sy_list = [y_vals[i+1] - y_vals[i] for i in range(len(y_vals)-1)]
        s_y = sum(sy_list) / len(sy_list)
    else:
        s_y = 0.0

    s_rata = (s_x + s_y) / 2 if (s_x > 0 and s_y > 0) else max(s_x, s_y)

    peringatan = ""
    if not is_grid:
        peringatan = (
            "Susunan tiang tidak membentuk pola grid (n_baris × n_kolom) yang simetris. "
            "Converse-Labarre dihitung dengan jarak rata-rata antar tiang dan "
            "n_baris/n_kolom diestimasi — hasil mungkin tidak presisi. "
            "Verifikasi manual disarankan."
        )

    return {
        'is_grid' : is_grid,
        'n_baris' : n_y,
        'n_kolom' : n_x,
        's_x'     : s_x,
        's_y'     : s_y,
        's_rata'  : s_rata,
        'peringatan': peringatan,
    }


def _hitung_s_rata_aktual(pile_coords: List[Tuple[float, float]]) -> float:
    """
    Hitung jarak rata-rata dari semua pasangan tiang bersebelahan (jarak minimum per tiang).
    Dipakai jika susunan bukan grid.
    """
    n = len(pile_coords)
    if n <= 1:
        return 0.0

    # Untuk setiap tiang, cari jarak ke tiang terdekat
    jarak_min_per_tiang = []
    for i in range(n):
        xi, yi = pile_coords[i]
        jarak_ke_lain = []
        for j in range(n):
            if i == j:
                continue
            xj, yj = pile_coords[j]
            d = math.hypot(xj - xi, yj - yi)
            jarak_ke_lain.append(d)
        if jarak_ke_lain:
            jarak_min_per_tiang.append(min(jarak_ke_lain))

    return sum(jarak_min_per_tiang) / len(jarak_min_per_tiang)


# ---------------------------------------------------------------------------
# Metode Converse-Labarre
# ---------------------------------------------------------------------------
def efisiensi_converse_labarre(
    geom    : PilecapGeometry,
    detail  : List[str],
) -> Tuple[float, Dict]:
    """
    Hitung efisiensi grup metode Converse-Labarre.

    Rumus:
        η = 1 − θ° × [(n_baris−1)×n_kolom + (n_kolom−1)×n_baris]
                      / (90 × n_baris × n_kolom)
        di mana θ° = arctan(D/s) dalam derajat

    Catatan:
      - θ° = sudut gesekan antara massa tanah di dalam grup dan di luar grup
      - s  = jarak antar tiang (pusat ke pusat)
      - D  = diameter tiang
      - Jika tiang tidak dalam susunan grid → gunakan jarak rata-rata & peringatkan

    Return
    ------
    (eta, dict_info)
    """
    D_m = geom.D_m
    grid = _deteksi_grid(geom.pile_coords)

    detail.append("  Metode Converse-Labarre:")
    detail.append(f"  Rumus: η = 1 − θ° × [(m−1)×n + (n−1)×m] / (90 × m × n)")
    detail.append(f"  di mana θ° = arctan(D/s) dalam derajat, m = n_baris, n = n_kolom")
    detail.append("")

    if grid['is_grid']:
        n_baris = grid['n_baris']
        n_kolom = grid['n_kolom']
        # Jika 2 arah berbeda, pakai rata-rata
        s = (grid['s_x'] + grid['s_y']) / 2 if (grid['s_x'] > 0 and grid['s_y'] > 0) else max(grid['s_x'], grid['s_y'])
        detail.append(f"  Susunan tiang: {n_baris} baris × {n_kolom} kolom (GRID TERDETEKSI ✓)")
        detail.append(f"  Jarak antar tiang arah X: sx = {grid['s_x']:.4f} m")
        detail.append(f"  Jarak antar tiang arah Y: sy = {grid['s_y']:.4f} m")
        detail.append(f"  s_rata = (sx + sy) / 2 = ({grid['s_x']:.4f} + {grid['s_y']:.4f}) / 2 = {s:.4f} m")
    else:
        # Estimasi n_baris dan n_kolom dari jumlah tiang
        n = geom.jumlah_tiang
        n_kolom = max(1, round(math.sqrt(n)))
        n_baris = max(1, math.ceil(n / n_kolom))
        s = _hitung_s_rata_aktual(geom.pile_coords)
        detail.append(f"  ⚠ Susunan tiang BUKAN grid teratur.")
        detail.append(f"  n_baris estimasi = {n_baris}, n_kolom estimasi = {n_kolom}")
        detail.append(f"  s rata-rata (jarak minimum per tiang) = {s:.4f} m")
        if grid['peringatan']:
            detail.append(f"  PERINGATAN: {grid['peringatan']}")

    if s < 1e-6:
        detail.append("  ERROR: jarak antar tiang = 0, tidak dapat menghitung efisiensi.")
        return 1.0, grid

    theta_rad = math.atan(D_m / s)
    theta_deg = math.degrees(theta_rad)

    pembilang = (n_baris - 1) * n_kolom + (n_kolom - 1) * n_baris
    penyebut  = 90.0 * n_baris * n_kolom

    eta = 1.0 - theta_deg * pembilang / penyebut
    eta = min(eta, 1.0)   # η tidak boleh > 1.0
    eta = max(eta, 0.0)   # η tidak boleh negatif

    detail.append("")
    detail.append(f"  θ° = arctan(D/s) = arctan({D_m:.4f}/{s:.4f})")
    detail.append(f"  θ° = arctan({D_m/s:.4f}) = {theta_deg:.4f}°")
    detail.append(f"  Pembilang = (m−1)×n + (n−1)×m = ({n_baris}−1)×{n_kolom} + ({n_kolom}−1)×{n_baris}")
    detail.append(f"            = {(n_baris-1)*n_kolom} + {(n_kolom-1)*n_baris} = {pembilang}")
    detail.append(f"  Penyebut  = 90 × m × n = 90 × {n_baris} × {n_kolom} = {penyebut:.0f}")
    detail.append(f"  η_CL = 1 − {theta_deg:.4f} × {pembilang} / {penyebut:.0f}")
    detail.append(f"  η_CL = 1 − {theta_deg * pembilang / penyebut:.4f}")
    detail.append(f"  η_CL = {eta:.4f}  ({eta*100:.2f}%)")

    grid['n_baris'] = n_baris
    grid['n_kolom'] = n_kolom
    grid['s_pakai'] = s
    grid['theta_deg'] = theta_deg

    return eta, grid


# ---------------------------------------------------------------------------
# Metode Feld
# ---------------------------------------------------------------------------
def efisiensi_feld(
    geom   : PilecapGeometry,
    grid   : Dict,
    detail : List[str],
) -> float:
    """
    Hitung efisiensi grup metode Feld.

    Prinsip:
      Setiap tiang dikurangi 1/16 kapasitasnya untuk setiap tiang
      yang bersebelahan langsung (termasuk diagonal = 8 arah maksimum).

    Rumus:
      η_Feld = [n_total − (1/16) × Σ(jumlah tetangga per tiang)] / n_total

    Return
    ------
    eta_Feld : float
    """
    n_baris = grid.get('n_baris', 1)
    n_kolom = grid.get('n_kolom', 1)
    n       = geom.jumlah_tiang

    detail.append("")
    detail.append("  Metode Feld:")
    detail.append(f"  Prinsip: setiap tiang dikurangi 1/16 kapasitas per tiang bersebelahan")
    detail.append(f"  Tetangga dihitung dari 8 arah (termasuk diagonal)")
    detail.append(f"  η_Feld = [n − (1/16) × Σtetangga] / n")
    detail.append("")

    # Hitung jumlah tetangga per tiang berdasarkan posisi dalam grid
    if grid.get('is_grid', False):
        # Grid teratur: hitung tetangga berdasarkan posisi (sudut, tepi, tengah)
        jumlah_tetangga_total = 0
        for baris in range(n_baris):
            for kolom in range(n_kolom):
                tetangga = 0
                for db in [-1, 0, 1]:
                    for dk in [-1, 0, 1]:
                        if db == 0 and dk == 0:
                            continue
                        if 0 <= baris + db < n_baris and 0 <= kolom + dk < n_kolom:
                            tetangga += 1
                jumlah_tetangga_total += tetangga
                detail.append(
                    f"  Tiang baris {baris+1} kolom {kolom+1}: {tetangga} tetangga"
                )
    else:
        # Non-grid: gunakan jarak untuk menentukan tetangga (jarak ≤ 1.5 × s_rata)
        s_rata = grid.get('s_rata', _hitung_s_rata_aktual(geom.pile_coords))
        batas_tetangga = 1.5 * s_rata
        jumlah_tetangga_total = 0
        for i in range(n):
            xi, yi = geom.pile_coords[i]
            tetangga = 0
            for j in range(n):
                if i == j:
                    continue
                xj, yj = geom.pile_coords[j]
                d = math.hypot(xj - xi, yj - yi)
                if d <= batas_tetangga:
                    tetangga += 1
            jumlah_tetangga_total += tetangga
            detail.append(f"  Tiang {i+1}: {tetangga} tetangga")

    pengurangan = jumlah_tetangga_total / 16.0
    eta_feld = (n - pengurangan) / n
    eta_feld = min(eta_feld, 1.0)
    eta_feld = max(eta_feld, 0.0)

    detail.append(f"  Σ tetangga total = {jumlah_tetangga_total}")
    detail.append(f"  Pengurangan = {jumlah_tetangga_total} / 16 = {pengurangan:.4f} tiang")
    detail.append(f"  η_Feld = ({n} − {pengurangan:.4f}) / {n}")
    detail.append(f"  η_Feld = {eta_feld:.4f}  ({eta_feld*100:.2f}%)")

    return eta_feld


# ---------------------------------------------------------------------------
# Kapasitas blok tiang (untuk tanah lempung / kohesif)
# ---------------------------------------------------------------------------
def kapasitas_blok(
    geom       : PilecapGeometry,
    L_tiang    : float,
    cu         : float,
    detail     : List[str],
) -> float:
    """
    Hitung kapasitas blok grup tiang untuk tanah lempung (metode block failure).

    Rumus (Terzaghi & Peck):
        P_blok = 2 × (Lg + Bg) × L_tiang × cu  +  Lg × Bg × 9 × cu

    di mana:
        Lg  = panjang blok tiang arah Y (jarak antar pusat tiang terluar + D)
        Bg  = lebar  blok tiang arah X (jarak antar pusat tiang terluar + D)
        L_tiang = panjang tiang tertanam (m)
        cu      = kohesi undrained tanah (kN/m²)

    Catatan:
        Kapasitas blok hanya relevan untuk tanah LEMPUNG.
        Untuk tanah PASIR, kapasitas blok tidak menentukan (sangat besar).

    Return
    ------
    P_blok (kN)
    """
    D_m = geom.D_m
    if not geom.pile_coords:
        return 0.0

    x_vals = [x for x, _ in geom.pile_coords]
    y_vals = [y for _, y in geom.pile_coords]

    Bg = (max(x_vals) - min(x_vals)) + D_m   # lebar blok arah X
    Lg = (max(y_vals) - min(y_vals)) + D_m   # panjang blok arah Y

    # Keliling blok
    keliling = 2 * (Lg + Bg)
    P_geser  = keliling * L_tiang * cu
    P_ujung  = Lg * Bg * 9 * cu
    P_blok   = P_geser + P_ujung

    detail.append("")
    detail.append("  Kapasitas blok tiang (untuk tanah lempung):")
    detail.append(f"  Rumus: P_blok = 2(Lg+Bg)×L×cu  +  Lg×Bg×9×cu")
    detail.append(f"  Bg (lebar blok arah X)  = (x_max − x_min) + D = ({max(x_vals):.3f} − {min(x_vals):.3f}) + {D_m:.3f} = {Bg:.3f} m")
    detail.append(f"  Lg (panjang blok arah Y) = (y_max − y_min) + D = ({max(y_vals):.3f} − {min(y_vals):.3f}) + {D_m:.3f} = {Lg:.3f} m")
    detail.append(f"  Keliling blok = 2×(Lg+Bg) = 2×({Lg:.3f}+{Bg:.3f}) = {keliling:.3f} m")
    detail.append(f"  P_geser = {keliling:.3f} × {L_tiang:.2f} × {cu:.2f} = {P_geser:.2f} kN")
    detail.append(f"  P_ujung = {Lg:.3f} × {Bg:.3f} × 9 × {cu:.2f} = {P_ujung:.2f} kN")
    detail.append(f"  P_blok  = {P_geser:.2f} + {P_ujung:.2f} = {P_blok:.2f} kN")

    return P_blok


# ---------------------------------------------------------------------------
# Fungsi utama: hitung efisiensi grup lengkap
# ---------------------------------------------------------------------------
def hitung_efisiensi_grup(
    geom            : PilecapGeometry,
    P_ijin_tekan    : float,
    Pmax            : float,
    SigmaPtekan     : float,
    L_tiang         : float   = 10.0,
    cu              : float   = 0.0,
    jenis_tanah     : str     = "pasir",
) -> Tuple[HasilEfisiensiGrup, List[str]]:
    """
    Hitung efisiensi grup tiang secara lengkap.

    Parameter
    ---------
    geom            : PilecapGeometry
    P_ijin_tekan    : kapasitas ijin tekan tiang tunggal (kN)
    Pmax            : gaya tekan maksimum tiang aktual (kN)
    SigmaPtekan     : total gaya tekan semua tiang (kN)
    L_tiang         : panjang tiang tertanam (m), untuk kapasitas blok
    cu              : kohesi undrained (kN/m²), 0 jika tanah pasir
    jenis_tanah     : 'lempung' | 'pasir'

    Return
    ------
    (HasilEfisiensiGrup, List[str])
    """
    n      = geom.jumlah_tiang
    detail = []

    detail.append("")
    detail.append("=" * 60)
    detail.append("LANGKAH 8 — Efisiensi Grup Tiang")
    detail.append("=" * 60)
    detail.append(f"  Jumlah tiang  : n = {n}")
    detail.append(f"  P_ijin_tekan  : {P_ijin_tekan:.2f} kN/tiang")
    detail.append(f"  Pmax aktual   : {Pmax:.2f} kN")
    detail.append(f"  ΣP_tekan      : {SigmaPtekan:.2f} kN")
    detail.append("")

    peringatan = []

    # --- Converse-Labarre ---
    detail.append("-" * 50)
    eta_CL, grid_info = efisiensi_converse_labarre(geom, detail)
    if grid_info.get('peringatan'):
        peringatan.append(grid_info['peringatan'])

    # --- Feld ---
    detail.append("")
    detail.append("-" * 50)
    eta_Feld = efisiensi_feld(geom, grid_info, detail)

    # Pakai Converse-Labarre sebagai η utama
    eta_pakai = eta_CL
    detail.append("")
    detail.append(f"  η yang dipakai (Converse-Labarre) = {eta_pakai:.4f}")
    detail.append(f"  η Feld (pembanding)               = {eta_Feld:.4f}")

    # --- Kapasitas grup ---
    detail.append("")
    detail.append("-" * 50)
    detail.append("  Kapasitas Grup Tiang:")
    P_grup = eta_pakai * n * P_ijin_tekan
    detail.append(f"  P_grup = η × n × P_ijin_tekan")
    detail.append(f"  P_grup = {eta_pakai:.4f} × {n} × {P_ijin_tekan:.2f}")
    detail.append(f"  P_grup = {P_grup:.2f} kN")

    # --- Kapasitas blok ---
    if jenis_tanah.lower() == "lempung" and cu > 0:
        P_blok = kapasitas_blok(geom, L_tiang, cu, detail)
        P_blok_berlaku = True
        P_grup_efektif = min(P_grup, P_blok)
        detail.append(f"  Kapasitas menentukan = min(P_grup, P_blok) = min({P_grup:.2f}, {P_blok:.2f}) = {P_grup_efektif:.2f} kN")
    else:
        P_blok = P_grup * 10   # sangat besar — tidak menentukan
        P_blok_berlaku = False
        P_grup_efektif = P_grup
        detail.append("")
        detail.append(f"  Tanah PASIR atau cu = 0 → kapasitas blok tidak menentukan")
        detail.append(f"  P_grup_efektif = P_grup = {P_grup_efektif:.2f} kN")

    # --- Cek kapasitas ---
    detail.append("")
    detail.append("-" * 50)
    detail.append("  CEK KAPASITAS GRUP:")

    # Cek 1: Pmax ≤ η × P_ijin_tekan
    P_ijin_tiang_grup = eta_pakai * P_ijin_tekan
    detail.append(f"  Cek 1: Pmax ≤ η × P_ijin_tekan")
    detail.append(f"         {Pmax:.2f} ≤ {eta_pakai:.4f} × {P_ijin_tekan:.2f} = {P_ijin_tiang_grup:.2f} kN")
    if Pmax <= P_ijin_tiang_grup:
        cek_Pmax = 'OK'
        detail.append(f"         → OK ✓  ({Pmax:.2f} ≤ {P_ijin_tiang_grup:.2f})")
    else:
        cek_Pmax = 'NG'
        detail.append(f"         → TIDAK AMAN ✗  ({Pmax:.2f} > {P_ijin_tiang_grup:.2f})")
        peringatan.append(f"Pmax = {Pmax:.2f} kN > η×P_ijin = {P_ijin_tiang_grup:.2f} kN — tiang kelebihan beban!")

    # Cek 2: ΣPtekan ≤ P_grup_efektif
    detail.append(f"  Cek 2: ΣP_tekan ≤ P_grup_efektif")
    detail.append(f"         {SigmaPtekan:.2f} ≤ {P_grup_efektif:.2f} kN")
    if SigmaPtekan <= P_grup_efektif:
        cek_grup = 'OK'
        detail.append(f"         → OK ✓")
    else:
        cek_grup = 'NG'
        detail.append(f"         → TIDAK AMAN ✗  (total gaya tekan melebihi kapasitas grup)")
        peringatan.append(f"ΣP_tekan = {SigmaPtekan:.2f} kN > P_grup = {P_grup_efektif:.2f} kN!")

    hasil = HasilEfisiensiGrup(
        metode_CL       = f"Converse-Labarre: η = {eta_CL:.4f} ({eta_CL*100:.2f}%)",
        eta_CL          = eta_CL,
        metode_Feld     = f"Feld: η = {eta_Feld:.4f} ({eta_Feld*100:.2f}%)",
        eta_Feld        = eta_Feld,
        eta_pakai       = eta_pakai,
        P_grup          = P_grup,
        P_blok          = P_blok,
        P_blok_berlaku  = P_blok_berlaku,
        P_grup_efektif  = P_grup_efektif,
        Pmax            = Pmax,
        SigmaPtekan     = SigmaPtekan,
        cek_Pmax        = cek_Pmax,
        cek_grup        = cek_grup,
        peringatan      = peringatan,
        ada_peringatan  = len(peringatan) > 0,
    )

    return hasil, detail
