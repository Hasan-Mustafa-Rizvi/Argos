"""The Gemini check: one frame, two questions, real calls with `GEMINI_API_KEY`.

Package `google-genai` (the current SDK; `google-generativeai` is retired). Model
`gemini-3.5-flash-lite` by default (`GEMINI_MODEL`): stable, takes images, returns JSON, and
thinks only minimally, so it answers fast. The image goes inline as JPEG bytes with
`types.Part.from_bytes(data=..., mime_type="image/jpeg")`.

1. `check(frame)`: when a `fall` or `stillness` check starts, how likely the frame shows a
   person who may need help, 0 to 1. It updates the incident's `confidence`. It never
   cancels a check, and the check never waits for it.
2. `summary(frame, trigger)`: after an escalation, one or two plain sentences on what Argos
   saw. No guess at identity, age or medical condition, and no dashes (any that come back
   are removed).

A `help_call` is not sent: the camera adds nothing reliable to what was heard, and a frame
sent without need is a frame that left the machine.

The frame is sent and not kept. On Google's free tier, what is sent may be used to improve
Google's products and read by reviewers; use a paid-tier key for anything real.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Any

from argos import images, text

log = logging.getLogger("argos.gemini")

CHECK_PROMPT = (
    "You help a home safety robot decide whether to check on someone. Look at this single "
    "camera image. How likely is it that it shows a person who may need help right now, for "
    "example someone lying on the floor, slumped, or fallen? Give a score from 0 (no person, "
    "or clearly fine) to 1 (very likely needs help). Do not guess who the person is, their "
    "age, or any medical condition."
)
SUMMARY_PROMPT = (
    "A home safety robot noticed this: {reason} It asked the person \"Are you okay?\" and "
    "got no answer, so it is alerting their family. In one or two short, plain sentences, "
    "describe what this image shows about the person and where they are. Describe only what "
    "is visible. Do not guess who they are, their age, or any medical condition. Do not use "
    "dashes. Write only the sentences."
)
REASONS = {
    "fall": "it saw someone on the floor.",
    "stillness": "someone had not moved for a long time.",
    "help_call": "it heard a call for help.",
    "manual": "a check was started by hand.",
}
SCORE_SCHEMA = {
    "type": "object",
    "properties": {"score": {"type": "number", "minimum": 0, "maximum": 1}},
    "required": ["score"],
}

Generate = Callable[[str, bytes, dict[str, Any] | None], str]

# The SDK sends its time limit to Google as the request's deadline, and the API refuses any
# deadline under 10 s with HTTP 400 ("Manually set deadline 8s is too short. Minimum allowed
# deadline is 10s."), seen on the real Pi. So the SDK is given at least 10 s. The brain's own
# limits (`ARGOS_GEMINI_TIMEOUT_S` for the check, `ARGOS_SUMMARY_TIMEOUT_S` for the summary)
# are kept around each call by `brain.call_with_timeout`, unchanged.
SERVER_MIN_DEADLINE_S = 10.0


def sdk_timeout_ms(timeout_s: float) -> int:
    """The time limit to give the SDK: the brain's own, raised to the API's minimum."""
    return int(max(timeout_s, SERVER_MIN_DEADLINE_S) * 1000)


def sdk_generate(api_key: str, model: str, timeout_s: float) -> Generate:
    """The real call, through google-genai."""
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=api_key, http_options=types.HttpOptions(timeout=sdk_timeout_ms(timeout_s))
    )

    def generate(prompt: str, jpeg: bytes, schema: dict[str, Any] | None) -> str:
        config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="minimal"),
            **({"response_mime_type": "application/json", "response_json_schema": schema}
               if schema else {}),
        )
        response = client.models.generate_content(
            model=model,
            contents=[types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"), prompt],
            config=config,
        )
        return response.text or ""

    return generate


def first_sentences(value: str, count: int = 2) -> str:
    value = text.clean(" ".join(value.split()))
    parts = re.split(r"(?<=[.!?])\s+", value)
    return " ".join(parts[:count]).strip()


class GeminiJudge:
    def __init__(self, generate: Generate, max_side: int = 768) -> None:
        self._generate = generate
        self.max_side = max_side

    def _jpeg(self, frame: Any) -> bytes:
        return images.jpeg(images.image_of(frame), max_side=self.max_side, quality=80)

    def check(self, frame: Any) -> float | None:
        try:
            answer = self._generate(CHECK_PROMPT, self._jpeg(frame), SCORE_SCHEMA)
            score = float(json.loads(answer)["score"])
        except Exception as exc:
            log.warning("Gemini check failed (%s); confidence stays as it is",
                        type(exc).__name__)
            return None
        return min(1.0, max(0.0, score))

    def summary(self, frame: Any, trigger: str) -> str | None:
        prompt = SUMMARY_PROMPT.format(reason=REASONS.get(trigger, "something was wrong."))
        try:
            answer = self._generate(prompt, self._jpeg(frame), None)
        except Exception as exc:
            log.warning("Gemini summary failed (%s); using the fixed sentence",
                        type(exc).__name__)
            return None
        written = first_sentences(answer)
        return written or None
