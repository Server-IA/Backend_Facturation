import requests
from fastapi import HTTPException

def get_altitude(lat: float, lon: float) -> float:
    """
    Obtiene altitud (m) a partir de latitud/longitud.
    Usa Open-Elevation (gratuito, sin API key).
    """
    try:
        resp = requests.get(
            "https://api.open-elevation.com/api/v1/lookup",
            params={"locations": f"{lat},{lon}"},
            timeout=5
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return 0.0
        return float(results[0].get("elevation", 0.0))
    except Exception as e:
        # En caso de falla, retornamos 0.0
        return 0.0


def get_weather_data(lat: float, lon: float) -> dict:
    """
    Obtiene datos meteorológicos para lat/lon usando Open-Meteo:
      - temp: temperatura en °C
      - humidity: humedad relativa en %
      - rain: precipitación en mm (última hora)
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,relativehumidity_2m,precipitation",
        "timezone": "UTC"
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error al obtener clima (Open-Meteo): {e}"
        )

    data = resp.json().get("hourly", {})
    temps = data.get("temperature_2m", [])
    hums = data.get("relativehumidity_2m", [])
    rains = data.get("precipitation", [])

    # Tomar el último registro horario disponible
    temp = float(temps[-1]) if temps else 0.0
    humidity = float(hums[-1]) if hums else 0.0
    rain = float(rains[-1]) if rains else 0.0

    return {"temp": temp, "humidity": humidity, "rain": rain}
