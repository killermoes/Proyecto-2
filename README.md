# Proyecto 2: análisis de ventas, compras e inventario

Proyecto de análisis de datos de autopartes. Incluye exploración y preparación
de datos, reglas de asociación (Track 1), segmentación con K-Means (Track 2) y
una proyección de demanda y reabastecimiento (Track 3).

## Estructura del repositorio

```text
.
├── data/
│   ├── raw/                         # Archivos fuente; no modificarlos
│   │   └── originals/               # Copias archivadas de algunos originales
│   └── processed/                   # CSV de trabajo y resultados del EDA
├── notebooks/
│   ├── eda.ipynb                    # Exploración y preparación de datos
│   ├── 02_etl_y_track1.ipynb        # ETL y análisis de asociación
│   ├── track2.ipynb                 # Segmentación de productos
│   └── Track3.ipynb                 # Predicción y reabastecimiento
├── scripts/
│   └── limpieza_ventas.py           # Normaliza y exporta las ventas
├── .python-version                  # Versión recomendada: Python 3.11.9
└── requirements.txt                 # Dependencias de análisis y notebooks
```

Los notebooks se ejecutan desde la raíz del proyecto. Leen los archivos fuente
de `data/raw/` y utilizan `data/processed/` para los datos preparados. Conserva
los originales sin modificarlos; los CSV procesados pueden regenerarse.

## Requisitos e instalación

Se recomienda Python **3.11.9**. En PowerShell, desde la raíz del repositorio:

```powershell
py -3.11 --version
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Si PowerShell bloquea la activación del entorno, ejecuta los comandos de pip
con `.\.venv\Scripts\python.exe -m pip ...` sin activar el entorno.

En VS Code, abre la carpeta del proyecto, instala la extensión **Jupyter** si
no está instalada y selecciona el intérprete `.venv` como kernel de cada
notebook. Ejecuta las celdas en orden, de arriba hacia abajo.

## Flujo de trabajo

Sigue estos pasos en orden. Los notebooks Track 1, Track 2 y Track 3 usan el
inventario limpio y las ventas normalizadas que se preparan en los primeros
pasos.

### 1. EDA y preparación inicial

Abre y ejecuta todas las celdas de [`notebooks/eda.ipynb`](notebooks/eda.ipynb).
El notebook explora los archivos fuente y genera en `data/processed/` los
extractos de compras y ventas, además del inventario limpio.

### 2. Normalizar las ventas

Después del EDA, ejecuta desde la raíz:

```powershell
python scripts/limpieza_ventas.py
```

Este paso es necesario: genera `data/processed/ventas_limpia.csv` con las
columnas normalizadas que consumen los tres tracks. Ejecutarlo después del EDA
también evita que el extracto de ventas sin normalizar exportado por el
notebook reemplace ese archivo.

### 3. ETL y Track 1: reglas de asociación

Abre [`notebooks/02_etl_y_track1.ipynb`](notebooks/02_etl_y_track1.ipynb) y
ejecuta todas sus celdas. Usa `ventas_limpia.csv` e
`INVENTARIO_PRODUCTOS_LIMPIO.csv` para construir las transacciones y comparar
Apriori, FP-Growth y ECLAT.

### 4. Track 2: segmentación

Abre [`notebooks/track2.ipynb`](notebooks/track2.ipynb) en un kernel propio y
ejecuta todas las celdas. El notebook aplica K-Means a las referencias de
producto y presenta sus perfiles de rotación y margen.

### 5. Track 3: predicción y reabastecimiento

Abre [`notebooks/Track3.ipynb`](notebooks/Track3.ipynb) en un kernel propio y
ejecuta todas las celdas. El notebook estima la demanda del siguiente mes y
calcula las unidades sugeridas para compra. Actualmente, las compras
históricas de este track se simulan a partir de las ventas; no provienen de un
modelo de compras real.

## Organización de los datos

| Ruta | Uso |
|---|---|
| `data/raw/ANALISISVENTASYCOMPRASIA.xlsx` | Hojas fuente de ventas y compras |
| `data/raw/INVENTARIOPRODUCTOS.xlsx` | Fuente de inventario |
| `data/processed/INVENTARIO_PRODUCTOS_LIMPIO.csv` | Inventario usado por los tracks |
| `data/processed/ventas_limpia.csv` | Ventas normalizadas usadas por los tracks |
| `data/processed/DS_COMPRAS.csv` y `DS_VENTAS.csv` | Extractos exportados por el EDA |

Para regenerar los archivos de trabajo, vuelve a ejecutar el EDA y luego el
script de limpieza de ventas antes de correr los tracks. Track 1, Track 2 y
Track 3 se ejecutan como notebooks independientes después de preparar esos
archivos.
