#!/usr/bin/env python3
"""AOI support-block gate check — standalone arithmetic re-check.

Re-implements ONLY the support-block gate rule, from the rule as stated in
the calibration notes, in plain Python (standard library only):

  * informative test: a block counts as informative iff
        ref_count >= 12  AND  var_per_count >= 25 * ref_count
    ("count>=12、variance>=25*count"; the reference-sample / variance test
    from the existing code, restated here, not copied).
  * stage-b ordering: informative++ happens BEFORE the partially-out check,
    so a partially-out block still counts as informative — and it
    contributes correlation 0, so it can never be "supported".
  * variant A ordering: informative++ happens AFTER the partially-out
    check, so a partially-out block is not informative at all.
  * support: an informative block is supported iff its per-block
    correlation >= threshold (localized 0.80 stage-b / 0.70 variant B;
    dense 0.80 variant C).
  * gate: reject unless supported == required (100% of informative).

This program does NOT locate anything. It does NOT prove an impostor is
blocked. It only replays the gate arithmetic on previously measured
per-block support counts (cases.json). The verdict of the real search is
whatever the real run did; where this program and a real run disagree,
the real run wins (see the comparison section at the end of the output).

Usage:  python3 gate_check.py [cases.json]
"""

import json
import math
import sys
from pathlib import Path

# ---------------------------------------------------------------- rules

STAGE_A2_RATIO = 0.55  # documented looser bar, used only for the fallback
# below; the gate itself is 100% in every rule evaluated here.


def is_informative(ref_count, var_per_count, partially_out, variant_a):
    """Informative-block test, rewritten from the stated rule.

    stage-b (variant_a=False): the partially-out check comes after the
    informative count, so a partially-out block still counts.
    variant A (variant_a=True): the partially-out check comes first, so a
    partially-out block never counts.
    A partially-out block contributes correlation 0 in both orderings, so
    it can never be supported; that is why, for variant A, the supported
    count is simply the total support count (all supported blocks are
    necessarily fully visible).
    """
    if partially_out and variant_a:
        return False
    return ref_count >= 12 and var_per_count >= 25 * ref_count


def selftest_informative():
    """Synthetic checks of the rule above (NOT measurements)."""
    checks = [
        # (ref_count, var_per_count, partially_out, variant_a, expected)
        (12, 300, False, False, True),    # exactly at both floors
        (11, 300, False, False, False),   # too few reference samples
        (12, 299, False, False, False),   # variance just under 25*count
        (20, 500, False, False, True),    # comfortably informative
        (20, 500, True, False, True),     # stage-b: out block still counts
        (20, 500, True, True, False),     # variant A: out block not counted
        (5, 125, True, True, False),      # out + too few samples
    ]
    for ref, var, out, va, want in checks:
        got = is_informative(ref, var, out, va)
        assert got == want, (ref, var, out, va, got, want)
    return len(checks)


# rule_id -> (label, value_key, threshold, variant_a_out_handling)
RULES = {
    "stage_b": ("stage-b  (loc 0.80, out blocks counted)", "loc", "0.80", False),
    "variant_a": ("variant A (loc 0.80, out blocks NOT counted)", "loc", "0.80", True),
    "variant_b": ("variant B (loc 0.70, out blocks counted)", "loc", "0.70", False),
    "variant_c": ("variant C (dense 0.80, out blocks counted)", "dense", "0.80", False),
}


def verdict(case, rule_id):
    """Return (verdict, supported, required, note).

    verdict is PASS / REJECT / UNKNOWN. UNKNOWN means the data needed for
    this rule was never measured for this case; the program refuses to
    guess. supported/required are None for UNKNOWN.
    """
    _label, value_key, threshold, variant_a = RULES[rule_id]
    support = case.get(f"{value_key}_support")
    informative = case.get("informative")

    # Textured impostors: only a dense@0.80 count out of 16 blocks was ever
    # measured, and no informative count. For the dense rule we can still
    # say REJECT if the count fails even the looser documented stage-a2 bar
    # (ceil(16*0.55) = 9); anything at/above that bar would be UNKNOWN.
    if informative is None and value_key == "dense" and support is not None:
        total = case.get("total_blocks", 16)
        loose_bar = math.ceil(total * STAGE_A2_RATIO)
        n = support.get("0.80")
        if n is not None and n < loose_bar:
            return ("REJECT", n, None,
                    f"dense@0.80 support {n}/{total} fails even the looser "
                    f"stage-a2 bar ({loose_bar} of {total}); informative count "
                    f"not measured, so no 100% verdict is claimed")
        return ("UNKNOWN", None, None,
                "dense@0.80 count at/above the loose bar but informative "
                "count not measured; 100% verdict not computable")
    if informative is None:
        return ("UNKNOWN", None, None,
                "informative count not measured for this case")
    if support is None:
        return ("UNKNOWN", None, None,
                f"no {value_key} per-block support counts measured")
    if threshold not in support or support[threshold] is None:
        return ("UNKNOWN", None, None,
                f"no {value_key} support count at threshold {threshold}")

    part_out = case.get("partial_out_blocks")
    assumed = False
    if part_out is None:
        part_out, assumed = [], True
    supported = support[threshold]
    required = informative - (len(part_out) if variant_a else 0)
    note = ""
    if assumed:
        note = "assumed 0 partially-out blocks (not measured for this case)"
    if variant_a and part_out:
        note = (f"{len(part_out)} partially-out blocks excluded from "
                f"informative ({informative} -> {required})")
    return ("PASS" if supported >= required else "REJECT",
            supported, required, note)


# ------------------------------------------------------- real-run reference
# Hard-coded from the calibration reports (sources in cases.json meta).
# These are the facts the program's predictions are compared against.
REAL_RUNS = {
    "stage_b": {"matrix": "195/220", "kills": 25, "neg11": "11/11",
                "rescued": []},
    "variant_a": {"matrix": "199/220", "kills": 21, "neg11": "11/11",
                  "rescued": ["metal/translation-49", "metal/translation-50",
                              "pcb/translation-49", "pcb/translation-50"]},
    "variant_b": {"matrix": "200/220", "kills": 20, "neg11": "11/11",
                  "rescued": ["metal/noise-15", "metal/noise-30",
                              "metal/occlusion-0.1", "pcb/noise-15",
                              "pcb/occlusion-0.1"]},
    # variant C (dense) has no real-run result yet: calibration-c was still
    # running when this program was written. Deliberately no comparison.
}


def main(argv):
    path = Path(argv[1]) if len(argv) > 1 else Path(__file__).with_name("cases.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    cases = doc["cases"]

    n_checks = selftest_informative()
    print(f"gate_check.py — AOI support-block gate arithmetic re-check")
    print(f"cases file: {path}  ({len(cases)} cases)")
    print(f"informative-rule self-test: {n_checks}/{n_checks} synthetic "
          f"checks passed (synthetic inputs, not measurements)")
    print()

    results = {}  # (case_id, rule_id) -> verdict tuple
    for rule_id, (label, _vk, _th, _va) in RULES.items():
        print(f"== {label} ==")
        print(f"{'case':<42} {'verdict':<8} {'sup/req':<10} note")
        for case in cases:
            v, sup, req, note = verdict(case, rule_id)
            results[(case["id"], rule_id)] = (v, sup, req)
            ratio = f"{sup}/{req}" if sup is not None and req is not None else (
                f"{sup}/?" if sup is not None else "-")
            print(f"{case['id']:<42} {v:<8} {ratio:<10} {note}")
        print()

    # ---- summary per rule, split by case kind ----
    print("== summary (this program, closest-to-ground-truth proxy) ==")
    for rule_id, (label, _vk, _th, _va) in RULES.items():
        kills = [c for c in cases if c["kind"] == "kill"]
        passes = [c for c in cases if c["kind"] == "pass-sample"]
        wrong = [c for c in cases if c["kind"] == "wrong-target"]
        tex = [c for c in cases if c["kind"] == "textured-impostor"]
        def count(group, want):
            return sum(1 for c in group
                       if results[(c["id"], rule_id)][0] == want)
        def unknown(group):
            return sum(1 for c in group
                       if results[(c["id"], rule_id)][0] == "UNKNOWN")
        rescued = [c["id"] for c in kills
                   if results[(c["id"], rule_id)][0] == "PASS"]
        print(f"{label}")
        print(f"  kill cases still rejected: {count(kills, 'REJECT')}/25 "
              f"(rescued by this rule: {len(rescued)} {rescued})")
        print(f"  pass-sample still passing: {count(passes, 'PASS')}/13 "
              f"(rejected by proxy: {count(passes, 'REJECT')}/13, "
              f"unknown: {unknown(passes)})")
        print(f"  wrong-target rejected: {count(wrong, 'REJECT')}/3 "
              f"(unknown: {unknown(wrong)})")
        print(f"  textured-impostor rejected: {count(tex, 'REJECT')}/5 "
              f"(unknown: {unknown(tex)})")
    print()

    # ---- comparison against the real runs ----
    print("== predicted (proxy) vs real run ==")
    print("Real runs: 11-case dotnet test + 220-case generated matrix, "
          "calibration-a/b NOTES.md. Where they disagree, the real run wins.")
    for rule_id in ("stage_b", "variant_a", "variant_b"):
        label = RULES[rule_id][0]
        real = REAL_RUNS[rule_id]
        kills = [c for c in cases if c["kind"] == "kill"]
        pred_rescued = sorted(c["id"] for c in kills
                              if results[(c["id"], rule_id)][0] == "PASS")
        real_rescued = sorted(real["rescued"])
        extra = sorted(set(real_rescued) - set(pred_rescued))
        missing = sorted(set(pred_rescued) - set(real_rescued))
        print(f"{label}")
        print(f"  proxy rescued: {len(pred_rescued)} {pred_rescued}")
        print(f"  real rescued:  {len(real_rescued)} {real_rescued} "
              f"(matrix {real['matrix']}, kills {real['kills']}, "
              f"11-case {real['neg11']})")
        print(f"  proxy kills: {25 - len(pred_rescued)}/25; "
              f"real kills: {real['kills']}/25")
        if extra:
            print(f"  real rescued but proxy missed: {extra}")
        if missing:
            print(f"  proxy rescued but real did not: {missing}")
        if not extra and not missing:
            print("  proxy and real agree on which cases are rescued")
    print("  variant C (dense 0.80): NO real-run comparison — "
          "calibration-c was still running when this was written.")
    print()

    print("== known mismatches and why (proxy vs real search) ==")
    print("1. Variant A: proxy rescues 3, real run rescues 4. Extra case is")
    print("   pcb/translation-50: proxy closest complete evaluation had angle")
    print("   error 1.05 deg and worst fully-visible block 0.574 (9/10); the")
    print("   variant A accepted pose (calibration-a/matrix/poses.csv) is")
    print("   0.08 px / 0.04 deg from ground truth. The proxy sampled ONE pose")
    print("   ~1 deg off; the search found a nearer pose where that block")
    print("   clears 0.80. Single-pose proxy vs multi-pose search.")
    print("2. Variant B: proxy rescues 1, real run rescues 5. Extra cases:")
    print("   pcb/noise-15, metal/noise-15, metal/noise-30,")
    print("   metal/occlusion-0.1 (proxy worst blocks 0.496-0.680, support")
    print("   13-14/15 at 0.70). Their accepted poses")
    print("   (calibration-b/matrix/poses.csv) are 0.13-0.64 px / 0.04-0.79 deg")
    print("   from ground truth — the same neighbourhood as the proxy pose —")
    print("   yet the worst block clears 0.70 there. Worst-block correlation")
    print("   swings by 0.1-0.2+ under sub-pixel / sub-degree changes; the")
    print("   proxy samples one pose, the search tries hundreds and accepts")
    print("   any passing pose. The proxy therefore systematically")
    print("   underestimates rescues. Largest swing is metal/noise-30")
    print("   (0.496 -> >=0.70); which pose detail flips it is not recorded")
    print("   in the available data — that would need the accepted pose's")
    print("   per-block values.")
    print("3. Pass-sample metal/scale-0.7: proxy says REJECT under every rule")
    print("   (14/15, worst block 0.133), but stage-b, variant A and variant B")
    print("   real runs all passed it (absent from every kill list). step1")
    print("   notes the top-5 nearby evaluations include a 15/15 pose: a")
    print("   known proxy artefact, not a real regression.")
    print("4. Textured impostors at 0.70: NOT computable from cases.json")
    print("   (only dense@0.80 counts were measured). Their 0.70 blocking")
    print("   rests on the variant B 11-case real run (11/11), not on this")
    print("   program. This program reports UNKNOWN for them under variant B.")
    print("5. metal/occlusion-0.4: step1 notes its rejection is driven mainly")
    print("   by the contradiction early-return, not by the support count.")
    print("   This program models only the support-count gate, not the")
    print("   contradiction gate.")
    print()
    print("What this program does NOT verify: that the gate blocks real")
    print("impostors in a live search; that any threshold is safe for unseen")
    print("targets; speed; the full 220-case matrix; anything about the")
    print("contradiction gate, blurred rescue paths, or the dense/localized")
    print("correlation computation itself. See README.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
