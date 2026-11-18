# A8 — WITHDRAWN (never run)

**Statü (2026-07-09):** A8 (guard canlı-bloklarının insan-precision doğrulaması)
GERİ ÇEKİLDİ ve HİÇ KOŞULMADI. Bkz. `PREREGISTRATION.md` §9 **A11** + `SCIENTIFIC_REVIEW.md` v2.12.

**Neden:** Kullanıcı elle-kodlamayı denedi; simülasyon çıktılarını (NPV/IRR/gerilim)
elle doğrulamak imkânsız, gerçek model-hataları yok denecek kadar az, guard minik
artefaktları (P50→"50") işaretliyor. Otomatik canlı-flag taksonomisi
(`../analyze_guard_flag_taxonomy.py`) bunu kanıtladı: 696 flag'in ~%20'si zaten doğru
sayı (guard FP), ~%50'si değer-eşleştirmeyle çözülemeyen (meşru format-farkları dahil).

**Sonuç:** "Guard N canlı uydurma yakaladı" iddiası desteklenemez → gate iddiasıyla
birlikte düştü (prereg-ihlali değil). Guard'ın değeri **G4** (kontrollü enjeksiyon,
kendi-doğrulayan) + G1 mekanistik ayrıştırmaya dayanır. Bu klasördeki materyaller
(kodkitabı, sheet, guard-key, HTML araç) hash-kayıtlı olarak KALIR ama kullanılmaz.
