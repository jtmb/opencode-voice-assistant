/** Strip presentation syntax without sending code, URLs or reasoning to speech. */
export function spokenText(raw: string): string {
  return raw
    .replace(/```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)/g, " ")
    .replace(/`[^`]*(?:`|$)/g, " ")
    .replace(/<think>[\s\S]*?(?:<\/think>|$)/g, " ")
    .replace(/!?\[([^\]]*)\]\([^)]*(?:\)|$)/g, "$1")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/^\s*(?:#{1,6}\s+|[-*>]\s+|\d+\.\s+)/gm, "")
    .replace(/[*_~]/g, "")
    .replace(/\s+/g, " ")
    .trimStart()
}

export class Sentences {
  private raw = ""
  private consumed = 0

  push(delta: string, final = false): string[] {
    this.raw += delta
    if (this.raw.length > 262144) throw new Error("Speech text exceeded the per-part limit")
    const text = spokenText(this.raw)
    const remaining = text.slice(this.consumed)
    const result: string[] = []
    const expression = /[\s\S]*?[.!?](?:\s+|$)/g
    // A trailing full stop might be the first half of a decimal or abbreviation.
    for (const match of remaining.matchAll(expression)) {
      if (!final && match.index + match[0].length === remaining.length && !/\s$/.test(match[0])) break
      if (match[0].trim()) result.push(match[0].trim())
      this.consumed += match[0].length
    }
    if (final) {
      const tail = text.slice(this.consumed).trim()
      if (tail) result.push(tail)
      this.consumed = text.length
    }
    return result
  }
}
