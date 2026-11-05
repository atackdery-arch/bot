#!/usr/bin/env bash
# Script de build para Render Native Python Environment
set -o errexit

STORAGE_DIR=/opt/render/project/.render

if [[ ! -d $STORAGE_DIR/chrome ]]; then
  echo "...Descargando e instalando Google Chrome en Render..."
  mkdir -p $STORAGE_DIR/chrome
  cd $STORAGE_DIR/chrome
  wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  dpkg -x google-chrome-stable_current_amd64.deb .
  rm google-chrome-stable_current_amd64.deb
  cd /opt/render/project/src
else
  echo "...Usando Google Chrome desde cache..."
fi

# Instalar dependencias de Python
pip install --upgrade pip
pip install -r requirements.txt
