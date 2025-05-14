# routes.py
from fastapi import APIRouter, Depends, Body, Request
from typing import Dict, Any
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.payu.services import PayUProcessor, PayUService

router = APIRouter(prefix="/payu", tags=["PayU"])
db = next(get_db())
payu_service = PayUService(db)

@router.get("/pse-banks")
def get_pse_banks():
    """
    Obtener listado de bancos habilitados para pagos por PSE.
    """
    return payu_service.get_pse_bank_list()


@router.post("/pse-payment")
def create_pse_payment(request: Request, payload: dict = Body(...)):
    """
    Crear una transacción PSE con los datos del cliente y el banco.
    """
    # Extraer información del cliente HTTP
    ip_address = request.client.host
    user_agent = request.headers.get("user-agent")
    cookie = request.headers.get("cookie")  # Asegúrate que el cliente lo envíe si lo necesitas

    # Combinar todo en un solo diccionario
    payment_data = {
        **payload,
        "ipAddress": ip_address,
        "userAgent": user_agent,
        "cookie": cookie,
    }
    return payu_service.create_pse_payment(payment_data=payment_data)

@router.get("/retorno", response_class=HTMLResponse)
def payu_retorno(request: Request):
    params = dict(request.query_params)
    estado = params.get("lapTransactionState", "DESCONOCIDO")
    referencia = params.get("referenceCode", "")
    mensaje = {
        "APPROVED": "✅ Transacción aprobada",
        "DECLINED": "❌ Transacción rechazada",
        "PENDING": "⌛ Transacción pendiente"
    }.get(estado.upper(), "⚠️ Estado desconocido")
    
    return f"""
    <html><body>
        <h2>{mensaje}</h2>
        <p>Referencia: {referencia}</p>
        <p>Estado técnico: {estado}</p>
    </body></html>
    """

@router.post("/notificacion")
async def payu_notificacion(request: Request, db: Session = Depends(get_db)):
    try:
        # PayU envía x-www-form-urlencoded, así que usamos request.form()
        form = await request.form()
        form_data = dict(form)

        processor = PayUProcessor(db)
        pago = processor.process_notification(form_data)

        return pago

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "data": {"title": "Error procesando notificación", "message": str(e)}}
        )