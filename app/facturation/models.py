from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    Float,
    Date,
    ForeignKey,
    DateTime,
    func,
    Table,
)
from sqlalchemy.orm import relationship
from app.database import Base


# Tabla de valores de estado (vars)
class Var(Base):
    __tablename__ = 'vars'

    id    = Column(Integer, primary_key=True, index=True)
    name  = Column(String, nullable=False)
    # Puedes agregar aquí los demás campos que tengas en vars


# Tabla de tipos de concepto
class ConceptType(Base):
    __tablename__ = 'concept_types'

    id   = Column(Integer, primary_key=True, index=True)
    name = Column(String(15), nullable=False, unique=True)


# Tabla de scopes (alcance)
class ScopeType(Base):
    __tablename__ = 'scope_types'

    id   = Column(Integer, primary_key=True, index=True)
    name = Column(String(10), nullable=False, unique=True)


class Property(Base):
    __tablename__ = 'property'

    id                            = Column(Integer, primary_key=True, index=True)
    name                          = Column(String(100), nullable=False)
    longitude                     = Column(Float,   nullable=False)
    latitude                      = Column(Float,   nullable=False)
    extension                     = Column(Float,   nullable=False)
    real_estate_registration_number = Column(Integer, nullable=False)
    public_deed                   = Column(String,  nullable=True)
    freedom_tradition_certificate = Column(String,  nullable=True)
    State = Column("State", Integer, ForeignKey("vars.id"), default=3, nullable=False)
    vars                          = relationship("Var", foreign_keys=[State])
    lots                          = relationship(
        "Lot",
        secondary="property_lot",
        back_populates="properties",
    )


class Lot(Base):
    __tablename__ = 'lot'

    id                             = Column(Integer, primary_key=True, index=True)
    name                           = Column(String, nullable=False)
    longitude                      = Column(Float, nullable=False)
    latitude                       = Column(Float, nullable=False)
    extension                      = Column(Float, nullable=False)
    real_estate_registration_number = Column(Integer, nullable=False)
    public_deed                    = Column(String, nullable=True)
    freedom_tradition_certificate  = Column(String, nullable=True)
    planting_date                  = Column(Date, nullable=True)
    estimated_harvest_date         = Column(Date, nullable=True)

    State = Column("State", Integer, ForeignKey("vars.id"), default=5, nullable=False)
    vars  = relationship("Var", foreign_keys=[State])
    properties                     = relationship(
        "Property",
        secondary="property_lot",
        back_populates="lots",
    )


# Tabla intermedia predio ↔ lote
class PropertyLot(Base):
    __tablename__ = 'property_lot'

    property_id = Column(Integer, ForeignKey('property.id'), primary_key=True)
    lot_id      = Column(Integer, ForeignKey('lot.id'),     primary_key=True)

# Tabla intermedia predio ↔ lote
class InvoiceConcept(Base):
    __tablename__ = 'invoice_concept'

    concept_id = Column(Integer, ForeignKey('concepts.id'), primary_key=True)
    invoice_id = Column(Integer, ForeignKey('invoice.id'),  primary_key=True)
    consumption_measurement_id = Column(Integer, ForeignKey('consumption_measurements.id'),  primary_key=True)
    total_amount = Column(Numeric(20, 2), nullable=False)



# (Opcional) Usuarios ↔ predios
class PropertyUser(Base):
    __tablename__ = 'user_property'

    property_id = Column(Integer, ForeignKey('property.id'), primary_key=True)
    user_id     = Column(Integer, ForeignKey('users.id'),    primary_key=True)


# Tabla principal de conceptos
class Concept(Base):
    __tablename__ = 'concepts'

    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(30), nullable=False)
    descripcion = Column(String(100), nullable=False)
    valor       = Column(Numeric(20, 2), nullable=False)

    scope_id    = Column(Integer, ForeignKey('scope_types.id'), nullable=False)
    tipo_id     = Column(Integer, ForeignKey('concept_types.id'), nullable=False)
    estado_id   = Column(Integer, ForeignKey('vars.id'),          nullable=False)
    predio_id   = Column(Integer, ForeignKey('property.id'),      nullable=True)
    lote_id     = Column(Integer, ForeignKey('lot.id'),           nullable=True)

    created_at  = Column(DateTime(timezone=False), server_default=func.now())
    updated_at  = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now()
    )

    # relaciones
    scope       = relationship('ScopeType')
    tipo        = relationship('ConceptType')
    estado      = relationship('Var',       foreign_keys=[estado_id])
    property    = relationship('Property',  foreign_keys=[predio_id])
    lot         = relationship('Lot',       foreign_keys=[lote_id])

class ConsumptionMeasurement(Base):
    __tablename__ = "consumption_measurements"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, nullable=False)
    final_volume = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relación con invoice
    invoice_id = Column(Integer, ForeignKey("invoice.id"), nullable=True)