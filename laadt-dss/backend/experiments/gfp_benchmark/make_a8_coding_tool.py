"""A8 flag-adjudikasyon kodlama aracı (tek-dosya HTML, kurulumsuz).

v3 (kullanıcı kararı 2026-07-09): KÖR-bağımsız yerine FLAG-ADJUDIKASYONU. Guard'ın
bloklu ham (pre-intervention) metinde işaretlediği spesifik sayılar, tool_trace'ten
kurulan in-run grafıyla YENİDEN TÜRETİLİR (guard'ın canlı kararı). Kodlayıcı her
işaretli sayıyı REFERANS yer-gerçeğine karşı yargılar: gerçek ihlal (U/S/Un) mi,
guard yanıldı (aslında doğru = FP) mi. Yanıtta avlanmak yok → çok daha hızlı.

Ölçülen: guard blok-PRECISION'ı (standart pozitif-adjudikasyonu). Birincil değişken
response-düzeyi block_justified (≥1 flag gerçek) → over-block oranı + κ; per-flag
adjudikasyon → claim-precision. Guard'ın KAÇIRDIĞINI ölçmez (o G4'ün işi).
Sınır: körlemeden taviz (onaylama-eğilimi) → 2 kodlayıcı+κ + makalede beyan.

Kullanım: python -m experiments.gfp_benchmark.make_a8_coding_tool
"""
from __future__ import annotations
import csv
import glob
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "a8_precision"
_VIOL = ("UNGROUNDED", "SCALE_VIOLATION", "UNIT_MISMATCH")


def _fmt_tr(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if v == 0:
        return "0"
    if v == int(v) and abs(v) < 1e15:
        return f"{int(round(v)):,}".replace(",", ".")
    dec = max(0, 3 - math.floor(math.log10(abs(v))))
    r = round(v, dec)
    if r == int(r):
        return f"{int(round(r)):,}".replace(",", ".")
    return f"{r:,.{dec}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _reference_rows(question, orch) -> list[dict]:
    from experiments.gfp_benchmark.run_benchmark import _reference_graph
    g, ok, _ = _reference_graph(question, orch)
    if not ok:
        return []
    seen, rows = set(), []
    for d in g.records_as_dicts():
        k = (d.get("key"), d.get("scale"))
        if k in seen:
            continue
        seen.add(k)
        rows.append({"key": d.get("key", "?"), "value": _fmt_tr(d.get("value")),
                     "unit": d.get("unit") or "", "scale": d.get("scale") or "?"})
    return rows


def main() -> None:
    from app.llm import ollama_orchestrator as oo
    from experiments.gfp_benchmark.run_g4_final import _inrun_graph
    orch = oo.OllamaOrchestrator()

    # coding_id ↔ (model, qid, repeat) — frozen guard_key'den (sıra korunur)
    key_rows = list(csv.DictReader((OUT / "A8_guard_key.csv").open(encoding="utf-8-sig")))
    cid_of = {(r["model"], r["qid"], str(r["repeat"])): r["coding_id"] for r in key_rows}

    # model başına YALNIZ en yeni dosya (frozen sheet ile birebir 106 bloklu) —
    # smoke/eski koşu dosyaları duplike blok üretiyordu (A8-073 res-01 çakışması).
    blocked = []
    for pat in ("raw_g1_gemma4-e4b_2026070*.jsonl", "raw_g1_qwen3.5-27b_2026070*.jsonl"):
        hits = sorted(glob.glob(str(HERE / "results" / pat)))
        if not hits:
            continue
        for line in Path(hits[-1]).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if (r.get("provenance") or {}).get("blocked"):
                    blocked.append(r)

    ref_cache: dict = {}
    items = []
    for r in blocked:
        cid = cid_of.get((r["model"], r["question"]["id"], str(r.get("repeat"))))
        if not cid:
            continue
        qid = r["question"]["id"]
        if qid not in ref_cache:
            ref_cache[qid] = _reference_rows(r["question"], orch)
        g = _inrun_graph(r, orch)
        pre = ((r.get("provenance") or {}).get("pre_intervention") or {}).get("reply") or ""
        flags = []
        if g is not None and pre:
            rep = g.check_response(pre)
            for c in rep.claims:
                if c.verdict in _VIOL:
                    flags.append({"text": c.text, "sentence": (c.sentence or "").strip()})
        items.append({
            "coding_id": cid, "model": r["model"], "qid": qid,
            "scale_focus": r["question"].get("scale_focus"),
            "chain_length": r["question"].get("chain_length"),
            "question_tr": r["question"].get("question_tr", ""),
            "raw_reply": pre,
            "reference": ref_cache[qid] or [{"key": "(referans kurulamadı)", "value": "", "unit": "", "scale": ""}],
            "flags": flags,
        })

    items.sort(key=lambda x: x["coding_id"])
    data_json = json.dumps(items, ensure_ascii=False).replace("<", "\\u003c")
    html = _TEMPLATE.replace("__DATA__", data_json).replace("__N__", str(len(items)))
    (OUT / "A8_coding_tool.html").write_text(html, encoding="utf-8")
    nf = sum(len(it["flags"]) for it in items)
    noflag = sum(1 for it in items if not it["flags"])
    print(f"yazıldı: {OUT/'A8_coding_tool.html'} ({len(items)} madde, {nf} işaretli sayı, "
          f"{noflag} maddede flag türetilemedi)")


_TEMPLATE = r"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A8 Flag-Adjudikasyon</title>
<style>
:root{--bg:#0f1115;--card:#181b22;--fg:#e7e9ee;--mut:#9aa4b2;--acc:#4f9cf9;--ok:#3fb27f;--warn:#e0a458;--bad:#e06a6a;--line:#262b34}
@media(prefers-color-scheme:light){:root{--bg:#f4f6fa;--card:#fff;--fg:#1a1f2b;--mut:#5a6472;--line:#e2e6ee}}
*{box-sizing:border-box}
body{margin:0;font:15px/1.55 system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--fg)}
header{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line);padding:9px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
header h1{font-size:15px;margin:0;color:var(--acc)}
input,textarea,button{font:inherit;color:var(--fg)}
input[type=text],textarea{background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:6px 8px}
.wrap{max-width:1080px;margin:0 auto;padding:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0}
.meta{color:var(--mut);font-size:13px;margin-bottom:6px}.meta b{color:var(--fg)}
.q{font-size:16px;font-weight:600;margin:2px 0 10px}
.split{display:grid;grid-template-columns:1fr 320px;gap:16px}
@media(max-width:820px){.split{grid-template-columns:1fr}}
.label{font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--mut);margin:0 0 6px}
.reftab{width:100%;border-collapse:collapse;font-size:13px}
.reftab td{border-bottom:1px solid var(--line);padding:5px 6px;vertical-align:top}
.reftab .v{font-weight:700;white-space:nowrap;font-variant-numeric:tabular-nums}
.reftab .k{color:var(--mut)}.reftab .sc{font-size:11px;color:var(--mut)}
.sticky{position:sticky;top:56px}
.flag{border:1px solid var(--line);border-left:3px solid var(--warn);border-radius:8px;padding:10px 12px;margin:8px 0;background:var(--bg)}
.flag .num{font-size:18px;font-weight:800;color:var(--warn);font-variant-numeric:tabular-nums}
.flag .sent{color:var(--mut);font-size:13px;margin:4px 0 8px}
.flag .opts{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.flag .opts label{border:1px solid var(--line);border-radius:8px;padding:5px 9px;cursor:pointer;font-size:13px}
.flag.real{border-left-color:var(--bad)} .flag.fp{border-left-color:var(--ok)}
.flag .opts label.selR{border-color:var(--bad);background:rgba(224,106,106,.12);font-weight:600}
.flag .opts label.selF{border-color:var(--ok);background:rgba(63,178,127,.12);font-weight:600}
.typ{margin-left:6px;font-size:12px;color:var(--mut)}
.derived{padding:8px 12px;border-radius:8px;font-weight:700;margin:6px 0}
.derived.E{background:rgba(224,106,106,.14);color:var(--bad)}
.derived.H{background:rgba(63,178,127,.14);color:var(--ok)}
.derived.part{background:rgba(224,164,88,.14);color:var(--warn)}
details.resp summary{cursor:pointer;color:var(--acc);font-size:13px}
details.resp .body{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:12px;margin-top:8px;max-height:360px;overflow:auto;font-size:13px}
details.resp h4{color:var(--acc);margin:10px 0 4px}
details.resp table{border-collapse:collapse;font-size:12px;width:100%}
details.resp td,details.resp th{border:1px solid var(--line);padding:3px 6px}
details.help summary{cursor:pointer;color:var(--acc)}
details.help div{color:var(--mut);font-size:13px;margin-top:6px;border-left:2px solid var(--line);padding-left:10px}
button{background:var(--acc);border:none;border-radius:8px;padding:8px 14px;color:#fff;cursor:pointer;font-weight:600}
button.ghost{background:transparent;color:var(--fg);border:1px solid var(--line)}
button:disabled{opacity:.4;cursor:default}
.pill{background:var(--bg);border:1px solid var(--line);border-radius:20px;padding:3px 10px;font-size:12px;color:var(--mut)}
.done{color:var(--ok)}.undone{color:var(--warn)}
.bar{flex:1;height:8px;background:var(--bg);border:1px solid var(--line);border-radius:8px;overflow:hidden;min-width:110px}
.bar>i{display:block;height:100%;background:var(--ok);width:0}
.nav{display:flex;gap:8px;align-items:center;justify-content:space-between;margin-top:14px}
textarea{width:100%}
</style></head><body>
<header>
  <h1>A8 Flag-Adjudikasyon</h1>
  <span class="pill">Kodlayıcı: <input type="text" id="coder" placeholder="adınız" style="width:110px"></span>
  <div class="bar"><i id="bar"></i></div>
  <span class="pill" id="prog">0/__N__</span>
  <button class="ghost" id="jump">İlk boş →</button>
  <button id="export">CSV indir</button>
</header>
<div class="wrap">
  <details class="help"><summary>Nasıl? (guard'ın işaretlediği sayıları referansa karşı yargıla — ~10 sn/madde)</summary>
  <div>
   Her turuncu kart, guard'ın blokladığı yanıttaki bir sayıdır. Sağdaki <b>referans</b> ile karşılaştır:<br>
   • <b>Gerçek ihlal</b> = sayı referansa aykırı → tipini seç: <b>U</b> uydurma (referansta yok) · <b>S</b> yanlış ölçek (doğru değer, hane↔fider/toplam karışık) · <b>Un</b> yanlış birim (kW↔kWh, TL↔%).<br>
   • <b>Guard yanıldı</b> = sayı ASLINDA doğru (referansla uyuyor / yuvarlama / ±%2 / kullanıcı girdisi) — guard gereksiz işaretlemiş (FP).<br>
   Karar: bir sayı gerçek-ihlal olur olmaz "blok haklı" (E) türetilir; hepsi guard-yanıldı ise over-block (H). Otomatik kayıt; ← → gezinme.
  </div></details>

  <div id="item"></div>
  <div class="nav">
    <button class="ghost" id="prev">◀ Önceki</button>
    <span class="pill" id="idlabel"></span>
    <button id="next">Sonraki ▶</button>
  </div>
</div>

<script type="application/json" id="data">__DATA__</script>
<script>
const ITEMS=JSON.parse(document.getElementById('data').textContent), N=ITEMS.length; let idx=0;
const coderEl=document.getElementById('coder');
coderEl.value=localStorage.getItem('a8_coder')||'';
coderEl.addEventListener('input',()=>{localStorage.setItem('a8_coder',coderEl.value);render();updateProg();});
function key(id){return 'a8adj::'+(coderEl.value||'_')+'::'+id;}
function load(id){try{return JSON.parse(localStorage.getItem(key(id)))||{}}catch(e){return {}}}
function save(id,o){localStorage.setItem(key(id),JSON.stringify(o));}
function esc(s){return String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
// item durumu: her flag için 'R:U|R:S|R:Un' (gerçek+tip) ya da 'FP' ; + notes
function derived(it,a){const fl=a.flags||{}; const n=it.flags.length;
  if(n===0){return a.bj||'';} // flag yoksa manuel (nadiren)
  const vals=it.flags.map((_,i)=>fl[i]); const set=vals.filter(Boolean).length;
  if(vals.some(v=>v&&v[0]==='R'))return 'E';
  if(set===n && vals.every(v=>v==='FP'))return 'H';
  return set===n?'H':'';}
function isDone(it,a){const d=derived(it,a); return d==='E'||d==='H';}

function md(src){const L=src.split(/\r?\n/);let h='';let i=0;
  const il=s=>esc(s).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/`(.+?)`/g,'<code>$1</code>');
  while(i<L.length){let ln=L[i];
    if(/^\s*\|.*\|/.test(ln)){const tb=[];while(i<L.length&&/^\s*\|.*\|/.test(L[i])){tb.push(L[i]);i++;}
      const cl=r=>r.replace(/^\s*\|/,'').replace(/\|\s*$/,'').split('|').map(c=>c.trim());
      let t='<table>';tb.forEach((r,ri)=>{if(/^\s*\|?[\s:|-]+\|?\s*$/.test(r))return;const tg=ri===0?'th':'td';t+='<tr>'+cl(r).map(c=>`<${tg}>${il(c)}</${tg}>`).join('')+'</tr>';});h+=t+'</table>';continue;}
    if(/^\s*#{1,6}\s/.test(ln)){h+='<h4>'+il(ln.replace(/^\s*#{1,6}\s/,''))+'</h4>';i++;continue;}
    if(/^\s*([-*•]|\d+\.)\s/.test(ln)){const ol=/^\s*\d+\.\s/.test(ln);const li=[];while(i<L.length&&/^\s*([-*•]|\d+\.)\s/.test(L[i])){li.push(L[i].replace(/^\s*([-*•]|\d+\.)\s/,''));i++;}h+=(ol?'<ol>':'<ul>')+li.map(x=>'<li>'+il(x)+'</li>').join('')+(ol?'</ol>':'</ul>');continue;}
    if(ln.trim()===''){i++;continue;} h+='<p>'+il(ln)+'</p>';i++;}
  return h;}

function render(){
  const it=ITEMS[idx], a=load(it.coding_id); a.flags=a.flags||{};
  const refRows=it.reference.map(r=>`<tr><td class="v">${esc(r.value)}${r.unit?' <span class="k">'+esc(r.unit)+'</span>':''}</td><td class="k">${esc(r.key)}${r.scale?'<div class="sc">'+esc(r.scale)+'</div>':''}</td></tr>`).join('');
  let flagsHtml = it.flags.length? it.flags.map((f,i)=>{
    const v=a.flags[i]||''; const real=v&&v[0]==='R'; const typ=real?v.slice(2):'';
    return `<div class="flag ${real?'real':(v==='FP'?'fp':'')}" data-i="${i}">
      <div class="num">${esc(f.text)}</div>
      <div class="sent">${esc(f.sentence)}</div>
      <div class="opts">
        <label class="${real?'selR':''}" data-set="R"><input type="radio" name="f${i}" ${real?'checked':''} style="display:none"> ⚠️ Gerçek ihlal</label>
        <span class="typ" ${real?'':'style=display:none'} id="typ${i}">
          <label class="${typ==='U'?'selR':''}" data-set="R:U">U</label>
          <label class="${typ==='S'?'selR':''}" data-set="R:S">S</label>
          <label class="${typ==='Un'?'selR':''}" data-set="R:Un">Un</label></span>
        <label class="${v==='FP'?'selF':''}" data-set="FP"><input type="radio" name="f${i}" ${v==='FP'?'checked':''} style="display:none"> ✓ Guard yanıldı</label>
      </div></div>`;}).join('')
    : `<div class="flag"><div class="sent">Bu yanıt için guard-işaretli sayı türetilemedi (tool_trace boş / özel durum). Aşağıdaki yanıtı okuyup elle karar verin.</div>
       <div class="opts"><label data-set="MB:E">⚠️ Blok haklı</label><label data-set="MB:H">✓ Over-block</label></div></div>`;
  const d=derived(it,a);
  document.getElementById('item').innerHTML=`
   <div class="card">
    <div class="meta"><b>${it.coding_id}</b> · ${esc(it.model)} · ${esc(it.qid)} · ölçek <b>${esc(it.scale_focus)}</b> · zincir ${esc(it.chain_length)} · ${it.flags.length} işaretli sayı</div>
    <div class="q">${esc(it.question_tr)}</div>
    <div class="split">
      <div>
        <div class="label">Guard'ın işaretlediği sayılar — her birini referansa karşı yargıla</div>
        ${flagsHtml}
        <div class="derived ${d==='E'?'E':(d==='H'?'H':'part')}" id="der">${d==='E'?'→ BLOK HAKLI (≥1 gerçek ihlal)':(d==='H'?'→ OVER-BLOCK (hepsi guard hatası)':'→ (henüz tamamlanmadı)')}</div>
        <details class="resp"><summary>Tüm yanıtı göster (bağlam gerekirse)</summary><div class="body" id="respbody"></div></details>
        <textarea rows="2" id="notes" placeholder="not (opsiyonel)">${esc(a.notes||'')}</textarea>
      </div>
      <div><div class="sticky"><div class="label">Referans yer-gerçeği</div><table class="reftab"><tbody>${refRows}</tbody></table></div></div>
    </div>
   </div>`;
  document.getElementById('respbody').innerHTML=md(it.raw_reply);
  document.querySelectorAll('.opts label[data-set]').forEach(el=>el.onclick=()=>{
    const set=el.getAttribute('data-set'); const fl=el.closest('.flag'); const i=fl.getAttribute('data-i');
    const a2=load(it.coding_id); a2.flags=a2.flags||{};
    if(set.startsWith('MB:')){a2.bj=set.slice(3);}
    else if(i!=null){ if(set==='R'){ if(!(a2.flags[i]&&a2.flags[i][0]==='R'))a2.flags[i]='R:U'; }
      else a2.flags[i]=set; }
    save(it.coding_id,a2); render(); updateProg();
  });
  const nt=document.getElementById('notes'); if(nt)nt.oninput=()=>{const a2=load(it.coding_id);a2.notes=nt.value;save(it.coding_id,a2);};
  document.getElementById('idlabel').textContent=(idx+1)+' / '+N+(isDone(it,a)?'  ✓':'');
  document.getElementById('prev').disabled=idx===0; document.getElementById('next').disabled=idx===N-1;
}
function updateProg(){let c=0;ITEMS.forEach(it=>{if(isDone(it,load(it.coding_id)))c++;});
  document.getElementById('prog').innerHTML=`<span class="${c===N?'done':'undone'}">${c}/${N}</span>`;
  document.getElementById('bar').style.width=(100*c/N)+'%';}
document.getElementById('prev').onclick=()=>{if(idx>0){idx--;render();}};
document.getElementById('next').onclick=()=>{if(idx<N-1){idx++;render();}};
document.getElementById('jump').onclick=()=>{for(let k=0;k<N;k++){if(!isDone(ITEMS[k],load(ITEMS[k].coding_id))){idx=k;render();return;}}};
document.addEventListener('keydown',e=>{if(['TEXTAREA','INPUT'].includes(e.target.tagName))return;
  if(e.key==='ArrowRight'&&idx<N-1){idx++;render();}if(e.key==='ArrowLeft'&&idx>0){idx--;render();}});
document.getElementById('export').onclick=()=>{
  const coder=coderEl.value||'anon';
  const head=['coding_id','coder','flag_index','flag_text','adjudication','block_justified_YN','notes'];
  const q=s=>'"'+String(s==null?'':s).replace(/"/g,'""')+'"';
  const out=[head.join(',')];
  ITEMS.forEach(it=>{const a=load(it.coding_id);const d=derived(it,a);
    if(it.flags.length===0){out.push([q(it.coding_id),q(coder),q(''),q(''),q('NO_FLAGS'),q(a.bj||d),q(a.notes)].join(','));return;}
    it.flags.forEach((f,i)=>{out.push([q(it.coding_id),q(coder),q(i),q(f.text),q((a.flags||{})[i]||''),q(d),q(i===0?a.notes:'')].join(','));});
  });
  const blob=new Blob(['﻿'+out.join('\r\n')],{type:'text/csv;charset=utf-8'});
  const u=URL.createObjectURL(blob),l=document.createElement('a');l.href=u;l.download='A8_adj_'+coder+'.csv';l.click();URL.revokeObjectURL(u);
};
render(); updateProg();
</script></body></html>"""


if __name__ == "__main__":
    main()
