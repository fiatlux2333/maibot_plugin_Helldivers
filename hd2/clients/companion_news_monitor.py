"""Companion 新闻订阅管理：会话列表 + 新闻指纹变更检测。

与 ``BilibiliMonitor`` 的订阅接口保持一致，但不含独立轮询循环——
变更检测由 ``main._companion_warmup_loop`` 在每次预热截图后驱动。
"""

from __future__ import annotations

import json
from pathlib import Path

from ..compat import logger


class CompanionNewsMonitor:
    """管理新闻推送订阅会话和上次新闻指纹。

    state.json 结构::

        {"sessions": ["group_123", "group_456"], "last_fingerprint": "abc123"}
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_dir / "state.json"
        self.sessions: list[str] = []
        self.last_fingerprint: str = ""
        self._load_state()

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self.sessions = [
                    str(x) for x in raw.get("sessions", []) if str(x).strip()
                ]
                self.last_fingerprint = str(raw.get("last_fingerprint", "") or "")
        except Exception as e:
            logger.warning(f"[HD2] Companion news monitor load state failed: {e}")

    def _save_state(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "sessions": self.sessions,
                    "last_fingerprint": self.last_fingerprint,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        temporary.replace(self.state_path)

    def subscribe(self, unified_msg_origin: str) -> bool:
        value = str(unified_msg_origin).strip()
        if not value or value in self.sessions:
            return False
        self.sessions.append(value)
        self._save_state()
        return True

    def unsubscribe(self, unified_msg_origin: str) -> bool:
        value = str(unified_msg_origin).strip()
        if value not in self.sessions:
            return False
        self.sessions.remove(value)
        self._save_state()
        return True

    def check_fingerprint(self, fingerprint: str) -> bool:
        """Check if the fingerprint differs from the last recorded one.

        Returns True if news has changed (or if this is the first call,
        which establishes the baseline).  Does NOT persist the new
        fingerprint — call ``commit_fingerprint`` after a successful
        push to record that this change has been delivered.
        """
        fp = str(fingerprint or "").strip()
        if not fp:
            return False
        if not self.last_fingerprint:
            logger.info(
                "[HD2] Companion news fingerprint baseline initialized: %s",
                fp[:12],
            )
            self.last_fingerprint = fp
            self._save_state()
            return False
        return fp != self.last_fingerprint

    def commit_fingerprint(self, fingerprint: str) -> None:
        """Persist a fingerprint after the corresponding push is complete.

        Called only after a successful (or intentionally skipped) delivery,
        so that a transient push failure doesn't permanently consume a
        news change — the next warmup cycle will re-detect it.
        """
        fp = str(fingerprint or "").strip()
        if fp and fp != self.last_fingerprint:
            self.last_fingerprint = fp
            self._save_state()
            logger.info(
                "[HD2] Companion news fingerprint committed: %s", fp[:12]
            )
