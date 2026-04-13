FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive
# Install dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-liberation \
    fonts-noto-color-emoji \
    xvfb \
    xdg-utils \
    libgbm1 \
    && ln -s /usr/bin/chromium /usr/bin/google-chrome \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
# Explicitly install critical dependencies to bypass any requirements.txt sync issues
RUN pip install --no-cache-dir httpx undetected-chromedriver zendriver discord.py asyncpg python-dotenv
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Run with virtual display (xvfb)
CMD xvfb-run --auto-servernum --server-args="-screen 0 1280x800x24" python main.py
