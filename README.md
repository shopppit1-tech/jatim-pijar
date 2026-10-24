# JatimPijar — pantauan berita RSS dan draf AI harian

Website publik ini mengambil metadata RSS untuk Jawa Timur, lalu menampilkan paling banyak satu draf narasi dan satu ilustrasi AI baru per hari. **Frontend, arsip berita, gambar, dan hasil tetap di GitHub Pages/repository; Render hanya menjalankan endpoint backend yang memakai Gemini.**

## Cara kerja otomatis

- GitHub Actions memperbarui metadata RSS secara berkala.
- Workflow terpisah berjalan pukul 08.00 WIB, memilih berita terbaru yang belum pernah diproses, lalu memanggil backend Render.
- Ada batas keras satu percobaan per tanggal WIB. Jika berita sudah diproses atau permintaan gagal, workflow tidak mencoba lagi pada tanggal yang sama. Tombol **Run workflow** memakai batas yang sama.
- Actions menggunakan token GitHub sementara untuk memanggil backend. Server memeriksa token dan run terhadap repository/workflow yang benar; tidak perlu secret pemicu tambahan di GitHub.
- Backend memakai judul dan cuplikan metadata RSS; tidak membaca artikel lengkap. Teks dan gambar adalah draf/ilustrasi AI, bukan fakta terverifikasi atau foto kejadian.
- Maksimal 30 hasil tersimpan di repository dan ditampilkan di panel dengan tombol salin naskah, buka sumber, dan unduh ilustrasi.

## Setup layanan

1. Repository ini dipublikasikan melalui **Settings → Pages → Deploy from a branch → `main` → `/(root)`**. URL: <https://shopppit1-tech.github.io/jatim-pijar/>.
2. Web Service Render `jatim-pijar-ai` menggunakan paket **Free** dan region **Singapore**. Service menjalankan `render_service.py` dan health check `/health`.
3. Di Render → service → **Environment**, masukkan **key Gemini baru** sebagai `GEMINI_API_KEY`. Key hanya boleh berada sebagai environment secret Render—jangan commit, kirim lewat chat, atau simpan di GitHub. **Cabut key yang pernah dikirim lewat chat dan buat key baru di Google AI Studio; jangan pakai ulang key lama.**
4. Cek key tanpa membuat konten melalui **Actions → Verifikasi akses Gemini tanpa generasi → Run workflow**. Workflow ini hanya membaca daftar model; tidak menghasilkan teks atau gambar.
5. Jika key dan kedua model tersedia, jalankan **Actions → Buat narasi dan ilustrasi AI harian → Run workflow**. Hasil akan dikomit ke `main` dan tampil di GitHub Pages setelah Pages selesai deploy. Batas satu percobaan per hari tetap berlaku, termasuk jika generasi gagal.

## Paket gratis dan batasan

Render Free tidak dikenai biaya service, tetapi service dapat tidur setelah 15 menit tanpa trafik dan cold start dapat memerlukan sekitar satu menit. Render Free bersifat sementara/stateless; karena itu endpoint tidak menyimpan hasil di disk—GitHub repository tetap menjadi arsip. Waktu jadwal Actions dapat terlambat.

Biaya Gemini terpisah dari Render. Model gambar yang dipilih tidak memiliki free tier; perkiraan tarif yang diperiksa pada 24 Oktober 2026 sekitar US$0,0336 per gambar 1K atau sekitar US$1,01 untuk 30 gambar, belum termasuk teks dan pajak. Periksa kembali [harga resmi Gemini API](https://ai.google.dev/gemini-api/docs/pricing) karena tarif dapat berubah. Batas harian membatasi jumlah permintaan aplikasi, bukan tagihan atau kuota keseluruhan akun Gemini.

## Menjalankan lokal dan pemeriksaan

Tidak ada paket Python tambahan yang diperlukan untuk mengambil RSS, menjalankan backend, atau meminta generasi (key Render dan token GitHub Actions tentu dibutuhkan untuk panggilan nyata). Dari folder repository:

```bash
python3 scripts/fetch_news.py
python3 -m http.server 8000
```

Untuk pemeriksaan tanpa panggilan jaringan/Gemini:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/fetch_news.py scripts/generate_editorial.py scripts/request_render_generation.py scripts/verify_render_gemini.py render_service.py
node --check app.js
```

## Publikasi

Pilih **Konten siap posting**, salin narasi, periksa fakta ke sumber asli, lalu tempel manual ke kanal sosial. Pengiriman otomatis ke Facebook/YouTube tidak termasuk; itu memerlukan integrasi resmi dan izin platform.
