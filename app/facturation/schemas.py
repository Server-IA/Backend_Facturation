from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

class ConceptTypeOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}

class ScopeTypeOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}

class VarOut(BaseModel):
    id: int

    model_config = {"from_attributes": True}

class PropertyOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}

class LotOut(BaseModel):
    id: int
    name: str
    property: PropertyOut

    model_config = {"from_attributes": True}

class ConceptBase(BaseModel):
    nombre:      str     = Field(..., max_length=30)
    descripcion: str     = Field(..., max_length=100)
    valor:       Decimal = Field(..., gt=0)
    scope_id:    int
    tipo_id:     int
    predio_id:   Optional[int] = None
    lote_id:     Optional[int] = None

class ConceptCreate(BaseModel):
    nombre:      str     = Field(..., max_length=30)
    descripcion: str     = Field(..., max_length=100)
    valor:       Decimal = Field(..., gt=0)
    scope_id:    int
    tipo_id:     int
    predio_id:   Optional[int] = None
    lote_id:     Optional[int] = None

    model_config = {"from_attributes": True}

class ConceptUpdate(BaseModel):
    nombre: str = Field(..., max_length=30)
    descripcion: str = Field(..., max_length=100)
    valor: Decimal = Field(..., gt=0)
    scope_id: int
    tipo_id: int
    predio_id: Optional[int] = None
    lote_id: Optional[int] = None

    model_config = {"from_attributes": True}

class ConceptUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=30)
    descripcion: Optional[str] = Field(None, max_length=100)
    valor: Optional[Decimal] = Field(None, gt=0)
    scope_id: Optional[int]
    tipo_id: Optional[int]
    predio_id: Optional[int]
    lote_id: Optional[int]

class ConceptOut(BaseModel):
    id: int
    nombre: str
    descripcion: str
    valor: Decimal
    scope_id: int
    tipo_id: int
    estado_id: int
    predio_id: Optional[int]
    lote_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    scope: ScopeTypeOut
    tipo: ConceptTypeOut
    # etc...
    model_config = {"from_attributes": True}

class PredictInput(BaseModel):
    Temperatura: float = Field(..., example=25.3)
    Humedad: float = Field(..., example=45.2)
    Altitud: float = Field(..., example=1200.0)
    AreaCultivo: float = Field(..., example=1.5)
    TipoCultivo: str = Field(..., example="cafe")
    TipoTierra: str = Field(..., example="arenosa")
    lot_id: Optional[int] = Field(None, description="Para calcular histórico")

    model_config = {"from_attributes": True}


class ConceptResponse(BaseModel):
    success: bool
    data: ConceptOut

    model_config = {"from_attributes": True}
    

class PredictByLot(BaseModel):
    lot_id: int

class ConsumptionPredictionOut(BaseModel):
    prediccion_consumo_base: float
    promedio_historico_consumo: float
    prediccion_lluvia_mm: float
    factor_ajuste_por_clase: float
    consumo_ajustado_final: float

    class Config:
        orm_mode = True