from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from datetime import datetime
from app.database import get_db
from app.facturation.services import FacturationService

router = APIRouter(prefix="/facturation", tags=["Facturation"])

@router.get("/", response_model=Dict)
def get_facturation(db: Session = Depends(get_db)):
    """Obtener todos los mantenimientos"""
    facturation_service = FacturationService(db)
    return facturation_service.get_facturation()
