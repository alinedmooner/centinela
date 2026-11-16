"""Markers that separate a customer's message from the model's instructions."""


def wrap(text: str, marker: str) -> str:
    """Puts the message between markers and neutralizes any marker it contains.

    The marker tag ``<mensaje_cliente>`` is Spanish on purpose: the model sees it.
    """
    clean = text.replace("<mensaje_cliente", "<mensaje-cliente").replace(
        "</mensaje_cliente", "</mensaje-cliente"
    )
    return f'<mensaje_cliente id="{marker}">\n{clean}\n</mensaje_cliente id="{marker}">'
