"""Reproducción, recorte y espectrogramas de WAV (muestras locales o descargados de Drive)."""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure

APP_ROOT = Path(__file__).resolve().parents[1]


def listar_muestras(wav_dir: Path) -> list[Path]:
    if not wav_dir.exists():
        return []
    files = sorted(wav_dir.glob("*.WAV")) + sorted(wav_dir.glob("*.wav"))
    # Evitar duplicados si el sistema no distingue mayúsculas
    seen = set()
    out = []
    for p in files:
        key = p.name.lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def describir_muestra(path: Path) -> dict:
    """Extrae dispositivo, sello horario y tipo a partir del nombre del archivo."""
    name = path.name
    info = {
        "archivo": name,
        "ruta": str(path),
        "tipo": "Clip de 3 s" if "segment" in name.lower() else "WAV original (muestra local)",
        "dispositivo": "—",
        "sello": "—",
        "nota": (
            "Sin Google Drive conectado solo se reproducen las grabaciones de muestra incluidas en el "
            "repositorio. Al conectar Drive, cualquier grabación se descarga bajo demanda, una a la vez."
        ),
    }
    m = re.search(r"(AM00\d)", name, re.I)
    if m:
        info["dispositivo"] = m.group(1).upper()
    m = re.search(r"(20\d{6})_(\d{6})", name)
    if m:
        hh, mm, ss = m.group(2)[0:2], m.group(2)[2:4], m.group(2)[4:6]
        info["sello"] = f"{hh}:{mm}:{ss} (hora local UTC−5; el sello sale del nombre del archivo)"
    return info


def _leer(fuente: Path | str | bytes) -> tuple[np.ndarray, int]:
    """Lee un WAV (ruta o bytes) en mono float32 con su frecuencia original."""
    import soundfile as sf

    src = io.BytesIO(fuente) if isinstance(fuente, (bytes, bytearray)) else str(fuente)
    y, sr = sf.read(src, dtype="float32", always_2d=True)
    return y.mean(axis=1), int(sr)


def recortar_wav(
    fuente: Path | str | bytes, inicio_s: float, fin_s: float, margen_s: float = 1.0
) -> tuple[bytes, float, float]:
    """Devuelve (wav_bytes, t0, t1) con el segmento [inicio - margen, fin + margen]."""
    import soundfile as sf

    y, sr = _leer(fuente)
    dur = len(y) / sr if sr else 0.0
    t0 = max(0.0, float(inicio_s) - float(margen_s))
    t1 = min(dur, float(fin_s) + float(margen_s))
    if t1 <= t0:
        raise ValueError("El segmento pedido está fuera de la duración del archivo.")
    buf = io.BytesIO()
    sf.write(buf, y[int(t0 * sr) : int(t1 * sr)], sr, format="WAV", subtype="PCM_16")
    return buf.getvalue(), t0, t1


def espectrograma(
    fuente: Path | str | bytes,
    titulo: str | None = None,
    marcas: Iterable[tuple[float, float]] | None = None,
    desplazamiento_s: float = 0.0,
) -> tuple[Figure, dict]:
    """Espectrograma de un WAV. ``marcas`` = lista de (inicio_s, fin_s) a sombrear.

    ``desplazamiento_s`` sirve para rotular el eje con el tiempo del archivo
    original cuando se grafica solo un recorte.
    """
    import librosa
    import librosa.display

    y, sr = _leer(fuente)
    dur = len(y) / sr if sr else 0.0
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=256))
    S_db = librosa.amplitude_to_db(S, ref=np.max)

    fig, ax = plt.subplots(figsize=(9.2, 3.6))
    fig.patch.set_facecolor("#F7F4EE")
    ax.set_facecolor("white")
    img = librosa.display.specshow(
        S_db, sr=sr, hop_length=256, x_axis="time", y_axis="hz", ax=ax, cmap="magma"
    )
    if desplazamiento_s:
        ticks = ax.get_xticks()
        ax.set_xticks(ticks)
        ax.set_xticklabels([f"{t + desplazamiento_s:.1f}" for t in ticks])
        ax.set_xlim(0, dur)
    for ini, fin in marcas or []:
        try:
            a, b = float(ini) - desplazamiento_s, float(fin) - desplazamiento_s
        except (TypeError, ValueError):
            continue
        if b > 0 and a < dur:
            ax.axvspan(max(a, 0), min(b, dur), color="#7FD3E0", alpha=0.25, lw=0)
            ax.axvline(max(a, 0), color="#7FD3E0", lw=1)
    ax.set_ylim(0, min(12000, sr / 2 if sr else 12000))
    ax.set_xlabel("Tiempo (s)")
    ax.set_ylabel("Frecuencia (Hz)")
    nombre = titulo or (Path(str(fuente)).name if not isinstance(fuente, (bytes, bytearray)) else "audio")
    ax.set_title(nombre, loc="left", fontsize=10, color="#0A3D5C")
    fig.colorbar(img, ax=ax, format="%+0.0f dB", pad=0.02)
    fig.tight_layout()

    meta = {
        "sample_rate_hz": int(sr),
        "duracion_s": round(float(dur), 3),
        "n_muestras": int(len(y)),
        "canales": 1,
    }
    return fig, meta
