# efferents tests

Tests are split by whether they exercise lab-agnostic framework code or
historical domain-specific behavior from the original reference lab.

- `tests/test_*.py` — generic framework tests. Run against the
  `smoke_lab_config` fixture in `conftest.py`. Must pass without data or code
  from the original reference lab.
- `tests/lab_reference/test_*.py` — domain-coupled tests inherited from the
  original reference lab. Currently `@pytest.mark.skip`-ed. They should
  ultimately live in that lab's own test suite.
- `tests/integration/test_smoke_lab_e2e.py` — end-to-end test against
  `examples/smoke-lab/`. Marked `@pytest.mark.integration`; opt in via
  `pytest -m integration`.

## Running

- All generic + smoke tests: `uv run pytest tests/ --ignore=tests/lab_reference`
- Integration only: `uv run pytest -m integration`
