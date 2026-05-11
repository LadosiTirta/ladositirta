# =============================================================================
# uditch/ui_input.py  — Tahap A Revision
# =============================================================================
# Perubahan dari versi sebelumnya:
#   • Geometri dinding: ta (atas) + tb (bawah) + ts (slab) — bukan satu tw
#   • Geometri CU: tcu (tengah) + te-cu = ta+gap; L-CU = Wo+2×ta (auto)
#   • Panjang UD: single input, default 1.2m
#   • Beban kendaraan: G, x1, x2, y1 (sesuai truk SNI)
#   • Tulangan: As_tarik (luar) + As_tekan (dalam) + slab bawah/atas
#   • Debug box dihapus
#   • Semua CU calculation references dihilangkan
# =============================================================================

import math
import streamlit as st
from uditch.lang_dict import t

REBAR_DIAMETERS = [6, 8, 10, 12, 13, 16, 19, 22, 25, 29, 32]

DEFAULTS = {
    # UD geometry
    "ud_inner_width":    600,   # Wo mm
    "ud_inner_height":   600,   # Ho mm
    "ud_wall_thick_top":  80,   # ta mm
    "ud_wall_thick_bot": 100,   # tb mm
    "ud_slab_thick":     120,   # ts mm
    "ud_length":         1.2,   # L m
    # CU geometry
    "cu_gap":             20,   # gap mm (0-50)
    "cu_thick_centre":   100,   # tcu mm (centre thickness)
    # Material
    "fc_prime":         30.0,
    "fy_main":         420.0,
    "fy_shear":        240.0,
    "gamma_c":          24.0,
    "cover_clear":        30,
    # Soil
    "gamma_s":          18.0,
    "phi_soil":         30.0,
    "cohesion":          0.0,
    "soil_fill_beside":  0.0,   # Hf m (jalan lebih tinggi dari top UD/CU)
    "fill_type_idx":       0,   # 0=tanah,1=aspal,2=beton
    "lat_method_idx":      0,   # 0=surcharge,1=boussinesq
    # Vehicle
    "axle_load_G":     225.0,   # kN (SNI truk 50T: G1=G2=22.5T=225kN)
    "wheel_spacing_x2":  1.75,  # m
    "axle_spacing_y1":   5.0,   # m
    "wheel_dist_x1":     0.25,  # m (jarak tepi UD ke roda terdekat)
    # Loading
    "cover_load_type_idx": 1,   # 0=pedestrian,1=vehicle,2=soil+wheel (default=vehicle)
    "pedestrian_kpa":    5.0,
    "soil_fill_above_cu":0.0,   # Ht m (timbunan di atas CU, kondisi 2)
    # Load factors
    "gamma_DL":          1.2,
    "gamma_LL":          1.6,
    "phi_flex":          0.90,
    "phi_shear_f":       0.75,
    "phi_axial_f":       0.65,
    # Connection
    "conn_mechanism":    1,     # 0=none/cantilever, 1=notch, 2=dowel
    "dowel_dia":          12,
    "dowel_spacing":     200,
    "dowel_embed":       150,
    # Rebar — wall
    "rebar_tension_dia":  13,   # outer face (tarik)
    "rebar_tension_spc": 150,
    "rebar_comp_dia":     10,   # inner face (tekan)
    "rebar_comp_spc":    200,
    # Rebar — slab
    "rebar_slab_bot_dia": 13,
    "rebar_slab_bot_spc":150,
    "rebar_slab_top_dia": 10,
    "rebar_slab_top_spc":200,
}


def _As(dia, spc):
    return math.pi / 4 * dia**2 / spc * 1000  # mm²/m


# =============================================================================
# SVG: Cross-section sketch
# =============================================================================

def _draw_cross_section(d: dict, condition: str) -> str:
    """
    Cross-section SVG with CORRECT CU geometry:
    - UD: trapezoidal walls (ta top, tb bottom), slab ts at base
    - CU: sits fully on top of UD walls (ta), flush — no vertical gap
    - tcu (centre) spans Wo - 2*gap (horizontal clear span)
    - te-cu (bearing zone) = ta mm wide on each side
    - gap is HORIZONTAL: the horizontal space between te-cu inner face and wall inner face
      (this gap is where the CU notch can deflect before engaging)
    """
    Wo  = d.get("ud_inner_width",  600)   # mm
    Ho  = d.get("ud_inner_height", 600)
    ta  = d.get("ud_wall_thick_top", 80)
    tb  = d.get("ud_wall_thick_bot", 100)
    ts  = d.get("ud_slab_thick",   120)
    tcu = d.get("cu_thick_centre", 100)
    gap = d.get("cu_gap", 20)
    cov = d.get("cover_clear",  30)
    condition_str = condition
    show_cu = condition_str in ("Kondisi 1", "Kondisi 2")

    # Derived
    te_cu = ta + gap          # total width of CU bearing zone (mm)
    # Outer width at top = Wo + 2*ta; at bottom = Wo + 2*tb
    Bo_top = Wo + 2 * ta
    Bo_bot = Wo + 2 * tb
    H_total = Ho + ts          # total UD height

    SVG_W, SVG_H = 480, 380
    # Scale to fit: use top width (widest point)
    scale = min(340 / Bo_top, 220 / H_total)
    # x origin: centre the drawing
    ox = (SVG_W - Bo_top * scale) / 2
    # y origin: top of UD walls (CU will go above this)
    oy_ud_top = 80.0 if show_cu else 50.0   # pixels from top of SVG

    # Key y-coordinates (pixels, y increases downward)
    y_ud_top  = oy_ud_top
    y_ud_bot  = y_ud_top + Ho * scale
    y_slab_bot= y_ud_bot + ts * scale
    # CU sits on TOP of the UD walls (y = y_ud_top - tcu*scale)
    y_cu_top  = y_ud_top - tcu * scale
    y_cu_bot  = y_ud_top   # CU bottom = UD wall top

    # x-coords at TOP of UD (using ta)
    x_wall_L_out = ox                        # left outer face of left wall
    x_wall_L_in  = ox + ta * scale           # left inner face of left wall
    x_wall_R_in  = ox + (ta + Wo) * scale    # right inner face of right wall
    x_wall_R_out = ox + Bo_top * scale       # right outer face of right wall

    # x-coords at BOTTOM of UD (using tb — walls widen toward base)
    extra = (tb - ta) * scale   # extra width on each side at bottom
    x_bot_L_out = ox - extra
    x_bot_L_in  = ox + ta * scale     # inner face stays same as top
    x_bot_R_in  = x_wall_R_in
    x_bot_R_out = x_wall_R_out + extra

    C_conc    = "#B0BEC5"
    C_cu_main = "#78909C"    # centre tcu (darker)
    C_cu_bear = "#90A4AE"    # bearing zone te-cu (slightly lighter)
    C_gap_col = "#FFF9C4"    # gap zone colour (yellow)
    C_steel   = "#E53935"
    C_comp    = "#1E88E5"
    C_dim     = "#455A64"
    C_soil    = "#81C784"

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_W}" height="{SVG_H}" '
        f'style="background:#F8F9FA;border-radius:8px;font-family:Arial,sans-serif;">',
        f'<rect x="0" y="0" width="{SVG_W}" height="{SVG_H}" fill="#F8F9FA" rx="8"/>',
    ]

    def poly(pts, fill, stroke="#546E7A", sw=1.5, alpha=1.0):
        pts_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        lines.append(f'<polygon points="{pts_str}" fill="{fill}" '
                     f'stroke="{stroke}" stroke-width="{sw}" opacity="{alpha}"/>')

    def rect(x, y, w, h, fill, stroke="#546E7A", sw=1.5, alpha=1.0, hatch=""):
        lines.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                     f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{alpha}"/>')

    def text(x, y, msg, size=9, color="#37474F", bold=False, anchor="middle"):
        fw = "bold" if bold else "normal"
        lines.append(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
                     f'font-size="{size}" fill="{color}" font-weight="{fw}">{msg}</text>')

    # ── UD Left wall (trapezoid: wider at bottom) ─────────────────────────────
    poly([(x_wall_L_out, y_ud_top), (x_wall_L_in, y_ud_top),
          (x_bot_L_in,   y_ud_bot), (x_bot_L_out, y_ud_bot)],
         fill=C_conc)
    # ── UD Right wall (mirrored)
    poly([(x_wall_R_in,  y_ud_top), (x_wall_R_out, y_ud_top),
          (x_bot_R_out,  y_ud_bot), (x_bot_R_in,   y_ud_bot)],
         fill=C_conc)
    # ── UD Base slab
    rect(x_bot_L_out, y_ud_bot, x_bot_R_out - x_bot_L_out, ts * scale, C_conc)
    # ── Interior void (light fill)
    rect(x_wall_L_in, y_ud_top, x_wall_R_in - x_wall_L_in, Ho * scale, "#ECEFF1", stroke="none")

    # ── UD centre label
    cx = (x_wall_L_in + x_wall_R_in) / 2
    cy = y_ud_top + Ho * scale / 2
    text(cx, cy + 4, "UD", size=11, color="#546E7A", bold=True)

    # ── CU (if applicable) ────────────────────────────────────────────────────
    if show_cu:
        # CU geometry (all in pixels):
        # - Bearing zone LEFT:  x from x_wall_L_out to x_wall_L_out + te_cu*scale
        #                       sits on top of left wall (ta wide)
        # - Gap zone LEFT:      horizontal gap between inner face of te-cu and inner wall face
        #                       width = gap*scale, coloured yellow
        # - Centre tcu:         from (x_wall_L_out + te_cu*scale + gap*scale) to matching right
        #                       BUT: te_cu = ta + gap, so inner edge of bearing = x_wall_L_in + gap*scale
        # Actually simpler:
        # CU left bearing zone: x_wall_L_out → x_wall_L_out + ta*scale   (width=ta, sitting on wall)
        # CU gap zone:          x_wall_L_in  → x_wall_L_in + gap*scale   (horizontal, at top level)
        # CU centre span:       x_wall_L_in + gap*scale  → x_wall_R_in - gap*scale
        # CU right gap zone:    x_wall_R_in - gap*scale  → x_wall_R_in
        # CU right bearing:     x_wall_R_in → x_wall_R_out

        x_cu_LB_l = x_wall_L_out                    # left bearing zone left edge
        x_cu_LB_r = x_wall_L_out + ta * scale       # left bearing zone right edge (= x_wall_L_in)
        x_cu_Lgap_l = x_wall_L_in                   # left gap zone left
        x_cu_Lgap_r = x_wall_L_in + gap * scale     # left gap zone right
        x_cu_span_l = x_cu_Lgap_r                   # centre span left
        x_cu_span_r = x_wall_R_in - gap * scale     # centre span right
        x_cu_Rgap_l = x_cu_span_r                   # right gap zone left
        x_cu_Rgap_r = x_wall_R_in                   # right gap zone right
        x_cu_RB_l   = x_wall_R_in                   # right bearing left (= x_wall_R_in)
        x_cu_RB_r   = x_wall_R_out                  # right bearing right

        cu_h = tcu * scale

        # Left bearing (te-cu portion) — same height as tcu (or show shorter as te-cu)
        # For clarity: bearing zone has full tcu height; gap shows as notch
        rect(x_cu_LB_l, y_cu_top, ta * scale,     cu_h, C_cu_bear)
        # Left gap zone — horizontal void / notch (shown as yellow stripe IN THE CU)
        # The gap is horizontal: the te-cu extends (ta + gap) wide, but only ta sits ON the wall.
        # The gap part hangs over the void side. Show this as a lighter colour.
        rect(x_cu_LB_r, y_cu_top, gap * scale,    cu_h, C_gap_col, stroke="#F9A825", sw=0.8)
        # Centre tcu span
        rect(x_cu_span_l, y_cu_top, x_cu_span_r - x_cu_span_l, cu_h, C_cu_main)
        # Right gap zone
        rect(x_cu_span_r, y_cu_top, gap * scale,  cu_h, C_gap_col, stroke="#F9A825", sw=0.8)
        # Right bearing
        rect(x_cu_RB_l, y_cu_top, ta * scale,     cu_h, C_cu_bear)

        # ── Gap labels (horizontal gap annotation) ────────────────────────────
        gap_mid_x = x_cu_LB_r + gap * scale / 2
        gap_mid_y = y_cu_top + cu_h / 2
        lines.append(
            f'<text x="{gap_mid_x:.1f}" y="{gap_mid_y + 3:.1f}" text-anchor="middle" '
            f'font-size="7" fill="#E65100" font-weight="bold">{gap}mm</text>'
        )

        # ── CU labels ─────────────────────────────────────────────────────────
        # "te-cu" label on bearing zone
        te_mid_x = x_cu_LB_l + ta * scale / 2
        lines.append(
            f'<text x="{te_mid_x:.1f}" y="{y_cu_top - 4:.1f}" text-anchor="middle" '
            f'font-size="7.5" fill="{C_dim}">te-cu={te_cu}mm</text>'
        )
        # "tcu" label in centre span
        text((x_cu_span_l + x_cu_span_r) / 2, y_cu_top + cu_h / 2 + 4,
             "CU", size=10, color="white", bold=True)
        text((x_cu_span_l + x_cu_span_r) / 2, y_cu_top + cu_h / 2 + 14,
             f"tcu={tcu}mm", size=7.5, color="white")

        # ── Arrow showing gap is HORIZONTAL ───────────────────────────────────
        arr_y = y_cu_top + cu_h + 6
        lines.append(
            f'<line x1="{x_cu_LB_r:.1f}" y1="{arr_y:.1f}" '
            f'x2="{x_cu_Lgap_r:.1f}" y2="{arr_y:.1f}" '
            f'stroke="#F57F17" stroke-width="1.2" '
            f'marker-start="url(#ah)" marker-end="url(#ah)"/>'
        )
        lines.append(
            f'<text x="{gap_mid_x:.1f}" y="{arr_y + 9:.1f}" text-anchor="middle" '
            f'font-size="7" fill="#E65100">gap (horiz)</text>'
        )

        # ── Vertical dim: tcu ─────────────────────────────────────────────────
        vdim_x = x_wall_R_out + 14
        lines.append(
            f'<line x1="{vdim_x:.1f}" y1="{y_cu_top:.1f}" '
            f'x2="{vdim_x:.1f}" y2="{y_cu_bot:.1f}" '
            f'stroke="{C_dim}" stroke-width="0.8"/>'
        )
        lines.append(
            f'<text x="{vdim_x + 18:.1f}" y="{y_cu_top + cu_h/2:.1f}" '
            f'text-anchor="middle" font-size="7.5" fill="{C_dim}" '
            f'transform="rotate(-90,{vdim_x+18:.1f},{y_cu_top+cu_h/2:.1f})">tcu={tcu}mm</text>'
        )

    # ── Rebar schematic ───────────────────────────────────────────────────────
    r_t = max(3.0, d.get("rebar_tension_dia", 13) * scale / 3)
    r_c = max(2.5, d.get("rebar_comp_dia", 10) * scale / 3)
    cov_px = cov * scale

    # Tension (outer face = left outer, right outer)
    for xr in (x_wall_L_out + cov_px, x_wall_R_out - cov_px):
        lines.append(f'<circle cx="{xr:.1f}" cy="{y_ud_bot - cov_px:.1f}" '
                     f'r="{r_t:.1f}" fill="{C_steel}"/>')
    # Compression (inner face)
    for xr in (x_wall_L_in - cov_px, x_wall_R_in + cov_px):
        lines.append(f'<circle cx="{xr:.1f}" cy="{y_ud_bot - cov_px:.1f}" '
                     f'r="{r_c:.1f}" fill="{C_comp}"/>')
    # Slab bottom tension
    lines.append(f'<circle cx="{cx:.1f}" cy="{y_slab_bot - cov_px:.1f}" '
                 f'r="{r_t:.1f}" fill="{C_steel}"/>')

    # ── Horizontal dimension annotations ─────────────────────────────────────
    ann_y = y_slab_bot + 16
    # B_o = Wo + 2ta
    lines.append(
        f'<line x1="{x_wall_L_out:.1f}" y1="{ann_y:.1f}" '
        f'x2="{x_wall_R_out:.1f}" y2="{ann_y:.1f}" '
        f'stroke="{C_dim}" stroke-width="0.8" marker-start="url(#ah)" marker-end="url(#ah)"/>'
    )
    lines.append(
        f'<text x="{(x_wall_L_out+x_wall_R_out)/2:.1f}" y="{ann_y-3:.1f}" '
        f'text-anchor="middle" font-size="8" fill="{C_dim}">Wo+2ta={Bo_top}mm</text>'
    )
    # Wo
    ann_y2 = ann_y + 14
    lines.append(
        f'<line x1="{x_wall_L_in:.1f}" y1="{ann_y2:.1f}" '
        f'x2="{x_wall_R_in:.1f}" y2="{ann_y2:.1f}" '
        f'stroke="{C_dim}" stroke-width="0.8" marker-start="url(#ah)" marker-end="url(#ah)"/>'
    )
    lines.append(
        f'<text x="{cx:.1f}" y="{ann_y2-3:.1f}" '
        f'text-anchor="middle" font-size="8" fill="{C_dim}">Wo={Wo}mm</text>'
    )
    # Vertical dim: Ho (right side)
    vx = x_wall_R_out + 28
    lines.append(
        f'<line x1="{vx:.1f}" y1="{y_ud_top:.1f}" x2="{vx:.1f}" y2="{y_ud_bot:.1f}" '
        f'stroke="{C_dim}" stroke-width="0.8"/>'
    )
    lines.append(
        f'<text x="{vx+16:.1f}" y="{y_ud_top+Ho*scale/2:.1f}" text-anchor="middle" '
        f'font-size="8" fill="{C_dim}" '
        f'transform="rotate(-90,{vx+16:.1f},{y_ud_top+Ho*scale/2:.1f})">Ho={Ho}mm</text>'
    )
    # ta label
    lines.append(
        f'<text x="{x_wall_L_out + ta*scale/2:.1f}" y="{y_ud_top - 5:.1f}" '
        f'text-anchor="middle" font-size="7.5" fill="{C_dim}">ta={ta}mm</text>'
    )

    # ── Title ─────────────────────────────────────────────────────────────────
    lines.append(
        f'<text x="{SVG_W/2:.0f}" y="18" text-anchor="middle" '
        f'font-size="12" fill="#1A237E" font-weight="bold">'
        f'Penampang UD — {condition_str}</text>'
    )

    # Arrowhead marker def
    lines.insert(2,
        '<defs><marker id="ah" markerWidth="5" markerHeight="5" '
        'refX="2.5" refY="2.5" orient="auto">'
        '<path d="M0,0 L5,2.5 L0,5 Z" fill="#546E7A"/></marker></defs>'
    )
    lines.append('</svg>')
    return "\n".join(lines)


def _draw_load_schematic(d: dict, condition: str) -> str:
    SVG_W, SVG_H = 460, 220
    Wo   = d["ud_inner_width"]
    ta   = d["ud_wall_thick_top"]
    Bo   = Wo + 2*ta
    x1   = d["wheel_dist_x1"] * 1000    # mm
    x2   = d["wheel_spacing_x2"] * 1000 # mm
    G    = d["axle_load_G"]
    P1   = G / 2

    scale = min(280/Bo, 1.0)
    ox = (SVG_W - Bo*scale) / 2
    oy = 160

    C_arr = "#D32F2F"; C_conc = "#B0BEC5"; C_load = "#1565C0"

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_W}" height="{SVG_H}" '
        f'style="background:#FAFAFA;border-radius:8px;">',
        '<defs><marker id="ah" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">'
        '<path d="M0,0 L0,6 L6,3 Z" fill="#D32F2F"/></marker></defs>',
        f'<rect x="0" y="0" width="{SVG_W}" height="{SVG_H}" fill="#FAFAFA" rx="8"/>',
        # Ground line
        f'<line x1="{ox-30:.1f}" y1="{oy:.1f}" x2="{ox+Bo*scale+30:.1f}" y2="{oy:.1f}" '
        f'stroke="#78909C" stroke-width="1.5" stroke-dasharray="6,3"/>',
        # Left wall
        f'<rect x="{ox:.1f}" y="{oy-80:.1f}" width="{ta*scale:.1f}" height="80" fill="{C_conc}" stroke="#546E7A" stroke-width="1.2"/>',
        # Right wall
        f'<rect x="{ox+(Wo+ta)*scale:.1f}" y="{oy-80:.1f}" width="{ta*scale:.1f}" height="80" fill="{C_conc}" stroke="#546E7A" stroke-width="1.2"/>',
    ]

    def arrow_down(x, y_top, y_bot, label, color=C_arr):
        lines.append(f'<line x1="{x:.1f}" y1="{y_top:.1f}" x2="{x:.1f}" y2="{y_bot:.1f}" '
                     f'stroke="{color}" stroke-width="2" marker-end="url(#ah)"/>')
        lines.append(f'<text x="{x:.1f}" y="{y_top-3:.1f}" text-anchor="middle" '
                     f'font-size="9" fill="{color}" font-weight="bold">{label}</text>')

    if condition in ("Kondisi 1", "Kondisi 3"):
        # Roda di samping UD: P1 pada jarak x1 dari tepi kiri UD
        px_P1 = ox - x1*scale        # ke kiri dari tepi
        px_P2 = px_P1 - x2*scale     # roda kedua lebih jauh
        arrow_down(px_P1, oy-60, oy-2, f"P1={P1:.0f}kN")
        arrow_down(px_P2, oy-60, oy-2, f"P2={P1:.0f}kN", color="#E65100")
        # Tekanan lateral → dinding kiri
        for yy in range(10, 85, 14):
            lx = ox - 2
            lines.append(f'<line x1="{lx-18:.1f}" y1="{oy-yy:.1f}" x2="{lx:.1f}" y2="{oy-yy:.1f}" '
                         f'stroke="#7B1FA2" stroke-width="1.5" marker-end="url(#ah)"/>')
        lines.append(f'<text x="{ox-28:.1f}" y="{oy-42:.1f}" font-size="9" fill="#7B1FA2" '
                     f'text-anchor="middle" transform="rotate(-90,{ox-28:.1f},{oy-42:.1f})">q lateral</text>')

    elif condition == "Kondisi 2":
        # Roda di atas CU (crossing)
        cx = ox + Bo*scale/2
        arrow_down(cx, oy-110, oy-82, f"G={G:.0f}kN", color=C_load)
        # CU (blue bar)
        lines.append(f'<rect x="{ox:.1f}" y="{oy-82:.1f}" width="{Bo*scale:.1f}" height="12" '
                     f'fill="#90CAF9" stroke="#1565C0" stroke-width="1.2" opacity="0.85"/>')
        lines.append(f'<text x="{cx:.1f}" y="{oy-72:.1f}" text-anchor="middle" '
                     f'font-size="8" fill="{C_load}">CU</text>')
        # Reactions at walls
        for rx in (ox + ta*scale/2, ox + (Wo+1.5*ta)*scale):
            arrow_down(rx, oy-2, oy+30, "R", color="#2E7D32")
        lines.append(f'<text x="{cx:.1f}" y="{oy+46:.1f}" text-anchor="middle" '
                     f'font-size="9" fill="#2E7D32">Dinding = Kolom (N+M)</text>')

    lines.append(f'<text x="{SVG_W//2}" y="16" text-anchor="middle" font-size="11" '
                 f'fill="#1A237E" font-weight="bold">Skema Beban — {condition}</text>')
    lines.append('</svg>')
    return "\n".join(lines)


# =============================================================================
# INPUT SECTIONS
# =============================================================================

def _sec_ud_dimensions(lang):
    d = {}
    with st.expander(t("sec_dimensions", lang), expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            d["ud_inner_width"]  = st.number_input(t("ud_inner_width",  lang),
                min_value=200, max_value=3000, value=DEFAULTS["ud_inner_width"], step=50, key="in_Wo")
            d["ud_inner_height"] = st.number_input(t("ud_inner_height", lang),
                min_value=150, max_value=3000, value=DEFAULTS["ud_inner_height"], step=50, key="in_Ho")
            d["ud_wall_thick_top"] = st.number_input(t("ud_wall_thick_top", lang),
                min_value=50, max_value=400, value=DEFAULTS["ud_wall_thick_top"], step=5, key="in_ta",
                help="ta = tebal dinding di puncak UD (bagian terkecil)" if lang=="ID"
                     else "ta = wall thickness at top of UD (smallest section)")
            d["ud_wall_thick_bot"] = st.number_input(t("ud_wall_thick_bot", lang),
                min_value=50, max_value=500, value=DEFAULTS["ud_wall_thick_bot"], step=5, key="in_tb",
                help="tb = tebal dinding di dasar (biasanya > ta)" if lang=="ID"
                     else "tb = wall thickness at base (usually > ta)")
        with c2:
            d["ud_slab_thick"] = st.number_input(t("ud_slab_thick", lang),
                min_value=80, max_value=500, value=DEFAULTS["ud_slab_thick"], step=5, key="in_ts")
            d["ud_length"] = st.number_input(t("ud_length", lang),
                min_value=0.5, max_value=6.0, value=DEFAULTS["ud_length"],
                step=0.1, format="%.2f", key="in_L",
                help="Panjang satu segmen precast. Default = 1.2 m" if lang=="ID"
                     else "Length of one precast segment. Default = 1.2 m")

        # Derived summary
        Wo = d["ud_inner_width"]; ta = d["ud_wall_thick_top"]; tb = d["ud_wall_thick_bot"]
        ts = d["ud_slab_thick"];  Ho = d["ud_inner_height"]
        st.caption(
            f"🔹 Lebar luar atas = **{Wo+2*ta} mm** | "
            f"Lebar luar bawah = **{Wo+2*tb} mm** | "
            f"Tinggi total = **{Ho+ts} mm**"
        )
    return d


def _sec_cu_dimensions(lang, ta, Wo):
    d = {}
    with st.expander(t("sec_cu_dimensions", lang), expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            d["cu_gap"] = st.number_input(t("cu_gap", lang),
                min_value=0, max_value=50, value=DEFAULTS["cu_gap"], step=1, key="in_cu_gap",
                help=("Gap antara sisi dalam te-cu dan dinding UD. "
                      "0 = CU langsung menempel ke dinding." if lang=="ID"
                      else "Gap between inner side of te-cu and UD wall. "
                           "0 = CU contacts wall directly."))
            d["cu_thick_centre"] = st.number_input(t("cu_thick_centre", lang),
                min_value=60, max_value=400, value=DEFAULTS["cu_thick_centre"], step=5, key="in_tcu",
                help=("Tebal bagian tengah CU (yang menggantung di atas bukaan UD). "
                      "te-cu otomatis = ta + gap." if lang=="ID"
                      else "Thickness of centre CU portion (spanning over UD opening). "
                           "te-cu is automatic = ta + gap."))
        with c2:
            gap = d["cu_gap"]
            te_cu = ta + gap
            L_cu  = Wo + 2*ta
            inner_span = Wo - 2*gap
            d["cu_te_cu"]       = te_cu
            d["cu_length"]      = L_cu
            d["cu_inner_span"]  = inner_span

            st.metric(t("cu_te_auto_label", lang), f"{te_cu} mm",
                      help="= ta + gap (otomatis)" if lang=="ID" else "= ta + gap (automatic)")
            st.metric(t("cu_length_auto_label", lang), f"{L_cu} mm",
                      help="= Wo + 2×ta" if lang=="ID" else "= Wo + 2×ta")
            st.metric(t("cu_inner_span_label", lang), f"{inner_span} mm",
                      help="= Wo − 2×gap (lebar tcu)" if lang=="ID" else "= Wo − 2×gap (tcu width)")

        if d["cu_gap"] == 0:
            st.info(t("gap_note_zero", lang))
    return d


def _sec_vehicle(lang):
    d = {}
    with st.expander(t("sec_vehicle", lang), expanded=True):
        st.caption(
            "Truk SNI T-50: G1 = G2 = 225 kN. P1 = P2 = G/2. "
            "Gandar depan G0 = 50 kN diabaikan untuk desain dinding."
            if lang=="ID" else
            "SNI T-50 truck: G1 = G2 = 225 kN. P1 = P2 = G/2. "
            "Front axle G0 = 50 kN ignored for wall design."
        )
        c1, c2 = st.columns(2)
        with c1:
            d["axle_load_G"] = st.number_input(t("axle_load_G", lang),
                min_value=10.0, max_value=1000.0, value=DEFAULTS["axle_load_G"],
                step=5.0, format="%.1f", key="in_G")
            d["wheel_spacing_x2"] = st.number_input(t("wheel_spacing_x2", lang),
                min_value=0.5, max_value=4.0, value=DEFAULTS["wheel_spacing_x2"],
                step=0.05, format="%.2f", key="in_x2")
        with c2:
            d["axle_spacing_y1"] = st.number_input(t("axle_spacing_y1", lang),
                min_value=1.0, max_value=20.0, value=DEFAULTS["axle_spacing_y1"],
                step=0.5, format="%.1f", key="in_y1")
            d["wheel_dist_x1"] = st.number_input(t("wheel_dist_x1", lang),
                min_value=0.0, max_value=5.0, value=DEFAULTS["wheel_dist_x1"],
                step=0.05, format="%.2f", key="in_x1",
                help=("Jarak dari tepi luar UD ke tepi roda terdekat (m). "
                      "Untuk kondisi kritis: x1 kecil (roda sangat dekat UD)."
                      if lang=="ID" else
                      "Distance from outer UD edge to nearest wheel edge (m). "
                      "Critical case: small x1 (wheel very close to UD)."))
        # Derived
        P1 = d["axle_load_G"] / 2
        x_centre = d["wheel_dist_x1"] + d["wheel_spacing_x2"] / 2
        st.caption(
            f"🚛 P1 = P2 = G/2 = **{P1:.1f} kN** | "
            f"Jarak pusat gandar dari tepi UD = x1 + x2/2 = **{x_centre:.2f} m**"
        )
    return d


def _sec_material(lang):
    d = {}
    with st.expander(t("sec_material", lang), expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            d["fc_prime"] = st.number_input(t("fc_prime", lang),
                min_value=17.0, max_value=80.0, value=DEFAULTS["fc_prime"],
                step=1.0, format="%.1f", key="in_fc")
            d["fy_main"]  = st.number_input(t("fy_main", lang),
                min_value=200.0, max_value=600.0, value=DEFAULTS["fy_main"],
                step=10.0, format="%.0f", key="in_fy",
                help="BJTD 40=400 | BJTD 42=420 | BJTD 50=500" if lang=="ID"
                     else "BJTD 40=400 | BJTD 42=420 | BJTD 50=500")
            d["fy_shear"] = st.number_input(t("fy_shear", lang),
                min_value=200.0, max_value=600.0, value=DEFAULTS["fy_shear"],
                step=10.0, format="%.0f", key="in_fyt",
                help="BJTP 24=240 | BJTD 40=400" if lang=="ID" else "BJTP 24=240 | BJTD 40=400")
        with c2:
            d["gamma_c"]    = st.number_input(t("concrete_unit_weight", lang),
                min_value=20.0, max_value=28.0, value=DEFAULTS["gamma_c"],
                step=0.5, format="%.1f", key="in_gammac")
            d["cover_clear"]= st.number_input(t("cover_clear", lang),
                min_value=15, max_value=75, value=DEFAULTS["cover_clear"],
                step=5, key="in_cov",
                help="SNI 2847:2019 Tabel 20.6.1.3 — Precast ekspos: 40mm min")
        with c3:
            fc = d["fc_prime"]
            b1 = max(0.65, 0.85 - 0.05*(fc-28)/7)
            Ec = 4700 * math.sqrt(fc)
            st.metric("β₁  (SNI 2847:2019 Ps.22.2.2.4.3)", f"{b1:.3f}")
            st.metric("Ec  (MPa)", f"{Ec:.0f}")
    return d


def _sec_soil(lang, condition):
    d = {}
    with st.expander(t("sec_soil", lang), expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            d["gamma_s"]  = st.number_input(t("soil_unit_weight", lang),
                min_value=14.0, max_value=22.0, value=DEFAULTS["gamma_s"],
                step=0.5, format="%.1f", key="in_gammas")
            d["phi_soil"] = st.number_input(t("soil_friction_angle", lang),
                min_value=0.0, max_value=45.0, value=DEFAULTS["phi_soil"],
                step=1.0, format="%.1f", key="in_phi")
            d["cohesion"] = st.number_input(t("soil_cohesion", lang),
                min_value=0.0, max_value=200.0, value=DEFAULTS["cohesion"],
                step=1.0, format="%.1f", key="in_c")
        with c2:
            d["soil_fill_beside"] = st.number_input(t("soil_fill_beside", lang),
                min_value=0.0, max_value=5.0, value=DEFAULTS["soil_fill_beside"],
                step=0.05, format="%.2f", key="in_Hf",
                help=("Tinggi jalan/timbunan di atas top UD (atau top CU). "
                      "Jika 0 = muka atas UD/CU = muka jalan." if lang=="ID"
                      else "Road/fill height above top of UD (or CU). "
                           "If 0 = top UD/CU flush with road surface."))

            fill_opts = [t("fill_type_soil",lang), t("fill_type_asphalt",lang), t("fill_type_concrete",lang)]
            fill_lbl  = st.radio(t("fill_type_label",lang), fill_opts,
                                 index=DEFAULTS["fill_type_idx"], key="in_fill_type",
                                 horizontal=True,
                                 help=("Jenis material samping UD — menentukan berat jenis beban samping." if lang=="ID"
                                       else "Material type beside UD — determines unit weight of surcharge."))
            d["fill_type_idx"] = fill_opts.index(fill_lbl)
            d["fill_type"]     = fill_lbl

            # Ka derived
            phi_r = math.radians(d["phi_soil"])
            Ka = math.tan(math.radians(45) - phi_r/2)**2
            st.metric("Ka  (Rankine Aktif)", f"{Ka:.3f}",
                      help="Ka digunakan (bukan Ko) karena dinding UD akan berdefleksi, memobilisasi tekanan aktif." if lang=="ID"
                           else "Ka used (not Ko) because UD wall deflects, mobilizing active pressure.")
            d["Ka"] = Ka

        # Lateral pressure method
        st.markdown(f"**{t('lateral_pressure_option', lang)}**")
        lat_opts = [t("lat_opt_surcharge", lang), t("lat_opt_point", lang)]
        lat_sel  = st.radio("##lat_method", lat_opts,
                            index=DEFAULTS["lat_method_idx"], key="in_lat_method",
                            horizontal=True, label_visibility="collapsed")
        d["lat_method_idx"] = lat_opts.index(lat_sel)
        if d["lat_method_idx"] == 0:
            st.caption(t("lat_opt_note_surcharge", lang))
        else:
            st.info(t("lat_opt_note_point", lang))

    return d


def _sec_loading(lang, condition):
    d = {}
    with st.expander(t("sec_loading", lang), expanded=True):

        if condition == "Kondisi 2":
            # Crossing: load ON TOP of CU
            st.markdown(f"**{t('cover_load_type', lang)}**")
            clt_opts = [t("cover_load_pedestrian",lang),
                        t("cover_load_vehicle",lang),
                        t("cover_load_soil_wheel",lang)]
            st.caption(
                "ℹ️ Default: Beban Roda Kendaraan. Pejalan kaki hanya untuk jalur non-kendaraan."
                if lang=="ID" else
                "ℹ️ Default: Vehicular Wheel Load. Pedestrian only for non-vehicle paths."
            )
            clt_lbl  = st.radio("##clt", clt_opts,
                                 index=DEFAULTS["cover_load_type_idx"],
                                 key="in_clt", horizontal=True, label_visibility="collapsed")
            d["cover_load_type_idx"] = clt_opts.index(clt_lbl)

            if d["cover_load_type_idx"] == 0:
                d["pedestrian_kpa"] = st.number_input(t("pedestrian_load_kpa",lang),
                    min_value=2.0, max_value=20.0, value=DEFAULTS["pedestrian_kpa"],
                    step=0.5, format="%.1f", key="in_qped")
            elif d["cover_load_type_idx"] == 2:
                d["soil_fill_above_cu"] = st.number_input(t("soil_fill_above_cu",lang),
                    min_value=0.0, max_value=5.0, value=DEFAULTS["soil_fill_above_cu"],
                    step=0.05, format="%.2f", key="in_Ht")
                st.caption(
                    "Distribusi beban roda ke CU: metode 2:1 melalui timbunan." if lang=="ID"
                    else "Wheel load distribution to CU: 2:1 method through fill.")
            else:
                d["pedestrian_kpa"]    = 0.0
                d["soil_fill_above_cu"]= 0.0
        else:
            # Kondisi 1 & 3: lateral from vehicle already in soil section
            d["cover_load_type_idx"] = 0
            d["pedestrian_kpa"]      = 0.0
            d["soil_fill_above_cu"]  = 0.0
            st.caption(
                "Kondisi 1 & 3: beban kendaraan bekerja lateral ke dinding UD. "
                "Input gandar & jarak roda di bagian 🚛 Kendaraan."
                if lang=="ID" else
                "Condition 1 & 3: vehicle load acts laterally on UD wall. "
                "Enter axle & wheel data in 🚛 Vehicle section."
            )

        st.divider()
        # Load factors (all conditions)
        st.markdown(
            f"**{t('sec_load_factors', lang)} (SNI 2847:2019 Tabel 21.2.1)**"
        )
        c1, c2, c3, c4, c5 = st.columns(5)
        d["gamma_DL"]   = c1.number_input(t("load_factor_DL",lang), 1.0, 1.6, DEFAULTS["gamma_DL"],  0.05, "%.2f", key="in_gDL")
        d["gamma_LL"]   = c2.number_input(t("load_factor_LL",lang), 1.0, 2.0, DEFAULTS["gamma_LL"],  0.05, "%.2f", key="in_gLL")
        d["phi_flex"]   = c3.number_input(t("phi_flexure",lang),    0.65,0.90, DEFAULTS["phi_flex"],  0.01, "%.2f", key="in_pflex")
        d["phi_shear_f"]= c4.number_input(t("phi_shear",lang),      0.60,0.85, DEFAULTS["phi_shear_f"],0.01,"%.2f", key="in_psh")
        d["phi_axial_f"]= c5.number_input(t("phi_axial",lang),      0.60,0.80, DEFAULTS["phi_axial_f"],0.01,"%.2f", key="in_pax")
    return d


def _sec_connection(lang, condition, ta, gap):
    d = {}
    disabled = condition == "Kondisi 3"
    header = t("sec_connection", lang) + ("  *(N/A — Kondisi 3)*" if disabled else "")
    with st.expander(header, expanded=(not disabled)):
        if disabled:
            st.caption("Kondisi 3: tanpa CU → tidak ada sambungan." if lang=="ID"
                       else "Condition 3: no cover → no connection.")
            d.update({"conn_mechanism": 0, "dowel_dia": 0,
                      "dowel_spacing": 0, "dowel_embed": 0})
            return d

        mech_opts = [t("conn_none",lang), t("conn_notch",lang), t("conn_dowel",lang)]
        mech_lbl  = st.radio(t("conn_mechanism_title",lang), mech_opts,
                             index=DEFAULTS["conn_mechanism"], key="in_conn")
        d["conn_mechanism"] = mech_opts.index(mech_lbl)

        if d["conn_mechanism"] == 0:
            st.info("ℹ️ Dinding UD didesain sebagai kantilever murni (konservatif)."
                    if lang=="ID" else
                    "ℹ️ UD wall designed as pure cantilever (conservative).")
            d.update({"dowel_dia": 0, "dowel_spacing": 0, "dowel_embed": 0})

        elif d["conn_mechanism"] == 1:
            if gap == 0:
                st.info(t("gap_note_zero", lang))
            else:
                st.info(
                    f"📐 Notch bearing aktif setelah defleksi ≥ {gap} mm.\n\n"
                    "Kapasitas bidang tumpu = (te-cu − ta) × L_seg × 0.85f'c (bearing strength)."
                    if lang=="ID" else
                    f"📐 Notch bearing active after deflection ≥ {gap} mm.\n\n"
                    "Bearing capacity = (te-cu − ta) × L_seg × 0.85f'c."
                )
            d.update({"dowel_dia": 0, "dowel_spacing": 0, "dowel_embed": 0})

        else:  # dowel
            st.info(t("gap_note_dowel", lang))
            c1, c2, c3 = st.columns(3)
            with c1:
                d["dowel_dia"] = st.selectbox(t("dowel_diameter",lang),
                    REBAR_DIAMETERS, REBAR_DIAMETERS.index(DEFAULTS["dowel_dia"]),
                    key="in_ddia")
            with c2:
                d["dowel_spacing"] = st.number_input(t("dowel_spacing",lang),
                    50, 500, DEFAULTS["dowel_spacing"], 25, key="in_dsp")
            with c3:
                d["dowel_embed"] = st.number_input(t("dowel_embedment",lang),
                    50, 400, DEFAULTS["dowel_embed"], 10, key="in_demb",
                    help="Min = 8 × dia (SNI 2847:2019 Ps.26.8)")

            min_emb = 8 * d["dowel_dia"]
            if d["dowel_embed"] < min_emb:
                st.warning(f"⚠️ Embedment {d['dowel_embed']} mm < min {min_emb} mm "
                           f"(8×ø{d['dowel_dia']}) — SNI 2847:2019 Ps.26.8")
    return d


def _sec_rebar(lang):
    d = {}
    with st.expander(t("sec_rebar", lang), expanded=False):
        # ── Wall reinforcement ────────────────────────────────────────────────
        st.markdown(f"**{t('rebar_wall_tension', lang)}**  *(muka luar, tulangan tarik)*" if lang=="ID"
                    else f"**{t('rebar_wall_tension', lang)}**  *(outer face, tension steel)*")
        c1, c2 = st.columns(2)
        with c1:
            d["rebar_tension_dia"] = st.selectbox(
                t("rebar_dia",lang) + " — Tarik Luar" if lang=="ID" else t("rebar_dia",lang) + " — Outer Tension",
                REBAR_DIAMETERS, REBAR_DIAMETERS.index(DEFAULTS["rebar_tension_dia"]),
                key="in_rtd")
        with c2:
            d["rebar_tension_spc"] = st.number_input(
                t("rebar_spacing",lang) + " — Tarik Luar" if lang=="ID" else t("rebar_spacing",lang) + " — Outer Tension",
                50, 300, DEFAULTS["rebar_tension_spc"], 25, key="in_rts")

        st.markdown(f"**{t('rebar_wall_comp', lang)}**  *(muka dalam, tulangan tekan)*" if lang=="ID"
                    else f"**{t('rebar_wall_comp', lang)}**  *(inner face, compression steel)*")
        c3, c4 = st.columns(2)
        with c3:
            d["rebar_comp_dia"] = st.selectbox(
                t("rebar_dia",lang) + " — Tekan Dalam" if lang=="ID" else t("rebar_dia",lang) + " — Inner Comp.",
                REBAR_DIAMETERS, REBAR_DIAMETERS.index(DEFAULTS["rebar_comp_dia"]),
                key="in_rcd")
        with c4:
            d["rebar_comp_spc"] = st.number_input(
                t("rebar_spacing",lang) + " — Tekan Dalam" if lang=="ID" else t("rebar_spacing",lang) + " — Inner Comp.",
                50, 300, DEFAULTS["rebar_comp_spc"], 25, key="in_rcs")

        st.divider()
        # ── Slab reinforcement ────────────────────────────────────────────────
        st.markdown(f"**{t('rebar_slab_bot', lang)}**")
        c5, c6 = st.columns(2)
        with c5:
            d["rebar_slab_bot_dia"] = st.selectbox(
                t("rebar_dia",lang) + " — Slab Bawah" if lang=="ID" else t("rebar_dia",lang) + " — Slab Bot",
                REBAR_DIAMETERS, REBAR_DIAMETERS.index(DEFAULTS["rebar_slab_bot_dia"]),
                key="in_rsbd")
        with c6:
            d["rebar_slab_bot_spc"] = st.number_input(
                t("rebar_spacing",lang) + " — Slab Bawah" if lang=="ID" else t("rebar_spacing",lang) + " — Slab Bot",
                50, 300, DEFAULTS["rebar_slab_bot_spc"], 25, key="in_rsbs")

        st.markdown(f"**{t('rebar_slab_top', lang)}**")
        c7, c8 = st.columns(2)
        with c7:
            d["rebar_slab_top_dia"] = st.selectbox(
                t("rebar_dia",lang) + " — Slab Atas" if lang=="ID" else t("rebar_dia",lang) + " — Slab Top",
                REBAR_DIAMETERS, REBAR_DIAMETERS.index(DEFAULTS["rebar_slab_top_dia"]),
                key="in_rstd")
        with c8:
            d["rebar_slab_top_spc"] = st.number_input(
                t("rebar_spacing",lang) + " — Slab Atas" if lang=="ID" else t("rebar_spacing",lang) + " — Slab Top",
                50, 300, DEFAULTS["rebar_slab_top_spc"], 25, key="in_rsts")

        # ── As summary ────────────────────────────────────────────────────────
        st.divider()
        As_tension  = _As(d["rebar_tension_dia"],  d["rebar_tension_spc"])
        As_comp     = _As(d["rebar_comp_dia"],      d["rebar_comp_spc"])
        As_slab_bot = _As(d["rebar_slab_bot_dia"],  d["rebar_slab_bot_spc"])
        As_slab_top = _As(d["rebar_slab_top_dia"],  d["rebar_slab_top_spc"])

        cc1, cc2, cc3, cc4 = st.columns(4)
        cc1.metric("As Tarik Dinding",  f"{As_tension:.0f} mm²/m")
        cc2.metric("As Tekan Dinding",  f"{As_comp:.0f} mm²/m")
        cc3.metric("As Slab Bawah",     f"{As_slab_bot:.0f} mm²/m")
        cc4.metric("As Slab Atas",      f"{As_slab_top:.0f} mm²/m")

        d["As_tension"]  = As_tension
        d["As_comp"]     = As_comp
        d["As_slab_bot"] = As_slab_bot
        d["As_slab_top"] = As_slab_top
    return d


# =============================================================================
# PUBLIC API
# =============================================================================

def render_input(lang: str, condition: str) -> dict:
    st.markdown(
        f"### {t('step_input', lang)}  —  "
        f"**{condition}**"
    )

    # Placeholder for illustrations (filled after input collected)
    ill = st.empty()
    st.divider()

    # 1. UD dimensions
    d_ud = _sec_ud_dimensions(lang)
    ta   = d_ud["ud_wall_thick_top"]
    Wo   = d_ud["ud_inner_width"]

    # 2. CU dimensions (only if condition has CU)
    if condition in ("Kondisi 1", "Kondisi 2"):
        d_cu = _sec_cu_dimensions(lang, ta, Wo)
    else:
        d_cu = {
            "cu_gap": 0, "cu_thick_centre": 0,
            "cu_te_cu": 0, "cu_length": 0, "cu_inner_span": 0,
        }

    # 3. Vehicle
    d_veh = _sec_vehicle(lang)

    # 4. Material
    d_mat = _sec_material(lang)

    # 5. Soil
    d_soil = _sec_soil(lang, condition)

    # 6. Loading
    d_load = _sec_loading(lang, condition)

    # 7. Connection
    gap = d_cu.get("cu_gap", 0)
    d_conn = _sec_connection(lang, condition, ta, gap)

    # 8. Rebar
    d_rebar = _sec_rebar(lang)

    # Assemble full dict
    data: dict = {}
    data.update(d_ud)
    data.update(d_cu)
    data.update(d_veh)
    data.update(d_mat)
    data.update(d_soil)
    data.update(d_load)
    data.update(d_conn)
    data.update(d_rebar)
    data["condition"] = condition
    data["lang"]      = lang

    # Derived effective depths
    cov = data["cover_clear"]
    stir_dia = 8   # assumed stirrup
    data["d_eff_tension"] = ta - cov - stir_dia - data["rebar_tension_dia"] / 2
    data["d_eff_comp"]    = ta - cov - stir_dia - data["rebar_comp_dia"] / 2
    data["d_eff_slab"]    = data["ud_slab_thick"] - cov - stir_dia - data["rebar_slab_bot_dia"] / 2

    # Illustrations
    with ill.container():
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**{t('out_section_sketch', lang)}**")
            st.markdown(_draw_cross_section(data, condition), unsafe_allow_html=True)
        with col2:
            st.markdown(f"**{t('out_load_diagram', lang)}**")
            st.markdown(_draw_load_schematic(data, condition), unsafe_allow_html=True)

    st.session_state["input_data"] = data
    return data
