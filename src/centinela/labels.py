"""Example labels for a lead classifier. Each business defines its own.

The names and definitions are Spanish on purpose: they are the labels of the sales bot used
in the saved measurements, and the model sees the definitions.
"""

#: The label only the code assigns, never the model. It is not in any list of labels.
HUMAN_REVIEW = "human_review"

#: Label name -> definition given to the model.
LEAD_LABELS: dict[str, str] = {
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
