from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class HttpClient:
    user_agent: str
    timeout_seconds: int = 20

    def fetch_text(self, url: str, headers: dict[str, str] | None = None) -> str:
        request_headers = {"User-Agent": self.user_agent, **(headers or {})}
        request = urllib.request.Request(url, headers=request_headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc

    def fetch_json(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        text = self.fetch_text(url, headers={"Accept": "application/json", **(headers or {})})
        return json.loads(text)

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers = {
            "User-Agent": self.user_agent,
            "Content-Type": "application/json; charset=utf-8",
            **(headers or {}),
        }
        request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                text = response.read().decode("utf-8", errors="replace")
                if not text:
                    return {}
                return json.loads(text)
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"HTTP {exc.code} for {url}: {body_text}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc

    def post_form(self, url: str, payload: dict[str, str]) -> str:
        body = urllib.parse.urlencode(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"HTTP {exc.code} for {url}: {body_text}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc
