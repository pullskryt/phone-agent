# coding: utf-8
"""
Провайдер для локальных моделей через llama.cpp сервер (llama-server).
llama-server сам поднимает OpenAI-совместимый /v1/chat/completions эндпоинт,
поэтому формат запроса идентичен api.py — просто другой url и без ключа.

ВАЖНО: сервер нужно запускать отдельно перед стартом агента:
    llama-server -m /путь/к/model.gguf -c 4096 --port 8080

Не все локальные модели умеют нормально в function calling — качество
tool-calling сильно зависит от модели (лучше всего — модели с пометкой
"tool use" / "function calling" в описании, напр. Hermes, Qwen2.5-Instruct).
"""
import json
import urllib.request
import urllib.error


def chat(messages, tools, cfg):
    url = cfg["server_url"]

    body = {
        "model": "local",
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.3,
    }

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Не удалось подключиться к локальному серверу ({url}). "
            f"Запущен ли llama-server? Ошибка: {e}"
        )
    except Exception as e:
        raise RuntimeError(f"Ошибка запроса к локальной модели: {e}")
