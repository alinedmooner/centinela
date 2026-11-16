# Cómo contribuir

Gracias por querer mejorar Centinela. Todo aporte entra por un pull request (PR) hacia `main`.

## Preparar el entorno

```bash
uv sync
uv run pytest
uv run ruff check .
```

Las pruebas no usan internet ni claves. Si tu cambio necesita un modelo, pruébalo con un proveedor falso, como hacen `tests/test_clasificador.py` y `tests/test_detector_llm.py`.

## Tres aportes fáciles

### 1. Agregar un caso al banco de pruebas

Cada caso es una línea en un archivo de `data/`. El formato está en `data/README.md`.

1. Agrega la línea al archivo que corresponda.
2. Corre `python3 scripts/validate_data.py`.
3. En el PR, di de dónde viene el caso y si lo escribiste tú o lo generó una IA.

No uses datos personales reales: nombres, teléfonos y correos deben ser inventados.

### 2. Agregar un detector

Un detector es una clase con un atributo `nombre` y un método `revisar(texto)` que devuelve un `Hallazgo`. Mira `src/centinela/detectores/base.py`. Si no puede responder, devuelve un `Hallazgo` con `error` en vez de lanzar una excepción.

### 3. Conectar otro proveedor de modelos

Un proveedor es una clase con un atributo `nombre` y un método `responder_json(sistema, mensaje, esquema)`. Mira `src/centinela/proveedores/base.py` y el ejemplo de `anthropic.py`.

## Reglas del detector de reglas

Las reglas se escriben mirando solo la partición `dev` de los datos. La partición `test` solo se usa para medir. Si cambias una regla, corre la prueba del filtro en `dev` y cuenta en el PR cómo cambiaron los números.

## Estilo

- Código y documentación en español, con nombres claros.
- `uv run ruff format .` antes de subir.
- Un PR por tema, con qué cambia, por qué y cómo probarlo.
- Si una parte la escribió una IA, dilo en el PR.

## Publicar una versión

Solo para quienes mantienen el proyecto.

1. Sube la versión en `pyproject.toml` y en `src/centinela/__init__.py`, corre `uv lock` y fusiona el PR.
2. Crea una versión (release) en GitHub con la etiqueta `vX.Y.Z`, igual a la versión del paquete.
3. El flujo `publicar.yml` construye el paquete, lo prueba y espera la aprobación en el entorno `pypi`. Al aprobarla, se publica en PyPI sin claves guardadas (trusted publishing) y con atestaciones de origen.

## Seguridad

Si encuentras una forma de saltarte el guardia, no abras un issue público. Sigue [SECURITY.md](SECURITY.md).
