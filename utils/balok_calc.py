"""
=============================================================
utils/balok_calc.py
Fungsi kalkulasi murni untuk evaluasi balok beton bertulang.
Referensi : SNI 2847:2019 (ACI 318-14)

TIDAK mengandung: streamlit, docx, fpdf
Dipanggil oleh  : pages/1_Lentur_Balok.py
                  utils/balok_report.py
=============================================================
"""

import math
import io
import matplotlib.pyplot as plt
import matplotlib.patches as patches


# ============================================================
# KONSTANTA & HELPER PDF SANITASI
# ============================================================
DIAMETER_LIST = [10, 13, 16, 19, 22, 25, 29, 32]

_UNICODE_MAP = {
    "\u2014": "-",    "\u2013": "-",    "\u2019": "'",   "\u2018": "'",
    "\u201c": '"',    "\u201d": '"',    "\u00b2": "2",   "\u00b3": "3",
    "\u00b0": " deg", "\u00d7": "x",   "\u2265": ">=",  "\u2264": "<=",
    "\u2260": "!=",   "\u221a": "sqrt", "\u03c6": "Phi", "\u03b2": "Beta",
    "\u03b5": "et",   "\u03c1": "Rho",  "\u03bc": "mu",  "\u2022": "-",
    "\u2192": "->",   "\u00b7": ".",    "\u00e9": "e",   "\u00e8": "e",
    "\u00e0": "a",    "\u2550": "=",    "\u2500": "-",
    "\u03bb": "lambda",
}

def sp(teks: str) -> str:
    """Sanitasi string agar aman untuk fpdf2 (Latin-1 only)."""
    if not isinstance(teks, str):
        teks = str(teks)
    for ch, repl in _UNICODE_MAP.items():
        teks = teks.replace(ch, repl)
    return teks.encode("latin-1", errors="replace").decode("latin-1")


# ============================================================
# FUNGSI HITUNG GEOMETRI TULANGAN
# ============================================================
def luas_batang(d_mm: float) -> float:
    """Luas penampang satu batang tulangan (mm2)."""
    return math.pi * d_mm ** 2 / 4.0


def hitung_lapis_tarik(h, cc, ds, n1, db1, n2, db2, spasi=25.0):
    lapis = []
    if n1 > 0 and db1 > 0:
        y1 = h - cc - ds - db1 / 2.0
        As1 = n1 * luas_batang(db1)
        lapis.append(dict(no=1, n=n1, db=db1, As=As1, y=y1))
    if n2 > 0 and db2 > 0:
        if n1 > 0 and db1 > 0:
            y_top_lapis1 = h - cc - ds - db1
            y2 = y_top_lapis1 - spasi - db2 / 2.0
        else:
            y2 = h - cc - ds - db2 / 2.0
        As2 = n2 * luas_batang(db2)
        lapis.append(dict(no=2, n=n2, db=db2, As=As2, y=y2))
    if not lapis:
        return [], 0.0, 0.0
    As_total = sum(L["As"] for L in lapis)
    d_total  = sum(L["As"] * L["y"] for L in lapis) / As_total
    return lapis, d_total, As_total


def hitung_lapis_tekan(cc, ds, n1, db1, n2, db2, spasi=25.0):
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
    Es     = 200_000.0
    eps_cu = 0.003
    eps_y  = fy / Es
    a      = beta1 * c
    Cc     = 0.85 * fc * a * b

    Cs_total   = 0.0
    info_tekan = []
    for L in lapis_tekan:
        eps_s = eps_cu * (c - L["y"]) / c
        if eps_s >= eps_y:    fs = fy
        elif eps_s <= -eps_y: fs = -fy
        else:                 fs = eps_s * Es
        fs_eff = fs - 0.85 * fc if L["y"] <= a else fs
        F = L["As"] * fs_eff
        Cs_total += F
        info_tekan.append(dict(no=L["no"], y=L["y"], As=L["As"], eps=eps_s, fs=fs, F=F))

    T_total   = 0.0
    info_tarik = []
    for L in lapis_tarik:
        eps_s = eps_cu * (L["y"] - c) / c
        if eps_s >= eps_y:    fs = fy
        elif eps_s <= -eps_y: fs = -fy
        else:                 fs = eps_s * Es
        F = L["As"] * fs
        T_total += F
        info_tarik.append(dict(no=L["no"], y=L["y"], As=L["As"], eps=eps_s, fs=fs, F=F))

    residu = Cc + Cs_total - T_total
    return dict(a=a, c=c, Cc=Cc, Cs=Cs_total, T=T_total,
                info_tekan=info_tekan, info_tarik=info_tarik,
                residu=residu, eps_y=eps_y)


def cari_c_keseimbangan(fc, fy, b, beta1, lapis_tarik, lapis_tekan, h):
    """Iterasi bisection untuk c sehingga residu (Cc+Cs-T) = 0."""
    lo, hi = 0.001, h * 1.5
    for _ in range(200):
        mid   = (lo + hi) / 2.0
        r     = gaya_dalam(mid, fc, fy, b, beta1, lapis_tarik, lapis_tekan)["residu"]
        r_lo  = gaya_dalam(lo,  fc, fy, b, beta1, lapis_tarik, lapis_tekan)["residu"]
        if abs(r) < 1e-3:
            return mid
        if r_lo * r < 0: hi = mid
        else:             lo = mid
    return (lo + hi) / 2.0


def evaluasi_balok(fc, fy, b, h, cc_sel, ds, lapis_tarik, lapis_tekan,
                   d_tarik, As_tarik, d_tekan, As_tekan, Mu):
    """Evaluasi penuh penampang LENTUR dengan strain compatibility."""
    R = {}
    beta1, beta1_cara = hitung_beta1(fc)
    R["beta1"]      = beta1
    R["beta1_cara"] = beta1_cara

    c = cari_c_keseimbangan(fc, fy, b, beta1, lapis_tarik, lapis_tekan, h)
    G = gaya_dalam(c, fc, fy, b, beta1, lapis_tarik, lapis_tekan)

    a = G["a"]; Cc = G["Cc"]; Cs = G["Cs"]; T = G["T"]
    info_tk = G["info_tekan"]; info_tr = G["info_tarik"]; eps_y = G["eps_y"]

    Mn_Nmm = Cc * (d_tarik - a / 2)
    for L in info_tk:
        Mn_Nmm += L["F"] * (d_tarik - L["y"])
    Mn = Mn_Nmm / 1_000_000.0

    et = max((L["eps"] for L in info_tr), default=0.0)

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

    rho     = As_tarik / (b * d_tarik)
    rho_mA  = 0.25 * math.sqrt(fc) / fy
    rho_mB  = 1.4 / fy
    rho_min = max(rho_mA, rho_mB)
    rho_bal = (0.85 * beta1 * fc / fy) * (600 / (600 + fy))
    rho_max = 0.75 * rho_bal

    R.update(dict(
        c=c, a=a, Cc=Cc, Cs=Cs, T=T,
        info_tarik=info_tr, info_tekan=info_tk,
        eps_y=eps_y, et=et, phi=phi, phi_cara=phi_cara,
        Mn=Mn, phiMn=phiMn, Mu=Mu, DC=DC,
        rho=rho, rho_mA=rho_mA, rho_mB=rho_mB,
        rho_min=rho_min, rho_bal=rho_bal, rho_max=rho_max,
        ok_rho_min=(rho >= rho_min), ok_rho_max=(rho <= rho_max),
        ok_et=(et >= 0.004), ok_dc=(DC <= 1.0),
        d_tarik=d_tarik, d_tekan=d_tekan,
        As_tarik=As_tarik, As_tekan=As_tekan,
    ))
    return R


# ============================================================
# FUNGSI EVALUASI GESER (SNI 2847:2019)
# ============================================================
def hitung_geser(fc, fyt, b, d_aktual, Vu, ds, s_seng, n_kaki, lambda_=1.0):
    G = {}
    Phi_v     = 0.75
    Vc_N      = 0.17 * lambda_ * math.sqrt(fc) * b * d_aktual
    Vc        = Vc_N / 1000.0
    half_phiVc = 0.5 * Phi_v * Vc
    phiVc     = Phi_v * Vc

    if Vu <= half_phiVc:
        klas_seng = "tidak_perlu"
        ket_klas  = (f"Vu = {Vu:.2f} kN <= 0.5 Phi.Vc = {half_phiVc:.2f} kN  "
                     f"-->  secara teori tidak perlu sengkang, tetap pasang sengkang minimum.")
    elif Vu <= phiVc:
        klas_seng = "minimum"
        ket_klas  = (f"0.5 Phi.Vc = {half_phiVc:.2f} kN < Vu = {Vu:.2f} kN <= "
                     f"Phi.Vc = {phiVc:.2f} kN  -->  pasang sengkang minimum.")
    else:
        klas_seng = "perlu_hitung"
        ket_klas  = (f"Vu = {Vu:.2f} kN > Phi.Vc = {phiVc:.2f} kN  "
                     f"-->  perlu menghitung tulangan geser (Vs).")

    Vs_perlu      = max(0.0, Vu / Phi_v - Vc)
    Vs_max        = 0.66 * math.sqrt(fc) * b * d_aktual / 1000.0
    ok_Vs_max     = (Vs_perlu <= Vs_max)
    Av_pasang     = n_kaki * (math.pi / 4.0) * ds ** 2
    Vs_batas_spasi = 0.33 * math.sqrt(fc) * b * d_aktual / 1000.0

    if Vs_perlu <= Vs_batas_spasi:
        s_max = min(d_aktual / 2.0, 600.0)
        rumus_smax = (f"Vs_perlu = {Vs_perlu:.2f} kN <= 0.33 sqrt(fc) b d / 1000 "
                      f"= {Vs_batas_spasi:.2f} kN\n"
                      f"  -->  s_max = min(d/2 , 600 mm) = "
                      f"min({d_aktual/2.0:.1f} , 600) = {s_max:.1f} mm")
    else:
        s_max = min(d_aktual / 4.0, 300.0)
        rumus_smax = (f"Vs_perlu = {Vs_perlu:.2f} kN > 0.33 sqrt(fc) b d / 1000 "
                      f"= {Vs_batas_spasi:.2f} kN\n"
                      f"  -->  s_max = min(d/4 , 300 mm) = "
                      f"min({d_aktual/4.0:.1f} , 300) = {s_max:.1f} mm")
    ok_spasi = (s_seng <= s_max)

    AvS_minA = 0.062 * math.sqrt(fc) * b / fyt
    AvS_minB = 0.35 * b / fyt
    AvS_min  = max(AvS_minA, AvS_minB)
    Av_min   = AvS_min * s_seng
    ok_Av    = (Av_pasang >= Av_min)

    Vs_aktual     = (Av_pasang * fyt * d_aktual / s_seng) / 1000.0
    Vs_efektif    = min(Vs_aktual, Vs_max)
    Vn_efektif    = Vc + Vs_efektif
    PhiVn_efektif = Phi_v * Vn_efektif
    DC_geser      = Vu / PhiVn_efektif if PhiVn_efektif > 0 else float("inf")
    ok_dc         = (DC_geser <= 1.0)
    ok_total      = ok_dc and ok_Vs_max and ok_Av and ok_spasi

    G.update(dict(
        Phi_v=Phi_v, lambda_=lambda_,
        Vc_N=Vc_N, Vc=Vc, half_phiVc=half_phiVc, phiVc=phiVc,
        klas_seng=klas_seng, ket_klas=ket_klas,
        Vs_perlu=Vs_perlu, Vs_max=Vs_max, ok_Vs_max=ok_Vs_max,
        Av_pasang=Av_pasang,
        AvS_minA=AvS_minA, AvS_minB=AvS_minB, AvS_min=AvS_min,
        Av_min=Av_min, ok_Av=ok_Av,
        s_max=s_max, rumus_smax=rumus_smax, ok_spasi=ok_spasi,
        Vs_aktual=Vs_aktual, Vs_efektif=Vs_efektif,
        Vn_efektif=Vn_efektif, PhiVn_efektif=PhiVn_efektif,
        DC_geser=DC_geser, ok_dc=ok_dc, ok_total=ok_total, Vu=Vu,
    ))
    return G


# ============================================================
# FUNGSI EVALUASI TORSI (SNI 2847:2019 Pasal 22.7)
# ============================================================
def hitung_torsi(fc, fy_long, fyt, b, h, cc_sel, ds, s_seng,
                 Tu, Vu, Vc, d_aktual, Av_pasang_geser,
                 tipe_torsi, db_long_torsi, lambda_=1.0):
    T_res = {}
    Phi_t = 0.75

    Acp = b * h
    pcp = 2.0 * (b + h)
    x1  = b - 2.0 * cc_sel - ds
    y1  = h - 2.0 * cc_sel - ds
    Aoh = x1 * y1
    ph  = 2.0 * (x1 + y1)
    Ao  = 0.85 * Aoh

    Tth_Nmm = 0.083 * lambda_ * math.sqrt(fc) * (Acp ** 2 / pcp)
    Tth     = Tth_Nmm / 1_000_000.0
    phi_Tth = Phi_t * Tth
    Tu_Nmm  = Tu * 1_000_000.0
    abaikan_torsi = (Tu <= phi_Tth)

    Tcr_Nmm = 0.33 * lambda_ * math.sqrt(fc) * (Acp ** 2 / pcp)
    Tcr     = Tcr_Nmm / 1_000_000.0
    phi_Tcr = Phi_t * Tcr

    if tipe_torsi == "Compatibility" and Tu > phi_Tcr:
        Tu_desain     = phi_Tcr
        Tu_desain_Nmm = phi_Tcr * 1_000_000.0
        catatan_tu    = (f"Torsi Kompatibilitas: Tu ({Tu:.3f} kN.m) > Phi_t x Tcr "
                         f"({phi_Tcr:.3f} kN.m)\n"
                         f"  -->  Tu_desain direduksi = Phi_t x Tcr = {Tu_desain:.3f} kN.m")
    else:
        Tu_desain     = Tu
        Tu_desain_Nmm = Tu_Nmm
        if tipe_torsi == "Equilibrium":
            catatan_tu = (f"Torsi Keseimbangan: tidak boleh redistribusi\n"
                          f"  -->  Tu_desain = Tu = {Tu_desain:.3f} kN.m")
        else:
            catatan_tu = (f"Torsi Kompatibilitas: Tu ({Tu:.3f} kN.m) <= Phi_t x Tcr "
                          f"({phi_Tcr:.3f} kN.m)\n"
                          f"  -->  Tu_desain = Tu = {Tu_desain:.3f} kN.m (tidak direduksi)")

    Vu_N     = Vu * 1000.0
    Vc_N_val = Vc * 1000.0
    Phi_v    = 0.75

    term_geser = Vu_N / (b * d_aktual)
    term_torsi = Tu_desain_Nmm * ph / (1.7 * Aoh ** 2)
    lhs_dim    = math.sqrt(term_geser ** 2 + term_torsi ** 2)
    rhs_dim    = Phi_v * (Vc_N_val / (b * d_aktual) + 0.66 * math.sqrt(fc))
    ok_dimensi = (lhs_dim <= rhs_dim)
    DC_dim     = lhs_dim / rhs_dim if rhs_dim > 0 else float("inf")

    cot_theta = 1.0
    At_per_s  = Tu_desain_Nmm / (Phi_t * 2.0 * Ao * fyt * cot_theta)

    Av_per_s_pasang      = Av_pasang_geser / s_seng
    Avt_per_s_perlu      = Av_per_s_pasang + 2.0 * At_per_s
    Avt_per_s_ada        = Av_pasang_geser / s_seng
    Avt_pasang           = Av_pasang_geser
    Avt_perlu_abs        = Avt_per_s_perlu * s_seng
    s_perlu_gabungan     = (Av_pasang_geser / Avt_per_s_perlu
                            if Avt_per_s_perlu > 0 else s_seng)
    ok_sengkang_gabungan = (Av_pasang_geser >= Avt_perlu_abs)

    AvtS_minA  = 0.062 * math.sqrt(fc) * b / fyt
    AvtS_minB  = 0.35 * b / fyt
    AvtS_min   = max(AvtS_minA, AvtS_minB)
    Avt_min    = AvtS_min * s_seng
    ok_Avt_min = (Av_pasang_geser >= Avt_min)

    s_max_torsi    = min(ph / 8.0, 300.0)
    ok_spasi_torsi = (s_seng <= s_max_torsi)

    Al        = At_per_s * ph * (fyt / fy_long) * (cot_theta ** 2)
    Al_minA   = (0.42 * math.sqrt(fc) * Acp / fy_long
                 - At_per_s * ph * (fyt / fy_long))
    Al_minB   = (0.42 * math.sqrt(fc) * Acp / fy_long
                 - (0.175 * b / fyt) * ph * (fyt / fy_long))
    Al_min    = max(Al_minA, Al_minB, 0.0)
    Al_pakai  = max(Al, Al_min)
    Ab_long   = luas_batang(db_long_torsi)
    n_batang  = math.ceil(Al_pakai / Ab_long) if Ab_long > 0 else 0

    At_per_s_cap = Av_pasang_geser / s_seng
    Tn_cap       = 2.0 * Ao * At_per_s_cap * fyt * cot_theta / 1_000_000.0
    PhiTn_cap    = Phi_t * Tn_cap
    DC_torsi     = Tu_desain / PhiTn_cap if PhiTn_cap > 0 else float("inf")
    ok_DC_torsi  = (DC_torsi <= 1.0)

    ok_torsi_total = (ok_dimensi and ok_sengkang_gabungan and ok_Avt_min
                      and ok_spasi_torsi and ok_DC_torsi)

    T_res.update(dict(
        Phi_t=Phi_t, lambda_=lambda_,
        Acp=Acp, pcp=pcp, x1=x1, y1=y1, Aoh=Aoh, ph=ph, Ao=Ao,
        Tth=Tth, phi_Tth=phi_Tth, Tth_Nmm=Tth_Nmm,
        Tcr=Tcr, phi_Tcr=phi_Tcr,
        abaikan_torsi=abaikan_torsi,
        Tu=Tu, Tu_desain=Tu_desain, Tu_desain_Nmm=Tu_desain_Nmm,
        tipe_torsi=tipe_torsi, catatan_tu=catatan_tu,
        term_geser=term_geser, term_torsi=term_torsi,
        lhs_dim=lhs_dim, rhs_dim=rhs_dim,
        ok_dimensi=ok_dimensi, DC_dim=DC_dim,
        cot_theta=cot_theta, At_per_s=At_per_s,
        Av_per_s_pasang=Av_per_s_pasang,
        Avt_per_s_perlu=Avt_per_s_perlu,
        Avt_perlu_abs=Avt_perlu_abs,
        Avt_pasang=Avt_pasang,
        s_perlu_gabungan=s_perlu_gabungan,
        ok_sengkang_gabungan=ok_sengkang_gabungan,
        AvtS_minA=AvtS_minA, AvtS_minB=AvtS_minB,
        AvtS_min=AvtS_min, Avt_min=Avt_min, ok_Avt_min=ok_Avt_min,
        s_max_torsi=s_max_torsi, ok_spasi_torsi=ok_spasi_torsi,
        Al=Al, Al_minA=Al_minA, Al_minB=Al_minB,
        Al_min=Al_min, Al_pakai=Al_pakai,
        db_long_torsi=db_long_torsi, Ab_long=Ab_long, n_batang=n_batang,
        At_per_s_cap=At_per_s_cap, Tn_cap=Tn_cap,
        PhiTn_cap=PhiTn_cap, DC_torsi=DC_torsi,
        ok_DC_torsi=ok_DC_torsi, ok_torsi_total=ok_torsi_total,
        Vu=Vu, Vc=Vc, d_aktual=d_aktual,
        fy_long=fy_long, fyt=fyt,
    ))
    return T_res


# ============================================================
# BUAT STEP-STEP LAPORAN LENTUR (b1 - b10)
# ============================================================
def buat_steps_balok(fc, fy, b, h, cc_sel, ds, lapis_tarik, lapis_tekan, R):
    eps_y  = R["eps_y"]
    ok_rho = R["ok_rho_min"] and R["ok_rho_max"]
    Mu     = R["Mu"]

    s1 = dict(no="b1.", ref="SNI 2847:2019 Pasal 22.2.2.4.3",
              judul="Faktor Beta-1",
              isi=f"{R['beta1_cara']}\n  -->  Beta-1 = {R['beta1']:.4f}",
              ok=True)

    teks_lapis = ""
    for L in lapis_tarik:
        teks_lapis += (f"  Tarik Lapis-{L['no']}: {L['n']} D{int(L['db'])}  "
                       f"As = {L['As']:.1f} mm2   y (dari atas) = {L['y']:.2f} mm\n")
    for L in lapis_tekan:
        teks_lapis += (f"  Tekan Lapis-{L['no']}: {L['n']} D{int(L['db'])}  "
                       f"As' = {L['As']:.1f} mm2   y (dari atas) = {L['y']:.2f} mm\n")

    s2 = dict(no="b2.", ref="SNI 2847:2019 Pasal 26.6.2 & geom. penampang",
              judul="Posisi tiap lapis tulangan (dari serat tekan atas)",
              isi=(f"Penentuan posisi y = h - cc - ds - db/2 (tarik bawah)\n"
                   f"                 y = cc + ds + db/2 (tekan atas)\n\n"
                   f"{teks_lapis.rstrip()}\n\n"
                   f"d-aktual  (tarik) = {R['d_tarik']:.2f} mm  (titik berat As-tarik)\n"
                   f"d'-aktual (tekan) = {R['d_tekan']:.2f} mm  (titik berat As-tekan)"),
              ok=True)

    s3 = dict(no="b3.", ref="SNI 2847:2019 Pasal 22.2.1.1 - eps_cu = 0.003",
              judul="Iterasi sumbu netral c (bisection, 200 iterasi)",
              isi=(f"Cari c sehingga Cc + Cs - T = 0\n"
                   f"  a     = Beta-1 x c = {R['beta1']:.4f} x {R['c']:.2f} = {R['a']:.2f} mm\n"
                   f"  Cc    = 0.85 x fc x a x b = 0.85 x {fc} x {R['a']:.2f} x {b} "
                   f"= {R['Cc']:,.0f} N\n"
                   f"  c     = {R['c']:.4f} mm  -->  [OK]"),
              ok=True)

    teks_eps = ""
    for L in R["info_tekan"]:
        status = "leleh" if abs(L["eps"]) >= eps_y else "elastis"
        teks_eps += (f"  Tekan Lapis-{L['no']}  (y={L['y']:.1f} mm):\n"
                     f"    eps-s' = 0.003 x (c - y) / c = "
                     f"0.003 x ({R['c']:.2f} - {L['y']:.1f}) / {R['c']:.2f} "
                     f"= {L['eps']:+.5f}  ({status})\n"
                     f"    fs'    = {L['fs']:+.2f} MPa\n")
    for L in R["info_tarik"]:
        notasi = "et" if L["no"] == 1 else f"eps-s{L['no']}"
        status = "leleh" if abs(L["eps"]) >= eps_y else "elastis"
        teks_eps += (f"  Tarik Lapis-{L['no']} (y={L['y']:.1f} mm):\n"
                     f"    {notasi:<6} = 0.003 x (y - c) / c = "
                     f"0.003 x ({L['y']:.1f} - {R['c']:.2f}) / {R['c']:.2f} "
                     f"= {L['eps']:+.5f}  ({status})\n"
                     f"    fs     = {L['fs']:+.2f} MPa\n")

    s4 = dict(no="b4.", ref="SNI 2847:2019 Pasal 22.2.1.1 - Strain linear",
              judul="Regangan & tegangan baja per lapis",
              isi=(f"Tegangan tiap lapis: jika |eps| < eps-y -> fs = eps x 200000\n"
                   f"                     jika |eps| >= eps-y -> fs = +/- fy\n\n"
                   f"{teks_eps.rstrip()}"),
              ok=True)

    teks_F = ""
    for L in R["info_tekan"]:
        teks_F += (f"  Cs Lapis-{L['no']} = As' x (fs' - 0.85 fc)" if L["y"] <= R["a"]
                   else f"  Cs Lapis-{L['no']} = As' x fs'")
        teks_F += f" = {L['F']:+,.0f} N\n"
    for L in R["info_tarik"]:
        teks_F += f"  T  Lapis-{L['no']} = As x fs = {L['F']:+,.0f} N\n"

    s5 = dict(no="b5.", ref="SNI 2847:2019 Pasal 22.2.2 - Distribusi tegangan",
              judul="Gaya tekan beton (Cc), gaya baja tekan (Cs), gaya tarik (T)",
              isi=(f"Cc = 0.85 x fc x a x b\n"
                   f"   = 0.85 x {fc} x {R['a']:.2f} x {b}\n"
                   f"   = {R['Cc']:,.0f} N  =  {R['Cc']/1000:.2f} kN\n\n"
                   f"{teks_F}"
                   f"\nCek keseimbangan: Cc + Cs - T = "
                   f"{R['Cc']:,.0f} + {R['Cs']:,.0f} - {R['T']:,.0f} = "
                   f"{R['Cc']+R['Cs']-R['T']:,.0f} N  (~ 0, OK)"),
              ok=True)

    s6 = dict(no="b6.", ref="SNI 2847:2019 Pasal 9.6.1 & 21.2.2",
              judul="Rasio tulangan tarik (Rho) - kontrol min & max",
              isi=(f"Rho     = As / (b x d) = {R['As_tarik']:.1f} / "
                   f"({b:.0f} x {R['d_tarik']:.2f}) = {R['rho']*100:.4f}%\n"
                   f"Rho-min = max(0.25 sqrt(fc)/fy , 1.4/fy)\n"
                   f"        = max({R['rho_mA']*100:.4f}% , {R['rho_mB']*100:.4f}%) "
                   f"= {R['rho_min']*100:.4f}%\n"
                   f"Rho-bal = 0.85 Beta-1 fc/fy x 600/(600+fy) = {R['rho_bal']*100:.4f}%\n"
                   f"Rho-max = 0.75 Rho-bal = {R['rho_max']*100:.4f}%\n\n"
                   f"Kontrol Rho >= Rho-min : {'[OK]' if R['ok_rho_min'] else '[TIDAK OK]'}\n"
                   f"Kontrol Rho <= Rho-max : {'[OK]' if R['ok_rho_max'] else '[TIDAK OK]'}"),
              ok=ok_rho)

    if R["et"] >= 0.005:
        klas = "et >= 0.005  -->  Tension-controlled  [OK]"
    elif R["et"] >= 0.004:
        klas = "0.004 <= et < 0.005  -->  Zona transisi  [PERLU TINJAUAN]"
    else:
        klas = "et < 0.004  -->  Tidak memenuhi syarat  [TIDAK OK]"

    s7 = dict(no="b7.", ref="SNI 2847:2019 Pasal 21.2.2",
              judul="Regangan tarik terjauh (et) - klasifikasi penampang",
              isi=(f"et = regangan lapis tarik paling bawah\n"
                   f"   = {R['et']:.5f}\n"
                   f"{klas}"),
              ok=R["ok_et"])

    s8 = dict(no="b8.", ref="SNI 2847:2019 Tabel 21.2.2",
              judul="Faktor reduksi kekuatan (Phi)",
              isi=f"{R['phi_cara']}\n  -->  Phi = {R['phi']:.4f}",
              ok=R["ok_et"])

    teks_mom = (f"Mn = Cc x (d - a/2) + Sum[ Cs_i x (d - y_i) ]\n"
                f"     (referensi: titik berat tulangan tarik d = {R['d_tarik']:.2f} mm)\n\n"
                f"  Cc x (d - a/2) = {R['Cc']:,.0f} x ({R['d_tarik']:.2f} - {R['a']/2:.2f})\n"
                f"                 = {R['Cc']*(R['d_tarik']-R['a']/2):,.0f} N.mm\n")
    for L in R["info_tekan"]:
        teks_mom += (f"  Cs Lapis-{L['no']} x (d - y_i) = "
                     f"{L['F']:+,.0f} x ({R['d_tarik']:.2f} - {L['y']:.1f}) "
                     f"= {L['F']*(R['d_tarik']-L['y']):+,.0f} N.mm\n")

    s9 = dict(no="b9.", ref="SNI 2847:2019 Pasal 22.3.2",
              judul="Momen nominal (Mn) dan momen rencana (Phi.Mn)",
              isi=(f"{teks_mom}\n"
                   f"Mn     = {R['Mn']:.3f} kN.m\n"
                   f"Phi.Mn = Phi x Mn = {R['phi']:.4f} x {R['Mn']:.3f} = "
                   f"{R['phiMn']:.3f} kN.m"),
              ok=True)

    ket_dc = "AMAN  --  Phi.Mn >= Mu" if R["ok_dc"] else \
             "TIDAK AMAN  --  Phi.Mn < Mu  (penampang perlu diperbesar / tulangan ditambah)"
    s10 = dict(no="b10.", ref="SNI 2847:2019 Pasal 9.5.1.1 - Mu <= Phi.Mn",
               judul="D/C Ratio (Demand-to-Capacity) - LENTUR",
               isi=(f"D/C = Mu / Phi.Mn\n"
                    f"    = {Mu:.3f} / {R['phiMn']:.3f}\n"
                    f"    = {R['DC']:.3f}\n\n"
                    f"{ket_dc}"),
               ok=R["ok_dc"])

    return [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10]


# ============================================================
# BUAT STEP-STEP LAPORAN GESER (b11 - b18)
# ============================================================
def buat_steps_geser(fc, fyt, b, d_aktual, Vu, ds, s_seng, n_kaki, G):
    s11 = dict(no="b11.", ref="SNI 2847:2019 Pasal 21.2.1",
               judul="Faktor reduksi geser (Phi_v)",
               isi=f"Untuk evaluasi geser balok beton bertulang:\n  -->  Phi_v = {G['Phi_v']:.2f}",
               ok=True)

    s12 = dict(no="b12.", ref="SNI 2847:2019 Pasal 22.5.5.1",
               judul="Kapasitas geser beton (Vc)",
               isi=(f"Vc = 0.17 x lambda x sqrt(fc) x b x d        (Newton)\n"
                    f"   = 0.17 x {G['lambda_']:.2f} x sqrt({fc:.1f}) x {b:.0f} x {d_aktual:.2f}\n"
                    f"   = 0.17 x {G['lambda_']:.2f} x {math.sqrt(fc):.4f} x "
                    f"{b:.0f} x {d_aktual:.2f}\n"
                    f"   = {G['Vc_N']:,.0f} N\n"
                    f"   = {G['Vc']:.2f} kN\n\n"
                    f"Phi.Vc       = {G['Phi_v']:.2f} x {G['Vc']:.2f} = {G['phiVc']:.2f} kN\n"
                    f"0.5 Phi.Vc   = {G['half_phiVc']:.2f} kN"),
               ok=True)

    s13 = dict(no="b13.", ref="SNI 2847:2019 Pasal 9.6.3 & 22.5.1.1",
               judul="Cek kebutuhan sengkang",
               isi=(f"Kategori berdasarkan Vu:\n"
                    f"  Jika Vu <= 0.5 Phi.Vc            -->  tidak perlu sengkang\n"
                    f"  Jika 0.5 Phi.Vc < Vu <= Phi.Vc   -->  pasang sengkang minimum\n"
                    f"  Jika Vu > Phi.Vc                 -->  hitung Vs\n\n"
                    f"{G['ket_klas']}"),
               ok=True)

    s14 = dict(no="b14.", ref="SNI 2847:2019 Pasal 22.5.1.2",
               judul="Vs perlu & cek Vs maksimum",
               isi=(f"Vs_perlu = Vu/Phi_v - Vc\n"
                    f"         = {Vu:.2f}/{G['Phi_v']:.2f} - {G['Vc']:.2f}\n"
                    f"         = {G['Vs_perlu']:.2f} kN\n\n"
                    f"Vs_max   = 0.66 x sqrt(fc) x b x d / 1000\n"
                    f"         = 0.66 x {math.sqrt(fc):.4f} x {b:.0f} x {d_aktual:.2f} / 1000\n"
                    f"         = {G['Vs_max']:.2f} kN\n\n"
                    f"Kontrol Vs_perlu ({G['Vs_perlu']:.2f}) <= Vs_max ({G['Vs_max']:.2f})  "
                    f"-->  {'[OK]' if G['ok_Vs_max'] else '[TIDAK OK] - Penampang harus diperbesar'}"),
               ok=G["ok_Vs_max"])

    s15 = dict(no="b15.", ref="SNI 2847:2019 Pasal 22.5.10.5.3",
               judul="Luas sengkang terpasang (Av) per spasi",
               isi=(f"Av_pasang = n_kaki x (pi/4 x ds^2)\n"
                    f"          = {n_kaki} x (pi/4 x {ds:.0f}^2)\n"
                    f"          = {n_kaki} x {math.pi/4*ds**2:.2f}\n"
                    f"          = {G['Av_pasang']:.2f} mm2\n\n"
                    f"  --> Sengkang terpasang : {n_kaki} kaki D{int(ds)} - jarak {s_seng:.0f} mm"),
               ok=True)

    s16 = dict(no="b16.", ref="SNI 2847:2019 Pasal 9.6.3.3 & 9.7.6.2.2",
               judul="Av minimum & spasi maksimum sengkang",
               isi=(f"-- Av minimum --\n"
                    f"Av_min/s = max( 0.062 sqrt(fc) b/fyt , 0.35 b/fyt )\n"
                    f"         = max( 0.062 x {math.sqrt(fc):.4f} x {b:.0f}/{fyt:.0f} ,\n"
                    f"                0.35 x {b:.0f}/{fyt:.0f} )\n"
                    f"         = max( {G['AvS_minA']:.4f} , {G['AvS_minB']:.4f} ) "
                    f"= {G['AvS_min']:.4f} mm2/mm\n"
                    f"Av_min   = (Av_min/s) x s_pasang = {G['AvS_min']:.4f} x {s_seng:.0f}\n"
                    f"         = {G['Av_min']:.2f} mm2\n\n"
                    f"Kontrol Av_pasang ({G['Av_pasang']:.2f}) >= Av_min ({G['Av_min']:.2f})  "
                    f"-->  {'[OK]' if G['ok_Av'] else '[TIDAK OK]'}\n\n"
                    f"-- Spasi maksimum --\n"
                    f"{G['rumus_smax']}\n\n"
                    f"Kontrol s_pasang ({s_seng:.0f} mm) <= s_max ({G['s_max']:.1f} mm)  "
                    f"-->  {'[OK]' if G['ok_spasi'] else '[TIDAK OK]'}"),
               ok=(G["ok_Av"] and G["ok_spasi"]))

    s17 = dict(no="b17.", ref="SNI 2847:2019 Pasal 22.5.10.5.3",
               judul="Vs aktual & kapasitas geser rencana (Phi.Vn)",
               isi=(f"Vs_aktual = Av_pasang x fyt x d / s_pasang / 1000\n"
                    f"          = {G['Av_pasang']:.2f} x {fyt:.0f} x {d_aktual:.2f} / "
                    f"{s_seng:.0f} / 1000\n"
                    f"          = {G['Vs_aktual']:.2f} kN\n"
                    + (f"  (Vs_aktual > Vs_max -> Vs efektif dibatasi = "
                       f"{G['Vs_efektif']:.2f} kN)\n"
                       if G['Vs_aktual'] > G['Vs_max'] else "") +
                    f"\nVn        = Vc + Vs_efektif\n"
                    f"          = {G['Vc']:.2f} + {G['Vs_efektif']:.2f}\n"
                    f"          = {G['Vn_efektif']:.2f} kN\n\n"
                    f"Phi.Vn    = Phi_v x Vn = {G['Phi_v']:.2f} x {G['Vn_efektif']:.2f}\n"
                    f"          = {G['PhiVn_efektif']:.2f} kN"),
               ok=True)

    ket_dc = "AMAN  --  Phi.Vn >= Vu" if G["ok_dc"] else \
             "TIDAK AMAN  --  Phi.Vn < Vu  (perbesar penampang / rapatkan sengkang / tambah kaki)"
    s18 = dict(no="b18.", ref="SNI 2847:2019 Pasal 9.5.1.1 - Vu <= Phi.Vn",
               judul="D/C Ratio (Demand-to-Capacity) - GESER",
               isi=(f"D/C = Vu / Phi.Vn\n"
                    f"    = {Vu:.2f} / {G['PhiVn_efektif']:.2f}\n"
                    f"    = {G['DC_geser']:.3f}\n\n"
                    f"{ket_dc}"),
               ok=G["ok_dc"])

    return [s11, s12, s13, s14, s15, s16, s17, s18]


# ============================================================
# BUAT STEP-STEP LAPORAN TORSI (b19 - b28)
# ============================================================
def buat_steps_torsi(fc, fyt, fy_long, b, h, cc_sel, ds, s_seng,
                     Tu, Vu, d_aktual, T):
    if T["abaikan_torsi"]:
        s_abaikan = dict(
            no="b19-b28.", ref="SNI 2847:2019 Pasal 22.7.4",
            judul="EVALUASI TORSI -- DILEWATI",
            isi=(f"Tu = {Tu:.3f} kN.m\n"
                 f"Phi_t x Tth = {T['Phi_t']:.2f} x {T['Tth']:.3f} = {T['phi_Tth']:.3f} kN.m\n\n"
                 f"Karena Tu ({Tu:.3f}) <= Phi_t x Tth ({T['phi_Tth']:.3f}) kN.m\n"
                 f"  -->  [DIABAIKAN] Efek torsi dapat diabaikan sesuai SNI 2847:2019 Pasal 22.7.4"),
            ok=True)
        return [s_abaikan]

    _ok_dim   = "[OK] Dimensi penampang mencukupi" if T["ok_dimensi"] else "[TIDAK OK] Penampang harus diperbesar!"
    _ok_seng  = "[OK]" if T["ok_sengkang_gabungan"] else ("[TIDAK OK] Perlu s <= " + str(round(T["s_perlu_gabungan"])) + " mm")
    _ok_avt   = "[OK]" if T["ok_Avt_min"] else "[TIDAK OK]"
    _ok_spasi = "[OK]" if T["ok_spasi_torsi"] else "[TIDAK OK]"
    _ok_dc_t  = "AMAN  --  Phi.Tn >= Tu_desain" if T["ok_DC_torsi"] else "TIDAK AMAN  --  Phi.Tn < Tu_desain (perkecil spasi / tambah sengkang)"
    _ok_dim_r  = "[OK]" if T["ok_dimensi"] else "[TIDAK OK]"
    _ok_seng_r = "[OK]" if T["ok_sengkang_gabungan"] else "[TIDAK OK]"
    _ok_avt_r  = "[OK]" if T["ok_Avt_min"] else "[TIDAK OK]"
    _ok_spasi_r= "[OK]" if T["ok_spasi_torsi"] else "[TIDAK OK]"
    _ok_dc_r   = "[OK]" if T["ok_DC_torsi"] else "[TIDAK OK]"

    s19 = dict(no="b19.", ref="SNI 2847:2019 Pasal 22.7",
               judul="Properti penampang torsi",
               isi=(f"Acp = b x h = {b:.0f} x {h:.0f} = {T['Acp']:,.0f} mm2\n"
                    f"pcp = 2 x (b + h) = 2 x ({b:.0f} + {h:.0f}) = {T['pcp']:.0f} mm\n\n"
                    f"Dimensi sengkang tertutup (c to c):\n"
                    f"  x1 = b - 2 cc - ds = {b:.0f} - 2x{cc_sel:.0f} - {ds:.0f} = {T['x1']:.1f} mm\n"
                    f"  y1 = h - 2 cc - ds = {h:.0f} - 2x{cc_sel:.0f} - {ds:.0f} = {T['y1']:.1f} mm\n\n"
                    f"Aoh = x1 x y1 = {T['x1']:.1f} x {T['y1']:.1f} = {T['Aoh']:,.1f} mm2\n"
                    f"ph  = 2 x (x1 + y1) = 2 x ({T['x1']:.1f} + {T['y1']:.1f}) = {T['ph']:.1f} mm\n"
                    f"Ao  = 0.85 x Aoh = 0.85 x {T['Aoh']:,.1f} = {T['Ao']:,.1f} mm2"),
               ok=True)

    s20 = dict(no="b20.", ref="SNI 2847:2019 Pasal 21.2.1",
               judul="Faktor reduksi torsi (Phi_t)",
               isi=f"Untuk evaluasi torsi balok beton bertulang:\n  -->  Phi_t = {T['Phi_t']:.2f}",
               ok=True)

    s21 = dict(no="b21.", ref="SNI 2847:2019 Pasal 22.7.4",
               judul="Batas ambang torsi (Tth) -- cek apakah torsi diabaikan",
               isi=(f"Tth = 0.083 x lambda x sqrt(fc) x Acp^2 / pcp\n"
                    f"    = 0.083 x {T['lambda_']:.2f} x {math.sqrt(fc):.4f} x "
                    f"{T['Acp']:,.0f}^2 / {T['pcp']:.0f}\n"
                    f"    = {T['Tth_Nmm']:,.0f} N.mm  =  {T['Tth']:.4f} kN.m\n\n"
                    f"Phi_t x Tth = {T['Phi_t']:.2f} x {T['Tth']:.4f} = {T['phi_Tth']:.4f} kN.m\n\n"
                    f"Tu = {Tu:.3f} kN.m\n"
                    f"  -->  [HITUNG TORSI] Tu > Phi_t x Tth"),
               ok=True)

    s22 = dict(no="b22.", ref="SNI 2847:2019 Pasal 22.7.3",
               judul="Klasifikasi torsi & Tu desain",
               isi=(f"Tipe torsi : {T['tipe_torsi']}\n\n"
                    f"Tcr = 0.33 x lambda x sqrt(fc) x Acp^2 / pcp = {T['Tcr']:.4f} kN.m\n"
                    f"Phi_t x Tcr = {T['Phi_t']:.2f} x {T['Tcr']:.4f} = {T['phi_Tcr']:.4f} kN.m\n\n"
                    f"{T['catatan_tu']}"),
               ok=True)

    s23 = dict(no="b23.", ref="SNI 2847:2019 Pasal 22.7.7.1",
               judul="Cek dimensi penampang torsi",
               isi=(f"sqrt( (Vu/bw.d)^2 + (Tu.ph/(1.7.Aoh^2))^2 ) <= Phi_v.(Vc/bw.d + 0.66.sqrt(fc))\n\n"
                    f"Sisi kiri  = sqrt({T['term_geser']:.4f}^2 + {T['term_torsi']:.4f}^2) = {T['lhs_dim']:.4f} MPa\n"
                    f"Sisi kanan = {T['Phi_v']:.2f} x ({T['Vc']:,.2f}*1000/({b:.0f}*{d_aktual:.2f}) + 0.66*{math.sqrt(fc):.4f})\n"
                    f"           = {T['rhs_dim']:.4f} MPa\n\n"
                    f"DC_dim = {T['DC_dim']:.3f}  -->  {_ok_dim}"),
               ok=T["ok_dimensi"])

    s24 = dict(no="b24.", ref="SNI 2847:2019 Pasal 22.7.6.1",
               judul="At/s -- Kebutuhan sengkang torsi",
               isi=(f"At/s = Tu_desain / (Phi_t x 2 x Ao x fyt x cot(theta))\n"
                    f"     = {T['Tu_desain']:.4f}x1e6 / ({T['Phi_t']:.2f} x 2 x {T['Ao']:,.1f} x {fyt:.0f} x {T['cot_theta']:.1f})\n"
                    f"     = {T['At_per_s']:.6f} mm2/mm"),
               ok=True)

    s25 = dict(no="b25.", ref="SNI 2847:2019 Pasal 9.6.4.2",
               judul="Sengkang gabungan (geser + torsi)",
               isi=(f"Av/s pasang  = Av_pasang / s = {T['Avt_pasang']:.2f} / {s_seng:.0f} = {T['Av_per_s_pasang']:.4f} mm2/mm\n"
                    f"Perlu gabungan = Av/s + 2.(At/s) = {T['Av_per_s_pasang']:.4f} + 2x{T['At_per_s']:.6f}\n"
                    f"              = {T['Avt_per_s_perlu']:.4f} mm2/mm\n"
                    f"Av perlu abs  = {T['Avt_per_s_perlu']:.4f} x {s_seng:.0f} = {T['Avt_perlu_abs']:.2f} mm2\n"
                    f"Av terpasang  = {T['Avt_pasang']:.2f} mm2\n\n"
                    f"Kontrol  -->  {_ok_seng}\n\n"
                    f"-- (Av+2At) minimum --\n"
                    f"(Av+2At)_min/s = max(0.062 sqrt(fc) b/fyt , 0.35 b/fyt)\n"
                    f"              = max({T['AvS_minA']:.4f} , {T['AvS_minB']:.4f}) = {T['AvS_min']:.4f} mm2/mm\n"
                    f"(Av+2At)_min   = {T['AvS_min']:.4f} x {s_seng:.0f} = {T['Avt_min']:.2f} mm2\n"
                    f"Kontrol Av_pasang >= (Av+2At)_min  -->  {_ok_avt}"),
               ok=(T["ok_sengkang_gabungan"] and T["ok_Avt_min"]))

    s26 = dict(no="b26.", ref="SNI 2847:2019 Pasal 9.7.6.3.3",
               judul="Spasi maksimum sengkang torsi",
               isi=(f"s_max_torsi = min(ph/8 , 300 mm)\n"
                    f"           = min({T['ph']:.1f}/8 , 300)\n"
                    f"           = min({T['ph']/8:.1f} , 300)\n"
                    f"           = {T['s_max_torsi']:.1f} mm\n\n"
                    f"Kontrol s_pasang ({s_seng:.0f} mm) <= s_max_torsi ({T['s_max_torsi']:.1f} mm)  -->  {_ok_spasi}"),
               ok=T["ok_spasi_torsi"])

    s27 = dict(no="b27.", ref="SNI 2847:2019 Pasal 22.7.6.1 & 9.6.4.3",
               judul="Tulangan longitudinal torsi (Al)",
               isi=(f"Al = At/s x ph x (fyt/fy_long) x cot^2(theta)\n"
                    f"   = {T['At_per_s']:.6f} x {T['ph']:.1f} x ({fyt:.0f}/{fy_long:.0f}) x {T['cot_theta']:.1f}^2\n"
                    f"   = {T['Al']:.2f} mm2\n\n"
                    f"Al_min = max(Al_minA , Al_minB) = max({T['Al_minA']:.2f} , {T['Al_minB']:.2f}) = {T['Al_min']:.2f} mm2\n"
                    f"Al_pakai = max(Al , Al_min) = max({T['Al']:.2f} , {T['Al_min']:.2f}) = {T['Al_pakai']:.2f} mm2\n\n"
                    f"Jumlah batang D{int(T['db_long_torsi'])}: n = ceil({T['Al_pakai']:.2f} / {T['Ab_long']:.2f}) = {T['n_batang']} batang"),
               ok=True)

    s28 = dict(no="b28.", ref="SNI 2847:2019 Pasal 9.5.1.2",
               judul="D/C Ratio (Demand-to-Capacity) - TORSI & Kesimpulan",
               isi=(f"Kapasitas Phi.Tn (dari sengkang terpasang):\n"
                    f"  At/s_cap = Av_pasang / s = {T['Avt_pasang']:.2f} / {s_seng:.0f} = {T['At_per_s_cap']:.4f} mm2/mm\n"
                    f"  Tn_cap = 2 x Ao x At/s_cap x fyt x cot(theta) / 1e6\n"
                    f"         = 2 x {T['Ao']:,.1f} x {T['At_per_s_cap']:.4f} x {fyt:.0f} x 1.0 / 1e6\n"
                    f"         = {T['Tn_cap']:.4f} kN.m\n"
                    f"  Phi.Tn = {T['Phi_t']:.2f} x {T['Tn_cap']:.4f} = {T['PhiTn_cap']:.4f} kN.m\n\n"
                    f"D/C = Tu_desain / Phi.Tn\n"
                    f"    = {T['Tu_desain']:.4f} / {T['PhiTn_cap']:.4f}\n"
                    f"    = {T['DC_torsi']:.3f}\n\n"
                    f"{_ok_dc_t}\n\n"
                    f"-- Rangkuman kontrol torsi --\n"
                    f"Dimensi penampang    : {_ok_dim_r}\n"
                    f"Sengkang gabungan    : {_ok_seng_r}\n"
                    f"(Av+2At) minimum     : {_ok_avt_r}\n"
                    f"Spasi max torsi      : {_ok_spasi_r}\n"
                    f"D/C torsi <= 1.0     : {_ok_dc_r}"),
               ok=T["ok_torsi_total"])

    return [s19, s20, s21, s22, s23, s24, s25, s26, s27, s28]


# ============================================================
# FUNGSI CEK SYARAT SEISMIK (SRPMB / SRPMM / SRPMK)
# Referensi: SNI 2847:2019 Pasal 18.4 (SRPMM) & 18.6 (SRPMK)
# ============================================================
def hitung_mpr(As, fy, fc, b, d):
    """
    Momen probable Mpr dengan 1.25fy.
    SNI 2847:2019 Pasal 18.6.5 / ACI 318-14 R18.6.5
    As  : luas tulangan (mm2)
    d   : tinggi efektif (mm)
    Returns Mpr dalam kN.m
    """
    fy_pr = 1.25 * fy
    a_pr  = As * fy_pr / (0.85 * fc * b)
    Mpr   = As * fy_pr * (d - a_pr / 2.0) / 1_000_000.0   # kN.m
    return Mpr, a_pr


def cek_syarat_seismik(mode, R, G, fc, fy, fyt, b, h, d,
                        As_tarik, As_tekan, s_seng, ds,
                        lapis_tarik, beta1,
                        Ln=None, Vu_input=None):
    """
    Cek persyaratan tambahan sesuai mode seismik.
    Returns list of dict {no, judul, ref, isi, ok}
    mode: "Biasa", "SRPMB", "SRPMM", "SRPMK"
    Ln  : bentang bersih balok (mm) -- untuk Ve SRPMM/K
    """
    if mode == "Biasa":
        return []

    steps = []

    # ---- SRPMB: Informatif saja ----
    if mode == "SRPMB":
        steps.append(dict(
            no="g1.", ref="SNI 2847:2019 Pasal 18.3",
            judul="SRPMB — Informasi Persyaratan",
            isi=(
                f"Sistem Rangka Pemikul Momen Biasa (SRPMB)\n"
                f"tidak memiliki persyaratan detailing khusus\n"
                f"di luar persyaratan umum SNI 2847:2019.\n\n"
                f"Hasil evaluasi lentur, geser, dan torsi di atas\n"
                f"sudah mencakup seluruh persyaratan yang berlaku.\n\n"
                f"Rho terpasang = {R['rho']*100:.4f}%\n"
                f"  Rho-min    = {R['rho_min']*100:.4f}%   --> "
                f"{'[OK]' if R['ok_rho_min'] else '[TIDAK OK]'}\n"
                f"  Rho-max    = {R['rho_max']*100:.4f}%   --> "
                f"{'[OK]' if R['ok_rho_max'] else '[TIDAK OK]'}"
            ),
            ok=(R["ok_rho_min"] and R["ok_rho_max"]),
        ))
        return steps

    # ---- SRPMM & SRPMK: cek bersama ----
    # Ambil diameter terkecil dari lapis tarik
    db_list = [L["db"] for L in lapis_tarik if L["n"] > 0]
    db_min  = min(db_list) if db_list else ds

    # --- g1: As' >= 0.5 As_tarik ---
    ok_as_tekan = (As_tekan >= 0.5 * As_tarik)
    ref_as = "SNI 2847:2019 Pasal 18.4.2.1" if mode == "SRPMM" else "SNI 2847:2019 Pasal 18.6.3.2"
    steps.append(dict(
        no="g1.", ref=ref_as,
        judul="Tulangan tekan minimum (As' >= 0.5 As_tarik)",
        isi=(
            f"As_tarik   = {As_tarik:.1f} mm2\n"
            f"0.5 x As_tarik = {0.5*As_tarik:.1f} mm2\n"
            f"As_tekan   = {As_tekan:.1f} mm2\n\n"
            f"Kontrol As_tekan >= 0.5 x As_tarik  -->  "
            f"{'[OK]' if ok_as_tekan else '[TIDAK OK] -- Tambah tulangan tekan'}"
        ),
        ok=ok_as_tekan,
    ))

    # --- g2: Panjang zona lo (informatif) ---
    lo_min = 2.0 * h   # mm
    if Ln is not None:
        ket_lo = (
            f"lo_min = 2 x h = 2 x {h:.0f} = {lo_min:.0f} mm\n"
            f"Ln (bentang bersih) = {Ln:.0f} mm\n"
            f"Zona lo dipasang dari muka kolom sejauh >= {lo_min:.0f} mm\n"
            f"  -->  [PERLU DIPASANG] Sengkang rapat di zona lo = {lo_min:.0f} mm"
        )
    else:
        ket_lo = (
            f"lo_min = 2 x h = 2 x {h:.0f} = {lo_min:.0f} mm\n"
            f"Bentang bersih Ln tidak diinput -- zona lo = {lo_min:.0f} mm dari muka kolom\n"
            f"  -->  [INFORMATIF] Pasang sengkang rapat di zona lo"
        )
    steps.append(dict(
        no="g2.", ref="SNI 2847:2019 Pasal 18.4.2.2" if mode=="SRPMM" else "SNI 2847:2019 Pasal 18.6.4.2",
        judul="Panjang zona sendi plastis (lo)",
        isi=ket_lo,
        ok=True,
    ))

    # --- g3: Spasi sengkang zona lo ---
    if mode == "SRPMM":
        s_max_lo  = min(d / 4.0, 8.0 * db_min, 24.0 * ds, 300.0)
        ref_spasi = "SNI 2847:2019 Pasal 18.4.2.3"
        rumus_s   = (
            f"s_max_lo = min(d/4, 8db_min, 24ds, 300 mm)\n"
            f"         = min({d/4:.1f}, {8*db_min:.1f}, {24*ds:.1f}, 300)\n"
            f"         = {s_max_lo:.1f} mm"
        )
    else:  # SRPMK
        s_max_lo  = min(d / 4.0, 6.0 * db_min, 150.0)
        ref_spasi = "SNI 2847:2019 Pasal 18.6.4.4"
        rumus_s   = (
            f"s_max_lo = min(d/4, 6db_min, 150 mm)\n"
            f"         = min({d/4:.1f}, {6*db_min:.1f}, 150)\n"
            f"         = {s_max_lo:.1f} mm"
        )
    ok_spasi_lo = (s_seng <= s_max_lo)
    steps.append(dict(
        no="g3.", ref=ref_spasi,
        judul=f"Spasi sengkang zona lo ({mode})",
        isi=(
            f"{rumus_s}\n\n"
            f"s terpasang = {s_seng:.0f} mm\n"
            f"Kontrol s <= s_max_lo  -->  "
            f"{'[OK]' if ok_spasi_lo else f'[TIDAK OK] -- Rapatkan ke <= {s_max_lo:.0f} mm'}"
        ),
        ok=ok_spasi_lo,
    ))

    # --- g4: Mpr & Ve ---
    Mpr_tarik, a_tarik = hitung_mpr(As_tarik, fy, fc, b, d)
    Mpr_tekan, a_tekan = hitung_mpr(As_tekan, fy, fc, b, d) if As_tekan > 0 else (0.0, 0.0)
    ref_ve = "SNI 2847:2019 Pasal 18.4.2.3" if mode == "SRPMM" else "SNI 2847:2019 Pasal 18.6.5.1"

    if Ln is not None and Ln > 0:
        Ve     = (Mpr_tarik + Mpr_tekan) / (Ln / 1000.0)   # Ln mm -> m
        ok_ve  = (Vu_input is not None and Ve > (Vu_input if Vu_input else 0))
        ket_ve = (
            f"Mpr_tarik = As_tarik x 1.25fy x (d - a/2)\n"
            f"          = {As_tarik:.1f} x {1.25*fy:.0f} x ({d:.2f} - {a_tarik/2:.2f}) / 1e6\n"
            f"          = {Mpr_tarik:.3f} kN.m\n\n"
            f"Mpr_tekan = {Mpr_tekan:.3f} kN.m  (pakai As_tekan = {As_tekan:.1f} mm2)\n\n"
            f"Ve = (Mpr_tarik + Mpr_tekan) / Ln\n"
            f"   = ({Mpr_tarik:.3f} + {Mpr_tekan:.3f}) / {Ln/1000:.3f}\n"
            f"   = {Ve:.2f} kN\n\n"
            f"Vu input   = {Vu_input:.2f} kN\n"
            f"Ve desain  = {Ve:.2f} kN\n"
            f"  -->  {'[PERHATIAN] Ve > Vu input -- gunakan Ve sebagai gaya geser desain!' if Ve > (Vu_input or 0) else '[OK] Vu input sudah mencakup Ve'}"
        )
        ok_g4 = True   # informatif
    else:
        Ve     = None
        ket_ve = (
            f"Mpr_tarik = {Mpr_tarik:.3f} kN.m  (As_tarik = {As_tarik:.1f} mm2, 1.25fy = {1.25*fy:.0f} MPa)\n"
            f"Mpr_tekan = {Mpr_tekan:.3f} kN.m  (As_tekan = {As_tekan:.1f} mm2)\n\n"
            f"Ve = (Mpr_tarik + Mpr_tekan) / Ln\n"
            f"  -->  [INPUT Ln diperlukan untuk menghitung Ve]\n"
            f"       Masukkan bentang bersih balok Ln untuk mendapatkan Ve desain."
        )
        ok_g4 = True

    steps.append(dict(
        no="g4.", ref=ref_ve,
        judul="Momen probable (Mpr) & gaya geser desain seismik (Ve)",
        isi=ket_ve,
        ok=ok_g4,
    ))

    # ---- Tambahan khusus SRPMK ----
    if mode == "SRPMK":
        # g5: rho <= 0.025
        rho = As_tarik / (b * d)
        ok_rho_max_srpmk = (rho <= 0.025)
        steps.append(dict(
            no="g5.", ref="SNI 2847:2019 Pasal 18.6.3.1",
            judul="Rasio tulangan tarik maksimum SRPMK (rho <= 0.025)",
            isi=(
                f"rho = As_tarik / (b x d)\n"
                f"    = {As_tarik:.1f} / ({b:.0f} x {d:.2f})\n"
                f"    = {rho*100:.4f}%\n\n"
                f"rho_max_SRPMK = 2.5%\n"
                f"Kontrol rho <= 2.5%  -->  "
                f"{'[OK]' if ok_rho_max_srpmk else '[TIDAK OK] -- Kurangi tulangan tarik atau perbesar dimensi'}"
            ),
            ok=ok_rho_max_srpmk,
        ))

        # g6: Kait gempa 135° (informatif)
        steps.append(dict(
            no="g6.", ref="SNI 2847:2019 Pasal 18.6.4.1",
            judul="Kait gempa sengkang 135 derajat (informatif)",
            isi=(
                f"SRPMK mensyaratkan kait gempa 135 derajat pada sengkang.\n"
                f"Ekstensi ujung kait >= 6 x ds = 6 x {ds:.0f} = {6*ds:.0f} mm\n"
                f"  -->  [INFORMATIF] Pastikan detail gambar memenuhi syarat kait 135 derajat"
            ),
            ok=True,
        ))

    return steps


# ============================================================
# VISUALISASI PENAMPANG (matplotlib)
# ============================================================
def gambar_penampang(b, h, cc_sel, ds, lapis_tarik, lapis_tekan,
                     c=None, torsi_data=None):
    fig, ax = plt.subplots(figsize=(5.5, 6.5))
    ax.add_patch(patches.Rectangle((0, 0), b, h, fill=True,
                                   facecolor="#e8e8e8", edgecolor="black", linewidth=1.8))
    sx, sy, sw, sh = cc_sel, cc_sel, b - 2*cc_sel, h - 2*cc_sel
    ax.add_patch(patches.Rectangle((sx, sy), sw, sh, fill=False,
                                   edgecolor="#1a3c5e", linewidth=1.2, linestyle="--"))
    if torsi_data is not None and not torsi_data.get("abaikan_torsi", True):
        x1 = torsi_data["x1"]; y1_t = torsi_data["y1"]
        xoh = cc_sel + ds / 2.0; yoh = cc_sel + ds / 2.0
        ax.add_patch(patches.Rectangle((xoh, yoh), x1, y1_t, fill=True,
                                       facecolor="#ff9800", alpha=0.12,
                                       edgecolor="#e65100", linewidth=1.0, linestyle=":"))
        ax.annotate(f"Aoh = {x1:.0f} x {y1_t:.0f} = {torsi_data['Aoh']:,.0f} mm2",
                    xy=(b/2, yoh + y1_t/2), fontsize=7.5, ha="center", va="center",
                    color="#e65100", bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.7))
        if torsi_data.get("n_batang", 0) > 0:
            db_lt = torsi_data["db_long_torsi"]; r_lt = db_lt / 2.0
            for cx_, cy_ in [(xoh, yoh), (xoh+x1, yoh), (xoh, yoh+y1_t), (xoh+x1, yoh+y1_t)]:
                ax.add_patch(patches.Circle((cx_, cy_), r_lt,
                                            facecolor="#9e9e9e", edgecolor="black", linewidth=0.6))
    for L in lapis_tarik:
        y_plot = h - L["y"]; n = L["n"]
        x_left = cc_sel + ds + L["db"]/2; x_right = b - cc_sel - ds - L["db"]/2
        xs = [x_left + i*(x_right-x_left)/(n-1) for i in range(n)] if n > 1 else [(x_left+x_right)/2]
        for x in xs:
            ax.add_patch(patches.Circle((x, y_plot), L["db"]/2,
                                        facecolor="#1a3c5e", edgecolor="black", linewidth=0.6))
        ax.annotate(f"{n}D{int(L['db'])}", xy=(b+8, y_plot), fontsize=8, va="center", color="#1a3c5e")
    for L in lapis_tekan:
        y_plot = h - L["y"]; n = L["n"]
        x_left = cc_sel + ds + L["db"]/2; x_right = b - cc_sel - ds - L["db"]/2
        xs = [x_left + i*(x_right-x_left)/(n-1) for i in range(n)] if n > 1 else [(x_left+x_right)/2]
        for x in xs:
            ax.add_patch(patches.Circle((x, y_plot), L["db"]/2,
                                        facecolor="#c62828", edgecolor="black", linewidth=0.6))
        ax.annotate(f"{n}D{int(L['db'])}", xy=(b+8, y_plot), fontsize=8, va="center", color="#c62828")
    if c is not None:
        y_c_plot = h - c
        ax.axhline(y=y_c_plot, color="#f9a825", linewidth=1.4, linestyle="-.", alpha=0.85)
        ax.annotate(f"  garis netral c = {c:.1f} mm", xy=(0, y_c_plot),
                    fontsize=8, va="bottom", color="#7a5800")
    ax.annotate(f"b = {int(b)} mm", xy=(b/2, -h*0.05), fontsize=9, ha="center", color="black")
    ax.annotate(f"h = {int(h)} mm", xy=(-b*0.10, h/2), fontsize=9, ha="center", color="black", rotation=90)
    if torsi_data is not None and not torsi_data.get("abaikan_torsi", True):
        legend_elems = [
            patches.Patch(facecolor="#ff9800", alpha=0.3, edgecolor="#e65100",
                          linestyle=":", label="Area Aoh (torsi)"),
            patches.Patch(facecolor="#9e9e9e", edgecolor="black",
                          label=f"Tul. long. torsi D{int(torsi_data['db_long_torsi'])}"),
        ]
        ax.legend(handles=legend_elems, loc="upper right", fontsize=7, framealpha=0.8)
    pad = max(b, h) * 0.18
    ax.set_xlim(-pad, b + pad*1.6); ax.set_ylim(-pad, h + pad*0.6)
    ax.set_aspect("equal"); ax.axis("off")
    ax.set_title("Penampang Balok (skala proporsional)", fontsize=10, color="#1a3c5e", pad=10)
    fig.tight_layout()
    return fig


def fig_to_png_bytes(fig):
    """Convert matplotlib figure ke PNG bytes."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    return buf
