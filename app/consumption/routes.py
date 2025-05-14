# app/consumption/routes.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Dict, List

from app.consumption.services import ConsumptionService
from app.database             import get_db

router = APIRouter(prefix="/consumption", tags=["Consumo"])

@router.get("/measurements", response_model=List[Dict])
def list_consumptions(db: Session = Depends(get_db)):
    return ConsumptionService(db).list_all_consumptions()

@router.get("/measurements/summary/{year}/{month}")
def consumption_summary(year: int, month: int, db: Session = Depends(get_db)):
    return ConsumptionService(db).get_monthly_stats(year, month)

@router.get("/measurements/{measurement_id}", response_model=Dict)
def get_consumption_detail(measurement_id: int, db: Session = Depends(get_db)):
    return ConsumptionService(db).get_consumption_detail(measurement_id)
