# app/consumption/schemas.py

from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional, Dict

class ConsumptionRecord(BaseModel):
    property_id:      int
    lot_id:           int
    payment_interval: Optional[str]
    measurement_date: datetime
    final_volume:     float

class ConsumptionStats(BaseModel):
    registered_avg:    float   # promedio mensual registrado
    projected_avg:     float   # promedio mensual proyectado (IA)
    variation_percent: float   # variación esperada

class ConsumptionDetail(BaseModel):
    measurement_id:    int
    property_id:       int
    property_name:     str
    lot_id:            int
    lot_name:          str
    # asumimos que tu modelo Lot no tiene tipo de cultivo; omitimos o ponemos Optional[str]
    registered_avg:    float
    projected_avg:     float
    variation_percent: float
    records:           List[ConsumptionRecord]


class LotConsumption(BaseModel):
    property_id: int
    property_name: str
    lot_id: int
    lot_name: str
    total_consumption: float
    billing_start_date: datetime | None
    billing_end_date: datetime | None

class ProjectedMonthlyAvg(BaseModel):
    projected_monthly_avg: Dict[int, float]  # mes (1-12) -> promedio proyectado

class UserLotConsumptionRecord(BaseModel):
    property_name: str
    lot_id: int
    lot_name: str
    payment_interval: Optional[str]
    measurement_date: datetime
    final_volume: float