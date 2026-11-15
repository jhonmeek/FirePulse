// Shared intensity scale: low counts are light, high counts are dark.
export const HEAT_STOPS: [number, [number, number, number]][] = [
  [0, [247, 239, 226]],
  [0.18, [236, 204, 162]],
  [0.42, [219, 122, 59]],
  [0.72, [163, 42, 25]],
  [1, [42, 6, 6]],
]

export function heatColor(value: number, max: number): string {
  const normalized = Math.sqrt(Math.max(0, Math.min(1, value / Math.max(1, max))))
  for (let i = 1; i < HEAT_STOPS.length; i++) {
    const [p1, c1] = HEAT_STOPS[i]!
    const [p0, c0] = HEAT_STOPS[i - 1]!
    if (normalized <= p1) {
      const ratio = (normalized - p0) / (p1 - p0)
      return `rgb(${c0.map((v, j) => Math.round(v + (c1[j]! - v) * ratio)).join(', ')})`
    }
  }
  return 'rgb(42, 6, 6)'
}

export const HEAT_GRADIENT = `linear-gradient(90deg, ${HEAT_STOPS.map(
  ([position, rgb]) => `rgb(${rgb.join(', ')}) ${position * 100}%`,
).join(', ')})`
