# coding: utf-8
"""
Оформление вывода в терминале: цвета, рамки, спиннер, маскот, стартовый экран.
Чистый ANSI, без внешних зависимостей — работает в Termux из коробки.

Палитра — как в Claude Code: один акцентный цвет (циан) + чёрный/белый/серый.
"""
import sys
import time
import random
import threading
import shutil


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"

    ACCENT = "\033[38;5;51m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"

    # Единственный цвет вне циан/чёрно-белой палитры — для настоящих ошибок,
    # это нужно семантически (взглядом отличить "что-то сломалось"), а не эстетически.
    RED = "\033[31m"


def _term_size(default_w=60, default_h=24):
    try:
        size = shutil.get_terminal_size((default_w, default_h))
        return size.columns, size.lines
    except Exception:
        return default_w, default_h


def _term_width(default=60):
    return _term_size(default)[0]


def _box_line(width, char="─"):
    return char * width


def _center_line(text_visible_len, line, width):
    pad = max((width - text_visible_len) // 2, 0)
    return " " * pad + line


# ---- Маскот: фигура из сплошных блоков ∎ (по эскизу пользователя) ----
# Живёт ПРЯМО НА рамке заголовка. Пока рамка видна на экране (стартовый
# экран / после /clear / ожидание ввода) — время от времени лениво дёргает
# ножкой. Как только начинается обычный вывод диалога и рамка "уходит" вверх
# по истории терминала — маскот остаётся статичным, как обычный текст.
MASCOT_BASE = [
    "      ∎∎∎∎∎∎∎∎∎∎∎∎      ",
    "    ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎    ",
    "  ∎∎  ∎∎∎∎∎∎∎∎∎∎∎∎  ∎∎  ",
    "    ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎    ",
    "  ∎∎  ∎∎∎∎∎∎∎∎∎∎∎∎  ∎∎  ",
    "      ∎∎∎      ∎∎∎      ",
    "      ∎∎∎      ∎∎∎      ",
]

MASCOT_FRAMES = [
    # кадр 0 — сидит спокойно (нейтральный, самый частый)
    list(MASCOT_BASE),
    # кадр 1 — левая ножка дёрнулась влево
    MASCOT_BASE[:5] + [
        "     ∎∎∎       ∎∎∎      ",
        "    ∎∎∎        ∎∎∎      ",
    ],
    # кадр 2 — правая ножка дёрнулась вправо
    MASCOT_BASE[:5] + [
        "      ∎∎∎       ∎∎∎     ",
        "      ∎∎∎        ∎∎∎    ",
    ],
]

_MASCOT_WIDTH = max(len(line) for frame in MASCOT_FRAMES for line in frame)
MASCOT_FRAMES = [[line.ljust(_MASCOT_WIDTH) for line in frame] for frame in MASCOT_FRAMES]
MASCOT_HEIGHT = len(MASCOT_FRAMES[0])


def _render_mascot_frame(frame_idx, width):
    frame = MASCOT_FRAMES[frame_idx % len(MASCOT_FRAMES)]
    return [_center_line(len(line), f"{C.ACCENT}{line}{C.RESET}", width) for line in frame]


def print_mascot_static(width=None):
    """
    Печатает маскота один раз, в нейтральной позе, без анимации.
    Сохраняет позицию курсора СРАЗУ ПОСЛЕ маскота (\\033[s) — так
    MascotIdle сможет вернуться и перерисовать именно эту область,
    сколько бы строк ни было напечатано между вызовами.
    """
    width = width or min(_term_width(), 60)
    lines = _render_mascot_frame(0, width)
    for line in lines:
        print(line)
    # запоминаем, где курсор оказался сразу под маскотом
    sys.stdout.write("\033[s")
    sys.stdout.flush()


class MascotIdle:
    """
    Фоновая idle-анимация маскота — использовать ТОЛЬКО пока курсор
    гарантированно можно временно увести в сторону и вернуть (ожидание
    input()). Полагается на ANSI save/restore cursor position (\\033[s / \\033[u),
    сохранённую в print_mascot_static() сразу после печати маскота — поэтому
    работает независимо от того, сколько строк текста напечатано ниже.
    Как только начинается обычный вывод диалога, нужно .stop() — маскот
    остаётся статичной частью истории терминала.
    """
    MASCOT_ROW_OFFSET = MASCOT_HEIGHT  # сколько строк над сохранённой позицией — сам маскот

    def __init__(self, width=None):
        self.width = width or min(_term_width(), 60)
        self._stop = threading.Event()
        self._thread = None

    def _loop(self):
        while not self._stop.wait(random.uniform(2.5, 6.0)):
            if self._stop.is_set():
                break
            kick_frame = random.choice([1, 2])
            self._redraw(kick_frame)
            if self._stop.wait(0.25):
                break
            self._redraw(0)

    def _redraw(self, frame_idx):
        lines = _render_mascot_frame(frame_idx, self.width)
        # Сохраняем ТЕКУЩУЮ позицию курсора (там, где сейчас реально стоит
        # input() и мигает "❯") — это критично: раньше здесь ошибочно
        # полагались на позицию, сохранённую в header() СРАЗУ под маскотом,
        # из-за чего курсор после перерисовки прыгал обратно под маскота, а
        # не туда, где пользователь печатает — рамка "въезжала" в текст.
        sys.stdout.write("\0337")  # DEC save cursor (курсор ввода)
        sys.stdout.write("\033[u")  # restore к позиции под маскотом (из header())
        sys.stdout.write(f"\033[{self.MASCOT_ROW_OFFSET}A")  # подняться к первой строке маскота
        for line in lines:
            sys.stdout.write("\r\033[K" + line + "\n")
        sys.stdout.write("\0338")  # DEC restore cursor — назад туда, где печатает пользователь
        sys.stdout.flush()

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)


def new_screen():
    """
    ПОЛНАЯ смена экрана — не просто дописывание текста и не плавная замена,
    а мгновенный переход в чистое 'новое окно', как переключение вкладки.
    """
    sys.stdout.write("\033[2J\033[3J\033[H")
    sys.stdout.flush()


def header(text: str, width=None):
    """
    Рисует маскота (статично, в нейтральной позе) прямо над рамкой заголовка,
    затем саму рамку. Не запускает idle-анимацию сам — это делает вызывающий
    код (main loop), потому что именно он знает, когда можно безопасно писать
    поверх экрана, а когда нет.
    """
    width = width or min(_term_width(), 60)

    print_mascot_static(width)
    print(_center_line(width, f"{C.ACCENT}╭{_box_line(width - 2)}╮{C.RESET}", width))
    inner = f" {C.BOLD}{C.WHITE}{text}{C.RESET}"
    visible_len = len(text) + 2
    pad = max(width - 2 - visible_len, 0)
    line = f"{C.ACCENT}│{C.RESET}{inner}{' ' * pad}{C.ACCENT}│{C.RESET}"
    print(_center_line(width, line, width))
    print(_center_line(width, f"{C.ACCENT}╰{_box_line(width - 2)}╯{C.RESET}", width))


def user_prompt():
    return input(f"\n{C.BOLD}{C.ACCENT}❯ {C.RESET}")


def _strip_wrapping_quotes(text: str) -> str:
    stripped = text.strip()
    quote_pairs = [("'", "'"), ('"', '"'), ("«", "»")]
    for open_q, close_q in quote_pairs:
        if not (len(stripped) > 1 and stripped.startswith(open_q) and stripped.endswith(close_q)):
            continue
        inner = stripped[len(open_q):-len(close_q)]
        if open_q not in inner and close_q not in inner:
            return inner.strip()
    return text


def assistant_reply(text: str):
    text = _strip_wrapping_quotes(text)
    width = min(_term_width(), 60)
    print(f"\n{C.ACCENT}┌{'─' * (width - 2)}{C.RESET}")
    for line in text.split("\n"):
        print(f"{C.ACCENT}│{C.RESET} {line}")
    print(f"{C.ACCENT}└{'─' * (width - 2)}{C.RESET}")


def tool_call(name: str, args_repr: str):
    print(f"  {C.ACCENT}▸{C.RESET} {C.ACCENT}{C.BOLD}{name}{C.RESET}{C.GRAY}({args_repr}){C.RESET}")


def tool_result_preview(result, max_lines=4, max_chars=300):
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
    print(f"  {C.ACCENT}{C.BOLD}⚠{C.RESET} {C.GRAY}{text}{C.RESET}")


def error(text: str):
    print(f"\n{C.RED}{C.BOLD}✗ {C.RESET}{C.RED}{text}{C.RESET}")


def info(text: str):
    print(f"{C.GRAY}{text}{C.RESET}")


def confirm_dangerous(cmd: str) -> bool:
    # Единственное место, где сознательно используем красный вне ошибок —
    # это подтверждение перед потенциально разрушительной командой (rm -rf и
    # т.п.), где действительно важно визуально выделиться сильнее обычного.
    print(f"\n{C.RED}{C.BOLD}⚠ Агент хочет выполнить потенциально опасную команду:{C.RESET}")
    print(f"    {C.RED}{cmd}{C.RESET}")
    answer = input(f"{C.RED}Разрешить? (y/N): {C.RESET}").strip().lower()
    return answer == "y"


def confirm_action(description: str) -> bool:
    print(f"\n{C.ACCENT}{C.BOLD}? {C.RESET}{description}")
    answer = input(f"{C.ACCENT}Выполнить? (y/N): {C.RESET}").strip().lower()
    return answer == "y"


def show_help(tool_schemas, cfg):
    width = min(_term_width(), 60)
    print(f"\n{C.ACCENT}╭{_box_line(width - 2)}╮{C.RESET}")
    print(f"{C.ACCENT}│{C.RESET} {C.BOLD}Доступные инструменты (для ИИ){C.RESET}")
    print(f"{C.ACCENT}╰{_box_line(width - 2)}╯{C.RESET}")

    for schema in tool_schemas:
        fn = schema["function"]
        name = fn["name"]
        desc = fn.get("description", "")
        params = fn.get("parameters", {}).get("properties", {})
        required = set(fn.get("parameters", {}).get("required", []))

        print(f"\n  {C.ACCENT}▸{C.RESET} {C.ACCENT}{C.BOLD}{name}{C.RESET}")
        print(f"     {C.GRAY}{desc}{C.RESET}")
        if params:
            param_list = []
            for pname in params:
                mark = "" if pname in required else "?"
                param_list.append(f"{pname}{mark}")
            print(f"     {C.DIM}аргументы: {', '.join(param_list)}{C.RESET}")

    print(f"\n{C.ACCENT}╭{_box_line(width - 2)}╮{C.RESET}")
    print(f"{C.ACCENT}│{C.RESET} {C.BOLD}Команды (для тебя){C.RESET}")
    print(f"{C.ACCENT}╰{_box_line(width - 2)}╯{C.RESET}")
    print(f"  {C.ACCENT}/help{C.RESET}              — этот список")
    print(f"  {C.ACCENT}/run <file> [args]{C.RESET} — сразу запустить python-файл")
    print(f"  {C.ACCENT}/model <name>{C.RESET}      — сменить модель на лету")
    print(f"  {C.ACCENT}/system [текст]{C.RESET}    — показать/изменить системный промпт")
    print(f"  {C.ACCENT}/provider{C.RESET}          — показать текущего провайдера")
    print(f"  {C.ACCENT}/logs{C.RESET}              — вкл/выкл подробный вывод вызовов инструментов")
    print(f"  {C.ACCENT}/economy{C.RESET}           — вкл/выкл экономию запросов к провайдеру")
    print(f"  {C.ACCENT}/clear{C.RESET}             — очистить историю диалога")
    print(f"  {C.ACCENT}exit{C.RESET}               — выйти")
    print(f"\n  {C.DIM}Провайдер: {cfg['active_provider']}, модель: "
          f"{cfg.get(cfg['active_provider'], {}).get('model', '?')}{C.RESET}")
    print(f"{C.ACCENT}{_box_line(width)}{C.RESET}")


def show_system_prompt(prompt: str):
    width = min(_term_width(), 60)
    print(f"\n{C.ACCENT}╭{_box_line(width - 2)}╮{C.RESET}")
    print(f"{C.ACCENT}│{C.RESET} {C.BOLD}Текущий системный промпт{C.RESET}")
    print(f"{C.ACCENT}╰{_box_line(width - 2)}╯{C.RESET}")
    print(f"{C.GRAY}{prompt}{C.RESET}")
    print(f"\n{C.DIM}Чтобы изменить: /system <новый текст целиком>{C.RESET}")


def wait_rate_limit(seconds: float):
    print()
    while seconds > 0:
        sys.stdout.write(
            f"\r{C.ACCENT}⏳ Лимит токенов исчерпан, жду {seconds:.0f}с...{C.RESET}   "
        )
        sys.stdout.flush()
        step = min(0.5, seconds)
        time.sleep(step)
        seconds -= step
    sys.stdout.write("\r" + " " * 50 + "\r")
    sys.stdout.flush()
    print(f"{C.WHITE}✓ Продолжаю...{C.RESET}")


def _build_breath_palette(steps=100):
    """
    Строит плавный градиент циана из `steps` точек, СТРОГО по порядку
    (не рандом — только цвет идёт по порядку, вдох-выдох).
    Используем 24-битный truecolor ANSI (\\033[38;2;R;G;Bm), а не 256-цветную
    палитру — там всего 6 уровней на канал, из-за чего соседние коды дают
    "плато" (несколько одинаковых оттенков подряд) и цвет норовит соскочить
    в зелёный, если G и B округляются не в лад. С truecolor такого нет: R, G, B
    растут гладко и B задан заведомо больше G на каждом шаге.
    """
    half = steps // 2
    palette = []
    for i in range(half):
        t = i / max(half - 1, 1)  # 0.0 -> 1.0, плавно
        r = int(10 + t * 15)
        g = int(60 + t * 130)
        b = int(95 + t * 150)  # b всегда заметно больше g — гарантия циана
        palette.append((r, g, b))
    return palette + palette[::-1]


class Spinner:
    """
    Спиннер во время ожидания ответа модели — как в Claude Code:
    цвет текста плавно "дышит" по 100-точечному градиенту СТРОГО по порядку
    (вдох-выдох, без скачков и без рандома), а фраза-подсказка каждый раз
    выбирается СЛУЧАЙНО (не по кругу), чтобы не примелькаться. Context manager.
    """
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    PHRASES = [
        "Думаю",
        "Прикидываю план",
        "Смотрю на файлы",
        "Собираю контекст",
        "Ещё немного",
        "Почти готово",
        "Проверяю детали",
        "Секунду",
    ]

    _BREATH_COLORS = _build_breath_palette(100)

    def __init__(self, message=None):
        self.base_message = message
        self._stop = threading.Event()
        self._thread = None

    def _color_code(self, idx):
        r, g, b = self._BREATH_COLORS[idx % len(self._BREATH_COLORS)]
        return f"\033[38;2;{r};{g};{b}m"

    def _spin(self):
        i = 0
        # тик каждые 0.05с × 200 точек полного цикла = 10с на вдох-выдох — плавно
        tick_len = 0.05
        current_phrase = self.base_message or random.choice(self.PHRASES)
        next_phrase_at = time.monotonic() + random.uniform(2.0, 3.5)

        while not self._stop.is_set():
            frame = self.FRAMES[i % len(self.FRAMES)]
            breath = self._color_code(i)

            if not self.base_message and time.monotonic() >= next_phrase_at:
                # случайная (не по кругу) новая фраза, но не повторяем текущую подряд
                choices = [p for p in self.PHRASES if p != current_phrase]
                current_phrase = random.choice(choices)
                next_phrase_at = time.monotonic() + random.uniform(2.0, 3.5)

            sys.stdout.write(f"\r{breath}{frame} {current_phrase}...{C.RESET}   ")
            sys.stdout.flush()
            i += 1
            time.sleep(tick_len)
        sys.stdout.write("\r" + " " * 40 + "\r")
        sys.stdout.flush()

    def __enter__(self):
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stop.set()
        if self._thread:
            self._thread.join()
