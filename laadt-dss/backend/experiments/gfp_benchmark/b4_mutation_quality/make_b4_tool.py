"""B4 kodlama-aracı üreticisi — B4_coding_sheet.csv'den kendine-yeterli HTML üretir.

Kodlayıcı `B4_coding_tool.html`'i tarayıcıda açar, öğeleri kart-kart işaretler
(Akıcı? / Sonuç-değeri mi? + not), sonunda `B4_coding_<isim>.csv` indirir. KÖR
(guard-key gömülü DEĞİL). Otomatik-kayıt (localStorage). Her kartta:
 - kısa alıntı (>>değişen<< vurgulu)
 - "Tam metni göster" açılır bölüm (ham ⇄ markdown; gömülü render, CDN yok)

Kullanım: python make_b4_tool.py
"""
from __future__ import annotations
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHEET = HERE / "B4_coding_sheet.csv"
OUT = HERE / "B4_coding_tool.html"

CAT_SHORT = {"value-fabrication": "value-fabrication", "unit-swap": "unit-swap",
             "scale-swap": "scale-swap", "small-int": "small-int"}


def cat_key(label: str) -> str:
    for k in CAT_SHORT:
        if label.startswith(k):
            return k
    return label


def main() -> None:
    rows = list(csv.DictReader(SHEET.open(encoding="utf-8")))
    items = [{
        "id": r["item_id"], "set": r.get("set", ""),
        "cat": r["intended_category"], "catKey": cat_key(r["intended_category"]),
        "orig": r["original_sentence"], "mut": r["mutated_sentence"],
        "fullOrig": r.get("full_original", r["original_sentence"]),
        "fullMut": r.get("full_mutated", r["mutated_sentence"]),
    } for r in rows]
    html = _TEMPLATE.replace("/*__DATA__*/", json.dumps(items, ensure_ascii=False)) \
                    .replace("__N__", str(len(items)))
    OUT.write_text(html, encoding="utf-8")
    print(f"{len(items)} öğe → {OUT.name}  ({OUT.stat().st_size} B)")


_TEMPLATE = r"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>B4 — Mutasyon Kalitesi Kodlama</title>
<style>
  :root{--bg:#0f1115;--card:#1a1d24;--card2:#20242d;--ink:#e8eaed;--mut:#9aa2ad;
    --line:#2c313b;--accent:#4a90d9;--yes:#2e9e5b;--no:#c0453c;--mark:#ffd24a;--markink:#231c00;}
  @media (prefers-color-scheme: light){
    :root{--bg:#f4f6f9;--card:#fff;--card2:#f0f3f7;--ink:#1a1d24;--mut:#5a636e;
      --line:#dfe4ea;--accent:#2b6cb0;--mark:#ffe27a;--markink:#231c00;}}
  *{box-sizing:border-box}
  body{margin:0;font:15px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
    background:var(--bg);color:var(--ink);padding-bottom:80px}
  header{position:sticky;top:0;z-index:10;background:var(--card);border-bottom:1px solid var(--line);
    padding:12px 20px;display:flex;flex-wrap:wrap;gap:12px;align-items:center}
  header h1{font-size:16px;margin:0;flex:1 1 auto}
  .prog{font-size:13px;color:var(--mut)}
  .bar{height:6px;background:var(--line);border-radius:3px;flex-basis:100%;overflow:hidden}
  .bar>i{display:block;height:100%;background:var(--accent);width:0;transition:width .2s}
  input[type=text]{background:var(--card2);border:1px solid var(--line);color:var(--ink);
    border-radius:6px;padding:6px 10px;font-size:14px}
  .wrap{max-width:920px;margin:18px auto;padding:0 16px}
  .intro{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px;margin-bottom:18px}
  .intro summary{cursor:pointer;font-weight:600}
  .intro ul{margin:8px 0 0;padding-left:20px;color:var(--mut)}
  .intro b{color:var(--ink)}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:16px}
  .card.done{border-color:var(--accent)}
  .top{display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap}
  .id{font-weight:700;font-size:15px}
  .badge{font-size:11px;padding:2px 9px;border-radius:20px;background:var(--card2);color:var(--mut);border:1px solid var(--line)}
  .badge-set{color:#5aa0e0;border-color:#2c4463;font-weight:600}
  .b-value{color:#d98a4a;border-color:#5a4630}
  .b-unit{color:#4ab0a0;border-color:#2c5049}
  .b-scale{color:#8a7ad9;border-color:#3d3560}
  .b-small{color:#c07a9e;border-color:#5a3a4a}
  .lbl{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);margin:10px 0 4px}
  .txt{background:var(--card2);border:1px solid var(--line);border-radius:8px;padding:10px 12px;
    font-size:14px;white-space:pre-wrap;word-break:break-word;font-family:ui-monospace,Menlo,Consolas,monospace}
  mark{background:var(--mark);color:var(--markink);padding:1px 3px;border-radius:3px;font-weight:700}
  details.full{margin-top:10px}
  details.full>summary{cursor:pointer;font-size:13px;color:var(--accent);user-select:none}
  .vtoggle{display:inline-flex;border:1px solid var(--line);border-radius:7px;overflow:hidden;margin:8px 0}
  .vtoggle button{background:var(--card2);color:var(--ink);border:0;padding:4px 12px;font-size:12px;cursor:pointer}
  .vtoggle button.on{background:var(--accent);color:#fff}
  .rendered{background:var(--card2);border:1px solid var(--line);border-radius:8px;padding:10px 14px;
    font-size:14px;max-height:420px;overflow:auto;word-break:break-word}
  .rendered.raw{white-space:pre-wrap;font-family:ui-monospace,Menlo,Consolas,monospace}
  .rendered h4,.rendered h5,.rendered h6{margin:.5em 0 .3em;font-size:14px}
  .rendered table{border-collapse:collapse;margin:.4em 0;font-size:13px}
  .rendered th,.rendered td{border:1px solid var(--line);padding:3px 7px}
  .rendered code{background:var(--bg);padding:0 4px;border-radius:3px;font-size:13px}
  .rendered ul,.rendered ol{margin:.3em 0;padding-left:22px}
  .rendered hr{border:0;border-top:1px solid var(--line);margin:.6em 0}
  .q{display:flex;flex-wrap:wrap;gap:6px 22px;align-items:center;margin-top:14px}
  .q>.qlab{font-size:13px;font-weight:600;min-width:210px}
  .qhelp{flex-basis:100%;font-size:12px;color:var(--mut);margin-top:-2px;margin-bottom:2px}
  .seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
  .seg button{background:var(--card2);color:var(--ink);border:0;padding:6px 16px;font-size:14px;cursor:pointer}
  .seg button+button{border-left:1px solid var(--line)}
  .seg button.y.on{background:var(--yes);color:#fff}
  .seg button.n.on{background:var(--no);color:#fff}
  .note{width:100%;margin-top:10px;background:var(--card2);border:1px solid var(--line);color:var(--ink);
    border-radius:8px;padding:8px 10px;font-size:13px;resize:vertical;min-height:34px}
  footer{position:fixed;bottom:0;left:0;right:0;background:var(--card);border-top:1px solid var(--line);
    padding:12px 20px;display:flex;gap:12px;align-items:center;justify-content:flex-end}
  footer .status{margin-right:auto;color:var(--mut);font-size:13px}
  button.exp{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:9px 20px;font-size:14px;font-weight:600;cursor:pointer}
  button.exp:disabled{opacity:.5;cursor:not-allowed}
  button.rst{background:transparent;color:var(--mut);border:1px solid var(--line);border-radius:8px;padding:9px 16px;font-size:13px;cursor:pointer}
</style>
</head>
<body>
<header>
  <h1>B4 — G4 Enjeksiyon Mutasyon-Kalitesi Kodlama</h1>
  <label class="prog">Kodlayıcı adı: <input type="text" id="coder" placeholder="ör. Ayşe"></label>
  <span class="prog" id="count">0 / __N__</span>
  <div class="bar"><i id="fill"></i></div>
</header>

<div class="wrap">
  <details class="intro">
    <summary>Nasıl kodlanır? (özet — tam ölçütler B4_CODEBOOK.md)</summary>
    <ul>
      <li>Her kart bir enjekte-edilmiş öğedir. <b>Orijinal</b> → <b>Mutasyon</b>; değişen bölüm <mark>sarı</mark>. Kesik görüyorsan <b>“Tam metni göster”</b> ile tümünü aç (ham veya markdown).</li>
      <li><b>Akıcı?</b> — Mutasyon-sonrası cümle dilbilgisel/doğal mı? Kırık ek/uyumsuz ifade üretmişse <b>Hayır</b>. (Anlam yanlış olabilir; akıcılık ≠ doğruluk.)</li>
      <li><b>Bozulan şey gerçek bir SONUÇ değeri mi?</b> — <b>Evet</b>: mutasyon gerçek bir simülasyon-sonucu/karar-değeri üzerinde (NPV, tasarruf, üretim, gerilim, geri-ödeme yılı, kapasite…). <b>Hayır</b>: liste-numarası, başlık, tablo-şablonu, veri-isteği etiketi ya da soru cümlesi üzerinde (geçersiz test öğesi).</li>
      <li>KÖR: guard'ın kararını görmüyorsunuz. Bağımsız yargı verin. İlerleme otomatik kaydedilir.</li>
    </ul>
  </details>
  <div id="cards"></div>
</div>

<footer>
  <span class="status" id="status">İşaretleyin, kodlayıcı adını girin, sonra CSV indirin. (İlerleme otomatik kaydedilir; ad yazınca silinmez.)</span>
  <button class="rst" id="reset">Sıfırla</button>
  <button class="exp" id="export" disabled>CSV indir</button>
</footer>

<script>
const ITEMS = /*__DATA__*/;
const N = ITEMS.length;
const state = {};
const badgeCls = {"value-fabrication":"b-value","unit-swap":"b-unit","scale-swap":"b-scale","small-int":"b-small"};

function esc(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}
// kısa alıntı: esc + >>..<< -> <mark>
function renderExcerpt(t){ return esc(t).replace(/&gt;&gt;([\s\S]*?)&lt;&lt;/g,'<mark>$1</mark>'); }

// ---- gömülü markdown render (kendine-yeterli) ----
function inlineMd(s){
  s = esc(s);
  s = s.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
  s = s.replace(/`([^`]+)`/g,'<code>$1</code>');
  s = s.replace(/(^|[^*])\*([^*\s][^*]*)\*/g,'$1<em>$2</em>');
  return s;
}
function splitRow(s){ return s.replace(/^\s*\|/,'').replace(/\|\s*$/,'').split('|').map(x=>x.trim()); }
function renderMd(text){
  text = text.replace(/>>/g,'@@MK@@').replace(/<</g,'@@ME@@');   // vurgu sentinel (duz-ASCII)
  const L = text.split(/\r?\n/); let h='', i=0;
  while(i<L.length){
    let ln=L[i];
    if(/\|/.test(ln) && i+1<L.length && /\|/.test(L[i+1]) && /^[\s|:\-]+$/.test(L[i+1])){
      const head=splitRow(ln); i+=2; const rows=[];
      while(i<L.length && /\|/.test(L[i]) && L[i].trim()!==''){ rows.push(splitRow(L[i])); i++; }
      h+='<table><thead><tr>'+head.map(c=>'<th>'+inlineMd(c)+'</th>').join('')+'</tr></thead><tbody>'
        +rows.map(r=>'<tr>'+r.map(c=>'<td>'+inlineMd(c)+'</td>').join('')+'</tr>').join('')+'</tbody></table>'; continue;
    }
    let m;
    if(m=ln.match(/^(#{1,6})\s+(.*)$/)){ const lv=Math.min(6,m[1].length+3); h+='<h'+lv+'>'+inlineMd(m[2])+'</h'+lv+'>'; i++; continue; }
    if(/^\s*(---+|\*\*\*+)\s*$/.test(ln)){ h+='<hr>'; i++; continue; }
    if(/^\s*[-*]\s+/.test(ln)){ let it=[]; while(i<L.length && /^\s*[-*]\s+/.test(L[i])){ it.push(inlineMd(L[i].replace(/^\s*[-*]\s+/,''))); i++; } h+='<ul>'+it.map(x=>'<li>'+x+'</li>').join('')+'</ul>'; continue; }
    if(/^\s*\d+\.\s+/.test(ln)){ let it=[]; while(i<L.length && /^\s*\d+\.\s+/.test(L[i])){ it.push(inlineMd(L[i].replace(/^\s*\d+\.\s+/,''))); i++; } h+='<ol>'+it.map(x=>'<li>'+x+'</li>').join('')+'</ol>'; continue; }
    if(ln.trim()===''){ i++; continue; }
    let para=[ln]; i++;
    while(i<L.length && L[i].trim()!=='' && !/\|/.test(L[i]) && !/^(#{1,6}\s|\s*[-*]\s|\s*\d+\.\s|\s*(---+|\*\*\*+)\s*$)/.test(L[i])){ para.push(L[i]); i++; }
    h+='<p>'+para.map(inlineMd).join('<br>')+'</p>';
  }
  return h.replace(/@@MK@@/g,'<mark>').replace(/@@ME@@/g,'</mark>');
}
function renderFull(t, mode){ return mode==='md' ? renderMd(t) : renderExcerpt(t); }

// SABİT anahtar — kayıt kodlayıcı-adına BAĞLI DEĞİL (ad yazınca is silinmez).
const SAVE_KEY='b4:coding';
function coderName(){ return document.getElementById('coder').value.trim(); }
function save(){ localStorage.setItem(SAVE_KEY, JSON.stringify({coder:coderName(), answers:state})); }
function load(){  // yalnız sayfa açılışında bir kez
  let obj=null;
  try{ obj=JSON.parse(localStorage.getItem(SAVE_KEY)||'null'); }catch(e){}
  if(!obj){  // ESKI ad-anahtarli girdilerden en cok cevaplilar migrasyon (is kaybi onleme)
    let best=null,bestN=0;
    for(let i=0;i<localStorage.length;i++){ const k=localStorage.key(i);
      if(k && k.indexOf('b4:')===0 && k!==SAVE_KEY){
        try{ const a=JSON.parse(localStorage.getItem(k))||{};
          const n=Object.keys(a).filter(x=>a[x]&&(a[x].fluent!==undefined||a[x].cat!==undefined)).length;
          if(n>bestN){ bestN=n; best={coder:(k.slice(3)==='anon'?'':k.slice(3)), answers:a}; }
        }catch(e){} }
    }
    if(best) obj=best;
  }
  if(obj){ Object.assign(state, obj.answers||{});
    if(obj.coder && !coderName()) document.getElementById('coder').value=obj.coder; save(); }
  document.querySelectorAll('.card').forEach(applyState); refresh();
}
function resetAll(){
  if(!confirm('Tüm işaretlemeler silinip sıfırlanacak (yeni kodlayıcı için). Önce CSV indirdiniz mi?')) return;
  for(const k in state) delete state[k];
  localStorage.removeItem(SAVE_KEY);
  document.getElementById('coder').value='';
  document.querySelectorAll('.card').forEach(applyState);
  document.querySelectorAll('.note').forEach(n=>n.value=''); refresh();
}
function seg(id, field, val){ const st=state[id]||(state[id]={}); st[field]=val; save(); applyState(document.getElementById('c-'+id)); refresh(); }
function setNote(id, v){ const st=state[id]||(state[id]={}); st.note=v; save(); }

function applyState(card){
  if(!card) return; const id=card.dataset.id; const st=state[id]||{};
  card.querySelectorAll('.seg button').forEach(b=>b.classList.toggle('on', st[b.dataset.f]===b.dataset.v));
  card.classList.toggle('done', st.fluent!==undefined && st.cat!==undefined);
  const nb=card.querySelector('.note'); if(nb && st.note!==undefined && nb.value!==st.note) nb.value=st.note;
}
function refresh(){
  const done=ITEMS.filter(it=>{const s=state[it.id]||{};return s.fluent!==undefined&&s.cat!==undefined;}).length;
  document.getElementById('count').textContent=done+' / '+N;
  document.getElementById('fill').style.width=(100*done/N)+'%';
  document.getElementById('export').disabled=done<N;
  document.getElementById('status').textContent=done<N?(N-done)+' öğe kaldı.':'Tamam — CSV indirebilirsiniz.';
}
// tam-metin görünüm modu (kart-başına)
function setView(id, mode){
  const card=document.getElementById('c-'+id); const it=ITEMS.find(x=>x.id===id);
  card.querySelectorAll('.vtoggle button').forEach(b=>b.classList.toggle('on', b.dataset.v===mode));
  const cls='rendered'+(mode==='md'?'':' raw');
  card.querySelector('[data-full="orig"]').className=cls;
  card.querySelector('[data-full="orig"]').innerHTML=renderFull(it.fullOrig, mode);
  card.querySelector('[data-full="mut"]').className=cls;
  card.querySelector('[data-full="mut"]').innerHTML=renderFull(it.fullMut, mode);
}

function build(){
  document.getElementById('cards').innerHTML = ITEMS.map(it=>{
    const bc=badgeCls[it.catKey]||'';
    return `<div class="card" id="c-${it.id}" data-id="${it.id}">
      <div class="top"><span class="id">${it.id}</span>
        <span class="badge badge-set">${esc(it.set)}</span>
        <span class="badge ${bc}">${esc(it.cat)}</span></div>
      <div class="lbl">Orijinal (alıntı)</div><div class="txt">${renderExcerpt(it.orig)}</div>
      <div class="lbl">Mutasyon (alıntı)</div><div class="txt">${renderExcerpt(it.mut)}</div>
      <details class="full">
        <summary>Tam metni göster</summary>
        <div class="vtoggle">
          <button data-v="raw" class="on" onclick="setView('${it.id}','raw')">Ham</button>
          <button data-v="md" onclick="setView('${it.id}','md')">Markdown</button>
        </div>
        <div class="lbl">Tam orijinal</div><div class="rendered raw" data-full="orig"></div>
        <div class="lbl">Tam mutasyon</div><div class="rendered raw" data-full="mut"></div>
      </details>
      <div class="q"><span class="qlab">Akıcı? (fluent)</span>
        <div class="seg">
          <button class="y" data-f="fluent" data-v="Y" onclick="seg('${it.id}','fluent','Y')">Evet</button>
          <button class="n" data-f="fluent" data-v="N" onclick="seg('${it.id}','fluent','N')">Hayır</button>
        </div></div>
      <div class="q"><span class="qlab">Bozulan şey gerçek bir SONUÇ değeri mi?</span>
        <div class="seg">
          <button class="y" data-f="cat" data-v="Y" onclick="seg('${it.id}','cat','Y')">Evet</button>
          <button class="n" data-f="cat" data-v="N" onclick="seg('${it.id}','cat','N')">Hayır</button>
        </div>
        <div class="qhelp"><b>Evet</b> = NPV, tasarruf, üretim, gerilim, geri-ödeme yılı, kapasite gibi bir <b>sonuç/karar-değeri</b> bozuldu. <b>Hayır</b> = liste-numarası, başlık, tablo-şablonu, veri-isteği etiketi ya da soru üzerinde (geçersiz öğe).</div>
      </div>
      <textarea class="note" placeholder="not (isteğe bağlı)" oninput="setNote('${it.id}',this.value)"></textarea>
    </div>`;
  }).join('');
  // tam-metin bölümü ilk açılışta doldurulsun
  document.querySelectorAll('details.full').forEach(d=>d.addEventListener('toggle',function(){
    if(this.open){ const id=this.closest('.card').dataset.id;
      const mode=this.querySelector('.vtoggle button.on').dataset.v; setView(id,mode); }
  }));
}

function toCSV(){
  const head=["item_id","set","intended_category","original_sentence","mutated_sentence","fluent_YN","category_correct_YN","coder_notes"];
  const q=s=>'"'+String(s==null?'':s).replace(/"/g,'""')+'"';
  const lines=[head.join(",")];
  for(const it of ITEMS){ const s=state[it.id]||{};
    lines.push([q(it.id),q(it.set),q(it.cat),q(it.orig),q(it.mut),q(s.fluent||''),q(s.cat||''),q(s.note||'')].join(",")); }
  return "﻿"+lines.join("\r\n");
}
function download(){
  const c=document.getElementById('coder').value.trim()||'anon';
  const blob=new Blob([toCSV()],{type:'text/csv;charset=utf-8'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='B4_coding_'+c.replace(/[^\w.-]/g,'_')+'.csv';
  document.body.appendChild(a); a.click(); a.remove();
}

document.getElementById('coder').addEventListener('input', save);  // yalnız kaydet, YÜKLEME (is silinmez)
document.getElementById('export').addEventListener('click', download);
document.getElementById('reset').addEventListener('click', resetAll);
build(); load();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
