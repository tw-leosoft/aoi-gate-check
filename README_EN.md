# AOI Supported-Block Threshold — Independent Gate Check (public-gate-check)

> Chinese version: see `README.md` （中文版見 `README.md`）.
> This English version mirrors the Chinese `README.md` section by section.
> If the two ever disagree, the numbers in the run logs and in
> `calibration-a/NOTES.md` / `calibration-b/NOTES.md` are authoritative.

## What this is

A small program that checks only the "threshold arithmetic". It extracts the
AOI stage-b supported-block threshold logic, rewrites it in Python using only
the standard library, and re-runs the accept/reject decision of four rules
against previously measured per-block support counts:

- **stage-b**: localized >= 0.80, out-of-bounds blocks count toward
  `informative`, 100% support required to pass.
- **Variant A**: localized >= 0.80, out-of-bounds blocks do NOT count toward
  `informative`, 100% support required to pass.
- **Variant B**: localized >= 0.70, out-of-bounds blocks count toward
  `informative`, 100% support required to pass.
- **Variant C (included)**: dense >= 0.80, out-of-bounds blocks count toward
  `informative`, 100% support required to pass.

Threshold rules (rewritten from the wording of the calibration report,
not copied from the product source code):

- Informative decision: `ref_count >= 12` and `variance >= 25 * ref_count`.
- stage-b order: `informative++` happens BEFORE the out-of-bounds check, so
  an out-of-bounds block still counts as informative, and its correlation is
  counted as 0, so it can never count as supported.
- Variant A order: `informative++` happens AFTER the out-of-bounds check,
  so an out-of-bounds block does not count as informative at all.
- Gate: `supportedBlocks < informative` means reject (the 100% count
  requirement).

The data contains only numbers: no images, no source code, no weights,
no license codes. All 46 cases come from already-measured tables
(see the `source` field of each entry in `cases.json`).

## What this is not

- **Not a locator**: it does not search, does not compute correlations,
  does not read images. It only does arithmetic on support counts that
  already exist.
- **Does not prove the locator really blocks impostors**: the evidence that
  impostors are blocked is the 11-case real run (dotnet test 11/11) and
  the 220-case matrix real run, not this program.
- **Not product source code**: it does not copy `GeometricLocate.cs` or
  `GeometricPattern.cs`, and it was not pasted from `~/workspace/sdk/aoi/`;
  it only rewrites the few threshold rules above.

## Files to be published (local-only, not yet public)

| File | Lines | Contents |
|---|---|---|
| `gate_check.py` | 282 | Check program (Python standard library only) |
| `cases.json` | 1157 | 46 cases of synthetic numeric data (source noted per case) |
| `README.md` | 133 | Chinese version of this document |
| `README_EN.md` | 177 | This file (English version) |
| `run.log` | 282 | Local run output |
| **Total** | **2031 lines** | Program itself is only 282 lines |

The public scope is exactly these five files, nothing else. No SDK source
code, no test images, no model weights, no license-related content.

## How to run

```sh
python3 gate_check.py            # reads cases.json in the same directory by default
python3 gate_check.py cases.json # or specify a data file
```

Exit code 0 means the program finished (not that the threshold passed).
The output contains a per-case decision table, a summary of the four rules,
a predicted-vs-real-run comparison, and notes on known discrepancies.

## Local check results (proxy metric) vs real-run results

"Predicted" is this program's decision on the step-1 "nearest-to-truth
evaluation"; "real run" is the calibration-a / calibration-b 11-case
dotnet test plus the 220-case matrix. Step 1 is a single-pose proxy metric,
not the candidate the search actually accepts or rejects; when they
disagree, the real run wins.

| Rule | Predicted false kills (of 25) | Predicted rescued | Real-run false kills | Real-run rescued | 11-case real run |
|---|---|---|---|---|---|
| stage-b (0.80, out-of-bounds counted) | 25 | 0 | 25 (195/220) | 0 | 11/11 |
| Variant A (0.80, out-of-bounds excluded) | 22 | 3 | 21 (199/220) | 4 | 11/11 |
| Variant B (0.70, out-of-bounds counted) | 24 | 1 | 20 (200/220) | 5 | 11/11 |
| Variant C (dense 0.80) | 24 | 1 | — (calibration-c still running) | — | — |

Other predicted numbers:

- 13 sampled passing cases: predicted 12/13 pass under all four rules
  (see mismatch point 3).
- WrongTarget, 3 cases: predicted 3/3 rejected under stage-b / A / B
  (12/13 supported, worst block 0.597 / 0.583 / 0.596, all below 0.70);
  dense was not measured, so variant C is UNKNOWN.
- Textured impostors, 4 cases, plus contradictory, 1 case: UNKNOWN under
  the loc rules (no measured data); under dense 0.80, 5/5 rejected
  (support counts 2 / 4 / 0 / 4 / 4, below even the looser stage-a2
  threshold of 9/16).

## Mismatches (listed honestly, not forced to agree)

1. **Variant A: predicted 3 rescued, real run rescued 4.** The extra one is
   `pcb/translation-50`. The proxy measurement's nearest full evaluation
   had an angle error of 1.05° and a worst fully-visible block of 0.574
   (9/10 supported); the pose variant A actually accepted in the real run
   (`calibration-a/matrix/poses.csv`) is only 0.08 px / 0.04° from the
   truth. The proxy sampled a single pose 1° off; the search found a
   closer pose, and that block then passed 0.80. Single-pose proxy
   vs multi-pose search.
2. **Variant B: predicted 1 rescued, real run rescued 5.** The extra four
   are `pcb/noise-15`, `metal/noise-15`, `metal/noise-30`, and
   `metal/occlusion-0.1` (proxy worst block 0.496–0.680, 0.70 support
   13–14/15). The poses actually accepted in the real run
   (`calibration-b/matrix/poses.csv`) are 0.13–0.64 px / 0.04–0.79° from
   the truth, in the same neighborhood as the proxy pose, yet the worst
   block passed 0.70 there. The worst block's localized correlation is
   very sensitive to sub-pixel / sub-degree changes (swings of 0.1–0.2 or
   more); the proxy samples one pose, the search tries hundreds of poses
   and accepts if any one passes, so the proxy systematically
   underestimates the rescue count. The biggest swing is
   `metal/noise-30` (0.496 → ≥0.70); which pose detail flipped it is not
   recorded in the current data — it would need the accepted pose's
   per-block values to say, and this program does not guess.
3. **Passing case `metal/scale-0.7`: the proxy rejects it under all four
   rules** (14/15, worst block 0.133), but the stage-b / A / B real runs
   all pass it (it appears in none of the three false-kill lists).
   Step 1 already noted: among the nearest 5 evaluations there was a 15/15
   pose, so this is a proxy-sampling artifact, not a real regression.
4. **Whether textured impostors are blocked at 0.70 cannot be checked by
   this program.** Only 0.80 support counts exist; there are no per-block
   values at 0.70, so the program reports UNKNOWN for variant B. The
   evidence that 0.70 still blocks textured impostors is variant B's
   11-case real run (11/11), not this program.
5. **`metal/occlusion-0.4` was rejected mainly for a different reason than
   support count.** Step 1 noted that 376 of 377 near-truth evaluations
   left early through the contradiction early-return. This program only
   models the support-count gate, not the contradiction gate.

## What this program cannot verify

- Whether the gate blocks impostors in a real search (needs the 11-case /
  matrix real runs).
- Whether any threshold is safe for targets never seen before (the sample
  is only 25 + 13 + 3 + 5 cases).
- The full 220-case matrix (this program has proxy measurements for only
  38 of its cases, plus an 8-case impostor summary).
- The contradiction gate, the blurred-rescue paths, or the dense /
  localized correlation computation itself.
- Speed, licensing, builds, or CI.

## Data sources and honesty notes

- 25 false kills + 13 sampled passing cases: the nearest-to-truth
  evaluations in `calibration/calib-analysis.txt`
  (summarized in `calibration/step1-NOTES.md`); informative is always
  15/16, with exactly 1 block per template having insufficient reference
  variance.
- WrongTarget, 3 cases: `REPORT.md` (12/13 supported, worst-block values).
  Support counts at thresholds other than 0.80 are strictly derived
  (12/13 means exactly one block is below 0.80, and that block is the
  worst block at 0.583–0.597, below 0.60, so the support count is 12 at
  every threshold), not measured per block; `cases.json` carries a
  `loc_support_derived` marker for this.
- Textured impostors, 4 cases, plus contradictory: the dense@0.80 support
  counts in `REPORT.md` (2 / 4 / 0 / 4 / 16; the contradictory count of 4
  was derived from the sentence "it would pass under a 0.25 ratio
  threshold", noted in `cases.json`, not tabulated directly).
- The number of out-of-bounds blocks for WrongTarget was not measured:
  variant A's decision assumes 0, and the program output says so.
- Real-run comparison numbers: `calibration-a/NOTES.md` (199/220,
  21 false kills, 4 rescued), `calibration-b/NOTES.md` (200/220,
  20 false kills, 5 rescued), `REPORT.md` (stage-b 195/220, 25 false
  kills).
