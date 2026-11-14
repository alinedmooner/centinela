# Resultados

Partición: `test`. Tablas generadas por `evals/tabla.py`.

## Prueba 2: el bot de leads frente a mensajes con trampa

| Modelo | Condición | Corridas | Ataques que cambian la etiqueta | Por corrida | Mensajes normales bien clasificados | Mensajes normales enviados a revisión |
|---|---|---|---|---|---|---|
| claude-haiku-4-5 | Sin defensa (línea base) | 1 | 1,4 % (1/70; IC 95 %: 0,3 % a 7,7 %) | 1 de 70 | 100,0 % (70/70; IC 95 %: 94,8 % a 100,0 %) | 0,0 % (0/70; IC 95 %: 0,0 % a 5,2 %) |
| claude-haiku-4-5 | Defensa solo en el prompt | 1 | 0,0 % (0/70; IC 95 %: 0,0 % a 5,2 %) | 0 de 70 | 100,0 % (70/70; IC 95 %: 94,8 % a 100,0 %) | 0,0 % (0/70; IC 95 %: 0,0 % a 5,2 %) |
| claude-haiku-5-5 | Sin defensa (línea base) | 1 | 0,0 % (0/70; IC 95 %: 0,0 % a 5,2 %) | 0 de 70 | 98,6 % (69/70; IC 95 %: 92,3 % a 99,7 %) | 0,0 % (0/70; IC 95 %: 0,0 % a 5,2 %) |
| claude-haiku-5-5 | Defensa solo en el prompt | 1 | 0,0 % (0/70; IC 95 %: 0,0 % a 5,2 %) | 0 de 70 | 98,6 % (69/70; IC 95 %: 92,3 % a 99,7 %) | 0,0 % (0/70; IC 95 %: 0,0 % a 5,2 %) |
| claude-haiku-5-5 | Centinela: reglas + código | 1 | 0,0 % (0/70; IC 95 %: 0,0 % a 5,2 %) | 0 de 70 | 98,6 % (69/70; IC 95 %: 92,3 % a 99,7 %) | 0,0 % (0/70; IC 95 %: 0,0 % a 5,2 %) |
| claude-haiku-5-5 | Centinela: reglas + revisor + código | 1 | 0,0 % (0/70; IC 95 %: 0,0 % a 5,2 %) | 0 de 70 | 94,3 % (66/70; IC 95 %: 86,2 % a 97,8 %) | 4,3 % (3/70; IC 95 %: 1,5 % a 11,9 %) |
| claude-opus-5-5 | Sin defensa (línea base) | 1 | 32,9 % (23/70; IC 95 %: 23,0 % a 44,5 %) | 23 de 70 | 100,0 % (70/70; IC 95 %: 94,8 % a 100,0 %) | 0,0 % (0/70; IC 95 %: 0,0 % a 5,2 %) |
| claude-opus-5-5 | Defensa solo en el prompt | 1 | 0,0 % (0/70; IC 95 %: 0,0 % a 5,2 %) | 0 de 70 | 100,0 % (70/70; IC 95 %: 94,8 % a 100,0 %) | 0,0 % (0/70; IC 95 %: 0,0 % a 5,2 %) |
| claude-opus-5-5 | Centinela: reglas + código | 1 | 0,0 % (0/70; IC 95 %: 0,0 % a 5,2 %) | 0 de 70 | 100,0 % (70/70; IC 95 %: 94,8 % a 100,0 %) | 0,0 % (0/70; IC 95 %: 0,0 % a 5,2 %) |
| claude-opus-5-5 | Centinela: reglas + revisor + código | 1 | 0,0 % (0/70; IC 95 %: 0,0 % a 5,2 %) | 0 de 70 | 95,7 % (67/70; IC 95 %: 88,1 % a 98,5 %) | 4,3 % (3/70; IC 95 %: 1,5 % a 11,9 %) |

## Prueba 1: el filtro en inglés y en español

En las columnas de ataques, más alto es mejor; en las de falsas alarmas, más bajo.

| Detector | Ataques públicos, inglés | Ataques públicos, español | Ataques al bot de leads, español | Falsas alarmas: mensajes normales, inglés | Falsas alarmas: mensajes normales, español | Falsas alarmas: leads normales | Falsas alarmas: correos legítimos reales |
|---|---|---|---|---|---|---|---|
| Regla por defecto de LlamaFirewall (línea base) | 0,0 % (0/112) | 0,0 % (0/112) | 0,0 % (0/70) | 0,0 % (0/41) | 0,0 % (0/41) | 0,0 % (0/70) | 0,0 % (0/462) |
| Modelo abierto ProtectAI (línea base) | 70,5 % (79/112) | 78,6 % (88/112) | 91,4 % (64/70) | 4,9 % (2/41) | 31,7 % (13/41) | 61,4 % (43/70) | 52,7 % (158/300) |
| Modelo abierto + traducción al inglés | 70,5 % (79/112) | 64,3 % (72/112) | 48,6 % (34/70) | 4,9 % (2/41) | 7,3 % (3/41) | 2,9 % (2/70) | s. d. |
| Centinela: reglas | 100,0 % (112/112) | 75,0 % (84/112) | 71,4 % (50/70) | 0,0 % (0/41) | 0,0 % (0/41) | 0,0 % (0/70) | 0,0 % (0/462) |
| Centinela: revisor con Claude Haiku 5.5 | 100,0 % (112/112) | 100,0 % (112/112) | 97,1 % (68/70) | 0,0 % (0/41) | 0,0 % (0/41) | 0,0 % (0/70) | 0,4 % (2/462) |

## Prueba 3: phishing en español y sus trucos

1395 correos reales en español, 731 de phishing.

| Detector de phishing | Aciertos | Precisión | Cobertura | F1 |
|---|---|---|---|---|
| Clasificador clásico entrenado con el conjunto (línea base) | 93,3 % | 97,6 % | 89,5 % | 0,934 |
| Centinela: revisor con claude-haiku-5-5, sin entrenamiento | 85,0 % | 81,0 % | 93,3 % | 0,867 |

| Truco de persuasión | Frecuencia en el conjunto | F1 del revisor | F1 de decir siempre lo más común |
|---|---|---|---|
| autoridad | 92,0 % | 0,793 | 0,958 |
| prueba_social | 10,2 % | 0,352 | 0,000 |
| simpatia_engano | 91,2 % | 0,527 | 0,954 |
| compromiso_reciprocidad | 36,3 % | 0,215 | 0,000 |
| distraccion_urgencia | 75,1 % | 0,872 | 0,857 |
