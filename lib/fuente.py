"""Selección de la fuente de datos del dashboard: Google Drive (opcional) o Parquet locales.

Orden para el ID de carpeta: campo de la barra lateral > secrets ``[drive] folder_id``
> ``config.yaml`` ``drive.folder_id``. Si no hay cuenta de servicio o falla Drive,
se usan los Parquet del repositorio, así la app nunca se queda sin datos.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import pandas as pd
import streamlit as st

from lib.data import load_tables
from lib.drive import DriveError, DriveLector, extraer_folder_id, localizar_excel, localizar_wav
from lib.transform import transformar_tablas

TTL_S = 3600


@dataclass
class Fuente:
    modo: str  # "drive" | "local"
    folder_id: str | None = None
    folder_nombre: str | None = None
    origen_id: str | None = None  # "barra lateral" | "secrets" | "config.yaml"
    email_cuenta: str | None = None
    error: str | None = None
    detalles: list[str] = field(default_factory=list)

    @property
    def drive(self) -> bool:
        return self.modo == "drive"


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


def _secrets_seccion(nombre: str) -> dict | None:
    """Lee una tabla de st.secrets sin fallar si no existe secrets.toml."""
    try:
        if nombre in st.secrets:
            return dict(st.secrets[nombre])
    except Exception:  # noqa: BLE001 — sin secrets.toml Streamlit lanza excepción
        return None
    return None


def cuenta_servicio() -> dict | None:
    info = _secrets_seccion("gcp_service_account")
    if not info or not info.get("private_key") or not info.get("client_email"):
        return None
    return info


@st.cache_resource(show_spinner=False)
def _lector() -> DriveLector:
    info = cuenta_servicio()
    if info is None:
        raise DriveError("No hay cuenta de servicio configurada.")
    return DriveLector(info)


# ---------------------------------------------------------------------------
# Cachés de lectura (solo lectura en Drive)
# ---------------------------------------------------------------------------


@st.cache_data(ttl=TTL_S, show_spinner=False)
def _listar(folder_id: str) -> list[dict]:
    return _lector().listar(folder_id)


@st.cache_data(ttl=TTL_S, show_spinner=False)
def _verificar(folder_id: str) -> dict:
    return _lector().verificar_carpeta(folder_id)


@st.cache_data(ttl=TTL_S, show_spinner="Descargando TablaFinal y Lista_Especies desde Google Drive…")
def _tablas_drive(folder_id: str, cfg_cols: tuple) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    cfg = _descongelar(cfg_cols)
    lector = _lector()
    tabla = localizar_excel(_listar, folder_id, "TablaFinal")
    if tabla is None:
        raise DriveError(
            "La carpeta no tiene Resultados/TablaFinal.xlsx. Revise que sea la carpeta del "
            "dataset AudioMoth (con la subcarpeta «Resultados»)."
        )
    catalogo = localizar_excel(_listar, folder_id, "Lista_Especies")
    raw = pd.read_excel(io.BytesIO(lector.descargar(tabla)))
    detalles = [f"Tabla: {tabla['name']}"]
    if catalogo is not None:
        cat_raw = pd.read_excel(io.BytesIO(lector.descargar(catalogo)))
        detalles.append(f"Catálogo: {catalogo['name']}")
    else:
        cat_raw = pd.DataFrame(columns=list(cfg["columnas_catalogo"].values()))
        detalles.append("Catálogo: no se encontró Lista_Especies.xlsx")
    try:
        det, cat = transformar_tablas(raw, cat_raw, cfg)
    except ValueError as exc:
        raise DriveError(f"TablaFinal.xlsx no tiene el formato esperado: {exc}") from exc
    return det, cat, detalles


@st.cache_data(ttl=TTL_S, show_spinner=False, max_entries=64)
def _ubicar_wav(folder_id: str, dispositivo: str, dia: str, hora: str, periodo: str | None, tol: int):
    ub = localizar_wav(_listar, folder_id, dispositivo, dia, hora, periodo, tol)
    return (ub.archivo, ub.ruta) if ub else None


@st.cache_data(ttl=TTL_S, show_spinner=False, max_entries=12)
def _descargar_wav(file_id: str, nombre: str, size: str | None, max_bytes: int) -> bytes:
    return _lector().descargar({"id": file_id, "name": nombre, "size": size}, max_bytes=max_bytes)


def limpiar_cache() -> None:
    for fn in (_listar, _verificar, _tablas_drive, _ubicar_wav, _descargar_wav):
        fn.clear()
    _lector.clear()


# ---------------------------------------------------------------------------
# Barra lateral y carga
# ---------------------------------------------------------------------------


def _folder_por_defecto(cfg: dict) -> tuple[str | None, str | None]:
    sec = _secrets_seccion("drive") or {}
    fid = extraer_folder_id(str(sec.get("folder_id", "") or ""))
    if fid:
        return fid, "secrets"
    fid = extraer_folder_id(str((cfg.get("drive") or {}).get("folder_id", "") or ""))
    if fid:
        return fid, "config.yaml"
    return None, None


def _cfg_hashable(cfg: dict) -> tuple:
    claves = ("columnas_tabla_final", "columnas_catalogo", "alias_periodo")
    return tuple((k, _congelar(cfg[k])) for k in claves)


def _congelar(x):
    if isinstance(x, dict):
        return tuple(sorted((k, _congelar(v)) for k, v in x.items()))
    return x


def _descongelar(cfg_cols: tuple) -> dict:
    return {k: dict(v) for k, v in cfg_cols}


def cargar_datos(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, Fuente]:
    """Dibuja la sección «Fuente de datos» y devuelve (detecciones, catálogo, fuente)."""
    sb = st.sidebar
    sb.markdown("### Fuente de datos")
    info = cuenta_servicio()
    fid_def, origen_def = _folder_por_defecto(cfg)

    texto = sb.text_input(
        "Carpeta de Google Drive (opcional)",
        value="",
        placeholder="Pegue el enlace o el ID de otra carpeta",
        help=(
            "Déjelo vacío para usar la carpeta configurada. La carpeta debe estar compartida "
            "como «Lector» con la cuenta de servicio y tener la misma estructura "
            "(Resultados/TablaFinal.xlsx y carpetas AM00X/AAAAMMDD/…). Nunca se modifica nada en Drive."
        ),
        disabled=info is None,
    )
    if sb.button("Recargar datos", help="Vuelve a leer los Excel y la lista de archivos de Drive."):
        limpiar_cache()

    fuente = Fuente(modo="local")
    if info is None:
        sb.info(
            "Usando datos locales (copia incluida en el repositorio). "
            "Para leer directamente de Google Drive, configure la cuenta de servicio en los secrets."
        )
    else:
        fuente.email_cuenta = info.get("client_email")
        fid, origen = fid_def, origen_def
        if texto.strip():
            fid = extraer_folder_id(texto)
            origen = "barra lateral"
            if not fid:
                fuente.error = "El texto pegado no parece un enlace ni un ID de carpeta de Google Drive."
        if fid and not fuente.error:
            try:
                meta = _verificar(fid)
                det, cat, detalles = _tablas_drive(fid, _cfg_hashable(cfg))
                fuente = Fuente(
                    modo="drive",
                    folder_id=fid,
                    folder_nombre=meta.get("name"),
                    origen_id=origen,
                    email_cuenta=info.get("client_email"),
                    detalles=detalles,
                )
                sb.success(
                    f"Conectado a Google Drive: «{fuente.folder_nombre}» "
                    f"({len(det):,} detecciones).".replace(",", " ")
                )
                sb.caption(f"Carpeta tomada de: {origen}. Cuenta: {fuente.email_cuenta}. Solo lectura.")
                return det, cat, fuente
            except DriveError as exc:
                fuente.error = str(exc)
            except Exception as exc:  # noqa: BLE001
                fuente.error = f"Error inesperado al leer Google Drive: {exc}"
        elif not fid and not fuente.error:
            fuente.error = "No hay ID de carpeta configurado (secrets [drive] o config.yaml)."
        sb.error(fuente.error + "\n\nMientras tanto se muestran los datos locales.")
        sb.caption(f"Cuenta de servicio: {fuente.email_cuenta}")

    det, cat = load_tables(cfg)
    return det, cat, fuente


def wav_de_drive(
    fuente: Fuente, dispositivo: str, fecha, hora: str, periodo: str | None, cfg: dict
) -> tuple[bytes, str]:
    """Localiza y descarga (con caché) el WAV original de una detección."""
    dcfg = cfg.get("drive") or {}
    tol = int(dcfg.get("tolerancia_segundos", 1))
    max_mb = float(dcfg.get("max_audio_mb", 25))
    dia = fecha.strftime("%Y%m%d") if hasattr(fecha, "strftime") else str(fecha)
    hallado = _ubicar_wav(fuente.folder_id, dispositivo, dia, hora, periodo, tol)
    if hallado is None:
        raise DriveError(
            f"No se encontró en Drive el WAV de {dispositivo} del {dia} a las {hora} "
            f"(se buscó con tolerancia de ±{tol} s en las carpetas de audio del día)."
        )
    item, ruta = hallado
    data = _descargar_wav(item["id"], item["name"], item.get("size"), int(max_mb * 1e6))
    return data, ruta
