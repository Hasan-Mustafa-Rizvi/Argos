# Web build plan

Version 0.1 · Sat Nov 14 2026

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
| `/sign-in` | Two demo buttons and a real form | No |
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
their role (`family` or `clinician`), and how do they sign out.

---

## Argos's view: the centre panel

This is the largest panel and the one a judge looks at first.

The team's locked privacy rule is that nothing is recorded continuously and an image leaves
the room only after a check has failed. So the centre panel cannot be a live video feed. It
shows this instead:

| Device state | What the panel shows |
|---|---|
| `calm`, `checking` | A figure of the person, drawn from body points only and printed in dither on the night panel, like a figure on a vase. It moves as they move. No image has left the room. |
| `alert` | Family: the one snapshot Argos took, printed in two-tone dither, with a control to show the original. Clinician: the figure, and a note that the image is shared with family only. |
| Offline | The mark, faded, and when Argos was last seen. |

A caption under the panel always says which of these it is, in plain words.

**Status: needs Hasan's decision.** The figure needs body points sent from the laptop, which
is an addition to the contract. Until that is decided, W2 builds the panel with the snapshot
and offline states and a still figure.

---

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
| Reveal | `references/glass-icon-reveal/README.md` | Plays a recorded clip if present, a still mark if not |
| Dashboard shell | `IDENTITY.md` section 7 | Header, meander, the grid of empty labelled plates, the state reprint |

Proves itself when: the three routes work, both demo buttons reach the dashboard through the
reveal, the dashboard reprints in all three inks, and the site is live on Netlify.

### W2. Dashboard on replay data

Depends on W1 and the decision on Argos's view.

| Piece | Open this reference | Take |
|---|---|---|
| Data seam, replay | `../contract/CONTRACT.md` sections 3 and 5 | Row shapes, the replay rules |
| Grid | `references/21st/finance-bento.tsx` | Twelve columns and the responsive spans |
| Plate weight | `references/21st/bento-dashboard.tsx` | Border, offset shadow, label style |
| Tick gauges | `references/21st/finance-bento.tsx`, `updateCash` and `updateGoals` | Rows of ticks, some filled |
| Incidents | The ledger in the landing template | Rows that open |
| Who sees what | `../contract/CONTRACT.md` section 4 | Family and clinician differences |

Proves itself when: the scripted run plays end to end, the state reprints at the right
moments, an escalated incident can be acknowledged, and family and clinician see different
things.

### W3. Live data and real sign-in

Depends on W2 and the Supabase project. Swaps in the live data source and Supabase sign-in
behind the two seams. Replay stays.

---

## Rules for every work package

- Nothing invented: no fake people, clients, numbers, quotes or press.
- The landing template file is copied in whole and not edited, except where this plan names a
  removal. Its license comment stays at the top.
- Every borrowed piece is listed in `web/CREDITS.md` with its author.
- The checks in `IDENTITY.md` section 8 pass before a package is reported done.
