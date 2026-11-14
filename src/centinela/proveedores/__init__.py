"""Conexiones con modelos de lenguaje. El de Anthropic necesita el extra ``llm``."""

from centinela.proveedores.base import ErrorProveedor, Proveedor, RespuestaModelo

__all__ = ["ErrorProveedor", "Proveedor", "RespuestaModelo"]
