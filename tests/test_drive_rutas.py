"""Pruebas de la resolución de rutas en Drive con un listado simulado.

La estructura imita la real de «AudioMoth - CONDESAN» (ver inventario):
carpetas AM00X/AAAAMMDD/<periodo> con nombres no uniformes, dos patrones de
nombre de WAV y el desfase de :01 en AM002.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from lib.drive import (
    FOLDER_MIME,
    GSHEET_MIME,
    elegir_wav,
    es_carpeta_audio,
    extraer_folder_id,
    localizar_excel,
    localizar_wav,
    parsear_wav,
    periodo_canonico,
)

ROOT = "1yjJKnCO6NgIXe88RHFza3SsOC1mC0Twf"


def _f(name, fid=None):
    return {"id": fid or f"id:{name}", "name": name, "mimeType": FOLDER_MIME}


def _w(name, size="5280488"):
    return {"id": f"id:{name}", "name": name, "mimeType": "audio/wav", "size": size}


def _minutos(prefijo, dia, desde, hasta, seg="00"):
    out = []
    h, m = desde
    while (h, m) <= hasta:
        out.append(_w(f"{prefijo}{dia}_{h:02d}{m:02d}{seg}.WAV"))
        m += 1
        if m == 60:
            h, m = h + 1, 0
    return out


AM002_ID = "24F319055CC5BF71"
AM003_ID = "24F319055CC5C26F"


@pytest.fixture
def arbol():
    t: dict[str, list[dict]] = {}
    t[ROOT] = [
        _f("AM001"), _f("AM002"), _f("AM003"), _f("AM005"), _f("AM007"), _f("AM008"),
        _f("Resultados"),
    ]
    # AM001: patrón sin Device ID; día 24 solo tarde; 27 jul con carpetas vacías.
    t["id:AM001"] = [_f("20250724", "AM001/20250724"), _f("20250727", "AM001/20250727"),
                     _f("20250806", "AM001/20250806")]
    t["AM001/20250724"] = [_f("Audio_Sunset", "AM001/20250724/Audio_Sunset"),
                           _f("Results_Sunset", "AM001/20250724/Results_Sunset")]
    t["AM001/20250724/Audio_Sunset"] = _minutos("", "20250724", (17, 0), (20, 59))
    t["AM001/20250724/Results_Sunset"] = [_f("Valid_Tables"), _f("Segment_Analyzer")]
    t["AM001/20250727"] = [_f("Audio_Sunrise", "e1"), _f("Audio_Sunset", "e2"),
                           _f("Results_Sunrise"), _f("Results_Sunset")]
    t["e1"], t["e2"] = [], []
    t["AM001/20250806"] = [_f("Audio_Sunrise", "AM001/20250806/Audio_Sunrise"),
                           _f("Audio_Sunset", "AM001/20250806/Audio_Sunset"),
                           _f("Results_Sunrise", "AM001/20250806/Results_Sunrise")]
    t["AM001/20250806/Audio_Sunrise"] = _minutos("", "20250806", (5, 30), (7, 59))
    t["AM001/20250806/Audio_Sunset"] = _minutos("", "20250806", (17, 0), (20, 59))
    # Un WAV con el mismo minuto dentro de Results (no debe elegirse).
    t["AM001/20250806/Results_Sunrise"] = [_w("20250806_064100.WAV")]
    # AM002: Device ID en el nombre, carpetas Audios_*, Segment/Valid_tables sin prefijo
    # y archivos de :01 (54 s).
    t["id:AM002"] = [_f("20250724", "AM002/20250724"), _f("20250729", "AM002/20250729"),
                     _f("DCIM"), {"id": "cfg", "name": "CONFIG.TXT", "mimeType": "text/plain"}]
    t["AM002/20250724"] = [_f("Audios_Sunset", "AM002/20250724/Audios_Sunset"),
                           _f("Segment"), _f("Valid_tables")]
    t["AM002/20250724/Audios_Sunset"] = (
        _minutos(f"{AM002_ID}_", "20250724", (17, 0), (17, 32))
        + [_w(f"{AM002_ID}_20250724_173301.WAV", "5184803")]
        + _minutos(f"{AM002_ID}_", "20250724", (17, 34), (20, 19))
    )
    t["AM002/20250729"] = [_f("Audios_Sunrise", "AM002/20250729/Audios_Sunrise"),
                           _f("Audios_Sunset", "AM002/20250729/Audios_Sunset"),
                           _f("Resultados_Sunrise"), _f("Resultados_Sunset")]
    t["AM002/20250729/Audios_Sunrise"] = _minutos(f"{AM002_ID}_", "20250729", (5, 30), (7, 59))
    t["AM002/20250729/Audios_Sunset"] = _minutos(f"{AM002_ID}_", "20250729", (17, 0), (20, 59))
    # AM003: Device ID, minutos faltantes (17:03 y 17:05).
    t["id:AM003"] = [_f("20250724", "AM003/20250724")]
    t["AM003/20250724"] = [_f("Audio_Sunset", "AM003/20250724/Audio_Sunset")]
    t["AM003/20250724/Audio_Sunset"] = [
        w for w in _minutos(f"{AM003_ID}_", "20250724", (17, 0), (17, 10))
        if not w["name"].endswith(("170300.WAV", "170500.WAV"))
    ]
    # AM008: sin Device ID, carpetas en español (Mañana/Tarde) y en inglés (Morning/Sunset).
    t["id:AM008"] = [_f("20250724", "AM008/20250724"), _f("20250801", "AM008/20250801"),
                     {"id": "zip", "name": "DCIM.zip", "mimeType": "application/zip"}]
    t["AM008/20250724"] = [_f("Sunset", "AM008/20250724/Sunset")]
    t["AM008/20250724/Sunset"] = _minutos("", "20250724", (17, 0), (20, 19))
    t["AM008/20250801"] = [_f("Mañana", "AM008/20250801/Mañana"), _f("Tarde", "AM008/20250801/Tarde")]
    t["AM008/20250801/Mañana"] = _minutos("", "20250801", (5, 30), (7, 59))
    t["AM008/20250801/Tarde"] = _minutos("", "20250801", (17, 0), (20, 59))
    # AM005 / AM007: Morning y variantes.
    t["id:AM005"] = [_f("20250725", "AM005/20250725"), _f("LOST.DIR")]
    t["AM005/20250725"] = [_f("Morning", "AM005/20250725/Morning")]
    t["AM005/20250725/Morning"] = _minutos("24A04F085CC5BF65_", "20250725", (5, 30), (6, 0))
    t["id:AM007"] = []
    # Resultados
    t["id:Resultados"] = [
        {"id": "tf", "name": "TablaFinal.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        {"id": "le", "name": "Lista_Especies.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        _f("Gráficos"),
    ]
    llamadas: list[str] = []

    def listar(fid):
        llamadas.append(fid)
        return t.get(fid, [])

    listar.llamadas = llamadas
    return listar


# --- utilidades puras -------------------------------------------------------

@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("https://drive.google.com/drive/u/1/folders/1yjJKnCO6NgIXe88RHFza3SsOC1mC0Twf", ROOT),
        ("https://drive.google.com/drive/folders/1yjJKnCO6NgIXe88RHFza3SsOC1mC0Twf?usp=sharing", ROOT),
        ("https://drive.google.com/open?id=1yjJKnCO6NgIXe88RHFza3SsOC1mC0Twf", ROOT),
        ("  1yjJKnCO6NgIXe88RHFza3SsOC1mC0Twf  ", ROOT),
        ("", None),
        (None, None),
        ("hola mundo", None),
    ],
)
def test_extraer_folder_id(texto, esperado):
    assert extraer_folder_id(texto) == esperado


@pytest.mark.parametrize(
    "nombre,periodo,esperado",
    [
        ("Audio_Sunrise", "Sunrise", True),
        ("Audios_Sunrise", "Mañana", True),
        ("Morning", "Sunrise", True),
        ("Mañana", "Sunrise", True),
        ("MAÑANA", "Mañana", True),
        ("Audio_Sunset", "Sunset", True),
        ("Audios_Sunset", "Tarde", True),
        ("Sunset", "Sunset", True),
        ("Tarde", "Sunset", True),
        ("Audio_Sunset", "Sunrise", False),
        ("Mañana", "Sunset", False),
        ("Results_Sunrise", "Sunrise", False),
        ("Resultados_Sunset", "Sunset", False),
        ("Segment", None, False),
        ("Valid_tables", None, False),
        ("DCIM", None, False),
    ],
)
def test_es_carpeta_audio(nombre, periodo, esperado):
    assert es_carpeta_audio(nombre, periodo) is esperado


def test_periodo_canonico():
    assert periodo_canonico("Sunrise") == periodo_canonico("Mañana") == "manana"
    assert periodo_canonico("Sunset") == periodo_canonico("Tarde") == "tarde"
    assert periodo_canonico("otro") is None


def test_parsear_wav_dos_patrones():
    dev, ts = parsear_wav("20250724_170000.WAV")
    assert dev is None and ts.strftime("%Y%m%d %H%M%S") == "20250724 170000"
    dev, ts = parsear_wav("24F319055CC5BF71_20250724_173301.WAV")
    assert dev == AM002_ID and ts.second == 1
    assert parsear_wav("20250724_170000.wav") is not None
    # Clips de 3 s y otros archivos no son WAV originales
    assert parsear_wav("0.333_3_24F319055CC5BF71_20250724_170800_39.00s_42.00s.wav") is None
    assert parsear_wav("CONFIG.TXT") is None


def test_elegir_wav_tolerancia():
    archivos = [_w(f"{AM002_ID}_20250724_173301.WAV"), _w(f"{AM002_ID}_20250724_173400.WAV")]
    assert elegir_wav(archivos, "20250724", "17:33:00")["name"].endswith("173301.WAV")
    assert elegir_wav(archivos, "20250724", "17:33:01")["name"].endswith("173301.WAV")
    assert elegir_wav(archivos, "20250724", "17:33:00", tolerancia_s=0) is None
    assert elegir_wav(archivos, "20250724", "17:33:30") is None
    # Prefiere coincidencia exacta frente a ±1 s
    archivos.append(_w(f"{AM002_ID}_20250724_173300.WAV"))
    assert elegir_wav(archivos, "20250724", "17:33:00")["name"].endswith("173300.WAV")


# --- localizar_wav sobre el árbol simulado ----------------------------------

@pytest.mark.parametrize(
    "dev,fecha,hora,periodo,ruta",
    [
        ("AM001", "20250724", "17:38:00", "Sunset", "AM001/20250724/Audio_Sunset/20250724_173800.WAV"),
        ("AM001", date(2025, 8, 6), "06:41:00", "Sunrise", "AM001/20250806/Audio_Sunrise/20250806_064100.WAV"),
        ("AM001", pd.Timestamp("2025-08-06"), "18:00:00", "Tarde", "AM001/20250806/Audio_Sunset/20250806_180000.WAV"),
        ("AM002", "20250724", "17:33:01", "Sunset", f"AM002/20250724/Audios_Sunset/{AM002_ID}_20250724_173301.WAV"),
        ("AM002", "20250724", "17:33:00", "Sunset", f"AM002/20250724/Audios_Sunset/{AM002_ID}_20250724_173301.WAV"),
        ("AM002", "2025-07-29", "07:41:00", "Sunrise", f"AM002/20250729/Audios_Sunrise/{AM002_ID}_20250729_074100.WAV"),
        ("AM003", "20250724", "17:04:00", "Sunset", f"AM003/20250724/Audio_Sunset/{AM003_ID}_20250724_170400.WAV"),
        ("AM005", "20250725", "05:45:00", "Sunrise", "AM005/20250725/Morning/24A04F085CC5BF65_20250725_054500.WAV"),
        ("AM008", "20250724", "19:00:00", "Sunset", "AM008/20250724/Sunset/20250724_190000.WAV"),
        ("AM008", "20250801", "06:10:00", "Sunrise", "AM008/20250801/Mañana/20250801_061000.WAV"),
        ("AM008", "20250801", "17:10:00", "Sunset", "AM008/20250801/Tarde/20250801_171000.WAV"),
        # Periodo mal etiquetado: igual se encuentra revisando las otras carpetas de audio
        ("AM008", "20250801", "17:10:00", "Sunrise", "AM008/20250801/Tarde/20250801_171000.WAV"),
        ("AM008", "20250801", "17:10:00", None, "AM008/20250801/Tarde/20250801_171000.WAV"),
    ],
)
def test_localizar_wav_ok(arbol, dev, fecha, hora, periodo, ruta):
    ub = localizar_wav(arbol, ROOT, dev, fecha, hora, periodo)
    assert ub is not None
    assert ub.ruta == ruta
    assert ub.archivo["id"] == f"id:{ruta.split('/')[-1]}"


@pytest.mark.parametrize(
    "dev,fecha,hora,periodo",
    [
        ("AM003", "20250724", "17:03:00", "Sunset"),   # minuto faltante
        ("AM001", "20250727", "06:00:00", "Sunrise"),  # carpetas vacías
        ("AM004", "20250724", "17:00:00", "Sunset"),   # dispositivo inexistente
        ("AM001", "20250799", "17:00:00", "Sunset"),   # día inexistente
        ("AM007", "20250724", "17:00:00", "Sunset"),   # dispositivo sin días
    ],
)
def test_localizar_wav_no_encontrado(arbol, dev, fecha, hora, periodo):
    assert localizar_wav(arbol, ROOT, dev, fecha, hora, periodo) is None


def test_no_elige_wav_dentro_de_results(arbol):
    ub = localizar_wav(arbol, ROOT, "AM001", "20250806", "06:41:00", "Sunrise")
    assert "Results" not in ub.ruta


def test_no_baja_a_carpetas_de_resultados(arbol):
    localizar_wav(arbol, ROOT, "AM002", "20250724", "17:33:00", "Sunset")
    assert not any("Segment" in c or "Valid" in c for c in arbol.llamadas)


def test_localizar_excel(arbol):
    assert localizar_excel(arbol, ROOT, "TablaFinal")["id"] == "tf"
    assert localizar_excel(arbol, ROOT, "Lista_Especies")["id"] == "le"
    assert localizar_excel(arbol, ROOT, "NoExiste") is None


def test_localizar_excel_hoja_de_google_en_raiz():
    t = {ROOT: [{"id": "gs", "name": "TablaFinal", "mimeType": GSHEET_MIME}]}
    assert localizar_excel(lambda f: t.get(f, []), ROOT, "TablaFinal")["id"] == "gs"


def test_alcance_solo_lectura():
    from lib import drive

    assert drive.SCOPES == ["https://www.googleapis.com/auth/drive.readonly"]
    fuente = Path(drive.__file__).read_text(encoding="utf-8")
    for metodo in (".create(", ".update(", ".delete(", ".copy(", "permissions()", ".emptyTrash("):
        assert metodo not in fuente


class _Resp:
    def __init__(self, status):
        self.status = status


class _HttpErr(Exception):
    def __init__(self, status, msg=""):
        super().__init__(msg)
        self.resp = _Resp(status)


def test_mensajes_de_error_amigables():
    from lib.drive import DriveLector

    lector = DriveLector.__new__(DriveLector)
    lector.email = "lector@p.iam.gserviceaccount.com"
    msg = str(lector._traducir(_HttpErr(404)))
    assert "no está compartida" in msg and lector.email in msg
    assert "API de Google Drive no está habilitada" in str(lector._traducir(_HttpErr(403, "accessNotConfigured")))
    assert lector.email in str(lector._traducir(_HttpErr(403, "insufficientPermissions")))
