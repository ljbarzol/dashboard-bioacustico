"""Reproducción y espectrogramas de los WAV de muestra locales."""

from __future__ import annotations

import re
from pathlib import Path

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
            "Esta v1 solo reproduce las grabaciones de muestra que están en el equipo. "
            "El corpus completo se cargará bajo demanda más adelante, sin bajar las decenas de GB de Drive."
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


def espectrograma(path: Path) -> tuple[Figure, dict]:
    import librosa
    import librosa.display

    y, sr = librosa.load(path, sr=None, mono=True)
    dur = len(y) / sr if sr else 0.0
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=256))
    S_db = librosa.amplitude_to_db(S, ref=np.max)

    fig, ax = plt.subplots(figsize=(9.2, 3.6))
    fig.patch.set_facecolor("#F7F4EE")
    ax.set_facecolor("white")
    img = librosa.display.specshow(
        S_db, sr=sr, hop_length=256, x_axis="time", y_axis="hz", ax=ax, cmap="magma"
    )
    ax.set_ylim(0, min(12000, sr / 2 if sr else 12000))
    ax.set_xlabel("Tiempo (s)")
    ax.set_ylabel("Frecuencia (Hz)")
    ax.set_title(path.name, loc="left", fontsize=10, color="#0A3D5C")
    fig.colorbar(img, ax=ax, format="%+0.0f dB", pad=0.02)
    fig.tight_layout()

    meta = {
        "sample_rate_hz": int(sr),
        "duracion_s": round(float(dur), 3),
        "n_muestras": int(len(y)),
        "canales": 1,
    }
    return fig, meta
