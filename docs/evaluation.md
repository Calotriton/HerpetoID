# HerpetoID evaluation record — *Salamandra salamandra*

Source material for a future publication: what was measured, on which data, with which method, and what
the limitations are. Every number here was measured in this repository or in the analysis scripts named
at the end; none is taken from literature unless cited as such. Chronological detail lives in
`session-log.md`; this file is the consolidated record.

Last updated: 2026-09-16 (round 5 mining in progress).

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
| **Total** | | | | **111 same / 456 different (567 pairs)** |

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
| RootSIFT + LNBNN (the round-1 recipe) vs ORB, symmetric | ORB better on **both** fair splits (rounds 2+3: 0.783 vs 0.676; rounds 1+4: 0.946 vs 0.800). Apparent complementarity (21 recaptures found only by SIFT) is **circular**: all 21 come from rounds SIFT itself mined, 0 from the 22 recaptures in rounds it did not |

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

1. **A closed-set benchmark without selection bias.** Take a fixed set of photographs from one site
   (~50), have the expert sort them into individuals by eye, and evaluate the engine against that
   complete grouping. This measures recall honestly, which mined pairs cannot.
2. **Independent verification** of a subset by a second experienced observer, reporting agreement.
3. **Field-verified recaptures** if any exist (marked or otherwise known individuals).
4. **Comparison with published tools** on the same photographs. Published fire-salamander figures
   (Amphibian & Reptile Wildbook 77%, ManderMatcher 73%, AmphIdent 61%, I3S Pattern+ 56%, Wild-ID 38%
   recognition rate on 377 adult field images; PLOS One 2024, doi:10.1371/journal.pone.0298285) are
   **not** comparable to the figures above, which use different photographs, different regions and a
   different protocol.
