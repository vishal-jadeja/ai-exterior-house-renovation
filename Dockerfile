# Hugging Face Space image (Docker Spaces need the Dockerfile at the repo root).
# Same as infra/Dockerfile.api but listens on 7860 and runs api + worker in one container.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/tmp/models PORT=7860
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 fonts-dejavu-core curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY apps/api/pyproject.toml ./
RUN pip install --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple torch torchvision
COPY apps/api/app ./app
RUN pip install ".[ml,report]"
COPY apps/api/ ./
COPY seed /srv/seed
COPY infra/space-entrypoint.sh /srv/entrypoint.sh
ENV SEED_DIR=/srv/seed
RUN mkdir -p /tmp/models && useradd -m -u 1000 app && chown -R app:app /srv /tmp/models
USER app
EXPOSE 7860
CMD ["sh", "/srv/entrypoint.sh"]
