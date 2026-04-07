FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    CHROME_EXTRA_ARGS="--no-sandbox --disable-dev-shm-usage --disable-gpu --single-process --no-zygote"
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    unzip \
    xvfb \
    # Chrome dependencies
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
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    # Robust Hotfix for Chrome 146+ KeyError/ValueError: 'privateNetworkRequestPolicy' inside zendriver
    # We wrap the from_json call in a conditional to skip it if the key is missing from the CDP event
    python3 -c "import re; p='/usr/local/lib/python3.11/site-packages/zendriver/cdp/network.py'; c=open(p).read(); open(p,'w').write(re.sub(r'PrivateNetworkRequestPolicy\.from_json\(\s*json\[\"privateNetworkRequestPolicy\"\]\s*\)', '(PrivateNetworkRequestPolicy.from_json(json[\"privateNetworkRequestPolicy\"]) if \"privateNetworkRequestPolicy\" in json else None)', c))" && \
    # Verify the patch and ensure no syntax errors were introduced
    python3 -m py_compile /usr/local/lib/python3.11/site-packages/zendriver/cdp/network.py && \
    grep "if \"privateNetworkRequestPolicy\" in json else None" /usr/local/lib/python3.11/site-packages/zendriver/cdp/network.py
COPY . .
CMD ["xvfb-run", "--auto-servernum", "--server-args=-screen 0 1280x800x24", "python", "main.py"]
