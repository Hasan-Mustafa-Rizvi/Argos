# Argos

A companion robot dog that keeps watch over someone who is recovering, elderly, or needs
looking after, and sends word when something is wrong.

Built at HackUTA 2026. The theme is Homer's Odyssey. Argos is the dog who kept watch for
twenty years and was the first to recognize Odysseus when he came home.

## What it does

1. **Watches.** It glances at the person now and then and listens.
2. **Checks.** When it notices a fall, a call for help or a long stillness, it turns to the
   person and asks, "Are you okay?"
3. **Stands down** if they answer or pat its head.
4. **Escalates** if they do not. It video calls the emergency contact with a live view,
   sends a backup email, and updates a dashboard for family and clinicians.

Nothing has to be worn, nothing is recorded continuously, and an image leaves the room only
after a check has failed.

## What is in this repo

| Folder | Contents |
|---|---|
| `contract/` | The agreed messages and records between the parts, with a scripted demo run |
| `web/` | The dashboard |
| `brain/` | The program on the laptop: detection, voice, escalation |
| `firmware/` | The ESP32 code for the dog's body |
| `supabase/` | Database schema and access rules |
| `docs/` | Architecture and the build tracker |
| `progress.md` | The team's idea, decisions and checklist |

## Team

Hasan, Neel and Farrell.
