# Baut das Add-on aus dem aktuellen main-Branch des Repos.
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 TZ=Europe/Berlin PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
ADD https://github.com/DonHelmut/Preis-Checker/archive/refs/heads/main.tar.gz /tmp/src.tar.gz
RUN tar xzf /tmp/src.tar.gz --strip-components=1 -C /app \
    && rm /tmp/src.tar.gz \
    && pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /root/.cache
ENV PREISCHECKER_CONFIG=/data/config.yaml PREISCHECKER_DATA=/data
CMD ["python", "-m", "preischecker", "serve"]
