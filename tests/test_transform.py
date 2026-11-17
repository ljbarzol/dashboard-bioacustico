"""La transformación compartida reproduce los Parquet versionados."""

from pathlib import Path

import pandas as pd
import pytest

from lib.data import load_config
from lib.transform import transformar_tablas

ROOT = Path(__file__).resolve().parents[1]


def _cfg():
    return load_config()


def test_hora_como_time_y_columnas():
    import datetime as dt

    cfg = _cfg()
    cols = cfg["columnas_tabla_final"]
    fila = {v: None for v in cols.values()}
    fila.update({
        cols["nombre_cientifico"]: " Mimus longicaudatus ",
        cols["dispositivo"]: "AM002",
        cols["fecha"]: "2025-07-24",
        cols["periodo"]: "Sunset",
        cols["hora"]: dt.time(17, 33, 1),
        cols["inicio_s"]: 3,
        cols["fin_s"]: 6,
        cols["valid"]: 1,
        cols["confidence"]: 0.8,
    })
    cat = pd.DataFrame({v: ["Mimus longicaudatus"] for v in cfg["columnas_catalogo"].values()})
    det, c = transformar_tablas(pd.DataFrame([fila]), cat, cfg)
    assert det.loc[0, "hora"] == "17:33:01"
    assert det.loc[0, "periodo"] == "Tarde"
    assert bool(det.loc[0, "en_catalogo"]) and bool(c.loc[0, "tiene_detecciones"])


def test_faltan_columnas():
    with pytest.raises(ValueError):
        transformar_tablas(pd.DataFrame({"x": [1]}), pd.DataFrame(), _cfg())


@pytest.mark.skipif(
    not (ROOT.parent / "drive_sample" / "TablaFinal.xlsx").exists(),
    reason="Excel originales no disponibles fuera del equipo de desarrollo",
)
def test_reproduce_parquet_versionado():
    cfg = _cfg()
    base = ROOT.parent / "drive_sample"
    det, cat = transformar_tablas(
        pd.read_excel(base / "TablaFinal.xlsx"), pd.read_excel(base / "Lista_Especies.xlsx"), cfg
    )
    d0 = pd.read_parquet(ROOT / "data" / "detecciones.parquet")
    k0 = pd.read_parquet(ROOT / "data" / "catalogo.parquet")
    pd.testing.assert_frame_equal(det[d0.columns], d0, check_dtype=False)
    pd.testing.assert_frame_equal(cat[k0.columns], k0, check_dtype=False)
