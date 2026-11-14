"""Conexiones con modelos de lenguaje.

Cada proveedor necesita su extra: ``llm`` (Anthropic), ``google`` (Gemini y Gemma) u
``openrouter`` (cientos de modelos abiertos y cerrados). Para otro proveedor basta una
clase con un atributo ``nombre`` y el método ``responder_json`` (ver ``base.Proveedor``).
"""

from centinela.proveedores.base import ErrorProveedor, Proveedor, RespuestaModelo

PROVEEDORES = ("anthropic", "google", "openrouter")


def crear_proveedor(nombre: str = "anthropic", modelo: str | None = None) -> Proveedor:
    """El proveedor ``nombre``, con ``modelo`` o con su modelo por defecto (uno barato)."""
    if nombre == "anthropic":
        from centinela.proveedores import anthropic as modulo

        return modulo.ProveedorAnthropic(modelo or modulo.MODELO_POR_DEFECTO)
    if nombre == "google":
        from centinela.proveedores import google as modulo

        return modulo.ProveedorGoogle(modelo or modulo.MODELO_POR_DEFECTO)
    if nombre == "openrouter":
        from centinela.proveedores import openrouter as modulo

        return modulo.ProveedorOpenRouter(modelo or modulo.MODELO_POR_DEFECTO)
    raise ValueError(f"proveedor desconocido: {nombre}; usa uno de {', '.join(PROVEEDORES)}")


__all__ = ["PROVEEDORES", "ErrorProveedor", "Proveedor", "RespuestaModelo", "crear_proveedor"]
