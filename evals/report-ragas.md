# Ragas report — findability-api `/ask`

Judge: `claude-haiku-4-5` via `langchain-anthropic`. Embeddings for answer relevancy: `gemini-embedding-2`, the same model the corpus is indexed with. Both reuse keys the service already holds — no new accounts.

Samples: 36 answerable golden entries scored on the four metrics; 39 answers (including 6 out-of-corpus questions) classified refused/answered, and 3 `partial` entries checked separately.

## Metric means (answerable entries)

| metric | mean |
| --- | --- |
| faithfulness | 0.8105 |
| answer_relevancy | 0.7401 |
| context_precision | 0.7778 |
| context_recall | 0.9148 |

`context_precision` is printed for continuity and **is not read as a retrieval
signal on this corpus** — the mechanism is below, under "Why `context_precision`
collapses on multi-source questions". `faithfulness` is not a valid gate here
either (PROGRESS.md, Stage E). The two metrics that survived audit are
`answer_relevancy` and `context_recall`; the deterministic retrieval metrics in
`report-retrieval.md` are what CI actually gates on.

## Refusal behaviour (39 of 42 entries)

Measured in both directions on purpose: a service that refuses everything would score 100% on "did it refuse the out-of-corpus questions" alone.

The 3 `partial` entries are **not** in this table. They ask for several things at once where the corpus carries some and not the rest, so both binary labels are wrong for them; folding them in is what made this report print a 6.7% false-refusal rate on 2026-08-11 while the service had in fact refused nothing it could answer. They are measured below instead.

| | refused | answered |
| --- | --- | --- |
| **should refuse** (6) | 6 | 0 |
| **should answer** (33) | 0 | 33 |

- Refusal accuracy (out-of-corpus correctly declined): **6/6 = 100.0%**
- False-refusal rate (fully-answerable wrongly declined): **0/33 = 0.0%**
- Citations on refusals: 4/6 = 66.7% returned none (an unsourced refusal is the correct shape).

## Partial answers (3 entries)

A separate two-sided check, not a third value in the matrix above: does the reply answer the part the corpus supports **and** state that the rest is not in the portfolio? Failing either half fails the check.

- Answered in part and flagged the gap: **3/3 = 100.0%**

- `g35` (en) — both halves present; cited `hxvp-marketing-group, haptic-navigation-research, thu-adri`
- `g36` (zh) — both halves present; cited `haptic-atlas, belt-for-the-blind, spatial-pixel-lab`
- `g41` (en) — both halves present; cited `heartwhisper`

## Why `context_precision` collapses on multi-source questions

Ragas asks its judge, once per retrieved chunk, whether that chunk "was useful in arriving at the given answer" — where the answer it is shown is the **whole** golden reference. When the reference aggregates several projects, no single chunk supports the whole of it, the judge votes 0 on every chunk, and average precision is `0 / (0 + 1e-10)` = exactly 0.000. The verdict is driven by the shape of the reference, not by whether retrieval was right.

| reference aggregates | n | mean ctx.prec. | entries at exactly 0.000 |
| --- | --- | --- | --- |
| one expected source | 26 | 0.9679 | 0 |
| two or more expected sources | 10 | 0.2833 | 6 |

Entries scoring 0.000 while retrieval actually found expected chunks:

- `g24` (cross) — retrieved 2 of 2 expected ids (`spatial-pixel-lab, social-rhythm`) and still scores 0.000.
- `g25` (cross) — retrieved 2 of 3 expected ids (`social-rhythm, belt-for-the-blind`) and still scores 0.000.
- `g26` (cross) — retrieved 1 of 2 expected ids (`floralink`) and still scores 0.000.
- `g27` (cross) — retrieved 1 of 3 expected ids (`belt-for-the-blind`) and still scores 0.000.
- `g28` (cross) — retrieved 2 of 2 expected ids (`ikon-pass-japan, ikon-atlas`) and still scores 0.000.
- `g36` (partial) — retrieved 4 of 4 expected ids (`spatial-pixel-lab, haptic-navigation-research, belt-for-the-blind, haptic-atlas`) and still scores 0.000.

Verified in isolation against the same judge: replaying a 0.000 entry chunk by chunk and trimming the reference to the half each chunk covers flips every verdict from 0 to 1, with the retrieval byte-identical. A number that can be moved from 0.000 to 1.000 by editing `golden.jsonl` alone is not measuring the service.

## Three weakest entries

### g09 (direct, en) — faithfulness 0.167, answer_relevancy 0.650, context_precision 1.000, context_recall 1.000

**Q** Who did he collaborate with on the plant-based neighborhood game, and which part did he handle himself?

**Expected citations** `floralink` — **retrieved** `floralink, spatial-pixel-lab, haptic-navigation-research, social-rhythm, haptic-atlas` — **cited** `floralink`

**Answer** He collaborated with Xiaotong Qin on FloraLink, the plant-based neighborhood game. Jerry handled the sociological research, game mechanism design, drawings, and model making.

### g02 (direct, en) — faithfulness 0.300, answer_relevancy 0.709, context_precision 1.000, context_recall 1.000

**Q** What does the one-minute walkthrough of the studio platform actually show?

**Expected citations** `hxvp` — **retrieved** `hxvp, hxvp-marketing-group, social-rhythm, ikon-pass-japan, haptic-atlas` — **cited** `hxvp`

**Answer** The walkthrough traces a complete production cycle in nine scenes: role-based login, live budget editing that recomputes totals immediately, casting approval, client shortlist distribution, crew booking and call-sheet confirmation, time-log verification, and invoice approval — demonstrating how production, client, talent, and crew portals share one data spine and update each other in real time.

### g11 (direct, en) — faithfulness 0.333, answer_relevancy 0.818, context_precision 1.000, context_recall 1.000

**Q** What is the Belt for the Blind based on, and when did he work on it?

**Expected citations** `belt-for-the-blind` — **retrieved** `belt-for-the-blind, haptic-atlas, haptic-navigation-research, social-rhythm, spatial-pixel-lab` — **cited** `belt-for-the-blind`

**Answer** Belt for the Blind is based on tactile perception and uses a motor module worn at the waist to deliver directional cues through vibration. Jerry worked on it from October 2023 to October 2024.


## Per entry

| id | cat | lang | faith. | ans.rel. | ctx.prec. | ctx.rec. | outcome | expected | cited |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| g01 | direct | en | 1.000 | 0.806 | 1.000 | 1.000 | answered | answered | hxvp |
| g02 | direct | en | 0.300 | 0.709 | 1.000 | 1.000 | answered | answered | hxvp |
| g03 | direct | en | 1.000 | 0.640 | 1.000 | 1.000 | answered | answered | hxvp |
| g04 | direct | zh | 1.000 | 0.720 | 1.000 | 1.000 | answered | answered | hxvp, hxvp-marketing-group |
| g05 | direct | en | 1.000 | 0.803 | 0.833 | 1.000 | answered | answered | haptic-atlas, haptic-navigation-research |
| g06 | direct | en | 1.000 | 0.820 | 0.833 | 1.000 | answered | answered | haptic-atlas, haptic-navigation-research, belt-for-the-blind |
| g07 | direct | en | 1.000 | 0.709 | 1.000 | 1.000 | answered | answered | social-rhythm |
| g08 | direct | en | 0.833 | 0.731 | 1.000 | 1.000 | answered | answered | social-rhythm |
| g09 | direct | en | 0.167 | 0.650 | 1.000 | 1.000 | answered | answered | floralink |
| g10 | direct | en | 1.000 | 0.714 | 1.000 | 1.000 | answered | answered | heartwhisper |
| g11 | direct | en | 0.333 | 0.818 | 1.000 | 1.000 | answered | answered | belt-for-the-blind |
| g12 | direct | en | 0.667 | 0.692 | 1.000 | 1.000 | answered | answered | hxvp-marketing-group |
| g13 | direct | en | 0.556 | 0.753 | 0.500 | 1.000 | answered | answered | hxvp-marketing-group |
| g14 | direct | zh | 1.000 | 0.757 | 1.000 | 1.000 | answered | answered | hxvp-marketing-group |
| g15 | direct | en | 1.000 | 0.847 | 1.000 | 1.000 | answered | answered | spatial-pixel-lab |
| g16 | direct | en | 0.833 | 0.676 | 1.000 | 1.000 | answered | answered | start-me-up |
| g17 | direct | en | 1.000 | 0.813 | 1.000 | 1.000 | answered | answered | haptic-atlas, haptic-navigation-research |
| g18 | direct | zh | 1.000 | 0.776 | 1.000 | 1.000 | answered | answered | thu-adri |
| g19 | direct | en | 1.000 | 0.927 | 1.000 | 1.000 | answered | answered | ascii-motion-jellyfish |
| g20 | direct | en | 0.875 | 0.757 | 1.000 | 1.000 | answered | answered | ikon-atlas, ikon-pass-japan |
| g21 | direct | en | 0.833 | 0.834 | 1.000 | 1.000 | answered | answered | findability |
| g22 | cross | en | 0.500 | 0.701 | 0.500 | 1.000 | answered | answered | hxvp, hxvp-marketing-group |
| g23 | cross | en | 1.000 | 0.721 | 1.000 | 1.000 | answered | answered | haptic-atlas, haptic-navigation-research |
| g24 | cross | en | 0.750 | 0.581 | 0.000 | 1.000 | answered | answered | spatial-pixel-lab, social-rhythm |
| g25 | cross | en | 0.667 | 0.858 | 0.000 | 0.400 | answered | answered | social-rhythm, belt-for-the-blind, haptic-navigation-research |
| g26 | cross | en | 0.556 | 0.703 | 0.000 | 0.500 | answered | answered | floralink |
| g27 | cross | en | 1.000 | 0.552 | 0.000 | 0.333 | answered | answered | belt-for-the-blind |
| g28 | cross | zh | 1.000 | 0.641 | 0.000 | 1.000 | answered | answered | ikon-pass-japan, ikon-atlas |
| g29 | refusal | en | — | — | — | — | refused | refused | — |
| g30 | refusal | zh | — | — | — | — | refused | refused | heartwhisper |
| g31 | refusal | en | — | — | — | — | refused | refused | — |
| g32 | refusal | en | — | — | — | — | refused | refused | spatial-pixel-lab, haptic-navigation-research |
| g33 | refusal | en | — | — | — | — | refused | refused | — |
| g34 | refusal | en | — | — | — | — | refused | refused | — |
| g35 | partial | en | 0.889 | 0.943 | 1.000 | 0.500 | partial | partial | hxvp-marketing-group, haptic-navigation-research, thu-adri |
| g36 | partial | zh | 0.385 | 0.000 | 0.000 | 0.600 | partial | partial | haptic-atlas, belt-for-the-blind, spatial-pixel-lab |
| g37 | direct | en | 0.909 | 0.951 | 1.000 | 1.000 | answered | answered | heartwhisper |
| g38 | direct | en | 0.571 | 0.798 | 1.000 | 1.000 | answered | answered | floralink |
| g39 | direct | en | 1.000 | 0.839 | 1.000 | 1.000 | answered | answered | belt-for-the-blind |
| g40 | direct | zh | 0.667 | 0.847 | 1.000 | 1.000 | answered | answered | heartwhisper |
| g41 | partial | en | 1.000 | 0.950 | 1.000 | 1.000 | partial | partial | heartwhisper |
| g42 | cross | en | 0.889 | 0.607 | 0.333 | 0.600 | answered | answered | haptic-navigation-research, spatial-pixel-lab, belt-for-the-blind |
