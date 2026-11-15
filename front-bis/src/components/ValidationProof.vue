<script setup lang="ts">
import { computed } from 'vue'
import LineChart from '@/components/LineChart.vue'
import { validation } from '@/lib/validation'
import type { ValidationMetrics } from '@/lib/validation'

defineProps<{ reducedMotion?: boolean }>()

const MODEL_LABELS: Record<string, string> = {
  naive: 'Naïf (V = M)',
  global_ratio: 'Ratio global',
  seasonal_ratio: 'Ratio saisonnier',
  ols_linear: 'OLS linéaire',
  power_law_log1p: 'Power-law log1p',
  seasonal_baseline: 'Baseline saisonnière',
}

const MODEL_ORDER = [
  'naive',
  'global_ratio',
  'seasonal_ratio',
  'ols_linear',
  'power_law_log1p',
  'seasonal_baseline',
]

const modelRows = computed(() =>
  MODEL_ORDER.map((key) => ({
    key,
    label: MODEL_LABELS[key] ?? key,
    accent: key === 'power_law_log1p',
    raw: validation.models[key]?.raw,
    anomaly: validation.models[key]?.anomaly,
  })),
)

const chartPoints = computed(() =>
  validation.test_series.map((point) => ({
    month: point.month,
    raw: point.observed,
    harm: point.power_law,
    lo: null,
    hi: null,
    anomaly: null,
  })),
)

const highSeason = validation.by_season.haute_saison_juin_octobre
const lowSeason = validation.by_season.basse_saison_nov_mai
const noaa20 = validation.held_out.noaa20
const terraAqua = validation.held_out.terra_to_aqua
const conformal = validation.conformal
const maskDelta = validation.mask_freeze_delta

const sensitivityRows = computed(() =>
  Object.entries(validation.sensitivity).map(([key, value]) => ({
    key,
    label:
      key === 'permissif_10_24'
        ? 'Permissif 10 / 24'
        : key === 'strict_30_72'
          ? 'Strict 30 / 72'
          : 'Référence 20 / 48',
    ...value,
  })),
)

const fmtMetric = (value: number | null | undefined): string =>
  value === null || value === undefined
    ? '—'
    : new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 }).format(value)

const fmtR2 = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '—'
  const rounded = Math.abs(value) < 0.0005 ? 0 : value
  return rounded.toFixed(2).replace('.', ',').replace('-', '−')
}

const fmtQ = (value: number | null | undefined): string =>
  value === null || value === undefined ? '—' : value.toFixed(2).replace('.', ',')

const fmtPct = (value: number | null | undefined): string =>
  value === null || value === undefined
    ? '—'
    : `${(value * 100).toFixed(1).replace('.', ',')} %`

const coverage = conformal.coverage_test_q80_calibration
const coverageLeaky = conformal.coverage_test_q80_leaky
</script>

<template>
  <div class="validation">
    <!-- ---------------------------------------------------------- stats -->
    <div class="v-stats">
      <article class="panel panel-pad v-stat">
        <span class="v-stat-label">Protocole</span>
        <strong class="v-stat-value">3 temps</strong>
        <span class="v-stat-note">
          {{ validation.split.n_train }} train · {{ validation.split.n_calibration }} calibration ·
          {{ validation.split.n_test }} test
        </span>
      </article>
      <article class="panel panel-pad v-stat">
        <span class="v-stat-label">Masque gelé</span>
        <strong class="v-stat-value">{{ validation.mask.cells_frozen }}</strong>
        <span class="v-stat-note">
          cellules 0,05° sur {{ validation.mask.frozen_on }} · {{ validation.mask.cells_all_years }}
          all-years
        </span>
      </article>
      <article class="panel panel-pad v-stat">
        <span class="v-stat-label">Couverture empirique</span>
        <strong class="v-stat-value">{{ fmtPct(coverage) }}</strong>
        <span class="v-stat-note">nominal {{ fmtPct(conformal.nominal) }} · mesuré sur 2020–2025</span>
      </article>
      <article class="panel panel-pad v-stat">
        <span class="v-stat-label">R² sur anomalies</span>
        <strong class="v-stat-value">
          {{ fmtR2(validation.models.power_law_log1p?.anomaly.r2) }}
        </strong>
        <span class="v-stat-note">le vrai test, pas le R² brut gonflé par la saison</span>
      </article>
    </div>

    <!-- ---------------------------------------------------------- table + chart -->
    <div class="v-grid-2">
      <article class="panel panel-pad v-panel">
        <div class="panel-label">
          <span class="tiny-label">Comparaison des modèles</span>
          <span class="tag dot">Test 2020–2025</span>
        </div>
        <table class="v-table">
          <thead>
            <tr>
              <th scope="col">Modèle</th>
              <th scope="col">MAE</th>
              <th scope="col">R² brut</th>
              <th scope="col">R² anomalies</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in modelRows"
              :key="row.key"
              :class="{ 'is-accent': row.accent }"
            >
              <th scope="row">{{ row.label }}</th>
              <td>{{ fmtMetric(row.raw?.mae) }}</td>
              <td>{{ fmtR2(row.raw?.r2) }}</td>
              <td>{{ fmtR2(row.anomaly?.r2) }}</td>
            </tr>
          </tbody>
        </table>
        <p class="v-note">
          Le R² brut est gonflé par le cycle saisonnier. Le R² anomalies mesure la capacité à
          retrouver les écarts interannuels ; c'est le vrai test.
        </p>
      </article>

      <article class="panel panel-pad v-panel">
        <div class="panel-label">
          <span class="tiny-label">Observé vs modèle</span>
          <span class="tag">72 mois de test</span>
        </div>
        <LineChart
          :points="chartPoints"
          :show-raw="true"
          :show-harmonized="true"
          :show-band="false"
          :reduced-motion="reducedMotion"
          mark-month="2024-08"
          title="S-NPP observé et power-law, 2020–2025"
          raw-label="S-NPP observé"
          harm-label="Power-law"
        />
        <p class="v-note">
          Le power-law reproduit la saison et les écarts interannuels. Le biais moyen reste
          positif : le modèle sur-prédit légèrement.
        </p>
      </article>
    </div>

    <!-- ---------------------------------------------------------- 3 cards -->
    <div class="v-grid-3">
      <article class="panel panel-pad v-panel">
        <div class="panel-label">
          <span class="tiny-label">Intervalle conforme</span>
          <span class="tag dot">80 % nominal</span>
        </div>
        <div class="v-coverage">
          <span class="v-coverage-track">
            <i class="v-coverage-fill" :style="{ width: `${coverage * 100}%` }"></i>
            <i class="v-coverage-target" :style="{ left: `${conformal.nominal * 100}%` }"></i>
          </span>
          <div class="v-coverage-labels">
            <span>couverture {{ fmtPct(coverage) }}</span>
            <span>cible {{ fmtPct(conformal.nominal) }}</span>
          </div>
        </div>
        <dl class="v-kv">
          <div>
            <dt>q80 calibration 2018–2019</dt>
            <dd>{{ fmtQ(conformal.q80_calibration) }}</dd>
          </div>
          <div>
            <dt>q90 calibration</dt>
            <dd>{{ fmtQ(conformal.q90_calibration) }} → {{ fmtPct(conformal.coverage_test_q90_calibration) }}</dd>
          </div>
          <div>
            <dt>q80 test « leaky »</dt>
            <dd>{{ fmtQ(conformal.q80_test_leaky) }} → {{ fmtPct(coverageLeaky) }}</dd>
          </div>
        </dl>
        <p class="v-note v-warning">
          Le 80 % nominal n'est pas atteint hors échantillon : la couverture réelle est
          {{ fmtPct(coverage) }}. La couverture « leaky » est tautologique ; nous ne la présentons
          pas comme une validation.
        </p>
      </article>

      <article class="panel panel-pad v-panel">
        <div class="panel-label">
          <span class="tiny-label">Capteur tenu à l'écart</span>
          <span class="tag cool">NOAA-20</span>
        </div>
        <div class="v-held">
          <div>
            <span class="v-held-label">NOAA-20 · test 2020–2025</span>
            <strong class="v-held-value">R² {{ fmtR2(noaa20.anomaly.r2) }}</strong>
            <span class="v-held-note">
              anomalies · MAE {{ fmtMetric(noaa20.raw.mae) }} · ratio
              {{ fmtQ(noaa20.ratio_noaa20_to_snpp_calibration) }}
            </span>
          </div>
          <div class="v-held-negative">
            <span class="v-held-label">Terra → Aqua · contrôle négatif</span>
            <strong class="v-held-value">R² {{ fmtR2(terraAqua.anomaly.r2) }}</strong>
            <span class="v-held-note">
              le transfert de plateforme n'est pas gratuit ; nous ne le revendiquons pas.
            </span>
          </div>
        </div>
      </article>

      <article class="panel panel-pad v-panel">
        <div class="panel-label">
          <span class="tiny-label">Masque gelé vs all-years</span>
          <span class="tag dot">look-ahead</span>
        </div>
        <div class="v-big-compare">
          <div>
            <span class="v-compare-value">{{ maskDelta.cells_frozen }}</span>
            <span class="v-compare-label">cellules gelées</span>
          </div>
          <div>
            <span class="v-compare-value">{{ maskDelta.cells_all }}</span>
            <span class="v-compare-label">all-years</span>
          </div>
        </div>
        <dl class="v-kv">
          <div>
            <dt>MAE gelé</dt>
            <dd>{{ fmtMetric(maskDelta.frozen_power_law.mae) }}</dd>
          </div>
          <div>
            <dt>MAE all-years</dt>
            <dd>{{ fmtMetric(maskDelta.all_years_power_law.mae) }}</dd>
          </div>
          <div>
            <dt>Coût du look-ahead</dt>
            <dd>+{{ fmtMetric((maskDelta.frozen_power_law.mae ?? 0) - (maskDelta.all_years_power_law.mae ?? 0)) }} MAE</dd>
          </div>
        </dl>
        <p class="v-note v-warning">
          Le masque all-years connaît les torchères de 2020–2025. Le masque gelé est le seul
          protocole honnête ; en production, il faut le rafraîchir régulièrement.
        </p>
      </article>
    </div>

    <!-- ---------------------------------------------------------- season + sensitivity -->
    <div class="v-grid-2">
      <article class="panel panel-pad v-panel">
        <div class="panel-label">
          <span class="tiny-label">Par saison</span>
          <span class="tag">Power-law</span>
        </div>
        <div class="v-season">
          <div class="v-season-row">
            <div>
              <span class="v-held-label">Haute saison · juin–octobre</span>
              <span class="v-held-note">le modèle est fait pour ces mois</span>
            </div>
            <strong>MAE {{ fmtMetric(highSeason.raw.mae) }}</strong>
            <span>R² {{ fmtR2(highSeason.anomaly.r2) }}</span>
          </div>
          <div class="v-season-row">
            <div>
              <span class="v-held-label">Basse saison · novembre–mai</span>
              <span class="v-held-note">signal plus faible, plus difficile</span>
            </div>
            <strong>MAE {{ fmtMetric(lowSeason.raw.mae) }}</strong>
            <span>R² {{ fmtR2(lowSeason.anomaly.r2) }}</span>
          </div>
        </div>
        <p class="v-note">
          La performance est plus faible en basse saison. C'est une limite réelle, pas un détail :
          les anomalies de saison sèche sont plus faciles à détecter que les mois calmes.
        </p>
      </article>

      <article class="panel panel-pad v-panel">
        <div class="panel-label">
          <span class="tiny-label">Sensibilité du masque</span>
          <span class="tag">2000–2019</span>
        </div>
        <table class="v-table v-table-compact">
          <thead>
            <tr>
              <th scope="col">Seuils</th>
              <th scope="col">Cellules</th>
              <th scope="col">MAE</th>
              <th scope="col">R² anom.</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in sensitivityRows" :key="row.key">
              <th scope="row">{{ row.label }}</th>
              <td>{{ row.cells }}</td>
              <td>{{ fmtMetric(row.raw.mae) }}</td>
              <td>{{ fmtR2(row.anomaly.r2) }}</td>
            </tr>
          </tbody>
        </table>
        <p class="v-note">
          Le permissif 10/24 est meilleur sur le test, mais le choisir sur le test serait une
          faute. Nous publions la sensibilité, pas une sélection opportuniste.
        </p>
      </article>
    </div>

    <!-- ---------------------------------------------------------- prove / limits -->
    <div class="v-grid-2">
      <article class="panel panel-pad v-panel v-prove">
        <div class="panel-label">
          <span class="tiny-label">Ce que ça prouve</span>
          <span class="tag cool">Positif</span>
        </div>
        <ul>
          <li>
            Le power-law bat le naïf, le ratio global, l'OLS et le ratio saisonnier
            <strong>sur les anomalies</strong> (R² 0,79 vs 0,73 / 0,67 / 0,64).
          </li>
          <li>
            Il généralise à <strong>NOAA-20</strong>, un capteur non utilisé pour l'entraînement
            (R² anomalies 0,87).
          </li>
          <li>
            Le signal reste stable quand on change les seuils du masque (R² 0,79–0,86), même si le
            choix doit se faire sur calibration.
          </li>
          <li>
            Le protocole est reproductible : masque gelé, split 3 temps, calibration séparée,
            couverture mesurée.
          </li>
        </ul>
      </article>

      <article class="panel panel-pad v-panel v-limits">
        <div class="panel-label">
          <span class="tiny-label">Ce que ça ne prouve pas</span>
          <span class="tag">Honnête</span>
        </div>
        <ul>
          <li>
            Le 80 % nominal n'est pas atteint : la couverture empirique est
            <strong>{{ fmtPct(coverage) }}</strong>.
          </li>
          <li>
            Le masque gelé coûte
            <strong>{{ fmtMetric((maskDelta.frozen_power_law.mae ?? 0) - (maskDelta.all_years_power_law.mae ?? 0)) }} MAE</strong>
            par rapport à un masque qui connaît le futur. Une production doit le rafraîchir.
          </li>
          <li>
            Le transfert Terra → Aqua échoue (R² anomalies {{ fmtR2(terraAqua.anomaly.r2) }}) :
            on ne remplace pas un capteur par l'autre sans calibration.
          </li>
          <li>
            Le pont NOAA-20 post-2026 reste une <strong>projection</strong>, pas une validation.
          </li>
          <li>
            Les comptages ne sont pas une mesure physique : la FRP et la surface brûlée sont les
            prochaines étapes.
          </li>
        </ul>
      </article>
    </div>

    <p class="v-source">
      Source : {{ validation.split.n_test }} mois de test · {{ validation.split.n_train }} mois de
      train · {{ validation.split.n_calibration }} mois de calibration · masque
      {{ validation.mask.frozen_on }} · données FIRMS pays Gabon, géométrie non rejointe.
    </p>
  </div>
</template>

<style scoped>
.validation {
  display: grid;
  gap: 16px;
}

.v-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.v-stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.v-stat-label {
  font-family: var(--font-mono);
  font-size: 0.54rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--dim);
}

.v-stat-value {
  font-family: var(--font-display);
  font-weight: 300;
  font-size: clamp(1.8rem, 2.5vw, 2.6rem);
  line-height: 1;
  letter-spacing: -0.03em;
  color: var(--ink);
}

.v-stat-note {
  font-size: 0.66rem;
  line-height: 1.5;
  color: var(--muted);
}

.v-grid-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.v-grid-3 {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.v-panel {
  min-width: 0;
}

.v-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.72rem;
}

.v-table th,
.v-table td {
  padding: 8px 0;
  border-bottom: 1px solid var(--line);
  text-align: right;
  font-weight: 400;
  white-space: nowrap;
}

.v-table thead th {
  padding-top: 0;
  font-family: var(--font-mono);
  font-size: 0.52rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dim);
}

.v-table th:first-child {
  text-align: left;
}

.v-table tbody th {
  color: var(--muted);
}

.v-table tbody td {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: var(--ink);
}

.v-table tr.is-accent th,
.v-table tr.is-accent td {
  color: var(--gold);
}

.v-table tr.is-accent {
  background: rgba(255, 196, 107, 0.06);
}

.v-table tr.is-accent th {
  font-weight: 600;
}

.v-table-compact th,
.v-table-compact td {
  padding: 6px 0;
}

.v-note {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
  font-size: 0.66rem;
  line-height: 1.55;
  color: var(--dim);
}

.v-warning {
  color: var(--muted);
  border-left: 2px solid rgba(255, 196, 107, 0.4);
  padding-left: 10px;
}

.v-coverage {
  display: grid;
  gap: 6px;
}

.v-coverage-track {
  position: relative;
  display: block;
  height: 8px;
  border-radius: 4px;
  background: rgba(244, 241, 232, 0.08);
  overflow: hidden;
}

.v-coverage-fill {
  display: block;
  height: 100%;
  border-radius: 4px;
  background: var(--grad-heat);
}

.v-coverage-target {
  position: absolute;
  top: -3px;
  width: 2px;
  height: 14px;
  background: var(--teal);
  box-shadow: 0 0 8px rgba(94, 234, 212, 0.7);
}

.v-coverage-labels {
  display: flex;
  justify-content: space-between;
  font-family: var(--font-mono);
  font-size: 0.52rem;
  color: var(--dim);
}

.v-kv {
  display: grid;
  gap: 5px;
  margin: 14px 0 0;
}

.v-kv > div {
  display: flex;
  justify-content: space-between;
  gap: 14px;
}

.v-kv dt {
  font-size: 0.66rem;
  color: var(--dim);
}

.v-kv dd {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 0.66rem;
  color: var(--ink);
}

.v-held {
  display: grid;
  gap: 14px;
}

.v-held > div {
  display: grid;
  gap: 3px;
}

.v-held-label {
  font-family: var(--font-mono);
  font-size: 0.52rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dim);
}

.v-held-value {
  font-family: var(--font-display);
  font-weight: 300;
  font-size: 1.65rem;
  line-height: 1;
  color: var(--teal);
}

.v-held-note {
  font-size: 0.64rem;
  line-height: 1.5;
  color: var(--muted);
}

.v-held-negative .v-held-value {
  color: var(--danger);
}

.v-big-compare {
  display: flex;
  gap: 28px;
  margin-bottom: 12px;
}

.v-big-compare > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.v-compare-value {
  font-family: var(--font-display);
  font-weight: 300;
  font-size: 2.1rem;
  line-height: 1;
  color: var(--gold);
}

.v-compare-label {
  font-family: var(--font-mono);
  font-size: 0.52rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dim);
}

.v-season {
  display: grid;
  gap: 0;
}

.v-season-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 14px;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--line);
}

.v-season-row > div {
  display: grid;
  gap: 2px;
}

.v-season-row strong {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  font-weight: 500;
  color: var(--ink);
}

.v-season-row > span {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: var(--gold);
}

.v-prove ul,
.v-limits ul {
  display: grid;
  gap: 9px;
  margin-top: 14px;
}

.v-prove li,
.v-limits li {
  position: relative;
  padding-left: 19px;
  font-size: 0.68rem;
  line-height: 1.55;
  color: var(--muted);
}

.v-prove li::before {
  content: '✓';
  position: absolute;
  left: 0;
  color: var(--teal);
}

.v-limits li::before {
  content: '—';
  position: absolute;
  left: 0;
  color: var(--ember);
}

.v-prove strong,
.v-limits strong {
  color: var(--ink);
  font-weight: 600;
}

.v-source {
  font-family: var(--font-mono);
  font-size: 0.54rem;
  letter-spacing: 0.04em;
  line-height: 1.6;
  color: var(--dim);
}

@media (max-width: 1100px) {
  .v-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .v-grid-3 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 820px) {
  .v-grid-2,
  .v-grid-3 {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 560px) {
  .v-stats {
    grid-template-columns: minmax(0, 1fr);
  }
  .v-season-row {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .v-season-row > span {
    grid-column: 1 / -1;
  }
}
</style>
