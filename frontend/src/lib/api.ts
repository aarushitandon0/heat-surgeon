// Where the app's data comes from (SPEC.md §7). Two sources share one shape:
// - live: the backend, through the Vite proxy for /api and /ws.
// - replay: responses the same API returned, recorded by `python -m app.snapshot` (see lib/replay.ts).
// Errors carry the backend's own detail string; nothing here substitutes data.

import type {
  CalibrationRequest,
  CalibrationResult,
  OptimizationResult,
  OptimizeJobHandle,
  OptimizeMessage,
  OptimizeRequest,
  StreetBasemap,
  StreetGeometry,
  StreetSummary,
  ThermalGrid,
} from '../types/contracts.ts'
import {
  manifestUrl,
  replayDelaysMs,
  requestMatches,
  snapshotUrl,
  streetsUrl,
  type SnapshotFile,
  type SnapshotManifest,
  type StreamEntry,
} from './replay.ts'

export const BACKEND_UNREACHABLE =
  'The backend did not respond. Start it with: cd backend && uvicorn app.main:app --reload --port 8000'

export class ApiError extends Error {
  /** True when nothing answered, as opposed to the backend answering with an error. */
  readonly unreachable: boolean
  constructor(message: string, unreachable = false) {
    super(message)
    this.unreachable = unreachable
  }
}

function detailMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // pydantic validation errors: [{ loc: [...], msg }]
    return detail
      .map((item: { loc?: unknown[]; msg?: string }) => `${(item.loc ?? []).slice(1).join('.')}: ${item.msg ?? ''}`)
      .join('; ')
  }
  return `The backend answered ${status} with no explanation.`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch {
    throw new ApiError(BACKEND_UNREACHABLE, true)
  }
  const text = await response.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = null
  }
  if (!response.ok) {
    // The dev proxy answers with an empty or non-JSON body when the backend is down.
    if (body === null) throw new ApiError(BACKEND_UNREACHABLE, true)
    throw new ApiError(detailMessage(body, response.status))
  }
  return body as T
}

function postJson<T>(path: string, payload: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) })
}

export interface StreamHandlers {
  onOpen: () => void
  onMessage: (message: OptimizeMessage) => void
  onClose: () => void
}

export interface DataSource {
  kind: 'live' | 'replay'
  streets: () => Promise<StreetSummary[]>
  geometry: (streetId: string) => Promise<StreetGeometry>
  basemap: (streetId: string) => Promise<StreetBasemap>
  thermal: (streetId: string, scope: 'street' | 'window') => Promise<ThermalGrid>
  calibrate: (streetId: string, body: CalibrationRequest) => Promise<CalibrationResult>
  optimize: (streetId: string, body: OptimizeRequest) => Promise<OptimizeJobHandle>
  /** Starts delivering the search's messages; returns a function that stops delivery. */
  stream: (streetId: string, handle: OptimizeJobHandle, handlers: StreamHandlers) => () => void
  result: (resultUrl: string) => Promise<OptimizationResult>
}

export function websocketUrl(path: string): string {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}${path}`
}

export const liveSource: DataSource = {
  kind: 'live',
  streets: () => request<StreetSummary[]>('/api/streets'),
  geometry: (streetId) => request<StreetGeometry>(`/api/street/${encodeURIComponent(streetId)}/geometry`),
  basemap: (streetId) => request<StreetBasemap>(`/api/street/${encodeURIComponent(streetId)}/basemap`),
  thermal: (streetId, scope) => request<ThermalGrid>(`/api/street/${encodeURIComponent(streetId)}/thermal?scope=${scope}`),
  calibrate: (streetId, body) => postJson<CalibrationResult>(`/api/street/${encodeURIComponent(streetId)}/calibrate`, body),
  optimize: (streetId, body) => postJson<OptimizeJobHandle>(`/api/street/${encodeURIComponent(streetId)}/optimize`, body),
  stream: (_streetId, handle, handlers) => {
    const ws = new WebSocket(websocketUrl(handle.ws_url))
    ws.onopen = () => handlers.onOpen()
    ws.onmessage = (event: MessageEvent<string>) => handlers.onMessage(JSON.parse(event.data) as OptimizeMessage)
    ws.onclose = () => handlers.onClose()
    return () => {
      ws.onopen = ws.onmessage = ws.onclose = ws.onerror = null
      ws.close()
    }
  },
  result: (resultUrl) => request<OptimizationResult>(resultUrl),
}

/** A recorded file, or a plain statement that the recording does not have it. */
async function recorded<T>(url: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(url)
  } catch {
    throw new ApiError(`The recording could not be read from ${url}.`)
  }
  if (!response.ok) throw new ApiError(`The recording has no file at ${url}.`)
  try {
    return (await response.json()) as T
  } catch {
    throw new ApiError(`The recording at ${url} is not readable JSON.`)
  }
}

export function loadManifest(base: string): Promise<SnapshotManifest> {
  return recorded<SnapshotManifest>(manifestUrl(base))
}

/** Serves only what was recorded. A request the recording cannot answer is refused, never approximated. */
export function replaySource(base: string, manifest: SnapshotManifest): DataSource {
  const has = new Set(manifest.streets.map((s) => s.id))
  const file = <T>(streetId: string, name: SnapshotFile): Promise<T> => {
    if (!has.has(streetId)) return Promise.reject(new ApiError('This recording does not include that street.'))
    return recorded<T>(snapshotUrl(base, streetId, name))
  }
  return {
    kind: 'replay',
    streets: () => recorded<StreetSummary[]>(streetsUrl(base)),
    geometry: (streetId) => file(streetId, 'geometry'),
    basemap: (streetId) => file(streetId, 'basemap'),
    thermal: (streetId, scope) => file(streetId, scope === 'window' ? 'thermal-window' : 'thermal-street'),
    calibrate: (streetId, body) => {
      const r = manifest.calibration_request
      if (body.holdout_fraction !== r.holdout_fraction || body.seed !== r.seed) {
        return Promise.reject(new ApiError('This recording holds only the calibration with its recorded settings.'))
      }
      return file(streetId, 'calibration')
    },
    optimize: (streetId, body) => {
      if (!requestMatches(manifest.optimize_request, body)) {
        return Promise.reject(new ApiError('This recording holds only the search with its recorded settings.'))
      }
      return file(streetId, 'optimize-handle')
    },
    stream: (streetId, handle, handlers) => {
      let stopped = false
      const timers: number[] = []
      file<StreamEntry[]>(streetId, 'stream').then(
        (entries) => {
          if (stopped) return
          handlers.onOpen()
          const delays_ms = replayDelaysMs(entries)
          entries.forEach((entry, i) => {
            timers.push(
              window.setTimeout(() => {
                if (stopped) return
                // The recorded result_url points at the backend's job store; the recorded result file is its replay.
                const message: OptimizeMessage =
                  entry.message.type === 'done' ? { ...entry.message, result_url: snapshotUrl(base, streetId, 'result') } : entry.message
                handlers.onMessage(message)
                if (i === entries.length - 1) handlers.onClose()
              }, delays_ms[i]),
            )
          })
        },
        (error: unknown) => {
          if (stopped) return
          handlers.onMessage({ type: 'error', job_id: handle.job_id, code: 'replay_missing', message: messageOf(error) })
          handlers.onClose()
        },
      )
      return () => {
        stopped = true
        timers.forEach((t) => window.clearTimeout(t))
      }
    },
    result: (resultUrl) => recorded<OptimizationResult>(resultUrl),
  }
}

export function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
