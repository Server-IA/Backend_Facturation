# my_facturation/schemas.py

from pydantic import BaseModel
from datetime import date
from typing import Optional

class UserInvoice(BaseModel):
    invoice_id: int
    reference_code: str
    property_id: int
    property_name: str               
    lot_id: int
    lot_name: str                    
    payment_interval: str
    payment_days: int
    expiration_date: date
    issuance_date: date
    total_amount: float
    status: str
    pdf_url: Optional[str]
    document_number: int
    invoiced_period: int

    model_config = {"from_attributes": True}