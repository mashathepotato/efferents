# Journal editor / indexer (not an LLM)

The index is generated deterministically by `crosslab.py` — labs at a glance,
per-lab run tables, review verdicts, cross-review listing, and the
adoption-chain callout. Rerun after any lab or review changes:

    .venv/bin/python examples/challengescape/crosslab.py

The one LLM-editable surface is review frontmatter (`status:` fields), which
the indexer renders. Keep the honesty paragraph at the top of the index
intact — it is the demo's credibility contract.
