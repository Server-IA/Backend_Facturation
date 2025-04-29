from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from app.facturation.models import Vars

class FacturationService:
    def __init__(self, db: Session):
        self.db = db
    
    def get_facturation(self):
        """Obtener todos los facturacion"""
        try:
            # Obtener todos los facturacions con el query
            facturation = self.db.query(Vars).all()

            if not facturation:
                return JSONResponse(
                    status_code=404,
                    content={
                        "success": False,
                        "data": {
                            "title": "Facturacion",
                            "message": "No se encontraron facturacion."
                        }
                    }
                )

            # Convertir la respuesta a un formato JSON válido
            facturation_data = jsonable_encoder(facturation)

            return JSONResponse(
                status_code=200,
                content={"success": True, "data": facturation_data}
            )
        except Exception as e:
            # Aquí capturamos cualquier excepción inesperada
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "data": {
                        "title": "Error al obtener facturacion",
                        "message": f"Ocurrió un error al intentar obtener los facturacion: {str(e)}"
                    }
                }
            )