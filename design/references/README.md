# References

What the identity was built from, and what to take from each. The source files sit beside
this README on Hasan's machine and are not in the repository, because they are other people's
work. This index is the record of what was used and who made it.

Everything here is reference. Read it to understand a look or a technique. Do not paste whole
files into `web/` unless the build plan says to.

| Reference | Path under `design/references/` | Made by | License |
|---|---|---|---|
| Cobalt Toile Landing | `cobalt-toile/cobalt-toile-landing/components/cobalt-toile-landing/` | Kedhareswer Naidu, kedhar.pages.dev | MIT |
| Ridgeline Dither Footer | `21st/ridgeline-dither-footer.tsx` | 21st.dev community component | As published on 21st.dev |
| Sign-in page | `21st/sign-in.tsx` | 21st.dev community component | As published on 21st.dev |
| Brutalist bento dashboard | `21st/bento-dashboard.tsx` | 21st.dev community component | As published on 21st.dev |
| Finance bento | `21st/finance-bento.tsx` | Roman Vasnev, vasnev.art | As published on 21st.dev |
| HackUTA 2026 site | `hackuta/HACKUTA_DESIGN_CONTEXT.md`, live at hackuta.com | HackUTA organizers | Their own |
| Glass Icon Reveal | `glass-icon-reveal/index.html` | Zanwei Guo, github.com/zanwei/glass-icon-reveal | MIT |

## What we take, and what we leave

### Cobalt Toile Landing: the identity itself

- **Take:** the whole template as the landing page. Its two-colour rule, its `color-mix`
  token formulas, its serif-and-sans pairing, its hatching, its ledger rows and bookmarks.
  `demo-indigo.tsx` shows how the entire page is driven by props.
- **Leave:** the palette switcher, the newsletter, the invented clients, press and
  statistics. Nothing invented stays.
- **Rule:** change the words through props. Do not redraw the illustrations.

### Ridgeline Dither Footer: how images are printed

- **Take:** the ordered-dither technique. `RDF_BAYER`, `rdfDither`, `rdfRidgeline` and the
  draw loop print a mountain range through an 8 by 8 Bayer matrix on a small pixel-scaled
  canvas. The `palette.tones` prop accepts any seven-tone ramp. We use it as a scene (the
  island on the horizon), and the same technique prints Argos's view.
- **Leave:** the footer itself: the link columns, socials, credit line and altimeter.

### Sign-in page: the layout only

- **Take:** the split screen. Form on the left, one large image panel on the right, fields
  that rise in one after another.
- **Leave:** violet accents, glass input wrappers, Google sign-in, testimonials, the stock
  photo, the rounded-3xl corners.

### Brutalist bento dashboard: the weight

- **Take:** the confidence. Thick borders, hard offset shadows, uppercase labels, a dotted
  texture, one strong heading per panel. In Argos the border is 2 px ink and the shadow is
  hatched.
- **Leave:** black-and-white, the candy chart colours, the charts themselves, 3 px borders,
  framer-motion springs on everything.

### Finance bento: the grid and the instruments

- **Take:** the twelve-column bento grid with responsive spans, the tick-mark gauges
  (`updateCash`, `updateGoals`), big light numerals with a small mono caption, panels that
  enter one after another.
- **Leave:** the dark neon palette, glass and blur, rounded 28 px cards, the dot-matrix
  numbers, drawing with `innerHTML`.

### HackUTA 2026 site: the theme done well

- **Take:** the restraint. Pottery and illustration over marble and gold, a Greek key line
  that doubles as progress, one dramatic inversion used once, plain navigation labels with
  myth only as flavour. Its "kiln transition" is the precedent for our state reprint.
- **Leave:** its palette and its artwork. Argos is cobalt on cream, not black on terracotta,
  and must not look like a copy of the event's own site.

### Glass Icon Reveal: one moment

- **Take:** a single recorded clip of the Argos mark being revealed, played once after
  sign-in.
- **Leave:** the tool itself. It is a standalone page with controls, not a component. We
  record with it and ship the clip.
