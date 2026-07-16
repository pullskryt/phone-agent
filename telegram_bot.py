# coding: utf-8
"""
Telegram-интеграция для Termux AI Agent — тот же агент, но через Telegram-бота
вместо терминала. Работает изнутри Termux (long polling), поэтому жив ровно
пока жив процесс — как и обычный агент.

Запуск:
    python telegram_bot.py

Настройка токена и разрешённых ID — в config.json -> "telegram", либо через
install.sh при установке.
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error

import tools
import agent as agent_core

# У Telegram-бота нет понятия "текущей папки терминала" (в отличие от CLI,
# где WORKDIR берётся из AI_AGENT_CWD) — фиксируем на домашнюю директорию.
# Системный промпт всё равно направляет новые проекты в ~/Projects.
tools.WORKDIR = os.path.expanduser("~")

AGENT_HOME = os.path.dirname(os.path.abspath(__file__))

# Хранилище ожидающих подтверждения действий (run_python/delete_file/install_package
# /опасный bash_exec) — ключ: callback_data id, значение: threading.Event + результат.
import threading
_pending_confirmations = {}
_confirmation_counter = 0
_confirmation_lock = threading.Lock()


def load_config():
    config_path = os.path.join(AGENT_HOME, "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


class TelegramAPI:
    """Тонкая обёртка над Telegram Bot HTTP API — чистый urllib, без сторонних библиотек."""

    def __init__(self, token):
        self.base = f"https://api.telegram.org/bot{token}"

    def _call(self, method, payload, timeout=35):
        url = f"{self.base}/{method}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_updates(self, offset=None, timeout=30):
        payload = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        return self._call("getUpdates", payload, timeout=timeout + 10)

    def send_message(self, chat_id, text, reply_markup=None):
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        # Telegram режет сообщения длиннее 4096 символов — бьём на части
        if len(text) > 4000:
            chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
            for chunk in chunks[:-1]:
                self._call("sendMessage", {"chat_id": chat_id, "text": chunk})
            payload["text"] = chunks[-1]
        return self._call("sendMessage", payload)

    def answer_callback_query(self, callback_query_id, text=None):
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        return self._call("answerCallbackQuery", payload)

    def edit_message_text(self, chat_id, message_id, text):
        return self._call("editMessageText", {
            "chat_id": chat_id, "message_id": message_id, "text": text,
        })


def make_confirm_button_markup(confirm_id):
    return {
        "inline_keyboard": [[
            {"text": "Разрешить", "callback_data": f"yes:{confirm_id}"},
            {"text": "Отклонить", "callback_data": f"no:{confirm_id}"},
        ]]
    }


def request_confirmation(api, chat_id, description, timeout=120):
    """
    Отправляет сообщение с inline-кнопками да/нет и БЛОКИРУЕТ выполнение
    (в отдельном потоке — это нормально, весь tool-calling для одного чата
    и так последовательный), пока пользователь не нажмёт кнопку или не
    истечёт таймаут. Возвращает True/False.
    """
    global _confirmation_counter
    with _confirmation_lock:
        _confirmation_counter += 1
        confirm_id = str(_confirmation_counter)

    event = threading.Event()
    _pending_confirmations[confirm_id] = {"event": event, "result": False}

    api.send_message(
        chat_id,
        f"Подтверждение нужно:\n{description}",
        reply_markup=make_confirm_button_markup(confirm_id),
    )

    got_answer = event.wait(timeout)
    result = _pending_confirmations.pop(confirm_id, {}).get("result", False)
    if not got_answer:
        api.send_message(chat_id, "Время ожидания подтверждения истекло — действие отклонено.")
        return False
    return result


def handle_callback_query(api, callback_query):
    data = callback_query.get("data", "")
    callback_id = callback_query["id"]
    chat_id = callback_query["message"]["chat"]["id"]
    message_id = callback_query["message"]["message_id"]

    if ":" not in data:
        api.answer_callback_query(callback_id)
        return

    action, confirm_id = data.split(":", 1)
    pending = _pending_confirmations.get(confirm_id)
    if not pending:
        api.answer_callback_query(callback_id, "Уже неактуально.")
        return

    pending["result"] = (action == "yes")
    pending["event"].set()

    verdict = "Разрешено" if action == "yes" else "Отклонено"
    api.answer_callback_query(callback_id, verdict)
    try:
        api.edit_message_text(chat_id, message_id, f"{verdict}.")
    except Exception:
        pass


def process_user_message(api, chat_id, text, cfg, sessions):
    """Один ход диалога для конкретного чата — переиспользует agent_core."""
    if chat_id not in sessions:
        sessions[chat_id] = [{"role": "system", "content": cfg["system_prompt"]}]
    messages = sessions[chat_id]

    if text.strip().lower() == "/clear":
        agent_core.save_dialogue(messages, cfg)
        sessions[chat_id] = [{"role": "system", "content": cfg["system_prompt"]}]
        api.send_message(chat_id, "История диалога очищена.")
        return

    if text.strip().lower() in ("/help", "/start"):
        names = ", ".join(tools.TOOL_FUNCTIONS.keys())
        api.send_message(
            chat_id,
            f"Termux AI Agent через Telegram.\n\n"
            f"Доступные инструменты: {names}\n\n"
            f"Команды: /clear — сбросить историю диалога.\n"
            f"Действия вроде запуска скриптов или удаления файлов запрашивают "
            f"подтверждение прямо здесь, кнопками.",
        )
        return

    messages.append({"role": "user", "content": text})

    confirm_fn = lambda desc: request_confirmation(api, chat_id, desc)
    log_fn = lambda name, args_repr: api.send_message(chat_id, f"Вызываю: {name}({args_repr})")

    consecutive_tool_errors = 0
    for _ in range(cfg.get("max_tool_iterations", 15)):
        try:
            response = agent_core.call_model(messages, cfg)
        except Exception as e:
            api.send_message(chat_id, f"Ошибка: {e}")
            return

        if "error" in response:
            err = response["error"]
            err_code = err.get("code", "")
            if err_code == "tool_use_failed":
                consecutive_tool_errors += 1
                if consecutive_tool_errors >= 3:
                    api.send_message(chat_id, "Модель трижды не смогла корректно вызвать инструмент. Попробуй переформулировать.")
                    return
                err_message = err.get("message", "")
                if "which was not in request.tools" in err_message:
                    real_names = ", ".join(tools.TOOL_FUNCTIONS.keys())
                    messages.append({
                        "role": "user",
                        "content": f"Такого инструмента не существует. Доступные: {real_names}. Используй точно одно из этих имён.",
                    })
                else:
                    messages.append({
                        "role": "user",
                        "content": "Твой предыдущий вызов инструмента содержал невалидный JSON. Повтори вызов, тщательно проверив синтаксис.",
                    })
                continue
            api.send_message(chat_id, f"Ошибка модели: {err}")
            return

        consecutive_tool_errors = 0
        choice = response["choices"][0]
        msg = choice["message"]
        messages.append(msg)

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            content = msg.get("content", "") or "(пустой ответ)"
            api.send_message(chat_id, content)
            return

        for tc in tool_calls:
            result = agent_core.run_tool_call(tc, cfg, confirm_fn=confirm_fn, log_fn=log_fn)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": str(result),
            })
    else:
        api.send_message(chat_id, "Достигнут лимит итераций инструментов.")


def main():
    cfg = load_config()
    tg_cfg = cfg.get("telegram", {})
    token = tg_cfg.get("bot_token", "")
    allowed_ids = set(tg_cfg.get("allowed_user_ids", []))

    if not token or token == "ВСТАВЬ_СЮДА_ТОКЕН_БОТА":
        print("Telegram bot_token не настроен в config.json -> telegram.bot_token")
        print("Получи токен у @BotFather в Telegram и впиши его туда, либо запусти install.sh заново.")
        sys.exit(1)

    if not allowed_ids:
        print("ВНИМАНИЕ: telegram.allowed_user_ids пуст — бот не ответит НИКОМУ, пока ты")
        print("не впишешь свой Telegram user_id в config.json -> telegram.allowed_user_ids")
        print("Узнать свой ID можно у бота @userinfobot")

    api = TelegramAPI(token)
    sessions = {}
    offset = None

    print(f"Telegram-бот запущен. Разрешённые ID: {allowed_ids or '(никто)'}")
    print("Ctrl+C для остановки.")

    while True:
        try:
            updates = api.get_updates(offset=offset, timeout=30)
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2)
            continue
        except KeyboardInterrupt:
            print("\nОстановлено.")
            break

        if not updates.get("ok"):
            time.sleep(2)
            continue

        for update in updates.get("result", []):
            offset = update["update_id"] + 1

            if "callback_query" in update:
                cq = update["callback_query"]
                user_id = cq["from"]["id"]
                if allowed_ids and user_id not in allowed_ids:
                    api.answer_callback_query(cq["id"], "Нет доступа.")
                    continue
                handle_callback_query(api, cq)
                continue

            message = update.get("message")
            if not message or "text" not in message:
                continue

            user_id = message["from"]["id"]
            chat_id = message["chat"]["id"]
            text = message["text"]

            if allowed_ids and user_id not in allowed_ids:
                api.send_message(chat_id, "У тебя нет доступа к этому боту.")
                continue

            # Обработка в отдельном потоке, чтобы долгие ответы модели не
            # блокировали получение новых апдейтов (например callback кнопок)
            threading.Thread(
                target=process_user_message,
                args=(api, chat_id, text, cfg, sessions),
                daemon=True,
            ).start()


if __name__ == "__main__":
    main()
