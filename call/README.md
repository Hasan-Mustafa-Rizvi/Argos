# Argos call agent

When an incident escalates, this program texts the emergency contact over iMessage, then
FaceTimes them. On the call, an agent speaks for Argos, shows what the dog's camera sees,
answers questions from the incident, and takes an acknowledgement. It runs on a laptop and
learns about incidents from the backend, so it needs no connection to the brain.

How a call goes: Chert owns the FaceTime line and bridges the call into a LiveKit room that
this program makes. The program's agent sits in that room with one audio track and one video
track. It asks Chert's API for the call, stays silent until Chert reports `bridge_ready`, then
talks. The person's voice arrives as the track `facetime-remote-audio`.

## Install (Windows 11, natively; no WSL2 needed)

```
cd call
uv venv --python 3.12 .venv            # or: py -3.12 -m venv .venv
.venv\Scripts\activate
uv pip install -r requirements-dev.txt
python tools/fetch_models.py           # the offline phrase list's speech model, into call/models/
copy .env.example .env.local           # then fill it in; see Settings
```

`assets/argos-mark.png` is made from `design/logo/argos-mark.svg` by `python tools/make_mark.py`.

## Run it for the demo

In order, from `call/`:

```
python -m argos_call check                  # 1. settings, the line, open calls, seconds used
python -m argos_call rehearse               # 2. the conversation in a LiveKit room; no call, no minutes
python -m argos_call run --demo             # 3. watch the backend; real only with ARGOS_DRY_RUN=0
```

Step 3 sends nothing real unless `ARGOS_DRY_RUN=0` is set in `call/.env.local` or the
environment. `--demo` marks the judged demo: it may call after the 30 test minutes are used.

A healthy start of step 3 prints, in this order:

```
mode: REAL: texts and calls go out
contact: 'Son' (the number goes to Chert only)
backend: on
chert: key set, line set, https://facetime.trychert.com/api
livekit: set
voice: ElevenLabs eleven_flash_v2_5
answers: Gemini gemini-3.5-flash-lite
state files: ...\call\var
seconds used so far: 36 (0.6 of 50 minutes)
using the line set in CHERT_LINE_ID
line Lucas Martin: status available, availability available, worker accepting, current call none
  outbound audio yes, outbound video yes, video ready True, framing fit
hearing: the offline phrase list is on
hearing: Gemini gemini-3.5-flash-lite answers questions
REAL: an escalation will be texted and called (judged demo: past the 30 minute limit)
watching for escalations every 1.5 s
```

No warning lines should appear between them. A warning names the setting that is missing and
what still works without it.

Other commands:

| Command | Does |
|---|---|
| `python -m argos_call run --fake [fall\|help_call\|stillness\|manual]` | One made-up escalation, local only (the database is not touched), then stop. Its events are printed and kept in memory. In dry-run nothing is sent; with `ARGOS_DRY_RUN=0` it texts and calls, as a test (60 s limit) that says it is a test. |
| `python -m argos_call rehearse --browser` | The conversation in a LiveKit room; your browser opens LiveKit Meet in the same room so you can talk to the agent. No call, no minutes. |
| `python -m argos_call ring [--audio]` | Stage 1's proof: one test call that says one sentence, 60 s at most. |

## Settings

Read from the environment, then from `call/.env.local`.

| Name | Where the value comes from | Without it |
|---|---|---|
| `ARGOS_DRY_RUN` | You. `0` is the only value that sends. | Dry-run: texts and calls are logged, not sent; events say `"dry_run": true`. |
| `CHERT_API_KEY` | Chert web app, Developer page (https://app.trychert.com/developer), owners only. A project key (`ftk_...`) with `facetime:read` and `facetime:write`. Shown once. Not the CLI's sign-in. | Dry-run only. |
| `CHERT_PROJECT_ID` | `npx --yes @trychert/facetime@0.1.0-beta.21 whoami` (run in `call/`), or the web app. | Dry-run only. |
| `CHERT_LINE_ID` | `python -m argos_call check` lists it, or the web app's Lines. | The project's only line is used, with a warning. |
| `CONTACT_FACETIME_TO` | The contact's phone, international form (`+1...`). Must be verified with the Chert project. Goes to Chert only. | Dry-run only. |
| `CONTACT_LABEL` | You: how records name the contact, such as `Daughter`. Never a number. | `Family`. |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | LiveKit Cloud, project settings, API keys. | Dry-run only. |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | ElevenLabs; the same voice as the brain's. | No real call (a silent call is dropped by Chert). |
| `GEMINI_API_KEY` | Google AI Studio. Use a paid-tier key: on the free tier Google may keep what it is sent. | The call still speaks, shows and takes "I'm on my way" (offline phrase list); it cannot answer questions. |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Supabase project settings. The secret key; it stays on this laptop. | Nothing to watch, no events written. `run --fake` still runs. |
| `ELEVENLABS_MODEL` | Optional. | `eleven_flash_v2_5`, as the brain. |
| `GEMINI_MODEL` | Optional. | `gemini-3.5-flash-lite`, as the brain. |
| `CHERT_API_BASE` | Optional: `https://facetime.trychert.com/api` or `https://app.trychert.com/api`. Anything else is refused. | The first. |
| `ARGOS_CALL_STATE_DIR` | Optional. | `var` (the handled list and the seconds file). |
| `ARGOS_CALL_POLL_S` | Optional. How often to look for an escalation. | `1.5` |
| `ARGOS_VOSK_MODEL` | Optional. | `models/vosk-model-small-en-us-0.15` |

## The rules, and where they live

1. **Nothing real leaves unless switched on.** `config.Settings.dry_run` is false only for
   `ARGOS_DRY_RUN=0`. In dry-run the Chert client is not even made (`__main__.run`), and
   `escalate.Escalator` logs and records `"dry_run": true`.
2. **Minutes are money.** `session.Session` ends every call in a `finally`: at 4 minutes, 60
   seconds for a test, when the conversation ends, when the person hangs up, on any error. At
   start, `session.end_stale_calls` ends any call Chert still shows open. `state.Seconds` keeps
   the seconds in `var/seconds.json`, prints the total after every call, and refuses a real call
   past 30 minutes without `--demo`.
3. **One incident, one text, one call.** `state.Handled.claim` writes the step to
   `var/handled.json` before the request goes out. Chert's idempotency key is
   `argos-<incident id>-call-<n>`, reused only to send that same attempt again. Incidents whose
   `escalated` event is more than two minutes old are ignored.
4. **No personal details.** `redact.Redactor` masks the number (in any format), every key and
   every token minted, on every log line, every error and every exception.
5. **Nothing seen is kept.** Frames, the snapshot, the person's voice and the synthesised voice
   live in memory only. Logs say "heard 1.8 s of speech: question", never the words. The only
   files written are `var/handled.json` and `var/seconds.json`. The call is not recorded.
6. **Say only what the incident says.** Every fixed line is built from the incident
   (`incident.py`). Gemini's answers are bound by its instructions and then checked: a reply
   that diagnoses, says someone is hurt or fine, or advises is replaced by "I don't know"
   (`answers.safe_reply`).
7. **Chert's tools stay in `call/`.** The program calls Chert's HTTP API only. The CLI
   (`npx`) is used only for `whoami` and `doctor`, run from `call/`. Never `chert context
   --write`.

## On the call

1. **Speak.** "This is Argos, the companion dog watching over Eleni. At 3:41 PM I saw what
   looked like a fall. I asked if Eleni was okay and got no answer." Made before dialling.
2. **Show.** Live view frames from `view:<device id>` while they arrive; otherwise the stored
   snapshot; otherwise the Argos card with the time. The agent says which.
3. **Acknowledge.** "I'm on my way" (or "acknowledge", "I'll take it from here"...) is heard by
   the offline phrase list, and by Gemini when there is a key. The agent says what it heard,
   makes the dashboard's acknowledgement as "<label>, by FaceTime", says so, and hangs up. If no
   row comes back, someone was first, and it says that instead.
4. **Answer.** Gemini hears what the person said and answers from the incident, the timeline,
   and the current live frame, then ElevenLabs speaks it in Argos's voice.
5. **See: not built.** The person's camera does reach the room on this line (Chert reported
   `caller_video_published` on the test call), but Chert's own guide says the captured picture
   can include FaceTime's self-preview: our own video, which may show the person at home. A
   model could then "see a person" who is not the caller, so this step is left out.

Thirty seconds before the 4 minute limit the agent says it has to hang up, repeats the line,
and ends the call. Silence twice in a row (20 seconds each) ends the call too.

## Test

```
python -m pytest           # no network, no call: Chert, LiveKit, the backend and the models are faked
ruff check .
```

## Privacy

- The number goes to Chert and nowhere else. Records name the contact by `CONTACT_LABEL`.
- Gemini is sent the person's utterances and, when the live view is on, the current frame,
  to answer a question. On Gemini's free tier Google may keep them. Leave `GEMINI_API_KEY`
  empty to keep the person's voice on this laptop.
- LiveKit Cloud: this program does not use LiveKit's Agents framework and never starts a
  recording, so no transcript or audio is uploaded by it. Check that "Agent observability"
  is off in the LiveKit Cloud project settings; only the project owner can see that switch.
