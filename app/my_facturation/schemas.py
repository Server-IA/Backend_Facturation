# my_facturation/schemas.py

from pydantic import BaseModel
from datetime import date
from typing import Optional

class UserInvoice(BaseModel):
    invoice_id:      int
    reference_code:  str
    property_id:     int
    lot_id:          int
    payment_interval: Optional[str]
    expiration_date: date
    total_amount:    float
    status:          str

    class Config:
        orm_mode = True
