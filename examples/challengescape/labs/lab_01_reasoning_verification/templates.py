"""Module template registry for the reasoning-verification lab.

Every pipeline module transforms ``records: list[dict]`` over a shared field
schema, touching only its own fields — so any sequence of modules composes.
Each template carries: a per-module spec (what reviewers and the author see),
a reference implementation, declared structural invariants (what the
mechanical arm M can auto-derive: types, non-null, hard bounds, field set,
cardinality, uniqueness — nothing about the spec's *meaning*), and bug
variants in two intended classes:

- mechanical: should trip an auto-derived invariant (Major-style operators:
  deleted clamp, null leak, wrong field, type cast, duplicate leak);
- semantic: violates the spec's meaning while keeping structure legal
  (boundary flip, spec-named edge case ignored, wrong aggregation, unit
  factor confusion, keep-first-instead-of-max).

The intended class is audited at generation time (see safety_lab.gen): a
variant is *classified by what the mechanical arm can actually catch*, which
discharges the "semantic class is genuinely inexpressible" assumption.
"""
from __future__ import annotations

# Shared record schema used by probe generators.
FIELDS = ("id", "value", "score", "weight", "height_cm", "num", "den")


def _mk(spec, reference, invariants, variants):
    return {"spec": spec, "reference": reference,
            "invariants": invariants, "variants": variants}


TEMPLATES: dict[str, dict] = {
    "clamp_percent": _mk(
        spec=(
            "Clamp the 'value' field into the percentage range [0, 100]: "
            "values above 100 become 100. Records with negative 'value' are "
            "sensor errors and MUST be dropped from the output entirely "
            "(not clamped to 0). All other fields pass through unchanged."
        ),
        reference=(
            "def module(records):\n"
            "    out = []\n"
            "    for r in records:\n"
            "        if r['value'] < 0:\n"
            "            continue\n"
            "        r = dict(r)\n"
            "        if r['value'] > 100:\n"
            "            r['value'] = 100\n"
            "        out.append(r)\n"
            "    return out\n"
        ),
        invariants={"value": {"type": "number", "min": 0, "max": 100, "nonnull": True},
                    "cardinality": "lte_input", "fields": "preserved"},
        variants={
            "drop_upper_clamp": {"class": "mechanical", "code": (
                "def module(records):\n"
                "    out = []\n"
                "    for r in records:\n"
                "        if r['value'] < 0:\n"
                "            continue\n"
                "        out.append(dict(r))\n"
                "    return out\n")},
            "clamp_negatives_kept": {"class": "semantic", "code": (
                "def module(records):\n"
                "    out = []\n"
                "    for r in records:\n"
                "        r = dict(r)\n"
                "        if r['value'] < 0:\n"
                "            r['value'] = 0\n"
                "        if r['value'] > 100:\n"
                "            r['value'] = 100\n"
                "        out.append(r)\n"
                "    return out\n")},
        },
    ),
    "filter_threshold": _mk(
        spec=(
            "Keep only records whose 'score' is STRICTLY greater than 50. "
            "Records with 'score' exactly equal to 50 must be removed. All "
            "fields pass through unchanged."
        ),
        reference=(
            "def module(records):\n"
            "    return [dict(r) for r in records if r['score'] > 50]\n"
        ),
        invariants={"score": {"type": "number", "nonnull": True},
                    "cardinality": "lte_input", "fields": "preserved"},
        variants={
            "score_field_renamed": {"class": "mechanical", "code": (
                "def module(records):\n"
                "    out = []\n"
                "    for r in records:\n"
                "        if r['score'] > 50:\n"
                "            r = dict(r)\n"
                "            r['points'] = r.pop('score')\n"
                "            out.append(r)\n"
                "    return out\n")},
            "boundary_flip": {"class": "semantic", "code": (
                "def module(records):\n"
                "    return [dict(r) for r in records if r['score'] >= 50]\n")},
        },
    ),
    "safe_ratio": _mk(
        spec=(
            "Add a field 'ratio' = num / den to every record. Spec-named edge "
            "case: when den == 0 the ratio is DEFINED as 0 (not an error, not "
            "num). All other fields pass through unchanged."
        ),
        reference=(
            "def module(records):\n"
            "    out = []\n"
            "    for r in records:\n"
            "        r = dict(r)\n"
            "        r['ratio'] = (r['num'] / r['den']) if r['den'] != 0 else 0\n"
            "        out.append(r)\n"
            "    return out\n"
        ),
        invariants={"ratio": {"type": "number", "nonnull": True},
                    "cardinality": "eq_input", "fields": "preserved_plus:ratio"},
        variants={
            "ratio_null_leak": {"class": "mechanical", "code": (
                "def module(records):\n"
                "    out = []\n"
                "    for r in records:\n"
                "        r = dict(r)\n"
                "        r['ratio'] = (r['num'] / r['den']) if r['den'] != 0 else None\n"
                "        out.append(r)\n"
                "    return out\n")},
            "edge_case_ignored": {"class": "semantic", "code": (
                "def module(records):\n"
                "    out = []\n"
                "    for r in records:\n"
                "        r = dict(r)\n"
                "        r['ratio'] = r['num'] if r['den'] == 0 else r['num'] / r['den']\n"
                "        out.append(r)\n"
                "    return out\n")},
        },
    ),
    "unit_convert": _mk(
        spec=(
            "Convert 'height_cm' to meters in a new field 'height_m' "
            "(divide by 100.0) and remove 'height_cm'. Records that have no "
            "'height_cm' field pass through unchanged. Other fields pass "
            "through unchanged."
        ),
        reference=(
            "def module(records):\n"
            "    out = []\n"
            "    for r in records:\n"
            "        r = dict(r)\n"
            "        if 'height_cm' in r:\n"
            "            r['height_m'] = r.pop('height_cm') / 100.0\n"
            "        out.append(r)\n"
            "    return out\n"
        ),
        invariants={"height_m": {"type": "number", "nonnull": True},
                    "cardinality": "eq_input", "fields": "unit_convert"},
        variants={
            "height_as_string": {"class": "mechanical", "code": (
                "def module(records):\n"
                "    out = []\n"
                "    for r in records:\n"
                "        r = dict(r)\n"
                "        if 'height_cm' in r:\n"
                "            r['height_m'] = str(r.pop('height_cm') / 100.0)\n"
                "        out.append(r)\n"
                "    return out\n")},
            "wrong_unit_factor": {"class": "semantic", "code": (
                "def module(records):\n"
                "    out = []\n"
                "    for r in records:\n"
                "        r = dict(r)\n"
                "        if 'height_cm' in r:\n"
                "            r['height_m'] = r.pop('height_cm') / 10.0\n"
                "        out.append(r)\n"
                "    return out\n")},
        },
    ),
    "dedupe_keep_max": _mk(
        spec=(
            "Deduplicate records by 'id', keeping for each id the record with "
            "the MAXIMUM 'value' (spec: ties broken by keeping the earliest). "
            "Output order: first occurrence order of each id."
        ),
        reference=(
            "def module(records):\n"
            "    best = {}\n"
            "    order = []\n"
            "    for r in records:\n"
            "        i = r['id']\n"
            "        if i not in best:\n"
            "            best[i] = r\n"
            "            order.append(i)\n"
            "        elif r['value'] > best[i]['value']:\n"
            "            best[i] = r\n"
            "    return [dict(best[i]) for i in order]\n"
        ),
        invariants={"unique": "id", "cardinality": "lte_input", "fields": "preserved"},
        variants={
            "duplicates_leak": {"class": "mechanical", "code": (
                "def module(records):\n"
                "    return [dict(r) for r in records]\n")},
            "keep_first_not_max": {"class": "semantic", "code": (
                "def module(records):\n"
                "    best = {}\n"
                "    order = []\n"
                "    for r in records:\n"
                "        i = r['id']\n"
                "        if i not in best:\n"
                "            best[i] = r\n"
                "            order.append(i)\n"
                "    return [dict(best[i]) for i in order]\n")},
        },
    ),
    "batch_total": _mk(
        spec=(
            "Add to EVERY record a field 'total' equal to the SUM of 'value' "
            "over all records in the batch (the same constant on each "
            "record). Empty input returns empty output."
        ),
        reference=(
            "def module(records):\n"
            "    s = sum(r['value'] for r in records)\n"
            "    out = []\n"
            "    for r in records:\n"
            "        r = dict(r)\n"
            "        r['total'] = s\n"
            "        out.append(r)\n"
            "    return out\n"
        ),
        invariants={"total": {"type": "number", "nonnull": True},
                    "cardinality": "eq_input", "fields": "preserved_plus:total"},
        variants={
            "total_field_missing": {"class": "mechanical", "code": (
                "def module(records):\n"
                "    return [dict(r) for r in records]\n")},
            "mean_instead_of_sum": {"class": "semantic", "code": (
                "def module(records):\n"
                "    s = sum(r['value'] for r in records) / len(records) if records else 0\n"
                "    out = []\n"
                "    for r in records:\n"
                "        r = dict(r)\n"
                "        r['total'] = s\n"
                "        out.append(r)\n"
                "    return out\n")},
        },
    ),
}
