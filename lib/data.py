"""Carga de configuración, Parquet y filtros del dashboard."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

APP_ROOT = Path(__file__).resolve().parents[1]


def load_config() -> dict:
    with (APP_ROOT / "config.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = (APP_ROOT / path).resolve()
    return path


def load_tables(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    det_path = resolve_path(cfg["rutas"]["detecciones_parquet"])
    cat_path = resolve_path(cfg["rutas"]["catalogo_parquet"])
    if not det_path.exists():
        raise FileNotFoundError(
            f"No está {det_path}. Ejecuta primero: python -m pipeline.ingest"
        )
    det = pd.read_parquet(det_path)
    cat = pd.read_parquet(cat_path) if cat_path.exists() else pd.DataFrame()
    if "fecha" in det.columns:
        det["fecha"] = pd.to_datetime(det["fecha"], errors="coerce")
    return det, cat


def apply_filters(
    df: pd.DataFrame,
    *,
    dispositivos: list[str] | None,
    periodos: list[str] | None,
    especies: list[str] | None,
    gremios: list[str] | None,
    iucn: list[str] | None,
    solo_validadas: bool,
    confidence_min: float,
) -> pd.DataFrame:
    out = df
    if dispositivos:
        out = out[out["dispositivo"].isin(dispositivos)]
    if periodos:
        out = out[out["periodo"].isin(periodos)]
    if especies:
        out = out[out["nombre_espanol"].isin(especies)]
    if gremios:
        out = out[out["gremio"].isin(gremios)]
    if iucn:
        out = out[out["iucn"].isin(iucn)]
    if solo_validadas:
        out = out[out["valid"] == 1]
    if confidence_min is not None:
        out = out[out["confidence"] >= float(confidence_min)]
    return out.copy()


def csv_bytes(df: pd.DataFrame) -> bytes:
    cols = [
        "deteccion_id",
        "nombre_espanol",
        "nombre_cientifico",
        "nombre_ingles",
        "iucn",
        "gremio",
        "dispositivo",
        "fecha",
        "periodo",
        "hora",
        "inicio_s",
        "fin_s",
        "duracion_segmento_s",
        "freq_low_hz",
        "freq_high_hz",
        "freq_peak_hz",
        "valid",
        "confidence",
    ]
    use = [c for c in cols if c in df.columns]
    export = df[use].copy()
    if "fecha" in export.columns:
        export["fecha"] = pd.to_datetime(export["fecha"]).dt.strftime("%Y-%m-%d")
    return export.to_csv(index=False).encode("utf-8-sig")
