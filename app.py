"""Dashboard del proyecto: venta cruzada, rentabilidad y reabastecimiento.

Usa la misma lógica que los notebooks (``src/analitica.py``), así que los
resultados coinciden con los del análisis.
"""

from io import BytesIO
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src import analitica as an

RAIZ = Path(__file__).resolve().parent
PROCESADOS = RAIZ / "data" / "processed"

st.set_page_config(page_title="Dashboard Autopartes | Proyecto-2", page_icon="🚗", layout="wide")


# ==========================================
# CARGA DE DATOS
# ==========================================
def _leer(subido, archivo):
    if subido is not None:
        return pd.read_csv(BytesIO(subido.getvalue()))
    return pd.read_csv(PROCESADOS / archivo)


@st.cache_data(show_spinner="Cargando datos…")
def cargar(inv_bytes, ventas_bytes, compras_bytes):
    inventario = an.preparar_inventario(_leer(inv_bytes, "INVENTARIO_PRODUCTOS_LIMPIO.csv"))
    ventas = an.preparar_ventas(_leer(ventas_bytes, "ventas_limpia.csv"))
    compras = an.preparar_compras(_leer(compras_bytes, "DS_COMPRAS.csv"))
    return inventario, ventas, compras


@st.cache_data(show_spinner="Calculando reglas de asociación…")
def calcular_track1(inventario, ventas):
    canasta = an.canasta_por_factura(ventas, inventario)
    reglas, comparacion = an.reglas_asociacion(canasta)
    return canasta, reglas, comparacion


@st.cache_data(show_spinner="Calculando rentabilidad y rotación…")
def calcular_track2(inventario, ventas, compras):
    calidad = an.control_calidad_costos(inventario, ventas, compras)
    rentabilidad = an.rentabilidad_por_referencia(ventas, calidad)
    rotacion = an.rotacion_inventario(inventario, ventas, calidad)
    segmentacion, evaluacion, resumen = an.segmentar_referencias(rentabilidad)
    return calidad, rotacion, segmentacion, resumen


@st.cache_data(show_spinner="Validando pronóstico y generando el plan…")
def calcular_track3(inventario, ventas, compras):
    return an.plan_reabastecimiento(inventario, ventas, compras)


st.sidebar.title("🗂️ Proyecto-2: Autopartes")
st.sidebar.markdown("### 📥 Reemplazar datos (opcional)")
inv_subido = st.sidebar.file_uploader("Inventario limpio (.csv)", type=["csv"])
ventas_subidas = st.sidebar.file_uploader("Ventas limpias (.csv)", type=["csv"])
compras_subidas = st.sidebar.file_uploader("Compras (.csv)", type=["csv"])
st.sidebar.info("Por defecto se usan los CSV de `data/processed/`. Lo que subas reemplaza esa fuente solo en esta sesión.")

try:
    inventario, ventas, compras = cargar(inv_subido, ventas_subidas, compras_subidas)
except (FileNotFoundError, ValueError) as error:
    st.error(f"No se pudieron cargar los datos: {error}")
    st.stop()

st.title("🚗 Dashboard: venta cruzada, rentabilidad y reabastecimiento")
st.caption(f"Datos de ventas del {ventas['fecha'].min():%Y-%m-%d} al {ventas['fecha'].max():%Y-%m-%d} · "
           "Familias: ACEITES, BATERIAS, FILTROS, LLANTAS")

tab1, tab2, tab3 = st.tabs([
    "🛒 Track 1: venta cruzada",
    "💰 Track 2: rentabilidad y lento movimiento",
    "🚀 Track 3: reabastecimiento",
])

# ==========================================
# TRACK 1
# ==========================================
with tab1:
    canasta, reglas, comparacion = calcular_track1(inventario, ventas)
    st.markdown("Reglas calculadas sobre **todas las facturas**: el lift se mide contra el total real de transacciones.")
    c1, c2 = st.columns([1, 2])
    with c1:
        familia = st.selectbox("Familia que lleva el cliente", list(an.CATEGORIAS))
        st.metric("Facturas analizadas", f"{len(canasta):,}")
        st.metric("Reglas fuertes", int((reglas["fuerza"] == "Fuerte").sum()))
    with c2:
        st.markdown(f"#### Sugerencias para **{familia}**")
        sugeridas = reglas[reglas["antecedente"] == familia]
        for _, r in sugeridas.iterrows():
            texto = (f"**{r.consecuente}** · confianza {r.confidence:.1%} · lift {r.lift:.2f} · "
                     f"soporte {r.support:.2%} · *{r.fuerza}*")
            (st.success if r.fuerza == "Fuerte" else st.info)(texto)
    st.plotly_chart(
        px.bar(reglas.assign(regla=reglas["antecedente"] + " → " + reglas["consecuente"]),
               x="lift", y="regla", color="fuerza", orientation="h",
               color_discrete_map={"Fuerte": "#2E7D32", "Débil": "#F9A825", "Sin asociación": "#9E9E9E"},
               hover_data={"confidence": ":.1%", "support": ":.2%"}, title="Lift por regla (1 = independencia)"),
        width="stretch",
    )

# ==========================================
# TRACK 2
# ==========================================
with tab2:
    calidad, rotacion, segmentacion, resumen_seg = calcular_track2(inventario, ventas, compras)
    rot_total = an.resumen_rotacion(rotacion)
    lento = rot_total[rot_total["tramo_rotacion"].isin(an.TRAMOS_ROTACION[3:])]
    c1, c2, c3 = st.columns(3)
    c1.metric("Stock sin venta > 180 días o sin ventas", f"{lento['valor_stock'].sum() / 1e6:,.1f} M COP",
              f"{lento['pct_valor'].sum():.1f} % del stock valorizado", delta_color="off")
    c2.metric("Referencias con costo o precio anómalo", int(calidad["anomalia"].sum()))
    estrella = resumen_seg.sort_values("unidades_mediana").iloc[-1]
    c3.metric(f"Utilidad de '{estrella['perfil']}'", f"{estrella['pct_utilidad']:.1f} %",
              f"{int(estrella['referencias'])} referencias", delta_color="off")

    st.markdown("### Rentabilidad por familia y perfil")
    st.plotly_chart(an.figura_treemap(segmentacion), width="stretch")
    st.caption("Haga clic en una familia para ampliarla. Verde = margen alto, rojo = margen bajo.")

    st.markdown("### Detalle por referencia")
    familia_detalle = st.selectbox("Familia", list(an.CATEGORIAS), key="familia-detalle")
    st.plotly_chart(an.figura_top_referencias(segmentacion, familia_detalle), width="stretch")

    st.markdown("### Valor del stock por antigüedad de la última venta")
    rot_familia = an.resumen_rotacion(rotacion, ["categoria"])
    st.plotly_chart(
        px.bar(rot_familia, x="valor_stock", y="categoria", color="tramo_rotacion", orientation="h",
               category_orders={"tramo_rotacion": an.TRAMOS_ROTACION},
               color_discrete_sequence=["#2E7D32", "#9CCC65", "#FDD835", "#FB8C00", "#C62828"],
               labels={"valor_stock": "Valor del stock (COP)", "categoria": "", "tramo_rotacion": "Última venta"}),
        width="stretch",
    )
    lentas = rotacion[rotacion["tramo_rotacion"].isin(an.TRAMOS_ROTACION[3:]) & (rotacion["stock_positivo"] > 0)]
    st.dataframe(
        lentas.sort_values("valor_stock", ascending=False)[
            ["codigo", "descripcion", "categoria", "stock", "ultima_venta", "dias_sin_venta", "valor_stock", "tramo_rotacion"]
        ],
        width="stretch", hide_index=True,
    )

    st.markdown("### Control de calidad de costos y precios")
    diagnosticos = sorted(calidad.loc[calidad["anomalia"], "diagnostico"].unique())
    elegidos = st.multiselect("Diagnóstico", diagnosticos, default=diagnosticos)
    st.dataframe(
        calidad[calidad["diagnostico"].isin(elegidos)][
            ["codigo", "descripcion", "categoria", "diagnostico", "costo", "costo_compra_mediano",
             "precio_venta_mediano", "precio_lista", "stock", "evidencia"]
        ],
        width="stretch", hide_index=True,
    )

# ==========================================
# TRACK 3
# ==========================================
with tab3:
    plan, info = calcular_track3(inventario, ventas, compras)
    st.markdown(
        f"Demanda estimada para los **30 días siguientes al {info['fecha_corte']:%Y-%m-%d}**, con meses completos "
        f"hasta {info['ultimo_mes_completo']}. Modelo elegido por validación: **{info['modelo']}**."
    )
    with st.expander("Validación del pronóstico (abril–junio 2026)"):
        st.dataframe(info["validacion"], width="stretch", hide_index=True)
        st.caption("MAE: error medio en unidades por referencia y mes. WAPE: error total / unidades vendidas. "
                   "Sesgo positivo = tendencia a sobrestimar.")

    f1, f2, f3 = st.columns(3)
    categorias = f1.multiselect("Categoría", list(an.CATEGORIAS), default=list(an.CATEGORIAS))
    codigo = f2.text_input("Código de referencia", placeholder="Todo o parte del código").strip()
    estados = sorted(plan["estado_stock"].unique())
    estados_sel = f3.multiselect("Estado", estados, default=[e for e in estados if e != "Sin rotación: no comprar"])

    filtrado = plan[plan["categoria"].isin(categorias) & plan["estado_stock"].isin(estados_sel)]
    if codigo:
        filtrado = filtrado[filtrado["codigo"].str.contains(codigo, case=False, regex=False, na=False)]

    m1, m2, m3 = st.columns(3)
    m1.metric("Referencias", len(filtrado))
    m2.metric("Referencias a comprar", int((filtrado["unidades_a_comprar"] > 0).sum()))
    m3.metric("Unidades a comprar", int(filtrado["unidades_a_comprar"].sum()))

    columnas = ["codigo", "descripcion", "categoria", "stock", "demanda_pronosticada", "stock_seguridad",
                "unidades_a_comprar", "cobertura_meses", "estado_stock", "horizonte"]
    if filtrado.empty:
        st.info("No hay referencias que coincidan con los filtros.")
    else:
        st.dataframe(filtrado.sort_values("unidades_a_comprar", ascending=False)[columnas],
                     width="stretch", hide_index=True)
        st.download_button("📥 Descargar plan filtrado (CSV)",
                           filtrado[columnas].to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"plan_de_compras_{info['fecha_corte']:%Y%m%d}.csv", mime="text/csv")
        top = filtrado.nlargest(20, "unidades_a_comprar").sort_values("unidades_a_comprar")
        st.plotly_chart(
            px.bar(top, x="unidades_a_comprar", y="codigo", color="categoria", orientation="h",
                   hover_data=["descripcion", "stock", "demanda_pronosticada", "stock_seguridad"],
                   title="Referencias con mayor necesidad de compra"),
            width="stretch",
        )
    st.caption("El plan es una sugerencia para el jefe de compras: revise primero las referencias marcadas "
               "en el control de calidad (Track 2).")
