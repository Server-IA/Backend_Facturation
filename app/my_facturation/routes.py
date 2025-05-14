# my_facturation/routes.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.my_facturation.services import MyFacturationService
from app.my_facturation.schemas  import UserInvoice
from app.database            import get_db

router = APIRouter(prefix="/my_facturation", tags=["MyFacturación"])

@router.get(
    "/invoices/user/{user_id}",
    response_model=List[UserInvoice]
)
def get_user_invoices(user_id: int, db: Session = Depends(get_db)):
    """
    Lista todas las facturas asociadas a un usuario (user_id).
    """
    return MyFacturationService(db).list_user_invoices(user_id)
