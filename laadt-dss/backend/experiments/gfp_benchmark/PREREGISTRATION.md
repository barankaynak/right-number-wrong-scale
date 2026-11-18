# GFP/GFS Deney Ön-Kaydı (A2) — v1.0 **FROZEN**, 2026-07-08

> **DURUM: ✅ FROZEN (v1.0) — scientific-advisor F6#2 onayı, 2026-07-08.**
> Bu ön-kayıt DONDU: git commit'i `prereg-v1.0` tag'iyle işaretlidir; §8
> SHA-256 hash'leri dosya-düzeyi sürüm kanıtıdır. **Bu noktadan sonra hipotez,
> metrik, parametre veya benchmark DEĞİŞTİRİLEMEZ** — zorunlu değişiklikler
> yalnız §9 Amendment Log'a tarihli gerekçeyle eklenir. Deney koşusu (G1/G2/G4)
> artık başlatılabilir.
> Sürüm geçmişi: v0.2 ORTA-9 revizyonu (referans-notlama, pre-intervention,
> H_G1a çerçevesi, H_G4 pilot-v3, legacy çift-okuma, seed+tekrar, chain-3 n=10);
> v0.3 KRİTİK-7 (tam-zincir referans, H_G2 birincil=in-run, compute_gfs.py);
> v1.0-rc F4/F5 (ikinci model qwen3.5:27b + §8 hash tablosu).
>
> **F6 sign-off süreci (scientific-advisor, 2026-07-08):**
> **#1 = ŞARTLI RED** — `compute_gfs.py` H_G2 analizi tekrar-düzeyi çalışıyordu
> (pseudoreplication, n 3× şişme, H_G2 lehine bias); donma F7 düzeltmelerine
> bağlandı. **F7 uygulandı:** F7-1 G2 → soru-düzeyi hücre-ortalaması (n=27/19/10;
> birim-testli); F7-2 tek-model assert + havuzlanmış-6 Holm ayrı
> `--pooled-sensitivity`; F7-3 within-repeat variance; F7-4 §8 hash `bccbc793`.
> **#2 = DONDUR/ONAY** — F7-1/2/3/4 doğrulandı, kod↔prereg (§6.2/§6.3/§7) birebir
> tutarlı, hash eşleşti. Ayrıntı: SCIENTIFIC_REVIEW.md v2.7 (netleştirmeler) + v2.8 (donma).
> Bu turda işlenen F6#1 netleştirmeleri (hipotez/parametre değişikliği YOK):
> §5 50→56 soru; §6.1 v2→v3; §6.2 McNemar hücre-düzeyi + Holm model-içi aile;
> §6.4 nihai taban-korpus; §6.5 G5 harness-yok dürüstlük notu; §7 invokasyon
> protokolü; §7.1 Bilinen sınırlar.

## 1. Çalışma

**Başlık (çalışma):** Right Number, Wrong Scale: Measuring Grounding Fidelity in
LLM-Orchestrated Energy-Investment Decision Support from Buildings to Feeders
**Platform:** LAaDT-DSS (fizik-temelli çok-paydaşlı TR enerji yatırım DSS'i).
**Ön-kayıt kapsamı:** G1, G2, G4, G5 (G3/SimBench ayrı protokol ekiyle donar).

## 2. Hipotezler (falsifiye edilebilir)

- **H_G1a (manipulation check):** Araç+guard (grounded_guard) kolu, çıplak-LLM
  (ungrounded) koluna göre REFERANS-GFS'te anlamlı yüksektir. *Çerçeve notu
  (ORTA-9a):* bu, tasarımın çalıştığını gösteren manipulation-check'tir; guard'lı
  kolun in-run GFS'i mekanik olarak yüksek olacağından TÜM kollar §3'teki
  kol-bağımsız REFERANS grafına karşı notlanır. Asıl bilimsel yük H_G1b/G2/G4'tedir.
- **H_G1b (guard marjinal katkısı — birincil):** grounded_guard, grounded_noguard'a
  göre kullanıcıya ULAŞAN yanıtların referans-GFS'inde anlamlı yüksektir
  (bloklama/düzeltme mekanizmasının katkısı; araç-çağırmanın katkısından İZOLE).
  İkincil: **pre-intervention GFS** (müdahale-öncesi ham LLM metni) iki kolda
  KARŞILAŞTIRILIR — fark yoksa kazanım tamamen müdahaleden gelir (dürüst ayrıştırma).
- **H_G2:** GFS, zincir uzunluğu (chain_length 1→3) arttıkça monoton düşer
  (grounded_noguard kolunda ölçülür — guard müdahalesi etkiyi maskelemesin).
- **H_G4:** GFP provenance guard'ın hata-yakalama recall'ü, legacy guard'ın
  BLOKLAMA-kararına göre dört kategoride de üstündür (value_fabrication,
  unit_swap, scale_swap, small_int_fabrication). *Pilot-v3 dayanağı (dev-korpus,
  NİHAİ ANALİZE GİRMEZ):* GFP 1.0/1.0/1.0/1.0 vs legacy 0.0/0.0/0.0/0.0; FP 0/0.
  Mekanizma revizyonları pilotla yinelendi: payback/ertele-cue (small_int),
  oran-bandı toleransı (0-1 kayıtlarında 0.5 mutlak toleransın %-iddialarıyla
  çarpışması — %35,1↔0.538 vakası — giderildi). **Legacy ÇİFT-OKUMA:** birincil
  karşılaştırma = bloklama-kararı (violations); ikincil = warnings-as-detection
  (legacy'nin uyarıları tespit sayılır; kontrol-FP'si de aynı cömert okumayla
  raporlanır — adil-baseline gereği).
- **H_G5:** GFS, agent hand-off sayısı (0→3) arttıkça monoton düşer;
  provenance-survival rate her hand-off'ta azalır.
- **Null-sonuç taahhüdü:** Her hipotezin reddi de raporlanır (ör. "provenance
  hand-off'a dayanıklı" bulgusu yayınlanabilir sonuçtur).

## 3. Birincil metrik — GFS (Grounding Fidelity Score)

Bir yanıttaki IGNORED-dışı sayısal iddialar kümesi n üzerinden:

```
GFS = n_GROUNDED / (n_GROUNDED + n_UNGROUNDED + n_SCALE_VIOLATION + n_UNIT_MISMATCH)
```

**Notlama referansı (ORTA-9a + KRİTİK-7):** GFS, kol-bağımsız **TAM-ZİNCİR
REFERANS grafına** karşı hesaplanır — soru başına `expected_tools`'un TÜM
adımları, `suggested_args_per_step` (adım-argümanları; policy adımları
`$prev.<key>` ile önceki adımların sonucundan GERİYE-DOĞRU-ARAMALI türetilir)
ile LLM'siz doğrudan çalıştırılır (`run_benchmark._reference_graph`);
ungrounded kol dahil TÜM kolların yanıtları bu grafa karşı notlanır
(`reference_check`). *KRİTİK-7 gerekçesi:* tek-adım referans, chain-2/3
sorularda (56'nın 29'u) mükemmel-grounded yanıtın referans-GFS'ini ≈1/zincir
yapıp H_G2'yi İNŞA GEREĞİ doğrulardı (ölçüm artefaktı). **Fail-fast:**
kurulumu başarısız referans → soru referans-temelli analizden kayıtlı-dışlanır
(sessiz devam yok); 56/56 referans doğrulandı. Bu doğrulama süreci bir de
ÜRETİM BUG'ı açığa çıkardı: `run_monte_carlo` LLM-aracı MC endpoint'ine
yanlış payload gönderiyordu (baştan beri 422) → araç fizibilite-öncesi adımla
düzeltildi, ilgili test gerçek sözleşmeye göre revize edildi.
In-run provenance raporu guard MEKANİZMASININ ölçümüdür; kollar-arası GFS
kıyası referans-temellidir.
**Pre-intervention GFS (ORTA-9b):** guard block-modunda nihai yanıt (retry/safe-
summary sonrası) mekanik-temiz olur; bu yüzden müdahale-ÖNCESİ ham LLM metninin
bileşenleri (`provenance.pre_intervention`) ikincil metrik olarak raporlanır.

- **Birincil tanım eşit-ağırlıklıdır** (her ihlal türü eşit). Ağırlıklı varyant
  (w_u, w_s, w_m) YALNIZ duyarlılık analizi olarak raporlanır; ağırlıklar donma
  anında w_u=w_s=w_m=1 olarak sabitlenir.
- Bileşen oranları (u, s, m) her koşuda AYRICA raporlanır (GFS'i tek sayıya
  indirgemenin bilgi kaybı Limitations'ta).
- n=0 (hiç sayısal iddia yok) yanıtlar GFS'ten HARİÇ, oranı raporlanır.
- **Over-blocking (guard yan-metriği):** grounded_guard kolunda bloklanan/retry'a
  giren yanıt oranı + insan-doğrulamalı yanlış-bloklama oranı (2 kodlayıcı).

## 4. Donmuş guard parametreleri (kod: `app/llm/provenance_guard.py`)

| Parametre | Değer | Not |
|---|---|---|
| Sayısal tolerans (göreli) | **%2** (birincil) | Duyarlılık: {%1, %5} yeniden-analiz |
| Mutlak tolerans (kademeli) | \|rv\|≤1.5 → max(%2, 0.01); 1.5<\|rv\|<30 → max(0.5, %2); ≥30 → %2 | Oran-bandı sıkı toleransı pilot-v3'te eklendi (%-iddiası↔oran çarpışması) |
| `_IGNORABLE_INTS` | {1,2,3,4,12,24,25,100,365,8760} | Karar-kritik yıl iddiaları MUAF DEĞİL: `_PAYBACK_CUES` (geri ödeme/dönüş, amorti, öder, ödeme süre, **ertele**) ±25 karakter penceresinde ise UNGROUNDED; yıl-sayıları (1990-2100) ve ≥100 hariç |
| Varlık-sayısı bağlamı | sayı + bina-tipi kelime ("40 daire") → IGNORED | Doğru-ölçek uyarı cümleleri bloklanmaz (dc-27) |
| Ölçek sözlüğü | `SCALE_DICT_VERSION = v3-2026-07-08` | İki-yönlü dev-korpus (27 FP + 8 FN probe, G1'den AYRI); testler: `test_calibration_dev_corpus_zero_false_positives` + `test_calibration_fn_probes_all_detected` |
| Birim çıkarımı | EN-YAKIN birim, ±30/15 karakter; eşitlikte uzun desen | |
| Retry bütçesi (block modu) | **1** | Latency+GFS etkisi raporlanır |
| MAX_TOOL_ROUNDS | 4 | |
| Oturum-kalıcı graf üst sınırı | 600 kayıt | |
| Ambiguous-match telemetrisi | rapor-başına sayaç | ProvenanceMatchRate şişme riski izlenir |

## 5. Modeller ve kollar

- **Birincil model:** `gemma4:e4b` (Ollama, self-hosted).
- **İkinci model (genellenebilirlik):** **`qwen3.5:27b`** (Ollama, self-hosted;
  kullanıcı onayı 2026-07-08). Farklı model ailesi (Qwen vs Gemma) + daha büyük
  parametre sınıfı → hem aile- hem boyut-idiosinkrazisi itirazını kapatır.
  Harness-uyumluluğu donma öncesi smoke ile doğrulandı (2 soru, tool-calling ✓;
  res-01'de guard'ın ilk gerçek bloklaması gözlendi — mekanizma ikinci modelde de işliyor).
  İkinci model doğrulamazsa iddia dürüstçe daraltılır.
- **Keşifsel üçüncü model (OPSİYONEL, amendment gerektirmez):** bir frontier API
  modeli (ör. Claude) ileride keşifsel analiz olarak eklenebilir; birincil
  hipotez testlerine DAHİL DEĞİLDİR, ayrı raporlanır.
- **G1 kolları:** grounded_guard / grounded_noguard / ungrounded (bkz.
  `run_benchmark.py`). Aynı 56 soru (`questions.json` v3) her kolda; kol-içi
  soru sırası sabit.
- **G5 kolları:** hand-off N∈{0,1,2,3} (tek-agent = N0); aynı G1 soruları.

## 6. Veri ve istatistik planı

### 6.1 Benchmark seti
`questions.json` **v3-2026-07-08 — 56 soru** (v3: chain-sorulara
`suggested_args_per_step` + `args_pinned` eklendi, bkz. §3): paydaş 14/15/14/13
(res/com/dis/sta), zincir 27×1 + 19×2 + **10×3** (chain-3 n=4→10: Page/Dunn
istatistik gücü için, ORTA-9 donma koşulu), 7 cross-ölçek tuzağı.
Set donma anında hash'lenir; sonradan soru değişikliği amendment gerektirir.

**Tekrar & seed politikası:** hücre (soru × kol × model) başına **3 tekrar**,
deterministik seed'ler {10000, 10001, 10002} (`orch._ollama_seed` → Ollama
options.seed), sıcaklık 0.3 sabit. Analiz birimi = hücre-ortalaması GFS;
tekrar-içi varyans ayrıca raporlanır.

### 6.2 G1 analizi
- Birim: yanıt-düzeyi GFS. Eşleştirilmiş tasarım (aynı sorular).
- **Test:** kol çiftleri için Wilcoxon signed-rank (GFS sürekli); ikincil olarak
  hücre-düzeyi "tam-temiz" ikilisi (hücrenin TÜM tekrarları GFS=1 ⇔
  hücre-ortalaması=1) üzerinde exact McNemar (binom; `compute_gfs.mcnemar_exact`).
  *F6 netleştirmesi:* tekrar-düzeyi ("yanıt-düzeyi") McNemar, aynı sorunun 3
  tekrarını bağımsız saymak olurdu — hücre-düzeyi tanım script'le birebir örtüşür.
- **Belirsizlik:** GFS farkları için 10.000-örneklem bootstrap %95 GA (soru-düzeyi yeniden örnekleme).
- Çoklu karşılaştırma: **Holm düzeltmesi, model-içi 3 kol çifti üzerinde**
  (modeller ayrı analiz edilir; ikinci model bağımsız genellenebilirlik
  replikasyonudur, §5 + §7 invokasyon protokolü). Duyarlılık: 6-testlik
  havuzlanmış aile (3 çift × 2 model; daha muhafazakâr) ayrıca raporlanır.
  *F6 netleştirmesi:* önceki "3 kol çifti × 2 model" ifadesi script'in
  model-başına-invokasyon yapısıyla çelişiyordu; birincil = model-içi aile.

### 6.3 G2 analizi
- **BİRİNCİL ölçüt (KRİTİK-7 kararı): in-run GFS**, grounded_noguard kolunda —
  in-run graf modelin GERÇEKTEN çağırdığı araçlardan kurulur, zincir-kapsama
  artefaktı taşımaz; kalıntı karıştırıcısı H_G2 ALEYHİNE çalışır (muhafazakâr).
  Referans-GFS aynı analizle İKİNCİL olarak raporlanır (karşılaştırma).
- chain_length gruplarına Kruskal-Wallis + Dunn post-hoc (Holm);
  Spearman ρ (chain_length, GFS). Karıştırıcı not: chain≥2 sorular doğal olarak
  daha çok iddia içerir → iddia sayısı kovaryat olarak raporlanır.
- Zincir grupları: n₁=27, n₂=19, n₃=10 (questions.json v3).

### 6.4 G4 analizi
- Enjeksiyon: `inject_errors.py`, seed=42; kategori başına **≥30** enjeksiyon
  (nihai set G1 grounded yanıtlarından üretilir; dev-korpus PİLOT içindir,
  nihai analize GİRMEZ — kalibrasyon/test ayrımı).
- **Nihai taban-korpus (F6 netleştirmesi):** birincil modelin G1 grounded
  kollarındaki (guard + noguard) **in-run İHLALSİZ** nihai yanıtları; taban
  temizliği enjeksiyon ÖNCESİ doğrulanır ki yakalanan ihlal enjeksiyona
  atfedilebilsin (önceden-var-olan ihlal recall'ü kirletmesin). Kategori
  başına ≥30 uygulanabilir enjeksiyon dolmazsa ikinci modelin temiz yanıtları
  eklenir (hangi yanıtın hangi modelden geldiği kayıt altında).
- Metrik: guard×kategori recall; kontrollerde FP oranı (precision).
- **Test:** guard çiftleri kategori-başına McNemar (aynı enjeksiyonlar iki guard'a).
- **Güç analizi:** hedef — recall 0.9 vs 0.5 farkını α=0.05, güç 0.8 ile tespit.
  İki-oran yaklaşımı: n = ((z₀.₀₂₅·√(2p̄q̄) + z₀.₂·√(p₁q₁+p₂q₂)) / Δ)²
  = ((1.96·0.648 + 0.842·0.583) / 0.4)² ≈ **19.4 → kategori başına n=30
  (muhafazakâr; eşleştirilmiş McNemar tasarımında güç daha yüksek).**
- İnsan doğrulaması: enjeksiyonların %20'si 2 bağımsız kodlayıcı; Cohen κ raporlanır.

### 6.5 G5 analizi
- Eşleştirilmiş Wilcoxon (N0 vs N3) + Page trend testi (N0→N3 monotonluk);
  provenance-survival rate hand-off başına raporlanır.
- **Dürüstlük notu (F6):** çok-agent deney-harness'ı bu donma anında HENÜZ
  İNŞA EDİLMEMİŞTİR. Burada donan: H_G5 hipotezi, kollar (N0–N3, §5), birincil
  metrikler (GFS + provenance-survival) ve istatistik planı. Hand-off'un
  OPERASYONEL tanımı (mesaj şeması, agent'lar arasında hangi bilgiler aktarılır,
  provenance-kayıtlarının taşınma kuralı) G3 gibi **AYRI protokol ekiyle**,
  G5 koşusundan ÖNCE donar; bu ek donmadan G5 koşulmaz ve G5 sonuçları
  ana-hipotez (G1/G2/G4) raporunu bekletmez.

### 6.6 Dışlama kuralları
- Ollama/API hatasıyla boş dönen koşu: 1 kez yeniden; yine hata → kayıtlı-dışlama.
- MockLLM-fallback'e düşen yanıtlar dışlanır (kayıt edilir).
- Dışlama oranı >%10 olursa koşu geçersiz sayılır, altyapı düzeltilip tekrarlanır.

## 7. Tekrarlanabilirlik

- Ham izler (JSONL) + benchmark + korpus + kod yayında paylaşılır.
- Sıcaklık 0.3 (mevcut orchestrator ayarı); model sürümleri kayıt altına alınır.
- Repo git altında; donma, F6 sign-off sonrası TEK bir commit'e `prereg-v1.0`
  git tag'iyle bağlanır — §8 SHA-256 hash'leri dosya-düzeyi sürüm kanıtıdır.
- **Analiz-invokasyon protokolü (F6):** `compute_gfs.py` **model başına ayrı**
  çağrılır (tek invokasyonda tek modelin JSONL'leri); modeller-arası havuzlama
  yapılmaz — ikinci model bağımsız genellenebilirlik replikasyonudur (§5).

### 7.1 Bilinen sınırlar (makale Limitations bölümüne haritalanır)

1. **Dev-korpus kısmen el-yazması** (spec "gerçek guard-off çıktılarından" idi);
   yalnız kalibrasyon amaçlıdır, nihai analize girmez (§6.4).
2. **Unit-denetimi** yalnız `_KEY_META`/`_ARG_UNITS` kapsamındaki anahtarlarda
   etkindir; boş-unit kayıtlar her birimle uyumlu sayılır (A1-r2 sınırı).
3. **GFS tek-sayı indirgemesi** bilgi kaybettirir — bileşen oranları (u, s, m)
   her koşuda ayrıca raporlanır (§3).
4. **Guard-kolu nihai-yanıt GFS'i mekanik olarak temizdir** (safe-summary öz-
   denetimden geçer) — pre-intervention ikincil metriğiyle ayrıştırılır (§3).
5. **Her iki model self-hosted/açık-ağırlık** (Gemma + Qwen); frontier-API
   genellemesi keşifsel-üçüncü modele bırakılmıştır (§5).
6. **Ölçek/agregasyon sözlüğü TR-diline özgüdür**; dil-genellemesi kapsam dışı.
7. **Oran-bandı sıkı toleransı**: 1.0–1.5 aralığındaki meşru değerlerde
   marjinal FN riski (v2.6 duyarlılık-notu); {%1, %5} yeniden-analiz
   kapsamında izlenir.

## 8. Donma anında doldurulacak dosya hash'leri (SHA-256)

| Dosya | SHA-256 |
|---|---|
| `questions.json` (v3) | `318bde9febbefa7801e89e2f193ff72d8a328eb977d614c27ca1890c86ec0f4a` |
| `dev_corpus.json` (v2) | `eeb6a252d4757957087b934dd9ca13502a0f72babf11043a9c886e9261296739` |
| `app/llm/provenance_guard.py` | `db385def93d130ee1b3ac9fea0d538c2a9c0ef30bcc18869f07680ff32aa3ae2` |
| `app/llm/ollama_orchestrator.py` | `819666d2b3c44bcb3cec4b958b0349f8fc3f3c94f540b99da3080b92461adbc4` |
| `run_benchmark.py` | `bf570604eab898b6abd7589a9066beda241670e31d58103bfbfcf9901f099a40` |
| `inject_errors.py` | `b4d2bd928124944616691736b781c2706df85e4fa97168a821078d6906e178df` |
| `compute_gfs.py` (F3 — ön-kayıtlı analiz; F7 sonrası) | `bccbc793d1b217d2ce267f4bcf8a7709c70feafdb5cf65f0336cccb454e197f4` |

(Hesap: SHA-256, 2026-07-08. Bu belgenin kendisi tabloya giremez — sürüm kanıtı
donma commit'i + `prereg-v1.0` git tag'idir; F6 onayında atılır.)

## 9. Amendment Log

### A8 (2026-07-09) — Guard blok precision'ı insan-kodlaması [EXPLORATORY]

**Gerekçe:** G1 sonuçlarında guard blok oranı yüksek (qwen %52) ama referans-GFS
artışı küçük (+~%2). Bu gerilim iki-kaynaklı olabilir: metrik-seyrelme (guard doğru
yakalıyor, ortalama seyreltiyor) vs over-block (guard sağlam yanıtları da blokluyor).
Ön-kayıtlı ölçütler bunu ayırt edemiyor → **keşifsel** insan-precision kodlaması
eklenir. Ön-kayıtlı H_G1a/H_G1b/H_G2 birincil ölçütleri DEĞİŞMEZ; bu ek analiz
makalede _exploratory_ olarak etiketlenir ve birincil sonucun yerine geçmez.

**Materyal (kodlama başlamadan DONDURULDU):**

| Dosya | SHA-256 |
|---|---|
| `a8_precision/A8_CODEBOOK.md` (v1.0-A8) | `13a08c107b943fb1cd47a29061c32e350a5c0ccbe622fe8a118ca5346a35244c` |
| `a8_precision/A8_coding_sheet.csv` (106 satır, KÖR) | `95735f23b2acb83fae71f40b4c8c7d0d8496eaacd3629fa581c094b8bc5dc414` |
| `a8_precision/A8_guard_key.csv` (kodlayıcıya kapalı) | `8c4991fd516b5bb17eea3d563b2e3328fb2bd137d94f139afd2003e2e0cd4a52` |
| `make_a8_package.py` (üretici) | `b10c224b0510e5827e927dea619a2b3b476a4da48319fb7b8f298a95f9b0de7c` |

**Tasarım:** 2 bağımsız kodlayıcı, guard etiketine kör; birincil IRR değişkeni
`block_justified_YN`, Cohen's κ; over-block oranı = P(N|bloklu); adjudication
üçüncü hakem. Metrikler §6/kodkitabı. Kodlama başladıktan sonra kodkitabı değişmez.

### A9 (2026-07-09) — G4 nihai koşu: uygulanabilirlik-sansüsü sonrası tasarım netleştirmeleri [PRE-OUTCOME]

**Gerekçe:** §G4 "kategori başına ≥30" hedefi, G1 grounded-temiz havuzunun gerçek
uygulanabilirlik verimine bağlıdır. Skorlama BAŞLAMADAN yapılan sonuç-kör mekanik
sansüs (iki modelin ham JSONL'leri): qid-düzeyinde value_fabrication ve
small_int_fabrication ≥30'u karşılamıyor. Aşağıdaki netleştirmeler hipotez, metrik
veya guard parametresi DEĞİŞTİRMEZ; tümü skorlama öncesi donar. (Danışman v2.10 onayı.)

1. **Analiz birimi:** benzersiz soru (qid). Kategori-başına temsilci = deterministik
   sırada (model gemma→qwen; kol noguard→guard[yalnız müdahalesiz]; seed artan) İLK
   grounded-temiz yanıt ki enjeksiyon o kategoride uygulanabilir olsun; qid×kategori
   başına 1 enjeksiyon. Tüm-temiz-yanıt havuzu yalnız duyarlılık (betimsel).
2. **Taban-temizlik & notlama:** GFP birincil = kol-bağımsız tam-zincir REFERANS grafı
   (çakışma-muhafazakâr — büyük graf GFP recall'ü ALEYHİNE); ikincil = in-run graf
   (tool_trace'ten deterministik yeniden-koşu). Her maddede orijinal metin kullanılan
   grafta 0-ihlal + GROUNDED≥1 doğrulanır. value_fabrication hedefi orijinal notlamada
   GROUNDED-eşleşen bir sayı olmalıdır (IGNORED/yıl hedefleri uygulanamaz — mekanik,
   SONUÇ-KÖR: hangi guard'ın yakaladığına bakmaz, yalnız kaynağın grounded sayısını hedefler).
3. **Legacy okumaları:** BİRİNCİL = deploy-sadık `validate_response(mutated, son-araç-sonucu)`,
   detection=violations. İKİNCİL-1 = aynı dict warnings-as-detection. İKİNCİL-2 =
   cömertlik-tavanı: zincirdeki her araç-sonucuna ayrı validate, herhangi birinde
   violation/warning → tespit. Kontrol-FP her okumada AYNI kuralla (simetri).
4. **Güç katmanlaması (hipotez değişikliği DEĞİL):** H_G4 dört kategoride sınanır;
   Tier-1 tam-güçlü doğrulayıcı = scale_swap + unit_swap (n≥30); Tier-2 uygulanabilirlik-
   sınırlı = value_fabrication + small_int_fabrication — exact McNemar (binom) + Wilson CI
   + dürüst-n. MDE: legacy-recall≈0 rejiminde kategori-içi ≥6 tek-yönlü discordant α=0.05'e yeter.
5. **İstatistik sabitleri:** enjeksiyon seed=42; bootstrap seed=20260708; kategori-başı
   exact McNemar; kategoriler-üstü havuzlanmış recall yalnız betimsel. Kategori×ihlal-türü
   kırılımı raporlanır (mekanizma-saflığı).
6. **Araç değişikliği (uygulama beyanı):** Nihai koşu AYRI modülde: `run_g4_final.py`
   (koşu harness'ı) + `compute_g4.py` (ön-kayıtlı analiz). `inject_errors.py` FROZEN
   §8 hash'iyle **BYTE-AYNI** kaldı (b4d2bd92…) ve unit_swap/scale_swap/small_int için
   değişmeden kullanıldı. **value_fabrication** naive `inject()` yerine `run_g4_final.py`
   içinde grounded-hedefli + CÜMLE-YEREL yazıldı (madde 2 gereği; naive inject() metindeki
   ilk rakam-eşleşmesini bozup liste-madde-numarası "1."yi bozan bir BUG içeriyordu —
   grounded-hedef bunun doğru uygulaması, sonuç-kör). Nihai koşu SHA-256'ları + sansüs n'leri:

   | Dosya | SHA-256 |
   |---|---|
   | `run_g4_final.py` | `c74a910283ea34985e3b16a510cb1618f8b981fea7871cbc08794984a168261c` |
   | `compute_g4.py` (ön-kayıtlı analiz) | `34c2227dc711882747705d33d50359e70f6a3d0bd4b2849ca9328875cbeef98b` |

   **Nihai sansüs n'leri (seed=42, 39 qid, 109 enjeksiyon + 39 kontrol):** scale_swap 31,
   unit_swap 30, value_fabrication 38, small_int_fabrication 10.
   **Güçlendirme beyanları (danışman v2.11.3-H5):** (i) **Simetri:** mutasyon-metni her
   iki guard'a (GFP + legacy) BİREBİR AYNI verilir; kontroller de her okumada aynı kuralla.
   (ii) **Zaman-çizgisi:** A9 tasarım-metni + koşu-dosyası hash'leri koşu-ÖNCESİ kayıtlarda
   (SCIENTIFIC_REVIEW v2.10.5, 2026-07-09); bu §9 girişinin YAZIMI koşu-sonrasıdır — git-tarih
   denetimine önden dürüst cevap; tasarım donması ≠ giriş-yazımı. (iii) **qwen-ekleme denetim-izi:**
   temsilci-model dağılımı gemma 92 / qwen 17 (gemma-öncelikli determinist sıra). Kategori-başı
   gemma/qwen: scale 28/3, unit 25/5, value 33/5, small 6/4 — qwen yalnız gemma'nın uygulanabilir
   temiz-kaynağı olmayan qid×kategori'lerde devreye girdi (§6.4 "ikinci-model genişletme" kuralı).
7. **Bilinen sınırlar (Limitations'a):** (i) scale_swap ifadeleri guard ölçek-sözlüğünün
   kapsadığı kelime alanındandır — recall sözlük-kapsamlı yeniden-çerçevelemeler için
   geçerlidir; ayrıca swap sayısız cümleye düşerse ihlal yaratmaz (ATIL enjeksiyon:
   31'in 6'sı SCALE_VIOLATION yarattı) — atıllar concordant-no-detect → McNemar-DEĞİŞMEZ,
   yalnız recall-oranını düşük gösterir. (ii) legacy bloklama-kanalı metne yapısal olarak
   duyarsızdır (violations yalnız fiziksel-sınır) — birincil-okuma 0-recall'ü tasarım
   özelliğidir, makalede açıkça belirtilir. Sonuçlar SCIENTIFIC_REVIEW v2.11'de.

### A10 (2026-07-09) — Bloklu-altküme karşı-olgusal + safe_summary zincir-sınırı [EXPLORATORY, POST-OUTCOME]

**Gerekçe:** G1'in "%52 blok ↔ +%2 GFS" gerilimini metrik-seyrelme vs over-block olarak
ayırmak. Keşifsel; ön-kayıtlı ölçütlerin yerine GEÇMEZ. Script: `a9_counterfactual.py`
(SHA-256 commit `7eb48e2`'de; dosya-adı tarihsel, log-etiketi A10).
**Yöntem:** bloklu 106 yanıtın pre-intervention ham metni kol-bağımsız referans-grafiğe
YENİDEN-notlanır (kayıtta yalnız safe_summary'nin ref-GFS'i saklı); eşleştirilmiş
ref-GFS(safe) vs ref-GFS(ham). **Bulgular:** (a) bloklu ham metinlerin %100'ü (gemma) /
%98'i (qwen) referansa karşı gerçek ihlalliydi → over-block DEĞİL; (b) sürekli ref-GFS
kazancı küçük+anlamsız → guard değeri İKİLİ (McNemar-reframe); (c) qwen bloklarının
%76'sında safe_summary bilgisiz non-cevap — kök neden: safe_summary yalnız son araç
sonucunu okur, Monte-Carlo-biten zincirlerde iç-içe istatistik anahtarları skaler
_KEY_META ile eşleşmez (dondurulmuş sistem sınırı; Limitations).
> **⚠️ v2.12 GÜNCELLEME:** A10(a)'nın "over-block ≈ 0 / bloklar %100 haklı" okuması da
> AYNI değer-eşleştirme enstrümanına dayanıyordu → **instrument-unverifiable** olarak
> geri çekildi (bkz. A11). Referans-graf değer-eşleştirmesi 1.1024↔1,102 gibi meşru
> format-farklarını "ihlal" sayabildiği için "%98-100 haklı" da kanıt olarak kullanılamaz.

### A11 (2026-07-09) — A8 GERİ ÇEKİLDİ (never run) + canlı-flag taksonomisi [POST-OUTCOME, kullanıcı-yönlendirmeli; danışman v2.12 onayı]

**Gerekçe:** A8 (canlı guard bloklarının insan-precision doğrulaması) HİÇ KOŞULMADI ve
GERİ ÇEKİLDİ — desteklediği iddiayla (manşet katman-iii: "guard N canlı uydurma yakaladı")
BİRLİKTE düştü, o yüzden prereg-ihlali değildir (gate, iddiasıyla beraber kalkar).
Kullanıcı (bilişim araştırmacısı) elle-kodlamanın (a) simülasyon çıktılarını elle
doğrulamanın imkânsızlığı, (b) gerçek hataların yok denecek azlığı, (c) guard'ın minik
artefaktları işaretlemesi nedeniyle uygulanamaz olduğunu tespit etti.

**Kanıt — otomatik canlı-flag taksonomisi** (`analyze_guard_flag_taxonomy.py`, SHA-256
`25925237dcaddcd34675e1a5ff93274184a20786c91775412af0f044d0a99aea`; 106 bloklu yanıt,
696 flag): value_matches_reference_FP %20,3 (sayı ASLINDA doğru → guard FP);
percentile/pct-label %4,3; small_int_context %25,9; **unresolved_by_value_matching %49,6**
— AMA bu son kategori DOĞRULANMIŞ UYDURMA DEĞİL: değer-eşleştiricinin (guard ve script
AYNI zaaf) çözemediği artık, örnekleri sık sık meşru sayılar (gerilim 1.1024↔referans 1,102).

**Hüküm (danışman v2.12):** (i) hiçbir canlı-sayım (591/32/44) makalede iddialaşmaz;
(ii) guard "hata-dedektörü" değil **"fail-closed doğrulanabilirlik-filtresi"** diye
çerçevelenir; (iii) taksonomi tablosu + değer-kanalı iki-yönlü doygunluğu (FP: format;
FN: aliasing, A9-madde) makalede POZİTİF bulgu = "provenance değer-ötesine (fonksiyon/
ölçek/birim/bağlam) uzanmalı — GFP varlık-gerekçesi"; GFP'nin kendi UNGROUNDED kanalının
bu sınırı miras aldığı teslim edilir. (iv) A8 materyalleri (§9-A8 hash'li) repoda kalır,
"WITHDRAWN — never run" etiketiyle.

**G4 kontrol-FP çerçevelemesi (v2.12-rigor):** GFP'nin 0/39 kontrol-FP'si BY-CONSTRUCTION
(kontroller seçimde aynı grafla temiz-doğrulandı → deterministik yeniden-notlama zorunlu 0)
→ makalede "harness-bütünlük denetimi" diye sunulur, SAHA-precision DEĞİL; **"at zero
false-positive cost" ifadesi YASAK**; legacy-FP'leri (S1 %38, S2 %64) bilgilendirici kalır;
canlı-FP taksonomisi Limitations'a zorunlu girdi. H_G4 kategori-McNemar sonuçları ETKİLENMEZ
(iki guard aynı metni görür, ground-truth bilinir). **G4 %20 mutasyon-kalitesi denetimi
DÜŞMEZ** (lay-yapılabilir akıcılık/kategori-uygunluğu; frozen H_G4 şartı).

### A12 (2026-07-09) — G3 cross-scale ön-kayıt eki [tasarım PRE-OUTCOME; ilk koşu keşifsel; danışman v2.13]

Feeder/cross-scale iddiasının (canlı-SCALE v2.12'de düştü) TEK gerçek kanıtı. Ayrı ek:
**`PREREGISTRATION_G3.md`** + `g3_cross_scale.py` (SHA-256 **G3-V1 storage-fix sonrası**
`2fa512f91385f1368bc6884e043c9ab849447672ef60b597aec120ef4399fee1`).
**Özet:** her müşteri net-zero (grid-kör) → 6 SimBench LV fider census → öğle (yük 0.20,
PV 0.85, slack 1.025) NR yük-akışı; **çift-kriter** (slack-bağımsız ΔV>%3 BİRİNCİL +
mutlak Vmax>1.05 İKİNCİL slack-koşullu + trafo/hat termal); metrik = kanal-başına doğrudan
ihlal + **kritik ölçekleme f\*** (uniform-hosting DEĞİL). Karar-kuralı: manşet slack-bağımsız
kanallar; rural1 baz-gerilim confound'u (bazı PV'siz 1.048) açıkça beyan → mutlak-kriter o
fiderde PV'yi abartır, ΔV de-confound eder. **Sonuç (G3-V1 storage-fix sonrası):** net-zero'da
1/6 (semiurb4) ihlal; ΔV'de 6/6 fider ≤1.56× oversize'da ihlal (f*_ΔV 0.86-1.56); rural1'in ilk-koşu
sahte "dramatik" trafosu (f*=0.23) storage-kontaminasyonuydu → düzeltildi f*_traf 1.50 (aykırı-değer YOK). GFP-bağı:
yeni canlı-guard demosu YOK (v2.12 cephesini açmaz) — G3-olgu + G4-yetenek + birim-test
worked-example üçlüsü. İlk koşu POST-OUTCOME; f*-sweep + duyarlılık-ızgarası + kriter/karar
kuralları bu ekle PRE-OUTCOME sabitlendi.

### A13 (2026-07-10) — B4: G4 enjeksiyon mutasyon-kalitesi insan-kodlaması [EXPLORATORY, PRE-CODING]

Danışman v2.12.6-2 "yayın-kapısı": H_G4 enjeksiyonlarının **%20'si** (109'un 22'si),
2 bağımsız kodlayıcı tarafından **akıcılık** + **kategori-uygunluğu** açısından,
guard'ın kararına **KÖR** olarak denetlenir. Materyal `b4_mutation_quality/`:
- `B4_CODEBOOK.md` (v1.0-B4, donmuş) — ölçütler, KÖR protokol, adjudication, metrikler.
- `B4_coding_sheet.csv` (22 satır, katmanlı: value 8 / unit 6 / scale 6 / small-int 2;
  seed=42). SHA-256 **`eacb5b4acc2daee67803fcbaf11c0dc7ff0e2196a5e489dfedcb63dd99534f6b`**.
- `B4_guard_key.csv` (kodlayıcılara KAPALI) SHA-256
  **`b1242b1156b8200b843d471c3b06444e8213bca78cc38077fe38823fd3201904`**.
- `make_b4_package.py` (üretici), `compute_b4_kappa.py` (Cohen's κ + oranlar).

**Materyal notu (metin otantikliği):** Donmuş G4 raw (`raw_g4_final_seed42_20260709T011118Z.jsonl`,
OTORİTER) mutasyon METNİNİ saklamıyordu. `run_g4_final.py` `source`+`mutated` yazacak
şekilde güncellendi (ek; tespit-mantığını ETKİLEMEZ). Seed=42 determinist yeniden-koşu
**97/109** enjeksiyonu yeniden üretti (3 qid'in referans-grafı canlı-veri/simülatör
kaymasıyla düştü — mutasyon-kalitesiyle İLGİSİZ; determinizmin çevre-bağımlılığı
kayıtlı). Örneklem YALNIZ bu 97 otantik-metinli, donmuş-eşleşen satırdan → her kodlama
öğesinin gerçek mutasyon metni var. Metrik metne değil, tespit-bayraklarına göre;
donmuş 109 otoriter kalır. **Statü:** kodkitabı + sayfa DONDU, kodlama BAŞLAMADI.
Sonuç makalede _exploratory_ raporlanır; H_G4 birincil McNemar'ı DEĞİŞTİRMEZ (geçersiz
öğeler ağırlıkla eşzamanlı-tespit-edilmeyen → discordant çiftleri etkilemez), ancak
düşük geçerli-öğe oranı çıkarsa recall-seyrelmesi dürüstçe raporlanır / enjeksiyon
grounded-hedefli daraltılıp yeniden koşulabilir.

### A14 (2026-07-10) — CROSS-LINGUAL: İngilizce dil-koşulu + TR–EN karşılaştırma [PRE-OUTCOME]

**Gerekçe:** v1.0'daki tüm LLM-değerlendirmesi Türkçe yapıldı (sorular + yanıtlar +
Türkçe-ayarlı guard). Bu bir genellenebilirlik-sınırıydı (uluslararası Q1 dergi hakemi
"İngilizce'ye/başka dile transfer eder mi?" diye sorar). Onu bir _threat-to-validity_
olarak bırakmak yerine, **İngilizce'yi ikinci dil-koşulu olarak EKLİYORUZ ve
KARŞILAŞTIRIYORUZ** — dil-genellenebilirliğini caveat ile değil VERİYLE yanıtlarız.
Türkçe v1.0 BİRİNCİL kalır ve çöpe gitmez; İngilizce _eklenen koşuldur_ (sonuç görülüp
dil değiştirilmedi — v1.0 sonuçları donmuş, İngilizce koşu bu ekle PRE-OUTCOME dondu).

**Tasarım (dil TEK değişen faktör):** aynı 56 soru **birebir İngilizce'ye çevrildi**
(`questions.json` → her soruya `question_en`; aynı Türk piyasası: Ankara/TL/EPDK, aynı
sayılar, aynı `scale_focus` — 7 cross-scale trap dahil). **İngilizce sistem promptları**
(`stakeholder_prompts.py` → modele "respond in English"). **Guard iki-dilli** yapıldı
(`provenance_guard.py` `SCALE_DICT_VERSION="v4-bilingual-2026-07-10"`: EN ölçek-sözlüğü +
agregasyon + payback-cue + birim + EN sayı-formatı `1,234.56`/büyüklük thousand/million/
billion EKLENDİ, TR korundu; guard dil-agnostik — cümlede hangi dilin terimi geçerse
yakalar). Aynı modeller (gemma4:e4b, qwen3.5:27b), aynı kollar (guard/noguard/ungrounded),
aynı seed'ler {10000,10001,10002}, 3 tekrar, hücre-ortalaması analiz-birimi.

**İngilizce guard KALİBRASYONU (koşudan önce, donmuş):** `dev_corpus_en.json` (27 FP +
8 FN probe, TR dev-korpusun birebir İngilizce'si) → **FP 0/27, FN 0/8 TEMİZ**; TR
dev-korpus regresyonu **0/0** (İngilizce ekleme Türkçe'yi bozmadı); 32 guard testi +
277 paket testi geçer.

**Cross-lingual hipotezler (PRE-OUTCOME):**
- **H_LANG-1 (birincil, null-yönelimli):** GFP'nin çekirdek bulguları dile-DAYANIKLIDIR
  — (a) G1 mekanistik ayrıştırma (guard ham metni değiştirmez; değer müdahalede),
  (b) G4 yapısal-körlük (point-check ölçek/birim-bozulmalarını üretim-okumasında kaçırır),
  (c) taksonomi iki-yönlü doygunluğu — İngilizce'de de tutar.
- **H_LANG-2 (keşifsel):** GFS düzeyi ve guard-davranışı (blok-oranı, recall) diller
  arasında FARKLI olabilir; fark ölçülür ve raporlanır (dil-duyarlılığı başlı başına bulgu).

**Analiz:** G1/G2/G4/taksonomi HER DİL için AYRI hesaplanır (mevcut `compute_gfs.py`/
`compute_g4.py`, `--lang` ile) + TR↔EN karşılaştırması (ΔGFS, Δrecall; dil bir faktör).
G3 (fizik/SimBench) dil-BAĞIMSIZ — değişmez. Makale: dil bir GÜÇ olarak çerçevelenir
(caveat değil); yeni "cross-lingual robustness" alt-bölümü + figür/tablo.

**Donmuş İngilizce-koşul dosya hash'leri (SHA-256, koşu-öncesi):**

| Dosya | SHA-256 |
|-------|---------|
| `questions.json` (v3+en) | `7c5332396e0d7514cf00ffc7120debe8ed8ce8ae01ecb80d7c70feb7f9b4d546` |
| `dev_corpus_en.json` | `66dc084513a90cc349d0b6e9a7ab9329bae3ad257b846ca35aad5f38db4e145c` |
| `app/llm/provenance_guard.py` (v4-bilingual) | `2a9c5f6a7e1ec9d4a9371a3e6140d547bb0e1349e65bbcce6988afc7e3409850` |
| `app/llm/prompts/stakeholder_prompts.py` | `8ac4d7ebd7ece693003fd5ddcfde43ab9955a26c4e4b3f1fbc3ef795089906ea` |
| `app/llm/ollama_orchestrator.py` | `1db0f04647d3d7a6b29cca7c8936db170780eb33a9c6c0d9b42ab042f51bad04` |
| `run_benchmark.py` | `7cba4a7d3c1b025729c5a4a2e7275104aea1db11008468c28cd9008f02137d64` |

**Statü:** kod + içerik + kalibrasyon DONDU (yukarıdaki hash'ler); İngilizce G1 koşusu
BAŞLATILIYOR. G4 için `inject_errors.py` İngilizce-swap eki ayrı sub-amendment (G4
koşusundan önce) ile dondurulur.

### A15 (2026-07-10) — Birim-çıkarımı parser düzeltmesi (mekanik bug; her iki dile SİMETRİK) [PRE-FINAL-ANALYSIS]

**Bulgu (İngilizce G1 koşusu sırasında gözlendi, gemma-EN kısmi çıktısından):**
`provenance_guard._infer_claim_unit` iki mekanik kusur taşıyordu:
1. Fonksiyon "SONRA" penceresinde birim bulunca "ÖNCE"ye bakmadan dönüyordu → sayının
   HEMEN ÖNÜNDEKİ para-simgesi (₺), ~20 karakter SONRAKİ "years"e yeniliyordu
   ("₺33,956 ... over 25 years" → yanlış `yıl`, doğrusu `TL`) → gerçekte grounded NPV
   sahte-UNIT_MISMATCH.
2. 30-karakterlik pencere **tablo-hücresi/satır sınırını (`|`, newline) aşıyordu** →
   yandaki hücrenin birimi sızıyordu ("0.1039 | 9,635 kWh" → 0.1039'un birimi sahte-kWh).
   İngilizce'nin tablo-ağırlıklı biçimi bunu daha çok tetikliyordu.

**Düzeltme:** (1) ÖNCE+SONRA BİRLİKTE değerlendirilir, GLOBAL en-yakın birim kazanır;
(2) pencere `|`/newline'da kırpılır (hücre-sınırı aşılmaz). **Dil-agnostik ve her iki
dile SİMETRİK** uygulanır — sonucu değil mekanik bug'ı hedefler, held-out dev-korpusla
doğrulanır → dil-cherry-picking imkânsız.

**Doğrulama:** vaka-testleri (₺33,956/years→TL; 0.1039|kWh→None; "7 yıl"→yıl;
"500.000 TL"→TL); **iki dil dev-korpus FP 0/0 FN 0/0**; 32 guard testi geçer.

**NİHAİ-SKORLAMA KURALI (bütünlük):** G1 birincil metriği = referans-GFS, LLM'in
**pre_intervention** (guard-öncesi ham) metni üzerinde POST-HOC skorlanır — guard-sürüm
BAĞIMSIZ üretim. Koşu-içi guard (v4) yalnız guard-kolu teslim-metnini/bloklamayı etkiler
(ikincil). **Cross-lingual karşılaştırma ve tüm nihai metrikler, HER İKİ DİLİN saklı
pre_intervention yanıtları BU sürümle (v4.1) yeniden-skorlanarak hesaplanır** →
tek-guard, adil karşılaştırma; LLM yeniden-koşusu GEREKMEZ. Türkçe v1.0 birincil
sonuçları da v4.1 altında yeniden-doğrulanır (materyal değişirse raporlanır).

**Yeni hash:** `app/llm/provenance_guard.py` (v4.1) SHA-256
`d7644303ad94f6aba4dac4116db20eb2bebddebabb4bc0a3b62146804ce1f233`.

### A16 (2026-07-10) — Üçüncü açık-model (Mistral Small 3.2 24B), TR-birincil genelleme [PRE-OUTCOME]

**Gerekçe:** Danışman v2.14/v2.16 ve ön-kayıtın "iki model" sınırı en büyük genelleme
threat'iydi. Claude-proxy (v2.16) proxy-yolu confound'u + soru-yazarı/denek örtüşmesi
nedeniyle REDDEDİLDİ. Onun yerine **üretim Ollama function-calling yolundan geçen,
FARKLI AİLEDEN üçüncü bir açık-model** eklenir — tüm confound'lar kapanır:
- **Model:** `mistral-small3.2:24b` (Mistral AI; 24B, Q4_K_M; native function-calling).
  Üç ayrı lab: **Gemma (Google, 8B) + Qwen (Alibaba, 28B) + Mistral (Fransa, 24B)**;
  boyut aralığı 8B→24B→28B.
- **Yol AYNI:** aynı orchestrator, aynı tool-şeması, aynı prompt (stakeholder_prompts),
  aynı guard (v4.1), aynı seed'ler {10000,10001,10002}, 3 tekrar, 3 kol → temiz,
  yeniden-üretilebilir; proxy-confound YOK.
- **KAPI (koşu-öncesi doğrulandı):** tool-calling smoke — Mistral `simulate_pv_bess`
  çağırdı, TR grounded yanıt (12 GROUNDED, 0 ihlal, passed). Araç çağırıyor → geçerli.
- **Tek dil (TR-birincil):** danışman H_LANG uyarısı gereği 3. model cross-lingual
  eksene SOKULMAZ (dil×model×yol üç-yönlü etkileşim, güç≈0). Yalnız primary G1/G4
  genellemesini güçlendirir: "yapısal bulgular (nokta-guard körlüğü, cross-scale) 3.
  açık modelde de tutuyor mu?"
- **SONUÇ-KOŞULSUZ RAPORLAMA (taahhüt):** Mistral sonucu ne olursa olsun raporlanır;
  "iyi görünürse ekle" post-hoc seçimi YOK. Bu ek koşu-ÖNCESİ donar.
- **Rol:** birincil hipotez-testlerine (H_G1/H_G4/H_LANG) DAHİL DEĞİL — açık modeller
  genelinde tutarlılık için ek kanıt; makalede 3-model tablosunda + genelleme cümlesinde.

Donmuş materyal A14/A15 ile AYNI (guard v4.1, questions v3+en'in TR metni, promptlar,
orchestrator, runner — hash'ler yukarıda); yeni değişken yalnız MODEL. Koşu:
`run_benchmark --model mistral-small3.2:24b --lang tr --repeats 3` (G1) → `run_g4_final`
(G4). **Statü:** kapı GEÇTİ, A16 DONDU, TR-Mistral G1 BAŞLATILIYOR.

### A17 (2026-07-14) — B4 mutasyon-kalitesi analiz-planı (kodlayıcı-2'den ÖNCE dondu) [PRE-CONSENSUS]

Danışman v2.19: kodlayıcı-1 (Baran) 51/51 tamamlandı; **kodlayıcı-2 başlamadan** analiz-planı
donar ("analysis chosen after κ" itirazını kapatır). Materyal hash'leri (dondu):
- `B4_coding_sheet.csv` `4e3b709b7ee5a41070fcf0c71cd1467b8a60defd209784ebbab26d0c9d12f1cd`
- `B4_guard_key.csv` `abb66036c4be47060b34dc53c05a6d1e7295ead3b3203cc3b6502f8f35f9ea97`
- `B4_CODEBOOK.md` `014a833270b353fdf000a9d1d63561b87931c271156ad303e3fff7f620bdd356`

**Örneklem:** 3 G4 setinin (TR-primary 109, EN 87, Mistral 66) %20'si, kategori-oranıyla
katmanlı, seed=42 → 51 öğe (TR-19/EN-18/Mistral-14). Otantik mutasyon metni.

**Değişkenler (kodlayıcı-başı, KÖR):** `fluent_YN` (akıcılık) + `category_correct_YN`
(mutasyon gerçek bir simülasyon-sonucu/karar-değeri üzerinde mi). Türetilen:
`valid_item = fluent AND category_correct`.

**Kodlayıcı-2 protokolü:** guard-çıktısına VE kodlayıcı-1 etiketlerine **kör**; aynı 51 öğe;
kodlayıcı-1'in makale-yazarı olduğu **açıkça beyan edilir** (bağımsızlık-sınırı).

**Raporlanacak analizler (dondu):**
1. **Cohen's κ** (fluent + category_correct ayrı, ham 2-kodlayıcı) + ham anlaşma.
2. **Geçerli-öğe oranı** (konsensüs-sonrası), Wilson %95 GA; kategori + set kırılımı.
3. **Birincil H_G4 DEĞİŞMEZ:** ITT per-kategori exact McNemar (tam enjeksiyon-setleri,
   invalid dahil) — audit bunu ETKİLEMEZ (simetri: iki dedektör aynı metni gördü,
   invalid öğe discordance üretemez).
4. **İkincil/betimsel:** valid-altkümede GFP recall (Wilson GA ZORUNLU — n küçük) vs
   legacy; **legacy'nin insan-onaylı geçerli öğelerde de 0 olması** ("baseline yalnız
   çöp-mutasyonda başarısız" itirazını kapatır) manşet ikincil-bulgu.
5. **Triangülasyon:** insan valid-rate (scale ~%18) vs otomatik atıl-analiz (~%19) —
   iki bağımsız enstrümanın yakınsaması.

**κ düşükse (duyarlılık-üçlüsü, dondu):** (a) ham-κ raporlanır; (b) konsensüs-etiketleriyle
analiz; (c) yalnız-iki-kodlayıcı-hemfikir alt-kümede duyarlılık — üçü de raporlanır.

**Enjeksiyon prosedürü YENİDEN KOŞULMAZ:** düşük valid-rate (unit ~%7 veri-isteği-etiketleri,
scale ~%18) audit-görüldükten-sonra grounded-hedefli daraltma = sonuç-koşullu ayarlama
(v2.11.3-H5 Option-B sonuç-öncesi reddedildi). Çözüm: audit-temelli dürüst savunma +
"claim-targeted injection = future work" cümlesi + unit-%7 kök-nedeni Limitations'a.
**Tek-kodlayıcı sonucu makaleye İŞLENMEZ** (frozen §6.4 = 2 kodlayıcı+κ).

### A18 (2026-07-22) — B4 konsensüs prosedürü ve raporlama-kuralı [POST-κ, PRE-CONSENSUS]

Kodlayıcı-2 (kör) 51/51 tamamladı; A17'de donmuş analizler koşuldu ve κ GÖRÜLDÜ
(saklanmaz, aşağıda kayda geçer). Konsensüs-etiketleri HENÜZ ÜRETİLMEDİ; bu amendment
adjudikasyon oturumundan ÖNCE, danışman hükmü v2.20 uyarınca donar.

Materyal hash'leri (dondu):
- `B4_coding_coder1.csv` (kodlayıcı-1, yazar) `e9485418b7bd76d0f1bbf8304fa7aad1b5d5b082a0fd15b501269d58538a20fb`
- `B4_coding_coder2.csv` (kodlayıcı-2, kör) `751de1cc14482c4c18e932124c68df36d4de3455b434cd84d0c7ad007b87773d`
- `B4_results.json` (A17 analizleri) `e90ad009e6ff5ad6518c02eab26a9badc5af17a9b51326b2ae6464d4c79cde24`

**(i) Gözlenen güvenilirlik (kalıcı kayıt).** n=51. `fluent_YN`: κ=0.284, ham anlaşma
%64.7, hücreler [K1=Y/K2=Y 26 | **K1=Y/K2=N 0** | K1=N/K2=Y 18 | NN 7].
`category_correct_YN`: κ=0.125, ham anlaşma %45.1, hücreler [17 | **0** | 28 | 6].
**Her iki değişkende K1=Y∧K2=N hücresi SIFIR** → katı kodlayıcının (K1) kabul-kümesi
gevşek kodlayıcının (K2) ÖZ ALT-KÜMESİDİR (nested). Marjinal-homojenlik exact testi
(discordant hücreler üzerinde iki-yönlü binom): category p=7.45×10⁻⁹, fluent p=7.63×10⁻⁶.
Bu test bir **anlaşmazlık-YAPISI betimidir**, güvenilirlik-kurtarma katsayısı DEĞİLDİR;
κ sonrası eklendiği açıkça beyan edilir (girdi hücreleri A17-donmuş script çıktısıdır,
yeni ölçüm yoktur). Kayıt için Gwet AC1 (category −0.049, fluent +0.380) ve PABAK
(−0.098 / +0.294) `B4_results.json`'a yazılır; **makalede "kappa paradoksu / marjinal
dengesizlik κ'yı deflate ediyor" savunması KULLANILMAZ** (ham anlaşma %45'i hiçbir
şans-düzeltmesi kurtarmaz; en fazla tek önleyici cümle: "prevalence-adjusted coefficients
do not materially improve it").

**(ii) Konsensüs prosedürü.** Adjudike edilecek küme = `category_correct_YN`
anlaşmazlıkları (28) ∪ `fluent_YN` anlaşmazlıkları (18) BİRLEŞİMİ, öğe-öğe. Karar,
iki kodlayıcının uzlaşı görüşmesiyle (kodkitabı §6.2) verilir ve **her karar YAZILI bir
kodkitabı-maddesi atıfıyla gerekçelendirilir** (§3 akıcılık / §4 kategori dışlama-maddeleri).
Yazar-otoritesi değil madde-metni karar verir. Çıktılar: `B4_consensus.csv` (öğe-başı
konsensüs `fluent_YN`/`category_correct_YN`) + `B4_adjudication_notes.csv` (öğe-başı
madde-atfı ve gerekçe); ikisinin de SHA-256'sı bu amendment'a ek olarak işlenir.

**(iii) Eşitlik-bozma kuralı (dondu).** Bir öğe ancak **spesifik bir kodkitabı
dışlama-maddesi (§3 veya §4) gösterilebiliyorsa** konsensüs-**N** olur; gösterilemiyorsa
konsensüs-**Y**. Gerekçe: bu, kodkitabının kendi tereddüt-kuralının ("sonuç sayısını
etkiliyorsa Y") yönüdür VE yazar-aleyhine muhafazakârdır — payda büyür, geçerli-altküme
GFP-recall'ü DÜŞER.

**(iv) Sonuç-koşulsuz taahhüt.** Konsensüs nokta-değeri **ve** katı–gevşek sınırların
ÜÇÜ DE raporlanır (nested yapıda AND=K1, OR=K2). Yeniden-kodlama YOK, kodkitabı
post-hoc netleştirme YOK, G4 enjeksiyon-koşusu YENİDEN KOŞULMAZ (A17 teyidi).
"Re-operationalized codebook with additional independent coders" + "claim-targeted
injection generation" = **future work** cümleleri.

**(v) Raporlama-kuralı (dondu).** (a) Manşet = **invariant**: konvansiyonel nokta-denetimi
her eşikte 0 tespit (0/14 katı-geçerli, 0/42 gevşek-geçerli, 0/51 ITT). (b) Geçerli-altküme
GFP-recall'ü **%78.6 hiçbir yerde %42.9'suz anılmaz** (iki sınır birlikte, Wilson GA ile).
(c) Kategori-invalid öğelerdeki GFP tespitleri (katı eşikte 9/37) geçerli-altküme
recall'üne DAHİL EDİLMEZ, ayrı satırda betimsel raporlanır. (d) **A17-3'ün gerekçe-cümlesi
DÜZELTİLDİ:** "invalid öğe discordance üretemez" ifadesi ampirik olarak YANLIŞTIR
(legacy her yerde 0 olduğundan 20 GFP tespitinin tamamı discordant çifttir ve 9'u
katı-eşikte invalid öğededir) ve **makaleye girmez**. Yerine geçen doğru zincir:
(1) ITT-estimand audit'ten ÖNCE donmuştu; (2) invalid öğeler iki dedektörü **simetrik**
seyreltir (ikisi de birebir aynı teslim-metnini gördü); (3) invalid-öğe tespitleri ayrı
raporlanır ve meşrudur (metin gerçekten bozulmuştur); (4) mutasyonsuz kontrolde FP=0.
(e) İnsan-vs-otomatik valid-rate triangülasyonu (scale %18 ↔ %19) yalnız **disclosure'lı**
biçimde yazılır (yazar-kodlayıcı otomatik tahmini biliyordu → corroborative, bağımsız
değil) ya da tamamen düşülür; bağımsızlık imasıyla ASLA.

**Statü:** A18 DONDU → adjudikasyon oturumu BAŞLAYABİLİR.

#### A18-ek (2026-07-22) — konsensüs SONUCU (adjudikasyon tamamlandı)

Adjudikasyon oturumu A18-(ii)/(iii) uyarınca yapıldı. Çıktı hash'leri (dondu):
- `B4_consensus.csv` `4d8515340da25787c31cfc7d4b2444aeda11efdebd6aae0cf87b25e2b1ab2c5e`
- `B4_adjudication_notes.csv` `8493f4eef6967b900937dec568a9090cda847eed54fac86b89e801719021d412`

**Prosedür-ifası:** 51 öğenin 18'i hemfikir (otomatik taşındı), 33'ü adjudike edildi
(46 değişken-kararı). **45 geçersizlik-kararının 45'i de spesifik kodkitabı-maddesi
atıflı + yazılı gerekçeli**; madde gösterilemeyen hiçbir öğe N yapılmadı (A18-(iii)
eşitlik-bozma kuralı ihlal edilmedi). Kullanılan maddeler: §3-N/gramer 13, §4-unit/istek 9,
§4-value/liste 7, §4-scale/baslik 6, §3-N/uyum 5, §4-unit/aciklama 3, §4-small/baglam 1,
§4-value/baglam 1.

**Sonuç (ön-kayıtlı nokta-değer):** konsensüs geçerli-öğe oranı **15/51 = %29.4**
(Wilson %95 GA [18.7, 43.0]) — Y'ye eğimli eşitlik-bozma kuralına rağmen **katı sınıra
oturdu** (katı 14/51, gevşek 42/51). Kategori: unit 1/15, scale 2/11, value 9/21,
small-int 3/4. Set: tr 5/19, en 7/18, mistral 3/14.

**Tespit (A17-4, betimsel):** konsensüs-geçerli n=15 → **GFP 12/15 = %80.0** [54.8, 93.0]
vs **legacy 0/15 = %0** [0, 20.4]; konsensüs-geçersiz n=36 → GFP 8/36, legacy 0/36.
**İnvariant teyit edildi: legacy konsensüs dahil HER eşikte 0** (0/15, 0/14, 0/42, 0/51).
Birincil H_G4 (ITT per-kategori McNemar, tam setler) DEĞİŞMEDİ.

**Statü:** B4 kapısı İFA EDİLDİ.

### A19 (2026-10-14) — Çapraz-ölçek tuzak-sorularının ayrık raporu [EXPLORATORY, POST-OUTCOME, PRE-ANALYSIS]

**Gerekçe:** Benchmark'taki 7 çapraz-ölçek tuzak sorusu (`scale_focus=="cross"`: res-11,
res-12, com-10, dis-09, dis-10, sta-07, sta-10) makalede §4'te anılıyor ama sonuçları
hiçbir ön-kayıtlı analizde ayrıca raporlanmadı (iç-hakem incelemesi, 2026-10-14). Bu
analiz G1/G2 verisinin sonuçları bilindikten SONRA, ancak bu tabakalaşma HİÇ
hesaplanmadan ÖNCE tanımlandı. Ön-kayıtlı hiçbir testin yerine geçmez.
**Veri ve enstrüman:** A15 kuralıyla aynı — 5 koşul (TR: gemma/qwen/mistral; EN:
gemma/qwen) × 3 kol, saklı `pre_intervention` metinleri, TEK guard v4.1
(SHA-256 `d7644303…f233`) ile kol-bağımsız referans grafa karşı yeniden-skorlama
(`rescore_crosslingual.py` ile aynı yükleme/dışlama). LLM yeniden-koşusu YOK.
**Tabakalar:** tuzak (7 soru) vs diğer (49 soru).
**Metrikler (betimsel):**
- M1: yanıt başına ≥1 `SCALE_VIOLATION` göstergesi; soru-düzeyi ortalama oran
  (pseudoreplication kuralı: birim = soru-hücresi), tuzak vs diğer, koşul × kol.
- M2: referans-GFS hücre-ortalaması, tuzak vs diğer.
- M3 (grounded_guard kolu, teslim tarafı): tuzak yanıtlarında in-run `blocked`/`retried`
  oranları; teslim edilen `reply`'ın aynı guard'la yeniden-skorlanmasında `SCALE_VIOLATION`
  sayısı.
- M4: tuzak sorularında bayraklanan `SCALE_VIOLATION` cümleleri incelemeye açık dosyaya
  dökülür; insan-doğrulamalı precision İDDİA EDİLMEZ (A11 enstrüman sınırı geçerli).
**Test:** yalnız grounded_noguard kolunda (modelin ham yazdığı), koşul başına M1 için
iki-yönlü Mann–Whitney U (7 vs 49 soru) — keşifsel, düzeltmesiz, betimsel okunur.
**Raporlama taahhüdü:** sonuç-koşulsuz; yön ne çıkarsa makalede "exploratory" etiketiyle
raporlanır. Script: `trap_analysis.py`; çıktı: `results/trap_analysis.json`,
`results/trap_flagged_sentences.jsonl`.

### A20 (2026-10-14) — Guard değerlendirme-kapsamı (araçsız tek-tur boşluğu) + tuzak-bayrağı mekanik ayrıştırması [EXPLORATORY, POST-OUTCOME, betimsel]

**Gerekçe (A19 incelemesi sırasında fark edildi, 2026-10-14):** Orchestrator guard'ı
yalnız `pgraph.has_records` iken çalıştırır (`ollama_orchestrator.py:434`). G1'de her soru
tek-turlu oturumdur → model hiç araç çağırmazsa graf boştur ve yanıt guard tarafından
**değerlendirilmeden** teslim edilir (`provenance: null`). A1-r1'deki "araçsız-tur
denetimi" yalnız önceki turdan kayıt taşıyan ÇOK-TURLU oturumlar için geçerlidir; tek-tur
için geçerli değildir. Bu bir eşleştirici sızıntısı değil, **kapsam sınırıdır**: guard
değerlendirdiği her yanıtta fail-closed'dur, değerlendirme provenance-koşulludur. Kod
DEĞİŞTİRİLMEZ, LLM yeniden-koşusu YOK; rapor edilen deneyler koşulduğu haliyle tarif edilir.
**Metrikler (betimsel, sonuç-koşulsuz):**
- C1: grounded_guard kolunda guard-değerlendirilen yanıt payı (`provenance != null`),
  koşul başına (TR: A/B/Mistral; EN: A/B).
- C2: blok oranı hem tüm yanıtlara hem değerlendirilen yanıtlara göre.
- C3: değerlendirilmeyen yanıtlardan referans denetiminin doğrulayamadığı ≥1 sayı içerenlerin
  sayısı (A11 disiplini: "fabrikasyon" DEĞİL, "referansa karşı doğrulanamayan").
- C4 (karşı-olgusal, yalnız betimsel): değerlendirilmeyen yanıtların ön-müdahale metni BOŞ
  grafa karşı guard v4.1 ile skorlanır; ≥1 skorlanan (IGNORED-dışı) iddia taşıyanlar,
  boş-graf turlarında karar-kritik sayıyı UNGROUNDED sayan bir politika altında müdahaleye
  (düzeltme → blok) tabi olurdu. Düzeltme denemesinin sonucu LLM'siz simüle EDİLEMEZ →
  "blok" değil "müdahaleye tabi" olarak raporlanır.
- T1: tuzak sorularında kol başına araç-çağıran yanıt payı.
- T2: A19-M4 tuzak SCALE_VIOLATION bayraklarının mekanik ayrıştırması — (a) `matched_key`
  `input:*` (kullanıcı girdisinin yankısı), (b) eşleşen iddia değeri tamsayı ≤100 (sayım,
  liste indeksi, yüzde tesadüfü), (c) kalan. İnsan kodlaması YOK; yalnız (c) gözle okunup
  niteliksel betimlenir.
Script: `guard_coverage.py`; çıktı: `results/guard_coverage.json`.

### A21 (2026-10-14) — Guard v4.2 (boş-graf değerlendirmesi) + G1 tam yeniden-koşusu (5 koşul × 3 kol) [PRE-OUTCOME; danışman v2.22 GO-with-changes, E1–E10 işlendi]

**Gerekçe.** A20 boşluğu: v4.1 orchestrator guard'ı yalnız `pgraph.has_records` iken çalıştırıyordu; tek-turlu G1 oturumunda araç çağrılmayan yanıt değerlendirilmeden teslim edildi (grounded_guard değerlendirme payı: TR A %20.2, B %64.3, Mistral %43.4; EN A %28.6, B %57.1). Makalenin "doğrulanamayan sayı kullanıcıya ulaşmaz" iddiası koşulduğu haliyle yalnız değerlendirilen yanıtlar için doğruydu. A1-r1'deki "araçsız-tur denetimi" yalnız çok-turlu oturumlar için geçerliydi; tek-tur boşluğu v4.2 ile kapanır. Yazar kararı (2026-10-14): boşluğu kodda kapat ve G1'i yeniden koş.
**Tekrarlanamazlık bulgusu (yeniden-koşu kapsamını belirler).** 2026-10-14 smoke'u: gemma4:e4b, grounded_noguard, res-01..03, seed 10000 — 3/3 yanıt Temmuz'dakinden tamamen farklı (SequenceMatcher ≈0.05), 2/3'te araç-kullanımı tersine döndü. Sunucu modelleri 2026-08-26'da güncellenmiş; Temmuz'da Ollama sürümü/model digest'i KAYDEDİLMEMİŞTİ. Sonuç: Temmuz kolları yeniden üretilemez → yalnız guard kolunu yeniden koşmak kol-kıyasına zaman karıştırıcısı sokar → **5 koşulun 3 kolu birlikte** yeniden koşulur. (Aynı gün aynı yapılandırmada guard ve noguard kollarının ön-müdahale metinleri 3/3 özdeş çıktı — E4 bunu ölçer.)

**Politika (v4.2).**
1. Guard her yanıtı değerlendirir (`guard_mode != "off"`); boş grafta her sayısal iddia UNGROUNDED ya da IGNORED olur (eşleştirme/ignore kuralları DEĞİŞMEDİ).
2. Müdahale hattı aynı: tek düzeltme denemesi (metin-only) → ihlal sürerse blok. Boş graf için iki metin varyantı (TR+EN): düzeltme talimatı ("simülasyon çalıştırılmadı; sayı vermeden hangi simülasyonu çalıştırabileceğini ve gereken girdileri söyle; bu yanıtta araç çağırma") ve blok mesajı (sayı içermez; simülasyon yapılmış gibi göstermez).
3. Log modu (grounded_noguard, ungrounded) kaydeder, müdahale ETMEZ — teslim metni v4.1 ile aynı tanımda.
4. Kullanıcı-mesajı sayıları provenance'a EKLENMEZ (kapsam dışı); araçsız turda kullanıcı girdisinin yankısı da UNGROUNDED sayılır — fail-closed'un bilinen bedeli (E2 ile nicelenir). **Beklenti (hipotez değil):** Model A guard-kolu blok oranı belirgin yükselir.
5. **(E9) Bilinen sınır, v4.1 ile aynı, değiştirilmez:** düzeltme turunda ilk taslak history'ye eklenmez; model yalnız düzeltme talimatındaki ihlal-snippet'lerini görür. Retry `tools` listesiyle çağrılır ama araç YÜRÜTÜLMEZ; araç isteyen retry boş içerik → blok (E3 ile ölçülür).

**Değişmeyenler.** Hipotezler (H_G1a/b, H_G2, H_LANG-1/2, çapraz-model manipülasyon denetimi) ve birincil/ikincil testleri; `questions.json`, sistem promptları, model adları, seed'ler {10000,10001,10002}, sıcaklık 0.3, 3 tekrar, 3 kol, GFS formülü/ağırlıkları, toleranslar, ölçek sözlüğü, ignore kuralları, A2 dışlama kuralları (fallback/error/payda=0), %10 dışlama geçersizlik eşiği.
**(E8) Estimand notu:** hipotezler ve testler değişmedi; ancak H_G1b'nin fiili popülasyonu (teslim-edilen-sayılı yanıtlar) v4.2 altında Temmuz'dan farklıdır ve guard-kolunda seçime açıktır — E1 duyarlılık sınırları bu nedenle zorunludur.

**Analiz-tanımı netleştirmeleri (veri görülmeden).**
- (a) In-run temelli analizler (G1b ön-müdahale, G2 in-run birincil) Temmuz'un fiili popülasyonunda kalır: ≥1 provenance kaydı olan yanıtlar (`n_records > 0`). Gerekçe: araç çağrılmayan yanıtta zincir uzunluğu tanımsızdır ve boş-graf skoru yalnız araç-kullanım oranını yansıtır. Kısıt YALNIZ in-run analizlere uygulanır; referans-GFS birincil analizleri (H_G1a/b) tüm yanıtları görür. `compute_gfs.py` Temmuz verisinde birincil çıktıyı birebir korur (yalnız yeni betimsel alanlar eklendi). Makale notu: Temmuz makalesindeki "pre-intervention reference-GFS 0.816/0.817 (n=17)" aslında in-run GFS'tir (araç-çağıran yanıtlar, n=17 SORU) — makalede etiket düzeltilir ve referansa karşı popülasyon-tam ön-müdahale skoru (`rescore_crosslingual.py`) yanına konur.
- (b) **(E1) Withheld tanımı ve analiz-giriş kuralı.** 'Withheld' = teslim metni ≥1 skorlanabilir iddia taşımayan guard-kolu yanıtı (boş-graf blok mesajı VEYA sayısız düzeltme-yanıtı; kod: guard kolu ∧ ref-GFS yok ∧ blocked∨retried). Referans-GFS paydası 0 → A2 kuralıyla BİRİNCİL analizlerden (Wilcoxon/bootstrap/McNemar hücre-ortalaması) hariç; başarılan eşli n (`achieved_n`) her test için raporlanır; dışlama kuralı veri görüldükten sonra DEĞİŞTİRİLMEZ. ÖN-KAYITLI DUYARLILIK (iki uç, birincille birlikte üçü de raporlanır): (i) withheld = GFS 0 / not-clean (kapsam-cezalı alt sınır); (ii) withheld = GFS 1 / clean (fail-closed-kredili üst sınır) (`G1_reference_gfs_sensitivity`). Betimsel zorunlu: `clean_in_noguard_withheld_in_guard` (soru sayısı ve payı; herhangi-tekrar ve tüm-tekrarlar) = over-blocking maliyeti. 'One-directional' iddiasının ön-tanımı: 'guard teslim edilen metne temelsiz sayı SOKMAZ'; 'doğru sayıyı asla alıkoymaz' DEĞİL — alıkoyma oranı ayrıca raporlanır. Blok oranı her zaman araçlı/araçsız kırılımıyla verilir; Temmuz'daki 'müdahale maliyeti rejimle ölçeklenir' anlatısı Ekim verisi ne gösterirse ona göre, sonuç-koşulsuz yeniden yazılır.
- (c) Betimsel ek metrikler (`compute_gfs.py` `guard_side_metrics`): değerlendirme payı, araçsız pay, blok oranı araçlı/araçsız kırılımı, withheld oranı.
- (d) **Canlı-bayrak taksonomisi** aynı script'le (`analyze_guard_flag_taxonomy.py`) yeni veride. Düzeltme (kod-okuma, 2026-10-14): taksonomi, bloklanan yanıtların ön-müdahale metnindeki **GFP in-run guard** bayraklarını sınıflandırır (eski değer-eşleştirme guard'ının değil); in-run grafı boş olan (araçsız) bloklar `_inrun_graph=None` ile dışarıda kalır. Payda = araç-çağıran bloklar; analiz edilen blok sayısı ayrıca raporlanır (`n_blocked_analysed_with_inrun_graph`). Temmuz makalesi §5.3 bu bayrakları yanlışlıkla "deployed numeric guard"a atfetmişti — makalede düzeltilir. Ek bulgu: makaledeki 696 bayrak/106 blok sayısı 2026-07-09'da guard v3 ile üretilmişti ve A14/A15 (v4-bilingual, v4.1) sonrası yeniden koşulmamıştı; aynı Temmuz verisi v4.1/v4.2 ile 608 bayrak verir (105 blok in-run graflı). Fark guard-sürümü kaynaklıdır, v4.2 değişikliğinden değil (v4.2 yalnız boş-graf yolunu değiştirir, taksonomi boş grafı dışlar). Ekim taksonomisi tek guard v4.2 ile üretilir.
- (e) Cross-lingual/cross-model: `rescore_crosslingual.py` (glob'lar tarih-bağımsız; Temmuz dizininde aynı dosyaları seçtiği doğrulandı) + `crosslingual_stats.py` (G1 hücreleri `GFP_RUN_DIR`'dan, G4 setleri Temmuz korpusundan; Temmuz'da çıktı bayt-özdeş), tek guard v4.2 ile. A19 (tuzak) ve A20 (kapsam) analizleri yeni veride de koşulur ve raporlanır.
- (f) **(E2) Yankı over-blocking (C5, `guard_coverage.py`):** grounded_guard araçsız-bloklarında UNGROUNDED iddiaların TAMAMI soru metnindeki sayılarla (aynı tolerans, guard'ın kendi ayrıştırıcısı) eşleşen yanıtların payı ('echo-only blocks'); kısmi-yankı payı ayrıca. Mekanik, LLM'siz. Yorum: echo-only blok = fail-closed'un kapsam-bedeli, uydurma değil.
- (g) **(E3) Retry telemetrisi** (orchestrator, yalnız log; karar hattı DEĞİŞMEZ): iz alanları `retry_tool_calls_requested`, `retry_content_empty`, `retry_error`. Rapor (`guard_coverage.py`): blok başına kırılım (a) retry araç istedi, (b) retry sayı tekrarladı, (c) retry boş/hata.
- (h) **(E4) Determinizm ve ayrıştırma kontrolleri (betimsel, ön-beyanlı).** (i) Aynı (lang, model, qid, tekrar) için guard vs noguard `pre_intervention.reply` özdeşlik oranı (tam-eşit ve SequenceMatcher ≥0.95; `guard_coverage.py`). (ii) Her koşul bitince önceden sabitlenen 5 hücre (res-01, com-01, dis-01, sta-01, res-11; seed 10000; grounded_noguard) yeniden koşulur → AYRI dosya `determinism_check_*.jsonl` (`_latest` glob'u ve dışlama sayımları karışmaz). Sonuç-koşulsuz yazım kuralı: özdeşlik ≈%100 ise §5.1 "pre-intervention text is identical by construction (same seed/prompt); the decomposition is structural"; değilse "essentially unchanged" dili kalır.

**(E5) Durdurma / drift / kısmi-başarısızlık / ara-bakış (`run_g1_rerun.py` + `run_benchmark.py`).** `ollama_version` + `model_digest` başlangıçta, her (kol, tekrar) başında ve koşu sonunda yeniden sorgulanır (geçici ağ hatasına karşı 3 deneme). Başlangıç A21 tablosuyla eşleşmezse koşu BAŞLAMAZ ve sürücü durur. Koşu-içi sapmada o KOŞULUN 3 kolu birlikte iptal edilir (dosya `aborted_*` olarak arşivlenir, neden `rerun_log.jsonl`'a yazılır) ve baştan koşulur. Hücre-düzeyi yama YASAK; yeniden-koşu birimi = koşul. `fallback`/`error` dışlaması A2 %10 kuralıyla; eşik aşılırsa koşul geçersiz → `aborted_*` + baştan (en çok 2 deneme, sonra "not run"). Ara-bakış yasağı: 5 koşul bitmeden `compute_gfs.py`/`rescore_*`/`crosslingual_stats.py`/`trap_analysis.py`/`guard_coverage.py`/taksonomi koşulmaz; yalnız iz/fallback/error/süre sayımı izlenir. Tamamlanamayan koşul 'not run' raporlanır, Temmuz verisiyle DOLDURULMAZ.

**(E7) Kapsam.** Yeniden koşulan: G1 (→ G1, G2, taksonomi, cross-lingual, cross-model). Temmuz'dan KALAN: **G4 + B4** ve **G3** (LLM'siz). G4/B4 taban-korpusu Temmuz G1 (v4.1) grounded-temiz metinlerinden türetilmiştir ve Ekim G1'den yeniden türetilMEZ (regresyon kanıtı + B4 insan-kodlamasının sabit korpusa bağlılığı). A10 karşı-olgusal, A11 canlı-taksonomi, A19, A20 Ekim verisinde aynı script'lerle yeniden koşulur; Temmuz'a ait tüm G1-türevli sayılar makaleden çıkar, Temmuz izleri arşivlenir ve yayınlanır. Regresyon kanıtı: v4.1 (`d7644303…f233`) ve v4.2 guard Temmuz korpusundaki 3889 metni (5 koşul G1 pre/teslim + 3 G4 setinin kaynak/mutasyon metinleri), 54 769 iddiayı aynı referans graflara karşı skorladı: **0 fark** (`results/regression_v41_v42.json`). 286/286 paket testi yeşil (9 yeni v4.2/A21 testi dahil).

**Ortam (iz başına kaydedilir: `ollama_version`, `model_digest`, `guard_sha256`).** Ollama 0.34.3; gemma4:e4b `c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb`; qwen3.5:27b `7653528ba5cba4dd8e19da24aaddc7f4d0b5ecd93571c0825dfd4137958ec06e`; mistral-small3.2:24b `5a408ab55df5c1b5cf46533c368813b30bf9e4d8fc39263bf2a3338cfa3b895b` (hepsi Q4_K_M).

**(E6) Donmuş hash'ler (SHA-256) — git tag `prereg-v3.0`, koşu başlamadan.**
| Dosya | SHA-256 |
|---|---|
| `app/llm/provenance_guard.py` | `a050b46ab5d8fa392215a1df47162c311daae95118d2bfa311d31e84a729f7c2` |
| `app/llm/ollama_orchestrator.py` | `aa3475289be5c1e336a6a1784dc6372ef8cce33ad3490bbec93b94f6b2a0dcbb` |
| `app/llm/prompts/stakeholder_prompts.py` | `8ac4d7ebd7ece693003fd5ddcfde43ab9955a26c4e4b3f1fbc3ef795089906ea` |
| `experiments/gfp_benchmark/questions.json` | `7c5332396e0d7514cf00ffc7120debe8ed8ce8ae01ecb80d7c70feb7f9b4d546` |
| `experiments/gfp_benchmark/run_benchmark.py` | `f957457ff6d344d86c49e9e8e28363323e4c24fcc901077e277848e1bc9e941d` |
| `experiments/gfp_benchmark/run_g1_rerun.py` | `f097280b383e757f8d9e8fc8c5ec4558df7a0529389e772035b02f83749e090a` |
| `experiments/gfp_benchmark/compute_gfs.py` | `bc730e5404326b01730a86af9b57570fcdb97184799e13e01a84d45ab7f8015d` |
| `experiments/gfp_benchmark/rescore_crosslingual.py` | `77df426116cdd7e4070221152315cf898a4661a32cc02ab4fc5939e5d6476c2c` |
| `experiments/gfp_benchmark/crosslingual_stats.py` | `d16501c412f4f1d256df87bf90422994d6779356722a0d69e0be0173a341e678` |
| `experiments/gfp_benchmark/analyze_guard_flag_taxonomy.py` | `761dc9f3bff3b2c5f2d41cf9b17ce93648b5b2e6ceea479931bc812f9c36197f` |
| `experiments/gfp_benchmark/trap_analysis.py` | `f4823546094c19b55eb8606b4ef80f9b1a0b2e1264ce5dfd25376e214fd24976` |
| `experiments/gfp_benchmark/guard_coverage.py` | `93e8d2798171b52b6fc70ea52d87d4d631cd739df670df353b5af8270b916ef1` |
| `experiments/gfp_benchmark/regression_v41_v42.py` | `99bca635fcecab19a5fafd7ac0fd0bd41e171f216e9c01c97a24b56d523ac1af` |
| `experiments/gfp_benchmark/results/regression_v41_v42.json` | `c251e0fd11802210fd3dcfc566eeee6640a8a1a65a7879e8ee1e1110aed25648` |

**Koşu düzeni.** `GFP_RUN_DIR=oct_v42` alt-dizinine, konteynerde detached, `run_g1_rerun.py` ile sıralı: gemma4:e4b-TR → qwen3.5:27b-TR → mistral-small3.2:24b-TR → gemma4:e4b-EN → qwen3.5:27b-EN; her biri 3 kol × 56 soru × 3 tekrar (504 iz). Temmuz izleri yerinde kalır ve yayınlanır.
**(E10) Raporlama taahhüdü:** sonuç-koşulsuz. Makalede tüm G1-türevli sonuçlar Ekim-2026 koşusundan (guard v4.2; Ollama 0.34.3; yukarıdaki digest'ler) raporlanır. Temmuz-2026 koşusu (guard v4.1) Reproducibility + Threats'te adıyla anılır: araçsız tek-tur yanıtların değerlendirilmeden teslim edildiği, bunun iç-incelemede fark edilip kodda düzeltildiği, modellerin bu arada güncellendiği ve zaman-karıştırıcısını önlemek için tüm kolların birlikte yeniden koşulduğu yazılır. G4/B4 substratının Temmuz metinleri olduğu belirtilir. Ön-kayıt tag zinciri: `prereg-v1.0` (hipotez/metrik) → `prereg-v2.0` (dil/model) → `prereg-v3.0` (kapsam düzeltmesi + yeniden-koşu).

### A22 (2026-10-14) — Teslim-metni ölçümünün bağımsızlaştırılması: müdahale-yolu ayrıştırması, insan izlenebilirlik-denetimi, tolerans duyarlılığı, G1 iddia-şekli [PRE-RUN; iç-hakem yorumları + danışman v2.22.7; prereg-v3.1]

A21 koşusu A23 nedeniyle 16:01 UTC'de durdurulduğu ve baştan koşulacağı için A22 artık koşu-öncesidir (iptal edilen izler `aborted_oct_v42_A23/`, bakılmadı).

**A22-1 [ZORUNLU] Müdahale-yolu tabakalaşması** — `intervention_paths.py` (LLM'siz; `compute_gfs.py` değişmez). grounded_guard kolunda provenance'lı her yanıt tam olarak bir yola düşer: **P0** `retried=False`; **P1a** `retried ∧ ¬blocked` ∧ teslim metninde ≥1 skorlanan iddia (düzeltmeyle çözüldü); **P1b** `retried ∧ ¬blocked` ∧ skorlanan iddia yok (= E1 withheld-by-correction); **P2** `blocked ∧ n_records>0` ∧ özette ≥1 skorlanan iddia; **P3** `blocked ∧ (n_records=0 ∨ özette skorlanan iddia yok)`. Koşul başına: yol payları; yol başına teslim referans-GFS ortalaması ve tam-temiz oranı; aynı (qid, tekrar) noguard yanıtının referans-GFS'i ve yol-içi Δ; ayrıştırma Δ_H_G1b = Σ_yol pay × Δ_yol (birincil: tanımlı çiftler; E1-(i)/(ii) varyantlarında P1b/P3 0/1 doldurulur). İlk taslak kol-bağımsız olduğundan P0'ın Δ'ya katkısı tanım gereği 0'dır. P1a ve P2 için ilk taslak ile teslim metninin referans-GFS'i yan yana; P2'de referans-GFS<1 özet sayısı; düzeltmeyle-çözülme payı |P1a ∪ P1b| / |retried| ve E3 kırılımı. Sonuç-koşulsuz.

**A22-2 [ZORUNLU] İnsan izlenebilirlik-denetimi** — kodkitabı `AUDIT_CODEBOOK.md` (bu tag'le dondu). Yapı dar ve mekanik: her numaralı sayı için `traceable_YN` ("bu sayı basılı referans çıktı sayfasında, yuvarlama payıyla, var mı?"; soru girdisinin yankısı Y + `input_echo`), yanıt düzeyinde `usable_answer_YN`. Doğruluk, kategori, ölçek yargısı YOK. Kodlayıcılar kol, yol ve eşleştirici kararını görmez (özet şablon başlığı yol-körlüğünü P2 için bozar — beyan; işlevsel körlük = eşleştirici-kararına körlük). Örneklem `audit_sample.py`: seed=42, tabaka = yol × koşul, hedef P1a 40 / P2 25 / P0 25 (koşullara orantılı; tabaka küçükse tümü). 2 kodlayıcı (kodlayıcı-1 yazar, beyanlı; kodlayıcı-2 kör). Analizler: sayı-düzeyi ve yanıt-düzeyi Cohen κ; **Y1** = eşleştiricinin GROUNDED dediği sayılarda insan-traceable payı (dairesellik sınırı), Wilson %95 GA, yol başına; **Y2** = eşleştiricinin ihlal dediği teslim-sayılarında insan-traceable payı; usable-oranı yol başına. κ düşükse A18 kuralı aynen. Betimsel sınır; sonuç-koşulsuz; sonradan düşürülemez.

**A22-3 [ZORUNLU] Tolerans duyarlılığı** (§4-104 ve §7.1-7'de ön-kayıtlıydı, raporlanmamıştı) — `tolerance_sensitivity.py`: `_REL_TOL ∈ {0.01, 0.02, 0.05}` çalışma-anında (donmuş guard dosyası değişmez); ek sınır olarak 0.0 ("A22'de eklendi"). Kademeli mutlak tabanlar (0.01, 0.5) sabit; legacy guard toleransı taranmaz (beyan). Kapsam: (i) G1 referans-GFS kol ortalamaları ve H_G1a/H_G1b Wilcoxon + bootstrap GA, teslim VE ilk-taslak metni, model başına (Ekim); (ii) G4 kategori-başına GFP recall + kontrol-FP (Temmuz korpusu, clear-sky replay; TR için metin-taşıyan 97/109 kayıt — B4 "metin otantikliği" notu); (iii) taksonominin "value matches reference" kategori payı (Ekim). **Zorunlu uyarı cümlesi:** guard %2 toleransla müdahale etti ve yeniden koşulamaz; tarama ölçümü değiştirir, müdahaleyi değil. Raporlama ek tablo, sonuç-koşulsuz.

**A22-4 [ZORUNLU] G1 iddia-şekli (veri görülmeden sabit)** — (a) "In this single-turn, fixed-seed benchmark the first draft is identical across the guarded and unguarded arms by construction (the guard acts only after the draft); E4 identity [X%] is reported as a harness-integrity check, not as a finding." (b) "The guard's effect on delivered text is realised only through a text-only correction pass—itself a second generation step, scored like any text—or through withholding; [P1a]% of guarded responses were resolved by correction, [P2+P3]% withheld ([P2]% with a provenance summary, [P3]% without numbers)." (c) "The delivered reference-GFS contrast (H_G1b, pre-registered tests unchanged; E1 bounds) is scored by the protocol's own matcher; decomposed by path, [share]% of the gain arises in matcher-constructed summaries and [share]% in model rewrites; in a blinded audit of [n] delivered numerals, [Y1]% [CI] of matcher-GROUNDED numerals were human-traceable to the reference output." (d) "channel" yalnız ihlal türleri; üretim/müdahale = "path". (e) "leaves generated text essentially unchanged" ampirik bulgu olarak hiçbir yerde kalmaz.

**A22-5 [ZORUNLU] Parametre beyanı (Appendix B)** — kod-izli tablo: şehirler/koordinatlar (6), PVGIS TMY (SARAH3/ERA5, 2005–2023, önbellek SHA-256'ları), tilt 30° / azimut 180°, inverter verimi 0.96 ve **başka sistem kaybı modellenmiyor (estimated, optimistic)**, batarya kimyası/RTE 0.90/öz-tüketim dispatch, PV capex 25 000 TL/kWp ve BESS capex 20 000 TL/kWh (**estimated**), benchmark araç-rotasının fiilen kullandığı iskonto oranı (`/simulate/pv-bess` şeması: 0.12; nominal, estimated), tarife artışı 0.08 (estimated), fatura→tüketim dönüşümü 0.5 TL/kWh (orchestrator; estimated), ömür 25 yıl, ihracat fiyatı/mahsup rejimi, tarife tarihi (2026-04-04 çeyreği). Kaynaksız her değer "estimated". Threats "Setting": Alman yük-şekli × Türk tarife/ışınım birleşimi G1/G2/G4'ü etkilemez (izlenebilirlik simülatör-parametresinden bağımsız); G3 büyüklükleri ve alıntılanan mutlak ekonomik sayılar için geçerlidir; mutlak sayılar "illustrative".

**A22-6 [OPSİYONEL — kullanılmayacak] LLM-yargıç.** Yerine A25 (dış öğrenilmiş doğrulayıcı) gelir.

**A22-7 [OPSİYONEL — keşifsel, donmuş G3 ekinin DIŞINDA]** G3 öğle yük-faktörü ızgarasına klima-eşzamanlılık noktası (0.30–0.40) ya da yalnız Threats cümlesi.

**A22-8 [ZORUNLU] Süreç.** Tek tag `prereg-v3.1` (A22+A23+A24+A25) koşu başlamadan; yeni script'ler yalnız arşivlenmiş Temmuz verisinde ya da deneme dizinlerinde mekanik duman-testinden geçirildi (`GFP_SMOKE_LIMIT`), sonuçları raporlanmadı ve silindi (beyan). E5 ara-bakış yasağı koşu boyunca sürer.

### A23 (2026-10-14) — PV ışınım veri-yolu arızası: durdurma, düzeltme, Temmuz-replay kanıtı, sessiz-fallback envanteri [ZORUNLU; danışman v2.22.8; prereg-v3.1]

**Bulgu.** pvlib 0.15.2'de `get_pvgis_tmy` iki değer döndürür; `solar_model.py` dört değer açtığı için her çağrı `ValueError` ile bir `except` bloğuna düştü ve **sessizce clear-sky ışınıma** geçti (2024 aralığı, 25 °C, 2 m/s; provenance bayrağı yok). Temmuz G1, G4 korpusu ve ilk Ekim denemesi bu yolla üretildi (Model A Temmuz res-01 yanıtları "10,541 kWh" alıntılar; Ankara 5 kW clear-sky = 2 108 kWh/kWp). Makalenin "real PVGIS irradiance" iddiası koşulduğu haliyle yanlıştı.

**A23-1 Durdurma.** A21 koşusu 2026-10-14 16:01 UTC'de durduruldu; 214 kısmi iz `results/aborted_oct_v42_A23/`'e arşivlendi (sebep dosyası `ABORTED.md`), sonuçlarına bakılmadı.

**A23-2 Düzeltme.** (a) `get_pvgis_tmy` pvlib 0.15 imzasıyla; (b) şehir-başına yerel TMY önbelleği `app/simulation/pv/tmy_cache/` (6 benchmark şehri; PVGIS-SARAH3/ERA5, 2005–2023; `MANIFEST.json` SHA-256'ları; meta JSON'da PVGIS girdileri ve çekim tarihi) — benchmark konumlarında koşu sırasında ağ çağrısı yok; (c) sessiz fallback YOK: önbellek yoksa ve PVGIS'e ulaşılamazsa `IrradianceUnavailable`; (d) `IRRADIANCE_SOURCE` = `pvgis_tmy_cache` (varsayılan) | `clearsky` (yalnız Temmuz-replay); PV araç-sonucuna metin alanları `irradiance_source` + `tmy_sha256` (provenance grafı sayısal olmayanı almaz → `provenance_guard.py` değişmez), `run_benchmark` iz başına `irradiance_source` ve koşu başına `tmy_manifest_sha256` kaydeder; (e) testler: 6 şehirde özgül verim 1 200–1 900 kWh/kWp bandında ve ağ çağrısı olmadan; PVGIS düşükken hata yükselir; clear-sky modu Temmuz değerini (10 541 kWh) üretir; önbellek hash'leri sabit. Özgül verimler: Ankara 1 664, Antalya 1 890, Bursa 1 533, İstanbul 1 575, İzmir 1 810, Konya 1 768 kWh/kWp. Redis `sim:*` sonuç-önbelleği (42 eski clear-sky anahtar) silindi; koşu öncesi yeniden silinir.

**A23-3 Temmuz-replay kanıtı.** `regression_clearsky_replay.py`: düzeltmeden ÖNCE çalışan backend üzerinden 56 referans grafının kayıtları donduruldu (`clearsky_ref_snapshot.json`); düzeltmeden SONRA süreç-içi `clearsky` modunda (Redis atlanarak) yeniden kuruldu: **56 soru, 5 032 kayıt, 0 fark** (sessiz-fallback kaldırımlarından sonra yeniden koşuldu, yine 0). Bu nedenle v4.1/v4.2 regresyonu, G4 ve B4 Temmuz korpusunda geçerli kalır; Temmuz-korpusu analizleri `clearsky_mode.py` ile yeniden üretilir ve "July corpus: clear-sky irradiance" diye etiketlenir.

**A23-4 G4 legacy uyarı-kanalı ayrıştırması [EXPLORATORY, POST-OUTCOME].** `a23_legacy_decomposition.py` (clear-sky replay; üç G4 seti, TR metin-taşıyan 97/109): legacy `validate_response` uyarıları türlerine ayrıldı. **Özgül-verim fiziksel-sınır uyarısı hiçbir sette tetiklenmedi** (legacy kontrolü `panel_kw` alanı gerektirir ve PV+BESS sonucu bu alanı taşımaz) → "artefakt dahil/hariç" sütunları özdeş; replay, saklı Temmuz S1/S2 bayraklarını %100 yeniden üretti. G4 legacy uyarı/tavan kanalı sonuçları PV arızasından etkilenmemiştir; makale cümlesi değişmez.

**A23-5 Sessiz-fallback envanteri (benchmark araç-yolu).**
| Yer | Davranış | Sınıf / işlem |
|---|---|---|
| `solar_model.py` PVGIS | clear-sky'a sessiz düşüş | **düzeltildi** → `IrradianceUnavailable` |
| `grid_model.py` SimBench yükleme | sentetik radyal ağa sessiz düşüş | **yükseltildi**; sentetik ağ yalnız açık `create_synthetic_radial_network()` (testler) |
| `grid_model.py` `apply_const_controllers` | 6 SimBench ağının hepsinde `AttributeError`, yutuluyordu | **kaldırıldı** (hiç etkisi yoktu; statik SimBench temel durumu açıkça beyan) |
| `standard_profiles.py` demandlib | sentetik konut profiline sessiz düşüş | **yükseltildi** (demandlib H0/G0 çalışıyor; davranış değişmedi) |
| `grid_model.py` numba→saf Python | aynı algoritma | zararsız |
| `grid_model.py` yük akışı yakınsamama | `converged=False` açık sonuç | açık |
| `economic_engine.calculate_irr` | kök yoksa NaN → `irr_percent=None` | açık |
| `api/routes/simulation.py` | `HTTPException 500` | yükselt |
| `ollama_orchestrator` Ollama hatası | Mock fallback, `fallback=True` | kayıtlı-dışla (A2) |
| `ollama_orchestrator._execute_tool` | `simulation_failed` + `tool_trace.failed` | kayıtlı |
| `ollama_orchestrator` retry hatası | `retry_error=True` → blok | kayıtlı (E3) |
| `core/cache.py` Redis | önbelleksiz devam | zararsız |
SimBench ortam denetimi: mevcut konteynerde altı LV ağının hepsi yükleniyor (rural1 15, semiurb4 44, urban6 59 bara) — Temmuz izleri bara sayısı saklamadığı için "ortam denetimi, iz denetimi değil" diye beyan. G3 kendi ağını doğrudan kurar; bu bloklardan etkilenmez.

**A23-6 Referans yeniden-doğrulama.** Düzeltilmiş simülatörle 56/56 referans graf kuruldu; çalışılmış-örnek figürü ve makaledeki mutlak PV/ekonomi sayıları Ekim koşusundan yeniden üretilir ya da "illustrative (clear-sky, July)" etiketi alır.

**A23-7 Donma.** `prereg-v3.1` hash tablosu (aşağıda) tüm düzenlemeler bittikten sonra tamamen yeniden hesaplandı; `provenance_guard.py` bayt-özdeş (`a050…f7c2`).

**A23-8 Makale.** "PVGIS TMY irradiance" ancak Ekim koşusu önbellekten koştuğu için yazılır; Threats "Evaluation coverage and the re-run" paragrafına PV arızası, durdurma ve düzeltme; Discussion'a tek cümle (provenance simülatörün veri-kaynağını da taşımalı).

### A24 (2026-10-14) — Model seti güncellemesi: Model B qwen3.5→qwen3.8 + iki yeni lab (GLM, Muse), TR-only [PRE-RUN; danışman v2.22.9; prereg-v3.1]

**Kural (mekanik, simetrik):** donma anında ön-kayıtlı her (aile, boyut-sınıfı) için en yeni resmî Ollama checkpoint'i: `gemma4:e4b` (Model A, TR+EN; gemma4 en yeni aile), **`qwen3.8:27b` (Model B, TR+EN; §5'teki `qwen3.5:27b`'nin yerine — Temmuz qwen3.5 sonuçları bilindikten sonra yapılan, sonuç-koşulsuz beyanlı değişiklik; Temmuz izleri arşivlenir ve yayınlanır)**, `mistral-small3.2:24b` (TR; en yeni Mistral Small). **Yeni labler (TR-only, A16 kuralı: cross-lingual eksene ve birincil hipotez-testlerine girmez, çapraz-model tablosunda birer satır):** `glm-4.7-flash:latest` (Z.ai, 29.9B, Q4_K_M, akıl-yürütme modeli — `think` varsayılan) ve `muse-glimmer:30b` (Meta, 27.9B, Q4_K_M, Apache-2.0). Ollama `/api/chat` akıl-yürütmeyi ayrı `thinking` alanında döndürür, `content` temizdir (doğrulandı); orchestrator yalnız `content`'i kullanır.
**Ortam tablosu (Ollama 0.34.3; hepsi Q4_K_M):** gemma4:e4b `c6eb396d…982eb`; qwen3.8:27b `aaee06c39dcf2437cde036998d960e1fc1494b8191be7cc9657d01e509097813`; mistral-small3.2:24b `5a408ab5…895b`; glm-4.7-flash:latest `4475827791a269b02c8ec49b1c3bc1abb5846bacf3fae015b75d33986322d8f6`; muse-glimmer:30b `de878ce33ad81d060001db1469a02eebe4d86f0ad58cfe52dc062fdcbe4464c1`. A21-E5 drift kuralı 7 koşula uygulanır.
**Kapı (harness-uyumluluk; davranış filtresi DEĞİL):** res-01, com-01, dis-01; seed 10000; TR; grounded_noguard; guard v4.2; PVGIS önbelleği. GEÇER ⇔ (a) 3/3 hata/fallback yok; (b′) ≥1 iyi-biçimli, yürütülmüş araç çağrısı; (c) 3/3 Türkçe; (d) `reply`'da think işareti yok. Yerleşik üç modele uygulanmadı (beyan). Sonuçlar: **GLM GEÇTİ, qwen3.8 GEÇTİ, muse-glimmer GEÇTİ** (üçünde de 3/3 araç çağrısı, Türkçe, hatasız, sızıntı yok). Kapı izleri (`results/gate_a24/`) determinizm gereği ana-koşu hücreleriyle özdeştir; yalnız hata/araç/dil için incelendi, GFS hesaplanmadı, analiz glob'larına girmez.
**Kapsam:** yalnız G1 (→ G1/G2/taksonomi/A19/A20/A22-1/çapraz-model). **G4 yeni modellerde KOŞULMAZ.** G4/B4 korpusu Temmuz (gemma4:e4b, qwen3.5:27b, mistral; clear-sky replay). Makale cümlesi (danışman v2.22.9-A-2): "The G4 injection corpus and its human audit were derived from July 2026 grounded responses of gemma4:e4b, qwen3.5:27b and mistral-small3.2:24b (clear-sky irradiance; Sec. Threats). G1 is reported from the October 2026 run, in which Model B is qwen3.8:27b, the newest checkpoint of the same family and size class at re-freezing, and two further open models are added. The detector contrast in G4 does not depend on which model wrote the text—both detectors score identical mutated texts—so the corpus is retained rather than regenerated."
**Sıra:** A-TR, B-TR, A-EN, B-EN, C (Mistral), D (GLM), E (Muse); her koşul 3 kol × 56 × 3; tamamlanamayan D/E "not run". Hipotezler/testler/dışlama kuralları değişmez. `rescore_crosslingual.py` (Ekim koşul kümesi `GFP_RUN_DIR` doluyken; Temmuz dizininde Temmuz kümesi — Temmuz çıktıları bayt-özdeş doğrulandı), `crosslingual_stats.py` (model listeleri koşul kümesinden türer; Temmuz çıktısı bayt-özdeş) ve `run_g1_rerun.py` güncellendi.

### A25 (2026-10-14) — Bağımsız öğrenilmiş doğrulayıcı (TypeSafe Jev `jev-1.13.0`): G4 evidence-format ablasyonu + teslim-metni üçgenlemesi [PRE-RUN tasarım; danışman v2.22.9; prereg-v3.1]

**Beyan:** tag öncesi hiçbir G4 öğesi hiçbir doğrulayıcıya gönderilmedi; yalnız iki sentetik sonda yapıldı (Fig-2 örneği, annotated evidence; ve istemci duman-testinde tek sentetik iddia). Raw-format sondası yapılmadı. Laya kullanılmaz (Jev hiçbir manşet iddianın tek dayanağı değil; zero-shot taban modeli saman-adam olur).
**Araç yolu:** `jev_g4.py`, ana makinede, `@jkudish/jev-mcp@0.14.3` MCP sunucusunu stdio üzerinden başlatıp `jev_verify` çağırır (varsayılanlar: `auto_accept` 0.8, `subject_at` 0.5); tüm istek/yanıtlar `a25_jev_calls.jsonl`'e yazılır ve yayınlanır. Zaman aşımı/3 deneme; `verifier_error` sayılı dışlama; hata >%10 → "incomplete, not reported"; çağrı tavanı 1 500.
**Birim ve eşli tasarım:** her G4 enjeksiyonu için mutasyonun değiştirdiği cümle vs aynı cümlenin mutasyonsuz hali, aynı evidence → eşli. Birincil FP = orijinal cümlede bayrak oranı. Ek: G4 kontrolleri (sayı içeren her cümle; herhangi biri bayraklıysa kontrol bayraklı).
**Evidence (donmuş, `a25_evidence_items.json`, `a25_freeze_evidence.py`):** kol-bağımsız referans zinciri, clear-sky replay; 51 soru, 250 enjeksiyon öğesi (TR 97, EN 87, Mistral 66), 102 kontrol, 0 eşlenemeyen. İki format: **raw** = araç adı + girdi argümanları + JSON çıktı (ölçek etiketi yok; JSON anahtarları birim taşır, araç adı ölçeği ima eder — beyan); **annotated** = kayıt başına anahtar | değer | birim | geçerli ölçek | kaynak fonksiyon.
**Karar eşlemesi (a priori):** tespit = verdict ∈ {contradicted, unsupported} ∧ confidence ≥ eşik; eşik **0.8** birincil, **0.5** duyarlılık; tespit ve FP aynı eşikte; "review" eylemi ayrı sütun.
**Tek hipotez H_V1:** scale_swap kategorisinde annotated − raw recall > 0 (enjeksiyon-eşli exact McNemar, iki-yönlü, α=0.05; set başına ve havuzlanmış). Betimsel: kategori × format recall (Wilson GA), orijinal-cümle FP, kontrol-FP; GFP recall yanında referans olarak (yarış değil, "GFP Jev'i yener" dili yasak). Sonuç-koşulsuz: H_V1 reddedilirse "öğrenilmiş doğrulayıcı ölçeği araç-adı/anahtar ipuçlarından çıkarabiliyor" diye raporlanır.
**Teslim-metni üçgenlemesi:** yalnız A22-2 denetim örneklemi; `jev_g4.py audit`: her numaralı sayı için iddia 'The number "<sayı>" in the following statement is supported by the evidence: "<cümle>"', evidence = insanların gördüğü referans sayfa; Jev-traceable ⇔ verified ∧ confidence ≥ 0.8. Rapor: sayı-düzeyi Cohen κ (Jev vs insan-konsensüs) + 2×2; Jev insanın ikamesi değildir. κ ≥ 0.6 ise tüm teslim metinlerine opsiyonel uzatma; değilse uzatılmaz.
**Makale:** "closed commercial verifier (jev-1.13.0, accessed [date]); inputs and outputs released; the analysis can be re-run with any claim verifier".

**Donmuş hash'ler (SHA-256) — git tag `prereg-v3.1`, koşu başlamadan.**
| Dosya | SHA-256 |
|---|---|
| `app/llm/provenance_guard.py` | `a050b46ab5d8fa392215a1df47162c311daae95118d2bfa311d31e84a729f7c2` |
| `app/llm/ollama_orchestrator.py` | `aa3475289be5c1e336a6a1784dc6372ef8cce33ad3490bbec93b94f6b2a0dcbb` |
| `app/llm/prompts/stakeholder_prompts.py` | `8ac4d7ebd7ece693003fd5ddcfde43ab9955a26c4e4b3f1fbc3ef795089906ea` |
| `app/simulation/pv/solar_model.py` | `58196264e1ff294e6f84b61bf373e1bbd3a94d38b27df1dcb3515ec3f6e0e097` |
| `app/simulation/pv/tmy_cache/MANIFEST.json` | `4d78202d1d9f02351bf034119fe5a9bdcb45dfb3d82debfacc2979763976bbd5` |
| `app/simulation/advisor/feasibility_service.py` | `656b1c41570c82c52a05bab9bfa42582abb2056c90c0eab53f5b2c39156ad9c7` |
| `app/simulation/grid/grid_model.py` | `0680ee498b31d12a14838fbc00b17a442d472f13afa7388be01a6c775db19c16` |
| `app/simulation/loads/standard_profiles.py` | `13aa28a42c74e723ba445cd9e9295bebf97b0d45c571a641ec7d3552a98bcdb5` |
| `experiments/gfp_benchmark/questions.json` | `7c5332396e0d7514cf00ffc7120debe8ed8ce8ae01ecb80d7c70feb7f9b4d546` |
| `experiments/gfp_benchmark/run_benchmark.py` | `53c508231e0b657ccf7c4f52761200be8c4a0171b3591a8a3ff7cd80e6bc5b08` |
| `experiments/gfp_benchmark/run_g1_rerun.py` | `9874b69927bf9beb517364a6b4a6311c49080058cdd7b624a2927e1baae8b243` |
| `experiments/gfp_benchmark/compute_gfs.py` | `bc730e5404326b01730a86af9b57570fcdb97184799e13e01a84d45ab7f8015d` |
| `experiments/gfp_benchmark/rescore_crosslingual.py` | `d1cbe7747a56e0e79f3de8d06f15ef21e8760cfebe6ad4d06523910dfff897b1` |
| `experiments/gfp_benchmark/crosslingual_stats.py` | `840fad008573b5ea998dfc796f9e71a114cceea3c9f857f496fad1ce55341344` |
| `experiments/gfp_benchmark/analyze_guard_flag_taxonomy.py` | `761dc9f3bff3b2c5f2d41cf9b17ce93648b5b2e6ceea479931bc812f9c36197f` |
| `experiments/gfp_benchmark/trap_analysis.py` | `f4823546094c19b55eb8606b4ef80f9b1a0b2e1264ce5dfd25376e214fd24976` |
| `experiments/gfp_benchmark/guard_coverage.py` | `93e8d2798171b52b6fc70ea52d87d4d631cd739df670df353b5af8270b916ef1` |
| `experiments/gfp_benchmark/intervention_paths.py` | `000a07eece101858664d2a9cc8a84e3ea5a3f512acf652509bb5a6769f6ae713` |
| `experiments/gfp_benchmark/tolerance_sensitivity.py` | `61f1d9f0fc40497a4131babe270b4bb1484ff6ae332468ac9d0c54febe55bc75` |
| `experiments/gfp_benchmark/audit_sample.py` | `104d91c3bdeb0964614d123d44159c495b63156b65527a06562d491302d7e25b` |
| `experiments/gfp_benchmark/AUDIT_CODEBOOK.md` | `aebecc452b44b2ae8e847c42ccbf3126e5e229bf881d7527c2f655637fd1cfc8` |
| `experiments/gfp_benchmark/clearsky_mode.py` | `9324d43d1f15d473acacacc5067ede10a9b56ad8a2aa43634d63f83678a704f6` |
| `experiments/gfp_benchmark/regression_v41_v42.py` | `99bca635fcecab19a5fafd7ac0fd0bd41e171f216e9c01c97a24b56d523ac1af` |
| `experiments/gfp_benchmark/regression_clearsky_replay.py` | `9563ddf87f6a1239676cc874c47488163464a3e7e02e7f005928c744e20fcce7` |
| `experiments/gfp_benchmark/a23_legacy_decomposition.py` | `82711efc7c90703a37668cd76ad6404fda0b1cf665c804d854c2934d04cfbc48` |
| `experiments/gfp_benchmark/a25_freeze_evidence.py` | `e17e0a59412599bac06561b4c2da376aa0f3cfb2813f5d1c13dfc154ac1e4ada` |
| `experiments/gfp_benchmark/jev_g4.py` | `477c36a072fe841a11293a3041250a0fc4a33d35193b9ed76d14628bc25b23ef` |
| `experiments/gfp_benchmark/results/regression_v41_v42.json` | `c251e0fd11802210fd3dcfc566eeee6640a8a1a65a7879e8ee1e1110aed25648` |
| `experiments/gfp_benchmark/results/clearsky_ref_snapshot.json` | `2c395eebe038ffcde2d237fd2b46a89447aef82b01e91b384c0b515c96c1045e` |
| `experiments/gfp_benchmark/results/regression_clearsky_replay.json` | `ee96c100b19f278bb31d0bf16aa969d8d390db070000edbfad5e55ea9c6688ce` |
| `experiments/gfp_benchmark/results/a23_legacy_decomposition.json` | `6b9fa463efb969a5e0ba4ce321358c58df029d807a322d31be4f01c80e4799d3` |
| `experiments/gfp_benchmark/results/a25_evidence_items.json` | `953daa372ce4340ce5fd02b635416b6c262dd8aaa2a831bb89b2f20b27a2206b` |

Testler: 298/298 (A23/A24 testleri dahil). `provenance_guard.py` A21 ile bayt-özdeş.

### A26 (2026-10-14) — Canlı ölçek-iddiası ve sözlük-geçerliliği: tuzak sorularında tabakalı insan-kodlu cümle-düzeyi ölçek (n≈250) + opsiyonel Jev ölçeklendirici [PRE-OUTCOME, analiz-only, LLM yeniden-koşusu YOK; danışman v2.22.11; prereg-v3.2]

**Beyan (zamanlama ve görülenler).** A26, A21 G1 yeniden-koşusu sürerken (başlangıç 2026-10-14 16:57 UTC) ve `results/oct_v42/` analiz edilmeden donduruldu. Koşu boyunca `oct_v42/` ham dosyasından yalnız **sağlık meta-verisi** okundu: satır sayısı (318), `error`/`fallback` sayıları (0/0), `irradiance_source` değer kümesi, alan adları ve `repeat` değer kümesi. Ayrıca bir sağlık kontrolünde `tail -2 rerun.log` iki ProvenanceGuard log satırını ekrana bastı. Bunlar `g1-tr-grounded_noguard-dis-12-r2` ve `dis-13-r2` (gemma4:e4b, TR) oturumlarına ait, 300 karakterde kesilmiş UNGROUNDED bayrak özetleriydi ("Bu %35 penetrasyonun…", "Şimdilik BESS'i %0…"). `dis-12` ve `dis-13` tuzak sorusu DEĞİLDİR (`scale_focus=feeder`): A26 insan örnekleminde yer almazlar, yalnız opsiyonel Jev ölçeklendirme popülasyonuna (tuzak-dışı) girebilirler. Bunların dışında hiçbir `reply` metni, `claims`, verdict veya GFS görülmedi. Hiçbir örnekleme, eşik ya da analiz kararı bu iki satıra bağlı değildir. A25 sonuçları (H_V1 desteklenmedi; kontrol-FP yüksek) A26 tasarlanırken biliniyordu; bu yüzden Jev A26'da yalnız insan-doğrulamalı, κ-kapılı bir ölçeklendirici olarak yer alır ve manşet iddianın dayanağı değildir.

**İşlem sırası (dondu).** Koşu biter → betik `experiments/gfp_benchmark/` altına bayt-özdeş taşınır (hash doğrulanır) → `scale_assertion_analysis.py build` ve A22-2 `audit_sample.py` koşulur (yalnız örnekleme paketleri üretir; sonuç göstermez) → insan kodlaması yapılır (A22-2, sonra A26) → kodlayıcı dosyaları hash'lenip commit edilir → **ancak bundan sonra** G1 sonuç analizleri koşulur (`compute_gfs`, `rescore_crosslingual`, `crosslingual_stats`, taksonomi, `trap_analysis`, `guard_coverage`, `intervention_paths`, `tolerance_sensitivity`). Kodlayıcı 1 aynı zamanda yazar olduğu için bu sıra, kodlayıcıların G1 sonuçlarını görmeden kodlamasının tek güvencesidir.

**Amaç.** (i) SCALE_VIOLATION kanalının cümle-ölçek sözlüğünün canlı precision'ı (birincil) ve recall-sınırı (ikincil, kaba); (ii) canlı cross-scale restatement sayısı (sansüs, in-run, yalnız simülatör-çıktısı kayıtları). **Taahhüt:** sonuç-koşulsuz. Restatement bulunursa "exploratory, observed in [k] of 147 trap responses" diye raporlanır. Bulunmazsa sınırlı-null ve "kaynak sayı yokken restatement tanım gereği imkânsız" (A19: tuzaklarda araç 0/21) kabul edilebilir bir sonuçtur.

**Popülasyon.** 7 tuzak (`scale_focus=="cross"`) × 7 koşul × 3 tekrar, **grounded_noguard** `reply` (= ilk taslak, guard-bağımsız). Cümle = `provenance_guard._split_sentences`. Dahil olan cümleler, guard parser'ının ≥1 IGNORED-dışı numeral bulduğu cümlelerdir; izdeki `claims` cümleye `sentence` alanıyla (ilk 160 karakter) eşlenir. N kaydedilir. In-run ölçek-çıkarımı ve eşleşmeler izdeki `provenance.claims`'ten okunur (`claimed_scales`, `matched_key`, `record_scale`); yeniden-skorlama yapılmaz. Fallback/error yanıtları dışlanır ve sayılır. Cümle bölücüsünün bıraktığı parçalar (ör. "4.", iki harfli kelimeden az) popülasyonda kalır, `fragment_flag` ile işaretlenir ve kodkitabı §2 uyarınca "none" kodlanır; sayıları raporlanır.

**Tabakalar (seed 42).**
- **S1** = sözlük non-building iddialı cümleler (`claimed_scales` ∩ {feeder, policy} ≠ ∅). Sansüs; 150'den fazlaysa seed 42 ile 150'ye kırpılır.
- **S2** = ≥1 sayısı `record_scale=building` ve `matched_key` `input:`-dışı bir in-run kayıtla eşleşen cümleler. Sansüs, kırpılmaz. S1∩S2 → S2.
- **S3** = kalanlardan koşula orantılı rastgele örneklem (en büyük kalan yöntemi), n₃ = max(100, 250 − |S1| − |S2|). Toplam gerekirse 250'yi aşar.

Öğeler seed-42 permütasyonuyla tek listede karıştırılır. Tabaka, koşul, tekrar, sözlük ve eşleşme bilgisi ayrı bir anahtar dosyasındadır (`coding_key.csv`). Paket ve anahtar hash'leri `build_hashes.json`'a yazılır. `build` idempotenttir: aynı girdi aynı hash'leri verir (duman-testinde doğrulandı).

**İnsan kodlaması.** 2 kodlayıcı (A22-2 ekibi), A22-2 oturumundan SONRA. Ayrı sayfa ve kodkitabı kullanılır (`SCALE_CODEBOOK.md`, örneklemeden önce donar). Kodlayıcılar tabaka, kol, model ve sözlük çıktısına kördür. Kodlayıcı cümleyi ve soru metnini görür; komşu cümleleri görmez. Cümle başına `scale_building_YN`, `scale_multi_feeder_YN`, `scale_policy_YN` (çoklu izinli), `aggregation_YN`, `unsure_YN` kodlanır. Şüphede tüm ölçekler N'dir (none; muhafazakâr — restatement sayısını ve prevalansı DÜŞÜRÜR). Doğruluk/uydurma yargısı yapılmaz. Kodlayıcılar hiçbir G1 sonucunu görmeden kodlar: kodlama A22-1/A22-3 analizlerinden ÖNCE tamamlanır ya da kodlayıcılar o çıktıları görmez (beyan edilir).

**Güvenilirlik.** Değişken başına Cohen κ + ham anlaşma raporlanır. κ düşükse A18 kuralı uygulanır: ham κ + katı (AND) / gevşek (OR) sınırlar + madde-atıflı konsensüs. Yeniden-kodlama ve kodkitabı revizyonu yapılmaz. `analyze`, iki kodlayıcı dosyasında her öğenin dört ölçek/agregasyon değişkeni Y/N değilse koşmaz. Boş `unsure_YN` = N sayılır (kodkitabı §3). Kodlama paketleri UTF-8-BOM ile yazılır. Excel (TR) dönüşlerine tolerans: BOM, `;` ayırıcı ve küçük harf y/n kabul edilir. Bu yalnız biçim normalizasyonudur, kod değiştirmez.

**Analizler (dondu; `scale_assertion_analysis.py analyze`).** İnsan etiketi: multi = `scale_multi_feeder` ∨ `aggregation`.
1. **Precision** (ham, Wilson %95 GA): sözlük-bayraklı sansüs cümlelerinde (S1 + S2'ye düşen bayraklılar; S2 payı `n_from_S2` olarak etiketlenir) sözlük iddiasının insanla örtüşme payı. Feeder→multi ve policy→policy ayrı raporlanır. S1 kırpılmışsa ek olarak HT nokta tahmini verilir.
2. **FN-oranı** (S3, ham, Wilson): insan multi ∧ sözlük none/building.
3. **Recall (popülasyon)** = TP_S1 / (TP_S1 + p̂_FN × N₃), S1 ∪ S3 üzerinde HT ağırlıklı, yanıt-kümeli bootstrap (küme = koşul × soru × tekrar; 1 000, seed 20261014), "rough bound" etiketiyle. İkincil olarak S2 dahil HT recall de verilir.
4. **Prevalans** (HT ağırlıklı, tüm tabakalar, kümeli bootstrap).
5. **Restatement sayısı** (S2 sansüs): ≥1 simülatör-çıktısı building-kayıt eşleşmesi ∧ insan multi ∧ `scale_building=N`. Cümle, yanıt, soru ve koşul düzeyinde sayılır. **T2 ayrıştırması** iddia düzeyinde ve karşılıklı dışlayıcıdır: [0,100] aralığında tamsayı → `small_int`; değilse |v| ≤ 1.5 → `ratio`; değilse `other`. Hem tüm S2 eşleşmeleri hem restatement eşleşmeleri için verilir (yankı `input:` zaten dışarıda).
6. **Parametrik agregasyon:** simülatör-eşleşmesiz (`matched_key` yok ya da yalnız `input:`) ∧ insan multi. Ayrı betimsel satırdır; provenance-restatement DEĞİLDİR.
7. Restatement hücrelerinin (koşul, soru, tekrar) guard-kolu A22-1 yolu (`intervention_paths.classify`), betimsel.

**Hipotez testi YOK.** Metin önce tabaka-özgü ham sayıları verir; popülasyon tahminleri ikincildir.

**Jev (opsiyonel ölçeklendirici).** `jev` komutu ana makinede `jev_g4.McpClient` üzerinden koşar (`@jkudish/jev-mcp@0.14.3`, beklenen model `jev-1.13.0`, görülen model loglanır). Aynı kodlanan cümlelerde iki çağrı yapılır: `jev_classify` `asserted_scale` ∈ {building, multi_feeder, policy, none} (sınıf tanımları betikte donmuş) ve `jev_noul` aggregation önermesi. Eşik 0.8; altı çekimser = none. 32'lik partiler, 3 deneme. İstek ve yanıtlar tam olarak JSONL'e yazılır (`a26_jev_coded.jsonl`) ve yayınlanır. Log asla üzerine yazılmaz. Kesinti olursa yalnız aynı başlıkla (model, eşik, kapı, n) devam edilir ve etiketli cümleler atlanır. İstem ve eşik ayarı sonuç sonrası YASAKTIR. κ (değişken başına) insan etiketine karşı, kodlanan altkümede hesaplanır.

**Dondurulmuş κ-kapısı (tek kural).** Kapı değişkeni **multi** = `scale_multi_feeder` ∨ `aggregation` (Jev ve insan için aynı tanım). Referans, konsensüs dosyası varsa **konsensüs**, yoksa **katı (AND)** etikettir. Kapı = bu tek κ ≥ 0.6 ve Jev kodlanan koşusunun "complete" olmasıdır. Kapıyı `analyze` hesaplar ve `a26_results.json` → `jev.coded.gate` alanına yazar; `jev --scale-out` κ'yı komut satırından ALMAZ, bu dosyadan okur.
- **Kapı geçerse →** kalan tuzak cümlelerine ve tuzak-dışı 49 sorunun grounded_noguard cümlelerine (`population_nontrap.jsonl`) ölçeklendirme yapılır (`a26_jev_scaleout.jsonl`). Yalnız kapılı değişken (multi) ölçeklenir: multi oranı, sözlük-bayraklılarda Jev-multi payı, S2-uygun cümlelerde Jev restatement adayı (multi ∧ ¬building). Bunlar "Jev-estimated, human-validated on n=… trap sentences (κ=…)" etiketiyle ayrı blokta verilir ve insan oranlarıyla aynı tabloda birleştirilmez.
- **Kapı geçmezse →** betik ölçeklendirmeyi reddeder; yalnız κ raporlanır.

Tavan 3 000 çağrıdır. Etiketsiz cümle oranı %10'u aşarsa veya tavana ulaşılırsa sonuç "incomplete" olarak işaretlenir.

**Tasarım sırasında yapılan Jev sondaları (sızıntısız).** (a) Yanıt alanlarını öğrenmek için kodkitabının dev-korpus örnekleri #1 ve #4 ile 1 classify (2 öğe) + 1 noul (1 önerme) çağrısı yapıldı. (b) Betiğin ilk sürümü `smoke_v42` verisiyle denendi (Ekim öncesi tek-model duman koşusu; tuzak sorusu içermez; 21 cümle) + 10 cümlelik elle kurulmuş tuzak-dışı fikstür; 4 çağrı. (c) Son sürüm (kapı, devam, Excel toleransı) gerçek Jev'e hiç çağrı yapmadan, sahte bir istemciyle denendi (kesinti → devam; kapı reddi/geçişi; Excel-TR dosyaları). Hiçbir `oct_v42` cümlesi gönderilmedi. Duman çıktıları silindi.

**Konum ve donma.** Betik koşu sürerken `laadt-dss/prereg_staging/scale_assertion_analysis.py` altında dondurulur: backend `uvicorn --reload` `/app` altındaki `.py` değişikliklerini izler ve koşuyu bozardı. Koşu bittikten sonra `experiments/gfp_benchmark/` altına **bayt-özdeş** taşınır; hash aynı kalır ve taşıma commit'inde doğrulanır. A21/A24 hash'li dosyalara dokunulmaz.

| Dosya | SHA-256 |
|---|---|
| `experiments/gfp_benchmark/SCALE_CODEBOOK.md` (yeni) | `59fc975f8a1c9cbbfe94f61beab22b716b910741cf00d28bc9bedc7772563b90` |
| `laadt-dss/prereg_staging/scale_assertion_analysis.py` → `experiments/gfp_benchmark/scale_assertion_analysis.py` (yeni; koşu sonrası bayt-özdeş taşınır) | `e137905a5df499678b98c16870a0b65510377aaf0b2181959815eb0b322107cc` |
| `app/llm/provenance_guard.py` (bağımlılık; prereg-v3.1 ile aynı) | `a050b46ab5d8fa392215a1df47162c311daae95118d2bfa311d31e84a729f7c2` |
| `experiments/gfp_benchmark/questions.json` (bağımlılık; prereg-v3.1 ile aynı) | `7c5332396e0d7514cf00ffc7120debe8ed8ce8ae01ecb80d7c70feb7f9b4d546` |
| `experiments/gfp_benchmark/rescore_crosslingual.py` (bağımlılık; prereg-v3.1 ile aynı) | `d1cbe7747a56e0e79f3de8d06f15ef21e8760cfebe6ad4d06523910dfff897b1` |
| `experiments/gfp_benchmark/intervention_paths.py` (bağımlılık; prereg-v3.1 ile aynı) | `000a07eece101858664d2a9cc8a84e3ea5a3f512acf652509bb5a6769f6ae713` |
| `experiments/gfp_benchmark/jev_g4.py` (bağımlılık; prereg-v3.1 ile aynı) | `477c36a072fe841a11293a3041250a0fc4a33d35193b9ed76d14628bc25b23ef` |
| `experiments/gfp_benchmark/run_benchmark.py` (bağımlılık; prereg-v3.1 ile aynı) | `53c508231e0b657ccf7c4f52761200be8c4a0171b3591a8a3ff7cd80e6bc5b08` |

Hash'ler LF satır sonlu içerik üzerindendir (git blob içeriğiyle aynı). `core.autocrlf=true` bir checkout'ta dosyayı CRLF'ye çevirirse doğrulama `git show prereg-v3.2:<yol> | sha256sum` ile yapılır.

Git tag `prereg-v3.2`, koşu bitmeden ve `oct_v42/` analiz edilmeden.

### A27 (2026-10-14) — Araç-yolu denetimi: politika-şeması asimetrisi + üç simülatör düzeltmesi; G1 yeniden-koşusunun İPTALİ ve BAŞTAN koşusu [PRE-OUTCOME; koşu ~%11'de durduruldu (19:20 UTC); hiçbir Ekim sonucu görülmedi; danışman önerisi + kullanıcı kararı; prereg-v3.3]

**Nasıl bulundu.** Makale Appendix B (parametre beyanı, A22-5) için benchmark araç-yolundaki her parametre koddan izlendi (salt-okunur alt-ajan; bulgular satır satır doğrulandı). Danışman: politika-şeması hatası tek başına durdurmayı gerektirir; diğerleri simetriktir ama yeniden-başlatılacaksa birlikte düzeltilir. Kullanıcı "durdur, düzelt, yeniden başlat" seçti.

**A27-1 Harness asimetrisi (ölçümü etkiler).** `run_policy_scenario` şeması `discount_rate` ve `lifetime_years` alanlarını göstermiyordu; `_run_policy_scenario` ikisini okur (varsayılan 0.12 / 25). Referans graf sorunun `suggested_args`'ı ile kurulur. 8/56 soru (com-13, sta-02, sta-03, sta-04, sta-06, sta-08, sta-09, sta-11) varsayılan-dışı değer ister; sadık bir model bile bu sorularda referans sayılarına ulaşamaz. Etki: iki grounded kolda referans-GFS düşer (H_G1b nötr, H_G1a muhafazakâr yönde); A22-1 P2 argüman-sapması sayımı kirlenir. Temmuz'da da vardı. Karar-gerekçesi kanıtı (yalnız Temmuz verisi; grounded_noguard soru-ortalaması referans-GFS, etkilenen 8 / diğer 6 devlet sorusu): gemma TR 0.722 / 0.791; qwen3.5 TR 0.609 / 0.779; mistral TR 0.613 / 0.697; gemma EN 0.839 / 0.734; qwen3.5 EN 0.633 / 0.768. **Düzeltme:** şemaya iki alan (`discount_rate` için "Ondalık oran, ör. 0.12 = %12" açıklaması). **Sistematik kontrol:** her araç için soru-argümanları ⊆ şema; yalnız politika aracı eksikti. Test: `test_every_reference_argument_is_in_the_tool_schema`.

**A27-2 Simülatör düzeltmeleri (mutlak TL/kWh'yi etkiler, izlenebilirliği etkilemez).** Referans graf ve tüm kollar aynı `_execute_tool` yolundan geçtiği için ölçüm simetriktir.
- (a) **KDV iki kez:** `get_simple_tariff` fiyatı KDV-dahil; `simulate_annual_cashflow` yeniden ×(1+KDV) uyguluyordu (TL tasarruf/NPV ≈ %10 şişkin). Düzeltme: tarifede `vat_included`.
- (b) **Fatura→kWh:** sabit 0.5 TL/kWh (≈10× tüketim; 7 soru: com-02, res-01, res-04, sta-01, sta-05, sta-10, sta-12). Düzeltme: `bill_to_annual_consumption` (mesken kademeli tarife tersi; diğerleri düz ticari fiyat). Örnek: 2 500 TL/ay mesken → 7 137 kWh/yıl (eski 60 000).
- (c) **PV saat ekseni:** PV (UTC saatleri) yerel-saat yüküne konumdan eşleniyordu (≈3 saat erken). Düzeltme: PV yerel saate kaydırılır (`LOCAL_TIMEZONE="Europe/Istanbul"`, IANA tz; yıl boyu UTC+3). Ankara günlük ortalama tepe saati 12 (yerel).
- (d) **Vergi indirimi oranı:** `tax_deduction` varsayılan kurumlar vergisi 25 (formül 0.25 bekler) → 0.25. Hiçbir soru ve varsayılan politika kullanmaz; yalnız modelin kendiliğinden gönderdiği bir politikada etkili.

**A27-3 Temmuz-replay koruması.** (a)–(c) `IRRADIANCE_SOURCE=clearsky` (yalnız Temmuz replay) altında eski davranışı korur (`app/simulation/compat.py`); (d) Temmuz referanslarında hiç kullanılmadığından korumasızdır. `regression_clearsky_replay.py replay` yeniden koşuldu: 56 graf, 5 032 kayıt, 0 fark; çıktı dosyası bayt-özdeş (`ee96c100…88ce`). G4/B4/A25/A22-3-G4/A23-4 Temmuz analizleri geçerli kalır.

**A27-4 Belgelenen, düzeltilmeyen (Appendix B'de bayraklı).** Batarya kimyası araç yolunda sonucu değiştirmez (res-10, com-04, com-14 kimya karşılaştırır → özdeş sonuç); tüm paydaşlar mesken kademe-2 fiyatı öder; ticarethane 2× üretim sınırı uygulanmaz; grid aracı yalnız `1-LV-rural1--1-sw` ve SimBench yerleşik üretim/depolamasını korur (G3 betiği sıfırlar); MC 1 000 yineleme (uç-nokta 10 000 varsayılanı atlanır), MC iç fizibilitesi `residential`; PV degradasyonu (fizibilitede), O&M, batarya/inverter değişimi modellenmez; inverter dışı kayıp yok (pvlib `losses_model` varsayılanı); varsayılan tüketim 5 000 kWh; utility profili girdi/1.1 toplar; politika bağlamında ihracat 5.30 TL/kWh (0.4941 ihracat tarifesiyle çelişir); iskonto 0.12 etiketsiz (TL tasarruf %8/yıl arttığı için nominal davranır). Makalede "estimated / not modelled" bayraklı; mutlak ekonomik sayılar "illustrative".

**A27-5 Durdurma ve arşiv.** `oct_v42/` → `aborted_oct_v42_A27/` (455 satır, gemma4:e4b TR, 7 koşulun 1.'si; analiz edilmedi; `ABORTED.md`); `rerun_log.jsonl`'a `aborted` olayı. Koşu sırasında yalnız satır/hata/fallback/ortam alanları okundu (+ A26'da beyan edilen iki tuzak-dışı guard log satırı).

**A27-6 Kapı (A24 kapısının tekrarı).** 5 model; res-01, com-01, dis-01 + politika sorusu sta-04 (yeni şema alanları için); seed 10000; TR; grounded_noguard; `GFP_RUN_DIR=gate_a27`. Yalnız hata/fallback/araç-kaydı/dil/think incelendi; GFS hesaplanmadı; izler analiz glob'larına girmez. Sonuç: gemma4:e4b, qwen3.8:27b, mistral-small3.2:24b ve muse-glimmer:30b GEÇTİ: üç kapı sorusunda hata/fallback yok; ≥1 yürütülmüş araç çağrısı (gemma 2/3, qwen 3/3, mistral 1/3, muse 3/3); yanıtlar Türkçe; think sızıntısı yok. **Politika kontrolü (sta-04):** gemma, qwen, mistral ve GLM aracı `discount_rate=0.16` ile çağırdı (soru %16 ister) → şema düzeltmesi çalışıyor. Muse'un kapı hücresinde politika çağrısı `simulation_failed` döndü ve yanıt boş kaldı; aynı hücrenin tanı tekrarında Muse araç çağırmadan 708 karakterlik yanıt verdi. Yani Muse çıktısı bu sunucuda tohum-sabit olmayabilir; hata metni izde saklanmadığı için nedeni bilinmiyor; koşunun kendi determinizm kontrolü ölçer. **glm-4.7-flash ilk denemede KALDI:** res-01 fallback (60 s zaman aşımı → Mock yanıtı). Tanı: GLM'de res-01, model yüklendikten sonraki İLK istek olduğunda üretim 60, 120 ve 300 s zaman aşımlarını aştı; başka bir istekten sonra ≈10 s sürdü (com-01 ilk istek olarak 14.7 s). Çıktı sunucunun önek-önbelleği durumuna bağlı. **Düzeltme:** `run_g1_rerun._warm_up(model, lang)`: her koşuldan ve determinizm kontrolünden önce aynı sistem-promptu ve araç listesiyle, benchmark dışı tek token'lık bir sohbet isteği (`num_predict=1`, `temperature=0`, `keep_alive=30m`). Böylece her benchmark hücresi aynı (önekli) önbellek durumunda başlar. Isınmalı yeniden kapıda GLM 3/3 GEÇTİ (10.3 / 9.7 / 10.2 s; hata/fallback yok, Türkçe, think yok). Diğer dört model ısınmasız geçtiği için yeniden koşulmadı (ısınma yalnız ilk hücrenin önbellek durumunu eşitler). Kapı ve tanı izleri `results/gate_a27/` ve `results/gate_a27_diag/` altında; analiz glob'larına girmez, GFS hesaplanmadı. **Yan bulgu (makale Threats):** açık bir modelin tohum-sabit çıktısı sunucunun önbellek durumuna bağlı olabilir.

**A27-6b Koşu sürücüsü.** `run_g1_rerun.py`'ye yalnız `_warm_up` eklendi (A27-6); koşul sırası, kollar, tekrarlar, dışlama sınırı, determinizm kontrolü ve ortam tablosu DEĞİŞMEZ. İstek zaman aşımı 60 s olarak kalır (`OLLAMA_TIMEOUT` varsayılanı).

**A27-7 Doğrulama.** Testler 306/306 (yeni `tests/test_a27_fixes.py`: şema kapsamı, tek KDV + replay çift KDV, PV yerel saat + replay UTC, vergi oranı; fatura testi yeni davranışa güncellendi + replay testi). Üretim modunda 56/56 referans grafı geçerli (5 029 kayıt). Redis `sim:*` temizlendi.

**A27-8 Kapsam.** Hipotezler, testler, dışlama kuralları ve A21–A26 analiz kuralları DEĞİŞMEZ. `provenance_guard.py` bayt-özdeş (`a050…f7c2`). A26 (`prereg-v3.2`) olduğu gibi geçerlidir (izden okur); A26'nın koşu-sonrası işlem sırası bu (v3.3) koşuya uygulanır. Hash tablosu A21-α gereği TAMAMI yeniden hesaplandı.

**A27-9 Makale.** Threats "Evaluation coverage and the re-run": üçüncü paragraf (politika şeması + üç simülatör hatası + durdurma + replay + kapı + v3.3). Appendix B: her kalem kaynaklı / estimated / not modelled; A27 düzeltmeleri † ile.

**Donma.** `prereg-v3.3`; 7 koşul × 3 kol × 56 soru × 3 tekrar baştan; `GFP_RUN_DIR=oct_v42`.

**Donmuş hash'ler (SHA-256) — git tag `prereg-v3.3`, koşu başlamadan.**
| Dosya | SHA-256 |
|---|---|
| `app/llm/provenance_guard.py` | `a050b46ab5d8fa392215a1df47162c311daae95118d2bfa311d31e84a729f7c2` |
| `app/llm/ollama_orchestrator.py` | `283ccfe725bf45d34498cfa0acd2eeab76c0e553bcd3bc2e422f1a388296b94e` |
| `app/llm/prompts/stakeholder_prompts.py` | `8ac4d7ebd7ece693003fd5ddcfde43ab9955a26c4e4b3f1fbc3ef795089906ea` |
| `app/api/routes/simulation.py` | `4cec91f4853a6d05eb4a3e7aeaec535709e9a48e82daa16214836a21fb6bca06` |
| `app/simulation/compat.py` | `ee0d7143b5a2bf6e2bfd3527126c6d85032ab59f3093be6846bfa136fe219021` |
| `app/simulation/pv/solar_model.py` | `0a8314e7b6467407350b88dfff8760653bd8519ac6e21cf25c485c803693744a` |
| `app/simulation/pv/tmy_cache/MANIFEST.json` | `4d78202d1d9f02351bf034119fe5a9bdcb45dfb3d82debfacc2979763976bbd5` |
| `app/simulation/advisor/feasibility_service.py` | `656b1c41570c82c52a05bab9bfa42582abb2056c90c0eab53f5b2c39156ad9c7` |
| `app/simulation/advisor/sizing.py` | `219925af7a7487c0ff48faba313ba780fb922f446780febe4a6189e92219aeb6` |
| `app/simulation/economic/economic_engine.py` | `924454c25d743ce5396fce4e0bd37781dd2e77cbd1411fba0b5c568b2f7ebda7` |
| `app/simulation/economic/tariffs/turkey_2026.py` | `2815f15fc8505792e574820a674daaa8b8e69107407593dc86c858c462714ce1` |
| `app/simulation/economic/monte_carlo.py` | `d8d01ae0182a138baff4fceee745f59f9f72ec7b8b6e77c62ebfd8396dd82668` |
| `app/simulation/bess/battery_model.py` | `4745973a911820fc6f1e52ee946174cdc66d6295b81034c2482af799aab42844` |
| `app/simulation/policy/policy_engine.py` | `f12a66eeca7441ed2f2f18feff53acb32f50df812c2e9353099f3572437c2d1b` |
| `app/simulation/grid/grid_model.py` | `0680ee498b31d12a14838fbc00b17a442d472f13afa7388be01a6c775db19c16` |
| `app/simulation/loads/standard_profiles.py` | `13aa28a42c74e723ba445cd9e9295bebf97b0d45c571a641ec7d3552a98bcdb5` |
| `app/simulation/loads/turkey_parameters.py` | `26b7b1a9995f2b3cd0a300239685191ed7e1de15fdbe29cb3e838360c94b51cc` |
| `tests/test_a27_fixes.py` | `5a1009e98c471ab5d07328d2a429119df0ce7abcd81220255f38674fa51e99b7` |
| `experiments/gfp_benchmark/questions.json` | `7c5332396e0d7514cf00ffc7120debe8ed8ce8ae01ecb80d7c70feb7f9b4d546` |
| `experiments/gfp_benchmark/run_benchmark.py` | `53c508231e0b657ccf7c4f52761200be8c4a0171b3591a8a3ff7cd80e6bc5b08` |
| `experiments/gfp_benchmark/run_g1_rerun.py` | `da13124781a5e34328ee95cf32667443ee7389cfa4be13deb00c7ba7693b9389` |
| `experiments/gfp_benchmark/compute_gfs.py` | `bc730e5404326b01730a86af9b57570fcdb97184799e13e01a84d45ab7f8015d` |
| `experiments/gfp_benchmark/rescore_crosslingual.py` | `d1cbe7747a56e0e79f3de8d06f15ef21e8760cfebe6ad4d06523910dfff897b1` |
| `experiments/gfp_benchmark/crosslingual_stats.py` | `840fad008573b5ea998dfc796f9e71a114cceea3c9f857f496fad1ce55341344` |
| `experiments/gfp_benchmark/analyze_guard_flag_taxonomy.py` | `761dc9f3bff3b2c5f2d41cf9b17ce93648b5b2e6ceea479931bc812f9c36197f` |
| `experiments/gfp_benchmark/trap_analysis.py` | `f4823546094c19b55eb8606b4ef80f9b1a0b2e1264ce5dfd25376e214fd24976` |
| `experiments/gfp_benchmark/guard_coverage.py` | `93e8d2798171b52b6fc70ea52d87d4d631cd739df670df353b5af8270b916ef1` |
| `experiments/gfp_benchmark/intervention_paths.py` | `000a07eece101858664d2a9cc8a84e3ea5a3f512acf652509bb5a6769f6ae713` |
| `experiments/gfp_benchmark/tolerance_sensitivity.py` | `61f1d9f0fc40497a4131babe270b4bb1484ff6ae332468ac9d0c54febe55bc75` |
| `experiments/gfp_benchmark/audit_sample.py` | `104d91c3bdeb0964614d123d44159c495b63156b65527a06562d491302d7e25b` |
| `experiments/gfp_benchmark/AUDIT_CODEBOOK.md` | `aebecc452b44b2ae8e847c42ccbf3126e5e229bf881d7527c2f655637fd1cfc8` |
| `experiments/gfp_benchmark/SCALE_CODEBOOK.md` | `59fc975f8a1c9cbbfe94f61beab22b716b910741cf00d28bc9bedc7772563b90` |
| `experiments/gfp_benchmark/clearsky_mode.py` | `9324d43d1f15d473acacacc5067ede10a9b56ad8a2aa43634d63f83678a704f6` |
| `experiments/gfp_benchmark/regression_v41_v42.py` | `99bca635fcecab19a5fafd7ac0fd0bd41e171f216e9c01c97a24b56d523ac1af` |
| `experiments/gfp_benchmark/regression_clearsky_replay.py` | `9563ddf87f6a1239676cc874c47488163464a3e7e02e7f005928c744e20fcce7` |
| `experiments/gfp_benchmark/a23_legacy_decomposition.py` | `82711efc7c90703a37668cd76ad6404fda0b1cf665c804d854c2934d04cfbc48` |
| `experiments/gfp_benchmark/a25_freeze_evidence.py` | `e17e0a59412599bac06561b4c2da376aa0f3cfb2813f5d1c13dfc154ac1e4ada` |
| `experiments/gfp_benchmark/jev_g4.py` | `477c36a072fe841a11293a3041250a0fc4a33d35193b9ed76d14628bc25b23ef` |
| `experiments/gfp_benchmark/results/regression_v41_v42.json` | `c251e0fd11802210fd3dcfc566eeee6640a8a1a65a7879e8ee1e1110aed25648` |
| `experiments/gfp_benchmark/results/clearsky_ref_snapshot.json` | `2c395eebe038ffcde2d237fd2b46a89447aef82b01e91b384c0b515c96c1045e` |
| `experiments/gfp_benchmark/results/regression_clearsky_replay.json` | `ee96c100b19f278bb31d0bf16aa969d8d390db070000edbfad5e55ea9c6688ce` |
| `experiments/gfp_benchmark/results/a23_legacy_decomposition.json` | `6b9fa463efb969a5e0ba4ce321358c58df029d807a322d31be4f01c80e4799d3` |
| `experiments/gfp_benchmark/results/a25_evidence_items.json` | `953daa372ce4340ce5fd02b635416b6c262dd8aaa2a831bb89b2f20b27a2206b` |
| `laadt-dss/prereg_staging/scale_assertion_analysis.py` (A26; koşu sonrası `experiments/gfp_benchmark/` altına bayt-özdeş taşınır) | `e137905a5df499678b98c16870a0b65510377aaf0b2181959815eb0b322107cc` |

Testler: 306/306. `provenance_guard.py` A21 ile bayt-özdeş. Hash'ler LF satır sonlu içerik üzerindendir (git blob içeriğiyle aynı; doğrulama `git show prereg-v3.3:<yol> | sha256sum`).

### Beyan (2026-10-14) — Kodlayıcı-2 kimliği (A22-2 ve A26) [PRE-OUTCOME; hiçbir kural değişmez]
Kodlayıcı-1 yazar Baran Kaynak'tır (A22-2'de beyanlı). Kodlayıcı-2 Sümeyye Kaynak'tır. Kendisi çalışmanın iç hakemidir: makalenin taslağını, hipotezlerini ve Temmuz sonuçlarını bilir, Ekim (`prereg-v3.3`) sonuçlarını bilmez. Körlük kuralları değişmez. Kodlayıcı-2 yalnız kodlama paketlerini ve kodkitaplarını (`AUDIT_CODEBOOK.md`, `SCALE_CODEBOOK.md`) görür. Kol, yol, model ve tabaka etiketlerini, eşleştirici kararlarını, kodlayıcı-1'in etiketlerini ve hiçbir Ekim sonucunu kodlama bitip kodlayıcı dosyaları hash'lenene dek görmez. Makalede şöyle beyan edilir: "the second coder is an internal reviewer familiar with the study's hypotheses and July results, and blind to the October results, the arm and model labels, and the first coder's labels".

### Beyan (2026-11-05) — Referans erişilebilirliği ve trafo-erteleme çıktısı [PRE-OUTCOME; hiçbir Ekim sonucu görülmedi; A22-2/A26 kodlaması sürerken; birincil analizler değişmez]

**Nasıl bulundu.** Kodlayıcı-1'in S4 sorusu (`results/oct_v42/audit/CODER_QA_LOG.md`) üzerine soru seti tarandı: her referans argümanı soru metniyle ve araç varsayılanlarıyla karşılaştırıldı (otomatik tarama + elle geçiş). Yalnız `questions.json`, araç kodu ve LLM'siz referans snapshot'ının anahtar adları okundu. Ayrıntı ve tablolar: `QUESTION_INPUTS.md`.

**B1 Referans erişilebilirliği.** 25/56 soruda referans graf, metinde geçmeyen ve araç varsayılanına eşit olmayan en az bir argüman değeri kullanır. Bu sorularda sadık bir model referans sayılarına ancak tahminle ulaşır. A27-1'in 8 politika sorusundan com-13, sta-04 ve sta-08 iskonto ve ömür değerlerini metinde verir; sta-06 yalnız iskontoyu verir; sta-02, sta-03, sta-09 ve sta-11 ikisini de vermez. Bu yüzden A27-1 düzeltmesi referansı yalnız com-13 ve sta-04 için tam erişilebilir yapar. sta-08 başka bir nedenle erişilemez kalır: yatırım ve tasarruf tutarları metinde yoktur. Sekiz sorunun altısı 25'lik listededir. Etki A27-1 ile aynı yöndedir: yalnız grounded kolların referans-GFS'i düşer. Bu, grounded–ungrounded karşılaştırmasını muhafazakâr yapar; guard–noguard karşılaştırması simetrik kalır.

**B2 Trafo-erteleme çıktısı araç yolunda yok.** `_run_grid_impact`, `run_deferral_analysis` göndermez. Bu yüzden hiçbir referans ya da oturum grafı erteleme kaydı içermez. dis-05 ve dis-11 yalnız ertelemeyi sorar; bu ikisinde hiçbir kolda izlenebilir cevap yoktur. dis-08 ve res-12 ertelemeyi başka büyüklüklerle birlikte sorar. Bu durum düzeltilmez: G1 koşusu bitti ve araç yolu G1-MT'de de aynı kalmalıdır (A28).

**B3 Analize etkisi (ön-belirlenmiş duyarlılık; birincil DEĞİŞMEZ).** G1 referans-GFS'e dayanan birincil analizler (H_G1a/H_G1b, model başına Wilcoxon + bootstrap GA) aynı kodla ek olarak 30 soruluk alt kümede raporlanır. Bu alt küme, iki sınırlamadan da etkilenmeyen sorulardır (`QUESTION_INPUTS.md`). Raporlama sonuç-koşulsuzdur ve ikisi de verilir; birincil sonuç tam settir. **Uygulama:** Donmuş dosyalar değişmez. Alt küme, `QUESTION_INPUTS.md`'deki id listesini mevcut `compute_gfs`/`crosslingual_stats` fonksiyonlarına geçiren ince bir sarmalayıcıyla hesaplanır (`g1_reachable_subset.py`). Sarmalayıcının hash'i, G1 sonuçları incelenmeden önce bir Beyan'la kaydedilir. Makale §limits'teki A27 cümlesi düzeltilir ("ask for" yerine "reference graphs use") ve iki sınırlama eklenir.

### A28 (2026-11-05) — Çok turlu ek deney G1-MT: eksik-girdili sorularda ikinci tur [PRE-RUN; G1-MT koşusu yok; hiçbir Ekim sonucu görülmedi; A22-2/A26 kodlaması sürerken; danışman (Fable) görüşü + kullanıcı kararı (boyut "Tam"); prereg-v3.4]

**Gerekçe.** Benchmark tek turludur. 21/56 soruda gereken bir aracın zorunlu girdisi metinde yoktur: 17'si net, 4'ü katı okumayla (`QUESTION_INPUTS.md`). Bu sorularda girdi istemek makul bir hamledir, ama tek turda "kullanılamaz" sayılır. G1-MT iki şeyi test eder:
- kullanıcı eksik girdiyi verdiğinde sistem sorulan büyüklüğe izlenebilir bir sayı veriyor mu;
- guard'ın fail-closed kullanılabilirlik maliyeti konuşmada geri kazanılıyor mu.

Bu ikincil bir deneydir; G1'in hipotezlerini, analizlerini ve sonuçlarını değiştirmez. Sonuç her iki yönde de çıkabilir. Örneğin kullanıcının verdiği sayının metinde yalnız yankılanması, guard'lı kolda yeni ihlal üretir. Sonuç-koşulsuz raporlanır. G1-MT koşusu makale gönderiminden önce tamamlanırsa makalede raporlanır, sonucu ne olursa olsun.

**A28-1 Tasarım.**
- **Sorular:** `multiturn_turn2.json`'daki 21 soru (`subset` = clear 17 / strict 4).
- **Tur 1:** soru metni; G1 ile aynı, dil koşula göre seçilir.
- **Tur 2:** sorunun sabit mesajı ("Ek bilgi: …" / "Additional information: …"). Tur-1 cevabından bağımsız olarak **her zaman** gönderilir. Mesaj yalnız metinde geçmeyen referans argüman değerlerini sayar; araç, ölçek ya da çarpma hakkında ipucu içermez. Bilinen tuhaflıklar raporda belirtilir: res-04'te kullanıcı "uygun boyut" istemişken mesaj "4 kW" der; sta-07 ve sta-10'da mesaj, soruda geçmeyen bir batarya kapasitesi verir. Değerler `suggested_args[_per_step]` ile birebir aynıdır (üretici betikte assert'li). Bu yüzden donmuş referans graflar tur 2'de aynen geçerlidir.
- **Kollar, koşullar, tekrarlar** G1 ile aynıdır:
  - 3 kol (`grounded_guard`, `grounded_noguard`, `ungrounded`);
  - `run_g1_rerun.CONDITIONS`'taki 7 model–dil koşulunun hepsi;
  - 3 tekrar; seed 10000+r, iki turda aynı.
- **Oturum:** (koşul, kol, soru, tekrar) başına bir oturum; her konuşma başında oturum silinir.
- **G1'den aynen alınanlar:** ısınma, Ollama sürümü/digest kaydı, MAX_ATTEMPTS=2, EXCL_LIMIT=0.10 ve Mock-fallback dışlaması.
- **Digest değişikliği:** Bir modelin digest'i G1'dekinden farklıysa koşul yeni digest'le koşulur ve beyan edilir. Tur 1–tur 2 karşılaştırması koşu içindedir; G1 ile karşılaştırma yalnız betimseldir.
- **Değişmeyen kod:** Guard, orkestratör ve simülatör `prereg-v3.3` ile bayt-özdeştir (aşağıdaki hash'ler). Özellikle iki davranış değiştirilmez: tur 2'de araçsız bloklamada `safe_summary(None)`'ın "özetlenebilir alan yok" çıktısı ve trafo-erteleme çıktısının yokluğu (Beyan B2).
- **Yazılmamış kod:** Koşucu `run_multiturn.py` ve analiz `multiturn_analysis.py` henüz yazılmadı. Koşudan **önce** yazılır, testlenir ve hash'leri bir koşu-öncesi Beyan'la kaydedilir. Bu iki dosya yalnız bu amendment'ı uygular; herhangi bir sapma, koşudan önce yeni bir amendment gerektirir.
- **Çıktı ve zamanlama:** Çıktı `results/oct_v42_mt/` altına yazılır. Koşu, G1 analizleri bittikten ve GPU boşaldıktan sonra yapılır.

**A28-2 Ölçütler (otomatik; yeni insan kodlaması yok).**
- **TU_t (izlenebilir kullanılabilir cevap, t ∈ {1,2}):**
  - Tanım: tur-t kaydındaki guard raporunda (`provenance.claims`, teslim metni) verdict'i GROUNDED olan ve `matched_key`'i bir `answer_keys.json` regex'ine uyan en az bir iddia varsa 1, yoksa 0. Regex, sorunun `numeric_focus` etiketlerinden birine aittir; `matched_key` karşılaştırmadan önce `[n]` → `[]` biçimine getirilir ve `re.fullmatch` kullanılır.
  - `input:*` anahtarları cevap sayılmaz, çünkü bunlar yankıdır.
  - Değiştirilmiş (withheld) yanıt aynı kuralla puanlanır.
  - `ungrounded` kolda kayıt olmadığı için TU yapısal olarak 0'dır. Bu kol TU testlerine girmez; yalnız betimsel kalır.
  - dis-05'in bütün etiketleri eşlemesizdir (Beyan B2). Bu soru TU analizlerinden çıkarılır, böylece n = 20 soru kalır.
  - Bilinen sınır: bir değer birden çok kayda eşleşirse graf sırasındaki ilk birim-uyumlu kayıt kazanır. Bu durumda cevap anahtarı kaçabilir (§limits "Verification rules").
- **Analiz birimi:** soru. TU(q, kol, t), 7 koşul × 3 tekrar üzerinden ortalamadır; dışlanan konuşmalar hariç tutulur ve başarılan n raporlanır.
- **H_MT1 (birincil):** `grounded_guard` kolunda TU(q, 2) − TU(q, 1). Test: soru düzeyinde eşli Wilcoxon signed-rank, iki yönlü.
- **H_MT2 (birincil):** Guard'ın kullanılabilirlik maliyeti C(q, t) = TU(q, noguard, t) − TU(q, guard, t) olarak tanımlanır. Test: C(q, 2) ile C(q, 1) arasında eşli Wilcoxon, iki yönlü.
- **Birincil ailenin istatistik ayarları:** Holm düzeltmesi {H_MT1, H_MT2} üzerinde, α = 0.05. Etki büyüklüğü: ortalama eşli fark ve 10.000 örneklemli bootstrap %95 GA (soru yeniden örneklemesi, seed 20260708). Wilcoxon, `compute_gfs` ile aynı ayarlarla çalışır (`zero_method="wilcox"`, iki yönlü).
- **Duyarlılık:** H_MT1 ve H_MT2 yalnız clear-17 alt kümesinde tekrarlanır.
- **İkincil (betimsel, GA'lı; doğrulayıcı iddia yok):**
  - (a) tur-2 referans-GFS, kol başına; guard ile noguard arasında soru düzeyinde Wilcoxon;
  - (b) `grounded_guard` kolunda tur-2 bloklama oranı, tur 2'de araç çağrılıp çağrılmadığına göre ayrılmış (kaynak: tur-2 `provenance.tool_trace`);
  - (c) koşul başına TU tabloları;
  - (d) tur-1 araç-çağırma oranı;
  - (e) tuzak sorularında (res-11, res-12, com-10, sta-07, sta-10) tur-2 SCALE_VIOLATION sayıları, kol başına. Tur-2 mesajı bu sorularda fider-ölçekli bir girdi (penetrasyon) verir; tuzak sonuçları yalnız betimseldir.

**A28-3 Vekil doğrulaması (A22-2 etiketleriyle).**
- **Ne zaman:** A22-2 kodlayıcı dosyaları hash'lenip commit edildikten sonra.
- **Nasıl:** TU, A22-2 örnekleminin 86 yanıtı için aynı kuralla G1 kayıtlarından hesaplanır. Sonra her kodlayıcının `usable_answer_YN` etiketiyle Cohen κ'sı ölçülür.
- **Geçerlilik ölçütü:** Her iki kodlayıcı için de κ(TU, kodlayıcı) ≥ 0.70 **ya da** ham uyum ≥ 0.85 (PABAK ≥ 0.70'e denk). Ham uyum ölçütü, `usable_answer_YN` dağılımı tek yanlı olduğunda κ'nın yaygınlık nedeniyle düşmesine karşı eklendi (bkz. makale §limits, A17 denetimi κ = 0.13). Her kodlayıcı için κ, PABAK ve ham uyum birlikte raporlanır.
- **Ölçüt sağlanmazsa:**
  - H_MT testleri yine raporlanır, ama "vekil doğrulanamadı" ibaresiyle.
  - Ek olarak 40 tur-2 teslim metni (20 guard, 20 noguard; seed 42; soruya göre tabakalı) iki kodlayıcı tarafından donmuş `AUDIT_CODEBOOK.md` ile `usable_answer_YN` olarak kodlanır ve κ(TU, insan) raporlanır.
  - Testler değişmez.
- **Kapsam beyanı:** A22-2 yalnız guard kolu metinlerini içerir. TU, kullanılabilirliğe ek olarak izlenebilirlik de ister; guard kolunda teslim edilen sayılar zaten büyük ölçüde temellidir.

**A28-4 Körlük ve sıra.**
1. Bu amendment, A22-2 ve A26 kodlayıcı dosyaları hash'lenmeden önce dondu. Hiçbir Ekim sonucu ya da anahtarı görülmeden yazıldı.
2. G1-MT koşulduğunda G1 sonuçları bilinebilir; ancak tasarım ondan önce donmuştur.
3. G1-MT çıktısı, analiz betiğinin hash'i kaydedilmeden incelenmez.

**Donmuş dosyalar** (sha256, LF satır sonlu içerik; doğrulama `git show prereg-v3.4:<yol> | sha256sum`):

| dosya | sha256 |
|---|---|
| `experiments/gfp_benchmark/multiturn_turn2.json` | `6297bbac5a616dde070f38da96864e9be191be53b60fb21aa54cf166717774e9` |
| `experiments/gfp_benchmark/answer_keys.json` | `758f63b862db4f55e58c8056c4f6b907024601ce1c083446070b1cfe6a6457e1` |
| `experiments/gfp_benchmark/make_multiturn_assets.py` | `d7c0e3465bdeafdfde1b6ccb93e924b95a89604ee7edcf8e7374104065273434` |
| `experiments/gfp_benchmark/QUESTION_INPUTS.md` | `579ba2bb0d4bd158cfddf0ef15e852c5fb6d2fbaef9f23f92a398d4779184320` |
| `experiments/gfp_benchmark/questions.json` (değişmedi) | `7119745b109465d511e669f1e2a162fa753d541a4bacf68be1368864c029e855` |
| `app/llm/provenance_guard.py` (prereg-v3.3 ile aynı) | `a050b46ab5d8fa392215a1df47162c311daae95118d2bfa311d31e84a729f7c2` |
| `app/llm/ollama_orchestrator.py` (prereg-v3.3 ile aynı) | `283ccfe725bf45d34498cfa0acd2eeab76c0e553bcd3bc2e422f1a388296b94e` |
| `experiments/gfp_benchmark/run_benchmark.py` (prereg-v3.3 ile aynı) | `53c508231e0b657ccf7c4f52761200be8c4a0171b3591a8a3ff7cd80e6bc5b08` |
| `experiments/gfp_benchmark/run_g1_rerun.py` (prereg-v3.3 ile aynı) | `da13124781a5e34328ee95cf32667443ee7389cfa4be13deb00c7ba7693b9389` |
| `experiments/gfp_benchmark/compute_gfs.py` (prereg-v3.3 ile aynı) | `bc730e5404326b01730a86af9b57570fcdb97184799e13e01a84d45ab7f8015d` |

Not: Önceki tablolarda `questions.json` için kayıtlı `7c5332396e0d7514…` değeri, Windows çalışma kopyasının (CRLF) hash'idir. Diğer dosyalar gibi LF/blob içeriğinin hash'i yukarıdaki `7119745b…` değeridir. İçerik değişmemiştir: `git diff prereg-v3.3 -- experiments/gfp_benchmark/questions.json` boştur. Uygulama kodu (`app/`) `prereg-v3.3`'ten beri değişmedi (`git diff --stat prereg-v3.3 -- app/` boş).

### A29 (2026-11-05) — Kodlayıcı-2 alt kümesi: kısmi çift kodlama (A22-2 30/86, A26 80/263) [PRE-OUTCOME; kodlayıcı-2 hiç başlamadı; hiçbir kodlayıcı-2 etiketi yok; hiçbir Ekim sonucu görülmedi; danışman (Fable) görüşü + kullanıcı kararı ("Az"); prereg-v3.5]

**Gerekçe.** Kodlayıcı-2'nin (Sümeyye Kaynak) zamanı tüm öğeleri kodlamaya yetmiyor. A22-2 ve A26 "2 kodlayıcı" diye ön-kayıtlıydı; tam set artık çift kodlanmayacak. Bu, beyan edilen bir sapmadır. Daha güçlü kanıt başka bir ikinci kodlayıcıyla tam çift kodlama olurdu; kullanıcı alt-küme yolunu seçti. Kodlayıcı-1 (yazar) bütün öğeleri kodlamaya devam eder; bu değişmez.

**A29-1 Alt küme.**
- Çekim `coder2_subset.py` ile yapıldı: seed 20261105, donmuş tabakalara orantılı, en büyük kalan yöntemi. Tabakalar A22-2'de yol × koşul, A26'da S1/S2/S3'tür.
- Kullanılan kümeler: `coder2_subset.json` içindeki boyut "30" (A22-2) ve boyut "80" (A26). Her ikisi de yaklaşık üçte birdir.
- Çekim, kodlayıcı-2'nin durumu sorulmadan ve hiçbir etiket okunmadan commit `dc89447`'de yapıldı. Kodlayıcı-2'nin durumu ("hiç başlamadı", kodlayıcı-1'in beyanı) çekimden sonra öğrenildi.
- Kodlayıcı-2 sayfası (arayüz v4) yalnız bu öğeleri gösterir. Sayfanın geri kalanı v3 ile bayt-özdeştir (`CODER_QA_LOG.md`).

**A29-2 A22-2 analizi.**
- Birincil insan etiketi kodlayıcı-1'inkidir ve 86 yanıtın tümünü kapsar. Y1, Y2 ve usable-oranı bu etiketlerle hesaplanır.
- Sayı-düzeyi ve yanıt-düzeyi Cohen κ, 30'luk örtüşmede hesaplanır; ham uyum ve PABAK ile birlikte raporlanır.
- Yanıt-düzeyi κ yalnız 30 birime dayandığı için GA'sı geniştir. Sayı-düzeyi κ çok daha fazla birime dayanır.
- Y1 ve Y2 örtüşmede iki kodlayıcının etiketleriyle ayrı ayrı da hesaplanır ve yan yana raporlanır.
- κ düşükse A18 kuralı örtüşmede aynen uygulanır.

**A29-3 A26 analizi.**
- Tahminler 263 cümlenin tümünde kodlayıcı-1 etiketleriyle hesaplanır: precision, S3 FN-oranı, recall sınırı, prevalans ve restatement. Bu "coder1" etiket seti, A26'daki konsensüs ve katı/gevşek setlerinin yerini alır.
- Değişken başına κ ve ham uyum, 80'lik örtüşmede hesaplanır.
- Örtüşmede ayrıca değişken başına şu sayılar raporlanır: kodlayıcı-1 etiketinin katı (AND) ve gevşek (OR) etiketten farklı olduğu cümle sayıları. Bu, birincil etiketin hangi yöne yanlı olabileceğini gösterir.
- **Jev κ-kapısı:** donmuş tanım aynen geçerlidir:
  - kapı değişkeni multi;
  - referans: konsensüs varsa konsensüs, yoksa katı AND;
  - koşul: κ ≥ 0.6 ve Jev koşusu "complete".
  Kapı yalnız 80'lik örtüşmede hesaplanır. Kapı geçerse ölçeklendirme kapsamı A26'daki gibidir.

**A29-4 A28-3 vekil doğrulaması (yeniden yazım).**
- κ(TU, kodlayıcı-1) 86 yanıtta, κ(TU, kodlayıcı-2) 30'luk örtüşmede hesaplanır.
- Ölçüt her biri için A28-3'teki gibidir: κ ≥ 0.70 ya da ham uyum ≥ 0.85.
- Ölçüt sağlanmazsa 40 yanıtlık insan kontrolünü yalnız kodlayıcı-1 yapar.

**A29-5 Uygulama.**
- Donmuş `scale_assertion_analysis.analyze` iki tam kodlayıcı dosyası ister ve değiştirilmez.
- Bunun yerine bir sarmalayıcı (`coder_subset_analysis.py`) donmuş yardımcıları (`_read_coding`, `_kappa`, `_wilson`, `_ratio_boot`) aynı tanımlarla çağırır: κ ve kapıyı örtüşmede, tahminleri kodlayıcı-1 etiketleriyle hesaplar.
- Eksik kodlayıcı-2 satırları **asla** doldurulmaz.
- Sarmalayıcının hash'i, kodlayıcı dosyaları hash'lenmeden önce bir Beyan'la kaydedilir.
- A22-2 analiz betiği henüz yazılmadı; bu kuralları uygular ve aynı şekilde hash'lenir.

**A29-6 Makale (Threats, taslak cümle).** "Both human audits were pre-registered with two full coders. Because the second coder's time was limited, the first author coded every item and a second coder, blind to arm, path, matcher verdicts and the first coder's labels, independently coded a seed-drawn stratified subset of about one third (30 of 86 responses; 80 of 263 sentences), drawn before the second coder's progress or any label was known. Agreement is reported on that subset; the primary labels are the first author's."

**Donmuş dosyalar** (sha256, LF içerik):

| dosya | sha256 |
|---|---|
| `experiments/gfp_benchmark/coder2_subset.py` | `326298ff2024593ea39c0c4a7ea5e29e7bb5f4819651cfa7eb8984609b1b8a64` |
| `experiments/gfp_benchmark/coder2_subset.json` | `5803c55c81338dea92b478d572c5b9890b12a22a07ce26b8785017177b0c0b86` |
| `results/oct_v42/audit/coding_interface_v4/coder2.html` (git dışı; yayımlanan kodlayıcı-2 sayfası, sürüm `1793829474-3107`) | `221e190d1354d80f6cd4143114b8caeda20b8c97750f0ffa129c36ae3f1bd6bd` |
| `results/oct_v42/audit/coding_interface_v4/patch_v4_subset.py` (git dışı) | `d67e59bdf9637ab2934f7383b1970e74397632d6f36fd8a35e294ed349865af0` |

### Beyan (2026-11-05) — Kodlama bitti; analiz betikleri kodlayıcı dosyaları hash'lenmeden ÖNCE donuyor [PRE-OUTCOME; hiçbir etiket içeriği ve hiçbir Ekim sonucu görülmedi; A29-5 ve Beyan B3 uyarınca]

**Durum.** İki kodlayıcı da kodlamayı bitirdi.
- **Kodlayıcı-1:** etiketler kodlama sayfasının veritabanından (`codes/`, 349 belge) ArtifactData ile `audit/coder1_db_final/` altına indirildi. `export_coder1_csv.py`, bunları sayfanın kendi CSV dışa aktarımıyla birebir aynı biçimde `coded/audit_coded_coder1.csv` ve `coded/scale_coded_coder1.csv` dosyalarına yazar. Etiket-dışı sütunların örnekleme şablonlarıyla aynı olduğu assert'lidir.
- **Kodlayıcı-2:** iki dışa aktarım dosyası kodlayıcı-1 aracılığıyla alındı ve `coded/audit_coded_coder2.csv` ile `coded/scale_coded_coder2.csv` olarak kopyalandı.
- **Kontrol:** Yalnız eksiksizlik sayıldı: kodlayıcı-1'de 86/86 yanıt ve 263/263 cümle; kodlayıcı-2'de 30/30 ve 80/80; boş zorunlu hücre yok, öğe kümeleri `coder2_subset.json` ile aynı. Etiket değerleri görüntülenmedi.

**Analiz betikleri.** Hepsi rastgele sahte etiketlerle duman testinden geçti. G1 sarmalayıcısı yalnız Temmuz verisiyle denendi; Ekim çıktısı üretilmedi.
- `a22_audit_analysis.py`: A22-2 için κ, Y1, Y2 ve usable (A29-2). Sayı düzeyi κ'da "N/A excluded" şöyle uygulanır: iki kodlayıcıdan biri N/A dediyse birim κ'ya girmez; N/A uyuşmazlıkları ayrıca sayılır. A18 sınırları örtüşmede her zaman raporlanır: ikisi de N/A ise N/A; katı etikette Y yalnız ikisi de Y ise; gevşek etikette Y biri Y ise. Y1 ve Y2'de insan N/A'sı paydadan dışlanır. Her κ ile ham uyum ve PABAK birlikte verilir.
- `coder_subset_analysis.py`: A26 sarmalayıcısı (A29-3, A29-5). Tahminler donmuş `analyze(c1, c1, c1)` ile, yani kodlayıcı-1 tek etiket seti olarak hesaplanır. κ, katı/gevşek farkları ve Jev kapısı 80'lik örtüşmede hesaplanır. Kapı sonucu `jev.coded.gate`'e yazılır; donmuş `jev --scale-out` onu okur.
- `g1_reachable_subset.py`: B3 duyarlılığı; donmuş `compute_gfs.analyze_one_model` 30 soruda.
- `export_coder1_csv.py`: yukarıdaki kodlayıcı-1 dönüşümü.

| dosya | sha256 (LF) |
|---|---|
| `experiments/gfp_benchmark/a22_audit_analysis.py` | `cb7f845070c6c9c93d8832af2fdd9b6fdf977b3fc3568f24a634ae71185f0cb8` |
| `experiments/gfp_benchmark/coder_subset_analysis.py` | `817ad12bfca8494589c8d5ff38948434d0be3614033b4a6c4012ea28c6252682` |
| `experiments/gfp_benchmark/g1_reachable_subset.py` | `d0df19f461bc1f6bd3e5b67cc3990805ae7db6aa12c89fe2f36f6f739b735f1a` |
| `experiments/gfp_benchmark/export_coder1_csv.py` | `affe1ae2977d199d69c3de828881445c600153e04de96c2f5695094909a61e1e` |
| `experiments/gfp_benchmark/scale_assertion_analysis.py` (A26, değişmedi) | `e137905a5df499678b98c16870a0b65510377aaf0b2181959815eb0b322107cc` |
| `experiments/gfp_benchmark/compute_gfs.py` (değişmedi) | `bc730e5404326b01730a86af9b57570fcdb97184799e13e01a84d45ab7f8015d` |

**Sıra.** (1) Bu Beyan commit edilir. (2) Kodlayıcı dosyaları hash'lenip commit edilir; körleme biter. (3) Analizler koşulur.

### Beyan (2026-11-05) — G1-MT koşu-öncesi: koşucu ve analiz betiği dondu [PRE-RUN; A28-1 uyarınca; G1-MT koşusu başlamadı]

**Dosyalar.**
- `run_multiturn.py`: A28-1'i uygular. Kol yapılandırması, referans graflar, ortam/digest denetimi, ısınma, MAX_ATTEMPTS ve EXCL_LIMIT için `run_benchmark` ve `run_g1_rerun` yardımcıları değiştirilmeden kullanılır. Kayıt konuşma başına tutulur ve `turns[0..1]` alanını içerir. Turlardan biri fallback/error ise konuşma dışlanır. Digest G1'den farklıysa koşul yeni digest'le koşulur ve `mt_log.jsonl`'a `digest_differs_from_G1` olarak yazılır.
- `multiturn_analysis.py`: `validate` (A28-3/A29-4 vekil doğrulaması; A22-2 seçimi seed 42 ile birebir yeniden üretilir ve soru metniyle assert'lidir) ve `analyze` (H_MT1, H_MT2, clear-17 duyarlılığı, ikincil (a)–(e)) komutlarını içerir.

**Uygulama ayrıntıları** (A28'de açık bırakılan noktalar, koşudan önce sabitlendi):
- (b)'deki "tur 2'de araç çağrıldı mı" bilgisi turun kendi `provenance.tool_trace` alanından okunur. Kümülatif `tools_used` kullanılmaz, çünkü önceki turların kayıtlarını da içerir.
- (d) tur-1 `tool_trace` alanından hesaplanır.
- (e) tur-2 guard raporundaki SCALE_VIOLATION sayısıdır.

**Duman testi.**
- Kapsam: gemma4:e4b, TR, 3 soru (sta-02, dis-03, res-11) × 3 kol × 1 tekrar; `results/oct_v42_mt_smoke/`.
- Sonuç: 9/9 konuşma iki turla tamamlandı; konuşma başına 20–40 s.
- Kod doğrulaması için bu konuşmaların guard raporları ve TU değerleri incelendi. Bu çıktılar G1-MT verisi **değildir**; analize girmez ve kod bu incelemeden sonra değiştirilmedi.
- İnceleme öncesindeki tek değişiklik: bu Beyan'daki hash'lerin alındığı sürümde duman-testi parametreleri (`qids`, `arms`, `repeats`) eklendi; koşu bunların varsayılanlarıyla yapılır.

**GPU.** RTX 3090 (local host) boş doğrulandı (nvidia-smi: %0, 1 MiB; Ollama'da yüklü model yok). Aynı makineyi kullanan mmWave oturumu GPU'yu bıraktığını ve Ollama'yı kullanmadığını yazılı bildirdi.

**Sıra.** G1 analizleri bittikten sonra `GFP_RUN_DIR=oct_v42_mt python -m experiments.gfp_benchmark.run_multiturn` çalıştırılır.

| dosya | sha256 (LF) |
|---|---|
| `experiments/gfp_benchmark/run_multiturn.py` | `a93aa93f7dad2026d9cef98c3fea428c2333a719523256d83d9cfb253cda9747` |
| `experiments/gfp_benchmark/multiturn_analysis.py` | `b1088bea8888dd81ff7dcabd2364e43932bc4ccdb798bd4221f79e0c81487da8` |

### Beyan (2026-11-05) — Koşu-sonrası hata düzeltmesi: `crosslingual_stats.py` koşulmamış koşulda çöküyordu [POST-OUTCOME sapma; hesap değişmez]

Ön-kayıtlı analizler G1 körlemesi bittikten sonra çalıştırıldı. `crosslingual_stats.py` (prereg-v3.3, sha `840fad00…`), koşul listesini `FILE_GLOBS`'tan türetiyor; bu liste glm-4.7-flash'ı da içeriyor. Ancak GLM koşulu Ekim'de "not run" durumunda: iki deneme de iptal edildi (`aborted_raw_g1_glm-4.7-flash-latest_*`), tamamlanmış dosya yok. Bu yüzden hücreleri boştu ve betik `statistics.mean([])` çağrısında çöktü.

**Düzeltme:** Hücresi boş modeller iki model listesinden çıkarılır ve "not run" olarak yazdırılır. Verisi olan modellerin hesabı değişmez; değişen tek satır, model listesinin süzülmesidir. Yeni sha256 (LF): `2e7cec32338d08b04f220eccaf37caba6fdb26abac69436cebbf8db2d53f2aff`.

### A30 (2026-11-05) — EVREN: büyük uzak modelle keşifsel ölçek denetimi (deepseek-v4.1-flash; G1 + G1-MT, TR) [EXPLORATORY; G1 için POST-OUTCOME (Ekim G1 analizleri 07bc958'de koşuldu); A30 için PRE-RUN; Ekim G1-MT sonuçları görülmedi; danışman görüşü + kullanıcı kararı; prereg-v3.6]

**Gerekçe.** Ekim model kümesi 4–30 milyar parametreli, yerelde koşan modellerden oluşur. Bulguların yalnız küçük modellere özgü olup olmadığını görmek için aynı boru hattı çok daha büyük bir uzak modelle koşulur. Bu amendment, Ekim G1 sonuçları bilinirken yazıldı; bu yüzden keşifseldir. Doğrulayıcı hipotez yoktur. G1 ve G1-MT'nin hipotezleri, analizleri ve sonuçları değişmez. Sonuç-koşulsuz raporlanır.

**A30-1 Servis ve model.**
- Servis: EVREN LLM API (endpoint not published), OpenAI-uyumlu, yurt içi H200 kümesi. 1 Aralık 2026'ya kadar ücretsiz; günlük 15M token. Kullanım şartları v1 kullanıcı tarafından kabul edildi; şartlarda sonuç yayımlamayı ya da karşılaştırmalı değerlendirmeyi kısıtlayan madde yok.
- Model: `deepseek-v4.1-flash` (sunulan ad `deepseek/deepseek-v4.1-flash`; ~763B toplam, ~16B aktif MoE).
- Duman testinde elenenler (sayılarıyla, raporda verilir):
  - `glm-5.3`: 11 dakikada 19 kez 503 `model_capacity_exhausted`; sunulduğunda yaklaşık 1–2 token/s. Konuşma ortasındaki `system` adımı kapasite yüzünden hiç tamamlanamadı.
  - `qwen3.8-flash-next`: konuşma ortasındaki `system` mesajını HTTP 400 ("System message must be at the beginning") ile reddediyor. Guard kolunun düzeltme adımı her blokta hataya düşerdi. Mesajın rolünü değiştirmek guard kolunun davranışını değiştireceği için bu model alınmadı.
  - `mimo-v2.6-pro` denenmedi.
- Sürüm sabitlenemez; digest yoktur. Kimlik olarak model kartının SHA-256'sı kullanılır; `created` alanı hariç tutulur, çünkü sunucu bu alanı her istekte değiştiriyor. Şartlar sürümü ayrı bir alanda kaydedilir ama kimliğe girmez: kozmetik bir şart güncellemesi sapma sayılmaz, esaslı bir güncelleme ise zaten her çağrıyı 403 ile durdurur. Kimlik koşul başında alınır. Koşul içinde değişirse G1'deki gibi koşul iptal edilir ve baştan koşulur.
- Sunucuya ulaşılamaması model değişimi sayılmaz. Kimlik sorguları, kapasite kuralındaki gibi en çok 30 dakika beklenerek yeniden denenir; ancak bundan sonra kimlik "alınamadı" olur.
- Ücretsiz dönem bittikten sonra yeniden üretilebilirlik sınırlıdır; makalede beyan edilir.
- **Hassasiyet karışıklığı:** Yerel modeller Ollama'nın nicemlenmiş (GGUF) sürümleridir. deepseek ise sağlayıcının sunduğu hassasiyette çalışır; kart hassasiyet belirtmiyor. Bu yüzden "ölçek" karşılaştırması hassasiyetle karışıktır; makalede böyle yazılır.

**A30-2 G1 ve A28 ile aynı olanlar.**
- G1: 56 soru × 3 kol × 3 tekrar. G1-MT: 21 soru × 3 kol × 3 tekrar × 2 tur (A28-1). Dil TR.
- Seed 10000+r, sıcaklık 0.3. Sistem promptu, araç şemaları, guard v4.2 ve referans graflar aynıdır.
- EXCL_LIMIT 0.10, MAX_ATTEMPTS 2. G1'den sonra 5 hücrelik determinizm denetimi (`DET_QIDS`).
- Sürücüler `run_benchmark.run` ve `run_multiturn.run_mt` değiştirilmeden çağrılır. `app/` değişmez (`git diff prereg-v3.5 -- app/` boş).

**A30-3 Farklar (taşıma; beyan edilir).**
- **Taşıma:** Ayrı bir süreçte `OllamaOrchestrator._call_ollama` EVREN `/v1/chat/completions` çağrısıyla değiştirilir. Koşan Ekim G1-MT'si etkilenmez. Ayrıntılar:
  - araç mesajlarına `tool_call_id`, önceki asistan mesajındaki çağrılarla sırayla eşlenir;
  - `content: null` boş metne çevrilir;
  - düşünme metni (`reasoning`) teslim metnine girmez. Yerelde de girmiyordu: Ekim ham G1 yanıtlarının hiçbirinde `<think>` yok;
  - `ungrounded` kolda `tools` alanı hiç gönderilmez (yerelde boş liste gönderiliyordu).
- **Düşünme:** sağlayıcı varsayılanı; `thinking` parametresi gönderilmez. Yerelde de `think` gönderilmedi ve 5 modelin 4'ü düşünme yetenekli. `max_tokens` gönderilmez (model varsayılanı 65536). `finish_reason=length` fallback sayılır.
- **Örnekleme:** Yalnız sıcaklık (0.3) ve seed sabitlenir; yerelde de böyleydi. top_p, top_k ve tekrar cezaları sağlayıcının varsayılanlarıdır; bunlar Ollama'nınkilerle aynı olmayabilir.
- **Zaman aşımı:** çağrı başına 600 s (yerelde 60 s). Duman testinde en uzun çağrı 237 s sürdü.
- **Kapasite:**
  - Üretim başlamadan reddedilen istekler yeniden gönderilir: 503, 429 eşzamanlılık/hız ve bağlantı kurulamaması. `Retry-After` kadar beklenir, çağrı başına en çok 30 dakika. Bu satırlar dışlanmaz, çünkü model henüz bir şey üretmemiştir; seed ve sıcaklık değişmez.
  - Günlük kota dolarsa sıfırlanmaya kadar beklenir (en çok 2 kez).
  - Üretim sırasında kopan istekler yeniden denenmez; G1'deki zaman aşımı gibi fallback'e, yani dışlamaya gider. Bunlar okuma zaman aşımı, 500/502/504 ve diğer 4xx'tir.
- **Isınma yok:** sunucu uzakta.
- **Seed tekrar üretmez:** Duman testinde aynı istek aynı seed'le farklı çıktı verdi; bu üç modelde de görüldü. Determinizm denetimi bunu ölçer. Tekrarlar bağımsız örnekler gibi okunur.
- **Sıralı koşu:** tek istek, paralellik yok.
- **Oturum önekleri:** G1 `a30`, determinizm `a30det`. G1-MT'de `run_mt`'nin sabit `mt-` öneki kullanılır, Ekim G1-MT'siyle aynı Redis anahtarları. Bu yüzden A30 G1-MT'si Ekim G1-MT'si bittikten sonra koşulur.
- Her çağrı `a30_calls.jsonl`'a yazılır: sunulan model adı, token kullanımı, `finish_reason`, kapasite beklemeleri.

**A30-4 Analiz (betimsel; `a30_analysis.py`).**
- `compute_gfs.analyze_one_model`, 56 sorunun tümünde.
- Donmuş ikincil analizler, ortak `FILE_GLOBS` tek EVREN koşuluna indirgenerek çalıştırılır: `rescore_crosslingual`, `intervention_paths`, `trap_analysis`, `g1_reachable_subset`. Çıktılar `oct_v42_evren/` altına yazılır.
- G1-MT için donmuş `multiturn_analysis.analyze` (vekil doğrulaması Ekim'den okunur).
- Determinizm: 5 hücre, ana koşunun aynı seed'li `grounded_noguard` satırlarıyla karşılaştırılır; birebir aynı teslim metni sayısı ve referans-GFS.
- Çağrı telemetrisi.
- Raporlanacak başlıca sayılar (önceden seçildi):
  - kol başına referans-GFS;
  - guard kolunda müdahale-yolu payları (özellikle P3, araçsız blok) ve araç çağırma oranı;
  - tuzak sorularında SCALE_VIOLATION;
  - G1-MT'de TU tabloları ile H_MT1/H_MT2 farkları.
- p-değerleri betimseldir. Yerel modellerle karşılaştırma yalnız yan yana tablodur; havuzlanmaz ve test edilmez.

**A30-5 Sıra ve zamanlama.**
1. Bu amendment commit edilir ve `prereg-v3.6` etiketi atılır.
2. Ekim G1-MT'si bittikten sonra (`end` olayı; simülasyon motoru ve Redis ortaktır) önce `a30_analysis` kuru çalıştırılır (A30-6). Ardından `GFP_RUN_DIR=oct_v42_evren python -m experiments.gfp_benchmark.run_a30_evren run` çalıştırılır. Sıra: G1, determinizm, G1-MT.
3. Bittikten sonra `a30_analysis` çalıştırılır.

Makale gönderiminden önce tamamlanırsa sonucu ne olursa olsun raporlanır; tamamlanmazsa "not run" yazılır.

**A30-6 Duman testi.** Yalnız taşıma denendi (`results/oct_v42_evren_smoke/`):
- gerçek soru metni (res-01) ve sahte araç sonucu (`smoke_fake`) kullanıldı; simülasyon motoru çağrılmadı;
- adımlar: araç gidiş-dönüşü, konuşma ortasında `system` mesajı, araçsız çağrı, seed tekrarı.

Bu çıktılar veri değildir ve analize girmez. Taşıma kodundaki değişikliklerin bir kısmı (kapasite kuralı, model listesi, zaman aşımı) duman testinden sonra yapıldı ve tek bir gerçek çağrıyla yeniden denendi. Kimlik sorgusunun yeniden deneme kuralı ise yalnız derleme kontrolünden geçti.

**Analiz betiğinin testi.** `a30_analysis.py` şimdilik yalnız derleme kontrolünden geçti. Kuru çalıştırma şimdi yapılamıyor, çünkü `intervention_paths` ve `trap_analysis` referans grafları kurarken simülasyon motorunu çağırıyor. Plan:
- Ekim G1-MT'si bittikten sonra ve A30 koşusundan önce, bir Ekim `raw_g1` dosyası EVREN dosya adıyla ayrı bir deneme dizinine kopyalanır ve betik orada çalıştırılır.
- `analyze_one_model` satırları model adına göre süzmüyor; kopyadaki `model` alanının değiştirilmesi gerekmez.
- Bu denemede bir düzeltme gerekirse koşudan önce, yeni hash'le bir Beyan yazılır.

| dosya | sha256 (LF) |
|---|---|
| `experiments/gfp_benchmark/run_a30_evren.py` | `9135c6c56770f9178fe0d1c1cbc86aebc359913be20fb294efdeb54228c35d03` |
| `experiments/gfp_benchmark/a30_analysis.py` | `927b01b1786f9f5b37492df6a9ccb756ac277a3732af7a5f53cf83b6469ea359` |
| `experiments/gfp_benchmark/run_benchmark.py` (değişmedi) | `53c508231e0b657ccf7c4f52761200be8c4a0171b3591a8a3ff7cd80e6bc5b08` |
| `experiments/gfp_benchmark/run_g1_rerun.py` (değişmedi) | `da13124781a5e34328ee95cf32667443ee7389cfa4be13deb00c7ba7693b9389` |
| `experiments/gfp_benchmark/run_multiturn.py` (değişmedi) | `a93aa93f7dad2026d9cef98c3fea428c2333a719523256d83d9cfb253cda9747` |
| `experiments/gfp_benchmark/multiturn_analysis.py` (değişmedi) | `b1088bea8888dd81ff7dcabd2364e43932bc4ccdb798bd4221f79e0c81487da8` |
| `experiments/gfp_benchmark/compute_gfs.py` (değişmedi) | `bc730e5404326b01730a86af9b57570fcdb97184799e13e01a84d45ab7f8015d` |
| `experiments/gfp_benchmark/rescore_crosslingual.py` (değişmedi) | `d1cbe7747a56e0e79f3de8d06f15ef21e8760cfebe6ad4d06523910dfff897b1` |
| `experiments/gfp_benchmark/intervention_paths.py` (değişmedi) | `000a07eece101858664d2a9cc8a84e3ea5a3f512acf652509bb5a6769f6ae713` |
| `experiments/gfp_benchmark/trap_analysis.py` (değişmedi) | `f4823546094c19b55eb8606b4ef80f9b1a0b2e1264ce5dfd25376e214fd24976` |
| `experiments/gfp_benchmark/g1_reachable_subset.py` (değişmedi) | `d0df19f461bc1f6bd3e5b67cc3990805ae7db6aa12c89fe2f36f6f739b735f1a` |
| `app/llm/ollama_orchestrator.py` (değişmedi) | `283ccfe725bf45d34498cfa0acd2eeab76c0e553bcd3bc2e422f1a388296b94e` |
| `app/llm/provenance_guard.py` (değişmedi) | `a050b46ab5d8fa392215a1df47162c311daae95118d2bfa311d31e84a729f7c2` |

Diğer bütün analizler donmuş haliyle hatasız çalıştı (`results/oct_v42/analysis/*.out`).

### Beyan (2026-11-05) — Sonuç-sonrası dört düzeltme: E4(ii) karşılaştırması, taksonomi glob'u, kural önceliği, A26 Jev sürümü [POST-OUTCOME; Ekim G1 analizleri 07bc958'de görüldü; danışman v2.23.0/v2.23.3; hiçbir test, eşik ya da dışlama kuralı değişmez]

**(a) E4(ii) determinizm karşılaştırması — ödenmemiş ön-taahhüt.** A21(h)(ii) her koşul bitince beş sabit hücrenin (res-01, com-01, dis-01, sta-01, res-11; seed 10000; grounded_noguard) ayrı bir dosyaya yeniden koşulmasını ve özdeşliğinin raporlanmasını öngördü. Dosyalar altı koşulda da var (`results/oct_v42/determinism_check_*.jsonl`), ama onları ana koşuyla karşılaştıran donmuş bir betik yoktu. Yeni `determinism_identity.py` yalnız bu karşılaştırmayı yapar:
- Her determinizm hücresinin metni, ana koşunun aynı soru, grounded_noguard, tekrar 0 (seed 10000) satırıyla karşılaştırılır.
- Metrik E4(i) ile aynıdır: tam eşitlik ve SequenceMatcher ≥ 0.95. Metin seçimi `guard_coverage.py` ile aynıdır (`pre_intervention.reply`, yoksa `reply`).
- Fallback ya da hata taşıyan hücre "excluded" sayılır. LLM ya da simülatör çağrısı yok; yalnız iz okur.

Hesap Ekim G1 sonuçları bilindikten sonra yapılır; karşılaştırma A21(h)(ii)'de tarif edildiği gibidir. Betik çalıştırılmadan önce yalnız sahte bir kopyayla mantık testinden geçti: ana koşu satırlarından kurulan beş hücrenin biri değiştirildi, beklenen 4/5 çıktı. Test dizini silindi.

**(b) Taksonomi betiği A24'te güncellenmemişti.** `analyze_guard_flag_taxonomy.py` (sha `761dc9f3…`, prereg-v3.0'dan beri değişmedi) Model B'yi `raw_g1_qwen3.5-27b_2026*` glob'uyla arıyordu. A24 Model B'yi qwen3.8'e çevirdi ve kapsamına taksonomiyi açıkça aldı ("yalnız G1 (→ G1/G2/taksonomi/…)"); ancak `rescore_crosslingual`, `crosslingual_stats` ve `run_g1_rerun` güncellenirken bu betik atlandı. Sonuç: Ekim taksonomisi (`analysis/taxonomy.out`) sessizce yalnız Model A-TR'yi kapsadı.
- **Düzeltme:** glob listesine yalnız `raw_g1_qwen3.8-27b_2026*T*.jsonl` eklenir. Temmuz dizininde qwen3.8, Ekim dizininde qwen3.5 hiçbir dosyayla eşleşmez. Sınıflandırma kodu değişmez (diff yalnız glob satırı ve iki yorum satırı).
- **Kapsam:** Temmuz tasarımındaki gibi TR A+B. EN, Mistral ve Muse'a genişletilmez; bu, sonuç-sonrası kapsam büyütmesi olurdu.
- **Regresyon:** düzeltilmiş betik, yalnız A-TR dosyasını içeren bir deneme dizininde koşulur ve çıktısı `analysis/taxonomy.out` ile bayt-özdeş olmalıdır. Sayımlar toplamsal olduğu için birleşik A+B çıktısından B-TR sayımı çıkarma ile elde edilir.
- B-TR taksonomi çıktısı bu düzeltmeden önce görülmedi. `tolerance_sensitivity.py taxonomy`, `tax.run()`'ı çağırdığı için aynı düzeltmeyle yeniden koşulur.
- **Başka kaçak var mı:** analiz betiklerinde `qwen3.5` geçen yerler tarandı.
  - `rescore_crosslingual.py` ve `crosslingual_stats.py`: yalnız Temmuz glob'u ya da yorum; Ekim kümesi ayrı.
  - `run_g4_final.py`: G4, tasarım gereği Temmuz korpusu.
  - `make_a8_*`: A8 geri çekildi, hiç koşulmadı.
  - `a9_counterfactual.py` (A10, keşifsel): glob'u Temmuz tarihine bağlı (`2026070*`), bu yüzden A21-E7'nin "Ekim'de aynı script'le yeniden koşulur" taahhüdü bu betikle yerine getirilemez. A10 makalede yer almıyor ve sorusu (blok altkümesinde ilk taslak ile teslim metni) A22-1 müdahale-yolu ayrıştırmasıyla ön-kayıtlı olarak cevaplanıyor. A10 Ekim'de koşulmaz ve "not re-run, superseded by A22-1" olarak beyan edilir.

**(c) Kural önceliği ve düşen iki öncül.** Ekim verisinde aynı seed'le guard ve noguard ilk taslakları her koşulda yalnız %3–85 oranında bayt-özdeştir (`guard_coverage.json` → `a21_pre_identity`). Özdeş olmayan çiftler 0.95 benzerlik eşiğini de geçemez, yani baştan ayrışmış bağımsız örneklerdir. Bu iki ön-kayıtlı öncülü düşürür:
- A22-4(a)'nın "identical by construction" şablonu.
- A22-1'in "P0'ın Δ'ya katkısı tanım gereği 0'dır" ifadesi. Ekim'de P0 Δ = +0.009…+0.055.

İfade kuralları çeliştiğinde sonraki ve daha özgül kural yönetir. A21(h)'nin "≈%100 değilse 'essentially unchanged' kalır" yedeği uygulanmaz; A22-4(e) (prereg-v3.1, veri görülmeden) geçerlidir: "essentially unchanged" hiçbir yerde ampirik bulgu olarak yazılmaz. Makale şunları açıkça söyler:
- "Identical by construction" yalnız guard'ın mimarisi için doğrudur; örnekler için doğru değildir.
- Ön-müdahale karşılaştırması kollar arası bir değişebilirlik kontrolüdür.
- A22-4(c) ayrıştırması üç terimle verilir: P2, P1a ve P0. P0 terimi kollar arası örnekleme gürültüsünün tabanıdır.

Gürültüden arındırılmış yeni bir tahmin edici kurulmaz; hiçbir sayı ve test değişmez.

**(d) A26 Jev ölçeklendirmesi başka bir model sürümüyle koştu; etiket yanlış.** `a26_results.json` iki şey gösteriyor:
- Kapı (κ = 0.66, `multi`, strict-AND, A29 örtüşmesi n = 80) `jev-1.13.0` etiketleriyle hesaplandı. Ölçeklendirme çağrılarının hepsini ise `jev-1.14.0` yanıtladı (`models_seen`). Sürüm, sağlayıcı tarafında kapı ile ölçeklendirme arasında değişti. A26 yalnız "görülen model loglanır" diyordu; bu durum için kural yoktu.
- Çıktıdaki etiket "human-validated on n=263 trap sentences (kappa=0.6603)" yanlıştır: κ 80 cümlelik örtüşmede hesaplandı. 263 cümlede kodlayıcı-1'e karşı `multi` κ'sı 0.57'dir (bilgi amaçlı, kapı değil).

Karar: ölçeklendirme sonuçları (8 937 cümle; tuzak-dışında ve kalan tuzak cümlelerinde 0 restatement adayı) makalede yalnız betimsel verilir ve kapının doğrulamadığı sürümle üretildiği yazılır. Ölçeklendirme yeniden koşulmaz. Sonuç dosyası değiştirilmez; düzeltme bu kayıttadır.

| dosya | sha256 (LF) |
|---|---|
| `experiments/gfp_benchmark/determinism_identity.py` (yeni) | `cc2a5daadfd6b1e7d3dd3cbac98fc96151e013bc07e355f96426568d2e30210b` |
| `experiments/gfp_benchmark/analyze_guard_flag_taxonomy.py` (`761dc9f3…` → glob düzeltmesi) | `e7fde016c903764ecde6d3cdea274fbcfa3a1d8a08679b90503c58b5e4013196` |

Betikler repoya G1-MT koşusu bittikten sonra konur ve bu kayıtla aynı commit'e alınır; koşu sırasında `/app` altında `.py` düzenlenmez. (b)'nin taksonomi koşuları referans grafları için simülasyon motorunu çağırdığından, G1-MT bittikten sonra ve A30 koşusundan önce yapılır.

### Beyan (2026-11-06) — A30'un ilk G1 denemesi ana makine kapanınca kesildi; koşu baştan yapılır [KOŞU-İÇİ; hiçbir A30 sonucu incelenmedi]

A30 koşusu 2026-11-05 21:13 UTC'de başladı (`prereg-v3.6`; analiz betiği kuru çalıştırmada düzeltme gerektirmedi). 2026-11-06 06:40 UTC civarında ana makine kapandı ve Docker ile birlikte koşu süreci durdu. O anda G1 ham dosyasında 504 satırın 291'i vardı: guard 168, noguard r0–r1 112, noguard r2 11.
- Koşucuda kaldığı yerden devam etme mantığı yok. A30-2 sürücülerin (`run_benchmark.run`, `run_multiturn.run_mt`) değiştirilmeden çağrılmasını şart koşuyor ve kesinti için kural yoktu. G1'de bir koşul iptal edildiğinde uygulanan kural (koşul baştan koşulur) uygulanır.
- Kesik ham dosya `aborted_` önekiyle arşivlenir ve analize girmez. Bu denemenin çağrı telemetrisi (`a30_calls.jsonl`: 863 çağrı, 3.93M token) ve `run.log` `aborted_attempt1_` önekiyle ayrılır; A30-4 telemetrisi yalnız geçerli denemeyi sayar. `a30_log.jsonl` olduğu gibi kalır; yeni deneme ona eklenir.
- Koşu aynı komutla baştan başlatılır. Kimlik koşul başında yeniden alınır.
- Kesik dosyadan yalnız satır sayısı, kol/tekrar dağılımı ve fallback/hata sayısı (0) okundu. Teslim metinleri, GFS ve yol payları incelenmedi.
- Kesinti MAX_ATTEMPTS sayımına girmez; o kural dışlama oranı ve kimlik sapması içindir.
- Makalede şöyle beyan edilir: ilk deneme ana makine kapanınca 291/504 satırda kesildi, analiz edilmeden arşivlendi ve koşu baştan yapıldı.

### Beyan (2026-11-10) — A30 sonuç klasöründe Seafile çakışma kopyaları [KOŞU-SONRASI; veri değişmedi]

A30 2026-11-07 22:02 UTC'de bitti (`end` olayı). 2026-11-08'de Seafile eşitleme istemcisi sonuç klasöründe beş `(SFConflict …)` kopyası üretti.
- `a30_calls`, `a30_log`, `raw_g1_deepseek-v4.1-flash_20261106T091533Z` ve `run.log` kopyaları asıl dosyalarla bayt-özdeştir (sha256 aynı).
- `a30_calls (… 2026-11-08-13-45-45)` kopyası, asıl `a30_calls.jsonl`'ın ilk 526 satırıyla bayt-özdeştir. Koşu sürerken alınmış eski bir anlık görüntüdür.
- Asıl dosyalar eksiksizdir: G1 504, G1-MT 189 ve determinizm 5 satır. Satır sayıları `condition_done` olaylarıyla aynıdır ve her satır JSON olarak okunur.
- Kopyalar silinmedi. Bir glob'un onları seçmesini önlemek için `_seafile_conflicts/` altına taşındılar ve commit'lenmediler.
- `a30_analysis` bu taşımadan sonra koşuldu; donmuş betik hash'leri doğrulandı. Yetkili kopyalar commit `d159c16`'daki dosyalardır.
- Danışman v2.23.9 gereği makalede anılmaz; veri erişilebilirliği bölümünde "commit'lenen dosyalar yetkili kopyalardır" demek yeterlidir.


### Beyan (2026-11-14) — Donmuş guard'da iki eşleştirici kusuru ve raporlanmamış bilinen bir davranış; keşifsel duyarlılık analizi koşulmadan önce dondu [POST-OUTCOME; guard ve orkestratör hash'leri değişmez; hiçbir test, eşik ya da dışlama kuralı değişmez; yeniden koşu yok; danışman v2.25]

**Ne bulundu.** Platform makalesi oturumu kendi senaryo koşusunda (`scn_freeze_v1`) donmuş guard'da iki kusur buldu. İkisi de GFP izlerinde kod okuyarak ve kaba taramayla doğrulandı.
- **(1) İşaret.** `_NUM_RE` sayının eksi işaretini yakalamaz; kayıtlar ise işaretli tutulur. Doğru aktarılmış her negatif değer (çoğunlukla negatif NPV) bu yüzden UNGROUNDED olur; buna guard'ın kendi `safe_summary` yedeği de dahildir. Ters yönde bir açık da var: "−X", +X kaydıyla büyüklük üzerinden eşleşir ve GROUNDED olur. Garanti yalnız büyüklük içindir.
- **(2) Ondalık.** 1–3 basamaklı tam kısım, tek ayraç ve ≥4 ondalık basamaklı bir sayı bölünür: "1.1015" → "1.101" + artık "5".
- **(3) Biliniyordu, dondurulmuştu, ama raporlanmadı.** `safe_summary` yalnız son araç sonucunun üst düzeyindeki sekiz alanı okur (A10; A28 "Değişmeyen kod"; MULTITURN_DESIGN §7). Yeni olan iki şey var: bu davranış makalede raporlanmadı, ve teslim edilen özet teslimden önce kapı olarak denetlenmiyor (`ollama_orchestrator.py:474-475`).
- Birincil sonuçlar donmuş eşleştiricinin sonuçlarıdır ve öyle kalır. Guard ve orkestratör düzeltilmez, yeniden koşu yapılmaz (danışman v2.25).

**Betik görülmeden önce görülenler.** Danışman v2.25 girişindeki ön sayımlar grep ya da kaba tarama düzeyindedir, analiz değildir:
- teslim edilen özetin kendi denetiminden geçmemesi: G1'de 18, A30'da 3;
- boş özet: `oct_v42`'de 204, G1-MT'de 165, A30 G1'de 79;
- eksi-önekli iddialar, kol ve hüküm başına.

Betik dört şeyle denendi:
- Sabit test cümleleri ve sentetik bir iz (`check`): öz-test ve fixture testi.
- Analize girmeyen deneme izleri: `smoke_v42` ve `oct_v42_mt_smoke`. G1-MT denemesi kapıdan 18/18 geçti. `smoke_v42` 9 izin 6'sında referans kapısından kaldı; bu iz TMY önbelleğinden (A23) önce alınmıştır, ama neden ayrıca doğrulanmadı. Test dizini silindi.
- S1/S6/S7 aşamaları, yalnız çökmeden bittiklerini görmek için çalıştırıldı; çıktıları açılmadan silindi.
- **Yalnız donmuş eşleştiriciyle gerçek veride kuru çalıştırma** (`SENS_VARIANTS=frozen`, `SENS_DRYRUN=1`): kapı oranları ve donmuş kopyadan S3 analizlerinin makaledeki çıktılarla karşılaştırması. Bu çalıştırma yalnız donmuş-ile-saklı karşılaştırmasıdır; makalede zaten olan sayıları yeniden üretir. S2/S4/S5 hesaplandı ama yazılmadı. Sonuçlar:
  - **Kapı:** 14 dosyanın hepsinde ve her üç aşamada kapı kaybı 0. Donmuş eşleştirici saklı her sayımı birebir üretti; hiçbir iz çıkarılmadı.
  - **S3:** donmuş kopyadan çıkan her çıktı, makalenin kullandığı çıktıyla (yol adları dışında) bayt bayt aynı: yedi `gfs_*.out` (TR çekirdek havuzu dahil), `paths.out`, `rescore.out`, `mt_analysis.out`, `a30_analysis.out`, `intervention_paths.json`, `crosslingual_{rescore,cells,stats}.json`, `mt_results.json`, ve A30'un `a30_gfs`, `a30_results`, `trap_analysis` ve `g1_reachable_subset` dosyaları.
  - Taksonomi çıktısı düzeltilmiş A+B sürümüyle (`taxonomy_AB.out`, Beyan 2026-11-05 (b)) aynıdır.
  - Asıl sonuç dosyalarına yazılmadı.
  - Kuru çalıştırmanın ara kopyaları silindi; `results/sens_v225_dryrun/` altında yalnız `gate.json` ve donmuş analiz çıktıları kaldı.

Hiçbir varyantın sonucu görülmedi.

**Betik ve kurallar** (bu nottan sonra, çıktı görülmeden sabittir):
- `experiments/gfp_benchmark/sens_v225.py`. LLM çağırmaz. Guard'ın canlı kararlarına (blok, yeniden deneme, teslim metni) dokunmaz; yalnız saklı metinleri yeniden puanlar. `app/` altında hiçbir dosyayı değiştirmez; varyantları bellekte kurar.
- **İşaret kuralı:** `claim_sign`. Kaynağı `experiments/gfp_benchmark/sens_v225_v5.py`, platformun `provenance_guard_v5.py` dosyasının (platform/ems 9c5de68) bayt-özdeş kopyası; aynı hash'i taşır. İki makale tek kuralı kullanır. Kural:
  - eksi (`-`, `−`, `–`) yalnız sayının hemen önündeyse sayılır; arada ₺, $, TL, `*` ya da `**` olabilir;
  - harf, rakam, `%` ya da `.` sonrasındaki tire ve aralıklar ("5-10", "%8 - %12", "12:00 - 16:00") pozitif kalır;
  - arkasında boşluk olan liste tiresi ("- 25 yıllık") pozitif kalır;
  - işaretli iddia yalnız aynı işaretli kayıtla eşleşir; işaretsiz iddia negatif kayıtla hiç eşleşmez. Yazıyla anlatılan negatif ("588.032 TL zarar") eşleşmeden kalır; bu, fail-closed tercihtir.
- **Ondalık kuralı:** `_NUM_RE`'nin `num` grubuna en önce denenen tek bir seçenek eklenir: `\d{1,3}[.,]\d{4,}(?![.,]?\d)`. Tek ayraçlı, 1–3 basamak tam kısımlı ve ≥4 basamak kesirli belirteç tek sayı olarak okunur. `_candidate_values` değişmez. Binlik grubu ve ≥4 ondalığı birlikte taşıyan sayı ("1,234.5678") bu kuralın kapsamı dışındadır ve donmuş bölünmeyi korur.
- **Varyantlar:** `frozen`, `sign`, `decimal` ve `both`.

**Aşamalar** (sıra bağlayıcıdır):
- **S0 kapı.** Donmuş eşleştirici saklı sayımları her aşamada BİREBİR üretmelidir:
  - `reference_check.counts`: teslim metni ile referans grafı. Referans grafı koşu-zamanı kurucusuyla kurulur (`run_benchmark._reference_graph`).
  - `provenance.counts` ve `pre_intervention.counts`: teslim metni ve ilk taslak ile canlı graf. Canlı graf `tool_trace`'ten deterministik simülatörle yeniden kurulur. Canlı orkestratör gibi her çağrı eklenir, başarısız çağrının yalnız girdileri girer. G1-MT'de ikinci tur, oturumun saklı (üst sınırlı) kayıtlarıyla başlar.

  Referans kapısını geçmeyen iz bütün varyant kopyalarından çıkarılır. Bu, donmuş tabanı da değiştirir: varyant farkları basılı makale sayılarına değil, donmuş KOPYAYA göre okunur. Canlı-graf kapısını geçmeyen birimin saklı alanları bütün varyantlarda olduğu gibi kalır ve birim S2 (canlı), S4 ve S5'e girmez. Bütün kapı kayıpları sayılır ve raporlanır.
- **S1.** P3 ayrımı, yalnız saklı dizgilerden, guard kolunun bloklanan her biriminde. Üç hücre:
  - boş graf;
  - kayıt var ama özet boş. Bu hücre son çağrının araç adına ve `failed` bayrağına göre ayrılır; o birimde hiç çağrı yoksa (G1-MT ikinci tur: kayıtlar ilk turdan) ayrı bir hücreye girer;
  - sayılı özet.

  `oct_v42`, G1-MT turları ve A30 için.
- **S2.** Kusur sıklığı, kol × koşul × aşama (teslim/referans, teslim/canlı, ilk taslak/canlı):
  - puanlanan metinlerde eksi-önekli ve uzun-ondalıklı sayıların sayısı;
  - varyant başına hüküm toplamları, sayımı farklılaşan birimler, geçerken kalan ve kalırken geçen birimler;
  - `sign` için (belirteçleme değişmediğinden iddialar bire bir hizalanır) donmuş→sign hüküm çapraz tablosu.
- **S3.** Donmuş analiz betikleri değiştirilmeden, yamalı eşleştiriciyle varyant kopyaları üzerinde koşar: `compute_gfs` (altı koşul + TR çekirdek havuzu), `intervention_paths`, `rescore_crosslingual`, `crosslingual_stats`, `analyze_guard_flag_taxonomy`, `multiturn_analysis analyze`, `a30_analysis`. `frozen` kopyası makaledeki sayıları yeniden üretmelidir; üretmeyen her fark raporlanır.
- **S4.** Blok atfı, alt sınır olarak: guard kolunda yeniden denenmiş ve ilk taslağı varyant altında geçen yanıtlar. Bloklanan turlarda yeniden deneme metni saklanmadığı için yalnız alt sınırdır. Kendi denetiminden geçmeyen teslim özetleri tek tek listelenir.
- **S5.** Ters yöndeki açık: guard kolunun teslim metinlerinde donmuş eşleştiricinin GROUNDED dediği eksi-önekli iddialar, eşleştikleri canlı kaydın işaretiyle tek tek. İddianın metindeki yeri donmuş regex'le yeniden tarayarak bulunur; donmuş denetim her eşleşmeye tam bir iddia ekler.
- **S6.** A22 denetim sayılarından işaretli ya da ≥4 ondalıklı olanlar; eşleştirici hükmü ve kodlayıcı-1 etiketleriyle çapraz tablo. Yeni kodlama yok. Taksonomi S3'te varyantlarla yeniden koşar.
- **S7.** G4 korpusu (`raw_g4_final*`): kaynak ve mutasyon metinlerinde işaretli ve ≥4 ondalıklı sayılar.

**Eşik** (danışman v2.25). Aşağıdakilerden biri olursa etkilenen iddia ANA METİNDE yeniden yazılır:
- (i) ön-kayıtlı bir testte (H_G1b, H_G1a, E1, McNemar, H_MT1/2) Holm sonrası anlamlılık ya da yön değişir;
- (ii) herhangi bir koşulda McNemar'ın "yalnız no-guard temiz" hücresi 0'dan çıkar;
- (iii) Mistral'in ayrıştırılmış kazancının işareti döner;
- (iv) S4 alt sınırı herhangi bir koşulda blokların %10'unu geçer.

Hiçbir eşik yeniden koşu gerektirmez. Duyarlılık ekte durur. Düzeltilmiş guard'la canlı koşu ancak ayrı, ön-kayıtlı bir takip çalışması olabilir. "Conservative / guard aleyhine" ifadesi S3 görülmeden yazılmaz.

**Sapma kuralı.** Koşu sırasında kural, varyant, aşama ya da eşik değiştirmeyen bir altyapı hatası (dosya yolu, çökme) çıkarsa, düzeltme yeni hash'le bu kayda tarihli bir ek olarak yazılır ve aşama baştan koşulur. Sonuca bakarak hiçbir kural değiştirilmez.

**Çıktılar.**
- Özetler `results/sens_v225/` altına yazılır: `gate`, `s1`, `s2`, `s4`, `s5`, `s6` ve `s7` JSON dosyaları ile `analysis/<varyant>/*.out`.
- Ara kopyalar `results/sens_v225/_work/` altındadır. Yeniden puanlanmış izleri ve S3 işlerinin okuduğu dosyaların bir izin listesini taşırlar: `oct_v42/audit/tu_proxy_validation.json`, `oct_v42_evren/a30_calls.jsonl` ve `determinism_check_*`. Kodlayıcı dosyaları ve A22 körleme anahtarı kopyalanmaz. Yeniden üretilebilirler, analizden sonra silinebilirler ve commit'lenmezler.
- `.gitattributes`, hash'i dondurulan dört `.py` dosyasını LF'ye sabitler. Böylece `core.autocrlf=true` olan bir çalışma kopyasında da diskteki hash ön kayıtla aynı kalır.

| dosya | sha256 (LF) |
|---|---|
| `experiments/gfp_benchmark/sens_v225.py` (yeni; kuru çalıştırmayla aynı) | `47c30854e7df1fada74a1c7f95932f0466c5a27b230eec2c0c777293c47eb50b` |
| `experiments/gfp_benchmark/sens_v225_v5.py` (platform `provenance_guard_v5.py` 9c5de68 ile bayt-özdeş) | `a477e0eb8d6e5778390eb8a12acf8f818d136d2860bac23d007983b9f69867b1` |
| `app/llm/provenance_guard.py` (değişmedi) | `a050b46ab5d8fa392215a1df47162c311daae95118d2bfa311d31e84a729f7c2` |
| `app/llm/ollama_orchestrator.py` (değişmedi) | `283ccfe725bf45d34498cfa0acd2eeab76c0e553bcd3bc2e422f1a388296b94e` |
| `.gitattributes` (yeni; dört dosyayı LF'ye sabitler) | — |

### Sonuç notu (2026-11-14) — v2.25 eşleştirici duyarlılık analizi [POST-OUTCOME; `prereg-v3.8` sonrası koşuldu]

Bu not yalnız sonucu kaydeder; hiçbir test, eşik, dışlama kuralı ya da kod değişmez. Koşu 045baea, danışman hükmü
SCIENTIFIC_REVIEW v2.26 (17c0453), sonuç özeti `results/sens_v225/SUMMARY.md`.

- **Uygunluk.** Analiz Beyan'daki gibi koşuldu; sapma yok. S0 kapısı: 14 dosya, 0 kayıp. Donmuş varyantın S3 çıktıları
  makalenin çıktılarıyla bayt-özdeş.
- **Eşik.**
  - (i) Eşikte adı geçen testler (H_G1b, H_G1a, E1 sınırları, McNemar, H_MT1/H_MT2) Holm sonrası anlamlılık ve yön
    olarak değişmedi.
  - Sınırda bir durum: aynı Holm ailesinin üyesi olan yardımcı karşılaştırma H_G1a_aux (araç katkısı: no-guard ↔
    ungrounded) ondalık kuralıyla Model E'de anlamlı oldu (Holm p .234 → .030; bootstrap aralığı sıfırı içeriyor).
    Model C'de Holm p .214 → .083 (`both`), anlamlı değil. Eşik listesinde adıyla geçmiyordu; makalede nitelendi
    (§crosslingual, §limits).
  - (ii) McNemar "yalnız no-guard temiz" hücresi her koşulda ve varyantta 0 kaldı.
  - (iii) Model C'nin ayrıştırılmış kazancı negatif kaldı.
  - (iv) Karşılandı, yalnız ondalık kuralıyla. Ana metin buna göre yeniden yazıldı.
- **S4 payı.** Beyan, S4'ü yeniden denenmiş yanıtlar üzerinden tanımlar; raporlanan oran "bloklanmış ve ilk taslağı
  geçen / bloklar"dır. İki pay da dosyada; eşik ikisinde de aynı sonucu verir.
- **S1 ↔ S4 farkı.** S4, `fallback` işaretli bir kaydı (Model C, G1-MT, ikinci tur) saymış. Bu kayıt taslağında uzun
  ondalık ya da işaretli sayı taşımıyor. S1 ve makale bu kayıtları dışladığı için raporlanan sayı 4/33'tür
  (ham dosyada 4/34).
- **G4.** Yeniden puanlanmadı. Makalede ölçülmemiş olarak yazıldı.
- **Makale.** main.tex'e eklenenler:
  - "Matcher defects found after the outcomes" sınırlılık paragrafı;
  - tab:g1'e iki satır, tab:a30'a iki satır;
  - Ek `app:matcher`;
  - v2.26 listesindeki ifade düzeltmeleri.

  Abstract, highlights ve grafik özet değişmedi.

### Sonuç-sonrası bulgu notu (2026-11-15) — A23-5 envanteri eksikti; ihracat fiyatı mevzuatla çelişiyor [POST-OUTCOME; analiz yok, kod değişmedi]

Bu not yalnız iki bulguyu kaydeder; hiçbir test, eşik, dışlama kuralı ya da kod değişmez; hiçbir sayı yeniden hesaplanmadı.
Danışman hükmü: SCIENTIFIC_REVIEW v2.27.

- **A23-5 kapsamı.** Envanter yalnız referans graflarının çağırdığı dört simülatörü kapsıyordu. Modele sunulan dokuz ek
  araç (yapılandırma, bileşen düzeyi koşu, ağ kurma) denetlenmemişti; `questions.json` bunların hiçbirini içermez.
- **Atlanan noktalar (donmuş kodda duruyor).**
  - `app/simulation/pv/system_store.py:195`: `get_pvgis_tmy` dört değere açılıyor, pvlib 0.15 iki değer döndürüyor;
    çıplak `except` her çağrıda sessizce clear-sky'a düşüyor (`run_pv_simulation`).
  - `app/simulation/bess/system_store.py:240-275`: dispatch çıktısı yanlış anahtarlarla okunuyor; `annual_cycles` hep 0;
    degradasyon hatası yutuluyor (`run_bess_simulation`).
  - `app/llm/ollama_orchestrator.py:718-727`: `_run_bess_simulation` içindeki PV çağrısı hatası yutuluyor (`pv_hourly=None`).
  - Dokuz aracın kalan yedisi sessiz fallback açısından denetlenmedi.
- **İz kullanımı** (`provenance.tool_trace` ayrıştırması, metin araması değil). Ekim G1, Model B Türkçe: 504 yanıtın 1'i
  (com-04, guard kolu, tekrar 0); bloklandı ve teslim edilen özet hiç sayı içermedi. A30 (keşifsel): 504 yanıtın 7'si
  (com-04, com-14; guard ve no-guard). G1-MT, G2 ve analiz edilen diğer koşularda bu iki araç çağrılmadı. Dokuz aracın
  tamamı tarandığında analiz edilen Ekim koşularında ek olarak yalnız Model C'nin 2 `configure_pv_system` çağrısı
  (simülasyon koşmaz) görülür.
- **Karar.** Dışlama yok, duyarlılık analizi yok. Gerekçe: guard hükmü, sayının aracın döndürdüğü değere izlenmesidir;
  araca göre sonuç-sonrası dışlama ön-kayıtlı kurallarda yoktur. Makalede §limits, §3 ve `app:params` içinde beyan edildi.
- **İhracat fiyatı.** `EXPORT_SURPLUS_RATE_TL_PER_KWH = 0.4941` (mesken düşük kademe aktif enerji) bütün paydaşlara
  uygulanıyor. RG 02.04.2026/33212 ile değişen Md. 28(11), tamamı Mesken AG olan tüketimde yüksek kademeli tarife fiyatını
  esas alır; diğer gruplar için ayrı kurallar vardır. Kod değişmedi. G1, G2 ve G4 simülatör parametrelerinden bağımsızdır;
  makalede `app:params`, §3 ve "Setting" içinde düzeltilmemiş kusur olarak beyan edildi. Politika aracının feed-in ve
  net-metering mekanizmaları bağlam verilmediğinde sabit 5,30 TL/kWh ile değerlenir; `app:params` Policy satırına eklendi.

### Beyan notu (2026-11-15) — v2.28 uzunluk kesimi; G5 ve H_LANG-1(c) [analiz yok, kod değişmedi]

- Makale Applied Energy ortalamasına indirildi (Giriş..Sonuç ~14.350 → ~9.000 sözcük). Çıkan metin silinmedi;
  `paper/supplement.tex` (S1–S11) içine olduğu gibi taşındı. Hiçbir sayı, test ya da kusur beyanı değişmedi.
  Danışman planı: SCIENTIFIC_REVIEW v2.28.
- **G5 (ajan devirleri).** `prereg-v1.0` H_G5'i dondurdu; protokol eki hiç donmadı ve G5 koşulmadı. Makale
  bundan söz etmiyordu; artık §4 "Pre-registration" paragrafında beyan ediliyor.
- **H_LANG-1(c).** Taksonominin İngilizce tekrarı (birincil H_LANG-1'in c bileşeni) koşulmadı (taksonomi betiği
  tasarım gereği TR iki-model). Makale §5.5'te beyan ediliyor.
- **H_G2 ifadesi.** Makale G2'yi "null hypothesis" olarak anlatıyordu; ön-kayıt bir azalma hipotezi ve null'u
  raporlama sözüdür. Metin ve Tablo 1 buna göre düzeltildi.

### Beyan notu (2026-11-16) — G3 ikincil kriterinin etiketi [analiz yok, kod değişmedi]

`PREREGISTRATION_G3.md` ve `g3_cross_scale.py` ikincil kriteri (Vmax > 1.05 pu @ teslim-slack) "EN 50160" diye etiketler; EN 50160 bandı bundan geniştir. Kriter ve sonuçlar değişmez; makale (§5.1) kriteri "1.05 pu mutlak üst sınır" olarak anlatır ve etiketin standarttan dar olduğunu belirtir. Kaynakça doğrulaması sırasında platform oturumu fark etti.
