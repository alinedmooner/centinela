# Sitio de Centinela

Página de presentación de Centinela y de su sistema de diseño, Vigía: https://centinela.alinedlabs.co

- Sitio estático hecho con [Astro](https://astro.build), sin frameworks de interfaz: en el navegador solo corren HTML, CSS y JavaScript propios.
- El diseño y el código inicial los generó Lovable a partir de un prompt del equipo; aquí se pasaron a componentes de Astro.
- La demo de la sala de revisión corre en el navegador (`src/scripts/desarmar.js`) y la página `/pruebas/` la comprueba.
- Las cabeceras de seguridad están en `public/_headers`: una CSP sin scripts ni estilos en línea, y `no-transform` para que Cloudflare no modifique las páginas.

## Desarrollo

```bash
cd web
pnpm install   # solo instala versiones con al menos 7 días de publicadas
pnpm dev       # http://localhost:4321
pnpm build     # genera dist/
```

## Publicación en Cloudflare

`cloudflare/` es un proyecto mínimo que publica `dist/` con el CLI `cf`, sin adaptador de Astro. Cloudflare sirve las páginas estáticas directo; solo las rutas `/api/*` pasan por el Worker (`cloudflare/src/worker.js`). El nombre del Worker, el dominio, las rutas y los límites están en `cloudflare/cloudflare.config.ts`.

```bash
cd web && pnpm build
cd cloudflare && pnpm install && pnpm exec cf deploy
```

## Revisión en vivo con Claude (`/api/revisar`)

El botón «Revisar con Claude, en vivo» de la sala manda el texto a `POST /api/revisar`. El Worker lo revisa con Claude Haiku 5.5 y el revisor de la librería (`DetectorLLM`): mismas instrucciones, mismo esquema y la misma regla, porque la decisión la toma el código con las dos respuestas del modelo. Si el modelo se niega o responde mal, el mensaje va a revisión humana.

- **Instrucciones:** `cloudflare/src/reviewer.js` se genera desde Python con `uv run python web/cloudflare/generate_reviewer.py`; `tests/test_web_revisor.py` falla si se desalinea.
- **Clave:** `ANTHROPIC_API_KEY` es un secreto de Cloudflare (`secret_text`); no está en el código ni llega al navegador. Se sube con la publicación, desde un archivo temporal que se borra al terminar:

  ```bash
  umask 077; grep -E '^ANTHROPIC_API_KEY=' ../../.env > /tmp/secreto.env
  pnpm exec cf deploy --secrets-file /tmp/secreto.env; rm -f /tmp/secreto.env
  ```

- **Límites:** hasta 2000 caracteres por mensaje y 700 tokens de respuesta. Hay 6 revisiones por minuto por visitante y 60 por minuto en total, por ubicación de Cloudflare. Solo acepta peticiones con el origen del sitio. Cada revisión cuesta unos 0,0002 USD (unos 1400 tokens de entrada y 100 de salida).
- **Privacidad:** el texto no se guarda ni se registra; viaja a la API de Anthropic para revisarlo.
- **Estado actual: apagada** desde el fin del hackathon (2026-11-16). Para volver a encenderla, cambien `REVISION_EN_VIVO` a `'activa'` y publiquen con `--secrets-file`.
- **Apagarla** (después de una presentación): en `cloudflare.config.ts`, `REVISION_EN_VIVO: bindings.text('apagada')`, y `pnpm exec cf deploy`. El botón muestra que está apagado y la demostración en el navegador sigue funcionando. Para borrar también la clave, usen `npx wrangler secret delete ANTHROPIC_API_KEY --name centinela-web`.
- **SDK:** el Worker usa el SDK oficial `@anthropic-ai/sdk` (licencia Apache 2.0).
