#!/bin/bash
# Собрать карту и выложить её в /var/www/karta. Запускать из каталога проекта.
set -e
cd "$(dirname "$0")"
python3 build.py
sudo cp index.html /var/www/karta/index.html
sudo chown root:www-data /var/www/karta/index.html
sudo chmod 644 /var/www/karta/index.html
echo "выложено: http://72.56.25.105/karta/"
