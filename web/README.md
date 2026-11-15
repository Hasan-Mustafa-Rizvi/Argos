# Argos web

The Argos website: the landing page, sign-in, and the dashboard that family and clinicians
read. Vite, React, TypeScript, Tailwind and shadcn/ui. It runs with no backend: the dashboard
plays a scripted run of the device in the browser.

## Run

```
npm install
npm run dev
```

Then open the address Vite prints (usually http://localhost:5173).

| Route | What it is |
|---|---|
| `/` | The landing page |
| `/sign-in` | Sign-in, and the two buttons that open the demo |
| `/dashboard` | The dashboard. It needs a session, and a demo session is enough. |

Add `?dev=1` to the dashboard address for a state switcher and replay controls (speed and
restart).

## Build

```
npm run build     # type check, then build into dist/
npm run preview   # serve dist/ locally
```

## Test and check

```
npm test          # Vitest and Testing Library
npm run lint      # oxlint
npm run typecheck # tsc -b
```

## Settings

Copy `.env.example` to `.env.local` to change them.

| Name | Meaning |
|---|---|
| `VITE_DATA_MODE` | `replay` plays the scripted run. `live` reads the backend, and only when both settings below are set. Any other value, or a live mode with either setting missing, stays on the script. |
| `VITE_SUPABASE_URL` | Project URL. Publishable. Leave empty to keep the demo. |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Publishable key. Leave empty to keep the demo. |

## The scripted run

`src/data/demo_scenario.jsonl` is a byte-for-byte copy of `contract/fixtures/demo_scenario.jsonl`
at the repository root. The contract's file is the original. When it changes, copy it here
again. Nothing in this folder imports from outside it.

## Netlify

`netlify.toml` builds with `npm run build`, publishes `dist/`, and serves `index.html` for
`/sign-in` and `/dashboard` so both load directly. Create the site with `web` as its base
directory.

## Credits

See [CREDITS.md](./CREDITS.md).
