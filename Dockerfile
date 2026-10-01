FROM python:3.12-slim

WORKDIR /code

# Instalamos dependencias primero: Docker cachea esta capa y no
# reinstala todo cada vez que cambiamos el código.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
