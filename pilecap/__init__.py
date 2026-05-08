"""
Paket pilecap — Perhitungan Pondasi Pilecap (Pile Cap)
=======================================================
Repositori  : LadosiTirta/ladositirta-pawon
Standar     : SNI 2847:2019, SNI 8460:2017
Dibuat oleh : Ladosi Engineering
Versi       : 2.0.0

CATATAN PENTING — mengapa __init__.py ini TIDAK mengimpor apa-apa:
  Import di __init__.py menyebabkan SEMUA modul (termasuk python-docx
  dan reportlab) dimuat saat Streamlit pertama kali memuat halaman.
  Jika satu paket gagal → halaman kosong tanpa pesan error.
  Solusi: setiap halaman (pages/*.py) mengimpor langsung dari modul
  yang dibutuhkan. report_pilecap diimpor secara LAZY (hanya saat
  tombol Generate Laporan ditekan).
"""

# Tidak ada import di sini — by design.
