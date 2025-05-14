# routes.py
from fastapi import APIRouter, Depends , Body
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.database import get_db
from app.facturation.services import FacturationService , MLService , InvoiceService
from app.facturation.schemas import ConceptCreate, ConceptUpdate , PredictInput


router = APIRouter(prefix="/facturations", tags=["Facturations"])
# router_invoice = APIRouter(prefix="/facturations", tags=["Facturation"])


@router.get("/", response_model=Dict[str, Any])
def list_concepts(db: Session = Depends(get_db)):
    """
    Devuelve todos los conceptos junto con sus nombres de scope, tipo, estado,
    predio y lote (si aplica).
    """
    return FacturationService(db).list_concepts()


@router.post("/", response_model=Dict[str, Any], status_code=201)
def add_concept(payload: ConceptCreate, db: Session = Depends(get_db)):
    return FacturationService(db).create_concept(payload)


@router.put("/{concept_id}", response_model=Dict[str, Any])
def edit_concept(concept_id: int, payload: ConceptUpdate, db: Session = Depends(get_db)):
    return FacturationService(db).update_concept(concept_id, payload)


@router.patch("/{concept_id}/enable",  response_model=Dict[str, Any])
def enable_concept(concept_id: int, db: Session = Depends(get_db)):
    """
    Habilita un concepto (estado_id = 27).
    """
    return FacturationService(db).enable_concept(concept_id)


@router.patch("/{concept_id}/disable", response_model=Dict[str, Any])
def disable_concept(concept_id: int, db: Session = Depends(get_db)):
    """
    Inhabilita un concepto (estado_id = 28).
    """
    return FacturationService(db).disable_concept(concept_id)



@router.post(
    "/predict-consumption",
    summary="Predecir consumo de agua",
    response_model=Dict[str, Any],
    tags=["Machine Learning"]
)
def predict_consumption(
    payload: PredictInput = Body(...),
    db:      Session      = Depends(get_db),
):
    """
    Devuelve:
      - predicted_consumption: estimación (m³)
      - historical_avg_consumption: promedio histórico para ese lote (si se provee lot_id)
    """
    return MLService(db).predict_consumption(payload)

@router.get("/detail/{invoice_id}")
def get_invoice_detail(invoice_id: int, db: Session = Depends(get_db)):
    return InvoiceService(db).get_invoice_detail(invoice_id)

@router.post("/create", status_code=201)
def create_invoice(payload: dict, db: Session = Depends(get_db)):
    invoice = InvoiceService(db).create_invoice(payment_data=payload)
    return invoice

