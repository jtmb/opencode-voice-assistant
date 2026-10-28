export type Settings = {
  enabled: boolean
  submission: "automatic" | "review"
  readout: "voice" | "all"
}

export const defaults: Settings = { enabled: true, submission: "automatic", readout: "voice" }

export type WorkerCommand =
  | { type: "configure"; enabled: boolean; epoch: number }
  | { type: "listen"; epoch: number }
  | { type: "cancel"; epoch: number }
  | { type: "speak"; text: string; epoch: number }
  | { type: "stop_playback" }
  | { type: "shutdown" }

export type WorkerEvent =
  | { type: "ready" }
  | { type: "wake"; epoch: number }
  | { type: "partial" | "transcript"; text: string; epoch: number }
  | { type: "state"; state: string }
  | { type: "error"; message: string }

export function parseEvent(line: string): WorkerEvent {
  const value: unknown = JSON.parse(line)
  if (!value || typeof value !== "object" || !("type" in value)) throw new Error("Invalid audio event")
  const data = value as Record<string, unknown>
  if (data.type === "ready") return { type: "ready" }
  if (data.type === "state" && typeof data.state === "string") return { type: "state", state: data.state }
  if (data.type === "error" && typeof data.message === "string") return { type: "error", message: data.message }
  if (Number.isSafeInteger(data.epoch)) {
    const epoch = data.epoch as number
    if (data.type === "wake") return { type: "wake", epoch }
    if ((data.type === "partial" || data.type === "transcript") && typeof data.text === "string") {
      return { type: data.type, text: data.text, epoch }
    }
  }
  throw new Error("Unknown audio event")
}
