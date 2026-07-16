#!/data/data/com.termux/files/usr/bin/bash
# Установка локального AI (Ollama) для Termux AI Agent — без ручной сборки.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

C_ACCENT='\033[38;5;51m'
C_BOLD='\033[1m'
C_GRAY='\033[90m'
C_RESET='\033[0m'

box() {
    local text="$1"
    local width=50
    echo -e "${C_ACCENT}╭$(printf '─%.0s' $(seq 1 $((width-2))))╮${C_RESET}"
    local padded
    padded=$(python3 -c "
import sys
text = sys.argv[1]
width = int(sys.argv[2]) - 4
pad = max(width - len(text), 0)
print(text + ' ' * pad)
" "$text" "$width")
    echo -e "${C_ACCENT}│${C_RESET} ${C_BOLD}${padded}${C_RESET} ${C_ACCENT}│${C_RESET}"
    echo -e "${C_ACCENT}╰$(printf '─%.0s' $(seq 1 $((width-2))))╯${C_RESET}"
}

step() {
    echo -e "\n${C_ACCENT}▸${C_RESET} ${C_BOLD}$1${C_RESET}"
}

box "Локальная модель — установка Ollama"

step "Обновление пакетов"
pkg update -y > /dev/null 2>&1
echo -e "${C_GRAY}готово${C_RESET}"

step "Установка Ollama"
pkg install -y ollama > /dev/null 2>&1
echo -e "${C_GRAY}готово${C_RESET}"

step "Запуск Ollama сервера в фоне"
nohup ollama serve > "$HOME/.ollama-server.log" 2>&1 &
sleep 3
echo -e "${C_GRAY}готово${C_RESET}"

# ---- Явно отделяем момент, где нужен ввод — чтобы не выглядело зависанием ----
echo ""
box "Выбор модели — нужен твой ввод"
echo -e "${C_GRAY}qwen2.5:1.5b   — самая лёгкая, ~1.2GB, для слабых телефонов${C_RESET}"
echo -e "${C_GRAY}qwen2.5:3b     — баланс скорости/качества, ~2GB (по умолчанию)${C_RESET}"
echo -e "${C_GRAY}qwen2.5:7b     — только если у телефона 8GB+ RAM${C_RESET}"
echo ""
read -p "Имя модели [qwen2.5:3b]: " MODEL_NAME
MODEL_NAME=${MODEL_NAME:-qwen2.5:3b}

step "Скачиваю $MODEL_NAME (может занять несколько минут)"
ollama pull "$MODEL_NAME"
echo -e "${C_GRAY}готово${C_RESET}"

python3 - "$SCRIPT_DIR/config.json" "$MODEL_NAME" << 'PYEOF'
import json, sys
config_path, model_name = sys.argv[1], sys.argv[2]
with open(config_path) as f:
    cfg = json.load(f)
cfg["local"]["model"] = model_name
cfg["local"]["server_url"] = "http://127.0.0.1:11434/v1/chat/completions"
with open(config_path, "w") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
PYEOF

echo ""
box "Готово!"
echo -e "Ollama сервер уже запущен в фоне (лог: ~/.ollama-server.log)."
echo -e "Запусти агента в локальном режиме: ${C_ACCENT}ai --provider local${C_RESET}"
echo ""
echo -e "${C_GRAY}Если перезапустишь Termux, сервер погаснет — подними заново:${C_RESET}"
echo -e "  ${C_ACCENT}bash $SCRIPT_DIR/local_start.sh${C_RESET}"
