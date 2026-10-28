/** @jsxImportSource @opentui/solid */
import { Plugin } from "@opencode/plugin/tui"
import { createEffect, createSignal } from "solid-js"
import { VoiceController } from "./controller.ts"
import { defaults, type Settings } from "./protocol.ts"
import { AudioWorker } from "./worker.ts"

export default Plugin.define({
  id: "voice-assistant",
  setup(context) {
    const [settings, update] = context.storage.store<Settings>("preferences", { initial: { ...defaults } })
    const [status, setStatus] = createSignal("Loading speech")
    const [partial, setPartial] = createSignal("")
    const parts = new Map<string, string>()
    let disposed = false
    const error = (message: string) => {
      if (disposed) return
      setStatus(message)
      context.ui.toast.show({ title: "Voice assistant", message, variant: "error" })
    }
    const guard = (operation: () => void | Promise<void>) => {
      try {
        void Promise.resolve(operation()).catch((failure: unknown) => error(failure instanceof Error ? failure.message : "Voice operation failed"))
      } catch (failure) {
        error(failure instanceof Error ? failure.message : "Voice operation failed")
      }
    }
    const worker = new AudioWorker((event) => guard(() => controller.worker(event)), error)
    const controller = new VoiceController({
      send: (command) => worker.send(command),
      async submit(sessionID, text, id) {
        const model = context.ui.model.current()
        if (model) await context.client.session.switchModel({
          sessionID, model: { providerID: model.providerID, id: model.modelID, variant: model.variant },
        })
        await context.client.session.prompt({ sessionID, text, id })
      },
      async interrupt(sessionID) { await context.client.session.interrupt({ sessionID, resume: false }) },
      review: (value) => context.ui.dialog.prompt({ title: "Review spoken request", value, description: "Edit your transcript; Enter sends it to this OpenCode session. Esc discards it." }),
      status: setStatus,
      partial: setPartial,
      error,
    }, () => settings)

    createEffect(() => {
      const route = context.ui.router.current()
      const sessionID = route.type === "session" ? route.sessionID : undefined
      if (controller.session !== sessionID) parts.clear()
      controller.setSession(sessionID)
    })

    async function preferences(): Promise<void> {
      while (!disposed) {
        const selected = await context.ui.dialog.select({
          title: "Voice assistant settings",
          options: [
            { title: `Hands-free: ${settings.enabled ? "on" : "off"}`, value: "enabled", description: 'Wake phrase: “hey assistant”; works in the background.' },
            { title: `Submission: ${settings.submission === "automatic" ? "send after pause" : "review transcript"}`, value: "submission" },
            { title: `Read replies: ${settings.readout === "voice" ? "voice requests only" : "all active-session replies"}`, value: "readout" },
            { title: "Choose OpenCode model/provider", value: "model", description: "Opens OpenCode’s own model picker." },
            { title: "Close", value: "close" },
          ],
        })
        if (!selected || selected === "close") return
        if (selected === "model") {
          context.keymap.dispatch("model.list")
          return
        }
        await update((draft) => {
          if (selected === "enabled") draft.enabled = !draft.enabled
          if (selected === "submission") draft.submission = draft.submission === "automatic" ? "review" : "automatic"
          if (selected === "readout") draft.readout = draft.readout === "voice" ? "all" : "voice"
        })
        if (!settings.enabled) controller.stopPlayback()
        controller.configure()
      }
    }

    context.keymap.layer(() => ({
      mode: "global",
      commands: [
        {
          id: "voice.toggle", title: "Toggle hands-free voice", group: "Voice", palette: true, bind: false,
          slash: { name: "voice", arguments: true },
          run: (input) => guard(async () => {
            if (input?.trim() === "settings") return preferences()
            await update((draft) => { draft.enabled = input?.trim() === "on" ? true : input?.trim() === "off" ? false : !draft.enabled })
            if (!settings.enabled) controller.stopPlayback()
            controller.configure()
          }),
        },
        { id: "voice.settings", title: "Voice assistant settings", group: "Voice", palette: true, bind: false, slash: { name: "voice_settings" }, run: () => guard(preferences) },
        { id: "voice.listen", title: "Listen to a spoken request", group: "Voice", palette: true, bind: false, slash: { name: "voice_listen" }, run: () => controller.listen() },
        { id: "voice.stop", title: "Stop spoken playback", group: "Voice", palette: true, bind: false, slash: { name: "voice_stop" }, run: () => controller.stopPlayback() },
        { id: "voice.cancel", title: "Cancel current OpenCode task", group: "Voice", palette: true, bind: false, slash: { name: "voice_cancel" }, run: () => guard(async () => {
          controller.stopPlayback()
          if (controller.session) await context.client.session.interrupt({ sessionID: controller.session, resume: false })
        }) },
      ],
      bindings: ["voice.toggle", "voice.settings", "voice.listen", "voice.stop", "voice.cancel"],
    }))

    const unsubscribe = [
      context.data.on("session.inbox.delivered", (event) => controller.delivered(event.data.sessionID, event.data.inboxID)),
      context.data.on("session.text.delta", (event) => guard(() => {
        if (event.data.sessionID !== controller.session) return
        const key = `${event.data.assistantMessageID}:${event.data.ordinal}`
        parts.set(key, (parts.get(key) ?? "") + event.data.delta)
        controller.text(event.data.sessionID, key, event.data.delta)
      })),
      context.data.on("session.text.ended", (event) => guard(() => {
        const key = `${event.data.assistantMessageID}:${event.data.ordinal}`
        const received = parts.get(key) ?? ""
        const tail = event.data.text.startsWith(received) ? event.data.text.slice(received.length) : ""
        controller.text(event.data.sessionID, key, tail, true)
        parts.delete(key)
      })),
      ...(["session.execution.succeeded", "session.execution.failed", "session.execution.interrupted"] as const).map((type) =>
        context.data.on(type, (event) => guard(() => { controller.ended(event.data.sessionID); parts.clear() }))),
      context.ui.slot({ append: "prompt.footer.status", render: () =>
        <text fg={context.theme.text.muted} onMouseDown={() => guard(preferences)}>
          {`VOICE ${settings.enabled ? "ON" : "OFF"} · ${context.ui.router.current().type === "session" ? status() : "open a session"}`}
        </text> }),
      context.ui.slot({ append: "home.footer.status", render: () => <text fg={context.theme.text.muted}>Voice · open a session</text> }),
      context.ui.slot({ append: "session.composer.top", render: () => partial() ? <text fg={context.theme.text.muted}>{`Hearing: ${partial().slice(0, 200)}`}</text> : null }),
    ]

    return () => {
      disposed = true
      for (const stop of unsubscribe) stop()
      controller.dispose()
      worker.close()
      parts.clear()
    }
  },
})
