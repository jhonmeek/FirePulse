import predictionJson from '@/data/prediction.json'

export interface PredictionCell {
  id: string
  lat: number
  lon: number
  province: string
  provinceName: string
  forest: number
  cropland: number
  builtup: number
}

/** [cellIndex, probability, baseProbability, positiveYears, observedYears] */
export type PredictionValue = [number, number, number, number, number]

/** [cellIndex, annualProbability, expectedFireMonths, peakMonth] */
export type PredictionAnnualValue = [number, number, number, number]

export interface PredictionProvinceRow {
  code: string
  name: string
  year: number
  month: number
  meanProbability: number
  highRiskShare: number
  expectedFireCellsMonth: number
  meanAnnualProbability: number
  highAnnualRiskShare: number
  expectedFireCellsYear: number
  expectedFireMonths: number
  cells: number
}

export interface PredictionMetrics {
  protocol: {
    train: string
    test: string
    target: string
    forest_threshold: number
    smoothing: { alpha: number; beta: number }
  }
  monthly: {
    n: number
    positives: number
    base_rate: number
    brier: number
    log_loss: number
    roc_auc: number
    average_precision: number
    calibration: Array<{
      bin: string
      n: number
      predicted_mean: number
      observed_rate: number
    }>
    top_k: Array<{
      k: number
      selected: number
      positives: number
      captured: number
      capture_rate: number
      precision: number
    }>
  }
  annual: {
    n: number
    positives: number
    base_rate: number
    brier: number
    roc_auc: number
    average_precision: number
  }
  provinces: Record<
    string,
    {
      monthly: PredictionMetrics['monthly']
      cells: number
      months: number
    }
  >
}

export interface PredictionPayload {
  schemaVersion: number
  artifactKind: string
  generatedAt: string
  model: string
  futureYears: number[]
  forestThreshold: number
  cells: PredictionCell[]
  values: Record<string, Record<string, PredictionValue[]>>
  annual: Record<string, PredictionAnnualValue[]>
  provinces: PredictionProvinceRow[]
  metrics: PredictionMetrics
  limits: string[]
}

export const prediction = predictionJson as unknown as PredictionPayload
export const predictionCells = prediction.cells
export const predictionYears = prediction.futureYears
export const predictionMetrics = prediction.metrics

export const predictionProvinceOptions = (() => {
  const names = new Map<string, string>()
  for (const row of prediction.provinces) {
    names.set(row.code, row.name)
  }
  const order = ['GA', ...Array.from(names.keys()).filter((code) => code !== 'GA').sort()]
  return order.map((code) => ({ code, name: names.get(code) ?? code }))
})()

const monthValueIndex = new Map<string, Map<number, Map<number, PredictionValue>>>()
for (const [year, months] of Object.entries(prediction.values)) {
  const yearMap = new Map<number, Map<number, PredictionValue>>()
  for (const [month, values] of Object.entries(months)) {
    const valueMap = new Map<number, PredictionValue>()
    for (const value of values) {
      valueMap.set(value[0], value)
    }
    yearMap.set(Number(month), valueMap)
  }
  monthValueIndex.set(year, yearMap)
}

export function predictionMonthValues(
  year: number,
  month: number,
): Map<number, PredictionValue> {
  return monthValueIndex.get(String(year))?.get(month) ?? new Map()
}

export function predictionAnnualValues(year: number): Map<number, PredictionAnnualValue> {
  const values = prediction.annual[String(year)] ?? []
  const result = new Map<number, PredictionAnnualValue>()
  for (const value of values) {
    result.set(value[0], value)
  }
  return result
}

const provinceRowIndex = new Map<string, PredictionProvinceRow>()
for (const row of prediction.provinces) {
  provinceRowIndex.set(`${row.code}:${row.year}:${row.month}`, row)
}

export function predictionProvinceRow(
  code: string,
  year: number,
  month: number,
): PredictionProvinceRow | undefined {
  return provinceRowIndex.get(`${code}:${year}:${month}`)
}

export const predictionCellsByProvince = (() => {
  const result = new Map<string, PredictionCell[]>()
  for (const cell of prediction.cells) {
    const list = result.get(cell.province) ?? []
    list.push(cell)
    result.set(cell.province, list)
  }
  return result
})()

export function predictionCellsForProvince(code: string): PredictionCell[] {
  return code === 'GA' ? prediction.cells : (predictionCellsByProvince.get(code) ?? [])
}

export function probabilityClass(probability: number): {
  id: 'low' | 'moderate' | 'high' | 'very-high'
  labelFr: string
  labelEn: string
  color: string
} {
  if (probability >= 0.5) {
    return {
      id: 'very-high',
      labelFr: 'Très élevé',
      labelEn: 'Very high',
      color: '#ff7a3d',
    }
  }
  if (probability >= 0.25) {
    return {
      id: 'high',
      labelFr: 'Élevé',
      labelEn: 'High',
      color: '#ffc46b',
    }
  }
  if (probability >= 0.1) {
    return {
      id: 'moderate',
      labelFr: 'Modéré',
      labelEn: 'Moderate',
      color: '#5eead4',
    }
  }
  return {
    id: 'low',
    labelFr: 'Faible',
    labelEn: 'Low',
    color: '#637080',
  }
}
