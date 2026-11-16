# Salidas de referencia (main@9810607)

Estos archivos son lo que hacía Centinela justo antes de pasar el proyecto a inglés. Salieron de
correr el código de ese commit una sola vez, con su API en español. No se editan a mano: sirven
para demostrar que el renombre y la traducción no cambiaron el comportamiento.

| Archivo | Qué guarda |
|---|---|
| `messages.json` | Los 38 mensajes de entrada: los de `test_reglas`, los de la bandeja de la demostración y los cuatro ejemplos de la sala del sitio |
| `cli.json` | Salida y código de salida de `centinela revisar` (JSON y texto, con y sin etiquetas de clínica) |
| `cards.json`, `review_room.json` | Tarjetas de revisión y las decisiones de la sala (con y sin segunda persona) |
| `mail.json` | Los cinco correos de la demostración: texto que ve el modelo, veredicto y tarjeta |
| `classifier.json`, `llm_detector.json` | Qué decide el clasificador y qué envía a un modelo (con un proveedor falso) |
| `protocol.json` | El texto exacto que ve un modelo: instrucciones, esquema, marcador, etiquetas |
| `rules_cases.json` | Decisión y evidencias de las reglas sobre 652 casos del banco de pruebas |
| `resumen.md`, `resumen.json` | Las tablas de resultados publicadas |
| `records.sha256` | sha256 de cada archivo de datos y de cada registro de resultados |

Las pruebas que los usan son `tests/test_golden_*.py`. Si una falla, cambió el comportamiento,
no solo los nombres. `protocol.json` guarda el texto que ven los modelos: traducirlo invalidaría
las cifras de `resultados/`, que salieron de ahí.
