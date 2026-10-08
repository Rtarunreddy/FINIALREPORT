# Web service image: FastAPI + built frontend + LibreOffice for server-side PDF export.
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
# Metric-compatible fonts keep line breaks close to Word: Liberation (Arial/Times/Courier), Carlito (Calibri), Caladea (Cambria).
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-writer fonts-liberation fonts-crosextra-carlito fonts-crosextra-caladea fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements-cloud.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt -r backend/requirements-cloud.txt
COPY backend backend
COPY --from=web /web/dist frontend/dist
RUN useradd --create-home app && mkdir -p backend/data && chown -R app /app
USER app
WORKDIR /app/backend
ENV PORT=8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
