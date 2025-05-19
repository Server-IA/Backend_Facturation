# routes.py
from fastapi import APIRouter, Depends, Body, Request
from typing import Dict, Any
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.factus.services import FactusService

router = APIRouter(prefix="/factus", tags=["Factus"])

db = next(get_db())
factus_service = FactusService(db)

@router.get("/invoice/{invoice_id}/download-documents")
def descargar_documentos_factura(invoice_id: int):
    return factus_service.descargar_pdf_xml_factura(invoice_id)
