FROM python:3.11-slim

# Evita generar archivos .pyc y fuerza salida sin búfer para ver logs en vivo
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala compiladores y librerías C necesarias para compilar dependencias
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia e instala primero requirements para aprovechar la caché de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copia el resto del código del repositorio
COPY . .

# Expone el puerto de la API FastAPI
EXPOSE 8000

# Comando para ejecutar FastAPI usando uvicorn
CMD ["uvicorn", "src.api.api:app", "--host", "0.0.0.0", "--port", "8000"]