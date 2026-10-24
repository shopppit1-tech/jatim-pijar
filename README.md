# JatimPijar — pantauan berita RSS dan draf AI harian

Website statis untuk mengambil metadata RSS publik dan menyiapkan satu draf narasi berita beserta ilustrasi AI setiap hari.

## Otomatis
- GitHub Actions dijadwalkan setiap 15 menit untuk mengambil RSS terbaru.
- Workflow terpisah berjalan sekali sehari pada pukul 08.00 WIB dan hanya membuat konten jika berita terbaru belum pernah diproses.
- Batas keras satu percobaan generasi per tanggal WIB: satu teks narasi dan satu ilustrasi 1K. Jika tidak ada berita baru atau secret Gemini belum tersedia, tidak ada panggilan AI.
- Narasi memakai judul dan cuplikan RSS; sistem tidak membaca artikel penuh. Setiap gambar merupakan ilustrasi editorial, bukan foto atau bukti kejadian.
- Maksimal 30 draf AI terbaru tampil pada panel dengan tombol salin teks lengkap, tautan verifikasi sumber, dan unduh ilustrasi.
- Pencarian tidak menyertakan Malang Raya.

## Batasan penting
Narasi merupakan **draf AI dari metadata dan cuplikan RSS**, bukan ringkasan artikel lengkap atau fakta yang sudah diverifikasi. Teks dan gambar akan disajikan di situs publik agar dapat disalin. Periksa isi sumber asli sebelum memakai narasi; jangan menggambarkan ilustrasi AI sebagai foto nyata.

## Mulai cepat di GitHub
1. Buka **Settings → Pages**.
2. Pada **Build and deployment**, pilih **Deploy from a branch**, branch `main`, folder `/(root)`, lalu **Save**.
3. Pastikan Actions diizinkan berjalan. Workflow pembaruan menyatakan izin `contents: write` untuk menyimpan hasil RSS ke `news.json` dan `content.json`.
4. Dari tab **Actions**, jalankan **Update berita JatimPijar** dengan **Run workflow**. Push pertama ke `main` juga memicu pengambilan data.
5. Tunggu workflow selesai, lalu buka URL yang muncul di **Settings → Pages** dan muat ulang.

Untuk mengaktifkan narasi dan gambar AI, tambahkan secret repository bernama `GEMINI_API_KEY` melalui **Settings → Secrets and variables → Actions → New repository secret**. Jangan menaruh key di berkas, commit, atau chat. Key yang pernah dikirim di chat harus dicabut di Google AI Studio; buat key baru dan simpan langsung sebagai secret GitHub.

Setelah secret baru disimpan, buka **Actions → Buat narasi dan ilustrasi AI harian → Run workflow** untuk mencoba generasi pertama. Tombol manual dan jadwal harian memakai batas yang sama: paling banyak satu percobaan Gemini per tanggal WIB.

Jadwal berjalan pada pukul 01.00 UTC (08.00 WIB). Model gambar standar yang dipakai tidak memiliki free tier. Berdasarkan tarif Google yang diperiksa pada 24 Oktober 2026, satu gambar 1K sekitar US$0,0336; 30 gambar sekitar US$1,01, belum termasuk token teks/pajak. [Harga Gemini API](https://ai.google.dev/gemini-api/docs/pricing).

## Menjalankan lokal dan pemeriksaan
Tidak perlu memasang paket Python tambahan. Jalankan dari folder repository:

```bash
python3 scripts/fetch_news.py
python3 -m http.server 8000
```

Kemudian buka <http://localhost:8000>. Untuk pemeriksaan lokal, jalankan:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/fetch_news.py scripts/generate_editorial.py
node --check app.js
```

Pengambilan RSS tidak memerlukan key. Generasi narasi/gambar memerlukan `GEMINI_API_KEY` yang valid dan dapat memakai kuota atau biaya API. Jadwal GitHub bisa terlambat; pukul 08.00 WIB adalah waktu target, bukan jaminan tepat waktu.

## Publikasi
Pilih **Konten siap posting**, salin caption, lalu tempel ke media sosial. Pengiriman otomatis ke Facebook/YouTube tidak termasuk dalam paket ini; itu membutuhkan integrasi resmi dan izin platform.
