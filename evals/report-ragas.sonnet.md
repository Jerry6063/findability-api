# Ragas report — findability-api `/ask`

Judge: `claude-sonnet-4-5` via `langchain-anthropic`. Embeddings for answer relevancy: `gemini-embedding-2`, the same model the corpus is indexed with. Both reuse keys the service already holds — no new accounts.

Samples: 24 answerable golden entries scored on the four metrics; all 30 answers (including 6 out-of-corpus questions) classified refused/answered.

## Metric means (answerable entries)

| metric | mean |
| --- | --- |
| faithfulness | 0.6749 |
| answer_relevancy | 0.7904 |
| context_precision | 0.7292 |
| context_recall | 0.9375 |

## Refusal behaviour (all 30 entries)

Measured in both directions on purpose: a service that refuses everything would score 100% on "did it refuse the out-of-corpus questions" alone.

| | refused | answered |
| --- | --- | --- |
| **should refuse** (6) | 6 | 0 |
| **should answer** (24) | 1 | 23 |

- Refusal accuracy (out-of-corpus correctly declined): **6/6 = 100.0%**
- False-refusal rate (answerable wrongly declined): **1/24 = 4.2%**
- Citations on refusals: 3/6 = 50.0% returned none (an unsourced refusal is the correct shape).

## Three weakest entries

### g18 (direct, zh) — faithfulness 0.000, answer_relevancy 0.781, context_precision 1.000, context_recall 1.000

**Q** 他在建筑设计院实习过吗？那段时间具体负责哪些工作？

**Expected citations** `thu-adri` — **retrieved** `thu-adri, haptic-navigation-research, spatial-pixel-lab, start-me-up` — **cited** `thu-adri`

**Answer** Yes, Jerry interned as an Assistant Architect at the Architectural Design and Research Institute at Tsinghua University in Beijing from July to November 2024. During that time, he scripted Rhino and Grasshopper solar and circulation analyses for academic buildings, delivering three master plans and four massing options. He also produced over twenty CAD review sheets and closed more than fifteen code and access items, reducing coordination clashes in construction documents by approximately twenty-five percent.

### g08 (direct, en) — faithfulness 0.143, answer_relevancy 0.710, context_precision 1.000, context_recall 1.000

**Q** Who did he collaborate with on the plant-based neighborhood game, and which part did he handle himself?

**Expected citations** `floralink` — **retrieved** `floralink, haptic-atlas, spatial-pixel-lab, haptic-navigation-research` — **cited** `floralink`

**Answer** On FloraLink, Jerry collaborated with Xiaotong Qin under the mentorship of Ruby Wu. Jerry himself handled the sociological research, game mechanism design, drawings, and model making. The project ran from December 2023 through November 2024.

### g04 (direct, en) — faithfulness 0.182, answer_relevancy 0.841, context_precision 1.000, context_recall 1.000

**Q** How did he build the wearable that gives directions through vibration?

**Expected citations** `haptic-atlas` — **retrieved** `haptic-atlas, belt-for-the-blind, haptic-navigation-research, social-rhythm` — **cited** `haptic-atlas, haptic-navigation-research`

**Answer** Jerry built the Haptic Atlas wearable navigation system using Arduino microcontrollers and vibration motors, connected to a custom iOS app via Bluetooth LE. He developed a vocabulary of vibrotactile patterns that mapped to directional cues and proximity alerts. In his research role at Columbia GSAPP and Tsinghua, he constructed a prototype using Python and microcontrollers, creating a pipeline that converted geographic data from GIS and routing systems into vibrotactile feedback. He tested the system through hallway trials, measuring metrics like latency, jitter, and accuracy, and delivered supporting UI components in Figma alongside test scripts.


## Per entry

| id | cat | lang | faith. | ans.rel. | ctx.prec. | ctx.rec. | refused | cited |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| g01 | direct | en | 0.429 | 0.841 | 1.000 | 1.000 | no | hxvp |
| g02 | direct | en | 0.667 | 0.801 | 1.000 | 1.000 | no | hxvp |
| g03 | direct | en | 1.000 | 0.832 | 1.000 | 1.000 | no | hxvp |
| g04 | direct | en | 0.182 | 0.841 | 1.000 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g05 | direct | en | 1.000 | 0.874 | 1.000 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g06 | direct | en | 1.000 | 0.725 | 1.000 | 1.000 | no | social-rhythm |
| g07 | direct | en | 0.800 | 0.697 | 1.000 | 1.000 | no | social-rhythm |
| g08 | direct | en | 0.143 | 0.710 | 1.000 | 1.000 | no | floralink |
| g09 | direct | en | 1.000 | 0.655 | 1.000 | 1.000 | no | heartwhisper |
| g10 | direct | en | 0.750 | 0.790 | 1.000 | 1.000 | no | belt-for-the-blind |
| g11 | direct | en | 1.000 | 0.925 | 1.000 | 1.000 | no | ascii-motion-jellyfish |
| g12 | direct | en | 0.875 | 0.843 | 1.000 | 1.000 | no | ikon-atlas, ikon-pass-japan |
| g13 | direct | en | 0.400 | 0.877 | 1.000 | 1.000 | no | spatial-pixel-lab |
| g14 | direct | en | 0.800 | 0.849 | 0.500 | 1.000 | no | haptic-navigation-research |
| g15 | direct | en | 0.444 | 0.832 | 0.500 | 1.000 | no | haptic-navigation-research |
| g16 | direct | en | 0.857 | 0.753 | 1.000 | 1.000 | no | start-me-up |
| g17 | direct | zh | 0.500 | 0.612 | 1.000 | 1.000 | no | hxvp |
| g18 | direct | zh | 0.000 | 0.781 | 1.000 | 1.000 | no | thu-adri |
| g19 | cross | en | 0.471 | 0.720 | 0.500 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g20 | cross | en | 0.714 | 0.831 | 0.000 | 0.250 | no | belt-for-the-blind |
| g21 | cross | en | 1.000 | 0.901 | 0.000 | 0.250 | yes | belt-for-the-blind |
| g22 | cross | en | 0.444 | 0.837 | 0.000 | 1.000 | no | spatial-pixel-lab, social-rhythm |
| g23 | cross | en | 0.875 | 0.837 | 0.000 | 1.000 | no | floralink, heartwhisper |
| g24 | cross | zh | 0.846 | 0.606 | 0.000 | 1.000 | no | ikon-pass-japan, ikon-atlas |
| g25 | refusal | en | — | — | — | — | yes | — |
| g26 | refusal | en | — | — | — | — | yes | — |
| g27 | refusal | en | — | — | — | — | yes | — |
| g28 | refusal | en | — | — | — | — | yes | spatial-pixel-lab, haptic-navigation-research, haptic-atlas, ikon-pass-japan |
| g29 | refusal | en | — | — | — | — | yes | belt-for-the-blind, spatial-pixel-lab, thu-adri, heartwhisper |
| g30 | refusal | zh | — | — | — | — | yes | heartwhisper |
