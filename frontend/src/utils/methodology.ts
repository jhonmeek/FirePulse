import type { CalibrationParams, OutOfSampleMetrics } from '@/types/api'

export interface BenchmarkRow extends OutOfSampleMetrics {
  key: string
  label: string
  formula: string
  selected: boolean
}

const MODEL_ORDER = [
  'naive',
  'global_ratio',
  'ols_linear',
  'power_law_log1p',
  'terra_only_power_law',
]

const nf = (v: number, d = 3) => v.toLocaleString('fr-FR', { maximumFractionDigits: d })

/** Libellés et formules lisibles, remplis avec les paramètres calibrés réels. */
export function benchmarkRows(
  models: Record<string, OutOfSampleMetrics>,
  params: CalibrationParams,
  methodName: string,
): BenchmarkRow[] {
  const meta: Record<string, { label: string; formula: string }> = {
    naive: { label: 'Naïf (aucune correction)', formula: 'V = M' },
    global_ratio: { label: 'Ratio global', formula: `V = ${nf(params.global_ratio_alpha)} · M` },
    ols_linear: {
      label: 'Régression linéaire',
      formula: `V = ${nf(params.ols_slope)} · M + ${nf(params.ols_intercept, 1)}`,
    },
    power_law_log1p: {
      label: 'Loi de puissance log1p',
      formula: `V = exp(${nf(params.power_law_p)} · ln(M+1) + ${nf(params.power_law_q)}) − 1`,
    },
    terra_only_power_law: {
      label: 'Loi de puissance, Terra seul',
      formula: `V = exp(${nf(params.terra_only_p)} · ln(T+1) + ${nf(params.terra_only_q)}) − 1`,
    },
  }
  const keys = [
    ...MODEL_ORDER.filter((k) => k in models),
    ...Object.keys(models).filter((k) => !MODEL_ORDER.includes(k)),
  ]
  return keys.map((key) => ({
    key,
    label: meta[key]?.label ?? key,
    formula: meta[key]?.formula ?? '',
    selected: methodName.startsWith(key),
    ...models[key]!,
  }))
}

/** Gain relatif de MAE du modèle retenu vs une référence (positif = meilleur). */
export function maeGain(rows: BenchmarkRow[], reference: string): number | null {
  const sel = rows.find((r) => r.selected)
  const ref = rows.find((r) => r.key === reference)
  if (!sel || !ref || ref.mae === 0) return null
  return (ref.mae - sel.mae) / ref.mae
}

/** Demi-largeur de l'intervalle conforme 80 % exprimée en facteur multiplicatif sur (V+1). */
export const conformalFactor = (q80Log: number) => Math.exp(q80Log)
