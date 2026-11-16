"""Marcas que separan el mensaje de un cliente de las instrucciones del modelo."""


def wrap(text: str, marker: str) -> str:
    """Pone el mensaje entre marcas y neutraliza cualquier marca que traiga dentro."""
    clean = text.replace("<mensaje_cliente", "<mensaje-cliente").replace(
        "</mensaje_cliente", "</mensaje-cliente"
    )
    return f'<mensaje_cliente id="{marker}">\n{clean}\n</mensaje_cliente id="{marker}">'
