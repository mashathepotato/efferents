# Hypothesis generation

**Input:** `challenge.md` + the lab's dataset description (`datagen.py`
docstring or real-data notes).

**Output:** the `goal:` field of `efferents.yaml` — one sentence naming the
metric, the direction, the swept knob, and the constraint (efferents renders
it into `001_hypothesis.md` at run time).

**Success criteria:** falsifiable — it must name a measurable quantity that
could fail to improve; a reader can tell from the sentence alone what a
null result looks like.

**Provenance:** none required at this stage; the run attaches it.
