import { test } from "node:test"
import assert from "node:assert/strict"
import { mkdtemp, mkdir, readFile, writeFile, stat, rm, symlink } from "node:fs/promises"
import { join } from "node:path"
import { configuration, registrationEdit, prepareRegistration, applyRegistration, root } from "../scripts/register.ts"

test("registration preserves comments, options, directives and non-plugin preferences", () => {
  const text = '{\n // keep this\n "theme":{"mode":"dark"},\n "plugins":["first", /* keep inline */ {"package":"second","options":{"scope":"selected"}}, "-third",],\n}\n'
  const updated = registrationEdit(text, "/repo/voice")
  assert.ok(updated.includes("// keep this"))
  assert.ok(updated.includes("/* keep inline */"))
  assert.deepEqual(configuration(updated), {
    theme: { mode: "dark" }, plugins: ["first", { package: "second", options: { scope: "selected" } }, "-third", "/repo/voice"],
  })
  assert.equal(registrationEdit(updated, "/repo/voice"), updated)
})

test("existing object registrations are not duplicated; invalid input is refused", () => {
  const existing = '{"plugins":[{"package":"/voice","options":{"keep":true}}]}'
  assert.equal(registrationEdit(existing, "/voice"), existing)
  assert.deepEqual(configuration(registrationEdit('{"mouse":false}', "/voice")), { mouse: false, plugins: ["/voice"] })
  assert.throws(() => registrationEdit('{"plugins":"bad"}', "/voice"), /array/)
  assert.throws(() => registrationEdit('{bad}', "/voice"), /Invalid/)
  assert.throws(() => configuration('[]'), /Invalid/)
})

test("deployment is previewable, backed up, permission-preserving and idempotent", async (t) => {
  await mkdir(join(root, "state"), { recursive: true })
  const directory = await mkdtemp(join(root, "state/registration-"))
  t.after(() => rm(directory, { recursive: true, force: true }))
  const target = join(directory, "cli.json")
  const original = '{"plugins":["keep"],"mouse":false}\n'
  await writeFile(target, original, { mode: 0o600 })
  const plan = await prepareRegistration(target, "/voice")
  assert.equal(await readFile(target, "utf8"), original)
  const backup = await applyRegistration(plan)
  assert.ok(backup)
  assert.equal(await readFile(backup, "utf8"), original)
  assert.equal((await stat(target)).mode & 0o777, 0o600)
  assert.equal((await stat(backup)).mode & 0o777, 0o600)
  assert.deepEqual(configuration(await readFile(target, "utf8")), { plugins: ["keep", "/voice"], mouse: false })
  assert.equal(await applyRegistration(await prepareRegistration(target, "/voice")), undefined)
})

test("concurrent edits and symlink targets cannot be overwritten", async (t) => {
  await mkdir(join(root, "state"), { recursive: true })
  const directory = await mkdtemp(join(root, "state/registration-"))
  t.after(() => rm(directory, { recursive: true, force: true }))
  const target = join(directory, "cli.json")
  await writeFile(target, '{}\n')
  const plan = await prepareRegistration(target, "/voice")
  await writeFile(target, '{"mouse":false}\n')
  await assert.rejects(applyRegistration(plan), /changed after preview/)
  assert.equal(await readFile(target, "utf8"), '{"mouse":false}\n')
  const link = join(directory, "linked.json")
  await symlink(target, link)
  await assert.rejects(prepareRegistration(link, "/voice"), /regular file/)
})

test("first registration creates a private native CLI configuration", async (t) => {
  await mkdir(join(root, "state"), { recursive: true })
  const directory = await mkdtemp(join(root, "state/registration-"))
  t.after(() => rm(directory, { recursive: true, force: true }))
  const target = join(directory, "new/cli.json")
  assert.equal(await applyRegistration(await prepareRegistration(target, "/voice")), undefined)
  assert.deepEqual(configuration(await readFile(target, "utf8")), { plugins: ["/voice"] })
  assert.equal((await stat(target)).mode & 0o777, 0o600)
})
