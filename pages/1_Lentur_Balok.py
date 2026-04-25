"""
=============================================================
APLIKASI WEB — KAPASITAS LENTUR BALOK BETON BERTULANG
Referensi : SNI 2847:2019 (ACI 318-14)
Framework  : Streamlit
Output     : Word (.docx) & PDF (.pdf)
=============================================================
"""

import math
import io
import datetime
import streamlit as st
import pandas as pd
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from fpdf import FPDF

# ════════════════════════════════════════════════════════════
# KONFIGURASI HALAMAN
# ════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Lentur Balok Beton | SNI 2847:2019",
    page_icon="🏗️",
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


# ════════════════════════════════════════════════════════════
# FUNGSI PERHITUNGAN
# ════════════════════════════════════════════════════════════
def hitung(fc, fy, b, h, d, As, Asp):
    R = {}

    # beta1
    if fc <= 28:
        beta1 = 0.85
        R["beta1_cara"] = f"fc = {fc} MPa <= 28 MPa  -->  Beta-1 = 0.85"
    elif fc >= 56:
        beta1 = 0.65
        R["beta1_cara"] = f"fc = {fc} MPa >= 56 MPa  -->  Beta-1 = 0.65"
    else:
        beta1 = max(0.65, min(0.85, 0.85 - 0.05 * (fc - 28) / 7))
        R["beta1_cara"] = (
            f"Beta-1 = 0.85 - 0.05 x (fc - 28) / 7\n"
            f"       = 0.85 - 0.05 x ({fc} - 28) / 7"
        )
    R["beta1"] = beta1

    As_net  = As - Asp
    T       = As_net * fy
    a       = (As_net * fy) / (0.85 * fc * b)
    c       = a / beta1
    rho     = As / (b * d)
    rho_mA  = 0.25 * math.sqrt(fc) / fy
    rho_mB  = 1.4 / fy
    rho_min = max(rho_mA, rho_mB)
    rho_bal = (0.85 * beta1 * fc / fy) * (600 / (600 + fy))
    rho_max = 0.75 * rho_bal
    et      = 0.003 * (d - c) / c

    if et >= 0.005:
        phi = 0.90
        R["phi_cara"] = "et >= 0.005  -->  Tension-controlled  -->  Phi = 0.90"
    elif et <= 0.002:
        phi = 0.65
        R["phi_cara"] = "et <= 0.002  -->  Compression-controlled  -->  Phi = 0.65"
    else:
        phi = 0.65 + (et - 0.002) * (250 / 3)
        R["phi_cara"] = (
            f"0.002 < et < 0.005  -->  Zona transisi\n"
            f"Phi = 0.65 + (et - 0.002) x 250/3\n"
            f"    = 0.65 + ({et:.5f} - 0.002) x 83.333"
        )

    Mn    = As_net * fy * (d - a / 2) / 1_000_000
    phiMn = phi * Mn

    R.update(dict(
        As_net=As_net, T=T, a=a, c=c,
        rho=rho, rho_mA=rho_mA, rho_mB=rho_mB,
        rho_min=rho_min, rho_bal=rho_bal, rho_max=rho_max,
        et=et, phi=phi, Mn=Mn, phiMn=phiMn,
        ok_rho_min=(rho >= rho_min),
        ok_rho_max=(rho <= rho_max),
        ok_et=(et >= 0.004),
    ))
    return R


def buat_steps(fc, fy, b, h, d, As, Asp, R):
    """Kembalikan list dict langkah-langkah, dipakai UI & export."""
    ok_rho = R["ok_rho_min"] and R["ok_rho_max"]
    return [
        dict(
            no="Langkah 1", ref="SNI 2847:2019 Pasal 22.2.2.4.3",
            judul="Faktor blok tegangan ekivalen (Beta-1)",
            isi=(
                f"{R['beta1_cara']}\n"
                f"  -->  Beta-1 = {R['beta1']:.4f}"
            ),
            ok=True,
        ),
        dict(
            no="Langkah 2", ref="SNI 2847:2019 Pasal 22.2.1",
            judul="Gaya tarik tulangan (T)",
            isi=(
                f"T = As_net x fy\n"
                f"  = ({As:.0f} - {Asp:.0f}) x {fy:.0f}\n"
                f"  = {R['T']:,.0f} N  =  {R['T']/1000:.1f} kN"
            ),
            ok=True,
        ),
        dict(
            no="Langkah 3", ref="SNI 2847:2019 Pasal 22.2.2.4",
            judul="Kedalaman blok tegangan ekivalen (a)",
            isi=(
                f"a = As_net x fy / (0.85 x fc x b)\n"
                f"  = {R['As_net']:.0f} x {fy:.0f} / (0.85 x {fc} x {b:.0f})\n"
                f"  = {R['a']:.2f} mm"
            ),
            ok=True,
        ),
        dict(
            no="Langkah 4", ref="SNI 2847:2019 Pasal 22.2.2.4.1",
            judul="Kedalaman sumbu netral (c)",
            isi=(
                f"c = a / Beta-1\n"
                f"  = {R['a']:.2f} / {R['beta1']:.4f}\n"
                f"  = {R['c']:.2f} mm"
            ),
            ok=True,
        ),
        dict(
            no="Langkah 5", ref="SNI 2847:2019 Pasal 9.6.1",
            judul="Rasio tulangan aktual (Rho)",
            isi=(
                f"Rho = As / (b x d)\n"
                f"    = {As:.0f} / ({b:.0f} x {d:.0f})\n"
                f"    = {R['rho']:.6f}  =  {R['rho']*100:.4f}%"
            ),
            ok=ok_rho,
        ),
        dict(
            no="Langkah 6", ref="SNI 2847:2019 Pasal 9.6.1.2",
            judul="Rasio tulangan minimum (Rho-min)",
            isi=(
                f"Rho-min = max( 0.25 x sqrt(fc)/fy  ,  1.4/fy )\n"
                f"        = max( {R['rho_mA']:.6f}  ,  {R['rho_mB']:.6f} )\n"
                f"        = {R['rho_min']:.6f}  =  {R['rho_min']*100:.4f}%\n"
                f"Kontrol : Rho = {R['rho']*100:.4f}%  {'>=  Rho-min  [OK]' if R['ok_rho_min'] else '<   Rho-min  [TIDAK OK]'}"
            ),
            ok=R["ok_rho_min"],
        ),
        dict(
            no="Langkah 7", ref="SNI 2847:2019 Pasal 21.2.2",
            judul="Rasio tulangan maksimum (Rho-max)",
            isi=(
                f"Rho-bal = 0.85 x Beta-1 x fc/fy x 600/(600+fy)\n"
                f"        = 0.85 x {R['beta1']:.4f} x {fc}/{fy:.0f} x 600/{600+fy:.0f}\n"
                f"        = {R['rho_bal']:.6f}  =  {R['rho_bal']*100:.4f}%\n"
                f"Rho-max = 0.75 x Rho-bal\n"
                f"        = {R['rho_max']:.6f}  =  {R['rho_max']*100:.4f}%\n"
                f"Kontrol : Rho = {R['rho']*100:.4f}%  {'<=  Rho-max  [OK]' if R['ok_rho_max'] else '>   Rho-max  [TIDAK OK]'}"
            ),
            ok=R["ok_rho_max"],
        ),
        dict(
            no="Langkah 8", ref="SNI 2847:2019 Pasal 21.2.2",
            judul="Regangan tarik tulangan (et)",
            isi=(
                f"et = 0.003 x (d - c) / c\n"
                f"   = 0.003 x ({d:.0f} - {R['c']:.2f}) / {R['c']:.2f}\n"
                f"   = {R['et']:.5f}\n"
                f"{'et >= 0.005  -->  Tension-controlled  [OK]' if R['et'] >= 0.005 else '0.004 <= et < 0.005  -->  Zona transisi  [PERLU TINJAUAN]' if R['et'] >= 0.004 else 'et < 0.004  -->  Tidak memenuhi syarat  [TIDAK OK]'}"
            ),
            ok=R["ok_et"],
        ),
        dict(
            no="Langkah 9", ref="SNI 2847:2019 Tabel 21.2.2",
            judul="Faktor reduksi kekuatan (Phi)",
            isi=(
                f"{R['phi_cara']}\n"
                f"  -->  Phi = {R['phi']:.4f}"
            ),
            ok=R["et"] >= 0.004,
        ),
        dict(
            no="Langkah 10", ref="SNI 2847:2019 Pasal 22.3.2",
            judul="Momen nominal dan momen rencana",
            isi=(
                f"Mn = As_net x fy x (d - a/2)\n"
                f"   = {R['As_net']:.0f} x {fy:.0f} x ({d:.0f} - {R['a']/2:.2f})\n"
                f"   = {R['As_net']*fy*(d-R['a']/2):,.0f} N.mm\n"
                f"   = {R['Mn']:.3f} kN.m\n\n"
                f"Phi.Mn = Phi x Mn\n"
                f"       = {R['phi']:.4f} x {R['Mn']:.3f}\n"
                f"       = {R['phiMn']:.3f} kN.m"
            ),
            ok=True,
        ),
    ]


# ════════════════════════════════════════════════════════════
# GENERATOR WORD (.docx)  —  format natural seperti diketik
# ════════════════════════════════════════════════════════════
def create_word(fc, fy, b, h, d, As, Asp, R, steps, nama_proyek):
    doc = Document()

    # Margin A4
    for sec in doc.sections:
        sec.page_width    = Cm(21)
        sec.page_height   = Cm(29.7)
        sec.left_margin   = Cm(3)
        sec.right_margin  = Cm(2.5)
        sec.top_margin    = Cm(3)
        sec.bottom_margin = Cm(2.5)

    # Helper: tambah paragraf
    def par(teks="", bold=False, size=11, indent=0, space_after=4,
            align=WD_ALIGN_PARAGRAPH.LEFT, color=None, italic=False, mono=False):
        p = doc.add_paragraph()
        p.alignment = align
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(space_after)
        if indent:
            p.paragraph_format.left_indent = Cm(indent)
        if teks:
            r = p.add_run(teks)
            r.bold   = bold
            r.italic = italic
            r.font.size = Pt(size)
            if color:
                r.font.color.rgb = RGBColor(*color)
            if mono:
                r.font.name = "Courier New"
        return p

    def garis():
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after  = Pt(2)
        run = p.add_run("_" * 72)
        run.font.size  = Pt(9)
        run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    def subjudul(teks):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after  = Pt(4)
        r = p.add_run(teks)
        r.bold = True
        r.font.size = Pt(11)
        r.font.color.rgb = RGBColor(0x1A, 0x3C, 0x5E)
        garis()

    # ─── JUDUL ───────────────────────────────────────────────
    par("LAPORAN PERHITUNGAN STRUKTUR", bold=True, size=14,
        align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2, color=(0x1A, 0x3C, 0x5E))
    par("Kapasitas Lentur Balok Beton Bertulang", bold=False, size=12,
        align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    par(f"Referensi  :  SNI 2847:2019 (ACI 318-14)", size=10,
        align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2,
        color=(0x55, 0x55, 0x55), italic=True)
    par(f"Proyek     :  {nama_proyek}", size=10,
        align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2,
        color=(0x55, 0x55, 0x55), italic=True)
    par(f"Tanggal    :  {datetime.datetime.now().strftime('%d %B %Y')}", size=10,
        align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10,
        color=(0x55, 0x55, 0x55), italic=True)
    garis()
    par(space_after=6)

    # ─── 1. DATA INPUT ───────────────────────────────────────
    subjudul("1.  DATA INPUT PENAMPANG")
    data_input = [
        ("Kuat tekan beton",    "fc",      f"{fc:.1f} MPa"),
        ("Kuat leleh tulangan", "fy",      f"{fy:.0f} MPa"),
        ("Lebar balok",         "b",       f"{b:.0f} mm"),
        ("Tinggi total balok",  "h",       f"{h:.0f} mm"),
        ("Tinggi efektif",      "d",       f"{d:.0f} mm"),
        ("Luas tulangan tarik", "As",      f"{As:.0f} mm2"),
        ("Luas tulangan tekan", "As'",     f"{Asp:.0f} mm2"),
    ]
    for nama, simb, nilai in data_input:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(2)
        p.paragraph_format.left_indent  = Cm(0.5)
        r1 = p.add_run(f"{simb:<6}")
        r1.bold = True
        r1.font.size = Pt(10)
        r1.font.name = "Courier New"
        r2 = p.add_run(f"  =  {nilai:<18}  ({nama})")
        r2.font.size = Pt(10)
        r2.font.name = "Courier New"
    par(space_after=6)

    # ─── 2. ANALISA PERHITUNGAN ───────────────────────────────
    subjudul("2.  ANALISA PERHITUNGAN")
    par("Urutan perhitungan mengacu pada SNI 2847:2019.", size=10, italic=True,
        color=(0x55, 0x55, 0x55), space_after=8)

    for s in steps:
        # Judul langkah
        p_hdr = doc.add_paragraph()
        p_hdr.paragraph_format.space_before = Pt(8)
        p_hdr.paragraph_format.space_after  = Pt(1)
        r_no  = p_hdr.add_run(f"{s['no']}  ")
        r_no.bold      = True
        r_no.font.size = Pt(10)
        r_no.font.color.rgb = RGBColor(0x1A, 0x3C, 0x5E)
        r_jdl = p_hdr.add_run(s["judul"])
        r_jdl.bold      = True
        r_jdl.font.size = Pt(10)

        # Referensi pasal
        p_ref = doc.add_paragraph()
        p_ref.paragraph_format.space_before = Pt(0)
        p_ref.paragraph_format.space_after  = Pt(2)
        p_ref.paragraph_format.left_indent  = Cm(0.5)
        r_ref = p_ref.add_run(f"[{s['ref']}]")
        r_ref.italic   = True
        r_ref.font.size = Pt(8.5)
        r_ref.font.color.rgb = RGBColor(0x15, 0x65, 0xC0)

        # Baris-baris perhitungan
        for baris in s["isi"].split("\n"):
            p_b = doc.add_paragraph()
            p_b.paragraph_format.space_before = Pt(0)
            p_b.paragraph_format.space_after  = Pt(1)
            p_b.paragraph_format.left_indent  = Cm(0.5)
            r_b = p_b.add_run(baris if baris.strip() else " ")
            r_b.font.name = "Courier New"
            r_b.font.size = Pt(9.5)
            is_result = baris.strip().startswith("-->") or "[OK]" in baris or "[TIDAK OK]" in baris
            if is_result:
                r_b.bold = True
                r_b.font.color.rgb = (
                    RGBColor(0x1B, 0x5E, 0x20) if s["ok"] else RGBColor(0xB7, 0x1C, 0x1C)
                )

    par(space_after=6)

    # ─── 3. RANGKUMAN ─────────────────────────────────────────
    subjudul("3.  RANGKUMAN HASIL")

    rangkuman = [
        ("Beta-1",    f"{R['beta1']:.4f}",         ""),
        ("a",         f"{R['a']:.2f} mm",           "Kedalaman blok tegangan"),
        ("c",         f"{R['c']:.2f} mm",           "Kedalaman sumbu netral"),
        ("et",        f"{R['et']:.5f}",             "Regangan tarik tulangan"),
        ("Phi",       f"{R['phi']:.4f}",            "Faktor reduksi"),
        ("Rho",       f"{R['rho']*100:.4f}%",       "Rasio tulangan aktual"),
        ("Rho-min",   f"{R['rho_min']*100:.4f}%",   "Batas minimum"),
        ("Rho-max",   f"{R['rho_max']*100:.4f}%",   "Batas maksimum"),
        ("Mn",        f"{R['Mn']:.3f} kN.m",        "Momen nominal"),
        ("Phi.Mn",    f"{R['phiMn']:.3f} kN.m",     "Momen rencana"),
    ]
    for simb, nilai, ket in rangkuman:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(2)
        p.paragraph_format.left_indent  = Cm(0.5)
        r1 = p.add_run(f"{simb:<12}")
        r1.bold = True
        r1.font.size = Pt(10)
        r1.font.name = "Courier New"
        r2 = p.add_run(f"=  {nilai:<22}  {ket}")
        r2.font.size = Pt(10)
        r2.font.name = "Courier New"
    par(space_after=6)

    # ─── 4. KONTROL PENAMPANG ─────────────────────────────────
    subjudul("4.  KONTROL PENAMPANG")

    all_ok = R["ok_rho_min"] and R["ok_rho_max"] and R["ok_et"]

    kontrol = [
        (f"Rho-min = {R['rho_min']*100:.4f}%  <=  Rho = {R['rho']*100:.4f}%", R["ok_rho_min"]),
        (f"Rho-max = {R['rho_max']*100:.4f}%  >=  Rho = {R['rho']*100:.4f}%", R["ok_rho_max"]),
        (f"et      = {R['et']:.5f}  >=  0.004", R["ok_et"]),
    ]
    for teks_k, ok_k in kontrol:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(3)
        p.paragraph_format.left_indent  = Cm(0.5)
        r_k = p.add_run(f"{teks_k}   --> {'[OK]' if ok_k else '[TIDAK OK]'}")
        r_k.font.name = "Courier New"
        r_k.font.size = Pt(10)
        r_k.bold = True
        r_k.font.color.rgb = (
            RGBColor(0x1B, 0x5E, 0x20) if ok_k else RGBColor(0xB7, 0x1C, 0x1C)
        )

    par(space_after=4)

    if all_ok and R["et"] >= 0.005:
        status_teks = "KESIMPULAN : Penampang OK - Tension-controlled, memenuhi seluruh syarat SNI 2847:2019."
        ok_final = True
    elif all_ok:
        status_teks = "KESIMPULAN : Penampang diterima dengan catatan - Zona transisi (perlu tinjauan ulang)."
        ok_final = True
    else:
        masalah = []
        if not R["ok_rho_min"]: masalah.append("rho < rho-min")
        if not R["ok_rho_max"]: masalah.append("rho > rho-max")
        if not R["ok_et"]:      masalah.append("et < 0.004")
        status_teks = "KESIMPULAN : Penampang TIDAK OK - " + " | ".join(masalah)
        ok_final = False

    p_kes = doc.add_paragraph()
    p_kes.paragraph_format.space_before = Pt(6)
    p_kes.paragraph_format.space_after  = Pt(4)
    r_kes = p_kes.add_run(status_teks)
    r_kes.bold      = True
    r_kes.font.size = Pt(10.5)
    r_kes.font.color.rgb = (
        RGBColor(0x1B, 0x5E, 0x20) if ok_final else RGBColor(0xB7, 0x1C, 0x1C)
    )

    # Footer
    garis()
    par(
        "Referensi: SNI 2847:2019 | ACI 318-14  --  "
        "Untuk keperluan profesional, verifikasi mandiri tetap diperlukan.",
        size=8, italic=True, color=(0x99, 0x99, 0x99),
        align=WD_ALIGN_PARAGRAPH.CENTER, space_after=0,
    )

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


# ════════════════════════════════════════════════════════════
# GENERATOR PDF (.pdf)  —  layout formal + watermark
# ════════════════════════════════════════════════════════════
WATERMARK_TEXT = "DIHASILKAN OLEH: LADOSI ENGINEERING"
BRAND_COLOR    = (26, 60, 94)    # #1a3c5e
OK_COLOR       = (27, 94, 32)    # hijau
FAIL_COLOR     = (183, 28, 28)   # merah
GRAY           = (120, 120, 120)


# ════════════════════════════════════════════════════════════
# SANITASI STRING UNTUK PDF (fpdf2 hanya mendukung Latin-1)
# ════════════════════════════════════════════════════════════
_UNICODE_MAP = {
    "\u2014": "-",    # em dash —
    "\u2013": "-",    # en dash –
    "\u2019": "'",    # right single quote
    "\u2018": "'",    # left single quote
    "\u201c": '"',    # left double quote
    "\u201d": '"',    # right double quote
    "\u00b2": "2",    # superscript 2 (mm2)
    "\u00b3": "3",    # superscript 3
    "\u00b0": " deg", # degree
    "\u00d7": "x",    # multiplication x
    "\u2265": ">=",   # >=
    "\u2264": "<=",   # <=
    "\u2260": "!=",   # !=
    "\u221a": "sqrt", # sqrt
    "\u03c6": "Phi",  # phi
    "\u03b2": "Beta", # beta
    "\u03b5": "et",   # epsilon
    "\u03c1": "Rho",  # rho
    "\u03bc": "mu",   # mu
    "\u2022": "-",    # bullet
    "\u2192": "->",   # arrow right
    "\u00b7": ".",    # middle dot
    "\u00e9": "e",    # e acute
    "\u00e8": "e",    # e grave
    "\u00e0": "a",    # a grave
}

def sp(teks: str) -> str:
    """Sanitasi string agar aman untuk fpdf2 (Latin-1 only)."""
    if not isinstance(teks, str):
        teks = str(teks)
    for ch, repl in _UNICODE_MAP.items():
        teks = teks.replace(ch, repl)
    return teks.encode("latin-1", errors="replace").decode("latin-1")


class LaporanPDF(FPDF):
    def __init__(self, nama_proyek):
        super().__init__()
        self.nama_proyek = sp(nama_proyek)  # sanitasi dari awal
        self.set_margins(25, 25, 20)
        self.set_auto_page_break(auto=True, margin=25)

    def header(self):
        # Garis atas
        self.set_draw_color(*BRAND_COLOR)
        self.set_line_width(0.8)
        self.line(25, 15, 190, 15)

        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*BRAND_COLOR)
        self.set_xy(25, 17)
        self.cell(0, 5, "LAPORAN PERHITUNGAN STRUKTUR  |  SNI 2847:2019", ln=False, align="L")
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GRAY)
        self.set_xy(25, 17)
        self.cell(0, 5, f"Proyek: {self.nama_proyek}", ln=False, align="R")
        self.ln(10)

    def footer(self):
        self.set_y(-18)
        self.set_draw_color(*BRAND_COLOR)
        self.set_line_width(0.4)
        self.line(25, self.get_y(), 190, self.get_y())
        self.set_font("Helvetica", "I", 7.5)
        self.set_text_color(*GRAY)
        self.cell(0, 6,
            "Referensi: SNI 2847:2019 | ACI 318-14 - "
            "Untuk keperluan profesional, verifikasi mandiri tetap diperlukan.",
            align="C")
        self.set_xy(25, self.get_y())
        self.set_font("Helvetica", "", 7.5)
        self.cell(0, 6, f"Halaman {self.page_no()}", align="R")

    def watermark(self):
        """Teks watermark diagonal transparan di tengah halaman."""
        self.set_font("Helvetica", "B", 28)
        # Warna abu muda (simulasi transparan)
        self.set_text_color(210, 215, 220)
        # Posisi tengah halaman
        x_center = self.w / 2
        y_center = self.h / 2
        with self.rotation(40, x_center, y_center):
            self.set_xy(x_center - 65, y_center - 6)
            self.cell(130, 12, sp(WATERMARK_TEXT), align="C")
        self.set_text_color(0, 0, 0)   # reset

    def section_title(self, teks):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*BRAND_COLOR)
        self.ln(4)
        self.cell(0, 7, sp(teks), ln=True)
        self.set_draw_color(*BRAND_COLOR)
        self.set_line_width(0.4)
        self.line(self.get_x(), self.get_y(), 190, self.get_y())
        self.ln(3)
        self.set_text_color(0, 0, 0)

    def mono_line(self, teks, bold=False, color=None):
        self.set_font("Courier", "B" if bold else "", 9)
        if color:
            self.set_text_color(*color)
        self.set_x(28)
        self.multi_cell(0, 4.5, sp(teks))
        self.set_text_color(0, 0, 0)


def create_pdf(fc, fy, b, h, d, As, Asp, R, steps, nama_proyek):
    pdf = LaporanPDF(nama_proyek)
    pdf.add_page()
    pdf.watermark()

    # ─── JUDUL ───────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*BRAND_COLOR)
    pdf.ln(2)
    pdf.cell(0, 9, sp("LAPORAN PERHITUNGAN STRUKTUR"), ln=True, align="C")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, sp("Kapasitas Lentur Balok Beton Bertulang"), ln=True, align="C")
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(*GRAY)
    pdf.cell(0, 5, sp(f"Referensi: SNI 2847:2019 (ACI 318-14)"), ln=True, align="C")
    pdf.cell(0, 5, sp(f"Proyek: {nama_proyek}   |   Tanggal: {datetime.datetime.now().strftime('%d %B %Y')}"),
             ln=True, align="C")
    pdf.ln(6)
    pdf.set_draw_color(*BRAND_COLOR)
    pdf.set_line_width(0.6)
    pdf.line(25, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(6)
    pdf.set_text_color(0, 0, 0)

    # ─── 1. DATA INPUT ───────────────────────────────────────
    pdf.section_title("1.  DATA INPUT PENAMPANG")
    pdf.set_font("Courier", "", 9.5)
    data_input = [
        ("fc",    f"{fc:.1f} MPa",   "Kuat tekan beton"),
        ("fy",    f"{fy:.0f} MPa",   "Kuat leleh tulangan"),
        ("b",     f"{b:.0f} mm",     "Lebar balok"),
        ("h",     f"{h:.0f} mm",     "Tinggi total balok"),
        ("d",     f"{d:.0f} mm",     "Tinggi efektif"),
        ("As",    f"{As:.0f} mm2",   "Luas tulangan tarik"),
        ("As'",   f"{Asp:.0f} mm2",  "Luas tulangan tekan"),
    ]
    for simb, nilai, ket in data_input:
        pdf.set_x(28)
        pdf.set_font("Courier", "B", 9.5)
        pdf.cell(18, 5, sp(f"{simb:<6}"), ln=False)
        pdf.set_font("Courier", "", 9.5)
        pdf.cell(35, 5, sp(f"=  {nilai}"), ln=False)
        pdf.set_font("Helvetica", "I", 8.5)
        pdf.set_text_color(*GRAY)
        pdf.cell(0, 5, sp(f"({ket})"), ln=True)
        pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # ─── 2. ANALISA PERHITUNGAN ───────────────────────────────
    pdf.section_title("2.  ANALISA PERHITUNGAN")

    for s in steps:
        # Cek apakah halaman hampir habis
        if pdf.get_y() > 240:
            pdf.add_page()
            pdf.watermark()

        # Header langkah
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*BRAND_COLOR)
        pdf.set_x(25)
        pdf.cell(0, 6, sp(f"{s['no']}  {s['judul']}"), ln=True)

        # Referensi
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*GRAY)
        pdf.set_x(28)
        pdf.cell(0, 4, sp(f"[{s['ref']}]"), ln=True)
        pdf.set_text_color(0, 0, 0)

        # Baris perhitungan
        for baris in s["isi"].split("\n"):
            is_result = (baris.strip().startswith("-->") or
                         "[OK]" in baris or "[TIDAK OK]" in baris)
            if is_result:
                pdf.mono_line(
                    baris,
                    bold=True,
                    color=OK_COLOR if s["ok"] else FAIL_COLOR,
                )
            else:
                pdf.mono_line(baris if baris.strip() else "")
        pdf.ln(2)

    # ─── 3. RANGKUMAN ─────────────────────────────────────────
    if pdf.get_y() > 210:
        pdf.add_page()
        pdf.watermark()

    pdf.section_title("3.  RANGKUMAN HASIL")
    pdf.set_font("Courier", "", 9.5)
    rangkuman = [
        ("Beta-1",  f"{R['beta1']:.4f}",        ""),
        ("a",       f"{R['a']:.2f} mm",          "Kedalaman blok tegangan"),
        ("c",       f"{R['c']:.2f} mm",          "Kedalaman sumbu netral"),
        ("et",      f"{R['et']:.5f}",            "Regangan tarik"),
        ("Phi",     f"{R['phi']:.4f}",           "Faktor reduksi"),
        ("Rho",     f"{R['rho']*100:.4f}%",      "Rasio tulangan aktual"),
        ("Rho-min", f"{R['rho_min']*100:.4f}%",  "Batas minimum"),
        ("Rho-max", f"{R['rho_max']*100:.4f}%",  "Batas maksimum"),
        ("Mn",      f"{R['Mn']:.3f} kN.m",       "Momen nominal"),
        ("Phi.Mn",  f"{R['phiMn']:.3f} kN.m",    "Momen rencana"),
    ]
    for simb, nilai, ket in rangkuman:
        pdf.set_x(28)
        pdf.set_font("Courier", "B", 9.5)
        pdf.cell(22, 5, sp(f"{simb:<10}"), ln=False)
        pdf.set_font("Courier", "", 9.5)
        pdf.cell(38, 5, sp(f"=  {nilai}"), ln=False)
        if ket:
            pdf.set_font("Helvetica", "I", 8.5)
            pdf.set_text_color(*GRAY)
            pdf.cell(0, 5, sp(f"({ket})"), ln=True)
            pdf.set_text_color(0, 0, 0)
        else:
            pdf.ln()
    pdf.ln(4)

    # ─── 4. KONTROL ───────────────────────────────────────────
    pdf.section_title("4.  KONTROL PENAMPANG")

    kontrol = [
        (f"Rho-min = {R['rho_min']*100:.4f}%  <=  Rho = {R['rho']*100:.4f}%",
         R["ok_rho_min"]),
        (f"Rho-max = {R['rho_max']*100:.4f}%  >=  Rho = {R['rho']*100:.4f}%",
         R["ok_rho_max"]),
        (f"et      = {R['et']:.5f}  >=  0.004",
         R["ok_et"]),
    ]
    for teks_k, ok_k in kontrol:
        tanda = "[OK]" if ok_k else "[TIDAK OK]"
        pdf.set_x(28)
        pdf.set_font("Courier", "B", 9.5)
        pdf.set_text_color(*(OK_COLOR if ok_k else FAIL_COLOR))
        pdf.cell(0, 5.5, sp(f"{teks_k}   --> {tanda}"), ln=True)
        pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    all_ok = R["ok_rho_min"] and R["ok_rho_max"] and R["ok_et"]
    if all_ok and R["et"] >= 0.005:
        kes = "KESIMPULAN : Penampang OK - Tension-controlled, memenuhi seluruh syarat SNI 2847:2019."
        ok_final = True
    elif all_ok:
        kes = "KESIMPULAN : Penampang diterima - Zona transisi (perlu tinjauan ulang)."
        ok_final = True
    else:
        masalah = []
        if not R["ok_rho_min"]: masalah.append("rho < rho-min")
        if not R["ok_rho_max"]: masalah.append("rho > rho-max")
        if not R["ok_et"]:      masalah.append("et < 0.004")
        kes = "KESIMPULAN : Penampang TIDAK OK - " + " | ".join(masalah)
        ok_final = False

    pdf.set_x(25)
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.set_text_color(*(OK_COLOR if ok_final else FAIL_COLOR))
    pdf.multi_cell(0, 6, sp(kes))
    pdf.set_text_color(0, 0, 0)

    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return buf


# ════════════════════════════════════════════════════════════
# UI — HEADER
# ════════════════════════════════════════════════════════════
st.markdown('<p class="main-title">🏗️ Kapasitas Lentur Balok Beton Bertulang</p>',
            unsafe_allow_html=True)
st.markdown(
    '<p class="sub-title">Referensi: SNI 2847:2019 (setara ACI 318-14) '
    '| Urutan perhitungan sesuai urutan pasal</p>',
    unsafe_allow_html=True)
st.markdown('<hr class="divider">', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# UI — LAYOUT DUA KOLOM
# ════════════════════════════════════════════════════════════
col_inp, col_out = st.columns([1, 2], gap="large")

with col_inp:
    st.markdown("### 📋 Data Input")

    nama_proyek = st.text_input(
        "Nama Proyek (untuk header laporan)",
        value="Laporan Analisa Struktur",
        help="Nama proyek akan muncul di header Word dan PDF.",
    )

    st.markdown("**Material**")
    fc = st.number_input("f'c — Kuat tekan beton (MPa)",
                         min_value=17.0, max_value=100.0, value=30.0, step=1.0, format="%.1f")
    fy = st.number_input("fy — Kuat leleh tulangan (MPa)",
                         min_value=240.0, max_value=600.0, value=400.0, step=10.0, format="%.0f")

    st.markdown("**Geometri**")
    cb, ch = st.columns(2)
    with cb:
        b = st.number_input("b (mm)", min_value=100.0, max_value=2000.0,
                            value=300.0, step=10.0, format="%.0f")
    with ch:
        h = st.number_input("h (mm)", min_value=100.0, max_value=5000.0,
                            value=500.0, step=10.0, format="%.0f")
    d = st.number_input("d (mm) — Tinggi efektif (h − selimut − ½D)",
                        min_value=50.0, max_value=4900.0, value=440.0, step=5.0, format="%.0f")

    st.markdown("**Tulangan**")
    As  = st.number_input("As (mm²) — Tulangan tarik",
                          min_value=0.0, value=1520.0, step=10.0, format="%.0f",
                          help="Contoh: 4D22 = 4 × 380.1 = 1520 mm²")
    Asp = st.number_input("As' (mm²) — Tulangan tekan",
                          min_value=0.0, value=0.0, step=10.0, format="%.0f",
                          help="Isi 0 jika tidak ada")

    st.markdown("")
    tombol = st.button("⚡ HITUNG KAPASITAS LENTUR",
                       use_container_width=True, type="primary")

    with st.expander("📌 Tabel luas tulangan (mm²)"):
        st.markdown("""
        | Ø | 1 | 2 | 3 | 4 | 5 | 6 |
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

# ════════════════════════════════════════════════════════════
# UI — HASIL + TOMBOL DOWNLOAD
# ════════════════════════════════════════════════════════════
with col_out:
    if tombol:
        if d >= h:
            st.error("⚠️ Tinggi efektif d harus lebih kecil dari tinggi total h!")
            st.stop()
        if As <= 0:
            st.error("⚠️ Luas tulangan tarik As harus lebih besar dari 0!")
            st.stop()

        R     = hitung(fc, fy, b, h, d, As, Asp)
        steps = buat_steps(fc, fy, b, h, d, As, Asp, R)

        # ── Metrik Utama ────────────────────────────────────
        st.markdown("### 📊 Hasil Utama")
        m1, m2, m3, m4 = st.columns(4)
        for col, lbl, val, unt in [
            (m1, "Momen Nominal Mn",    f"{R['Mn']:.2f}",    "kN·m"),
            (m2, "φMn (Momen Rencana)", f"{R['phiMn']:.2f}", "kN·m"),
            (m3, "Faktor Reduksi φ",    f"{R['phi']:.3f}",   "—"),
            (m4, "Regangan εt",         f"{R['et']:.4f}",    "—"),
        ]:
            with col:
                st.markdown(
                    f'<div class="metric-card">'
                    f'<div class="metric-lbl">{lbl}</div>'
                    f'<div class="metric-val">{val}</div>'
                    f'<div class="metric-unt">{unt}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        st.markdown("")

        # ── Status ──────────────────────────────────────────
        all_ok = R["ok_rho_min"] and R["ok_rho_max"] and R["ok_et"]
        if all_ok and R["et"] >= 0.005:
            st.markdown(
                '<div class="result-ok">✅ PENAMPANG OK — '
                'Tension-controlled, memenuhi seluruh syarat SNI 2847:2019</div>',
                unsafe_allow_html=True)
        elif all_ok:
            st.markdown(
                '<div class="result-warn">⚠️ PERLU TINJAUAN — '
                'Zona transisi (0.004 ≤ εt &lt; 0.005)</div>',
                unsafe_allow_html=True)
        else:
            masalah = []
            if not R["ok_rho_min"]: masalah.append("ρ &lt; ρ_min → tambah tulangan")
            if not R["ok_rho_max"]: masalah.append("ρ > ρ_max → kurangi tulangan")
            if not R["ok_et"]:      masalah.append("εt &lt; 0.004 → tidak memenuhi syarat")
            st.markdown(
                f'<div class="result-fail">❌ TIDAK OK — {" | ".join(masalah)}</div>',
                unsafe_allow_html=True)

        st.markdown('<hr class="divider">', unsafe_allow_html=True)

        # ── Langkah Perhitungan ──────────────────────────────
        st.markdown("### 📐 Urutan Perhitungan")
        for s in steps:
            warna = "#2e7d32" if s["ok"] else "#c62828"
            tanda = "✓" if s["ok"] else "✗"
            st.markdown(
                f'<div class="step-box" style="border-left-color:{warna}">'
                f'<div class="ref-badge">{s["ref"]}</div><br>'
                f'<div class="step-hdr">{s["no"]} — {s["judul"]} &nbsp; {tanda}</div>'
                f'<pre style="margin:0;font-size:.82rem;white-space:pre-wrap;'
                f'font-family:monospace">{s["isi"]}</pre></div>',
                unsafe_allow_html=True,
            )

        # ── Tabel Rangkuman ──────────────────────────────────
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        st.markdown("### 📋 Tabel Rangkuman")
        et_s = ("✅ OK" if R["et"] >= 0.005
                else "⚠️ Transisi" if R["et"] >= 0.004
                else "❌ Tidak OK")
        rh_s = "✅ OK" if (R["ok_rho_min"] and R["ok_rho_max"]) else "❌ Tidak OK"
        df = pd.DataFrame({
            "Parameter": ["β₁","a (mm)","c (mm)","εt","φ",
                          "ρ (%)","ρ_min (%)","ρ_max (%)","Mn (kN·m)","φMn (kN·m)"],
            "Nilai": [
                f"{R['beta1']:.4f}", f"{R['a']:.2f}", f"{R['c']:.2f}",
                f"{R['et']:.5f}", f"{R['phi']:.4f}", f"{R['rho']*100:.4f}",
                f"{R['rho_min']*100:.4f}", f"{R['rho_max']*100:.4f}",
                f"{R['Mn']:.3f}", f"{R['phiMn']:.3f}",
            ],
            "Status": ["—","—","—", et_s,"—", rh_s,"—","—","—","—"],
        })
        st.dataframe(df, use_container_width=True, hide_index=True)

        # ════════════════════════════════════════════════════
        # TOMBOL DOWNLOAD — WORD & PDF BERDAMPINGAN
        # ════════════════════════════════════════════════════
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        st.markdown("### 📄 Download Laporan")

        nama_file_base = (
            f"Laporan_Lentur_Balok_fc{int(fc)}_fy{int(fy)}_b{int(b)}x{int(h)}"
        )

        word_buf = create_word(fc, fy, b, h, d, As, Asp, R, steps, nama_proyek)
        pdf_buf  = create_pdf(fc, fy, b, h, d, As, Asp, R, steps, nama_proyek)

        dl_word, dl_pdf = st.columns(2)
        with dl_word:
            st.download_button(
                label="⬇️  Download Laporan Word (.docx)",
                data=word_buf,
                file_name=f"{nama_file_base}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                help="Format natural, siap diedit di Microsoft Word.",
            )
        with dl_pdf:
            st.download_button(
                label="⬇️  Download Laporan PDF (.pdf)",
                data=pdf_buf,
                file_name=f"{nama_file_base}.pdf",
                mime="application/pdf",
                use_container_width=True,
                help="Layout formal dengan watermark. Siap cetak atau kirim ke klien.",
            )
        st.caption(
            "File Word dapat diedit lebih lanjut.  "
            "File PDF sudah dilengkapi watermark dan siap untuk laporan resmi."
        )

    else:
        st.info("👈  Isi data di panel kiri, lalu klik **HITUNG KAPASITAS LENTUR**")
        st.markdown("""
        **Yang akan dihitung secara runtut:**
        1. Faktor β₁ (blok tegangan Whitney)
        2. Gaya tarik tulangan T
        3. Kedalaman blok tegangan **a**
        4. Kedalaman sumbu netral **c**
        5. Rasio tulangan aktual ρ
        6. Batas ρ_min (SNI Pasal 9.6.1.2)
        7. Batas ρ_max (0.75 ρ_bal)
        8. Regangan tarik εt
        9. Faktor reduksi φ
        10. Momen nominal **Mn** dan momen rencana **φMn**

        **Output tersedia dalam dua format:**
        - 📝 Word (.docx) — format natural, bisa diedit
        - 📋 PDF (.pdf)  — formal + watermark LADOSI ENGINEERING
        """)

# ── Footer ────────────────────────────────────────────────
st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;font-size:.75rem;color:#aaa'>"
    "Referensi: SNI 2847:2019 | ACI 318-14 | "
    "Untuk keperluan profesional - verifikasi mandiri tetap diperlukan"
    "</p>",
    unsafe_allow_html=True,
)
