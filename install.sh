#!/data/data/com.termux/files/usr/bin/bash
# Единый установщик Termux AI Agent — ставит всё нужное за один прогон.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ---- Оформление (тот же циан-акцент, что и в самом агенте) ----
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

clear
box "Termux AI Agent — установка"
echo ""

step "Обновление пакетов"
pkg update -y > /dev/null 2>&1
echo -e "${C_GRAY}готово${C_RESET}"

step "Python"
pkg install -y python > /dev/null 2>&1
echo -e "${C_GRAY}готово${C_RESET}"

step "Доступ к файлам (storage)"
termux-setup-storage > /dev/null 2>&1 || true
echo -e "${C_GRAY}готово${C_RESET}"

step "Папка для проектов (~/Projects)"
mkdir -p "$HOME/Projects"
echo -e "${C_GRAY}готово${C_RESET}"

step "Команды ai / ии"
bash "$SCRIPT_DIR/setup_alias.sh" > /dev/null 2>&1
echo -e "${C_GRAY}готово${C_RESET}"

# ---- Выбор облачного сервиса ----
echo ""
box "Облачный сервис (API)"
echo -e "${C_GRAY}1) Groq — рекомендуется, есть бесплатный тир${C_RESET}"
echo -e "${C_GRAY}2) Другой OpenAI-совместимый сервис (свой URL)${C_RESET}"
echo -e "${C_GRAY}3) Пропустить, настрою вручную позже${C_RESET}"
read -p "Выбор [1]: " SERVICE_CHOICE
SERVICE_CHOICE=${SERVICE_CHOICE:-1}

API_KEY=""
BASE_URL="https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME="openai/gpt-oss-120b"

if [ "$SERVICE_CHOICE" = "1" ]; then
    echo -e "${C_GRAY}Ключ: https://console.groq.com/keys${C_RESET}"
    read -p "Вставь API-ключ: " API_KEY
    echo -e "${C_GRAY}Модели: openai/gpt-oss-120b (по умолчанию), openai/gpt-oss-20b, qwen/qwen3.6-27b${C_RESET}"
    read -p "Модель [openai/gpt-oss-120b]: " MODEL_INPUT
    MODEL_NAME=${MODEL_INPUT:-openai/gpt-oss-120b}

elif [ "$SERVICE_CHOICE" = "2" ]; then
    read -p "URL эндпоинта (…/v1/chat/completions): " BASE_URL
    read -p "API-ключ: " API_KEY
    read -p "Название модели: " MODEL_NAME

else
    echo -e "${C_GRAY}Пропущено — впиши вручную в config.json позже${C_RESET}"
fi

if [ -n "$API_KEY" ] || [ "$SERVICE_CHOICE" = "2" ]; then
    python3 - "$SCRIPT_DIR/config.json" "$API_KEY" "$BASE_URL" "$MODEL_NAME" << 'PYEOF'
import json, sys
config_path, api_key, base_url, model_name = sys.argv[1:5]
with open(config_path) as f:
    cfg = json.load(f)
if api_key:
    cfg["api"]["api_key"] = api_key
if base_url:
    cfg["api"]["base_url"] = base_url
if model_name:
    cfg["api"]["model"] = model_name
with open(config_path, "w") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
PYEOF
    echo -e "${C_GRAY}config.json обновлён${C_RESET}"
fi

# ---- Локальная модель ----
echo ""
box "Локальная модель (офлайн, бесплатно)"
read -p "Поставить через Ollama сейчас? (y/N): " WANT_LOCAL
if [ "$WANT_LOCAL" = "y" ] || [ "$WANT_LOCAL" = "Y" ]; then
    bash "$SCRIPT_DIR/local_setup.sh"
else
    echo -e "${C_GRAY}Пропущено — поставить позже: bash $SCRIPT_DIR/local_setup.sh${C_RESET}"
fi

# ---- Telegram-бот ----
echo ""
box "Telegram-бот (управлять агентом из чата)"
read -p "Настроить сейчас? (y/N): " WANT_TELEGRAM
TG_TOKEN=""
TG_IDS=""
if [ "$WANT_TELEGRAM" = "y" ] || [ "$WANT_TELEGRAM" = "Y" ]; then
    echo -e "${C_GRAY}1. Открой Telegram, напиши @BotFather, команда /newbot${C_RESET}"
    echo -e "${C_GRAY}2. Скопируй выданный токен сюда${C_RESET}"
    read -p "Токен бота: " TG_TOKEN
    echo ""
    echo -e "${C_GRAY}Узнать свой Telegram user_id можно у @userinfobot${C_RESET}"
    echo -e "${C_GRAY}Можно указать несколько ID через запятую (например: 111111,222222)${C_RESET}"
    read -p "Твой Telegram user_id: " TG_IDS

    if [ -n "$TG_TOKEN" ]; then
        python3 - "$SCRIPT_DIR/config.json" "$TG_TOKEN" "$TG_IDS" << 'PYEOF'
import json, sys
config_path, token, ids_raw = sys.argv[1], sys.argv[2], sys.argv[3]
with open(config_path) as f:
    cfg = json.load(f)
cfg.setdefault("telegram", {})
cfg["telegram"]["bot_token"] = token
ids = []
for part in ids_raw.replace(" ", "").split(","):
    if part.isdigit():
        ids.append(int(part))
cfg["telegram"]["allowed_user_ids"] = ids
with open(config_path, "w") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
print(f"Telegram настроен, разрешённые ID: {ids}")
PYEOF
    fi
else
    echo -e "${C_GRAY}Пропущено — настроить позже в config.json -> telegram, или запусти install.sh снова${C_RESET}"
fi

# ---- Готово ----
echo ""
box "Готово!"
echo -e "1. Выполни: ${C_ACCENT}source ~/.bashrc${C_RESET}   (или перезапусти Termux)"
echo -e "2. Дальше просто пиши из любой папки:  ${C_ACCENT}ai${C_RESET}   или   ${C_ACCENT}ии${C_RESET}"
if [ -n "$TG_TOKEN" ]; then
    echo -e "3. Запусти Telegram-бота: ${C_ACCENT}aibot${C_RESET}"
fi
echo ""
if [ -z "$API_KEY" ] && [ "$SERVICE_CHOICE" != "2" ]; then
    echo -e "${C_GRAY}Не забудь вписать API-ключ в config.json перед первым запуском.${C_RESET}"
fi
