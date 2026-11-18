# A8 — Guard Blok Precision'ı: İnsan Kodlama Kodkitabı (DONMUŞ v1.0)

**Sürüm:** v1.0-A8 · **Tarih:** 2026-07-09 · **Statü:** kodlama BAŞLAMADAN önce DONDURULUR
**Ön-kayıt bağlamı:** `PREREGISTRATION.md` §9 Amendment Log'a **exploratory** olarak eklenir.
Bu kodkitabının SHA-256'sı dondurma anında amendment-log'a yazılır; sonrasında
madde değişmez (yalnız amendment-log ile ekleme).

> **Neden A8?** Canlı-koşuda guard (grounded_guard kolu) yanıtların bir kısmını
> blokladı (gemma 18, qwen 88 = **106** yanıt). GFS-artışı küçük (+~%2) ama blok
> oranı yüksek (qwen %52). İki açıklama var: (a) guard **doğru** yakalıyor ama
> ortalama-metrik değeri seyreltiyor, ya da (b) guard **over-block** yapıyor
> (aslında sağlam yanıtları da blokluyor). A8, blokların **PRECISION'ını**
> guard'ın kendi etiketinden BAĞIMSIZ insan yargısıyla ölçerek bu ikisini ayırır.

---

## 1. Analiz birimi ve materyal

- **Birim:** bir bloklu yanıt = bir kodlama satırı (`A8_coding_sheet.csv`, 106 satır).
- **Kodlayıcı sayısı:** 2 bağımsız kodlayıcı, ayrı ayrı doldurur.
- **KÖRLEME (zorunlu):** Kodlayıcı guard'ın kararını/etiketlerini/sayılarını
  GÖRMEZ. `A8_guard_key.csv` kodlayıcılara **verilmez** (yalnız kodlama bitince,
  adjudication sonrası karşılaştırma için açılır).
- Her satırda kodlayıcının gördüğü: `question_tr` (soru), `raw_reply`
  (guard müdahalesinden ÖNCEki ham LLM yanıtı), `reference_numbers`
  (kol-bağımsız tam-zincir simülasyon yer-gerçeği: `key = değer birim [ölçek, kaynak]`),
  ve meta (`scale_focus`, `chain_length`, `stakeholder`).

---

## 2. Kararlar (kodlayıcı her satır için doldurur)

Kodlayıcı, `raw_reply` içindeki **sayısal iddiaları** `reference_numbers`e karşı
tek tek değerlendirir ve şu 5 sütunu doldurur:

| Sütun | Ne yazılır |
|-------|-----------|
| `n_numeric_claims` | Yanıttaki **simülasyon-sonucu** sayısal iddia adedi (bkz §3 hariç tutulanlar) |
| `n_genuine_violations` | Bunlardan **gerçek ihlal** olanların adedi (§4 tanımları) |
| `violation_types` | İhlal tiplerinin kısaltması, virgülle: `U` (ungrounded), `S` (scale), `Un` (unit) — yoksa boş |
| `block_justified_YN` | **Y** = en az 1 gerçek ihlal var (blok haklı) · **N** = 0 gerçek ihlal (over-block) |
| `coder_notes` | Tereddüt, sınır durum, gerekçe (serbest metin) |

**Birincil IRR değişkeni:** `block_justified_YN` (ikili). İki kodlayıcı arası
**Cohen's κ** bu değişken üzerinden hesaplanır.

---

## 3. Sayı SAYILMAZ (ihlal olarak da, iddia olarak da değerlendirme)

Aşağıdakiler `n_numeric_claims`e DAHİL EDİLMEZ (simülasyon-sonucu değil):
- Kullanıcı girdisinin tekrarı (soru "5 kW" dediyse yanıttaki "5 kW").
- Tarih, saat, yıl (takvim), yüzde-işareti olmayan sıralama/madde numaraları.
- Genel/örnek/açıklayıcı sayılar ("örneğin 20-25 yıl panel ömrü" gibi tipik
  literatür bilgisi — simülasyondan gelmemiş genel ifade).
- Birim tanımı içindeki sayı ("pu = per unit" gibi).
Tereddütte: sayı bir **karar-değeri** (payback, NPV, gerilim, tasarruf, kapasite…)
gibi sunuluyorsa DAHİL et; salt bağlam ise hariç tut ve `coder_notes`a yaz.

---

## 4. Gerçek ihlal tanımları (yer-gerçeğine karşı, BAĞIMSIZ yargı)

Bir simülasyon-sonucu iddiası, `reference_numbers` listesindeki ilgili değere karşı:

- **Grounded (ihlal DEĞİL):** Gösterilen hassasiyette veya **±%2 bağıl** tolerans
  içinde referans bir değere **doğru ölçekte** eşleşiyor. (Örn. yanıt 1.1024 pu,
  referans max_voltage_pu=1.102 → grounded.)
- **`U` Ungrounded/fabrikasyon:** Hiçbir referans değere (herhangi ölçekte, ±%2)
  eşleşmiyor — sayı uydurulmuş. (Örn. referansta olmayan bir NPV.)
- **`S` Scale-violation (MANŞET olay):** Sayı **doğru büyüklükte bir referans
  değere eşleşiyor AMA yanlış ölçekte sunuluyor** — hane-ölçeği bir değer fider/
  toplam gibi, ya da tersi. ("Right number, wrong scale." Örn. tek-hane payback'i
  fider-geneli sonucu gibi ifade etmek.) Ölçek bilgisi `reference_numbers`teki
  `[ölçek=...]` ile karşılaştırılır ve sorunun `scale_focus`u dikkate alınır.
- **`Un` Unit-mismatch:** Büyüklük doğru ama birim yanlış (kW↔kWh, TL↔%, pu↔%
  karışıklığı yanlış sonuç veriyorsa).

Bir iddia birden çok tipe uyabilir; en ağırını seç (S > Un > U ihlal-ciddiyeti
değil, sadece etiketleme önceliği: önce S, sonra Un, sonra U). `n_genuine_violations`
ihlal eden **iddia** sayısıdır (tip başına değil).

**Tolerans netliği:** ±%2 bağıl VEYA gösterilen ondalık hassasiyetin son basamağı
(hangisi gevşekse). Yuvarlama farkı (56.319 vs 56.320) ihlal DEĞİLDİR.

---

## 5. Adjudication (anlaşmazlık çözümü)

1. İki kodlayıcı bağımsız doldurur → ham anlaşma yüzdesi + Cohen's κ hesaplanır
   (`block_justified_YN` üzerinden).
2. `block_justified_YN` anlaşmazlıkları üçüncü bir hakem (veya iki kodlayıcının
   uzlaşı görüşmesi) ile çözülür → **konsensüs etiketi**.
3. Hem ham κ hem konsensüs-sonrası metrikler raporlanır.

---

## 6. Raporlanan metrikler (kodlama sonrası)

- **Over-block oranı** = P(`block_justified_YN`=N | bloklu), Wilson %95 GA.
- **Guard blok precision'ı** = 1 − over-block oranı.
- **Model kırılımı** (gemma vs qwen ayrı) + **ölçek kırılımı**.
- **Scale-violation kanıtı:** konsensüste `S` etiketli iddia sayısı → "right number,
  wrong scale" olayının canlı-koşuda insan-doğrulanmış varlığı (manşet iii).
- **Guard vs insan karşılaştırması:** `A8_guard_key.csv`teki guard pre-intervention
  ihlal sayıları vs kodlayıcı konsensüsü (guard'ın tip-bazında hizası).

---

## 7. Donma disiplini

- Bu kodkitabı **kodlama başlamadan** donar; SHA-256'sı `PREREGISTRATION.md` §9
  Amendment Log'a **exploratory (A8)** olarak yazılır.
- Kodlama başladıktan sonra madde/tolerans/karar-kuralı **değişmez**. Zorunlu
  düzeltme çıkarsa: amendment-log'a gerekçeyle eklenir, kodlama baştan yapılır.
- Kodlayıcılar guard etiketine kördür (§1).

---

## 8. Materyaller

- `A8_coding_sheet.csv` — kör kodlama sayfası (106 satır; her kodlayıcı kendi kopyasını doldurur).
- `A8_guard_key.csv` — guard kararı (kodlayıcılara KAPALI; adjudication sonrası açılır).
- `make_a8_package.py` — bu iki dosyayı `results/` ham JSONL'lerinden üreten script (yeniden-üretilebilir).
