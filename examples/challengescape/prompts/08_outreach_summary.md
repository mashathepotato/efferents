# Outreach-summary generator

**Input:** one lab's full journal (001–006) + its `questions_for_poc.md`.

**Output:** a ≤120-word plain-English summary for the challenge POC email:
what was run, the one number that matters, the one caveat the review raised,
and the top 2 questions from `questions_for_poc.md`.

**Success criteria:** zero hype adjectives; the caveat is included (sending
the limitation is what makes the summary credible); a domain scientist can
read it in 30 seconds; every number traceable to a run_id on request.

**Provenance:** numbers copied only from `runs.jsonl`/`005_review.md`; the
summary must not claim scientific novelty — the demo's value is the loop,
not the result.
