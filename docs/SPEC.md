# Argos: how it is built

Read `contract/CONTRACT.md` for exact names and shapes. This file explains how the parts fit
and what must stay true.

## The parts

```
 Reachy Mini Lite            Raspberry Pi 5: the brain (Python)      Backend (Supabase)
 head, antennas,     USB     state machine                   HTTPS   devices, incidents,
 camera, microphones, ─────▶ fall, stillness and voice detection ──▶ events, readings,
 speaker             ◀─────  spoken lines (ElevenLabs)               snapshot storage,
                             Gemini check on one frame               sign-in and access rules
 Optional sensor      USB    live view frames                            │ live updates
 board (ESP32):      ──────▶ escalation                                  ▼
 temperature, tilt,  serial                                          Dashboard (web/)
 touch pad                   Call agent (MacBook): FaceTime          family view, clinician view
                             through Chert and LiveKit
```

- **The Raspberry Pi is the brain.** The same program runs on a laptop for development and as
  the fallback. The robot only moves, sees, hears and speaks.
- **The brain owns the state machine** in section 1 of the contract. The body shows the
  state. The dashboard displays it. Neither decides it.
- **The brain is the only writer** to the backend. The dashboard reads, and makes exactly
  one write: acknowledging an escalated incident.

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
| Dog's body unplugged | Brain carries on with voice and escalation only. |
| Microphone useless in the noise | Manual trigger starts the check. A pat stands it down. |
| FaceTime call fails | `call_failed` is logged. Email and the dashboard still carry the alert. |
| Camera detection misfires | The check exists for this. "I'm fine" or a pat stands it down. |
| Live view frames stop | The centre panel shows the last frame faded and its age. Everything else keeps working. |

## Open questions

| Question | Status |
|---|---|
| How does our code reach a FaceTime call through Chert? | Answered from their docs, Sat 4:45 PM. Chert bridges a FaceTime line into a LiveKit room. Our agent joins that room, hears the person and speaks. See the tracker log. |
| Can our line place outbound calls, carry video out, and show our own picture to the person called? | Chert's challenge page says yes to all three for hackathon teams. To be proven on our own line. Calls go only to phones verified with the line. |
| Which machine runs the Chert connector and the call agent? | A teammate's MacBook. Windows 11 is supported in beta. |
| What is in the body? | Answered Sat 5:03 PM: a Reachy Mini Lite on the Pi, with its own camera, microphones, speaker and moving head. Contract v0.3. |
| How does a person give Argos a pat? | Answered Sat 6:22 PM: by pressing the robot's head down. The brain senses it from the motors. To be proven on the real robot. |
| The robot sits on the team's own wheels. Does the brain drive them? | Open. Movement was a stretch goal. Ask what controls the wheels. |
| Does Chert access last through Sunday afternoon? | Yes if the trial starts after Sat 4 PM: it runs 48 hours. The limit that matters is 50 FaceTime minutes in total, 5 minutes a call. Ask Chert for more if testing eats them. |
| Email provider | Open. Decided at the escalation milestone. |
| What the body has: servos, camera, speaker | Open. Waiting on the components list in `progress.md`. |
| Demo sessions are open to anyone with the link during the event | Accepted. A demo session plays the scripted run only and never receives live records or the live view. |
| Does the venue network carry the live view at 4 frames a second? | Open. Test early on Sunday. The frame rate drops through `LIVE_VIEW_FPS`. |
