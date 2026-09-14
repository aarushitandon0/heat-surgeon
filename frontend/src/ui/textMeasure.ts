// Text widths for label placement, measured with the same font the labels are drawn in.

import type { Measure } from '../lib/labels.ts'

let scratch: CanvasRenderingContext2D | null = null

export function measurer(font: string): Measure {
  scratch ??= document.createElement('canvas').getContext('2d')
  const ctx = scratch!
  return (text) => {
    ctx.font = font
    return ctx.measureText(text).width
  }
}
