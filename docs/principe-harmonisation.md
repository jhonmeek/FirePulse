# MODIS → VIIRS Harmonization Principle (FirePulse)

> **Release**: Live Baseline `v2.0` + **Strengthened Out-of-Sample Validation** (November 2026).  
> **Summary**: FirePulse translates 25 years of multi-sensor satellite thermal detections over Gabon onto a single comparable scale, so decision-makers see documented detection trends rather than camera upgrades or candidate persistent heat sources.

---

## 0. Two Protocols, Distinct Roles

FirePulse deliberately separates its live exploratory product from its independent validation benchmark:

| Dimension | **Live Baseline `v2.0`** | **Strengthened Validation** |
|---|---|---|
| **Purpose** | Live calendar, API, map, CSV export | Blind scientific proof & audit |
| **Static Flare Mask** | `183` cells built on `2000–2025` | `61` cells **frozen on `2000–2019`** |
| **Training Window** | `2012-02 → 2019-12` (`95` months) | `2012-02 → 2017-12` (`71` months) |
| **Calibration Window** | — | `2018-01 → 2019-12` (`24` months) |
| **Blind Test Window** | `2020-01 → 2025-12` (`72` months) | `2020-01 → 2025-12` (`72` months) |
| **Conformal Interval** | `q80` residual spread | `q80` learned on `2018–2019`, evaluated blind on `2020–2025` |
| **Artifact** | API `/api/v1/methodology/` | [`front-bis/src/data/validation.json`](../front-bis/src/data/validation.json) |

---

## 1. The Core Problem

Successive NASA instruments observe Earth at different spatial resolutions:

- **MODIS (`1 km/pixel`)**: Terra from `2000-11`, joined by Aqua from `2002-07`. Coarser spatial pixels miss smaller savanna/understory burns.
- **VIIRS S-NPP (`375 m/pixel`, since `2012-02`)**: Much sharper resolution—over Gabon (with static sites excluded), S-NPP records **~3.93×** more hotspots per month than MODIS (`global_ratio_alpha = 3.9328`).
- **VIIRS NOAA-20 (since `2018-04`)**: Twin 375 m sensor. **Suomi-NPP's** operational delivery ended on **`2026-11-02`**; the NOAA-20 relay is calibrated but **not yet validated on 2026 data**, and the demo archive stops in `2025-12`.

Without separating candidate persistent sources and rescaling MODIS onto VIIRS sensitivity, raw historical graphs misrepresent 2012 as an ecological fire explosion and let coastal heat sources mask seasonal cycles.

---

## 2. Live Baseline `v2.0` Pipeline

Implemented in [`build_baseline_series.py`](../backend/apps/harmonization/management/commands/build_baseline_series.py) using **VIIRS S-NPP 375 m** (`VIIRS_375m_SNPP_equiv`) as the unified scale:

### Step 1 — Isolate Candidate Persistent Sources (`filter_static=true`)
Keep presumed vegetation detections (`hotspot_type = 0`) outside `183` candidate `0.05°` cells (`type23_count >= 20` or `active_months_snpp >= 48`). On national `GA` boundaries (`285,013` detections), the full filter removes `109,513` detections (`38.4%`) and retains `175,500` type-0 detections outside candidate cells (`61.6%`). The excluded share is `57,934` type 2/3 (`20.3%`) plus `51,579` type 0 inside candidate cells (`18.1%`); these cells are candidates, not individually confirmed flares.

### Step 2 — Log-Scale Power-Law Calibration (`2012–2019` Overlap)
Instead of multiplying counts by a flat ratio (`×3.93`), which mis-scales rainy low seasons vs dry peaks, FirePulse fits a power law in `log1p` space:

$$
\hat{y} = \exp\big(p \cdot \ln(1 + x) + q\big) - 1
$$

Exploratory historical `v2.0` Gabon baseline figures (`GA`, `filter_static=true`):
- **MODIS Terra + Aqua (`power_law_log1p`)**: `p ≈ 0.944`, `q ≈ 1.653`
- **MODIS Terra-only (`terra_only_power_law`, `< 2002-07`)**: `p ≈ 0.691`, `q ≈ 3.681`
- **2020–2025 evaluation (`v2.0` live export)**: Naive MAE `≈ 355.6` (`R² ≈ 0.143`) → `power_law_log1p` MAE `≈ 100.8` (`R² ≈ 0.919`, bias `≈ +41.8`).

These historical results are exploratory: the test period was also used for other choices and is not an independent validation.

### Step 3 — Nominal 80% Uncertainty Band & Timeline Assembly
Reconstructed MODIS months (`2000-11`–`2012-01`) carry an asymmetric nominal 80% band `[ci_low, ci_high]` (`conformal_q80_log ≈ 0.524`, `conformal_q80_terra_log = 0.6445`), followed by direct S-NPP observations (`2012-02`–`2025-12` in the archive) and the post-2026 NOAA-20 bridge projection (`2026-11+`). Calendar months are normalized against their `2001–2025` calendar-month medians to measure seasonal anomalies (`%` and absolute deltas).
In the historical baseline, the quantile uses test-period residuals: independent coverage is not demonstrated. A nominal 80% target does not guarantee 80% coverage, especially for time series.

> The `2012-02`–`2026-10` S-NPP and `2026-11+` NOAA-20 regimes describe the **reconstruction**, not observed demo data: no 2026 observations are ingested. The NOAA-20 ratio used by the live reconstruction (`1.0381`, `2019–2025`) differs from the held-out validation ratio (`0.940`, `2018–2019`).

---

## 3. Strengthened Blind Validation Proof

Produced deterministically by [`front-bis/scripts/validate_harmonization.py`](../front-bis/scripts/validate_harmonization.py) and stored in [`validation.json`](../front-bis/src/data/validation.json):

### 3.1 Frozen Pre-Test Flare Mask (`2000–2019`)
Rebuilding the `0.05°` mask strictly on pre-test years (`2000–2019`, `61` cells) vs the full archive (`183` cells) quantifies look-ahead optimism explicitly:
- Frozen mask (`61` cells) test MAE (`2020–2025`): **`120.8`**
- All-years mask (`183` cells) test MAE (`2020–2025`): **`96.7`** (a `+24.1` MAE look-ahead gap, motivating regular operational mask refreshes in production).

### 3.2 Strict Three-Way Split & Blind Model Comparison (`2020–2025`)
Split: Train `2012-02`→`2017-12` (`71` months) | Calibration `2018-01`→`2019-12` (`24` months) | Blind Test `2020-01`→`2025-12` (`72` months).

| Model | MAE | Raw R² | Anomaly R² |
|---|---:|---:|---:|
| Naive (`VIIRS = MODIS`) | 460.3 | 0.08 | −1.37 |
| Global ratio | 147.4 | 0.87 | 0.67 |
| Seasonal ratio | 147.1 | 0.86 | 0.64 |
| Linear OLS | 133.1 | 0.90 | 0.73 |
| **Power-law `log1p`** | **120.8** | **0.92** | **0.79** |
| Seasonal median baseline | 238.8 | 0.61 | 0.00 |

Raw `R²` is naturally buoyed by Gabon's strong annual dry/wet cycle; **Anomaly `R²` (`0.79`)** verifies that `power-law log1p` captures true year-to-year surges (outperforming OLS `0.73`, global ratio `0.67`, and seasonal ratio `0.64`).

### 3.3 Out-of-Sample Conformal Coverage
Calibrated strictly on `2018–2019` (`q80 = 0.310`, `q90 = 0.360`) and tested blind on `2020–2025`, empirical coverage reaches **`63.9%`** (and `66.7%` at `q90`), honestly reporting wider `2020–2025` variance compared to a leaky in-test fit (`79.2%`).

### 3.4 Held-Out Sensor Generalization (`NOAA-20`) & Negative Control (`Terra → Aqua`)
- **Held-out NOAA-20 (`2020–2025`, calibration ratio `0.940` learned on `2018–2019`)**: MAE `100.1`, Raw `R² = 0.956`, **Anomaly `R² = 0.867`**.
- **Negative control (`Terra → Aqua`)**: Fails (`MAE = 428.7`, Anomaly `R² = −0.241`), proving MODIS platforms are not zero-cost interchangeable and justifying separate pre-2002 vs post-2002 calibration regimes.

---

## 4. Reproducibility

From repository root (Python `3.10+`, standard library only, zero mutation of inputs):

```bash
python front-bis/scripts/validate_harmonization.py
```

Outputs: [`front-bis/src/data/validation.json`](../front-bis/src/data/validation.json) and [`front-bis/src/data/validation_series.csv`](../front-bis/src/data/validation_series.csv).
