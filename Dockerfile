# Usa una imagen base liviana de Python
FROM python:3.11-slim

# Directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiamos los requisitos primero para aprovechar la cache de Docker
COPY requirements.txt .

# Instalamos dependencias (solo una vez al build)
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el código del daemon
COPY . .

# Comando por defecto del contenedor
CMD ["python", "-u","daemon.py"]
