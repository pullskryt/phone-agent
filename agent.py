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
            with display.Spinner("Думаю..."):
                return call_model(messages, cfg)
        except api_provider.RateLimitError as e:
            if attempt == max_retries - 1:
                raise RuntimeError(f"Лимит токенов исчерпан, попытки повтора закончились: {e}")
            display.wait_rate_limit(e.retry_after)


def run_tool_call(tool_call):
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
        if not display.confirm_action(f"Запустить скрипт: {display_cmd}"):
            return "ERROR: пользователь отклонил запуск скрипта"

    # delete_file — тоже требует подтверждения (необратимое действие)
    if name == "delete_file":
        target = args.get("path", "?")
        if not display.confirm_action(f"Удалить файл: {target}"):
            return "ERROR: пользователь отклонил удаление файла"

    # Подтверждение для потенциально опасных bash-команд
    if name == "bash_exec":
        cmd = args.get("command", "")
        dangerous = any(x in cmd for x in ["rm -rf", "mkfs", "dd if=", ":(){:|:&};:"])
        if dangerous:
            if not display.confirm_dangerous(cmd):
                return "ERROR: пользователь отклонил выполнение команды"

    args_repr = ', '.join(
        f"{k}={v!r}" if k != 'content' else f"{k}=<{len(str(v))} байт>"
        for k, v in args.items()
    )
    display.tool_call(name, args_repr)
    try:
        result = fn(**args)
        display.tool_result_preview(result)
        return result
    except TypeError as e:
        # Модель передала неизвестные/лишние параметры — не роняем процесс,
        # а сообщаем ей об этом, чтобы она поправила вызов.
        return f"ERROR: неверные аргументы для {name}: {e}"


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

    elif cmd == "/clear":
        messages = messages[:1]  # оставляем только системный промпт
        display.info("История диалога очищена.")

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

    display.header(f"Termux AI Agent · провайдер: {cfg['active_provider']}")
    display.info(f"Рабочая директория: {tools.WORKDIR}")
    display.info("Введи задачу (или 'exit' для выхода)")

    messages = [{"role": "system", "content": cfg["system_prompt"]}]

    while True:
        try:
            user_input = display.user_prompt().strip()
        except (EOFError, KeyboardInterrupt):
            print("\nВыход.")
            break

        if user_input.lower() in ("exit", "quit", "выход"):
            break
        if not user_input:
            continue

        if user_input.startswith("/"):
            messages = handle_slash_command(user_input, cfg, messages)
            continue

        messages.append({"role": "user", "content": user_input})

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
                    # Модель сгенерировала невалидный JSON в аргументах инструмента.
                    # Не падаем — просим модель повторить попытку.
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
                result = run_tool_call(tc)
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
