"""Small, deterministic voice-command parser.

Only commands that start with an explicit wake word are considered. This is
deliberately not an LLM: the supported grammar is predictable and offline.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlparse


@dataclass(frozen=True)
class Command:
    kind: str
    value: object = None


_APP_ALIASES = {
    "ブラウザ": "browser", "chrome": "browser", "クローム": "browser",
    "ターミナル": "terminal", "端末": "terminal", "コマンドプロンプト": "terminal",
    "ファイル": "files", "フォルダ": "files",
    "ファイルマネージャー": "files", "エクスプローラー": "files",
    "設定": "settings", "settings": "settings",
}

_FOLDER_ALIASES = {
    "ホーム": "home", "ダウンロード": "downloads",
    "ダウンロードフォルダ": "downloads", "デスクトップ": "desktop",
    "ドキュメント": "documents",
}


class CommandRouter:
    def __init__(self, wake_words):
        words = {w.strip().lower() for w in wake_words if w.strip()}
        # Whisper commonly drops the Japanese long-vowel mark here.
        words.update(w[:-1] for w in tuple(words) if w.endswith("ー"))
        self.wake_words = tuple(sorted(words, key=len, reverse=True))

    def parse(self, text: str) -> Command | None:
        body = self._strip_wake_word(text)
        if body is None:
            return None
        normalized = body.lower().strip(" 。、,.!！?？")
        normalized = re.sub(r"(?:ください|下さい)$", "", normalized).rstrip(" 。、,.!！?？")
        normalized = re.sub(r"^パソコンの", "", normalized)
        if normalized in {"今何時", "今何時ですか", "時刻を教えて", "時間を教えて"}:
            return Command("time")
        if normalized in {"今日は何日", "今日は何日ですか", "日付を教えて"}:
            return Command("date")
        volume = self._parse_volume(normalized)
        if volume:
            return volume
        for label, folder in sorted(_FOLDER_ALIASES.items(), key=lambda x: -len(x[0])):
            if normalized in {f"{label}を開いて", f"{label}開いて", f"{label}を表示して"}:
                return Command("open_folder", folder)
        for label, app in sorted(_APP_ALIASES.items(), key=lambda x: -len(x[0])):
            if normalized in {f"{label}を開いて", f"{label}開いて", f"{label}を起動して"}:
                return Command("open_app", app)
        match = re.fullmatch(r"(?:ブラウザで)?(.+?)(?:を)?検索して", normalized)
        if match:
            query = match.group(1).strip()
            if query:
                return Command("web_search", query)
        match = re.fullmatch(r"(https?://\S+?)(?:を)?開いて", normalized)
        if match and self._safe_url(match.group(1)):
            return Command("open_url", match.group(1))
        return Command("unknown", body.strip())

    def _strip_wake_word(self, text):
        candidate = text.strip().lower()
        for wake_word in self.wake_words:
            if candidate.startswith(wake_word):
                return candidate[len(wake_word):].lstrip(" 、,。:：")
        return None

    @staticmethod
    def _safe_url(value):
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _parse_volume(text):
        if text in {"ミュートして", "消音して", "音を消して"}:
            return Command("volume", "mute")
        if text in {"ミュートを解除して", "消音を解除して", "音を戻して"}:
            return Command("volume", "unmute")
        if text in {"音量を上げて", "ボリュームを上げて"}:
            return Command("volume", "up")
        if text in {"音量を下げて", "ボリュームを下げて"}:
            return Command("volume", "down")
        match = re.fullmatch(r"(?:音量|ボリューム)を?(\d{1,3})(?:パーセント|%)?(?:に)?して", text)
        if match:
            return Command("volume", max(0, min(100, int(match.group(1)))))
        return None
