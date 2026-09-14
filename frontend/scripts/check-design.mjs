// Mechanical checks for the design rules in CLAUDE.md and SPEC.md §9. Run: npm run check:design
// Covers what a grep can prove. Mono-on-labels and sentence case still need a human eye.

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const SRC = fileURLToPath(new URL('../src/', import.meta.url))
const TOKENS = 'styles/tokens.css'
// The thermal ramp may only be read by the legend and by the canvas colour reader for data grids.
const RAMP_ALLOWED = new Set([TOKENS, 'ui/ThermalScale.css', 'ui/tokens.ts'])

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? walk(path) : /\.(tsx?|css)$/.test(name) ? [path] : []
  })
}

const violations = []
let signalUses = 0

for (const path of walk(SRC)) {
  const file = relative(SRC, path).replaceAll('\\', '/')
  const lines = readFileSync(path, 'utf8').split('\n')
  const isCss = file.endsWith('.css')
  lines.forEach((line, i) => {
    const at = `src/${file}:${i + 1}`
    const flag = (rule) => violations.push(`${at}  ${rule}\n    ${line.trim()}`)

    if (file !== TOKENS && /#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?(?:[0-9a-fA-F]{2})?\b/.test(line)) flag('hex colour outside tokens.css')
    if (!RAMP_ALLOWED.has(file) && /--t-(00|25|50|75|100)\b/.test(line)) flag('thermal ramp token outside the data legend and canvas reader')
    if (file !== TOKENS) signalUses += (line.match(/var\(--signal\)/g) ?? []).length
    if (/\p{Extended_Pictographic}/u.test(line)) flag('emoji')
    if (/[←-⇿⟰-⟿⤀-⥿]/.test(line)) flag('arrow character')
    if (/·|&middot;/.test(line)) flag('middle dot')
    if (/text-transform\s*:\s*uppercase/i.test(line)) flag('all-caps text transform')
    if (isCss && /@keyframes|(^|[\s;{])(transition|animation)(-[a-z]+)?\s*:/.test(line)) flag('CSS motion: only the decode and the reveal move, both in components')
    if (isCss && /:hover/.test(line)) flag('hover style')
    if (isCss && /box-shadow|backdrop-filter/.test(line)) flag('shadow or glass effect')
  })
}

if (signalUses !== 1) violations.push(`var(--signal) is used ${signalUses} times; it must be used exactly once, on the delta readout`)

if (violations.length > 0) {
  console.error(`Design check failed:\n\n${violations.join('\n')}`)
  process.exit(1)
}
console.log('Design check passed.')
