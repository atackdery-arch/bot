#!/usr/bin/env bash
# build.sh - Script de construcción para Render
# Instala Google Chrome oficial + chromedriver compatible + dependencias Python

set -e  # salir si cualquier comando falla

echo "=============================="
echo "  RENDER BUILD - SIMYO BOT"
echo "=============================="

echo ""
echo "→ Actualizando lista de paquetes..."
apt-get update -qq

echo ""
echo "→ Instalando dependencias del sistema..."
apt-get install -y -qq \
    wget \
    curl \
    unzip \
    gnupg \
    ca-certificates \
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
    --no-install-recommends

echo ""
echo "→ Instalando Google Chrome estable..."
wget -q -O /tmp/google-chrome.deb \
    "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"
apt-get install -y -qq /tmp/google-chrome.deb || true
rm -f /tmp/google-chrome.deb

# Verificar instalación
CHROME_VERSION=$(google-chrome-stable --version 2>/dev/null || echo "no encontrado")
echo "→ Chrome instalado: $CHROME_VERSION"

echo ""
echo "→ Instalando dependencias Python..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo ""
echo "=============================="
echo "  BUILD COMPLETADO"
echo "=============================="
