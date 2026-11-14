# Argos software tracker

**Last updated:** Sat Nov 14 2026, 4:45 PM CT
**Status:** Web A is building. M3 is applied. Brain A prompt is written. Chert is understood; three answers are needed from their table.

Hasan owns all software. This file records where the software is. Coding agents never edit it.

## Status at a glance

| # | Milestone | Lane | State | Waiting on |
|---|---|---|---|---|
| M0 | Repo layout, ignore rules, agent rules, docs | root | Done | |
| M1 | Contract v0.2 and scripted demo run | `contract/` | Done | |
| W1 | Web shell: tokens, landing, sign-in, logo reveal, empty dashboard frame | `web/` | Ready to start, one prompt with W2 | |
| W2 | Dashboard on replay data | `web/` | Ready to start, one prompt with W1 | |
| M3 | Schema, access rules, second factor, live updates, live view channel | `supabase/` | Applied and tested. Three dashboard switches and the first account are Hasan's. | |
| W3 | Dashboard reads live data, real sign-in with second factor, live view, keeps replay mode | `web/` | Not started | W2, M3 |
| M5 | Brain: simulator first, then real detection, voice and live view frames | `brain/` | Not started | M3 for writes |
| M6 | Escalation: FaceTime call and email, dry-run by default | `brain/` | Not started | Chert answers |
| M7 | Firmware | `firmware/` | Not started | Components list |

## Decisions

| When (CT) | Decision | Why |
|---|---|---|
| Sat 2:27 PM | Dashboard: Vite, React, TypeScript, Tailwind, shadcn/ui | 21st.dev parts drop in. No server rendering needed, so a static build on Netlify is simplest. |
| Sat 2:27 PM | Backend: Supabase | Live updates, sign-in with per-role rules, and private storage without writing a server. |
| Sat 2:27 PM | Skip the Tiger Data and MongoDB prizes | Cost of choosing Supabase. Accepted. |
| Sat 2:27 PM | Contract and replay data before dashboard and backend | The dashboard never waits on the backend, and replay stays as the network fallback. |
| Sat 2:27 PM | One lane per top-level folder, at most two coding agents at once | They never write to the same folder, and review stays manageable. |
| Sat 2:45 PM | Everyone signs in. Two demo accounts give judges a family view and a clinician view. | Shows the access rules working, which is the privacy answer. |
| Sat 2:45 PM | Family sees the snapshot, clinician sees sensor history, neither sees the other's | From the privacy stance in `progress.md`. |
| Sat 3:30 PM | Identity: cobalt engraving on cream paper, two colours, from the Cobalt Toile landing | The landing template already has the Greek feel, so the dashboard adopts its rules instead of inventing a second look. |
| Sat 3:30 PM | The page reprints in a different ink per state: cobalt, ochre, oxblood | The state is readable from across a room, and it uses the template's own palette mechanism. |
| Sat 3:30 PM | Site flow: landing, sign-in, logo reveal, dashboard | Hasan's call. |
| Sat 3:30 PM | ~~The logo reveal is a recorded clip~~ Replaced at 3:50 PM. | |
| Sat 3:50 PM | The logo is Hasan's design: a seated hound in a ring of Greek key and laurel, traced to SVG | His call. It reprints in the page ink like everything else. |
| Sat 3:50 PM | The logo reveal uses the liquid glass reveal component from 21st.dev with our mark | Hasan has used it before. It takes any logo and has a still fallback without WebGL. |
| Sat 3:50 PM | The landing carries only what is planned now, a "who made this" section, and a credit line in the footer | Hasan's call. |
| Sat 3:50 PM | **The centre of the dashboard is the live view from the dog's camera** | Hasan's call. The dashboard is only for signed-in people, so the feed is protected by sign-in and a second factor. |
| Sat 3:50 PM | The live view is never stored, needs a second factor, goes to family accounts only, and is off unless switched on | Keeps the stored-image rule intact and keeps the family and clinician split consistent: clinicians already do not see images. |
| Sat 3:50 PM | Demo sessions play the scripted run and never get live records or the live view | The demo buttons are public. Nothing real should be one tap away from a stranger. |
| Sat 4:05 PM | The web build is two prompts, not three: W1 and W2 in one run, then W3 | Neither W1 nor W2 needs a backend, and the coding agent has no usage limit. Review happens per stage inside one report. |
| Sat 4:05 PM | Supabase gets only what security needs. Sign-ups are off; the one or two real accounts are created by hand. | Hasan's call. No one else can make an account, which removes most of the attack surface for the least work. |
| Sat 3:50 PM | Frames travel as small JPEGs over a private Supabase broadcast channel, 4 a second | No extra service. Free plan allows 256 KB a message and 100 messages a second; a frame is under 100 KB. |
| Sat 3:30 PM | Reference source files stay on Hasan's machine, out of the repo | They are other people's work. The index and credits are in the repo. |
| Sat 3:30 PM | Kimi dropped from the plan | Hasan's call. Cursor and Claude Code are the coding agents. |

## Tracks this build serves

General, Hardware, Chert (best use of FaceTime), ElevenLabs, MLH Gemini API, MLH SpaceXSI.

## Accounts

| Account | Needed by | State |
|---|---|---|
| GitHub, Netlify | M0, M2 | Ready |
| Supabase | M3 | Ready. Project "Argos". New tables are not exposed to the API unless granted. |
| Gemini (Google AI Studio) | M5 | To create |
| ElevenLabs | M5 | To create |
| Chert | M6 | Get our assigned FaceTime line, time slot and dispatch name from the organizers or the Chert table. |
| LiveKit Cloud | M6 | To create. Chert connects FaceTime to a LiveKit room that we own. |
| Email sender | M6 | To choose |
| Devpost | Sat midnight | To create |

## Open decisions

- None open. Argos's view was decided at 3:50 PM: it is the live view. See contract section 6.

## Backlog and known limits

- The Chert integration is unresearched. It is the least certain part of the plan.
- Demo sessions are open to anyone with the link while the event runs. They see the scripted run only.
- The live view over the venue network is untested. Test early on Sunday.
- A manual override was mentioned by Hasan as a possible later addition. Not specified yet.

## Log

### Sat Nov 14, 4:45 PM
Read Chert's FaceTime docs. How it works: Chert owns the FaceTime line and bridges each call
into a LiveKit room that we create. Our agent is a LiveKit agent in that room. It receives
the person's audio (and their camera only if capture is switched on for the line) and
publishes its own audio. A call is placed with one HTTP request once the room and a silent
agent are ready, and the agent speaks only after the bridge reports ready. What this changes:
the escalation is a second small program, the call agent, beside the brain; it needs a
LiveKit Cloud project and a voice model account; and the Chert connector runs on macOS or
Linux with Node, not on Windows. What is not settled: outbound calling, outbound video and
showing our own picture are each enabled per line, and the hackathon starter is inbound
audio only. Fallback if outbound is not available: Argos sends word by email and dashboard,
and the contact FaceTimes Argos's line and talks to the agent.

The MLH prize noted as "SpaceXSI" is DeepSpace, a full-stack SDK (sign-in, data, live sync,
hosting) that an app is scaffolded on. Building with Cursor does not use it. Not adopted for
the core. A separate small app is the only cheap way to enter; awaiting Hasan's call.

Brain A prompt written: the core in stage 1 (state machine, records, serial, keyboard
triggers, dry-run escalation), senses and voice in stage 2 (camera, listening, Gemini,
ElevenLabs, snapshot, live view frames).

### Sat Nov 14, 4:25 PM
M3 applied to the Supabase project "Argos" from `supabase/schema.sql`. Tested inside a
transaction that was rolled back, with made-up users: the public key alone is refused; a
password-only session reads nothing; a family member with a second factor reads the device,
incidents and timeline but no readings; a clinician reads readings; a signed-in outsider
reads nothing; a member can acknowledge an escalated incident and cannot acknowledge a
stood-down one, edit a summary, set any other status or insert anything; the database itself
refuses a summary on a stood-down incident. Not yet tested, because they need a real
session: the live view channel rule and the snapshot storage rule. The combined web prompt
was reviewed by a second agent against the contract and the fixture; fourteen fixes applied.

### Sat Nov 14, 4:05 PM
Web work regrouped into two prompts: W1 and W2 together (the whole site on demo data), then
W3 (live data, sign-in, second factor, live view). Fixed a contradiction found while writing
the prompt: the dashboard sketch showed stillness and room temperature to family, but the
contract gives sensor readings to clinicians only. Family now gets Last check and Today in
those places. Supabase scope agreed as the minimum that is safe: access rules on every table,
second factor enforced in the rules, private live channel, private snapshot storage, sign-ups
off. No extras.

### Sat Nov 14, 3:50 PM
Hasan's logo traced to SVG: emblem, a heavier cut for small sizes, a side-by-side lockup and a
stacked lockup with the line "Guardian & Assistant". The original is kept in
`design/logo/source/`. Hasan decided the centre panel is the live view, protected by sign-in
and a second factor. Contract moved to v0.2 with section 6. Checked against Supabase's
published limits: second factor by authenticator app is free on every plan and can be
enforced in access rules; the free plan's broadcast limit is 256 KB a message and 100
messages a second. Identity, build plan and the W1 prompt were revised for the new logo, the
glass reveal component, the team section and the footer credit.

### Sat Nov 14, 3:30 PM
Design groundwork. Read the Cobalt Toile landing template (MIT, one 150 KB file, React only,
driven by props), the four 21st.dev components, HackUTA's own design notes and the glass icon
reveal tool. Wrote `design/IDENTITY.md`, `design/BUILD_PLAN.md` and
`design/references/README.md`, drew the mark and lockup in `design/logo/`, and wrote the W1
prompt. Contrast checked for all three inks on paper: body text 12.3 to 14.7 : 1, ink 5.4 to
9.4 : 1. Found that the template merges props over defaults, so an empty object does not clear
its fictional contact details. The W1 prompt tells the coding agent to verify and report this.

### Sat Nov 14, 2:45 PM
M0 and M1 written. Contract v0.1 covers the state machine, the serial link, four record types,
who sees what, and the replay format. The scripted run has 61 lines: 24 device updates, 19
readings, 12 events and 6 incident writes across two incidents. Checked: lines are in time
order, event ids are unique, no summary or snapshot appears before an incident escalates, and
no phone number or email address appears anywhere in the file.
