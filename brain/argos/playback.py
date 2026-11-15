"""Play one line of sound, then exit. Run by the brain in a process of its own, never imported
into the brain's.

    python -m argos.playback --out auto --robot --rate 16000   < raw 16-bit mono PCM

Why a process of its own: on the real robot, pressing the head knocked the robot's sound card
off USB for about a second. The brain then opened the card while it was gone, and PortAudio
failed an assertion (`PaAlsaStream_Initialize`) that aborts the whole process. No Python code
can catch that. Here it ends only this process, and the brain records the line as not played
(`voice.ProcessSpeaker`).

Exit 0: the line was played. Anything else, a signal included: it was not.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m argos.playback")
    parser.add_argument("--out", default="auto", help="ARGOS_AUDIO_OUT: auto, a number, or "
                        "part of a device name")
    parser.add_argument("--robot", action="store_true", help="the robot is in use: auto means "
                        "the robot's sound card")
    parser.add_argument("--rate", type=int, default=16000)
    args = parser.parse_args(argv)
    pcm = sys.stdin.buffer.read()
    if len(pcm) < 2:
        print("no sound was given", file=sys.stderr)
        return 2
    try:
        import numpy as np
        import sounddevice as sd

        from argos.senses.hearing import pick_device
        from argos.voice import spread

        device = pick_device(args.out, "output", args.robot)
        samples = np.frombuffer(pcm[: len(pcm) - len(pcm) % 2], dtype="<i2")
        channels = int(sd.query_devices(device, "output")["max_output_channels"])
        sd.play(spread(samples, channels), samplerate=args.rate, device=device, blocking=True)
    except Exception as exc:
        print(f"not played: {type(exc).__name__}: {str(exc)[:160]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
