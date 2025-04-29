import logging
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic.error_wrappers import ValidationError

# **Manejo de errores de validación de Pydantic**
async def validation_exception_handler(request: Request, exc: ValidationError):
    """Captura errores de validación y retorna un JSON estructurado."""
    error_messages = [{"field": e["loc"][-1], "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "data": "Error en los datos enviados",
            "errors": error_messages
        }
    )

# **Manejo de errores globales**
async def global_exception_handler(request: Request, exc: Exception):
    # Log detallado del error
    logging.error(f"Uncaught error occurred: {exc}, URL: {request.url}")
    
    # Devuelve una respuesta clara
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": "Error interno del servidor. Por favor, contacte al administrador.",
            "error_details": str(exc)
        },
        headers={"X-Error-Code": "INTERNAL_SERVER_ERROR"}
    )

# **Función para configurar los manejadores de excepciones**
def setup_exception_handlers(app):
    """Registra los manejadores de excepciones en la aplicación FastAPI."""
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)
