"""Funciones de análisis compartidas por los notebooks y por ``app.py``.

El módulo concentra la carga de datos y los cálculos de los tres tracks para que
los notebooks y el dashboard produzcan exactamente los mismos resultados.

Nombres internos de columnas:

* Inventario: ``codigo``, ``descripcion``, ``costo``, ``precio_lista``,
  ``stock``, ``categoria``.
* Ventas: ``factura``, ``fecha``, ``codigo``, ``descripcion``, ``cantidad``,
  ``precio_unitario``, ``subtotal``, ``categoria`` (más columnas de IVA).
* Compras: ``fecha``, ``codigo``, ``cantidad``, ``costo_unitario``,
  ``proveedor``.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

CATEGORIAS = ("ACEITES", "BATERIAS", "FILTROS", "LLANTAS")

# Umbral para considerar un costo fuera del rango histórico de compras
# (más de 3 veces o menos de un tercio del costo mediano de compra).
UMBRAL_COSTO = 3.0

TRAMOS_ROTACION = [
    "Vendida en los últimos 30 días",
    "Sin venta 31–90 días",
    "Sin venta 91–180 días",
    "Sin venta más de 180 días",
    "Sin ventas en todo el periodo",
]


# ==============================================================================
# CARGA Y PREPARACIÓN
# ==============================================================================
def raiz_proyecto(inicio: Path | str | None = None) -> Path:
    """Devuelve la carpeta del proyecto (la que contiene ``data/processed``)."""
    raiz = Path(inicio or Path.cwd()).resolve()
    while not (raiz / "data" / "processed").is_dir():
        if raiz.parent == raiz:
            raise FileNotFoundError("No se encontró la carpeta data/processed del proyecto.")
        raiz = raiz.parent
    return raiz


def _normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).replace("﻿", "").strip().lower() for c in df.columns]
    return df


def _codigo(serie: pd.Series) -> pd.Series:
    return serie.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)


def _exigir(df: pd.DataFrame, columnas: set[str], nombre: str) -> None:
    faltantes = sorted(columnas - set(df.columns))
    if faltantes:
        raise ValueError(f"Faltan columnas en {nombre}: {', '.join(faltantes)}")


def preparar_inventario(df: pd.DataFrame) -> pd.DataFrame:
    inv = _normalizar_columnas(df).rename(
        columns={"costo_c(cop)": "costo", "precio_v(cop)": "precio_lista"}
    )
    _exigir(inv, {"codigo", "descripcion", "costo", "precio_lista", "stock", "categoria"}, "inventario")
    inv["codigo"] = _codigo(inv["codigo"])
    inv["descripcion"] = inv["descripcion"].astype("string").str.strip()
    inv["categoria"] = inv["categoria"].astype("string").str.strip().str.upper()
    for col in ["costo", "precio_lista", "stock"]:
        inv[col] = pd.to_numeric(inv[col], errors="coerce").fillna(0)
    return inv.dropna(subset=["codigo"]).reset_index(drop=True)


def preparar_ventas(df: pd.DataFrame) -> pd.DataFrame:
    ventas = _normalizar_columnas(df).rename(columns={"codigo_producto": "codigo", "porcentaje_iva": "iva"})
    _exigir(ventas, {"factura", "fecha", "codigo", "cantidad", "precio_unitario", "subtotal", "categoria"}, "ventas")
    ventas["factura"] = _codigo(ventas["factura"])
    ventas["codigo"] = _codigo(ventas["codigo"])
    ventas["fecha"] = pd.to_datetime(ventas["fecha"], errors="coerce")
    ventas["categoria"] = ventas["categoria"].astype("string").str.strip().str.upper()
    for col in ["cantidad", "precio_unitario", "subtotal"]:
        ventas[col] = pd.to_numeric(ventas[col], errors="coerce")
    return ventas.dropna(subset=["factura", "fecha", "codigo", "cantidad"]).reset_index(drop=True)


def preparar_compras(df: pd.DataFrame) -> pd.DataFrame:
    """Acepta el extracto original (FECHA, REFE, KAR_ENT, KAR_PRE...) o la versión renombrada."""
    compras = _normalizar_columnas(df).rename(
        columns={
            "refe": "codigo",
            "kar_ent": "cantidad",
            "cantidad_comprada": "cantidad",
            "kar_pre": "costo_unitario",
            "nombre": "proveedor",
            "nom_proveedor": "proveedor",
        }
    )
    _exigir(compras, {"fecha", "codigo", "cantidad", "costo_unitario"}, "compras")
    # Las filas idénticas se eliminan con el mismo criterio aplicado a las ventas.
    compras = compras.drop_duplicates()
    compras["codigo"] = _codigo(compras["codigo"])
    compras["fecha"] = pd.to_datetime(compras["fecha"], errors="coerce").dt.normalize()
    for col in ["cantidad", "costo_unitario"]:
        compras[col] = pd.to_numeric(compras[col], errors="coerce")
    compras = compras.dropna(subset=["fecha", "codigo", "cantidad", "costo_unitario"])
    compras = compras[(compras["cantidad"] > 0) & (compras["costo_unitario"] > 0)]
    columnas = ["fecha", "codigo", "cantidad", "costo_unitario"] + (["proveedor"] if "proveedor" in compras else [])
    return compras[columnas].reset_index(drop=True)


def cargar_datos(raiz: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Carga inventario, ventas y compras desde ``data/processed``."""
    carpeta = raiz_proyecto(raiz) / "data" / "processed"
    inventario = preparar_inventario(pd.read_csv(carpeta / "INVENTARIO_PRODUCTOS_LIMPIO.csv"))
    ventas = preparar_ventas(pd.read_csv(carpeta / "ventas_limpia.csv"))
    compras = preparar_compras(pd.read_csv(carpeta / "DS_COMPRAS.csv"))
    return inventario, ventas, compras


def inventario_por_referencia(inventario: pd.DataFrame) -> pd.DataFrame:
    """Inventario de las 4 familias con un registro por código.

    Los códigos repetidos con datos distintos se excluyen aquí y se reportan en
    el control de calidad.
    """
    inv = inventario[inventario["categoria"].isin(CATEGORIAS)]
    return inv[~inv["codigo"].duplicated(keep=False)].copy()


# ==============================================================================
# TRACK 1: REGLAS DE ASOCIACIÓN ENTRE FAMILIAS
# ==============================================================================
def canasta_por_factura(ventas: pd.DataFrame, inventario: pd.DataFrame) -> pd.DataFrame:
    """Matriz booleana factura x familia sobre **todas** las facturas.

    Las facturas sin ninguna de las 4 familias se conservan como filas vacías:
    así el soporte y el lift se calculan sobre el total real de transacciones.
    """
    familias = inventario_por_referencia(inventario).set_index("codigo")["categoria"]
    lineas = ventas[["factura", "codigo"]].copy()
    lineas["familia"] = lineas["codigo"].map(familias)
    lineas = lineas.dropna(subset=["familia"])
    todas = pd.Index(ventas["factura"].unique(), name="factura")
    canasta = pd.crosstab(lineas["factura"], lineas["familia"]).gt(0)
    return canasta.reindex(index=todas, columns=list(CATEGORIAS), fill_value=False)


def eclat(canasta: pd.DataFrame, min_support: float) -> pd.DataFrame:
    """ECLAT: búsqueda en profundidad intersectando los conjuntos de facturas."""
    total = len(canasta)
    tidsets = {col: set(np.flatnonzero(canasta[col].to_numpy(dtype=bool))) for col in canasta.columns}
    encontrados = []

    def minar(prefijo: frozenset, candidatos: list, tidset_prefijo: set | None) -> None:
        for i, item in enumerate(candidatos):
            tidset = tidsets[item] if tidset_prefijo is None else tidset_prefijo & tidsets[item]
            soporte = len(tidset) / total
            if soporte >= min_support:
                itemset = prefijo | {item}
                encontrados.append({"support": soporte, "itemsets": itemset})
                minar(itemset, candidatos[i + 1 :], tidset)

    minar(frozenset(), list(canasta.columns), None)
    return pd.DataFrame(encontrados, columns=["support", "itemsets"])


def _reglas_1a1(frecuentes: pd.DataFrame) -> pd.DataFrame:
    from mlxtend.frequent_patterns import association_rules

    columnas = ["antecedente", "consecuente", "support", "confidence", "lift"]
    if frecuentes.empty:
        return pd.DataFrame(columns=columnas)
    reglas = association_rules(frecuentes, metric="confidence", min_threshold=0.0)
    reglas = reglas[(reglas["antecedents"].apply(len) == 1) & (reglas["consequents"].apply(len) == 1)].copy()
    reglas["antecedente"] = reglas["antecedents"].apply(lambda s: next(iter(s)))
    reglas["consecuente"] = reglas["consequents"].apply(lambda s: next(iter(s)))
    return (
        reglas[columnas]
        .sort_values(["lift", "confidence"], ascending=False)
        .reset_index(drop=True)
    )


def clasificar_regla(confianza: float, lift: float) -> str:
    if lift >= 2 and confianza >= 0.5:
        return "Fuerte"
    if lift > 1:
        return "Débil"
    return "Sin asociación"


def reglas_asociacion(canasta: pd.DataFrame, min_support: float = 0.001) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ejecuta Apriori, FP-Growth y ECLAT; devuelve (reglas ECLAT, comparación)."""
    from mlxtend.frequent_patterns import apriori, fpgrowth

    algoritmos = {
        "Apriori": lambda: apriori(canasta, min_support=min_support, use_colnames=True),
        "FP-Growth": lambda: fpgrowth(canasta, min_support=min_support, use_colnames=True),
        "ECLAT": lambda: eclat(canasta, min_support),
    }
    resultados, comparacion = {}, []
    for nombre, minar in algoritmos.items():
        inicio = time.perf_counter()
        reglas = _reglas_1a1(minar())
        segundos = time.perf_counter() - inicio
        resultados[nombre] = reglas
        comparacion.append({"algoritmo": nombre, "segundos": segundos, "reglas": len(reglas),
                            "lift_max": reglas["lift"].max() if len(reglas) else np.nan})
    reglas = resultados["ECLAT"].copy()
    reglas["fuerza"] = [clasificar_regla(c, l) for c, l in zip(reglas["confidence"], reglas["lift"])]
    comparacion = pd.DataFrame(comparacion)
    clave = lambda r: r.round(10).sort_values(["antecedente", "consecuente"]).reset_index(drop=True)
    comparacion["mismas_reglas_que_eclat"] = [clave(resultados[n]).equals(clave(resultados["ECLAT"])) for n in algoritmos]
    return reglas, comparacion


# ==============================================================================
# TRACK 2: CALIDAD DE COSTOS, RENTABILIDAD Y ROTACIÓN
# ==============================================================================
def control_calidad_costos(inventario: pd.DataFrame, ventas: pd.DataFrame, compras: pd.DataFrame,
                           umbral: float = UMBRAL_COSTO) -> pd.DataFrame:
    """Diagnostica costos y precios sospechosos por referencia.

    Contrasta el costo del inventario con tres fuentes independientes: el precio
    de lista, el precio real de venta y el historial de costos de compra.
    """
    inv = inventario[inventario["categoria"].isin(CATEGORIAS)].copy()
    inv["codigo_duplicado"] = inv["codigo"].duplicated(keep=False)
    inv = inv.drop_duplicates("codigo", keep="first").set_index("codigo")

    lineas = ventas.merge(inv[["costo"]], left_on="codigo", right_index=True, how="inner")
    lineas["bajo_costo"] = (lineas["costo"] > 0) & (lineas["precio_unitario"] < lineas["costo"])
    v = lineas.groupby("codigo").agg(
        lineas_venta=("cantidad", "size"),
        precio_venta_mediano=("precio_unitario", "median"),
        lineas_bajo_costo=("bajo_costo", "sum"),
    )

    cp = compras.sort_values("fecha").groupby("codigo")["costo_unitario"]
    c = pd.DataFrame({
        "compras_registradas": cp.size(),
        "costo_compra_mediano": cp.median(),
        "costo_compra_max": cp.max(),
        "costo_ultima_compra": cp.last(),
        "costo_compra_reciente": cp.apply(lambda s: s.tail(3).median()),
    })

    df = inv[["descripcion", "categoria", "costo", "precio_lista", "stock", "codigo_duplicado"]].join(v).join(c)
    df[["lineas_venta", "lineas_bajo_costo", "compras_registradas"]] = (
        df[["lineas_venta", "lineas_bajo_costo", "compras_registradas"]].fillna(0).astype(int)
    )
    df["margen_lista_pct"] = np.where(df["precio_lista"] > 0,
                                      (df["precio_lista"] - df["costo"]) / df["precio_lista"] * 100, np.nan)
    df["ratio_costo_vs_compras"] = df["costo"] / df["costo_compra_mediano"]
    df["compra_atipica_registrada"] = df["costo_compra_max"] > umbral * df["costo_compra_mediano"]

    fuera_rango_compras = (df["ratio_costo_vs_compras"] > umbral) | (df["ratio_costo_vs_compras"] < 1 / umbral)
    sin_compras_y_muy_alto = (df["compras_registradas"] == 0) & (df["costo"] > umbral * df["precio_venta_mediano"])
    costo_supera_venta = df["costo"] > df["precio_venta_mediano"]
    costo_supera_lista = (df["precio_lista"] > 0) & (df["costo"] > df["precio_lista"])
    compras_recientes_suben = df["costo_compra_reciente"] > 1.3 * df["costo_compra_mediano"]

    condiciones = [
        df["codigo_duplicado"],
        df["costo"] <= 0,
        fuera_rango_compras,
        sin_compras_y_muy_alto,
        costo_supera_venta & compras_recientes_suben,
        costo_supera_lista & (df["precio_venta_mediano"] > df["costo"]),
        df["precio_lista"] <= 0,
        costo_supera_lista | costo_supera_venta,
    ]
    diagnosticos = [
        "Código duplicado con datos distintos",
        "Costo faltante",
        "Probable error de digitación del costo",
        "Probable error de digitación (costo o precio de venta)",
        "Probable cambio de costo no trasladado al precio",
        "Precio de lista desactualizado",
        "Precio de lista faltante",
        "Margen negativo sin causa identificada",
    ]
    df["diagnostico"] = np.select(condiciones, diagnosticos, default="Sin anomalía")
    df["anomalia"] = df["diagnostico"] != "Sin anomalía"

    def _fmt(x):
        return "—" if pd.isna(x) else f"{x:,.0f}"

    evidencias = []
    for _, fila in df.iterrows():
        partes = []
        if fila["anomalia"]:
            partes.append(f"costo inventario {_fmt(fila['costo'])}")
            if fila["compras_registradas"]:
                partes.append(f"costo mediano de compra {_fmt(fila['costo_compra_mediano'])} "
                              f"({fila['compras_registradas']} compras)")
            else:
                partes.append("sin compras registradas")
            partes.append(f"precio de venta mediano {_fmt(fila['precio_venta_mediano'])}")
            partes.append(f"precio de lista {_fmt(fila['precio_lista'])}")
            if fila["compra_atipica_registrada"]:
                partes.append(f"hay una compra registrada a {_fmt(fila['costo_compra_max'])}")
        evidencias.append("; ".join(partes))
    df["evidencia"] = evidencias
    # Costo de referencia: si el costo del inventario está fuera del rango de las
    # compras, se reemplaza por el costo mediano de compra.
    corregible = df["diagnostico"] == "Probable error de digitación del costo"
    df["costo_referencia"] = np.where(corregible, df["costo_compra_mediano"], df["costo"])
    df["costo_confiable"] = ~df["diagnostico"].isin([
        "Código duplicado con datos distintos",
        "Costo faltante",
        "Probable error de digitación (costo o precio de venta)",
    ])
    return df.reset_index()


def rentabilidad_por_referencia(ventas: pd.DataFrame, calidad: pd.DataFrame) -> pd.DataFrame:
    """Margen realizado (precio real de venta frente al costo de referencia)."""
    base = calidad.set_index("codigo")
    lineas = ventas[ventas["codigo"].isin(base.index)].copy()
    lineas["costo_total"] = lineas["cantidad"] * lineas["codigo"].map(base["costo_referencia"])
    r = lineas.groupby("codigo").agg(
        unidades=("cantidad", "sum"),
        ingresos=("subtotal", "sum"),
        costo_ventas=("costo_total", "sum"),
        facturas=("factura", "nunique"),
    )
    r["utilidad_bruta"] = r["ingresos"] - r["costo_ventas"]
    r["margen_real_pct"] = np.where(r["ingresos"] > 0, r["utilidad_bruta"] / r["ingresos"] * 100, np.nan)
    return base[["descripcion", "categoria", "stock", "costo_referencia", "costo_confiable",
                 "diagnostico", "margen_lista_pct"]].join(r, how="inner").reset_index()


def rotacion_inventario(inventario: pd.DataFrame, ventas: pd.DataFrame, calidad: pd.DataFrame,
                        fecha_corte: pd.Timestamp | None = None) -> pd.DataFrame:
    """Antigüedad de la última venta y valor del stock inmovilizado por referencia."""
    corte = pd.Timestamp(fecha_corte) if fecha_corte is not None else ventas["fecha"].max()
    base = calidad.set_index("codigo")[["descripcion", "categoria", "stock", "costo_referencia", "costo_confiable"]]
    ultima = ventas[ventas["fecha"] <= corte].groupby("codigo")["fecha"].max()
    ult_12m = ventas[ventas["fecha"] > corte - pd.DateOffset(months=12)].groupby("codigo")["cantidad"].sum()
    df = base.join(ultima.rename("ultima_venta")).join(ult_12m.rename("unidades_ult_12m"))
    df["dias_sin_venta"] = (corte - df["ultima_venta"]).dt.days
    df["unidades_ult_12m"] = df["unidades_ult_12m"].fillna(0)
    df["stock_positivo"] = df["stock"].clip(lower=0)
    df["valor_stock"] = df["stock_positivo"] * df["costo_referencia"]
    df["tramo_rotacion"] = np.select(
        [df["ultima_venta"].isna(), df["dias_sin_venta"] > 180, df["dias_sin_venta"] > 90, df["dias_sin_venta"] > 30],
        TRAMOS_ROTACION[::-1][:4],
        default=TRAMOS_ROTACION[0],
    )
    df["tramo_rotacion"] = pd.Categorical(df["tramo_rotacion"], categories=TRAMOS_ROTACION, ordered=True)
    df["fecha_corte"] = corte
    return df.reset_index()


def resumen_rotacion(rotacion: pd.DataFrame, por: list[str] | None = None) -> pd.DataFrame:
    """Valor y unidades en stock por tramo de rotación (solo costos confiables)."""
    datos = rotacion[rotacion["costo_confiable"] & (rotacion["stock_positivo"] > 0)]
    claves = (por or []) + ["tramo_rotacion"]
    r = datos.groupby(claves, observed=False).agg(
        referencias=("codigo", "size"), unidades=("stock_positivo", "sum"), valor_stock=("valor_stock", "sum")
    ).reset_index()
    total = r.groupby(por)["valor_stock"].transform("sum") if por else r["valor_stock"].sum()
    r["pct_valor"] = r["valor_stock"] / total * 100
    return r


def segmentar_referencias(rentabilidad: pd.DataFrame, k_opciones=range(2, 7), random_state: int = 42):
    """K-Means sobre log(unidades) y margen realizado.

    Se excluyen las referencias con costo no confiable y los márgenes fuera de
    [-100 %, 100 %] para que los errores de datos no definan los grupos.
    Devuelve (referencias con perfil, tabla de silhouette por k, resumen por clúster).
    """
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    df = rentabilidad.copy()
    valida = df["costo_confiable"] & df["margen_real_pct"].between(-100, 100) & (df["unidades"] > 0)
    modelo = df[valida].copy()
    X = StandardScaler().fit_transform(np.c_[np.log1p(modelo["unidades"]), modelo["margen_real_pct"]])

    evaluacion = []
    for k in k_opciones:
        km = KMeans(n_clusters=k, random_state=random_state, n_init=10).fit(X)
        evaluacion.append({"k": k, "silhouette": silhouette_score(X, km.labels_), "inercia": km.inertia_})
    evaluacion = pd.DataFrame(evaluacion)
    k_elegido = int(evaluacion.loc[evaluacion["silhouette"].idxmax(), "k"])
    km = KMeans(n_clusters=k_elegido, random_state=random_state, n_init=10).fit(X)
    modelo["cluster"] = km.labels_

    # Etiquetas según la posición del centroide (variables estandarizadas):
    # por encima de 0 = por encima del promedio de las referencias.
    resumen = modelo.groupby("cluster").agg(
        referencias=("codigo", "size"),
        unidades_mediana=("unidades", "median"),
        margen_mediano=("margen_real_pct", "median"),
        ingresos=("ingresos", "sum"),
        utilidad_bruta=("utilidad_bruta", "sum"),
    )
    centros = km.cluster_centers_
    resumen["perfil"] = [
        f"{'Alta' if centros[i, 0] > 0 else 'Baja'} rotación / margen {'alto' if centros[i, 1] > 0 else 'bajo'}"
        for i in resumen.index
    ]
    # Si dos clústeres caen en el mismo cuadrante, se numeran para distinguirlos.
    repetidos = resumen["perfil"].duplicated(keep=False)
    resumen.loc[repetidos, "perfil"] += " (" + (resumen[repetidos].groupby("perfil").cumcount() + 1).astype(str) + ")"
    modelo["perfil"] = modelo["cluster"].map(resumen["perfil"])

    df["perfil"] = df["codigo"].map(modelo.set_index("codigo")["perfil"])
    df.loc[~valida, "perfil"] = "Excluida: dato de costo o margen anómalo"
    resumen["pct_ingresos"] = resumen["ingresos"] / resumen["ingresos"].sum() * 100
    resumen["pct_utilidad"] = resumen["utilidad_bruta"] / resumen["utilidad_bruta"].sum() * 100
    return df, evaluacion, resumen.reset_index()


def resumen_familia_perfil(rentabilidad_perfil: pd.DataFrame) -> pd.DataFrame:
    """Ingresos, utilidad y margen por familia y perfil (sin referencias excluidas)."""
    datos = rentabilidad_perfil[~rentabilidad_perfil["perfil"].str.startswith("Excluida")]
    r = datos.groupby(["categoria", "perfil"]).agg(
        referencias=("codigo", "size"), ingresos=("ingresos", "sum"), utilidad_bruta=("utilidad_bruta", "sum")
    ).reset_index()
    r["margen_pct"] = r["utilidad_bruta"] / r["ingresos"] * 100
    r["pct_ingresos_total"] = r["ingresos"] / r["ingresos"].sum() * 100
    return r


def figura_treemap(rentabilidad_perfil: pd.DataFrame):
    """Árbol de dos niveles: familia → perfil. Tamaño = ingresos; color = margen real.

    Se muestran solo dos niveles para que la vista sea legible; el detalle por
    referencia está en ``figura_top_referencias``.
    """
    import plotly.graph_objects as go

    r = resumen_familia_perfil(rentabilidad_perfil)
    fam = r.groupby("categoria").agg(
        referencias=("referencias", "sum"), ingresos=("ingresos", "sum"), utilidad_bruta=("utilidad_bruta", "sum")
    ).reset_index()
    fam["margen_pct"] = fam["utilidad_bruta"] / fam["ingresos"] * 100
    fam["pct_ingresos_total"] = fam["ingresos"] / fam["ingresos"].sum() * 100

    ids = list(fam["categoria"]) + list(r["categoria"] + "/" + r["perfil"])
    etiquetas = list(fam["categoria"]) + list(r["perfil"].str.replace(" / ", "<br>"))
    padres = [""] * len(fam) + list(r["categoria"])
    valores = list(fam["ingresos"]) + list(r["ingresos"])
    margenes = list(fam["margen_pct"]) + list(r["margen_pct"])
    pct = list(fam["pct_ingresos_total"]) + list(r["pct_ingresos_total"])
    refs = list(fam["referencias"]) + list(r["referencias"])

    fig = go.Figure(go.Treemap(
        ids=ids, labels=etiquetas, parents=padres, values=valores, branchvalues="total",
        customdata=np.c_[pct, margenes, refs],
        texttemplate="<b>%{label}</b><br>%{customdata[0]:.0f} % de los ingresos<br>margen %{customdata[1]:.0f} %",
        hovertemplate="<b>%{label}</b><br>Ingresos: %{value:,.0f} COP<br>Margen real: %{customdata[1]:.1f} %"
                      "<br>Referencias: %{customdata[2]:.0f}<extra></extra>",
        marker=dict(colors=margenes, colorscale="RdYlGn", cmin=15, cmax=60,
                    colorbar=dict(title="Margen<br>real %")),
        textfont=dict(size=14),
        maxdepth=2,
    ))
    fig.update_layout(
        title="Rentabilidad por familia y perfil (tamaño = ingresos, color = margen real)",
        margin=dict(t=50, l=10, r=10, b=10), height=520,
    )
    return fig


def figura_top_referencias(rentabilidad_perfil: pd.DataFrame, familia: str, n: int = 10):
    """Barras con las ``n`` referencias de una familia que más utilidad bruta generan."""
    import plotly.express as px

    datos = rentabilidad_perfil[(rentabilidad_perfil["categoria"] == familia)
                                & ~rentabilidad_perfil["perfil"].str.startswith("Excluida")]
    top = datos.nlargest(n, "utilidad_bruta").sort_values("utilidad_bruta")
    top = top.assign(referencia=top["codigo"] + " · " + top["descripcion"].str.slice(0, 35))
    fig = px.bar(
        top, x="utilidad_bruta", y="referencia", color="perfil", orientation="h",
        text=top["margen_real_pct"].map(lambda m: f"margen {m:.0f} %"),
        hover_data={"unidades": ":,.0f", "ingresos": ":,.0f", "referencia": False},
        labels={"utilidad_bruta": "Utilidad bruta (COP)", "referencia": "", "perfil": "Perfil"},
        title=f"{familia}: las {len(top)} referencias con más utilidad bruta",
        color_discrete_map={
            "Alta rotación / margen alto": "#2E7D32",
            "Baja rotación / margen alto": "#F9A825",
            "Baja rotación / margen bajo": "#C62828",
        },
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(margin=dict(t=50, l=10, r=40, b=10), height=420, legend=dict(orientation="h", y=-0.15))
    return fig


# ==============================================================================
# TRACK 3: PRONÓSTICO DE DEMANDA Y REABASTECIMIENTO
# ==============================================================================
VARIABLES_VENTAS = ["ventas_lag_1", "ventas_lag_2", "ventas_lag_3", "ventas_media_3m", "ventas_media_6m", "mes"]
VARIABLES_COMPRAS = ["compras_lag_1", "compras_lag_2", "compras_lag_3"]
MODELOS = {
    "Último mes": None,
    "Promedio móvil 3 meses": None,
    "Promedio móvil 6 meses": None,
    "Random Forest (ventas)": VARIABLES_VENTAS,
    "Random Forest (ventas + compras reales)": VARIABLES_VENTAS + VARIABLES_COMPRAS,
}


def ultimo_mes_completo(ventas: pd.DataFrame) -> pd.Period:
    """Último mes con datos completos: un mes que termina antes del día 28 se descarta."""
    fecha_max = ventas["fecha"].max()
    mes = fecha_max.to_period("M")
    return mes if fecha_max.day >= 28 else mes - 1


def panel_mensual(ventas: pd.DataFrame, compras: pd.DataFrame, referencias, ultimo_mes: pd.Period) -> pd.DataFrame:
    """Ventas y compras mensuales por referencia, con 0 en los meses sin movimiento.

    Incluye una fila adicional por referencia para el mes a pronosticar
    (``ultimo_mes + 1``) con las ventas vacías.
    """
    referencias = pd.Index(pd.unique(pd.Series(list(referencias), dtype="string")), name="codigo")
    meses = pd.period_range(ventas["fecha"].min().to_period("M"), ultimo_mes + 1, freq="M")

    def mensual(df, nombre):
        d = df[df["codigo"].isin(referencias)]
        return d.groupby(["codigo", d["fecha"].dt.to_period("M").rename("periodo")])["cantidad"].sum().rename(nombre)

    indice = pd.MultiIndex.from_product([referencias, meses], names=["codigo", "periodo"])
    panel = pd.DataFrame(index=indice).join(mensual(ventas, "ventas")).join(mensual(compras, "compras"))
    panel = panel.fillna(0).reset_index()
    futuro = panel["periodo"] == ultimo_mes + 1
    panel.loc[futuro, ["ventas", "compras"]] = np.nan
    return panel.sort_values(["codigo", "periodo"]).reset_index(drop=True)


def agregar_variables(panel: pd.DataFrame) -> pd.DataFrame:
    """Variables con información disponible antes de cada mes (sin fuga de datos)."""
    df = panel.copy()
    g = df.groupby("codigo", sort=False)
    for lag in (1, 2, 3):
        df[f"ventas_lag_{lag}"] = g["ventas"].shift(lag)
        df[f"compras_lag_{lag}"] = g["compras"].shift(lag)
    previas = g["ventas"].shift(1)
    df["ventas_media_3m"] = previas.groupby(df["codigo"]).transform(lambda s: s.rolling(3).mean())
    df["ventas_media_6m"] = previas.groupby(df["codigo"]).transform(lambda s: s.rolling(6).mean())
    df["ventas_std_6m"] = previas.groupby(df["codigo"]).transform(lambda s: s.rolling(6).std())
    df["mes"] = df["periodo"].dt.month
    return df


def _predecir(nombre: str, entrenamiento: pd.DataFrame, objetivo: pd.DataFrame) -> np.ndarray:
    if nombre == "Último mes":
        return objetivo["ventas_lag_1"].to_numpy()
    if nombre == "Promedio móvil 3 meses":
        return objetivo["ventas_media_3m"].to_numpy()
    if nombre == "Promedio móvil 6 meses":
        return objetivo["ventas_media_6m"].to_numpy()
    from sklearn.ensemble import RandomForestRegressor

    variables = MODELOS[nombre]
    datos = entrenamiento.dropna(subset=variables + ["ventas"])
    modelo = RandomForestRegressor(n_estimators=200, min_samples_leaf=5, random_state=42, n_jobs=-1)
    modelo.fit(datos[variables], datos["ventas"])
    return modelo.predict(objetivo[variables])


def validar_pronostico(variables: pd.DataFrame, meses_prueba: int = 3) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validación con origen móvil: cada mes de prueba se predice entrenando solo con meses anteriores."""
    historicos = variables[variables["ventas"].notna()]
    meses = sorted(historicos["periodo"].unique())[-meses_prueba:]
    detalle = []
    for mes in meses:
        entrenamiento = historicos[historicos["periodo"] < mes]
        prueba = historicos[(historicos["periodo"] == mes)].dropna(subset=VARIABLES_VENTAS + VARIABLES_COMPRAS)
        y = prueba["ventas"].to_numpy()
        for nombre in MODELOS:
            pred = np.clip(_predecir(nombre, entrenamiento, prueba), 0, None)
            detalle.append({
                "mes_prueba": str(mes), "modelo": nombre,
                "MAE": np.mean(np.abs(pred - y)),
                "WAPE_pct": np.abs(pred - y).sum() / y.sum() * 100,
                "sesgo_pct": (pred.sum() - y.sum()) / y.sum() * 100,
            })
    detalle = pd.DataFrame(detalle)
    resumen = (detalle.groupby("modelo", sort=False)[["MAE", "WAPE_pct", "sesgo_pct"]].mean()
               .sort_values("MAE").reset_index())
    return resumen, detalle


def plan_reabastecimiento(inventario: pd.DataFrame, ventas: pd.DataFrame, compras: pd.DataFrame,
                          z_servicio: float = 1.65, meses_sin_venta_max: int = 6, modelo: str | None = None):
    """Pronóstico del próximo mes y unidades sugeridas por referencia.

    * Usa solo meses completos y rellena con 0 los meses sin venta.
    * Elige el modelo con menor MAE en la validación, salvo que se indique otro.
    * Stock de seguridad = z x desviación estándar de las ventas de los últimos 6 meses.
    * No sugiere compras para referencias sin ventas en los últimos ``meses_sin_venta_max`` meses.
    """
    inv = inventario_por_referencia(inventario)
    ultimo = ultimo_mes_completo(ventas)
    variables = agregar_variables(panel_mensual(ventas, compras, inv["codigo"], ultimo))
    resumen, detalle = validar_pronostico(variables)
    modelo = modelo or resumen.iloc[0]["modelo"]

    historicos = variables[variables["ventas"].notna()]
    futuro = variables[variables["periodo"] == ultimo + 1].copy()
    futuro["demanda_pronosticada"] = np.clip(_predecir(modelo, historicos, futuro), 0, None)
    recientes = historicos[historicos["periodo"] > ultimo - meses_sin_venta_max]
    activas = recientes.groupby("codigo")["ventas"].sum() > 0

    plan = inv[["codigo", "descripcion", "categoria", "stock"]].merge(
        futuro[["codigo", "demanda_pronosticada", "ventas_std_6m"]], on="codigo", how="left"
    )
    plan["activa"] = plan["codigo"].map(activas).fillna(False).astype(bool)
    plan.loc[~plan["activa"], ["demanda_pronosticada", "ventas_std_6m"]] = 0
    plan["demanda_pronosticada"] = np.ceil(plan["demanda_pronosticada"].fillna(0)).astype(int)
    plan["stock_seguridad"] = np.ceil(z_servicio * plan["ventas_std_6m"].fillna(0)).astype(int)
    stock = plan["stock"].clip(lower=0)
    plan["unidades_a_comprar"] = np.maximum(0, plan["demanda_pronosticada"] + plan["stock_seguridad"] - stock).astype(int)
    plan["cobertura_meses"] = np.where(plan["demanda_pronosticada"] > 0, stock / plan["demanda_pronosticada"].replace(0, np.nan), np.nan)
    plan["estado_stock"] = np.select(
        [~plan["activa"], plan["unidades_a_comprar"] > 0],
        ["Sin rotación: no comprar", "Comprar"],
        default="Cubierto",
    )
    # La demanda mensual se estima con meses completos y se aplica a los 30 días
    # siguientes a la fecha de corte, que es la fecha del stock disponible.
    corte = ventas["fecha"].max()
    plan["horizonte"] = f"30 días desde {corte:%Y-%m-%d}"
    plan = plan.drop(columns=["ventas_std_6m"])
    info = {"ultimo_mes_completo": str(ultimo), "mes_pronosticado": str(ultimo + 1), "modelo": modelo,
            "fecha_corte": corte, "validacion": resumen, "validacion_detalle": detalle}
    return plan, info


def balance_compras_ventas(inventario: pd.DataFrame, ventas: pd.DataFrame, compras: pd.DataFrame) -> pd.DataFrame:
    """Unidades compradas frente a unidades vendidas por familia en el periodo común."""
    familias = inventario_por_referencia(inventario).set_index("codigo")["categoria"]
    inicio = max(ventas["fecha"].min(), compras["fecha"].min())
    fin = min(ventas["fecha"].max(), compras["fecha"].max())
    vendidas = ventas[ventas["fecha"].between(inicio, fin)].assign(familia=lambda d: d["codigo"].map(familias))
    compradas = compras[compras["fecha"].between(inicio, fin)].assign(familia=lambda d: d["codigo"].map(familias))
    r = pd.DataFrame({
        "unidades_compradas": compradas.groupby("familia")["cantidad"].sum(),
        "unidades_vendidas": vendidas.groupby("familia")["cantidad"].sum(),
    }).reindex(list(CATEGORIAS)).fillna(0)
    r["compras_sobre_ventas"] = r["unidades_compradas"] / r["unidades_vendidas"]
    return r.reset_index(names="familia")
