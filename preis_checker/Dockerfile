# Wird von GitHub Actions gebaut (.github/workflows/addon-image.yml) und als fertiges Image
# bereitgestellt. Home Assistant lädt es nur herunter, baut nichts selbst → keine Reste beim Update.
# Build-Kontext ist das Repo-Wurzelverzeichnis: docker build -f preis_checker/Dockerfile .
FROM python:3.12-slim-bookworm
ARG BUILD_VERSION=dev
ARG BUILD_ARCH=amd64
LABEL io.hass.type="addon" io.hass.version="${BUILD_VERSION}" io.hass.arch="${BUILD_ARCH}" \
      org.opencontainers.image.source="https://github.com/DonHelmut/Preis-Checker"
ENV PYTHONUNBUFFERED=1 TZ=Europe/Berlin PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /root/.cache
COPY preischecker ./preischecker
ENV PREISCHECKER_CONFIG=/data/config.yaml PREISCHECKER_DATA=/data
CMD ["python", "-m", "preischecker", "serve"]
