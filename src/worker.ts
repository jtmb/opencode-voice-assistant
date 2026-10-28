import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process"
import { createInterface } from "node:readline"
import { fileURLToPath } from "node:url"
import { join } from "node:path"
import { parseEvent, type WorkerCommand, type WorkerEvent } from "./protocol.ts"

export const root = fileURLToPath(new URL("../", import.meta.url))

export class AudioWorker {
  private process: ChildProcessWithoutNullStreams | undefined
  private pending: WorkerCommand[] = []
  private ready = false
  private closed = false

  constructor(onEvent: (event: WorkerEvent) => void, onError: (message: string) => void) {
    const child = spawn(join(root, "scripts/audio-worker.sh"), [], { cwd: root, stdio: "pipe" })
    this.process = child
    child.on("error", () => onError("Audio worker could not start. Run ./setup.sh in the plugin folder."))
    const lines = createInterface({ input: child.stdout })
    lines.on("line", (line) => {
      try {
        const event = parseEvent(line)
        if (event.type === "ready") {
          this.ready = true
          for (const command of this.pending.splice(0)) this.send(command)
        }
        onEvent(event)
      } catch {
        onError("The audio worker sent an invalid protocol event.")
      }
    })
    // Do not forward native-library diagnostics, which can contain audio internals.
    child.stderr.resume()
    child.on("exit", (code) => {
      this.ready = false
      lines.close()
      if (!this.closed) onError(`Audio worker stopped (${code ?? "signal"}). Run ./setup.sh or check audio devices.`)
    })
  }

  send(command: WorkerCommand): void {
    if (this.closed || !this.process?.stdin.writable) return
    if (command.type === "shutdown") return this.close()
    if (!this.ready) {
      // Retain only the latest session configuration while models load.
      if (command.type === "configure" || command.type === "cancel") {
        this.pending = this.pending.filter((entry) => entry.type !== command.type)
      }
      if (this.pending.length < 32) this.pending.push(command)
      return
    }
    this.process.stdin.write(JSON.stringify(command) + "\n")
  }

  close(): void {
    if (this.closed) return
    this.closed = true
    this.pending = []
    const child = this.process
    if (!child) return
    child.stdin.end(JSON.stringify({ type: "shutdown" }) + "\n")
    const timer = setTimeout(() => { if (child.exitCode === null) child.kill("SIGTERM") }, 2000)
    timer.unref()
    child.once("exit", () => clearTimeout(timer))
  }
}
