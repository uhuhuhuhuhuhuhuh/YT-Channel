"""AI provider layer, tested against a fake OpenAI-compatible server (no network)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ytc import ai, config, writer


class FakeServer:
    """Answers /chat/completions with queued replies and records the requests."""

    def __init__(self):
        self.replies: list[str] = []
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
                text = outer.replies.pop(0) if outer.replies else "ok"
                payload = json.dumps({"choices": [{"message": {"role": "assistant", "content": text},
                                                   "finish_reason": "stop"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def fake(monkeypatch):
    server = FakeServer()
    cfg = dict(config.load_config())
    cfg["ai"] = {"default": "fake", "providers": {
        "fake": {"type": "openai", "base_url": server.url, "model": "tiny", "key_env": "FAKE_KEY",
                 "json_mode": True},
        "claude": {"type": "anthropic", "model": "claude-opus-5", "key_env": "ANTHROPIC_API_KEY"},
    }}
    monkeypatch.setattr(ai, "load_config", lambda: cfg)
    monkeypatch.setenv("FAKE_KEY", "sk-test")
    monkeypatch.delenv("YTC_MODEL", raising=False)
    yield server
    server.close()


def test_resolve_specs(fake, monkeypatch):
    assert str(ai.resolve()) == "fake:tiny"
    assert str(ai.resolve("fake:big-model")) == "fake:big-model"
    assert str(ai.resolve("claude")) == "claude:claude-opus-5"
    monkeypatch.setenv("YTC_MODEL", "fake:from-env")
    assert str(ai.resolve()) == "fake:from-env"
    with pytest.raises(ai.AIError, match="unknown provider"):
        ai.resolve("nope:x")


def test_model_names_with_colons_survive():
    # Ollama tags look like "qwen2.5:14b"
    assert ai.resolve("ollama:qwen2.5:14b").model == "qwen2.5:14b"


def test_ask_sends_openai_compatible_request(fake):
    fake.replies.append("An octopus has three hearts.")
    assert ai.ask("How many hearts?", system="Be brief.", model="fake:tiny") == "An octopus has three hearts."
    req = fake.requests[0]
    assert req["path"] == "/v1/chat/completions"
    assert req["auth"] == "Bearer sk-test"
    assert req["body"]["model"] == "tiny"
    assert req["body"]["messages"][0] == {"role": "system", "content": "Be brief."}
    assert "response_format" not in req["body"]


def test_extract_json_handles_fences_and_chatter():
    assert ai.extract_json('Sure! ```json\n{"a": 1}\n``` hope that helps') == {"a": 1}
    assert ai.extract_json('Here you go: {"a": {"b": [1, 2]}} bye') == {"a": {"b": [1, 2]}}
    with pytest.raises(ValueError):
        ai.extract_json("no json here")


def test_ask_json_retries_once_then_succeeds(fake):
    fake.replies += ["I can't do JSON today", '{"title": "ok"}']
    assert ai.ask_json("go", "sys", {"type": "object"}, model="fake") == {"title": "ok"}
    assert len(fake.requests) == 2
    assert fake.requests[0]["body"]["response_format"] == {"type": "json_object"}
    assert "could not be used" in fake.requests[1]["body"]["messages"][1]["content"]


def test_unreachable_local_server_gives_hint(monkeypatch):
    cfg = dict(config.load_config())
    cfg["ai"] = {"providers": {"local": {"type": "openai", "base_url": "http://127.0.0.1:9/v1", "model": "m"}}}
    monkeypatch.setattr(ai, "load_config", lambda: cfg)
    with pytest.raises(ai.AIError, match="local server running"):
        ai.ask("hi", model="local")


def test_clean_repairs_sloppy_local_model_output():
    messy = {
        "title": "Cats Purr?!",
        "segments": [
            {"say": "Cats   purr   when happy.", "headline": "PURR PURR PURR PURR PURR PURR PURR",
             "bg": "not-a-bg", "sprites": [{"name": "Cat", "x": "2", "y": 0.9, "size": 5, "motion": "moonwalk"}]},
            {"say": "", "sprites": []},
            "garbage",
        ],
    }
    out = writer.clean(messy)
    assert len(out["segments"]) == 1
    seg = out["segments"][0]
    assert seg["say"] == "Cats purr when happy."
    assert len(seg["headline"]) <= 28
    assert seg["bg"] == "sunny"
    sp = seg["sprites"][0]
    assert sp == {"name": "cat", "x": 0.92, "y": 0.62, "size": 0.6, "motion": "float"}
    assert out["thumbnail_sprite"] == "cat"


def test_draft_end_to_end_with_fake_model(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(writer, "EPISODES", tmp_path)
    monkeypatch.setattr(writer, "list_episodes", lambda: [])
    draft = {
        "title": "Why Do Cats Purr? #shorts", "slug": "cats-purr", "description": "Purr facts.",
        "tags": ["cats"], "thumbnail_text": "PURR?!", "thumbnail_sprite": "cat",
        "segments": [{"say": "Cats purr when they are happy.", "headline": "PURR!", "bg": "sunny",
                      "sprites": [{"name": "cat", "x": 0.5, "y": 0.45, "size": 0.4, "motion": "bounce"}]}],
        "sources": ["Example: https://example.org"],
    }
    fake.replies.append("```json\n" + json.dumps(draft) + "\n```")
    path = writer.draft("cats purring", "facts", model="fake:tiny")
    from ytc.episode import load_episode

    ep = load_episode(path)
    assert ep.title == draft["title"]
    assert ep.segments[0].sprites[0].motion == "bounce"
    assert path.endswith("001-why-do-cats-purr/episode.yaml")
    assert "fake:tiny" in open(path).read()


def test_draft_retries_when_json_is_structurally_useless(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(writer, "EPISODES", tmp_path)
    monkeypatch.setattr(writer, "list_episodes", lambda: [])
    fake.replies += ['{"title": "Cats"}',
                     '{"title": "Cats", "segments": [{"say": "Cats purr.", "sprites": []}]}']
    path = writer.draft("cats", model="fake")
    assert len(fake.requests) == 2
    assert "segments" in fake.requests[1]["body"]["messages"][1]["content"]
    assert "Cats purr." in open(path).read()


@pytest.mark.parametrize("guess, expected", [
    ("cat_girl", "cat"), ("Red Heart", "red heart"), ("jack o lantern", "jack-o-lantern"),
    ("happy cat face", "cat"), ("qwertyuiop", "bitsy"),
])
def test_sprite_names_map_to_real_sprites(guess, expected):
    assert writer.sprite_name(guess, writer.known_sprites()) == expected


def test_speakable_strips_emoji():
    assert writer.speakable("Cats purr! 🐱💕 Wow 👍🏽") == "Cats purr! Wow"
