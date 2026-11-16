# How to contribute

Thank you for wanting to improve Centinela. Every contribution comes in as a pull request (PR) to `main`.

## Set up the environment

```bash
uv sync
uv run pytest
uv run ruff check .
```

The tests use no internet and no keys. If your change needs a model, test it with a fake provider, as `tests/test_classifier.py` and `tests/test_llm_detector.py` do.

## Three easy contributions

### 1. Add a case to the benchmark

Each case is one line in a file in `data/`. The format is in `data/README.md`. The data stays in Spanish (see [Style](#style)).

1. Add the line to the file that fits.
2. Run `python3 scripts/validate_data.py`.
3. In the PR, say where the case comes from and whether you wrote it or an AI generated it.

Do not use real personal data: names, phone numbers and emails must be made up.

### 2. Add a detector

A detector is a class with a `name` attribute and a `check(text)` method that returns a `Finding`. See `src/centinela/detectors/base.py`. If it cannot answer, it returns a `Finding` with `error` instead of raising an exception.

### 3. Connect another model provider

A provider is a class with a `name` attribute and a `respond_json(system, message, schema)` method. See `src/centinela/providers/base.py` and the example in `anthropic.py`.

## Rules for the rules detector

The rules are written looking only at the `dev` split of the data. The `test` split is only used to measure. If you change a rule, run the filter test on `dev` and say in the PR how the numbers changed.

`src/centinela/detectors/rules.py` is pinned by a hash in `results/rules_frozen.txt`, and a test fails if the file changes without a new line there. If you change a rule on purpose, add a short paragraph at the end of that file saying what changed and why, followed by the line `sha256 de src/centinela/detectors/rules.py: <hash>` with the new hash. Never edit the older lines: they record what the published results were measured with.

## Style

- Code, comments and documentation in English, with clear names.
- Spanish stays on purpose in the benchmark data, the patterns of the detection rules, the model prompts and label definitions, and the Spanish messages used in tests. See the Language policy in [README.md](README.md#language-policy).
- Run `uv run ruff format .` before you push.
- One PR per topic, saying what changes, why and how to test it.
- If an AI wrote part of it, say so in the PR.

## Publish a release

Only for the people who maintain the project.

1. Bump the version in `pyproject.toml` and in `src/centinela/__init__.py`, run `uv lock` and merge the PR.
2. Create a release on GitHub with the tag `vX.Y.Z`, the same as the package version.
3. The `publish.yml` workflow builds the package, tests it and waits for approval in the `pypi` environment. Once approved, it publishes to PyPI without stored keys (trusted publishing) and with provenance attestations.

## Security

If you find a way around the guard, do not open a public issue. Follow [SECURITY.md](SECURITY.md).
