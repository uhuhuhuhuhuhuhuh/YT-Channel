"""Talk to any AI model: Claude, OpenAI, Gemini, OpenRouter, or a local model.

Pick a model with a "spec":

    claude                      the provider's default model (from config.yaml)
    claude:claude-sonnet-5      a specific model at a provider
    openai:gpt-5
    gemini:gemini-2.5-flash
    openrouter:meta-llama/llama-3.3-70b-instruct
    ollama:llama3.2             local, free, no key (https://ollama.com)
    lmstudio:qwen2.5-7b-instruct

Providers are listed under `ai.providers` in config.yaml. Two kinds exist:

- `anthropic`: Claude through the official Anthropic SDK
  (`pip install -e ".[draft]"`).
- `openai`: any server that speaks the OpenAI-compatible
  `/chat/completions` API. That covers OpenAI, Gemini, OpenRouter, Groq,
  Together, Mistral, DeepSeek, Ollama, LM Studio, llama.cpp, vLLM… No extra
  package is needed.

Add a new one by adding an entry to config.yaml. No code changes needed.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .config import load_config


class AIError(RuntimeError):
    pass


@dataclass
class Target:
    provider: str
    kind: str              # "anthropic" | "openai"
    model: str
    base_url: str | None
    api_key: str | None
    json_mode: bool        # send response_format={"type": "json_object"}
    extra_headers: dict
    max_tokens_param: str = "max_tokens"   # OpenAI's newer models want "max_completion_tokens"

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


def providers() -> dict:
    return (load_config().get("ai") or {}).get("providers") or {}


def resolve(spec: str | None = None) -> Target:
    """Turn "provider[:model]" into a Target. Empty spec → $YTC_MODEL → config default."""
    cfg = load_config().get("ai") or {}
    spec = (spec or os.environ.get("YTC_MODEL") or cfg.get("default") or "claude").strip()
    name, _, model = spec.partition(":")
    table = providers()
    if name not in table:
        raise AIError(f"unknown provider {name!r}. Configured: {', '.join(sorted(table))} "
                      "(add more under ai.providers in config.yaml)")
    p = table[name]
    kind = p.get("type", "openai")
    if kind not in ("anthropic", "openai"):
        raise AIError(f"provider {name!r}: type must be 'anthropic' or 'openai'")
    model = model or p.get("model")
    if not model:
        raise AIError(f"provider {name!r} has no default model; use {name}:<model>")
    key_env = p.get("key_env")
    key = os.environ.get(key_env) if key_env else None
    return Target(name, kind, model, p.get("base_url"), key, bool(p.get("json_mode", False)),
                  dict(p.get("headers") or {}), p.get("max_tokens_param", "max_tokens"))


# --------------------------------------------------------------------------
# Calls
# --------------------------------------------------------------------------


def _anthropic(t: Target, system: str, prompt: str, max_tokens: int, schema: dict | None) -> str:
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover - depends on the machine
        raise AIError('Claude needs the Anthropic SDK: pip install -e ".[draft]"') from e

    client = anthropic.Anthropic(api_key=t.api_key) if t.api_key else anthropic.Anthropic()
    kwargs: dict = {}
    output_config: dict = {}
    if "haiku" not in t.model:                     # Haiku 4.5 doesn't take adaptive thinking
        kwargs["thinking"] = {"type": "adaptive"}
        output_config["effort"] = "high"
    if schema:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    if output_config:
        kwargs["output_config"] = output_config
    if t.model in ("claude-opus-5", "claude-fable-5-1"):
        # re-run a safety-declined request on Anthropic's recommended fallback model
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["fallbacks"] = "default"
        create = client.beta.messages.create
    else:
        create = client.messages.create
    try:
        response = create(model=t.model, max_tokens=max_tokens, system=system,
                          messages=[{"role": "user", "content": prompt}], **kwargs)
    except anthropic.APIConnectionError as e:
        raise AIError(f"{t}: could not reach the Anthropic API ({e})") from e
    except anthropic.AuthenticationError as e:
        raise AIError(f"{t}: authentication failed. Set ANTHROPIC_API_KEY or run `ant auth login`") from e
    except anthropic.APIStatusError as e:
        raise AIError(f"{t}: API error {e.status_code}: {e.message}") from e
    if response.stop_reason == "refusal":
        raise AIError(f"{t} declined this request: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise AIError(f"{t}: the answer was cut off (max_tokens={max_tokens})")
    return "".join(b.text for b in response.content if b.type == "text")


def _openai_compatible(t: Target, system: str, prompt: str, max_tokens: int, want_json: bool) -> str:
    if not t.base_url:
        raise AIError(f"provider {t.provider!r} needs a base_url in config.yaml")
    body: dict = {
        "model": t.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        t.max_tokens_param: max_tokens,
    }
    if want_json and t.json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json", **t.extra_headers}
    if t.api_key:
        headers["Authorization"] = f"Bearer {t.api_key}"
    url = t.base_url.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=float(os.environ.get("YTC_AI_TIMEOUT", 600))) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        hint = ""
        if e.code in (401, 403):
            key_env = providers()[t.provider].get("key_env")
            hint = f" Check that {key_env} is set." if key_env else ""
        raise AIError(f"{t}: HTTP {e.code} from {url}: {detail}{hint}") from e
    except urllib.error.URLError as e:
        local = "localhost" in url or "127.0.0.1" in url
        hint = " Is the local server running (e.g. `ollama serve`)?" if local else ""
        raise AIError(f"{t}: could not reach {url} ({e.reason}).{hint}") from e
    try:
        choice = data["choices"][0]
        text = choice["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise AIError(f"{t}: unexpected response: {json.dumps(data)[:300]}") from e
    if choice.get("finish_reason") == "length":
        raise AIError(f"{t}: the answer was cut off (max_tokens={max_tokens})")
    return text


def ask(prompt: str, system: str = "You are a helpful assistant.", model: str | None = None,
        max_tokens: int = 8000) -> str:
    """Send one prompt to the chosen model and return its text answer."""
    t = resolve(model)
    if t.kind == "anthropic":
        return _anthropic(t, system, prompt, max_tokens, None)
    return _openai_compatible(t, system, prompt, max_tokens, want_json=False)


# --------------------------------------------------------------------------
# JSON answers
# --------------------------------------------------------------------------


def extract_json(text: str) -> dict:
    """Pull a JSON object out of a model's reply (handles ```json fences and chatter)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else text
    start = candidate.find("{")
    if start < 0:
        raise ValueError("no JSON object in the reply")
    obj, _ = json.JSONDecoder().raw_decode(candidate[start:])
    if not isinstance(obj, dict):
        raise ValueError("reply JSON is not an object")
    return obj


def ask_json(prompt: str, system: str, schema: dict, model: str | None = None,
             max_tokens: int = 16000, attempts: int = 3,
             validate: Callable[[dict], object] | None = None):
    """Ask for a JSON object matching `schema`.

    Claude gets the schema as a structured-output constraint, so its reply is
    always valid JSON. Other models get the schema in the prompt and retries
    with feedback when the reply doesn't parse. `validate(obj)` may raise
    ValueError to trigger a retry; its return value is what ask_json returns.
    """
    validate = validate or (lambda obj: obj)
    t = resolve(model)
    if t.kind == "anthropic":
        return validate(json.loads(_anthropic(t, system, prompt, max_tokens, schema)))
    system = (f"{system}\n\nReply with ONE JSON object and nothing else (no prose, no code fences). "
              f"It must match this JSON Schema:\n{json.dumps(schema)}")
    last_error = ""
    for _ in range(attempts):
        p = prompt if not last_error else (
            f"{prompt}\n\nYour previous reply could not be used ({last_error}). "
            "Reply again with only the JSON object.")
        text = _openai_compatible(t, system, p, max_tokens, want_json=True)
        try:
            return validate(extract_json(text))
        except ValueError as e:
            last_error = str(e)
    raise AIError(f"{t} did not return valid JSON after {attempts} tries ({last_error})")


def status() -> list[tuple[str, str, str]]:
    """(provider, default model, readiness note) for `ytc models`."""
    rows = []
    for name, p in providers().items():
        key_env = p.get("key_env")
        if key_env:
            note = f"{key_env} set" if os.environ.get(key_env) else f"needs {key_env}"
            if p.get("type") == "anthropic" and not os.environ.get(key_env):
                note += " (or `ant auth login`)"
        else:
            note = f"local, no key ({p.get('base_url')})"
        rows.append((name, p.get("model", "?"), note))
    return rows
