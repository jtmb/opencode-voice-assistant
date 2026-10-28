/** One-time native CLI configuration deployment; never starts a TUI or server. */
import { execFileSync } from "node:child_process"
import { constants } from "node:fs"
import { chmod, copyFile, lstat, mkdir, readFile, rename, unlink, writeFile } from "node:fs/promises"
import { dirname, join, resolve } from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import { parseArgs, isDeepStrictEqual } from "node:util"
import { randomUUID } from "node:crypto"
import { applyEdits, modify, parse, type ParseError } from "jsonc-parser"

export const root = fileURLToPath(new URL("../", import.meta.url))

export function configuration(text: string): Record<string, unknown> {
  const errors: ParseError[] = []
  const value: unknown = parse(text, errors, { allowTrailingComma: true })
  if (errors.length || !value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Invalid OpenCode CLI configuration")
  }
  return value as Record<string, unknown>
}

function packageName(entry: unknown): unknown {
  return typeof entry === "object" && entry !== null && "package" in entry ? entry.package : entry
}

export function registrationEdit(text: string, entry: string): string {
  const before = configuration(text)
  if (before.plugins !== undefined && !Array.isArray(before.plugins)) {
    throw new Error("OpenCode CLI plugins must be an array")
  }
  const plugins: unknown[] = before.plugins ?? []
  if (plugins.some((value) => packageName(value) === entry)) return text
  const updated = applyEdits(text, modify(text, before.plugins ? ["plugins", -1] : ["plugins"],
    before.plugins ? entry : [entry], {
      isArrayInsertion: true,
      formattingOptions: { tabSize: 2, insertSpaces: true },
    }))
  if (!isDeepStrictEqual(configuration(updated), { ...before, plugins: [...plugins, entry] })) {
    throw new Error("Registration would change unrelated configuration")
  }
  return updated
}

export type Registration = { target: string; original?: string; updated: string; mode: number }

async function readTarget(target: string): Promise<{ text?: string; mode: number }> {
  try {
    const info = await lstat(target)
    if (!info.isFile() || info.isSymbolicLink()) throw new Error("CLI configuration must be a regular file")
    return { text: await readFile(target, "utf8"), mode: info.mode & 0o777 }
  } catch (error) {
    if (error instanceof Error && "code" in error && error.code === "ENOENT") return { mode: 0o600 }
    throw error
  }
}

export async function prepareRegistration(target: string, entry: string): Promise<Registration> {
  const before = await readTarget(target)
  return { target, original: before.text, updated: registrationEdit(before.text ?? "{}\n", entry), mode: before.mode }
}

export async function applyRegistration(plan: Registration): Promise<string | undefined> {
  if (plan.original === plan.updated) return undefined
  const current = await readTarget(plan.target)
  if (current.text !== plan.original || current.mode !== plan.mode) {
    throw new Error("CLI configuration changed after preview; prepare registration again")
  }
  await mkdir(dirname(plan.target), { recursive: true })
  const stamp = `${new Date().toISOString().replaceAll(":", "-")}-${randomUUID()}`
  const backup = plan.original === undefined ? undefined : `${plan.target}.backup-voice-${stamp}`
  if (backup) {
    await copyFile(plan.target, backup, constants.COPYFILE_EXCL)
    await chmod(backup, plan.mode)
  }
  const temporary = `${plan.target}.voice-${randomUUID()}.tmp`
  try {
    await writeFile(temporary, plan.updated, { mode: plan.mode, flag: "wx" })
    const latest = await readTarget(plan.target)
    if (latest.text !== plan.original || latest.mode !== plan.mode) {
      throw new Error("CLI configuration changed during deployment; no replacement made")
    }
    await rename(temporary, plan.target)
    if (await readFile(plan.target, "utf8") !== plan.updated) throw new Error("CLI registration readback failed")
  } finally {
    await unlink(temporary).catch((error: unknown) => {
      if (!(error instanceof Error && "code" in error && error.code === "ENOENT")) throw error
    })
  }
  return backup
}

async function main(): Promise<void> {
  const { values } = parseArgs({ options: {
    apply: { type: "boolean", default: false },
    "config-dir": { type: "string" },
    source: { type: "string" },
  } })
  if (values.source) {
    const source = configuration(await readFile(resolve(values.source), "utf8"))
    if (!Array.isArray(source.plugins) || !source.plugins.some((entry) => packageName(entry) === root.replace(/\/$/, ""))) {
      throw new Error("Canonical CLI source does not register this plugin directory")
    }
  }
  const paths = values["config-dir"] ? undefined : execFileSync("opencode", ["debug", "paths"], { encoding: "utf8" })
  const directory = values["config-dir"] ?? paths?.split("\n").find((line) => /^config\s/.test(line))?.replace(/^config\s+/, "").trim()
  if (!directory || resolve(directory) === "/") throw new Error("Cannot determine a safe OpenCode config directory")
  const info = await lstat(directory).catch((error: unknown) => {
    if (error instanceof Error && "code" in error && error.code === "ENOENT") return undefined
    throw error
  })
  if (info && (!info.isDirectory() || info.isSymbolicLink())) throw new Error("Config directory must be a regular directory")
  const entry = root.replace(/\/$/, "")
  const plan = await prepareRegistration(join(resolve(directory), "cli.json"), entry)
  process.stdout.write(`target=${plan.target}\nplugin=${entry}\n`)
  if (plan.original === plan.updated) {
    process.stdout.write("Already registered; no changes.\n")
    return
  }
  if (!values.apply) {
    process.stdout.write("Preview: append this plugin only. Rerun with --apply to deploy.\n")
    return
  }
  const backup = await applyRegistration(plan)
  if (backup) process.stdout.write(`backup=${backup}\n`)
  process.stdout.write("Registered in native CLI configuration. Start OpenCode normally with opencode.\n")
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await main()
}
