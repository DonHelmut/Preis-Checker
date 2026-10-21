FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && playwright install chromium
COPY preischecker ./preischecker
ENV PREISCHECKER_CONFIG=/app/config.yaml PREISCHECKER_DATA=/app/data TZ=Europe/Berlin
EXPOSE 8080
CMD ["python", "-m", "preischecker", "serve"]
