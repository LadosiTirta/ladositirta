import streamlit as st

# --- KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="Ladosi Engineering Portal",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- CSS UNTUK TAMPILAN PROFESIONAL (SUDAH FIX WARNA DI HP) ---
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
        color: #1a1a1a; /* FIX: Memaksa teks jadi gelap agar tidak hilang di HP */
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


# --- NAVIGASI CEPAT DI HALAMAN UTAMA ---
st.markdown("### 📋 PILIH PROGRAM PERHITUNGAN DI BAWAH INI:")
st.info("Klik salah satu tombol di bawah ini untuk langsung menuju halaman perhitungan.")

col_nav1, col_nav2, col_nav3 = st.columns(3)

# =====================================================================
# PERHATIAN: Ganti teks di dalam "pages/..." sesuai nama file asli di GitHub
# =====================================================================
with col_nav1:
    # Contoh jika nama file aslinya Lentur_Balok.py atau Lentur Balok.py
    st.page_link("pages/Lentur Balok.py", label="Lentur Balok", icon="📏") 
with col_nav2:
    st.page_link("pages/kolomC.py", label="Kolom C", icon="🏢")
with col_nav3:
    st.page_link("pages/HCS Design.py", label="HCS Design", icon="⚙️")

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
            <li><b>Efisien & Cepat:</b> Membantu konsultan menghemat waktu dalam penyusunan laporan teknis.</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("### 🏗️ Modul Perhitungan Tersedia")
    st.markdown("""
    Modul yang saat ini tersedia:
    * **Lentur Balok Beton:** Analisis kapasitas penampang balok persegi (SNI 2847:2019).
    * **Lentur Kolom Beton:** (Segera Hadir) Analisis kolom pendek simetris.
    * **Modul Lainnya:** Sedang dalam tahap verifikasi akademisi.
    """)

# --- FOOTER ---
st.markdown("---")
st.markdown(
    "<p style='text-align:center; color: #888; font-size: 0.8rem;'>"
    "&copy; 2026 Ladosi Engineering Project | Dikembangkan untuk kemajuan infrastruktur Indonesia"
    "</p>", 
    unsafe_allow_html=True
)
