# Guion de la sustentación: Inteligencia de Inventarios y Ventas Conjuntas

**Duración:** 10 minutos de presentación + preguntas · **6 diapositivas**

| # | Diapositiva | Tiempo |
|---|---|---|
| 1 | El problema | 0:00–1:15 |
| 2 | La solución: datos, flujo y herramienta | 1:15–2:30 |
| 3 | Track 1: ventas conjuntas | 2:30–3:30 |
| 4 | Track 2: calidad de datos e inventario estancado | 3:30–5:30 |
| 5 | Track 2: Pareto frente a K-Means | 5:30–6:45 |
| 6 | Track 3, limitaciones y cierre | 6:45–10:00 |

El Track 2 ocupa dos diapositivas porque el profesor recomendó darle más peso.

Todas las cifras salen de los notebooks ejecutados (`notebooks/`) y de la app (`app.py`).
Datos: ventas del 2 de enero de 2025 al 10 de julio de 2026. Si se vuelven a ejecutar los
notebooks con datos nuevos, hay que actualizar las cifras.

**Antes de presentar, revisar que:**

- [ ] Las diapositivas no tengan la marca de agua de "Gemini Notebook".
- [ ] No quede ninguna cifra del boceto (72 %, lift 3,4, "Aceite 20W-50 → Filtro X", Clase A/B/C/D, soporte 35,5 %).
- [ ] No se mencionen DBSCAN, consumo de RAM ni "tiempo real".
- [ ] La captura de la app sea real (diapositiva 2).
- [ ] La app esté abierta en otra pestaña por si piden una demostración: `streamlit run app.py`.

---

## Diapositiva 1 · El problema (0:00–1:15)

**En pantalla**
> **Inteligencia de Inventarios y Ventas Conjuntas**
> Cristhian Bejarano · Maria Alejandra Villa
>
> **¿Quién decide qué comprar?** El jefe de compras y el jefe de bodega.
> **¿Cómo lo hacían?** Revisando tablas de Excel y el software de inventario, referencia por referencia.
>
> | | |
> |---|---|
> | **185 M COP** | en stock sin venderse hace más de 180 días (34 % del inventario) |
> | **99 referencias** | con costos o precios erróneos en el sistema |
> | **2.159 referencias** | imposibles de revisar a mano cada mes |

**Visual:** el engranaje de la portada del boceto a la derecha y las tres cifras grandes a la izquierda.

**Notas del orador**
"Este proyecto apoya al jefe de compras y al jefe de bodega de un almacén de autopartes. El problema no
es la falta de datos: el sistema registra todo. El problema es que nadie puede revisar 2.159 referencias
a mano. Por eso un tercio del valor del inventario lleva más de seis meses sin venderse y hay costos mal
digitados que nadie detecta. Respondemos tres preguntas: qué se vende junto, qué referencias valen la
pena y cuánto comprar."

---

## Diapositiva 2 · La solución: datos, flujo y herramienta (1:15–2:30)

**En pantalla**

Arriba, el flujo de 4 pasos (adaptado de la diapositiva 4 del boceto):

```
Exportación del ERP ─► Limpieza (Python) ─► Motor analítico (3 tracks) ─► Dashboard Streamlit
  • 45.982 facturas      • Tipos, espacios     • Track 1: venta cruzada        • Filtros por
  • 30.923 compras       • Duplicados          • Track 2: calidad, rotación,     familia y código
  • 2.159 referencias    • Mes incompleto        segmentación                 • Plan de compras
    (4 familias)           excluido            • Track 3: pronóstico              descargable
```

Abajo, **una captura real de la app** (pestaña Track 3, con el plan filtrado y el botón de descarga),
con la frase: *"El jefe de compras carga el corte del mes y obtiene alertas y plan de compra, sin tocar código."*

**Cómo tomar la captura:** `streamlit run app.py` → pestaña "Track 3: reabastecimiento" → capturar la ventana.

**Notas del orador**
"Usamos tres tablas reales del ERP: ventas, compras e inventario, de 18 meses y cuatro familias (aceites,
filtros, llantas y baterías). Las tres se unen por el código de referencia. Toda la lógica está en un solo
módulo que usan los notebooks y el tablero, así que lo que ven en la app es exactamente lo que validamos.
Cada mes se cargan los archivos nuevos desde la barra lateral."

---

## Diapositiva 3 · Track 1: ventas conjuntas (2:30–3:30)

**En pantalla** (formato "señal → acción" de la diapositiva 11 del boceto)
> **Regla detectada: FILTROS → ACEITES**
> **Confianza: 88 %** · **Lift: 4,5**
> El 88 % de las facturas con filtro lleva aceite: 4,5 veces más de lo esperado por azar.
> Las otras 10 combinaciones tienen confianza ≤ 19 %: no justifican venta cruzada.
>
> **Acción operativa**
> 1. Planear juntas las compras de filtros y aceites: si falta el filtro, se arriesga la venta del aceite.
> 2. Sugerir el combo al facturar y ubicar ambos productos juntos en la bodega.

**Visual:** `reports/figuras/track1_lift_reglas.png` (pequeño, a la derecha).

**Notas del orador**
"Comparamos Apriori, FP-Growth y ECLAT; los tres dan exactamente las mismas reglas. El hallazgo confirma lo
que el negocio ya sabía, el cambio de aceite con filtro, pero ahora está cuantificado. Las demás
combinaciones son débiles. Que solo haya una regla fuerte también es un resultado: evita invertir en
promociones cruzadas que no funcionarían."

---

## Diapositiva 4 · Track 2: calidad de datos e inventario estancado (3:30–5:30)

**En pantalla:** dos columnas.

**Izquierda: costos mal digitados**
> | Referencia | Costo en inventario | Costo habitual de compra | Precio real de venta |
> |---|---|---|---|
> | 771 Aceite transmisión | 850.000 | 44.500 | 64.000 |
> | 1028 Filtro aire Kia | 9.733.333 | 13.500 | 22.500 |
>
> **99 referencias marcadas**, 41 de ellas con probable error de digitación del costo.
> Método: el costo se contrasta con el **historial de compras** y con el **precio real de venta**.

**Derecha: inventario estancado**
> **185 M COP (34 %) sin venta hace más de 180 días**
> - Llantas: 142 M de 257 M (55 %).
> - Aceites: el 88 % del valor de su stock está en referencias vendidas en los últimos 30 días.
> - Se compraron **27 % más baterías** y **14 % más filtros** de lo que se vendió.

**Visual de la derecha:** `reports/figuras/track2_lento_movimiento.png`

**Notas del orador**
"En la asesoría nos preguntaron si los márgenes negativos eran errores de digitación o cambios de costo.
Lo resolvimos con las compras reales. El aceite 771 aparecía con margen de −2.786 %: siempre se compró a
unos 44.500 pesos, pero una compra quedó registrada a 850.000 y ese valor pasó al inventario. Ahora el jefe
de compras no revisa 2.159 referencias: revisa 99, y cada una viene con su evidencia.

Con los costos corregidos medimos el inventario estancado: 185 millones sin venderse en más de seis meses.
El problema no está repartido por igual. Los aceites rotan muy bien; las llantas concentran el capital
inmovilizado. Y las compras reales muestran que en baterías y filtros se compró más de lo que se vendió:
ahí se origina la acumulación."

---

## Diapositiva 5 · Track 2: Pareto frente a K-Means (5:30–6:45)

**En pantalla** (estructura de la diapositiva 9 del boceto, ahora con datos)
> **Izquierda: lo que muestra Pareto**
> 233 referencias (20 %) generan el 80 % de los ingresos.
> Pero **99 de esas 233** tienen baja rotación y margen bajo.
>
> **Derecha: lo que muestra K-Means** (rotación × margen real, 3 grupos, silhouette 0,46)
> - **Alta rotación / margen alto:** 182 referencias → **71 % de la utilidad bruta**
> - Baja rotación / margen alto: 278 referencias → 14 %
> - Baja rotación / margen bajo: 727 referencias → 15 %
>
> Dato extra: las llantas tienen un margen real de **29,3 %**, frente al 37 % de lista (se venden con descuento).

**Visual:** `reports/figuras/track2_segmentacion.png` (solo el gráfico de dispersión de la derecha).

**Notas del orador**
"Pareto ordena por una sola variable, los ingresos, y considera prioritarias 233 referencias. K-Means
combina rotación y margen real y muestra que 99 de ellas venden mucho dinero pero con poco margen. El grupo
que de verdad sostiene el negocio son 182 referencias que generan el 71 % de la utilidad: ahí hay que
priorizar stock. El número de grupos lo elegimos con el coeficiente silhouette, y excluimos las referencias
con costos erróneos para que un dato mal digitado no forme su propio grupo."

---

## Diapositiva 6 · Track 3, limitaciones y cierre (6:45–10:00)

**En pantalla:** tres bloques.

**Arriba: pronóstico validado**
> Validamos 5 modelos con meses que no vieron en el entrenamiento (abril–junio 2026):
>
> | Modelo | Error medio (MAE) |
> |---|---|
> | **Promedio móvil 3 meses** | **0,72** ✔ elegido |
> | Random Forest (ventas + compras reales) | 0,75 |
> | Random Forest (solo ventas) | 0,79 |
>
> **Plan para 30 días:** comprar **2.852 unidades en 520 referencias** ·
> **no comprar** 1.376 referencias sin ventas en 6 meses.

**Abajo a la izquierda: limitaciones**
> - 4 familias, sin subcategorías oficiales.
> - Margen calculado con el costo actual: no hay costo histórico por venta.
> - 18 meses de historia, sin tiempos de entrega de proveedores.
> - Las alertas y el plan son **sugerencias**: los valida el jefe de compras.

**Abajo a la derecha: siguientes pasos**
> 1. Corregir en el sistema las 41 referencias con costo mal digitado.
> 2. Plan de salida para los 185 M COP estancados (llantas primero).
> 3. Ampliar a subcategorías y a más familias.

**Notas del orador**
"Para el pronóstico validamos cinco modelos con meses que no habían visto. El más simple ganó: la demanda
por referencia es baja e intermitente, y el promedio de tres meses pronostica mejor que el Random Forest.
Lo elegimos también porque es fácil de explicar al jefe de compras. El plan suma un stock de seguridad,
resta lo disponible y, sobre todo, le dice qué **no** comprar: 1.376 referencias que llevan seis meses sin
venderse.

Tenemos limitaciones claras: trabajamos cuatro familias, el margen usa el costo actual y 18 meses no
alcanzan para la estacionalidad anual. Por eso todo se presenta como sugerencia para el jefe de compras.

En resumen: confirmamos con datos la única venta cruzada que importa, encontramos los costos que
distorsionaban la rentabilidad, cuantificamos 185 millones inmovilizados y entregamos un plan de compras
validado. La herramienta funciona con datos reales y se puede usar desde el próximo corte."

---

## Preguntas probables del jurado

| # | Pregunta | Respuesta corta |
|---|---|---|
| 1 | La regla filtros → aceites es obvia, ¿qué aporta? | Cuantifica lo intuitivo (88 %, lift 4,5) y descarta las otras 10 combinaciones. Saber qué **no** funciona evita promociones inútiles. |
| 2 | ¿Por qué el lift es 4,5 y no otro valor? | Se calcula sobre todas las facturas (45.982). Si se usaran solo las facturas con alguna de las 4 familias, el aceite aparece en el 77 % de ellas y el lift se subestima a 1,16. |
| 3 | ¿Cómo distinguen un error de digitación de un cambio de costo? | Si el costo está más de 3 veces fuera del costo mediano de compra, es error. Si las compras recientes suben de forma sostenida, es cambio de costo. Sin compras registradas no se puede saber, y se marca para revisión. |
| 4 | Un silhouette de 0,46 es bajo, ¿los grupos son confiables? | Indica grupos razonables pero no perfectamente separados. Es una guía para priorizar, no una clasificación rígida. Una versión anterior daba 0,95, pero era un artefacto de un solo dato erróneo; preferimos el valor honesto. |
| 5 | ¿Por qué no usaron el Random Forest si es más sofisticado? | Lo validamos y perdió frente al promedio móvil (MAE 0,75 frente a 0,72). Con demanda intermitente, lo simple funciona igual o mejor y se explica más fácil. |
| 6 | ¿Por qué el plan no sugiere compras para todas las referencias? | Las referencias sin ventas en 6 meses se excluyen a propósito: comprarlas aumentaría el inventario estancado. |
| 7 | ¿Cuál es el error del pronóstico en términos de negocio? | El WAPE es del 47 % por referencia porque la demanda es baja e irregular. El sesgo total es de solo +2 %: en conjunto, no compra ni de más ni de menos. Por eso se suma stock de seguridad. |
| 8 | ¿Cómo se usa esto el próximo mes? | Se exportan los archivos del ERP, se ejecuta la limpieza y se cargan en la app. Todo el cálculo está en un solo módulo, así que no hay que tocar código. |
