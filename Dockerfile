# Usa Python 3.11 como imagen base
FROM python:3.11

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia los archivos del backend al contenedor
COPY . /app/

# Instala las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Expone el puerto 8001 para FastAPI
EXPOSE 8000

# Comando de inicio del backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
