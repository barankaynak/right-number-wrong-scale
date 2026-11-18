"""A25 — Bağımsız öğrenilmiş doğrulayıcı (TypeSafe Jev) ile G4 evidence-format ablasyonu.

Ana makinede çalışır (yalnız standart kütüphane + Node): `@jkudish/jev-mcp@0.14.3` MCP sunucusu
stdio üzerinden başlatılır ve `jev_verify` aracı çağrılır (oturumdaki araçla aynı yol).
Anahtar `TYPESAFE_API_KEY` ortam değişkeninden okunur; hiçbir yere yazılmaz.

Girdi : results/a25_evidence_items.json (tag'den önce donmuş; clear-sky replay evidence)
Çıktı : results/a25_jev_calls.jsonl  — her çağrının tam isteği ve yanıtı (yayınlanır)
        results/a25_jev_summary.json — ön-kayıtlı analiz
Ön-kayıtlı karar eşlemesi: tespit = verdict ∈ {contradicted, unsupported} ∧ confidence ≥ eşik;
eşik 0.8 birincil, 0.5 duyarlılık; "review" eylemi ayrı sayılır. Tek hipotez H_V1:
scale_swap'ta annotated − raw recall > 0 (enjeksiyon-eşli exact McNemar, iki-yönlü).

Teslim-metni üçgenlemesi (koşu + A22-2 örneklemi sonrası; eşleme burada dondu):
  `audit <audit_dir>` — her numaralı sayı için iddia: 'The number "<sayı>" in the following
  statement is supported by the evidence: "<cümle>"'; evidence = insan kodlayıcıların gördüğü
  referans çıktı sayfası (aynı satırlar). Jev-traceable ⇔ verdict = verified ∧ confidence ≥ 0.8.
  Çıktı: <audit_dir>/audit_jev.jsonl (istek+yanıt) — κ (Jev vs insan-konsensüs) analizi
  A22-2 analiziyle birlikte raporlanır; Jev insanın ikamesi değildir.

Kullanım: python experiments/gfp_benchmark/jev_g4.py run | analyze | audit <audit_dir>
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
ITEMS = RESULTS / "a25_evidence_items.json"
CALLS = RESULTS / "a25_jev_calls.jsonl"
SUMMARY = RESULTS / "a25_jev_summary.json"
PACKAGE = "@jkudish/jev-mcp@0.14.3"
FORMATS = ("raw", "annotated")
CHUNK = 24
MAX_CALLS = 1500
THRESHOLDS = (0.8, 0.5)
DETECT = {"contradicted", "unsupported"}


class McpClient:
    def __init__(self) -> None:
        cmd = (["cmd", "/c", "npx", "-y", PACKAGE] if os.name == "nt" else ["npx", "-y", PACKAGE])
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                     env=os.environ.copy())
        self.next_id = 0
        self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "gfp-a25", "version": "1.0"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _send(self, msg: dict) -> None:
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def request(self, method: str, params: dict) -> dict:
        self.next_id += 1
        rid = self.next_id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("MCP sunucusu kapandı")
            msg = json.loads(line)
            if msg.get("id") == rid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg["result"]

    def verify(self, claims: list[str], evidence: str) -> dict:
        res = self.request("tools/call", {"name": "jev_verify",
                                          "arguments": {"claims": claims, "evidence": evidence}})
        text = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        if res.get("isError"):
            raise RuntimeError(text)
        return json.loads(text)

    def close(self) -> None:
        self.proc.terminate()


def run() -> None:
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY tanımlı değil")
    data = json.loads(ITEMS.read_text(encoding="utf-8"))
    groups = defaultdict(set)                    # (set, qid) -> claim metinleri
    for it in data["items"]:
        key = (it["set"], it["qid"])
        if it["kind"] == "control":
            groups[key].update(it["sentences"])
        else:
            groups[key].update([it["original_sentence"], it["mutated_sentence"]])
    done = set()
    if CALLS.exists():                           # kesintiden devam (aynı istek tekrar edilmez)
        for line in CALLS.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("response"):
                done.add((r["set"], r["qid"], r["format"], r["chunk"]))
    client, n_calls = McpClient(), 0
    with CALLS.open("a", encoding="utf-8") as fh:
        for (set_name, qid), claims in sorted(groups.items()):
            claims = sorted(claims)
            for fmt in FORMATS:
                evidence = data["evidence"][qid][fmt]
                for ci in range(0, len(claims), CHUNK):
                    tag = (set_name, qid, fmt, ci // CHUNK)
                    if tag in done:
                        continue
                    if n_calls >= MAX_CALLS:
                        sys.exit("çağrı tavanı aşıldı")
                    chunk = claims[ci:ci + CHUNK]
                    resp, err = None, None
                    for attempt in range(3):
                        try:
                            resp = client.verify(chunk, evidence)
                            break
                        except Exception as exc:          # verifier_error: sayılı dışlama
                            err = repr(exc)
                            time.sleep(5 * (attempt + 1))
                    n_calls += 1
                    fh.write(json.dumps({
                        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "package": PACKAGE, "set": set_name, "qid": qid, "format": fmt,
                        "chunk": ci // CHUNK, "claims": chunk, "evidence": evidence,
                        "response": resp, "verifier_error": None if resp else err,
                    }, ensure_ascii=False) + "\n")
                    fh.flush()
                    print(set_name, qid, fmt, ci // CHUNK, "ok" if resp else f"ERROR {err}")
    client.close()


def _wilson(k: int, n: int) -> list[float] | None:
    if n == 0:
        return None
    z, p = 1.959964, k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def _mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def analyze() -> None:
    data = json.loads(ITEMS.read_text(encoding="utf-8"))
    verdict = {}                                  # (set, qid, fmt, claim) -> result dict
    n_err = n_calls = 0
    for line in CALLS.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        n_calls += 1
        if not r.get("response"):
            n_err += 1
            continue
        for res in r["response"]["results"]:
            verdict[(r["set"], r["qid"], r["format"], res["claim"])] = res
    model = next((json.loads(l)["response"].get("model") for l in
                  CALLS.read_text(encoding="utf-8").splitlines() if json.loads(l).get("response")), None)

    def flagged(key, thr):
        v = verdict.get(key)
        if v is None:
            return None
        return v["verdict"] in DETECT and float(v.get("confidence") or 0) >= thr

    out = {"model": model, "package": PACKAGE, "n_calls": n_calls, "n_verifier_error": n_err,
           "incomplete": n_calls > 0 and n_err / n_calls > 0.10, "by_threshold": {}}
    for thr in THRESHOLDS:
        rec = defaultdict(lambda: defaultdict(lambda: [0, 0]))   # set|cat|fmt -> [n, det]
        fp_orig = defaultdict(lambda: [0, 0])
        ctrl = defaultdict(lambda: [0, 0])
        pairs = defaultdict(list)                                # set -> (raw, annotated) scale_swap
        review = defaultdict(int)
        for it in data["items"]:
            for fmt in FORMATS:
                if it["kind"] == "control":
                    fl = [flagged((it["set"], it["qid"], fmt, s), thr) for s in it["sentences"]]
                    if any(f is None for f in fl):
                        continue
                    c = ctrl[f"{it['set']}|{fmt}"]
                    c[0] += 1
                    c[1] += int(any(fl))
                    continue
                m = flagged((it["set"], it["qid"], fmt, it["mutated_sentence"]), thr)
                o = flagged((it["set"], it["qid"], fmt, it["original_sentence"]), thr)
                if m is None or o is None:
                    continue
                rr = rec[f"{it['set']}|{it['category']}"][fmt]
                rr[0] += 1
                rr[1] += int(m)
                fo = fp_orig[f"{it['set']}|{fmt}"]
                fo[0] += 1
                fo[1] += int(o)
                v = verdict.get((it["set"], it["qid"], fmt, it["mutated_sentence"])) or {}
                review[f"{it['set']}|{fmt}"] += int(v.get("action") == "review")
            if it["kind"] == "injected" and it["category"] == "scale_swap":
                a = flagged((it["set"], it["qid"], "raw", it["mutated_sentence"]), thr)
                b = flagged((it["set"], it["qid"], "annotated", it["mutated_sentence"]), thr)
                if a is not None and b is not None:
                    pairs[it["set"]].append((a, b))
                    pairs["pooled"].append((a, b))
        hv1 = {}
        for s, ps in pairs.items():
            b = sum(1 for a, an in ps if an and not a)     # annotated tespit, raw değil
            c = sum(1 for a, an in ps if a and not an)
            hv1[s] = {"n": len(ps), "annotated_only": b, "raw_only": c,
                      "recall_raw": sum(a for a, _ in ps), "recall_annotated": sum(an for _, an in ps),
                      "mcnemar_p": _mcnemar(b, c)}
        out["by_threshold"][str(thr)] = {
            "recall": {k: {f: {"n": v[0], "detected": v[1], "wilson": _wilson(v[1], v[0])}
                           for f, v in d.items()} for k, d in rec.items()},
            "original_sentence_fp": {k: {"n": v[0], "flagged": v[1], "wilson": _wilson(v[1], v[0])}
                                     for k, v in fp_orig.items()},
            "control_fp": {k: {"n": v[0], "flagged": v[1]} for k, v in ctrl.items()},
            "review_action_on_mutated": dict(review),
            "H_V1_scale_swap": hv1,
        }
    SUMMARY.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("model", "n_calls", "n_verifier_error", "incomplete")}))


def audit(audit_dir: str) -> None:
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY tanımlı değil")
    import csv
    d = Path(audit_dir)
    items = {json.loads(l)["item"]: json.loads(l)
             for l in (d / "audit_items.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    rows = list(csv.DictReader((d / "audit_sheet.csv").open(encoding="utf-8")))
    client = McpClient()
    with (d / "audit_jev.jsonl").open("w", encoding="utf-8") as fh:
        for item_id, it in items.items():
            nums = [r for r in rows if r["item"] == item_id and r["number"] != "0"]
            if not nums:
                continue
            sheet = "\n".join(f"{x['field']} | {x['value_en']} | {x['value_tr']} | {x['unit']}"
                               for x in it["reference_sheet"])
            evidence = f"Reference simulator output (field | value EN | value TR | unit):\n{sheet}"
            text = it["delivered_numbered"]
            claims = []
            for r in nums:
                tag = f"[#{r['number']}]"
                pos = text.find(tag)
                start = max(text.rfind(".", 0, pos), text.rfind("\n", 0, pos)) + 1
                end_dot = [e for e in (text.find(".", pos), text.find("\n", pos)) if e >= 0]
                sentence = text[start:min(end_dot) if end_dot else len(text)].strip()
                claims.append(f'The number "{r["shown_value"]}" in the following statement is '
                              f'supported by the evidence: "{sentence}"')
            resp, err = None, None
            for attempt in range(3):
                try:
                    resp = client.verify(claims, evidence)
                    break
                except Exception as exc:
                    err = repr(exc)
                    time.sleep(5 * (attempt + 1))
            fh.write(json.dumps({"item": item_id, "numbers": [r["number"] for r in nums],
                                 "claims": claims, "evidence": evidence, "response": resp,
                                 "verifier_error": None if resp else err},
                                ensure_ascii=False) + "\n")
    client.close()


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "audit":
        audit(sys.argv[2])
    else:
        {"run": run, "analyze": analyze}[cmd]()
