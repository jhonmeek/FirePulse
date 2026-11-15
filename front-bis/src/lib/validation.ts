import validationJson from '@/data/validation.json'

export interface ValidationMetrics {
  n: number
  mae: number | null
  rmse: number | null
  bias: number | null
  r2: number | null
}

export interface ValidationModel {
  raw: ValidationMetrics
  anomaly: ValidationMetrics
}

export interface ValidationSeriesPoint {
  month: string
  observed: number
  power_law: number
  seasonal_baseline: number
  seasonal_ratio: number
  noaa20_observed: number | null
}

export interface ValidationReport {
  schema_version: number
  artifact_kind: string
  generated_at: string
  split: {
    train: [string, string]
    calibration: [string, string]
    test: [string, string]
    n_train: number
    n_calibration: number
    n_test: number
  }
  mask: {
    grid_deg: number
    frozen_on: string
    type23_min: number
    snpp_months_min: number
    cells_frozen: number
    cells_all_years: number
  }
  params: Record<string, number | null>
  models: Record<string, ValidationModel>
  conformal: {
    nominal: number
    q80_calibration: number
    coverage_test_q80_calibration: number
    q90_calibration: number
    coverage_test_q90_calibration: number
    q80_test_leaky: number
    coverage_test_q80_leaky: number
    note: string
  }
  held_out: {
    noaa20: {
      role: string
      ratio_noaa20_to_snpp_calibration: number | null
      calibration_months: number
      raw: ValidationMetrics | null
      anomaly: ValidationMetrics | null
      limitation?: string
    }
    terra_to_aqua: {
      role: string
      raw: ValidationMetrics
      anomaly: ValidationMetrics
    }
  }
  by_season: Record<string, ValidationModel>
  mask_freeze_delta: {
    frozen_on: string
    all_years: string
    cells_frozen: number
    cells_all: number
    delta_cells: number
    frozen_power_law: ValidationMetrics
    all_years_power_law: ValidationMetrics
    note: string
  }
  sensitivity: Record<
    string,
    {
      type23_min: number
      snpp_months_min: number
      cells: number
      raw: ValidationMetrics
      anomaly: ValidationMetrics
    }
  >
  test_series: ValidationSeriesPoint[]
  notes: string[]
}

export const validation = validationJson as unknown as ValidationReport
