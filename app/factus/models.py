from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoice.id"), nullable=True)
    reference_code = Column(String(50), index=True)
    transaction_id = Column(String(50))
    payment_method = Column(String(20))  # Ej: PSE
    status = Column(String(20))  # Aprobado, Rechazado, Pendiente
    amount = Column(Numeric(12, 2))
    currency = Column(String(5))
    payer_email = Column(String(100))
    paid_at = Column(DateTime, default=datetime.utcnow)

    invoice = relationship("Invoice", backref="payments")
