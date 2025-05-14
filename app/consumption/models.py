# app/consumption/models.py

from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, Date
from sqlalchemy.orm import relationship
from app.database import Base




# Reusamos Lot, PropertyLot, PaymentInterval y Request de facturation
