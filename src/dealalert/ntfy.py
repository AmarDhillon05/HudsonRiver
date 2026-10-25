"""Push alerts through ntfy (https://ntfy.sh or self-hosted).

Published as JSON so titles with non-ASCII characters (14", ™) survive.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import http

# ntfy priorities: 1 min, 2 low, 3 default, 4 high, 5 urgent.
AT_TARGET = 4
NEAR_TARGET = 3
CHECK_PRICE = 2


@dataclass(frozen=True)
class Alert:
    title: str
    message: str
    priority: int
    url: str
    tags: tuple[str, ...] = ()


class NtfySender:
    def __init__(self, topic: str, server: str = "https://ntfy.sh", token: str | None = None):
        self.topic = topic
        self.server = server.rstrip("/")
        self.token = token

    def send(self, alert: Alert) -> None:
        headers = {"Authorization": "Bearer " + self.token} if self.token else {}
        http.post_json(
            self.server,
            {
                "topic": self.topic,
                "title": alert.title,
                "message": alert.message,
                "priority": alert.priority,
                "tags": list(alert.tags),
                "click": alert.url,
            },
            headers,
        )


class ConsoleSender:
    """Prints instead of pushing; used by ``python -m dealalert.cli``."""

    def __init__(self):
        self.sent: list[Alert] = []

    def send(self, alert: Alert) -> None:
        self.sent.append(alert)
        print(f"[p{alert.priority}] {alert.title}\n    {alert.message}\n    {alert.url}")
