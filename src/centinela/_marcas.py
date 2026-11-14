"""Marcas que separan el mensaje de un cliente de las instrucciones del modelo."""


def envolver(texto: str, marca: str) -> str:
    """Pone el mensaje entre marcas y neutraliza cualquier marca que traiga dentro."""
    limpio = texto.replace("<mensaje_cliente", "<mensaje-cliente").replace(
        "</mensaje_cliente", "</mensaje-cliente"
    )
    return f'<mensaje_cliente id="{marca}">\n{limpio}\n</mensaje_cliente id="{marca}">'
