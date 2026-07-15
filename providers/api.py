# coding: utf-8
"""
Провайдер для облачных API (Groq, OpenAI, любой OpenAI-совместимый эндпоинт).
"""
import json
import re
import urllib.request
import urllib.error


class RateLimitError(Exception):
    """Превышен лимит токенов/запросов. retry_after — секунды до повтора."""
    def __init__(self, message, retry_after=15):
        super().__init__(message)
        self.retry_after = retry_after


def _extract_retry_seconds(err_body: str, default=15) -> float:
    # Groq пишет в сообщении что-то вроде "Please try again in 12.495s."
    match = re.search(r"try again in ([\d.]+)s", err_body)
    if match:
        try:
            return float(match.group(1)) + 0.5  # небольшой запас
        except ValueError:
            pass
    return default


def chat(messages, tools, cfg):
    """
    cfg — словарь cfg["api"] из config.json
    Возвращает сырой JSON-ответ модели (dict).
    """
    url = cfg["base_url"]
    api_key = cfg["api_key"]
    model = cfg["model"]

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
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            # Без User-Agent Cloudflare перед Groq блокирует запрос как
            # автоматизированный (error code: 1010), даже с валидным ключом.
            "User-Agent": "termux-ai-agent/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        if e.code == 429:
            retry_after = _extract_retry_seconds(err_body)
            raise RateLimitError(err_body, retry_after=retry_after)
        raise RuntimeError(f"API ошибка {e.code}: {err_body}")
    except Exception as e:
        raise RuntimeError(f"Ошибка запроса к API: {e}")
