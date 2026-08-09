# Ragas report — findability-api `/ask`

Judge: `claude-haiku-4-5` via `langchain-anthropic`. Embeddings for answer relevancy: `gemini-embedding-2`, the same model the corpus is indexed with. Both reuse keys the service already holds — no new accounts.

Samples: 28 answerable golden entries scored on the four metrics; all 34 answers (including 6 out-of-corpus questions) classified refused/answered.

## Metric means (answerable entries)

| metric | mean |
| --- | --- |
| faithfulness | 0.7044 |
| answer_relevancy | 0.7589 |
| context_precision | 0.7798 |
| context_recall | 0.9643 |

## Refusal behaviour (all 34 entries)

Measured in both directions on purpose: a service that refuses everything would score 100% on "did it refuse the out-of-corpus questions" alone.

| | refused | answered |
| --- | --- | --- |
| **should refuse** (6) | 6 | 0 |
| **should answer** (28) | 0 | 28 |

- Refusal accuracy (out-of-corpus correctly declined): **6/6 = 100.0%**
- False-refusal rate (answerable wrongly declined): **0/28 = 0.0%**
- Citations on refusals: 4/6 = 66.7% returned none (an unsourced refusal is the correct shape).

## Three weakest entries

### g18 (direct, zh) — faithfulness 0.000, answer_relevancy 0.747, context_precision 1.000, context_recall 1.000

**Q** 他在建筑设计院实习过吗？那段时间具体负责哪些工作？

**Expected citations** `thu-adri` — **retrieved** `thu-adri, haptic-navigation-research, hxvp-marketing-group, start-me-up, spatial-pixel-lab` — **cited** `thu-adri`

**Answer** 是的，Jerry 在清华大学建筑设计研究院担任过助理建筑师实习生，时间是 2024 年 7 月至 11 月。他主要负责两方面工作：第一，使用 Rhino 和 Grasshopper 编写脚本进行日照分析和人流动线分析，这些分析结果为 3 个总体规划和 4 个体量方案的学术建筑项目提供了设计决策依据；第二，在 20 多张 CAD 审查图纸中处理了 15 项以上的规范和无障碍条款，并将施工图协调中的冲突减少了约 25%。

### g22 (cross, en) — faithfulness 0.167, answer_relevancy 0.653, context_precision 0.500, context_recall 1.000

**Q** His current job and one of the projects on the site both seem to be about the same studio platform — how do the two connect?

**Expected citations** `hxvp-marketing-group, hxvp` — **retrieved** `hxvp, hxvp-marketing-group, ikon-pass-japan, spatial-pixel-lab, haptic-navigation-research` — **cited** `hxvp, hxvp-marketing-group`

**Answer** Jerry's current role at HXVP Marketing Group is as an AI Solutions Engineer embedded at a film production studio, where he owned the complete 0→1 rebuild of its operations platform. That rebuild is the HXVP Studio Portal project featured on his portfolio. He authored the product requirements, shipped four role-based portals in React, turned the designer's Figma frames into the prototype the backend engineer used as a living API spec, and drove nine-plus releases in four weeks on an AI-assisted workflow. The job entry describes the work; the project entry showcases the delivered system with a walkthrough of its full production cycle.

### g12 (direct, en) — faithfulness 0.231, answer_relevancy 0.657, context_precision 1.000, context_recall 1.000

**Q** Where is he working right now, and what did he own in that role?

**Expected citations** `hxvp-marketing-group` — **retrieved** `hxvp-marketing-group, haptic-navigation-research, start-me-up, thu-adri, hxvp` — **cited** `hxvp-marketing-group`

**Answer** Jerry is currently working as an AI Solutions Engineer at HXVP Marketing Group in Dallas and New York. In this role, he owned the complete 0-to-1 rebuild of the studio's operations platform. He authored the product requirements document and shipped four role-based portals—for production, client, talent, and crew—to live public deployment. He turned Figma designs into a high-fidelity React 19 prototype that served as the living specification for the backend team, audited nearly 290 API endpoints in the legacy Django backend, and automated talent-booking and crew-scheduling workflows. His AI-assisted development process enabled stakeholder requests to ship to production within days, delivering more than nine releases in four weeks.


## Per entry

| id | cat | lang | faith. | ans.rel. | ctx.prec. | ctx.rec. | refused | cited |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| g01 | direct | en | 1.000 | 0.845 | 1.000 | 1.000 | no | hxvp |
| g02 | direct | en | 1.000 | 0.726 | 1.000 | 1.000 | no | hxvp |
| g03 | direct | en | 1.000 | 0.851 | 1.000 | 1.000 | no | hxvp |
| g04 | direct | zh | 0.588 | 0.651 | 1.000 | 1.000 | no | hxvp, hxvp-marketing-group |
| g05 | direct | en | 0.700 | 0.835 | 1.000 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g06 | direct | en | 0.600 | 0.835 | 0.833 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g07 | direct | en | 0.889 | 0.638 | 1.000 | 1.000 | no | social-rhythm, spatial-pixel-lab |
| g08 | direct | en | 1.000 | 0.683 | 1.000 | 1.000 | no | social-rhythm |
| g09 | direct | en | 0.375 | 0.651 | 1.000 | 1.000 | no | floralink |
| g10 | direct | en | 0.778 | 0.607 | 1.000 | 1.000 | no | heartwhisper |
| g11 | direct | en | 0.636 | 0.905 | 1.000 | 1.000 | no | belt-for-the-blind |
| g12 | direct | en | 0.231 | 0.657 | 1.000 | 1.000 | no | hxvp-marketing-group |
| g13 | direct | en | 0.667 | 0.710 | 0.500 | 1.000 | no | hxvp-marketing-group |
| g14 | direct | zh | 0.875 | 0.661 | 1.000 | 1.000 | no | hxvp-marketing-group |
| g15 | direct | en | 0.500 | 0.890 | 1.000 | 1.000 | no | spatial-pixel-lab, social-rhythm |
| g16 | direct | en | 0.900 | 0.795 | 1.000 | 1.000 | no | start-me-up |
| g17 | direct | en | 1.000 | 0.837 | 1.000 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g18 | direct | zh | 0.000 | 0.747 | 1.000 | 1.000 | no | thu-adri |
| g19 | direct | en | 1.000 | 0.885 | 1.000 | 1.000 | no | ascii-motion-jellyfish |
| g20 | direct | en | 0.778 | 0.730 | 1.000 | 1.000 | no | ikon-atlas, ikon-pass-japan |
| g21 | direct | en | 0.875 | 0.729 | 1.000 | 1.000 | no | findability |
| g22 | cross | en | 0.167 | 0.653 | 0.500 | 1.000 | no | hxvp, hxvp-marketing-group |
| g23 | cross | en | 0.750 | 0.754 | 1.000 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g24 | cross | en | 0.538 | 0.769 | 0.000 | 1.000 | no | spatial-pixel-lab, social-rhythm |
| g25 | cross | en | 0.778 | 0.898 | 0.000 | 0.667 | no | belt-for-the-blind, social-rhythm |
| g26 | cross | en | 0.750 | 0.774 | 0.000 | 0.667 | no | floralink, heartwhisper |
| g27 | cross | en | 0.600 | 0.842 | 0.000 | 0.667 | no | belt-for-the-blind, heartwhisper |
| g28 | cross | zh | 0.750 | 0.691 | 0.000 | 1.000 | no | ikon-pass-japan, ikon-atlas |
| g29 | refusal | en | — | — | — | — | yes | — |
| g30 | refusal | zh | — | — | — | — | yes | heartwhisper |
| g31 | refusal | en | — | — | — | — | yes | — |
| g32 | refusal | en | — | — | — | — | yes | spatial-pixel-lab, ikon-pass-japan, haptic-navigation-research |
| g33 | refusal | en | — | — | — | — | yes | — |
| g34 | refusal | en | — | — | — | — | yes | — |
