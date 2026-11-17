"""Fuente de datos opcional en Google Drive, SOLO LECTURA.

- Autenticación con una cuenta de servicio (``[gcp_service_account]`` en los
  secrets de Streamlit) y el alcance ``drive.readonly``. Este módulo nunca
  crea, edita, mueve, comparte ni borra nada en Drive.
- La lógica de rutas (carpeta de periodo, patrón de nombre del WAV, tolerancia
  de ±1 s) es pura y recibe una función ``listar(folder_id)``, para poder
  probarla sin conexión.
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_MIME = "application/vnd.google-apps.folder"
GSHEET_MIME = "application/vnd.google-apps.spreadsheet"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

Item = dict  # {"id", "name", "mimeType", "size"?}
Listar = Callable[[str], list[Item]]


class DriveError(Exception):
    """Error con un mensaje amigable en español para mostrar en la interfaz."""


# ---------------------------------------------------------------------------
# Utilidades puras
# ---------------------------------------------------------------------------

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")


def extraer_folder_id(texto: str | None) -> str | None:
    """Acepta un enlace de carpeta de Drive o un ID y devuelve el ID (o None)."""
    if not texto:
        return None
    t = texto.strip()
    if not t:
        return None
    m = re.search(r"/folders/([A-Za-z0-9_-]{10,})", t)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([A-Za-z0-9_-]{10,})", t)
    if m:
        return m.group(1)
    if _ID_RE.match(t):
        return t
    return None


def normalizar(nombre: str) -> str:
    """Minúsculas, sin tildes y sin espacios/guiones repetidos."""
    s = unicodedata.normalize("NFKD", nombre or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[\s\-]+", "_", s.strip().lower())


_TOKENS_MANANA = ("sunrise", "morning", "manana", "amanecer")
_TOKENS_TARDE = ("sunset", "evening", "tarde", "atardecer")
_EXCLUIR = ("result", "resultado", "segment", "valid", "table", "tabla")


def periodo_canonico(periodo: str | None) -> str | None:
    """'Sunrise'/'Mañana' -> 'manana'; 'Sunset'/'Tarde' -> 'tarde'."""
    if not periodo:
        return None
    p = normalizar(str(periodo))
    if any(t in p for t in _TOKENS_MANANA):
        return "manana"
    if any(t in p for t in _TOKENS_TARDE):
        return "tarde"
    return None


def es_carpeta_audio(nombre: str, periodo: str | None = None) -> bool:
    """True si el nombre es una carpeta de audio del periodo pedido.

    Reconoce Audio_Sunrise, Audios_Sunrise, Morning, Mañana (y los equivalentes
    de la tarde) y descarta Results_*, Resultados_*, Segment, Valid_tables...
    """
    n = normalizar(nombre)
    if any(x in n for x in _EXCLUIR):
        return False
    canon = periodo_canonico(n)
    if canon is None:
        return False
    if periodo is None:
        return True
    return canon == periodo_canonico(periodo)


_WAV_RE = re.compile(
    r"^(?:(?P<devid>[0-9A-Fa-f]{16})_)?(?P<fecha>\d{8})_(?P<hora>\d{6})\.wav$",
    re.IGNORECASE,
)


def parsear_wav(nombre: str) -> tuple[str | None, datetime] | None:
    """Devuelve (device_id o None, datetime local) para un WAV original de AudioMoth.

    Patrones: ``YYYYMMDD_HHMMSS.WAV`` (AM001, AM008) y
    ``{DEVICEID}_YYYYMMDD_HHMMSS.WAV`` (AM002, AM003, AM005, AM007).
    """
    m = _WAV_RE.match(nombre.strip())
    if not m:
        return None
    try:
        ts = datetime.strptime(m.group("fecha") + m.group("hora"), "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return (m.group("devid").upper() if m.group("devid") else None), ts


def _a_datetime(fecha: object, hora: str) -> datetime:
    if hasattr(fecha, "strftime"):
        dia = fecha.strftime("%Y%m%d")
    else:
        dia = re.sub(r"\D", "", str(fecha))[:8]
    h = str(hora).strip()
    if len(h) == 5:
        h += ":00"
    return datetime.strptime(dia + h, "%Y%m%d%H:%M:%S")


def elegir_wav(
    archivos: Iterable[Item], fecha: object, hora: str, tolerancia_s: int = 1
) -> Item | None:
    """Elige el WAV cuyo sello coincide con fecha+hora (exacto primero, luego ±tolerancia)."""
    objetivo = _a_datetime(fecha, hora)
    mejor: tuple[float, Item] | None = None
    for it in archivos:
        if it.get("mimeType") == FOLDER_MIME:
            continue
        p = parsear_wav(it.get("name", ""))
        if not p:
            continue
        diff = abs((p[1] - objetivo).total_seconds())
        if diff <= tolerancia_s and (mejor is None or diff < mejor[0]):
            mejor = (diff, it)
    return mejor[1] if mejor else None


def _hijo(items: Iterable[Item], nombre: str, carpeta: bool | None = None) -> Item | None:
    objetivo = normalizar(nombre)
    for it in items:
        if carpeta is True and it.get("mimeType") != FOLDER_MIME:
            continue
        if carpeta is False and it.get("mimeType") == FOLDER_MIME:
            continue
        if normalizar(it.get("name", "")) == objetivo:
            return it
    return None


def _dia_texto(fecha: object) -> str:
    if hasattr(fecha, "strftime"):
        return fecha.strftime("%Y%m%d")
    return re.sub(r"\D", "", str(fecha))[:8]


@dataclass
class UbicacionWav:
    archivo: Item
    ruta: str  # ruta legible, p. ej. AM002/20250729/Audios_Sunrise/xxx.WAV


def localizar_wav(
    listar: Listar,
    raiz_id: str,
    dispositivo: str,
    fecha: object,
    hora: str,
    periodo: str | None = None,
    tolerancia_s: int = 1,
) -> UbicacionWav | None:
    """Busca el WAV original de una detección: raíz/AM00X/YYYYMMDD/<periodo>/archivo.

    Si el periodo no ayuda (carpeta con nombre inesperado), revisa todas las
    carpetas de audio del día.
    """
    raiz = listar(raiz_id)
    dev = _hijo(raiz, dispositivo, carpeta=True)
    if dev is None:
        return None
    dia = _dia_texto(fecha)
    dia_item = _hijo(listar(dev["id"]), dia, carpeta=True)
    if dia_item is None:
        return None
    subcarpetas = [i for i in listar(dia_item["id"]) if i.get("mimeType") == FOLDER_MIME]
    preferidas = [c for c in subcarpetas if es_carpeta_audio(c["name"], periodo)] if periodo else []
    resto = [c for c in subcarpetas if es_carpeta_audio(c["name"]) and c not in preferidas]
    for carpeta in preferidas + resto:
        wav = elegir_wav(listar(carpeta["id"]), fecha, hora, tolerancia_s)
        if wav:
            ruta = "/".join([dev["name"], dia_item["name"], carpeta["name"], wav["name"]])
            return UbicacionWav(archivo=wav, ruta=ruta)
    return None


def localizar_excel(listar: Listar, raiz_id: str, nombre_base: str) -> Item | None:
    """Encuentra Resultados/<nombre_base>.xlsx (o una Hoja de cálculo de Google con ese nombre).

    También acepta el archivo directamente en la raíz.
    """
    objetivo = normalizar(nombre_base)

    def buscar(items: list[Item]) -> Item | None:
        for it in items:
            if it.get("mimeType") == FOLDER_MIME:
                continue
            n = normalizar(it.get("name", ""))
            base = n.rsplit(".", 1)[0] if n.endswith((".xlsx", ".xls")) else n
            if base == objetivo and (
                n.endswith((".xlsx", ".xls")) or it.get("mimeType") == GSHEET_MIME
            ):
                return it
        return None

    raiz = listar(raiz_id)
    resultados = _hijo(raiz, "Resultados", carpeta=True)
    if resultados is not None:
        hallado = buscar(listar(resultados["id"]))
        if hallado:
            return hallado
    return buscar(raiz)


# ---------------------------------------------------------------------------
# Cliente de Drive (solo lectura)
# ---------------------------------------------------------------------------


class DriveLector:
    """Envoltorio mínimo de la API de Drive v3 con alcance drive.readonly."""

    def __init__(self, info_cuenta: dict):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        info = dict(info_cuenta)
        if "private_key" in info and isinstance(info["private_key"], str):
            # Por si la clave se pegó con '\n' literales en vez de saltos de línea.
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        self.email = info.get("client_email", "(sin client_email)")
        try:
            creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        except Exception as exc:  # noqa: BLE001
            raise DriveError(
                "La clave de la cuenta de servicio en los secrets no es válida. "
                "Revise que pegó el JSON completo en [gcp_service_account]."
            ) from exc
        self._svc = build("drive", "v3", credentials=creds, cache_discovery=False)

    # --- errores -----------------------------------------------------------
    def _traducir(self, exc: Exception, folder_id: str | None = None) -> DriveError:
        status = getattr(getattr(exc, "resp", None), "status", None)
        texto = str(exc)
        if status == 404:
            return DriveError(
                "No se encontró la carpeta o no está compartida con la cuenta de servicio. "
                f"Pida a la dueña de la carpeta que la comparta como «Lector» con {self.email}."
            )
        if status == 403:
            if "accessNotConfigured" in texto or "has not been used" in texto or "disabled" in texto:
                return DriveError(
                    "La API de Google Drive no está habilitada en el proyecto de Google Cloud "
                    "de la cuenta de servicio. Habilítela y vuelva a intentar."
                )
            return DriveError(
                f"La cuenta de servicio {self.email} no tiene permiso para leer esta carpeta. "
                "Pida que la compartan como «Lector»."
            )
        if "invalid_grant" in texto or "unauthorized_client" in texto:
            return DriveError(
                "Google rechazó la cuenta de servicio (clave revocada o mal copiada). "
                "Genere una clave JSON nueva y actualice los secrets."
            )
        return DriveError(f"No se pudo leer Google Drive: {texto[:300]}")

    # --- lectura -------------------------------------------------------------
    def verificar_carpeta(self, folder_id: str) -> dict:
        try:
            meta = (
                self._svc.files()
                .get(fileId=folder_id, fields="id,name,mimeType", supportsAllDrives=True)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise self._traducir(exc, folder_id) from exc
        if meta.get("mimeType") != FOLDER_MIME:
            raise DriveError("El enlace o ID corresponde a un archivo, no a una carpeta de Drive.")
        return meta

    def listar(self, folder_id: str) -> list[Item]:
        items: list[Item] = []
        token = None
        try:
            while True:
                resp = (
                    self._svc.files()
                    .list(
                        q=f"'{folder_id}' in parents and trashed = false",
                        fields="nextPageToken, files(id,name,mimeType,size)",
                        pageSize=1000,
                        pageToken=token,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    )
                    .execute()
                )
                items.extend(resp.get("files", []))
                token = resp.get("nextPageToken")
                if not token:
                    break
        except Exception as exc:  # noqa: BLE001
            raise self._traducir(exc, folder_id) from exc
        return items

    def descargar(self, item: Item, max_bytes: int | None = None) -> bytes:
        """Descarga un archivo a memoria (nunca escribe en Drive)."""
        from googleapiclient.http import MediaIoBaseDownload

        size = int(item.get("size") or 0)
        if max_bytes and size and size > max_bytes:
            raise DriveError(
                f"El archivo {item.get('name')} pesa {size / 1e6:.1f} MB y supera el límite "
                f"de {max_bytes / 1e6:.0f} MB configurado para descargas."
            )
        try:
            if item.get("mimeType") == GSHEET_MIME:
                req = self._svc.files().export_media(fileId=item["id"], mimeType=XLSX_MIME)
            else:
                req = self._svc.files().get_media(fileId=item["id"], supportsAllDrives=True)
            buf = io.BytesIO()
            dl = MediaIoBaseDownload(buf, req, chunksize=4 * 1024 * 1024)
            done = False
            while not done:
                _, done = dl.next_chunk()
                if max_bytes and buf.tell() > max_bytes:
                    raise DriveError(
                        f"El archivo {item.get('name')} supera el límite de "
                        f"{max_bytes / 1e6:.0f} MB configurado para descargas."
                    )
            return buf.getvalue()
        except DriveError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._traducir(exc) from exc


__all__ = [
    "DriveError",
    "DriveLector",
    "UbicacionWav",
    "elegir_wav",
    "es_carpeta_audio",
    "extraer_folder_id",
    "localizar_excel",
    "localizar_wav",
    "normalizar",
    "parsear_wav",
    "periodo_canonico",
]
