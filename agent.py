# coding: utf-8
"""
Termux AI Agent — CLI-агент вроде Claude Code.
Работает либо через облачный API (Groq и т.п.), либо через локальный llama.cpp сервер.

Запуск:
    python agent.py
    python agent.py --provider local
    python agent.py --provider api
"""
import os
import sys
import json
import argparse

import tools
import display
from providers import api as api_provider
from providers import local as local_provider

# Папка, где лежит сам agent.py — config.json всегда читаем отсюда,
# независимо от того, из какой директории юзера был вызван агент.
AGENT_HOME = os.path.dirname(os.path.abspath(__file__))


def load_config():
    config_path = os.path.join(AGENT_HOME, "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def call_model(messages, cfg):
    provider = cfg["active_provider"]
    if provider == "api":
        return api_provider.chat(messages, tools.TOOL_SCHEMAS, cfg["api"])
    elif provider == "local":
        return local_provider.chat(messages, tools.TOOL_SCHEMAS, cfg["local"])
    else:
        raise RuntimeError(f"Неизвестный провайдер: {provider}")


def call_model_with_retry(messages, cfg, max_retries=5):
    """Оборачивает call_model: при rate limit (429) ждёт нужное время и повторяет."""
    for attempt in range(max_retries):
        try:
            with display.Spinner():
                return call_model(messages, cfg)
        except api_provider.RateLimitError as e:
            if attempt == max_retries - 1:
                raise RuntimeError(f"Лимит токенов исчерпан, попытки повтора закончились: {e}")
            display.wait_rate_limit(e.retry_after)


def run_tool_call(tool_call, cfg=None, confirm_fn=None, log_fn=None):
    """
    confirm_fn(description: str) -> bool — как спросить y/n. По умолчанию
    display.confirm_action (терминал). Telegram-бот передаёт свою версию
    через inline-кнопки.
    log_fn(name, args_repr) — как показать вызов инструмента. По умолчанию
    display.tool_call. Telegram-бот передаёт свою версию (отправка в чат).
    """
    verbose = (cfg or {}).get("_verbose", True)
    confirm_fn = confirm_fn or display.confirm_action
    log_fn = log_fn or display.tool_call

    name = tool_call["function"]["name"]
    try:
        args = json.loads(tool_call["function"]["arguments"])
    except json.JSONDecodeError:
        return f"ERROR: не удалось распарсить аргументы: {tool_call['function']['arguments']}"

    fn = tools.TOOL_FUNCTIONS.get(name)
    if not fn:
        return f"ERROR: неизвестный инструмент {name}"

    # run_python — всегда требует подтверждения, независимо от содержимого
    if name == "run_python":
        target = args.get("path", "?")
        extra = args.get("args", "")
        display_cmd = f"python3 {target} {extra}".strip()
        if not confirm_fn(f"Запустить скрипт: {display_cmd}"):
            return "ERROR: пользователь отклонил запуск скрипта"

    # delete_file — тоже требует подтверждения (необратимое действие)
    if name == "delete_file":
        target = args.get("path", "?")
        if not confirm_fn(f"Удалить файл: {target}"):
            return "ERROR: пользователь отклонил удаление файла"

    # install_package — тоже требует подтверждения (меняет систему)
    if name == "install_package":
        manager = args.get("manager", "?")
        package = args.get("package", "?")
        if not confirm_fn(f"Установить пакет: {manager} install {package}"):
            return "ERROR: пользователь отклонил установку пакета"

    # Подтверждение для потенциально опасных bash-команд
    if name == "bash_exec":
        cmd = args.get("command", "")
        dangerous = any(x in cmd for x in ["rm -rf", "mkfs", "dd if=", ":(){:|:&};:"])
        if dangerous:
            if not confirm_fn(f"[ОПАСНО] Выполнить команду: {cmd}"):
                return "ERROR: пользователь отклонил выполнение команды"

    args_repr = ', '.join(
        f"{k}={v!r}" if k != 'content' else f"{k}=<{len(str(v))} байт>"
        for k, v in args.items()
    )
    if verbose:
        log_fn(name, args_repr)
    try:
        result = fn(**args)
        if verbose and log_fn is display.tool_call:
            # превью результата — только для терминального вывода по умолчанию;
            # Telegram-бот решает сам, показывать ли превью, в своей log_fn
            display.tool_result_preview(result)
        return result
    except TypeError as e:
        # Модель передала неизвестные/лишние параметры — не роняем процесс,
        # а сообщаем ей об этом, чтобы она поправила вызов.
        return f"ERROR: неверные аргументы для {name}: {e}"


def save_dialogue(messages, cfg):
    """
    Сохраняет диалог сессии в ~/Dialogues как читаемый текстовый файл —
    и для человека, и для модели (которая потом сможет прочитать его через
    read_dialogue). Хранит только последние 5 диалогов, старые удаляются.
    """
    import time as _time

    dialogues_dir = os.path.expanduser("~/Dialogues")
    os.makedirs(dialogues_dir, exist_ok=True)

    # Пропускаем сохранение, если в диалоге не было ничего кроме системного промпта
    if len(messages) <= 1:
        return

    timestamp = _time.strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"dialogue_{timestamp}.txt"
    filepath = os.path.join(dialogues_dir, filename)

    lines = [f"# Диалог от {_time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    for msg in messages[1:]:  # пропускаем системный промпт
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if role == "user":
            lines.append(f"[Пользователь]: {content}")
        elif role == "assistant":
            if content:
                lines.append(f"[Агент]: {content}")
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    fn_name = tc.get("function", {}).get("name", "?")
                    lines.append(f"[Агент вызвал инструмент]: {fn_name}")
        elif role == "tool":
            preview = str(content)[:200]
            lines.append(f"[Результат инструмента]: {preview}")

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception:
        return  # сохранение диалогов не должно ронять выход из программы

    # Ротация: держим только последние 5 файлов диалогов
    try:
        existing = sorted(
            [f for f in os.listdir(dialogues_dir) if f.startswith("dialogue_")],
        )
        while len(existing) > 5:
            oldest = existing.pop(0)
            os.remove(os.path.join(dialogues_dir, oldest))
    except Exception:
        pass


def handle_slash_command(command: str, cfg: dict, messages: list):
    """
    Возвращает (messages, should_clear_screen).
    Может мутировать cfg на месте (для /model).
    """
    parts = command.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd in ("/help", "/?"):
        display.show_help(tools.TOOL_SCHEMAS, cfg)

    elif cmd == "/provider":
        display.info(f"Текущий провайдер: {cfg['active_provider']}")

    elif cmd == "/model":
        if not arg:
            current = cfg.get(cfg["active_provider"], {}).get("model", "?")
            display.info(f"Текущая модель: {current}. Использование: /model <название>")
        else:
            cfg[cfg["active_provider"]]["model"] = arg
            display.info(f"Модель переключена на: {arg}")

    elif cmd == "/system":
        if not arg:
            display.show_system_prompt(cfg["system_prompt"])
        else:
            cfg["system_prompt"] = arg
            if messages:
                messages[0] = {"role": "system", "content": arg}
            display.info("Системный промпт обновлён (действует с текущего момента).")

    elif cmd == "/run":
        if not arg:
            display.tool_warning("Использование: /run <путь-к-файлу.py> [аргументы]")
        else:
            run_parts = arg.split(maxsplit=1)
            path = run_parts[0]
            run_args = run_parts[1] if len(run_parts) > 1 else ""
            if display.confirm_action(f"Запустить: python3 {path} {run_args}".strip()):
                display.tool_call("run_python", f"path={path!r}")
                result = tools.run_python(path, run_args)
                display.tool_result_preview(result)

    elif cmd == "/logs":
        cfg["_verbose"] = not cfg.get("_verbose", True)
        state = "включены" if cfg["_verbose"] else "выключены"
        display.info(f"Подробные логи вызовов инструментов {state}.")

    elif cmd == "/clear":
        messages = messages[:1]  # оставляем только системный промпт
        display.new_screen()
        display.header(f"Termux AI Agent · провайдер: {cfg['active_provider']}")
        display.info("История диалога очищена. Готов к новой задаче.")

    else:
        display.tool_warning(f"Неизвестная команда: {command}. Введи /help для списка команд.")

    return messages


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["api", "local"], default=None)
    args = parser.parse_args()

    cfg = load_config()
    if args.provider:
        cfg["active_provider"] = args.provider
    cfg.setdefault("_verbose", True)

    display.new_screen()
    display.header(f"Termux AI Agent · провайдер: {cfg['active_provider']}")
    display.info(f"Рабочая директория: {tools.WORKDIR}")
    display.info("Введи задачу (или 'exit' для выхода, /help для списка команд)")

    messages = [{"role": "system", "content": cfg["system_prompt"]}]

    # Маскот "оживает" только на ПЕРВОМ ожидании ввода сразу после того, как
    # экран был свежеочищен (старт программы или /clear) — то есть пока курсор
    # гарантированно стоит ровно там, где был сохранён (\033[s в header()).
    # На всех следующих input() внутри той же "страницы" маскот уже замер как
    # обычный текст — так безопаснее: не полагаемся на save/restore курсора
    # через произвольное количество строк вывода, накопившихся в диалоге.
    screen_is_fresh = True

    while True:
        if screen_is_fresh:
            mascot = display.MascotIdle().start()
            screen_is_fresh = False
        else:
            mascot = None

        try:
            user_input = display.user_prompt().strip()
        except (EOFError, KeyboardInterrupt):
            if mascot:
                mascot.stop()
            save_dialogue(messages, cfg)
            print("\nВыход.")
            break
        finally:
            if mascot:
                mascot.stop()

        if user_input.lower() in ("exit", "quit", "выход"):
            save_dialogue(messages, cfg)
            break
        if not user_input:
            continue

        if user_input.startswith("/"):
            if user_input.strip().lower() == "/clear":
                save_dialogue(messages, cfg)
            messages = handle_slash_command(user_input, cfg, messages)
            if user_input.strip().lower() == "/clear":
                screen_is_fresh = True  # экран очищен заново — маскот снова может дёргаться
            continue

        messages.append({"role": "user", "content": user_input})

        consecutive_tool_errors = 0

        for _ in range(cfg.get("max_tool_iterations", 15)):
            try:
                response = call_model_with_retry(messages, cfg)
            except RuntimeError as e:
                display.error(str(e))
                break

            if "error" in response:
                err = response["error"]
                err_code = err.get("code", "")
                if err_code == "tool_use_failed":
                    consecutive_tool_errors += 1
                    if consecutive_tool_errors >= 3:
                        display.error(
                            "Модель трижды подряд не смогла корректно вызвать инструмент. "
                            "Попробуй переформулировать задачу или смени модель через /model."
                        )
                        break

                    err_message = err.get("message", "")

                    if "which was not in request.tools" in err_message:
                        # Модель выдумала несуществующее имя инструмента (например
                        # ls_dir вместо list_dir) — даём ей точный список реальных имён.
                        real_names = ", ".join(tools.TOOL_FUNCTIONS.keys())
                        display.tool_warning(
                            "Модель вызвала несуществующий инструмент, подсказываю верные имена..."
                        )
                        messages.append({
                            "role": "user",
                            "content": (
                                f"Такого инструмента не существует. Доступные инструменты: "
                                f"{real_names}. Используй точно одно из этих имён."
                            ),
                        })
                    else:
                        # Невалидный JSON в аргументах — просим переформулировать.
                        display.tool_warning("Модель ошиблась в формате вызова инструмента, прошу повторить...")
                        messages.append({
                            "role": "user",
                            "content": (
                                "Твой предыдущий вызов инструмента содержал невалидный JSON "
                                "(скорее всего проблема с экранированием кавычек/переносов строк "
                                "в поле content). Повтори вызов, тщательно проверив JSON-синтаксис."
                            ),
                        })
                    continue
                display.error(f"Ошибка модели: {err}")
                break

            consecutive_tool_errors = 0

            choice = response["choices"][0]
            msg = choice["message"]
            messages.append(msg)

            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                # Обычный текстовый ответ — печатаем и ждём следующий ввод
                content = msg.get("content", "")
                display.assistant_reply(content)
                break

            # Модель попросила вызвать инструменты
            for tc in tool_calls:
                result = run_tool_call(tc, cfg)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": str(result),
                })
            # цикл продолжается — отдаём результаты обратно модели
        else:
            display.tool_warning("Достигнут лимит итераций инструментов.")


if __name__ == "__main__":
    main()
