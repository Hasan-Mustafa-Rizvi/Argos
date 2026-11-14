# Web build plan

Version 0.2 · Sat Nov 14 2026

How the dashboard gets built, in what order, and which reference to open for each piece. Read
`IDENTITY.md` first for the look, and `../contract/CONTRACT.md` for the data. Reference files
are indexed in `references/README.md`.

This plan covers `web/` only.

---

## The flow

```
/  landing  ──▶  /sign-in  ──▶  logo reveal (once)  ──▶  /dashboard
```

| Route | What it is | Signed in? |
|---|---|---|
| `/` | The Cobalt Toile landing with Argos's words | No |
| `/sign-in` | A real form, and two buttons that open the demo | No |
| `/dashboard` | The monitor. Family view or clinician view. | Yes. Without a session it sends you to `/sign-in`. |

---

## Stack

- Vite, React, TypeScript, Tailwind, shadcn/ui. React Router for the three routes.
- Fonts from Google Fonts: Libre Baskerville, Atkinson Hyperlegible, JetBrains Mono.
- Icons from Lucide.
- Deployed on Netlify from `web/`, with a redirect so deep links load.
- Animation with CSS. Add an animation library only if a prompt names one.

## Folder shape inside `web/`

```
web/
  src/
    components/ui/      shadcn parts, and cobalt-toile-landing.tsx copied in unchanged
    components/argos/   our own: Plate, StateWord, Meander, TickGauge, DitherScene, ArgosMark ...
    pages/              Landing, SignIn, Dashboard
    data/               the data seam, below
    auth/               the auth seam, below
    styles/             tokens.css: every variable from IDENTITY.md section 1
  public/               logo files, the reveal clip
```

## Two seams that let the rest be built now

The dashboard must not know where its data or its session comes from.

**Data seam.** One interface with two implementations.

| | Replay | Live |
|---|---|---|
| Source | `contract/fixtures/demo_scenario.jsonl`, copied into the build | Supabase, with live updates |
| Built in | W2 | W3 |
| Chosen by | `VITE_DATA_MODE=replay` | `VITE_DATA_MODE=live` |

The interface gives the page: the device row, the incident list, the timeline, the readings,
and one action, acknowledge. Replay stays in the product for good. If live data stops
arriving, the dashboard says so and offers replay.

**Auth seam.** One interface with two implementations: a demo session held in the browser
(W1), and Supabase sign-in (W3). It answers three questions: is someone signed in, what is
their role (`family` or `clinician`), is it a demo session, and how do they sign out. A demo
session always gets replay data and never the live view.

---

## Argos's view: the centre panel

This is the largest panel and the one a judge looks at first. It is the live view from the
dog's camera. Decided by Hasan, Sat 3:25 PM.

**Who gets it.** Only a family account that has signed in and passed its second factor.
Clinicians do not see images, live or stored. Demo sessions never receive it. Nothing in the
live view is stored.

| Situation | What the panel shows |
|---|---|
| Family account, Argos online | The live view, printed in dither in the current ink. A control shows the original picture. A "LIVE" label and the time of the last frame. |
| Family account, `alert` | The live view, with the stored snapshot from the moment of escalation beside or under it, and the Acknowledge button. |
| Family account, frames stop for 5 s | The last frame, faded, and "No picture for N seconds". The rest of the dashboard keeps working. |
| Clinician account | The mark and the line "The live view is for family". The panel gives its space to sensor history. |
| Demo session | The mark and the line "The live view opens for signed-in family". |
| Argos offline | The mark, faded, and when Argos was last seen. |

**How frames travel** is defined in `../contract/CONTRACT.md` section 6: small JPEG frames
sent a few times a second over a private live channel. Low resolution and a low frame rate
are fine, because the dither treatment is the look. This keeps the live view working on a
poor venue network and needs no extra service.

## Work packages

Each one is a single prompt to a coding agent and leaves the site working.

### W1. Shell, landing, sign-in, reveal

Depends on nothing. Can start now.

| Piece | Open this reference | Take |
|---|---|---|
| Tokens | `IDENTITY.md` sections 1 to 3 | Every variable, mapped onto shadcn's variable names |
| Landing | `references/cobalt-toile/.../cobalt-toile-landing.tsx` and `demo-indigo.tsx` | The file unchanged, driven by props |
| Landing words | `../progress.md` | The idea, how it behaves, the "why not X" answers |
| Sign-in | `references/21st/sign-in.tsx` | The split layout only |
| Sign-in scene | `references/21st/ridgeline-dither-footer.tsx` | The dither canvas, as a `DitherScene` with our cobalt ramp |
| Mark | `logo/` | The three SVG files |
| Reveal | `references/21st/liquid-glass-logo-reveal.tsx` | The component, driven with our mark, paper and cobalt |
| Who made this | `IDENTITY.md` section 7 | The team, in the template's list section |
| Dashboard shell | `IDENTITY.md` section 7 | Header, meander, the grid of empty labelled plates, the state reprint |

Proves itself when: the three routes work, both demo buttons reach the dashboard through the
reveal, the dashboard reprints in all three inks, and the site is live on Netlify.

### W2. Dashboard on replay data

Depends on W1 and contract v0.2.

| Piece | Open this reference | Take |
|---|---|---|
| Data seam, replay | `../contract/CONTRACT.md` sections 3 and 5 | Row shapes, the replay rules |
| Grid | `references/21st/finance-bento.tsx` | Twelve columns and the responsive spans |
| Plate weight | `references/21st/bento-dashboard.tsx` | Border, offset shadow, label style |
| Tick gauges | `references/21st/finance-bento.tsx`, `updateCash` and `updateGoals` | Rows of ticks, some filled |
| Incidents | The ledger in the landing template | Rows that open |
| Who sees what | `../contract/CONTRACT.md` section 4 | Family and clinician differences |
| Argos's view | `../contract/CONTRACT.md` section 6, and `DitherScene` from W1 | The demo states now, the live frames in W3 |

Proves itself when: the scripted run plays end to end, the state reprints at the right
moments, an escalated incident can be acknowledged, and family and clinician see different
things.

### W3. Live data and real sign-in

Depends on W2 and the Supabase project. Swaps in the live data source, Supabase sign-in with
a second factor, and the live view channel, behind the two seams. Replay stays.

---

## Rules for every work package

- Nothing invented: no fake people, clients, numbers, quotes or press.
- The landing template file is copied in whole and not edited, except where this plan names a
  removal. Its license comment stays at the top.
- Every borrowed piece is listed in `web/CREDITS.md` with its author, and the landing footer
  carries one credit line that links to it.
- The checks in `IDENTITY.md` section 8 pass before a package is reported done.
