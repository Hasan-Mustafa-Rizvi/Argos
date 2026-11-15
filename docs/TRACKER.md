# Argos software tracker

**Last updated:** Sat Nov 14 2026, 8:15 PM CT
**Status:** The dashboard is live on demo data. The brain is built and reviewed but untried on real hardware. The Chert trial is running and a phone is verified. Next: the dashboard on live data (W3, prompt written), then the FaceTime call agent (M6). The wheels wait on the hardware team's answers.

Hasan owns all software. This file records where the software is. Coding agents never edit it.

## Status at a glance

| # | Milestone | Lane | State | Waiting on |
|---|---|---|---|---|
| M0 | Repo layout, ignore rules, agent rules, docs | root | Done | |
| M1 | Contract v0.4 and scripted demo run | `contract/` | Done | |
| W1 | Web shell: tokens, landing, sign-in, logo reveal, empty dashboard frame | `web/` | Done, reviewed, committed | |
| W2 | Dashboard on replay data | `web/` | Done, reviewed, committed, deployed. | |
| M3 | Schema, access rules, second factor, live updates, live view channel | `supabase/` | Applied and tested. Three dashboard switches and the first account are Hasan's. | |
| W3 | Dashboard reads live data, real sign-in with second factor, live view, keeps replay mode | `web/` | Next. Prompt being written. | |
| M5 | Brain: core, robot body language, then detection, voice and live view frames | `brain/` | Built, reviewed, committed. Nothing tried on real hardware or with real keys yet. | The robot, the Pi, keys |
| M6 | Escalation: the FaceTime call agent (Chert, LiveKit, ElevenLabs voice, Gemini on what it sees), and the backup email | its own lane | Not started | An iPhone, a LiveKit account, the Chert trial |
| M8 | The brain drives the wheels: a short approach to the person during a check. Also the head press as a pat. | `brain/` | Not started | The hardware team's answers; the wheels being printed |
| M7 | Firmware | none | Dropped. There is no ESP32 in the robot. | |

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
| Sat 6:28 PM | One Raspberry Pi 5 runs the whole robot: a Reachy Mini Lite on a four-wheeled base. No ESP32. | The hardware team's build. |
| Sat 6:28 PM | The brain will drive the wheels, as a short camera-guided approach during a check, off unless switched on | Hasan wants the robot to go to the person. Kept small and switchable because robustness is scored and the wheels do not exist yet. |
| Sat 6:35 PM | The sign-in plate is the night watch: the hound over a wave-scroll sea under the Dog Star, with ΑΡΓΟΣ | Hasan chose it from three drawings. |
| Sat 7:55 PM | The dashboard is deployed at argos-watch.netlify.app and redeploys on every push | Hasan linked the repo. |
| Sat 8:00 PM | The call agent runs on Hasan's Windows laptop, WSL2 first | Nobody on the team has macOS. The agent reads from the backend, so it need not sit with the robot. |
| Sat 5:03 PM | The body is a Reachy Mini Lite on the Pi: camera, microphones, speaker, moving head (team's call). The ESP32 becomes an optional sensor board. | The robot already has every sense the brain needs. Contract v0.3. |
| Sat 6:00 PM | One art language: line engraving. The dithered hills go. Sign-in gets the mark as an engraved plate; the dashboard ends with a wave scroll band; the reveal is cut to about 1.5 s and made gentle; no em dashes anywhere. | Hasan's review of the built site. The hills were pixel texture beside engraved line, so they read as foreign. |
| Sat 5:35 PM | The reveal's brighter blue while the glass holds the mark stays as it is | It lasts about two seconds, is part of the glass effect, and settles to cobalt. Not worth another edit to a copied file. Hasan can overrule after seeing it. |
| Sat 4:53 PM | The dog carries a Raspberry Pi 5 (team's call). The brain runs on it; the laptop is where it is developed and the fallback. | More power in the body, no tether, and the same code runs on both. |
| Sat 4:53 PM | DeepSpace is left out. SpaceXSI, DEV post and a domain sit in a track check list for spare time. | Hasan's call. None of them may touch the core. |
| Sat 4:05 PM | The web build is two prompts, not three: W1 and W2 in one run, then W3 | Neither W1 nor W2 needs a backend, and the coding agent has no usage limit. Review happens per stage inside one report. |
| Sat 4:05 PM | Supabase gets only what security needs. Sign-ups are off; the one or two real accounts are created by hand. | Hasan's call. No one else can make an account, which removes most of the attack surface for the least work. |
| Sat 3:50 PM | Frames travel as small JPEGs over a private Supabase broadcast channel, 4 a second | No extra service. Free plan allows 256 KB a message and 100 messages a second; a frame is under 100 KB. |
| Sat 3:30 PM | Reference source files stay on Hasan's machine, out of the repo | They are other people's work. The index and credits are in the repo. |
| Sat 3:30 PM | Kimi dropped from the plan | Hasan's call. Cursor and Claude Code are the coding agents. |

## Tracks this build serves

Rules as published on Devpost and the sponsors' pages, read Sat 5:00 PM.

| Track | What it requires | What we must do | Where it lives |
|---|---|---|---|
| General | Judged on robustness, theme, creativity | Submit | Everything |
| Hardware | A Devpost section titled "Hardware Info" listing each part and what it did | Write the section from the final parts list | The dog's body |
| Chert: Best Use of FaceTime | Built on Chert's FaceTime API. One iPhone on the team. The agent makes or takes a FaceTime call during the demo. Select the prize on Devpost. Judged live by Chert's CEO: fresh use of FaceTime video counts double, then wow factor, then usefulness. | A call agent that uses video, not just voice | M6 |
| ElevenLabs | A Devpost section titled "How We Used ElevenLabs" listing each feature and how it was used. The brief asks for more than plain text-to-speech. | Use it for the spoken check and as the voice of the call agent, and say so | M5, M6 |
| MLH Gemini API | Real API calls | The check on one frame, the summary, and what the call agent sees | M5, M6 |

Not entering: FaZe Clan, Solana, Tiger Data, MongoDB Atlas, Vultr.

## Track check: cheap extras, only if there is time

| Extra | What it takes | Worth it? |
|---|---|---|
| MLH SpaceXSI raffle | Cursor as the main coding agent (true already), one Grok Bot automation in our workflow, both described on Devpost, and opting in. Needs an X Premium trial and the Grok Bot app. It is a raffle, not judged. | Low effort if a Grok Bot job can do something harmless, such as drafting the Devpost text from the repo. Do it Sunday morning or not at all. |
| MLH DEV Writing Challenge | Publish a post about the project on DEV. Prize $100. | Yes if someone has an hour on Sunday. The Devpost text can be reused. |
| MLH GoDaddy domain | Register a domain for the project through MLH's offer. | Only if a good name is free and it takes minutes. |
| DeepSpace | Not a prize category. It is a sponsor offering build credits (expires Nov 25). | No prize to win. A separate family board built on it stays as an idea only. |

## Accounts

| Account | Needed by | State |
|---|---|---|
| GitHub, Netlify | M0, M2 | Ready. The dashboard is live at https://argos-watch.netlify.app, linked to the GitHub repo, so every push to `main` deploys. `argos-live-tracker` is the team tracker page, unrelated. |
| Supabase | M3 | Ready. Project "Argos". New tables are not exposed to the API unless granted. |
| Gemini (Google AI Studio) | M5 | To create. Use a paid-tier key: on the free tier the frames sent may be used by Google and seen by reviewers. |
| ElevenLabs | M5 | To create. One free month of Creator through the coupon bot in the ElevenLabs Discord, using the HackUTA registration email. |
| Chert | M6 | Trial started Sat Nov 14, about 7:35 PM, on Hasan's account. A friend's iPhone is verified for the project. 50 FaceTime minutes in total, 5 minutes a call. The tool says the trial lasts 24 hours and the web guide says 48: check the billing page. The line is shared and takes one call at a time; it was busy three times in a row on Saturday evening. With no agent connected the line is released after 3 hours (15 minutes when busy); running onboarding again gives a line with the minutes kept, and the number may change. A join code lets any iPhone join the project by sending one text. The sign-in lives in Hasan's user profile and a scratch folder `C:\Projects\argos-call`, outside this repo. |
| LiveKit Cloud | M6 | To create. Chert connects FaceTime to a LiveKit room that we own. |
| An iPhone | M6 | A friend's, verified. He takes one or two test calls and comes to judging on Sunday at 1 PM. The join code is the fallback for any other iPhone, the judge's included. |
| Email sender | M6 | To choose |
| Devpost | Sat midnight | To create |

## Open items

With Hasan:
- Chert: read the trial's end time off the billing page. Watch the Chert Discord for the answer on busy shared lines during judging. Keep the join code private.
- Sunday morning: run onboarding again if the line was released, then the friend sends one text to the line's number.
- Gemini key: paid tier, or change the privacy wording.
- Claim the ElevenLabs coupon; create the Gemini and LiveKit accounts.
- Create the Devpost page before Saturday midnight. What that first submission must contain is unconfirmed.

With Neel and Farrell:
- The twelve hardware questions sent Sat 6:49 PM.
- What the landing page should say each of them did. It says "Hardware and the dog's body" for both.

## Known limits

- Nothing in `brain/` has run on the real Pi, robot, camera, microphone or speaker, or against the real backend or real keys.
- The pat the brain senses today is a press on an antenna, not on the head.
- The dashboard shows demo data only. Real sign-in is not built, so nobody can see live records yet.
- The live view over the venue network is untested.
- The Chert sign-up tool ran on Windows with Node 24. The connector that carries a call is still untested on Windows and on WSL2, and no FaceTime call has been placed yet: the demo call never got through a busy line.
- Whether a phone that joined by the join code can receive a call from the agent, not only place one, is unconfirmed.
- Demo sessions are open to anyone with the link. They see the scripted run only.
- A manual override was mentioned by Hasan as a possible later addition. Not specified.

## Log

### Sat Nov 14, 7:50 PM
Chert onboarding done from a scratch folder outside the repo, with a friend's iPhone. The
phone verified on the first try. The demo call never happened: the shared line was busy for
three attempts, so onboarding was finished with the demo skipped. What that taught us: the
trial line is shared between projects and carries one call at a time, so a busy line at
judging is a real risk. The call agent must ask to queue, retry, and fall back to the email.
Asked Chert in their Discord whether teams share a line during the live demos. Found a join
code: one text from any iPhone joins the project, which removes the dependence on one phone.

Wrote the Web B prompt (real sign-in with a second factor, live records, the acknowledge
write, the live view, the snapshot). Contract 0.4.1: once the live view has stopped, the
reader forgets the last `seq`, so a restarted brain is picked up at once. The dashboard's
key setting is now named `VITE_SUPABASE_PUBLISHABLE_KEY`.

### Sat Nov 14, 7:20 PM
Reviewed Brain A. Verified from a clean copy with its pinned dependencies on Python 3.12:
180 of 180 tests pass, the linter is clean. Read the privacy code: a summary or snapshot
path can only be written to an incident the brain itself escalated, and the write is
filtered on the incident's status; the live view goes to Realtime's own endpoint as a
private broadcast and nowhere else; contact details are never read. Scanned for keys and
contact details: none. Committed.

Choices the coding agent made that matter later: the brain drives the robot through the
robot daemon's HTTP interface and opens the camera and audio itself, so the robot's own
software needs no compiler on the Pi beyond its documented install; fall detection is
MediaPipe pose with two plain rules; listening is Vosk with a fixed phrase list; the pat
it built is a press on an antenna.

Not done on any real thing: robot, Pi, camera, microphone, speaker, Supabase, Gemini,
ElevenLabs. The coding agent ran `git status` once, read-only, and said so.

Hardware as now understood: one Raspberry Pi 5 runs everything. Reachy Mini Lite on a base
with four wheels. No ESP32. The team wants the robot to drive to the person. Questions sent
to the hardware teammates through Hasan.

Open risk raised by the coding agent: on Gemini's free tier, frames sent for the check may
be used by Google and seen by reviewers, which would make "sent, not stored" untrue.

### Sat Nov 14, 6:05 PM
Reviewed the polish pass (Web A2). Verified from a clean copy: 65 of 65 tests, build passes,
linter 0 errors and 2 warnings in the copied files. `web/src/data` and `web/src/auth` are
byte-identical to the previous commit. Watched the reveal in a real browser, which the
coding agent could not: the mark is readable throughout and it hands over quickly. Seen and
left for a small follow-up: the team cards have no inner padding, and a leftover arrow sits
at the top right of that section. Committed as `67d8fea`.

Netlify: the connected team already holds a site named `argos-live-tracker`. The dashboard
is not deployed. Best route is to import the GitHub repo in Netlify with base directory
`web`, so every push deploys; the connector cannot link a repo.

### Sat Nov 14, 5:35 PM
Reviewed Web A. Verified independently from a clean copy: 57 of 57 tests pass, the build
succeeds, the linter reports 0 errors and 3 warnings (all inside the two copied files). Read
the role filter (`web/src/data/admit.ts`): rows are rebuilt from known columns and what a
role may not see is dropped before storage. Looked at the running site: landing, sign-in,
the reveal, the dashboard calm and in alert. Scanned for contact details and keys: none.
Committed as `5684b24`.

Findings from the coding agent's report, and what was done:
- Contract: `ended_at` on acknowledgement was set by nobody. Now the brain sets it (v0.3).
- Contract: `last_seen_at` may be null (v0.3).
- Contract: `room_alert` carried a temperature that family could read through the
  timeline. Removed (v0.3).
- Contract: a fixture's last line is never seen for long. Rule added (v0.3).
- Identity: two wrong statements corrected (the landing's font stack; the offline ink).
- Left for Web B: the landing still lists ESP32 under "Built with"; the press tiles draw
  each teammate as a newspaper masthead; an empty paragraph where the copyright was.

The body changed to a Reachy Mini Lite. Brain A now has three body drivers (none, the robot,
the optional sensor board) and reads the camera and audio from the robot or the machine.

### Sat Nov 14, 5:10 PM
Track rules logged from Devpost, Discord and Chert's challenge page. Corrections to earlier
notes: the hardware section is titled "Hardware Info"; SpaceXSI is a raffle that needs Cursor
plus a Grok Bot automation, and is not DeepSpace; DeepSpace has no prize. Chert's own page
settles most of what was open: teams get a free line for 48 hours with 50 minutes of
FaceTime in total and calls of at most 5 minutes; the agent can see the caller's camera,
send video back, and place calls; outbound calls and texts go only to phones that have
verified with the line; Windows 11 is supported in beta with Node 24. The 50 minutes are the
scarce thing: testing spends them.

The team's hardware changed: the dog carries a Raspberry Pi 5. Brain A now targets the Pi,
with the Windows laptop as the place it is developed and the fallback, one codebase. Not yet
known: whether an ESP32 is still in the body, and what is wired to the Pi.

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
