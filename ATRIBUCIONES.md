# Atribuciones

Centinela se apoya en trabajo de otras personas. Aquí está lo que usamos, de dónde viene y qué parte hizo una IA.

## Datos

| Fuente | Qué tomamos | Licencia |
|---|---|---|
| [AgentDojo](https://github.com/ethz-spylab/agentdojo) (Debenedetti et al., 2024) | Cuatro plantillas públicas de ataque (`important_instructions`, `ignore_previous`, `injecagent`, `system_message`) y 27 objetivos de inyección | MIT |
| AgentDyn (Li et al., 2026) | 28 objetivos de inyección de las suites `shopping`, `github` y `dailylife` | MIT |
| SpaPhish | 1395 correos reales en español, anonimizados, con etiquetas de phishing y de persuasión de tres anotadores. Las definiciones de los trucos de persuasión de `centinela/detectores/llm.py` siguen su guía de anotación | No indica licencia: lo usamos desde una copia local y **no lo redistribuimos**. El repositorio solo guarda respuestas del modelo por identificador y métricas, nunca el texto de los correos |
| [LlamaFirewall](https://github.com/meta-llama/PurpleLlama) (Meta) | Su patrón por defecto para inyección de instrucciones, como línea base en `evals/filtro.py`, y la idea de buscar texto escondido con caracteres invisibles | MIT |

Los mensajes de `datos/leads.jsonl`, los de `datos/portadores.jsonl` y las traducciones al español de `datos/ataques.jsonl` son nuestros. Ver «Uso de IA».

## Modelos

| Modelo | Uso | Licencia o acceso |
|---|---|---|
| `protectai/deberta-v3-base-prompt-injection-v2` | Línea base de detección y detector local opcional | Apache-2.0 |
| `Helsinki-NLP/opus-mt-es-en` | Traducción al inglés antes del detector local | Apache-2.0 |
| Claude Haiku 5.5, Claude Opus 5.5 y Claude Haiku 4.5 | Revisor y bot en las pruebas | API de Anthropic |

## Librerías

SDK oficial de Anthropic, [Inspect AI](https://inspect.aisi.org.uk/) (UK AI Security Institute), transformers, PyTorch, scikit-learn, pytest, ruff, hatchling y uv. Las versiones exactas están en `uv.lock`.

## Ideas

- Principios de persuasión: Ferreira, A., Coventry, L. y Lenzini, G. (2015). *Principles of Persuasion in Social Engineering and Their Use in Phishing*.
- Poner las decisiones en código y convertir cada ataque que funciona en una prueba: [AgentBreak](https://github.com/urcuqui/AgentBreak) (C. Urcuqui).
- Separar con cuidado los datos para escribir reglas de los datos para medir: lo aprendimos de AgentDojo y de AgentDyn, que muestra que un filtro puede frenar los ataques y a la vez romper las tareas normales.

## Uso de IA

Este proyecto se hizo en un día, con ayuda de IA, y lo decimos con claridad:

- **Código:** escrito con Claude Code (modelo Claude Fable 5.2), dirigido y revisado por el equipo. Cada commit generado así lleva la línea `Co-Authored-By: Claude`.
- **Datos:** las traducciones de los ataques, los mensajes portadores y los mensajes de leads fueron generados con Claude. Cada fila lo indica en los campos `traduccion` o `generado_con_ia`. La revisión humana está en curso; hasta entonces deben tratarse como datos sintéticos.
- **Documentación y ficha técnica:** redactadas con ayuda de IA y revisadas por el equipo.
- **Evaluación:** el revisor y el bot de las pruebas son modelos de Anthropic. Las respuestas guardadas están en `resultados/`.
