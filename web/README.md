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

`cloudflare/` es un proyecto mínimo que publica `dist/` como sitio estático con el CLI `cf`, sin adaptador de Astro ni código de servidor. El nombre del Worker, el dominio y el manejo de rutas están en `cloudflare/cloudflare.config.ts`.

```bash
cd web && pnpm build
cd cloudflare && pnpm install && pnpm exec cf deploy
```
