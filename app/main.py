from fastapi import FastAPI
from app.database import Base, engine
from app.facturation.routes import router as facturation_router
from app.payu.routes import router as payu_router
from app.factus.routes import router as factus_router
from app.billing.routes import router as billing_router
from app.my_facturation.routes import router as my_facturation
from app.consumption.routes import router as consumption
from app.middlewares import setup_middlewares
from app.exceptions import setup_exception_handlers
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()
# Importa la función que carga los modelos
from app.ml import get_models

app = FastAPI(
    title="Distrito de Riego API Gateway - Facturación",
    description="API Gateway para Mantenimiento en el sistema de riego",
    version="1.0.0"
)

# Servir carpeta de facturas estáticas

setup_middlewares(app)
setup_exception_handlers(app)
app.include_router(facturation_router)
app.include_router(payu_router)
app.include_router(factus_router)
app.include_router(billing_router)
app.include_router(my_facturation)
app.include_router(consumption)
Base.metadata.create_all(bind=engine)

@app.on_event("startup")
def load_ml_models():
    print("⚙️ [startup] Cargando modelos de ML...")
    get_models()

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "message": "API funcionando correctamente"}
