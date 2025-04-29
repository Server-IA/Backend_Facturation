import time
import logging
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

# **Middleware de Logging para registrar peticiones**
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Generar un ID único por cada petición
        request_id = request.headers.get("X-Request-ID", str(time.time()))
        logging.info(f"Request [{request_id}]: {request.method} {request.url}")

        # Procesar la solicitud
        response = await call_next(request)

        process_time = time.time() - start_time
        logging.info(f"Response [{request_id}]: {response.status_code} ({process_time:.2f}s)")

        return response

# Función para agregar todos los middlewares
def setup_middlewares(app):
    """Agrega los middlewares a la aplicación FastAPI."""

    # Protección contra Host Header Attacks
    # app.add_middleware(TrustedHostMiddleware, allowed_hosts=["example.com", "*.example.com", "localhost", "127.0.0.1"])

    # Configuración CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Cambiar a dominios específicos en producción
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    # Middleware de Logging
    app.add_middleware(LoggingMiddleware)
