# ── Base: Python 3.11 slim (Debian Bookworm) ──────────────────────────────
FROM python:3.11-slim

# Evitar prompts interactivos durante apt
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# ── Dependencias del sistema + Google Chrome oficial ──────────────────────
RUN apt-get update -qq && apt-get install -y -qq \
    wget \
    gnupg \
    ca-certificates \
    curl \
    unzip \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgdk-pixbuf2.0-0 \
    libnspr4 \
    libnss3 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    xdg-utils \
    --no-install-recommends \
 && rm -rf /var/lib/apt/lists/*

# Instalar Google Chrome estable desde los repositorios oficiales de Google
RUN wget -q -O /tmp/chrome.deb \
      https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
 && apt-get update -qq \
 && apt-get install -y -qq /tmp/chrome.deb \
 && rm /tmp/chrome.deb \
 && rm -rf /var/lib/apt/lists/* \
 && google-chrome-stable --version

# ── Instalar chromedriver que coincida con la versión de Chrome ───────────
# webdriver-manager lo descargará automáticamente en el primer arranque,
# pero lo pre-cacheamos aquí para no tardar al iniciar el bot.
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && python -c "from webdriver_manager.chrome import ChromeDriverManager; ChromeDriverManager().install()" \
 && echo "✅ chromedriver pre-cacheado OK"

# ── Copiar el código del bot ───────────────────────────────────────────────
COPY . .

# ── Arrancar el bot ────────────────────────────────────────────────────────
CMD ["python", "bot.py"]
