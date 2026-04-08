FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive
# Install Google Chrome (same as GitHub Actions ubuntu-latest) instead of Debian chromium.
# Debian chromium gets blocked by Cloudflare Turnstile on ChronoGenesis.
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    unzip \
    xvfb \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*
# Add Google Chrome APT repo and install stable
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*
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
