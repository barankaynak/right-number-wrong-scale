# G3 Ön-Kayıt Eki (A12) — Cross-scale sessiz geçersizlik

> **Ana ön-kayıt:** `PREREGISTRATION.md` (v1.0 FROZEN) §9 **A12**. Bu ek, G3'ün
> tasarımını + karar/dil kurallarını dondurur. **İlk koşu POST-OUTCOME/keşifseldir**
> (sonuç görülerek yazıldı); bu ek, f*-sweep + duyarlılık-ızgarası + çift-kriter +
> karar-kurallarını **PRE-OUTCOME** olarak sabitler ki tekrar-koşular ve yorumlar
> disiplinli kalsın. Danışman v2.13 tasarım-onayı.

## 1. Hipotez (H_G3)

Her müşterinin KENDİ tüketimine göre optimal (grid-kör, net-zero) PV kararı, gerçek
bir dağıtım fiderinde toplandığında gerilim/termal limitleri aşabilir — ve bu aşımın
olup olmayacağı **fider-bağımlıdır ve bina-ölçeğinde KARAR-VERİLEMEZ**. Her müşterinin
sayısı bina-ölçeğinde geçerlidir; agregatın geçerliliği yalnız fider-ölçekli simülasyonla
bilinir. Bu, GFP ölçek-geçerliliği alanının koruduğu "right number, wrong scale"
olgusunun ENJEKTE-EDİLMEMİŞ saha-benzeri kanıtıdır (G4 enjeksiyon-yeteneğinin tamamlayıcısı).

**Falsifiye:** Hiçbir fiderde makul oversize (≤~1.6×) aralığında ihlal olmasaydı VEYA
tüm fiderler aynı eşikte ihlal etseydi (fider-bağımsız), H_G3 çürürdü.

## 2. Veri & model (donmuş)

- **Fiderler = 6 SimBench LV kodunun TAMAMI** (`1-LV-{rural1,rural2,rural3,semiurb4,semiurb5,urban6}--1-sw`)
  — **census, seçim YOK** (cherry-picking itirazı kapalı). simbench 1.6.2, pandapower 3.4.0.
- **Yerleşik SimBench TÜM DER (sgen + storage + gen) SIFIRLANIR** — rural1'de ~468 kW
  sgen + 4 storage (~150 kW). **[DENETİM-DÜZELTMESİ G3-V1, danışman v2.13.9]:** ilk koşu
  yalnız sgen'i sıfırlıyordu; storage kontaminasyonu güç-dengesini bozup rural1 trafosunu
  sahte %155 (f*_traf sahte 0.23) yapıyordu. Storage+gen sıfırlanınca güç-dengesi ≈0 ve
  rural1 trafo %64 (f*_traf 1.50) — sahte "dramatik aykırı-değer" kayboldu.
- **Boyutlama BİRİNCİL = net-zero** (`sizing.demand_to_kwp` = yıllık_kWh / specific_yield;
  grid-kör). Gerekçe: TR net-mahsup + sözleşme-gücü ile içsel-rasyonel, muhafazakâr.
  Yıllık kWh, SimBench BDEW profil zaman-serisinden (15-dk ∫). Agresif kurala geçiş YOK
  ("tuned" damgası) — bunun yerine f*-sweep tek duyarlılık.
- **İşletim-noktası BİRİNCİL:** yük ×0.20 (EPRI min-daytime-load konvansiyonu; %20
  aralık-ortası, "standart" DEĞİL) × PV-tepe 0.85 (açık-gökyüzü öğle). ext_grid
  slack = 1.025 pu (SimBench teslim gerilimi).
- **Terminoloji:** SimBench LV yükleri "müşteri/bağlantı-noktası"dır (hane DEĞİL —
  1.5–41.6 MWh/yıl ticari/tarımsal içerir). **BESS YOK** (çıplak PV; öğle-tepesinde
  batarya zaten dolu, Moshövel 2015 — kapsam-adlandırma).

## 3. Çift kriter + termal (donmuş)

| Kanal | Eşik | Slack-bağımlılığı |
|---|---|---|
| **voltage_rise_dV3pct** (BİRİNCİL) | ΔV = max_bus(V_pv − V_base) > **%3** [VDE-AR-N 4105] | **slack/tap-BAĞIMSIZ** |
| voltage_abs_EN50160 (İKİNCİL) | Vmax > **1.05** pu @ teslim-slack [EN 50160] | slack-BAĞIMLI |
| trafo_overload | trafo yüklenme > **%100** | slack-bağımsız |
| line_overload | hat yüklenme > **%100** | slack-bağımsız |

**KARAR KURALI (PRE-OUTCOME):** Manşet = **slack-bağımsız kanallar** (ΔV + trafo).
`voltage_abs_EN50160` İKİNCİL raporlanır ve **baz-gerilim confound'u AÇIKÇA beyan
edilir** (bkz. §5: rural1 bazı PV'siz 1.048 — mutlak-ihlali kısmen tap/slack-kaynaklı;
ΔV bunu de-confound eder). Hiçbir slack-koşullu sayı tek-manşet yapılmaz.

## 4. Metrik (donmuş)

- **Birincil (kesikli):** kanal-başına doğrudan ihlal @ f=1 (gerçek net-zero yerleşim) + severity.
- **Birincil (sürekli): kritik ölçekleme faktörü f\*** = gerçek yerleşim × f'in ilgili
  kanalı ilk-ihlal ettiği f (bisection, tol 0.02, f_hi 5.0). f*<1 → net-zero zaten ihlal;
  f*=None → 5×'e kadar ihlal yok. **uniform-hosting-aşımı KULLANILMAZ** (non-uniform
  agregatta tutarsız — semiurb4 yerleşim-inversiyonuyla kanıtlı).
- **Uzamsal-yoğunlaşma alt-bulgusu** (semiurb4: agregat uniform-hosting altında AMA ihlal)
  POZİTİF adlandırılır: "sadece toplam MW değil, KONUM da önemli".

## 5. Duyarlılık ızgarası (PRE-OUTCOME)

{yük 0.10, 0.20, 0.30} × {slack 1.000, 1.025} — 6 hücre; her hücrede kanal-ihlal + ΔV/vmax/trafo.
Amaç: birincil işletim-noktasının (0.20/1.025) sonucu bu ızgarada bağlam kazanır;
slack=1.000 sütunu mutlak-kriterin slack-bağımlılığını şeffaflaştırır.

## 6. Bilinen sınırlar (Limitations — donmuş)

- **Storage-kontaminasyon confound'u (G3-V1, ÇÖZÜLDÜ):** ilk koşuda yalnız sgen
  sıfırlanmış, SimBench storage'ı (rural1'de ~150 kW) baz gerilimi 1.048'e yükseltip
  mutlak-ihlali+f*_traf'ı ŞİŞİRİYORDU. Tüm-DER-sıfırlamayla çözüldü; güç-dengesi denetimi
  (ext+sgen−load−kayıp≈0) standart CI-kontrolü olarak korunur. Düzeltilmiş rural1: temiz
  baz ~1.02, vmax@f1 1.042 (ihlal yok). **Ders:** mutlak-EN50160 slack/baz-durumuna duyarlı;
  slack-bağımsız ΔV birincil olduğu için manşet güvenli — metodoloji-vitrini.
- Tek-instant (öğle) analizi; 8760-saat kronolojik değil. BESS/eğri-kısma yok.
- Net-zero tek boyutlama-kuralı (f*-sweep bunu oversize eksenine genişletir).
- SimBench Alman fiderleri (TR-adaptasyonu değil) — dış-geçerlilik notu.

## 7. Donmuş dosya + parametreler

| Öğe | Değer |
|---|---|
| `g3_cross_scale.py` SHA-256 (G3-V1 storage-fix + G3-R7 invariant sonrası) | `2fa512f91385f1368bc6884e043c9ab849447672ef60b597aec120ef4399fee1` |

**G3-R7 (güç-dengesi invariant, danışman v2.13.10):** `_solve` her çözümde
`ext+sgen−load−(hat+trafo kaybı)` mutlak değerini üretimin %1'iyle karşılaştırır, aşarsa
AssertionError — yerleşik-DER sızıntısı (G3-V1) bir daha sessizce geçemez.

**Yük×slack ızgarası stabilite (v3-nihai, zorunlu-kontrol GEÇTİ):** f*_ΔV yük-faktörü
{0.10,0.20,0.30} boyunca ±0.03 stabil (ΔV yükten ~bağımsız); tüm fider+yük MAX f*_ΔV=**1.58**;
semiurb4 hep net-zero altında (0.86-0.88). Net-zero ΔV-ihlal sayısı 6-hücrenin hepsinde 1/6
(sabit). → marjinal hikaye kırılgan DEĞİL.
| V_ABS_UPPER / DV_LIMIT / THERMAL | 1.05 pu / 0.03 / %100 |
| LOAD_FACTOR / PV_PEAK_FACTOR / SLACK | 0.20 / 0.85 / 1.025 |
| f* bisection tol / f_hi | 0.02 / 5.0 |

Bu ekten sonra tasarım/kriter/metrik değişmez (yalnız ana §9 Amendment Log ile).
