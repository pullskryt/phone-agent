#!/data/data/com.termux/files/usr/bin/bash
# Быстро поднять Ollama сервер в фоне (после перезапуска Termux сессии).
set -e

if pgrep -f "ollama serve" > /dev/null; then
    echo "Ollama сервер уже запущен."
else
    echo "Запускаю Ollama сервер в фоне..."
    nohup ollama serve > "$HOME/.ollama-server.log" 2>&1 &
    sleep 2
    echo "Готово. Лог: ~/.ollama-server.log"
fi

echo ""
echo "Теперь можно запускать: ai --provider local"
