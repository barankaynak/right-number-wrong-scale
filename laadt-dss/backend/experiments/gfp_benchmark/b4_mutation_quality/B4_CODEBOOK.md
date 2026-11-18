# B4 — G4 Enjeksiyon Mutasyon-Kalitesi: İnsan Kodlama Kodkitabı (DONMUŞ v1.0)

**Sürüm:** v1.0-B4 · **Tarih:** 2026-07-10 · **Statü:** kodlama BAŞLAMADAN önce DONDURULUR
**Ön-kayıt bağlamı:** `PREREGISTRATION.md` §9 Amendment Log'a **exploratory (B4)** olarak
eklenir. Bu kodkitabının ve `B4_coding_sheet.csv`'nin SHA-256'ları dondurma anında
amendment-log'a yazılır; sonrasında madde değişmez (yalnız amendment-log ile ekleme).

> **Neden B4?** H_G4 (GFP vs legacy recall), makalenin en güçlü sonucu ve enjekte
> edilen kontrollü hataların **geçerli test öğeleri** olmasına dayanır. Ön-kayıt,
> enjeksiyonların **%20'sinin** 2 bağımsız kodlayıcı tarafından — guard'ın kararına
> **KÖR** olarak — **akıcılık** ve **kategori-uygunluğu** açısından denetlenmesini
> "yayın-kapısı" olarak şart koşar (danışman v2.12.6-2). B4 bu denetimi sağlar:
> enjeksiyonların ne kadarının gerçekten sağlam, kategori-doğru mutasyonlar olduğunu
> insan yargısıyla ölçer.

---

## 1. Analiz birimi ve materyal

- **Birim:** bir enjekte-edilmiş öğe = bir kodlama satırı (`B4_coding_sheet.csv`, **51 satır** = ÜÇ G4 setinin %20'si; danışman v2.17: EN enjeksiyonları da denetime alındı).
- **Örneklem (BİRLEŞİK; her set %20, kategori-oranıyla katmanlı, seed=42):**
  - **TR (primary, H_G4):** donmuş `raw_g4_final_seed42_20260709T011118Z.jsonl` (109) →
    metni **yeniden-üretilebilir** 97 satırdan **19** öğe (metin-tekrar-üretilemeyen 12
    satır=3 soru yalnız metin nedeniyle dışlandı; enjeksiyon prosedürü aynı).
  - **EN:** `raw_g4_final_en_seed42_*` (87, source/mutated doğrudan) → **18** öğe.
  - **Mistral (TR):** `raw_g4_final_mistral-small3.2-24b_seed42_*` (66) → **14** öğe.
  Her satırda **`set`** sütunu (TR/EN/Mistral) GÖRÜNÜR — akıcılık ilgili dile göre yargılanır.
- **Kodlayıcı sayısı:** 2 bağımsız kodlayıcı, her biri sayfanın KENDİ kopyasını doldurur
  (`B4_coding_coderA.csv`, `B4_coding_coderB.csv` olarak kaydedin).
- **KÖRLEME (zorunlu):** Kodlayıcı, guard'ın (GFP veya legacy) o öğeyi yakalayıp
  yakalamadığını GÖRMEZ. `B4_guard_key.csv` kodlayıcılara **verilmez** (yalnız kodlama
  bitince, adjudication sonrası karşılaştırma için açılır).
- Her satırda kodlayıcının gördüğü sütunlar: `item_id`, `intended_category`
  (hedeflenen mutasyon türü), `original_sentence`, `mutated_sentence`. Değişen bölüm
  her iki cümlede de `>>...<<` ile işaretlidir.

---

## 2. Kararlar (kodlayıcı her satır için doldurur)

Kodlayıcı, `original_sentence` → `mutated_sentence` değişimini `intended_category`ye
göre değerlendirir ve şu 3 sütunu doldurur:

| Sütun | Ne yazılır |
|-------|-----------|
| `fluent_YN` | **Y** = mutasyon-sonrası cümle akıcı/dilbilgisel (değişim kırık ek/uyumsuz ifade ÜRETMEMİŞ) · **N** = bozuk (§3) |
| `category_correct_YN` | **Y** = mutasyon, hedeflenen kategoriyi **gerçek bir simülasyon-sonucu / karar-değeri** üzerinde doğru uyguladı · **N** = değil (§4) |
| `coder_notes` | Tereddüt, sınır durum, gerekçe (serbest metin; isteğe bağlı) |

**Birincil IRR değişkeni:** `category_correct_YN` (öğenin H_G4 için geçerli-test-öğesi
olup olmadığı). İki kodlayıcı arası **Cohen's κ** bu değişken üzerinden hesaplanır;
`fluent_YN` için de κ ayrıca raporlanır.

---

## 3. `fluent_YN` — akıcılık ölçütü

- **Y (akıcı):** Değişen bölüm cümleye dilbilgisel oturuyor; okuyan bir insan için
  cümle doğal/anlaşılır kalıyor (anlam yanlış olabilir — akıcılık ≠ doğruluk).
- **N (bozuk):** Değişim, kırık ek, çift-ek, uyumsuz sözcük ya da bariz gramer hatası
  üretmiş. Örnekler:
  - "Ofis **>>fider genelinde<<**ın en yoğun..." → "fider genelindeın" kırık ek → **N**.
  - "(Batarya Enerji Depolama **>>Mahalle genelinde s<<**istemi)" → "Depolama Mahalle
    genelinde sistemi" uyumsuz → **N**.
- Sadece bir sözcüğün/birimin/sayının temiz değiştiği durumlar (ör. "(TL)"→"(kWh)",
  "eviniz"→"mahalledeki tüm 40 ev") akıcıdır → **Y**.

---

## 4. `category_correct_YN` — kategori-uygunluğu ölçütü

Mutasyon, hedeflenen kategoriyi **gerçek bir simülasyon-sonucu veya karar-değeri**
üzerinde uygulamışsa **Y**; **sonuç olmayan** bir sayı/etiket üzerinde uygulanmışsa
**N**. Kategori tanımları:

- **value-fabrication** — temellendirilmiş bir **sonuç sayısı** (NPV, tasarruf, üretim,
  gerilim, kapasite, geri-ödeme vb.) farklı bir değere bozulmuş → **Y**. Bir **liste/
  başlık numarası** ("1." → "1,8."), tablo-şablonu yer-tutucusu ("%80" örnek-tablo), ya
  da salt bağlam sayısı bozulmuşsa → **N**.
- **unit-swap** — bir **sonuç değerinin birimi** yanlış değiştirilmiş (sayı ile birlikte
  yanlış nicelik sunulmuş) → **Y**. Yalnız bir **veri-isteği/şablon etiketi** ("...tutarını
  (TL)" gibi kullanıcıdan bilgi isteyen) ya da açıklayıcı-metin birimi değişmişse → **N**.
- **scale-swap** — bir **sonuç-cümlesi** bina→fider/mahalle çerçevesine, SAYI aynı
  kalarak yeniden çerçevelenmiş ("eviniz"→"mahalledeki tüm 40 ev" ve cümlede bir
  temellendirilmiş sayı var) → **Y**. Yalnız bir **soru/başlık** çerçevesi değişmiş ve
  cümlede temellendirilmiş sonuç sayısı yoksa → **N**.
- **small-int** — bir **karar-kritik yıl-değeri** (geri-ödeme/erteleme süresi) farklı
  bir tamsayıya değişmiş → **Y**. Sıralama/adım numarası ("Adım 3"→"Adım 12") ya da
  bağlamsal yıl değişmişse → **N**.

**Tereddütte:** Değişim, kullanıcının okuyup yatırım kararı vereceği bir **sonuç
sayısını** etkiliyorsa **Y**; salt biçim/şablon/soru/liste öğesiyse **N** — ve
`coder_notes`a yaz.

---

## 5. Türetilen `valid_item`

Kodlama sonrası (kodlayıcı doldurmaz, script türetir):
`valid_item = fluent_YN AND category_correct_YN` — öğenin hem akıcı hem kategori-doğru
(H_G4 için tam-geçerli test öğesi) olduğu.

---

## 6. Adjudication (anlaşmazlık çözümü)

1. İki kodlayıcı bağımsız doldurur → `fluent_YN` ve `category_correct_YN` için ham
   anlaşma yüzdesi + Cohen's κ hesaplanır (`compute_b4_kappa.py`).
2. `category_correct_YN` anlaşmazlıkları üçüncü bir hakem (veya iki kodlayıcının
   uzlaşı görüşmesi) ile çözülür → **konsensüs etiketi**.
3. Hem ham κ hem konsensüs-sonrası metrikler raporlanır.

---

## 7. Raporlanan metrikler (kodlama sonrası)

- **Cohen's κ** — `fluent_YN` ve `category_correct_YN` için ayrı ayrı (ham, 2 kodlayıcı).
- **Kategori-doğruluk oranı** = P(`category_correct_YN`=Y | öğe), Wilson %95 GA;
  kategori kırılımı (value/unit/scale/small ayrı).
- **Akıcılık oranı** = P(`fluent_YN`=Y | öğe), Wilson %95 GA.
- **Geçerli-öğe oranı** = P(`valid_item`=Y | öğe).
- **Yorum:** Yüksek geçerli-öğe oranı → enjeksiyonlar sağlam, H_G4 recall paydaları
  geçerli. Düşük oran → enjeksiyon prosedürü sonuç-olmayan metne sık düşüyor demektir;
  bu durumda (a) geçersiz öğeler ağırlıkla **eşzamanlı-tespit-edilmeyen** (her iki guard
  da yakalamaz) olduğundan **per-kategori McNemar ETKİLENMEZ** (discordant çiftler
  gerçek sonuç-sayılarındadır), ANCAK (b) recall oranları (6/31 vb.) geçersiz öğelerle
  seyreldiğinden dürüstçe raporlanmalı ve gerekiyorsa enjeksiyon grounded-hedefli
  daraltılıp yeniden koşulmalıdır (karar: geçerli-öğe oranı sonucuna göre).
- **Guard vs insan (adjudication sonrası):** `B4_guard_key.csv`teki `gfp_ref_detected`
  ile konsensüs `valid_item` çapraz tablosu — GFP'nin geçerli öğelerdeki hizası.

---

## 8. Donma disiplini

- Bu kodkitabı ve `B4_coding_sheet.csv` **kodlama başlamadan** donar; SHA-256'ları
  `PREREGISTRATION.md` §9 Amendment Log'a **exploratory (B4)** olarak yazılır.
- Kodlama başladıktan sonra madde/ölçüt/karar-kuralı **değişmez**. Zorunlu düzeltme
  çıkarsa: amendment-log'a gerekçeyle eklenir, kodlama baştan yapılır.
- Kodlayıcılar guard etiketine kördür (§1).

---

## 9. Materyaller

- `make_b4_package.py` — kör sayfayı + gizli guard-key'i `results/` ham JSONL'lerinden üreten script (seed=42, yeniden-üretilebilir).
- **`B4_coding_tool.html`** — kendine-yeterli tarayıcı ARAYÜZÜ (önerilen giriş yöntemi): kodlayıcı çift-tıklar, 22 öğeyi kart-kart işaretler (`>>değişen<<` vurgulu), otomatik-kayıt (localStorage), sonunda `B4_coding_<isim>.csv` indirir. KÖR (guard-key gömülü DEĞİL). `make_b4_tool.py` ile `B4_coding_sheet.csv`'den üretilir.
- `B4_coding_sheet.csv` — kör kodlama sayfası (51 satır, TR+EN+Mistral; HTML aracı yerine CSV'yi elle doldurmak isteyen için).
- `B4_guard_key.csv` — guard kararı + text-provenance (kodlayıcılara KAPALI; adjudication sonrası açılır).
- `compute_b4_kappa.py` — iki doldurulmuş sayfadan Cohen's κ + oranlar + türetilmiş `valid_item` hesaplar.
