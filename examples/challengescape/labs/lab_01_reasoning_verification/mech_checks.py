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

    for field, spec in invariants.items():
        if not isinstance(spec, dict):
            continue
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
                if v is not None and not isinstance(v, (int, float)):
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
