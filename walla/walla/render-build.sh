#!/usr/bin/env bash
# Script de construcción para Render Native Python
set -o errexit

STORAGE_DIR=/opt/render/project/.render

if [[ ! -d $STORAGE_DIR/chrome ]]; then
  echo "...Descargando e instalando Chrome/Chromium en Render..."
  mkdir -p $STORAGE_DIR/chrome
  cd $STORAGE_DIR/chrome
  wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  dpkg -x google-chrome-stable_current_amd64.deb .
  rm google-chrome-stable_current_amd64.deb
  cd /opt/render/project/src
else
  echo "...Chrome ya se encuentra en caché..."
fi

# Instalar dependencias Python
pip install --upgrade pip
pip install -r requirements.txt
