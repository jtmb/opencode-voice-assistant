import { test } from "node:test"
import assert from "node:assert/strict"
import { VoiceController, type Host } from "../src/controller.ts"
import { defaults, parseEvent, type Settings, type WorkerCommand } from "../src/protocol.ts"
import { Sentences, spokenText } from "../src/sentences.ts"
import { Host as PluginHost } from "@opencode/plugin/host"
import { fileURLToPath } from "node:url"

function fixture(overrides: Partial<Settings> = {}) {
  const settings = { ...defaults, ...overrides }
  const commands: WorkerCommand[] = []
  const prompts: { sessionID: string; text: string; id: string }[] = []
  const interrupted: string[] = []
  let review: Host["review"] = async (text) => text
  const controller = new VoiceController({
    send: (command) => commands.push(command),
    submit: async (sessionID, text, id) => { prompts.push({ sessionID, text, id }) },
    interrupt: async (sessionID) => { interrupted.push(sessionID) },
    review: (text) => review(text), status: () => {}, partial: () => {}, error: () => {},
  }, () => settings)
  controller.setSession("ses_first")
  return { controller, settings, commands, prompts, interrupted, review: (callback: Host["review"]) => { review = callback } }
}

test("automatic speech uses the selected session and unique id; stale transcripts are discarded", async () => {
  const f = fixture()
  const epoch = f.controller.epoch
  await f.controller.worker({ type: "transcript", text: "Explain this project", epoch })
  assert.equal(f.prompts[0].sessionID, "ses_first")
  assert.match(f.prompts[0].id, /^msg_/)
  f.controller.setSession("ses_second")
  await f.controller.worker({ type: "transcript", text: "Wrong session", epoch })
  assert.equal(f.prompts.length, 1)
  assert.ok(f.commands.some((command) => command.type === "cancel"))
})

test("review can edit, discard, or become stale during a session change", async () => {
  const f = fixture({ submission: "review" })
  f.review(async () => "Corrected text")
  await f.controller.worker({ type: "transcript", text: "Wrong text", epoch: f.controller.epoch })
  assert.equal(f.prompts[0].text, "Corrected text")
  f.review(async () => undefined)
  await f.controller.worker({ type: "transcript", text: "Discard", epoch: f.controller.epoch })
  f.review(async () => { f.controller.setSession("ses_second"); return "Stale" })
  await f.controller.worker({ type: "transcript", text: "Stale", epoch: f.controller.epoch })
  assert.equal(f.prompts.length, 1)
})

test("voice-only readout ignores typed turns and other sessions; all mode includes typed turns", async () => {
  const f = fixture()
  f.controller.text("ses_first", "typed", "Silent reply. ")
  assert.equal(f.commands.filter((c) => c.type === "speak").length, 0)
  await f.controller.worker({ type: "transcript", text: "Hello", epoch: f.controller.epoch })
  f.controller.delivered("ses_first", f.prompts[0].id)
  f.controller.text("ses_other", "other", "Not ours. ")
  f.controller.text("ses_first", "voice", "First sentence. Second")
  f.controller.text("ses_first", "voice", " sentence", true)
  assert.deepEqual(f.commands.filter((c) => c.type === "speak").map((c) => c.text), ["First sentence.", "Second sentence"])
  f.controller.delivered("ses_first", "msg_typed")
  f.controller.text("ses_first", "typed2", "Still silent. ")
  f.settings.readout = "all"
  f.controller.text("ses_first", "typed3", "Now spoken. ")
  assert.equal(f.commands.filter((c) => c.type === "speak").length, 3)
})

test("wake interrupts playback only; explicit cancel interrupts OpenCode", async () => {
  const f = fixture({ readout: "all" })
  f.controller.text("ses_first", "reply", "Starting. ")
  await f.controller.worker({ type: "wake", epoch: f.controller.epoch })
  f.controller.text("ses_first", "reply", "Do not keep reading. ")
  assert.equal(f.interrupted.length, 0)
  assert.equal(f.commands.filter((c) => c.type === "speak").length, 1)
  await f.controller.worker({ type: "transcript", text: "cancel task", epoch: f.controller.epoch })
  assert.deepEqual(f.interrupted, ["ses_first"])
  assert.equal(f.prompts.length, 0)
  f.controller.dispose()
  assert.equal(f.commands.at(-1)?.type, "shutdown")
})

test("streaming markdown excludes code and URLs across arbitrary chunk boundaries", () => {
  const raw = "Here is help.\n```python\nprint('hey assistant')\n```\nRead `secret_code` and [the guide](https://example.com).\nDone!"
  const stream = new Sentences()
  const spoken: string[] = []
  for (const character of raw) spoken.push(...stream.push(character))
  spoken.push(...stream.push("", true))
  assert.equal(spoken.join(" "), "Here is help. Read and the guide. Done!")
  assert.ok(!spokenText(raw).includes("secret_code"))
  assert.throws(() => new Sentences().push("x".repeat(262145)), /limit/)
})

test("audio protocol rejects unknown and malformed messages", () => {
  assert.deepEqual(parseEvent('{"type":"wake","epoch":2}'), { type: "wake", epoch: 2 })
  assert.throws(() => parseEvent('{"type":"transcript","epoch":"bad","text":"x"}'))
  assert.throws(() => parseEvent('{"type":"run_shell","command":"x"}'))
  assert.throws(() => parseEvent("not json"))
})

test("the actual SDK discovers the local TUI entrypoint and no server harness", () => {
  const entries = PluginHost.resolve({ directory: fileURLToPath(new URL("../", import.meta.url)) })
  assert.match(entries.tui ?? "", /tui\.tsx$/)
  assert.equal(entries.server, undefined)
  assert.equal(PluginHost.resolve({ directory: "/tmp/nonexistent-voice-plugin" }).tui, undefined)
})
