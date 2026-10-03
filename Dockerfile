FROM node:24-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RUNBOOKOPS_ROOT=/app
WORKDIR /app
COPY pyproject.toml ./
COPY backend/ ./backend/
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 appuser
COPY data/ ./data/
COPY reports/ ./reports/
COPY --from=web /web/dist ./frontend/dist
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"
CMD ["python", "-m", "uvicorn", "runbookops.api:app", "--host", "0.0.0.0", "--port", "8000"]
