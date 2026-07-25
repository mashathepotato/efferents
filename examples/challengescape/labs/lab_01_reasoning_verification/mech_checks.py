"""Arm M — auto-derived structural checks. Stdlib-only (imported by eval.py).

These are the checks a mechanical harness derives from a module's declared
structure WITHOUT understanding the spec's meaning: output types, non-null,
hard bounds, field-set discipline, cardinality, and uniqueness. Nothing here
encodes thresholds, aggregation semantics, unit factors, tie-breaking, or
spec-named edge-case behavior — that boundary is what separates the
mechanical from the semantic violation class, and it is audited, not assumed
(see safety_lab.gen).

Returns (fired, executions): the invariant names that failed, and how many
individual checks ran (the M arm's cost unit).
"""
from __future__ import annotations


def run_checks(invariants: dict, input_records: list, output_records: list):
    fired: list[str] = []
    execs = 0

    card = invariants.get("cardinality")
    if card:
        execs += 1
        if card == "eq_input" and len(output_records) != len(input_records):
            fired.append("cardinality_eq")
        if card == "lte_input" and len(output_records) > len(input_records):
            fired.append("cardinality_lte")

    unique_key = invariants.get("unique")
    if unique_key:
        execs += 1
        keys = [r.get(unique_key) for r in output_records]
        if len(keys) != len(set(keys)):
            fired.append(f"unique_{unique_key}")

    fields_rule = invariants.get("fields")
    if fields_rule and input_records and output_records:
        execs += 1
        in_fields = set(input_records[0])
        for r in output_records:
            got = set(r)
            if fields_rule == "preserved" and got != in_fields:
                fired.append("field_set")
                break
            if fields_rule.startswith("preserved_plus:"):
                extra = fields_rule.split(":", 1)[1]
                if got != in_fields | {extra}:
                    fired.append("field_set")
                    break
            if fields_rule == "unit_convert":
                want = (in_fields - {"height_cm"}) | {"height_m"} \
                    if "height_cm" in in_fields else in_fields
                if got != want:
                    fired.append("field_set")
                    break

    if invariants.get("intervals_sorted_nonoverlap"):
        execs += 1
        seq = [(r.get("start"), r.get("end")) for r in output_records]
        ok = all(isinstance(s, (int, float)) and isinstance(e, (int, float))
                 and s <= e for s, e in seq)
        if ok:
            for (s1, e1), (s2, e2) in zip(seq, seq[1:]):
                if s2 < s1 or s2 <= e1:
                    ok = False
                    break
        if not ok:
            fired.append("intervals_sorted_nonoverlap")

    sum_eq = invariants.get("sum_eq")
    if isinstance(sum_eq, dict) and output_records:
        execs += 1
        try:
            total = sum(r.get(sum_eq["field"], 0) for r in output_records)
            if total != sum_eq["value"]:
                fired.append(f"sum_eq_{sum_eq['field']}")
        except TypeError:
            fired.append(f"sum_eq_{sum_eq['field']}")

    for field, spec in invariants.items():
        if not isinstance(spec, dict) or field == "sum_eq":
            continue
        if spec.get("monotone_nondecreasing"):
            execs += 1
            vals = [r.get(field) for r in output_records if field in r]
            if any(not isinstance(v, (int, float)) for v in vals) or \
                    any(b < a for a, b in zip(vals, vals[1:])):
                fired.append(f"{field}_monotone")
        for r in output_records:
            if field not in r:
                continue
            v = r[field]
            if spec.get("nonnull"):
                execs += 1
                if v is None:
                    fired.append(f"{field}_nonnull")
                    break
            if spec.get("type") == "number":
                execs += 1
                if v is not None and (not isinstance(v, (int, float))
                                      or isinstance(v, bool)):
                    fired.append(f"{field}_type")
                    break
            if spec.get("type") == "bool":
                execs += 1
                if v is not None and not isinstance(v, bool):
                    fired.append(f"{field}_type")
                    break
            if v is not None and isinstance(v, (int, float)):
                if "min" in spec:
                    execs += 1
                    if v < spec["min"]:
                        fired.append(f"{field}_min")
                        break
                if "max" in spec:
                    execs += 1
                    if v > spec["max"]:
                        fired.append(f"{field}_max")
                        break

    return sorted(set(fired)), execs
