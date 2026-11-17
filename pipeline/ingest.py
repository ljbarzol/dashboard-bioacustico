#!/usr/bin/env python3
"""Ingesta de TablaFinal.xlsx y Lista_Especies.xlsx hacia Parquet.

La transformación vive en ``lib.transform.transformar_tablas`` y es la misma
que usa el dashboard cuando lee los Excel directamente desde Google Drive.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from lib.transform import transformar_tablas  # noqa: E402


def load_config(path: Path | None = None) -> dict:
    cfg_path = path or (APP_ROOT / "config.yaml")
    with cfg_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _resolve(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = (APP_ROOT / path).resolve()
    return path


def ingest(config_path: Path | None = None) -> tuple[Path, Path]:
    cfg = load_config(config_path)
    rutas = cfg["rutas"]

    tabla_path = _resolve(rutas["tabla_final"])
    catalogo_path = _resolve(rutas["catalogo"])
    out_det = _resolve(rutas["detecciones_parquet"])
    out_cat = _resolve(rutas["catalogo_parquet"])
    out_det.parent.mkdir(parents=True, exist_ok=True)

    if not tabla_path.exists():
        raise FileNotFoundError(f"No se encontró la tabla de detecciones: {tabla_path}")
    if not catalogo_path.exists():
        raise FileNotFoundError(f"No se encontró el catálogo de especies: {catalogo_path}")

    det, cat = transformar_tablas(pd.read_excel(tabla_path), pd.read_excel(catalogo_path), cfg)

    det.to_parquet(out_det, index=False)
    cat.to_parquet(out_cat, index=False)

    n = len(det)
    n_valid = int(det["validada"].sum())
    n_sp = det["nombre_cientifico"].nunique()
    n_dev = det["dispositivo"].nunique()
    sin_det = cat.loc[~cat["tiene_detecciones"], "nombre_cientifico"].tolist()
    print(f"Escribí {out_det}")
    print(f"  {n} detecciones, {n_valid} validadas, {n_sp} especies, {n_dev} grabadoras")
    print(f"Escribí {out_cat}  ({len(cat)} especies en el catálogo)")
    if sin_det:
        print("  Especies del catálogo sin detecciones:", ", ".join(sin_det))
    return out_det, out_cat


def main() -> int:
    try:
        ingest()
    except Exception as exc:  # noqa: BLE001 — CLI surface
        print(f"Error en la ingesta: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
