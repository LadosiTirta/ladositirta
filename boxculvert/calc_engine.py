# boxculvert/calc_engine.py
# Full structural analysis + reinforcement design + frame model for plotting

import math
import numpy as np

# ---------- Constants ----------
G_CONCRETE = 24.0      # kN/m³
G_WATER    = 9.81      # kN/m³
ES         = 200_000   # MPa, steel elastic modulus

# ===================== SOIL ARCHING (MARSTON) =====================
def compute_marston_load(H_m, Bd_m, gamma_soil, phi_deg, condition, Ka, cohesion=0.0):
    H, Bd = H_m, Bd_m
    if condition == "Embankment":
        p_full = gamma_soil * H
        return {
            "condition": "Embankment",
            "Cd": 1.0,
            "p_vert_on_top_slab": p_full,
            "formula_used": "No arching reduction – full weight γ × H"
        }
    else:  # Trench
        K = Ka
        mu = math.tan(math.radians(phi_deg))
        if Bd > 0 and H > 0:
            factor = 2 * K * mu * (H / Bd)
            if factor > 50:
                Cd = 1.0 / (2 * K * mu)
            else:
                Cd = (1.0 - math.exp(-factor)) / (2 * K * mu)
        else:
            Cd = 1.0
        W_per_m = Cd * gamma_soil * Bd * Bd   # kN/m length
        return {
            "condition": "Trench",
            "Cd": Cd,
            "total_load_per_m": W_per_m,
            "p_vert_on_top_slab": None,   # will be set later
            "formula_used": (
                f"Trench: Cd = (1 - exp(-2·K·μ·H/Bd)) / (2·K·μ)\n"
                f"with K={K:.3f}, μ={mu:.3f}, H/Bd={H/Bd:.2f} → Cd = {Cd:.4f}\n"
                f"W = Cd·γ·Bd² = {W_per_m:.2f} kN/m"
            )
        }

def compute_lateral_pressure(phi_deg):
    return math.tan(math.radians(45 - phi_deg/2)) ** 2

def compute_lateral_pressure_diagram(Ka, gamma_soil, H_fill, surcharge, H_wall, H_total_culvert):
    p_top = Ka * (surcharge + gamma_soil * H_fill)
    p_bot = Ka * (surcharge + gamma_soil * (H_fill + H_total_culvert))
    return {"p_top": p_top, "p_bot": p_bot}

def compute_internal_water_pressure(water_fraction, H_clear, t_bot, t_top):
    interior_bottom = t_bot / 2.0
    water_height_inside = water_fraction * H_clear
    y_water = interior_bottom + water_height_inside
    p_bot_interior = G_WATER * water_height_inside if water_height_inside > 0 else 0.0
    wall_top_y = H_clear + (t_top + t_bot)/2.0
    wall_bot_y = 0.0
    p_wall_top = G_WATER * (y_water - wall_top_y) if y_water >= wall_top_y else 0.0
    p_wall_bot = G_WATER * max(0, (y_water - wall_bot_y))
    p_bot_slab = G_WATER * max(0, (y_water - interior_bottom))
    return {
        "y_water": y_water,
        "p_wall_top": p_wall_top,
        "p_wall_bot": p_wall_bot,
        "p_bot_slab": p_bot_slab,
        "water_height_inside": water_height_inside
    }

# ===================== FRAME ANALYSIS HELPERS =====================
def _member_local_stiffness(E, A, I, L):
    c1 = E*A / L
    c4 = 6*E*I / (L*L)
    c5 = 12*E*I / (L*L*L)
    c2 = 4*E*I / L
    c3 = 2*E*I / L
    return np.array([
        [ c1,  0,   0, -c1,  0,   0],
        [  0, c5,  c4,   0, -c5, c4],
        [  0, c4,  c2,   0, -c4, c3],
        [-c1,  0,   0,  c1,  0,   0],
        [  0,-c5, -c4,   0,  c5,-c4],
        [  0, c4,  c3,   0, -c4, c2]
    ])

def _rotation_matrix(cosX, cosY):
    T = np.zeros((6,6))
    R = np.array([[cosX, cosY], [-cosY, cosX]])
    T[0:2,0:2] = R
    T[2,2] = 1
    T[3:5,3:5] = R
    T[5,5] = 1
    return T

def _apply_udl_fixed_end_forces(L, w_perp, w_axial=0):
    f = np.zeros(6)
    f[0] = -w_axial * L / 2.0
    f[3] = -w_axial * L / 2.0
    f[1] = -w_perp * L / 2.0
    f[2] = -w_perp * L*L / 12.0
    f[4] = -w_perp * L / 2.0
    f[5] =  w_perp * L*L / 12.0
    return f

def _apply_point_load_fixed_end_forces(L, P_perp, a, P_axial=0, a_axial=0):
    b = L - a
    f = np.zeros(6)
    f[0] = -P_axial * b / L
    f[3] = -P_axial * a / L
    RA = P_perp * b*b * (L + 2*a) / (L**3)
    RB = P_perp * a*a * (L + 2*b) / (L**3)
    MA = P_perp * a * b*b / (L**2)
    MB = P_perp * a*a * b / (L**2)
    f[1] = -RA
    f[2] = -MA
    f[4] = -RB
    f[5] =  MB
    return f

def _trap_fixed_end(L, q1, q2):
    f = np.zeros(6)
    f_uniform = _apply_udl_fixed_end_forces(L, q1, 0)
    f += f_uniform
    dq = q2 - q1
    if abs(dq) > 1e-9:
        f[1] += -3.0 * dq * L / 20.0
        f[2] += -dq * L*L / 30.0
        f[4] += -7.0 * dq * L / 20.0
        f[5] +=  dq * L*L / 20.0
    return f

def fixed_end_forces_for_load(load, L):
    if load['type'] == 'udl':
        return _apply_udl_fixed_end_forces(L, load['w_perp'], load.get('w_axial',0))
    elif load['type'] == 'point':
        return _apply_point_load_fixed_end_forces(L, load['P_perp'], load['a'],
                                                  load.get('P_axial',0), load.get('a_axial',0))
    elif load['type'] == 'trap':
        return _trap_fixed_end(L, load['q1'], load['q2'])
    else:
        return np.zeros(6)

def _solve_frame(nodes, elems, fixed_nodes):
    n_nodes = len(nodes)
    node_ids = list(nodes.keys())
    dof_per_node = 3
    total_dof = n_nodes * dof_per_node
    node_index = {nid: idx for idx, nid in enumerate(node_ids)}
    K = np.zeros((total_dof, total_dof))
    F = np.zeros(total_dof)
    member_info = []

    for el in elems:
        ni, nj = el['i'], el['j']
        xi, yi = nodes[ni]
        xj, yj = nodes[nj]
        dx, dy = xj - xi, yj - yi
        L = math.sqrt(dx*dx + dy*dy)
        cosX, cosY = dx/L, dy/L
        E = el['E']
        A = el['A']
        I = el['I']
        k_loc = _member_local_stiffness(E, A, I, L)
        T = _rotation_matrix(cosX, cosY)
        k_glob = T.T @ k_loc @ T

        dofs_i = [node_index[ni]*3 + d for d in range(3)]
        dofs_j = [node_index[nj]*3 + d for d in range(3)]
        indices = dofs_i + dofs_j
        for a in range(6):
            for b in range(6):
                K[indices[a], indices[b]] += k_glob[a, b]

        F_fixed_local = np.zeros(6)
        for load in el['loads']:
            F_fixed_local += fixed_end_forces_for_load(load, L)
        F_eq = -T.T @ F_fixed_local
        for d in range(6):
            F[indices[d]] += F_eq[d]

        member_info.append({
            'i': ni, 'j': nj, 'L': L, 'cosX': cosX, 'cosY': cosY,
            'E': E, 'A': A, 'I': I, 'k_loc': k_loc, 'T': T,
            'loads': el['loads'], 'indices': indices
        })

    fixed_dofs = []
    for nid in fixed_nodes:
        idx0 = node_index[nid]*3
        fixed_dofs.extend([idx0, idx0+1, idx0+2])
    free_dofs = [d for d in range(total_dof) if d not in fixed_dofs]
    if len(free_dofs) == 0:
        U_f = np.array([])
    else:
        K_ff = K[np.ix_(free_dofs, free_dofs)]
        F_f = F[free_dofs]
        U_f = np.linalg.solve(K_ff, F_f)
    U_global = np.zeros(total_dof)
    U_global[free_dofs] = U_f

    mem_forces = []
    for mem in member_info:
        ind = mem['indices']
        U_el_glob = U_global[ind]
        U_el_loc = mem['T'] @ U_el_glob
        F_fix_loc = np.zeros(6)
        for load in mem['loads']:
            F_fix_loc += fixed_end_forces_for_load(load, mem['L'])
        F_el_loc = mem['k_loc'] @ U_el_loc + F_fix_loc
        mem_forces.append({
            'i_node': mem['i'], 'j_node': mem['j'],
            'L': mem['L'],
            'N_i': F_el_loc[0], 'V_i': F_el_loc[1], 'M_i': F_el_loc[2],
            'N_j': F_el_loc[3], 'V_j': F_el_loc[4], 'M_j': F_el_loc[5]
        })
    return U_global, mem_forces, node_index, member_info

def _compute_forces_at_points(member, loads, x_points):
    L = member['L']
    N_i, V_i, M_i = member['N_i'], member['V_i'], member['M_i']
    forces = []
    for x in x_points:
        N, V, M = N_i, V_i, M_i + V_i * x
        for load in loads:
            if load['type'] == 'udl':
                w_perp = load['w_perp']
                w_axial = load.get('w_axial',0)
                if x > 0:
                    l_eff = min(x, L)
                    M -= w_perp * l_eff**2 / 2.0
                    V -= w_perp * l_eff
                    N -= w_axial * l_eff
            elif load['type'] == 'point':
                a = load['a']
                if a <= x:
                    P_perp = load['P_perp']
                    P_axial = load.get('P_axial',0)
                    M -= P_perp * (x - a)
                    V -= P_perp
                    N -= P_axial
            elif load['type'] == 'trap':
                q1, q2 = load['q1'], load['q2']
                if x > 0:
                    l_eff = min(x, L)
                    V_load = q1*l_eff + (q2-q1)*l_eff**2/(2*L)
                    M_load = q1*l_eff**2/2 + (q2-q1)*l_eff**3/(6*L)
                    V -= V_load
                    M -= M_load
        forces.append({'x': x, 'N': N, 'V': V, 'M': M})
    return forces

# =========== BUILD MODEL FOR A WATER LEVEL (for plotting) ===========
def get_frame_model(inputs, water_frac):
    L_clear = inputs["clear_span"] / 1000.0
    H_clear = inputs["clear_height"] / 1000.0
    t_top = inputs["t_top_slab"] / 1000.0
    t_bot = inputs["t_bottom_slab"] / 1000.0
    t_wall = inputs["t_wall"] / 1000.0
    Bd = inputs["Bd"] / 1000.0
    H_fill = inputs["H"] / 1000.0
    fc = inputs["fc"]
    phi_deg = inputs["friction_angle"]
    install_cond = inputs["install_condition"]
    surcharge = inputs["surcharge_uniform"]
    use_wheel = inputs["use_wheel_loads"]
    gamma_soil = inputs["soil_density"]

    H_wall = H_clear + (t_top + t_bot) / 2.0
    L_slab = L_clear + t_wall
    H_total_culvert = t_top + H_clear + t_bot

    A_top = t_top * 1.0; I_top = (1.0 * t_top**3) / 12.0
    A_bot = t_bot * 1.0; I_bot = (1.0 * t_bot**3) / 12.0
    A_wall = t_wall * 1.0; I_wall = (1.0 * t_wall**3) / 12.0

    E_conc = 4700.0 * math.sqrt(fc) * 1000.0

    Ka = compute_lateral_pressure(phi_deg)
    arch = compute_marston_load(H_fill, Bd, gamma_soil, phi_deg, install_cond, Ka)
    if install_cond == "Trench":
        B_out = L_slab
        p_soil = arch["total_load_per_m"] / B_out if B_out > 0 else 0.0
    else:
        p_soil = gamma_soil * H_fill

    lat = compute_lateral_pressure_diagram(Ka, gamma_soil, H_fill, surcharge, H_wall, H_total_culvert)
    w_sw_top = G_CONCRETE * t_top
    w_sw_bot = G_CONCRETE * t_bot
    water = compute_internal_water_pressure(water_frac, H_clear, t_bot, t_top)

    nodes = {1: (0.0, 0.0), 2: (0.0, H_wall), 3: (L_slab, H_wall), 4: (L_slab, 0.0)}

    elems = []
    # top slab
    top_loads = [{'type':'udl','w_perp': -p_soil - surcharge - w_sw_top, 'w_axial':0.0}]
    if use_wheel:
        whl = inputs["wheel_load"]
        sp = inputs["wheel_spacing"]/1000.0
        L_half = L_slab/2
        a1 = max(0.001, L_half - sp/2); a2 = max(0.001, L_half + sp/2)
        a1 = min(a1, L_slab-0.001); a2 = min(a2, L_slab-0.001)
        top_loads.append({'type':'point','P_perp':-whl,'a':a1})
        if a2 != a1:
            top_loads.append({'type':'point','P_perp':-whl,'a':a2})
    elems.append({'i':2,'j':3,'E':E_conc,'A':A_top,'I':I_top,'loads':top_loads})

    # bottom slab (1->4)
    bot_loads = [{'type':'udl','w_perp': -w_sw_bot + water['p_bot_slab'], 'w_axial':0.0}]
    elems.append({'i':1,'j':4,'E':E_conc,'A':A_bot,'I':I_bot,'loads':bot_loads})

    # left wall (1->2)
    q1 = lat['p_bot'] - water['p_wall_bot']
    q2 = lat['p_top'] - water['p_wall_top']
    elems.append({'i':1,'j':2,'E':E_conc,'A':A_wall,'I':I_wall,'loads':[{'type':'trap','q1':q1,'q2':q2}]})

    # right wall (4->3)
    elems.append({'i':4,'j':3,'E':E_conc,'A':A_wall,'I':I_wall,'loads':[{'type':'trap','q1':q1,'q2':q2}]})

    U, mem_forces, nidx, member_info = _solve_frame(nodes, elems, fixed_nodes=[1,4])
    return {'nodes': nodes, 'elements': elems, 'member_forces': mem_forces, 'member_info': member_info}

# =============== MAIN ANALYSIS ===============
def analyze_box_culvert(inputs):
    empty_model = get_frame_model(inputs, 0.0)
    full_model = get_frame_model(inputs, 1.0)

    def extract_crit(model):
        crit = {'top_slab':{}, 'bottom_slab':{}, 'left_wall':{}, 'right_wall':{}}
        for mem, el in zip(model['member_forces'], model['elements']):
            if el['i']==2 and el['j']==3:
                pts = [0, mem['L']/2, mem['L']]
                vals = _compute_forces_at_points(mem, el['loads'], pts)
                crit['top_slab'] = {'left': vals[0], 'midspan': vals[1], 'right': vals[2]}
            elif el['i']==1 and el['j']==4:
                pts = [0, mem['L']/2, mem['L']]
                vals = _compute_forces_at_points(mem, el['loads'], pts)
                crit['bottom_slab'] = {'left': vals[0], 'midspan': vals[1], 'right': vals[2]}
            elif el['i']==1 and el['j']==2:
                pts = [0, mem['L']/2, mem['L']]
                vals = _compute_forces_at_points(mem, el['loads'], pts)
                crit['left_wall'] = {'bottom': vals[0], 'mid': vals[1], 'top': vals[2]}
            elif el['i']==4 and el['j']==3:
                pts = [0, mem['L']/2, mem['L']]
                vals = _compute_forces_at_points(mem, el['loads'], pts)
                crit['right_wall'] = {'bottom': vals[0], 'mid': vals[1], 'top': vals[2]}
        return crit

    crit_empty = extract_crit(empty_model)
    crit_full = extract_crit(full_model)

    # arching info (just once)
    L_clear = inputs["clear_span"] / 1000.0
    t_wall = inputs["t_wall"] / 1000.0
    L_slab = L_clear + t_wall
    Bd = inputs["Bd"] / 1000.0
    H_fill = inputs["H"] / 1000.0
    gamma_soil = inputs["soil_density"]
    phi_deg = inputs["friction_angle"]
    Ka = compute_lateral_pressure(phi_deg)
    arch = compute_marston_load(H_fill, Bd, gamma_soil, phi_deg, inputs["install_condition"], Ka)
    if inputs["install_condition"] == "Trench":
        B_out = L_slab
        p_soil = arch["total_load_per_m"] / B_out if B_out > 0 else 0.0
        arch["p_vert_on_top_slab"] = p_soil
    else:
        arch["p_vert_on_top_slab"] = gamma_soil * H_fill

    # Lateral earth pressures (valid, no more '...')
    H_wall = inputs["clear_height"]/1000.0 + (inputs["t_top_slab"]+inputs["t_bottom_slab"])/2000.0
    H_total = inputs["t_top_slab"]/1000.0 + inputs["clear_height"]/1000.0 + inputs["t_bottom_slab"]/1000.0
    lat = compute_lateral_pressure_diagram(Ka, gamma_soil, H_fill, inputs["surcharge_uniform"], H_wall, H_total)

    return {
        "inputs_summary": {
            "L_clear_m": L_clear,
            "H_clear_m": inputs["clear_height"]/1000.0,
            "t_top_m": inputs["t_top_slab"]/1000.0,
            "t_bot_m": inputs["t_bottom_slab"]/1000.0,
            "t_wall_m": t_wall
        },
        "marston_arch": arch,
        "lateral_earth": lat,
        "water_pressure_empty": compute_internal_water_pressure(0.0, inputs["clear_height"]/1000.0,
                                                                inputs["t_bottom_slab"]/1000.0, inputs["t_top_slab"]/1000.0),
        "water_pressure_full": compute_internal_water_pressure(1.0, inputs["clear_height"]/1000.0,
                                                               inputs["t_bottom_slab"]/1000.0, inputs["t_top_slab"]/1000.0),
        "critical_forces": {
            "top_slab": {"empty": crit_empty["top_slab"], "full": crit_full["top_slab"]},
            "bottom_slab": {"empty": crit_empty["bottom_slab"], "full": crit_full["bottom_slab"]},
            "left_wall": {"empty": crit_empty["left_wall"], "full": crit_full["left_wall"]},
            "right_wall": {"empty": crit_empty["right_wall"], "full": crit_full["right_wall"]}
        },
        "frame_model_empty": empty_model,
        "frame_model_full": full_model
    }

# ===================== DESIGN FUNCTIONS (STEP 4) =====================
def design_slab_flexure(Mu, b, d, fc, fy, phi=0.9):
    steps = []
    steps.append("=== FLEXURAL REINFORCEMENT DESIGN (SLAB) ===")
    steps.append(f"Ultimate moment Mu = {Mu:.2f} kN·m/m, b = {b} mm, effective depth d = {d} mm")
    steps.append(f"Concrete f'c = {fc} MPa, steel fy = {fy} MPa, strength reduction φ = {phi}")

    Mu_Nmm = Mu * 1e6
    Mn_Nmm = Mu_Nmm / phi
    steps.append(f"Required nominal moment Mn = Mu/φ = {Mu_Nmm:.0f} / {phi} = {Mn_Nmm:.0f} N·mm")

    beta1 = 0.85 if fc <= 28 else max(0.65, 0.85 - 0.05 * (fc - 28) / 7)
    steps.append(f"β₁ = {beta1:.3f} (for f'c = {fc} MPa)")

    rho_max = 0.85 * beta1 * (fc / fy) * (0.003 / (0.003 + 0.005))
    steps.append(f"Maximum tension‑controlled reinforcement ratio ρ_max = {rho_max:.4f}")

    Rn = Mn_Nmm / (b * d**2)
    steps.append(f"Flexural resistance factor Rn = Mn / (b·d²) = {Mn_Nmm:.0f} / ({b}·{d}²) = {Rn:.3f} MPa")

    A = 0.59 * fy**2 / fc
    B = -fy
    C = Rn
    rho = (-B - math.sqrt(B**2 - 4*A*C)) / (2*A)
    steps.append(f"Solving 0.59·({fy}²/{fc})·ρ² - {fy}·ρ + {Rn:.3f} = 0")
    steps.append(f"  a = {A:.2f}, b = {B:.2f}, c = {C:.2f}")
    steps.append(f"  ρ = {rho:.4f}")

    rho_min = max(1.4 / fy, 0.25 * math.sqrt(fc) / fy)
    steps.append(f"Minimum reinforcement ratio ρ_min = {rho_min:.4f}")
    if rho < rho_min:
        rho = rho_min
        steps.append(f"  ρ < ρ_min → use ρ_min = {rho_min:.4f}")

    As_required = rho * b * d
    steps.append(f"Required steel area As = ρ·b·d = {rho:.4f}·{b}·{d} = {As_required:.1f} mm²/m")

    bar_diameter = 10
    bar_area = math.pi * bar_diameter**2 / 4
    spacing = 1000 * bar_area / As_required if As_required > 0 else 500
    steps.append(f"Using D{bar_diameter} bars (area = {bar_area:.1f} mm²), required spacing ≈ {spacing:.0f} mm c/c")

    spacing_practical = 150
    As_provided = 1000 * bar_area / spacing_practical
    steps.append(f"Provide D{bar_diameter} @ {spacing_practical} mm → As,prov = {As_provided:.1f} mm²/m")

    a = As_provided * fy / (0.85 * fc * b)
    c = a / beta1
    epsilon_t = 0.003 * (d - c) / c
    steps.append(f"Strain in tension steel εt = 0.003·(d - c)/c with a = {a:.1f} mm, c = {c:.1f} mm → εt = {epsilon_t:.4f}")
    if epsilon_t >= 0.005:
        steps.append("Section is tension‑controlled (φ = 0.9) ✓")
    else:
        steps.append("Section is NOT tension‑controlled, φ must be reduced (detailed check omitted)")

    return {"As_required": As_required, "As_provided": As_provided, "rho": rho, "rho_min": rho_min,
            "spacing": spacing_practical, "epsilon_t": epsilon_t, "steps": steps}

def design_slab_shear(Vu, b, d, fc, fy, As_provided=None, phi=0.75):
    steps = []
    steps.append("=== SHEAR CHECK (SLAB) ===")
    steps.append(f"Ultimate shear Vu = {Vu:.2f} kN/m, b = {b} mm, d = {d} mm, f'c = {fc} MPa, φ = {phi}")

    Vu_N = Vu * 1000
    Vc = 0.17 * math.sqrt(fc) * b * d
    steps.append(f"Vc = 0.17·√(f'c)·b·d = 0.17·√{fc}·{b}·{d} = {Vc:.0f} N = {Vc/1000:.2f} kN")
    phi_Vc = phi * Vc / 1000
    steps.append(f"φVc = {phi}·{Vc/1000:.2f} = {phi_Vc:.2f} kN")

    if Vu <= phi_Vc:
        steps.append(f"Vu ({Vu:.2f} kN) ≤ φVc → Shear reinforcement not required.")
        return {"Vu": Vu, "Vc": Vc/1000, "phi_Vc": phi_Vc, "shear_reinf_needed": False, "steps": steps}
    else:
        Vs_required = (Vu_N - phi*Vc) / phi
        steps.append("Vu > φVc → shear reinforcement required.")
        steps.append(f"Required Vs = (Vu - φVc)/φ = ({Vu_N:.0f} - {phi*Vc:.0f}) / {phi} = {Vs_required:.0f} N")
        Vs_max = 0.66 * math.sqrt(fc) * b * d
        steps.append(f"Maximum Vs = 0.66·√f'c·b·d = {Vs_max:.0f} N")
        if Vs_required > Vs_max:
            steps.append("Vs required exceeds maximum → increase section depth!")
        steps.append("Provide shear reinforcement (e.g., inclined bars or shear studs) – detailed design omitted.")
        return {"Vu": Vu, "Vc": Vc/1000, "phi_Vc": phi_Vc, "Vs_required": Vs_required/1000,
                "shear_reinf_needed": True, "steps": steps}

def _stress_steel(eps, fy):
    if eps >= fy/ES: return fy
    elif eps <= -fy/ES: return -fy
    return eps * ES

def generate_pm_curve(b, h, fc, fy, cover, bar_dia_comp, n_comp, bar_dia_tens, n_tens, n_points=30, e_cu=0.003):
    steps = []
    steps.append("=== COLUMN P‑M INTERACTION DIAGRAM (WALL) ===")
    steps.append(f"Section: b={b} mm, h={h} mm, f'c={fc} MPa, fy={fy} MPa")
    steps.append(f"Cover = {cover} mm, compression face bars: {n_comp} D{bar_dia_comp}, tension face: {n_tens} D{bar_dia_tens}")

    d1 = cover + bar_dia_comp/2
    d2 = h - cover - bar_dia_tens/2
    steps.append(f"Effective depth of compression steel d' = {d1:.1f} mm, tension steel d = {d2:.1f} mm")

    As_comp = n_comp * math.pi * bar_dia_comp**2 / 4
    As_tens = n_tens * math.pi * bar_dia_tens**2 / 4
    steps.append(f"Area of compression steel A's = {As_comp:.1f} mm²/m, tension steel As = {As_tens:.1f} mm²/m")

    beta1 = 0.85 if fc <= 28 else max(0.65, 0.85 - 0.05 * (fc - 28) / 7)
    points = []

    for i in range(n_points):
        if i == 0: c = 0.001
        elif i == n_points-1: c = h * 1.5
        else:
            log_c = math.log(0.001) + (i/(n_points-1))*(math.log(h*1.5)-math.log(0.001))
            c = math.exp(log_c)

        if c <= 1e-6: continue
        a = min(beta1 * c, h)
        Cc = 0.85 * fc * b * a

        eps_sc = e_cu * (c - d1) / c
        fs_sc = _stress_steel(eps_sc, fy)
        Cs = As_comp * (fs_sc - (0.85*fc if eps_sc >= 0 else 0))

        eps_st = e_cu * (d2 - c) / c
        fs_st = _stress_steel(eps_st, fy)
        Ts = As_tens * fs_st

        Pn = Cc + Cs - Ts
        Mn = Cc * (h/2 - a/2) + Cs * (h/2 - d1) + Ts * (d2 - h/2)
        points.append((Pn/1000, Mn/1e6))

    points.append(( - (As_comp+As_tens)*fy/1000, 0.0))
    points.sort(key=lambda x: x[0])
    return {"pm_points": points, "steps": steps}

def check_wall_capacity(pm_points, Pu, Mu):
    steps = []
    steps.append("=== WALL CAPACITY CHECK ===")
    steps.append(f"Applied axial force Pu = {Pu:.2f} kN, moment Mu = {Mu:.2f} kN·m/m")
    sorted_pts = sorted(pm_points, key=lambda x: x[0])
    P_vals = [p[0] for p in sorted_pts]
    M_vals = [p[1] for p in sorted_pts]

    if Pu < min(P_vals) or Pu > max(P_vals):
        steps.append("Pu outside the P‑M curve range → unsafe.")
        return {"safe": False, "steps": steps}

    for i in range(len(P_vals)-1):
        if P_vals[i] <= Pu <= P_vals[i+1]:
            if P_vals[i+1] - P_vals[i] == 0:
                M_cap = M_vals[i]
            else:
                M_cap = M_vals[i] + (M_vals[i+1]-M_vals[i]) * (Pu - P_vals[i]) / (P_vals[i+1]-P_vals[i])
            break

    steps.append(f"At Pu = {Pu:.2f} kN, the nominal moment capacity Mn = {M_cap:.2f} kN·m/m")
    phi = 0.75
    phi_Mn = phi * M_cap
    steps.append(f"Using φ = {phi}, φMn = {phi_Mn:.2f} kN·m/m")
    if abs(Mu) <= phi_Mn:
        steps.append(f"|Mu| = {abs(Mu):.2f} ≤ φMn = {phi_Mn:.2f} → OK, wall is safe.")
        return {"safe": True, "phi_Mn": phi_Mn, "steps": steps}
    else:
        steps.append(f"|Mu| = {abs(Mu):.2f} > φMn = {phi_Mn:.2f} → UNSAFE.")
        return {"safe": False, "phi_Mn": phi_Mn, "steps": steps}

def design_culvert_sections(analysis_results, inputs):
    fc = inputs["fc"]
    fy = inputs["fy"]
    t_top = inputs["t_top_slab"] / 1000.0
    t_bot = inputs["t_bottom_slab"] / 1000.0
    t_wall = inputs["t_wall"] / 1000.0

    cover_slab = 50; bar_dia = 16
    d_top = t_top * 1000 - cover_slab - bar_dia/2
    d_bot = t_bot * 1000 - cover_slab - bar_dia/2

    crit = analysis_results["critical_forces"]

    # Top slab max Mu and Vu
    top_empty = crit["top_slab"]["empty"]
    top_full = crit["top_slab"]["full"]
    Mu_top_empty = max(abs(top_empty.get('left',{}).get('M',0)), abs(top_empty.get('midspan',{}).get('M',0)),
                       abs(top_empty.get('right',{}).get('M',0)))
    Vu_top_empty = max(abs(top_empty.get('left',{}).get('V',0)), abs(top_empty.get('right',{}).get('V',0)))
    if top_full:
        Mu_top_full = max(abs(top_full.get('left',{}).get('M',0)), abs(top_full.get('midspan',{}).get('M',0)),
                           abs(top_full.get('right',{}).get('M',0)))
        Vu_top_full = max(abs(top_full.get('left',{}).get('V',0)), abs(top_full.get('right',{}).get('V',0)))
        Mu_top = max(Mu_top_empty, Mu_top_full)
        Vu_top = max(Vu_top_empty, Vu_top_full)
    else:
        Mu_top = Mu_top_empty
        Vu_top = Vu_top_empty

    # Bottom slab
    bot_empty = crit["bottom_slab"]["empty"]
    bot_full = crit["bottom_slab"]["full"]
    Mu_bot_empty = max(abs(bot_empty.get('left',{}).get('M',0)), abs(bot_empty.get('midspan',{}).get('M',0)),
                       abs(bot_empty.get('right',{}).get('M',0)))
    Vu_bot_empty = max(abs(bot_empty.get('left',{}).get('V',0)), abs(bot_empty.get('right',{}).get('V',0)))
    if bot_full:
        Mu_bot_full = max(abs(bot_full.get('left',{}).get('M',0)), abs(bot_full.get('midspan',{}).get('M',0)),
                           abs(bot_full.get('right',{}).get('M',0)))
        Vu_bot_full = max(abs(bot_full.get('left',{}).get('V',0)), abs(bot_full.get('right',{}).get('V',0)))
        Mu_bot = max(Mu_bot_empty, Mu_bot_full)
        Vu_bot = max(Vu_bot_empty, Vu_bot_full)
    else:
        Mu_bot = Mu_bot_empty
        Vu_bot = Vu_bot_empty

    # Walls
    left_empty = crit["left_wall"]["empty"]
    left_full = crit["left_wall"]["full"]
    combos = []
    for case in [left_empty, left_full if left_full else None]:
        if case is None: continue
        for sec in ['bottom','mid','top']:
            f = case.get(sec, {'N':0,'M':0})
            combos.append((f.get('N',0), f.get('M',0)))
    Pu_wall_max = max(abs(n) for n,m in combos)
    Mu_wall_max = max(abs(m) for n,m in combos)

    # Design top slab
    top_flex = design_slab_flexure(Mu_top, b=1000, d=d_top, fc=fc, fy=fy)
    top_shear = design_slab_shear(Vu_top, b=1000, d=d_top, fc=fc, fy=fy)

    # Design bottom slab
    bot_flex = design_slab_flexure(Mu_bot, b=1000, d=d_bot, fc=fc, fy=fy)
    bot_shear = design_slab_shear(Vu_bot, b=1000, d=d_bot, fc=fc, fy=fy)

    # Walls
    b_wall = 1000  # mm
    h_wall = t_wall * 1000  # mm
    cover_wall = 50  # mm
    bar_dia_wall = 16  # mm
    n_bars_each = int(b_wall / 150)
    pm_data = generate_pm_curve(
        b=b_wall, h=h_wall, fc=fc, fy=fy, cover=cover_wall,
        bar_dia_comp=bar_dia_wall, n_comp=n_bars_each,
        bar_dia_tens=bar_dia_wall, n_tens=n_bars_each
    )
    wall_check = check_wall_capacity(pm_data["pm_points"], Pu_wall_max, Mu_wall_max)

    return {
        "top_slab": {
            "Mu_max": Mu_top,
            "Vu_max": Vu_top,
            "flexural_design": top_flex,
            "shear_check": top_shear
        },
        "bottom_slab": {
            "Mu_max": Mu_bot,
            "Vu_max": Vu_bot,
            "flexural_design": bot_flex,
            "shear_check": bot_shear
        },
        "walls": {
            "Pu_max": Pu_wall_max,
            "Mu_max": Mu_wall_max,
            "pm_curve": pm_data["pm_points"],
            "pm_steps": pm_data["steps"],
            "capacity_check": wall_check
        }
    }
