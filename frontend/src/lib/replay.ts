// Replay of recorded API responses (backend/app/snapshot.py). Used when the backend cannot be reached, or when the
// page is opened with ?replay. Every file is a response the API really returned from the cached fixtures; the
// interface says it is a recording and when it was made. No Vite globals here, so node tests can import it.

import type { CalibrationRequest, OptimizeMessage, OptimizeRequest } from '../types/contracts.ts'

export const REPLAY_QUERY_PARAM = 'replay'

export interface SnapshotStreet {
  id: string
  search_s: number
  messages: number
  size_bytes: number
}

/** Written by `python -m app.snapshot`. A file format, not an API contract. */
export interface SnapshotManifest {
  format_version: number
  recorded_at: string
  git_commit: string | null
  source_adapter: string
  calibration_request: CalibrationRequest
  optimize_request: OptimizeRequest
  streets: SnapshotStreet[]
}

/** One optimizer message and when it arrived, in seconds after the search was started. */
export interface StreamEntry {
  elapsed_s: number
  message: OptimizeMessage
}

export type SnapshotFile =
  | 'geometry'
  | 'basemap'
  | 'thermal-window'
  | 'thermal-street'
  | 'calibration'
  | 'optimize-handle'
  | 'stream'
  | 'result'

/** `base` is the app's base URL, ending in a slash. */
export function snapshotUrl(base: string, streetId: string, file: SnapshotFile): string {
  return `${base}snapshot/${encodeURIComponent(streetId)}/${file}.json`
}

export function manifestUrl(base: string): string {
  return `${base}snapshot/manifest.json`
}

export function rankingUrl(base: string): string {
  return `${base}snapshot/ranking.json`
}

export function streetsUrl(base: string): string {
  return `${base}snapshot/streets.json`
}

/** Delay before each message from the start of the replayed search, at `speed` times the recorded pace. */
export function replayDelaysMs(entries: StreamEntry[], speed = 1): number[] {
  if (!(speed > 0)) throw new RangeError('Replay speed must be positive.')
  return entries.map((entry) => (Math.max(0, entry.elapsed_s) * 1000) / speed)
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "15 Sep 2026", in UTC, from an ISO timestamp. Built by hand so every runtime prints the same string. */
export function formatRecordedDate(iso: string): string {
  const date = new Date(iso)
  return `${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]} ${date.getUTCFullYear()}`
}

/** Replay without trying the backend: a replay-only build, or ?replay in the address. */
export function replayForced(search: string, replayOnlyBuild: boolean): boolean {
  return replayOnlyBuild || new URLSearchParams(search).has(REPLAY_QUERY_PARAM)
}

/** True when a recorded optimize request matches the one the user would send, so the recording answers it. */
export function requestMatches(recorded: OptimizeRequest, wanted: OptimizeRequest): boolean {
  const keys = Object.keys(recorded) as (keyof OptimizeRequest)[]
  return keys.length === Object.keys(wanted).length && keys.every((key) => recorded[key] === wanted[key])
}
