# A26 — Scale-assertion coding: codebook (FROZEN before sampling)

## 1. Purpose and scope

You code **at which spatial scale a sentence speaks**, not whether its number is
correct. There is no judgement of correctness, fabrication, or plausibility.

## 2. What you see

For each item: the user's **question** (context only) and **one sentence** from an
answer. You do not see neighbouring sentences, the model, the experimental arm, or any
automatic label. Expect about 20–30 seconds per item. Items are in random order;
Turkish questions come with Turkish sentences, English with English.

Use the question only to resolve references inside the sentence ("this system",
"bu sistem", "your home" → the installation the question is about). Do not infer a scale
the sentence itself does not assert.

Some items are short fragments left by sentence splitting, such as a list number ("4.")
or a bare value ("2.100 kWh"). A fragment asserts no scale: code all three scale
variables N.

## 3. Variables and definitions

Code each of the five variables Y or N. More than one scale may be Y. Fill in every
scale and aggregation cell. You may leave `unsure_YN` blank when you are sure; a blank
there counts as N.

| Variable | Y when the sentence asserts something about … | Cues (TR / EN) |
|---|---|---|
| `scale_building_YN` | one installation: a single home, flat, roof, business, factory, or "the system" in the question | eviniz, çatınız, bu sistem, 5 kW'lık kurulum, işletmeniz, hane başına; your home, your roof, this system, per household |
| `scale_multi_feeder_YN` | several buildings, a street, a neighbourhood, a feeder, a transformer, a region, or a grid quantity | tüm evler, N hane, mahalle, fider, trafo, bölge, şebeke kapasitesi, hosting kapasitesi, penetrasyon; all homes, 40 flats, neighbourhood, feeder, transformer, hosting capacity, penetration |
| `scale_policy_YN` | a national, provincial, or programme level: incentive budgets, state cost, regulation | ulusal, Türkiye genelinde, teşvik bütçesi, devlete maliyeti, program; nationwide, incentive budget, cost to the state, programme |
| `aggregation_YN` | a per-building quantity is multiplied or generalised to many units | "hane başına 5.000 TL → 40 ev 200.000 TL", "tüm 30 eve kurulursa …", "if all 40 homes …" |
| `unsure_YN` | you cannot decide | — |

If no scale is asserted (a general price, a rate, a date, an explanation of method),
all three scale variables are N ("none").

## 4. Decision rules

a. **Several scales are allowed.** "Hanenizde 5 kW, fiderde toplam 200 kW" →
   building Y and multi/feeder Y.
b. **Code the claim, not the word.** A grid word does not make a sentence feeder-scale.
   "Şebekeden alacağınız enerji 2.100 kWh'e düşer" is about the household's import:
   building Y, multi/feeder N.
c. **`aggregation_YN` = Y only** when a per-building quantity is multiplied or generalised
   across several units. A feeder quantity simply stated (a feeder voltage) is
   multi/feeder Y, aggregation N.
d. **When in doubt**: all scale variables N and `unsure_YN` = Y.
e. **The unit does not decide the scale.** TL, kWh, kW, or % can appear at any scale.
f. **Ratios and percentages** may have no scale (e.g. "iç verim oranı %19").

## 5. Worked examples (development corpus, not from the experiment)

| # | Sentence | building | multi/feeder | policy | aggregation |
|---|---|---|---|---|---|
| 1 | Antalya'daki eviniz için 3.3 kW sistem öneriyorum. | Y | N | N | N |
| 2 | Şebekeden alacağınız enerji yıllık 2.100 kWh'e düşer; şebekeye 3.450 kWh satış yaparsınız. *(rule b)* | Y | N | N | N |
| 3 | Fider üzerinde gerilim 0,968–1,043 pu bandında kalıyor; sınır ihlali yok. | N | Y | N | N |
| 4 | Tüm 30 eve kurulursa mahalle geneli tasarruf 21.676 TL üzerinden katlanır. | N | Y | N | Y |
| 5 | Bu politikanın devlete maliyeti 53.550 TL; kaldıraç 3,3. | N | N | Y | N |
| 6 | Neighbourhood-wide, 7,300 kWh of production per household eases the grid. *(boundary: per-household value generalised)* | Y | Y | N | Y |
| 7 | The net present value is roughly 220 thousand TL; the internal rate of return is 19%. *(boundary: no scale asserted)* | N | N | N | N |
| 8 | Hosting capacity is 55% — the upper limit that can be safely connected on this feeder. | N | Y | N | N |

## 6. Do not

- Guess what neighbouring sentences or the model said.
- Judge whether the number is right, plausible, or traceable.
- Force consistency with earlier items about the same question.

## 7. Disagreements

The A18 rule applies. After both sheets are submitted and hashed, disagreements are
settled in a joint session. A code may change only when a specific clause of this
codebook is cited. There is no author authority. If no clause can be cited, the
tie-break is the conservative one: all scale variables N.

## 8. Version

A26 / prereg-v3.2. The SHA-256 of this file is recorded in PREREGISTRATION §9 A26.
