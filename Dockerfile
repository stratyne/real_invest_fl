FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2, lxml, Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libxml2-dev libxslt1-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --upgrade pip && pip install -e .

# Playwright browser (Chromium only)
RUN playwright install chromium --with-deps

COPY . .

EXPOSE 8000
