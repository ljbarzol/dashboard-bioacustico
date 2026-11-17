"""Transformación única de TablaFinal + Lista_Especies.

La usan tanto la ingesta local (``python -m pipeline.ingest``) como la carga
desde Google Drive, para que ambas fuentes produzcan exactamente las mismas
columnas.
"""

from __future__ import annotations

import hashlib

import pandas as pd


def _stable_id(*parts: object) -> str:
    raw = "|".join(
        "" if p is None or (isinstance(p, float) and pd.isna(p)) else str(p) for p in parts
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _hora_texto(valor: object) -> str:
    """Normaliza la columna Hora a 'HH:MM:SS' (Excel puede traer time, str o datetime)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    if hasattr(valor, "strftime"):
        return valor.strftime("%H:%M:%S")
    return str(valor).strip()


def transformar_tablas(
    raw: pd.DataFrame, cat_raw: pd.DataFrame, cfg: dict
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convierte los DataFrame crudos de los Excel en (detecciones, catalogo)."""
    colmap = cfg["columnas_tabla_final"]
    catmap = cfg["columnas_catalogo"]
    alias = cfg["alias_periodo"]

    missing = [src for src in colmap.values() if src not in raw.columns]
    if missing:
        raise ValueError(f"Faltan columnas en TablaFinal.xlsx: {missing}")

    det = raw.rename(columns={src: dst for dst, src in colmap.items()}).copy()
    det = det.reset_index(drop=True)
    det["fila_origen"] = det.index.astype(int)

    det["fecha"] = pd.to_datetime(det["fecha"], errors="coerce")
    det["hora"] = det["hora"].map(_hora_texto)
    hora_dt = pd.to_datetime(det["hora"], format="%H:%M:%S", errors="coerce")
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
    for col in (
        "inicio_s",
        "fin_s",
        "duracion_segmento_s",
        "freq_low_hz",
        "freq_high_hz",
        "freq_peak_hz",
    ):
        det[col] = pd.to_numeric(det[col], errors="coerce")

    det["deteccion_id"] = [
        _stable_id(d, f, h, i, s, n)
        for d, f, h, i, s, n in zip(
            det["dispositivo"],
            det["fecha"],
            det["hora"],
            det["inicio_s"],
            det["nombre_cientifico"],
            det["fila_origen"],
        )
    ]
    det["audio_id"] = [
        _stable_id(d, f, h) for d, f, h in zip(det["dispositivo"], det["fecha"], det["hora"])
    ]
    det["validada"] = det["valid"] == 1

    cat = cat_raw.rename(columns={src: dst for dst, src in catmap.items()}).copy()
    # Unificar tildes / espacios del nombre científico
    det["nombre_cientifico"] = det["nombre_cientifico"].astype(str).str.strip()
    cat["nombre_cientifico"] = cat["nombre_cientifico"].astype(str).str.strip()

    especies_tabla = set(det["nombre_cientifico"].unique())
    cat["tiene_detecciones"] = cat["nombre_cientifico"].isin(especies_tabla)
    det["en_catalogo"] = det["nombre_cientifico"].isin(set(cat["nombre_cientifico"].unique()))
    return det, cat
