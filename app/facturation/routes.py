# routes.py
from fastapi import APIRouter, Depends , Body , HTTPException
from typing import Dict, Any , List
from sqlalchemy.orm import Session

from app.database import get_db
from app.facturation.services import FacturationService , MLService , InvoiceService
from app.facturation.schemas import ConceptCreate, ConceptUpdate , PredictInput , ConceptTypeOut , ScopeTypeOut ,ConsumptionPredictionOut, PredictByLot, ConceptResponse


router = APIRouter(prefix="/facturations", tags=["Facturations"])
# router_invoice = APIRouter(prefix="/facturations", tags=["Facturation"])


@router.get("/", response_model=Dict[str, Any])
def list_concepts(db: Session = Depends(get_db)):
    """
    Devuelve todos los conceptos junto con sus nombres de scope, tipo, estado,
    predio y lote (si aplica).
    """
    return FacturationService(db).list_concepts()


@router.get("/concept_types", response_model=List[ConceptTypeOut])
def get_concept_types(db: Session = Depends(get_db)):
    return FacturationService(db).list_concept_types()

@router.get("/scope_types", response_model=List[ScopeTypeOut])
def get_scope_types(db: Session = Depends(get_db)):
    return FacturationService(db).list_scope_types()

@router.get("/{concept_id}", response_model=Dict[str, Any], summary="Ver detalles de un concepto")
def get_concept(concept_id: int, db: Session = Depends(get_db)):
    return FacturationService(db).get_concept(concept_id)

@router.post(
    "/",
    response_model=ConceptResponse,
    status_code=201,
)
def add_concept(
    payload: ConceptCreate,
    db: Session = Depends(get_db),
):
    """
    Crea un nuevo concepto.
    El campo estado_id no es necesario: se asigna Activo (27) por defecto.
    """
    try:
        concept = FacturationService(db).create_concept(payload)
        # FastAPI usará ConceptResponse para serializar el SQLAlchemy model
        return ConceptResponse(success=True, data=concept)
    except HTTPException as he:
        # Propaga errores de validación del servicio
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    response_model=ConsumptionPredictionOut,
    summary="Predecir consumo de agua por lote"
)
def predict_consumption(payload: PredictByLot, db: Session = Depends(get_db)):
    return FacturationService(db).predict_consumption_by_lot(payload.lot_id)

@router.get("/detail/{invoice_id}")
def get_invoice_detail(invoice_id: int, db: Session = Depends(get_db)):
    return InvoiceService(db).get_invoice_detail(invoice_id)

@router.post("/create", status_code=201)
def create_invoice(payload: dict, db: Session = Depends(get_db)):
    invoice = InvoiceService(db).create_invoice(payment_data=payload)
    return invoice

