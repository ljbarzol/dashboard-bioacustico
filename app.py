#!/usr/bin/env python3
"""Dashboard bioacústico v1 — interfaz en español para el equipo y FCV."""

from __future__ import annotations

import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lib.audio import describir_muestra, espectrograma, listar_muestras, recortar_wav
from lib.data import apply_filters, csv_bytes, load_config, resolve_path
from lib.drive import DriveError
from lib.fuente import Fuente, cargar_datos, wav_de_drive
from lib.qc import chequeos_tabulares, hallazgos_frame

NAVY = "#0A3D5C"
TEAL = "#1A6A7A"
GOLD = "#C4A35A"
SUNRISE = "#D4A017"
SUNSET = "#3D5A80"
BG = "#F7F4EE"

PLOTLY_LAYOUT = dict(
    paper_bgcolor=BG,
    plot_bgcolor="white",
    font=dict(color="#1F2A30", size=13),
    margin=dict(l=40, r=20, t=50, b=40),
    title_font=dict(color=NAVY, size=16),
)


def _style(fig):
    fig.update_layout(**PLOTLY_LAYOUT)  # title_font only; no title key
    fig.update_xaxes(showgrid=True, gridcolor="#E6EAEF", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="#E6EAEF", zeroline=False)
    return fig


def render_resumen(df: pd.DataFrame, df_full: pd.DataFrame) -> None:
    st.subheader("Resumen del corpus")
    st.caption(
        "Una mirada rápida: cuántas detecciones quedan con los filtros actuales, "
        "de cuántas especies y en qué grabadoras. Las cifras se actualizan solas al cambiar los filtros."
    )
    n = len(df)
    n_sp = df["nombre_cientifico"].nunique() if n else 0
    n_dev = df["dispositivo"].nunique() if n else 0
    n_aud = df["audio_id"].nunique() if n else 0
    pct_valid = 100 * df["valid"].eq(1).mean() if n else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Detecciones", f"{n:,}".replace(",", " "))
    c2.metric("Especies", f"{n_sp}")
    c3.metric("Grabadoras", f"{n_dev}")
    c4.metric("Archivos con detección", f"{n_aud:,}".replace(",", " "))
    c5.metric("Validadas", f"{pct_valid:.1f} %")

    if n == 0:
        st.warning("Ninguna detección coincide con los filtros actuales.")
        return

    top = (
        df.groupby(["nombre_espanol", "nombre_cientifico"], as_index=False)
        .size()
        .sort_values("size", ascending=False)
        .head(12)
    )
    top["etiqueta"] = top["nombre_espanol"] + "  (" + top["nombre_cientifico"] + ")"
    fig = px.bar(
        top.sort_values("size"),
        x="size",
        y="etiqueta",
        orientation="h",
        labels={"size": "Número de detecciones", "etiqueta": ""},
        title="Especies con más detecciones",
        color_discrete_sequence=[TEAL],
    )
    fig.update_traces(hovertemplate="%{y}<br>%{x} detecciones<extra></extra>")
    st.plotly_chart(_style(fig), width='stretch')

    col_a, col_b = st.columns(2)
    with col_a:
        per = df["periodo"].value_counts().rename_axis("periodo").reset_index(name="detecciones")
        fig = px.bar(
            per,
            x="periodo",
            y="detecciones",
            color="periodo",
            color_discrete_map={"Mañana": SUNRISE, "Tarde": SUNSET},
            title="Detecciones por periodo del día",
            labels={"periodo": "Periodo", "detecciones": "Detecciones"},
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(_style(fig), width='stretch')
        st.caption(
            "En el corpus suele haber más detecciones en la mañana, aunque la ventana de la tarde es más larga."
        )
    with col_b:
        por_dev = (
            df.groupby("dispositivo", as_index=False)
            .agg(detecciones=("deteccion_id", "size"), especies=("nombre_cientifico", "nunique"))
            .sort_values("detecciones", ascending=False)
        )
        fig = px.bar(
            por_dev,
            x="dispositivo",
            y="detecciones",
            title="Detecciones por grabadora",
            labels={"dispositivo": "Grabadora", "detecciones": "Detecciones"},
            color_discrete_sequence=[NAVY],
        )
        st.plotly_chart(_style(fig), width='stretch')

    st.caption(
        f"El conjunto completo de la tabla, sin filtros, tiene "
        f"{len(df_full):,} detecciones.".replace(",", " ")
    )


def render_especies(df: pd.DataFrame, catalogo: pd.DataFrame) -> None:
    st.subheader("Especies, gremios y categoría IUCN")
    st.caption(
        "Quién aparece más a menudo, cómo se reparte la comunidad por gremio alimenticio "
        "y dónde están las pocas detecciones que no son de preocupación menor (LC)."
    )
    if df.empty:
        st.warning("Ninguna detección coincide con los filtros actuales.")
        return

    top = (
        df.groupby(["nombre_espanol", "nombre_cientifico", "gremio", "iucn"], as_index=False)
        .agg(
            detecciones=("deteccion_id", "size"),
            duracion_s=("duracion_segmento_s", "sum"),
            confidence_mediana=("confidence", "median"),
        )
        .sort_values("detecciones", ascending=False)
    )
    top["etiqueta"] = top["nombre_espanol"] + "  (" + top["nombre_cientifico"] + ")"
    fig = px.bar(
        top.head(20).sort_values("detecciones"),
        x="detecciones",
        y="etiqueta",
        orientation="h",
        title="Veinte especies con más detecciones",
        labels={"detecciones": "Número de detecciones", "etiqueta": ""},
        color_discrete_sequence=[TEAL],
    )
    st.plotly_chart(_style(fig), width='stretch')

    c1, c2 = st.columns(2)
    with c1:
        gremio = (
            df.groupby("gremio", as_index=False)
            .size()
            .sort_values("size", ascending=False)
            .rename(columns={"size": "detecciones"})
        )
        fig = px.bar(
            gremio,
            x="gremio",
            y="detecciones",
            title="Comunidad por gremio alimenticio",
            labels={"gremio": "Gremio", "detecciones": "Detecciones"},
            color_discrete_sequence=["#1D6B54"],
        )
        st.plotly_chart(_style(fig), width='stretch')
    with c2:
        iucn = df.groupby("iucn", as_index=False).size().rename(columns={"size": "detecciones"})
        fig = px.pie(
            iucn,
            names="iucn",
            values="detecciones",
            title="Categoría IUCN de las detecciones",
            color="iucn",
            color_discrete_map={"LC": TEAL, "NT": GOLD, "VU": "#8B3A3A"},
        )
        fig.update_layout(**PLOTLY_LAYOUT)  # title_font only; no title key
        st.plotly_chart(fig, width='stretch')
        no_lc = df[df["iucn"] != "LC"][
            ["nombre_espanol", "nombre_cientifico", "iucn", "dispositivo", "periodo", "hora"]
        ]
        if len(no_lc):
            st.markdown("**Detecciones que no son LC**")
            st.dataframe(no_lc, width='stretch', hide_index=True)

    if not catalogo.empty and "tiene_detecciones" in catalogo.columns:
        faltan = catalogo.loc[~catalogo["tiene_detecciones"]]
        if len(faltan):
            nombres = ", ".join(
                f"{r.nombre_espanol} (*{r.nombre_cientifico}*)" for r in faltan.itertuples()
            )
            st.info(f"Especies del catálogo que aún no tienen detecciones en la tabla: {nombres}.")

    st.markdown("**Tabla resumen por especie (exportable junto con el CSV del filtro)**")
    show = top.copy()
    show["duracion_s"] = show["duracion_s"].round(1)
    show["confidence_mediana"] = show["confidence_mediana"].round(3)
    show["porcentaje"] = (100 * show["detecciones"] / show["detecciones"].sum()).round(2)
    st.dataframe(
        show.drop(columns=["etiqueta"]),
        width='stretch',
        hide_index=True,
    )


def render_actividad(df: pd.DataFrame, cfg: dict) -> None:
    st.subheader("Actividad por hora y coros")
    manana = "–".join(cfg["coros"]["manana"])
    tarde = "–".join(cfg["coros"]["tarde"])
    st.caption(
        f"A qué horas se concentran las detecciones. Las ventanas de coro, según los CONFIG de las grabadoras, "
        f"son **{manana}** (mañana) y **{tarde}** (tarde), hora local UTC−5. "
        "El coro de la tarde suele ser más intenso al inicio de su ventana."
    )
    if df.empty:
        st.warning("Ninguna detección coincide con los filtros actuales.")
        return

    horas = (
        df.groupby("hora_num", as_index=False)
        .size()
        .rename(columns={"hora_num": "hora", "size": "detecciones"})
        .sort_values("hora")
    )
    horas["hora_label"] = horas["hora"].map(lambda h: f"{int(h):02d}:00")
    fig = px.bar(
        horas,
        x="hora_label",
        y="detecciones",
        title="Detecciones a lo largo del día",
        labels={"hora_label": "Hora local (UTC−5)", "detecciones": "Detecciones"},
        color_discrete_sequence=[TEAL],
    )
    fig.add_vrect(x0=-0.5, x1=2.5, fillcolor=SUNRISE, opacity=0.08, line_width=0)
    st.plotly_chart(_style(fig), width='stretch')
    st.caption(f"Franjas de coro: mañana {manana} · tarde {tarde}.")

    top_sp = (
        df.groupby("nombre_espanol").size().sort_values(ascending=False).head(10).index.tolist()
    )
    sub = df[df["nombre_espanol"].isin(top_sp)]
    pivot = (
        sub.pivot_table(
            index="nombre_espanol",
            columns="hora_num",
            values="deteccion_id",
            aggfunc="count",
            fill_value=0,
        )
        .reindex(top_sp)
    )
    pivot = pivot.reindex(columns=sorted(pivot.columns))
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=[f"{int(c):02d}:00" for c in pivot.columns],
            y=list(pivot.index),
            colorscale="Teal",
            colorbar=dict(title="Detecciones"),
            hovertemplate="Especie: %{y}<br>Hora: %{x}<br>Detecciones: %{z}<extra></extra>",
        )
    )
    fig.update_layout(
        **PLOTLY_LAYOUT,
        title="Actividad por hora y especie (diez especies más frecuentes)",
        xaxis_title="Hora local (UTC−5)",
        yaxis_title="",
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, width='stretch')

    per = (
        df.groupby(["nombre_espanol", "periodo"], as_index=False)
        .size()
        .rename(columns={"size": "detecciones"})
    )
    top10 = top_sp
    per = per[per["nombre_espanol"].isin(top10)]
    fig = px.bar(
        per,
        x="nombre_espanol",
        y="detecciones",
        color="periodo",
        barmode="group",
        color_discrete_map={"Mañana": SUNRISE, "Tarde": SUNSET},
        title="Mañana y tarde en las diez especies más frecuentes",
        labels={"nombre_espanol": "Especie", "detecciones": "Detecciones", "periodo": "Periodo"},
    )
    fig.update_xaxes(tickangle=-30)
    st.plotly_chart(_style(fig), width='stretch')


def render_grabadoras(df: pd.DataFrame) -> None:
    st.subheader("Comparación entre grabadoras")
    st.caption(
        "Diferencias de actividad y de composición entre los seis AudioMoth. "
        "No hay un mapa: en los datos no constan coordenadas. Mientras tanto comparamos por el código de la grabadora."
    )
    if df.empty:
        st.warning("Ninguna detección coincide con los filtros actuales.")
        return

    combo = (
        df.groupby(["dispositivo", "periodo"], as_index=False)
        .size()
        .rename(columns={"size": "detecciones"})
    )
    fig = px.bar(
        combo,
        x="dispositivo",
        y="detecciones",
        color="periodo",
        barmode="group",
        color_discrete_map={"Mañana": SUNRISE, "Tarde": SUNSET},
        title="Detecciones por grabadora y periodo del día",
        labels={"dispositivo": "Grabadora", "detecciones": "Detecciones", "periodo": "Periodo"},
    )
    st.plotly_chart(_style(fig), width='stretch')

    tabla = (
        df.groupby("dispositivo", as_index=False)
        .agg(
            detecciones=("deteccion_id", "size"),
            especies=("nombre_cientifico", "nunique"),
            archivos=("audio_id", "nunique"),
            confidence_mediana=("confidence", "median"),
        )
        .sort_values("detecciones", ascending=False)
    )
    tabla["confidence_mediana"] = tabla["confidence_mediana"].round(3)
    st.markdown("**Resumen por grabadora**")
    st.dataframe(tabla, width='stretch', hide_index=True)

    gremio_dev = (
        df.groupby(["dispositivo", "gremio"], as_index=False)
        .size()
        .rename(columns={"size": "detecciones"})
    )
    fig = px.bar(
        gremio_dev,
        x="dispositivo",
        y="detecciones",
        color="gremio",
        title="Composición por gremio en cada grabadora",
        labels={"dispositivo": "Grabadora", "detecciones": "Detecciones", "gremio": "Gremio"},
    )
    st.plotly_chart(_style(fig), width='stretch')


def render_calidad(df: pd.DataFrame, df_full: pd.DataFrame) -> None:
    st.subheader("Calidad de los datos")
    st.caption(
        "Incidencias ya observadas en el inventario en solo lectura de la carpeta AudioMoth–CONDESAN, "
        "más chequeos que se pueden calcular sobre la tabla. Un minuto grabado sin detección no se trata como error."
    )
    st.markdown("**Hallazgos conocidos del inventario**")
    st.dataframe(hallazgos_frame(), width='stretch', hide_index=True)

    st.markdown("**Chequeos sobre la tabla (con el filtro vigente)**")
    st.dataframe(chequeos_tabulares(df), width='stretch', hide_index=True)

    if not df.empty:
        fig = px.histogram(
            df,
            x="confidence",
            nbins=30,
            title="Distribución del puntaje de confianza",
            labels={"confidence": "Puntaje de confianza", "count": "Detecciones"},
            color_discrete_sequence=[TEAL],
        )
        st.plotly_chart(_style(fig), width='stretch')

    n0 = int((df_full["valid"] == 0).sum())
    st.info(
        f"En la tabla completa hay {n0} detecciones con Valid = 0. "
        "El filtro «Solo validadas» las oculta por defecto. "
        "Los WAV sin detecciones no se listan aquí: son lo esperado en la mayoría de los minutos."
    )


def _reproductor(fuente_audio, titulo: str, dets: pd.DataFrame, clave: str) -> None:
    """Reproduce un WAV (ruta o bytes) completo o solo el segmento de una detección."""
    opciones = ["Archivo completo"]
    if len(dets):
        opciones.insert(0, "Solo el segmento de la detección")
    modo = st.radio("Qué reproducir", opciones, horizontal=True, key=f"modo_{clave}")

    marcas = list(zip(dets["inicio_s"], dets["fin_s"])) if len(dets) else []
    try:
        if modo.startswith("Solo") and len(dets):
            etiquetas = [
                f"{r.nombre_espanol} · {r.inicio_s:g}–{r.fin_s:g} s · confianza {r.confidence:.2f}"
                for r in dets.itertuples()
            ]
            c1, c2 = st.columns([3, 1])
            i = c1.selectbox(
                "Detección", range(len(etiquetas)), format_func=lambda k: etiquetas[k], key=f"det_{clave}"
            )
            margen = c2.slider("Margen (s)", 0.0, 5.0, 1.0, 0.5, key=f"margen_{clave}")
            fila = dets.iloc[int(i)]
            wav, t0, t1 = recortar_wav(fuente_audio, fila["inicio_s"], fila["fin_s"], margen)
            st.audio(wav, format="audio/wav")
            st.caption(
                f"Segmento {t0:.1f}–{t1:.1f} s del archivo original "
                f"(detección {fila['inicio_s']:g}–{fila['fin_s']:g} s ± {margen:g} s)."
            )
            fig, meta = espectrograma(
                wav, f"{titulo} · {t0:.1f}–{t1:.1f} s", [(fila["inicio_s"], fila["fin_s"])], t0
            )
        else:
            if isinstance(fuente_audio, (bytes, bytearray)):
                st.audio(fuente_audio, format="audio/wav")
            else:
                st.audio(str(fuente_audio))
            fig, meta = espectrograma(fuente_audio, titulo, marcas)
            if marcas:
                st.caption("Las franjas celestes del espectrograma marcan las detecciones de la tabla.")
        m1, m2, m3 = st.columns(3)
        m1.metric("Duración mostrada", f"{meta['duracion_s']} s")
        m2.metric("Frecuencia de muestreo", f"{meta['sample_rate_hz']:,} Hz".replace(",", " "))
        m3.metric("Muestras", f"{meta['n_muestras']:,}".replace(",", " "))
        st.pyplot(fig, width='stretch')
        plt_close(fig)
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo leer o graficar el audio: {exc}")


_COLS_DET = ["nombre_espanol", "nombre_cientifico", "periodo", "hora", "inicio_s", "fin_s", "confidence", "valid"]


def render_explorador(cfg: dict, df: pd.DataFrame, fuente: Fuente) -> None:
    st.subheader("Explorador de audio")
    if fuente.drive:
        render_explorador_drive(cfg, df, fuente)
    else:
        render_explorador_local(cfg, df)


def render_explorador_drive(cfg: dict, df: pd.DataFrame, fuente: Fuente) -> None:
    st.caption(
        "Elija una grabación con detecciones y escúchela directamente desde Google Drive. "
        "Solo se descarga ese archivo (unos 5 MB), en modo solo lectura; no se modifica nada en Drive."
    )
    if df.empty:
        st.warning("Ninguna detección coincide con los filtros actuales.")
        return
    c1, c2, c3 = st.columns(3)
    dev = c1.selectbox("Grabadora", sorted(df["dispositivo"].dropna().unique()), key="exp_dev")
    sub = df[df["dispositivo"] == dev]
    dias = sorted(pd.to_datetime(sub["fecha"]).dt.strftime("%Y-%m-%d").dropna().unique())
    dia = c2.selectbox("Día", dias, key="exp_dia")
    sub = sub[pd.to_datetime(sub["fecha"]).dt.strftime("%Y-%m-%d") == dia]
    grupos = (
        sub.groupby(["hora", "periodo", "periodo_codigo"], as_index=False)
        .size()
        .sort_values("hora")
    )
    etiquetas = [f"{g.hora} · {g.periodo} ({g.size} detecc.)" for g in grupos.itertuples()]
    k = c3.selectbox("Grabación (hora)", range(len(etiquetas)), format_func=lambda i: etiquetas[i], key="exp_hora")
    g = grupos.iloc[int(k)]
    dets = sub[sub["hora"] == g["hora"]].sort_values("inicio_s")
    st.dataframe(dets[_COLS_DET], width='stretch', hide_index=True)

    clave = f"{dev}|{dia}|{g['hora']}"
    if st.button("Escuchar desde Google Drive", type="primary", key="exp_cargar"):
        st.session_state["audio_drive"] = clave
    if st.session_state.get("audio_drive") != clave:
        st.caption("Pulse el botón para descargar y reproducir esta grabación.")
        return
    try:
        with st.spinner("Buscando y descargando el WAV desde Google Drive…"):
            data, ruta = wav_de_drive(
                fuente, dev, pd.Timestamp(dia), g["hora"], g["periodo_codigo"], cfg
            )
    except DriveError as exc:
        st.error(str(exc))
        return
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo descargar el audio: {exc}")
        return
    st.caption(f"Archivo en Drive: {ruta}")
    _reproductor(data, ruta.split("/")[-1], dets, clave="drive")


def render_explorador_local(cfg: dict, df: pd.DataFrame) -> None:
    st.caption(
        "Escuche y vea el espectrograma de las grabaciones de muestra incluidas en el repositorio. "
        "Si se conecta Google Drive (ver «Fuente de datos» en la barra lateral), podrá escuchar "
        "cualquier grabación del corpus bajo demanda."
    )
    wav_dir = resolve_path(cfg["rutas"]["audios_muestra"])
    muestras = listar_muestras(wav_dir)
    if not muestras:
        st.warning(f"No se encontraron WAV de muestra en {wav_dir}.")
        return

    etiquetas = [p.name for p in muestras]
    elegido = st.selectbox("Grabación de muestra", etiquetas)
    path = next(p for p in muestras if p.name == elegido)
    info = describir_muestra(path)

    c1, c2, c3 = st.columns(3)
    c1.metric("Grabadora", info["dispositivo"])
    c2.metric("Tipo", info["tipo"])
    c3.write(info["sello"])

    # Si el sello coincide con filas de la tabla, unirlas (solo para WAV originales).
    relacionados = pd.DataFrame(columns=_COLS_DET)
    es_clip = "segment" in path.name.lower()
    if info["dispositivo"] != "—" and "hora" in df.columns and ":" in info["sello"] and not es_clip:
        sello_hora = info["sello"].split(" ")[0]
        relacionados = df[(df["dispositivo"] == info["dispositivo"]) & (df["hora"] == sello_hora)]
        m = re.search(r"(20\d{6})_\d{6}", path.name)
        if m and len(relacionados):
            relacionados = relacionados[
                pd.to_datetime(relacionados["fecha"]).dt.strftime("%Y%m%d") == m.group(1)
            ]
        relacionados = relacionados.sort_values("inicio_s")

    _reproductor(path, path.name, relacionados, clave=f"local_{path.name}")

    if len(relacionados):
        st.markdown("**Detecciones de la tabla que coinciden con esta muestra (según filtros)**")
        st.dataframe(relacionados[_COLS_DET], width='stretch', hide_index=True)
    else:
        st.caption("No hay detecciones de la tabla filtrada unidas a esta muestra, o es un clip de recorte.")

    st.info(info["nota"])


def plt_close(fig) -> None:
    import matplotlib.pyplot as plt

    plt.close(fig)


def sidebar_filters(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Filtros")
    st.sidebar.caption("Los gráficos y las cifras de todas las pestañas respetan esta selección.")

    dispositivos = sorted(df["dispositivo"].dropna().unique().tolist())
    sel_dev = st.sidebar.multiselect("Grabadora", dispositivos, default=dispositivos)

    periodos = [p for p in ("Mañana", "Tarde") if p in set(df["periodo"].unique())]
    sel_per = st.sidebar.multiselect("Periodo del día", periodos, default=periodos)

    gremios = sorted(df["gremio"].dropna().unique().tolist())
    sel_grem = st.sidebar.multiselect("Gremio alimenticio", gremios, default=gremios)

    iucns = sorted(df["iucn"].dropna().unique().tolist())
    sel_iucn = st.sidebar.multiselect("Categoría IUCN", iucns, default=iucns)

    especies = sorted(df["nombre_espanol"].dropna().unique().tolist())
    sel_esp = st.sidebar.multiselect(
        "Especie (nombre en español)",
        especies,
        default=[],
        help="Déjelo vacío para ver todas las especies. Puede escribir para buscar.",
    )

    defaults = cfg.get("filtros_por_defecto", {})
    solo_val = st.sidebar.checkbox("Solo detecciones validadas", value=bool(defaults.get("solo_valid", True)))
    conf_min = st.sidebar.slider(
        "Umbral mínimo de confianza",
        min_value=0.0,
        max_value=1.0,
        value=float(defaults.get("confidence_min", 0.0)),
        step=0.01,
    )

    filtrado = apply_filters(
        df,
        dispositivos=sel_dev,
        periodos=sel_per,
        especies=sel_esp or None,
        gremios=sel_grem,
        iucn=sel_iucn,
        solo_validadas=solo_val,
        confidence_min=conf_min,
    )
    st.sidebar.markdown("---")
    st.sidebar.write(f"**{len(filtrado):,}** detecciones con este filtro.".replace(",", " "))
    st.sidebar.download_button(
        "Descargar CSV filtrado",
        data=csv_bytes(filtrado),
        file_name="detecciones_filtradas.csv",
        mime="text/csv",
    )
    return filtrado


def main() -> None:
    st.set_page_config(
        page_title="Dashboard bioacústico · Campus Prosperina",
        page_icon="🪶",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    cfg = load_config()
    st.title(cfg.get("titulo", "Dashboard bioacústico"))
    st.caption(
        f"Proyecto {cfg.get('proyecto', '')}  ·  versión {cfg.get('version', '1')}  ·  "
        "herramienta de consulta para el equipo y para la Facultad de Ciencias de la Vida. "
        "No se modifica nada en Google Drive."
    )

    try:
        df, catalogo, fuente = cargar_datos(cfg)
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()
        return

    filtrado = sidebar_filters(df, cfg)

    tabs = st.tabs(
        [
            "Resumen",
            "Especies y gremios",
            "Actividad por hora",
            "Grabadoras",
            "Calidad de datos",
            "Explorador de audio",
        ]
    )
    with tabs[0]:
        render_resumen(filtrado, df)
    with tabs[1]:
        render_especies(filtrado, catalogo)
    with tabs[2]:
        render_actividad(filtrado, cfg)
    with tabs[3]:
        render_grabadoras(filtrado)
    with tabs[4]:
        render_calidad(filtrado, df)
    with tabs[5]:
        render_explorador(cfg, filtrado, fuente)


if __name__ == "__main__":
    main()
