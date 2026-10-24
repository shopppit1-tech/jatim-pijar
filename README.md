# JatimPijar — pantauan berita RSS dan draf AI harian

Website publik ini mengambil metadata RSS untuk Jawa Timur, lalu menampilkan paling banyak satu draf narasi dan satu ilustrasi AI baru per hari. **Frontend, arsip berita, gambar, dan hasil tetap di GitHub Pages/repository; Render hanya menjalankan endpoint backend yang memakai Gemini.**

## Cara kerja otomatis

- GitHub Actions memperbarui metadata RSS secara berkala.
- Workflow terpisah berjalan pukul 08.00 WIB, memilih berita terbaru yang belum pernah diproses, lalu memanggil backend Render.
- Ada batas keras satu percobaan per tanggal WIB. Jika berita sudah diproses, konfigurasi belum lengkap, atau permintaan gagal, workflow tidak mencoba lagi pada tanggal yang sama. Tombol **Run workflow** memakai batas yang sama.
- Backend memakai judul dan cuplikan metadata RSS; tidak membaca artikel lengkap. Teks dan gambar adalah draf/ilustrasi AI, bukan fakta terverifikasi atau foto kejadian.
- Maksimal 30 hasil tersimpan di repository dan ditampilkan di panel dengan tombol salin naskah, buka sumber, dan unduh ilustrasi.

## Setup layanan

1. Repository ini dapat dipublikasikan melalui **Settings → Pages → Deploy from a branch → `main` → `/(root)`**. URL saat ini: <https://shopppit1-tech.github.io/jatim-pijar/>.
2. Buat Web Service Render dari Blueprint `render.yaml`, atau gunakan service `jatim-pijar-ai` yang sudah dibuat pada workspace. Tetap pilih paket **Free** dan region **Singapore**. Service menjalankan `render_service.py` dan health check `/health`.
3. Di Render → service → **Environment**, masukkan key Gemini baru sebagai `GEMINI_API_KEY`. Key hanya boleh berada sebagai environment secret Render—jangan commit, kirim lewat chat, atau simpan sebagai GitHub secret. **Cabut key yang pernah dikirim lewat chat dan buat key baru di Google AI Studio.**
4. Buat satu rahasia acak kuat untuk `RENDER_WEBHOOK_SECRET`. Isinya harus sama pada environment service Render dan **Settings → Secrets and variables → Actions → Secrets** di repository. Rahasia ini mengizinkan GitHub Actions memanggil endpoint backend; jangan masukkan ke URL atau log.
5. Tambahkan **Actions variable** `RENDER_API_URL` berisi URL dasar service, misalnya `https://jatim-pijar-ai.onrender.com` (tanpa path). URL harus HTTPS dan domain `.onrender.com`.
6. Setelah secret dan variable disimpan, buka **Actions → Buat narasi dan ilustrasi AI harian → Run workflow** untuk uji pertama. Hasil akan dikomit ke `main` dan tampil di GitHub Pages setelah Pages selesai deploy.

## Paket gratis dan batasan

Render Free tidak dikenai biaya service, tetapi service dapat tidur setelah 15 menit tanpa trafik dan cold start dapat memerlukan sekitar satu menit. Render Free bersifat sementara/stateless; karena itu endpoint tidak menyimpan hasil di disk—GitHub repository tetap menjadi arsip. Waktu jadwal Actions dapat terlambat.

Biaya Gemini terpisah dari Render. Model gambar yang dipilih tidak memiliki free tier; perkiraan tarif yang diperiksa pada 24 Oktober 2026 sekitar US$0,0336 per gambar 1K atau sekitar US$1,01 untuk 30 gambar, belum termasuk teks dan pajak. Periksa kembali [harga resmi Gemini API](https://ai.google.dev/gemini-api/docs/pricing) karena tarif dapat berubah. Batas harian membatasi jumlah permintaan aplikasi, bukan tagihan atau kuota keseluruhan akun Gemini.

## Menjalankan lokal dan pemeriksaan

Tidak ada paket Python tambahan yang diperlukan untuk mengambil RSS, menjalankan backend, atau meminta generasi (key dan endpoint tentu dibutuhkan untuk panggilan nyata). Dari folder repository:

```bash
python3 scripts/fetch_news.py
python3 -m http.server 8000
```

Untuk pemeriksaan tanpa panggilan jaringan/Gemini:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/fetch_news.py scripts/generate_editorial.py scripts/request_render_generation.py render_service.py
node --check app.js
```

## Publikasi

Pilih **Konten siap posting**, salin narasi, periksa fakta ke sumber asli, lalu tempel manual ke kanal sosial. Pengiriman otomatis ke Facebook/YouTube tidak termasuk; itu memerlukan integrasi resmi dan izin platform.
