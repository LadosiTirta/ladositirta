# =============================================================================
# uditch/perhitungan.py
# =============================================================================
# Satu fungsi utama: render_perhitungan(fr, dr, inp, lang)
#
# Menampilkan SELURUH RANTAI PERHITUNGAN secara runtut di Streamlit:
#
#   BAGIAN 1 — Data & Geometri
#   BAGIAN 2 — Tekanan Lateral per Kedalaman
#              • Tanah   → distribusi segitiga (dengan tabel z & σh)
#              • Surcharge → distribusi kotak  (uniform)
#              • Boussinesq → distribusi parabola (tabel z & σh)
#              • GAMBAR distribusi tekanan (matplotlib)
#   BAGIAN 3 — Resultan Gaya & Lengan Momen
#   BAGIAN 4 — Gaya Dalam: Mu, Vu, Nu
#              • Setiap baris: Rumus → Substitusi Angka → Hasil
#   BAGIAN 5 — DIAGRAM Mu, Vu, Nu sepanjang tinggi dinding (matplotlib)
#   BAGIAN 6 — Kapasitas penampang (ringkasan, detail ada di calc_engine)
#   BAGIAN 7 — Kontrol OK / NG
#
# Format setiap langkah:
#   st.latex(r"rumus")
#   st.markdown("`substitusi angka = hasil satuan`")
# =============================================================================

from __future__ import annotations
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import streamlit as st

# ── warna konsisten ───────────────────────────────────────────────────────────
_C_EARTH  = "#7B1FA2"   # ungu  — tekanan tanah
_C_SUR    = "#F57F17"   # oranye — surcharge / kotak
_C_BOU    = "#D32F2F"   # merah  — Boussinesq
_C_MU     = "#1565C0"   # biru   — momen
_C_VU     = "#2E7D32"   # hijau  — geser
_C_NU     = "#E65100"   # oranye — aksial
_C_WALL   = "#B0BEC5"   # abu    — beton
_C_DIM    = "#455A64"


# =============================================================================
# HELPERS
# =============================================================================

def _mm(mm): return mm / 1000.0

def _header(text: str):
    st.markdown(
        f'<div style="background:#1A237E;color:white;padding:8px 16px;'
        f'margin:16px 0 8px 0;border-radius:6px;font-size:14px;font-weight:700;">'
        f'{text}</div>',
        unsafe_allow_html=True,
    )

def _step(label: str, formula_latex: str, sub: str, result: float, unit: str,
          ref: str = "", ok: bool = None):
    """Satu baris perhitungan: label | formula LaTeX | substitusi → hasil"""
    # Badge OK/NG
    badge = ""
    if ok is True:
        badge = ' <span style="color:#2E7D32;font-weight:700;">✅ OK</span>'
    elif ok is False:
        badge = ' <span style="color:#C62828;font-weight:700;">❌ NG</span>'

    res_fmt = f"{result:.4f}".rstrip("0").rstrip(".")

    st.markdown(
        f'<div style="border-left:3px solid #1A237E;padding:4px 10px;'
        f'margin:4px 0;background:#F8F9FA;border-radius:0 4px 4px 0;">'
        f'<span style="font-weight:700;color:#1A237E;font-size:13px;">{label}</span>'
        + (f'<span style="color:#7B1FA2;font-size:10px;float:right;">{ref}</span>' if ref else "")
        + f'</div>',
        unsafe_allow_html=True,
    )
    try:
        st.latex(formula_latex)
    except Exception:
        st.code(formula_latex)
    st.markdown(
        f'<div style="padding:2px 14px 8px 14px;">'
        f'<code style="font-size:12px;background:#EDE7F6;padding:2px 6px;'
        f'border-radius:3px;">{sub}</code>'
        f' → <strong style="color:#1565C0;font-size:14px;">{res_fmt}</strong>'
        f' <span style="color:#546E7A;">{unit}</span>{badge}</div>',
        unsafe_allow_html=True,
    )

def _tbl_header(cols):
    st.markdown(
        '<table style="width:100%;border-collapse:collapse;font-size:12px;">'
        + '<tr style="background:#1A237E;color:white;">'
        + "".join(f'<th style="padding:5px 8px;text-align:right;">{c}</th>' for c in cols)
        + '</tr>',
        unsafe_allow_html=True,
    )

def _tbl_row(vals, highlight=False):
    bg = "#E3F2FD" if highlight else "white"
    st.markdown(
        f'<tr style="background:{bg};">'
        + "".join(f'<td style="padding:4px 8px;text-align:right;border-bottom:1px solid #ECEFF1;">{v}</td>'
                  for v in vals)
        + '</tr>',
        unsafe_allow_html=True,
    )

def _tbl_close():
    st.markdown('</table>', unsafe_allow_html=True)


# =============================================================================
# BAGIAN 2 — GAMBAR DISTRIBUSI TEKANAN (matplotlib)
# =============================================================================

def _fig_distribusi(sigma_e_pts, sigma_s_pts, sigma_b_pts, z_pts,
                    H, method, F_e, F_s, y_e, y_s, lang) -> plt.Figure:
    """
    Diagram distribusi tekanan lateral:
    - Segitiga  (tanah aktif)
    - Kotak     (surcharge, jika method=0)
    - Parabola  (Boussinesq, jika method=1)
    Sumbu y = kedalaman dari puncak (0=top, H=base), y-axis dibalik.
    """
    fig, ax = plt.subplots(figsize=(8, 5.5), facecolor="#F8F9FA")
    ax.set_facecolor("#F8F9FA")

    # ── Tekanan tanah (segitiga, warna ungu) ─────────────────────────────────
    ax.fill_betweenx(z_pts, 0, sigma_e_pts,
                     alpha=0.40, color=_C_EARTH,
                     label="Tanah aktif Ka·γs·z" if lang=="ID" else "Active earth Ka·γs·z")
    ax.plot(sigma_e_pts, z_pts, color=_C_EARTH, lw=2.5)

    # Annotation at base
    ax.annotate(f"σh = {sigma_e_pts[-1]:.2f} kPa",
                xy=(sigma_e_pts[-1], z_pts[-1]),
                xytext=(sigma_e_pts[-1]+1.5, z_pts[-1]-0.05*H),
                fontsize=8.5, color=_C_EARTH,
                arrowprops=dict(arrowstyle="->", color=_C_EARTH, lw=0.9))

    # ── Surcharge (kotak, oranye) ─────────────────────────────────────────────
    if method == 0 and sigma_s_pts is not None:
        tot_s = [se+ss for se, ss in zip(sigma_e_pts, sigma_s_pts)]
        ax.fill_betweenx(z_pts, sigma_e_pts, tot_s,
                         alpha=0.35, color=_C_SUR,
                         label=f"Surcharge ekivalen" if lang=="ID" else "Equivalent surcharge")
        ax.plot(tot_s, z_pts, color=_C_SUR, lw=2.5, ls="--")
        ax.annotate(f"σ_sur = {sigma_s_pts[0]:.2f} kPa (uniform)",
                    xy=(tot_s[len(tot_s)//2], z_pts[len(z_pts)//2]),
                    xytext=(tot_s[len(tot_s)//2]+1, z_pts[len(z_pts)//2]-0.08*H),
                    fontsize=8, color=_C_SUR,
                    arrowprops=dict(arrowstyle="->", color=_C_SUR, lw=0.8))
        ax.annotate(f"TOTAL = {tot_s[-1]:.2f} kPa",
                    xy=(tot_s[-1], z_pts[-1]),
                    xytext=(tot_s[-1]+1.5, z_pts[-1]+0.03*H),
                    fontsize=8.5, color=_C_SUR, fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color=_C_SUR, lw=0.9))

    # ── Boussinesq (parabola, merah) ─────────────────────────────────────────
    elif method == 1 and sigma_b_pts is not None:
        tot_b = [se+sb for se, sb in zip(sigma_e_pts, sigma_b_pts)]
        ax.fill_betweenx(z_pts, sigma_e_pts, tot_b,
                         alpha=0.30, color=_C_BOU,
                         label="Boussinesq (beban terpusat P1)" if lang=="ID"
                               else "Boussinesq (point load P1)")
        ax.plot(tot_b, z_pts, color=_C_BOU, lw=2.5, ls="--")
        # Mark peak Boussinesq
        peak_i = sigma_b_pts.index(max(sigma_b_pts))
        ax.plot(tot_b[peak_i], z_pts[peak_i], "o", color=_C_BOU, ms=8, zorder=5)
        ax.annotate(f"Puncak σh = {tot_b[peak_i]:.2f} kPa\n@ z = {z_pts[peak_i]:.2f} m",
                    xy=(tot_b[peak_i], z_pts[peak_i]),
                    xytext=(tot_b[peak_i]+1.5, z_pts[peak_i]-0.1*H),
                    fontsize=8.5, color=_C_BOU, fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color=_C_BOU, lw=0.9))

    # ── Garis resultante ──────────────────────────────────────────────────────
    ax.axhline(y_e, color=_C_EARTH, lw=1, ls=":", alpha=0.7)
    ax.text(0.3, y_e-0.02*H,
            f"F_tanah={F_e:.2f}kN/m @ y={y_e:.2f}m",
            fontsize=8, color=_C_EARTH)
    if method in (0,1) and F_s > 0:
        ax.axhline(y_s, color=_C_SUR if method==0 else _C_BOU, lw=1, ls=":", alpha=0.7)
        lbl_c = _C_SUR if method==0 else _C_BOU
        lbl_t = "F_sur" if method==0 else "F_Bou"
        ax.text(0.3, y_s+0.02*H,
                f"{lbl_t}={F_s:.2f}kN/m @ y={y_s:.2f}m",
                fontsize=8, color=lbl_c)

    ax.invert_yaxis()
    ax.set_xlabel("σh (kPa)", fontsize=10)
    ax.set_ylabel("Kedalaman z dari puncak dinding (m)" if lang=="ID"
                  else "Depth from wall top (m)", fontsize=10)
    ax.set_title(
        "Distribusi Tekanan Lateral pada Dinding UD\n"
        "(Ungu=Tanah/segitiga  Oranye=Surcharge/kotak  Merah=Boussinesq/parabola)"
        if lang=="ID" else
        "Lateral Pressure Distribution on UD Wall\n"
        "(Purple=Earth/triangle  Orange=Surcharge/rectangle  Red=Boussinesq/curve)",
        fontsize=10, pad=8)
    ax.legend(fontsize=9, loc="lower right")
    ax.set_xlim(left=0)
    ax.grid(color="#ECEFF1", lw=0.6)
    ax.tick_params(labelsize=8)
    fig.tight_layout()
    return fig


# =============================================================================
# BAGIAN 5 — DIAGRAM Mu, Vu, Nu SEPANJANG DINDING (matplotlib)
# =============================================================================

def _fig_gaya_dalam(z_fb, V_arr, M_arr, Nu_arr,
                    V_prop, M_prop,
                    wb_Mu, wb_Vu, wb_Nu,
                    H, gap_closed, lang) -> plt.Figure:
    """
    z_fb : array posisi dari BASE (0=dasar, H=puncak)
    Semua dari integrasi numerik distribusi tekanan.
    """
    fig, axes = plt.subplots(1, 3, figsize=(13, 5.5),
                             facecolor="#F8F9FA", sharey=True)

    def _setup(ax, title, xlabel, col):
        ax.set_facecolor("#F8F9FA")
        ax.set_title(title, fontsize=10, color=_C_DIM, pad=5)
        ax.set_xlabel(xlabel, fontsize=9, color=col)
        ax.axvline(0, color=_C_DIM, lw=1.5)
        ax.axhline(0, color=_C_DIM, lw=0.7, ls=":")   # dasar
        ax.axhline(H, color=_C_DIM, lw=0.7, ls=":")   # puncak
        ax.grid(color="#ECEFF1", lw=0.5)
        ax.tick_params(labelsize=7)
        ax.text(-0.01, 0,  "Dasar" if lang=="ID" else "Base",
                fontsize=7, color=_C_DIM, ha="right", va="bottom")
        ax.text(-0.01, H, "Puncak" if lang=="ID" else "Top",
                fontsize=7, color=_C_DIM, ha="right", va="top")

    # ── Vu ────────────────────────────────────────────────────────────────────
    ax0 = axes[0]
    ax0.fill_betweenx(z_fb, 0, V_arr, alpha=0.25, color=_C_VU)
    ax0.plot(V_arr, z_fb, color=_C_VU, lw=2.5,
             label="Kantilever" if lang=="ID" else "Cantilever")
    if V_prop is not None:
        ax0.plot(V_prop, z_fb, color=_C_VU, lw=2, ls="--",
                 label="Propped (CU aktif)")
        ax0.fill_betweenx(z_fb, 0, V_prop, alpha=0.12, color=_C_VU)
    # Annotate at base
    ax0.annotate(f"Vu = {wb_Vu:.3f}\nkN/m",
                 xy=(V_arr[0], 0),
                 xytext=(V_arr[0]*0.45+1, H*0.12),
                 fontsize=8.5, color=_C_VU, fontweight="bold",
                 arrowprops=dict(arrowstyle="->", color=_C_VU, lw=0.9))
    ax0.legend(fontsize=8)
    _setup(ax0, "Diagram Geser Vu" if lang=="ID" else "Shear Vu",
           "Vu (kN/m)", _C_VU)

    # ── Mu ────────────────────────────────────────────────────────────────────
    ax1 = axes[1]
    ax1.fill_betweenx(z_fb, 0, M_arr, alpha=0.25, color=_C_MU)
    ax1.plot(M_arr, z_fb, color=_C_MU, lw=2.5,
             label="Kantilever" if lang=="ID" else "Cantilever")
    if M_prop is not None:
        ax1.plot(M_prop, z_fb, color=_C_MU, lw=2, ls="--",
                 label="Propped (CU aktif)")
        ax1.fill_betweenx(z_fb, 0, M_prop, alpha=0.12, color=_C_MU)
        # Mark max propped moment
        Mmax_p = max(M_prop, key=abs)
        zi_max = z_fb[M_prop.index(Mmax_p)]
        ax1.plot(Mmax_p, zi_max, "o", color=_C_MU, ms=7, zorder=5)
        ax1.annotate(f"Mu,max={Mmax_p:.3f}",
                     xy=(Mmax_p, zi_max),
                     xytext=(Mmax_p*0.5+0.1, zi_max+H*0.1),
                     fontsize=8, color=_C_MU)
    ax1.annotate(f"Mu = {wb_Mu:.3f}\nkN·m/m",
                 xy=(M_arr[0], 0),
                 xytext=(M_arr[0]*0.4+0.05, H*0.12),
                 fontsize=8.5, color=_C_MU, fontweight="bold",
                 arrowprops=dict(arrowstyle="->", color=_C_MU, lw=0.9))
    ax1.legend(fontsize=8)
    _setup(ax1, "Diagram Momen Mu" if lang=="ID" else "Moment Mu",
           "Mu (kN·m/m)", _C_MU)

    # ── Nu ────────────────────────────────────────────────────────────────────
    ax2 = axes[2]
    ax2.fill_betweenx(z_fb, 0, Nu_arr, alpha=0.25, color=_C_NU)
    ax2.plot(Nu_arr, z_fb, color=_C_NU, lw=2.5)
    ax2.annotate(f"Nu = {wb_Nu:.3f}\nkN/m",
                 xy=(Nu_arr[0], 0),
                 xytext=(Nu_arr[0]*0.4+0.05, H*0.12),
                 fontsize=8.5, color=_C_NU, fontweight="bold",
                 arrowprops=dict(arrowstyle="->", color=_C_NU, lw=0.9))
    _setup(ax2, "Diagram Aksial Nu\n(tekan +)" if lang=="ID" else "Axial Nu\n(compression +)",
           "Nu (kN/m)", _C_NU)

    title_cond = ("Gaya Dalam Dinding UD" if lang=="ID" else "UD Wall Internal Forces")
    gap_note = ""
    if gap_closed:
        gap_note = " — CU Aktif (Propped)" if lang=="ID" else " — CU Active (Propped)"
    fig.suptitle(title_cond + gap_note, fontsize=11, color=_C_DIM, y=1.01)
    fig.tight_layout()
    return fig


# =============================================================================
# FUNGSI UTAMA
# =============================================================================

def render_perhitungan(fr, dr, inp: dict, lang: str) -> None:
    """
    Render SELURUH RANTAI PERHITUNGAN dari data input → gaya dalam → kapasitas.
    Dipanggil dari tab Perhitungan di 11_UDitch_CU.py.
    """
    from uditch.calc_engine import _compat, _rankine_Ka, _aashto_heq, _boussinesq_point_lateral

    # ── Ambil data yang sudah dikonversi ──────────────────────────────────────
    inp_c  = _compat(inp)
    lat    = fr.lateral
    wb     = fr.wall_base
    cond   = fr.condition

    # Geometri (semua dalam m)
    H      = _mm(inp_c.get("ud_inner_height", 600))
    ta     = _mm(inp_c.get("ud_wall_thickness", 80))     # ta = top wall thickness
    tb     = _mm(inp_c.get("ud_wall_thick_bot", 100))
    ts     = _mm(inp_c.get("ud_base_thickness", 120))
    Wo     = _mm(inp_c.get("ud_inner_width", 600))
    L_seg  = inp_c.get("ud_length", 1.2)
    gap_mm = inp_c.get("gap_cu_ud", 20.0)

    # Material
    fc     = inp_c.get("fc_prime", 30.0)
    gam_c  = inp_c.get("gamma_c", 24.0)

    # Tanah
    gs     = inp_c.get("gamma_s", 18.0)
    phi    = inp_c.get("phi_soil", 30.0)
    c_s    = inp_c.get("cohesion", 0.0)

    # Timbunan samping
    Hf     = inp_c.get("soil_fill_beside", 0.0)
    fill_t = inp_c.get("fill_type_idx", 0)

    # Kendaraan
    G      = inp_c.get("axle_load_G", 225.0)
    P1     = G / 2.0
    x1     = inp_c.get("wheel_dist", 0.25)
    method = inp_c.get("lat_method_idx", 0)

    # Faktor
    gDL    = inp_c.get("gamma_DL", 1.2)
    gLL    = inp_c.get("gamma_LL", 1.6)

    # Guard
    if lat is None or wb is None:
        st.error("Data perhitungan tidak lengkap. Jalankan ulang.")
        return

    Ka = lat.Ka
    # Surcharge dari timbunan samping
    gam_fill = [gs, 22.0, 24.0][fill_t]
    q_beside = gam_fill * Hf

    # ── Titik kedalaman (dari puncak ke dasar) ────────────────────────────────
    N_PTS  = 60
    z_top  = [i * H / N_PTS for i in range(N_PTS + 1)]   # 0=top, H=base

    def sigma_earth(z):
        return max(Ka * gs * z - 2 * c_s * math.sqrt(Ka), 0.0)

    sig_e_arr = [sigma_earth(z) for z in z_top]

    # Surcharge
    if method == 0:
        heq      = _aashto_heq(H)
        sig_sur  = Ka * gs * heq + Ka * q_beside
        sig_s_arr = [sig_sur] * len(z_top)
        sig_b_arr = None
    else:
        heq = None
        sig_s_arr = None
        sig_b_arr = [
            _boussinesq_point_lateral(P1, max(x1, 0.05), max(z, 0.001), L_seg) / L_seg
            for z in z_top
        ]

    # ═══════════════════════════════════════════════════════════════════════════
    # BAGIAN 1 — DATA & GEOMETRI
    # ═══════════════════════════════════════════════════════════════════════════
    _header("📐 BAGIAN 1 — Data & Geometri Input")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**U-Ditch (UD)**")
        st.markdown(
            f"Wo = **{int(Wo*1000)} mm**  \n"
            f"Ho = **{int(H*1000)} mm**  \n"
            f"ta (atas) = **{int(ta*1000)} mm**  \n"
            f"tb (bawah) = **{int(tb*1000)} mm**  \n"
            f"ts (slab) = **{int(ts*1000)} mm**  \n"
            f"L_seg = **{L_seg} m**  \n"
            f"Gap CU-UD = **{gap_mm} mm**"
        )
    with col2:
        st.markdown("**Tanah & Material**")
        st.markdown(
            f"γs = **{gs} kN/m³**  \n"
            f"φ  = **{phi}°**  \n"
            f"c  = **{c_s} kPa**  \n"
            f"γc = **{gam_c} kN/m³**  \n"
            f"f'c = **{fc} MPa**  \n"
            f"Timbunan samping Hf = **{Hf} m**"
        )
    with col3:
        st.markdown("**Kendaraan & Faktor**")
        st.markdown(
            f"G (gandar) = **{G:.0f} kN**  \n"
            f"P1 = G/2 = **{P1:.1f} kN**  \n"
            f"x1 (jarak roda ke UD) = **{x1} m**  \n"
            f"Metode lateral: **{'Surcharge' if method==0 else 'Boussinesq'}**  \n"
            f"γDL = **{gDL}** | γLL = **{gLL}**"
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # BAGIAN 2 — TEKANAN LATERAL PER KEDALAMAN
    # ═══════════════════════════════════════════════════════════════════════════
    _header("🌍 BAGIAN 2 — Tekanan Lateral per Kedalaman")

    # ── 2a. Koefisien Ka ─────────────────────────────────────────────────────
    st.markdown("**2a. Koefisien Tekanan Tanah Aktif (Rankine)**")
    _step("Ka",
          r"K_a = \tan^2\!\left(45° - \dfrac{\phi}{2}\right)",
          f"tan²(45° − {phi}/2) = tan²({45-phi/2:.1f}°)",
          Ka, "—",
          "Rankine (1857); SNI 8460:2017 §C.6.4")

    st.divider()

    # ── 2b. Tekanan tanah (segitiga) ─────────────────────────────────────────
    st.markdown(
        "**2b. Tekanan Tanah Aktif — Distribusi Segitiga**  \n"
        "σh(z) = Ka × γs × z − 2c√Ka  ≥ 0  "
        "*(z = kedalaman dari puncak dinding)*"
    )
    _step("σh (z=0)",
          r"\sigma_h = K_a \cdot \gamma_s \cdot z - 2c\sqrt{K_a}",
          f"{Ka:.3f} × {gs} × 0 − 2×{c_s}×√{Ka:.3f}",
          0.0, "kPa", "SNI 8460:2017 §6.4.1")
    _step(f"σh (z={H/2:.2f}m)",
          r"\sigma_h = K_a \cdot \gamma_s \cdot z - 2c\sqrt{K_a}",
          f"{Ka:.3f} × {gs} × {H/2:.3f} − 2×{c_s}×√{Ka:.3f}",
          sigma_earth(H/2), "kPa", "SNI 8460:2017 §6.4.1")
    _step(f"σh (z={H:.2f}m — DASAR)",
          r"\sigma_h = K_a \cdot \gamma_s \cdot z - 2c\sqrt{K_a}",
          f"{Ka:.3f} × {gs} × {H:.3f} − 2×{c_s}×√{Ka:.3f}",
          sigma_earth(H), "kPa", "SNI 8460:2017 §6.4.1")

    # Tabel lengkap per 0.1m (collapsible)
    with st.expander("📋 Tabel σh tanah per kedalaman (klik untuk buka)"):
        _tbl_header(["z (m)", "σh tanah (kPa)"])
        step_z = max(H / 10, 0.05)
        z_show = 0.0
        while z_show <= H + 0.001:
            highlight = abs(z_show - H) < 0.001
            _tbl_row([f"{z_show:.2f}", f"{sigma_earth(z_show):.2f}"], highlight)
            z_show += step_z
        _tbl_close()

    st.divider()

    # ── 2c. Surcharge atau Boussinesq ────────────────────────────────────────
    if method == 0:
        # ── Surcharge (kotak) ─────────────────────────────────────────────────
        st.markdown(
            "**2c. Tekanan Lateral Kendaraan — Distribusi Kotak (Surcharge Ekivalen)**  \n"
            "AASHTO Table 3.11.6.4-2: roda dikonversi ke tinggi tanah ekivalen heq."
        )
        _step("heq",
              r"h_{eq} = f(H_{wall}) \text{ — AASHTO Table 3.11.6.4-2}",
              f"H_wall = {H:.2f} m → interpolasi tabel",
              heq, "m", "AASHTO LRFD 9th Ed. Table 3.11.6.4-2")
        _step("σ_kend (uniform, sepanjang H)",
              r"\sigma_{kend} = K_a \cdot \gamma_s \cdot h_{eq} + K_a \cdot q_{timbunan}",
              f"{Ka:.3f}×{gs}×{heq:.2f} + {Ka:.3f}×{q_beside:.2f}",
              Ka*gs*heq + Ka*q_beside, "kPa (konstan di seluruh kedalaman)",
              "AASHTO LRFD §3.11.6.4")
        st.info(
            "**Surcharge = tekanan kotak/rectangular:** nilai konstan dari puncak ke dasar. "
            "Ini menyederhanakan distribusi roda menjadi beban merata ekivalen."
        )
    else:
        # ── Boussinesq (parabola) ─────────────────────────────────────────────
        st.markdown(
            "**2c. Tekanan Lateral Kendaraan — Boussinesq 3D (Parabola/Melengkung)**  \n"
            "Beban roda P1 sebagai beban terpusat 3D, diintegrasikan sepanjang L segmen.  \n"
            "Formula: σh(z) = 3·P1·x1²·z³ / (2π·R⁵·L)  dimana R = √(x1²+z²)"
        )
        _step("P1 = G/2",
              r"P_1 = \frac{G}{2}",
              f"{G:.0f}/2",
              P1, "kN", "SNI 1725:2016 — beban gandar G")
        _step("x1 (jarak roda ke muka dinding)",
              r"x_1 \text{ — input pengguna}",
              f"{x1} m",
              x1, "m", "—")

        # Tabel σh Boussinesq per kedalaman
        with st.expander("📋 Tabel σh Boussinesq per kedalaman (klik untuk buka)"):
            _tbl_header(["z (m)", "R = √(x1²+z²) (m)", "σh Boussinesq (kPa)"])
            step_z = max(H / 10, 0.05)
            z_show = step_z
            while z_show <= H + 0.001:
                R = math.sqrt(x1**2 + z_show**2)
                sb = _boussinesq_point_lateral(P1, max(x1, 0.05), z_show, L_seg) / L_seg
                highlight = abs(sb - max(sig_b_arr)) < 0.01 if sig_b_arr else False
                _tbl_row([f"{z_show:.2f}", f"{R:.3f}", f"{sb:.3f}"], highlight)
                z_show += step_z
            _tbl_close()
        st.info(
            "**Boussinesq = tekanan parabola/melengkung:** nilainya kecil di puncak (z≈0), "
            "mencapai puncak sekitar z ≈ x1/√2, lalu mengecil lagi ke dasar. "
            f"Untuk x1={x1}m, puncak σh terjadi di z ≈ {x1/math.sqrt(2):.2f} m."
        )

    # ── GAMBAR DISTRIBUSI TEKANAN ─────────────────────────────────────────────
    st.markdown("**📊 Diagram Distribusi Tekanan Lateral**")
    fig_dist = _fig_distribusi(sig_e_arr, sig_s_arr, sig_b_arr, z_top,
                               H, method, lat.F_earth, lat.F_surcharge,
                               lat.arm_earth, lat.arm_surcharge, lang)
    st.pyplot(fig_dist, use_container_width=True)
    plt.close(fig_dist)

    # ═══════════════════════════════════════════════════════════════════════════
    # BAGIAN 3 — RESULTAN GAYA & LENGAN MOMEN
    # ═══════════════════════════════════════════════════════════════════════════
    _header("⚖️ BAGIAN 3 — Resultan Gaya & Lengan Momen")

    st.markdown(
        "Resultan = luas area tekanan. Lengan momen = titik tangkap resultan dari dasar."
    )

    _step("F_tanah (resultante tekanan tanah)",
          r"F_{tanah} = \tfrac{1}{2}(\sigma_{top} + \sigma_{base}) \cdot H",
          f"½×({sig_e_arr[0]:.2f}+{sig_e_arr[-1]:.2f})×{H:.3f}",
          lat.F_earth, "kN/m",
          "AASHTO LRFD §3.11.5.1")
    _step("y_tanah (lengan dari dasar)",
          r"y_{tanah} = \dfrac{H}{3} \cdot \dfrac{\sigma_{base}+2\sigma_{top}}{\sigma_{base}+\sigma_{top}}",
          f"({H:.3f}/3)×({sig_e_arr[-1]:.2f}+2×{sig_e_arr[0]:.2f})/({sig_e_arr[-1]:.2f}+{sig_e_arr[0]:.2f})"
          if (sig_e_arr[-1]+sig_e_arr[0]) > 0 else f"{H:.3f}/3",
          lat.arm_earth, "m dari dasar",
          "Statics — centroid segitiga/trapesium")

    if method == 0:
        sig_s_val = sig_s_arr[0] if sig_s_arr else 0.0
        _step("F_kendaraan (surcharge, kotak)",
              r"F_{sur} = \sigma_{sur} \cdot H",
              f"{sig_s_val:.3f} × {H:.3f}",
              lat.F_surcharge, "kN/m",
              "AASHTO LRFD §3.11.6.4")
        _step("y_kendaraan (surcharge, tengah tinggi)",
              r"y_{sur} = H/2 \text{ (distribusi uniform)}",
              f"{H:.3f}/2",
              lat.arm_surcharge, "m dari dasar",
              "Statics — centroid persegi panjang")
    else:
        _step("F_Boussinesq (integrasi numerik)",
              r"F_{Bou} = \int_0^H \sigma_h(z)\,dz \; \text{(numerik)}",
              f"P1={P1:.0f}kN, x1={x1:.2f}m, H={H:.2f}m, L={L_seg}m",
              lat.F_surcharge, "kN/m",
              "Boussinesq; integrasi numerik (N=60 titik)")
        _step("y_Boussinesq (dari integrasi momen)",
              r"y_{Bou} = \dfrac{\int_0^H \sigma_h(z)\cdot z\,dz}{F_{Bou}}",
              "integrasi numerik",
              lat.arm_surcharge, "m dari dasar",
              "Numerik")

    # ═══════════════════════════════════════════════════════════════════════════
    # BAGIAN 4 — GAYA DALAM: Mu, Vu, Nu
    # ═══════════════════════════════════════════════════════════════════════════
    _header("⚡ BAGIAN 4 — Gaya Dalam: Mu, Vu, Nu")

    # ── Nu (aksial) ──────────────────────────────────────────────────────────
    st.markdown("**4a. Gaya Aksial Nu — Berat Sendiri Dinding UD**")
    W_wall = gam_c * H * ta
    _step("Berat dinding per meter (service)",
          r"W_{wall} = \gamma_c \cdot H \cdot t_a",
          f"{gam_c} × {H:.3f} × {ta:.3f}",
          W_wall, "kN/m",
          "SNI 1727:2020 §3.1")
    _step("Nu (terfaktor, di dasar)",
          r"N_u = \gamma_{DL} \cdot W_{wall}",
          f"{gDL} × {W_wall:.4f}",
          wb.Nu, "kN/m",
          "SNI 2847:2019 Ps.5.3.1")

    st.divider()

    # ── Mu & Vu kantilever ────────────────────────────────────────────────────
    st.markdown("**4b. Momen & Geser — Dinding sebagai Kantilever**")
    st.caption(
        "Momen di dasar = Σ(Gaya × Lengan).  "
        "Geser di dasar = Σ semua gaya lateral."
    )
    Mu_e_serv = lat.F_earth   * lat.arm_earth
    Mu_s_serv = lat.F_surcharge * lat.arm_surcharge

    _step("M_tanah (unfactored)",
          r"M_{tanah} = F_{tanah} \cdot y_{tanah}",
          f"{lat.F_earth:.4f} × {lat.arm_earth:.4f}",
          Mu_e_serv, "kN·m/m",
          "Statics — kantilever")
    _step("M_kendaraan (unfactored)",
          r"M_{kend} = F_{kend} \cdot y_{kend}",
          f"{lat.F_surcharge:.4f} × {lat.arm_surcharge:.4f}",
          Mu_s_serv, "kN·m/m",
          "Statics — kantilever")
    _step("Mu (terfaktor) — Momen Lentur di Dasar Dinding",
          r"M_u = \gamma_{DL} \cdot M_{tanah} + \gamma_{LL} \cdot M_{kend}",
          f"{gDL} × {Mu_e_serv:.4f} + {gLL} × {Mu_s_serv:.4f}",
          wb.Mu, "kN·m/m",
          "SNI 2847:2019 Ps.5.3.1  (U = 1.2D + 1.6L)")
    _step("Vu (terfaktor) — Geser di Dasar Dinding",
          r"V_u = \gamma_{DL} \cdot F_{tanah} + \gamma_{LL} \cdot F_{kend}",
          f"{gDL} × {lat.F_earth:.4f} + {gLL} × {lat.F_surcharge:.4f}",
          wb.Vu, "kN/m",
          "SNI 2847:2019 Ps.5.3.1")

    # ── Gap check (Kondisi 1) ────────────────────────────────────────────────
    if cond == "Kondisi 1":
        st.divider()
        st.markdown("**4c. Cek Gap — Dinding Murni Kantilever atau Propped oleh CU?**")
        Ec    = 4700 * math.sqrt(fc) * 1e3      # kN/m²
        I_w   = ta**3 / 12                       # m⁴/m
        EI    = Ec * I_w
        w_base_e = max(Ka*gs*H - 2*c_s*math.sqrt(Ka), 0.0)
        w_sur_eq = lat.F_surcharge / H if H > 0 else 0.0
        d_e   = w_base_e * H**4 / (30 * EI)
        d_s   = w_sur_eq  * H**4 / (8 * EI)
        d_tot = (d_e + d_s) * 1000  # mm

        _step("Ec (modulus elastisitas beton)",
              r"E_c = 4700\sqrt{f'_c}",
              f"4700×√{fc}",
              Ec/1e3, "MPa",
              "SNI 2847:2019 Ps.19.2.2.1")
        _step("I dinding (per m lebar)",
              r"I = t_a^3 / 12",
              f"{ta:.4f}³ / 12",
              I_w, "m⁴/m",
              "Statics")
        _step("EI (kekakuan lentur)",
              r"EI = E_c \cdot I",
              f"{Ec:.1f} × {I_w:.6f}",
              EI, "kN·m²/m",
              "—")
        _step("δ dari tekanan tanah (beban segitiga)",
              r"\delta_{tanah} = \dfrac{w_{base}\cdot H^4}{30\cdot EI}",
              f"{w_base_e:.3f}×{H:.3f}⁴ / (30×{EI:.1f})",
              d_e*1000, "mm",
              "Timoshenko — kantilever beban segitiga")
        _step("δ dari surcharge/Boussinesq (beban ekivalen uniform)",
              r"\delta_{kend} = \dfrac{w_{eq}\cdot H^4}{8\cdot EI}",
              f"{w_sur_eq:.3f}×{H:.3f}⁴ / (8×{EI:.1f})",
              d_s*1000, "mm",
              "Timoshenko — kantilever beban merata")
        _step("δ_total",
              r"\delta_{total} = \delta_{tanah} + \delta_{kend}",
              f"{d_e*1000:.3f} + {d_s*1000:.3f}",
              d_tot, "mm",
              "Superposisi / Superposition")

        if fr.gap_closed:
            st.success(
                f"✅ **δ = {d_tot:.3f} mm ≥ gap = {gap_mm} mm → CU aktif sebagai strut!**  \n"
                "Momen di dasar BERKURANG — dinding berubah menjadi batang tumpuan atas-bawah.  \n"
                "Momen yang digunakan untuk desain tulangan LUAR adalah dari kondisi **propped**."
            )
        else:
            st.info(
                f"ℹ️ **δ = {d_tot:.3f} mm < gap = {gap_mm} mm → Kantilever murni**  \n"
                "CU belum aktif. Dinding bekerja sebagai kantilever penuh.  \n"
                "Tulangan LUAR (tarik) didesain dari Mu kantilever ini."
            )

    # ── Ringkasan gaya dalam ─────────────────────────────────────────────────
    st.markdown(
        f'<div style="background:#1A237E;color:white;padding:10px 16px;'
        f'border-radius:6px;margin:12px 0;">'
        f'<b>📋 Ringkasan Gaya Dalam di Dasar Dinding UD</b></div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Mu (kN·m/m)", f"{wb.Mu:.3f}",
              help="Momen lentur terfaktor di dasar dinding")
    c2.metric("Vu (kN/m)", f"{wb.Vu:.3f}",
              help="Gaya geser terfaktor di dasar dinding")
    c3.metric("Nu (kN/m)", f"{wb.Nu:.3f}",
              help="Gaya aksial tekan terfaktor (berat dinding)")

    # ═══════════════════════════════════════════════════════════════════════════
    # BAGIAN 5 — DIAGRAM GAYA DALAM SEPANJANG DINDING
    # ═══════════════════════════════════════════════════════════════════════════
    _header("📊 BAGIAN 5 — Diagram Gaya Dalam Sepanjang Tinggi Dinding")

    st.caption(
        "Diagram dihitung dari integrasi distribusi tekanan lateral "
        f"(bukan hanya nilai di dasar). "
        f"{'Kantilever murni' if not fr.gap_closed else 'Propped cantilever (CU aktif)'}."
    )

    # Build arrays (z from BASE = 0)
    z_fb   = [i * H / N_PTS for i in range(N_PTS + 1)]

    def p_fact(z_from_base):
        depth = H - z_from_base
        p_e = max(Ka*gs*depth - 2*c_s*math.sqrt(Ka), 0.0)
        if method == 0:
            p_s = Ka*gs*(heq or 0.0) + Ka*q_beside
        else:
            p_s = (_boussinesq_point_lateral(P1, max(x1,0.05),
                                             max(depth, 0.001), L_seg) / L_seg
                   if depth > 0 else 0.0)
        return gDL * p_e + gLL * p_s

    def V_at(z):
        dz = (H - z) / 40
        return sum(p_fact(z + (j+0.5)*dz) * dz for j in range(40))

    def M_at(z):
        dz = (H - z) / 40
        return sum(p_fact(z + (j+0.5)*dz) * ((j+0.5)*dz) * dz
                   for j in range(40))

    V_arr = [V_at(zi) for zi in z_fb]
    M_arr = [M_at(zi) for zi in z_fb]
    Nu_arr = [gDL * gam_c * ta * (H - zi) for zi in z_fb]

    V_prop, M_prop = None, None
    if fr.gap_closed and fr.wall_top is not None:
        H_strut = fr.wall_top.Vu
        V_prop  = [V_at(zi) - H_strut for zi in z_fb]
        M_prop  = [M_at(zi) - H_strut*(H-zi) for zi in z_fb]

    fig_gd = _fig_gaya_dalam(z_fb, V_arr, M_arr, Nu_arr,
                              V_prop, M_prop,
                              wb.Mu, wb.Vu, wb.Nu,
                              H, fr.gap_closed, lang)
    st.pyplot(fig_gd, use_container_width=True)
    plt.close(fig_gd)

    # ═══════════════════════════════════════════════════════════════════════════
    # BAGIAN 6 — KAPASITAS PENAMPANG & KONTROL
    # ═══════════════════════════════════════════════════════════════════════════
    _header("🔩 BAGIAN 6 — Kapasitas Penampang & Kontrol")

    cap = dr.wall_base_cap if dr else None
    if cap is None:
        st.warning("Kapasitas penampang belum dihitung.")
        return

    phi_f = inp_c.get("phi_flex", 0.90)
    phi_s = inp_c.get("phi_shear_factor", inp_c.get("phi_shear_f", 0.75))

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Lentur / Flexure**")
        _step("As,req (dari Mu)",
              r"A_{s,req} \text{ dari: } \phi A_s f_y (d - a/2) = M_u",
              f"φ={phi_f}, Mu={wb.Mu:.3f}kN·m/m",
              cap.As_req_mm2, "mm²/m",
              "SNI 2847:2019 Ps.22.3.2")
        _step("As,min",
              r"A_{s,min} = 0.0012 \cdot b \cdot h",
              f"0.0012 × 1000 × {int(ta*1000)}",
              cap.As_min_mm2, "mm²/m",
              "SNI 2847:2019 Ps.11.6.1")
        st.markdown(f"As,terpasang = **{cap.As_prov_mm2:.0f} mm²/m**")
        _step("φMn",
              r"\phi M_n = \phi \cdot A_s \cdot f_y \cdot (d - a/2)",
              f"φ={phi_f}",
              cap.phi_Mn_kNm, "kN·m/m",
              "SNI 2847:2019 Ps.22.3.2",
              ok=cap.flexure_ok)
        if cap.flexure_ok:
            st.success(f"✅ φMn = {cap.phi_Mn_kNm:.3f} ≥ Mu = {wb.Mu:.3f} kN·m/m")
        else:
            st.error(f"❌ φMn = {cap.phi_Mn_kNm:.3f} < Mu = {wb.Mu:.3f} kN·m/m — perlu penambahan tulangan!")

    with col_b:
        st.markdown("**Geser / Shear**")
        _step("φVc (kapasitas geser beton)",
              r"\phi V_c = \phi \left(0.17\lambda\sqrt{f'_c} + \frac{N_u}{6A_g}\right)b\,d",
              f"φ={phi_s}",
              cap.phi_Vc_kNm, "kN/m",
              "SNI 2847:2019 Tabel 22.5.5.1 Pers.(a)")
        if cap.stirrup_needed:
            _step("Vs,req",
                  r"V_s = V_u/\phi - V_c",
                  f"{wb.Vu:.3f}/{phi_s} − {cap.phi_Vc_kNm/phi_s:.3f}",
                  cap.Vs_req_kNm, "kN/m",
                  "SNI 2847:2019 Ps.22.5.1.1")
            st.warning(f"⚠️ Perlu sengkang: Av,req = {cap.Av_req_mm2:.0f} mm²/m")
        else:
            st.success(f"✅ φVc = {cap.phi_Vc_kNm:.3f} ≥ Vu = {wb.Vu:.3f} kN/m → beton cukup!")
        _step("φVn (total, dengan sengkang)",
              r"\phi V_n = \phi(V_c + V_s)",
              f"φ={phi_s}",
              cap.phi_Vn_kNm, "kN/m",
              "SNI 2847:2019 Ps.22.5.1.1",
              ok=cap.shear_ok)

    # ── P-M Kondisi 2 ────────────────────────────────────────────────────────
    if cond == "Kondisi 2" and dr and dr.pm_curve:
        st.divider()
        _header("📈 BAGIAN 7 — Diagram Interaksi P-M (Dinding sebagai Kolom)")

        pm = dr.pm_curve

        # ── Penjelasan arah momen & tulangan ─────────────────────────────────
        st.info(
            "**Dasar teori P-M kurva ini:**  \n"
            "Dinding UD bekerja sebagai kolom (menerima N + M). "
            "Diagram P-M dibangun dengan **kompatibilitas regangan** — "
            "sumbu netral c disapu dari 0 sampai h (tebal dinding), "
            "menghasilkan pasangan (Pn, Mn) untuk setiap posisi c.  \n\n"
            "**Tulangan yang digunakan:**  \n"
            "• Kurva ini menggunakan **As_tarik (muka luar)** sebagai tulangan tarik "
            "dan **As_tekan (muka dalam)** sebagai tulangan tekan — "
            "sesuai kondisi kantilever murni (momen tarik di muka luar).  \n"
            "• Jika CU aktif (gap closed) dan momen berbalik di bagian atas dinding, "
            "**tulangan dalam menjadi tarik** → kurva P-M zona atas berbeda "
            "(As_dalam sebagai tarik, As_luar sebagai tekan). "
            "Kondisi ini perlu dicek terpisah dengan menukar posisi tulangan."
            if lang == "ID" else
            "**P-M curve basis:**  \n"
            "UD wall acts as a column (N + M). P-M diagram built by strain compatibility — "
            "neutral axis c swept from 0 to h, giving (Pn, Mn) pairs.  \n\n"
            "**Reinforcement used:**  \n"
            "• This curve uses **As_tension (outer face)** as tension steel and "
            "**As_comp (inner face)** as compression — matching cantilever condition.  \n"
            "• If CU is active (gap closed), moment reverses near wall top → "
            "**inner steel becomes tension**. That zone needs a separate P-M check "
            "with swapped steel positions."
        )

        # ── Metrik titik kontrol ──────────────────────────────────────────────
        st.markdown("**Titik kontrol kurva P-M:**")
        ci, cm, cn, co = st.columns(4)
        ci.metric("Pn,max (kN/m)", f"{pm.Pn_max:.1f}",
                  help="Tekan murni — seluruh penampang tekan")
        cm.metric("Pb (kN/m)",     f"{pm.Pb:.1f}",
                  help="Balanced — εt = εy pada tulangan tarik")
        cn.metric("Mb (kN·m/m)",   f"{pm.Mb:.2f}",
                  help="Momen pada kondisi balanced")
        co.metric("Mn,pure (kN·m/m)", f"{pm.Mn_pure:.2f}",
                  help="Lentur murni — Pn = 0")

        # ── Gambar diagram P-M (matplotlib — tidak butuh plotly) ──────────────
        from uditch.laporan import _fig_pm_curve_laporan
        fig_pm_st = _fig_pm_curve_laporan(pm)
        st.pyplot(fig_pm_st, use_container_width=True)
        plt.close(fig_pm_st)

        # ── Cek demand ────────────────────────────────────────────────────────
        st.markdown("**Kontrol titik beban terhadap kurva P-M:**")
        _step("Cek P-M",
              r"(M_u,\, N_u) \in \phi\text{P-M curve}?",
              f"Nu={pm.Nu_demand:.3f}kN/m, Mu={pm.Mu_demand:.3f}kN·m/m",
              1.0 if pm.inside_curve else 0.0, "—",
              "SNI 2847:2019 Ps.22.4; Diagram interaksi kolom",
              ok=pm.inside_curve)
        if pm.inside_curve:
            st.success(
                f"✅ **AMAN** — Titik beban (Nu={pm.Nu_demand:.2f}kN/m, "
                f"Mu={pm.Mu_demand:.2f}kN·m/m) berada DALAM kurva φP-M"
            )
        else:
            st.error(
                f"❌ **TIDAK AMAN** — Titik beban (Nu={pm.Nu_demand:.2f}kN/m, "
                f"Mu={pm.Mu_demand:.2f}kN·m/m) berada DI LUAR kurva φP-M"
            )

        # ── Info: jika gap closed, perlu cek kurva terbalik ───────────────────
        if fr.gap_closed:
            st.warning(
                f"⚠️ **Perhatian — CU Aktif (δ ≥ gap):**  \n"
                "Momen di bagian atas dinding berbalik arah (tarik di muka DALAM).  \n"
                "Kurva P-M di atas untuk **dasar dinding** (tarik muka luar). "
                "Untuk zona atas, cek kapasitas dengan As_dalam sebagai tulangan tarik."
                if lang == "ID" else
                f"⚠️ **Note — CU Active (δ ≥ gap):**  \n"
                "Moment near wall top reverses (tension on INNER face).  \n"
                "The P-M curve above is for the **wall base** (tension outer face). "
                "For the top zone, check capacity with As_inner as tension steel."
            )

        # ── Kurva P-M kedua: momen berbalik (jika tersedia) ─────────────────
        pm_rev = getattr(dr, "pm_curve_reversed", None)
        if pm_rev is not None:
            st.divider()
            st.markdown(
                "**📈 Kurva P-M Kedua — Momen Berbalik (Zona Atas Dinding)**"
                if lang == "ID" else
                "**📈 Second P-M Curve — Reversed Moment (Wall Top Zone)**"
            )
            st.info(
                "Kurva ini berlaku untuk zona atas dinding (dekat CU) saat CU aktif sebagai strut.  \n"
                "**Tulangan tarik = muka DALAM (As_tekan)**, tulangan tekan = muka luar (As_tarik).  \n"
                "Ini adalah kebalikan dari kondisi kantilever di dasar dinding."
                if lang == "ID" else
                "This curve applies to the wall top zone (near CU) when CU acts as strut.  \n"
                "**Tension steel = INNER face (As_comp)**, compression = outer face (As_tension).  \n"
                "This is the reverse of the cantilever condition at the wall base."
            )
            c_r1, c_r2, c_r3, c_r4 = st.columns(4)
            c_r1.metric("Pn,max (kN/m)",      f"{pm_rev.Pn_max:.1f}")
            c_r2.metric("Pb (kN/m)",           f"{pm_rev.Pb:.1f}")
            c_r3.metric("Mb (kN·m/m)",         f"{pm_rev.Mb:.2f}")
            c_r4.metric("Mn,pure (kN·m/m)",    f"{pm_rev.Mn_pure:.2f}")

            fig_pm_rev = _fig_pm_curve_laporan(pm_rev)
            st.pyplot(fig_pm_rev, use_container_width=True)
            plt.close(fig_pm_rev)

            if pm_rev.inside_curve:
                st.success(
                    f"✅ **AMAN** — Zona atas: demand (Nu={pm_rev.Nu_demand:.2f}, "
                    f"Mu={pm_rev.Mu_demand:.2f}) dalam kurva φP-M"
                )
            else:
                st.error(
                    f"❌ **TIDAK AMAN** — Zona atas: demand (Nu={pm_rev.Nu_demand:.2f}, "
                    f"Mu={pm_rev.Mu_demand:.2f}) DI LUAR kurva φP-M  \n"
                    "→ Perlu tambah tulangan muka DALAM atau perkuat sambungan CU."
                )

    st.divider()
    st.caption(
        "Catatan: Semua perhitungan berdasarkan SNI 2847:2019 & AASHTO LRFD 9th Ed. "
        "Selalu verifikasi dengan engineer yang bertanggung jawab."
    )
