import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from sklearn.ensemble import RandomForestRegressor
from mlxtend.frequent_patterns import association_rules
from pathlib import Path
from io import BytesIO

# ==========================================
# CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Dashboard Autopartes | Proyecto-2",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main-header {
        font-size: 26px;
        font-weight: bold;
        color: #1E3A8A;
        margin-bottom: 20px;
    }
    .card-recommendation {
        background-color: #EFF6FF;
        border-left: 5px solid #2563EB;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 10px;
    }
    </style>
""", unsafe_allow_html=True)


# ==========================================
# CARGA Y PREPROCESAMIENTO SEGÚN PIPELINE EDA
# ==========================================
@st.cache_data
def load_and_process_pipeline_data(uploaded_inv=None, uploaded_sales=None):
    project_root = Path(__file__).resolve().parent
    processed_dir = project_root / 'data' / 'processed'
    inv_processed_path = processed_dir / 'INVENTARIO_PRODUCTOS_LIMPIO.csv'
    sales_processed_path = processed_dir / 'ventas_limpia.csv'
    
    # 1. Cargar Inventario
    if uploaded_inv is not None:
        df_inv = pd.read_csv(BytesIO(uploaded_inv.getvalue()))
    elif inv_processed_path.exists():
        df_inv = pd.read_csv(inv_processed_path)
    else:
        df_inv = pd.DataFrame()

    # 2. Cargar Ventas
    if uploaded_sales is not None:
        df_sales = pd.read_csv(BytesIO(uploaded_sales.getvalue()))
    elif sales_processed_path.exists():
        df_sales = pd.read_csv(sales_processed_path)
    else:
        df_sales = pd.DataFrame()

    if df_inv.empty or df_sales.empty:
        return df_inv, df_sales

    # Normalización de nombres de columnas a minúsculas
    df_inv.columns = [str(c).replace('\ufeff', '').lower().strip() for c in df_inv.columns]
    df_sales.columns = [str(c).replace('\ufeff', '').lower().strip() for c in df_sales.columns]

    # Tipificación de fechas en ventas
    if 'fecha' in df_sales.columns:
        df_sales['fecha'] = pd.to_datetime(df_sales['fecha'], errors='coerce')

    # Tratamiento financiero e inventario
    if 'costo_c(cop)' in df_inv.columns:
        df_inv['costo_c(cop)'] = pd.to_numeric(df_inv['costo_c(cop)'], errors='coerce').replace(0, np.nan).fillna(0.01)
    if 'precio_v(cop)' in df_inv.columns:
        df_inv['precio_v(cop)'] = pd.to_numeric(df_inv['precio_v(cop)'], errors='coerce').replace(0, np.nan).fillna(0.01)
    if 'stock' in df_inv.columns:
        df_inv['stock'] = pd.to_numeric(df_inv['stock'], errors='coerce').fillna(0)

    # Asegurar tipos string para códigos y facturas
    if 'factura' in df_sales.columns:
        df_sales['factura'] = df_sales['factura'].astype(str)
    if 'codigo' in df_sales.columns:
        df_sales['codigo'] = df_sales['codigo'].astype(str)
    if 'codigo' in df_inv.columns:
        df_inv['codigo'] = df_inv['codigo'].astype(str)

    return df_inv, df_sales


def build_track3_plan(df_inv, df_sales):
    """Reproduce el flujo de Track 3 y devuelve el plan para el siguiente mes."""
    categories = {'LLANTAS', 'BATERIAS', 'ACEITES', 'FILTROS'}
    required_sales = {'fecha', 'categoria', 'codigo', 'cantidad'}
    required_inventory = {'categoria', 'codigo', 'stock'}
    missing_sales = sorted(required_sales - set(df_sales.columns))
    missing_inventory = sorted(required_inventory - set(df_inv.columns))

    if missing_sales or missing_inventory:
        missing = []
        if missing_sales:
            missing.append(f"ventas: {', '.join(missing_sales)}")
        if missing_inventory:
            missing.append(f"inventario: {', '.join(missing_inventory)}")
        raise ValueError(f"Faltan columnas requeridas ({'; '.join(missing)}).")

    sales = df_sales.copy()
    inventory = df_inv.copy()
    sales['fecha'] = pd.to_datetime(sales['fecha'], errors='coerce')
    sales['codigo'] = sales['codigo'].astype('string').str.strip().str.replace(r'\.0$', '', regex=True)
    sales['categoria'] = sales['categoria'].astype('string').str.strip().str.upper()
    sales['cantidad'] = pd.to_numeric(sales['cantidad'], errors='coerce')
    inventory['codigo'] = inventory['codigo'].astype('string').str.strip().str.replace(r'\.0$', '', regex=True)
    inventory['categoria'] = inventory['categoria'].astype('string').str.strip().str.upper()
    inventory['stock'] = pd.to_numeric(inventory['stock'], errors='coerce')

    sales = sales.dropna(subset=['fecha', 'codigo', 'categoria', 'cantidad'])
    sales = sales[sales['categoria'].isin(categories)].copy()
    inventory = inventory.dropna(subset=['codigo', 'categoria'])
    inventory = inventory[inventory['categoria'].isin(categories)].copy()

    if sales.empty:
        raise ValueError("No hay ventas válidas en las cuatro categorías que analiza Track 3.")
    if inventory.empty:
        raise ValueError("No hay inventario válido en las cuatro categorías que analiza Track 3.")

    sales['periodo'] = sales['fecha'].dt.to_period('M').dt.to_timestamp()
    monthly_sales = (
        sales.groupby(['periodo', 'categoria', 'codigo'], as_index=False)['cantidad']
        .sum()
        .rename(columns={'cantidad': 'ventas'})
    )
    monthly_sales['compras'] = monthly_sales['ventas'] * 1.05
    monthly_sales = monthly_sales.sort_values(['categoria', 'codigo', 'periodo']).reset_index(drop=True)

    keys = ['categoria', 'codigo']
    feature_columns = [
        'ventas_lag_1', 'ventas_lag_2', 'ventas_lag_3',
        'compras_lag_1', 'compras_lag_2', 'compras_lag_3',
        'ventas_media_3m',
    ]
    history = monthly_sales.copy()
    grouped = history.groupby(keys, sort=False)
    for lag in [1, 2, 3]:
        history[f'ventas_lag_{lag}'] = grouped['ventas'].shift(lag)
        history[f'compras_lag_{lag}'] = grouped['compras'].shift(lag)
    history['ventas_media_3m'] = history.groupby(keys, sort=False)['ventas'].transform(
        lambda values: values.rolling(3).mean()
    )

    training = history.dropna(subset=feature_columns + ['ventas'])
    model = None
    if not training.empty:
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(training[feature_columns], training['ventas'])

    predictions = []
    for (category, code), product_history in history.groupby(keys, sort=False):
        latest = product_history.iloc[-1]
        if model is not None and latest[feature_columns].notna().all():
            forecast = float(model.predict(latest[feature_columns].to_frame().T)[0])
        else:
            forecast = float(product_history['ventas'].tail(3).mean())
        predictions.append({
            'categoria': category,
            'codigo': code,
            'demanda_pronosticada': max(0, int(np.ceil(forecast))),
        })

    forecast_df = pd.DataFrame(predictions)
    inventory = inventory.drop_duplicates(subset=keys, keep='first')
    plan = inventory.merge(forecast_df, on=keys, how='left')
    plan['demanda_pronosticada'] = plan['demanda_pronosticada'].fillna(0).astype(int)
    plan['stock'] = plan['stock'].fillna(0)
    plan['mes_proyeccion'] = (
        sales['fecha'].max().to_period('M').to_timestamp() + pd.DateOffset(months=1)
    ).strftime('%Y-%m')
    plan['stock_seguridad'] = np.ceil(plan['demanda_pronosticada'] * 0.20).astype(int)
    plan['unidades_a_comprar'] = np.maximum(
        0, plan['demanda_pronosticada'] + plan['stock_seguridad'] - plan['stock']
    ).round().astype(int)
    plan['estado_stock'] = np.where(plan['unidades_a_comprar'] > 0, 'Urgente / Déficit', 'Saludable')
    return plan, sales['fecha'].max(), plan['mes_proyeccion'].iloc[0]


# ==========================================
# BARRA LATERAL (SIDEBAR)
# ==========================================
st.sidebar.title("🗂️ Proyecto-2: Autopartes")
st.sidebar.markdown("---")
st.sidebar.markdown("### 📥 Carga Dinámica de Archivos")
uploaded_inv_file = st.sidebar.file_uploader("Inventario Limpio (`.csv`)", type=["csv"])
uploaded_sales_file = st.sidebar.file_uploader("Ventas Limpias (`.csv`)", type=["csv"])

df_inventario, df_ventas = load_and_process_pipeline_data(uploaded_inv_file, uploaded_sales_file)

st.sidebar.markdown("---")
st.sidebar.info("💡 Por defecto se usan los CSV de `data/processed/`. Sube un CSV limpio solo si quieres reemplazar esa fuente en esta sesión.")


# ==========================================
# DASHBOARD EN 2 PESTAÑAS PRINCIPALES
# ==========================================
st.title("🚗 Dashboard Integral: POS & Control de Inventario")

tab1, tab2 = st.tabs([
    "🛒 Track 1: Ventas Conjuntas (Market Basket - ECLAT)",
    "🚀 Track 3: Control de Inventario y Reabastecimiento"
])

# ==========================================
# PESTAÑA 1: MARKET BASKET ANALYSIS (TRACK 1)
# ==========================================
with tab1:
    st.markdown("<div class='main-header'>Cross-Selling POS: Reglas de Asociación 1 a 1</div>", unsafe_allow_html=True)
    st.markdown("Motor basado en minería transaccional (ECLAT / Apriori). Filtro estricto aplicado: **Confianza > 70%**.")

    rules_eclat_all = pd.DataFrame()
    categorias_analisis = {'FILTROS', 'ACEITES', 'LLANTAS', 'BATERIAS'}

    if not df_ventas.empty and not df_inventario.empty:
        # Se usa df_inventario en lugar de df_inv
        if 'codigo' in df_inventario.columns and 'categoria' in df_inventario.columns:
            inventario_categorias = df_inventario[['codigo', 'categoria']].rename(
                columns={'categoria': 'CATEGORIA_PRODUCTO'}
            ).copy()

            inventario_categorias['CATEGORIA_PRODUCTO'] = inventario_categorias['CATEGORIA_PRODUCTO'].astype(str).str.upper().replace(
                {'NAN': 'OTROS', 'NONE': 'OTROS', '<NA>': 'OTROS', '': 'OTROS'}
            ).fillna('OTROS')

            inventario_categorias = (
                inventario_categorias.groupby('codigo')['CATEGORIA_PRODUCTO']
                .agg(lambda cats: cats.iloc[0] if cats.nunique() == 1 else 'OTROS')
                .rename('CATEGORIA_PRODUCTO')
                .reset_index()
            )

            ventas_categoria = df_ventas.merge(
                inventario_categorias,
                on='codigo',
                how='left',
                validate='many_to_one'
            )
            ventas_categoria['CATEGORIA_PRODUCTO'] = ventas_categoria['CATEGORIA_PRODUCTO'].fillna('OTROS')
            ventas_filtered = ventas_categoria[ventas_categoria['CATEGORIA_PRODUCTO'].isin(categorias_analisis)].copy()

            if not ventas_filtered.empty and 'factura' in ventas_filtered.columns and 'cantidad' in ventas_filtered.columns:
                basket_raw = (ventas_filtered.groupby(['factura', 'CATEGORIA_PRODUCTO'])['cantidad']
                              .sum().unstack(fill_value=0))
                basket_sets = basket_raw.gt(0).astype(int)

                MIN_SUPP = 0.015
                MIN_CONF = 0.15  

                total_transacciones = len(basket_sets)
                if total_transacciones > 0 and not basket_sets.columns.empty:
                    tidsets = {
                        cat: set(np.flatnonzero(basket_sets[cat].to_numpy(dtype=bool)))
                        for cat in basket_sets.columns
                    }
                    itemsets_eclat = []

                    def minar_eclat(prefijo, candidatos, tidset_prefijo):
                        for indice, item in enumerate(candidatos):
                            tidset_item = tidset_prefijo & tidsets[item]
                            soporte = len(tidset_item) / total_transacciones
                            if soporte >= MIN_SUPP:
                                itemset = prefijo | {item}
                                itemsets_eclat.append({'support': soporte, 'itemsets': itemset})
                                minar_eclat(itemset, candidatos[indice + 1:], tidset_item)

                    minar_eclat(set(), list(basket_sets.columns), set(range(total_transacciones)))
                    freq_eclat = pd.DataFrame(itemsets_eclat, columns=['support', 'itemsets'])

                    if not freq_eclat.empty:
                        rules_raw = association_rules(freq_eclat, metric="confidence", min_threshold=MIN_CONF)
                        if not rules_raw.empty:
                            rules_eclat_all = rules_raw[
                                (rules_raw['antecedents'].apply(lambda x: len(x) == 1)) & 
                                (rules_raw['consequents'].apply(lambda x: len(x) == 1)) &
                                (rules_raw['confidence'] > 0.70)
                            ].sort_values(by=['lift', 'confidence'], ascending=[False, False])

    col_sel, col_res = st.columns([1, 2])

    with col_sel:
        st.markdown("### 🔍 Selector POS")
        categorias_disp = sorted(list(categorias_analisis))
        cat_elegida = st.selectbox("Seleccione la categoría que compra el cliente:", categorias_disp)
        
        st.markdown("---")
        st.metric("Total Categorías Analizadas", len(categorias_disp))
        st.metric("Reglas con Confianza > 70%", len(rules_eclat_all))

    with col_res:
        st.markdown(f"### Recomendaciones de Cross-Selling para: **{cat_elegida}**")

        if not rules_eclat_all.empty:
            filtered_rules = rules_eclat_all[rules_eclat_all['antecedents'].apply(lambda x: cat_elegida in list(x))]

            if not filtered_rules.empty:
                for idx, row in filtered_rules.iterrows():
                    consequents = ", ".join(list(row['consequents']))
                    conf_pct = round(row['confidence'] * 100, 2)
                    lift_val = round(row['lift'], 2)
                    supp_val = round(row['support'] * 100, 2)

                    st.markdown(f"""
                        <div class='card-recommendation'>
                            <h4>💡 Producto Sugerido: <strong>{consequents}</strong></h4>
                            <p><b>Porcentaje de Confianza:</b> {conf_pct}% | <b>Factor Lift:</b> {lift_val}x | <b>Soporte:</b> {supp_val}%</p>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                st.info(f"No se encontraron reglas con confianza mayor al 70% para **{cat_elegida}**.")
        else:
            st.warning("No hay reglas de asociación que superen el umbral estricto del 70% de confianza con los datos actuales.")

    if not df_ventas.empty and 'fecha' in df_ventas.columns:
        st.markdown("---")
        st.markdown("### 📊 Volumen de Transacciones por Categoría")
        if 'ventas_filtered' in locals() and not ventas_filtered.empty:
            counts = ventas_filtered['CATEGORIA_PRODUCTO'].value_counts().reset_index()
            counts.columns = ['CATEGORIA', 'TRANSACCIONES']
            fig = px.bar(counts, x='CATEGORIA', y='TRANSACCIONES', color='CATEGORIA', text_auto=True)
            st.plotly_chart(fig, width='stretch')


# ==========================================
# PESTAÑA 2: CONTROL DE INVENTARIO Y REABASTECIMIENTO (TRACK 3)
# ==========================================
with tab2:
    st.markdown("<div class='main-header'>Control de Inventario y Plan de Reabastecimiento (Track 3)</div>", unsafe_allow_html=True)
    st.markdown(
        "Se calcula la proyección por **categoría y referencia**, siguiendo el flujo de "
        "`notebooks/Track3.ipynb`. Por defecto se usan los datos limpios del proyecto; "
        "puedes reemplazarlos temporalmente con los CSV de la barra lateral."
    )

    if df_ventas.empty or df_inventario.empty:
        st.warning(
            "No se encontraron datos de ventas o inventario. Verifica los CSV en "
            "`data/processed/` o carga las versiones actualizadas en la barra lateral."
        )
    else:
        try:
            df_plan, max_date, projected_month = build_track3_plan(df_inventario, df_ventas)
        except ValueError as error:
            st.error(f"No se pudo generar el plan de Track 3: {error}")
        else:
            st.markdown(
                f"🗓️ **Mes histórico final:** `{max_date:%Y-%m}` | "
                f"🚀 **Mes proyectado:** `{projected_month}`"
            )

            st.markdown("### 🔎 Filtros del plan")
            filter_category, filter_code, filter_status = st.columns(3)
            with filter_category:
                selected_categories = st.multiselect(
                    "Categoría",
                    options=sorted(df_plan['categoria'].dropna().unique().tolist()),
                    default=sorted(df_plan['categoria'].dropna().unique().tolist()),
                    key="track3-category-filter",
                )
            with filter_code:
                code_query = st.text_input(
                    "Código de referencia",
                    placeholder="Escribe todo o parte del código",
                    key="track3-code-filter",
                ).strip()
            with filter_status:
                selected_statuses = st.multiselect(
                    "Estado del stock",
                    options=sorted(df_plan['estado_stock'].dropna().unique().tolist()),
                    default=sorted(df_plan['estado_stock'].dropna().unique().tolist()),
                    key="track3-status-filter",
                )

            filtered_plan = df_plan[
                df_plan['categoria'].isin(selected_categories)
                & df_plan['estado_stock'].isin(selected_statuses)
            ].copy()
            if code_query:
                filtered_plan = filtered_plan[
                    filtered_plan['codigo'].astype(str).str.contains(
                        code_query, case=False, regex=False, na=False
                    )
                ]

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Referencias evaluadas", len(filtered_plan))
            c2.metric("Referencias que requieren compra", int((filtered_plan['unidades_a_comprar'] > 0).sum()))
            c3.metric("Unidades a reabastecer", int(filtered_plan['unidades_a_comprar'].sum()))
            c4.metric("Stock total", int(filtered_plan['stock'].sum()))

            st.markdown("---")
            st.markdown("### 📋 Plan de reabastecimiento")
            display_cols = [
                column for column in [
                    'mes_proyeccion', 'categoria', 'codigo', 'descripcion', 'stock',
                    'demanda_pronosticada', 'stock_seguridad', 'unidades_a_comprar',
                    'estado_stock',
                ]
                if column in df_plan.columns
            ]

            if filtered_plan.empty:
                st.info("No hay referencias que coincidan con los filtros seleccionados.")
            else:
                def highlight_stock(value):
                    color = '#FFD2D2' if value == 'Urgente / Déficit' else '#D4EDDA'
                    text_color = '#900C3F' if value == 'Urgente / Déficit' else '#155724'
                    return f'background-color: {color}; color: {text_color}; font-weight: bold;'

                styled_df = filtered_plan[display_cols].style.map(
                    highlight_stock, subset=['estado_stock']
                )
                st.dataframe(styled_df, width='stretch')

                csv_data = filtered_plan[display_cols].to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 Descargar plan filtrado (CSV)",
                    data=csv_data,
                    file_name=f"plan_de_compras_{projected_month}.csv",
                    mime="text/csv",
                    key="download-csv-track3",
                )

            st.markdown("---")
            st.markdown("### 📊 Demanda pronosticada y unidades a comprar")
            if filtered_plan.empty:
                st.info("No hay datos para mostrar con los filtros seleccionados.")
            else:
                chart_data = (
                    filtered_plan.nlargest(20, 'unidades_a_comprar')
                    .sort_values('unidades_a_comprar', ascending=True)
                )
                fig_plan = px.bar(
                    chart_data,
                    x='unidades_a_comprar',
                    y='codigo',
                    color='categoria',
                    orientation='h',
                    hover_data=['stock', 'demanda_pronosticada', 'stock_seguridad'],
                    labels={
                        'codigo': 'Referencia',
                        'unidades_a_comprar': 'Unidades a comprar',
                        'categoria': 'Categoría',
                    },
                    title='Referencias con mayor necesidad de reabastecimiento',
                )
                st.plotly_chart(fig_plan, width='stretch')