# Ragas report — findability-api `/ask`

Judge: `claude-haiku-4-5` via `langchain-anthropic`. Embeddings for answer relevancy: `gemini-embedding-2`, the same model the corpus is indexed with. Both reuse keys the service already holds — no new accounts.

Samples: 24 answerable golden entries scored on the four metrics; all 30 answers (including 6 out-of-corpus questions) classified refused/answered.

## Metric means (answerable entries)

| metric | mean |
| --- | --- |
| faithfulness | 0.7013 |
| answer_relevancy | 0.7870 |
| context_precision | 0.7292 |
| context_recall | 0.9722 |

## Refusal behaviour (all 30 entries)

Measured in both directions on purpose: a service that refuses everything would score 100% on "did it refuse the out-of-corpus questions" alone.

| | refused | answered |
| --- | --- | --- |
| **should refuse** (6) | 6 | 0 |
| **should answer** (24) | 0 | 24 |

- Refusal accuracy (out-of-corpus correctly declined): **6/6 = 100.0%**
- False-refusal rate (answerable wrongly declined): **0/24 = 0.0%**
- Citations on refusals: 5/6 = 83.3% returned none (an unsourced refusal is the correct shape).

## Three weakest entries

### g18 (direct, zh) — faithfulness 0.000, answer_relevancy 0.769, context_precision 1.000, context_recall 1.000

**Q** 他在建筑设计院实习过吗？那段时间具体负责哪些工作？

**Expected citations** `thu-adri` — **retrieved** `thu-adri, haptic-navigation-research, spatial-pixel-lab, start-me-up, belt-for-the-blind` — **cited** `thu-adri`

**Answer** 是的，Jerry 在清华大学建筑设计研究院担任过助理建筑师实习生，时间是 2024 年 7 月到 11 月，地点在北京。他主要负责两方面工作：一是用 Rhino/Grasshopper 脚本为学术建筑进行日照和人流分析，交付了 3 套总体规划方案和 4 套体量选项；二是制作了 20 多张 CAD 审查图纸，解决了 15 项以上的规范和无障碍问题，使施工图协调冲突减少了约 25%。

### g13 (direct, en) — faithfulness 0.182, answer_relevancy 0.873, context_precision 1.000, context_recall 1.000

**Q** What technical setup issues were logged on the two-player hand-tracking prototype at SVA, and what deliverables documented it?

**Expected citations** `spatial-pixel-lab` — **retrieved** `spatial-pixel-lab, social-rhythm, haptic-atlas, haptic-navigation-research, floralink` — **cited** `spatial-pixel-lab`

**Answer** Jerry logged low-lumen, occlusion, and interaction-latency issues during the two-player hand-tracking prototype at SVA's Spatial Pixel Lab. He documented these technical challenges and drafted a mitigation roadmap to address them. The deliverables included a 90-second demo video and a one-page spec that captured the setup and findings. Additionally, he calibrated the projector–wall and corner-wall configurations to support the dual-view alignment and gesture detection system.

### g08 (direct, en) — faithfulness 0.250, answer_relevancy 0.653, context_precision 1.000, context_recall 1.000

**Q** Who did he collaborate with on the plant-based neighborhood game, and which part did he handle himself?

**Expected citations** `floralink` — **retrieved** `floralink, haptic-atlas, spatial-pixel-lab, haptic-navigation-research, social-rhythm` — **cited** `floralink`

**Answer** On FloraLink, the plant-based neighborhood game, Jerry collaborated with Xiaotong Qin and was mentored by Ruby Wu. Jerry handled the sociological research, designed the game mechanism, created drawings, and built models. The project ran from December 2023 through November 2024.


## Per entry

| id | cat | lang | faith. | ans.rel. | ctx.prec. | ctx.rec. | refused | cited |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| g01 | direct | en | 0.692 | 0.844 | 1.000 | 1.000 | no | hxvp |
| g02 | direct | en | 1.000 | 0.794 | 1.000 | 1.000 | no | hxvp |
| g03 | direct | en | 1.000 | 0.840 | 1.000 | 1.000 | no | hxvp |
| g04 | direct | en | 0.375 | 0.841 | 1.000 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g05 | direct | en | 0.583 | 0.887 | 1.000 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g06 | direct | en | 1.000 | 0.724 | 1.000 | 1.000 | no | social-rhythm |
| g07 | direct | en | 1.000 | 0.712 | 1.000 | 1.000 | no | social-rhythm |
| g08 | direct | en | 0.250 | 0.653 | 1.000 | 1.000 | no | floralink |
| g09 | direct | en | 1.000 | 0.686 | 1.000 | 1.000 | no | heartwhisper |
| g10 | direct | en | 0.700 | 0.796 | 1.000 | 1.000 | no | belt-for-the-blind |
| g11 | direct | en | 1.000 | 0.885 | 1.000 | 1.000 | no | ascii-motion-jellyfish |
| g12 | direct | en | 0.750 | 0.752 | 1.000 | 1.000 | no | ikon-atlas, ikon-pass-japan |
| g13 | direct | en | 0.182 | 0.873 | 1.000 | 1.000 | no | spatial-pixel-lab |
| g14 | direct | en | 0.889 | 0.901 | 0.500 | 1.000 | no | haptic-navigation-research |
| g15 | direct | en | 0.500 | 0.785 | 0.500 | 1.000 | no | haptic-navigation-research |
| g16 | direct | en | 0.857 | 0.769 | 1.000 | 1.000 | no | start-me-up |
| g17 | direct | zh | 0.667 | 0.633 | 1.000 | 1.000 | no | hxvp |
| g18 | direct | zh | 0.000 | 0.769 | 1.000 | 1.000 | no | thu-adri |
| g19 | cross | en | 0.750 | 0.676 | 0.500 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g20 | cross | en | 0.562 | 0.818 | 0.000 | 0.667 | no | belt-for-the-blind, heartwhisper |
| g21 | cross | en | 1.000 | 0.913 | 0.000 | 0.667 | no | social-rhythm, belt-for-the-blind |
| g22 | cross | en | 0.308 | 0.820 | 0.000 | 1.000 | no | spatial-pixel-lab, social-rhythm |
| g23 | cross | en | 1.000 | 0.846 | 0.000 | 1.000 | no | floralink, heartwhisper |
| g24 | cross | zh | 0.765 | 0.674 | 0.000 | 1.000 | no | ikon-pass-japan, ikon-atlas |
| g25 | refusal | en | — | — | — | — | yes | — |
| g26 | refusal | en | — | — | — | — | yes | — |
| g27 | refusal | en | — | — | — | — | yes | — |
| g28 | refusal | en | — | — | — | — | yes | — |
| g29 | refusal | en | — | — | — | — | yes | — |
| g30 | refusal | zh | — | — | — | — | yes | heartwhisper |
