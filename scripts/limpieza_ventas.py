from pathlib import Path
import pandas as pd
import numpy as np

root = Path(__file__).resolve().parents[1]
raw_dir = root / "data" / "raw"
processed_dir = root / "data" / "processed"
processed_dir.mkdir(parents=True, exist_ok=True)

raw_file = raw_dir / "ANALISISVENTASYCOMPRASIA.xlsx"
if not raw_file.exists():
    raise FileNotFoundError(f"No se encontró el archivo raw: {raw_file}")

# Cargar datos de ventas
ventas = pd.read_excel(raw_file, sheet_name="VENTAS")

# Copia de seguridad para no alterar el original
clean = ventas.copy()

# Normalización de columnas
df_columns = [str(col).strip().lower() for col in clean.columns]
clean.columns = df_columns

# Limpieza de texto
for col in ["fac_veh", "ref_des", "gru_des"]:
    if col in clean.columns:
        clean[col] = clean[col].astype("string").str.strip()

clean["ref_des"] = clean["ref_des"].replace(r"\s+", " ", regex=True).str.strip()
clean["gru_des"] = clean["gru_des"].replace(r"\s+", " ", regex=True).str.strip()
clean["fac_veh"] = clean["fac_veh"].fillna("SIN_PLACA").replace(r"\s+", " ", regex=True).str.strip()

# Tipos numéricos y fechas
clean["fac_num"] = pd.to_numeric(clean["fac_num"], errors="coerce").astype("Int64")
clean["fac_fec"] = pd.to_datetime(clean["fac_fec"], errors="coerce")

for col in ["kar_cod", "kar_sal", "kar_pre", "kar_iva", "kar_vis", "subtotal", "vriva", "vrtotal"]:
    if col in clean.columns:
        clean[col] = pd.to_numeric(clean[col], errors="coerce")

# Completar valores faltantes en columnas clave
clean["fac_veh"] = clean["fac_veh"].fillna("SIN_PLACA")
clean["kar_sal"] = clean["kar_sal"].fillna(0)
clean["kar_vis"] = clean["kar_vis"].fillna(0)
clean["kar_iva"] = clean["kar_iva"].fillna(0)

# Eliminar duplicados y filas vacías
clean = clean.drop_duplicates()
clean = clean.dropna(subset=["fac_num", "ref_des"]).reset_index(drop=True)
clean = clean[clean["ref_des"].str.len() > 0].reset_index(drop=True)

# Orden final
def sort_cols(df):
    return df[[
        "fac_num", "fac_fec", "fac_veh", "kar_cod", "ref_des",
        "kar_sal", "kar_pre", "kar_iva", "kar_vis", "subtotal",
        "vriva", "vrtotal", "gru_des"
    ]]

clean = sort_cols(clean)
clean = clean.rename(
    columns={
        "fac_num": "factura",
        "fac_fec": "fecha",
        "fac_veh": "vehiculo",
        "kar_cod": "codigo_producto",
        "ref_des": "descripcion",
        "kar_sal": "cantidad",
        "kar_pre": "precio_unitario",
        "kar_iva": "porcentaje_iva",
        "kar_vis": "valor_base",
        "subtotal": "subtotal",
        "vriva": "valor_iva",
        "vrtotal": "total",
        "gru_des": "categoria",
    }
)

# Guardar salida limpia
output_path = processed_dir / "ventas_limpia.csv"
clean.to_csv(output_path, index=False)

print(f"Ventas procesadas: {len(clean)} filas")
print(f"Archivo generado: {output_path}")
print(clean.head().to_string(index=False))
