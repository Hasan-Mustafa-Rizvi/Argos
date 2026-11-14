# Argos software tracker

**Last updated:** Sat Nov 14 2026, 3:30 PM CT
**Status:** Visual identity, logo and web build plan written. W1 is ready to hand to a coding agent.

Hasan owns all software. This file records where the software is. Coding agents never edit it.

## Status at a glance

| # | Milestone | Lane | State | Waiting on |
|---|---|---|---|---|
| M0 | Repo layout, ignore rules, agent rules, docs | root | Done | |
| M1 | Contract v0.1 and scripted demo run | `contract/` | Done | |
| W1 | Web shell: tokens, landing, sign-in, logo reveal, empty dashboard frame | `web/` | Ready to start | |
| W2 | Dashboard on replay data | `web/` | Not started | W1, decision on Argos's view |
| M3 | Schema, access rules, live updates | `supabase/` | Not started | Supabase project |
| W3 | Dashboard reads live data and real sign-in, keeps replay mode | `web/` | Not started | W2, M3 |
| M5 | Brain: simulator first, then real detection and voice | `brain/` | Not started | M3 for writes |
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
| Sat 3:30 PM | The logo reveal is a recorded clip, not the WebGL tool embedded | The tool is a standalone page with controls. A clip is smaller and cannot break on a judge's phone. |
| Sat 3:30 PM | Reference source files stay on Hasan's machine, out of the repo | They are other people's work. The index and credits are in the repo. |
| Sat 3:30 PM | Kimi dropped from the plan | Hasan's call. Cursor and Claude Code are the coding agents. |

## Tracks this build serves

General, Hardware, Chert (best use of FaceTime), ElevenLabs, MLH Gemini API, MLH SpaceXSI.

## Accounts

| Account | Needed by | State |
|---|---|---|
| GitHub, Netlify | M0, M2 | Ready |
| Supabase | M3 | To create |
| Gemini (Google AI Studio) | M5 | To create |
| ElevenLabs | M5 | To create |
| Chert | M6 | To create. Confirm access lasts through Sunday afternoon first. |
| Email sender | M6 | To choose |
| Devpost | Sat midnight | To create |

## Open decisions

- **Argos's view.** The locked privacy rule rules out a live video feed in the centre panel.
  Proposed: a figure drawn from body points, with the snapshot on alert. Needs Hasan's yes,
  then a contract addition. See `design/BUILD_PLAN.md`.

## Backlog and known limits

- The Chert integration is unresearched. It is the least certain part of the plan.
- Demo accounts are open to anyone with the link while the event runs.

## Log

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
