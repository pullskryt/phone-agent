# coding: utf-8
"""
Инструменты, которые агент может вызывать.
Каждый tool — функция + JSON-схема для модели (в формате OpenAI/Groq function calling,
он же понятен большинству local-моделей через llama.cpp сервер).
"""
import os
import subprocess

# Рабочая директория агента — та папка, откуда его вызвали (важно для алиаса
# "ai"/"ии", который может cd'аться в папку самого агента перед запуском).
# Приоритет: переменная окружения AI_AGENT_CWD > текущая директория процесса.
WORKDIR = os.environ.get("AI_AGENT_CWD", os.getcwd())


def _safe_path(path: str) -> str:
    """Раскрываем ~ и переменные окружения, затем строим абсолютный путь."""
    expanded = os.path.expanduser(os.path.expandvars(path))
    if os.path.isabs(expanded):
        full = expanded
    else:
        full = os.path.abspath(os.path.join(WORKDIR, expanded))
    return full


def read_file(path: str, line_start: int = None, line_end: int = None) -> str:
    try:
        full = _safe_path(path)
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        if line_start is not None or line_end is not None:
            lines = content.splitlines()
            start = (line_start or 1) - 1
            end = line_end if line_end is not None else len(lines)
            start = max(0, start)
            end = min(len(lines), end)
            content = "\n".join(lines[start:end])

        # ограничим вывод, чтобы не забивать контекст
        if len(content) > 20000:
            return content[:20000] + "\n...[обрезано, файл длиннее]"
        return content
    except Exception as e:
        return f"ERROR: {e}"


def write_file(path: str, content: str) -> str:
    try:
        full = _safe_path(path)
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        return f"OK: записано {len(content)} байт в {path}"
    except Exception as e:
        return f"ERROR: {e}"


def edit_file(path: str, old_str: str, new_str: str) -> str:
    """Замена подстроки, как str_replace — old_str должен встречаться ровно 1 раз."""
    try:
        full = _safe_path(path)
        with open(full, "r", encoding="utf-8") as f:
            content = f.read()
        count = content.count(old_str)
        if count == 0:
            return "ERROR: old_str не найден в файле"
        if count > 1:
            return f"ERROR: old_str встречается {count} раз, нужно уникальное вхождение"
        new_content = content.replace(old_str, new_str, 1)
        with open(full, "w", encoding="utf-8") as f:
            f.write(new_content)
        return "OK: файл изменён"
    except Exception as e:
        return f"ERROR: {e}"


def list_dir(path: str = ".") -> str:
    try:
        full = _safe_path(path)
        items = os.listdir(full)
        dirs = sorted(i for i in items if os.path.isdir(os.path.join(full, i)))
        files = sorted(i for i in items if os.path.isfile(os.path.join(full, i)))
        lines = [f"[dir]  {d}" for d in dirs] + [f"[file] {f}" for f in files]
        return "\n".join(lines) if lines else "(пусто)"
    except Exception as e:
        return f"ERROR: {e}"


def bash_exec(command: str, timeout: int = 60) -> str:
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKDIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = result.stdout
        err = result.stderr
        combined = out
        if err:
            combined += f"\n[stderr]\n{err}"
        if len(combined) > 8000:
            combined = combined[:8000] + "\n...[обрезано]"
        return combined.strip() or "(команда выполнена, вывода нет)"
    except subprocess.TimeoutExpired:
        return f"ERROR: команда превысила таймаут {timeout}с"
    except Exception as e:
        return f"ERROR: {e}"


def check_syntax(path: str) -> str:
    """
    Проверка синтаксиса файла без его выполнения.
    Для .py — компиляция через py_compile (ловит SyntaxError).
    """
    full = _safe_path(path)
    if not os.path.isfile(full):
        return f"ERROR: файл не найден: {path}"

    if not full.endswith(".py"):
        return "INFO: проверка синтаксиса пока поддерживается только для .py файлов"

    compile_result = subprocess.run(
        ["python3", "-m", "py_compile", full],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if compile_result.returncode != 0:
        return f"SYNTAX ERROR:\n{compile_result.stderr.strip()}"

    return (
        "OK: синтаксис корректен (SyntaxError не найдены).\n"
        "Примечание: py_compile не ловит DeprecationWarning внутри функций, "
        "которые не выполняются при импорте — такие предупреждения проявятся "
        "только при реальном запуске файла (bash_exec)."
    )


def run_python(path: str, args: str = "", timeout: int = 30) -> str:
    """
    Запустить python-файл. В отличие от bash_exec — специализированный
    инструмент, который agent.py ВСЕГДА подтверждает у пользователя (y/n)
    перед выполнением, независимо от содержимого.
    """
    full = _safe_path(path)
    if not os.path.isfile(full):
        return f"ERROR: файл не найден: {path}"

    cmd = ["python3", full] + (args.split() if args else [])
    try:
        result = subprocess.run(
            cmd,
            cwd=WORKDIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = result.stdout
        err = result.stderr
        combined = out
        if err:
            combined += f"\n[stderr]\n{err}"
        combined += f"\n[exit code: {result.returncode}]"
        if len(combined) > 8000:
            combined = combined[:8000] + "\n...[обрезано]"
        return combined.strip()
    except subprocess.TimeoutExpired:
        return f"ERROR: скрипт превысил таймаут {timeout}с"
    except Exception as e:
        return f"ERROR: {e}"


def grep_search(pattern: str, path: str = ".", file_glob: str = "*") -> str:
    """Поиск текста по файлам через grep -r."""
    full = _safe_path(path)
    if not os.path.exists(full):
        return f"ERROR: путь не найден: {path}"

    cmd = ["grep", "-rn", "--include", file_glob, pattern, full]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 1:
            return "(совпадений не найдено)"
        if result.returncode > 1:
            return f"ERROR: {result.stderr.strip()}"
        out = result.stdout
        if len(out) > 8000:
            out = out[:8000] + "\n...[обрезано]"
        # укорачиваем абсолютные пути обратно в относительные для читаемости
        return out.replace(WORKDIR + "/", "").strip()
    except subprocess.TimeoutExpired:
        return "ERROR: поиск превысил таймаут"
    except Exception as e:
        return f"ERROR: {e}"


def delete_file(path: str) -> str:
    """Удалить файл. Требует подтверждения на уровне agent.py (как rm -rf)."""
    try:
        full = _safe_path(path)
        if not os.path.exists(full):
            return f"ERROR: файл не найден: {path}"
        if os.path.isdir(full):
            return "ERROR: это директория, delete_file удаляет только файлы"
        os.remove(full)
        return f"OK: файл {path} удалён"
    except Exception as e:
        return f"ERROR: {e}"


def web_fetch(url: str, save_to: str = None) -> str:
    """Скачать содержимое URL. Если save_to указан — сохраняет в файл, иначе возвращает текст (обрезанный)."""
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "termux-ai-agent/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()

        if save_to:
            full = _safe_path(save_to)
            os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
            with open(full, "wb") as f:
                f.write(data)
            return f"OK: сохранено {len(data)} байт в {save_to}"

        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return f"OK: получено {len(data)} байт бинарных данных (не текст, используй save_to)"
        if len(text) > 10000:
            text = text[:10000] + "\n...[обрезано]"
        return text
    except Exception as e:
        return f"ERROR: {e}"


def install_package(manager: str, package: str) -> str:
    """
    Установить зависимость через pip или pkg (Termux). Всегда требует
    подтверждения пользователя на уровне agent.py, как run_python/delete_file —
    установка пакетов меняет систему и не должна происходить незаметно.
    """
    manager = manager.lower().strip()
    if manager not in ("pip", "pkg"):
        return f"ERROR: неизвестный менеджер пакетов '{manager}', используй 'pip' или 'pkg'"

    if manager == "pip":
        cmd = ["pip", "install", "--break-system-packages", package]
    else:
        cmd = ["pkg", "install", "-y", package]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        out = result.stdout[-4000:] if result.stdout else ""
        err = result.stderr[-2000:] if result.stderr else ""
        combined = out
        if err:
            combined += f"\n[stderr]\n{err}"
        combined += f"\n[exit code: {result.returncode}]"
        return combined.strip()
    except subprocess.TimeoutExpired:
        return "ERROR: установка превысила таймаут (180с) — пакет слишком большой или сеть медленная"
    except FileNotFoundError:
        return f"ERROR: команда '{manager}' не найдена в системе"
    except Exception as e:
        return f"ERROR: {e}"


def list_dialogues() -> str:
    """
    Список сохранённых прошлых диалогов в ~/Dialogues — самые свежие первыми.
    Используй это, чтобы понять, какие диалоги вообще есть, прежде чем
    читать конкретный через read_dialogue.
    """
    dialogues_dir = os.path.expanduser("~/Dialogues")
    if not os.path.isdir(dialogues_dir):
        return "(папка ~/Dialogues пока не существует — сохранённых диалогов ещё нет)"

    files = sorted(
        [f for f in os.listdir(dialogues_dir) if f.startswith("dialogue_")],
        reverse=True,
    )
    if not files:
        return "(сохранённых диалогов пока нет)"
    return "\n".join(files)


def read_dialogue(filename: str) -> str:
    """
    Прочитать содержимое конкретного сохранённого диалога из ~/Dialogues
    (имя файла бери из list_dialogues). Используй это разово, когда прошлый
    контекст реально нужен для текущей задачи — если оказалось, что не
    пригодился, просто не опирайся на него дальше в ответе.
    """
    dialogues_dir = os.path.expanduser("~/Dialogues")
    full = os.path.join(dialogues_dir, os.path.basename(filename))
    if not os.path.isfile(full):
        return f"ERROR: диалог не найден: {filename}"
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if len(content) > 12000:
            content = content[:12000] + "\n...[обрезано]"
        return content
    except Exception as e:
        return f"ERROR: {e}"


# ---- JSON-схемы для function calling (OpenAI-совместимый формат) ----

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Прочитать содержимое файла по относительному пути. Можно указать диапазон строк для больших файлов.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "line_start": {"type": "integer", "description": "Первая строка (с 1), опционально"},
                    "line_end": {"type": "integer", "description": "Последняя строка (включительно), опционально"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Создать файл или полностью перезаписать его содержимым",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Заменить уникальный фрагмент текста в существующем файле",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_str": {"type": "string"},
                    "new_str": {"type": "string"},
                },
                "required": ["path", "old_str", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "Показать содержимое директории",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash_exec",
            "description": "Выполнить bash-команду в рабочей директории и вернуть вывод",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer", "description": "секунды, по умолчанию 60"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_syntax",
            "description": "Проверить синтаксис .py файла на SyntaxError без его запуска. НЕ ловит рантайм-warnings (DeprecationWarning и т.п.) внутри функций — для этого нужно реально запустить файл через bash_exec.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Запустить python-скрипт с опциональными аргументами командной строки. Пользователь всегда подтверждает запуск (y/n). Используй это, а не bash_exec, когда нужно именно выполнить python-файл.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "args": {"type": "string", "description": "аргументы командной строки одной строкой, например '3 + 4'"},
                    "timeout": {"type": "integer", "description": "секунды, по умолчанию 30"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": "Найти текст/паттерн во всех файлах в директории (рекурсивно)",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "description": "директория для поиска, по умолчанию текущая"},
                    "file_glob": {"type": "string", "description": "маска файлов, например '*.py', по умолчанию все файлы"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Удалить файл. Требует подтверждения пользователя.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Скачать содержимое по URL — веб-страницу, текстовый файл, JSON от API. Если save_to указан, сохраняет в файл (используй для бинарных данных), иначе возвращает текст.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "save_to": {"type": "string", "description": "путь для сохранения, опционально"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "install_package",
            "description": "Установить недостающую зависимость через pip (python-библиотеки) или pkg (Termux-пакеты). Пользователь всегда подтверждает установку.",
            "parameters": {
                "type": "object",
                "properties": {
                    "manager": {"type": "string", "description": "'pip' или 'pkg'"},
                    "package": {"type": "string", "description": "имя пакета, например 'requests' или 'imagemagick'"},
                },
                "required": ["manager", "package"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dialogues",
            "description": "Показать список сохранённых прошлых диалогов (сессий) с пользователем — самые свежие первыми. Используй перед read_dialogue, чтобы выбрать нужный.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_dialogue",
            "description": "Прочитать содержимое конкретного прошлого диалога (имя файла из list_dialogues), если контекст прошлой сессии реально нужен для текущей задачи.",
            "parameters": {
                "type": "object",
                "properties": {"filename": {"type": "string"}},
                "required": ["filename"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "list_dir": list_dir,
    "bash_exec": bash_exec,
    "check_syntax": check_syntax,
    "run_python": run_python,
    "grep_search": grep_search,
    "delete_file": delete_file,
    "web_fetch": web_fetch,
    "install_package": install_package,
    "list_dialogues": list_dialogues,
    "read_dialogue": read_dialogue,
}
