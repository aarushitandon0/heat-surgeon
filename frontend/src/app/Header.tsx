import { STAGES, stageAvailable, useStore } from '../store/store.ts'

export function Header() {
  const state = useStore()

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
        {state.job.socketOpen ? (
          <>
            <span className="status-dot" aria-hidden="true" />
            live
          </>
        ) : (
          (state.street?.name ?? 'No street selected')
        )}
      </p>
    </header>
  )
}
