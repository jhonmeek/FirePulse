<script setup lang="ts">
import { computed } from 'vue'
import { formatDecimal } from '@/lib/data'
import { t } from '@/lib/i18n'
import type { PredictionMetrics } from '@/lib/prediction'

const props = defineProps<{
  metrics: PredictionMetrics
  generatedAt: string
}>()

const top10 = computed(() => props.metrics.monthly.top_k.find((item) => item.k === 0.1))
const top20 = computed(() => props.metrics.monthly.top_k.find((item) => item.k === 0.2))
const highBins = computed(() =>
  props.metrics.monthly.calibration.filter((item) => item.predicted_mean >= 0.3),
)
const generatedDate = computed(() => props.generatedAt.slice(0, 10))
</script>

<template>
  <section class="prediction-confidence" :aria-label="t('Fiabilité de la prévision', 'Prediction reliability')">
    <div class="prediction-confidence-head">
      <div>
        <span class="prediction-confidence-eyebrow">{{ t('Fiche de confiance', 'Confidence note') }}</span>
        <h3>{{ t('Comment lire cette carte', 'How to read this map') }}</h3>
      </div>
      <span class="prediction-confidence-badge">{{ t('Projection climatologique', 'Climatological projection') }}</span>
    </div>

    <div class="prediction-confidence-grid">
      <article>
        <span class="prediction-confidence-label">{{ t('Ce que c’est', 'What it is') }}</span>
        <p>
          {{
            t(
              'Une probabilité mensuelle de détection d’au moins un feu de végétation en zone forestière, apprise sur 2012–2025 et projetée avec une tendance provinciale prudente. Utile pour comparer les provinces, repérer les mois à risque et cibler la surveillance — pas pour décider qu’un feu précis aura lieu.',
              'A monthly probability of detecting at least one vegetation fire in forest areas, learned over 2012–2025 and projected with a conservative province trend. Useful for comparing provinces, spotting risky months and targeting monitoring—not for deciding that a specific fire will occur.',
            )
          }}
        </p>
        <p class="prediction-confidence-muted">
          {{ t('Ce n’est pas une prévision météo : aucune pluie, température ou foudre n’est prédite.', 'This is not a weather forecast: no rainfall, temperature or lightning is predicted.') }}
        </p>
      </article>

      <article>
        <span class="prediction-confidence-label">{{ t('Validation 2020–2025', '2020–2025 validation') }}</span>
        <dl class="prediction-confidence-metrics">
          <div><dt>ROC-AUC</dt><dd>{{ formatDecimal(metrics.monthly.roc_auc, 3) }}</dd></div>
          <div><dt>PR-AUC</dt><dd>{{ formatDecimal(metrics.monthly.average_precision, 3) }}</dd></div>
          <div><dt>Brier</dt><dd>{{ formatDecimal(metrics.monthly.brier, 3) }}</dd></div>
          <div>
            <dt>{{ t('Top 10 % capturés', 'Top 10% captured') }}</dt>
            <dd>{{ formatDecimal((top10?.capture_rate ?? 0) * 100, 1) }} %</dd>
          </div>
          <div>
            <dt>{{ t('Top 20 % capturés', 'Top 20% captured') }}</dt>
            <dd>{{ formatDecimal((top20?.capture_rate ?? 0) * 100, 1) }} %</dd>
          </div>
        </dl>
        <p class="prediction-confidence-muted">
          {{
            t(
              `Test à l’aveugle sur ${metrics.monthly.n.toLocaleString('fr-FR')} cellules-mois ; ${metrics.monthly.positives.toLocaleString('fr-FR')} positifs.`,
              `Blind test on ${metrics.monthly.n.toLocaleString('en-US')} cell-months; ${metrics.monthly.positives.toLocaleString('en-US')} positives.`,
            )
          }}
        </p>
      </article>

      <article>
        <span class="prediction-confidence-label">{{ t('Calibration', 'Calibration') }}</span>
        <ul class="prediction-confidence-calibration">
          <li v-for="bin in highBins" :key="bin.bin">
            <span>{{ bin.bin }}</span>
            <strong>{{ Math.round(bin.predicted_mean * 100) }}% → {{ Math.round(bin.observed_rate * 100) }}%</strong>
          </li>
        </ul>
        <p class="prediction-confidence-muted">
          {{
            t(
              'Quand la carte annonce 30–50 %, le taux observé est plus élevé : le modèle lisse les hauts risques. Les classes hautes sont donc sous-estimées, pas surévaluées.',
              'When the map says 30–50%, the observed rate is higher: the model smooths high risks. High classes are therefore under-estimated, not over-estimated.',
            )
          }}
        </p>
      </article>
    </div>

    <div class="prediction-confidence-bottom">
      <div>
        <span class="prediction-confidence-label is-warn">{{ t('Ce qu’on ne peut pas conclure', 'What you cannot conclude') }}</span>
        <ul>
          <li>{{ t('La cause d’un feu (naturel, agricole, accidentel) n’est pas observable dans FIRMS.', 'The cause of a fire (natural, agricultural, accidental) is not observable in FIRMS.') }}</li>
          <li>{{ t('Une carte 2026–2035 n’est pas une prévision année par année : c’est un scénario climatologique.', 'A 2026–2035 map is not a year-by-year forecast: it is a climatological scenario.') }}</li>
          <li>{{ t('La couverture satellite n’est pas exhaustive : nuages, fumée et canopée masquent des détections.', 'Satellite coverage is not exhaustive: clouds, smoke and canopy hide detections.') }}</li>
          <li>{{ t('Le masque forêt est statique (ESA WorldCover 2021) et ne suit pas les changements de couvert.', 'The forest mask is static (ESA WorldCover 2021) and does not track land-cover change.') }}</li>
        </ul>
      </div>
      <div>
        <span class="prediction-confidence-label">{{ t('Modèle', 'Model') }}</span>
        <p>
          {{
            t(
              `Climatologie mensuelle lissée Beta(1,4), 2012–2025, + tendance provinciale 2026–2035. Artefact du ${generatedDate}. Type 0 hors sources persistantes ; forêt ≥ ${Math.round(metrics.protocol.forest_threshold * 100)} %.`,
              `Smoothed monthly Beta(1,4) climatology, 2012–2025, + province trend 2026–2035. Artifact dated ${generatedDate}. Type 0 outside persistent sources; forest ≥ ${Math.round(metrics.protocol.forest_threshold * 100)}%.`,
            )
          }}
        </p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.prediction-confidence {
  display: grid;
  gap: 14px;
  padding: 20px 22px;
  border: 1px solid var(--line-strong);
  border-radius: 16px;
  background: linear-gradient(160deg, rgba(94, 234, 212, 0.035), rgba(11, 16, 22, 0.94));
}

.prediction-confidence-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.prediction-confidence-eyebrow {
  display: block;
  font-family: var(--font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--dim);
}

.prediction-confidence-head h3 {
  margin: 3px 0 0;
  font-family: var(--font-display);
  font-size: clamp(1.3rem, 2vw, 1.6rem);
  font-weight: 400;
  color: var(--ink);
}

.prediction-confidence-badge {
  padding: 5px 10px;
  border: 1px solid rgba(94, 234, 212, 0.35);
  border-radius: 999px;
  font-family: var(--font-mono);
  font-size: 0.56rem;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: #5eead4;
  background: rgba(94, 234, 212, 0.07);
}

.prediction-confidence-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.prediction-confidence-grid article,
.prediction-confidence-bottom > div {
  padding: 13px 14px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: rgba(244, 241, 232, 0.025);
}

.prediction-confidence-label {
  display: block;
  margin-bottom: 7px;
  font-family: var(--font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--gold);
}

.prediction-confidence-label.is-warn {
  color: #ffb37a;
}

.prediction-confidence-grid p,
.prediction-confidence-bottom p {
  margin: 0;
  font-size: 0.76rem;
  line-height: 1.5;
  color: #cdd6df;
}

.prediction-confidence-muted {
  margin-top: 6px !important;
  color: var(--dim) !important;
  font-size: 0.7rem !important;
}

.prediction-confidence-metrics {
  margin: 0;
  display: grid;
  gap: 4px;
  font-size: 0.72rem;
}

.prediction-confidence-metrics > div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.prediction-confidence-metrics dt {
  color: var(--dim);
}

.prediction-confidence-metrics dd {
  margin: 0;
  font-family: var(--font-mono);
  color: var(--ink);
}

.prediction-confidence-calibration {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 4px;
  font-size: 0.7rem;
}

.prediction-confidence-calibration li {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  color: var(--dim);
}

.prediction-confidence-calibration strong {
  font-family: var(--font-mono);
  font-weight: 500;
  color: var(--ink);
}

.prediction-confidence-bottom {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 12px;
}

.prediction-confidence-bottom ul {
  margin: 0;
  padding-left: 17px;
  display: grid;
  gap: 5px;
  font-size: 0.73rem;
  line-height: 1.45;
  color: #cdd6df;
}

@media (max-width: 900px) {
  .prediction-confidence-grid {
    grid-template-columns: 1fr;
  }

  .prediction-confidence-bottom {
    grid-template-columns: 1fr;
  }
}
</style>
