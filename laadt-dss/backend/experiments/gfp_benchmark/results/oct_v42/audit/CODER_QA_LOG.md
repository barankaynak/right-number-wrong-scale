# A22-2 — Kodlayıcı soru-cevap kaydı

Kural: kodlama sırasında gelen sorulara yalnız AUDIT_CODEBOOK.md metnine dayanarak cevap
verilir. Kodkitabı değişmez, yeni kural eklenmez. Her cevap iki kodlayıcıya da aynen
iletilir. Bu kayıt, kodlayıcı sayfalarıyla birlikte hash'lenip commit edilir.

## S1 (2026-11-03, kodlayıcı-1)
Model cevap vermek yerine ek bilgi soruyor (takip sorusu). Gerçek kullanımda konuşma
sürerdi; bu öğeler neden kodlanıyor?

**C1.** Örneklem önceden dondurulmuştu; öğe çıkarılamaz. Deney tek turludur ve
soruların gerekli girdileri içerdiği soru setinde kontrol edilmiştir. Kodkitabı:
`usable_answer_YN` = **N** "(e.g. asks for inputs, says no simulation was run, …)".
N "yanlış" anlamına gelmez; yalnız "bu turda sorulana sayı verilmedi" demektir.
- Metindeki sayılar her zamanki kurallarla kodlanır. Sorudaki bir girdiyi tekrar eden
  sayı → `traceable` Y + `input_echo`.
- Model cevabı verip sonunda "batarya da ekleyelim mi?" gibi bir öneri soruyorsa
  sondaki soru kodu etkilemez; cevap kısmı normal kodlanır.

## S2 (2026-11-03, kodlayıcı-1)
"Note: the response was replaced with a deterministic summary …" ile başlayan
yanıtlarda simülasyon sayıları var, ama sorulan şeyin cevabı tam olarak yok.
`usable_answer_YN` ne olmalı?

**C2.** Kodkitabı: Y = "at least one number addresses what was asked"; N = "the text
gives no number for what was asked (… or lists unrelated fields only)". Metnin bir
şablon özet olması kodu etkilemez; yalnız içeriğe bakılır.
- Sorulan büyüklük listede herhangi bir yerde varsa → **Y**. Ham alan adıyla ya da
  başka alanların arasında olması fark etmez.
- Soru birden çok şey istiyorsa, birine sayı verilmesi yeterli → **Y** ("at least one").
- Listede yalnız başka büyüklükler varsa (konuyla ilgili olsalar bile) → **N**
  ("unrelated fields only").
- Sorulan sayı ancak kullanıcı kendisi hesaplarsa elde ediliyorsa (ör. yıllık değerden
  aylık değer) → **N**, çünkü metin o sayıyı vermiyor.
- Yalnız birimin farklı olması aynı büyüklük sayılır (kWh↔MWh, oran↔yüzde,
  bin/milyon) → **Y**. Bu, `traceable_YN`'deki dönüşüm kuralıyla aynıdır.

## S3 (2026-11-03, kodlayıcı-1)
Model, kendi sayılarından "1/10" gibi bir oran hesaplamış. Bu "sayı değil" (N/A) mı,
"yok" (N) mu?

**C3.** N/A değil. Kodkitabındaki N/A listesi yalnız nicelik bildirmeyen sayılardır:
"list numbering, dates and years, step labels, counts of items in the answer itself".
Oran ise bir nicelik bildirir. Ayrıştırıcı "1/10"u iki ayrı sayı olarak işaretler (1 ve
10), ve her işaretli sayı kendi başına aynı kuralla kodlanır: "Does this number appear on
the reference output sheet, allowing for rounding?"
- O değer tabloda ya da soruda varsa (yuvarlama ve saf ölçek dönüşümü serbest) → **Y**.
  Farklı bir alanda olması fark etmez: "Do not judge whether the number is used at the
  right scale, for the right quantity, or whether it is correct; only whether it can be
  found."
- Yoksa → **N**. Bir sayı ancak başka sayılardan hesaplanarak bulunabiliyorsa da **N**
  ("more than simple rounding or a pure unit rescaling").
- Modelin sayıyı kendisinin hesaplamış olması kodu değiştirmez.

## S4 (2026-11-04, kodlayıcı-1)
Model takip sorusu sorabilecekken konuşma neden sürdürülmemiş, bazı yanıtlarda neden
simülasyon sonuçları basılmış? Model cevap alsaydı sonuç verebilir miydi? Bu öğeler bilerek
mi seçildi?

**C4.** Kodlamayı etkileyen yeni kural yoktur; S1 ve S2 geçerlidir. Tasarım bilgisi:
- Deney tek turludur: her soru bir kez gönderilir ve sistemin teslim ettiği metin kaydedilir.
  Hiçbir kolda ve hiçbir koşulda ikinci kullanıcı mesajı yoktur. Model cevap alsaydı ne
  yapacağını bu veri ölçmez.
- Kodlanan metin, sistemin son çıktısıdır. Guard metindeki bir sayıyı kaynakla eşleyemezse
  modelden bir kez düzeltme ister. Yine olmazsa metnin tamamını değiştirir: o turda simülasyon
  çalışmışsa yerine simülasyon sonuç listesi ("deterministic summary") konur, çalışmamışsa
  sayı içermeyen bir "girdileri paylaşın" mesajı. Modelin ilk yazdığı metin kodlayıcıya
  gösterilmez; yalnız teslim metni kodlanır.
- Öğeleri kimse tek tek seçmedi. Öğeleri, kodlamadan önce dondurulmuş audit_sample.py sabit
  tohumla (seed=42) çekti. Örneklem, sistemin yanıtı nasıl işlediğine göre katmanlıdır; bu
  yüzden guard'ın metni değiştirdiği yanıtlar örnekleme bilerek ve önceden belirlenmiş sayıda
  alınmıştır. Hangi öğenin hangi katmanda olduğu kodlayıcılara gösterilmez.

## S1 düzeltmesi (2026-11-04)
C1'deki "soruların gerekli girdileri içerdiği soru setinde kontrol edilmiştir" cümlesi
**yanlıştır**. S4 üzerine yapılan kontrolde, 56 sorunun 17'sinde, gereken bir aracın zorunlu
bir girdisinin (şehir, sistem gücü, penetrasyon oranı, yatırım ya da tasarruf tutarı)
metinde verilmediği görüldü. 4 soruda daha bu durum katı bir okumayla geçerlidir.
Sınıflandırma: `experiments/gfp_benchmark/QUESTION_INPUTS.md`. Bu sorularda modelin girdi
sorması makul bir hamledir.

**Kodlama kuralı değişmez:** kodkitabı "asks for inputs" → `usable_answer_YN` = **N**. N,
"yanlış" ya da "kötü" anlamına gelmez; yalnız "bu tek turda sorulana sayı verilmedi" demektir.
C1'in geri kalanı geçerlidir.

## Arayüz değişikliği v3 (2026-11-03 14:36 UTC, yayından önce yazıldı)

**Neden.** Kodlayıcı-1, yuvarlanmış sayıların (yanıtta 4,86, tabloda 4,857) tablo
aramasıyla bulunamadığını bildirdi. Eski arama, rakam dizisini alt-dize olarak arıyordu.

**Ne değişti.** İki kodlayıcı sayfasında da aynı değişiklik yapıldı.
- Bir sayı seçilince (tıklama, ↑/↓ ya da Y/N/A sonrası otomatik geçiş), tablonun üstünde
  bir "en yakın değerler" paneli açılır. Referans tablodaki satırlar seçili sayıya
  sayısal yakınlıkla **sıralanır** ve ilk 6 grup gösterilir. Aynı değerdeki satırlar
  tek satırda birleşir.
- Kodkitabındaki saf ölçek dönüşümleri de denenir (×100, ÷100, ÷1000, ×1000,
  ÷1.000.000). Dönüşmüş değer düz aritmetik olarak yazılır, ör. "0,3259 · ×100 = 32,59".
- Sorudaki sayılar listeye "Soruda geçiyor" satırı olarak girer (input_echo kuralı).
- Biçimi belirsiz sayılarda (281,417 / 7.559) TR ve EN okumaların ikisi de denenir.
- Arama kutusuna sayı yazılırsa aynı sıralama kullanılır. Metin yazılırsa alan adları
  süzülür (eski davranış). Tam tablo panelin altında hep görünür.

**Tarafsızlık.** Panel "eşleşiyor / eşleşmiyor" demez. Eşik, renk, mesafe ya da
"bulunamadı" mesajı yoktur; her zaman en yakın satırları gösterir. Yuvarlamaya izin
verilip verilmeyeceğine ve Y / N / N/A koduna kodlayıcı karar verir. Panel, eşleştiricinin
(provenance guard) kodunu ya da kararlarını kullanmaz. Kodlayıcılar otomatik karar
görmez; bu kodkitabı kuralı korunur. Kodkitabı, öğeler ve etiket depolama değişmedi.
Veri satırının sha256'sı her iki sayfada da değişiklik öncesiyle aynıdır
(coder1 52095ee45b408db4…, coder2 cff165a645783d58…).

**Yayınlanan sayfalar** (`coding_interface_v3/`, sha256):
- coder1.html: f9261604f928c5ae17e3fcc874830fb281cc1494bdc7a90046f7dffdff168510
- coder2.html: b04e966b081bab43b79a612492b3205dc1ee365a9a41515a2fdb6076a8add9f5
- patch_v3.py: ff39450f2a5d8e3caaa4bc2340563440d9ccbfa3ebbd7252fd740e649bc4fd53

**Değişiklik anındaki durum.**
- Kodlayıcı-1: `codes` koleksiyonunda 27 öğe kaydı vardı (A002–A028, bazıları kısmi).
  Yedek `coder1_backup_20261103a/` klasöründe: 27 dosya, klasör sha256
  72c7abe74ef6c2c6788ca9ac378461f0819b3a8922e40ad943d0423b76d5aee2 (sıralı dosya adı +
  içerik). Etiketlerin içeriği okunmadı.
- Kodlayıcı-2: kişisel kayıt alanı sayfa sahibine de kapalıdır. Başlayıp başlamadığı
  kendisine sorulacak ve cevabı buraya eklenecek.

**Makale (threats).** "The coding interface's lookup aid was improved after coder 1
had saved labels for 27 of 86 responses; the change was identical for both coders. The aid
orders reference-sheet rows by numerical closeness and never displays a match or
no-match signal."

## Arayüz değişikliği v4 — yalnız kodlayıcı-2 sayfası (2026-11-05)

**Neden.** Kodlayıcı-2'nin zamanı tüm öğeleri kodlamaya yetmiyor. PREREGISTRATION.md A29
uyarınca kodlayıcı-2 yalnız rastgele çekilmiş bir alt kümeyi kodlar: 86 yanıttan 30'u ve 263
cümleden 80'i (`coder2_subset.json`, seed 20261105, donmuş tabakalara orantılı). Alt küme,
kodlayıcı-2'nin durumu bilinmeden ve hiçbir etiket okunmadan çekildi (commit dc89447).

**Ne değişti.** Kodlayıcı-2 sayfasında yalnız veri satırı değişti: öğe listeleri alt kümeye
indirildi. Sayfanın geri kalanı v3 ile bayt-özdeştir. Kodkitapları, sorular, referans tablolar
ve arama paneli aynıdır. Kodlayıcı-1 sayfası değişmedi; kodlayıcı-1 bütün öğeleri kodlar.
- Veri satırı sha256 (v3 yöntemiyle): önce cff165a645783d58…, sonra fda21f11cffb1b08….
- Sayfa: `coding_interface_v4/coder2.html` 221e190d1354d80f6cd4143114b8caeda20b8c97750f0ffa129c36ae3f1bd6bd.
- Yama: `patch_v4_subset.py` d67e59bdf9637ab2934f7383b1970e74397632d6f36fd8a35e294ed349865af0.
- Yayın: aynı bağlantı, sürüm 4 (1793829474-3107).

**Kodlayıcı-2 durumu.** Kodlayıcı-1'in beyanına göre kodlayıcı-2 kodlamaya hiç başlamadı
(2026-11-05). Bu bilgi alt küme çekildikten sonra öğrenildi.

**Kodlayıcı-2'ye iletilecek.** Sayfada yalnız size düşen öğeler var. S1–S4 cevapları ve S1
düzeltmesi sizin için de geçerlidir.


## Kodlama bitti — kodlayıcı dosyaları mühürlendi (2026-11-05)

- **Kodlayıcı-1:** 86/86 yanıt ve 263/263 cümle. Veritabanından indirildi ve sayfa biçiminde
  CSV'ye yazıldı (`export_coder1_csv.py`).
- **Kodlayıcı-2:** alt küme 30/30 yanıt ve 80/80 cümle. Kendi dışa aktarım dosyaları.
- **Sıra:** analiz betikleri bu mühürden önce donmuştu (PREREGISTRATION.md, Beyan 2026-11-05,
  commit e6d3f1b). Körleme bu commit ile biter.

sha256:
- `coded/audit_coded_coder1.csv` 1b97f2a0b87aa3f27314da87e693ef8ef294d263b74e9b82189fafb8d597e64f
- `coded/audit_coded_coder2.csv` 4e05c0c29de1eb5ca5d630fe3b1be3929f6ae7c33de49a0b88d92f8352f155d2
- `coded/scale_coded_coder1.csv` 4988ec3207978711f6581d67dc338748cbf1a0982bf47663584e379c77d91611
- `coded/scale_coded_coder2.csv` 533f819bd381c0231be1e991c02a510e7028629519d632c00ca1bdacd22f5245
- `audit/coder1_db_final/codes/` (349 belge; sıralı ad+içerik) 3d1748c0ea6b8919aaec5edcc797939e1b0271998c7d4ef7baacaa38e15ca580
