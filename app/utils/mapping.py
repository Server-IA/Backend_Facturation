# app/utils/mapping.py

def crop_to_soil_type(crop_name: str) -> str:
    """
    Mapea el nombre del cultivo a uno de los valores que el modelo IA acepta.
    """
    mapping = {
        "cafe":      "arenosa",
        "trigo":     "arcillosa",
        "maiz":      "franca",
        "soja":      "limosa",
        # añade aquí todos los que tu modelo maneje...
    }
    return mapping.get(crop_name.lower(), "arenosa")
