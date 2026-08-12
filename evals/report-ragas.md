# Ragas report — findability-api `/ask`

Judge: `claude-haiku-4-5` via `langchain-anthropic`. Embeddings for answer relevancy: `gemini-embedding-2`, the same model the corpus is indexed with. Both reuse keys the service already holds — no new accounts.

Samples: 30 answerable golden entries scored on the four metrics; all 36 answers (including 6 out-of-corpus questions) classified refused/answered.

## Metric means (answerable entries)

| metric | mean |
| --- | --- |
| faithfulness | 0.8092 |
| answer_relevancy | 0.7231 |
| context_precision | 0.7611 |
| context_recall | 0.9611 |

## Refusal behaviour (all 36 entries)

Measured in both directions on purpose: a service that refuses everything would score 100% on "did it refuse the out-of-corpus questions" alone.

| | refused | answered |
| --- | --- | --- |
| **should refuse** (6) | 6 | 0 |
| **should answer** (30) | 2 | 28 |

- Refusal accuracy (out-of-corpus correctly declined): **6/6 = 100.0%**
- False-refusal rate (answerable wrongly declined): **2/30 = 6.7%**
- Citations on refusals: 3/6 = 50.0% returned none (an unsourced refusal is the correct shape).

## Three weakest entries

### g09 (direct, en) — faithfulness 0.143, answer_relevancy 0.661, context_precision 1.000, context_recall 1.000

**Q** Who did he collaborate with on the plant-based neighborhood game, and which part did he handle himself?

**Expected citations** `floralink` — **retrieved** `floralink, spatial-pixel-lab, haptic-navigation-research, social-rhythm, haptic-atlas` — **cited** `floralink`

**Answer** On FloraLink, Jerry collaborated with Xiaotong Qin under mentor Ruby Wu. He handled the sociological research, game mechanism design, drawings, and model making.

### g24 (cross, en) — faithfulness 0.167, answer_relevancy 0.747, context_precision 0.000, context_recall 1.000

**Q** Where has he worked with hand tracking or gesture input, and what did each of those involve?

**Expected citations** `social-rhythm, spatial-pixel-lab` — **retrieved** `spatial-pixel-lab, haptic-navigation-research, social-rhythm, hxvp-marketing-group, haptic-atlas` — **cited** `spatial-pixel-lab, social-rhythm`

**Answer** Jerry worked with hand tracking and gesture detection at SVA's Spatial Pixel Lab, where he created a projection installation for two players, ran usability tests to cut gesture misclassifications, and addressed occlusion and latency issues. He also used Mediapipe hand tracking for Social Rhythm Part I, where each finger drives a live abstract tendril in the projection.

### g13 (direct, en) — faithfulness 0.444, answer_relevancy 0.784, context_precision 0.500, context_recall 1.000

**Q** On that studio platform rebuild, how did the designer's work and his own feed into the backend engineer's build, and what did he find in the existing backend?

**Expected citations** `hxvp-marketing-group` — **retrieved** `hxvp, hxvp-marketing-group, ikon-pass-japan, haptic-navigation-research, thu-adri` — **cited** `hxvp-marketing-group`

**Answer** He turned the designer's Figma frames into a high-fidelity prototype that became the living spec and draft API contract for the backend engineer's Django build. Auditing the existing backend, he found roughly 290 endpoints with live Stripe and payment-email wiring, then authored the feature-to-API integration scope and hardening guidance for the payment paths.


## Per entry

| id | cat | lang | faith. | ans.rel. | ctx.prec. | ctx.rec. | refused | cited |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| g01 | direct | en | 1.000 | 0.828 | 1.000 | 1.000 | no | hxvp |
| g02 | direct | en | 1.000 | 0.717 | 1.000 | 1.000 | no | hxvp |
| g03 | direct | en | 1.000 | 0.769 | 1.000 | 1.000 | no | hxvp |
| g04 | direct | zh | 1.000 | 0.737 | 1.000 | 1.000 | no | hxvp, hxvp-marketing-group |
| g05 | direct | en | 1.000 | 0.739 | 1.000 | 1.000 | no | haptic-atlas |
| g06 | direct | en | 0.800 | 0.801 | 0.833 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g07 | direct | en | 1.000 | 0.583 | 1.000 | 1.000 | no | social-rhythm |
| g08 | direct | en | 1.000 | 0.783 | 1.000 | 1.000 | no | social-rhythm |
| g09 | direct | en | 0.143 | 0.661 | 1.000 | 1.000 | no | floralink |
| g10 | direct | en | 1.000 | 0.701 | 1.000 | 1.000 | no | heartwhisper |
| g11 | direct | en | 0.500 | 0.803 | 1.000 | 1.000 | no | belt-for-the-blind |
| g12 | direct | en | 0.667 | 0.734 | 1.000 | 1.000 | no | hxvp-marketing-group |
| g13 | direct | en | 0.444 | 0.784 | 0.500 | 1.000 | no | hxvp-marketing-group |
| g14 | direct | zh | 0.625 | 0.662 | 1.000 | 1.000 | no | hxvp-marketing-group |
| g15 | direct | en | 0.571 | 0.690 | 1.000 | 1.000 | no | spatial-pixel-lab |
| g16 | direct | en | 0.800 | 0.765 | 1.000 | 1.000 | no | start-me-up |
| g17 | direct | en | 0.875 | 0.817 | 1.000 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g18 | direct | zh | 1.000 | 0.774 | 1.000 | 1.000 | no | thu-adri |
| g19 | direct | en | 1.000 | 0.729 | 1.000 | 1.000 | no | ascii-motion-jellyfish |
| g20 | direct | en | 1.000 | 0.662 | 1.000 | 1.000 | no | ikon-atlas, ikon-pass-japan |
| g21 | direct | en | 1.000 | 0.802 | 1.000 | 1.000 | no | findability |
| g22 | cross | en | 0.857 | 0.652 | 0.500 | 1.000 | no | hxvp, hxvp-marketing-group |
| g23 | cross | en | 0.667 | 0.713 | 1.000 | 1.000 | no | haptic-atlas, haptic-navigation-research |
| g24 | cross | en | 0.167 | 0.747 | 0.000 | 1.000 | no | spatial-pixel-lab, social-rhythm |
| g25 | cross | en | 0.857 | 0.851 | 0.000 | 0.667 | no | belt-for-the-blind, social-rhythm, haptic-navigation-research |
| g26 | cross | en | 1.000 | 0.669 | 0.000 | 1.000 | no | floralink, heartwhisper |
| g27 | cross | en | 1.000 | 0.863 | 0.000 | 0.667 | no | belt-for-the-blind, heartwhisper |
| g28 | cross | zh | 1.000 | 0.693 | 0.000 | 1.000 | no | ikon-atlas, ikon-pass-japan |
| g29 | refusal | en | — | — | — | — | yes | — |
| g30 | refusal | zh | — | — | — | — | yes | heartwhisper |
| g31 | refusal | en | — | — | — | — | yes | — |
| g32 | refusal | en | — | — | — | — | yes | spatial-pixel-lab |
| g33 | refusal | en | — | — | — | — | yes | haptic-navigation-research, spatial-pixel-lab, start-me-up |
| g34 | refusal | en | — | — | — | — | yes | — |
| g35 | partial | en | 0.636 | 0.965 | 1.000 | 0.500 | yes | hxvp-marketing-group, haptic-navigation-research, thu-adri |
| g36 | partial | zh | 0.667 | 0.000 | 0.000 | 1.000 | yes | spatial-pixel-lab, haptic-atlas |
