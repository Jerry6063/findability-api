# Ragas report — findability-api `/ask`

Judge: `claude-haiku-4-5` via `langchain-anthropic`. Embeddings for answer relevancy: `gemini-embedding-2`, the same model the corpus is indexed with. Both reuse keys the service already holds — no new accounts.

Samples: 28 answerable golden entries scored on the four metrics; all 34 answers (including 6 out-of-corpus questions) classified refused/answered.

## Metric means (answerable entries)

| metric | mean |
| --- | --- |
| faithfulness | 0.8774 |
| answer_relevancy | 0.7282 |
| context_precision | 0.7798 |
| context_recall | 0.9762 |

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

### g09 (direct, en) — faithfulness 0.167, answer_relevancy 0.650, context_precision 1.000, context_recall 1.000

**Q** Who did he collaborate with on the plant-based neighborhood game, and which part did he handle himself?

**Expected citations** `floralink` — **retrieved** `floralink, spatial-pixel-lab, haptic-navigation-research, social-rhythm, haptic-atlas` — **cited** `floralink`

**Answer** He collaborated with Xiaotong Qin on FloraLink, the plant-based neighborhood game. Jerry handled the sociological research, game mechanism design, drawings, and model making.

### g22 (cross, en) — faithfulness 0.500, answer_relevancy 0.715, context_precision 0.500, context_recall 1.000

**Q** His current job and one of the projects on the site both seem to be about the same studio platform — how do the two connect?

**Expected citations** `hxvp-marketing-group, hxvp` — **retrieved** `hxvp, hxvp-marketing-group, ikon-pass-japan, spatial-pixel-lab, haptic-navigation-research` — **cited** `hxvp, hxvp-marketing-group`

**Answer** They are the same platform at different stages. Jerry embedded at HXVP Marketing Group to own the 0→1 rebuild of its operations system, and that rebuild — four role-based portals he designed and prototyped in React — became the HXVP Studio Portal project now live on his portfolio.

### g23 (cross, en) — faithfulness 0.500, answer_relevancy 0.682, context_precision 1.000, context_recall 1.000

**Q** He seems to have both a wearable navigation project and an ongoing research role in that same area — how do the two fit together?

**Expected citations** `haptic-navigation-research, haptic-atlas` — **retrieved** `haptic-atlas, haptic-navigation-research, belt-for-the-blind, spatial-pixel-lab, findability` — **cited** `haptic-atlas, haptic-navigation-research`

**Answer** Haptic Atlas is the v1 wearable prototype that launched the research program; the ongoing research role at Columbia GSAPP and Tsinghua leads that same program, which has since grown the wearable into a multi-motor haptic belt.


## Per entry

| id | cat | lang | faith. | ans.rel. | ctx.prec. | ctx.rec. | refused | cited |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| g01 | direct | en | 1.000 | 0.812 | 1.000 | 1.000 | no | hxvp |
| g02 | direct | en | 1.000 | 0.592 | 1.000 | 1.000 | no | hxvp |
| g03 | direct | en | 1.000 | 0.769 | 1.000 | 1.000 | no | hxvp |
| g04 | direct | zh | 1.000 | 0.727 | 1.000 | 1.000 | no | hxvp, hxvp-marketing-group |
| g05 | direct | en | 1.000 | 0.772 | 1.000 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g06 | direct | en | 0.833 | 0.776 | 0.833 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g07 | direct | en | 1.000 | 0.583 | 1.000 | 1.000 | no | social-rhythm |
| g08 | direct | en | 1.000 | 0.746 | 1.000 | 1.000 | no | social-rhythm |
| g09 | direct | en | 0.167 | 0.650 | 1.000 | 1.000 | no | floralink |
| g10 | direct | en | 1.000 | 0.701 | 1.000 | 1.000 | no | heartwhisper |
| g11 | direct | en | 0.667 | 0.897 | 1.000 | 1.000 | no | belt-for-the-blind |
| g12 | direct | en | 1.000 | 0.699 | 1.000 | 1.000 | no | hxvp-marketing-group |
| g13 | direct | en | 1.000 | 0.745 | 0.500 | 1.000 | no | hxvp-marketing-group |
| g14 | direct | zh | 0.857 | 0.605 | 1.000 | 1.000 | no | hxvp-marketing-group |
| g15 | direct | en | 0.750 | 0.878 | 1.000 | 1.000 | no | spatial-pixel-lab |
| g16 | direct | en | 0.800 | 0.782 | 1.000 | 1.000 | no | start-me-up |
| g17 | direct | en | 1.000 | 0.811 | 1.000 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g18 | direct | zh | 0.917 | 0.716 | 1.000 | 1.000 | no | thu-adri |
| g19 | direct | en | 1.000 | 0.729 | 1.000 | 1.000 | no | ascii-motion-jellyfish |
| g20 | direct | en | 1.000 | 0.626 | 1.000 | 1.000 | no | ikon-atlas, ikon-pass-japan |
| g21 | direct | en | 1.000 | 0.686 | 1.000 | 1.000 | no | findability |
| g22 | cross | en | 0.500 | 0.715 | 0.500 | 1.000 | no | hxvp, hxvp-marketing-group |
| g23 | cross | en | 0.500 | 0.682 | 1.000 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g24 | cross | en | 1.000 | 0.803 | 0.000 | 1.000 | no | spatial-pixel-lab, social-rhythm |
| g25 | cross | en | 1.000 | 0.666 | 0.000 | 0.667 | no | social-rhythm, belt-for-the-blind |
| g26 | cross | en | 0.909 | 0.628 | 0.000 | 1.000 | no | floralink, heartwhisper |
| g27 | cross | en | 0.833 | 0.865 | 0.000 | 0.667 | no | belt-for-the-blind, heartwhisper |
| g28 | cross | zh | 0.833 | — | 0.000 | 1.000 | no | ikon-pass-japan, ikon-atlas |
| g29 | refusal | en | — | — | — | — | yes | — |
| g30 | refusal | zh | — | — | — | — | yes | heartwhisper |
| g31 | refusal | en | — | — | — | — | yes | — |
| g32 | refusal | en | — | — | — | — | yes | spatial-pixel-lab, haptic-navigation-research |
| g33 | refusal | en | — | — | — | — | yes | — |
| g34 | refusal | en | — | — | — | — | yes | — |
