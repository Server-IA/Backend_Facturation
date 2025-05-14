# routes.py
from fastapi import APIRouter, Depends, Body, Request
from typing import Dict, Any
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.payu.services import PayUService

router = APIRouter(prefix="/payu", tags=["PayU"])

payu_service = PayUService()

@router.get("/pse-banks")
def get_pse_banks():
    """
    Obtener listado de bancos habilitados para pagos por PSE.
    """
    return payu_service.get_pse_bank_list()


@router.post("/pse-payment")
def create_pse_payment(payload: dict = Body(...)):
    """
    Crear una transacción PSE con los datos del cliente y el banco.
    """
    return payu_service.create_pse_payment(payment_data=payload)

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
async def payu_notificacion(request: Request):
    form = await request.form()
    referencia = form.get("reference_sale")
    estado = form.get("state_pol")  # 4 = aprobado
    monto = form.get("value")
    moneda = form.get("currency")

    return JSONResponse(content={"message": "OK"}, status_code=200)