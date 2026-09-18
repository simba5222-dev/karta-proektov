#!/bin/bash
# Собрать карту и выложить её в /var/www/karta. Запускать из каталога проекта.
set -e
cd "$(dirname "$0")"
python3 build.py
python3 build_mindmap.py
for f in index.html mindmap.html; do
    sudo cp "$f" "/var/www/karta/$f"
    sudo chown root:www-data "/var/www/karta/$f"
    sudo chmod 644 "/var/www/karta/$f"
done
echo "выложено: https://72-56-25-105.nip.io/karta/ (и /karta/mindmap.html)"
