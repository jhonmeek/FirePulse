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

const noaaDiffPct = computed<number | null>(() => {
  const ratio = validation.held_out.noaa20.ratio_noaa20_to_snpp_calibration
  return ratio == null ? null : Math.abs(Math.round((ratio - 1) * 1000) / 10)
})
const frozenOn = validation.mask.frozen_on
const frozenCells = validation.mask.cells_frozen

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
    <p class="proof-review-note" role="note">
      {{
        t(
          "Résultats exploratoires en revue scientifique, non validés. Dans l'artefact affiché, le masque utilise la période de calibration, les mois sans détection ne prouvent pas une couverture complète et le quantile utilisé ne justifie pas une garantie conforme. Les années de test ont déjà été examinées. Les chiffres affichés proviennent de l'artefact initial, antérieur aux corrections de calcul en cours.",
          'Exploratory results under scientific review, not validated. In the displayed artifact, the mask uses the calibration period, months without detections do not prove complete coverage, and the quantile used does not justify a conformal guarantee. The test years have already been examined. The figures shown come from the initial artifact, prior to ongoing calculation fixes.',
        )
      }}
    </p>
    <!-- 3 clear steps replacing jargon-heavy metric tiles -->
    <div class="proof-steps" :aria-label="t('Comment le modèle est testé', 'How the model is tested')">
      <article class="proof-step">
        <span class="proof-step-tag">{{ t('Étape 1 · Apprendre', 'Step 1 · Learn') }}</span>
        <strong class="proof-step-value">2012 – 2019</strong>
        <p class="proof-step-desc">
          {{
            t(
              `Pendant ${trainMonths} mois (8 ans), les deux satellites observent le Gabon en même temps. On s'en sert pour régler la traduction.`,
              `For ${trainMonths} months (8 years), both satellites observe Gabon together. We use this overlap to tune the translation.`,
            )
          }}
        </p>
      </article>

      <article class="proof-step">
        <span class="proof-step-tag">{{ t('Étape 2 · Évaluer', 'Step 2 · Evaluate') }}</span>
        <strong class="proof-step-value">2020 – 2025</strong>
        <p class="proof-step-desc">
          {{
            t(
              `On évalue le modèle sur les ${testMonths} mois suivants (6 ans) à partir du seul ancien capteur. Ces années ont déjà été examinées : c'est une évaluation exploratoire, pas un test à l'aveugle.`,
              `We evaluate the model on the next ${testMonths} months (6 years) using only the older sensor. These years have already been examined: this is an exploratory evaluation, not a blind test.`,
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

    <!-- Observed vs predicted exploratory evaluation chart -->
    <div class="proof-chart-card">
      <div class="proof-chart-head">
        <div>
          <span class="chart-eyebrow">
            {{ t('Évaluation exploratoire · Gabon · 2020–2025', 'Exploratory evaluation · Gabon · 2020–2025') }}
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
          `Protocole exploratoire : masque gelé sur ${frozenOn} (${frozenCells} cellules, période de calibration incluse), apprentissage 2012–2017, calibration 2018–2019, test 2020–2025. L’intervalle expérimental (cible 80 %) couvre ${formatDecimal(coverageQ80 * 100, 1)} % des mois de test : c’est un indicateur, pas une garantie. La série live de la base suit un protocole distinct (masque toutes années, 183 cellules) ; les deux résultats ne sont pas interchangeables.`,
          `Exploratory protocol: mask frozen on ${frozenOn} (${frozenCells} cells, calibration period included), training 2012–2017, calibration 2018–2019, test 2020–2025. The experimental interval (80% target) covers ${formatDecimal(coverageQ80 * 100, 1)}% of test months: an indicator, not a guarantee. The live database series follows a distinct protocol (all-years mask, 183 cells); the two results are not interchangeable.`,
        )
      }}
    </p>

    <!-- Two plain takeaways cards: proof + limits -->
    <div class="proof-Takeaways">
      <article class="takeaway-card">
        <header class="takeaway-head">
          <span class="takeaway-badge is-good">{{ t('Fiabilité', 'Reliability') }}</span>
          <h4>{{ t('Résultats exploratoires', 'Exploratory results') }}</h4>
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
                `Sur les 6 années de test (déjà examinées), l'écart moyen est de ${formatCount(modelMae)} détections par mois.`,
                `Over the 6 test years (already examined), average monthly error is ${formatCount(modelMae)} detections.`,
              )
            }}
          </li>
          <li v-if="noaaDiffPct !== null">
            {{
              t(
                `Un capteur plus récent (VIIRS NOAA-20) donne un niveau proche sur la calibration 2018–2019 (${formatDecimal(noaaDiffPct, 1)} % d'écart) ; son indépendance est limitée par la construction du masque et du ratio.`,
                `A newer sensor (VIIRS NOAA-20) gives a close level over the 2018–2019 calibration (${formatDecimal(noaaDiffPct, 1)}% gap); its independence is limited by how the mask and ratio are built.`,
              )
            }}
          </li>
          <li v-else>
            {{ t('Évaluation NOAA-20 indisponible : ratio de calibration absent.', 'NOAA-20 evaluation unavailable: calibration ratio missing.') }}
          </li>
        </ul>
      </article>

      <article class="takeaway-card">
        <header class="takeaway-head">
          <span class="takeaway-badge is-warn">{{ t('Précautions', 'Limits') }}</span>
          <h4>{{ t('Ce qu’il faut garder en tête', 'What to keep in mind') }}</h4>
        </header>
        <ul class="takeaway-list">
          <li>
            {{
              t(
                'Un point chaud est une alerte thermique vue depuis l’espace, pas une mesure directe de la surface brûlée en hectares.',
                'A hotspot is a heat alert seen from space, not a direct measurement of burned area in hectares.',
              )
            }}
          </li>
          <li>
            {{
              t(
                'Quand le ciel gabonais reste très nuageux ou enfumé, le satellite peut manquer les petits feux sous la canopée.',
                'When skies over Gabon are cloudy or thick with smoke, satellites can miss small fires beneath the canopy.',
              )
            }}
          </li>
          <li>
            {{
              t(
                'Quelques sources industrielles ouvertes après 2019 peuvent apparaître localement tant qu’elles ne sont pas ajoutées au masque. Le masque live utilise toutes les années ; la validation gelée s’arrête à 2019.',
                'A few industrial sources opened after 2019 can show up locally until they are added to the mask. The live mask uses all years; the frozen validation stops in 2019.',
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

.proof-review-note {
  margin: 0;
  padding: 10px 14px;
  border: 1px solid rgba(255, 196, 107, 0.4);
  border-radius: 12px;
  background: rgba(255, 196, 107, 0.06);
  font-size: 0.78rem;
  line-height: 1.55;
  color: var(--muted);
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
