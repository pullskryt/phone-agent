#!/data/data/com.termux/files/usr/bin/bash
# Настройка быстрого запуска Termux AI Agent командой "ai" или "ии"
set -e

AGENT_DIR="$(cd "$(dirname "$0")" && pwd)"
SHELL_RC="$HOME/.bashrc"

# если юзер сидит на zsh — используем .zshrc
if [ -n "$ZSH_VERSION" ] || [ "$(basename "$SHELL")" = "zsh" ]; then
    SHELL_RC="$HOME/.zshrc"
fi

touch "$SHELL_RC"

MARKER_START="# >>> termux-ai-agent >>>"
MARKER_END="# <<< termux-ai-agent <<<"

# убираем старую версию блока, если уже был установлен (чтобы не дублировать)
if grep -q "$MARKER_START" "$SHELL_RC" 2>/dev/null; then
    sed -i "/$MARKER_START/,/$MARKER_END/d" "$SHELL_RC"
fi

cat >> "$SHELL_RC" <<EOF
$MARKER_START
# Быстрый запуск AI-агента из любой директории командами "ai" и "ии"
# AI_AGENT_CWD передаёт агенту твою текущую папку, чтобы он читал/писал
# файлы именно там, откуда его позвали, а не в папке самого агента.
ai() {
    AI_AGENT_CWD="\$(pwd)" python "$AGENT_DIR/agent.py" "\$@"
}
alias ии='ai'
alias aibot='python "$AGENT_DIR/telegram_bot.py"'
$MARKER_END
EOF

echo "Готово! Команды 'ai', 'ии' и 'aibot' добавлены в $SHELL_RC"
echo ""
echo "Чтобы применить прямо сейчас, выполни:"
echo "  source $SHELL_RC"
echo ""
echo "После этого из любой папки в Termux можно писать:"
echo "  ai"
echo "  ии"
echo "  ai --provider local"
echo "  aibot          # запустить Telegram-бота (если настроен)"
