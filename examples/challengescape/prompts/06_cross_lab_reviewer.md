# Cross-lab reviewer

**Input:** the reviewing lab's own memo + the reviewed lab's full journal and
`runs.jsonl` (both siblings' run records are fair evidence).

**Output:** `shared_journal/reviews/<reviewer>_on_<reviewed>.md` with
frontmatter naming both labs and the reviewed artifact, containing exactly
three parts: **one critique** of the reviewed lab through the reviewer lab's
distinctive lens, **one transferable technique** (from either direction), and
**one concrete suggestion** specific enough to become a swept parameter.

**Success criteria:** the critique must be one only *this* reviewer lab would
make (its lens, not generic review); run_ids cited from both labs where used;
if the reviewed lab adopts the suggestion, add `status: adopted — see <path>`
to the frontmatter.

**Provenance:** cite `<lab> run_NN` for every number; cross-lab claims cite
the *other* lab's runs.jsonl explicitly.
