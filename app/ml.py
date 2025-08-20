import sys
import joblib
import time
from pathlib import Path
from functools import lru_cache
import numpy
import types
import pandas
from dotenv import load_dotenv

load_dotenv()

# ——— Parche robusto para compatibilidad numpy ———
# 1) Redirige numpy._core → numpy.core
sys.modules['numpy._core'] = numpy.core

# 2) Parchea numpy._core.multiarray
try:
    import numpy.core.multiarray as multiarray
    sys.modules['numpy._core.multiarray'] = multiarray
    print("🩹 Patch aplicado: numpy._core.multiarray", flush=True)
except ImportError as e:
    print("❌ No se pudo patchear numpy._core.multiarray:", e, flush=True)

# 3) Parchea numpy._core._multiarray_umath
try:
    import numpy.core._multiarray_umath as mmu
    sys.modules['numpy._core._multiarray_umath'] = mmu
    print("🩹 Patch aplicado: numpy._core._multiarray_umath", flush=True)
except ImportError as e:
    print("❌ No se pudo patchear numpy._core._multiarray_umath:", e, flush=True)

# 4) Stub para numpy._core.defchararray y numpy._core.strings
for module_name in ['numpy._core.defchararray', 'numpy._core.strings']:
    sys.modules[module_name] = types.ModuleType(module_name)
    print(f"🩹 Stub creado para {module_name}", flush=True)

# 5) Stub para numpy._core.tests._natype (pd_NA)
tests_mod = types.ModuleType('numpy._core.tests')
sys.modules['numpy._core.tests'] = tests_mod
natype_mod = types.ModuleType('numpy._core.tests._natype')
natype_mod.pd_NA = pandas.NA
sys.modules['numpy._core.tests._natype'] = natype_mod
print("🩹 Patch aplicado: numpy._core.tests._natype", flush=True)

# Directorio base de los .pkl
BASE = Path(__file__).parent / "ml_models"
print("🔍 Ruta de ml_models:", BASE, flush=True)
try:
    archivos = [p.name for p in BASE.iterdir()]
    print("🔍 Archivos en ml_models:", archivos, flush=True)
except Exception as e:
    print("❌ No se pudo listar ml_models:", e, flush=True)

@lru_cache(maxsize=1)
def get_models():
    print("🔄 Iniciando carga de modelos desde:", BASE, flush=True)

    def carga(nombre):
        print(f"⏳ Cargando {nombre} …", flush=True)
        t0 = time.perf_counter()
        mdl = joblib.load(BASE / f"{nombre}.pkl")
        print(f"✅ {nombre} cargado en {time.perf_counter() - t0:.2f}s", flush=True)
        return mdl

    modelo_lluvia        = carga("modelo_lluvia")
    modelo_consumo       = carga("modelo_consumo")
    modelo_clasificacion = carga("modelo_clasificacion")

    try:
        print("⏳ Cargando columnas_esperadas …", flush=True)
        t0 = time.perf_counter()
        columnas_esperadas = joblib.load(BASE / "columnas_esperadas.pkl")
        print(f"✅ columnas_esperadas cargadas en {time.perf_counter() - t0:.2f}s", flush=True)
    except Exception as e:
        print("❌ Error cargando columnas_esperadas:", e, flush=True)
        raise

    return {
        "lluvia":        modelo_lluvia,
        "consumo":       modelo_consumo,
        "clasificacion": modelo_clasificacion,
        "columnas":      columnas_esperadas,
    }
