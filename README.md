# OpenCode Voice Assistant

Local hands-free speech input and streamed speech output for the **OpenCode v2 TUI**. OpenCode remains the agent: it owns models, sessions, tools, permissions and history. This package adds audio I/O and compact terminal controls.

## Setup

Tested target: Ubuntu 26.04, OpenCode **2.1.1**, Python 3.14, PipeWire with its WebRTC echo-cancellation module, `bwrap`, `uv`, Node.js and npm. OpenCode supplies its own TUI runtime. Standalone OpenTUI rendering requires Node ≥26.4 or Bun ≥1.3.14; Node 22 can run this package's source checks and pure behavior tests.

```bash
git clone https://github.com/jtmb/opencode-voice-assistant.git
cd opencode-voice-assistant
./setup.sh
./opencode-voice /path/to/your/project
```

The launcher executes the installed, unmodified `opencode` command with this plugin added to its CLI configuration for that process. It preserves the other configured plugins, JSONC settings and existing inline configuration. It writes no global configuration and starts no separate agent server. Open or select an OpenCode session to begin using voice.

For a computer-use checkout, this package is the `voice-assistant` submodule:

```bash
git submodule update --init voice-assistant
cd voice-assistant
./setup.sh
./opencode-voice
```

To register it permanently, include its absolute package directory in the `plugins` array of your canonical CLI configuration source, preserving existing entries. In computer-use, use that repository's preview/apply/backup deployment workflow for `cli.json`. The package exports only `./tui`; server-plugin registration is unnecessary. The launcher is the configuration-free alternative.

Setup installs pinned dependencies and checksum-verified Vosk English and Piper Lessac-medium models inside the package. It never downloads a conversation model. `--reuse-models DIR` can copy matching existing model files after checking their hashes.

## Use

Say **“hey assistant”**, pause until listening begins, then speak your request. After a short pause it enters the active OpenCode session. Wake detection remains active while the terminal is in the background and during spoken output.

| Command | Behavior |
|---|---|
| `/voice` | Toggle hands-free listening |
| `/voice on` / `/voice off` | Enable or disable hands-free |
| `/voice settings` or `/voice_settings` | Open voice preferences |
| `/voice_listen` | Capture one request without a wake phrase |
| `/voice_stop` | Stop audio without cancelling OpenCode work |
| `/voice_cancel` | Explicitly interrupt the current OpenCode task |

The same actions are available through the command palette. No keyboard shortcuts are taken over; bind the `voice.*` commands through native OpenCode keybind settings if desired. Click the voice footer to open preferences.

Say the wake phrase during a reply to stop playback and speak again. Say **“cancel task”** after waking it to interrupt OpenCode execution. **“Stop speaking”** stops only audio. Native permissions and approval dialogs remain native OpenCode behavior.

## Settings

| Setting | Default | Alternatives |
|---|---|---|
| Hands-free | On | Off; one-shot listening still available |
| Submission | Send after pause | Editable transcript review before sending |
| Read replies | Voice requests only | All replies in the active session |
| Model/provider | Current OpenCode selection | Opens OpenCode's native model picker |

Preferences persist through OpenCode plugin storage. The session's committed agent remains authoritative; voice does not inspect private composer state or submit an existing unsent draft. Local/cloud inference follows the model selected in OpenCode. Recognition and synthesis always use this machine's CPU.

Changing sessions cancels recording and queued speech. Only one plugin instance can own microphone capture at a time; other instances display that the microphone is in use and can acquire it when released. The footer always shows the current microphone/audio state. Closing the TUI or unloading the plugin stops its audio subprocess and temporary PipeWire nodes.

## Audio and privacy

The plugin uses the system's default audio devices. It creates temporary, low-priority PipeWire source/sink nodes for WebRTC echo cancellation and routes only its own streams through them. It does not change device defaults. Headsets and quiet surroundings can improve recognition.

The Python audio process runs with private network and PID namespaces. Internet access is blocked for speech libraries and their diagnostics. The authenticated OpenCode client remains outside that namespace and uses the provider you selected.

Microphone samples and partial transcripts remain in memory. Submitted text becomes ordinary OpenCode history. The plugin keeps no second chat log and saves no recordings. `state/` contains only ignored runtime locks and test reports; the microphone lock file is intentionally retained and never unlinked.

## Development and verification

```bash
./setup.sh --dev
npm run check
npm run smoke:audio
```

`check` runs strict typechecking against SDK 2.1.1, TypeScript behavior tests, Python lint/type checks and Python tests. `smoke:audio` uses the real models, microphone and speakers; it plays test phrases, checks self-echo suppression, tests a second sound source during playback, and verifies cleanup and network isolation. It saves measurements, not microphone transcripts.

See [ACCEPTANCE.md](ACCEPTANCE.md) for actual verification and remaining limitations. Live TUI acceptance is separate from fixture tests. Package-specific contributor rules are in [AGENTS.md](AGENTS.md).

## Troubleshooting and removal

- If the audio worker fails to start, rerun setup and check that PipeWire, `pw-cat`, `pw-cli`, `pw-dump` and `bwrap` are available.
- If another TUI owns the microphone, disable voice there or close that TUI.
- If speech is misheard, use transcript-review mode or correct the text in OpenCode.
- During model loading, ordinary OpenCode typing and work remain available.
- To unload, close the launcher-started TUI and open ordinary `opencode`. If permanently registered, remove only this package's entry through your normal configuration deployment workflow.

## Components and notices

Uses [OpenCode's public TUI plugin API](https://opencode.ai/v2/docs/build/plugins/cli/), [Vosk](https://alphacephei.com/vosk/), [Piper](https://github.com/OHF-Voice/piper1-gpl) and [PipeWire](https://pipewire.org/). Dependency and model licenses remain their authors' licenses. Model cards and SHA-256 provenance are downloaded to `models/`; model weights, runtime binaries, dependencies and credentials are excluded from this repository.
