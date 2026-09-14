import { formatRecordedDate } from '../lib/replay.ts'
import { STAGES, stageAvailable, useStore, type DataMode } from '../store/store.ts'

/** Says, on every stage, that the data on screen is a recording and when it was made. */
function ReplayNotice({ mode }: { mode: Extract<DataMode, { kind: 'replay' }> }) {
  const date = <span className="mono">{formatRecordedDate(mode.manifest.recorded_at)}</span>
  return (
    <p className="replay-notice" role="status">
      {mode.reason === 'backend_unreachable' ? 'The backend is not reachable, so this is a recording' : 'This is a recording'} of
      real runs made on {date} from the cached satellite and map data. Searches replay at the recorded pace with the
      recorded settings.
      {mode.reason === 'backend_unreachable' && ' Start the backend and reload to search live.'}
    </p>
  )
}

export function Header() {
  const state = useStore()
  const replaying = state.dataMode.kind === 'replay'

  return (
    <header className="header">
      <h1 className="brand">Heat Surgeon</h1>
      <nav aria-label="Pipeline stages">
        <ol className="stages">
          {STAGES.map((stage) => (
            <li key={stage.id}>
              <button
                className="stage"
                type="button"
                aria-current={stage.id === state.stage ? 'step' : undefined}
                disabled={!stageAvailable(state, stage.id)}
                onClick={() => state.goTo(stage.id)}
              >
                {stage.number} / {stage.name}
              </button>
            </li>
          ))}
        </ol>
      </nav>
      <p className="link-status" aria-live="polite">
        {state.job.socketOpen && !replaying ? (
          <>
            <span className="status-dot" aria-hidden="true" />
            live
          </>
        ) : state.job.socketOpen ? (
          'replaying'
        ) : (
          (state.street?.name ?? 'No street selected')
        )}
      </p>
      {state.dataMode.kind === 'replay' && <ReplayNotice mode={state.dataMode} />}
    </header>
  )
}
