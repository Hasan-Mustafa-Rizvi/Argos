# Argos: how it is built

Read `contract/CONTRACT.md` for exact names and shapes. This file explains how the parts fit
and what must stay true.

## The parts

```
 Dog body (ESP32)          Laptop brain (Python)               Backend (Supabase)
 eyes, touch pad,   USB    camera + microphone        HTTPS    devices, incidents,
 buzzer, room       serial pose and speech detection ───────▶  events, readings,
 temperature  ◀──────────▶ state machine                       snapshot storage,
 head (optional)    JSON   voice out                           sign-in and access rules
                    lines  Gemini check on one snapshot              │ live updates
                           escalation: FaceTime call, email          ▼
                                                               Dashboard (web/)
                                                               family view, clinician view
```

- **The laptop is the brain.** The ESP32 only runs the body. No vision or speech runs on it.
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
| What is in the body now that it carries a Raspberry Pi 5? | Open. Is there still an ESP32, and what is wired to the Pi: camera, microphone, speaker, eyes, touch? The contract's serial link and the diagram above change once this is known. |
| Does Chert access last through Sunday afternoon? | Yes if the trial starts after Sat 4 PM: it runs 48 hours. The limit that matters is 50 FaceTime minutes in total, 5 minutes a call. Ask Chert for more if testing eats them. |
| Email provider | Open. Decided at the escalation milestone. |
| What the body has: servos, camera, speaker | Open. Waiting on the components list in `progress.md`. |
| Demo sessions are open to anyone with the link during the event | Accepted. A demo session plays the scripted run only and never receives live records or the live view. |
| Does the venue network carry the live view at 4 frames a second? | Open. Test early on Sunday. The frame rate drops through `LIVE_VIEW_FPS`. |
