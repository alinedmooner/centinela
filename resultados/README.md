# Resultados guardados

Aquí están las respuestas de cada detector y de cada modelo, para que cualquiera pueda rehacer las tablas sin clave y revisar caso por caso.

| Ruta | Contenido |
|---|---|
| `resumen.md`, `resumen.json` | Las tablas de las cuatro pruebas, generadas por `evals/tabla.py` |
| `bot/test/<modelo>__<defensa>.jsonl` | Prueba 2. Una línea por mensaje: etiqueta esperada, etiqueta que salió y quién decidió |
| `filtro/test/<detector>.jsonl` | Prueba 1. Una línea por caso: si el detector lo marcó |
| `filtro/test/casos.jsonl` | Índice de los casos (grupo, idioma, si es ataque), sin el texto |
| `phishing/<modelo>.jsonl` | Prueba 3. Respuesta del revisor por correo, identificado por los primeros 16 caracteres de su `hash` en SpaPhish |
| `phishing/resumen.json` | Métricas de la prueba 3 |
| `revision/spaphish.jsonl` | Prueba 4. Una línea por correo, con el mismo identificador: enlaces activos antes y después de desarmar, destinos que muestra la tarjeta, qué pide y con qué presiona |
| `revision/resumen.json` | Métricas de la prueba 4 |
| `externos/asr_publico.json` | Prueba 5, externa: éxito del ataque «important_instructions» por modelo en los registros públicos de AgentDojo y AgentDyn (`evals/externos.py`) |
| `proveedores/<proveedor>-<modelo>.jsonl` y `.json` | Revisión con otros proveedores: el revisor de Centinela con Gemini en 20 casos en español de la partición de prueba (10 ataques y 10 mensajes normales), comparado con Claude Haiku 5.5 en los mismos casos (`evals/proveedores.py`) |
| `reglas_congeladas.txt` | Huella de las reglas en el momento en que se congelaron, antes de medir |

Ningún archivo contiene el texto de los correos de SpaPhish.

## Rehacer las tablas sin clave

```bash
uv run --extra evals python evals/tabla.py
```

## Repetir las pruebas

Hace falta `ANTHROPIC_API_KEY` en `.env` (y `GOOGLE_API_KEY` u `OPENROUTER_API_KEY` para los otros proveedores). Para la línea base del modelo abierto, el extra `local`. Para los correos reales, una copia local de SpaPhish.

```bash
# Prueba 1: el filtro
uv run --extra evals python evals/filtro.py --detectores reglas llamafirewall claude --spaphish RUTA.csv
uv run --extra evals --extra local python evals/filtro.py --detectores local --spaphish RUTA.csv --max-spaphish 300
uv run --extra evals --extra local python evals/filtro.py --detectores local_traduccion

# Prueba 2: el bot (una corrida por condición y por modelo)
uv run --extra evals inspect eval evals/bot.py -T defensa=ninguna \
    --model anthropic/claude-opus-5-5 --log-dir resultados/crudo/bot
# con modelos de Google (GOOGLE_API_KEY): -T esfuerzo=minimal es el razonamiento mínimo de Gemini
uv run --extra evals inspect eval evals/bot.py -T defensa=centinela -T esfuerzo=minimal \
    --model google/gemini-3.5-flash-lite --log-dir resultados/crudo/bot
uv run --extra evals python evals/tabla.py --exportar-bot resultados/crudo/bot

# Revisión con otros proveedores (20 casos)
uv run --extra evals python evals/proveedores.py --proveedor google

# Prueba 3: phishing
uv run --extra evals python evals/phishing.py --spaphish RUTA.csv

# Prueba 4: la sala de revisión (no usa clave)
uv run python evals/revision.py --spaphish RUTA.csv
```

## Cómo leer estos números

- Son de la partición `test`, que no se usó para escribir las reglas.
- Cada condición se corrió una vez, el 14 de noviembre de 2026, salvo Opus 5.5 sin defensa, que se corrió dos veces. Sonnet 5.5 y Haiku 4.5 con Centinela se sumaron por la tarde, con los mismos datos. Los modelos no permiten fijar la temperatura, así que otra corrida puede variar un poco.
- En la prueba 1, un detector que no pudo responder cuenta como «marcado», porque en ese caso el guardia manda el mensaje a una persona.
- Con el modelo abierto local se usaron 300 correos legítimos de SpaPhish, por tiempo; con los demás detectores, 462.
- La variante con traducción se midió sin los correos de SpaPhish.
- La prueba 4 no usa clave. Toma de la prueba 3 qué correos habría marcado como engaño el revisor, y arma la tarjeta de todos los correos, como si cada uno fuera a revisión.
- El desarmador de la prueba 4 se ajustó después de una primera pasada sobre estos mismos correos: no reconocía enlaces pegados a una palabra ni enlaces metidos dentro de otros. En esa pasada quedaban activos 7 enlaces en el phishing y 77 en los legítimos. Las pistas de la tarjeta (qué pide y con qué presiona) se escribieron antes de mirar estos correos y no se tocaron después.
