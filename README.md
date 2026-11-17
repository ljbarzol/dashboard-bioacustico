# Dashboard bioacústico del Campus Prosperina (v1)

Primera versión de consulta del dataset bioacústico del proyecto **FIEC-005-2026**. Está pensada para el equipo de FIEC y para investigadoras e investigadores de la Facultad de Ciencias de la Vida: se usa en el navegador, en español, sin programar.

Por defecto, el dashboard lee los archivos Parquet ya incluidos en `data/` y unas grabaciones de muestra en `data/wav/`. Opcionalmente puede leer los datos y los audios **directamente desde Google Drive, en modo solo lectura** (ver «Conectar Google Drive»). **Nunca modifica nada en Google Drive.**

## Cómo desplegarlo en Streamlit Community Cloud

1. Entre a [share.streamlit.io](https://share.streamlit.io) e inicie sesión con la cuenta de GitHub **ljbarzol**.
2. Pulse **New app**.
3. Elija el repositorio **ljbarzol/dashboard-bioacustico**, la rama **main** y, como archivo principal, **app.py**.
4. En la configuración avanzada, elija **Python 3.12**. Esta aplicación no instala en Python 3.11, porque `librosa` 1.0 y `numpy` 2.5 requieren 3.12 o superior.
5. Despliegue la app y espere a que termine la instalación (`requirements.txt` y `packages.txt`).
6. Vaya a **Settings → Sharing**, elija **Only specific people can view this app** e invite por correo a las personas que deben verla.

El repositorio es público; si la app pide permisos adicionales, acéptelos con **ljbarzol**. Si quiere que la app también sea pública, elija **This app is public and searchable** en el paso 6.

## Cómo arrancarlo en local

Desde la raíz de este repositorio, con Python 3.12 o 3.13:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Luego abra [http://localhost:8501](http://localhost:8501). No hace falta volver a generar los Parquet: ya están en `data/`.

Para correr las pruebas: `pip install pytest` y luego `python -m pytest -q tests`.

## Conectar Google Drive (opcional, solo lectura)

Sin esta configuración la app funciona igual, con los datos locales. Con ella, la barra lateral muestra **Fuente de datos: Conectado a Google Drive**, los gráficos usan `Resultados/TablaFinal.xlsx` y `Resultados/Lista_Especies.xlsx` de la carpeta (se vuelven a leer cada hora o con el botón **Recargar datos**), y el **Explorador de audio** puede reproducir cualquier grabación del corpus: se elige grabadora, día y hora, y solo se descarga ese WAV (unos 5 MB). Se puede oír el archivo completo o solo el segmento de una detección (`Inicio`–`Final` ± un margen).

### 1. Crear la cuenta de servicio en Google Cloud

1. Entre a [console.cloud.google.com](https://console.cloud.google.com) y cree un proyecto (o use uno existente).
2. En **APIs y servicios → Biblioteca**, busque **Google Drive API** y pulse **Habilitar**.
3. En **IAM y administración → Cuentas de servicio**, pulse **Crear cuenta de servicio** (por ejemplo, `dashboard-lector`). No necesita roles del proyecto.
4. Abra la cuenta creada → pestaña **Claves** → **Agregar clave → Crear clave nueva → JSON**. Se descarga un archivo `.json`. Guárdelo en un lugar seguro y **no lo suba a GitHub**.
5. Copie el correo de la cuenta (`client_email`, termina en `.iam.gserviceaccount.com`).

### 2. Compartir la carpeta

Pida a la dueña de la carpeta de Drive que la comparta como **Lector** con el correo de la cuenta de servicio. La app usa solo el permiso `drive.readonly`: aunque tuviera más permisos, no crea, edita, mueve ni borra nada.

### 3. Pegar la clave en los secrets

En Streamlit Community Cloud: **la app → ⋮ → Settings → Secrets**. En local: cree `.streamlit/secrets.toml` (ya está en `.gitignore`). Use el formato de `.streamlit/secrets.toml.example`; cada campo del JSON va como una línea dentro de `[gcp_service_account]`:

```toml
[drive]
folder_id = "1yjJKnCO6NgIXe88RHFza3SsOC1mC0Twf"   # opcional

[gcp_service_account]
type = "service_account"
project_id = "su-proyecto"
private_key_id = "..."
private_key = """-----BEGIN PRIVATE KEY-----
...
-----END PRIVATE KEY-----
"""
client_email = "dashboard-lector@su-proyecto.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
universe_domain = "googleapis.com"
```

Guarde los secrets; la app se reinicia sola. Si algo falla, la barra lateral muestra el motivo en español (por ejemplo, que la carpeta no está compartida con el correo de la cuenta de servicio) y sigue mostrando los datos locales.

### Cómo cambiar la carpeta

La carpeta se elige en este orden:

1. El campo **Carpeta de Google Drive** de la barra lateral (acepta el enlace completo o solo el ID). Vale solo para esa sesión del navegador.
2. `folder_id` dentro de `[drive]` en los secrets (cambio permanente sin tocar el código).
3. `drive.folder_id` en `config.yaml` (por defecto, *AudioMoth - CONDESAN*).

La carpeta nueva debe estar compartida con la cuenta de servicio y tener la misma estructura: `Resultados/TablaFinal.xlsx` (y `Lista_Especies.xlsx`) y las carpetas `AM00X/AAAAMMDD/<periodo>/`. Para el periodo se reconocen `Audio_Sunrise`, `Audios_Sunrise`, `Morning`, `Mañana` y sus equivalentes de la tarde (`Audio_Sunset`, `Audios_Sunset`, `Sunset`, `Tarde`); los WAV pueden llamarse `AAAAMMDD_HHMMSS.WAV` o `{DEVICEID}_AAAAMMDD_HHMMSS.WAV`, con tolerancia de ±1 s (`drive.tolerancia_segundos`). El límite por WAV descargado es `drive.max_audio_mb` (25 MB).

## Infraestructura

- **Interfaz:** Streamlit con gráficos interactivos de Plotly.
- **Datos:** sin Drive, el dashboard carga `data/detecciones.parquet` y `data/catalogo.parquet` (rutas relativas a `app.py`). Con Drive, descarga los Excel de `Resultados/` y los pasa por la misma transformación que la ingesta (`lib/transform.py`), con caché de una hora.
- **Google Drive (opcional):** `lib/drive.py` (API de Drive v3 con cuenta de servicio, alcance `drive.readonly`, búsqueda tolerante de carpetas y nombres de WAV) y `lib/fuente.py` (secrets, caché y barra lateral).
- **Audio:** `librosa`, `soundfile` y `matplotlib` para el espectrograma; el reproductor de Streamlit para oír la grabación o solo el segmento de una detección. Sin Drive hay tres muestras en `data/wav/` (dos WAV originales y un clip de 3 s); con Drive, cualquier WAV se descarga bajo demanda.
- **Configuración:** `config.yaml` (columnas, alias de periodo, ventanas de coro, rutas relativas a la raíz del repo).
- **Ingesta (opcional):** `python -m pipeline.ingest` usa la misma transformación y regenera los Parquet a partir de `data/TablaFinal.xlsx` y `data/Lista_Especies.xlsx`. Esos Excel no se incluyen en el repositorio; el dashboard funciona sin ellos.
- **Despliegue:** Streamlit Community Cloud (esta v1). El `Dockerfile` queda preparado por si más adelante se monta en un servidor de ESPOL.

## Qué incluye esta versión

- Filtros laterales: grabadora, periodo (mañana/tarde), especie, gremio, categoría IUCN, solo detecciones validadas y umbral de confianza.
- Pestañas: Resumen, Especies y gremios, Actividad por hora (con *heatmap* hora × especie y las ventanas de coro 05:30–08:00 y 17:00–21:00), Grabadoras, Calidad de datos y Explorador de audio.
- Descarga de un CSV con las detecciones que pasan el filtro.

## Limitaciones de la v1

- La conexión con Google Drive requiere una cuenta de servicio y que la carpeta se comparta con ella; sin eso solo están las tres grabaciones de muestra de `data/wav/`.
- Al cambiar `TablaFinal.xlsx` en Drive, el dashboard lo verá en máximo una hora o al pulsar **Recargar datos**. Los Parquet de `data/` (respaldo sin Drive) solo se actualizan con `python -m pipeline.ingest`.
- No hay mapa: en los datos no constan coordenadas de las grabadoras.
- El control de calidad muestra los hallazgos conocidos del inventario y chequeos tabulares; todavía no recorre todas las carpetas de Drive ni mide *clipping* o silencio sobre el corpus.
