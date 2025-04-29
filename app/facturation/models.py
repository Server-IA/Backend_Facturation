from sqlalchemy import TIMESTAMP, Column, Date, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Vars(Base):
    __tablename__ = 'vars'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
