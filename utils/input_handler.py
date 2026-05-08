# utils/input_handler.py
# Penanganan input data tanah dan parameter tiang
# Mendukung dua cara input: manual (st.data_editor) dan upload Excel

import streamlit as st
import pandas as pd
import numpy as np

# =============================================================
# KONSTANTA NAMA KOLOM TABEL DATA TANAH
# =============================================================
KOLOM_TANAH = {
    "no":       "No.",
    "z_atas":   "Kedalaman Atas (m)",
    "z_bawah":  "Kedalaman Bawah (m)",
    "jenis":    "Jenis Tanah",
    "spt":      "SPT-N (pukulan)",
    "cu":       "Cu (kPa)",
    "phi":      "φ (°)",
    "gamma":    "γ (kN/m³)",
}

JENIS_TANAH_OPSI = [
    "Lempung sangat lunak",
    "Lempung lunak",
    "Lempung sedang",
    "Lempung kaku",
    "Lempung sangat kaku",
    "Pasir lepas",
    "Pasir sedang",
    "Pasir padat",
    "Lanau",
    "Kerikil",
]

# Data contoh default untuk memudahkan user memulai
DATA_TANAH_DEFAULT = pd.DataFrame({
    KOLOM_TANAH["no"]:     [1, 2, 3, 4],
    KOLOM_TANAH["z_atas"]: [0.0, 3.0, 8.0, 15.0],
    KOLOM_TANAH["z_bawah"]:[3.0, 8.0, 15.0, 25.0],
    KOLOM_TANAH["jenis"]:  ["Lempung lunak", "Lempung sedang", "Pasir sedang", "Pasir padat"],
    KOLOM_TANAH["spt"]:    [4, 10, 22, 40],
    KOLOM_TANAH["cu"]:     [20.0, 40.0, 0.0, 0.0],
    KOLOM_TANAH["phi"]:    [0.0, 0.0, 30.0, 35.0],
    KOLOM_TANAH["gamma"]:  [16.0, 17.0, 18.0, 19.0],
})


def _buat_template_excel_lengkap() -> bytes:
    """
    Membuat template Excel form input data tanah yang lengkap:
    - Baris header berwarna
    - Contoh data 4 lapisan
    - Baris & kolom batas dengan keterangan
    - Petunjuk pengisian
    Mengembalikan bytes siap download.
    """
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, Protection
    from openpyxl.utils import get_column_letter

    wb  = Workbook()
    ws  = wb.active
    ws.title = "Data_Tanah"

    # -- Style --
    BIRU   = "1A5376"; KUNING = "FFF9C4"; HIJAU = "E8F8E8"
    ABU    = "F2F3F4"; MERAH  = "FADBD8"; PUTIH = "FFFFFF"
    f_hdr  = Font(name="Arial", bold=True, color="FFFFFF", size=10)
    f_body = Font(name="Arial", size=10)
    f_note = Font(name="Arial", size=9, italic=True, color="555555")
    f_bts  = Font(name="Arial", bold=True, size=9, color="922B21")
    al_c   = Alignment(horizontal="center", vertical="center", wrap_text=True)
    al_l   = Alignment(horizontal="left",   vertical="center", wrap_text=True)
    s      = Side(style="thin", color="AAAAAA")
    brd    = Border(left=s, right=s, top=s, bottom=s)

    def sel(r, c, val=None, bg=None, font=None, align=None, w=None):
        cell = ws.cell(r, c, val)
        if bg:    cell.fill   = PatternFill("solid", fgColor=bg)
        if font:  cell.font   = font
        if align: cell.alignment = align
        cell.border = brd
        return cell

    # -- Baris 1: judul --
    ws.merge_cells("A1:I1")
    t = ws["A1"]; t.value = "FORM INPUT DATA TANAH — Program Kapasitas Pondasi Tiang"
    t.font = Font(name="Arial", bold=True, size=12, color="FFFFFF")
    t.fill = PatternFill("solid", fgColor=BIRU)
    t.alignment = al_c
    ws.row_dimensions[1].height = 24

    # -- Baris 2: petunjuk --
    ws.merge_cells("A2:I2")
    p = ws["A2"]
    p.value = ("Isi data tanah mulai baris 5. Sel KUNING = wajib diisi. "
               "Cu=0 untuk pasir, φ=0 untuk lempung. "
               "JANGAN hapus/geser kolom. Simpan sebagai .xlsx lalu upload.")
    p.font = f_note; p.alignment = al_l
    p.fill = PatternFill("solid", fgColor="FEF9E7")
    ws.row_dimensions[2].height = 18

    # -- Baris 3: header kolom --
    headers = [
        ("No.", 5), ("Jenis Tanah", 20),
        ("Kedalaman Atas (m)", 14), ("Kedalaman Bawah (m)", 14),
        ("SPT-N (pukulan)", 12), ("Cu (kPa)", 10),
        ("φ (°)", 8), ("γ (kN/m³)", 10),
        ("Catatan", 20),
    ]
    for i, (nama, lebar) in enumerate(headers):
        c = i + 1
        cell = ws.cell(3, c, nama)
        cell.font  = f_hdr
        cell.fill  = PatternFill("solid", fgColor=BIRU)
        cell.alignment = al_c
        cell.border = brd
        ws.column_dimensions[get_column_letter(c)].width = lebar
    ws.row_dimensions[3].height = 30

    # -- Baris 4: sub-header satuan --
    satuan = ["—", "pilih jenis tanah", "m", "m", "pukulan", "kPa", "derajat", "kN/m³", "opsional"]
    for i, sat in enumerate(satuan):
        cell = ws.cell(4, i+1, sat)
        cell.font = Font(name="Arial", size=9, italic=True, color="555555")
        cell.fill = PatternFill("solid", fgColor="D6EAF8")
        cell.alignment = al_c; cell.border = brd
    ws.row_dimensions[4].height = 16

    # -- Data contoh (baris 5-8) --
    contoh = [
        (1, "Lempung lunak",  0.0,  3.0,  4, 20.0,  0.0, 16.0, "Lapisan permukaan"),
        (2, "Lempung sedang", 3.0,  8.0, 10, 40.0,  0.0, 17.0, ""),
        (3, "Pasir sedang",   8.0, 15.0, 22,  0.0, 30.0, 18.0, "Cu=0 karena pasir"),
        (4, "Pasir padat",   15.0, 25.0, 40,  0.0, 35.0, 19.0, ""),
    ]
    for i, baris in enumerate(contoh):
        r = 5 + i
        for j, val in enumerate(baris):
            bg = KUNING if j in [1,2,3,4,5,6,7] else ABU
            cell = ws.cell(r, j+1, val)
            cell.font = f_body; cell.alignment = al_c if j != 1 else al_l
            cell.fill = PatternFill("solid", fgColor=bg)
            cell.border = brd
        ws.row_dimensions[r].height = 18

    # -- Baris batas bawah (baris 9) --
    baris_batas = 9
    ws.merge_cells(f"A{baris_batas}:I{baris_batas}")
    bb = ws[f"A{baris_batas}"]
    bb.value = ("⬆ BATAS BAWAH DATA — Jika ingin menambah lapisan, "
                "INSERT ROW di atas baris ini (klik no. baris → Insert). "
                "Program membaca otomatis hingga baris terakhir berisi data.")
    bb.font  = f_bts
    bb.fill  = PatternFill("solid", fgColor=MERAH)
    bb.alignment = al_l; bb.border = brd
    ws.row_dimensions[baris_batas].height = 20

    # -- Kolom batas kanan (kolom J) --
    for r in range(3, baris_batas + 1):
        cell = ws.cell(r, 10,
            "◄ BATAS KANAN — jangan tambah kolom di kiri ini" if r == 3 else "")
        cell.font = f_bts if r == 3 else f_note
        cell.fill = PatternFill("solid", fgColor=MERAH)
        cell.alignment = al_c; cell.border = brd
    ws.column_dimensions["J"].width = 32

    # -- Sheet 2: Petunjuk --
    ws2 = wb.create_sheet("Petunjuk")
    petunjuk = [
        ("PETUNJUK PENGISIAN FORM DATA TANAH", True, BIRU, "FFFFFF"),
        ("", False, PUTIH, "000000"),
        ("1. JENIS TANAH", True, "D6EAF8", BIRU),
        ("   Pilih dari: Lempung sangat lunak / lunak / sedang / kaku / sangat kaku", False, PUTIH, "000000"),
        ("   atau: Pasir lepas / sedang / padat, Lanau, Kerikil", False, PUTIH, "000000"),
        ("", False, PUTIH, "000000"),
        ("2. KEDALAMAN", True, "D6EAF8", BIRU),
        ("   z atas lap. 1 = 0.0 (permukaan tanah)", False, PUTIH, "000000"),
        ("   z bawah lap. 1 = z atas lap. 2 (harus sambung, tidak boleh ada gap)", False, PUTIH, "000000"),
        ("", False, PUTIH, "000000"),
        ("3. SPT-N", True, "D6EAF8", BIRU),
        ("   Nilai pukulan per 30cm. Isi 0 jika tidak ada data SPT.", False, PUTIH, "000000"),
        ("", False, PUTIH, "000000"),
        ("4. Cu dan φ", True, "D6EAF8", BIRU),
        ("   Lempung: isi Cu (kPa), φ = 0", False, PUTIH, "000000"),
        ("   Pasir   : isi φ (°),  Cu = 0", False, PUTIH, "000000"),
        ("   Jika Cu & φ = 0: program estimasi otomatis dari SPT-N", False, PUTIH, "000000"),
        ("", False, PUTIH, "000000"),
        ("5. FORMAT FILE", True, "D6EAF8", BIRU),
        ("   Simpan sebagai .xlsx (Excel 2007 ke atas)", False, PUTIH, "000000"),
        ("   Google Sheets: File → Download → Microsoft Excel (.xlsx)", False, PUTIH, "000000"),
        ("   Format .xls (Excel 97-2003) juga diterima", False, PUTIH, "000000"),
        ("   Format .csv juga diterima (tanpa formatting)", False, PUTIH, "000000"),
        ("", False, PUTIH, "000000"),
        ("6. MENAMBAH LAPISAN", True, "D6EAF8", BIRU),
        ("   Klik nomor baris pada baris BATAS BAWAH → Insert Row Above", False, PUTIH, "000000"),
        ("   Isi data lapisan baru di baris yang baru ditambahkan", False, PUTIH, "000000"),
    ]
    ws2.column_dimensions["A"].width = 65
    for i, (teks, bold, bg, fc) in enumerate(petunjuk):
        cell = ws2.cell(i+1, 1, teks)
        cell.font = Font(name="Arial", bold=bold, size=10, color=fc)
        cell.fill = PatternFill("solid", fgColor=bg)
        cell.alignment = al_l
        ws2.row_dimensions[i+1].height = 18

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def render_input_tanah() -> pd.DataFrame:
    """
    Menampilkan antarmuka input data tanah.
    User bisa memilih: input manual via tabel, atau upload file Excel.
    Mengembalikan DataFrame data tanah yang sudah divalidasi.
    """
    st.subheader("Data Tanah")

    cara_input = st.radio(
        "Cara input data tanah:",
        options=["✏️ Input manual (edit tabel langsung)", "📂 Upload file Excel (.xlsx)"],
        horizontal=True,
        help="Pilih cara yang paling nyaman. Format kolom harus sama untuk kedua cara."
    )

    df_tanah = None

    # ----------------------------------------------------------
    # CARA 1: Input manual via st.data_editor
    # ----------------------------------------------------------
    if "manual" in cara_input:
        st.caption("Edit tabel di bawah langsung — klik sel untuk mengubah nilai.")

        # Inisialisasi session state agar tabel tidak reset saat widget lain berubah
        if "df_tanah_manual" not in st.session_state:
            st.session_state.df_tanah_manual = DATA_TANAH_DEFAULT.copy()

        col_tambah, col_hapus, col_reset = st.columns([1, 1, 1])
        with col_tambah:
            if st.button("➕ Tambah lapisan", use_container_width=True):
                baris_baru = pd.DataFrame({
                    KOLOM_TANAH["no"]:     [len(st.session_state.df_tanah_manual) + 1],
                    KOLOM_TANAH["z_atas"]: [st.session_state.df_tanah_manual[KOLOM_TANAH["z_bawah"]].iloc[-1]],
                    KOLOM_TANAH["z_bawah"]:[st.session_state.df_tanah_manual[KOLOM_TANAH["z_bawah"]].iloc[-1] + 3.0],
                    KOLOM_TANAH["jenis"]:  ["Lempung sedang"],
                    KOLOM_TANAH["spt"]:    [10],
                    KOLOM_TANAH["cu"]:     [30.0],
                    KOLOM_TANAH["phi"]:    [0.0],
                    KOLOM_TANAH["gamma"]:  [17.0],
                })
                st.session_state.df_tanah_manual = pd.concat(
                    [st.session_state.df_tanah_manual, baris_baru], ignore_index=True
                )
        with col_hapus:
            if st.button("➖ Hapus lapisan terakhir", use_container_width=True):
                if len(st.session_state.df_tanah_manual) > 1:
                    st.session_state.df_tanah_manual = st.session_state.df_tanah_manual.iloc[:-1].copy()
        with col_reset:
            if st.button("🔄 Reset ke default", use_container_width=True):
                st.session_state.df_tanah_manual = DATA_TANAH_DEFAULT.copy()

        df_edit = st.data_editor(
            st.session_state.df_tanah_manual,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                KOLOM_TANAH["no"]:     st.column_config.NumberColumn("No.", disabled=True, width="small"),
                KOLOM_TANAH["z_atas"]: st.column_config.NumberColumn("z atas (m)", min_value=0.0, step=0.5, format="%.1f"),
                KOLOM_TANAH["z_bawah"]:st.column_config.NumberColumn("z bawah (m)", min_value=0.1, step=0.5, format="%.1f"),
                KOLOM_TANAH["jenis"]:  st.column_config.SelectboxColumn("Jenis Tanah", options=JENIS_TANAH_OPSI),
                KOLOM_TANAH["spt"]:    st.column_config.NumberColumn("SPT-N", min_value=0, max_value=100, step=1),
                KOLOM_TANAH["cu"]:     st.column_config.NumberColumn("Cu (kPa)", min_value=0.0, step=5.0, format="%.1f",
                                           help="Isi 0 jika tanah pasir/non-kohesif"),
                KOLOM_TANAH["phi"]:    st.column_config.NumberColumn("φ (°)", min_value=0.0, max_value=45.0, step=1.0, format="%.1f",
                                           help="Isi 0 jika tanah lempung/kohesif"),
                KOLOM_TANAH["gamma"]:  st.column_config.NumberColumn("γ (kN/m³)", min_value=10.0, max_value=25.0, step=0.5, format="%.1f"),
            },
            hide_index=True,
            key="editor_tanah",
        )
        st.session_state.df_tanah_manual = df_edit.copy()
        df_tanah = df_edit.copy()

    # ----------------------------------------------------------
    # CARA 2: Upload file Excel
    # ----------------------------------------------------------
    else:
        st.caption("Upload file Excel dengan kolom sesuai template di bawah.")

        # Tombol download template — versi lengkap dengan keterangan
        col_tmpl, col_info = st.columns([1, 2])
        with col_tmpl:
            buf_tmpl = _buat_template_excel_lengkap()
            st.download_button(
                label="⬇️ Download Form Excel",
                data=buf_tmpl,
                file_name="form_input_data_tanah.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Download form Excel yang sudah terformat. Isi data, lalu upload kembali.",
                use_container_width=True,
            )
        with col_info:
            st.caption(
                "Form berisi contoh data, petunjuk pengisian, dan batas kolom/baris. "
                "Format: .xlsx (Excel 2007+). Google Sheets: File → Download → Excel (.xlsx)."
            )

        file_upload = st.file_uploader(
            "Upload file Excel data tanah:",
            type=["xlsx", "xls", "csv"],
            help="Upload form yang sudah diisi. Format: .xlsx, .xls, atau .csv."
        )

        if file_upload is not None:
            try:
                if file_upload.name.endswith('.csv'):
                    df_upload = pd.read_csv(file_upload)
                else:
                    # Coba baca dulu tanpa skip untuk deteksi format
                    df_cek = pd.read_excel(file_upload, nrows=3)
                    file_upload.seek(0)
                    # Jika kolom pertama bukan nama kolom standar (ada judul di baris 1-2),
                    # skip 2 baris pertama lalu skip lagi baris satuan (baris ke-4 = index 1 setelah header)
                    kolom_standar = KOLOM_TANAH["z_atas"]
                    if kolom_standar not in df_cek.columns:
                        # Format template lengkap: header di baris 3 (skiprows=2), ada baris satuan
                        df_upload = pd.read_excel(file_upload, header=2, skiprows=[3])
                        file_upload.seek(0)
                    else:
                        df_upload = pd.read_excel(file_upload)
                # Hapus baris yang kosong atau berisi teks batas
                if KOLOM_TANAH["z_atas"] in df_upload.columns:
                    # Filter: hanya baris yang nilai z_atas-nya numerik
                    df_upload = df_upload[
                        pd.to_numeric(df_upload[KOLOM_TANAH["z_atas"]], errors='coerce').notna()
                    ].copy()
                    df_upload = df_upload.reset_index(drop=True)

                # Cek kolom minimum yang wajib ada
                kolom_wajib = [KOLOM_TANAH["z_atas"], KOLOM_TANAH["z_bawah"],
                               KOLOM_TANAH["jenis"], KOLOM_TANAH["spt"]]
                kolom_hilang = [k for k in kolom_wajib if k not in df_upload.columns]
                if kolom_hilang:
                    st.error(f"Kolom berikut tidak ditemukan di file: {kolom_hilang}")
                    st.info("Pastikan nama kolom sama persis dengan template.")
                else:
                    # Isi kolom opsional yang mungkin tidak ada
                    for k, default in [(KOLOM_TANAH["cu"], 0.0),
                                       (KOLOM_TANAH["phi"], 0.0),
                                       (KOLOM_TANAH["gamma"], 17.0),
                                       (KOLOM_TANAH["no"], None)]:
                        if k not in df_upload.columns:
                            df_upload[k] = default
                    if KOLOM_TANAH["no"] not in df_upload.columns or df_upload[KOLOM_TANAH["no"]].isna().all():
                        df_upload[KOLOM_TANAH["no"]] = range(1, len(df_upload) + 1)

                    df_tanah = df_upload[list(KOLOM_TANAH.values())].copy()
                    st.success(f"File berhasil dibaca: {len(df_tanah)} lapisan tanah.")
                    st.dataframe(df_tanah, use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Gagal membaca file: {e}")
        else:
            st.info("Belum ada file yang diupload. Gunakan template di atas.")
            df_tanah = DATA_TANAH_DEFAULT.copy()

    return df_tanah


def validasi_data_tanah(df: pd.DataFrame) -> tuple[bool, list[str]]:
    """
    Memvalidasi DataFrame data tanah.
    Mengembalikan (valid: bool, pesan_error: list[str])
    """
    pesan = []

    if df is None or len(df) == 0:
        return False, ["Data tanah kosong. Masukkan minimal 1 lapisan tanah."]

    z_atas  = df[KOLOM_TANAH["z_atas"]].values
    z_bawah = df[KOLOM_TANAH["z_bawah"]].values

    # Cek kedalaman bawah > kedalaman atas
    for i, (za, zb) in enumerate(zip(z_atas, z_bawah)):
        if zb <= za:
            pesan.append(f"Lapisan {i+1}: kedalaman bawah ({zb} m) harus lebih besar dari kedalaman atas ({za} m).")

    # Cek kontinuitas antar lapisan (bawah lapisan i = atas lapisan i+1)
    for i in range(len(df) - 1):
        if abs(z_bawah[i] - z_atas[i+1]) > 0.01:
            pesan.append(
                f"Lapisan {i+1} → {i+2}: ada jeda/tumpang tindih kedalaman "
                f"({z_bawah[i]:.1f} m ≠ {z_atas[i+1]:.1f} m). "
                "Kedalaman bawah lapisan atas harus sama dengan kedalaman atas lapisan bawah."
            )

    # Cek SPT-N tidak negatif
    spt = df[KOLOM_TANAH["spt"]].values
    if any(s < 0 for s in spt):
        pesan.append("Nilai SPT-N tidak boleh negatif.")

    # Cek gamma masuk akal
    gamma = df[KOLOM_TANAH["gamma"]].values
    for i, g in enumerate(gamma):
        if g < 10.0 or g > 25.0:
            pesan.append(f"Lapisan {i+1}: γ = {g} kN/m³ di luar rentang wajar (10–25 kN/m³).")

    valid = len(pesan) == 0
    return valid, pesan


def render_input_tiang() -> dict:
    """
    Menampilkan input parameter tiang di sidebar.
    Mengembalikan dict parameter tiang.
    """
    st.sidebar.header("Parameter Tiang")

    tipe_tiang = st.sidebar.selectbox(
        "Tipe tiang",
        options=["Spun pile (bulat, pracetak)", "Square pile (kotak, pracetak)",
                 "Boredpile (beton cor, bulat)", "H-pile baja"],
        help="Tipe tiang mempengaruhi koefisien α/β dan metode end bearing."
    )

    # Dimensi tiang tergantung tipe
    if "Spun" in tipe_tiang or "Boredpile" in tipe_tiang:
        diameter = st.sidebar.number_input(
            "Diameter tiang (m)", min_value=0.10, max_value=2.50,
            value=0.40, step=0.05, format="%.2f"
        )
        lebar = None  # tidak dipakai untuk tiang bulat
    elif "Square" in tipe_tiang:
        lebar = st.sidebar.number_input(
            "Lebar sisi tiang (m)", min_value=0.10, max_value=1.50,
            value=0.35, step=0.05, format="%.2f"
        )
        diameter = None
    else:  # H-pile
        st.sidebar.caption("Dimensi H-pile (profil standar)")
        lebar_sayap = st.sidebar.number_input("Lebar sayap bf (m)", value=0.200, step=0.010, format="%.3f")
        tinggi_profil = st.sidebar.number_input("Tinggi profil d (m)", value=0.200, step=0.010, format="%.3f")
        tebal_badan = st.sidebar.number_input("Tebal badan tw (m)", value=0.009, step=0.001, format="%.3f")
        tebal_sayap = st.sidebar.number_input("Tebal sayap tf (m)", value=0.014, step=0.001, format="%.3f")
        diameter = None
        lebar = lebar_sayap

    kedalaman_tiang = st.sidebar.number_input(
        "Kedalaman tiang (m)", min_value=1.0, max_value=80.0,
        value=20.0, step=1.0, format="%.1f",
        help="Kedalaman dari muka tanah ke ujung bawah tiang."
    )

    variasi_kedalaman = st.sidebar.checkbox(
        "Hitung variasi kedalaman (untuk grafik Qtotal vs L)",
        value=True,
        help="Jika dicentang, program menghitung kapasitas untuk berbagai kedalaman tiang."
    )

    if variasi_kedalaman:
        col1, col2 = st.sidebar.columns(2)
        with col1:
            z_min = st.number_input("L min (m)", value=5.0, step=1.0, key="z_min_var")
        with col2:
            z_max = st.number_input("L maks (m)", value=kedalaman_tiang, step=1.0, key="z_max_var")
    else:
        z_min = kedalaman_tiang
        z_max = kedalaman_tiang

    # Material beton (tidak berlaku untuk H-pile)
    if "H-pile" not in tipe_tiang:
        material = st.sidebar.selectbox(
            "Mutu beton",
            options=["K-400 (fc' = 33.2 MPa)", "K-500 (fc' = 41.5 MPa)"],
        )
        fc_prime = 33.2 if "K-400" in material else 41.5
    else:
        material = "Baja A36 (fy = 250 MPa)"
        fc_prime = None

    muka_air = st.sidebar.number_input(
        "Kedalaman muka air tanah (m)", min_value=0.0, max_value=50.0,
        value=2.0, step=0.5, format="%.1f",
        help="Digunakan untuk menghitung tegangan efektif σ'v."
    )

    sf_tekan = st.sidebar.number_input(
        "Safety factor (tekan)", value=3.0, min_value=1.5, max_value=5.0,
        step=0.5, format="%.1f"
    )
    sf_tarik = st.sidebar.number_input(
        "Safety factor (tarik)", value=2.5, min_value=1.5, max_value=5.0,
        step=0.5, format="%.1f"
    )

    # Hitung properti geometri tiang
    if "Spun" in tipe_tiang or "Boredpile" in tipe_tiang:
        area_ujung  = np.pi / 4 * diameter**2
        keliling    = np.pi * diameter
        dim_label   = f"D = {diameter*100:.0f} cm"
    elif "Square" in tipe_tiang:
        area_ujung  = lebar**2
        keliling    = 4 * lebar
        diameter    = lebar  # gunakan sebagai referensi
        dim_label   = f"b = {lebar*100:.0f} cm"
    else:  # H-pile
        # Keliling H-pile (perimeter box untuk gesekan selimut)
        keliling    = 2 * (lebar_sayap + tinggi_profil)
        area_badan  = tinggi_profil * tebal_badan
        area_sayap  = 2 * lebar_sayap * tebal_sayap
        area_profil = area_badan + area_sayap
        area_ujung  = lebar_sayap * tinggi_profil  # plug area
        diameter    = (lebar_sayap + tinggi_profil) / 2  # ekuivalen
        dim_label   = f"bf={lebar_sayap*100:.0f}cm × d={tinggi_profil*100:.0f}cm"

    return {
        "tipe":             tipe_tiang,
        "diameter":         diameter,
        "lebar":            lebar if lebar else diameter,
        "area_ujung":       area_ujung,
        "keliling":         keliling,
        "kedalaman":        kedalaman_tiang,
        "variasi_kedalaman":variasi_kedalaman,
        "z_min":            z_min if variasi_kedalaman else kedalaman_tiang,
        "z_max":            z_max if variasi_kedalaman else kedalaman_tiang,
        "material":         material,
        "fc_prime":         fc_prime,
        "muka_air":         muka_air,
        "sf_tekan":         sf_tekan,
        "sf_tarik":         sf_tarik,
        "dim_label":        dim_label,
        "is_displacement":  "Spun" in tipe_tiang or "Square" in tipe_tiang,
        "is_bored":         "Boredpile" in tipe_tiang,
        "is_hpile":         "H-pile" in tipe_tiang,
    }
