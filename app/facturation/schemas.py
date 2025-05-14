# schemas.py
from pydantic import BaseModel, Field
from typing    import Optional, List
from datetime  import datetime
from decimal   import Decimal


class ConceptTypeOut(BaseModel):
    id:   int
    name: str

    model_config = {"from_attributes": True}


class ScopeTypeOut(BaseModel):
    id:   int
    name: str

    model_config = {"from_attributes": True}


class VarOut(BaseModel):
    id: int

    model_config = {"from_attributes": True}


class PropertyOut(BaseModel):
    id:   int
    name: str

    model_config = {"from_attributes": True}


class LotOut(BaseModel):
    id:   int
    name: str
    property: PropertyOut

    model_config = {"from_attributes": True}


class ConceptBase(BaseModel):
    nombre:      str     = Field(..., max_length=30)
    descripcion: str     = Field(..., max_length=100)
    valor:       Decimal = Field(..., gt=0)
    scope_id:    int
    tipo_id:     int
    estado_id:   int
    predio_id:   Optional[int] = None
    lote_id:     Optional[int] = None


class ConceptCreate(ConceptBase):
    pass


class ConceptUpdate(BaseModel):
    nombre:      Optional[str]     = Field(None, max_length=30)
    descripcion: Optional[str]     = Field(None, max_length=100)
    valor:       Optional[Decimal] = Field(None, gt=0)
    scope_id:    Optional[int]
    tipo_id:     Optional[int]
    estado_id:   Optional[int]
    predio_id:   Optional[int]
    lote_id:     Optional[int]


class ConceptOut(ConceptBase):
    id:         int
    created_at: datetime
    updated_at: datetime
    scope:      ScopeTypeOut
    tipo:       ConceptTypeOut
    estado:     VarOut
    property:   Optional[PropertyOut] = None
    lot:        Optional[LotOut]      = None

    model_config = {"from_attributes": True}



class PredictInput(BaseModel):
    Temperatura:  float   = Field(..., example=25.3)
    Humedad:      float   = Field(..., example=45.2)
    Altitud:      float   = Field(..., example=1200.0)
    AreaCultivo:  float   = Field(..., example=1.5)
    TipoCultivo:  str     = Field(..., example="cafe")
    TipoTierra:   str     = Field(..., example="arenosa")
    lot_id:       Optional[int] = Field(None, description="Para calcular histórico")

    model_config = {"from_attributes": True}