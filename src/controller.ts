import { randomUUID } from "node:crypto"
import type { Settings, WorkerCommand, WorkerEvent } from "./protocol.ts"
import { Sentences } from "./sentences.ts"

export interface Host {
  send(command: WorkerCommand): void
  submit(sessionID: string, text: string, id: string): Promise<void>
  interrupt(sessionID: string): Promise<void>
  review(text: string): Promise<string | undefined>
  status(text: string): void
  partial(text: string): void
  error(message: string): void
}

/** Routes voice I/O; conversation and execution remain entirely in OpenCode. */
export class VoiceController {
  epoch = 0
  session: string | undefined
  private settings: () => Settings
  private host: Host
  private voiceInputs = new Set<string>()
  private voiceTurn = false
  private suppressed = false
  private streams = new Map<string, Sentences>()
  private blocked = new Set<string>()
  private disposed = false
  private active = false

  constructor(host: Host, settings: () => Settings) {
    this.host = host
    this.settings = settings
  }

  setSession(sessionID: string | undefined): void {
    if (sessionID === this.session) return
    this.session = sessionID
    this.epoch++
    this.voiceTurn = false
    this.voiceInputs.clear()
    this.streams.clear()
    this.blocked.clear()
    this.host.send({ type: "cancel", epoch: this.epoch })
    this.host.partial("")
    this.configure()
  }

  configure(): void {
    const enabled = this.settings().enabled && !!this.session
    if (this.active && !enabled) {
      this.epoch++
      this.host.send({ type: "cancel", epoch: this.epoch })
      this.host.partial("")
    }
    this.active = enabled
    this.host.send({ type: "configure", enabled, epoch: this.epoch })
  }

  listen(): void {
    if (!this.session) return this.host.error("Open an OpenCode session before using voice.")
    this.host.send({ type: "listen", epoch: this.epoch })
  }

  stopPlayback(): void {
    this.suppressed = true
    for (const key of this.streams.keys()) this.blocked.add(key)
    this.host.send({ type: "stop_playback" })
  }

  async worker(event: WorkerEvent): Promise<void> {
    if (this.disposed) return
    if (event.type === "ready") return this.configure()
    if (event.type === "error") return this.host.error(event.message)
    if (event.type === "state") return this.host.status(event.state)
    if (event.epoch !== this.epoch || !this.session) return
    if (event.type === "wake") {
      this.stopPlayback()
      return this.host.status("Listening")
    }
    if (event.type === "partial") return this.host.partial(event.text)
    const epoch = this.epoch
    const session = this.session
    let text = event.text.trim()
    this.host.partial("")
    if (!text) return
    if (/^(?:please )?cancel (?:the )?task[.!?]?$/i.test(text)) {
      this.stopPlayback()
      await this.host.interrupt(session)
      return
    }
    if (/^(?:please )?stop speaking[.!?]?$/i.test(text)) return this.stopPlayback()
    if (this.settings().submission === "review") text = (await this.host.review(text))?.trim() ?? ""
    if (!text || this.disposed || epoch !== this.epoch || session !== this.session) return
    const id = "msg_" + randomUUID().replaceAll("-", "")
    this.voiceInputs.add(id)
    this.voiceTurn = true
    this.suppressed = false
    try {
      await this.host.submit(session, text, id)
      if (epoch === this.epoch) this.host.status("Waiting for OpenCode")
    } catch (error) {
      this.voiceInputs.delete(id)
      this.voiceTurn = false
      throw error
    }
  }

  delivered(sessionID: string, id: string): void {
    if (sessionID !== this.session) return
    this.voiceTurn = this.voiceInputs.delete(id)
    this.suppressed = false
  }

  text(sessionID: string, key: string, delta: string, final = false): void {
    if (this.disposed || sessionID !== this.session || this.blocked.has(key) || this.suppressed) return
    if (this.settings().readout === "voice" && !this.voiceTurn) return
    let stream = this.streams.get(key)
    if (!stream) {
      stream = new Sentences()
      this.streams.set(key, stream)
    }
    for (const sentence of stream.push(delta, final)) {
      this.host.send({ type: "speak", text: sentence, epoch: this.epoch })
    }
    if (final) this.streams.delete(key)
  }

  ended(sessionID: string): void {
    if (sessionID !== this.session) return
    for (const [key] of this.streams) this.text(sessionID, key, "", true)
    this.voiceTurn = false
    this.suppressed = false
    this.blocked.clear()
  }

  dispose(): void {
    this.disposed = true
    this.epoch++
    this.streams.clear()
    this.voiceInputs.clear()
    this.host.send({ type: "shutdown" })
  }
}
