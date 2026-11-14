# Argos visual identity

Version 0.4 · Sat Nov 14 2026

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
| offline | `#46547e` | Faded cobalt. Text is full strength; only the drawn parts (meander, mark, dither) fade to 60%, because faded text falls under 3 : 1. | | |

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

- The landing template's own font stack starts with fonts that only Apple devices have, so
  the site sets the template's serif and sans variables to these three. That makes the
  landing identical on every device with no edit to the template.
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
- **One art language: line engraving.** The landing's drawings and the logo are engraved
  line. Every ornament on the site is drawn the same way: crisp lines in the page ink, at
  their natural size, never stretched, never a pixel texture. The references were where the
  look came from, not things to copy: there is no dithered landscape anywhere.
- **Ordered dither** (8 by 8 Bayer, 2 px cells) is kept for one job only: printing camera
  pictures in the page ink, in Argos's view and on the snapshot. It is never scenery.
- **The wave.** A classical wave scroll, the border the Greeks' successors named the running
  dog, closes the dashboard at the bottom, as the meander opens it at the top. It is a
  repeating line pattern, not a picture.
- **The meander.** A Greek key line runs under the dashboard header. It is the heartbeat: it
  steps forward once each time Argos reports in, and it stops and fades when Argos is offline.
- **Tick gauges.** Durations and levels are drawn as rows of small ticks, some filled, in the
  manner of a ruler on an engraving. Used for stillness and room temperature.
- No gradients except inside dither. No blur, no drop shadows, no emoji, no stock photos.
- Glass appears exactly once: the logo reveal after sign-in. Nowhere else.

---

## 5. Motion

| Moment | Motion | Length |
|---|---|---|
| State change | Ink reprints across the page | 600 ms |
| Panel entering | Lines draw in, then the fill settles, as an etching | 400 ms |
| Heartbeat | Meander steps one unit | 300 ms |
| New timeline row | Slides down 8 px and fades in | 250 ms |
| Sign-in to dashboard | The glass logo reveal, once per session, skippable. Gentle: the mark is readable in every frame. | About 1.5 s |

Under `prefers-reduced-motion` nothing moves. States still change colour, instantly.

---

## 6. The mark

Hasan's design: a seated hound in line art, with a sensor at its ear and a tag on its collar,
inside a ring of Greek key and laurel. The files in `logo/` are traced from his original,
which is kept in `logo/source/`.

| File | Use |
|---|---|
| `argos-mark.svg` | The emblem. 64 px and larger. |
| `argos-mark-bold.svg` | The emblem with heavier lines. Under 64 px, favicons, and the logo reveal. |
| `argos-lockup.svg` | Emblem and wordmark side by side. Headers. |
| `argos-lockup-stacked.svg` | Emblem, wordmark and the line "Guardian & Assistant". Landing, sign-in. |
| `argos-mark-cobalt.svg` | Fixed cobalt, for places that cannot read CSS colour. |

All but the last take their colour from `currentColor`, so the mark reprints with the state
like everything else. It is never gold on charcoal in the product: it is ink on paper, or
paper on the night panel.

The Greek key in the mark's ring is the same line as the meander heartbeat on the dashboard.

Minimum size 32 px. Clear space of a quarter of its width on every side. Never on a photo.

---

## 7. Page by page

### Landing, `/`

The Cobalt Toile landing template, printed in cobalt, with Argos's words. It already is the
identity. Change the copy, not the drawing.

- Palette switcher off. Newsletter block removed: there is nothing to subscribe to.
- Nothing invented. No fake articles, clients, statistics, contact details or testimonials
  anywhere. The page says what is planned now, and its words are updated when plans change.
- **Who made this.** The template's press list becomes the team: Hasan, Neel and Farrell,
  with design, interface polish and organization credited to Hasan.
- **Credit in the footer.** One line names the landing template and its author and links to
  the full credits.
- The four bookmarks become the four things Argos does: watches, checks, stands down,
  escalates.
- The ledger becomes the questions people ask: why not a watch, a phone, a pendant, a camera.
  The answers are in `progress.md`.
- The marquee is labelled "Built with" and lists the real parts.
- Both calls to action go to sign-in.

### Sign-in, `/sign-in`

The split layout from the sign-in reference. Left: the form on paper. Right: an engraved
plate on the night colour: the Argos mark very large and cropped by the panel's edges,
inside a Greek key border.

- The email and password form is for real accounts, which also need a second factor.
- Two buttons open the demo: "Open the demo as family" and "Open the demo as clinician".
  The demo plays the scripted run and never shows the live view.
- No social sign-in, no testimonials, no violet.

### The logo reveal

After sign-in, the mark is revealed once through a drop of glass, then the dashboard is
there. It uses the liquid glass reveal component with `argos-mark-bold.svg`, the page's paper
as the backdrop and cobalt as the logo colour. It does not loop. It can be skipped with any
key or tap, never plays twice in a session, and falls back to a still mark where WebGL is
missing or motion is reduced.

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
│ STILLNESS *   │                                      │      call for help.   │
│ ▮▮▮▮▯▯▯▯▯▯▯▯  │                                      │ 3:12 Argos is online. │
├───────────────┤  [ Acknowledge ]  only during alert  │                       │
│ ROOM * 23.4°C │                                      │                       │
├───────────────┴──────────────────────────────────────┴───────────────────────┤
│ INCIDENTS  (ledger rows that open)          │ SENSOR HISTORY (clinician only)│
├──────────────────────────────────────────────────────────────────────────────┤
│ wave scroll band, line art in the page ink                                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

`*` Clinician only. Family does not receive sensor readings (contract section 4), so in those
two places family sees **Last check** (the most recent incident and how it ended) and
**Today** (checks counted by how they ended).

- **State plate.** The state word, since when, and when Argos last reported.
- **Argos's view.** The only dark panel, and the live view from the dog's camera for a
  signed-in family account. Frames are
  printed in dither in the current ink, with a control to show the original picture. A small
  "LIVE" label and the time of the last frame sit in its corner. What it shows in each state
  is defined in `BUILD_PLAN.md`.
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
