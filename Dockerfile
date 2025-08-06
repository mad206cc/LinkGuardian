FROM python:3.12-slim

# Installer les dépendances système nécessaires pour compiler certains paquets
RUN apt-get update && apt-get install -y \
    gcc \
    build-essential \
    libffi-dev \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Définir le répertoire de travail
WORKDIR /app

# Copier les fichiers
COPY . /app

# Installer les dépendances Python
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Exposer le port
EXPOSE 5000

# Lancer l'application
CMD ["python", "app.py", "runserver", "--host=0.0.0.0"]