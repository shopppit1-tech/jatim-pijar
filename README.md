# JatimPijar — media berita lokal tanpa AI dan API key

Website statis untuk mengambil metadata berita dari RSS publik dan menyiapkan caption berbagi tautan secara otomatis.

## Otomatis
- GitHub Actions dijadwalkan setiap 15 menit untuk mengambil RSS terbaru.
- Naskah berformat redaksi dibuat dari judul, wilayah, tanggal, nama sumber, dan hashtag menggunakan templat lokal. Tautan sumber disimpan sebagai catatan verifikasi, bukan dimasukkan ke caption publik.
- Tidak menggunakan AI, Gemini, OpenAI, API key, atau server Render.
- Pencarian tidak menyertakan Malang Raya.
- Caption siap disalin atau diunduh TXT dari website.

## Batasan penting
Konten otomatis adalah **naskah berformat redaksi dari metadata RSS**, bukan parafrasa atau ringkasan artikel penuh. Naskah tidak memasukkan URL artikel ke caption publik; nama sumber dicatat untuk verifikasi. Karena sistem tidak membaca isi artikel, naskah tidak boleh dianggap sebagai laporan lengkap atau langsung diperlakukan sebagai fakta terverifikasi. Untuk berita naratif yang akurat, isi sumber tetap perlu dibaca dan fakta dicek.

## Mulai cepat di GitHub
1. Buka **Settings → Pages**.
2. Pada **Build and deployment**, pilih **Deploy from a branch**, branch `main`, folder `/(root)`, lalu **Save**.
3. Pastikan Actions diizinkan berjalan. Workflow pembaruan menyatakan izin `contents: write` untuk menyimpan hasil RSS ke `news.json` dan `content.json`.
4. Dari tab **Actions**, jalankan **Update berita JatimPijar** dengan **Run workflow**. Push pertama ke `main` juga memicu pengambilan data.
5. Tunggu workflow selesai, lalu buka URL yang muncul di **Settings → Pages** dan muat ulang.

GitHub Pages pada paket gratis biasanya memerlukan repository publik untuk situs publik. Pertahankan repository privat jika kode tidak boleh dibagikan; bila Pages tidak tersedia, ubah visibilitas hanya setelah meninjau isi repository.

## Menjalankan lokal dan pemeriksaan
Tidak perlu memasang paket Python tambahan. Jalankan dari folder repository:

```bash
python3 scripts/fetch_news.py
python3 -m http.server 8000
```

Kemudian buka <http://localhost:8000>. Untuk pemeriksaan lokal, jalankan:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/fetch_news.py
node --check app.js
```

Tidak ada Secrets/API key yang perlu diisi. RSS publik tetap membutuhkan internet. GitHub Actions bisa terlambat menjalankan jadwal dan tidak menjamin tepat setiap 15 menit.

## Publikasi
Pilih **Konten siap posting**, salin caption, lalu tempel ke media sosial. Pengiriman otomatis ke Facebook/YouTube tidak termasuk dalam paket ini; itu membutuhkan integrasi resmi dan izin platform.
