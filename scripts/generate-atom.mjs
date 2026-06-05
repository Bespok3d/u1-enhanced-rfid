// Emit one plugin's index atom (a single catalog entry) for the federated registry. Same entry
// shape the monorepo's generate-index.mjs produces, plus the raw `require` so a list assembler can
// resolve cross-plugin `deps`. download_url/doc_url are absolute (this is a published list): the
// download_url is the GitHub release asset API URL, injected by CI.
//
// Usage: node scripts/generate-atom.mjs --plugin <plugin-id> [--download-url <url>] [--repo owner/repo]
// Writes dist/<plugin-id>.atom.json. Without --download-url it falls back to the local .b3 filename
// (a dry-run inspectable atom, not for publishing).

import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

function serviceName(provided) {
  return typeof provided === 'string' ? provided : provided.service
}

function copyIfPresent(target, source, keys) {
  keys.forEach((key) => {
    if (source[key] !== undefined) target[key] = source[key]
  })
}

export function buildAtom(manifest, downloadUrl, docUrl) {
  const entry = {
    name: manifest.name,
    title: manifest.title,
    version: manifest.version,
    description: manifest.description,
    tagline: manifest.tagline,
    category: manifest.category,
    channel: manifest.channel,
    publisher: manifest.publisher,
    printer_specific: manifest.printer_specific ?? false,
    published_at: manifest.published_at,
    updated_at: manifest.updated_at,
    requires: { capabilities: manifest.requires?.capabilities ?? [] },
    provides: (manifest.provides ?? []).map(serviceName),
    require: manifest.require ?? [],
    conflicts: manifest.conflicts ?? [],
    doc_url: docUrl,
    download_url: downloadUrl,
  }
  copyIfPresent(entry, manifest, ['icon', 'min_daemon_version', 'homepage', 'macros', 'config'])
  if (manifest.changelog) entry.changelog_url = `${manifest.name}/${manifest.changelog}`
  const endpoints = manifest.endpoints ?? []
  if (endpoints.length > 0) entry.endpoints = endpoints
  return entry
}

function arg(flag, fallback) {
  const index = process.argv.indexOf(flag)
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback
}

async function main() {
  const scriptDir = dirname(fileURLToPath(import.meta.url))
  const repoDir = dirname(scriptDir)
  const pluginId = arg('--plugin', undefined)
  if (!pluginId) throw new Error('missing required --plugin <plugin-id>')
  const manifest = JSON.parse(await readFile(join(repoDir, pluginId, 'manifest.json'), 'utf8'))
  const repo = arg('--repo', 'Bespok3d/u1-enhanced-rfid')
  const downloadUrl = arg('--download-url', `${manifest.name}-${manifest.version}.b3`)
  const docUrl = arg('--doc-url', `https://github.com/${repo}/blob/main/${pluginId}/doc/README.md`)
  const atom = buildAtom(manifest, downloadUrl, docUrl)
  const outDir = join(repoDir, 'dist')
  await mkdir(outDir, { recursive: true })
  const outFile = join(outDir, `${manifest.name}.atom.json`)
  await writeFile(outFile, `${JSON.stringify(atom, null, 2)}\n`)
  process.stdout.write(`Wrote ${outFile} (download_url=${downloadUrl})\n`)
}

if (process.argv[1] && process.argv[1].endsWith('generate-atom.mjs')) {
  main().catch((error) => {
    process.stderr.write(`generate-atom failed: ${error.message}\n`)
    process.exit(1)
  })
}
