#!/usr/bin/env python3
"""Fetch public Google News RSS metadata and prepare ready-to-share link posts locally."""
import hashlib, json, re, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET, html as htmlmod
from datetime import datetime, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime

ROOT=Path(__file__).resolve().parents[1]
QUERIES=[
("Surabaya","Surabaya Jawa Timur"),("Sidoarjo","Sidoarjo"),("Gresik","Gresik Jawa Timur"),
("Jombang","Jombang"),("Kediri","Kediri Jawa Timur"),("Mojokerto","Mojokerto"),
("Pasuruan","Pasuruan"),("Probolinggo","Probolinggo"),("Banyuwangi","Banyuwangi"),
("Jember","Jember Jawa Timur"),("Tuban","Tuban Jawa Timur"),("Bojonegoro","Bojonegoro"),
("Madiun","Madiun Jawa Timur"),("Ponorogo","Ponorogo"),("Trenggalek","Trenggalek"),
("Tulungagung","Tulungagung"),("Blitar","Blitar Jawa Timur"),("Pacitan","Pacitan"),
("Ngawi","Ngawi Jawa Timur"),("Magetan","Magetan"),("Lamongan","Lamongan"),
("Bangkalan","Bangkalan"),("Sampang","Sampang Madura"),("Pamekasan","Pamekasan"),
("Sumenep","Sumenep"),("Jawa Timur","Jawa Timur berita -Malang -Kabupaten Malang -Kota Malang")
]
REGION_TAGS = {
"Surabaya":"Surabaya","Sidoarjo":"Sidoarjo","Gresik":"Gresik","Jombang":"Jombang",
"Kediri":"Kediri","Mojokerto":"Mojokerto","Pasuruan":"Pasuruan","Probolinggo":"Probolinggo",
"Banyuwangi":"Banyuwangi","Jember":"Jember","Tuban":"Tuban","Bojonegoro":"Bojonegoro",
"Madiun":"Madiun","Ponorogo":"Ponorogo","Trenggalek":"Trenggalek","Tulungagung":"Tulungagung",
"Blitar":"Blitar","Pacitan":"Pacitan","Ngawi":"Ngawi","Magetan":"Magetan","Lamongan":"Lamongan",
"Bangkalan":"Bangkalan","Sampang":"Sampang","Pamekasan":"Pamekasan","Sumenep":"Sumenep"
}
def clean(s): return re.sub(r"\s+"," ",(s or "")).strip()
def strip_html(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return clean(htmlmod.unescape(value))

def editorial_headline(item):
    """Create a house-style headline frame; the underlying event title is an attributed topic."""
    region = item.get("region") or "Jawa Timur"
    title = clean(item.get("title") or "Perkembangan terbaru")
    # Remove a publisher suffix sometimes appended by Google News RSS.
    title = re.sub(r"\s+-\s+[^-]{2,80}$", "", title).strip()
    if not title:
        title = "Perkembangan terbaru"
    return f"Pantauan {region}: {title}"

def make_post(item):
    """A local editorial format from RSS metadata; no AI and no source URL in the social caption."""
    region = item.get("region") or "Jawa Timur"
    title = clean(item.get("title") or "Perkembangan terbaru")
    source = clean(item.get("source") or "sumber yang tercatat di RSS")
    date_text = item.get("published") or ""
    try:
        date_text = datetime.fromisoformat(date_text.replace("Z", "+00:00")).astimezone().strftime("%d %B %Y")
    except Exception:
        date_text = "tanggal publikasi tercatat di RSS"
    tags = ["#JatimPijar", "#InfoJawaTimur"]
    if region in REGION_TAGS:
        tags.append("#" + re.sub(r"[^A-Za-z0-9]", "", REGION_TAGS[region]))
    # This is explicitly framed as a newsroom brief, not a claim that the full article was summarized.
    return (
        f"{editorial_headline(item)}\n\n"
        f"Isu yang perlu dicermati warga {region} kali ini berkaitan dengan: {title}. "
        f"Informasi awal ini tercatat pada {date_text}. "
        f"Rincian kejadian, pihak terkait, lokasi spesifik, dan perkembangan terbaru perlu mengacu pada laporan sumber sebelum diperlakukan sebagai fakta lengkap.\n\n"
        f"Catatan redaksi: konten ini disusun dengan format lokal berdasarkan metadata RSS, tanpa AI. "
        f"Sumber pemantauan: {source}.\n\n" + " ".join(tags)
    )

def stable_id(link):
    """Return a repeatable short identifier for an RSS item URL."""
    return hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]

def main():
    rows=[]; seen=set(); successful_feeds=0
    try:
        previous=json.loads((ROOT/"news.json").read_text(encoding="utf-8"))
        previous_items=previous.get("items",[]) if isinstance(previous,dict) else []
        previous_updated=previous.get("updated_at") if isinstance(previous,dict) else None
    except (OSError, json.JSONDecodeError):
        previous_items=[]; previous_updated=None
    previous_by_id={item.get("id"):item for item in previous_items if isinstance(item,dict) and item.get("id")}
    for region, query in QUERIES:
        q=urllib.parse.quote(query + " when:7d")
        url=f"https://news.google.com/rss/search?q={q}&hl=id&gl=ID&ceid=ID:id"
        req=urllib.request.Request(url,headers={"User-Agent":"JatimPijarRSS/1.0 (public RSS reader)"})
        try:
            with urllib.request.urlopen(req,timeout=20) as resp: xml=resp.read()
            root=ET.fromstring(xml)
            successful_feeds+=1
            for item in root.findall(".//item"):
                title=clean(item.findtext("title")); link=clean(item.findtext("link"))
                pub=clean(item.findtext("pubDate")); description=strip_html(item.findtext("description")); source_node=item.find("source")
                source=clean(source_node.text if source_node is not None else "")
                if not title or not link or link in seen: continue
                if region=="Jawa Timur" and re.search(r"\b(malang|kabupaten malang|kota malang)\b",title,re.I): continue
                seen.add(link)
                try: published=parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat() if pub else None
                except Exception: published=None
                row={"id":stable_id(link),"title":title,"link":link,"source":source or "Google News RSS",
                     "published":published,"region":region,"description_context":description[:700]}
                row["post_text"]=make_post(row)
                old=previous_by_id.get(row["id"])
                if old and {k:v for k,v in old.items() if k!="fetched_at"}==row:
                    row["fetched_at"]=old.get("fetched_at") or datetime.now(timezone.utc).isoformat()
                else:
                    row["fetched_at"]=datetime.now(timezone.utc).isoformat()
                rows.append(row)
        except Exception as e: print(f"RSS gagal untuk {region}: {e}")
        time.sleep(.2)
    if successful_feeds==0:
        raise SystemExit("Semua feed RSS gagal dibaca; mempertahankan data terakhir.")
    rows.sort(key=lambda x:x.get("published") or "",reverse=True)
    rows=rows[:400]
    updated=previous_updated if previous_items==rows and previous_updated else datetime.now(timezone.utc).isoformat()
    payload={"updated_at":updated,"items":rows}
    (ROOT/"news.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    content={"updated_at":updated,"items":[{"id":n["id"],"title":n["title"],"region":n["region"],
        "source":n["source"],"link":n["link"],"published":n["published"],
        "caption":n["post_text"],"editorial_title":editorial_headline(n),"status":"DRAF FORMAT REDAKSI — CEK FAKTA"} for n in rows[:200]],
        "note":"Naskah berformat redaksi lokal, bukan ringkasan artikel penuh. Metadata dan tautan sumber disimpan untuk verifikasi; editor perlu mengecek fakta sebelum publikasi."}
    (ROOT/"content.json").write_text(json.dumps(content,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Tersimpan {len(rows)} berita RSS dan caption tautan.")
if __name__=="__main__": main()
