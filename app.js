const $ = (id) => document.getElementById(id);
let allNews = [];

const esc = (value = '') => String(value).replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[char]));

function safeHttpUrl(value) {
  try {
    const url = new URL(String(value || ''), window.location.href);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch {
    return '';
  }
}

function dateLabel(value) {
  if (!value) return 'Tanggal tidak tersedia';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? 'Tanggal tidak tersedia'
    : date.toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' });
}

function makePost(item) {
  if (item.post_text) return item.post_text;
  const region = item.region || 'Jawa Timur';
  const title = item.title || 'Perkembangan terbaru';
  return `Pantauan ${region}: ${title}\n\nIsu yang perlu dicermati warga ${region} kali ini berkaitan dengan: ${title}. Informasi awal ini berasal dari metadata RSS, bukan ringkasan artikel penuh. Rincian kejadian dan perkembangan terbaru harus dipastikan dari sumber sebelum diperlakukan sebagai fakta lengkap.\n\nCatatan redaksi: format disusun secara lokal tanpa AI. Sumber pemantauan: ${item.source || 'RSS'}.\n\n#JatimPijar #InfoJawaTimur`;
}

async function loadNews() {
  $('news').innerHTML = '<div class="empty">Memuat berita…</div>';
  try {
    const response = await fetch(`news.json?v=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error('news.json belum tersedia');
    const payload = await response.json();
    allNews = Array.isArray(payload) ? payload : (payload.items || []);
    if (!Array.isArray(allNews)) allNews = [];
    allNews.sort((a, b) => new Date(b.published || 0) - new Date(a.published || 0));
    $('updated').textContent = `Diperbarui: ${dateLabel(payload.updated_at || allNews[0]?.fetched_at)}`;
    renderNews();
  } catch {
    allNews = [];
    $('news').innerHTML = '<div class="empty">Berita belum tersedia. Jalankan GitHub Actions “Update berita RSS”, lalu muat ulang halaman.</div>';
    $('updated').textContent = 'Belum ada data';
    $('count').textContent = '0 berita';
  }
}

function renderNews() {
  const query = $('search').value.toLowerCase().trim();
  const region = $('region').value;
  const list = allNews.filter((item) => {
    const searchable = `${item.title || ''} ${item.source || ''} ${item.region || ''}`.toLowerCase();
    return (!query || searchable.includes(query)) && (!region || item.region === region || item.region === 'Jawa Timur');
  });
  $('count').textContent = `${list.length} berita`;
  if (!list.length) {
    $('news').innerHTML = '<div class="empty">Tidak ada berita yang cocok.</div>';
    return;
  }

  $('news').innerHTML = list.map((item) => {
    const index = allNews.indexOf(item);
    const link = safeHttpUrl(item.link);
    const sourceAction = link
      ? `<a href="${esc(link)}" target="_blank" rel="noopener noreferrer">Buka sumber ↗</a>`
      : '<span class="source-link-disabled">Tautan sumber tidak tersedia</span>';
    return `<article class="news-card"><div class="meta"><span>${esc(item.region || 'Jawa Timur')}</span><span>•</span><span>${esc(dateLabel(item.published))}</span></div><h3>${esc(item.title || 'Judul tidak tersedia')}</h3><div class="source">Sumber: ${esc(item.source || 'Google News RSS')}</div><div class="card-actions"><button data-post-index="${index}">Konten siap posting</button>${sourceAction}</div></article>`;
  }).join('');

  document.querySelectorAll('[data-post-index]').forEach((button) => {
    button.addEventListener('click', () => showPost(allNews[Number(button.dataset.postIndex)]));
  });
}

function showPost(item) {
  if (!item) return;
  const draft = makePost(item);
  $('draft-title').value = `Pantauan ${item.region || 'Jawa Timur'}: ${item.title || ''}`;
  $('draft-body').value = draft;
  $('draft-caption').value = draft;
  $('draft-empty').hidden = true;
  $('draft-panel').hidden = false;
  $('draft-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

$('search').addEventListener('input', renderNews);
$('region').addEventListener('change', renderNews);
$('refresh').addEventListener('click', loadNews);
$('reset-draft').addEventListener('click', () => {
  $('draft-panel').hidden = true;
  $('draft-empty').hidden = false;
});
$('copy-draft').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText($('draft-caption').value);
    $('copy-draft').textContent = 'Tersalin';
    setTimeout(() => { $('copy-draft').textContent = 'Salin konten'; }, 1600);
  } catch {
    alert('Salin manual dari kolom konten.');
  }
});
$('download-draft').addEventListener('click', () => {
  const blobUrl = URL.createObjectURL(new Blob([$('draft-caption').value], { type: 'text/plain;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = blobUrl;
  anchor.download = 'konten-jatim-pijar.txt';
  anchor.click();
  URL.revokeObjectURL(blobUrl);
});

loadNews();
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('./sw.js').catch(() => {}));
}
