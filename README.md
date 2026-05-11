# Hitung Lentur Balok — Program Perhitungan Struktur

Program perhitungan struktur berbasis **Streamlit** untuk kebutuhan engineer

Standar: **SNI** (mengacu ACI, AISC, ASCE) dan referensi geoteknik internasional
(NAVFAC, USS Sheet Pile Manual).

---

## Daftar Program

| No | Menu | File | Fungsi |
|----|------|------|--------|
| 1 | Lentur Balok | `pages/1_Lentur_Balok.py` | Desain lentur balok beton bertulang |
| 2 | Kolom C      | `pages/2_kolomC.py`       | Desain kolom bulat / persegi |
| 3 | HCS Design   | `pages/3_HCS_Design.py`   | Desain pelat HCS (Hollow Core Slab) |
| 5 | Baja WF C    | `pages/5_Baja_WF_C.py`    | Desain balok baja profil WF |
| 6 | Sheet Pile   | `pages/6_SheetPile.py`    | Perhitungan turap / sheet pile |

---

## Struktur Folder

```
hitung-lentur-balok/              <- root repository
|
+-- app.py                         <- main app (menu utama Streamlit)
+-- requirements.txt               <- dependensi Python semua program
+-- README.md                      <- file ini (satu untuk semua)
|
+-- pages/                         <- halaman-halaman Streamlit
|   +-- 1_Lentur_Balok.py
|   +-- 2_kolomC.py
|   +-- 3_HCS_Design.py
|   +-- 5_Baja_WF_C.py
|   +-- 6_SheetPile.py            <- halaman UI turap
|
+-- sheetpile/                     <- modul perhitungan turap
    +-- __init__.py                <- WAJIB ADA (file kecil)
    +-- earth_pressure.py
    +-- stability.py
    +-- internal_forces.py
    +-- section_design.py
    +-- anchor_design.py
    +-- steel_sections.csv
```

**Catatan:** Program lain (Lentur Balok, Kolom, HCS, Baja WF) menyimpan
fungsi perhitungannya langsung di dalam file pages/ masing-masing.
Program SheetPile memiliki folder sheetpile/ tersendiri karena modulnya
lebih banyak dan kompleks.

---

## Cara Menjalankan Lokal

```bash
git clone https://github.com/LadosiTirta/hitung-lentur-balok.git
cd hitung-lentur-balok
pip install -r requirements.txt
streamlit run app.py
```

Buka browser: http://localhost:8501

---

## Program 6 — Sheet Pile (Turap)

Perhitungan turap baja dan beton pracetak secara lengkap.

**Standar:**
- SNI 8460:2017 Pasal 5, 9, 10 (Geoteknik)
- SNI 2847:2019 Pasal 9.6, 21.2, 22.5 (Beton)
- SNI 1729:2020 Pasal E, F, J (Baja)
- NAVFAC DM-7.01 Ch.4,6 dan DM-7.02 Ch.3,7
- USS Steel Sheet Pile Design Manual (1975)
- AISC 16th Ed. Ch. E, F, J
- Terzaghi (1943), Bjerrum-Eide (1956), Lane (1935)

**Fitur per tab:**

| Tab | Konten |
|-----|--------|
| 1 Tekanan Tanah | Ka/Kp/Ko, distribusi multi-lapisan, diagram |
| 2 Stabilitas | D_min, D_design, SF heave, SF piping |
| 3 Gaya Dalam | Diagram V dan M, M_max |
| 4 Penampang | Baja ASD atau Beton LRFD/SNI |
| 5 Angkur/Strut | Tie rod, waling, deadman, strut |
| 6 Ringkasan | Semua SF, download TXT dan PNG |

---

## Requirements

```
streamlit>=1.32.0
numpy>=1.26.0
scipy>=1.12.0
matplotlib>=3.8.0
pandas>=2.0.0
python-docx>=1.1.0
reportlab>=4.1.0
Pillow>=10.0.0
```

---

*Dibuat oleh: Structural Civil Engineer, Pabrik Beton Pracetak, Jabodetabek.*
