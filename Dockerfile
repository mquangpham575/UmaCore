FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive
# Install Google Chrome .deb with deps pre-installed.
# Debian chromium gets blocked by Cloudflare Turnstile on ChronoGenesis.
# slim-bookworm can't resolve Chrome deps in one shot, so we install them first.
RUN apt-get update && apt-get install -y \
    wget gnupg curl unzip xvfb xdg-utils \
    fonts-liberation libasound2 libatk-bridge2.0-0 libatk1.0-0 \
    libatspi2.0-0 libcairo2 libcups2 libcurl4 libdbus-1-3 \
    libexpat1 libgbm1 libglib2.0-0 libgtk-3-0 libnspr4 libnss3 \
    libpango-1.0-0 libudev1 libvulkan1 libx11-6 libxcb1 \
    libxcomposite1 libxdamage1 libxext6 libxfixes3 libxkbcommon0 \
    libxrandr2 \
    && wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && dpkg -i ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    # Hotfix for Chrome 146+: privateNetworkRequestPolicy can be missing or None
    # Replace the from_json call to handle both cases safely
    python3 -c "\
import re; \
p='/usr/local/lib/python3.11/site-packages/zendriver/cdp/network.py'; \
c=open(p).read(); \
c=re.sub( \
    r'private_network_request_policy\s*=\s*PrivateNetworkRequestPolicy\.from_json\(\s*json\[.privateNetworkRequestPolicy.\]\s*\)', \
    'private_network_request_policy=(PrivateNetworkRequestPolicy.from_json(json[\"privateNetworkRequestPolicy\"]) if json.get(\"privateNetworkRequestPolicy\") is not None else None)', \
    c); \
open(p,'w').write(c)" && \
    python3 -m py_compile /usr/local/lib/python3.11/site-packages/zendriver/cdp/network.py
COPY . .
# Run with virtual display (xvfb)
CMD xvfb-run --auto-servernum --server-args="-screen 0 1280x800x24" python main.py
