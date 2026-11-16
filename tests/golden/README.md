# Reference outputs (main@9810607)

These files are what Centinela did right before the project moved to English. They came from
running the code of that commit once, with its Spanish API. They are not edited by hand: they
exist to show that the renaming and the translation did not change the behavior.

| File | What it stores |
|---|---|
| `messages.json` | The 38 input messages: those of `test_reglas` (today `test_rules`), those of the demo inbox and the four examples of the site's review room |
| `cli.json` | Output and exit code of `centinela revisar` (today `centinela check`), as JSON and as text, with and without clinic labels |
| `cards.json`, `review_room.json` | Review cards and the decisions of the review room (with and without a second person) |
| `mail.json` | The five demo emails: the text the model sees, the verdict and the card |
| `classifier.json`, `llm_detector.json` | What the classifier decides and what it sends to a model (with a fake provider) |
| `protocol.json` | The exact text a model sees: instructions, schema, marker, labels |
| `rules_cases.json` | Decision and evidence of the rules on 652 benchmark cases |
| `resumen.md`, `resumen.json` | The published results tables |
| `records.sha256` | sha256 of each data file and of each results record |

The tests that use them are `tests/test_golden_*.py`. If one fails, the behavior changed, not
just the names. `protocol.json` stores the text the models see: translating it would invalidate
the figures in `results/`, which came from it.
