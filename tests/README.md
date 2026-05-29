# efferents tests

Tests are split by whether they exercise lab-agnostic framework code or
QML-specific behavior from the reference lab.

- `tests/test_*.py` — generic framework tests. Run against the
  `smoke_lab_config` fixture in `conftest.py`. Must pass without QML data
  or auto-qml available.
- `tests/lab_reference/test_*.py` — QML-specific tests inherited from
  the auto-qml reference lab. Currently `@pytest.mark.skip`-ed. They will
  re-enable when auto-qml depends on efferents as a pip package and these
  tests move into auto-qml's own test suite.
- `tests/integration/test_smoke_lab_e2e.py` — end-to-end test against
  `examples/smoke-lab/`. Marked `@pytest.mark.integration`; opt in via
  `pytest -m integration`.

## Running

- All generic + smoke tests: `uv run pytest tests/ --ignore=tests/lab_reference`
- Integration only: `uv run pytest -m integration`
