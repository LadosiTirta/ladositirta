import streamlit as st

# --- KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="Ladosi Engineering Portal",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- CSS UNTUK TAMPILAN PROFESIONAL & TOMBOL SIDEBAR DI HP ---
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
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #1a3c5e;
        height: 100%;
    }
    
    /* --- KODE KHUSUS MEMBESARKAN TOMBOL SIDEBAR ( >> ) DI HP --- */
    [data-testid="collapsedControl"] {
        background-color: #ff4b4b !important; /* Warna merah */
        color: white !important;
        border-radius: 5px;
        padding: 5px 15px;
        top: 15px;
        left: 15px;
        width: auto;
        display: flex;
        align-items: center;
        gap: 10px;
        z-index: 999999;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* Menambahkan teks "DAFTAR PROGRAM" setelah icon panah */
    [data-testid="collapsedControl"]::after {
        content: " DAFTAR PROGRAM";
        font-weight: bold;
        font-size: 14px;
        color: white;
        margin-left: 5px;
    }

    /* Membesarkan icon panah agar lebih putih dan jelas */
    [data-testid="collapsedControl"] svg {
        fill: white !important;
        width: 20px;
        height: 20px;
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
    st.info("👈 Silakan klik tombol **DAFTAR PROGRAM** berwarna merah di pojok kiri atas untuk memulai analisis.")
    
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
