FROM node:24-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
# Apply the distro security fix even while the upstream image tag lags its archive.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends --only-upgrade zlib1g \
    && dpkg-query -W zlib1g \
    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' zlib1g)" ge '1:1.3.dfsg+really1.3.1-1+deb13u1' \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RUNBOOKOPS_ROOT=/app
WORKDIR /app
COPY pyproject.toml ./
COPY backend/ ./backend/
RUN python -m pip install --no-cache-dir --upgrade pip==26.2.1 \
    && python -m pip install --no-cache-dir . \
    && python -m pip uninstall --yes pip \
    && useradd --create-home --uid 10001 appuser
COPY data/ ./data/
COPY reports/ ./reports/
COPY --from=web /web/dist ./frontend/dist
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"
CMD ["python", "-m", "uvicorn", "runbookops.api:app", "--host", "0.0.0.0", "--port", "8000"]
