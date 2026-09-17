# HerpetoID evaluation record — *Salamandra salamandra*

Source material for a future publication: what was measured, on which data, with which method, and what
the limitations are. Every number here was measured in this repository or in the analysis scripts named
at the end; none is taken from literature unless cited as such. Chronological detail lives in
`session-log.md`; this file is the consolidated record.

Last updated: 2026-09-17 (closed-set benchmark completed — see §6.5, which supersedes the retrieval
figures in §6.3).

---

## 1. Why an evaluation was needed

The identification engine had never been measured on real recaptures. All earlier figures came from
synthetic images generated in the test-suite, which model pose, illumination, colour cast, shadow,
glare and noise, but not real skin texture, body deformation, optics or genuine inter-individual
similarity. The owner reported that two photographs of very similar animals scored ~50%, the same as
two clearly different animals; that observation started this work.

## 2. Data

Photographs downloaded from iNaturalist with an in-house downloader, five observers, one species.

| Observer | Photos on disk | Usable after automatic cropping | Site structure | Span | Licence |
|---|---|---|---|---|---|
| `andrej_funk_praha` | 614 | 564 | 2 sites near Prague, ~10 m GPS accuracy | 2020–2026 | CC BY-NC |
| `philippevoidrot` | 247 | 177 | 1 site, Vienna, ~9 m | 2020–2026 | all rights reserved |
| `caracalshan` | 561 | round 5 | Belgium, coordinates obscured ~26 km | 2017–2025 | CC BY |
| `jonatan_antunez` | 132 | not used | Pontevedra | 2015–2026 | CC BY-NC |
| `knarfoh` | 54 | not used | Bavaria | 2022–2026 | CC BY-NC |

Recaptures can only be sought **within** an observer: the five sites are in five countries.
One iNaturalist observation may contain photographs of **different animals** (verified in Andrej's
2022 uploads), so all identity bookkeeping is per photograph, never per observation.

**Licence note for publication:** `philippevoidrot`'s photographs are all-rights-reserved; they may be
analysed locally but not redistributed or reproduced. CC BY-NC material requires attribution and
excludes commercial use.

## 3. Automatic region of interest

Verification at this scale needed the animal located without hand-drawn regions. The detector keeps
saturated yellow blobs whose surrounding ring is ≥60% dark skin (which rejects leaf litter), drops
specks below 2% of the largest blob, joins blobs within ~3 typical blob diameters into one body, and
crops the convex hull plus 12% margin, rescaled so the long side is 700 px. Crops smaller than 180 px
in the original photograph are rejected.

Measured on 36 random photographs per observer: the whole back was framed in roughly three of four
photographs; 6/36 (Philippe) and 2/36 (Andrej) produced no crop. Failures reduce recall only — an
uncropped photograph simply produces no candidate.

**This is not how the app is used.** In HerpetoID the researcher draws the region by hand. All engine
figures below therefore describe the engine on automatic crops, not the full app workflow.

## 4. Engine

Species module (unchanged during this work): crop to the region, take the CIE Lab b\* (blue→yellow)
channel, remove illumination with a difference-of-Gaussians band-pass whose widths are fractions of the
region (0.006 and 0.040 of the shorter side), stretch to 8-bit.

Algorithm ORB, versions developed and measured here:

| Version | Verification geometry | Score | Notes |
|---|---|---|---|
| 1.0 | RANSAC homography + plausibility gate | `0.5·min(1, inliers/30) + 0.5·inlier_ratio` | as found |
| 1.1 | RANSAC similarity (rotation, scale, shift), tolerance 0.018 × keypoint extent | `1 − exp(−(n − 4.5)/5)` | inlier ratio removed |
| 1.2 | + one-to-one matching, fitted scale change limited to ¼–4× | same | fixes a collapse failure |
| 1.3 | same as 1.2 | `1 − exp(−(n − 3)/10)` | amber 6 inliers, green 10 |

Two defects were found and fixed with evidence:

1. **The inlier ratio carried no signal** (AUC 0.53 on 160 verified pairs) yet formed half the displayed
   score, so a handful of chance matches that happened to agree could read as a strong match.
2. **A collapse.** Many query keypoints could match one target keypoint, and a similarity transform with
   scale ≈ 0 mapped them all onto it; RANSAC counted them as agreeing. Different animals reached up to
   34 "inliers" this way, in one comparison direction only. On 310 verified pairs this made 30% of
   different-animal pairs display green, and swapping query and target changed the score by >0.3 in 159
   of 310 pairs.

## 5. Verification protocol

Candidate pairs were mined automatically and **verified by the project owner** (a herpetologist) from
side-by-side images, marking each pair Correct (same individual) or Incorrect. Pairs already judged, and
pairs already linked into one individual by earlier verdicts, were excluded from later rounds. Verdicts
were cross-checked against the owner's written summaries; no disagreements were found. Identities are
formed by chaining confirmed pairs per photograph; **no confirmed-different pair contradicts a chain**.

| Round | Mining method | Andrej | Philippe | Verified pairs added |
|---|---|---|---|---|
| 1 | RootSIFT on the pattern image + LNBNN distinctiveness | 77/80 correct | 5/80 | 82 same / 78 different |
| 2 | MiewID global embedding + ORB blend | 4/100 | 1/50 | 5 same / 145 different |
| 3 | exhaustive ORB 1.2, all pairs | 16/120 | 1/37 | 17 same / 140 different |
| 4 | round-1 recipe on the pool left after 1–3 | 7/50 | 0/50 | 7 same / 93 different |
| 5 | new population `caracalshan`, mined by **both** recipes over the 457 photographs both could process, union exported | 33/96 correct (see §6.4) | — | 33 same / 63 different |
| **Total** | | | | **144 same / 519 different (663 pairs)** |

Round 5 exists because rounds 1–4 each flattered their own miner. Two recipes searched the same unseen
collection, the union of their proposals was verified, and the precision of "ORB-only", "SIFT-only" and
"both" pairs is therefore the first complementarity measurement in which neither recipe selected the
pool. It does not fix the deeper bias in §8.1 (recaptures that *no* method proposes remain invisible).

Identities from round 5: **caracalshan 24 individuals** (5 photographed on ≥3 nights, 20 spanning ≥1
calendar year, longest 3 years), no contradictions.

Resulting identities: **Andrej 49 individuals** (20 photographed on ≥3 nights, 40 spanning ≥1 calendar
year, longest 2020→2026), **Philippe 7** (4 spanning ≥1 year). These are lower bounds: only mined
candidates were ever reviewed.

## 6. Results

### 6.1 Pair discrimination (AUC, 1.0 = perfect separation)

| Pair set | ORB 1.0 | ORB 1.1 | ORB 1.2 | ORB 1.3 |
|---|---|---|---|---|
| Round 1 (160 pairs) | 0.79 | 0.945 | 0.944 | 0.958 |
| Rounds 1–2 (310 pairs) | — | 0.794 | 0.940 | — |
| All 567 pairs | — | — | — | **0.863** |

### 6.2 Colour bands, ORB 1.3, on all 567 verified pairs

| Band | Threshold | Recaptures | Different animals |
|---|---|---|---|
| Green | ≥10 agreeing matches (score ≥0.50) | 43% | 0.7% |
| Amber or better | ≥6 (score ≥0.25) | 80% | ~30% |

In **open search** (round 3, exhaustive), green was right 6/9 times and amber 6/109. Pair-level
calibration does not transfer to searching a whole collection: with ~160 000 comparisons, the chance
tail at 8–9 agreeing matches produces dozens of false greens. This is why green requires 10 from v1.3
and is labelled "strong candidate", not a verdict.

### 6.3 Retrieval — the practical measure

Every confirmed photograph searched its observer's whole collection (photographs from the same night
excluded); the rank of the first photograph of the same individual was recorded.

| Engine | Andrej top-1 | top-5 | top-10 | median rank | Philippe top-1 | top-10 |
|---|---|---|---|---|---|---|
| ORB 1.1 | 44% | — | 64% | 2 | 20% | 60% |
| ORB 1.2 | 79% | 85% | 87% | 1 | 80% | 90% |
| ORB 1.3 (567-pair identity set, 136 queries) | 75% | 82% | 87% | 1 | 71% | 100% |

(The 1.3 row uses a larger query set that includes harder identities added in round 4.)

### 6.4 Round 5 — the unbiased comparison of two recipes

96 pairs from a population neither recipe had seen, both proposing freely; 33 confirmed recaptures.

**Precision by which recipe proposed the pair:**

| Proposed by | Confirmed recaptures |
|---|---|
| Both recipes | 22/24 (92%) |
| SIFT+LNBNN only | 9/36 (25%) |
| ORB only | 2/36 (6%) |

**As scorers, on the same 96 pairs:** SIFT+LNBNN AUC **0.913** (AP 0.896) vs ORB 1.3 AUC 0.798 (AP 0.819).

| Rule | Recaptures caught | Different animals passed |
|---|---|---|
| ORB ≥ 12 inliers | 18/33 | 0/63 |
| ORB ≥ 10 (app's green) | 20/33 | 4/63 |
| SIFT ≥ 1.0 | 20/33 | **0/63** |
| SIFT ≥ 0.5 | 31/33 | 29/63 |
| ORB ≥ 10 **or** SIFT ≥ 1.0 | **24/33** | 4/63 |
| ORB ≥ 10 **and** SIFT ≥ 0.5 | 19/33 | 0/63 |

**13 of the 33 recaptures are invisible to ORB** (fewer than 10 agreeing matches, several as low as 3);
12 of those score ≥0.5 with SIFT and 4 score ≥1.0. ORB's bands on this new population: green 20/24
(83%), amber 6/40 (15%), weak 7/32 (22%).

This **reverses** the conclusion drawn from rounds 1–4, where ORB looked uniformly better: those pools
had been stripped of easy recaptures by one recipe or the other, and each round flattered its own
miner. On a fresh population the two recipes are genuinely complementary, and running both would
surface recaptures the app currently cannot reach.

Caveats: one population, 33 recaptures; the pairs are the union of both recipes' proposals, so the AUC
figures are conditional on a pair having been proposed by at least one of them — fair *between* the
recipes, but not an absolute recall measure.

### 6.5 Closed-set benchmark — the honest measurement

69 photographs, four survey nights, one site; the expert grouped them **by eye before using the
software**: 58 individuals, 10 seen more than once, **12 true recapture pairs** among 2 346 possible
pairs. Regions were drawn by hand in the app (project `Test OBS 1.3`), so this measures the real
workflow, not automatic crops.

| | ORB 1.3 (shipped) | RootSIFT + LNBNN |
|---|---|---|
| Recaptures shown green / strong | **1 of 12** | 3 of 12 at zero false positives (≥2.0) |
| Best recall at ≤4 false pairs in 2 334 | 1 of 12 (≥10 pts) | **5 of 12** (≥1.0) |
| Different pairs shown green | 0 of 2 334 | 0 of 2 334 (≥2.0) |
| True pairs scoring exactly zero | 5 of 12 | 6 of 12 |
| Right animal ranked first | 6 of 21 (29%) | **12 of 21 (57%)** |
| Top-5 / top-10 | 38% / 57% | **62% / 67%** |
| Median rank of the true partner | 8 | **1** |

**This overturns §6.3.** The 75–79% top-1 reported there came from identities discovered by mining, i.e.
only recaptures some matcher could already see. On a set defined by *when the photographs were taken*,
the shipped engine ranks the right animal first in **29%** of searches, not 79%.

**Specificity is not the problem; recall is.** Zero of 2 334 different-animal pairs reach green with
either method. Six of the twelve recaptures are missed by both at any usable threshold.

**The expert's own app session** (77 identification runs) linked 6 pairs: 5 true (12-66, 16-35, 33-60,
44-53, 46-49), 7 true pairs missed, and one pair linked that the expert's grouping calls different
animals (61-62).

**The shipped plugin, measured through its own `rank()`** (2026-09-17, algorithm `sift_lnbnn` 1.0, same
photographs and hand-drawn regions):

| | ORB 1.3 | SIFT+LNBNN plugin |
|---|---|---|
| right animal ranked first | 6/21 (29%) | **10/21 (48%)** |
| top-5 / top-10 | 48% / 57% | **57% / 62%** |
| median rank | 9 | **2** |
| true pairs shown green | 1/12 | **5/12** (0.53–0.88) |

Slightly below the 57% of the research script in §6.5 above, for a principled reason: in the app the
query's own descriptors are not in the catalog the distinctiveness is measured against, while the script
left them in. The plugin's figure is the one that describes real use.

**Two software defects found during this session:**

1. **Scores move when a photograph is rotated** (median 0.10, worst 0.26 — enough to change band and
   reshuffle the candidate list). The matcher itself is rotation-invariant (a photograph matches its own
   quarter-turned copy at 1.00) and the region is mapped correctly (mask area differs by ≤20 px in
   ~200 000, keypoint counts by ≤5 in ~1 000). The cause is that these recaptures rest on **4–9**
   agreeing points, so one or two keypoints flipping near a detector threshold moves the score a whole
   band. A symptom of thin evidence, not of broken geometry.
2. **Identification results are not stored.** `match_runs` recorded all 77 runs but `matches` is empty:
   `CatalogService.record_identification` writes only the run header, and nothing ever writes the ranked
   candidates or the user's decision. Sessions are therefore not auditable and had to be reconstructed.

## 7. Approaches tested and rejected

All measured on the same verified pairs; none adopted.

| Approach | Result |
|---|---|
| ALIKED / DISK + LightGlue (deep local matchers) | pair AUC 0.55–0.71 vs ORB 0.945; 2–11 agreeing matches on real recaptures where ORB found 15–45. Lighting change between nights breaks appearance-based matching |
| MiewID-msv3 (global embedding, trained with fire salamanders) | AUC 0.81 on round 1, **0.44** on round 2, 0.52 overall; retrieval top-1 23% vs ORB 45% |
| ORB + 2×MiewID blend | best on round-1 retrieval (top-1 66% vs 45%) but **refuted**: as a miner it yielded 5 true pairs in 150 |
| Search-size-aware scores (expected chance matches, global or per-query; robust standout) | AUC 0.808–0.858 vs 0.862 for the plain count |
| Rank and margin rules ("top-1 only", "clear lead") | no gain: 33 of 38 false greens were already a search's top-1 |
| LNBNN distinctiveness over ORB features | AUC 0.754 raw / 0.843 share vs 0.861; retrieval top-1 68% vs 82% |
| RootSIFT + LNBNN (the round-1 recipe) vs ORB, symmetric on rounds 1–4 | ORB better on both fair splits (rounds 2+3: 0.783 vs 0.676; rounds 1+4: 0.946 vs 0.800); the apparent complementarity there (21 recaptures found only by SIFT) is **circular**, all 21 from rounds SIFT itself mined. **Superseded by §6.4**: on an unseen population SIFT scores better (AUC 0.913 vs 0.798) and finds recaptures ORB cannot. Retained here because it shows how misleading pools mined by the method under test are |

## 8. Limitations (essential for any publication)

1. **Selection bias in the ground truth.** Every verified pair was proposed by an automatic matcher.
   Recaptures that no method proposes are absent, so recall is overestimated and "complementarity"
   between methods is confounded with which method mined which round. The round-5 design (two recipes
   mining one new population, union verified) addresses this only partially.
2. **No independent ground truth.** Identities rest on expert visual judgement of the same photographs
   the engine matches — not on physical marking, genetics, or an independent observer. Inter-observer
   agreement has not been measured.
3. **Opportunistic data.** iNaturalist photographs vary in pose, angle, distance and lighting; sampling
   effort is unstructured; some observations contain several animals. This is not a designed
   capture–recapture study, so population estimates cannot be derived from it.
4. **Automatic crops, not user-drawn regions.** ~25% of photographs are cropped imperfectly and some not
   at all; the app's real workflow uses hand-drawn regions and has not been measured at this scale.
5. **Two observers carry the evidence.** 104 of 111 recaptures come from two sites; Philippe's figures
   rest on ≤14 queries.
6. **Species-specific calibration.** The bands were fitted on fire salamanders. On synthetic
   *Calotriton asper* material different individuals reach 0.50–0.67, so the bands must be re-measured
   before they mean anything for other species.
7. **Amber is noisy in open search** (6 of 109 correct in round 3) and is labelled accordingly.

## 9. Reproducibility

Ground truth and artefacts (outside the repository, with the photographs):
`recapture_candidates/ground_truth_all.csv` (567 pairs, with round, verdict, photo paths),
`individuals_<observer>.csv`, the per-round folders (`round2_blend/`, `round3/`, `round4_sift/`,
`round5_caracalshan/`), and the full score matrices `deep_eval/orb13_matrix_<observer>.npz`,
`sift_matrix_<observer>.npz`, `lnbnn_matrix_<observer>.npz`.

Scripts in `recapture_candidates/deep_eval/scripts/`: `recapture_miner.py` (round 1),
`mine_round3.py`, `mine_round4.py`, `mine_round5_dual.py`, `score_matrix.py`, `sift_matrix.py`,
`calibrate_orb.py`, `verified_analysis.py`, `search_score_eval.py`, `lnbnn_matrix.py`, `lnbnn_eval.py`,
`sift_vs_orb.py`; retired MiewID scripts under `retired/`.

Engine code and its regression tests are in this repository (`src/herpetoid/plugins/algorithms/orb/`,
`tests/test_plugins.py`); the ORB docstring carries the calibration tables.

## 10. Work still needed for a defensible publication

1. ~~**A closed-set benchmark without selection bias**~~ — **done 2026-09-17, results in §6.5.** `recapture_candidates/closed_set_benchmark/`: **69 photographs**, one per observation,
   being every observation from four survey nights at `andrej_funk_praha`'s busiest site (50.145 N,
   14.384 E): 2023-10-09 (19), 2024-01-02 (20), 2025-10-25 (13), 2025-11-02 (17). The sampling unit is
   the night, so no matcher influenced the selection; three seasons allow cross-year recaptures and two
   nights eight days apart allow short-interval ones. No photograph was excluded (all 69 show a dorsal
   pattern; the expert flags any unusable one in the manifest).
   Protocol (`INSTRUCTIONS.md` in that folder): (a) the expert groups all 69 by eye **before** using the
   software, so the grouping is independent of what is measured; (b) a fresh project is created, the
   photographs imported, **regions drawn by hand** — the first measurement of the app with real regions
   rather than automatic crops — and identification run in date order with sequential enrolment, as in a
   real season. The project bundle records every run and score, so ranks can be extracted without manual
   note-taking. Once the grouping exists, every one of the 2 346 possible pairs is labelled, which makes
   **recall** measurable for the first time.
2. **Independent verification** of a subset by a second experienced observer, reporting agreement.
3. **Field-verified recaptures** if any exist (marked or otherwise known individuals).
4. **Comparison with published tools** on the same photographs. Published fire-salamander figures
   (Amphibian & Reptile Wildbook 77%, ManderMatcher 73%, AmphIdent 61%, I3S Pattern+ 56%, Wild-ID 38%
   recognition rate on 377 adult field images; PLOS One 2024, doi:10.1371/journal.pone.0298285) are
   **not** comparable to the figures above, which use different photographs, different regions and a
   different protocol.
