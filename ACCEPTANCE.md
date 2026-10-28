# Verification — 2026-10-28

Target: Ubuntu 26.04.1; Intel i5-6200U; about 7 GiB RAM; OpenCode 2.1.1.

## Completed checks

- Strict TypeScript check against the real OpenCode 2.1.1 SDK.
- Behavior tests for session routing, stale recordings, edited/discarded review,
  voice-only/all reply selection, streaming Markdown filtering and cancellation.
- Python protocol, cancellation and configuration preservation tests; Python lint
  and strict type checks.
- Real CPU recognition of a synthesized question and local speech synthesis.
- A temporary PipeWire echo-cancellation source/sink starts and is removed on close.
- Speech namespace has no external network access.

## Live verification

Implementation verification is in progress. Final audio, TUI, instruction-discovery,
reload and parent-health results will be recorded here before publication.

This document does not equate source checks with live acceptance.
