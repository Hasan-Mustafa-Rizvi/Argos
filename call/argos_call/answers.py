"""Gemini on the call: hears one utterance, says whether it acknowledges, and answers a
question from the incident only.

Plain `generateContent` with the utterance as inline WAV and a JSON answer: one request per
thing the person says, so nothing is streamed, stored or kept open. The model is
`GEMINI_MODEL` (default `gemini-3.5-flash-lite`, the brain's), which takes audio and returns
text; ElevenLabs then speaks the text in Argos's voice.

Rule 6 is held twice: the instructions say what may be said, and every reply is checked
before it is spoken. A reply that diagnoses, says someone is hurt or fine, or gives advice
other than calling emergency services is replaced by a plain "I don't know".

The utterance goes to Google and nowhere else. On Gemini's free tier Google may keep what
it is sent; use a paid-tier key, or leave GEMINI_API_KEY empty to keep the person's voice on
this machine (the agent then hears only the fixed acknowledgement phrases, offline).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from argos_call.hearing import wav
from argos_call.incident import Incident, clean

log = logging.getLogger("argos_call.answers")

SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["acknowledge", "question", "other"]},
        "reply": {"type": "string"},
    },
    "required": ["intent", "reply"],
}

UNKNOWN = ("I don't know that. I can only tell you what I saw and heard. If you think it is "
           "needed, call emergency services.")

# Words that would diagnose, or say someone is hurt or fine. Checked on every reply.
_FORBIDDEN = re.compile(
    r"\b(hurt|injur\w*|unconscious|conscious|breathing|bleeding|blood|broken|fractur\w*|"
    r"stroke|heart attack|seizure|faint\w*|dizz\w*|dead|died|alive|pain|safe|fine|"
    r"diagnos\w*|medical condition|medication|ambulance is (?:on|coming)|"
    r"(?:is|are|was|seems|looks|appears)\s+(?:ok|okay|alright|all right|well|unharmed))\b",
    re.IGNORECASE)
_ASKED = re.compile(r"asked (?:if|whether) [\w\s']{1,40}? (?:was|is|were) "
                    r"(?:ok|okay|alright|all right)", re.IGNORECASE)
_ADVICE = re.compile(r"\b(you should|i recommend|i suggest|try to|make sure|give (?:her|him|"
                     r"them)|lift|move (?:her|him|them)|cpr|first aid)\b", re.IGNORECASE)


@dataclass
class Understood:
    intent: str  # acknowledge, question, other, or error when Gemini could not answer
    reply: str


def safe_reply(reply: str) -> str:
    """The reply if it keeps to rule 6, else the plain "I don't know"."""
    reply = clean(" ".join(str(reply).split()))
    if not reply:
        return ""
    allowed = reply.replace("call emergency services", "")
    allowed = _ASKED.sub("", allowed)  # "I asked if Eleni was okay" restates the check
    if _FORBIDDEN.search(allowed) or _ADVICE.search(allowed):
        return UNKNOWN
    sentences = re.split(r"(?<=[.!?])\s+", reply)
    return " ".join(sentences[:3]).strip()


def instructions(incident: Incident, timeline: list[str], on_screen: str, label: str,
                 noticed: str) -> str:
    facts = [f"At {incident.time}, {noticed}. Argos asked if {incident.who} was okay and got "
             "no answer, so it called."]
    facts.append(f"Argos's written note: {incident.summary}" if incident.summary
                 else "Argos has no written note about what it saw.")
    if timeline:
        facts.append("Timeline of this alert: " + " ".join(timeline))
    facts.append(f"On the caller's screen now: {on_screen}.")
    return "\n".join([
        f"You are the voice of Argos, a companion robot dog that watches over {incident.who} "
        f"at home. You are on a FaceTime call with {label}, the emergency contact, because "
        "a safety check failed.",
        "Facts you may use, and nothing else:",
        *[f"- {fact}" for fact in facts],
        "Rules:",
        "- Say only what these facts say. If the answer is not in them, say you do not know.",
        "- Never diagnose. Never say anyone is hurt, injured, unconscious, fine, safe or okay, "
        "and never guess at a medical condition.",
        "- The only advice you may give is to call emergency services if they think it is "
        "needed.",
        "- Never describe or comment on the caller.",
        "- If you are shown Argos's camera, you may say plainly what it shows now, without "
        "judging anyone's health.",
        "- Speak in one or two short, plain sentences. No lists. No dashes.",
        "Listen to the caller's audio and decide:",
        '- intent "acknowledge": they say they are coming, on their way, will handle it, or '
        'acknowledge the alert. Then reply is empty.',
        '- intent "question": they ask something. Then reply answers it under the rules.',
        '- intent "other": anything else, or nothing clear. Then reply is a short, polite '
        "line that invites them to ask a question or say they are on their way.",
    ])


Generate = Callable[[str, bytes, bytes | None], Awaitable[str]]


def sdk_generate(api_key: str, model: str, timeout_s: float = 10.0) -> Generate:
    """The real request, through google-genai's async client."""
    from google import genai
    from google.genai import types

    timeout_s = max(10.0, timeout_s)  # Gemini refuses a deadline under 10 seconds
    client = genai.Client(api_key=api_key,
                          http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))

    async def generate(system: str, audio_wav: bytes, camera_jpeg: bytes | None) -> str:
        contents: list[object] = []
        if camera_jpeg:
            contents += [types.Part.from_bytes(data=camera_jpeg, mime_type="image/jpeg"),
                         "This is what Argos's camera shows right now."]
        contents += [types.Part.from_bytes(data=audio_wav, mime_type="audio/wav"),
                     "This is what the caller just said."]
        response = await client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_json_schema=SCHEMA,
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                temperature=0.2,
            ),
        )
        return response.text or ""

    return generate


class Answers:
    def __init__(self, generate: Generate) -> None:
        self._generate = generate

    async def understand(self, pcm: bytes, system: str,
                         camera_jpeg: bytes | None = None) -> Understood:
        try:
            raw = await self._generate(system, wav(pcm), camera_jpeg)
            data = json.loads(raw)
            intent = str(data.get("intent") or "other")
            reply = str(data.get("reply") or "")
        except Exception as exc:
            log.warning("Gemini could not answer (%s)", type(exc).__name__)
            return Understood("error", "")
        if intent not in ("acknowledge", "question", "other"):
            intent = "other"
        return Understood(intent, "" if intent == "acknowledge" else safe_reply(reply))
