# =============================================================================
# uditch/lang_dict.py  — Tahap A Revision
# =============================================================================

LANG = {
    "app_title":    {"ID": "Analisis Struktur U-Ditch Precast",          "EN": "Precast U-Ditch Structural Analysis"},
    "app_subtitle": {"ID": "Berdasarkan SNI 2847:2019 & AASHTO LRFD",   "EN": "Based on SNI 2847:2019 & AASHTO LRFD"},
    "language_label": {"ID": "🌐 Bahasa / Language", "EN": "🌐 Bahasa / Language"},

    # Sidebar
    "sidebar_condition": {"ID": "Pilih Kondisi Analisis", "EN": "Select Analysis Condition"},
    "condition_1": {"ID": "Kondisi 1 — UD di Samping Jalan (dengan CU)",  "EN": "Condition 1 — UD Alongside Road (with Cover)"},
    "condition_2": {"ID": "Kondisi 2 — UD sebagai Crossing (dengan CU)",  "EN": "Condition 2 — UD as Crossing (with Cover)"},
    "condition_3": {"ID": "Kondisi 3 — UD di Samping Jalan (tanpa CU)",   "EN": "Condition 3 — UD Alongside Road (no Cover)"},
    "sidebar_step":  {"ID": "Langkah",          "EN": "Step"},
    "step_input":    {"ID": "📋 Input Data",     "EN": "📋 Input Data"},
    "step_calc":     {"ID": "🧮 Perhitungan",    "EN": "🧮 Calculation"},
    "step_output":   {"ID": "📊 Hasil & Laporan","EN": "📊 Results & Report"},

    # Tabs
    "tab_input":       {"ID": "Input",       "EN": "Input"},
    "tab_calculation": {"ID": "Perhitungan", "EN": "Calculation"},
    "tab_output":      {"ID": "Output",      "EN": "Output"},

    # Section headers
    "sec_dimensions":    {"ID": "📐 Dimensi U-Ditch (UD)",           "EN": "📐 U-Ditch (UD) Dimensions"},
    "sec_cu_dimensions": {"ID": "📐 Dimensi Cover (CU)",             "EN": "📐 Cover (CU) Dimensions"},
    "sec_vehicle":       {"ID": "🚛 Data Kendaraan & Beban Gandar",  "EN": "🚛 Vehicle & Axle Load Data"},
    "sec_material":      {"ID": "🧱 Properti Material",              "EN": "🧱 Material Properties"},
    "sec_soil":          {"ID": "🌍 Properti Tanah",                 "EN": "🌍 Soil Properties"},
    "sec_loading":       {"ID": "⬇️ Parameter Pembebanan",           "EN": "⬇️ Loading Parameters"},
    "sec_connection":    {"ID": "🔗 Sambungan UD–CU & Gap",          "EN": "🔗 UD–CU Connection & Gap"},
    "sec_rebar":         {"ID": "🔩 Tulangan Rencana",               "EN": "🔩 Proposed Reinforcement"},
    "sec_load_factors":  {"ID": "⚖️ Faktor Beban & Reduksi Kekuatan","EN": "⚖️ Load & Strength Reduction Factors"},

    # UD dimension fields
    "ud_inner_width":      {"ID": "Lebar Dalam UD — Wo (mm)",       "EN": "UD Inner Width — Wo (mm)"},
    "ud_inner_height":     {"ID": "Tinggi Dalam UD — Ho (mm)",      "EN": "UD Inner Height — Ho (mm)"},
    "ud_wall_thick_top":   {"ID": "Tebal Dinding Atas — ta (mm)",   "EN": "Wall Thickness Top — ta (mm)"},
    "ud_wall_thick_bot":   {"ID": "Tebal Dinding Bawah — tb (mm)",  "EN": "Wall Thickness Bottom — tb (mm)"},
    "ud_slab_thick":       {"ID": "Tebal Slab Dasar — ts (mm)",     "EN": "Base Slab Thickness — ts (mm)"},
    "ud_length":           {"ID": "Panjang Segmen UD — L (m)",      "EN": "UD Segment Length — L (m)"},

    # CU dimension fields — corrected geometry
    "cu_gap": {
        "ID": "Gap antara CU dan dinding UD (mm)  [0 = tanpa gap]",
        "EN": "Gap between CU and UD wall (mm)  [0 = no gap]",
    },
    "cu_thick_centre": {
        "ID": "Tebal tengah CU — tcu (mm)  [bagian yang menggantung]",
        "EN": "CU centre thickness — tcu (mm)  [spanning portion]",
    },
    "cu_te_auto_label": {
        "ID": "Tebal tumpuan CU — te-cu = ta + gap",
        "EN": "CU bearing edge — te-cu = ta + gap",
    },
    "cu_length_auto_label": {
        "ID": "Panjang CU — L-CU = Wo + 2×ta",
        "EN": "CU Length — L-CU = Wo + 2×ta",
    },
    "cu_inner_span_label": {
        "ID": "Bentang bersih CU — = Wo − 2×gap",
        "EN": "CU clear span — = Wo − 2×gap",
    },

    # Vehicle fields
    "axle_load_G": {
        "ID": "Beban Gandar G = G1 = G2 (kN)  [SNI: 225 kN per gandar]",
        "EN": "Axle Load G = G1 = G2 (kN)  [SNI: 225 kN per axle]",
    },
    "wheel_spacing_x2": {
        "ID": "Jarak antar roda satu gandar — x2 (m)  [default: 1.75 m]",
        "EN": "Wheel spacing within axle — x2 (m)  [default: 1.75 m]",
    },
    "axle_spacing_y1": {
        "ID": "Jarak gandar G1–G2 — y1 (m)  [default: 5.0 m]",
        "EN": "Axle spacing G1–G2 — y1 (m)  [default: 5.0 m]",
    },
    "wheel_dist_x1": {
        "ID": "Jarak tepi luar UD ke roda terdekat — x1 (m)",
        "EN": "Distance from UD outer edge to nearest wheel — x1 (m)",
    },

    # Material fields
    "fc_prime":            {"ID": "Kuat Tekan Beton f'c (MPa)",        "EN": "Concrete Compressive Strength f'c (MPa)"},
    "fy_main":             {"ID": "Tegangan Leleh Tulangan fy (MPa)",  "EN": "Rebar Yield Strength fy (MPa)"},
    "fy_shear":            {"ID": "Tegangan Leleh Sengkang fyt (MPa)","EN": "Stirrup Yield Strength fyt (MPa)"},
    "concrete_unit_weight":{"ID": "Berat Jenis Beton γc (kN/m³)",     "EN": "Concrete Unit Weight γc (kN/m³)"},
    "cover_clear":         {"ID": "Selimut Beton Bersih (mm)",        "EN": "Clear Concrete Cover (mm)"},

    # Soil fields
    "soil_unit_weight":    {"ID": "Berat Jenis Tanah γs (kN/m³)",     "EN": "Soil Unit Weight γs (kN/m³)"},
    "soil_friction_angle": {"ID": "Sudut Geser Dalam φ (°)",          "EN": "Internal Friction Angle φ (°)"},
    "soil_cohesion":       {"ID": "Kohesi Tanah c (kPa)",             "EN": "Soil Cohesion c (kPa)"},
    "soil_fill_beside": {
        "ID": "Tinggi Timbunan di Samping UD — Hf (m)  [tinggi jalan di atas top UD/CU]",
        "EN": "Fill Height Beside UD — Hf (m)  [road height above top UD/CU]",
    },
    "fill_type_label":    {"ID": "Jenis Material Samping UD",         "EN": "Material Type Beside UD"},
    "fill_type_soil":     {"ID": "Tanah",                             "EN": "Soil"},
    "fill_type_asphalt":  {"ID": "Aspal + Tanah",                    "EN": "Asphalt + Soil"},
    "fill_type_concrete": {"ID": "Beton Rigid",                       "EN": "Rigid Concrete"},
    "lateral_pressure_option": {
        "ID": "Metode Tekanan Lateral Akibat Kendaraan",
        "EN": "Lateral Pressure Method from Vehicle",
    },
    "lat_opt_surcharge": {"ID": "Surcharge Ekivalen (SNI/AASHTO)", "EN": "Equivalent Surcharge (SNI/AASHTO)"},
    "lat_opt_point":     {"ID": "Beban Terpusat Boussinesq",       "EN": "Point Load Boussinesq"},
    "lat_opt_note_surcharge": {
        "ID": ("ℹ️ **Surcharge Ekivalen:** Beban roda dikonversi menjadi beban merata setinggi heq "
               "(AASHTO Tabel 3.11.6.4-2). Cocok untuk UD panjang/menerus."),
        "EN": ("ℹ️ **Equiv. Surcharge:** Wheel load converted to uniform surcharge height heq "
               "(AASHTO Table 3.11.6.4-2). Suitable for long/continuous UD."),
    },
    "lat_opt_note_point": {
        "ID": ("ℹ️ **Boussinesq Terpusat:** Tekanan lateral dihitung dari beban roda sebagai beban terpusat 3D, "
               "diintegrasikan sepanjang L. Lebih realistis untuk segmen pendek (1.2–2.4 m)."),
        "EN": ("ℹ️ **Boussinesq Point Load:** Lateral pressure from wheel as 3D point load, integrated over L. "
               "More realistic for short segments (1.2–2.4 m)."),
    },

    # Loading (crossing - Kondisi 2)
    "cover_load_type":        {"ID": "Jenis Beban di Atas CU",           "EN": "Load Type on Cover"},
    "cover_load_pedestrian":  {"ID": "Pejalan Kaki",                     "EN": "Pedestrian"},
    "cover_load_vehicle":     {"ID": "Beban Roda Kendaraan",             "EN": "Vehicular Wheel Load"},
    "cover_load_soil_wheel":  {"ID": "Timbunan Tanah + Beban Roda",      "EN": "Soil Backfill + Wheel Load"},
    "soil_fill_above_cu":     {"ID": "Tinggi Timbunan di Atas CU (m)",   "EN": "Soil Fill Height above CU (m)"},
    "pedestrian_load_kpa":    {"ID": "Beban Pejalan Kaki (kPa)",         "EN": "Pedestrian Load (kPa)"},

    # Load factors
    "load_factor_DL": {"ID": "Faktor Beban Mati γDL",   "EN": "Dead Load Factor γDL"},
    "load_factor_LL": {"ID": "Faktor Beban Hidup γLL",  "EN": "Live Load Factor γLL"},
    "phi_flexure":    {"ID": "Faktor Reduksi Lentur φ", "EN": "Flexure Reduction Factor φ"},
    "phi_shear":      {"ID": "Faktor Reduksi Geser φ",  "EN": "Shear Reduction Factor φ"},
    "phi_axial":      {"ID": "Faktor Reduksi Aksial φ", "EN": "Axial Reduction Factor φ"},

    # Connection & gap
    "conn_mechanism_title": {"ID": "Mekanisme Tahanan Puncak Dinding", "EN": "Wall Top Restraint Mechanism"},
    "conn_none":   {"ID": "Tanpa tahanan — kantilever murni",                      "EN": "No restraint — pure cantilever"},
    "conn_notch":  {"ID": "Tumpu notch CU (aktif setelah defleksi ≥ gap)",         "EN": "CU notch bearing (active after deflection ≥ gap)"},
    "conn_dowel":  {"ID": "Dowel di puncak dinding UD",                            "EN": "Dowels at UD wall top"},
    "dowel_diameter":  {"ID": "Diameter Dowel (mm)",         "EN": "Dowel Diameter (mm)"},
    "dowel_spacing":   {"ID": "Jarak Dowel — sd (mm)",       "EN": "Dowel Spacing — sd (mm)"},
    "dowel_embedment": {"ID": "Kedalaman Tanam Dowel (mm)",  "EN": "Dowel Embedment Depth (mm)"},
    "gap_note_zero": {
        "ID": "⚡ **Gap = 0:** CU langsung menahan defleksi → batang dengan tumpuan atas & bawah sejak awal.",
        "EN": "⚡ **Gap = 0:** CU immediately restrains deflection → top-bottom supported member from start.",
    },
    "cantilever_note": {
        "ID": ("⚠️ **Defleksi < Gap:** Dinding bekerja sebagai **kantilever murni**. "
               "Tulangan luar (tarik) didesain dari kondisi ini."),
        "EN": ("⚠️ **Deflection < Gap:** Wall acts as **pure cantilever**. "
               "Outer (tension) reinforcement designed from this condition."),
    },
    "propped_note": {
        "ID": ("✅ **Defleksi ≥ Gap → Tahanan Aktif:** Dinding berubah menjadi batang tumpuan atas-bawah. "
               "Tulangan dalam (tekan/tarik-balik) dicek untuk kondisi ini."),
        "EN": ("✅ **Deflection ≥ Gap → Restraint Active:** Wall becomes top-bottom supported. "
               "Inner reinforcement checked for this reversed-moment condition."),
    },

    # Rebar fields
    "rebar_wall_tension": {"ID": "Tulangan Tarik — Muka Luar Dinding", "EN": "Tension Rebar — Outer Wall Face"},
    "rebar_wall_comp":    {"ID": "Tulangan Tekan — Muka Dalam Dinding","EN": "Compression Rebar — Inner Wall Face"},
    "rebar_slab_bot":     {"ID": "Tulangan Slab — Bawah (Tarik)",      "EN": "Slab Rebar — Bottom (Tension)"},
    "rebar_slab_top":     {"ID": "Tulangan Slab — Atas (Tekan)",       "EN": "Slab Rebar — Top (Compression)"},
    "rebar_dia":          {"ID": "Diameter ø (mm)", "EN": "Diameter ø (mm)"},
    "rebar_spacing":      {"ID": "Jarak (mm)",       "EN": "Spacing (mm)"},

    # Calculation
    "calc_header":  {"ID": "🧮 Rincian Perhitungan",            "EN": "🧮 Calculation Detail"},
    "calc_sec_A":   {"ID": "A. Data & Geometri",                "EN": "A. Data & Geometry"},
    "calc_sec_B":   {"ID": "B. Tekanan Tanah & Kendaraan",      "EN": "B. Earth & Vehicle Pressure"},
    "calc_sec_C":   {"ID": "C. Gaya Dalam (Mu, Vu, Nu)",        "EN": "C. Internal Forces (Mu, Vu, Nu)"},
    "calc_sec_D":   {"ID": "D. Kapasitas Penampang",             "EN": "D. Section Capacity"},
    "calc_sec_E":   {"ID": "E. Kontrol & Kesimpulan",            "EN": "E. Checks & Conclusions"},

    # Output
    "out_header":          {"ID": "📊 Hasil Analisis",           "EN": "📊 Analysis Results"},
    "out_section_sketch":  {"ID": "Sketsa Penampang",            "EN": "Cross-Section Sketch"},
    "out_load_diagram":    {"ID": "Diagram Pembebanan",          "EN": "Loading Diagram"},
    "out_internal_forces": {"ID": "Diagram Gaya Dalam",          "EN": "Internal Forces Diagram"},
    "out_stress_block":    {"ID": "Blok Tegangan",               "EN": "Stress Block"},
    "out_capacity_chart":  {"ID": "Kapasitas vs Gaya Dalam",     "EN": "Capacity vs Demand"},
    "out_pm_curve":        {"ID": "Diagram Interaksi P–M",       "EN": "P–M Interaction Diagram"},
    "out_export_word":     {"ID": "📄 Ekspor ke Word (.docx)",   "EN": "📄 Export to Word (.docx)"},
    "out_export_pdf":      {"ID": "📑 Ekspor ke PDF",            "EN": "📑 Export to PDF"},

    # Messages
    "msg_ok":          {"ID": "✅ OK — Memenuhi",       "EN": "✅ OK — Adequate"},
    "msg_ng":          {"ID": "❌ NG — Tidak Memenuhi", "EN": "❌ NG — Not Adequate"},
    "msg_run_calc":    {"ID": "▶️ Jalankan Perhitungan","EN": "▶️ Run Calculation"},
    "msg_input_first": {"ID": "⚠️ Lengkapi input terlebih dahulu.",       "EN": "⚠️ Please complete the input first."},
    "msg_calc_first":  {"ID": "⚠️ Jalankan perhitungan terlebih dahulu.", "EN": "⚠️ Please run the calculation first."},

    # Footer
    "footer": {
        "ID": "Aplikasi ini dibuat untuk keperluan teknis perencanaan precast. Selalu verifikasi hasil dengan engineer yang bertanggung jawab.",
        "EN": "This application is intended for precast design engineering purposes. Always verify results with a responsible licensed engineer.",
    },
}


def t(key: str, lang: str = "ID") -> str:
    entry = LANG.get(key)
    if entry is None:
        return f"[{key}]"
    return entry.get(lang, entry.get("ID", f"[{key}]"))
