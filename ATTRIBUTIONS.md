# Attributions

Centinela builds on the work of other people. Here is what we use, where it comes from and which part an AI did.

## Hackathon resources we use

The organizers of the Hackathon DefAcc 2026 provided resources in six themed folders. These are the ones Centinela uses, what for and in which files:

| Resource provided (folder) | What we use it for | Where |
|---|---|---|
| AgentDojo (Agent security) | Four public attack templates and 27 injection targets, translated into Spanish. Its implementation of the ProtectAI detector, as a reference for the local detector. Its public logs, to measure attack success on 22 models | `data/ataques.jsonl`, `src/centinela/detectors/local.py`, `evals/external.py` |
| AgentDyn (Agent security) | 28 injection targets. Its public logs, to measure attack success on 10 models | `data/ataques.jsonl`, `evals/external.py` |
| Inspect AI, from the UK AI Security Institute (AI control) | The lead bot test with four Claude models and two Google models (Gemini and the open model Gemma) | `evals/bot.py` |
| LlamaFirewall, from PurpleLlama, from Meta (Automated cyberdefense) | Its default rule, as the baseline of the filter, and the idea of looking for hidden text with invisible characters | `evals/injection_filter.py`, `src/centinela/detectors/rules.py` |
| SpaPhish (Epistemic defense) | 1395 real emails in Spanish for the false alarms, the phishing test and the review room. Its annotation guide, to define the persuasion tricks | `evals/cases.py`, `evals/phishing.py`, `evals/review_room.py`, `src/centinela/detectors/llm.py` |
| Technical sheet template | The structure of the sheet | `docs/ficha-tecnica.html`, `docs/technical-sheet.html` |

We also reviewed the rest of the resources, such as ControlArena, MCPTox and CyberSecEval, but they are not part of Centinela.

## Data

| Source | What we took | License |
|---|---|---|
| [AgentDojo](https://github.com/ethz-spylab/agentdojo) (Debenedetti et al., 2024) | Four public attack templates (`important_instructions`, `ignore_previous`, `injecagent`, `system_message`) and 27 injection targets | MIT |
| AgentDyn (Li et al., 2026) | 28 injection targets from the `shopping`, `github` and `dailylife` suites | MIT |
| SpaPhish | 1395 real emails in Spanish, anonymized, with phishing and persuasion labels from three annotators. The definitions of the persuasion tricks in `src/centinela/detectors/llm.py` follow its annotation guide | It states no license: we use it from a local copy and **do not redistribute it**. The repository only keeps the model's answers by identifier and metrics, never the text of the emails |
| [LlamaFirewall](https://github.com/meta-llama/PurpleLlama) (Meta) | Its default pattern for instruction injection, as the baseline in `evals/injection_filter.py`, and the idea of looking for hidden text with invisible characters | MIT |

The messages in `data/leads.jsonl`, those in `data/portadores.jsonl` and the Spanish translations in `data/ataques.jsonl` are ours. See “Use of AI”.

## Models

| Model | Use | License or access |
|---|---|---|
| `protectai/deberta-v3-base-prompt-injection-v2` | Detection baseline and optional local detector | Apache-2.0 |
| `Helsinki-NLP/opus-mt-es-en` | Translation into English before the local detector | Apache-2.0 |
| Claude Haiku 5.5, Claude Opus 5.5, Claude Sonnet 5.5 and Claude Haiku 4.5 | Reviewer and bot in the tests | Anthropic API |
| Gemini 3.5 Flash-Lite (Google) | Bot of test 2 and reviewer in the review with other providers | Gemini API (Google AI Studio) |
| Gemma 4 26B A4B (Google, open model) | Bot of test 2 | Gemini API (Google AI Studio); Gemma license |

## Libraries

Official Anthropic SDK, official Google SDK (`google-genai`), official OpenAI SDK (`openai`, for the [OpenRouter](https://openrouter.ai) API, which is compatible with OpenAI's), [Inspect AI](https://inspect.aisi.org.uk/) (UK AI Security Institute), transformers, PyTorch, scikit-learn, pytest, ruff, hatchling and uv. The exact versions are in `uv.lock`.

The Gmail demo can use the [Composio](https://composio.dev) SDK, in the optional `composio` group.

The website (`web/`) uses [Astro](https://astro.build) and is published on Cloudflare with `cf` and Wrangler; the exact versions are in its `pnpm-lock.yaml` files. Its fonts are Big Shoulders, Instrument Sans and Martian Mono, from Google Fonts, under the SIL Open Font License.

## Ideas

- Persuasion principles: Ferreira, A., Coventry, L. and Lenzini, G. (2015). *Principles of Persuasion in Social Engineering and Their Use in Phishing*.
- Putting the decisions in code and turning every attack that works into a test: [AgentBreak](https://github.com/urcuqui/AgentBreak) (C. Urcuqui).
- Defanging links before showing them (`hxxp://`, `[.]`) is a habit of incident response teams, to share indicators without anyone being able to open them. The review room applies it to what the person reviewing sees.
- Keeping the data used to write rules carefully apart from the data used to measure: we learned it from AgentDojo and from AgentDyn, which shows that a filter can stop the attacks and, at the same time, break normal tasks.

## Use of AI

This project was made in one day, with the help of AI, and we say so clearly:

- **Code:** written with Claude Code (models Claude Fable 5.2 and Claude Opus 5.5), directed and reviewed by the team. Each PR says so in its description.
- **Data:** the translations of the attacks, the carrier messages and the lead messages were generated with Claude. Each row says so in the `traduccion` or `generado_con_ia` fields. Human review is under way; until then they should be treated as synthetic data.
- **Documentation and technical sheet:** written with the help of AI and reviewed by the team.
- **Website (`web/`):** the design, the Vigía design system and the initial code were generated by Lovable from a prompt by the team; Claude Code moved them to Astro and prepared the publication.
- **Move to English (version 0.2.0):** the renames, the translations, the new tests and the documents were made with Claude Code, with helper agents, directed by the team. The tests in `tests/golden/` check that the published results and everything a model reads did not change. Each PR says so in its description.
- **Evaluation:** the reviewer and the bot of the tests are Anthropic models and, in the bot test and in the review with other providers, also Google models. The saved answers are in `results/`.
