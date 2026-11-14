# Argos software tracker

**Last updated:** Sat Nov 14 2026, 2:45 PM CT
**Status:** Foundation and contract written. Dashboard is next.

Hasan owns all software. This file records where the software is. Coding agents never edit it.

## Status at a glance

| # | Milestone | Lane | State | Waiting on |
|---|---|---|---|---|
| M0 | Repo layout, ignore rules, agent rules, docs | root | Done | |
| M1 | Contract v0.1 and scripted demo run | `contract/` | Done | |
| M2 | Dashboard on replay data, deployed with a public link | `web/` | Next | Visual references |
| M3 | Schema, access rules, live updates | `supabase/` | Not started | Supabase project |
| M4 | Dashboard reads live data, keeps replay mode | `web/` | Not started | M2, M3 |
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

## Backlog and known limits

- The Chert integration is unresearched. It is the least certain part of the plan.
- Demo accounts are open to anyone with the link while the event runs.

## Log

### Sat Nov 14, 2:45 PM
M0 and M1 written. Contract v0.1 covers the state machine, the serial link, four record types,
who sees what, and the replay format. The scripted run has 61 lines: 24 device updates, 19
readings, 12 events and 6 incident writes across two incidents. Checked: lines are in time
order, event ids are unique, no summary or snapshot appears before an incident escalates, and
no phone number or email address appears anywhere in the file.
