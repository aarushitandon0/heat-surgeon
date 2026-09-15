// Workspace layout helpers. No browser globals, so node tests can import them.

/** The data panel never gets narrower than this, so readout labels and values still fit side by side. */
export const PANEL_MIN_WIDTH_PX = 240
/** Nor wider than this, or this share of the window, whichever is smaller, so the viewport keeps most of the width. */
export const PANEL_MAX_WIDTH_PX = 720
export const PANEL_MAX_WINDOW_SHARE = 0.6
/** Arrow keys on the resize handle move it by this much. */
export const PANEL_KEY_STEP_PX = 16

/** The panel width to use for a requested width, given the window width. */
export function clampPanelWidth(requested_px: number, window_px: number): number {
  const max_px = Math.max(PANEL_MIN_WIDTH_PX, Math.min(PANEL_MAX_WIDTH_PX, Math.floor(window_px * PANEL_MAX_WINDOW_SHARE)))
  return Math.round(Math.min(max_px, Math.max(PANEL_MIN_WIDTH_PX, requested_px)))
}
