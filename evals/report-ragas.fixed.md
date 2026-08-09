# Ragas report — findability-api `/ask`

Judge: `claude-haiku-4-5` via `langchain-anthropic`. Embeddings for answer relevancy: `gemini-embedding-2`, the same model the corpus is indexed with. Both reuse keys the service already holds — no new accounts.

Samples: 24 answerable golden entries scored on the four metrics; all 30 answers (including 6 out-of-corpus questions) classified refused/answered.

## Metric means (answerable entries)

| metric | mean |
| --- | --- |
| faithfulness | 0.7767 |
| answer_relevancy | 0.7763 |
| context_precision | 0.7292 |
| context_recall | 0.9444 |

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

### g04 (direct, en) — faithfulness 0.250, answer_relevancy 0.816, context_precision 1.000, context_recall 1.000

**Q** How did he build the wearable that gives directions through vibration?

**Expected citations** `haptic-atlas` — **retrieved** `haptic-atlas, belt-for-the-blind, haptic-navigation-research, social-rhythm` — **cited** `haptic-atlas, haptic-navigation-research`

**Answer** Jerry built the Haptic Atlas wearable navigation system using Arduino microcontrollers and vibration motors, connected to a custom iOS app via Bluetooth LE. He developed a vocabulary of vibrotactile patterns that mapped to directional cues and proximity alerts. In his research role at Columbia GSAPP and Tsinghua, he constructed a prototype using Python and microcontrollers, creating a pipeline that converted geographic data from GIS and routing systems into vibrotactile feedback. He tested the system through hallway trials, measuring metrics like latency, jitter, and accuracy, and delivered supporting UI components in Figma alongside test scripts.

### g08 (direct, en) — faithfulness 0.250, answer_relevancy 0.650, context_precision 1.000, context_recall 1.000

**Q** Who did he collaborate with on the plant-based neighborhood game, and which part did he handle himself?

**Expected citations** `floralink` — **retrieved** `floralink, haptic-atlas, spatial-pixel-lab, haptic-navigation-research` — **cited** `floralink`

**Answer** On FloraLink, Jerry collaborated with Xiaotong Qin under the mentorship of Ruby Wu. Jerry himself handled the sociological research, game mechanism design, drawings, and model making. The project ran from December 2023 through November 2024.

### g13 (direct, en) — faithfulness 0.400, answer_relevancy 0.877, context_precision 1.000, context_recall 1.000

**Q** What technical setup issues were logged on the two-player hand-tracking prototype at SVA, and what deliverables documented it?

**Expected citations** `spatial-pixel-lab` — **retrieved** `spatial-pixel-lab, social-rhythm, haptic-atlas, haptic-navigation-research` — **cited** `spatial-pixel-lab`

**Answer** At the Spatial Pixel Lab at SVA, Jerry logged three categories of technical issues on the two-player hand-tracking prototype: low-lumen conditions, occlusion problems, and interaction-latency challenges. To document the setup and findings, he produced a 90-second demo video and a one-page specification. He also drafted a mitigation roadmap addressing these issues and calibrated both the projector-to-wall and corner-wall configurations during development.


## Per entry

| id | cat | lang | faith. | ans.rel. | ctx.prec. | ctx.rec. | refused | cited |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| g01 | direct | en | 1.000 | 0.867 | 1.000 | 1.000 | no | hxvp |
| g02 | direct | en | 0.833 | 0.784 | 1.000 | 1.000 | no | hxvp |
| g03 | direct | en | 1.000 | 0.832 | 1.000 | 1.000 | no | hxvp |
| g04 | direct | en | 0.250 | 0.816 | 1.000 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g05 | direct | en | 0.917 | 0.874 | 1.000 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g06 | direct | en | 1.000 | 0.724 | 1.000 | 1.000 | no | social-rhythm |
| g07 | direct | en | 0.800 | 0.720 | 1.000 | 1.000 | no | social-rhythm |
| g08 | direct | en | 0.250 | 0.650 | 1.000 | 1.000 | no | floralink |
| g09 | direct | en | 1.000 | 0.637 | 1.000 | 1.000 | no | heartwhisper |
| g10 | direct | en | 0.778 | 0.796 | 1.000 | 1.000 | no | belt-for-the-blind |
| g11 | direct | en | 1.000 | 0.885 | 1.000 | 1.000 | no | ascii-motion-jellyfish |
| g12 | direct | en | 0.889 | 0.811 | 1.000 | 1.000 | no | ikon-atlas, ikon-pass-japan |
| g13 | direct | en | 0.400 | 0.877 | 1.000 | 1.000 | no | spatial-pixel-lab |
| g14 | direct | en | 0.800 | 0.807 | 0.500 | 1.000 | no | haptic-navigation-research |
| g15 | direct | en | 0.643 | 0.802 | 0.500 | 1.000 | no | haptic-navigation-research |
| g16 | direct | en | 0.857 | 0.739 | 1.000 | 1.000 | no | start-me-up |
| g17 | direct | zh | 0.692 | 0.666 | 1.000 | 1.000 | no | hxvp |
| g18 | direct | zh | 1.000 | 0.755 | 1.000 | 1.000 | no | thu-adri |
| g19 | cross | en | 0.500 | 0.686 | 0.500 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g20 | cross | en | 0.714 | 0.660 | 0.000 | 0.333 | no | belt-for-the-blind |
| g21 | cross | en | 0.857 | 0.902 | 0.000 | 0.333 | yes | belt-for-the-blind |
| g22 | cross | en | 0.462 | 0.824 | 0.000 | 1.000 | no | spatial-pixel-lab, social-rhythm |
| g23 | cross | en | 1.000 | 0.846 | 0.000 | 1.000 | no | floralink, heartwhisper |
| g24 | cross | zh | 1.000 | 0.671 | 0.000 | 1.000 | no | ikon-pass-japan, ikon-atlas |
| g25 | refusal | en | — | — | — | — | yes | — |
| g26 | refusal | en | — | — | — | — | yes | — |
| g27 | refusal | en | — | — | — | — | yes | — |
| g28 | refusal | en | — | — | — | — | yes | spatial-pixel-lab, haptic-navigation-research, haptic-atlas, ikon-pass-japan |
| g29 | refusal | en | — | — | — | — | yes | belt-for-the-blind, spatial-pixel-lab, thu-adri, heartwhisper |
| g30 | refusal | zh | — | — | — | — | yes | heartwhisper |
