import os
import streamlit as st

# --- KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="Ladosi Engineering Portal",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- CSS UNTUK TAMPILAN PROFESIONAL ---
st.markdown("""
<style>
    .hero-section {
        background-color: #1a3c5e;
        padding: 3rem;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .feature-card {
        background: #f8f9fa;
        color: #1a1a1a;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #1a3c5e;
        height: 100%;
    }
</style>
""", unsafe_allow_html=True)

# --- HERO SECTION ---
st.markdown("""
<div class="hero-section">
    <h1>Selamat Datang di Ladosi Engineering Portal</h1>
    <p>Solusi Kalkulasi Struktur Terverifikasi & Profesional untuk Praktisi Teknik Sipil</p>
</div>
""", unsafe_allow_html=True)


# --- NAVIGASI OTOMATIS (Membaca file dari folder pages) ---
st.markdown("### 📋 DAFTAR PROGRAM PERHITUNGAN:")
st.info("Klik salah satu tombol di bawah ini untuk langsung menuju halaman perhitungan.")

pages_dir = "pages"
if os.path.exists(pages_dir):
    # Ambil semua file berakhiran .py di dalam folder pages dan urutkan
    page_files = sorted([f for f in os.listdir(pages_dir) if f.endswith(".py")])
    
    # Buat grid 3 kolom agar rapi
    cols = st.columns(3)
    
    for index, file_name in enumerate(page_files):
        # Logika membersihkan nama file untuk label tombol
        # Contoh: "1_Lentur_Balok.py" menjadi "Lentur Balok"
        nama_bersih = file_name.replace(".py", "")
        
        # Cek apakah ada angka dan underscore di depan (misal "1_")
        if "_" in nama_bersih and nama_bersih.split("_")[0].isdigit():
            # Potong angka di depannya
            nama_bersih = nama_bersih.split("_", 1)[1]
        
        # Ganti sisa underscore dengan spasi agar enak dibaca
        label_tombol = nama_bersih.replace("_", " ")
        
        # Tempatkan tombol secara berurutan di kolom 1, 2, 3, kembali ke 1, dst
        with cols[index % 3]:
            # Path harus sesuai aslinya (misal "pages/1_Lentur_Balok.py")
            st.page_link(f"pages/{file_name}", label=label_tombol, icon="⚙️")
else:
    st.warning("Folder navigasi belum tersedia.")

st.markdown("---")

# --- ISI UTAMA ---
col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🚀 Mengapa Menggunakan Ladosi?")
    st.markdown("""
    <div class="feature-card">
        <ul>
            <li><b>Akurasi Berdasarkan Standar:</b> Perhitungan disusun mengikuti urutan pasal SNI dan literatur yang berlaku.</li>
            <li><b>Laporan Siap Pakai:</b> Ekspor hasil ke format Word atau PDF dengan tata letak profesional.</li>
            <li><b>Transparansi Perhitungan:</b> Kami tidak memberikan angka instan, melainkan menjabarkan langkah demi langkah analisis.</li>
            <li><b>Efisien & Cepat:</b> Membantu engineer menghemat waktu dalam penyusunan laporan teknis.</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("### 🏗️ Pembaruan Modul")
    st.markdown("""
    Modul perhitungan yang tertera di atas akan terus bertambah seiring waktu. 
    Kami berkomitmen mengembangkan fitur tambahan dan menyempurnakan program yang ada untuk mendukung produktivitas kerja Anda.
    """)

# --- FOOTER ---
st.markdown("---")
st.markdown(
    "<p style='text-align:center; color: #888; font-size: 0.8rem;'>"
    "&copy; 2026 Ladosi Engineering Project | Dikembangkan untuk kemajuan infrastruktur Indonesia"
    "</p>", 
    unsafe_allow_html=True
)
