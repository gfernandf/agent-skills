from __future__ import annotations


import official_services.web_baseline as web_baseline


class _FakeResponse:
    def __init__(self, html: str) -> None:
        self._raw = html.encode("utf-8")

    def read(self, _max_bytes: int) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_search_web_respects_limit_and_emits_content(monkeypatch):
    html = """
    <a class="result__a" href="https://example.com/a">Alpha</a>
    <a class="result__snippet">First snippet</a>
    <a class="result__a" href="https://example.com/b">Beta</a>
    <a class="result__snippet">Second snippet</a>
    """

    def fake_urlopen(_req, timeout=None):  # noqa: ARG001
        return _FakeResponse(html)

    monkeypatch.setattr(web_baseline.urllib.request, "urlopen", fake_urlopen)

    out = web_baseline.search_web("agent test", limit=1)
    assert isinstance(out, dict)
    assert "results" in out
    assert len(out["results"]) == 1
    assert out["results"][0]["content"] == "Alpha. First snippet"


def test_search_web_returns_empty_on_provider_failures(monkeypatch):
    def failing_urlopen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("network down")

    monkeypatch.setattr(web_baseline.urllib.request, "urlopen", failing_urlopen)

    out = web_baseline.search_web("agent test", limit=3)
    assert out == {"results": []}
