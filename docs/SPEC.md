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
3. **Privacy.** No image or description is stored for an incident that stood down. Phone
   numbers and email addresses never reach a record or the browser.
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

## Open questions

| Question | Status |
|---|---|
| How does our code receive video and audio from a Chert FaceTime call, and show a live page on it? | Open. Needs their docs and their rep. |
| Does Chert access last through Sunday afternoon? | Open. The public trial is 24 hours. |
| Email provider | Open. Decided at the escalation milestone. |
| What the body has: servos, camera, speaker | Open. Waiting on the components list in `progress.md`. |
| Demo accounts are reachable by anyone with the link during the event | Accepted for the demo. Snapshots are cleared and demo passwords changed after judging. |
