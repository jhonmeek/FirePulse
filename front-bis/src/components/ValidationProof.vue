<script setup lang="ts">
import { computed } from 'vue'
import LineChart, { type ChartPoint } from './LineChart.vue'
import { formatCount, formatDecimal } from '@/lib/data'
import { t } from '@/lib/i18n'
import { validation } from '@/lib/validation'

withDefaults(
  defineProps<{
    reducedMotion?: boolean
  }>(),
  {
    reducedMotion: false,
  },
)

const naiveMae = computed(() => validation.models.naive.raw.mae ?? 0)
const modelMae = computed(() => validation.models.power_law_log1p.raw.mae ?? 0)
const modelR2 = computed(() => validation.models.power_law_log1p.raw.r2 ?? 0)
const modelAnomalyR2 = computed(() => validation.models.power_law_log1p.anomaly.r2 ?? 0)
const coverageQ80 = computed(() => validation.conformal.coverage_test_q80_calibration)
const trainMonths = computed(() => validation.split.n_train + validation.split.n_calibration)
const testMonths = computed(() => validation.split.n_test)

const errorReductionPct = computed(() => {
  if (!naiveMae.value) return 0
  return Math.max(0, Math.round(((naiveMae.value - modelMae.value) / naiveMae.value) * 100))
})

const noaaRatio = computed(() => validation.held_out.noaa20.ratio_noaa20_to_snpp_calibration)
const noaaDiffPct = computed(() => {
  if (noaaRatio.value === null) return null
  return Math.abs(Math.round((noaaRatio.value - 1) * 1000) / 10)
})
const noaaAnomalyR2 = computed(() => validation.held_out.noaa20.anomaly?.r2 ?? null)
const noaaLimitation = computed(() => validation.held_out.noaa20.limitation ?? null)
const maskFrozenOn = computed(() => validation.mask.frozen_on)
const cellsFrozen = computed(() => validation.mask.cells_frozen)
const cellsAllYears = computed(() => validation.mask.cells_all_years)

const testPoints = computed<ChartPoint[]>(() =>
  validation.test_series.map((d) => ({
    month: d.month,
    raw: d.observed,
    harm: d.power_law,
    lo: null,
    hi: null,
    anomaly: null,
  })),
)
</script>

<template>
  <div class="proof-root">
    <p class="proof-review-banner" role="note">
      {{
        t(
          `Résultats exploratoires en revue scientifique, non validés. Dans l'artefact affiché, le masque utilise la période de calibration, les mois sans détection ne prouvent pas une couverture complète et l'intervalle expérimental (cible 80 %) ne constitue pas une garantie conforme. Les années de test ont déjà été examinées.`,
          `Exploratory results under scientific review, not independently validated. In this initial artifact, the mask includes part of the calibration window, zero-detection months do not prove complete satellite coverage, and the experimental 80% target interval is not a conformal guarantee. Test years have already been examined.`,
        )
      }}
    </p>

    <!-- 3 clear steps replacing jargon-heavy metric tiles -->
    <div class="proof-steps" :aria-label="t('Protocole exploratoire du modèle', 'Exploratory model protocol')">
      <article class="proof-step">
        <span class="proof-step-tag">{{ t('Étape 1 · Apprendre', 'Step 1 · Learn') }}</span>
        <strong class="proof-step-value">2012 – 2019</strong>
        <p class="proof-step-desc">
          {{
            t(
              `Pendant ${trainMonths} mois (8 ans), les deux satellites observent le Gabon en même temps (${validation.split.n_train} mois d'entraînement, ${validation.split.n_calibration} mois de calibration).`,
              `For ${trainMonths} months (8 years), both satellites observe Gabon together (${validation.split.n_train} training months, ${validation.split.n_calibration} calibration months).`,
            )
          }}
        </p>
      </article>

      <article class="proof-step">
        <span class="proof-step-tag">{{ t('Étape 2 · Évaluation exploratoire', 'Step 2 · Exploratory evaluation') }}</span>
        <strong class="proof-step-value">2020 – 2025</strong>
        <p class="proof-step-desc">
          {{
            t(
              `On cache les ${testMonths} mois suivants (6 ans) au modèle, puis on lui demande de deviner la courbe uniquement depuis l'ancien capteur.`,
              `We hide the next ${testMonths} months (6 years) from the model, then ask it to predict the curve using only the older sensor.`,
            )
          }}
        </p>
      </article>

      <article class="proof-step is-highlight">
        <span class="proof-step-tag">{{ t('Étape 3 · Résultat', 'Step 3 · Result') }}</span>
        <strong class="proof-step-value">−{{ errorReductionPct }} % {{ t('d’erreur', 'less error') }}</strong>
        <p class="proof-step-desc">
          {{
            t(
              `L'écart moyen chute de ${formatCount(naiveMae)} à ${formatCount(modelMae)} détections/mois. Le R² brut des saisons est ${formatDecimal(modelR2, 2)}, mais il est gonflé par la saisonnalité : sur les anomalies, le R² tombe à ${formatDecimal(modelAnomalyR2, 2)}.`,
              `Average monthly error drops from ${formatCount(naiveMae)} to ${formatCount(modelMae)} detections/month. The raw seasonal R² is ${formatDecimal(modelR2, 2)}, inflated by seasonality: on anomalies it falls to ${formatDecimal(modelAnomalyR2, 2)}.`,
            )
          }}
        </p>
      </article>
    </div>

    <!-- Observed vs predicted test chart -->
    <div class="proof-chart-card">
      <div class="proof-chart-head">
        <div>
          <span class="chart-eyebrow">
            {{ t('Analyse exploratoire · Gabon · 2020–2025', 'Exploratory analysis · Gabon · 2020–2025') }}
          </span>
          <h3>
            {{
              t(
                'Ce que VIIRS a vraiment vu vs ce que notre modèle estimait',
                'What VIIRS actually saw vs what our model estimated',
              )
            }}
          </h3>
        </div>
        <div class="proof-legend-pills">
          <span class="proof-pill is-obs">
            <span class="proof-line-swatch is-obs" aria-hidden="true" />
            {{ t('Vraies mesures VIIRS (référence)', 'Real VIIRS measurements (reference)') }}
          </span>
          <span class="proof-pill is-mod">
            <span class="proof-line-swatch is-mod" aria-hidden="true" />
            {{ t('Estimation à partir de MODIS (notre modèle)', 'Estimate from MODIS (our model)') }}
          </span>
        </div>
      </div>

      <LineChart
        :points="testPoints"
        :show-raw="true"
        :show-harmonized="true"
        :show-band="false"
        :reduced-motion="reducedMotion"
        mark-month="2024-08"
        default-granularity="month"
        :raw-label="t('Vraies mesures VIIRS (référence)', 'Real VIIRS measurements (reference)')"
        :harm-label="t('Estimation à partir de MODIS (notre modèle)', 'Estimate from MODIS (our model)')"
      />
    </div>

    <p class="proof-protocol-note">
      {{
        t(
          `Protocole exploratoire : masque gelé ${maskFrozenOn} (${cellsFrozen} cellules, vs ${cellsAllYears} all-years), apprentissage 2012–2017, calibration 2018–2019, évaluation 2020–2025. L’intervalle expérimental (cible 80 %) couvre ${formatDecimal(coverageQ80 * 100, 1)} % des mois de test : c’est un indicateur exploratoire, pas une garantie conforme. La série live de la base suit un protocole distinct (masque toutes années, ${cellsAllYears} cellules).`,
          `Exploratory protocol: frozen mask ${maskFrozenOn} (${cellsFrozen} cells vs ${cellsAllYears} all-years), training 2012–2017, calibration 2018–2019, evaluation 2020–2025. The experimental interval (80% target) covers ${formatDecimal(coverageQ80 * 100, 1)}% of test months: an exploratory indicator, not a conformal guarantee. The live database series uses a distinct protocol (all-years mask, ${cellsAllYears} cells).`,
        )
      }}
    </p>

    <!-- Two plain takeaways cards: proof + limits -->
    <div class="proof-Takeaways">
      <article class="takeaway-card">
        <header class="takeaway-head">
          <span class="takeaway-badge is-good">{{ t('Résultats exploratoires · En revue', 'Exploratory results · Under review') }}</span>
          <h4>{{ t('Ce que montrent les résultats exploratoires', 'What the exploratory results show') }}</h4>
        </header>
        <ul class="takeaway-list">
          <li>
            {{
              t(
                'Le modèle retrouve bien les saisons calmes comme les grands pics secs, par exemple août 2024.',
                'The model tracks both quiet wet months and strong dry-season peaks such as August 2024.',
              )
            }}
          </li>
          <li>
            {{
              t(
                `Sur ces 6 années d'évaluation (déjà examinées), l'écart moyen reste limité à ${formatCount(modelMae)} détections thermiques par mois.`,
                `Across these 6 evaluation years (already examined), average monthly error stays limited to ${formatCount(modelMae)} thermal detections.`,
              )
            }}
          </li>
          <li>
            {{
              noaaRatio === null
                ? t(
                    `Évaluation exploratoire NOAA-20 indisponible : ratio de calibration absent (${noaaLimitation ?? 'calibration manquante'}).`,
                    `Exploratory NOAA-20 evaluation unavailable: calibration ratio missing (${noaaLimitation ?? 'missing calibration'}).`,
                  )
                : t(
                    `L'évaluation exploratoire VIIRS NOAA-20 donne ${formatDecimal(noaaDiffPct, 1)} % d'écart sur la calibration (R² anomalies ${noaaAnomalyR2 === null ? '—' : formatDecimal(noaaAnomalyR2, 2)}) ; son indépendance reste limitée par le masque et le ratio.`,
                    `Exploratory VIIRS NOAA-20 evaluation shows a ${formatDecimal(noaaDiffPct, 1)}% calibration gap (anomaly R² ${noaaAnomalyR2 === null ? '—' : formatDecimal(noaaAnomalyR2, 2)}); its independence remains limited by mask and ratio reuse.`,
                  )
            }}
          </li>
        </ul>
      </article>

      <article class="takeaway-card">
        <header class="takeaway-head">
          <span class="takeaway-badge is-warn">{{ t('Précautions scientifiques', 'Scientific limits') }}</span>
          <h4>{{ t('Ce qu’il faut garder en tête', 'What to keep in mind') }}</h4>
        </header>
        <ul class="takeaway-list">
          <li>
            {{
              t(
                'Un point chaud est une détection thermique vue depuis l’espace, pas une mesure directe de la surface brûlée en hectares.',
                'A hotspot is a thermal detection seen from space, not a direct measurement of burned area in hectares.',
              )
            }}
          </li>
          <li>
            {{
              t(
                'Quand le ciel gabonais reste très nuageux ou enfumé, le satellite peut manquer les petits feux sous la canopée ; l’absence de détection ne prouve pas l’absence de feu.',
                'When skies over Gabon are cloudy or thick with smoke, satellites can miss small fires beneath the canopy; missing detections do not prove complete coverage.',
              )
            }}
          </li>
          <li>
            {{
              t(
                `Quelques sources industrielles ouvertes après ${maskFrozenOn} peuvent apparaître localement tant qu’elles ne sont pas ajoutées au masque. Le masque live utilise toutes les années (${cellsAllYears} cellules) ; l’artefact exploratoire utilise un masque gelé sur ${maskFrozenOn} (${cellsFrozen} cellules).`,
                `A few industrial sources opened after ${maskFrozenOn} can appear locally until added to the mask. The live mask uses all years (${cellsAllYears} cells); the exploratory artifact uses a mask frozen on ${maskFrozenOn} (${cellsFrozen} cells).`,
              )
            }}
          </li>
        </ul>
      </article>
    </div>
  </div>
</template>

<style scoped>
.proof-root {
  display: grid;
  gap: 20px;
}

.proof-review-banner {
  margin: 0;
  padding: 12px 16px;
  border: 1px solid rgba(255, 196, 107, 0.42);
  border-left: 3px solid var(--gold);
  border-radius: 12px;
  background: rgba(255, 196, 107, 0.08);
  color: #f4e6cf;
  font-size: 0.84rem;
  line-height: 1.55;
}

.proof-protocol-note {
  margin: -6px 2px 0;
  font-size: 0.76rem;
  line-height: 1.55;
  color: var(--dim);
}

.proof-steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.proof-step {
  padding: 20px 22px;
  border-radius: 16px;
  border: 1px solid var(--line);
  background: rgba(11, 16, 22, 0.88);
  display: grid;
  align-content: start;
  gap: 8px;
}

.proof-step.is-highlight {
  border-color: rgba(255, 196, 107, 0.42);
  background: linear-gradient(155deg, rgba(255, 138, 61, 0.12), rgba(11, 16, 22, 0.92));
}

.proof-step-tag {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--gold);
}

.proof-step-value {
  font-family: var(--font-display);
  font-size: clamp(1.45rem, 2.2vw, 1.95rem);
  font-weight: 400;
  line-height: 1.1;
  color: var(--ink);
}

.proof-step-desc {
  margin: 0;
  font-size: 0.88rem;
  line-height: 1.52;
  color: #cdd6df;
}

.proof-chart-card {
  padding: 22px;
  border-radius: 18px;
  border: 1px solid var(--line);
  background: rgba(11, 16, 22, 0.92);
  display: grid;
  gap: 16px;
}

.proof-chart-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-end;
  gap: 14px;
}

.chart-eyebrow {
  display: block;
  font-family: var(--font-mono);
  font-size: 0.6rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--dim);
  margin-bottom: 5px;
}

.proof-chart-head h3 {
  margin: 0;
  font-size: 1.12rem;
  font-weight: 500;
  color: var(--ink);
}

.proof-legend-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.proof-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.03);
  font-size: 0.78rem;
  color: #dce3eb;
}

.proof-line-swatch {
  width: 18px;
  height: 3px;
  border-radius: 2px;
}

.proof-line-swatch.is-obs {
  background: #60a5fa;
}

.proof-line-swatch.is-mod {
  background: #ff8a3d;
}

.proof-Takeaways {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.takeaway-card {
  padding: 20px 22px;
  border-radius: 16px;
  border: 1px solid var(--line);
  background: rgba(11, 16, 22, 0.84);
  display: grid;
  align-content: start;
  gap: 12px;
}

.takeaway-head {
  display: grid;
  gap: 6px;
}

.takeaway-badge {
  width: fit-content;
  padding: 3px 9px;
  border-radius: 999px;
  font-family: var(--font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.takeaway-badge.is-good {
  background: rgba(74, 222, 128, 0.14);
  color: #86efac;
  border: 1px solid rgba(74, 222, 128, 0.35);
}

.takeaway-badge.is-warn {
  background: rgba(255, 196, 107, 0.14);
  color: var(--gold);
  border: 1px solid rgba(255, 196, 107, 0.35);
}

.takeaway-head h4 {
  margin: 0;
  font-size: 1rem;
  font-weight: 500;
  color: var(--ink);
}

.takeaway-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 9px;
  font-size: 0.88rem;
  line-height: 1.5;
  color: #cdd6df;
}

@media (max-width: 960px) {
  .proof-steps {
    grid-template-columns: minmax(0, 1fr);
  }
  .proof-Takeaways {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
