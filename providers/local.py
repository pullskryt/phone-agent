# coding: utf-8
"""
Провайдер для локальных моделей через Ollama.
Ollama ставится в Termux одной командой (pkg install ollama) и сама
поднимает OpenAI-совместимый /v1/chat/completions эндпоинт на порту 11434
(см. local_setup.sh — он всё делает автоматически: установка, запуск сервера,
скачивание модели, прописывание в config.json).

Не все локальные модели умеют нормально в function calling — качество
tool-calling сильно зависит от модели. Модели линейки Qwen2.5-Instruct
(qwen2.5:1.5b / 3b / 7b) — неплохой выбор для телефона.
"""
import json
import urllib.request
import urllib.error


def chat(messages, tools, cfg):
    url = cfg["server_url"]
    model = cfg.get("model", "qwen2.5:3b")

    body = {
        "model": model,
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
            f"Не удалось подключиться к Ollama ({url}). "
            f"Сервер запущен? Попробуй: bash local_start.sh. Ошибка: {e}"
        )
    except Exception as e:
        raise RuntimeError(f"Ошибка запроса к локальной модели: {e}")
