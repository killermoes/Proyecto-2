# Proyecto 2: análisis de ventas, compras e inventario

Repositorio de análisis exploratorio, limpieza de datos y análisis de cesta de
compra a partir de los archivos de ventas, compras e inventario.

## Estructura

```text
.
├── data/
│   ├── raw/          # Fuentes originales
│   │   └── originals/ # Copias duplicadas conservadas por compatibilidad
│   └── processed/    # CSV exportados y datos limpios
├── notebooks/        # Análisis exploratorio y pipeline de asociación
├── scripts/          # Procesamiento reproducible por línea de comandos
├── requirements.txt
└── README.md
```

Los archivos de entrada se leen desde `data/raw/`. Los notebooks y el script
guardan sus resultados CSV en `data/processed/`. Los archivos originales se
mantienen sin modificaciones; las copias idénticas que antes estaban en la raíz
se conservan en `data/raw/originals/`.

## Preparación

Se requiere Python 3.11.9, según `.python-version`. Instala las dependencias
desde la raíz del repositorio:

```powershell
python -m pip install -r requirements.txt
```

## Uso

Ejecuta la limpieza de ventas desde la raíz del repositorio:

```powershell
python scripts/limpieza_ventas.py
```

Abre `notebooks/eda.ipynb` para el análisis exploratorio y limpieza, o
`notebooks/02_etl_y_track1.ipynb` para el pipeline ETL y análisis de reglas de
asociación. Ambos notebooks localizan la raíz del proyecto y utilizan las
carpetas `data/raw/` y `data/processed/`.
