import { readFileSync } from "node:fs"
import { parse } from "jsonc-parser"

const errors = []
const value = parse(readFileSync(0, "utf8"), errors, { allowTrailingComma: true })
if (errors.length || !value || typeof value !== "object" || Array.isArray(value)) {
  throw new Error("Invalid OpenCode CLI configuration")
}
process.stdout.write(JSON.stringify(value))
