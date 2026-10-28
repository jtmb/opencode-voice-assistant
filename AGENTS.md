# OpenCode Voice Assistant

This repository is an OpenCode v2 **TUI plugin**, not an agent harness.
Honor applicable parent instructions. In the computer-use checkout, also read
`../AGENTS.md` and `../docs/maintainer-policy.md`; these rules supplement them.

## Architecture

- OpenCode owns sessions, models/providers, agents, tools, permissions and history.
- Use only public `@opencode/plugin/tui` and authenticated `context.client` APIs.
- Never modify the OpenCode binary, import private TUI internals, start an LLM
  server, add an agent loop, or rebuild a desktop chat application.
- `src/` contains the TUI adapter, speech presentation and worker transport.
- `audio/` contains a local CPU-only Vosk/Piper subprocess, communicating over
  JSON lines on stdin/stdout. Stdout is protocol only; diagnostics go to stderr.
- The speech subprocess has no internet access. Use transient PipeWire echo
  cancellation without changing system audio defaults. Release all audio resources.
- Keep requests bound to their original session; cancel capture/playback on
  session changes. Wake interruption stops speech; only “cancel task” stops work.
- Audio and partial transcripts stay in memory. OpenCode keeps its normal chat
  history; do not create another conversation store or log dictated content.

## Preferences

Persist preferences through OpenCode plugin storage. Default to hands-free,
“hey assistant”, automatic submission and speaking voice-initiated replies only.
Also support transcript review and reading all active-session replies.
Background listening stays active while the owning TUI is open.

## Verification

Run from this folder after `./setup.sh --dev`:

```bash
npm run check
npm run smoke:audio
git diff --check
```

`check` runs strict SDK typechecking, TypeScript behavior tests, Python lint/type
checks and Python tests. The audio smoke check uses real models and audio devices.
Live TUI acceptance is separate: confirm commands/settings, real session traffic,
streamed speech, interruption, reload cleanup and instruction discovery in 2.1.1.
Record actual checks and limitations in `ACCEPTANCE.md`. Run relevant parent
health checks when integrating. Never present fixtures as live acceptance.

## Git and installation

The public plugin repository has independent history; computer-use tracks only
its submodule revision. Preserve unrelated parent changes and index entries.
Do not commit models, virtual environments, recordings, credentials or runtime
state. Use lockfiles and checksum-verified setup downloads. Configuration changes
must be previewable, preserve existing settings, and use the repository's source
and deployment workflow. Disabling the plugin must not stop OpenCode's backend.
