# Dashboard bioacústico del Campus Prosperina (v1)

Primera versión de consulta del dataset bioacústico del proyecto **FIEC-005-2026**. Está pensada para el equipo de FIEC y para investigadoras e investigadores de la Facultad de Ciencias de la Vida: se usa en el navegador, en español, sin programar.

El dashboard lee los archivos Parquet ya incluidos en `data/` y unas grabaciones de muestra en `data/wav/`. **No modifica nada en Google Drive.**

## Cómo desplegarlo en Streamlit Community Cloud

1. Entre a [share.streamlit.io](https://share.streamlit.io) e inicie sesión con la cuenta de GitHub **ljbarzol**.
2. Pulse **New app**.
3. Elija el repositorio **ljbarzol/dashboard-bioacustico**, la rama **main** y, como archivo principal, **app.py**.
4. En la configuración avanzada, elija **Python 3.12**. Esta aplicación no instala en Python 3.11, porque `librosa` 1.0 y `numpy` 2.5 requieren 3.12 o superior.
5. Despliegue la app y espere a que termine la instalación (`requirements.txt` y `packages.txt`).
6. Vaya a **Settings → Sharing**, elija **Only specific people can view this app** e invite por correo a las personas que deben verla.

El repositorio es privado. Community Cloud puede desplegar repositorios privados de la misma cuenta de GitHub. Si la app pide permisos adicionales, acéptelos con **ljbarzol**.

## Cómo arrancarlo en local

Desde la raíz de este repositorio, con Python 3.12 o 3.13:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Luego abra [http://localhost:8501](http://localhost:8501). No hace falta volver a generar los Parquet: ya están en `data/`.

## Infraestructura

- **Interfaz:** Streamlit con gráficos interactivos de Plotly.
- **Datos:** el dashboard carga `data/detecciones.parquet` y `data/catalogo.parquet`. Las rutas se resuelven respecto a `app.py`, no respecto al directorio de trabajo.
- **Audio:** `librosa`, `soundfile` y `matplotlib` para el espectrograma; el reproductor de Streamlit para oír la grabación. En esta v1 solo hay tres muestras en `data/wav/` (dos WAV originales y un clip de 3 s). El corpus completo de Drive se cargará bajo demanda más adelante.
- **Configuración:** `config.yaml` (columnas, alias de periodo, ventanas de coro, rutas relativas a la raíz del repo).
- **Ingesta (opcional):** `python -m pipeline.ingest` regenera los Parquet a partir de `data/TablaFinal.xlsx` y `data/Lista_Especies.xlsx`. Esos Excel no se incluyen en el repositorio; el dashboard funciona sin ellos.
- **Despliegue:** Streamlit Community Cloud (esta v1). El `Dockerfile` queda preparado por si más adelante se monta en un servidor de ESPOL.

## Qué incluye esta versión

- Filtros laterales: grabadora, periodo (mañana/tarde), especie, gremio, categoría IUCN, solo detecciones validadas y umbral de confianza.
- Pestañas: Resumen, Especies y gremios, Actividad por hora (con *heatmap* hora × especie y las ventanas de coro 05:30–08:00 y 17:00–21:00), Grabadoras, Calidad de datos, Explorador de audio y Análisis de Michael (reserva).
- Descarga de un CSV con las detecciones que pasan el filtro.

## Limitaciones de la v1

- No hay conexión a Google Drive. El inventario completo de WAV no está aquí; solo tres grabaciones de muestra en `data/wav/`.
- No hay mapa: en los datos no constan coordenadas de las grabadoras.
- La página de Michael es un espacio reservado (las vistas de especies, gremios y periodo ya se recrean en las otras pestañas).
- El control de calidad muestra los hallazgos conocidos del inventario y chequeos tabulares; todavía no recorre carpetas de Drive ni mide *clipping* o silencio sobre el corpus.
