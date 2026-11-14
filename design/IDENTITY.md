# Argos visual identity

Version 0.1 · Sat Nov 14 2026

Argos looks like a cobalt engraving on cream paper: one ink, one paper, drawn lines, hatching
and dither where other products use gradients and glass. It comes from four references, listed
with what we take from each in `references/README.md`.

**The one rule.** Two colours. Everything on a page is mixed from the ink and the paper. The
only thing that changes the ink is Argos's state.

---

## 1. Colour

### The plate

| Token | Value | Use |
|---|---|---|
| `--paper` | `#f7f4ec` | Page background |
| `--ink` | set by state, see below | Lines, borders, headings, primary buttons |
| `--text` | `color-mix(in oklab, var(--ink) 42%, #0b0b14)` | Body text |
| `--soft` | `color-mix(in oklab, var(--text) 74%, var(--paper))` | Secondary text |
| `--line` | `color-mix(in oklab, var(--ink) 24%, var(--paper))` | Hairlines, quiet borders |
| `--wash` | `color-mix(in oklab, var(--ink) 6%, var(--paper))` | Panel fill |
| `--night` | `color-mix(in oklab, var(--ink) 15%, #05060b)` | The dark panel behind Argos's view |
| `--on-night` | `color-mix(in oklab, var(--paper) 94%, var(--ink))` | Text and lines on `--night` |

These are the landing template's own formulas, so the landing and the dashboard match without
any conversion.

### The state reprints the page

This is the signature of the dashboard. When Argos changes state, the page is reprinted in a
different ink. One variable changes and every border, heading and button follows over 600 ms.

| State | Ink | Name | Text on paper | Ink on paper |
|---|---|---|---|---|
| `calm` | `#2238c4` | Cobalt | 13.9 : 1 | 7.9 : 1 |
| `checking` | `#8a5a0b` | Ochre | 12.3 : 1 | 5.4 : 1 |
| `alert` | `#7a1d2b` | Oxblood | 14.7 : 1 | 9.4 : 1 |
| offline | `#46547e` at 60% | Faded cobalt | | |

A judge standing two metres away can read the state from the colour of the screen alone.
Colour never carries the state by itself: the state word is always printed in large type too.

The landing and sign-in pages are always cobalt.

### Dither ramp

Seven tones from paper to ink, for ordered-dither imagery on paper:

`#f7f4ec` `#dadfea` `#b4c3e6` `#8ba3e0` `#607fd7` `#3c5cce` `#2238c4`

On the night panel, from night to paper:

`#080e22` `#1a2134` `#373d4e` `#606571` `#91939a` `#c5c5c4` `#f7f4ec`

For other inks, build the ramp the same way: mix ink into paper at 0, 12, 28, 46, 66, 84 and
100 percent.

---

## 2. Type

| Role | Face | Where |
|---|---|---|
| Display | Libre Baskerville 400, 700, italic | Headings, the state word, incident titles |
| Text and UI | Atkinson Hyperlegible 400, 700 | Body, buttons, forms |
| Data and labels | JetBrains Mono 500 | Times, readings, small capital labels |

- Libre Baskerville is already in the landing template's font stack, so loading it makes the
  landing identical on every device.
- Atkinson Hyperlegible was designed for low-vision readers. That suits a product a family
  member checks in a hurry.
- Labels are mono, 11 px, uppercase, letter-spacing 0.12em, in `--soft`.
- Body text is never smaller than 16 px. Numbers that change use tabular figures.
- The state word is the largest type on the dashboard: Baskerville 700, clamp(40px, 6vw, 72px).
- Italic Baskerville in ink is the emphasis style, as the landing does with `*asterisks*`.

---

## 3. Shape and line

- **Plates, not cards.** Panels have a 2 px ink border, square corners (0 to 2 px radius) and
  a `--wash` fill.
- **Hatched shadow.** The primary panel on a page sits on a 6 px offset block of 45 degree ink
  hatching instead of a blurred shadow. Secondary panels have no shadow. This is the
  hard offset shadow from the brutalist reference, redrawn as engraving.
- **Hairlines** in `--line` separate rows. No zebra stripes.
- **Chips** are the one rounded shape: full pills with a 1 px ink border.
- **Buttons.** Primary: ink fill, paper text, square. Secondary: paper fill, 2 px ink border.
  Every target is at least 44 by 44 px.
- **Focus** is a 3 px ink outline with a 2 px offset. Never removed.

---

## 4. Texture and ornament

- **Hatching** fills anything that would otherwise be a flat tint: shadows, the stillness
  gauge's unfilled part, disabled buttons.
- **Ordered dither** (8 by 8 Bayer, 2 px cells) is how images are printed: the ridgeline
  scene, Argos's view, the snapshot's default treatment.
- **The meander.** A Greek key line runs under the dashboard header. It is the heartbeat: it
  steps forward once each time Argos reports in, and it stops and fades when Argos is offline.
- **Tick gauges.** Durations and levels are drawn as rows of small ticks, some filled, in the
  manner of a ruler on an engraving. Used for stillness and room temperature.
- No gradients except inside dither. No glass, no blur, no drop shadows, no emoji, no stock
  photos.

---

## 5. Motion

| Moment | Motion | Length |
|---|---|---|
| State change | Ink reprints across the page | 600 ms |
| Panel entering | Lines draw in, then the fill settles, as an etching | 400 ms |
| Heartbeat | Meander steps one unit | 300 ms |
| New timeline row | Slides down 8 px and fades in | 250 ms |
| Sign-in to dashboard | The logo reveal, once per session, skippable | 2.5 s at most |

Under `prefers-reduced-motion` nothing moves. States still change colour, instantly.

---

## 6. The mark

`logo/argos-mark.svg` is a watching hound in profile inside a seal. It takes its colour from
`currentColor`, so it reprints with the state like everything else. `logo/argos-lockup.svg`
adds the wordmark. `logo/argos-mark-cobalt.svg` has fixed colours for tools that cannot read
CSS, such as the logo reveal recorder.

Minimum size 24 px. Clear space of a quarter of its width on every side. Never on a photo.

---

## 7. Page by page

### Landing, `/`

The Cobalt Toile landing template, printed in cobalt, with Argos's words. It already is the
identity. Change the copy, not the drawing.

- Palette switcher off. Newsletter block removed: there is nothing to subscribe to.
- The "press" list is removed or replaced with nothing invented. No fake articles, clients,
  statistics or testimonials anywhere.
- The four bookmarks become the four things Argos does: watches, checks, stands down,
  escalates.
- The ledger becomes the questions people ask: why not a watch, a phone, a pendant, a camera.
  The answers are in `progress.md`.
- The marquee is labelled "Built with" and lists the real parts.
- Both calls to action go to sign-in.

### Sign-in, `/sign-in`

The split layout from the sign-in reference. Left: the form on paper. Right: the ridgeline
scene printed in cobalt dither, captioned as Ithaca on the horizon.

- Two large buttons come first: "Open as family" and "Open as clinician". The email and
  password form sits below them for a real account.
- No social sign-in, no testimonials, no violet.

### The logo reveal

After sign-in, the mark is revealed once, then the dashboard is there. The reveal is a
recorded clip made with the glass icon reveal tool, with a still mark as the fallback. It can
be skipped with any key or tap and never plays twice in a session.

### Dashboard, `/dashboard`

A twelve-column grid of plates. Argos's view is in the centre and is the largest thing on the
page.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [mark] ARGOS    Watching over Eleni          FAMILY · LIVE         Sign out  │
│ ▂▃▂▃▂▃▂▃▂▃▂▃▂▃▂▃▂▃▂▃▂▃▂▃▂▃▂▃  meander heartbeat  ▂▃▂▃▂▃▂▃▂▃▂▃▂▃▂▃▂▃▂▃▂▃▂▃▂▃▂▃ │
├───────────────┬──────────────────────────────────────┬───────────────────────┤
│ STATE         │                                      │ TIMELINE              │
│ Calm          │                                      │ 3:41 Argos asked:     │
│ since 3:12 PM │          ARGOS'S VIEW                │      Are you okay?    │
├───────────────┤          (night panel, dither)       │ 3:41 Argos heard a    │
│ STILLNESS     │                                      │      call for help.   │
│ ▮▮▮▮▯▯▯▯▯▯▯▯  │                                      │ 3:12 Argos is online. │
├───────────────┤  [ Acknowledge ]  only during alert  │                       │
│ ROOM  23.4 °C │                                      │                       │
├───────────────┴──────────────────────────────────────┴───────────────────────┤
│ INCIDENTS  (ledger rows that open)          │ SENSOR HISTORY (clinician only)│
├──────────────────────────────────────────────────────────────────────────────┤
│ ridgeline strip, cobalt dither                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **State plate.** The state word, since when, and when Argos last reported.
- **Argos's view.** The only dark panel. What it shows is defined in `BUILD_PLAN.md`.
- **Acknowledge** is the only primary button on the page and only exists during an alert.
- **Timeline.** Newest first. Each row is the time in mono and the event's sentence.
- **Incidents.** Rows in the style of the landing's ledger. Opening an escalated row shows the
  summary, and the snapshot for family.
- **Sensor history** is for the clinician. Family sees a short "What Argos does" plate there.
- **On a phone** it is one column in this order: state, Argos's view, acknowledge (sticky
  during an alert), timeline, incidents, the rest.

---

## 8. Checks before anything ships

- Text contrast at least 4.5 : 1 in all three inks. The table in section 1 already clears it.
- Works at 375, 768, 1024 and 1440 px wide.
- Every control reachable and visible by keyboard.
- Nothing invented: no fake people, numbers, quotes or logos.
- Icons are SVG, from Lucide, in ink. No emoji.
