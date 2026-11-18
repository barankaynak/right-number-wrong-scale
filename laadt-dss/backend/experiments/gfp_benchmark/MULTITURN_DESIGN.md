# Çok turlu ek deney — tasarım taslağı (2026-11-05: A28 olarak DONDU)

> **Bağlayıcı metin PREREGISTRATION.md A28'dir** (`prereg-v3.4`). Bu taslak tarihçe olarak
> kalır. Dondurmada üç değişiklik yapıldı:
> - Boyut: kullanıcı "Tam" seçti.
> - Vekil: `numeric_focus` etiketleri doğrudan kayıt adı olmadığından, etiket→anahtar
>   eşlemesi `answer_keys.json` ile donduruldu.
> - Kapsam: dis-05 yalnız trafo ertelemeyi sorar ve araç yolu bu çıktıyı üretmez; bu yüzden
>   TU analizinden çıkarıldı (n = 20).

**Durum.** 2026-11-04 tarihli taslak. A22-2 ve A26 insan kodlaması sürerken, **hiçbir Ekim G1
sonucuna bakılmadan** yazıldı. Danışman (Fable, advisor) görüşü alındı. Kod okumasıyla
doğrulanan davranışlar §7'de. Bu bir ön kayıt **değildir**. Dondurmak için PREREGISTRATION.md'ye
amendment (A28) ve tag (`prereg-v3.4`) gerekir; tarih kısıtı için §9'a bakın.

**Kaynak.** Kodlayıcı-1 sorusu S4 ve S1 düzeltmesi (`results/oct_v42/audit/CODER_QA_LOG.md`).
Soru sınıflandırması: `QUESTION_INPUTS.md` (56 sorunun 17'si net, 4'ü katı okumayla
eksik-girdili).

## 1. Araştırma sorusu

Tek turda zorunlu bir girdisi eksik olan sorularda, kullanıcı eksik girdiyi ikinci turda
verdiğinde:
1. Sistem sorulan büyüklüğe sayı veriyor mu (kullanılabilirlik)?
2. Bu sayılar izlenebilir mi (referans grafa ve oturumun kendi grafına göre)?
3. Guard'ın fail-closed maliyeti (metni değiştirme) konuşmada geri kazanılıyor mu? Kollar
   arasındaki fark tek tura göre nasıl değişiyor?

Bu deney bir iddiayı **test eder**; sistemin iyi olduğunu kanıtlamak için kurulmaz. Sonuç her
iki yönde de çıkabilir. Örneğin kullanıcının verdiği sayıların metinde tekrarlanması ("yankı"),
guard'lı kolu ikinci turda daha kötü gösterebilir. Ön kayıt bu yüzden gerekli: olumsuz bir sonuç
da yayımlanabilir kalır. Makaledeki yeri: "Single-turn evaluation" sınırlılığına ve Discussion'daki
fayda–izlenebilirlik ödünleşimine doğrudan cevap. Yeni bir katkı değil, ikincil bir deney.

## 2. Kapsam

- **Sorular:** `QUESTION_INPUTS.md`'deki 21 soru (17 net + 4 katı okuma). Ön-belirlenmiş
  duyarlılık analizi: yalnız 17 net soru.
- Tam belirli 35 soru ikinci tur almaz; onlar G1'de zaten kapsanıyor.
- Kollar, modeller, diller ve tekrarlar: G1 ile aynı. Maliyet kolları için §6'ya bakın.

## 3. İkinci tur mesajı

- Sabit TR/EN şablonu. Yalnız **metinde geçmeyen `suggested_args` değerleri** yazılır: zorunlu
  olanlar ve zorunlu olmayanlar. Böylece donmuş referans graf ikinci turda ulaşılabilir olur.
- Araç, ölçek ya da çarpma hakkında **hiçbir ipucu yoktur**. 21 sorunun beşi (res-11, res-12,
  com-10, sta-07, sta-10) ölçek tuzağıdır; şablon "çarpma" demez.
- Örnek (sta-02, TR): "Yatırım tutarı 400.000 TL, yıllık tasarruf 55.000 TL, sistem ömrü 25 yıl,
  iskonto oranı %15."
- Bilinen tuhaflık: res-04'te kullanıcı "uygun boyut" istemişti; ikinci turda "4 kW olsun"
  demek doğal değil. Soru tutulur ve bu not raporda yer alır.
- **Her zaman gönderilir.** İkinci tur, birinci turun cevabından bağımsız olarak gönderilir.
  Sınıflandırıcı gerekmez ve süreç deterministiktir; bilgiyi kendiliğinden veren kullanıcıyı
  modeller. "Model birinci turda girdi sordu mu" sorusu dal değil, betimsel bir ortak
  değişkendir.

## 4. Ölçüm — yeni insan kodlaması olmadan

- **Referans izlenebilirliği:** İkinci turdaki değerler `suggested_args` ile aynı olduğu için
  donmuş referans graflar aynen geçerlidir. Mevcut `reference_check` ve GFS araçları kullanılır.
- **Kendi-graf izlenebilirliği:** Guard raporu her turda zaten kaydediliyor.
- **Kullanılabilir-cevap vekili (proxy):** Teslim metninde, anahtarı sorunun `numeric_focus`
  listesinde olan bir kayda eşleşen (GROUNDED) en az bir sayı varsa "kullanılabilir" sayılır.
  - **Doğrulama:** Vekil, A22-2'nin 86 insan etiketi (`usable_answer_YN`, iki kodlayıcı
    uzlaşısı) üzerinde hesaplanır. Eşik **dondurma anında sayı olarak yazılır** (aday:
    Cohen κ ≥ 0.70). Etiketler henüz yokken eşiği sabitlemek, vekili meşru kılan şeydir.
  - Eşik geçilirse yeni kodlama yok. Geçilmezse sabit boyutlu küçük bir denetim yapılır
    (aday: 40 yanıt; ikinci kodlayıcı yalnız alt kümede).
  - **Tehditler:** Vekil eşleştiriciyi kullanır; bu, döngüsellik riski taşır. A22-2'nin Y1/Y2
    sınırları tam olarak bunu ölçer. Ayrıca doğrulama tek turlu yanıtlarda yapılır; vekilin
    ikinci turda da geçerli olduğu bir varsayımdır.

## 5. Ölçütler (aday; dondurmada kesinleşir)

- **U:** Kullanılabilir oran, tur 1'e karşı tur 2, kol başına. Eşleştirme birimi
  soru × koşul × tekrar; analiz birimi G1'deki gibi soru düzeyi (sözde-tekrarlama yok).
- **T:** Tur 2 teslim metninin referans-GFS'i ve kendi-graf ihlal oranı.
- **W:** Tur 2'de guard'ın metni değiştirme oranı. İki duruma ayrılır: model verilen
  değerlerle araç çağırdı (`input:<param>` kayıtları var) ya da değerleri yalnız metinde
  tekrarladı (yankı maliyeti).
- **Betimsel:** Tur 1'de girdi sorma oranı; tuzak sorularında ölçek ihlalleri.

## 6. Maliyet ve kollar (karar kullanıcının)

Tam tasarım 21 soru × 2 tur × 3 kol × 7 koşul × 3 tekrar = 2.646 LLM turu demek. G1'de
56 × 3 × 7 × 3 = 3.528 tur vardı, yani tam tasarım G1'in yaklaşık ¾'ü kadar. G1 süresine göre
bu kabaca 23–34 saat eder.

| kol | tasarruf | kaybedilen iddia |
|---|---|---|
| araçsız (tools-off) kolu çıkar | −⅓ | konuşmada "grounding lift" karşılaştırması |
| 3 tekrar → 1 tekrar | −⅔ | tekrar-arası değişkenlik (soru düzeyi analiz kalır) |
| 7 koşul → 3 model × TR | −4/7 | diller arası ve 5-model genellemesi |
| yalnız 17 net soru | −19 % | katı-okuma sorularının kapsamı |

Daha ucuz bir seçenek değerlendirildi ve önerilmiyor: G1'in kayıtlı tur-1 yanıtını geçmiş
olarak enjekte edip yalnız tur 2'yi koşmak. G1 kaydı araç mesajlarını saklamıyor; bu yüzden
modelin bağlamı gerçek bir konuşmadan eksik kalır.

## 7. Kod okumasıyla doğrulanan davranış (sonuç değil)

- **Provenance oturum-kalıcıdır** (`app/llm/ollama_orchestrator.py:380-384`, A1-r1): Tur-1
  kayıtları tur 2'de geçerlidir.
- **Araç girdileri kayıttır** (`app/llm/provenance_guard.py:466-469`, `input:<param>`):
  Kullanıcının verdiği değer araca geçirilirse izlenebilir olur. Yalnız metinde tekrarlanırsa
  UNGROUNDED olur. Kullanıcı mesajındaki sayılar kayıt değildir.
- **`last_tool_result` tur başına sıfırlanır** (`ollama_orchestrator.py:378`): Tur 2'de araç
  çağrılmadan guard metni değiştirirse, `safe_summary(None)` tur-1 kayıtları olsa bile
  "özetlenebilir sayısal alan bulunamadı" satırı üretir. Bu davranış **değiştirilmez**, çünkü
  guard kaynağı G1 ile bayt-özdeş kalmalıdır. Raporlanır.
- **Seed:** Koşucu `_ollama_seed`'i soru başına ayarlar; iki turda aynı seed kullanılır
  (10000 + tekrar). Prompt-önbelleği bağımlılığı (makale §limits) ve ısınma isteği G1'deki
  gibidir.
- Araç varsayılanları (`ollama_orchestrator.py:590-660`): `city` → ankara, tüketim → 5000 kWh
  (fatura yoksa), `bess_kwh` → 0, kimya → LFP, ömür → 25, iskonto → 0.12.

## 8. Kapsam dışı

Kullanıcı mesajındaki sayıları düşük-güvenli provenance kaydı olarak eklemek (Discussion,
"Design implications") ayrı bir müdahaledir. Aynı koşuya **eklenmez**; doğal sonraki adım
olarak anılır.

## 9. Zamanlama

1. **Dondurma:** A28 + `prereg-v3.4`, kodlayıcı sayfaları hash'lenip commit edilmeden
   **önce** yapılmalı. O commit doğal körleme sınırıdır. Tasarım hiçbir Ekim sonucu
   içermediği için kodlama sürerken dondurulabilir.
2. **Koşu:** G1 analizleri bittikten sonra.
3. **Makale mi, hakem cevabı mı:** Koşu bittikten sonra karar verilir, şimdi değil.

## 10. Yan bulgu — G1 referans erişilebilirliği (Beyan gerektirir)

Bu taslak yazılırken görüldü. Bazı sorularda referans graf, metinde geçmeyen ve araç
varsayılanından **farklı** `suggested_args` değerleri kullanıyor. Bu sorularda sadık bir model
bile referans sayılarına ancak tahminle ulaşabilir. Etkisi A27-1'e benzer: iki grounded kolda
referans-GFS düşer. A27-1 yalnız şema eksikliğini düzeltti; metinde geçmeyen değerler sorunu
sürüyor.

Adaylar (Beyan yazılırken satır satır doğrulanmalı):
- **Eksik-girdili 21 sorunun çoğu.**
- **Tam belirli görünen sorular:**
  - res-08: tüketim 4200 (varsayılan 5000)
  - res-10: batarya 8 kWh
  - com-05: tüketim 70.000
  - com-14: batarya 30 kWh
  - sta-12: batarya 10 kWh ve fatura 9000
- **A27-1'in 8 politika sorusu:** sta-02, sta-03, sta-09 ve sta-11'de iskonto ve/veya ömür
  metinde yok; sta-06'da ömür yok. com-13, sta-04 ve sta-08 bu değerleri metinde veriyor.
  Makale §limits'teki "Eight of the 56 questions ask for non-default values" ifadesi bu yüzden
  düzeltilmeli.

**Öneri:** G1 sonuçlarına bakılmadan PREREGISTRATION.md'ye bir **Beyan** (kural değişikliği
yok, betimsel): soru başına "referansa ulaşılabilir mi" listesi. Analizde bu bir kayıtlı-dışı
duyarlılık katmanı olarak raporlanabilir.
