import { useRef, type KeyboardEvent, type PointerEvent } from 'react'
import { PANEL_KEY_STEP_PX, PANEL_MAX_WIDTH_PX, PANEL_MIN_WIDTH_PX, clampPanelWidth } from '../lib/layout.ts'
import { useStore } from '../store/store.ts'

/** Default panel width in pixels, matching --panel-width (22.5rem) at the root font size, for the ARIA value only. */
const DEFAULT_PANEL_WIDTH_PX = 360

/**
 * The line between the data panel and the viewport. Drag it to resize the panel, or focus it and use the left and
 * right arrow keys. The width is kept in the store for the session. Chrome, not data; no animation.
 */
export function PanelResizer() {
  const width_px = useStore((s) => s.panelWidth_px)
  const setPanelWidth = useStore((s) => s.setPanelWidth)
  const dragging = useRef(false)

  const widthAt = (event: PointerEvent<HTMLDivElement>) => {
    const workspaceLeft_px = event.currentTarget.parentElement?.getBoundingClientRect().left ?? 0
    return clampPanelWidth(event.clientX - workspaceLeft_px, window.innerWidth)
  }

  return (
    <div
      className="panel-resizer"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the data panel"
      aria-valuemin={PANEL_MIN_WIDTH_PX}
      aria-valuemax={PANEL_MAX_WIDTH_PX}
      aria-valuenow={width_px ?? DEFAULT_PANEL_WIDTH_PX}
      tabIndex={0}
      onPointerDown={(event) => {
        event.preventDefault()
        event.currentTarget.setPointerCapture(event.pointerId)
        event.currentTarget.dataset.dragging = 'true'
        dragging.current = true
      }}
      onPointerMove={(event) => {
        if (dragging.current) setPanelWidth(widthAt(event))
      }}
      onPointerUp={(event) => {
        dragging.current = false
        delete event.currentTarget.dataset.dragging
        if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
      }}
      onPointerCancel={(event) => {
        dragging.current = false
        delete event.currentTarget.dataset.dragging
      }}
      onKeyDown={(event: KeyboardEvent<HTMLDivElement>) => {
        const step_px = event.key === 'ArrowLeft' ? -PANEL_KEY_STEP_PX : event.key === 'ArrowRight' ? PANEL_KEY_STEP_PX : 0
        if (step_px === 0) return
        event.preventDefault()
        setPanelWidth(clampPanelWidth((width_px ?? DEFAULT_PANEL_WIDTH_PX) + step_px, window.innerWidth))
      }}
    />
  )
}
