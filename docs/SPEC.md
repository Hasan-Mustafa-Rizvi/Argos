# Argos: how it is built

Read `contract/CONTRACT.md` for exact names and shapes. This file explains how the parts fit
and what must stay true.

## The parts

```
 The robot                    Raspberry Pi 5: the brain (Python)      Backend (Supabase)
 Reachy Mini Lite:    USB     state machine                   HTTPS   devices, incidents,
 head, antennas,     ──────▶  fall, stillness and voice detection ──▶ events, readings,
 camera, microphones, ◀─────  spoken lines (ElevenLabs)               snapshot storage,
 speaker                      Gemini check on one frame               sign-in and access rules
                              live view frames                            │ live updates
 Four-wheeled base   ◀─────   escalation                                  ▼
 (built by the                wheel commands (not built yet)          Dashboard (web/)
 hardware team)                                                       https://argos-watch.netlify.app
                                                                      family view, clinician view
 Call agent: FaceTime through Chert and LiveKit. Runs on a laptop, reads incidents and the
 live view from the backend. Not built yet.
```

- **One Raspberry Pi 5 runs everything on the robot.** There is no second board. The same
  brain program runs on a laptop for development and as the fallback.
- **The brain owns the state machine** in section 1 of the contract. The body shows the
  state. The dashboard displays it. Neither decides it.
- **The brain is the only writer** to the backend. The dashboard reads, and makes exactly
  one write: acknowledging an escalated incident.
- **The brain decides when the robot moves.** Movement is a short, slow approach toward the
  person during a check, guided by the camera, with a time limit and a stop. It is off
  unless switched on, and everything works without it.

## What must stay true

1. **Every part runs alone.** No body, no camera or no network must degrade the system,
   not stop it.
2. **Nothing real leaves by default.** A real call or a real email happens only when
   `ARGOS_DRY_RUN=0`.
3. **Privacy.** No image or description is stored for an incident that stood down. The live
   view is never stored, and reaches only a family account that has passed its second
   factor. Phone numbers and email addresses never reach a record or the browser.
4. **No secrets in the repo.** It is public.
5. **The demo has a manual trigger**, so a loud hall cannot stop it.

## When something fails

| Failure | What happens |
|---|---|
| Venue network drops | Dashboard switches to replay mode. Brain keeps running and logs locally. |
| The robot is unplugged or its software is not running | Brain carries on with the machine's own camera, microphone and speaker. |
| The wheels are missing, off or stuck | The robot asks from where it stands. Nothing else changes. |
| Microphone useless in the noise | Manual trigger starts the check. A pat stands it down. |
| FaceTime call fails | `call_failed` is logged. Email and the dashboard still carry the alert. |
| Camera detection misfires | The check exists for this. "I'm fine" or a pat stands it down. |
| Live view frames stop | The centre panel shows the last frame faded and its age. Everything else keeps working. |

## Open questions

| Question | Status |
|---|---|
| The wheels: which motors, how they are wired to the Pi, what powers them, any feedback sensors, any existing test code | Open. Twelve questions sent to Neel and Farrell, Sat 6:49 PM. The wheel code waits on answers 1, 2, 3 and 7. |
| Power: battery or wall power, and how far can the robot roll | Open. Part of the questions above. It decides whether the robot can move at all. |
| Is there an iPhone for the FaceTime prize? | Open, and the team has none right now. Chert requires one to verify the line and for calls. Options: the judge's own phone at judging, a borrowed iPhone for setup and tests, and building the agent against a LiveKit room in a browser so no iPhone is needed until the last step. Ask Chert. |
| Which machine runs the Chert connector and the call agent? | Hasan's Windows laptop, inside WSL2 first, native Windows second, the Pi third. Nobody on the team has macOS. Untested. |
| Does a press on the head read cleanly from the motors? | Open. The brain so far senses a press on an antenna. The head press is in the next brain prompt. To be proven on the real robot. |
| Does the brain run on the real Pi with the real robot, camera, microphones and speaker? | Open. Nothing has been tried on real hardware or with real keys. |
| Gemini free tier may use the frames it is sent and show them to reviewers | Open. Hasan to decide: a paid-tier key, or change the privacy wording. |
| Does Chert access last through Sunday afternoon? | Yes if the trial starts after Sat 4 PM: it runs 48 hours. The limit that matters is 50 FaceTime minutes in total, 5 minutes a call. |
| Does the venue network carry the live view at 4 frames a second? | Open. Test early on Sunday. The frame rate drops through `LIVE_VIEW_FPS`. |
| Email provider for the backup email | Open. Decided when escalation is built. |
| Demo sessions are open to anyone with the link during the event | Accepted. A demo session plays the scripted run only and never receives live records or the live view. |
