# Resultados guardados

Aquí están las respuestas de cada detector y de cada modelo, para que cualquiera pueda rehacer las tablas sin clave y revisar caso por caso.

| Ruta | Contenido |
|---|---|
| `resumen.md`, `resumen.json` | Las tres tablas, generadas por `evals/tabla.py` |
| `bot/test/<modelo>__<defensa>.jsonl` | Prueba 2. Una línea por mensaje: etiqueta esperada, etiqueta que salió y quién decidió |
| `filtro/test/<detector>.jsonl` | Prueba 1. Una línea por caso: si el detector lo marcó |
| `filtro/test/casos.jsonl` | Índice de los casos (grupo, idioma, si es ataque), sin el texto |
| `phishing/<modelo>.jsonl` | Prueba 3. Respuesta del revisor por correo, identificado por los primeros 16 caracteres de su `hash` en SpaPhish |
| `phishing/resumen.json` | Métricas de la prueba 3 |
| `reglas_congeladas.txt` | Huella de las reglas en el momento en que se congelaron, antes de medir |

Ningún archivo contiene el texto de los correos de SpaPhish.

## Rehacer las tablas sin clave

```bash
uv run --extra evals python evals/tabla.py
```

## Repetir las pruebas

Hace falta `ANTHROPIC_API_KEY` en `.env`. Para la línea base del modelo abierto, el extra `local`. Para los correos reales, una copia local de SpaPhish.

```bash
# Prueba 1: el filtro
uv run --extra evals python evals/filtro.py --detectores reglas llamafirewall claude --spaphish RUTA.csv
uv run --extra evals --extra local python evals/filtro.py --detectores local --spaphish RUTA.csv --max-spaphish 300
uv run --extra evals --extra local python evals/filtro.py --detectores local_traduccion

# Prueba 2: el bot (una corrida por condición y por modelo)
uv run --extra evals inspect eval evals/bot.py -T defensa=ninguna \
    --model anthropic/claude-opus-5-5 --log-dir resultados/crudo/bot
uv run --extra evals python evals/tabla.py --exportar-bot resultados/crudo/bot

# Prueba 3: phishing
uv run --extra evals python evals/phishing.py --spaphish RUTA.csv
```

## Cómo leer estos números

- Son de la partición `test`, que no se usó para escribir las reglas.
- Cada prueba se corrió una vez, el 14 de noviembre de 2026. Los modelos no permiten fijar la temperatura, así que otra corrida puede variar un poco.
- En la prueba 1, un detector que no pudo responder cuenta como «marcado», porque en ese caso el guardia manda el mensaje a una persona.
- Con el modelo abierto local se usaron 300 correos legítimos de SpaPhish, por tiempo; con los demás detectores, 462.
- La variante con traducción se midió sin los correos de SpaPhish.
