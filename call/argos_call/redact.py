"""Masking. No number, key or token is ever printed, written to a record or put in an error.

One `Redactor` per program knows every secret it must hide:

- the contact's number, in every way it can be written (with or without the country code,
  spaces, dots, dashes, brackets, or `%2B` for the plus sign in a URL);
- every key and secret read from the settings;
- every token minted while running (the agent's and the bridge's), added as they are made.

On top of what it knows, it masks anything shaped like a key or a token (`ftk_`, `sb_secret_`,
`sk_`, `AIza`, a JWT) and anything shaped like an international phone number, so a value
that was never registered is still caught.

Every log line passes through it (a filter on the one console handler), and so do uncaught
exceptions in any thread. Error messages built from an HTTP answer are masked where they are
built, because the answer can repeat what was sent.
"""

from __future__ import annotations

import logging
import re
import sys
import threading
import traceback
from collections.abc import Iterable
from urllib.parse import quote

MASK = "***"

_SEP = r"[\s().\-]*"
# Shapes of secrets, caught even if they were never registered.
_SHAPES = [
    re.compile(r"eyJ[\w-]{6,}\.[\w-]{6,}\.[\w-]{6,}"),  # a JWT (LiveKit tokens, legacy keys)
    re.compile(r"\b(?:ftk|ftw|sb_secret|sb_publishable|sk|xi)_[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),  # a Google API key
    re.compile(r"(?:\+|%2[Bb])\d[\d\s().\-]{8,}\d"),  # an international phone number
]


class Redactor:
    def __init__(self) -> None:
        self._exact: set[str] = set()
        self._patterns: list[re.Pattern[str]] = []
        self._lock = threading.Lock()

    def add_secret(self, value: str | None) -> None:
        """A key, a secret or a token. Masked as written and as it would appear in a URL."""
        if not value or len(value.strip()) < 6:
            return
        value = value.strip()
        with self._lock:
            self._exact.add(value)
            self._exact.add(quote(value, safe=""))

    def add_phone(self, value: str | None) -> None:
        """A phone number. Masked however it is formatted, with or without the country code."""
        if not value:
            return
        digits = re.sub(r"\D", "", value)
        if len(digits) < 7:
            self.add_secret(value)
            return
        national = digits[-10:] if len(digits) > 10 else digits
        country = digits[: len(digits) - len(national)]
        prefix = r"(?:\+|%2[Bb])?" + _SEP
        if country:
            prefix += "(?:" + _SEP.join(country) + _SEP + ")?"
        pattern = re.compile(prefix + _SEP.join(national))
        with self._lock:
            self._patterns.append(pattern)
            self._exact.add(value.strip())

    def add_all(self, values: Iterable[str | None]) -> None:
        for value in values:
            self.add_secret(value)

    def mask(self, text: object) -> str:
        text = str(text)
        with self._lock:
            exact = sorted(self._exact, key=len, reverse=True)
            patterns = list(self._patterns)
        for value in exact:
            if value in text:
                text = text.replace(value, MASK)
        for pattern in patterns:
            text = pattern.sub(MASK, text)
        for shape in _SHAPES:
            text = shape.sub(MASK, text)
        return text


class MaskingFilter(logging.Filter):
    """Masks the finished message and any exception text of every record it sees."""

    def __init__(self, redactor: Redactor) -> None:
        super().__init__()
        self.redactor = redactor

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # a bad format string must not escape unmasked
            message = f"{record.msg!r} {record.args!r}"
        record.msg = self.redactor.mask(message)
        record.args = None
        if record.exc_info:
            text = "".join(traceback.format_exception(*record.exc_info))
            record.exc_text = self.redactor.mask(text)
            record.exc_info = None
        if record.stack_info:
            record.stack_info = self.redactor.mask(record.stack_info)
        return True


class SafeError(Exception):
    """An error whose message has already been masked."""


def install(redactor: Redactor, level: int = logging.INFO,
            stream: object = None) -> logging.Handler:
    """One console handler for the whole program, masked. Uncaught exceptions, in the main
    thread and in any other thread, are printed masked too. Nothing is written to a file."""
    handler = logging.StreamHandler(stream or sys.stderr)  # type: ignore[arg-type]
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname).1s %(name)s: %(message)s",
                                           "%H:%M:%S"))
    handler.addFilter(MaskingFilter(redactor))
    root = logging.getLogger()
    for old in list(root.handlers):
        root.removeHandler(old)
    root.addHandler(handler)
    root.setLevel(level)
    # Libraries that would log request lines or their own internals at INFO.
    for noisy in ("httpx", "httpcore", "livekit", "websockets", "google_genai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    def excepthook(kind: type[BaseException], value: BaseException, tb: object) -> None:
        text = "".join(traceback.format_exception(kind, value, tb))  # type: ignore[arg-type]
        sys.stderr.write(redactor.mask(text))

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return
        text = "".join(traceback.format_exception(args.exc_type, args.exc_value,
                                                  args.exc_traceback))
        sys.stderr.write(redactor.mask(text))

    sys.excepthook = excepthook
    threading.excepthook = thread_hook
    return handler
