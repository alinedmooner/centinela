"""Etiquetas de ejemplo para un clasificador de leads. Cada negocio puede definir las suyas."""

#: Etiqueta que solo asigna el código, nunca el modelo.
REVISION_HUMANA = "revision_humana"

#: Nombre de la etiqueta -> definición que se le da al modelo.
ETIQUETAS_LEADS: dict[str, str] = {
    "prioritario": (
        "Intención de compra clara e inmediata: quiere comprar o contratar ya, pide una "
        "cotización formal, una llamada o una reunión, o menciona un presupuesto o una fecha."
    ),
    "interesado": (
        "Muestra interés en un producto y pide información (precios, planes, características), "
        "sin urgencia ni compromiso."
    ),
    "consulta": (
        "Pregunta general que no es de compra: horarios, ubicación, medios de pago, políticas, "
        "vacantes."
    ),
    "soporte": (
        "Ya es cliente y tiene un problema, un reclamo o una solicitud sobre algo que compró."
    ),
    "spam": (
        "Publicidad no solicitada, ofertas de terceros, cadenas o contenido sin relación con "
        "el negocio."
    ),
}
