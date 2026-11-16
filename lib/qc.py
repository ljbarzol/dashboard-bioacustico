"""Hallazgos de calidad conocidos (inventario en solo lectura) y chequeos tabulares."""

from __future__ import annotations

import pandas as pd

# Hallazgos del inventario de Drive (solo lectura). Se presentan como
# tabla de incidencias conocidas en la vista de calidad de la v1.
HALLAZGOS_CONOCIDOS = [
    {
        "dispositivo": "AM001",
        "tipo": "Carpetas de periodo vacías",
        "severidad": "Error de cobertura",
        "detalle": (
            "Hay dos días del muestreo cuyas carpetas Audio_Sunrise y "
            "Audio_Sunset están vacías. En esos mismos días TablaFinal.xlsx "
            "tampoco tiene detecciones de AM001."
        ),
    },
    {
        "dispositivo": "AM003",
        "tipo": "Minutos faltantes",
        "severidad": "Advertencia",
        "detalle": (
            "En una carpeta Audio_Sunset faltan al menos los minutos 17:03 y "
            "17:05 de la serie (un archivo por minuto dentro de la ventana de coro)."
        ),
    },
    {
        "dispositivo": "AM008",
        "tipo": "WAV truncados",
        "severidad": "Error",
        "detalle": (
            "En un tramo tardío del muestreo hay WAV de 229–328 KB (unos 2–3 s) "
            "en lugar de los ~5,28 MB de un archivo de 55 s. Posible fin de batería o de tarjeta."
        ),
    },
    {
        "dispositivo": "AM008",
        "tipo": "Cobertura tabla frente a Drive",
        "severidad": "Advertencia",
        "detalle": (
            "En Drive hay carpetas de AM008 posteriores al último día presente "
            "en TablaFinal.xlsx. No se decide aquí si es esfuerzo perdido o material a excluir."
        ),
    },
    {
        "dispositivo": "AM001",
        "tipo": "Intervalo de segmento nulo",
        "severidad": "Error de anotación",
        "detalle": (
            "Hay una detección validada (periodo Tarde, 18:59:00, "
            "Nyctidromus anthonyi) con Final (s) y Duración (s) nulos."
        ),
    },
    {
        "dispositivo": "Varios",
        "tipo": "Nombres de carpeta no uniformes",
        "severidad": "Advertencia",
        "detalle": (
            "Los alias de periodo no son consistentes entre grabadoras "
            "(Audio_Sunset, Sunset, Tarde, Morning, Mañana, etc.)."
        ),
    },
]


def hallazgos_frame() -> pd.DataFrame:
    return pd.DataFrame(HALLAZGOS_CONOCIDOS)[
        ["dispositivo", "tipo", "severidad", "detalle"]
    ]


def chequeos_tabulares(df: pd.DataFrame) -> pd.DataFrame:
    """Chequeos que se pueden calcular sobre la tabla filtrada, sin abrir audios."""
    rows = []
    n = len(df)
    n_valid0 = int((df["valid"] == 0).sum()) if n else 0
    n_fin_nulo = int(df["fin_s"].isna().sum()) if n else 0
    n_dur_nula = int(df["duracion_segmento_s"].isna().sum()) if n else 0
    n_freq0 = int(((df["valid"] == 0) & (df["freq_peak_hz"] == 0)).sum()) if n else 0
    clave = ["dispositivo", "fecha", "hora", "inicio_s", "nombre_cientifico"]
    n_dup = int(df.duplicated(clave, keep=False).sum()) if n and all(c in df.columns for c in clave) else 0
    rows.append(
        {
            "chequeo": "Detecciones no validadas (Valid = 0)",
            "conteo": n_valid0,
            "nota": "Por defecto el dashboard las deja fuera del análisis. Las 79 del corpus completo tienen frecuencias en cero.",
        }
    )
    rows.append(
        {
            "chequeo": "Segmentos sin hora de fin o sin duración",
            "conteo": max(n_fin_nulo, n_dur_nula),
            "nota": "Error de anotación en la tabla maestra.",
        }
    )
    rows.append(
        {
            "chequeo": "No validadas con frecuencias en cero",
            "conteo": n_freq0,
            "nota": "Coherente con Valid = 0; no es un fallo adicional de archivo.",
        }
    )
    rows.append(
        {
            "chequeo": "Filas con la misma clave dispositivo+día+hora+inicio+especie",
            "conteo": n_dup,
            "nota": "Posible doble registro en la tabla maestra (a veces cambia solo el puntaje de confianza).",
        }
    )
    return pd.DataFrame(rows)
