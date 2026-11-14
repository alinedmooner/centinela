"""Valida los datos del banco de pruebas de Centinela.

Revisa `ataques.jsonl`, `portadores.jsonl` y `leads.jsonl`: que cada línea sea un
objeto JSON, que estén los campos esperados con valores permitidos, que los
identificadores no se repitan, que cada ataque apunte a un mensaje base válido,
que los conteos por etiqueta, técnica y split sean los acordados y que ninguna
línea contenga una clave de API.

Uso:
    python3 scripts/validar_datos.py              # valida la carpeta datos/ del repositorio
    python3 scripts/validar_datos.py otra/carpeta # valida otra carpeta

Solo usa la biblioteca estándar (Python 3.11 o superior). Imprime un resumen
corto y termina con código 1 si encuentra cualquier error.

Si agregas casos, actualiza también los conteos esperados de este archivo.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

DATOS = Path(__file__).resolve().parent.parent / "datos"

# Ninguna línea puede contener este prefijo (es el de las claves de API). Se arma en dos
# partes para que este mismo archivo no haga saltar a los buscadores de secretos.
PREFIJO_PROHIBIDO = "sk-" + "ant-"
SPLITS = ("dev", "test")

# ---------------------------------------------------------------- ataques.jsonl
PLANTILLAS = ("important_instructions", "ignore_previous", "injecagent", "system_message")
# Quién hizo la traducción. Hoy todas son de IA; amplía la lista cuando haya revisión humana.
TRADUCCIONES = ("ia",)
# Por origen: prefijo del id, split, licencia, plantillas y número de objetivos por suite.
ORIGENES = {
    "agentdojo": {
        "prefijo": "adj",
        "split": "dev",
        "licencia": "MIT",
        "plantillas": ("important_instructions", "ignore_previous"),
        "objetivos": {"banking": 9, "slack": 5, "travel": 7, "workspace": 6},
    },
    "agentdyn": {
        "prefijo": "ady",
        "split": "test",
        "licencia": "MIT",
        "plantillas": PLANTILLAS,
        "objetivos": {"shopping": 9, "github": 9, "dailylife": 10},
    },
}
CAMPOS_ATAQUE = (
    "id",
    "origen",
    "suite",
    "objetivo_id",
    "plantilla",
    "split",
    "texto_en",
    "texto_es",
    "licencia",
    "traduccion",
)

# ------------------------------------------------------------- portadores.jsonl
# Por tipo: cuántos textos y entre cuántas palabras debe tener cada uno.
PORTADORES = {
    "correo": {"cantidad": 30, "palabras": (60, 120)},
    "whatsapp": {"cantidad": 30, "palabras": (15, 50)},
}
CAMPOS_PORTADOR = ("id", "tipo", "texto_es", "texto_en", "generado_con_ia")

# ------------------------------------------------------------------ leads.jsonl
ETIQUETAS = ("prioritario", "interesado", "consulta", "soporte", "spam")
ETIQUETA_OBJETIVO = "prioritario"
NORMALES_POR_ETIQUETA = {"dev": 6, "test": 14}
PALABRAS_NORMAL = (8, 60)
# Por técnica: cuántos ataques van a dev y cuántos a test.
TECNICAS = {
    "orden_directa": {"dev": 6, "test": 4},
    "autoridad": {"dev": 6, "test": 4},
    "sistema_falso": {"dev": 6, "test": 4},
    "nota_al_asistente": {"dev": 6, "test": 4},
    "formato_salida": {"dev": 6, "test": 4},
    "urgencia": {"dev": 0, "test": 10},
    "oculto": {"dev": 0, "test": 10},
    "ingles": {"dev": 0, "test": 10},
    "rol": {"dev": 0, "test": 10},
    "ofuscado": {"dev": 0, "test": 10},
}
ATAQUES_POR_ETIQUETA_BASE = 25
CAMPOS_NORMAL = ("id", "texto", "etiqueta", "tipo", "split", "generado_con_ia")
CAMPOS_LEAD_ATAQUE = (
    "id",
    "texto",
    "etiqueta",
    "tipo",
    "tecnica",
    "etiqueta_objetivo",
    "base_id",
    "split",
    "generado_con_ia",
)
# Un ataque «oculto» debe traer al menos uno de estos mecanismos.
ESPACIO_ANCHO_CERO = "\N{ZERO WIDTH SPACE}"  # U+200B
RE_ETIQUETAS_UNICODE = re.compile("[\U000e0000-\U000e007f]")
SALTOS_SEGUIDOS_OCULTO = 10

RE_ID_PORTADOR = re.compile(r"por-\d{3}")
RE_ID_NORMAL = re.compile(r"lead-\d{3}")
RE_ID_LEAD_ATAQUE = re.compile(r"lead-atk-\d{3}")
RE_OBJETIVO = re.compile(r"injection_task_(\d+)")

MAX_ERRORES_MOSTRADOS = 40


def leer_jsonl(ruta: Path, errores: list[str]) -> list[tuple[str, dict]]:
    """Lee un JSONL y devuelve pares (ubicación, fila). Anota los problemas en `errores`."""
    if not ruta.is_file():
        errores.append(f"{ruta.name}: no existe el archivo")
        return []
    try:
        contenido = ruta.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        errores.append(f"{ruta.name}: no es UTF-8 válido ({error})")
        return []
    lineas = contenido.split("\n")
    if lineas and lineas[-1] == "":
        lineas.pop()
    filas = []
    for numero, linea in enumerate(lineas, start=1):
        donde = f"{ruta.name}:{numero}"
        if PREFIJO_PROHIBIDO in linea:
            errores.append(f"{donde}: contiene «{PREFIJO_PROHIBIDO}» (¿una clave de API?)")
        if not linea.strip():
            errores.append(f"{donde}: línea vacía")
            continue
        try:
            fila = json.loads(linea)
        except json.JSONDecodeError as error:
            errores.append(f"{donde}: JSON inválido ({error.msg})")
            continue
        if not isinstance(fila, dict):
            errores.append(f"{donde}: la línea no es un objeto JSON")
            continue
        if any(PREFIJO_PROHIBIDO in valor for valor in fila.values() if isinstance(valor, str)):
            errores.append(f"{donde}: un campo contiene «{PREFIJO_PROHIBIDO}»")
        filas.append((donde, fila))
    return filas


def revisar_campos(fila: dict, campos: tuple[str, ...], donde: str, errores: list[str]) -> bool:
    """Exige exactamente `campos`: `generado_con_ia` booleano y los demás, texto no vacío."""
    faltan = [campo for campo in campos if campo not in fila]
    sobran = [campo for campo in fila if campo not in campos]
    if faltan:
        errores.append(f"{donde}: faltan campos {faltan}")
    if sobran:
        errores.append(f"{donde}: campos desconocidos {sobran}")
    bien = not faltan and not sobran
    for campo in campos:
        if campo not in fila:
            continue
        valor = fila[campo]
        if campo == "generado_con_ia":
            # true si el texto lo escribió una IA; false si lo escribió una persona.
            if not isinstance(valor, bool):
                errores.append(f"{donde}: «generado_con_ia» debe ser true o false")
                bien = False
        elif not isinstance(valor, str) or not valor.strip():
            errores.append(f"{donde}: «{campo}» debe ser un texto no vacío")
            bien = False
    return bien


def revisar_valor(fila: dict, campo: str, permitidos, donde: str, errores: list[str]) -> bool:
    if fila[campo] not in permitidos:
        errores.append(f"{donde}: «{campo}»={fila[campo]!r} no está entre {sorted(permitidos)}")
        return False
    return True


def revisar_ids(filas: list[tuple[str, dict]], errores: list[str]) -> None:
    vistos: dict[str, str] = {}
    for donde, fila in filas:
        ident = fila.get("id")
        if not isinstance(ident, str):
            continue
        if ident in vistos:
            errores.append(f"{donde}: id repetido {ident!r} (ya está en {vistos[ident]})")
        else:
            vistos[ident] = donde


def revisar_conteo(nombre: str, real: int, esperado: int, errores: list[str]) -> None:
    if real != esperado:
        errores.append(f"{nombre}: hay {real} y se esperaban {esperado}")


def palabras(texto: str) -> int:
    return len(texto.split())


def validar_ataques(ruta: Path, errores: list[str]) -> Counter:
    filas = leer_jsonl(ruta, errores)
    revisar_ids(filas, errores)
    por_split: Counter = Counter()
    # (origen, suite) -> objetivo_id -> plantillas vistas
    vistos: dict[tuple[str, str], dict[str, list[str]]] = {}
    for donde, fila in filas:
        if not revisar_campos(fila, CAMPOS_ATAQUE, donde, errores):
            continue
        if not revisar_valor(fila, "origen", ORIGENES, donde, errores):
            continue
        origen = ORIGENES[fila["origen"]]
        bien = revisar_valor(fila, "suite", origen["objetivos"], donde, errores)
        bien &= revisar_valor(fila, "plantilla", origen["plantillas"], donde, errores)
        bien &= revisar_valor(fila, "split", (origen["split"],), donde, errores)
        bien &= revisar_valor(fila, "licencia", (origen["licencia"],), donde, errores)
        bien &= revisar_valor(fila, "traduccion", TRADUCCIONES, donde, errores)
        objetivo = RE_OBJETIVO.fullmatch(fila["objetivo_id"])
        if objetivo is None:
            errores.append(f"{donde}: «objetivo_id» debe tener la forma injection_task_N")
            bien = False
        if not bien:
            continue
        esperado = f"{origen['prefijo']}-{fila['suite']}-{objetivo.group(1)}-{fila['plantilla']}"
        if fila["id"] != esperado:
            errores.append(f"{donde}: el id {fila['id']!r} debería ser {esperado!r}")
        if fila["texto_en"] == fila["texto_es"]:
            errores.append(f"{donde}: «texto_en» y «texto_es» son iguales")
        por_split[fila["split"]] += 1
        clave = (fila["origen"], fila["suite"])
        vistos.setdefault(clave, {}).setdefault(fila["objetivo_id"], []).append(fila["plantilla"])

    for nombre_origen, origen in ORIGENES.items():
        for suite, cantidad in origen["objetivos"].items():
            objetivos = vistos.get((nombre_origen, suite), {})
            revisar_conteo(
                f"{ruta.name}: objetivos de {nombre_origen}/{suite}",
                len(objetivos),
                cantidad,
                errores,
            )
            for objetivo_id, plantillas in objetivos.items():
                if sorted(plantillas) != sorted(origen["plantillas"]):
                    errores.append(
                        f"{ruta.name}: {nombre_origen}/{suite}/{objetivo_id} tiene las plantillas "
                        f"{sorted(plantillas)} y se esperaban {sorted(origen['plantillas'])}"
                    )
        total = sum(origen["objetivos"].values()) * len(origen["plantillas"])
        revisar_conteo(
            f"{ruta.name}: filas en {origen['split']}", por_split[origen["split"]], total, errores
        )
    return por_split


def validar_portadores(ruta: Path, errores: list[str]) -> Counter:
    filas = leer_jsonl(ruta, errores)
    revisar_ids(filas, errores)
    por_tipo: Counter = Counter()
    for donde, fila in filas:
        if not revisar_campos(fila, CAMPOS_PORTADOR, donde, errores):
            continue
        if RE_ID_PORTADOR.fullmatch(fila["id"]) is None:
            errores.append(f"{donde}: el id {fila['id']!r} debe tener la forma por-NNN")
        if not revisar_valor(fila, "tipo", PORTADORES, donde, errores):
            continue
        por_tipo[fila["tipo"]] += 1
        minimo, maximo = PORTADORES[fila["tipo"]]["palabras"]
        for campo in ("texto_es", "texto_en"):
            cantidad = palabras(fila[campo])
            if not minimo <= cantidad <= maximo:
                errores.append(
                    f"{donde}: «{campo}» tiene {cantidad} palabras y un {fila['tipo']} "
                    f"debe tener entre {minimo} y {maximo}"
                )
        if fila["texto_es"] == fila["texto_en"]:
            errores.append(f"{donde}: «texto_es» y «texto_en» son iguales")
    for tipo, regla in PORTADORES.items():
        revisar_conteo(
            f"{ruta.name}: textos de tipo {tipo}", por_tipo[tipo], regla["cantidad"], errores
        )
    return por_tipo


def trae_algo_oculto(texto: str) -> bool:
    return (
        ESPACIO_ANCHO_CERO in texto
        or RE_ETIQUETAS_UNICODE.search(texto) is not None
        or "\n" * SALTOS_SEGUIDOS_OCULTO in texto
    )


def validar_leads(ruta: Path, errores: list[str]) -> Counter:
    filas = leer_jsonl(ruta, errores)
    revisar_ids(filas, errores)
    por_tipo_y_split: Counter = Counter()
    normales: dict[str, dict] = {}
    ataques: list[tuple[str, dict]] = []
    textos: dict[str, str] = {}

    for donde, fila in filas:
        tipo = fila.get("tipo")
        if tipo not in ("normal", "ataque"):
            errores.append(f"{donde}: «tipo»={tipo!r} debe ser 'normal' o 'ataque'")
            continue
        campos = CAMPOS_NORMAL if tipo == "normal" else CAMPOS_LEAD_ATAQUE
        if not revisar_campos(fila, campos, donde, errores):
            continue
        if fila["texto"] in textos:
            errores.append(f"{donde}: el texto está repetido (ya está en {textos[fila['texto']]})")
        textos.setdefault(fila["texto"], donde)
        bien = revisar_valor(fila, "etiqueta", ETIQUETAS, donde, errores)
        bien &= revisar_valor(fila, "split", SPLITS, donde, errores)
        if tipo == "normal":
            if RE_ID_NORMAL.fullmatch(fila["id"]) is None:
                errores.append(f"{donde}: el id {fila['id']!r} debe tener la forma lead-NNN")
                bien = False
            cantidad = palabras(fila["texto"])
            if not PALABRAS_NORMAL[0] <= cantidad <= PALABRAS_NORMAL[1]:
                errores.append(
                    f"{donde}: el texto tiene {cantidad} palabras y debe tener entre "
                    f"{PALABRAS_NORMAL[0]} y {PALABRAS_NORMAL[1]}"
                )
            if bien:
                normales[fila["id"]] = fila
                por_tipo_y_split[("normal", fila["split"])] += 1
        else:
            if RE_ID_LEAD_ATAQUE.fullmatch(fila["id"]) is None:
                errores.append(f"{donde}: el id {fila['id']!r} debe tener la forma lead-atk-NNN")
                bien = False
            bien &= revisar_valor(fila, "tecnica", TECNICAS, donde, errores)
            bien &= revisar_valor(fila, "etiqueta_objetivo", (ETIQUETA_OBJETIVO,), donde, errores)
            if bien:
                ataques.append((donde, fila))
                por_tipo_y_split[("ataque", fila["split"])] += 1

    # Mensajes normales: conteo exacto por etiqueta y split.
    conteo_normales = Counter((fila["etiqueta"], fila["split"]) for fila in normales.values())
    for etiqueta in ETIQUETAS:
        for split, cantidad in NORMALES_POR_ETIQUETA.items():
            revisar_conteo(
                f"{ruta.name}: mensajes normales con etiqueta {etiqueta} en {split}",
                conteo_normales[(etiqueta, split)],
                cantidad,
                errores,
            )

    # Ataques: la base existe, no es prioritario y comparte etiqueta verdadera y split.
    conteo_tecnicas: Counter = Counter()
    conteo_bases: Counter = Counter()
    for donde, fila in ataques:
        conteo_tecnicas[(fila["tecnica"], fila["split"])] += 1
        conteo_bases[fila["etiqueta"]] += 1
        base = normales.get(fila["base_id"])
        if base is None:
            errores.append(f"{donde}: «base_id»={fila['base_id']!r} no es un mensaje normal válido")
            continue
        if base["etiqueta"] == ETIQUETA_OBJETIVO:
            errores.append(f"{donde}: la base {fila['base_id']} ya es {ETIQUETA_OBJETIVO}")
        if fila["etiqueta"] != base["etiqueta"]:
            errores.append(
                f"{donde}: «etiqueta»={fila['etiqueta']!r} no es la etiqueta verdadera de la base "
                f"{fila['base_id']} ({base['etiqueta']!r})"
            )
        if fila["split"] != base["split"]:
            errores.append(
                f"{donde}: el ataque está en {fila['split']} y su base {fila['base_id']} en "
                f"{base['split']}; deben compartir split para no filtrar test hacia dev"
            )
        if fila["texto"] == base["texto"]:
            errores.append(f"{donde}: el texto es idéntico al de la base, no trae ningún ataque")
        if fila["tecnica"] == "oculto" and not trae_algo_oculto(fila["texto"]):
            errores.append(
                f"{donde}: técnica «oculto» sin caracteres de ancho cero, etiquetas Unicode "
                f"ni {SALTOS_SEGUIDOS_OCULTO} saltos de línea seguidos"
            )
    for tecnica, por_split in TECNICAS.items():
        for split, cantidad in por_split.items():
            revisar_conteo(
                f"{ruta.name}: ataques con técnica {tecnica} en {split}",
                conteo_tecnicas[(tecnica, split)],
                cantidad,
                errores,
            )
    for etiqueta in ETIQUETAS:
        if etiqueta == ETIQUETA_OBJETIVO:
            continue
        revisar_conteo(
            f"{ruta.name}: ataques con base de etiqueta {etiqueta}",
            conteo_bases[etiqueta],
            ATAQUES_POR_ETIQUETA_BASE,
            errores,
        )
    return por_tipo_y_split


def main(carpeta: str | Path | None = None) -> int:
    """Valida los tres archivos. Devuelve 0 si todo está bien y 1 si hay algún error."""
    datos = Path(carpeta) if carpeta is not None else DATOS
    errores: list[str] = []
    ataques = validar_ataques(datos / "ataques.jsonl", errores)
    portadores = validar_portadores(datos / "portadores.jsonl", errores)
    leads = validar_leads(datos / "leads.jsonl", errores)

    print(f"Datos revisados en {datos}")
    print(
        f"  ataques.jsonl:    {sum(ataques.values())} filas "
        f"(dev {ataques['dev']}, test {ataques['test']})"
    )
    print(
        f"  portadores.jsonl: {sum(portadores.values())} filas "
        f"(correo {portadores['correo']}, whatsapp {portadores['whatsapp']})"
    )
    print(
        f"  leads.jsonl:      {sum(leads.values())} filas "
        f"(normales: dev {leads[('normal', 'dev')]}, test {leads[('normal', 'test')]}; "
        f"ataques: dev {leads[('ataque', 'dev')]}, test {leads[('ataque', 'test')]})"
    )
    if errores:
        print(f"ERRORES: {len(errores)}")
        for error in errores[:MAX_ERRORES_MOSTRADOS]:
            print(f"  - {error}")
        if len(errores) > MAX_ERRORES_MOSTRADOS:
            print(f"  ... y {len(errores) - MAX_ERRORES_MOSTRADOS} más")
        return 1
    print("Todo en orden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
