"""Los datos, las reglas congeladas y las tablas no cambian al renombrar el código.

- Las reglas dan las mismas decisiones sobre los 652 casos del banco de pruebas que no
  dependen de SpaPhish (que no se redistribuye).
- Ningún archivo de datos ni registro de resultados cambia un byte.
- La última línea de reglas_congeladas.txt es el hash del archivo de reglas actual.
- Las tablas de resumen se rehacen, sin clave, igual que las publicadas.
"""

import hashlib
import json
import re
import shutil

import casos
import pytest
import tabla
from golden_support import GOLDEN, RAIZ, cargar

from centinela import ETIQUETAS_LEADS, DetectorReglas

#: Carpetas que cambian de nombre en el proyecto (se completa al pasarlas a inglés).
CARPETAS = {}


def _ruta(texto: str):
    carpeta, _, resto = texto.partition("/")
    return RAIZ / CARPETAS.get(carpeta, carpeta) / resto


def test_las_reglas_dan_las_mismas_decisiones_y_evidencias():
    esperado = cargar("rules_cases.json")
    detector = DetectorReglas(etiquetas=ETIQUETAS_LEADS)
    distintos = []
    visto = 0
    for particion in ("dev", "test"):
        for caso in casos.casos_del_banco(particion):
            h = detector.revisar(caso["texto"])
            obtenido = {
                "ordenes_para_ia": h.ordenes_para_ia,
                "engano_a_personas": h.engano_a_personas,
                "trucos": list(h.trucos),
                "evidencias": list(h.evidencias),
            }
            visto += 1
            if obtenido != esperado[f"{particion}:{caso['id']}"]:
                distintos.append(f"{particion}:{caso['id']}")
    assert visto == len(esperado) == 652
    assert distintos == []


@pytest.mark.parametrize("particion", ["dev", "test"])
def test_las_reglas_coinciden_con_las_filas_guardadas_en_resultados(particion):
    guardado = {
        json.loads(linea)["id"]: json.loads(linea)["marcado"]
        for linea in _ruta(f"resultados/filtro/{particion}/reglas.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if linea.strip()
    }
    detector = DetectorReglas(etiquetas=ETIQUETAS_LEADS)
    casos_del_banco = casos.casos_del_banco(particion)
    assert casos_del_banco
    for caso in casos_del_banco:
        assert detector.revisar(caso["texto"]).ordenes_para_ia == guardado[caso["id"]], caso["id"]


def test_ningun_archivo_de_datos_ni_de_resultados_cambia():
    lineas = (GOLDEN / "records.sha256").read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 39
    cambiados = []
    for linea in lineas:
        digest, ruta = linea.split("  ", 1)
        if hashlib.sha256(_ruta(ruta).read_bytes()).hexdigest() != digest:
            cambiados.append(ruta)
    assert cambiados == []


def test_la_ultima_linea_de_reglas_congeladas_es_el_hash_del_archivo_actual():
    texto = _ruta("resultados/reglas_congeladas.txt").read_text(encoding="utf-8")
    fijados = re.findall(r"^sha256 de (\S+): ([0-9a-f]{64})$", texto, flags=re.MULTILINE)
    assert fijados, "reglas_congeladas.txt no tiene ninguna línea «sha256 de <ruta>: <hash>»"
    ruta, esperado = fijados[-1]
    actual = hashlib.sha256((RAIZ / ruta).read_bytes()).hexdigest()
    assert actual == esperado, (
        f"{ruta} cambió. Si el cambio no altera las decisiones, agreguen (sin borrar las "
        "anteriores) una línea nueva con el hash y la explicación."
    )


def test_las_tablas_de_resumen_se_rehacen_igual_sin_clave(tmp_path, monkeypatch):
    copia = tmp_path / "resultados"
    shutil.copytree(_ruta("resultados"), copia, ignore=shutil.ignore_patterns("crudo"))
    monkeypatch.setattr(tabla, "RESULTADOS", copia)
    assert tabla.main([]) == 0
    assert (copia / "resumen.md").read_text(encoding="utf-8") == (GOLDEN / "resumen.md").read_text(
        encoding="utf-8"
    )
    assert (copia / "resumen.json").read_text(encoding="utf-8") == (
        GOLDEN / "resumen.json"
    ).read_text(encoding="utf-8")
