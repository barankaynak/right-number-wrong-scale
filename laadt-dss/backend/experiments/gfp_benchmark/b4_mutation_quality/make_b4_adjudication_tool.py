"""B4 adjudikasyon-aracı üreticisi (A18 (ii)/(iii) donmuş prosedürü uygular).

Girdi: `B4_coding_sheet.csv` (metinler) + iki kodlayıcı CSV'si.
Çıktı: `B4_adjudication_tool.html` — iki kodlayıcının BİRLİKTE açıp anlaşmazlıkları
uzlaşı görüşmesiyle çözdüğü kendine-yeterli sayfa.

A18 kuralları araca GÖMÜLÜ:
 - Adjudike edilecek küme = category-anlaşmazlıkları ∪ fluent-anlaşmazlıkları (birleşim).
 - Hemfikir öğeler otomatik taşınır (adjudike EDİLMEZ), `source=agreed`.
 - **Eşitlik-bozma:** konsensüs-N ancak SPESİFİK bir kodkitabı dışlama-maddesi
   seçilirse verilebilir; madde seçilmeden N kilitlidir → gösterilemiyorsa Y.
 - Her adjudike karar için madde-atfı + serbest gerekçe zorunlu.

İki CSV indirir: `B4_consensus.csv` (51 satır) + `B4_adjudication_notes.csv`.

Kullanım: python make_b4_adjudication_tool.py
"""
from __future__ import annotations
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHEET = HERE / "B4_coding_sheet.csv"
C1 = HERE / "B4_coding_coder1.csv"
C2 = HERE / "B4_coding_coder2.csv"
OUT = HERE / "B4_adjudication_tool.html"
C1_NAME, C2_NAME = "Baran (K1)", "Sümeyye (K2)"

CAT_SHORT = ("value-fabrication", "unit-swap", "scale-swap", "small-int")

# Kodkitabı §3/§4 dışlama-maddeleri (konsensüs-N için gösterilmesi ZORUNLU)
CLAUSES = {
    "fluent": [
        ("§3-N/ek", "§3 — kırık ek / çift-ek (ör. 'fider genelindeın')"),
        ("§3-N/uyum", "§3 — uyumsuz sözcük yerleşimi (ör. 'Depolama Mahalle genelinde sistemi')"),
        ("§3-N/gramer", "§3 — bariz gramer hatası"),
    ],
    "cat": [
        ("§4-value/liste", "§4 value-fab — liste/başlık numarası bozuldu"),
        ("§4-value/sablon", "§4 value-fab — tablo-şablonu yer-tutucusu"),
        ("§4-value/baglam", "§4 value-fab — salt bağlam sayısı (sonuç değil)"),
        ("§4-unit/istek", "§4 unit-swap — veri-isteği/şablon etiketi (ör. 'tutarını (TL)')"),
        ("§4-unit/aciklama", "§4 unit-swap — açıklayıcı-metin birimi (sonuç değeri değil)"),
        ("§4-scale/baslik", "§4 scale-swap — yalnız soru/başlık çerçevesi; cümlede temellendirilmiş sonuç sayısı YOK"),
        ("§4-small/adim", "§4 small-int — sıralama/adım numarası"),
        ("§4-small/baglam", "§4 small-int — bağlamsal yıl (karar-kritik değil)"),
    ],
}


def _yn(v):
    s = (v or "").strip().upper()
    return "Y" if s in ("Y", "YES", "E", "EVET", "1", "TRUE") else (
        "N" if s in ("N", "NO", "H", "HAYIR", "0", "FALSE") else "")


def cat_key(label: str) -> str:
    for k in CAT_SHORT:
        if label.startswith(k):
            return k
    return label


def _read(p: Path):
    return {r["item_id"]: r for r in csv.DictReader(p.open(encoding="utf-8-sig"))}


def main() -> None:
    rows = list(csv.DictReader(SHEET.open(encoding="utf-8-sig")))
    A, B = _read(C1), _read(C2)
    items, n_disp = [], 0
    for r in rows:
        i = r["item_id"]
        a1, a2 = _yn(A[i]["fluent_YN"]), _yn(A[i]["category_correct_YN"])
        b1, b2 = _yn(B[i]["fluent_YN"]), _yn(B[i]["category_correct_YN"])
        disp_f, disp_c = a1 != b1, a2 != b2
        if disp_f or disp_c:
            n_disp += 1
        items.append({
            "id": i, "set": r.get("set", ""), "cat": r["intended_category"],
            "catKey": cat_key(r["intended_category"]),
            "orig": r["original_sentence"], "mut": r["mutated_sentence"],
            "fullOrig": r.get("full_original", r["original_sentence"]),
            "fullMut": r.get("full_mutated", r["mutated_sentence"]),
            "k1": {"fluent": a1, "cat": a2, "note": A[i].get("coder_notes", "")},
            "k2": {"fluent": b1, "cat": b2, "note": B[i].get("coder_notes", "")},
            "disp": {"fluent": disp_f, "cat": disp_c},
        })
    html = (_TEMPLATE
            .replace("/*__DATA__*/", json.dumps(items, ensure_ascii=False))
            .replace("/*__CLAUSES__*/", json.dumps(CLAUSES, ensure_ascii=False))
            .replace("__N__", str(n_disp))
            .replace("__TOT__", str(len(items)))
            .replace("__C1__", C1_NAME).replace("__C2__", C2_NAME))
    OUT.write_text(html, encoding="utf-8")
    print(f"{len(items)} öğe ({n_disp} adjudike edilecek) → {OUT.name}  ({OUT.stat().st_size} B)")


_TEMPLATE = r"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>B4 — Adjudikasyon (konsensüs oturumu)</title>
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
  .wrap{max-width:940px;margin:18px auto;padding:0 16px}
  .intro{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px;margin-bottom:18px}
  .intro summary{cursor:pointer;font-weight:600}
  .intro ul{margin:8px 0 0;padding-left:20px;color:var(--mut)}
  .intro b{color:var(--ink)}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:16px}
  .card.done{border-color:var(--accent)}
  .card.missing{border-color:var(--no)}
  .card.agreed{opacity:.5}
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
  .dispute{background:var(--card2);border:1px solid var(--line);border-left:3px solid var(--accent);
    border-radius:8px;padding:12px 14px;margin-top:14px}
  .dh{font-size:13px;font-weight:700;margin-bottom:8px}
  .votes{display:flex;gap:18px;flex-wrap:wrap;font-size:13px;color:var(--mut);margin-bottom:10px}
  .votes b{color:var(--ink)}
  .vY{color:var(--yes);font-weight:700}
  .vN{color:var(--no);font-weight:700}
  .q{display:flex;flex-wrap:wrap;gap:6px 16px;align-items:center}
  .q>.qlab{font-size:13px;font-weight:600;min-width:150px}
  .seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
  .seg button{background:var(--card);color:var(--ink);border:0;padding:6px 16px;font-size:14px;cursor:pointer}
  .seg button+button{border-left:1px solid var(--line)}
  .seg button.y.on{background:var(--yes);color:#fff}
  .seg button.n.on{background:var(--no);color:#fff}
  .seg button:disabled{opacity:.4;cursor:not-allowed}
  select{background:var(--card);border:1px solid var(--line);color:var(--ink);border-radius:7px;
    padding:6px 8px;font-size:13px;max-width:100%;margin-top:8px}
  .rule{font-size:12px;color:var(--mut);margin-top:6px}
  .note{width:100%;margin-top:8px;background:var(--card);border:1px solid var(--line);color:var(--ink);
    border-radius:8px;padding:8px 10px;font-size:13px;resize:vertical;min-height:34px}
  .agreedbox{font-size:13px;color:var(--mut);margin-top:12px}
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
  <h1>B4 — Adjudikasyon (konsensüs oturumu)</h1>
  <span class="prog" id="count">0 / __N__ anlaşmazlık</span>
  <div class="bar"><i id="fill"></i></div>
</header>

<div class="wrap">
  <details class="intro" open>
    <summary>Kural (ön-kayıt A18 — bağlayıcı)</summary>
    <ul>
      <li>Yalnız <b>anlaşmazlık</b> öğeleri kararlanır (__N__ / __TOT__). Hemfikir öğeler otomatik taşınır.</li>
      <li><b>Eşitlik-bozma kuralı:</b> Bir öğeye ancak <b>spesifik bir kodkitabı dışlama-maddesi gösterilebiliyorsa HAYIR</b> denebilir. Madde seçilmeden “Hayır” tuşu <b>kilitlidir</b> — gösteremiyorsanız cevap <b>Evet</b>'tir.</li>
      <li>Karar <b>madde metnine</b> göre verilir, kıdem/otoriteye göre değil. <b>Gerekçe yalnız “Hayır” kararlarında zorunlu</b> (madde + tek cümle); “Evet” zaten “gösterilebilir madde yok” demektir, gerekçe isteğe bağlıdır.</li>
      <li>Bu oturum kör değildir: iki kodlayıcının etiketleri görünür. Guard'ın kararı hâlâ <b>görünmez</b>.</li>
      <li>Sonuç: <b>B4_consensus.csv</b> (51 satır) + <b>B4_adjudication_notes.csv</b>. İlerleme otomatik kaydedilir.</li>
    </ul>
  </details>
  <div id="cards"></div>
</div>

<footer>
  <span class="status" id="status">Anlaşmazlıkları çözün, sonra iki CSV'yi indirin.</span>
  <button class="rst" id="goto" style="display:none">Eksiğe git</button>
  <button class="rst" id="reset">Sıfırla</button>
  <button class="exp" id="export" disabled>CSV'leri indir</button>
</footer>

<script>
const ITEMS = /*__DATA__*/;
const CLAUSES = /*__CLAUSES__*/;
const DISPUTED = ITEMS.filter(it=>it.disp.fluent||it.disp.cat);
const N = DISPUTED.length;
const state = {};
const badgeCls = {"value-fabrication":"b-value","unit-swap":"b-unit","scale-swap":"b-scale","small-int":"b-small"};
const VARLAB = {fluent:"Akıcı? (fluent)", cat:"Bozulan şey gerçek bir SONUÇ değeri mi? (category)"};

function esc(s){return String(s==null?'':s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}
function renderExcerpt(t){ return esc(t).replace(/&gt;&gt;([\s\S]*?)&lt;&lt;/g,'<mark>$1</mark>'); }

function inlineMd(s){
  s = esc(s);
  s = s.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
  s = s.replace(/`([^`]+)`/g,'<code>$1</code>');
  s = s.replace(/(^|[^*])\*([^*\s][^*]*)\*/g,'$1<em>$2</em>');
  return s;
}
function splitRow(s){ return s.replace(/^\s*\|/,'').replace(/\|\s*$/,'').split('|').map(x=>x.trim()); }
function renderMd(text){
  text = text.replace(/>>/g,'@@MK@@').replace(/<</g,'@@ME@@');
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

const SAVE_KEY='b4:adjudication';
function save(){ localStorage.setItem(SAVE_KEY, JSON.stringify(state)); }
function load(){
  let obj=null; try{ obj=JSON.parse(localStorage.getItem(SAVE_KEY)||'null'); }catch(e){}
  if(obj) Object.assign(state, obj);
  document.querySelectorAll('.card').forEach(applyState); refresh();
}
function resetAll(){
  if(!confirm('Tüm adjudikasyon kararları silinecek. Önce CSV indirdiniz mi?')) return;
  for(const k in state) delete state[k];
  localStorage.removeItem(SAVE_KEY);
  document.querySelectorAll('.card').forEach(applyState);
  document.querySelectorAll('.note').forEach(n=>n.value=''); refresh();
}
function st(id){ return state[id]||(state[id]={}); }

// A18 (iii): N ancak madde seçiliyse verilebilir.
function setClause(id, v, val){
  const s=st(id); s[v+'_clause']=val;
  if(!val && s[v]==='N') delete s[v];         // madde kalkarsa N geçersiz
  save(); applyState(document.getElementById('c-'+id)); refresh();
}
function seg(id, v, val){
  const s=st(id);
  if(val==='N' && !s[v+'_clause']){ alert('A18: “Hayır” için önce spesifik bir kodkitabı dışlama-maddesi seçin. Gösterilemiyorsa cevap “Evet”tir.'); return; }
  s[v]=val; save(); applyState(document.getElementById('c-'+id)); refresh();
}
function setNote(id, v, val){ st(id)[v+'_why']=val; save(); refresh(); }

// A18: zorunlu olan MADDE ATFI (yalnız N'de vardır). Y = "gosterilebilir madde yok"
// kararidir; serbest gerekce Y'de ISTEGE BAGLI, N'de zorunlu (madde + kisa gerekce).
function itemDone(it){
  const s=state[it.id]||{};
  for(const v of ['fluent','cat']){
    if(!it.disp[v]) continue;
    if(!s[v]) return false;
    if(s[v]==='N' && !(s[v+'_why']||'').trim()) return false;
  }
  return true;
}
function applyState(card){
  if(!card) return; const id=card.dataset.id; const s=state[id]||{}; const it=ITEMS.find(x=>x.id===id);
  card.querySelectorAll('.seg button').forEach(b=>{
    b.classList.toggle('on', s[b.dataset.v]===b.dataset.val);
    if(b.dataset.val==='N') b.disabled = !s[b.dataset.v+'_clause'];
  });
  card.querySelectorAll('select').forEach(sel=>{ if(sel.value!==(s[sel.dataset.v+'_clause']||'')) sel.value=s[sel.dataset.v+'_clause']||''; });
  card.querySelectorAll('.note').forEach(n=>{ const val=s[n.dataset.v+'_why']||''; if(n.value!==val) n.value=val; });
  card.classList.toggle('done', itemDone(it));
}
// Eksik kalan kararları GEREKÇESİYLE listele (indir tuşu neden kapalı sorusunu bitirir).
function incomplete(){
  const out=[];
  for(const it of DISPUTED){ const s=state[it.id]||{};
    for(const v of ['fluent','cat']){
      if(!it.disp[v]) continue;
      if(!s[v]) out.push({id:it.id, v, why:'karar verilmedi'});
      else if(s[v]==='N' && !(s[v+'_why']||'').trim()) out.push({id:it.id, v, why:'“Hayır” gerekçesi boş'});
    } }
  return out;
}
function gotoMissing(){
  const m=incomplete()[0]; if(!m) return;
  const c=document.getElementById('c-'+m.id);
  c.scrollIntoView({block:'center', behavior:'smooth'});
  c.style.transition='box-shadow .2s'; c.style.boxShadow='0 0 0 3px var(--no)';
  setTimeout(function(){ c.style.boxShadow=''; }, 1800);
}
function refresh(){
  const miss=incomplete();
  const done=DISPUTED.filter(itemDone).length;
  document.getElementById('count').textContent=done+' / '+N+' anlaşmazlık';
  document.getElementById('fill').style.width=(N?100*done/N:100)+'%';
  document.getElementById('export').disabled=miss.length>0;
  document.querySelectorAll('.card').forEach(function(c){
    c.classList.toggle('missing', miss.some(m=>m.id===c.dataset.id)); });
  const btn=document.getElementById('goto');
  btn.style.display = miss.length? 'inline-block':'none';
  document.getElementById('status').textContent = miss.length
    ? miss.length+' eksik: '+miss.slice(0,3).map(m=>m.id+' ('+VARLAB[m.v].split('?')[0]+' — '+m.why+')').join(', ')
        + (miss.length>3?' …':'')
    : 'Tamam — CSV\'leri indirebilirsiniz.';
}
function setView(id, mode){
  const card=document.getElementById('c-'+id); const it=ITEMS.find(x=>x.id===id);
  card.querySelectorAll('.vtoggle button').forEach(b=>b.classList.toggle('on', b.dataset.v===mode));
  const cls='rendered'+(mode==='md'?'':' raw');
  const o=card.querySelector('[data-full="orig"]'), m=card.querySelector('[data-full="mut"]');
  o.className=cls; o.innerHTML=renderFull(it.fullOrig, mode);
  m.className=cls; m.innerHTML=renderFull(it.fullMut, mode);
}

function voteHtml(v, it){
  const f=x=>'<span class="v'+x+'">'+(x==='Y'?'Evet':'Hayır')+'</span>';
  return '<div class="votes"><span><b>__C1__:</b> '+f(it.k1[v])+'</span><span><b>__C2__:</b> '+f(it.k2[v])+'</span></div>';
}
// Kategori-maddeleri yalnız öğenin KENDİ kategorisinden seçilebilir (yanlış-atıf önleme).
const CATPFX={"value-fabrication":"§4-value/","unit-swap":"§4-unit/","scale-swap":"§4-scale/","small-int":"§4-small/"};
function clausesFor(v, it){
  if(v!=='cat') return CLAUSES[v];
  const p=CATPFX[it.catKey];
  const own=CLAUSES.cat.filter(c=>p && c[0].indexOf(p)===0);
  return own.length?own:CLAUSES.cat;
}
function disputeHtml(v, it){
  const opts=['<option value="">— dışlama-maddesi seçilmedi (karar: Evet) —</option>']
    .concat(clausesFor(v,it).map(c=>'<option value="'+c[0]+'">'+esc(c[1])+'</option>')).join('');
  return `<div class="dispute">
    <div class="dh">${VARLAB[v]}</div>
    ${voteHtml(v, it)}
    <select data-v="${v}" onchange="setClause('${it.id}','${v}',this.value)">${opts}</select>
    <div class="rule">A18: <b>Hayır</b> ancak yukarıdan spesifik bir madde seçilirse açılır.</div>
    <div class="q" style="margin-top:8px"><span class="qlab">Konsensüs</span>
      <div class="seg">
        <button class="y" data-v="${v}" data-val="Y" onclick="seg('${it.id}','${v}','Y')">Evet</button>
        <button class="n" data-v="${v}" data-val="N" onclick="seg('${it.id}','${v}','N')">Hayır</button>
      </div></div>
    <textarea class="note" data-v="${v}" placeholder="gerekçe — “Hayır” için zorunlu, “Evet” için isteğe bağlı" oninput="setNote('${it.id}','${v}',this.value)"></textarea>
  </div>`;
}

function build(){
  document.getElementById('cards').innerHTML = ITEMS.map(it=>{
    const bc=badgeCls[it.catKey]||'';
    const agreed=!(it.disp.fluent||it.disp.cat);
    const body = agreed
      ? `<div class="agreedbox">Her iki kodlayıcı hemfikir (akıcı: <b>${it.k1.fluent}</b>, kategori: <b>${it.k1.cat}</b>) — otomatik taşınır, adjudike edilmez.</div>`
      : (it.disp.fluent?disputeHtml('fluent',it):'') + (it.disp.cat?disputeHtml('cat',it):'');
    const notes = [it.k1.note&&('__C1__ notu: '+it.k1.note), it.k2.note&&('__C2__ notu: '+it.k2.note)]
      .filter(Boolean).map(x=>'<div class="rule">'+esc(x)+'</div>').join('');
    return `<div class="card${agreed?' agreed':''}" id="c-${it.id}" data-id="${it.id}">
      <div class="top"><span class="id">${it.id}</span>
        <span class="badge badge-set">${esc(it.set)}</span>
        <span class="badge ${bc}">${esc(it.cat)}</span>
        ${agreed?'<span class="badge">hemfikir</span>':'<span class="badge" style="color:#d98a4a">anlaşmazlık</span>'}</div>
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
      ${notes}
      ${body}
    </div>`;
  }).join('');
  document.querySelectorAll('details.full').forEach(d=>d.addEventListener('toggle',function(){
    if(this.open){ const id=this.closest('.card').dataset.id;
      const mode=this.querySelector('.vtoggle button.on').dataset.v; setView(id,mode); }
  }));
}

const q=s=>'"'+String(s==null?'':s).replace(/"/g,'""')+'"';
function consensusCSV(){
  const head=["item_id","set","intended_category","fluent_YN","category_correct_YN","source"];
  const lines=[head.join(",")];
  for(const it of ITEMS){ const s=state[it.id]||{};
    const f = it.disp.fluent ? s.fluent : it.k1.fluent;
    const c = it.disp.cat    ? s.cat    : it.k1.cat;
    const src = (it.disp.fluent||it.disp.cat) ? "adjudicated" : "agreed";
    lines.push([q(it.id),q(it.set),q(it.cat),q(f),q(c),q(src)].join(","));
  }
  return "﻿"+lines.join("\r\n");
}
function notesCSV(){
  const head=["item_id","variable","coder1_label","coder2_label","consensus","codebook_clause","rationale"];
  const lines=[head.join(",")];
  for(const it of ITEMS){ const s=state[it.id]||{};
    for(const v of ['fluent','cat']){ if(!it.disp[v]) continue;
      lines.push([q(it.id),q(v),q(it.k1[v]),q(it.k2[v]),q(s[v]||''),q(s[v+'_clause']||''),q(s[v+'_why']||'')].join(","));
    }
  }
  return "﻿"+lines.join("\r\n");
}
function dl(name, text){
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'}));
  a.download=name; document.body.appendChild(a); a.click(); a.remove();
}
document.getElementById('export').addEventListener('click', function(){
  dl('B4_consensus.csv', consensusCSV());
  setTimeout(function(){ dl('B4_adjudication_notes.csv', notesCSV()); }, 300);
});
document.getElementById('reset').addEventListener('click', resetAll);
document.getElementById('goto').addEventListener('click', gotoMissing);
build(); load();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
