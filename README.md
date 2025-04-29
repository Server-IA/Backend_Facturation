# DisRiego_IoT

Este repositorio contiene el backend de **DisRiego**. La arquitectura está basada en **Python** y se estructura en microservicios. Este documento guía al equipo desde la instalación del entorno de desarrollo, la ejecución de tests y el despliegue, hasta la integración con Docker y CI/CD.

---

## 1. Organización del Repositorio y Ramas

- **Ramas Principales:**
  - **develop:** Rama de desarrollo activa.
  - **test:** Rama para integración y pruebas.
  - **main:** Rama de producción.

- **Flujo de Trabajo:**
  1. Desarrollo en `develop`.
  2. Una vez estabilizado, se realiza merge a `test` para ejecutar pruebas exhaustivas.
  3. Finalmente, se fusiona `test` en `main` para el despliegue en producción.

---

## 2. Configuración del Entorno Local

### Requisitos
- [Visual Studio Code](https://code.visualstudio.com/) u otro IDE de preferencia.
- Python 3 (recomendado virtualenv o pipenv para gestión de entornos).
- Docker y Docker Compose instalados.

### Pasos

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/DisRiego/Backed_IoT
   cd Backed_IoT
   ```

2. **Crear y activar el entorno virtual:**
   ```bash
   python3 -m venv env
   source env/bin/activate  # En Windows: env\Scripts\activate
   ```

3. **Instalar Dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar Variables de Entorno:**
   - Copia el archivo `.env.example` a `.env` y ajusta los valores.
   - Ejemplo:
     ```dotenv
     DATABASE_URL=postgres://youruser:yourpassword@db:5432/yourdb
     API_KEY=tu_api_key
     SECRET_KEY=super_secret_key
     ```

5. **Levantamiento del Entorno con Docker Compose:**
   - Ejecuta:
     ```bash
     docker-compose up
     ```
   - Esto levantará el contenedor del backend (microservicios en Python) y un contenedor de PostgreSQL para el desarrollo local.

6. **Ejecución de Tests:**
   - Ejecuta los tests locales (por ejemplo, usando pytest):
     ```bash
     pytest
     ```

---

## 3. Contenerización con Docker

### Dockerfile

Ejemplo de Dockerfile para un microservicio en Python:
```dockerfile
# Dockerfile para un microservicio del backend
FROM python:3.9-slim

WORKDIR /app

# Copiar y instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Exponer el puerto (modificar según sea necesario)
EXPOSE 8000

# Variable de entorno para producción
ENV ENV=production

# Comando para iniciar el servicio
CMD ["python", "app.py"]
```

### Docker Compose

Archivo `docker-compose.yml` para levantar el backend y PostgreSQL:
```yaml
version: '3.8'
services:
  backend:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      - db
  db:
    image: postgres:latest
    restart: always
    environment:
      POSTGRES_USER: youruser
      POSTGRES_PASSWORD: yourpassword
      POSTGRES_DB: yourdb
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

---

## 4. Integración de CI/CD con GitHub Actions

### Flujo de CI/CD

- **CI:**  
  - Se ejecutan tests (por ejemplo, con pytest) en cada push o Pull Request en `develop` y `test`.
- **CD:**  
  - Al fusionar en `main`, se despliega automáticamente en Render u otro servicio de hosting para backend.

### Ejemplo de Workflow (archivo `.github/workflows/ci-cd.yml`):
```yaml
name: CI/CD Backend

on:
  push:
    branches: [develop, test, main]
  pull_request:
    branches: [develop, test, main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Build Docker Image
        run: docker build -t disriego-backend .
      - name: Run Tests
        run: docker run --env-file .env disriego-backend pytest

  deploy:
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Deploy to Render
        run: echo "Desplegando a Render..."
```

---

## 5. Consideraciones Finales

- **Variables Sensibles:**  
  - Utiliza GitHub Secrets y configura las variables en el panel de Render.
- **Actualización:**  
  - Este README se actualizará conforme se presenten cambios o imprevistos.
- **Soporte:**  
  - Para dudas, abre un issue en el repositorio o contacta al líder del equipo.

¡Manos a la obra con el backend de DisRiego!
