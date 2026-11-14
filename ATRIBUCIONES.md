# Atribuciones

Centinela se apoya en trabajo de otras personas. Aquí está lo que usamos, de dónde viene y qué parte hizo una IA.

## Recursos del hackathon que usamos

La organización del Hackathon DefAcc 2026 entregó recursos en seis carpetas temáticas. Estos son los que usa Centinela, para qué y en qué archivos:

| Recurso entregado (carpeta) | Para qué lo usamos | Dónde |
|---|---|---|
| AgentDojo (Seguridad de agentes) | Cuatro plantillas públicas de ataque y 27 objetivos de inyección, traducidos al español. Su implementación del detector de ProtectAI, como referencia para el detector local. Sus registros públicos, para medir el éxito de los ataques en 22 modelos | `datos/ataques.jsonl`, `src/centinela/detectores/local.py`, `evals/externos.py` |
| AgentDyn (Seguridad de agentes) | 28 objetivos de inyección. Sus registros públicos, para medir el éxito de los ataques en 10 modelos | `datos/ataques.jsonl`, `evals/externos.py` |
| Inspect AI, del UK AI Security Institute (Control de IA) | La prueba del bot de leads con cuatro modelos de Claude y dos de Google (Gemini y el modelo abierto Gemma) | `evals/bot.py` |
| LlamaFirewall, de PurpleLlama, de Meta (Ciberdefensa automatizada) | Su regla por defecto, como línea base del filtro, y la idea de buscar texto oculto con caracteres invisibles | `evals/filtro.py`, `src/centinela/detectores/reglas.py` |
| SpaPhish (Defensa epistémica) | 1395 correos reales en español para las falsas alarmas, la prueba de phishing y la sala de revisión. Su guía de anotación, para definir los trucos de persuasión | `evals/casos.py`, `evals/phishing.py`, `evals/revision.py`, `src/centinela/detectores/llm.py` |
| Plantilla de la ficha técnica | La estructura de la ficha | `docs/ficha-tecnica.html` |

También revisamos el resto de los recursos, como ControlArena, MCPTox y CyberSecEval, pero no forman parte de Centinela.

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
| Claude Haiku 5.5, Claude Opus 5.5, Claude Sonnet 5.5 y Claude Haiku 4.5 | Revisor y bot en las pruebas | API de Anthropic |
| Gemini 3.5 Flash-Lite (Google) | Bot de la prueba 2 y revisor en la revisión con otros proveedores | API de Gemini (Google AI Studio) |
| Gemma 4 26B A4B (Google, modelo abierto) | Bot de la prueba 2 | API de Gemini (Google AI Studio); licencia de Gemma |

## Librerías

SDK oficial de Anthropic, SDK oficial de Google (`google-genai`), SDK oficial de OpenAI (`openai`, para la API de [OpenRouter](https://openrouter.ai), compatible con la de OpenAI), [Inspect AI](https://inspect.aisi.org.uk/) (UK AI Security Institute), transformers, PyTorch, scikit-learn, pytest, ruff, hatchling y uv. Las versiones exactas están en `uv.lock`.

La demostración con Gmail puede usar el SDK de [Composio](https://composio.dev), en el grupo opcional `composio`.

El sitio web (`web/`) usa [Astro](https://astro.build) y se publica en Cloudflare con `cf` y Wrangler; las versiones exactas están en sus `pnpm-lock.yaml`. Sus fuentes son Big Shoulders, Instrument Sans y Martian Mono, de Google Fonts, con licencia SIL Open Font License.

## Ideas

- Principios de persuasión: Ferreira, A., Coventry, L. y Lenzini, G. (2015). *Principles of Persuasion in Social Engineering and Their Use in Phishing*.
- Poner las decisiones en código y convertir cada ataque que funciona en una prueba: [AgentBreak](https://github.com/urcuqui/AgentBreak) (C. Urcuqui).
- Desarmar enlaces antes de mostrarlos (`hxxp://`, `[.]`) es una costumbre de los equipos de respuesta a incidentes para compartir indicadores sin que se puedan abrir. La sala de revisión la aplica a lo que ve quien revisa.
- Separar con cuidado los datos para escribir reglas de los datos para medir: lo aprendimos de AgentDojo y de AgentDyn, que muestra que un filtro puede frenar los ataques y a la vez romper las tareas normales.

## Uso de IA

Este proyecto se hizo en un día, con ayuda de IA, y lo decimos con claridad:

- **Código:** escrito con Claude Code (modelos Claude Fable 5.2 y Claude Opus 5.5), dirigido y revisado por el equipo. Cada PR lo dice en su descripción.
- **Datos:** las traducciones de los ataques, los mensajes portadores y los mensajes de leads fueron generados con Claude. Cada fila lo indica en los campos `traduccion` o `generado_con_ia`. La revisión humana está en curso; hasta entonces deben tratarse como datos sintéticos.
- **Documentación y ficha técnica:** redactadas con ayuda de IA y revisadas por el equipo.
- **Sitio web (`web/`):** el diseño, el sistema de diseño Vigía y el código inicial los generó Lovable a partir de un prompt del equipo; Claude Code los pasó a Astro y preparó la publicación.
- **Evaluación:** el revisor y el bot de las pruebas son modelos de Anthropic y, en la prueba del bot y en la revisión con otros proveedores, también de Google. Las respuestas guardadas están en `resultados/`.
