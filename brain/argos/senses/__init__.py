"""Stage 2: the camera, the ears, the voice, Gemini, the snapshot and the live view.

Each part is built here if it can be. Any part that cannot (no camera, no model file, no
microphone, no key, no network) is logged once, plainly, and left out. The keyboard always
works alongside whatever is here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from argos.body.base import BodyHub
from argos.clock import Clock
from argos.config import Settings
from argos.store import Store

log = logging.getLogger("argos.senses")


@dataclass
class Senses:
    camera: Any = None
    vision: Any = None
    listener: Any = None
    voice: Any = None
    judge: Any = None
    uploader: Callable[[str, Any], str | None] | None = None
    live_view: Any = None

    @property
    def frames(self) -> Any:
        return self.camera

    def start(self, brain: Any) -> None:
        from argos.brain import AnswerIn, HeardIn, TriggerIn

        if self.voice is not None:
            self.voice.gate = brain.gate
            self.voice.beep = brain.bodies.beep
            self.voice.prefetch()
        if self.camera is not None:
            self.camera.start()
        if self.vision is not None:
            self.vision.on_trigger = lambda kind, conf, frame: brain.post(
                TriggerIn(kind, conf, source="camera", frame=frame))
            self.vision.can_trigger = brain.can_trigger
            self.vision.start()
        if self.listener is not None:
            self.listener.gate = brain.gate
            self.listener.on_help = lambda conf: brain.post(
                TriggerIn("help_call", conf, source="microphone"))
            self.listener.on_yes = lambda said: brain.post(
                AnswerIn("voice", said, source="microphone"))
            self.listener.on_other = lambda said: brain.post(HeardIn(said))
            try:
                self.listener.start()
            except Exception as exc:
                log.warning("no microphone (%s): listening is off; keys and pats still work",
                            exc)
                self.listener = None
        if self.live_view is not None:
            self.live_view.start()

    def stop(self) -> None:
        for part in (self.live_view, self.listener, self.vision, self.camera, self.voice):
            if part is not None:
                try:
                    part.stop()
                except Exception as exc:
                    log.warning("stopping %s: %s", type(part).__name__, exc)


def build_senses(settings: Settings, clock: Clock, hub: BodyHub, store: Store | None) -> Senses:
    senses = Senses()
    robot = settings.robot_url is not None
    senses.camera = _camera(settings, clock, hub)
    if senses.camera is not None:
        senses.vision = _vision(settings, clock, senses.camera, hub)
    senses.listener = _listener(settings, clock, robot)
    senses.voice = _voice(settings, clock, robot)
    senses.judge = _judge(settings)
    if store is not None:
        from argos.snapshot import make_uploader

        senses.uploader = make_uploader(store)
    senses.live_view = _live_view(settings, clock, senses.camera)
    return senses


def _camera(settings: Settings, clock: Clock, hub: BodyHub) -> Any:
    from argos.senses.camera import Camera, resolve

    device = resolve(settings.camera)
    if device is None:
        log.info("camera: off (ARGOS_CAMERA=%s); no fall or stillness triggers", settings.camera)
        return None
    try:
        import cv2  # noqa: F401
    except ImportError as exc:
        log.warning("camera library missing (%s); no camera", exc)
        return None
    return Camera(device, clock, settings.camera_width, settings.camera_height,
                  moving_until=hub.moving_until)


def _vision(settings: Settings, clock: Clock, camera: Any, hub: BodyHub | None = None) -> Any:
    from argos.senses.vision import FallDetector, MediaPipePose, StillnessTracker, Vision

    estimator = None
    try:
        estimator = MediaPipePose(settings.pose_model)
    except Exception as exc:
        log.warning("pose model unavailable (%s): no fall or stillness triggers", exc)
    return Vision(
        camera,
        estimator,
        clock,
        FallDetector(settings.fall_angle_deg, settings.fall_hold_s, settings.person_min_score),
        StillnessTracker(settings.stillness_s, settings.still_move, settings.person_min_score),
        fps=settings.detect_fps,
        hfov_deg=settings.camera_hfov_deg,
        moving_until=hub.moving_until if hub is not None else (lambda: 0.0),
    )


def _listener(settings: Settings, clock: Clock, robot: bool) -> Any:
    if settings.listen.lower() == "off":
        log.info("listening: off (ARGOS_LISTEN=off)")
        return None
    try:
        from argos.brain import Gate
        from argos.senses.hearing import Listener, Microphone, VoskRecognizer, pick_device

        recognizer = VoskRecognizer(settings.vosk_model)
        source = Microphone(pick_device(settings.audio_in, "input", robot))
        return Listener(source, recognizer, Gate(), clock, settings.help_min_conf)
    except Exception as exc:
        log.warning("listening unavailable (%s): keys and pats still answer", exc)
        return None


def _voice(settings: Settings, clock: Clock, robot: bool) -> Any:
    from argos.voice import ElevenLabs, SoundDeviceSpeaker, Voice

    tts = None
    if settings.elevenlabs_api_key and settings.elevenlabs_voice_id:
        tts = ElevenLabs(settings.elevenlabs_api_key, settings.elevenlabs_voice_id,
                         settings.elevenlabs_model)
    else:
        log.warning("no ElevenLabs key or voice id: only cached lines can be spoken")
    speaker = None
    try:
        from argos.senses.hearing import pick_device

        speaker = SoundDeviceSpeaker(pick_device(settings.audio_out, "output", robot))
    except Exception as exc:
        log.warning("no speaker (%s): Argos will beep instead of speaking, if it can", exc)
    return Voice(clock, settings.cache_dir / "voice", tts, speaker,
                 cache_key=f"{settings.elevenlabs_voice_id}|{settings.elevenlabs_model}")


def _judge(settings: Settings) -> Any:
    if not settings.gemini_api_key:
        log.warning("no GEMINI_API_KEY: no Gemini check, and the summary is a fixed sentence")
        return None
    try:
        from argos.gemini import GeminiJudge, sdk_generate

        return GeminiJudge(sdk_generate(settings.gemini_api_key, settings.gemini_model,
                                        settings.gemini_timeout_s))
    except Exception as exc:
        log.warning("Gemini unavailable (%s)", exc)
        return None


def _live_view(settings: Settings, clock: Clock, camera: Any) -> Any:
    if not settings.live_view:
        log.info("live view: off (set ARGOS_LIVE_VIEW=1 to send frames)")
        return None
    if camera is None:
        log.warning("live view is on but there is no camera; nothing to send")
        return None
    if not settings.backend_configured:
        log.warning("live view is on but the backend settings are missing; nothing is sent")
        return None
    from argos.liveview import Broadcaster, LiveView

    sender = Broadcaster(settings.supabase_url, settings.supabase_key, settings.device_id)
    return LiveView(camera.latest_any, sender.send, clock, settings.live_view_fps)
