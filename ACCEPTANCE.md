# Verification — 2026-10-28

Target: Ubuntu 26.04.1; Intel i5-6200U; about 7 GiB RAM; OpenCode 2.1.1.

## Completed checks

- Strict TypeScript check against the real OpenCode 2.1.1 SDK.
- 8 TypeScript behavior tests: session routing, stale/disabled recordings,
  edited/discarded review, voice-only/all readout, streaming Markdown filtering,
  cancellation, and discovery through the real SDK's local-package loader.
- 11 Python tests: protocol validation, cancellation, microphone EOF cleanup and
  JSONC/configuration preservation; Python lint and strict type checks pass.
- Real CPU recognition of a synthesized question and local speech synthesis.
- A temporary PipeWire echo-cancellation source/sink starts and is removed on close.
- Speech namespace has no external network access.

## Live verification

- The unmodified installed OpenCode 2.1.1 TUI loaded the plugin footer and Settings
  dialog. Both submission/readout alternatives were selected, then restored to
  automatic submission and voice-only readout. Microphone off/on controls worked.
- Voice Settings opened the native OpenCode model picker without duplicating
  provider configuration.
- An acoustic wake phrase and question passed through the laptop microphone,
  plugin and native OpenCode session. Native history contains the recognized user
  message “what is the capital of france” and OpenCode's reply “Paris.”
- A fresh native session in the plugin folder identified the TUI-only ownership
  boundary and both exact npm verification commands from `AGENTS.md`, without
  calling tools or reading files. This was a real model response, not a fixture.
- A source hot reload replaced the audio subprocess, retained preferences and
  resumed wake listening. Exiting the TUI left no audio worker running.
- The real audio smoke test recognized its known synthetic question. Speech
  synthesis took 0.633 seconds for the short test sentence; initial model loading
  took 11.928 seconds in that run. OpenCode provider latency is separate.
- The speaker's own wake phrase caused zero activations. An external acoustic wake
  phrase interrupted a longer reply while playback was active. Disabling voice
  released capture. Temporary PipeWire nodes were removed on shutdown.
- Speech-process external connections fail with network unreachable.
- The actual stdio worker respected a competing microphone lock, acquired it after
  release, and processed batched disable/shutdown commands with a clean exit.
- `computer-use/scripts/health-check.sh` passed. Its source/fixture health result
  does not imply all unrelated MCP integrations are working in every location;
  the live test TUI displayed existing GitHub/Playwright MCP errors.
- OpenCode binary SHA-256 remained
  `0e81c77fcc27b263708b133bbf9880cd641060c20e22d3dec8a79b9a8db90450`.

## Limits and reproducibility

Hardware verification used controlled synthesized acoustic input. Recognition in
ordinary rooms depends on microphone placement and noise. Models load asynchronously,
so normal TUI use remains available during the roughly 12-second initial load.
This release supplies a Linux/PipeWire audio helper; other operating systems are
not tested. Default devices follow the system configuration.

Test reports and terminal captures remain in ignored `state/`; they are not shipped.
No audio recordings, model weights, provider credentials, independent LLM server,
or prototype desktop source are included in the repository.

This document does not equate source checks with live acceptance.
