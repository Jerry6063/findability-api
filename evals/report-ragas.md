# Ragas report — findability-api `/ask`

Judge: `claude-haiku-4-5` via `langchain-anthropic`. Embeddings for answer relevancy: `gemini-embedding-2`, the same model the corpus is indexed with. Both reuse keys the service already holds — no new accounts.

Samples: 30 answerable golden entries scored on the four metrics; 34 answers (including 6 out-of-corpus questions) classified refused/answered, and 2 `partial` entries checked separately.

## Metric means (answerable entries)

| metric | mean |
| --- | --- |
| faithfulness | 0.8092 |
| answer_relevancy | 0.7231 |
| context_precision | 0.7611 |
| context_recall | 0.9611 |

`context_precision` is printed for continuity and **is not read as a retrieval
signal on this corpus** — the mechanism is below, under "Why `context_precision`
collapses on multi-source questions". `faithfulness` is not a valid gate here
either (PROGRESS.md, Stage E). The two metrics that survived audit are
`answer_relevancy` and `context_recall`; the deterministic retrieval metrics in
`report-retrieval.md` are what CI actually gates on.

## Refusal behaviour (34 of 36 entries)

Measured in both directions on purpose: a service that refuses everything would score 100% on "did it refuse the out-of-corpus questions" alone.

The 2 `partial` entries are **not** in this table. They ask for several things at once where the corpus carries some and not the rest, so both binary labels are wrong for them; folding them in is what made this report print a 6.7% false-refusal rate on 2026-08-11 while the service had in fact refused nothing it could answer. They are measured below instead.

| | refused | answered |
| --- | --- | --- |
| **should refuse** (6) | 6 | 0 |
| **should answer** (28) | 0 | 28 |

- Refusal accuracy (out-of-corpus correctly declined): **6/6 = 100.0%**
- False-refusal rate (fully-answerable wrongly declined): **0/28 = 0.0%**
- Citations on refusals: 3/6 = 50.0% returned none (an unsourced refusal is the correct shape).

## Partial answers (2 entries)

A separate two-sided check, not a third value in the matrix above: does the reply answer the part the corpus supports **and** state that the rest is not in the portfolio? Failing either half fails the check.

- Answered in part and flagged the gap: **2/2 = 100.0%**

- `g35` (en) — both halves present; cited `hxvp-marketing-group, haptic-navigation-research, thu-adri`
- `g36` (zh) — both halves present; cited `spatial-pixel-lab, haptic-atlas`

## Why `context_precision` collapses on multi-source questions

Ragas asks its judge, once per retrieved chunk, whether that chunk "was useful in arriving at the given answer" — where the answer it is shown is the **whole** golden reference. When the reference aggregates several projects, no single chunk supports the whole of it, the judge votes 0 on every chunk, and average precision is `0 / (0 + 1e-10)` = exactly 0.000. The verdict is driven by the shape of the reference, not by whether retrieval was right.

| reference aggregates | n | mean ctx.prec. | entries at exactly 0.000 |
| --- | --- | --- | --- |
| one expected source | 21 | 0.9683 | 0 |
| two or more expected sources | 9 | 0.2778 | 6 |

Entries scoring 0.000 while retrieval actually found expected chunks:

- `g24` (cross) — retrieved 2 of 2 expected ids (`spatial-pixel-lab, social-rhythm`) and still scores 0.000.
- `g25` (cross) — retrieved 2 of 3 expected ids (`belt-for-the-blind, social-rhythm`) and still scores 0.000.
- `g26` (cross) — retrieved 2 of 2 expected ids (`floralink, heartwhisper`) and still scores 0.000.
- `g27` (cross) — retrieved 2 of 3 expected ids (`belt-for-the-blind, heartwhisper`) and still scores 0.000.
- `g28` (cross) — retrieved 2 of 2 expected ids (`ikon-pass-japan, ikon-atlas`) and still scores 0.000.
- `g36` (partial) — retrieved 4 of 4 expected ids (`spatial-pixel-lab, haptic-navigation-research, belt-for-the-blind, haptic-atlas`) and still scores 0.000.

Verified in isolation against the same judge: replaying a 0.000 entry chunk by chunk and trimming the reference to the half each chunk covers flips every verdict from 0 to 1, with the retrieval byte-identical. A number that can be moved from 0.000 to 1.000 by editing `golden.jsonl` alone is not measuring the service.

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

| id | cat | lang | faith. | ans.rel. | ctx.prec. | ctx.rec. | outcome | expected | cited |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| g01 | direct | en | 1.000 | 0.828 | 1.000 | 1.000 | answered | answered | hxvp |
| g02 | direct | en | 1.000 | 0.717 | 1.000 | 1.000 | answered | answered | hxvp |
| g03 | direct | en | 1.000 | 0.769 | 1.000 | 1.000 | answered | answered | hxvp |
| g04 | direct | zh | 1.000 | 0.737 | 1.000 | 1.000 | answered | answered | hxvp, hxvp-marketing-group |
| g05 | direct | en | 1.000 | 0.739 | 1.000 | 1.000 | answered | answered | haptic-atlas |
| g06 | direct | en | 0.800 | 0.801 | 0.833 | 1.000 | answered | answered | haptic-atlas, haptic-navigation-research |
| g07 | direct | en | 1.000 | 0.583 | 1.000 | 1.000 | answered | answered | social-rhythm |
| g08 | direct | en | 1.000 | 0.783 | 1.000 | 1.000 | answered | answered | social-rhythm |
| g09 | direct | en | 0.143 | 0.661 | 1.000 | 1.000 | answered | answered | floralink |
| g10 | direct | en | 1.000 | 0.701 | 1.000 | 1.000 | answered | answered | heartwhisper |
| g11 | direct | en | 0.500 | 0.803 | 1.000 | 1.000 | answered | answered | belt-for-the-blind |
| g12 | direct | en | 0.667 | 0.734 | 1.000 | 1.000 | answered | answered | hxvp-marketing-group |
| g13 | direct | en | 0.444 | 0.784 | 0.500 | 1.000 | answered | answered | hxvp-marketing-group |
| g14 | direct | zh | 0.625 | 0.662 | 1.000 | 1.000 | answered | answered | hxvp-marketing-group |
| g15 | direct | en | 0.571 | 0.690 | 1.000 | 1.000 | answered | answered | spatial-pixel-lab |
| g16 | direct | en | 0.800 | 0.765 | 1.000 | 1.000 | answered | answered | start-me-up |
| g17 | direct | en | 0.875 | 0.817 | 1.000 | 1.000 | answered | answered | haptic-atlas, haptic-navigation-research |
| g18 | direct | zh | 1.000 | 0.774 | 1.000 | 1.000 | answered | answered | thu-adri |
| g19 | direct | en | 1.000 | 0.729 | 1.000 | 1.000 | answered | answered | ascii-motion-jellyfish |
| g20 | direct | en | 1.000 | 0.662 | 1.000 | 1.000 | answered | answered | ikon-atlas, ikon-pass-japan |
| g21 | direct | en | 1.000 | 0.802 | 1.000 | 1.000 | answered | answered | findability |
| g22 | cross | en | 0.857 | 0.652 | 0.500 | 1.000 | answered | answered | hxvp, hxvp-marketing-group |
| g23 | cross | en | 0.667 | 0.713 | 1.000 | 1.000 | answered | answered | haptic-atlas, haptic-navigation-research |
| g24 | cross | en | 0.167 | 0.747 | 0.000 | 1.000 | answered | answered | spatial-pixel-lab, social-rhythm |
| g25 | cross | en | 0.857 | 0.851 | 0.000 | 0.667 | answered | answered | belt-for-the-blind, social-rhythm, haptic-navigation-research |
| g26 | cross | en | 1.000 | 0.669 | 0.000 | 1.000 | answered | answered | floralink, heartwhisper |
| g27 | cross | en | 1.000 | 0.863 | 0.000 | 0.667 | answered | answered | belt-for-the-blind, heartwhisper |
| g28 | cross | zh | 1.000 | 0.693 | 0.000 | 1.000 | answered | answered | ikon-atlas, ikon-pass-japan |
| g29 | refusal | en | — | — | — | — | refused | refused | — |
| g30 | refusal | zh | — | — | — | — | refused | refused | heartwhisper |
| g31 | refusal | en | — | — | — | — | refused | refused | — |
| g32 | refusal | en | — | — | — | — | refused | refused | spatial-pixel-lab |
| g33 | refusal | en | — | — | — | — | refused | refused | haptic-navigation-research, spatial-pixel-lab, start-me-up |
| g34 | refusal | en | — | — | — | — | refused | refused | — |
| g35 | partial | en | 0.636 | 0.965 | 1.000 | 0.500 | partial | partial | hxvp-marketing-group, haptic-navigation-research, thu-adri |
| g36 | partial | zh | 0.667 | 0.000 | 0.000 | 1.000 | partial | partial | spatial-pixel-lab, haptic-atlas |
