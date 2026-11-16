#!/usr/bin/env python3
"""Ingesta de TablaFinal.xlsx y Lista_Especies.xlsx hacia Parquet."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pandas as pd
import yaml

APP_ROOT = Path(__file__).resolve().parents[1]


def load_config(path: Path | None = None) -> dict:
    cfg_path = path or (APP_ROOT / "config.yaml")
    with cfg_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _resolve(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = (APP_ROOT / path).resolve()
    return path


def _stable_id(*parts: object) -> str:
    raw = "|".join("" if p is None or (isinstance(p, float) and pd.isna(p)) else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def ingest(config_path: Path | None = None) -> tuple[Path, Path]:
    cfg = load_config(config_path)
    rutas = cfg["rutas"]
    colmap = cfg["columnas_tabla_final"]
    catmap = cfg["columnas_catalogo"]
    alias = cfg["alias_periodo"]

    tabla_path = _resolve(rutas["tabla_final"])
    catalogo_path = _resolve(rutas["catalogo"])
    out_det = _resolve(rutas["detecciones_parquet"])
    out_cat = _resolve(rutas["catalogo_parquet"])
    out_det.parent.mkdir(parents=True, exist_ok=True)

    if not tabla_path.exists():
        raise FileNotFoundError(f"No se encontró la tabla de detecciones: {tabla_path}")
    if not catalogo_path.exists():
        raise FileNotFoundError(f"No se encontró el catálogo de especies: {catalogo_path}")

    raw = pd.read_excel(tabla_path)
    missing = [src for src in colmap.values() if src not in raw.columns]
    if missing:
        raise ValueError(f"Faltan columnas en TablaFinal.xlsx: {missing}")

    det = raw.rename(columns={src: dst for dst, src in colmap.items()}).copy()
    det["fila_origen"] = det.index.astype(int)

    det["fecha"] = pd.to_datetime(det["fecha"], errors="coerce")
    hora_txt = det["hora"].astype(str)
    det["hora"] = hora_txt
    hora_dt = pd.to_datetime(hora_txt, format="%H:%M:%S", errors="coerce")
    det["hora_num"] = hora_dt.dt.hour
    det["minuto_num"] = hora_dt.dt.minute
    det["datetime_local"] = pd.to_datetime(
        det["fecha"].dt.strftime("%Y-%m-%d") + " " + det["hora"],
        errors="coerce",
    )
    det["periodo_codigo"] = det["periodo"].astype(str)
    det["periodo"] = det["periodo_codigo"].map(alias).fillna(det["periodo_codigo"])
    det["valid"] = pd.to_numeric(det["valid"], errors="coerce").fillna(0).astype(int)
    det["confidence"] = pd.to_numeric(det["confidence"], errors="coerce")
    for col in ("inicio_s", "fin_s", "duracion_segmento_s", "freq_low_hz", "freq_high_hz", "freq_peak_hz"):
        det[col] = pd.to_numeric(det[col], errors="coerce")

    det["deteccion_id"] = [
        _stable_id(d, f, h, i, s, n)
        for d, f, h, i, s, n in zip(
            det["dispositivo"], det["fecha"], det["hora"], det["inicio_s"], det["nombre_cientifico"], det["fila_origen"]
        )
    ]
    det["audio_id"] = [
        _stable_id(d, f, h)
        for d, f, h in zip(det["dispositivo"], det["fecha"], det["hora"])
    ]
    det["validada"] = det["valid"] == 1

    cat_raw = pd.read_excel(catalogo_path)
    cat = cat_raw.rename(columns={src: dst for dst, src in catmap.items()}).copy()
    # Unificar tildes / espacios del nombre científico
    det["nombre_cientifico"] = det["nombre_cientifico"].astype(str).str.strip()
    cat["nombre_cientifico"] = cat["nombre_cientifico"].astype(str).str.strip()

    especies_tabla = set(det["nombre_cientifico"].unique())
    cat["tiene_detecciones"] = cat["nombre_cientifico"].isin(especies_tabla)
    det["en_catalogo"] = det["nombre_cientifico"].isin(set(cat["nombre_cientifico"].unique()))

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
