# coding: utf-8
"""
Оформление вывода в терминале: цвета, рамки, спиннер, иконки.
Чистый ANSI, без внешних зависимостей — работает в Termux из коробки.
"""
import sys
import time
import threading
import shutil


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"

    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"
    BLUE = "\033[34m"
    GRAY = "\033[90m"
    WHITE = "\033[97m"

    BG_CYAN = "\033[46m"


# Иконка под каждый инструмент — чтобы визуально сразу было видно, что делает агент
TOOL_ICONS = {
    "read_file": "📖",
    "write_file": "✏️ ",
    "edit_file": "✂️ ",
    "list_dir": "📂",
    "bash_exec": "💻",
    "check_syntax": "🔍",
    "run_python": "🐍",
    "grep_search": "🔎",
    "delete_file": "🗑️ ",
    "web_fetch": "🌐",
}


def _term_width(default=60):
    try:
        return shutil.get_terminal_size((default, 20)).columns
    except Exception:
        return default


def _box_line(width, char="─"):
    return char * width


def header(text: str):
    width = min(_term_width(), 60)
    print(f"{C.CYAN}╭{_box_line(width - 2)}╮{C.RESET}")
    pad = width - 4 - len(text)
    pad = max(pad, 0)
    print(f"{C.CYAN}│{C.RESET} {C.BOLD}{C.WHITE}{text}{C.RESET}{' ' * pad} {C.CYAN}│{C.RESET}")
    print(f"{C.CYAN}╰{_box_line(width - 2)}╯{C.RESET}")


def user_prompt():
    return input(f"\n{C.BOLD}{C.GREEN}❯ {C.RESET}")


def assistant_reply(text: str):
    width = min(_term_width(), 60)
    print(f"\n{C.MAGENTA}┌{'─' * (width - 2)}{C.RESET}")
    for line in text.split("\n"):
        print(f"{C.MAGENTA}│{C.RESET} {line}")
    print(f"{C.MAGENTA}└{'─' * (width - 2)}{C.RESET}")


def tool_call(name: str, args_repr: str):
    icon = TOOL_ICONS.get(name, "⚙️ ")
    print(f"  {icon} {C.BLUE}{C.BOLD}{name}{C.RESET}{C.GRAY}({args_repr}){C.RESET}")


def tool_result_preview(result, max_lines=4, max_chars=300):
    """Короткое превью результата инструмента сразу под вызовом — видно, что реально произошло."""
    text = str(result)
    is_error = text.startswith("ERROR")
    color = C.RED if is_error else C.GRAY

    lines = text.split("\n")
    truncated_lines = len(lines) > max_lines
    preview_lines = lines[:max_lines]

    preview = "\n".join(preview_lines)
    if len(preview) > max_chars:
        preview = preview[:max_chars] + "…"
        truncated_lines = True

    for line in preview.split("\n"):
        print(f"    {color}│ {line}{C.RESET}")
    if truncated_lines:
        print(f"    {C.DIM}│ …{C.RESET}")


def tool_warning(text: str):
    print(f"  {C.YELLOW}⚠ {text}{C.RESET}")


def error(text: str):
    print(f"\n{C.RED}{C.BOLD}✗ {C.RESET}{C.RED}{text}{C.RESET}")


def info(text: str):
    print(f"{C.GRAY}{text}{C.RESET}")


def confirm_dangerous(cmd: str) -> bool:
    print(f"\n{C.YELLOW}{C.BOLD}⚠ Агент хочет выполнить потенциально опасную команду:{C.RESET}")
    print(f"    {C.RED}{cmd}{C.RESET}")
    answer = input(f"{C.YELLOW}Разрешить? (y/N): {C.RESET}").strip().lower()
    return answer == "y"


def confirm_action(description: str) -> bool:
    print(f"\n{C.CYAN}{C.BOLD}? {C.RESET}{description}")
    answer = input(f"{C.CYAN}Выполнить? (y/N): {C.RESET}").strip().lower()
    return answer == "y"


def show_help(tool_schemas, cfg):
    width = min(_term_width(), 60)
    print(f"\n{C.CYAN}╭{_box_line(width - 2)}╮{C.RESET}")
    print(f"{C.CYAN}│{C.RESET} {C.BOLD}Доступные инструменты (для ИИ){C.RESET}")
    print(f"{C.CYAN}╰{_box_line(width - 2)}╯{C.RESET}")

    for schema in tool_schemas:
        fn = schema["function"]
        name = fn["name"]
        desc = fn.get("description", "")
        params = fn.get("parameters", {}).get("properties", {})
        required = set(fn.get("parameters", {}).get("required", []))
        icon = TOOL_ICONS.get(name, "⚙️ ")

        print(f"\n  {icon} {C.GREEN}{C.BOLD}{name}{C.RESET}")
        print(f"     {C.GRAY}{desc}{C.RESET}")
        if params:
            param_list = []
            for pname in params:
                mark = "" if pname in required else "?"
                param_list.append(f"{pname}{mark}")
            print(f"     {C.DIM}аргументы: {', '.join(param_list)}{C.RESET}")

    print(f"\n{C.CYAN}╭{_box_line(width - 2)}╮{C.RESET}")
    print(f"{C.CYAN}│{C.RESET} {C.BOLD}Команды (для тебя){C.RESET}")
    print(f"{C.CYAN}╰{_box_line(width - 2)}╯{C.RESET}")
    print(f"  {C.GREEN}/help{C.RESET}              — этот список")
    print(f"  {C.GREEN}/run <file> [args]{C.RESET} — сразу запустить python-файл")
    print(f"  {C.GREEN}/model <name>{C.RESET}      — сменить модель на лету")
    print(f"  {C.GREEN}/provider{C.RESET}          — показать текущего провайдера")
    print(f"  {C.GREEN}/clear{C.RESET}             — очистить историю диалога")
    print(f"  {C.GREEN}exit{C.RESET}               — выйти")
    print(f"\n  {C.DIM}Провайдер: {cfg['active_provider']}, модель: "
          f"{cfg.get(cfg['active_provider'], {}).get('model', '?')}{C.RESET}")
    print(f"{C.CYAN}{_box_line(width)}{C.RESET}")


def wait_rate_limit(seconds: float):
    print()
    while seconds > 0:
        sys.stdout.write(
            f"\r{C.YELLOW}⏳ Лимит токенов исчерпан, жду {seconds:.0f}с...{C.RESET}   "
        )
        sys.stdout.flush()
        step = min(0.5, seconds)
        time.sleep(step)
        seconds -= step
    sys.stdout.write("\r" + " " * 50 + "\r")
    sys.stdout.flush()
    print(f"{C.GREEN}✓ Продолжаю...{C.RESET}")


class Spinner:
    """Спиннер во время ожидания ответа модели. Использовать как context manager."""
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message="Думаю..."):
        self.message = message
        self._stop = threading.Event()
        self._thread = None

    def _spin(self):
        i = 0
        while not self._stop.is_set():
            frame = self.FRAMES[i % len(self.FRAMES)]
            sys.stdout.write(f"\r{C.CYAN}{frame} {self.message}{C.RESET}  ")
            sys.stdout.flush()
            i += 1
            time.sleep(0.08)
        sys.stdout.write("\r" + " " * (len(self.message) + 6) + "\r")
        sys.stdout.flush()

    def __enter__(self):
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stop.set()
        if self._thread:
            self._thread.join()
