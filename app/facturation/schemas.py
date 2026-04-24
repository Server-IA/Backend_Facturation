from pydantic import BaseModel, Field
from typing import Optional, List, Literal
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


# =========================================================
# NUEVOS SCHEMAS RF-INT-34 / AAEF
# AGREGADOS AL FINAL SIN TOCAR LO EXISTENTE
# =========================================================

class AAEFTypeOut(BaseModel):
    Code: str
    Name: str


class AAEFRequestedPeriodOut(BaseModel):
    From: str
    To: str


class AAEFSourceSystemOut(BaseModel):
    SystemId: Optional[str] = None
    SystemName: Optional[str] = None
    SystemNIT: Optional[str] = None
    Environment: Optional[str] = None


class AAEFMetadataOut(BaseModel):
    ExchangeId: Optional[str] = None
    GeneratedAt: Optional[datetime] = None
    StandardVersion: Optional[str] = None
    RequestedPeriod: Optional[AAEFRequestedPeriodOut] = None
    SourceSystem: Optional[AAEFSourceSystemOut] = None
    GeneratedBy: Optional[str] = None


class AAEFThirdPartyOut(BaseModel):
    NIT: Optional[str] = None
    Name: Optional[str] = None
    Address: Optional[str] = None
    City: Optional[str] = None
    Country: Optional[str] = None
    Email: Optional[str] = None


class AAEFInvoiceHeaderOut(BaseModel):
    DocumentId: str
    Prefix: Optional[str] = None
    Serial: Optional[str] = None
    Type: AAEFTypeOut
    IssueDate: Optional[str] = None
    DueDate: Optional[str] = None
    Status: Optional[str] = None
    UpdatedAt: Optional[str] = None


class AAEFInvoiceTotalsOut(BaseModel):
    Subtotal: float
    TotalVAT: float = 0.0
    TotalWithholdings: float = 0.0
    TotalDiscounts: float = 0.0
    TotalPayment: float
    OutstandingBalance: float


class AAEFInvoiceLineOut(BaseModel):
    Code: Optional[str] = None
    Name: str
    Description: Optional[str] = None
    LineType: Optional[str] = None
    accounting_account: List[str] = Field(default_factory=list)
    Quantity: float = 1.0
    UnitPrice: float
    Value: float
    Taxes: List[dict] = Field(default_factory=list)


class AAEFInvoiceOut(BaseModel):
    Header: AAEFInvoiceHeaderOut
    ThirdParty: AAEFThirdPartyOut
    Totals: AAEFInvoiceTotalsOut
    Lines: List[AAEFInvoiceLineOut] = Field(default_factory=list)


class AAEFPaymentMethodOut(BaseModel):
    Code: Optional[str] = None


class AAEFTransactionOut(BaseModel):
    DocumentId: str
    Date: Optional[str] = None
    RelatedInvoiceId: str
    ThirdParty: AAEFThirdPartyOut
    Amount: float
    Currency: str = "COP"
    Status: str
    Notes: Optional[str] = None
    UpdatedAt: Optional[datetime] = None
    Type: AAEFTypeOut
    PaymentMethod: Optional[AAEFPaymentMethodOut] = None


class AAEFSummaryOut(BaseModel):
    TotalDocuments: int
    TotalInvoices: int
    TotalTransactions: int
    TotalGrossAmount: float
    TotalNet: float
    Currency: str = "COP"


class FacturationEconomicEventsResponse(BaseModel):
    metadata: Optional[AAEFMetadataOut] = None
    summary: AAEFSummaryOut
    invoices: List[AAEFInvoiceOut] = Field(default_factory=list)
    transactions: List[AAEFTransactionOut] = Field(default_factory=list)