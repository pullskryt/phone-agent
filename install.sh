#!/data/data/com.termux/files/usr/bin/bash
# Установка зависимостей для Termux AI Agent
set -e

echo "== Обновление пакетов =="
pkg update -y

echo "== Python =="
pkg install -y python

echo "== Установка storage-доступа (чтобы агент видел /sdcard при желании) =="
termux-setup-storage || true

echo "== (опционально) llama.cpp для локальных моделей =="
echo "Если хочешь гонять модели локально — раскомментируй установку ниже"
echo "или собери llama.cpp вручную: pkg install cmake git && git clone https://github.com/ggerganov/llama.cpp"
# pkg install -y llama-cpp   # если пакет доступен в репе termux — проверь: pkg search llama-cpp

echo "== Настройка команд ai / ии =="
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
bash "$SCRIPT_DIR/setup_alias.sh"

echo ""
echo "== Готово =="
echo "1. Впиши свой API-ключ в config.json (поле api.api_key)"
echo "2. Выполни: source ~/.bashrc   (или перезапусти Termux)"
echo "3. Дальше просто пиши из любой папки:  ai   или   ии"
echo "   Для локального режима: ai --provider local (нужен запущенный llama-server)"
