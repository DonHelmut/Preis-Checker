FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 TZ=Europe/Berlin PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /root/.cache
COPY preischecker ./preischecker
COPY config.example.yaml .
ENV PREISCHECKER_CONFIG=/app/config/config.yaml PREISCHECKER_DATA=/app/data
EXPOSE 8080
CMD ["python", "-m", "preischecker", "serve"]
