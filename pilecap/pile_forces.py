"""
pilecap/pile_forces.py
======================
Modul perhitungan gaya reaksi setiap tiang akibat beban dari semua kolom.

Standar acuan:
  SNI 8460:2017  — Persyaratan Perancangan Geoteknik
  SNI 2847:2019  — Persyaratan Beton Struktural

Rumus pokok gaya aksial tiang ke-i (distribusi linear):
  Pi = ΣNu / n  ±  ΣMuy_total × xi / Σxi²  ±  ΣMux_total × yi / Σyi²

  di mana:
    ΣNu        = total beban aksial (kolom + berat sendiri pilecap + tanah − uplift)
    ΣMuy_total = total momen terhadap sumbu Y (momen kolom + eksentrisitas gaya geser)
    ΣMux_total = total momen terhadap sumbu X
    xi         = jarak tiang ke-i terhadap centroid grup, arah X
    yi         = jarak tiang ke-i terhadap centroid grup, arah Y
    Σxi²       = Iy (momen inersia grup tiang terhadap sumbu Y)
    Σyi²       = Ix (momen inersia grup tiang terhadap sumbu X)

Rumus gaya lateral tiang ke-i (distribusi merata — asumsi kekakuan lateral sama):
  Hxi = ΣVux / n
  Hyi = ΣVuy / n
  Hi  = √(Hxi² + Hyi²)

Konvensi tanda:
  Pi > 0  → TEKAN  (tiang menerima beban ke bawah dari pilecap)
  Pi < 0  → TARIK  (tiang menerima gaya ke atas — uplift)
"""

import math
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional

from pilecap.geometry import PilecapGeometry, DataKolom, KondisiGalian


# ---------------------------------------------------------------------------
# Konstanta fisik
# ---------------------------------------------------------------------------
GAMMA_BETON = 25.0   # kN/m³ — berat jenis beton bertulang
GAMMA_AIR   = 10.0   # kN/m³ — berat jenis air (untuk tekanan uplift)


# ---------------------------------------------------------------------------
# Dataclass hasil gaya per tiang
# ---------------------------------------------------------------------------
@dataclass
class HasilGayaTiang:
    """
    Hasil perhitungan gaya reaksi satu tiang pancang.

    Atribut
    -------
    no_tiang        : nomor urut tiang (mulai 1)
    x, y            : koordinat pusat tiang (m)
    xi, yi          : jarak tiang ke centroid grup (m)
    Pi              : gaya aksial tiang (kN), tekan (+), tarik (−)
    Hxi             : komponen gaya lateral arah X (kN)
    Hyi             : komponen gaya lateral arah Y (kN)
    Hi              : gaya lateral total (kN)
    status_aksial   : 'TEKAN' | 'TARIK'
    status_aksial_cek : 'OK' | 'NG'  (dibanding kapasitas ijin)
    status_lateral  : 'OK' | 'NG'
    P_ijin_tekan    : kapasitas ijin tekan (kN)
    P_ijin_tarik    : kapasitas ijin tarik (kN)
    P_ijin_lateral  : kapasitas ijin lateral (kN)
    """
    no_tiang          : int
    x                 : float
    y                 : float
    xi                : float
    yi                : float
    Pi                : float
    Hxi               : float
    Hyi               : float
    Hi                : float
    status_aksial     : str     # 'TEKAN' atau 'TARIK'
    status_aksial_cek : str     # 'OK' atau 'NG'
    status_lateral    : str     # 'OK' atau 'NG'
    P_ijin_tekan      : float
    P_ijin_tarik      : float
    P_ijin_lateral    : float

    @property
    def status_global(self) -> str:
        """Status keseluruhan tiang: OK jika semua cek lulus."""
        if self.status_aksial_cek == 'NG' or self.status_lateral == 'NG':
            return 'NG'
        return 'OK'


# ---------------------------------------------------------------------------
# Dataclass ringkasan beban total ke pilecap
# ---------------------------------------------------------------------------
@dataclass
class BebanTotal:
    """
    Ringkasan komponen beban total yang bekerja ke pilecap
    setelah memperhitungkan berat sendiri dan tanah.

    Semua nilai dalam kN atau kNm.
    """
    # Komponen beban aksial
    Nu_kolom_list   : List[float]    # Nu tiap kolom (kN)
    W_pilecap       : float          # berat sendiri pilecap (kN)
    W_tanah         : float          # beban tanah di atas pilecap (kN)
    F_uplift        : float          # gaya uplift air (kN), positif ke atas
    SigmaNu         : float          # total ΣNu (kN)

    # Komponen momen total di centroid grup tiang
    SigmaMuy        : float          # total Muy (kNm), menyebabkan ± aksial arah X
    SigmaMux        : float          # total Mux (kNm), menyebabkan ± aksial arah Y

    # Komponen geser total
    SigmaVux        : float          # total ΣVux (kN)
    SigmaVuy        : float          # total ΣVuy (kN)

    # Rincian momen (untuk tampilan detail)
    Muy_kolom_list  : List[float]    # Muy tiap kolom
    Mux_kolom_list  : List[float]    # Mux tiap kolom
    eMuy_geser_list : List[float]    # kontribusi momen dari geser (Vux × lengan)
    eMux_geser_list : List[float]    # kontribusi momen dari geser (Vuy × lengan)


# ---------------------------------------------------------------------------
# Fungsi utama perhitungan beban total
# ---------------------------------------------------------------------------
def hitung_beban_total(
    geom            : PilecapGeometry,
    P_ijin_tekan    : float = 800.0,
    P_ijin_tarik    : float = 300.0,
    P_ijin_lateral  : float = 80.0,
    t_pilecap_guna  : float = None,   # tebal efektif (default = geom.t)
) -> Tuple[BebanTotal, List[str]]:
    """
    Hitung total beban aksial dan momen yang bekerja ke pilecap.

    Langkah perhitungan:
    1. Jumlahkan Nu, Vux, Vuy, Mux, Muy dari semua kolom
    2. Hitung berat sendiri pilecap
    3. Hitung beban tanah urug di atas pilecap (dikurangi luas kolom)
    4. Hitung gaya uplift jika muka air tanah di atas dasar pilecap
    5. Hitung momen eksentrisitas akibat geser kolom (Vux × lengan, Vuy × lengan)
       Catatan: lengan momen = t/2 dari top ke centroid penampang pilecap
       (konservatif: geser diambil di muka kolom, lengan ke centroid pilecap = t/2)

    Parameter
    ---------
    geom            : objek PilecapGeometry dari sesi 1
    P_ijin_tekan    : kapasitas ijin tekan per tiang (kN)
    P_ijin_tarik    : kapasitas ijin tarik per tiang (kN)
    P_ijin_lateral  : kapasitas ijin lateral per tiang (kN)
    t_pilecap_guna  : tebal pilecap yang digunakan (default = geom.t)

    Return
    ------
    (BebanTotal, List[str])
        BebanTotal : objek ringkasan beban
        List[str]  : list string langkah perhitungan detail (untuk tampilan)
    """
    t = t_pilecap_guna if t_pilecap_guna is not None else geom.t
    g = geom.galian
    n = geom.jumlah_tiang

    detail = []   # list kalimat perhitungan detail

    # ----------------------------------------------------------------
    # LANGKAH 1 — Beban aksial & momen dari kolom
    # ----------------------------------------------------------------
    detail.append("=" * 60)
    detail.append("LANGKAH 1 — Beban aksial & momen dari kolom")
    detail.append("=" * 60)

    Nu_list  = [k.Nu  for k in geom.kolom_list]
    Vux_list = [k.Vux for k in geom.kolom_list]
    Vuy_list = [k.Vuy for k in geom.kolom_list]
    Mux_list = [k.Mux for k in geom.kolom_list]
    Muy_list = [k.Muy for k in geom.kolom_list]

    Nu_str  = " + ".join(f"{v:.2f}" for v in Nu_list)
    SigmaNu_kolom = sum(Nu_list)
    detail.append(f"  ΣNu_kolom  = {Nu_str}")
    detail.append(f"  ΣNu_kolom  = {SigmaNu_kolom:.2f} kN")

    Vux_str = " + ".join(f"{v:.2f}" for v in Vux_list)
    SigmaVux = sum(Vux_list)
    detail.append(f"  ΣVux       = {Vux_str}")
    detail.append(f"  ΣVux       = {SigmaVux:.2f} kN")

    Vuy_str = " + ".join(f"{v:.2f}" for v in Vuy_list)
    SigmaVuy = sum(Vuy_list)
    detail.append(f"  ΣVuy       = {Vuy_str}")
    detail.append(f"  ΣVuy       = {SigmaVuy:.2f} kN")

    # ----------------------------------------------------------------
    # LANGKAH 2 — Berat sendiri pilecap
    # ----------------------------------------------------------------
    detail.append("")
    detail.append("LANGKAH 2 — Berat sendiri pilecap")
    detail.append("-" * 40)
    W_pc = geom.Lx * geom.Ly * t * GAMMA_BETON
    detail.append(f"  W_pc = Lx × Ly × t × γ_beton")
    detail.append(f"  W_pc = {geom.Lx:.2f} × {geom.Ly:.2f} × {t:.2f} × {GAMMA_BETON:.1f}")
    detail.append(f"  W_pc = {W_pc:.2f} kN")

    # ----------------------------------------------------------------
    # LANGKAH 3 — Beban tanah di atas pilecap
    # ----------------------------------------------------------------
    detail.append("")
    detail.append("LANGKAH 3 — Beban tanah urug di atas pilecap")
    detail.append("-" * 40)

    h_galian = g.h_galian
    if h_galian <= 0.0:
        W_tanah = 0.0
        detail.append(f"  h_galian = {h_galian:.2f} m → tidak ada beban tanah di atas pilecap")
        detail.append(f"  W_tanah  = 0.00 kN")
    else:
        Area_kolom = sum(k.bk * k.hk for k in geom.kolom_list)
        Area_pc    = geom.Lx * geom.Ly
        Area_tanah = max(Area_pc - Area_kolom, 0.0)

        detail.append(f"  Luas pilecap       = Lx × Ly = {geom.Lx:.2f} × {geom.Ly:.2f} = {Area_pc:.3f} m²")
        detail.append(f"  Luas kolom total   = {Area_kolom:.3f} m²")
        detail.append(f"  Luas tanah efektif = {Area_pc:.3f} − {Area_kolom:.3f} = {Area_tanah:.3f} m²")

        # Cek muka air tanah
        h_muka_air = g.h_muka_air
        gamma      = g.gamma_tanah
        gamma_eff  = gamma - GAMMA_AIR   # berat jenis efektif di bawah muka air

        if h_muka_air >= h_galian:
            # Muka air di bawah bottom pilecap atau tidak ada — semua tanah kering
            W_tanah = Area_tanah * h_galian * gamma
            detail.append(f"  Muka air tanah pada h = {h_muka_air:.2f} m ≥ h_galian = {h_galian:.2f} m")
            detail.append(f"  → Seluruh tanah dianggap kering")
            detail.append(f"  W_tanah = A_tanah × h_galian × γ_tanah")
            detail.append(f"  W_tanah = {Area_tanah:.3f} × {h_galian:.2f} × {gamma:.1f}")
            detail.append(f"  W_tanah = {W_tanah:.2f} kN")
        else:
            # Ada bagian jenuh air
            h_kering = h_muka_air
            h_jenuh  = h_galian - h_muka_air
            W_kering = Area_tanah * h_kering * gamma
            W_jenuh  = Area_tanah * h_jenuh  * gamma_eff
            W_tanah  = W_kering + W_jenuh
            detail.append(f"  Muka air tanah pada h = {h_muka_air:.2f} m < h_galian = {h_galian:.2f} m")
            detail.append(f"  → Tanah kering: h = {h_kering:.2f} m, tanah jenuh: h = {h_jenuh:.2f} m")
            detail.append(f"  W_kering = {Area_tanah:.3f} × {h_kering:.2f} × {gamma:.1f} = {W_kering:.2f} kN")
            detail.append(f"  W_jenuh  = {Area_tanah:.3f} × {h_jenuh:.2f} × {gamma_eff:.1f} = {W_jenuh:.2f} kN")
            detail.append(f"  W_tanah  = {W_kering:.2f} + {W_jenuh:.2f} = {W_tanah:.2f} kN")

    # ----------------------------------------------------------------
    # LANGKAH 4 — Uplift tekanan air (jika ada)
    # ----------------------------------------------------------------
    detail.append("")
    detail.append("LANGKAH 4 — Uplift tekanan air")
    detail.append("-" * 40)

    h_muka_air = g.h_muka_air
    h_dasar_pc = h_galian + t   # kedalaman dasar pilecap dari muka tanah

    if h_muka_air < h_dasar_pc:
        # Muka air berada di atas dasar pilecap → ada uplift pada dasar pilecap
        h_air_di_pc = h_dasar_pc - h_muka_air   # tinggi air di atas dasar pilecap
        F_uplift = GAMMA_AIR * h_air_di_pc * geom.Lx * geom.Ly
        detail.append(f"  Muka air tanah pada h = {h_muka_air:.2f} m")
        detail.append(f"  Dasar pilecap pada h  = h_galian + t = {h_galian:.2f} + {t:.2f} = {h_dasar_pc:.2f} m")
        detail.append(f"  Tinggi air di atas dasar pilecap = {h_dasar_pc:.2f} − {h_muka_air:.2f} = {h_air_di_pc:.2f} m")
        detail.append(f"  F_uplift = γ_air × h_air × Lx × Ly")
        detail.append(f"  F_uplift = {GAMMA_AIR:.1f} × {h_air_di_pc:.2f} × {geom.Lx:.2f} × {geom.Ly:.2f}")
        detail.append(f"  F_uplift = {F_uplift:.2f} kN  ← mengurangi ΣNu")
    else:
        F_uplift = 0.0
        detail.append(f"  Muka air tanah pada h = {h_muka_air:.2f} m ≥ dasar pilecap h = {h_dasar_pc:.2f} m")
        detail.append(f"  → Tidak ada uplift tekanan air")
        detail.append(f"  F_uplift = 0.00 kN")

    # ----------------------------------------------------------------
    # LANGKAH 5 — Total ΣNu ke pilecap
    # ----------------------------------------------------------------
    detail.append("")
    detail.append("LANGKAH 5 — Total beban aksial ΣNu ke pilecap")
    detail.append("-" * 40)
    SigmaNu = SigmaNu_kolom + W_pc + W_tanah - F_uplift

    Nu_komponen_str = " + ".join(f"{v:.2f}" for v in Nu_list)
    detail.append(f"  ΣNu = ΣNu_kolom + W_pc + W_tanah − F_uplift")
    detail.append(f"  ΣNu = ({Nu_komponen_str}) + {W_pc:.2f} + {W_tanah:.2f} − {F_uplift:.2f}")
    detail.append(f"  ΣNu = {SigmaNu_kolom:.2f} + {W_pc:.2f} + {W_tanah:.2f} − {F_uplift:.2f}")
    detail.append(f"  ΣNu = {SigmaNu:.2f} kN")

    # ----------------------------------------------------------------
    # LANGKAH 6 — Total momen ke centroid grup tiang
    # ----------------------------------------------------------------
    detail.append("")
    detail.append("LANGKAH 6 — Total momen terhadap centroid grup tiang")
    detail.append("-" * 40)
    detail.append("  Momen dihitung di titik centroid grup tiang (x̄, ȳ).")
    detail.append("  Kontribusi momen:")
    detail.append("  (a) Momen langsung dari kolom: Mux, Muy")
    detail.append("  (b) Eksentrisitas Nu kolom dari centroid grup: e_x = xk − x̄, e_y = yk − ȳ")
    detail.append("  (c) Eksentrisitas geser: Vux × (t/2), Vuy × (t/2)  [lengan = setengah tebal pilecap]")
    detail.append("      Catatan: ini adalah pendekatan konservatif. Lengan momen geser ke centroid")
    detail.append("      tulangan tarik bawah lebih tepat dihitung di Sesi 3 (penulangan).")

    x_bar, y_bar = geom.centroid_grup()
    detail.append(f"  Centroid grup: x̄ = {x_bar:.4f} m, ȳ = {y_bar:.4f} m")
    detail.append(f"  t/2 = {t:.2f}/2 = {t/2:.3f} m  (lengan geser ke centroid pilecap)")

    # Momen Muy total (sumbu Y → menyebabkan gaya ± arah X)
    Muy_kolom_list  = []
    eMuy_geser_list = []
    SigmaMuy = 0.0

    detail.append("")
    detail.append("  --- Momen sumbu Y (ΣMuy_total) ---")
    detail.append("  ΣMuy_total = Σ[Muy_kolom + Nu_kolom × (xk − x̄) + Vux × (t/2)]")

    for i, kol in enumerate(geom.kolom_list):
        ex    = kol.xk - x_bar               # eksentrisitas kolom dari centroid arah X
        eMuy  = kol.Nu * ex                   # momen akibat eksentrisitas aksial kolom
        eMuy_geser = kol.Vux * (t / 2)       # momen akibat geser × lengan
        Muy_i = kol.Muy + eMuy + eMuy_geser
        Muy_kolom_list.append(kol.Muy)
        eMuy_geser_list.append(eMuy_geser)
        SigmaMuy += Muy_i
        detail.append(f"  Kolom {kol.id_kolom}: Muy = {kol.Muy:.2f} + {kol.Nu:.2f}×({kol.xk:.3f}−{x_bar:.3f}) + {kol.Vux:.2f}×{t/2:.3f}")
        detail.append(f"         = {kol.Muy:.2f} + {eMuy:.2f} + {eMuy_geser:.2f} = {Muy_i:.2f} kNm")

    detail.append(f"  ΣMuy_total = {SigmaMuy:.2f} kNm")

    # Momen Mux total (sumbu X → menyebabkan gaya ± arah Y)
    Mux_kolom_list  = []
    eMux_geser_list = []
    SigmaMux = 0.0

    detail.append("")
    detail.append("  --- Momen sumbu X (ΣMux_total) ---")
    detail.append("  ΣMux_total = Σ[Mux_kolom + Nu_kolom × (yk − ȳ) + Vuy × (t/2)]")

    for i, kol in enumerate(geom.kolom_list):
        ey    = kol.yk - y_bar
        eMux  = kol.Nu * ey
        eMux_geser = kol.Vuy * (t / 2)
        Mux_i = kol.Mux + eMux + eMux_geser
        Mux_kolom_list.append(kol.Mux)
        eMux_geser_list.append(eMux_geser)
        SigmaMux += Mux_i
        detail.append(f"  Kolom {kol.id_kolom}: Mux = {kol.Mux:.2f} + {kol.Nu:.2f}×({kol.yk:.3f}−{y_bar:.3f}) + {kol.Vuy:.2f}×{t/2:.3f}")
        detail.append(f"         = {kol.Mux:.2f} + {eMux:.2f} + {eMux_geser:.2f} = {Mux_i:.2f} kNm")

    detail.append(f"  ΣMux_total = {SigmaMux:.2f} kNm")

    # Buat objek BebanTotal
    beban = BebanTotal(
        Nu_kolom_list   = Nu_list,
        W_pilecap       = W_pc,
        W_tanah         = W_tanah,
        F_uplift        = F_uplift,
        SigmaNu         = SigmaNu,
        SigmaMuy        = SigmaMuy,
        SigmaMux        = SigmaMux,
        SigmaVux        = SigmaVux,
        SigmaVuy        = SigmaVuy,
        Muy_kolom_list  = Muy_kolom_list,
        Mux_kolom_list  = Mux_kolom_list,
        eMuy_geser_list = eMuy_geser_list,
        eMux_geser_list = eMux_geser_list,
    )

    return beban, detail


# ---------------------------------------------------------------------------
# Fungsi utama perhitungan gaya per tiang
# ---------------------------------------------------------------------------
def hitung_gaya_tiang(
    geom            : PilecapGeometry,
    beban           : BebanTotal,
    P_ijin_tekan    : float = 800.0,
    P_ijin_tarik    : float = 300.0,
    P_ijin_lateral  : float = 80.0,
) -> Tuple[List[HasilGayaTiang], List[str]]:
    """
    Hitung gaya aksial dan lateral setiap tiang.

    Rumus aksial tiang ke-i:
        Pi = ΣNu / n  ±  ΣMuy_total × xi / Iy  ±  ΣMux_total × yi / Ix
        di mana Iy = Σxi², Ix = Σyi²

    Rumus lateral tiang ke-i (distribusi merata):
        Hxi = ΣVux / n
        Hyi = ΣVuy / n
        Hi  = √(Hxi² + Hyi²)

    Parameter
    ---------
    geom         : PilecapGeometry dari sesi 1
    beban        : BebanTotal dari hitung_beban_total()
    P_ijin_*     : kapasitas ijin tiang (kN)

    Return
    ------
    (List[HasilGayaTiang], List[str])
    """
    n    = geom.jumlah_tiang
    Ix   = geom.Ix_grup()    # Σyi²
    Iy   = geom.Iy_grup()    # Σxi²
    jarak_rel = geom.jarak_tiang_ke_centroid()   # list (xi, yi)

    detail = []
    detail.append("")
    detail.append("=" * 60)
    detail.append("LANGKAH 7 — Gaya aksial setiap tiang")
    detail.append("=" * 60)
    detail.append("")
    detail.append("  Rumus:")
    detail.append("  Pi = ΣNu / n  ±  ΣMuy_total × xi / Iy  ±  ΣMux_total × yi / Ix")
    detail.append("")
    detail.append(f"  ΣNu        = {beban.SigmaNu:.2f} kN")
    detail.append(f"  ΣMuy_total = {beban.SigmaMuy:.2f} kNm")
    detail.append(f"  ΣMux_total = {beban.SigmaMux:.2f} kNm")
    detail.append(f"  n          = {n} tiang")
    detail.append(f"  Iy = Σxi²  = {Iy:.4f} m²")
    detail.append(f"  Ix = Σyi²  = {Ix:.4f} m²")
    detail.append("")

    # Komponen aksial rata-rata
    P_rata = beban.SigmaNu / n
    detail.append(f"  Komponen rata-rata: ΣNu / n = {beban.SigmaNu:.2f} / {n} = {P_rata:.4f} kN/tiang")

    # Komponen momen (jika Iy atau Ix = 0 berarti semua tiang segaris → tidak ada eksentrisitas)
    detail.append("")

    hasil_list = []

    for i, ((xi, yi), (x, y)) in enumerate(zip(jarak_rel, geom.pile_coords)):
        no = i + 1

        # Komponen dari Muy (momen sumbu Y → gaya ± arah X)
        if abs(Iy) > 1e-10:
            dP_Muy = beban.SigmaMuy * xi / Iy
        else:
            dP_Muy = 0.0

        # Komponen dari Mux (momen sumbu X → gaya ± arah Y)
        if abs(Ix) > 1e-10:
            dP_Mux = beban.SigmaMux * yi / Ix
        else:
            dP_Mux = 0.0

        Pi = P_rata + dP_Muy + dP_Mux

        # Tanda ± untuk tampilan
        tanda_Muy = "+" if dP_Muy >= 0 else "−"
        tanda_Mux = "+" if dP_Mux >= 0 else "−"

        detail.append(f"  Tiang {no:2d}: xi = {xi:+.4f} m, yi = {yi:+.4f} m")
        detail.append(f"    Pi = ΣNu/n  {tanda_Muy}  ΣMuy×xi/Iy  {tanda_Mux}  ΣMux×yi/Ix")
        detail.append(f"    Pi = {P_rata:.4f}  {tanda_Muy}  {beban.SigmaMuy:.2f}×({xi:+.4f})/{Iy:.4f}  {tanda_Mux}  {beban.SigmaMux:.2f}×({yi:+.4f})/{Ix:.4f}")
        detail.append(f"    Pi = {P_rata:.4f}  {tanda_Muy}  {abs(dP_Muy):.4f}  {tanda_Mux}  {abs(dP_Mux):.4f}")
        detail.append(f"    Pi = {Pi:.4f} kN")

        # Gaya lateral
        Hxi = beban.SigmaVux / n
        Hyi = beban.SigmaVuy / n
        Hi  = math.hypot(Hxi, Hyi)

        # Cek aksial
        if Pi >= 0:
            status_aksial = "TEKAN"
            if Pi <= P_ijin_tekan:
                status_aksial_cek = "OK"
                detail.append(f"    → TEKAN: Pi = {Pi:.2f} ≤ P_ijin_tekan = {P_ijin_tekan:.2f} kN  ✓")
            else:
                status_aksial_cek = "NG"
                detail.append(f"    → TEKAN: Pi = {Pi:.2f} > P_ijin_tekan = {P_ijin_tekan:.2f} kN  ✗ MELEBIHI KAPASITAS")
        else:
            status_aksial = "TARIK"
            if abs(Pi) <= P_ijin_tarik:
                status_aksial_cek = "OK"
                detail.append(f"    → TARIK: |Pi| = {abs(Pi):.2f} ≤ P_ijin_tarik = {P_ijin_tarik:.2f} kN  ✓")
            else:
                status_aksial_cek = "NG"
                detail.append(f"    → TARIK: |Pi| = {abs(Pi):.2f} > P_ijin_tarik = {P_ijin_tarik:.2f} kN  ✗ MELEBIHI KAPASITAS")

        # Cek lateral
        if Hi <= P_ijin_lateral:
            status_lateral = "OK"
            detail.append(f"    → LATERAL: Hi = {Hi:.2f} ≤ P_ijin_lateral = {P_ijin_lateral:.2f} kN  ✓")
        else:
            status_lateral = "NG"
            detail.append(f"    → LATERAL: Hi = {Hi:.2f} > P_ijin_lateral = {P_ijin_lateral:.2f} kN  ✗")

        detail.append("")

        hasil_list.append(HasilGayaTiang(
            no_tiang          = no,
            x                 = x,
            y                 = y,
            xi                = xi,
            yi                = yi,
            Pi                = Pi,
            Hxi               = Hxi,
            Hyi               = Hyi,
            Hi                = Hi,
            status_aksial     = status_aksial,
            status_aksial_cek = status_aksial_cek,
            status_lateral    = status_lateral,
            P_ijin_tekan      = P_ijin_tekan,
            P_ijin_tarik      = P_ijin_tarik,
            P_ijin_lateral    = P_ijin_lateral,
        ))

    # Ringkasan
    Pi_list  = [h.Pi for h in hasil_list]
    Pmax     = max(Pi_list)
    Pmin     = min(Pi_list)
    Hi_list  = [h.Hi for h in hasil_list]
    Hi_max   = max(Hi_list)
    tiang_tarik = [h.no_tiang for h in hasil_list if h.status_aksial == "TARIK"]

    detail.append("=" * 60)
    detail.append("RINGKASAN GAYA TIANG")
    detail.append("=" * 60)
    detail.append(f"  Pmax (tekan maks) = {Pmax:.2f} kN  (Tiang {Pi_list.index(Pmax)+1})")
    detail.append(f"  Pmin (tekan min)  = {Pmin:.2f} kN  (Tiang {Pi_list.index(Pmin)+1})")
    if tiang_tarik:
        detail.append(f"  Tiang TARIK       = Tiang {tiang_tarik}")
    else:
        detail.append(f"  Tidak ada tiang tarik — semua dalam kondisi tekan")
    detail.append(f"  Gaya lateral maks = {Hi_max:.2f} kN/tiang")

    return hasil_list, detail


# ---------------------------------------------------------------------------
# Fungsi ringkasan untuk kebutuhan modul lain (Sesi 3, 4)
# ---------------------------------------------------------------------------
def ringkasan_gaya_tiang(hasil_list: List[HasilGayaTiang]) -> Dict:
    """
    Ambil nilai-nilai ringkasan dari list hasil gaya tiang.

    Return: dict dengan kunci Pmax, Pmin, tiang_tarik, Hi_max, semua_ok
    """
    Pi_list      = [h.Pi for h in hasil_list]
    Hi_list      = [h.Hi for h in hasil_list]
    tiang_tarik  = [h.no_tiang for h in hasil_list if h.status_aksial == "TARIK"]
    tiang_ng     = [h.no_tiang for h in hasil_list if h.status_global == "NG"]

    return {
        "Pmax"        : max(Pi_list),
        "Pmin"        : min(Pi_list),
        "Pi_list"     : Pi_list,
        "Hi_max"      : max(Hi_list),
        "tiang_tarik" : tiang_tarik,
        "tiang_ng"    : tiang_ng,
        "semua_ok"    : len(tiang_ng) == 0,
        "ada_tarik"   : len(tiang_tarik) > 0,
        "SigmaPtekan" : sum(p for p in Pi_list if p > 0),
    }
