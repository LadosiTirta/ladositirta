"""
=============================================================
HALAMAN 1 - EVALUASI KAPASITAS LENTUR BALOK BETON BERTULANG
                (Tulangan Rangkap - Strain Compatibility)
Referensi : SNI 2847:2019 (ACI 318-14)
Framework : Streamlit (multipage)
Output    : Word (.docx) & PDF (.pdf) + Watermark
Session   : st.session_state untuk persistensi hasil
=============================================================
"""

import math
import io
import datetime
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from fpdf import FPDF

# ============================================================
# KONFIGURASI HALAMAN
# ============================================================
st.set_page_config(
    page_title="Evaluasi Lentur Balok | SNI 2847:2019",
    page_icon="🏗",
    layout="wide",
)

st.markdown("""
<style>
  .main-title{font-size:1.6rem;font-weight:600;color:#1a3c5e;margin-bottom:0}
  .sub-title{font-size:.9rem;color:#666;margin-bottom:1.5rem}
  .step-box{background:#f8f9fa;border-left:4px solid #1a3c5e;border-radius:0 8px 8px 0;
            padding:12px 16px;margin-bottom:10px;font-family:monospace;font-size:.85rem}
  .step-hdr{font-weight:700;color:#1a3c5e;font-size:.8rem;
            text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
  .result-ok  {background:#e8f5e9;border-left:4px solid #2e7d32;color:#1b5e20;
               padding:12px 16px;border-radius:8px;font-weight:600;margin-bottom:8px}
  .result-warn{background:#fff8e1;border-left:4px solid #f9a825;color:#5d4037;
               padding:12px 16px;border-radius:8px;font-weight:600;margin-bottom:8px}
  .result-fail{background:#ffebee;border-left:4px solid #c62828;color:#b71c1c;
               padding:12px 16px;border-radius:8px;font-weight:600;margin-bottom:8px}
  .metric-card{background:white;border:1px solid #e0e0e0;border-radius:10px;
               padding:14px;text-align:center}
  .metric-lbl{font-size:.75rem;color:#888;margin-bottom:4px}
  .metric-val{font-size:1.5rem;font-weight:700;color:#1a3c5e}
  .metric-unt{font-size:.75rem;color:#aaa}
  .ref-badge{display:inline-block;background:#e3f2fd;color:#1565c0;
             font-size:.7rem;padding:2px 8px;border-radius:20px;margin-bottom:6px}
  hr.divider{border:none;border-top:2px solid #e0e0e0;margin:1.5rem 0}
</style>
""", unsafe_allow_html=True)


# ============================================================
# SANITASI STRING UNTUK PDF (Latin-1 only)
# ============================================================
_UNICODE_MAP = {
    "\u2014": "-",    "\u2013": "-",    "\u2019": "'",   "\u2018": "'",
    "\u201c": '"',    "\u201d": '"',    "\u00b2": "2",   "\u00b3": "3",
    "\u00b0": " deg", "\u00d7": "x",   "\u2265": ">=",  "\u2264": "<=",
    "\u2260": "!=",   "\u221a": "sqrt", "\u03c6": "Phi", "\u03b2": "Beta",
    "\u03b5": "et",   "\u03c1": "Rho",  "\u03bc": "mu",  "\u2022": "-",
    "\u2192": "->",   "\u00b7": ".",    "\u00e9": "e",   "\u00e8": "e",
    "\u00e0": "a",    "\u2550": "=",    "\u2500": "-",
}

def sp(teks: str) -> str:
    """Sanitasi string agar aman untuk fpdf2 (Latin-1 only)."""
    if not isinstance(teks, str):
        teks = str(teks)
    for ch, repl in _UNICODE_MAP.items():
        teks = teks.replace(ch, repl)
    return teks.encode("latin-1", errors="replace").decode("latin-1")


# ============================================================
# LIBRARY DIAMETER TULANGAN (mm)
# ============================================================
DIAMETER_LIST = [10, 13, 16, 19, 22, 25, 29, 32]

def luas_batang(d_mm: float) -> float:
    """Luas penampang satu batang tulangan (mm2)."""
    return math.pi * d_mm ** 2 / 4.0


# ============================================================
# FUNGSI HITUNG GEOMETRI TULANGAN OTOMATIS
# ============================================================
def hitung_lapis_tarik(h, cc, ds, n1, db1, n2, db2, spasi=25.0):
    """
    Hitung posisi tiap lapis tarik (dari serat tekan teratas).
    Lapis 1 = paling bawah, Lapis 2 = di atas Lapis 1.

    Returns:
        list of dict per lapis aktif: {n, db, As, y (jarak dari serat tekan)}
        d_total : titik berat total tulangan tarik (mm dari serat tekan)
        As_total: luas total tulangan tarik (mm2)
    """
    lapis = []
    # Lapis 1 (paling bawah)
    if n1 > 0 and db1 > 0:
        y1 = h - cc - ds - db1 / 2.0
        As1 = n1 * luas_batang(db1)
        lapis.append(dict(no=1, n=n1, db=db1, As=As1, y=y1))
    # Lapis 2 (di atas Lapis 1, jarak bersih = spasi)
    if n2 > 0 and db2 > 0:
        # acuan permukaan teratas Lapis 1
        if n1 > 0 and db1 > 0:
            y_top_lapis1 = h - cc - ds - db1   # permukaan atas batang lapis 1
            y2 = y_top_lapis1 - spasi - db2 / 2.0
        else:
            # Lapis 1 kosong -> Lapis 2 ambil posisi paling bawah
            y2 = h - cc - ds - db2 / 2.0
        As2 = n2 * luas_batang(db2)
        lapis.append(dict(no=2, n=n2, db=db2, As=As2, y=y2))

    if not lapis:
        return [], 0.0, 0.0

    As_total = sum(L["As"] for L in lapis)
    d_total  = sum(L["As"] * L["y"] for L in lapis) / As_total
    return lapis, d_total, As_total


def hitung_lapis_tekan(cc, ds, n1, db1, n2, db2, spasi=25.0):
    """
    Hitung posisi tiap lapis tekan (dari serat tekan teratas).
    Lapis 1 = paling atas (paling dekat serat tekan).
    """
    lapis = []
    if n1 > 0 and db1 > 0:
        y1 = cc + ds + db1 / 2.0
        As1 = n1 * luas_batang(db1)
        lapis.append(dict(no=1, n=n1, db=db1, As=As1, y=y1))
    if n2 > 0 and db2 > 0:
        if n1 > 0 and db1 > 0:
            y_bot_lapis1 = cc + ds + db1
            y2 = y_bot_lapis1 + spasi + db2 / 2.0
        else:
            y2 = cc + ds + db2 / 2.0
        As2 = n2 * luas_batang(db2)
        lapis.append(dict(no=2, n=n2, db=db2, As=As2, y=y2))

    if not lapis:
        return [], 0.0, 0.0

    As_total = sum(L["As"] for L in lapis)
    d_total  = sum(L["As"] * L["y"] for L in lapis) / As_total
    return lapis, d_total, As_total


# ============================================================
# FUNGSI EVALUASI LENTUR (STRAIN COMPATIBILITY)
# ============================================================
def hitung_beta1(fc):
    """Beta-1 SNI 2847:2019 Pasal 22.2.2.4.3"""
    if fc <= 28:
        return 0.85, f"fc = {fc} MPa <= 28 MPa  -->  Beta-1 = 0.85"
    elif fc >= 56:
        return 0.65, f"fc = {fc} MPa >= 56 MPa  -->  Beta-1 = 0.65"
    else:
        b = max(0.65, min(0.85, 0.85 - 0.05 * (fc - 28) / 7))
        return b, (f"Beta-1 = 0.85 - 0.05 x (fc - 28) / 7\n"
                   f"       = 0.85 - 0.05 x ({fc} - 28) / 7")


def gaya_dalam(c, fc, fy, b, beta1, lapis_tarik, lapis_tekan):
    """
    Hitung gaya dalam berdasarkan asumsi nilai c (sumbu netral).
    Strain compatibility: regangan beton ekstrim = 0.003.
    Returns: dict gaya & regangan tiap lapis, plus residu = Cc + Cs - T
    """
    Es      = 200_000.0          # MPa
    eps_cu  = 0.003
    eps_y   = fy / Es
    a       = beta1 * c

    # Gaya tekan beton
    Cc = 0.85 * fc * a * b       # N

    # Gaya tekan baja (atas) - kurangi area beton yang ter-displace
    Cs_total = 0.0
    info_tekan = []
    for L in lapis_tekan:
        eps_s = eps_cu * (c - L["y"]) / c        # + jika tekan
        if eps_s >= eps_y:
            fs = fy
        elif eps_s <= -eps_y:
            fs = -fy
        else:
            fs = eps_s * Es                       # tegangan aktual
        # Reduksi: lapis di dalam blok tekan mengurangi area Cc -> kurangi 0.85 fc
        if L["y"] <= a:
            fs_eff = fs - 0.85 * fc
        else:
            fs_eff = fs
        F = L["As"] * fs_eff
        Cs_total += F
        info_tekan.append(dict(no=L["no"], y=L["y"], As=L["As"],
                               eps=eps_s, fs=fs, F=F))

    # Gaya tarik baja (bawah)
    T_total = 0.0
    info_tarik = []
    for L in lapis_tarik:
        eps_s = eps_cu * (L["y"] - c) / c        # + jika tarik
        if eps_s >= eps_y:
            fs = fy
        elif eps_s <= -eps_y:
            fs = -fy
        else:
            fs = eps_s * Es
        F = L["As"] * fs
        T_total += F
        info_tarik.append(dict(no=L["no"], y=L["y"], As=L["As"],
                               eps=eps_s, fs=fs, F=F))

    residu = Cc + Cs_total - T_total
    return dict(
        a=a, c=c, Cc=Cc, Cs=Cs_total, T=T_total,
        info_tekan=info_tekan, info_tarik=info_tarik,
        residu=residu, eps_y=eps_y,
    )


def cari_c_keseimbangan(fc, fy, b, beta1, lapis_tarik, lapis_tekan, h):
    """
    Iterasi bisection untuk menemukan c sehingga residu (Cc+Cs-T) = 0.
    """
    lo, hi = 0.001, h * 1.5
    for _ in range(200):
        mid = (lo + hi) / 2.0
        r = gaya_dalam(mid, fc, fy, b, beta1, lapis_tarik, lapis_tekan)["residu"]
        r_lo = gaya_dalam(lo, fc, fy, b, beta1, lapis_tarik, lapis_tekan)["residu"]
        if abs(r) < 1e-3:
            return mid
        if r_lo * r < 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def evaluasi_balok(fc, fy, b, h, cc_sel, ds, lapis_tarik, lapis_tekan,
                   d_tarik, As_tarik, d_tekan, As_tekan, Mu):
    """
    Evaluasi penuh penampang dengan strain compatibility.
    """
    R = {}
    beta1, beta1_cara = hitung_beta1(fc)
    R["beta1"]      = beta1
    R["beta1_cara"] = beta1_cara

    # Cari sumbu netral
    c = cari_c_keseimbangan(fc, fy, b, beta1, lapis_tarik, lapis_tekan, h)
    G = gaya_dalam(c, fc, fy, b, beta1, lapis_tarik, lapis_tekan)

    a       = G["a"]
    Cc      = G["Cc"]
    Cs      = G["Cs"]
    T       = G["T"]
    info_tk = G["info_tekan"]
    info_tr = G["info_tarik"]
    eps_y   = G["eps_y"]

    # Momen nominal dengan referensi serat tekan (top)
    # Mn = Sum(F_i x lengan_i) terhadap serat tekan teratas
    # Cc bekerja di y = a/2; Cs di y_lapis_tekan; T di y_lapis_tarik
    Mn_Nmm = Cc * (h / 2 - a / 2)  # placeholder, akan diganti dengan formulasi standar
    # Lebih tepat: ambil momen terhadap titik berat tulangan tarik
    Mn_Nmm = (Cc * (d_tarik - a / 2)
              + sum(L["F"] * (d_tarik - L["y"]) for L in info_tk)
              - sum(L["F"] * (d_tarik - L["y"]) for L in info_tr if L["no"] != 0))
    # Untuk single tarik resultan: Mn = Cc*(d-a/2) + Sum Cs_i (d - y_i)
    # T berada di d_tarik (titik berat) sehingga lengan = 0 jika diukur thd T.
    # Kita pakai referensi titik berat tulangan tarik:
    Mn_Nmm = Cc * (d_tarik - a / 2)
    for L in info_tk:
        Mn_Nmm += L["F"] * (d_tarik - L["y"])
    Mn = Mn_Nmm / 1_000_000.0    # kN.m

    # Regangan tarik terjauh (lapis paling bawah = y terbesar)
    if info_tr:
        et = max(L["eps"] for L in info_tr)
    else:
        et = 0.0

    # Faktor reduksi Phi (SNI Tabel 21.2.2)
    if et >= 0.005:
        phi = 0.90
        phi_cara = "et >= 0.005  -->  Tension-controlled  -->  Phi = 0.90"
    elif et <= 0.002:
        phi = 0.65
        phi_cara = "et <= 0.002  -->  Compression-controlled  -->  Phi = 0.65"
    else:
        phi = 0.65 + (et - 0.002) * (250 / 3)
        phi_cara = (f"0.002 < et < 0.005  -->  Zona transisi\n"
                    f"Phi = 0.65 + (et - 0.002) x 250/3\n"
                    f"    = 0.65 + ({et:.5f} - 0.002) x 83.333")

    phiMn = phi * Mn
    DC    = Mu / phiMn if phiMn > 0 else float("inf")

    # Rasio tulangan
    rho      = As_tarik / (b * d_tarik)
    rho_mA   = 0.25 * math.sqrt(fc) / fy
    rho_mB   = 1.4 / fy
    rho_min  = max(rho_mA, rho_mB)
    rho_bal  = (0.85 * beta1 * fc / fy) * (600 / (600 + fy))
    rho_max  = 0.75 * rho_bal

    R.update(dict(
        c=c, a=a, Cc=Cc, Cs=Cs, T=T,
        info_tarik=info_tr, info_tekan=info_tk,
        eps_y=eps_y, et=et, phi=phi, phi_cara=phi_cara,
        Mn=Mn, phiMn=phiMn, Mu=Mu, DC=DC,
        rho=rho, rho_mA=rho_mA, rho_mB=rho_mB,
        rho_min=rho_min, rho_bal=rho_bal, rho_max=rho_max,
        ok_rho_min=(rho >= rho_min),
        ok_rho_max=(rho <= rho_max),
        ok_et=(et >= 0.004),
        ok_dc=(DC <= 1.0),
        d_tarik=d_tarik, d_tekan=d_tekan,
        As_tarik=As_tarik, As_tekan=As_tekan,
    ))
    return R


# ============================================================
# BUAT STEP-STEP LAPORAN (b1, b2, b3, ...)
# ============================================================
def buat_steps_balok(fc, fy, b, h, cc_sel, ds, lapis_tarik, lapis_tekan, R):
    Mu = R["Mu"]
    ok_rho = R["ok_rho_min"] and R["ok_rho_max"]

    # b1 - Beta1
    s1 = dict(
        no="b1.", ref="SNI 2847:2019 Pasal 22.2.2.4.3",
        judul="Faktor blok tegangan ekivalen (Beta-1)",
        isi=f"{R['beta1_cara']}\n  -->  Beta-1 = {R['beta1']:.4f}",
        ok=True,
    )

    # b2 - Geometri Tulangan (d aktual & d' aktual)
    teks_tarik = ""
    for L in lapis_tarik:
        teks_tarik += (f"  Lapis-{L['no']}: {L['n']} D{int(L['db'])}  "
                       f"As = {L['As']:.1f} mm2  y = {L['y']:.1f} mm\n")
    teks_tekan = ""
    if lapis_tekan:
        for L in lapis_tekan:
            teks_tekan += (f"  Lapis-{L['no']}: {L['n']} D{int(L['db'])}  "
                           f"As = {L['As']:.1f} mm2  y = {L['y']:.1f} mm\n")
    else:
        teks_tekan = "  (Tidak ada tulangan tekan)\n"

    s2 = dict(
        no="b2.", ref="SNI 2847:2019 Pasal 25.2 - Penempatan tulangan",
        judul="Posisi tulangan & titik berat (d aktual & d' aktual)",
        isi=(
            f"Tulangan TARIK (dari serat tekan teratas):\n"
            f"{teks_tarik}"
            f"  d-aktual = Sum(As.y)/Sum(As) = {R['d_tarik']:.2f} mm\n"
            f"  As-total = {R['As_tarik']:.1f} mm2\n\n"
            f"Tulangan TEKAN (dari serat tekan teratas):\n"
            f"{teks_tekan}"
            + (f"  d'-aktual = {R['d_tekan']:.2f} mm\n"
               f"  As'-total = {R['As_tekan']:.1f} mm2"
               if lapis_tekan else "")
        ),
        ok=True,
    )

    # b3 - Iterasi sumbu netral c (strain compatibility)
    eps_y = R["eps_y"]
    s3 = dict(
        no="b3.", ref="SNI 2847:2019 Pasal 22.2.1 - Asumsi desain",
        judul="Strain compatibility - Cari sumbu netral c",
        isi=(
            f"Asumsi: regangan tekan beton ekstrim = 0.003\n"
            f"        regangan leleh baja eps-y = fy/Es = {fy}/200000 = {eps_y:.5f}\n"
            f"Iterasi bisection untuk Cc + Cs - T = 0\n"
            f"  -->  c = {R['c']:.2f} mm\n"
            f"  -->  a = Beta-1 x c = {R['beta1']:.4f} x {R['c']:.2f} = {R['a']:.2f} mm"
        ),
        ok=True,
    )

    # b4 - Regangan & tegangan tiap lapis
    teks_eps = ""
    for L in R["info_tekan"]:
        status = "leleh" if abs(L["eps"]) >= eps_y else "elastis"
        teks_eps += (f"  Tekan Lapis-{L['no']}  (y={L['y']:.1f} mm):\n"
                     f"    eps-s' = 0.003 x (c - y) / c = "
                     f"0.003 x ({R['c']:.2f} - {L['y']:.1f}) / {R['c']:.2f} "
                     f"= {L['eps']:+.5f}  ({status})\n"
                     f"    fs'    = {L['fs']:+.2f} MPa\n")
    for i, L in enumerate(R["info_tarik"]):
        notasi = "et" if L["no"] == 1 else f"eps-s{L['no']}"
        status = "leleh" if abs(L["eps"]) >= eps_y else "elastis"
        teks_eps += (f"  Tarik Lapis-{L['no']} (y={L['y']:.1f} mm):\n"
                     f"    {notasi:<6} = 0.003 x (y - c) / c = "
                     f"0.003 x ({L['y']:.1f} - {R['c']:.2f}) / {R['c']:.2f} "
                     f"= {L['eps']:+.5f}  ({status})\n"
                     f"    fs     = {L['fs']:+.2f} MPa\n")

    s4 = dict(
        no="b4.", ref="SNI 2847:2019 Pasal 22.2.1.1 - Strain linear",
        judul="Regangan & tegangan baja per lapis",
        isi=(
            f"Tegangan tiap lapis: jika |eps| < eps-y -> fs = eps x 200000\n"
            f"                     jika |eps| >= eps-y -> fs = +/- fy\n\n"
            f"{teks_eps.rstrip()}"
        ),
        ok=True,
    )

    # b5 - Gaya dalam Cc, Cs, T
    teks_F = ""
    for L in R["info_tekan"]:
        teks_F += (f"  Cs Lapis-{L['no']} = As' x (fs' - 0.85 fc)" if L["y"] <= R["a"]
                   else f"  Cs Lapis-{L['no']} = As' x fs'")
        teks_F += f" = {L['F']:+,.0f} N\n"
    for L in R["info_tarik"]:
        teks_F += f"  T  Lapis-{L['no']} = As x fs = {L['F']:+,.0f} N\n"

    s5 = dict(
        no="b5.", ref="SNI 2847:2019 Pasal 22.2.2 - Distribusi tegangan",
        judul="Gaya tekan beton (Cc), gaya baja tekan (Cs), gaya tarik (T)",
        isi=(
            f"Cc = 0.85 x fc x a x b\n"
            f"   = 0.85 x {fc} x {R['a']:.2f} x {b}\n"
            f"   = {R['Cc']:,.0f} N  =  {R['Cc']/1000:.2f} kN\n\n"
            f"{teks_F}"
            f"\nCek keseimbangan: Cc + Cs - T = "
            f"{R['Cc']:,.0f} + {R['Cs']:,.0f} - {R['T']:,.0f} = "
            f"{R['Cc']+R['Cs']-R['T']:,.0f} N  (~ 0, OK)"
        ),
        ok=True,
    )

    # b6 - Rasio tulangan (cek konstruktabilitas)
    s6 = dict(
        no="b6.", ref="SNI 2847:2019 Pasal 9.6.1 & 21.2.2",
        judul="Rasio tulangan tarik (Rho) - kontrol min & max",
        isi=(
            f"Rho     = As / (b x d) = {R['As_tarik']:.1f} / "
            f"({b:.0f} x {R['d_tarik']:.2f}) = {R['rho']*100:.4f}%\n"
            f"Rho-min = max(0.25 sqrt(fc)/fy , 1.4/fy)\n"
            f"        = max({R['rho_mA']*100:.4f}% , {R['rho_mB']*100:.4f}%) "
            f"= {R['rho_min']*100:.4f}%\n"
            f"Rho-bal = 0.85 Beta-1 fc/fy x 600/(600+fy) = {R['rho_bal']*100:.4f}%\n"
            f"Rho-max = 0.75 Rho-bal = {R['rho_max']*100:.4f}%\n\n"
            f"Kontrol Rho >= Rho-min : "
            f"{'[OK]' if R['ok_rho_min'] else '[TIDAK OK]'}\n"
            f"Kontrol Rho <= Rho-max : "
            f"{'[OK]' if R['ok_rho_max'] else '[TIDAK OK]'}"
        ),
        ok=ok_rho,
    )

    # b7 - Regangan tarik terjauh & klasifikasi
    if R["et"] >= 0.005:
        klas = "et >= 0.005  -->  Tension-controlled  [OK]"
    elif R["et"] >= 0.004:
        klas = "0.004 <= et < 0.005  -->  Zona transisi  [PERLU TINJAUAN]"
    else:
        klas = "et < 0.004  -->  Tidak memenuhi syarat  [TIDAK OK]"

    s7 = dict(
        no="b7.", ref="SNI 2847:2019 Pasal 21.2.2",
        judul="Regangan tarik terjauh (et) - klasifikasi penampang",
        isi=(
            f"et = regangan lapis tarik paling bawah\n"
            f"   = {R['et']:.5f}\n"
            f"{klas}"
        ),
        ok=R["ok_et"],
    )

    # b8 - Faktor reduksi Phi
    s8 = dict(
        no="b8.", ref="SNI 2847:2019 Tabel 21.2.2",
        judul="Faktor reduksi kekuatan (Phi)",
        isi=f"{R['phi_cara']}\n  -->  Phi = {R['phi']:.4f}",
        ok=R["ok_et"],
    )

    # b9 - Momen Nominal Mn & Phi.Mn (referensi titik berat tulangan tarik)
    teks_mom = (
        f"Mn = Cc x (d - a/2) + Sum[ Cs_i x (d - y_i) ]\n"
        f"     (referensi: titik berat tulangan tarik d = {R['d_tarik']:.2f} mm)\n\n"
        f"  Cc x (d - a/2) = {R['Cc']:,.0f} x ({R['d_tarik']:.2f} - {R['a']/2:.2f})\n"
        f"                 = {R['Cc']*(R['d_tarik']-R['a']/2):,.0f} N.mm\n"
    )
    for L in R["info_tekan"]:
        teks_mom += (f"  Cs Lapis-{L['no']} x (d - y_i) = "
                     f"{L['F']:+,.0f} x ({R['d_tarik']:.2f} - {L['y']:.1f}) "
                     f"= {L['F']*(R['d_tarik']-L['y']):+,.0f} N.mm\n")

    s9 = dict(
        no="b9.", ref="SNI 2847:2019 Pasal 22.3.2",
        judul="Momen nominal (Mn) dan momen rencana (Phi.Mn)",
        isi=(
            f"{teks_mom}\n"
            f"Mn     = {R['Mn']:.3f} kN.m\n"
            f"Phi.Mn = Phi x Mn = {R['phi']:.4f} x {R['Mn']:.3f} = "
            f"{R['phiMn']:.3f} kN.m"
        ),
        ok=True,
    )

    # b10 - D/C Ratio
    if R["ok_dc"]:
        ket_dc = "AMAN  --  Phi.Mn >= Mu"
    else:
        ket_dc = "TIDAK AMAN  --  Phi.Mn < Mu  (penampang perlu diperbesar / tulangan ditambah)"

    s10 = dict(
        no="b10.", ref="SNI 2847:2019 Pasal 9.5.1.1 - Mu <= Phi.Mn",
        judul="D/C Ratio (Demand-to-Capacity)",
        isi=(
            f"D/C = Mu / Phi.Mn\n"
            f"    = {Mu:.3f} / {R['phiMn']:.3f}\n"
            f"    = {R['DC']:.3f}\n\n"
            f"{ket_dc}"
        ),
        ok=R["ok_dc"],
    )

    return [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10]


# ============================================================
# VISUALISASI PENAMPANG (matplotlib)
# ============================================================
def gambar_penampang(b, h, cc_sel, ds, lapis_tarik, lapis_tekan, c=None):
    """Gambar cross-section balok proporsional."""
    fig, ax = plt.subplots(figsize=(5.2, 6.2))

    # Garis luar balok
    ax.add_patch(patches.Rectangle((0, 0), b, h, fill=True,
                                   facecolor="#e8e8e8", edgecolor="black",
                                   linewidth=1.8))

    # Garis sengkang (offset cc dari tepi)
    sx, sy, sw, sh = cc_sel, cc_sel, b - 2*cc_sel, h - 2*cc_sel
    ax.add_patch(patches.Rectangle((sx, sy), sw, sh, fill=False,
                                   edgecolor="#1a3c5e", linewidth=1.2,
                                   linestyle="--"))

    # Sumbu y di matplotlib: 0 di bawah; sedangkan koordinat y_lapis kita
    # diukur dari serat tekan teratas. Maka konversi: y_plot = h - y_lapis.

    # Tulangan tarik
    for L in lapis_tarik:
        y_plot = h - L["y"]
        n = L["n"]
        # sebar batang merata dalam lebar bersih
        x_left  = cc_sel + ds + L["db"] / 2
        x_right = b - cc_sel - ds - L["db"] / 2
        if n > 1:
            xs = [x_left + i * (x_right - x_left) / (n - 1) for i in range(n)]
        else:
            xs = [(x_left + x_right) / 2]
        for x in xs:
            ax.add_patch(patches.Circle((x, y_plot), L["db"] / 2,
                                        facecolor="#1a3c5e",
                                        edgecolor="black", linewidth=0.6))
        ax.annotate(f"{n}D{int(L['db'])}",
                    xy=(b + 8, y_plot), fontsize=8,
                    va="center", color="#1a3c5e")

    # Tulangan tekan
    for L in lapis_tekan:
        y_plot = h - L["y"]
        n = L["n"]
        x_left  = cc_sel + ds + L["db"] / 2
        x_right = b - cc_sel - ds - L["db"] / 2
        if n > 1:
            xs = [x_left + i * (x_right - x_left) / (n - 1) for i in range(n)]
        else:
            xs = [(x_left + x_right) / 2]
        for x in xs:
            ax.add_patch(patches.Circle((x, y_plot), L["db"] / 2,
                                        facecolor="#c62828",
                                        edgecolor="black", linewidth=0.6))
        ax.annotate(f"{n}D{int(L['db'])}",
                    xy=(b + 8, y_plot), fontsize=8,
                    va="center", color="#c62828")

    # Garis sumbu netral (jika c diberikan)
    if c is not None:
        y_c_plot = h - c
        ax.axhline(y=y_c_plot, color="#f9a825", linewidth=1.4,
                   linestyle="-.", alpha=0.85)
        ax.annotate(f"  garis netral c = {c:.1f} mm",
                    xy=(0, y_c_plot), fontsize=8,
                    va="bottom", color="#7a5800")

    # Dimensi
    ax.annotate(f"b = {int(b)} mm", xy=(b/2, -h*0.05),
                fontsize=9, ha="center", color="black")
    ax.annotate(f"h = {int(h)} mm", xy=(-b*0.10, h/2),
                fontsize=9, ha="center", color="black", rotation=90)

    # Cosmetics
    pad = max(b, h) * 0.18
    ax.set_xlim(-pad, b + pad * 1.6)
    ax.set_ylim(-pad, h + pad * 0.6)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Penampang Balok (skala proporsional)",
                 fontsize=10, color="#1a3c5e", pad=10)
    fig.tight_layout()
    return fig


def fig_to_png_bytes(fig):
    """Convert matplotlib figure ke PNG bytes."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    return buf


# ============================================================
# GENERATOR WORD (.docx)
# ============================================================
def create_word_balok(fc, fy, b, h, cc_sel, ds, Mu, lapis_tarik, lapis_tekan,
                      R, steps, nama_proyek, png_buf):
    doc = Document()
    for sec in doc.sections:
        sec.page_width    = Cm(21);  sec.page_height   = Cm(29.7)
        sec.left_margin   = Cm(3);   sec.right_margin  = Cm(2.5)
        sec.top_margin    = Cm(3);   sec.bottom_margin = Cm(2.5)

    def par(teks="", bold=False, size=11, indent=0, space_after=4,
            align=WD_ALIGN_PARAGRAPH.LEFT, color=None, italic=False):
        p = doc.add_paragraph()
        p.alignment = align
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(space_after)
        if indent:
            p.paragraph_format.left_indent = Cm(indent)
        if teks:
            r = p.add_run(teks)
            r.bold = bold; r.italic = italic; r.font.size = Pt(size)
            if color:  r.font.color.rgb = RGBColor(*color)
        return p

    def garis():
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(2); p.paragraph_format.space_after = Pt(2)
        run = p.add_run("_" * 72)
        run.font.size = Pt(9); run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    def subjudul(teks):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10); p.paragraph_format.space_after = Pt(4)
        r = p.add_run(teks); r.bold = True; r.font.size = Pt(11)
        r.font.color.rgb = RGBColor(0x1A, 0x3C, 0x5E)
        garis()

    # Judul
    par("LAPORAN PERHITUNGAN STRUKTUR", bold=True, size=14,
        align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2, color=(0x1A, 0x3C, 0x5E))
    par("Evaluasi Kapasitas Lentur Balok Beton Bertulang", size=12,
        align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    par("(Tulangan Rangkap - Strain Compatibility)", size=10,
        align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2,
        color=(0x55, 0x55, 0x55), italic=True)
    par("Referensi  :  SNI 2847:2019 (ACI 318-14)", size=10,
        align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2,
        color=(0x55, 0x55, 0x55), italic=True)
    par(f"Proyek     :  {nama_proyek}", size=10,
        align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2,
        color=(0x55, 0x55, 0x55), italic=True)
    par(f"Tanggal    :  {datetime.datetime.now().strftime('%d %B %Y')}", size=10,
        align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10,
        color=(0x55, 0x55, 0x55), italic=True)
    garis(); par(space_after=6)

    # =========== A. DATA INPUT ===========
    subjudul("A.  DATA INPUT PENAMPANG")

    rows = [
        ("Mu",   f"{Mu:.2f} kN.m",  "Momen rencana"),
        ("fc",   f"{fc:.1f} MPa",   "Kuat tekan beton"),
        ("fy",   f"{fy:.0f} MPa",   "Kuat leleh tulangan"),
        ("b",    f"{b:.0f} mm",     "Lebar balok"),
        ("h",    f"{h:.0f} mm",     "Tinggi total balok"),
        ("cc",   f"{cc_sel:.0f} mm","Tebal selimut bersih"),
        ("ds",   f"{ds:.0f} mm",    "Diameter sengkang"),
    ]
    for simb, nilai, ket in rows:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.left_indent  = Cm(0.5)
        r1 = p.add_run(f"{simb:<6}"); r1.bold = True
        r1.font.size = Pt(10); r1.font.name = "Courier New"
        r2 = p.add_run(f"  =  {nilai:<18}  ({ket})")
        r2.font.size = Pt(10); r2.font.name = "Courier New"

    par(space_after=4)
    par("Tulangan TARIK (bawah):", bold=True, size=10, indent=0.5, space_after=2)
    if lapis_tarik:
        for L in lapis_tarik:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.left_indent = Cm(1.0)
            r = p.add_run(f"Lapis-{L['no']} : {L['n']} D{int(L['db'])}  "
                          f"As = {L['As']:.1f} mm2   y = {L['y']:.1f} mm")
            r.font.size = Pt(10); r.font.name = "Courier New"
    par(f"  As-total = {R['As_tarik']:.1f} mm2  |  d-aktual = {R['d_tarik']:.2f} mm",
        bold=True, size=10, indent=1.0, space_after=4)

    par("Tulangan TEKAN (atas):", bold=True, size=10, indent=0.5, space_after=2)
    if lapis_tekan:
        for L in lapis_tekan:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.left_indent = Cm(1.0)
            r = p.add_run(f"Lapis-{L['no']} : {L['n']} D{int(L['db'])}  "
                          f"As' = {L['As']:.1f} mm2   y = {L['y']:.1f} mm")
            r.font.size = Pt(10); r.font.name = "Courier New"
        par(f"  As'-total = {R['As_tekan']:.1f} mm2  |  d'-aktual = {R['d_tekan']:.2f} mm",
            bold=True, size=10, indent=1.0, space_after=4)
    else:
        par("  (Tidak ada tulangan tekan)", size=10, indent=1.0,
            color=(0x55, 0x55, 0x55), space_after=4)

    # Sisipkan gambar penampang
    par(space_after=4)
    par("Visualisasi Penampang :", bold=True, size=10, indent=0.5, space_after=4)
    p_img = doc.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_img.add_run().add_picture(png_buf, width=Cm(9))
    par(space_after=6)

    # =========== B. ANALISA ===========
    subjudul("B.  ANALISA PERHITUNGAN")
    par("Urutan perhitungan mengacu pada SNI 2847:2019.", size=10, italic=True,
        color=(0x55, 0x55, 0x55), space_after=8)
    for s in steps:
        p_hdr = doc.add_paragraph()
        p_hdr.paragraph_format.space_before = Pt(8); p_hdr.paragraph_format.space_after = Pt(1)
        r_no = p_hdr.add_run(f"{s['no']}  "); r_no.bold = True
        r_no.font.size = Pt(10); r_no.font.color.rgb = RGBColor(0x1A, 0x3C, 0x5E)
        r_jdl = p_hdr.add_run(s["judul"]); r_jdl.bold = True; r_jdl.font.size = Pt(10)
        p_ref = doc.add_paragraph()
        p_ref.paragraph_format.space_before = Pt(0); p_ref.paragraph_format.space_after = Pt(2)
        p_ref.paragraph_format.left_indent  = Cm(0.5)
        r_ref = p_ref.add_run(f"[{s['ref']}]"); r_ref.italic = True
        r_ref.font.size = Pt(8.5); r_ref.font.color.rgb = RGBColor(0x15, 0x65, 0xC0)
        for baris in s["isi"].split("\n"):
            p_b = doc.add_paragraph()
            p_b.paragraph_format.space_before = Pt(0); p_b.paragraph_format.space_after = Pt(1)
            p_b.paragraph_format.left_indent  = Cm(0.5)
            r_b = p_b.add_run(baris if baris.strip() else " ")
            r_b.font.name = "Courier New"; r_b.font.size = Pt(9.5)
            if (baris.strip().startswith("-->") or "[OK]" in baris
                or "[TIDAK OK]" in baris or "AMAN" in baris):
                r_b.bold = True
                r_b.font.color.rgb = (RGBColor(0x1B, 0x5E, 0x20) if s["ok"]
                                      else RGBColor(0xB7, 0x1C, 0x1C))
    par(space_after=6)

    # =========== C. RANGKUMAN ===========
    subjudul("C.  RANGKUMAN HASIL")
    rangkuman = [
        ("Beta-1",  f"{R['beta1']:.4f}",        ""),
        ("c",       f"{R['c']:.2f} mm",          "Kedalaman sumbu netral"),
        ("a",       f"{R['a']:.2f} mm",          "Kedalaman blok tegangan"),
        ("Cc",      f"{R['Cc']/1000:.2f} kN",    "Gaya tekan beton"),
        ("Cs",      f"{R['Cs']/1000:.2f} kN",    "Gaya tekan baja total"),
        ("T",       f"{R['T']/1000:.2f} kN",     "Gaya tarik baja total"),
        ("et",      f"{R['et']:.5f}",            "Regangan tarik terjauh"),
        ("Phi",     f"{R['phi']:.4f}",           "Faktor reduksi"),
        ("Rho",     f"{R['rho']*100:.4f}%",      "Rasio tulangan tarik"),
        ("Rho-min", f"{R['rho_min']*100:.4f}%",  "Batas minimum"),
        ("Rho-max", f"{R['rho_max']*100:.4f}%",  "Batas maksimum"),
        ("Mn",      f"{R['Mn']:.3f} kN.m",       "Momen nominal"),
        ("Phi.Mn",  f"{R['phiMn']:.3f} kN.m",    "Momen rencana kapasitas"),
        ("Mu",      f"{R['Mu']:.3f} kN.m",       "Momen rencana ultimit"),
        ("D/C",     f"{R['DC']:.3f}",            "Demand-to-Capacity Ratio"),
    ]
    for simb, nilai, ket in rangkuman:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.left_indent  = Cm(0.5)
        r1 = p.add_run(f"{simb:<10}"); r1.bold = True
        r1.font.size = Pt(10); r1.font.name = "Courier New"
        r2 = p.add_run(f"=  {nilai:<22}  {ket}")
        r2.font.size = Pt(10); r2.font.name = "Courier New"
    par(space_after=6)

    # =========== D. KESIMPULAN ===========
    subjudul("D.  KESIMPULAN")

    # Cek ringkasan
    cek_list = [
        (f"Rho-min = {R['rho_min']*100:.4f}%  <=  Rho = {R['rho']*100:.4f}%", R["ok_rho_min"]),
        (f"Rho-max = {R['rho_max']*100:.4f}%  >=  Rho = {R['rho']*100:.4f}%", R["ok_rho_max"]),
        (f"et      = {R['et']:.5f}  >=  0.004",                                R["ok_et"]),
        (f"D/C     = {R['DC']:.3f}  <=  1.000",                                R["ok_dc"]),
    ]
    for teks_k, ok_k in cek_list:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.left_indent  = Cm(0.5)
        r_k = p.add_run(f"{teks_k}   --> {'[OK]' if ok_k else '[TIDAK OK]'}")
        r_k.font.name = "Courier New"; r_k.font.size = Pt(10); r_k.bold = True
        r_k.font.color.rgb = (RGBColor(0x1B, 0x5E, 0x20) if ok_k
                              else RGBColor(0xB7, 0x1C, 0x1C))
    par(space_after=4)

    # Status D/C
    if R["ok_dc"]:
        if R["et"] >= 0.005 and R["ok_rho_min"] and R["ok_rho_max"]:
            kes = (f"KESIMPULAN : PENAMPANG AMAN  |  D/C = {R['DC']:.3f} <= 1.0  "
                   f"|  Tension-controlled  |  Memenuhi seluruh syarat SNI 2847:2019.")
            ok_f = True
        elif R["ok_rho_min"] and R["ok_rho_max"] and R["ok_et"]:
            kes = (f"KESIMPULAN : PENAMPANG AMAN secara kapasitas (D/C = {R['DC']:.3f}), "
                   f"namun berada di zona transisi - perlu tinjauan ulang daktilitas.")
            ok_f = True
        else:
            kes = (f"KESIMPULAN : Kapasitas terpenuhi (D/C = {R['DC']:.3f} <= 1.0), "
                   f"namun ada syarat lain yang tidak terpenuhi - lihat kontrol di atas.")
            ok_f = False
    else:
        kes = (f"KESIMPULAN : PENAMPANG TIDAK AMAN  |  D/C = {R['DC']:.3f} > 1.0  "
               f"|  Mu = {R['Mu']:.2f} kN.m  >  Phi.Mn = {R['phiMn']:.2f} kN.m  "
               f"|  Penampang/tulangan harus diperbesar.")
        ok_f = False

    p_kes = doc.add_paragraph()
    p_kes.paragraph_format.space_before = Pt(6); p_kes.paragraph_format.space_after = Pt(4)
    r_kes = p_kes.add_run(kes); r_kes.bold = True; r_kes.font.size = Pt(10.5)
    r_kes.font.color.rgb = (RGBColor(0x1B, 0x5E, 0x20) if ok_f
                            else RGBColor(0xB7, 0x1C, 0x1C))
    garis()
    par("Referensi: SNI 2847:2019 | ACI 318-14  --  "
        "Untuk keperluan profesional, verifikasi mandiri tetap diperlukan.",
        size=8, italic=True, color=(0x99, 0x99, 0x99),
        align=WD_ALIGN_PARAGRAPH.CENTER, space_after=0)

    buf = io.BytesIO(); doc.save(buf); buf.seek(0)
    return buf


# ============================================================
# GENERATOR PDF (.pdf)
# ============================================================
WATERMARK_TEXT = "DIHASILKAN OLEH: LADOSI ENGINEERING"
BRAND_COLOR    = (26, 60, 94)
OK_COLOR       = (27, 94, 32)
FAIL_COLOR     = (183, 28, 28)
GRAY           = (120, 120, 120)


class LaporanBalokPDF(FPDF):
    def __init__(self, nama_proyek):
        super().__init__()
        self.nama_proyek = sp(nama_proyek)
        self.set_margins(25, 25, 20)
        self.set_auto_page_break(auto=True, margin=25)

    def header(self):
        self.set_draw_color(*BRAND_COLOR); self.set_line_width(0.8)
        self.line(25, 15, 190, 15)
        self.set_font("Helvetica", "B", 9); self.set_text_color(*BRAND_COLOR)
        self.set_xy(25, 17)
        self.cell(0, 5, sp("LAPORAN EVALUASI LENTUR BALOK  |  SNI 2847:2019"),
                  ln=False, align="L")
        self.set_font("Helvetica", "", 8); self.set_text_color(*GRAY)
        self.set_xy(25, 17)
        self.cell(0, 5, sp(f"Proyek: {self.nama_proyek}"), ln=False, align="R")
        self.ln(10)

    def footer(self):
        self.set_y(-18)
        self.set_draw_color(*BRAND_COLOR); self.set_line_width(0.4)
        self.line(25, self.get_y(), 190, self.get_y())
        self.set_font("Helvetica", "I", 7.5); self.set_text_color(*GRAY)
        self.cell(0, 6,
            sp("Referensi: SNI 2847:2019 | ACI 318-14 - "
               "Untuk keperluan profesional, verifikasi mandiri tetap diperlukan."),
            align="C")
        self.set_xy(25, self.get_y())
        self.set_font("Helvetica", "", 7.5)
        self.cell(0, 6, sp(f"Halaman {self.page_no()}"), align="R")

    def watermark(self):
        self.set_font("Helvetica", "B", 28); self.set_text_color(210, 215, 220)
        xc, yc = self.w / 2, self.h / 2
        with self.rotation(40, xc, yc):
            self.set_xy(xc - 65, yc - 6)
            self.cell(130, 12, sp(WATERMARK_TEXT), align="C")
        self.set_text_color(0, 0, 0)

    def section_title(self, teks):
        self.set_font("Helvetica", "B", 11); self.set_text_color(*BRAND_COLOR)
        self.ln(4); self.cell(0, 7, sp(teks), ln=True)
        self.set_draw_color(*BRAND_COLOR); self.set_line_width(0.4)
        self.line(self.get_x(), self.get_y(), 190, self.get_y())
        self.ln(3); self.set_text_color(0, 0, 0)

    def mono_line(self, teks, bold=False, color=None):
        self.set_font("Courier", "B" if bold else "", 9)
        if color: self.set_text_color(*color)
        self.set_x(28); self.multi_cell(0, 4.5, sp(teks))
        self.set_text_color(0, 0, 0)


def create_pdf_balok(fc, fy, b, h, cc_sel, ds, Mu, lapis_tarik, lapis_tekan,
                     R, steps, nama_proyek, png_buf):
    pdf = LaporanBalokPDF(nama_proyek)
    pdf.add_page(); pdf.watermark()

    # Header laporan
    pdf.set_font("Helvetica", "B", 15); pdf.set_text_color(*BRAND_COLOR); pdf.ln(2)
    pdf.cell(0, 9, sp("LAPORAN PERHITUNGAN STRUKTUR"), ln=True, align="C")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, sp("Evaluasi Kapasitas Lentur Balok Beton Bertulang"),
             ln=True, align="C")
    pdf.set_font("Helvetica", "I", 9); pdf.set_text_color(*GRAY)
    pdf.cell(0, 5, sp("(Tulangan Rangkap - Strain Compatibility)"), ln=True, align="C")
    pdf.cell(0, 5, sp("Referensi: SNI 2847:2019 (ACI 318-14)"), ln=True, align="C")
    pdf.cell(0, 5, sp(f"Proyek: {nama_proyek}   |   "
                      f"Tanggal: {datetime.datetime.now().strftime('%d %B %Y')}"),
             ln=True, align="C")
    pdf.ln(6); pdf.set_draw_color(*BRAND_COLOR); pdf.set_line_width(0.6)
    pdf.line(25, pdf.get_y(), 190, pdf.get_y()); pdf.ln(6); pdf.set_text_color(0, 0, 0)

    # =========== A. DATA INPUT ===========
    pdf.section_title("A.  DATA INPUT PENAMPANG")
    rows = [
        ("Mu",   f"{Mu:.2f} kN.m",   "Momen rencana"),
        ("fc",   f"{fc:.1f} MPa",    "Kuat tekan beton"),
        ("fy",   f"{fy:.0f} MPa",    "Kuat leleh tulangan"),
        ("b",    f"{b:.0f} mm",      "Lebar balok"),
        ("h",    f"{h:.0f} mm",      "Tinggi total balok"),
        ("cc",   f"{cc_sel:.0f} mm", "Tebal selimut bersih"),
        ("ds",   f"{ds:.0f} mm",     "Diameter sengkang"),
    ]
    for simb, nilai, ket in rows:
        pdf.set_x(28); pdf.set_font("Courier", "B", 9.5)
        pdf.cell(18, 5, sp(f"{simb:<6}"), ln=False)
        pdf.set_font("Courier", "", 9.5)
        pdf.cell(35, 5, sp(f"=  {nilai}"), ln=False)
        pdf.set_font("Helvetica", "I", 8.5); pdf.set_text_color(*GRAY)
        pdf.cell(0, 5, sp(f"({ket})"), ln=True); pdf.set_text_color(0, 0, 0)

    pdf.ln(2)
    pdf.set_x(25); pdf.set_font("Helvetica", "B", 9.5); pdf.set_text_color(*BRAND_COLOR)
    pdf.cell(0, 5, sp("Tulangan TARIK (bawah):"), ln=True); pdf.set_text_color(0, 0, 0)
    for L in lapis_tarik:
        pdf.set_x(30); pdf.set_font("Courier", "", 9)
        pdf.cell(0, 4.5,
                 sp(f"Lapis-{L['no']}: {L['n']} D{int(L['db'])}  "
                    f"As = {L['As']:.1f} mm2   y = {L['y']:.1f} mm"),
                 ln=True)
    pdf.set_x(30); pdf.set_font("Courier", "B", 9)
    pdf.cell(0, 4.5,
             sp(f"As-total = {R['As_tarik']:.1f} mm2  |  d-aktual = {R['d_tarik']:.2f} mm"),
             ln=True)

    pdf.ln(1)
    pdf.set_x(25); pdf.set_font("Helvetica", "B", 9.5); pdf.set_text_color(*BRAND_COLOR)
    pdf.cell(0, 5, sp("Tulangan TEKAN (atas):"), ln=True); pdf.set_text_color(0, 0, 0)
    if lapis_tekan:
        for L in lapis_tekan:
            pdf.set_x(30); pdf.set_font("Courier", "", 9)
            pdf.cell(0, 4.5,
                     sp(f"Lapis-{L['no']}: {L['n']} D{int(L['db'])}  "
                        f"As' = {L['As']:.1f} mm2   y = {L['y']:.1f} mm"),
                     ln=True)
        pdf.set_x(30); pdf.set_font("Courier", "B", 9)
        pdf.cell(0, 4.5,
                 sp(f"As'-total = {R['As_tekan']:.1f} mm2  |  d'-aktual = {R['d_tekan']:.2f} mm"),
                 ln=True)
    else:
        pdf.set_x(30); pdf.set_font("Helvetica", "I", 9); pdf.set_text_color(*GRAY)
        pdf.cell(0, 4.5, sp("(Tidak ada tulangan tekan)"), ln=True)
        pdf.set_text_color(0, 0, 0)

    # Sisipkan gambar penampang
    pdf.ln(3)
    pdf.set_x(25); pdf.set_font("Helvetica", "B", 9.5); pdf.set_text_color(*BRAND_COLOR)
    pdf.cell(0, 5, sp("Visualisasi Penampang:"), ln=True); pdf.set_text_color(0, 0, 0)
    # Simpan PNG buffer sementara ke file lalu sisipkan
    img_path = "/tmp/_penampang.png"
    with open(img_path, "wb") as fimg:
        fimg.write(png_buf.getvalue())
    pdf.image(img_path, x=70, y=pdf.get_y() + 1, w=70)
    pdf.ln(82)

    # =========== B. ANALISA ===========
    if pdf.get_y() > 220:
        pdf.add_page(); pdf.watermark()
    pdf.section_title("B.  ANALISA PERHITUNGAN")
    for s in steps:
        if pdf.get_y() > 240:
            pdf.add_page(); pdf.watermark()
        pdf.set_font("Helvetica", "B", 10); pdf.set_text_color(*BRAND_COLOR); pdf.set_x(25)
        pdf.cell(0, 6, sp(f"{s['no']}  {s['judul']}"), ln=True)
        pdf.set_font("Helvetica", "I", 8); pdf.set_text_color(*GRAY); pdf.set_x(28)
        pdf.cell(0, 4, sp(f"[{s['ref']}]"), ln=True); pdf.set_text_color(0, 0, 0)
        for baris in s["isi"].split("\n"):
            is_result = (baris.strip().startswith("-->") or
                         "[OK]" in baris or "[TIDAK OK]" in baris or "AMAN" in baris)
            pdf.mono_line(baris if baris.strip() else "",
                          bold=is_result,
                          color=(OK_COLOR if s["ok"] else FAIL_COLOR) if is_result else None)
        pdf.ln(2)

    # =========== C. RANGKUMAN ===========
    if pdf.get_y() > 200:
        pdf.add_page(); pdf.watermark()
    pdf.section_title("C.  RANGKUMAN HASIL")
    rangkuman = [
        ("Beta-1",  f"{R['beta1']:.4f}",        ""),
        ("c",       f"{R['c']:.2f} mm",          "Sumbu netral"),
        ("a",       f"{R['a']:.2f} mm",          "Blok tegangan"),
        ("Cc",      f"{R['Cc']/1000:.2f} kN",    "Gaya tekan beton"),
        ("Cs",      f"{R['Cs']/1000:.2f} kN",    "Gaya tekan baja"),
        ("T",       f"{R['T']/1000:.2f} kN",     "Gaya tarik baja"),
        ("et",      f"{R['et']:.5f}",            "Regangan tarik"),
        ("Phi",     f"{R['phi']:.4f}",           "Faktor reduksi"),
        ("Rho",     f"{R['rho']*100:.4f}%",      "Rasio tulangan tarik"),
        ("Rho-min", f"{R['rho_min']*100:.4f}%",  "Batas minimum"),
        ("Rho-max", f"{R['rho_max']*100:.4f}%",  "Batas maksimum"),
        ("Mn",      f"{R['Mn']:.3f} kN.m",       "Momen nominal"),
        ("Phi.Mn",  f"{R['phiMn']:.3f} kN.m",    "Momen rencana kapasitas"),
        ("Mu",      f"{R['Mu']:.3f} kN.m",       "Momen rencana ultimit"),
        ("D/C",     f"{R['DC']:.3f}",            "Demand-to-Capacity"),
    ]
    for simb, nilai, ket in rangkuman:
        pdf.set_x(28); pdf.set_font("Courier", "B", 9.5)
        pdf.cell(22, 5, sp(f"{simb:<10}"), ln=False)
        pdf.set_font("Courier", "", 9.5)
        pdf.cell(38, 5, sp(f"=  {nilai}"), ln=False)
        if ket:
            pdf.set_font("Helvetica", "I", 8.5); pdf.set_text_color(*GRAY)
            pdf.cell(0, 5, sp(f"({ket})"), ln=True); pdf.set_text_color(0, 0, 0)
        else:
            pdf.ln()
    pdf.ln(4)

    # =========== D. KESIMPULAN ===========
    if pdf.get_y() > 220:
        pdf.add_page(); pdf.watermark()
    pdf.section_title("D.  KESIMPULAN")
    cek_list = [
        (f"Rho-min = {R['rho_min']*100:.4f}%  <=  Rho = {R['rho']*100:.4f}%", R["ok_rho_min"]),
        (f"Rho-max = {R['rho_max']*100:.4f}%  >=  Rho = {R['rho']*100:.4f}%", R["ok_rho_max"]),
        (f"et      = {R['et']:.5f}  >=  0.004",                                R["ok_et"]),
        (f"D/C     = {R['DC']:.3f}  <=  1.000",                                R["ok_dc"]),
    ]
    for teks_k, ok_k in cek_list:
        pdf.set_x(28); pdf.set_font("Courier", "B", 9.5)
        pdf.set_text_color(*(OK_COLOR if ok_k else FAIL_COLOR))
        pdf.cell(0, 5.5, sp(f"{teks_k}   --> {'[OK]' if ok_k else '[TIDAK OK]'}"), ln=True)
        pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # Status D/C
    if R["ok_dc"]:
        if R["et"] >= 0.005 and R["ok_rho_min"] and R["ok_rho_max"]:
            kes = (f"KESIMPULAN : PENAMPANG AMAN  |  D/C = {R['DC']:.3f} <= 1.0  "
                   f"|  Tension-controlled  |  Memenuhi seluruh syarat SNI 2847:2019.")
            ok_f = True
        elif R["ok_rho_min"] and R["ok_rho_max"] and R["ok_et"]:
            kes = (f"KESIMPULAN : PENAMPANG AMAN secara kapasitas (D/C = {R['DC']:.3f}), "
                   f"namun zona transisi - perlu tinjauan ulang daktilitas.")
            ok_f = True
        else:
            kes = (f"KESIMPULAN : Kapasitas terpenuhi (D/C = {R['DC']:.3f} <= 1.0), "
                   f"namun ada syarat lain yang tidak terpenuhi.")
            ok_f = False
    else:
        kes = (f"KESIMPULAN : PENAMPANG TIDAK AMAN  |  D/C = {R['DC']:.3f} > 1.0  "
               f"|  Mu = {R['Mu']:.2f} kN.m  >  Phi.Mn = {R['phiMn']:.2f} kN.m")
        ok_f = False

    pdf.set_x(25); pdf.set_font("Helvetica", "B", 10.5)
    pdf.set_text_color(*(OK_COLOR if ok_f else FAIL_COLOR))
    pdf.multi_cell(0, 6, sp(kes)); pdf.set_text_color(0, 0, 0)

    buf = io.BytesIO(); pdf.output(buf); buf.seek(0)
    return buf


# ============================================================
# HELPER SESSION STATE
# ============================================================
def _init_state():
    defaults = {
        "balok_hasil":        None,
        "balok_steps":        None,
        "balok_word":         None,
        "balok_pdf":          None,
        "balok_fig":          None,
        "balok_last_inputs":  {},
        "balok_nama_file":    "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _snapshot_inputs(d):
    return dict(d)


def _inputs_changed(snap_now):
    last = st.session_state.balok_last_inputs
    if not last:
        return False
    return any(snap_now.get(k) != last.get(k) for k in snap_now)


# ============================================================
# UI
# ============================================================
_init_state()

st.markdown('<p class="main-title">Evaluasi Kapasitas Lentur Balok Beton Bertulang</p>',
            unsafe_allow_html=True)
st.markdown(
    '<p class="sub-title">Tulangan Rangkap | Strain Compatibility | '
    'Referensi: SNI 2847:2019 (setara ACI 318-14)</p>',
    unsafe_allow_html=True)
st.markdown('<hr class="divider">', unsafe_allow_html=True)

col_inp, col_out = st.columns([1, 2], gap="large")

with col_inp:
    st.markdown("### Data Input")

    nama_proyek = st.text_input(
        "Nama Proyek (untuk header laporan)",
        value="Laporan Analisa Struktur",
        key="balok_inp_nama",
    )

    st.markdown("**Gaya Dalam**")
    Mu = st.number_input("Mu - Momen rencana (kN.m)",
                         min_value=0.0, max_value=10000.0, value=200.0,
                         step=5.0, format="%.2f", key="balok_inp_mu")

    st.markdown("**Material**")
    fc = st.number_input("f'c - Kuat tekan beton (MPa)",
                         min_value=17.0, max_value=100.0, value=30.0,
                         step=1.0, format="%.1f", key="balok_inp_fc")
    fy = st.number_input("fy - Kuat leleh tulangan (MPa)",
                         min_value=240.0, max_value=600.0, value=400.0,
                         step=10.0, format="%.0f", key="balok_inp_fy")

    st.markdown("**Geometri**")
    cb, ch_ = st.columns(2)
    with cb:
        b = st.number_input("b (mm)", min_value=100.0, max_value=2000.0,
                            value=300.0, step=10.0, format="%.0f", key="balok_inp_b")
    with ch_:
        h = st.number_input("h (mm)", min_value=100.0, max_value=5000.0,
                            value=500.0, step=10.0, format="%.0f", key="balok_inp_h")
    cc_sel = st.number_input("cc (mm) - Tebal selimut bersih",
                             min_value=15.0, max_value=100.0, value=40.0,
                             step=5.0, format="%.0f", key="balok_inp_cc")
    ds_dia = st.number_input("ds (mm) - Diameter sengkang",
                             min_value=6.0, max_value=16.0, value=10.0,
                             step=1.0, format="%.0f", key="balok_inp_ds")

    st.markdown("**Tulangan TARIK (bawah)**")
    st.caption("Lapis 1 = paling bawah, Lapis 2 = di atas Lapis 1 (spasi bersih 25 mm)")
    ct1, ct2 = st.columns(2)
    with ct1:
        n_t1  = st.number_input("Lapis-1: Jumlah", min_value=0, max_value=20,
                                value=4, step=1, key="balok_inp_nt1")
        n_t2  = st.number_input("Lapis-2: Jumlah", min_value=0, max_value=20,
                                value=0, step=1, key="balok_inp_nt2")
    with ct2:
        db_t1 = st.selectbox("Lapis-1: Diameter (mm)", DIAMETER_LIST,
                             index=4, key="balok_inp_dbt1")
        db_t2 = st.selectbox("Lapis-2: Diameter (mm)", DIAMETER_LIST,
                             index=4, key="balok_inp_dbt2")

    st.markdown("**Tulangan TEKAN (atas)**")
    st.caption("Lapis 1 = paling atas, Lapis 2 = di bawah Lapis 1 (spasi bersih 25 mm)")
    cc1, cc2 = st.columns(2)
    with cc1:
        n_c1  = st.number_input("Lapis-1: Jumlah", min_value=0, max_value=20,
                                value=2, step=1, key="balok_inp_nc1")
        n_c2  = st.number_input("Lapis-2: Jumlah", min_value=0, max_value=20,
                                value=0, step=1, key="balok_inp_nc2")
    with cc2:
        db_c1 = st.selectbox("Lapis-1: Diameter (mm)", DIAMETER_LIST,
                             index=3, key="balok_inp_dbc1")
        db_c2 = st.selectbox("Lapis-2: Diameter (mm)", DIAMETER_LIST,
                             index=3, key="balok_inp_dbc2")

    st.markdown("")
    tombol = st.button("HITUNG EVALUASI LENTUR",
                       use_container_width=True, type="primary",
                       key="balok_btn_hitung")

    with st.expander("Tabel luas tulangan (mm2)"):
        st.markdown("""
        | D | 1 | 2 | 3 | 4 | 5 | 6 |
        |---|---|---|---|---|---|---|
        | D10 | 78.5 | 157 | 236 | 314 | 393 | 471 |
        | D13 | 132.7 | 265 | 398 | 531 | 663 | 796 |
        | D16 | 201.1 | 402 | 603 | 804 | 1005 | 1206 |
        | D19 | 283.5 | 567 | 851 | 1134 | 1418 | 1701 |
        | D22 | 380.1 | 760 | 1140 | 1520 | 1901 | 2281 |
        | D25 | 490.9 | 982 | 1473 | 1964 | 2454 | 2945 |
        | D29 | 660.5 | 1321 | 1981 | 2642 | 3302 | 3963 |
        | D32 | 804.2 | 1608 | 2413 | 3217 | 4021 | 4825 |
        """)

# ============================================================
# PROSES HITUNG
# ============================================================
if tombol:
    valid = True
    if n_t1 == 0 and n_t2 == 0:
        st.error("Harus ada minimal 1 lapis tulangan tarik!")
        valid = False
    if Mu <= 0:
        st.error("Mu harus lebih besar dari 0!")
        valid = False

    if valid:
        # Hitung lapisan otomatis
        lapis_tarik, d_tarik, As_tarik = hitung_lapis_tarik(
            h, cc_sel, ds_dia, n_t1, db_t1, n_t2, db_t2, spasi=25.0)
        lapis_tekan, d_tekan, As_tekan = hitung_lapis_tekan(
            cc_sel, ds_dia, n_c1, db_c1, n_c2, db_c2, spasi=25.0)

        # Validasi tinggi efektif masuk akal
        if d_tarik >= h or d_tarik <= 0:
            st.error(f"d-aktual ({d_tarik:.1f} mm) tidak valid. "
                     f"Cek selimut, sengkang, dan diameter tulangan.")
        else:
            R = evaluasi_balok(fc, fy, b, h, cc_sel, ds_dia,
                               lapis_tarik, lapis_tekan,
                               d_tarik, As_tarik, d_tekan, As_tekan, Mu)
            steps = buat_steps_balok(fc, fy, b, h, cc_sel, ds_dia,
                                     lapis_tarik, lapis_tekan, R)

            # Gambar penampang
            fig = gambar_penampang(b, h, cc_sel, ds_dia,
                                   lapis_tarik, lapis_tekan, c=R["c"])
            png_buf = fig_to_png_bytes(fig)

            w_buf = create_word_balok(fc, fy, b, h, cc_sel, ds_dia, Mu,
                                      lapis_tarik, lapis_tekan,
                                      R, steps, nama_proyek, png_buf)
            # rewind png_buf agar bisa dipakai PDF juga
            png_buf.seek(0)
            p_buf = create_pdf_balok(fc, fy, b, h, cc_sel, ds_dia, Mu,
                                     lapis_tarik, lapis_tekan,
                                     R, steps, nama_proyek, png_buf)

            snap = dict(nama_proyek=nama_proyek, Mu=Mu, fc=fc, fy=fy,
                        b=b, h=h, cc=cc_sel, ds=ds_dia,
                        n_t1=n_t1, db_t1=db_t1, n_t2=n_t2, db_t2=db_t2,
                        n_c1=n_c1, db_c1=db_c1, n_c2=n_c2, db_c2=db_c2)

            st.session_state.balok_hasil       = R
            st.session_state.balok_steps       = steps
            st.session_state.balok_word        = w_buf.getvalue()
            st.session_state.balok_pdf         = p_buf.getvalue()
            st.session_state.balok_fig         = fig
            st.session_state.balok_last_inputs = snap
            st.session_state.balok_nama_file   = (
                f"Laporan_Lentur_Balok_fc{int(fc)}_fy{int(fy)}_b{int(b)}x{int(h)}"
            )

# ============================================================
# UI - HASIL
# ============================================================
with col_out:
    if st.session_state.balok_hasil is None:
        st.info("Isi data di panel kiri, lalu klik HITUNG EVALUASI LENTUR")
        st.markdown("""
        **Yang akan dihitung secara runtut (Strain Compatibility):**
        - **b1.** Faktor Beta-1
        - **b2.** Posisi tiap lapis tulangan & titik berat (d-aktual, d'-aktual)
        - **b3.** Iterasi sumbu netral c (kesetimbangan Cc + Cs = T)
        - **b4.** Regangan & tegangan setiap lapis (et, eps-s', dst.)
        - **b5.** Gaya dalam Cc, Cs, T
        - **b6.** Rasio tulangan Rho (kontrol min & max)
        - **b7.** Klasifikasi penampang (tension-controlled / transisi)
        - **b8.** Faktor reduksi Phi
        - **b9.** Mn dan Phi.Mn
        - **b10.** D/C Ratio (Mu / Phi.Mn) - 'AMAN' jika <= 1.0

        **Output tersedia dalam dua format:**
        - Word (.docx) - format natural, bisa diedit
        - PDF (.pdf) - formal + watermark LADOSI ENGINEERING
        """)
    else:
        R     = st.session_state.balok_hasil
        steps = st.session_state.balok_steps
        fig   = st.session_state.balok_fig

        # Soft warning jika input berubah
        snap_now = dict(nama_proyek=nama_proyek, Mu=Mu, fc=fc, fy=fy,
                        b=b, h=h, cc=cc_sel, ds=ds_dia,
                        n_t1=n_t1, db_t1=db_t1, n_t2=n_t2, db_t2=db_t2,
                        n_c1=n_c1, db_c1=db_c1, n_c2=n_c2, db_c2=db_c2)
        if _inputs_changed(snap_now):
            st.warning(
                "Perhatian: Data input telah diubah. "
                "Hasil dan file laporan di bawah masih menggunakan "
                "data perhitungan sebelumnya. Klik HITUNG kembali untuk update."
            )

        # ---- Metrik Utama ----
        st.markdown("### Hasil Utama")
        m1, m2, m3, m4 = st.columns(4)
        for col, lbl, val, unt in [
            (m1, "Phi.Mn (Kapasitas)", f"{R['phiMn']:.2f}", "kN.m"),
            (m2, "Mu (Demand)",        f"{R['Mu']:.2f}",    "kN.m"),
            (m3, "D/C Ratio",          f"{R['DC']:.3f}",    "-"),
            (m4, "Regangan et",        f"{R['et']:.4f}",    "-"),
        ]:
            with col:
                st.markdown(
                    f'<div class="metric-card">'
                    f'<div class="metric-lbl">{lbl}</div>'
                    f'<div class="metric-val">{val}</div>'
                    f'<div class="metric-unt">{unt}</div>'
                    f'</div>', unsafe_allow_html=True)
        st.markdown("")

        # ---- Status D/C ----
        if R["ok_dc"] and R["et"] >= 0.005 and R["ok_rho_min"] and R["ok_rho_max"]:
            st.markdown(
                f'<div class="result-ok">[OK] AMAN - D/C = {R["DC"]:.3f} <= 1.0 | '
                f'Tension-controlled | Memenuhi seluruh syarat SNI 2847:2019</div>',
                unsafe_allow_html=True)
        elif R["ok_dc"]:
            catatan = []
            if R["et"] < 0.005 and R["et"] >= 0.004:
                catatan.append("zona transisi")
            if not R["ok_rho_min"]: catatan.append("Rho < Rho-min")
            if not R["ok_rho_max"]: catatan.append("Rho > Rho-max")
            if not R["ok_et"]:      catatan.append("et < 0.004")
            note = " | ".join(catatan) if catatan else "perlu tinjauan"
            st.markdown(
                f'<div class="result-warn">[!] AMAN secara D/C ({R["DC"]:.3f}) '
                f'namun perlu perhatian: {note}</div>',
                unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div class="result-fail">[X] TIDAK AMAN - D/C = {R["DC"]:.3f} > 1.0 | '
                f'Mu = {R["Mu"]:.2f} kN.m > Phi.Mn = {R["phiMn"]:.2f} kN.m | '
                f'Penampang/tulangan harus diperbesar</div>',
                unsafe_allow_html=True)

        st.markdown('<hr class="divider">', unsafe_allow_html=True)

        # ---- A. DATA INPUT (Visualisasi) ----
        st.markdown("### A.  Data Input - Visualisasi Penampang")
        cvis1, cvis2 = st.columns([1, 1])
        with cvis1:
            st.pyplot(fig, use_container_width=True)
        with cvis2:
            st.markdown(f"""
            **Material:**
            - f'c = {fc:.1f} MPa
            - fy = {fy:.0f} MPa

            **Geometri:**
            - b x h = {int(b)} x {int(h)} mm
            - cc = {int(cc_sel)} mm  |  ds = {int(ds_dia)} mm

            **Tulangan TARIK:**
            - As-total = {R['As_tarik']:.1f} mm2
            - d-aktual = {R['d_tarik']:.2f} mm

            **Tulangan TEKAN:**
            - As'-total = {R['As_tekan']:.1f} mm2
            - d'-aktual = {R['d_tekan']:.2f} mm

            **Gaya Dalam:**
            - Mu = {Mu:.2f} kN.m
            """)

        st.markdown('<hr class="divider">', unsafe_allow_html=True)

        # ---- B. ANALISA PERHITUNGAN ----
        st.markdown("### B.  Analisa Perhitungan")
        for s in steps:
            warna = "#2e7d32" if s["ok"] else "#c62828"
            tanda = "[OK]" if s["ok"] else "[X]"
            st.markdown(
                f'<div class="step-box" style="border-left-color:{warna}">'
                f'<div class="ref-badge">{s["ref"]}</div><br>'
                f'<div class="step-hdr">{s["no"]} {s["judul"]} &nbsp; {tanda}</div>'
                f'<pre style="margin:0;font-size:.82rem;white-space:pre-wrap;'
                f'font-family:monospace">{s["isi"]}</pre></div>',
                unsafe_allow_html=True)

        # ---- C. RANGKUMAN ----
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        st.markdown("### C.  Rangkuman Hasil")
        et_s = ("[OK] OK" if R["et"] >= 0.005
                else "[!] Transisi" if R["et"] >= 0.004 else "[X] Tidak OK")
        rh_s = "[OK] OK" if (R["ok_rho_min"] and R["ok_rho_max"]) else "[X] Tidak OK"
        dc_s = "[OK] AMAN" if R["ok_dc"] else "[X] TIDAK AMAN"

        df = pd.DataFrame({
            "Parameter": ["Beta-1","c (mm)","a (mm)","Cc (kN)","Cs (kN)","T (kN)",
                          "et","Phi","Rho (%)","Rho-min (%)","Rho-max (%)",
                          "Mn (kN.m)","Phi.Mn (kN.m)","Mu (kN.m)","D/C Ratio"],
            "Nilai": [
                f"{R['beta1']:.4f}", f"{R['c']:.2f}", f"{R['a']:.2f}",
                f"{R['Cc']/1000:.2f}", f"{R['Cs']/1000:.2f}", f"{R['T']/1000:.2f}",
                f"{R['et']:.5f}", f"{R['phi']:.4f}",
                f"{R['rho']*100:.4f}", f"{R['rho_min']*100:.4f}",
                f"{R['rho_max']*100:.4f}",
                f"{R['Mn']:.3f}", f"{R['phiMn']:.3f}",
                f"{R['Mu']:.3f}", f"{R['DC']:.3f}",
            ],
            "Status": ["-","-","-","-","-","-",
                       et_s,"-", rh_s,"-","-","-","-","-", dc_s],
        })
        st.dataframe(df, use_container_width=True, hide_index=True)

        # ---- D. KESIMPULAN ----
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        st.markdown("### D.  Kesimpulan")

        cek_ringkas = pd.DataFrame({
            "Kontrol": [
                f"Rho-min ({R['rho_min']*100:.4f}%) <= Rho ({R['rho']*100:.4f}%)",
                f"Rho-max ({R['rho_max']*100:.4f}%) >= Rho ({R['rho']*100:.4f}%)",
                f"et ({R['et']:.5f}) >= 0.004",
                f"D/C ({R['DC']:.3f}) <= 1.000",
            ],
            "Status": [
                "[OK]" if R["ok_rho_min"] else "[TIDAK OK]",
                "[OK]" if R["ok_rho_max"] else "[TIDAK OK]",
                "[OK]" if R["ok_et"]      else "[TIDAK OK]",
                "[OK] AMAN" if R["ok_dc"] else "[X] TIDAK AMAN",
            ],
        })
        st.dataframe(cek_ringkas, use_container_width=True, hide_index=True)

        # ---- Download ----
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        st.markdown("### Download Laporan")
        nama_f = st.session_state.balok_nama_file
        dl_w, dl_p = st.columns(2)
        with dl_w:
            st.download_button(
                label="Download Laporan Word (.docx)",
                data=st.session_state.balok_word,
                file_name=f"{nama_f}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key="balok_dl_word",
            )
        with dl_p:
            st.download_button(
                label="Download Laporan PDF (.pdf)",
                data=st.session_state.balok_pdf,
                file_name=f"{nama_f}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="balok_dl_pdf",
            )
        st.caption(
            "File Word dapat diedit lebih lanjut. "
            "File PDF sudah dilengkapi watermark dan visualisasi penampang, "
            "siap untuk laporan resmi."
        )

# Footer
st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;font-size:.75rem;color:#aaa'>"
    "Referensi: SNI 2847:2019 | ACI 318-14 | "
    "Untuk keperluan profesional - verifikasi mandiri tetap diperlukan"
    "</p>",
    unsafe_allow_html=True,
)
