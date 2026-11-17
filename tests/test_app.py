"""Pruebas de humo de la interfaz con streamlit.testing (sin conexión a Drive)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app.py")
TABS = ["Resumen", "Especies y gremios", "Actividad por hora", "Grabadoras", "Calidad de datos", "Explorador de audio"]


def _textos(at):
    return " ".join(str(getattr(e, "value", "")) for e in list(at.info) + list(at.success) + list(at.error))


def test_sin_secrets_usa_datos_locales():
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception, at.exception
    assert [t.label for t in at.tabs] == TABS
    assert "Usando datos locales" in _textos(at)
    assert not any("Michael" in str(m.value) for m in at.markdown)
    assert at.sidebar.button[0].label == "Recargar datos"


class _FakeLector:
    """Simula DriveLector con el árbol real y los Excel de muestra."""

    email = "lector@proyecto.iam.gserviceaccount.com"

    def __init__(self, info):
        self.base = ROOT.parent / "drive_sample"

    def verificar_carpeta(self, fid):
        if fid != "1yjJKnCO6NgIXe88RHFza3SsOC1mC0Twf":
            from lib.drive import DriveError

            raise DriveError(f"No se encontró la carpeta o no está compartida con {self.email}.")
        return {"id": fid, "name": "AudioMoth - CONDESAN", "mimeType": "application/vnd.google-apps.folder"}

    def listar(self, fid):
        F = "application/vnd.google-apps.folder"
        if fid == "1yjJKnCO6NgIXe88RHFza3SsOC1mC0Twf":
            return [{"id": "res", "name": "Resultados", "mimeType": F}] + [
                {"id": f"dev:{d}", "name": d, "mimeType": F} for d in ("AM001", "AM002", "AM008")
            ]
        if fid == "res":
            return [{"id": "tf", "name": "TablaFinal.xlsx", "mimeType": "x"},
                    {"id": "le", "name": "Lista_Especies.xlsx", "mimeType": "x"}]
        if fid.startswith("dev:") and "/" not in fid:
            return [{"id": f"{fid}/2025072{i}", "name": f"2025072{i}", "mimeType": F} for i in range(4, 10)]
        if fid.count("/") == 1:  # día
            return [{"id": f"{fid}/m", "name": "Mañana", "mimeType": F},
                    {"id": f"{fid}/t", "name": "Audio_Sunset", "mimeType": F},
                    {"id": f"{fid}/r", "name": "Results_Sunset", "mimeType": F}]
        dia = fid.split("/")[1]
        horas = range(5, 8) if fid.endswith("/m") else range(17, 21)
        return [{"id": "wav", "name": f"{dia}_{h:02d}{m:02d}00.WAV", "mimeType": "audio/wav", "size": "5280488"}
                for h in horas for m in range(60)]

    def descargar(self, item, max_bytes=None):
        if item["id"] == "wav":
            return (ROOT / "data" / "wav" / "AM001_20250724_170000.WAV").read_bytes()
        return (self.base / {"tf": "TablaFinal.xlsx", "le": "Lista_Especies.xlsx"}[item["id"]]).read_bytes()


SECRETS = {
    "type": "service_account",
    "client_email": "lector@proyecto.iam.gserviceaccount.com",
    "private_key": "-----BEGIN PRIVATE KEY-----\nfalsa\n-----END PRIVATE KEY-----\n",
}


@pytest.mark.skipif(not (ROOT.parent / "drive_sample" / "TablaFinal.xlsx").exists(), reason="sin Excel de muestra")
def test_con_drive_simulado(monkeypatch):
    import lib.fuente as fuente

    monkeypatch.setattr(fuente, "DriveLector", _FakeLector)
    fuente.limpiar_cache()
    at = AppTest.from_file(APP, default_timeout=180)
    at.secrets["gcp_service_account"] = SECRETS
    at.run()
    assert not at.exception, at.exception
    assert "Conectado a Google Drive" in _textos(at)

    # Explorador: descargar y reproducir una grabación (segmento por defecto)
    boton = next(b for b in at.button if b.label == "Escuchar desde Google Drive")
    boton.click().run()
    assert not at.exception, at.exception
    assert any("Archivo en Drive: AM001/" in str(c.value) for c in at.caption)
    assert any("Segmento" in str(c.value) for c in at.caption)
    radio = next(r for r in at.radio if r.label == "Qué reproducir")
    radio.set_value("Archivo completo").run()
    assert not at.exception, at.exception

    # Carpeta no compartida pegada en la barra lateral -> error amigable + datos locales
    at.sidebar.text_input[0].input("https://drive.google.com/drive/folders/OTRAcarpetaXYZ123456").run()
    assert not at.exception, at.exception
    txt = _textos(at)
    assert "no está compartida" in txt and "datos locales" in txt
    fuente.limpiar_cache()
