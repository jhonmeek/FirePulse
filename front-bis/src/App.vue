<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from 'vue'
import ChapterNav from '@/components/ChapterNav.vue'
import CalendarHeatmap from '@/components/CalendarHeatmap.vue'
import ConfidenceCard from '@/components/ConfidenceCard.vue'
import CountUp from '@/components/CountUp.vue'
import FlareSplit from '@/components/FlareSplit.vue'
import LineChart from '@/components/LineChart.vue'
import SeasonTimeline from '@/components/SeasonTimeline.vue'
import TopBar from '@/components/TopBar.vue'
import ValidationProof from '@/components/ValidationProof.vue'

// Three.js (~600 Ko) et MapLibre (~800 Ko) sont chargés dans des chunks séparés :
// le récit s'affiche sans attendre les moteurs 3D/carte.
const GlobeScene = defineAsyncComponent(() => import('@/components/GlobeScene.vue'))
const HotspotMap = defineAsyncComponent(() => import('@/components/HotspotMap.vue'))
import { useReducedMotion } from '@/composables/useReducedMotion'
import { useReveal } from '@/composables/useReveal'
import { useSmoothScroll } from '@/composables/useSmoothScroll'
import {
  allSeries,
  buildGlobePoints,
  buildSeriesCsvFallback,
  composition,
  dataSourceMode,
  flareSeries,
  formatCount,
  formatDecimal,
  initLiveData,
  monthlyMedians,
  params,
  staticSeries,
} from '@/lib/data'
import { USE_MOCKS, exportSeriesEndpoint } from '@/lib/api'
import { locale, t } from '@/lib/i18n'
import { provenance } from '@/lib/provenance'
import { validation } from '@/lib/validation'
import { ScrollTrigger, gsap } from '@/lib/motion'

const reducedMotion = useReducedMotion()
useSmoothScroll()
useReveal()

void initLiveData()

const chapters = computed(() => [
  { id: 'top', label: t('Le Gabon', 'Gabon') },
  { id: 'problem', label: t('Le constat', 'The issue') },
  { id: 'translate', label: t('L’accord des données', 'Aligning data') },
  { id: 'calendar', label: t('Le calendrier', 'Calendar') },
  { id: 'map', label: t('La carte', 'Map') },
  { id: 'proof', label: t('Analyse & suite', 'Analysis & next') },
])

const scrollProgress = ref(0)
const scrolled = ref(false)
const activeChapter = ref('top')
const cursor = ref({ x: 0, y: 0 })
const globePoints = computed(() => buildGlobePoints())
const pctSuffix = computed(() => (locale.value === 'en' ? '%' : ' %'))

const ambientGlobeStyle = computed(() => {
  const p = scrollProgress.value
  let opacity = 1
  let tx = 14
  let ty = 0
  let scale = 1

  if (p <= 14) {
    opacity = 1
    tx = 14
    scale = 1
  } else if (p < 58) {
    const tNorm = (p - 14) / 44
    opacity = 1 - tNorm * 0.64
    tx = 14 + tNorm * 12
    ty = -tNorm * 3
    scale = 1 - tNorm * 0.1
  } else if (p < 76) {
    const tNorm = (p - 58) / 18
    opacity = 0.36 * (1 - tNorm)
    tx = 26
    ty = -3
    scale = 0.9 - tNorm * 0.08
  } else {
    opacity = 0
    tx = 26
    ty = -3
    scale = 0.82
  }

  return {
    opacity: opacity.toFixed(3),
    visibility: opacity <= 0.01 ? ('hidden' as const) : ('visible' as const),
    transform: `translate3d(${tx.toFixed(1)}%, ${ty.toFixed(1)}%, 0) scale(${scale.toFixed(3)})`,
  }
})

const chartPoints = computed(() =>
  staticSeries.value.map((p) => ({
    month: p.month,
    raw: (p.modis_count ?? 0) + (p.viirs_snpp_count ?? 0),
    harm: p.harmonized_value,
    lo: p.ci_low,
    hi: p.ci_high,
    // Cette vue additionne deux capteurs : l'anomalie harmonisée ne s'y applique pas.
    anomaly: null,
  })),
)

/**
 * Vues par capteur : chaque série ne commence qu'au premier mois où le capteur
 * est disponible. La courbe harmonisée reste la référence S-NPP.
 */
const modisChartPoints = computed(() =>
  staticSeries.value
    .filter((p) => p.modis_count !== null)
    .map((p) => ({
      month: p.month,
      raw: p.modis_count ?? 0,
      harm: p.harmonized_value,
      lo: p.ci_low,
      hi: p.ci_high,
      // L'anomalie est calculée sur la série harmonisée, pas sur le capteur brut.
      anomaly: null,
    })),
)

const snppChartPoints = computed(() =>
  staticSeries.value
    .filter((p) => p.viirs_snpp_count !== null)
    .map((p) => ({
      month: p.month,
      raw: p.viirs_snpp_count ?? 0,
      harm: p.harmonized_value,
      lo: p.ci_low,
      hi: p.ci_high,
      anomaly: null,
    })),
)

const noaa20ChartPoints = computed(() =>
  staticSeries.value
    .filter((p) => p.viirs_noaa20_count !== null)
    .map((p) => ({
      month: p.month,
      raw: p.viirs_noaa20_count ?? 0,
      harm: p.harmonized_value,
      lo: p.ci_low,
      hi: p.ci_high,
      anomaly: null,
    })),
)

const rawChartPoints = computed(() =>
  allSeries.value.map((p) => ({
    month: p.month,
    raw: (p.modis_count ?? 0) + (p.viirs_snpp_count ?? 0),
    harm: p.harmonized_value,
    lo: p.ci_low,
    hi: p.ci_high,
    anomaly: null,
  })),
)

const flareChartPoints = computed(() =>
  flareSeries.value.map((p) => ({
    month: p.month,
    raw: (p.modis_count ?? 0) + (p.viirs_snpp_count ?? 0),
    harm: null,
    lo: null,
    hi: null,
    anomaly: null,
  })),
)

const rawAllDatasets = computed(() => [
  {
    id: 'all' as const,
    label: t('Tout (MODIS + S-NPP)', 'All (MODIS + S-NPP)'),
    points: rawChartPoints.value,
  },
  {
    id: 'veg' as const,
    label: t('Type 0 hors sources persistantes', 'Type 0 outside persistent sources'),
    points: chartPoints.value,
  },
  {
    id: 'flare' as const,
    label: t('Détections écartées par le filtre', 'Detections excluded by the filter'),
    points: flareChartPoints.value,
  },
])

const harmDatasets = computed(() => [
  {
    id: 'modis' as const,
    label: t('MODIS (entrée du modèle)', 'MODIS (model input)'),
    points: modisChartPoints.value,
  },
  {
    id: 'snpp' as const,
    label: t('VIIRS S-NPP (référence)', 'VIIRS S-NPP (reference)'),
    points: snppChartPoints.value,
  },
  {
    id: 'noaa20' as const,
    label: t('NOAA-20 (relais)', 'NOAA-20 (relay)'),
    points: noaa20ChartPoints.value,
  },
])

const maeBefore = computed(() => validation.models.naive.raw.mae ?? 0)
const maeAfter = computed(() => validation.models.power_law_log1p.raw.mae ?? 0)
const r2After = computed(() => validation.models.power_law_log1p.raw.r2 ?? 0)
const r2Anomaly = computed(() => validation.models.power_law_log1p.anomaly.r2 ?? 0)
const coverageQ80 = computed(() => validation.conformal.coverage_test_q80_calibration)
const maeReduction = computed(() =>
  maeBefore.value > 0 ? Math.round((1 - maeAfter.value / maeBefore.value) * 100) : 0,
)

const globalRatioAlpha = computed(() => params.value?.global_ratio_alpha ?? 3.9328)
const noaaBridgeRatio = computed(() => validation.held_out.noaa20.ratio_noaa20_to_snpp_calibration)
const jumpRatioLabel = computed(() => `×${formatDecimal(globalRatioAlpha.value, 1)}`)

const testMonths = computed(() => validation.split.n_test)
const trainYears = '2012–2019'
const testYears = '2020–2025'

const seasonCards = computed(() => {
  const m = monthlyMedians.value
  const jul = formatCount(m[6] ?? 0)
  const aug = formatCount(m[7] ?? 0)
  const feb = formatCount(m[1] ?? 0)
  const mar = formatCount(m[2] ?? 0)
  const nov = formatCount(m[10] ?? 0)
  const dec = formatCount(m[11] ?? 0)
  const unit = t('/mois', '/mo')
  return [
    {
      label: t('Grande saison sèche', 'Main dry season'),
      months: t('Juillet – Août', 'July – August'),
      values: t(`Juil. : ${jul}${unit} · Août : ${aug}${unit}`, `Jul: ${jul}${unit} · Aug: ${aug}${unit}`),
      note: t(
        'Le cœur de la saison des feux : sols secs, brûlis agricoles et feux de lisière.',
        'Peak fire season across Gabon: dry ground, farm clearing, and forest-edge fires.',
      ),
      tone: 'hot',
    },
    {
      label: t('Petite saison sèche', 'Short dry season'),
      months: t('Février – Mars', 'February – March'),
      values: t(`Fév. : ${feb}${unit} · Mar. : ${mar}${unit}`, `Feb: ${feb}${unit} · Mar: ${mar}${unit}`),
      note: t(
        'Une reprise courte mais régulière des feux au nord et au centre du pays.',
        'A brief but consistent rebound in northern and central Gabon.',
      ),
      tone: 'warm',
    },
    {
      label: t('Saison des pluies', 'Peak rainy season'),
      months: t('Novembre – Décembre', 'November – December'),
      values: t(`Nov. : ${nov}${unit} · Déc. : ${dec}${unit}`, `Nov: ${nov}${unit} · Dec: ${dec}${unit}`),
      note: t(
        'Les fortes pluies étouffent les feux presque partout ; il ne reste guère que les sources de chaleur persistantes de la côte.',
        'Heavy rainfall halts vegetation burning almost everywhere; coastal persistent heat sources remain.',
      ),
      tone: 'cool',
    },
  ]
})

function navigate(id: string) {
  const el = document.getElementById(id)
  if (!el) return
  const top = el.getBoundingClientRect().top + window.scrollY - 74
  window.scrollTo({ top, behavior: reducedMotion.value ? 'auto' : 'smooth' })
}

function updateScroll() {
  const y = window.scrollY
  const doc = document.documentElement.scrollHeight - window.innerHeight
  scrollProgress.value = doc > 0 ? Math.min(100, (y / doc) * 100) : 0
  scrolled.value = y > 40
  const mid = y + window.innerHeight * 0.38
  let current = 'top'
  for (const chapter of chapters.value) {
    const el = document.getElementById(chapter.id)
    if (el && el.offsetTop <= mid) current = chapter.id
  }
  activeChapter.value = current
}

let ticking = false
function onScroll() {
  if (ticking) return
  ticking = true
  requestAnimationFrame(() => {
    updateScroll()
    ticking = false
  })
}

function onPointerMove(event: PointerEvent) {
  cursor.value = { x: event.clientX, y: event.clientY }
}

async function downloadCsv() {
  let blob: Blob | null = null
  if (!USE_MOCKS) {
    try {
      const res = await fetch(exportSeriesEndpoint('GA', true))
      if (res.ok) {
        blob = await res.blob()
      }
    } catch {
      // Repli transparent sur la génération locale aux colonnes exactes du contrat API.
    }
  }
  if (!blob) {
    const csv = buildSeriesCsvFallback(staticSeries.value, 'GA', true)
    blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  }
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'firepulse-calendrier-GA-2000-2025.csv'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

onMounted(() => {
  updateScroll()
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('pointermove', onPointerMove, { passive: true })
  if (!reducedMotion.value) {
    gsap.from('.hero-title .line > span', {
      yPercent: 115,
      duration: 1.25,
      ease: 'power3.out',
      stagger: 0.12,
      delay: 0.15,
    })
    gsap.from('.hero-kicker, .hero-sub, .hero-actions, .hero-meta, .scroll-hint', {
      opacity: 0,
      y: 22,
      duration: 0.9,
      ease: 'power2.out',
      stagger: 0.1,
      delay: 0.6,
    })
  }
  document.fonts?.ready.then(() => ScrollTrigger.refresh())
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('pointermove', onPointerMove)
})
</script>

<template>
  <div id="top" class="app">
    <a class="skip-link" href="#calendar" @click.prevent="navigate('calendar')">
      {{ t('Aller au calendrier du Gabon', 'Jump to Gabon fire calendar') }}
    </a>
    <div class="site-bg" aria-hidden="true"></div>
    <div class="ambient-globe" :style="ambientGlobeStyle" aria-hidden="true">
      <GlobeScene :points="globePoints" :reduced-motion="reducedMotion" />
    </div>
    <div class="grain" aria-hidden="true"></div>
    <div class="vignette" aria-hidden="true"></div>
    <div
      class="cursor-glow"
      aria-hidden="true"
      :style="{ left: `${cursor.x}px`, top: `${cursor.y}px` }"
    ></div>

    <TopBar :scrolled="scrolled" :progress="scrollProgress" @navigate="navigate" />
    <ChapterNav :chapters="chapters" :active="activeChapter" @navigate="navigate" />

    <main>
      <!-- ============================================================ HERO -->
      <section class="hero">
        <div class="shell hero-inner">
          <div class="hero-copy">
            <p class="hero-badge">
              <span class="hero-badge-dot" aria-hidden="true" />
              {{ t('Gabon · 2000 – 2025', 'Gabon · 2000 – 2025') }}
            </p>
            <h1 class="display display-xl hero-title">
              <span class="line"><span>{{ t('Au Gabon, lire', 'In Gabon, read') }}</span></span>
              <span class="line">
                <span>{{ t('la vraie saison ', 'the true fire ') }}<em>{{ t('des feux.', 'season.') }}</em></span>
              </span>
            </h1>
            <p class="hero-sub">
              {{
                t(
                  'Deux générations de satellites et des sources de chaleur persistantes faussent les chiffres bruts. ',
                  'Two satellite generations and persistent heat sources distort the raw counts. ',
                )
              }}
              <strong>
                {{
                  t(
                    'Voici 25 ans de mesures remises au propre — mois par mois, sur les 9 provinces.',
                    'Here are 25 years cleaned up — month by month across all 9 provinces.',
                  )
                }}
              </strong>
            </p>
            <div class="hero-actions">
              <button type="button" class="btn btn-heat" @click="navigate('calendar')">
                {{ t('Explorer le calendrier des feux', 'Explore the fire calendar') }}
                <span aria-hidden="true">→</span>
              </button>
            </div>

            <div class="hero-meta hero-meta-pair">
              <div>
                <div class="value">
                  <CountUp :to="composition.gaClean" :reduced-motion="reducedMotion" />
                </div>
                <div class="label">{{ t('détections type 0 hors sources persistantes', 'type-0 detections outside persistent sources') }}</div>
              </div>
              <div>
                <div class="value">
                  {{ formatCount(composition.gaExcluded) }}
                  <span class="value-sub">({{ formatDecimal(composition.gaExcludedShare, 1) }}{{ pctSuffix }})</span>
                </div>
                <div class="label">{{ t('détections écartées par le filtre complet', 'detections excluded by the full filter') }}</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ============================================================ 01 : DOUBLE TRAP -->
      <section id="problem" class="chapter">
        <div class="shell chapter-grid">
          <div class="chapter-copy">
            <p class="kicker reveal">01 — {{ t('Le constat', 'The issue') }}</p>
            <h2 class="display display-lg reveal reveal-delay-1">
              {{ t('En 2012, la courbe bondit.', 'In 2012, the curve spikes.') }}<br />
              <em>{{ t('Les feux au Gabon, non.', 'Fires in Gabon did not.') }}</em>
            </h2>
            <p class="lede reveal reveal-delay-2">
              {{
                t(
                  'Un point chaud est une alerte de chaleur vue depuis l’espace. Jusqu’en 2011, le satellite MODIS voyait le Gabon à grands traits (',
                  'A hotspot is a heat alert seen from space. Until 2011, the older MODIS satellite scanned Gabon coarsely (',
                )
              }}<strong>1 km</strong>{{
                t('). En 2012, VIIRS prend le relais avec une vue bien plus fine (', '). In 2012, VIIRS took over with much sharper detail (')
              }}<strong>375 m</strong>{{
                t(
                  '). Sur les chiffres bruts, on croit à quatre fois plus de détections alors que la caméra a simplement gagné en netteté.',
                  '). Raw counts suddenly appear four times higher—not from more fires, just a sharper camera.',
                )
              }}
            </p>

            <div class="stat-row reveal reveal-delay-3">
              <div>
                <div class="stat">{{ jumpRatioLabel }}</div>
                <div class="stat-label">
                  {{ t('de saut apparent lors du changement de satellite en 2012', 'apparent jump when switching satellites in 2012') }}
                </div>
              </div>
              <div>
                <div class="stat stat-small">2 {{ t('satellites', 'satellites') }}</div>
                <div class="stat-label">
                  {{ t('observent le Gabon en parallèle entre 2012 et 2025', 'observe Gabon side by side between 2012 and 2025') }}
                </div>
              </div>
            </div>
          </div>

          <div class="chapter-visual reveal reveal-delay-2">
            <div class="panel panel-pad">
              <div class="panel-label">
                <span class="tiny-label">
                  {{ t('Chiffres bruts · Gabon · 2001–2025', 'Raw counts · Gabon · 2001–2025') }}
                </span>
                <span class="tag dot">{{ t('Interactif', 'Interactive') }}</span>
              </div>
              <LineChart
                :datasets="rawAllDatasets"
                initial-dataset-id="all"
                default-granularity="year"
                :show-raw="true"
                :show-harmonized="false"
                :show-anomaly="false"
                :highlight2012="true"
                :reduced-motion="reducedMotion"
                :title="t('Détections brutes au Gabon', 'Raw detections in Gabon')"
                :raw-label="t('Détections brutes (avant correction)', 'Raw detections (uncorrected)')"
              />
              <p class="panel-caption">
                {{
                  t(
                    'Les boutons séparent le tout (MODIS + S-NPP), les type 0 hors sources persistantes, et les détections écartées par le filtre. La somme MODIS + S-NPP n’est pas un nombre de feux : après 2012, les deux capteurs voient souvent les mêmes départs.',
                    'The buttons separate everything (MODIS + S-NPP), type-0 detections outside persistent sources, and detections excluded by the filter. MODIS + S-NPP is not a fire count: after 2012, both sensors often see the same ignitions.',
                  )
                }}
              </p>
            </div>
          </div>
        </div>

        <div id="flares" class="shell chapter-grid reverse trap-subsection">
          <div class="chapter-visual reveal reveal-delay-2">
            <div class="panel panel-pad">
              <div class="panel-label">
                <span class="tiny-label">
                  {{ t('Gabon entier · 2000–2025 · 285 013 détections', 'Whole Gabon · 2000–2025 · 285,013 detections') }}
                </span>
                <span class="tag cool">{{ t('Impact des sources persistantes', 'Persistent source impact') }}</span>
              </div>
              <FlareSplit />
            </div>
          </div>

          <div class="chapter-copy">
            <p class="kicker reveal">{{ t('Piège n°2 — Les sources persistantes', 'Trap #2 — Persistent sources') }}</p>
            <h2 class="display display-lg reveal reveal-delay-1">
              {{ t('Sur la côte gabonaise,', 'Along Gabon’s coast,') }}<br />
              <em>{{ t('des sources de chaleur brûlent toute l’année.', 'heat sources burn all year round.') }}</em>
            </h2>
            <p class="lede reveal reveal-delay-2">
              {{
                t(
                  `Sur ${formatCount(composition.gaTotal)} détections mesurées au Gabon, `,
                  `Out of ${formatCount(composition.gaTotal)} detections recorded in Gabon, `,
                )
              }}<strong>{{ formatDecimal(composition.gaExcludedShare, 1) }}{{ pctSuffix }}</strong>
              ({{ formatCount(composition.gaExcluded) }})
              {{
                t(
                  ` sont écartées par le filtre complet : ${formatCount(composition.gaType23Count)} détections type 2/3 (${formatDecimal(composition.gaType23Share, 1)} %, sources fixes ou offshore) et ${formatCount(composition.gaType0InMaskCount)} détections type 0 tombées dans ${composition.maskedCells} cellules candidates (${formatDecimal(composition.gaType0InMaskShare, 1)} %, ~5 km), surtout autour de Port-Gentil et de la côte de l’Ogooué-Maritime. Toutes ne sont pas des torchères confirmées.`,
                  ` are excluded by the full filter: ${formatCount(composition.gaType23Count)} type 2/3 detections (${formatDecimal(composition.gaType23Share, 1)}%, fixed or offshore sources) and ${formatCount(composition.gaType0InMaskCount)} type-0 detections inside ${composition.maskedCells} candidate cells (${formatDecimal(composition.gaType0InMaskShare, 1)}%, ~5 km), mostly around Port-Gentil and coastal Ogooué-Maritime. Not all of them are confirmed flares.`,
                )
              }}
            </p>

            <div class="stat-row reveal reveal-delay-3">
              <div>
                <div class="stat stat-small">{{ formatCount(composition.gaClean) }}</div>
                <div class="stat-label">
                  {{ t('détections type 0 hors sources persistantes (61,6 % du total)', 'type-0 detections outside persistent sources (61.6% of total)') }}
                </div>
              </div>
              <div>
                <div class="stat stat-small">{{ composition.maskedCells }}</div>
                <div class="stat-label">
                  {{ t('cellules candidates (~5 km) mises à part', 'candidate cells (~5 km) set aside') }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ============================================================ 02 : HARMONIZATION -->
      <section id="translate" class="chapter">
        <div class="shell chapter-grid">
          <div class="chapter-copy">
            <p class="kicker reveal">02 — {{ t('L’accord des données', 'Aligning data') }}</p>
            <h2 class="display display-lg reveal reveal-delay-1">
              {{ t('Remettre 25 ans de chiffres', 'Put 25 years of data') }}<br />
              <em>{{ t('sur la même échelle.', 'on the same scale.') }}</em>
            </h2>
            <p class="lede reveal reveal-delay-2">
              {{
                t(
                  `Entre ${trainYears}, l’ancien et le nouveau satellite ont observé le Gabon ensemble pendant 8 ans. Nous utilisons cet écart mesuré pour rehausser les chiffres d’avant 2012, puis nous vérifions la précision sur les 6 dernières années (${testYears}).`,
                  `During ${trainYears}, both the old and new satellites watched Gabon together for 8 years. We use that overlap to adjust pre-2012 data upward, then verify accuracy on the last 6 years (${testYears}).`,
                )
              }}
            </p>

            <ol class="steps reveal reveal-delay-3">
              <li>
                <span class="step-index">01</span>
                <div>
                  <strong>{{ t('Écarter les sources persistantes candidates', 'Set aside candidate persistent sources') }}</strong>
                  <span>{{ t(`Le filtre complet retire les types 2/3 et les type 0 dans ${composition.maskedCells} cellules candidates. Toutes ne sont pas des torchères confirmées.`, `The full filter removes type 2/3 and type-0 detections inside ${composition.maskedCells} candidate cells. Not all of them are confirmed flares.`) }}</span>
                </div>
              </li>
              <li>
                <span class="step-index">02</span>
                <div>
                  <strong>{{ t('Ajuster les années 2000–2011', 'Adjust years 2000–2011') }}</strong>
                  <span>{{ t('MODIS est converti vers l’échelle S-NPP. Après 2012, S-NPP reste la référence observée, pas une estimation.', 'MODIS is mapped onto the S-NPP scale. After 2012, S-NPP remains the observed reference, not an estimate.') }}</span>
                </div>
              </li>
              <li>
                <span class="step-index">03</span>
                <div>
                  <strong>{{ t('Afficher la marge d’incertitude', 'Show the uncertainty margin') }}</strong>
                  <span>{{ t('La bande vient de la baseline DB v2.0 ; sa couverture n’est pas établie. L’analyse exploratoire rapporte 63,9 % pour son propre intervalle (cible 80 %) : un indicateur, pas une garantie.', 'The band comes from the DB v2.0 baseline; its coverage is not established. The exploratory analysis reports 63.9% for its own interval (80% target): an indicator, not a guarantee.') }}</span>
                </div>
              </li>
            </ol>

            <div class="stat-row reveal reveal-delay-4">
              <div>
                <div class="stat">−{{ maeReduction }}{{ pctSuffix }}</div>
                <div class="stat-label">{{ t('d’erreur moyenne (validation renforcée, 2020–2025)', 'less average error (reinforced validation, 2020–2025)') }}</div>
              </div>
              <div>
                <div class="stat stat-small">
                  R² {{ formatDecimal(r2After, 2) }}
                </div>
                <div class="stat-label">{{ t(`brut sur ${testMonths} mois ; ${formatDecimal(r2Anomaly, 2)} sur les anomalies`, `raw over ${testMonths} months; ${formatDecimal(r2Anomaly, 2)} on anomalies`) }}</div>
              </div>
            </div>
          </div>

          <div class="chapter-visual reveal reveal-delay-2">
            <div class="panel panel-pad">
              <div class="panel-label">
                <span class="tiny-label">{{ t('Avant / après correction · Gabon', 'Before / after adjustment · Gabon') }}</span>
                <span class="tag dot">{{ t('2001–2025', '2001–2025') }}</span>
              </div>
              <LineChart
                :datasets="harmDatasets"
                initial-dataset-id="modis"
                default-granularity="year"
                :show-raw="true"
                :show-harmonized="true"
                :show-band="true"
                :show-anomaly="false"
                :highlight2012="true"
                mark-month="2024-08"
                :reduced-motion="reducedMotion"
                :title="t('Chaque capteur séparément, puis la série harmonisée', 'Each sensor separately, then the harmonized series')"
                :raw-label="t('Détections brutes du capteur sélectionné', 'Raw detections for the selected sensor')"
                :harm-label="t('Série harmonisée expérimentale (échelle S-NPP)', 'Experimental harmonized series (S-NPP scale)')"
              />
              <p class="panel-caption">
                {{
                  t(
                    'MODIS est l’entrée du modèle ; VIIRS S-NPP est la référence cible. Changez de capteur pour voir ce que chaque instrument observe vraiment : la rupture de 2012 est un changement de caméra, pas un pic de feux. Après 2012, MODIS continue de voler mais reste moins sensible ; la série orangée suit S-NPP.',
                    'MODIS is the model input; VIIRS S-NPP is the target reference. Switch sensors to see what each instrument actually observes: the 2012 break is a camera change, not a fire spike. After 2012, MODIS keeps flying but is less sensitive; the orange series follows S-NPP.',
                  )
                }}
              </p>
              <ConfidenceCard compact context="series" />
            </div>
          </div>
        </div>
      </section>

      <!-- ============================================================ 03 : CALENDAR -->
      <section id="calendar" class="chapter">
        <div class="shell">
          <div class="section-head">
            <div>
              <p class="kicker reveal">03 — {{ t('Le calendrier', 'The fire calendar') }}</p>
              <h2 class="display display-lg reveal reveal-delay-1">
                {{ t('La vraie saison des feux au Gabon.', 'Gabon’s true fire season.') }}
              </h2>
            </div>
            <p class="lede reveal reveal-delay-2">
              {{
                t(
                  'Chaque case représente un mois au Gabon de 2000 à 2025 : plus la couleur est sombre, plus il y a eu de détections. Utilisez les 4 filtres ci-dessous pour comparer les type 0 hors sources persistantes, les brûlis habituels vs flambées anormales, ou les détections écartées par le filtre.',
                  'Each cell is one month in Gabon from 2000 to 2025: darker cells mean more detections. Use the 4 filters below to switch between type 0 outside persistent sources, routine vs unusual surges, or detections excluded by the filter.',
                )
              }}
            </p>
          </div>

          <div class="calendar-shell reveal reveal-delay-2">
            <div class="calendar-head">
              <div class="calendar-head-left">
                <span class="tag dot">{{ t('Calendrier Gabon · Années × Mois', 'Gabon Calendar · Years × Months') }}</span>
                <span class="tiny-label">{{ t('Cliquez un mois pour l’épingler', 'Click any month to pin details') }}</span>
              </div>
              <button type="button" class="btn btn-ghost btn-small" @click="downloadCsv">
                {{ t('Télécharger le CSV', 'Download CSV') }}
              </button>
            </div>
            <CalendarHeatmap :reduced-motion="reducedMotion" />
          </div>

          <div class="season-cards-head reveal">
            <h3>{{ t('Les 3 temps du feu au Gabon', 'Gabon’s 3 fire seasons') }}</h3>
            <p>
              {{
                t(
                  'Médiane mensuelle calculée sur 25 années complètes (2001–2025, type 0 hors sources persistantes).',
                  'Median monthly counts measured across 25 full years (2001–2025, type 0 outside persistent sources).',
                )
              }}
            </p>
          </div>

          <div class="feature-grid">
            <article
              v-for="card in seasonCards"
              :key="card.label"
              class="feature-card reveal"
              :class="card.tone"
            >
              <span class="feature-label">{{ card.label }}</span>
              <h3>{{ card.months }}</h3>
              <p class="feature-values">{{ card.values }}</p>
              <p class="feature-note">{{ card.note }}</p>
            </article>
          </div>
        </div>
      </section>

      <!-- ============================================================ 04 : MAP -->
      <section id="map" class="chapter">
        <div class="shell">
          <div class="section-head">
            <div>
              <p class="kicker reveal">04 — {{ t('Le territoire', 'The territory') }}</p>
              <h2 class="display display-lg reveal reveal-delay-1">
                {{ t('Où ça brûle, province par province.', 'Where fires burn, province by province.') }}
              </h2>
            </div>
            <p class="lede reveal reveal-delay-2">
              {{
                t(
                  `En orange : les zones de détections type 0 (~28 km). En bleu : les ${composition.maskedCells} cellules candidates (~5 km) de sources persistantes, surtout sur la côte et en mer. Sélectionnez une province pour une lecture descriptive ; la calibration harmonisée reste nationale et n’est pas revalidée par polygone.`,
                  `Orange squares (~28 km) map type-0 detections. Blue cells (~5 km) mark ${composition.maskedCells} candidate persistent sources, mostly coastal and offshore. Choose a province for a descriptive read; the harmonized calibration stays national and is not revalidated per polygon.`,
                )
              }}
            </p>
          </div>

          <div class="map-shell reveal reveal-delay-2">
            <HotspotMap :reduced-motion="reducedMotion" />
          </div>

          <ConfidenceCard compact context="map" />

          <div class="geo-cards-grid reveal reveal-delay-3">
            <article class="geo-card is-flare">
              <span class="geo-card-tag">{{ t('Cellules bleues sur la carte', 'Blue cells on map') }}</span>
              <h3>{{ t('Côte Ouest & Mer', 'West Coast & Offshore') }}</h3>
              <p class="geo-card-provinces">Ogooué-Maritime · Estuaire</p>
              <p class="geo-card-desc">
                {{
                  t(
                    'Zones pétrolières et industrielles (Port-Gentil, Gamba, plateformes) où des sources de chaleur persistent toute l’année, sans lien avec les saisons agricoles. Ce sont des cellules candidates, pas des torchères confirmées une par une.',
                    'Oil and industrial zones (Port-Gentil, Gamba, offshore rigs) where heat sources persist year-round, unrelated to seasonal field clearing. These are candidate cells, not individually confirmed flares.',
                  )
                }}
              </p>
            </article>

            <article class="geo-card is-savanna">
              <span class="geo-card-tag">{{ t('Grands carrés orangés', 'Large orange squares') }}</span>
              <h3>{{ t('Sud & Sud-Est', 'South & South-East') }}</h3>
              <p class="geo-card-provinces">Haut-Ogooué · Nyanga · Ngounié</p>
              <p class="geo-card-desc">
                {{
                  t(
                    'Grandes savanes et plateaux où se concentre l’essentiel des feux de saison sèche entre juin et septembre.',
                    'Open savannas and plateaus where the bulk of Gabon’s dry-season burning concentrates between June and September.',
                  )
                }}
              </p>
            </article>

            <article class="geo-card is-forest">
              <span class="geo-card-tag">{{ t('Activité dispersée', 'Scattered activity') }}</span>
              <h3>{{ t('Centre & Nord', 'Center & North') }}</h3>
              <p class="geo-card-provinces">Ogooué-Ivindo · Woleu-Ntem · Moyen-Ogooué · Ogooué-Lolo</p>
              <p class="geo-card-desc">
                {{
                  t(
                    'Forêts denses plus humides : les alertes y restent plus rares et suivent surtout les petits brûlis agricoles autour des villages et routes.',
                    'Wetter rainforest interior: detections remain lighter and mostly track small farm clearings near roads and settlements.',
                  )
                }}
              </p>
            </article>
          </div>

          <div class="map-cta-bar reveal reveal-delay-3">
            <p>
              {{
                t(
                  'Besoin des chiffres mensuels complets du Gabon pour vos analyses ou présentations ?',
                  'Need Gabon’s full monthly fire series for your own reports or spreadsheets?',
                )
              }}
            </p>
            <div class="map-cta-actions">
              <button type="button" class="btn btn-heat btn-small" @click="downloadCsv">
                {{ t('Télécharger le CSV (Gabon 2000–2025)', 'Download CSV (Gabon 2000–2025)') }}
              </button>
              <button type="button" class="btn btn-ghost btn-small" @click="navigate('calendar')">
                {{ t('Revenir au calendrier', 'Back to calendar') }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- ============================================================ 05 : PROOF & TOMORROW -->
      <section id="proof" class="chapter proof-final">
        <div class="shell">
          <div class="section-head">
            <div>
              <p class="kicker reveal">05 — {{ t('Analyse & suite', 'Analysis & next') }}</p>
              <h2 class="display display-lg reveal reveal-delay-1">
                {{ t('Évalué sur 2020–2025.', 'Evaluated on 2020–2025.') }}<br />
                <em>{{ t('Les limites sont publiées.', 'The limits are published.') }}</em>
              </h2>
            </div>
            <p class="lede reveal reveal-delay-2">
              {{
                t(
                  'Nous avons évalué la méthode sur 6 années complètes (2020–2025), déjà examinées pendant sa mise au point. Ces résultats exploratoires sont en revue scientifique : voici ce qu’ils montrent et ce qu’ils ne mesurent pas.',
                  'We evaluated the method over 6 full years (2020–2025), already examined during its development. These exploratory results are under scientific review: here is what they show and what they do not measure.',
                )
              }}
            </p>
          </div>

          <ValidationProof :reduced-motion="reducedMotion" />

          <ConfidenceCard context="series" />

          <div id="future" class="future-subsection">
            <div class="section-head">
              <div>
                <p class="kicker reveal">{{ t('Le relais 2026', 'The 2026 relay') }}</p>
                <h3 class="display display-md reveal reveal-delay-1">
                  {{ t('Le satellite de référence s’est arrêté le 2 novembre 2026.', 'The reference satellite stopped on November 2, 2026.') }}
                  <em>{{ t('Le relais est préparé, pas encore démontré sur 2026.', 'The relay is prepared, not yet demonstrated on 2026.') }}</em>
                </h3>
              </div>
              <p class="lede reveal reveal-delay-2">
                {{
                  t(
                    'L’archive de cette démonstration s’arrête en décembre 2025. NOAA-20 est calibré sur la période commune 2018–2019 ; ingérer les alertes 2026 et vérifier la continuité du relais restent les prochaines étapes.',
                    'This demo archive ends in December 2025. NOAA-20 is calibrated over the 2018–2019 overlap; ingesting 2026 alerts and verifying relay continuity remain the next steps.',
                  )
                }}
              </p>
            </div>

            <div class="reveal reveal-delay-2">
              <SeasonTimeline
                :archive-end="provenance.archiveEnd"
                :noaa-bridge-ratio="noaaBridgeRatio"
                :reduced-motion="reducedMotion"
              />
            </div>

            <div class="roadmap">
              <article class="roadmap-card reveal">
                <span class="roadmap-horizon">{{ t('2026+', '2026+') }}</span>
                <h3>{{ t('Suivre avec NOAA-20', 'Track with NOAA-20') }}</h3>
                <p>
                  {{
                    t(
                      'Le ratio de calibration est mesuré. Il reste à ingérer les alertes 2026 et à vérifier la continuité sur des données réelles, pas seulement sur la période commune.',
                      'The calibration ratio is measured. Next: ingest 2026 alerts and verify continuity on real data, not only over the overlap period.',
                    )
                  }}
                </p>
                <span class="tag">{{ t('À valider', 'To validate') }}</span>
              </article>
              <article class="roadmap-card reveal reveal-delay-1">
                <span class="roadmap-horizon">{{ t('Régional', 'Regional') }}</span>
                <h3>{{ t('Étendre au Bassin du Congo', 'Expand to the Congo Basin') }}</h3>
                <p>
                  {{
                    t(
                      'Appliquer la même séparation sources persistantes / type 0 aux pays forestiers voisins du Gabon.',
                      'Apply the same persistent-source / type-0 separation across neighboring Congo Basin forest nations.',
                    )
                  }}
                </p>
                <span class="tag">{{ t('Prochaine étape', 'Next step') }}</span>
              </article>
              <article class="roadmap-card reveal reveal-delay-2">
                <span class="roadmap-horizon">{{ t('Terrain', 'Impact') }}</span>
                <h3>{{ t('Mesurer l’intensité des feux', 'Measure fire intensity') }}</h3>
                <p>
                  {{
                    t(
                      'En plus du nombre d’alertes, suivre la chaleur dégagée par les feux pour repérer les épisodes vraiment destructeurs.',
                      'Track heat energy released per detection alongside counts to spot unusually intense burns.',
                    )
                  }}
                </p>
                <span class="tag">{{ t('À venir', 'Planned') }}</span>
              </article>
            </div>
          </div>
        </div>
      </section>
    </main>

    <footer class="footer">
      <div class="shell">
        <div class="footer-grid">
          <div>
            <a class="brand" href="#top" @click.prevent="navigate('top')">
              <span class="brand-name">FirePulse</span>
            </a>
            <p class="footer-lede">
              {{
                t(
                  'Outil d’observation des saisons de feux au Gabon et dans ses 9 provinces, à partir des satellites ouverts de la NASA (2000–2025).',
                  'Open observation tool tracking Gabon’s fire seasons across all 9 provinces using NASA satellite archives (2000–2025).',
                )
              }}
            </p>
            <p class="footer-note">
              {{ t('Archive vérifiée (SHA-256) :', 'Verified archive (SHA-256):') }}
              <strong>{{
                dataSourceMode === 'live'
                  ? t('API Django et instantanés locaux, provenance variable', 'Django API and local snapshots, provenance varies')
                  : t('API partielle ou instantanés locaux, provenance variable', 'Partial API or local snapshots, provenance varies')
              }}</strong>
              — {{ formatCount(composition.gaTotal) }}
              {{
                t(
                  `détections au Gabon (2000–2025) : ${formatCount(composition.gaClean)} type 0 hors sources persistantes, ${formatCount(composition.gaExcluded)} écartées par le filtre complet (type 2/3 + ${composition.maskedCells} cellules candidates).`,
                  `detections inside Gabon (2000–2025): ${formatCount(composition.gaClean)} type 0 outside persistent sources, ${formatCount(composition.gaExcluded)} excluded by the full filter (type 2/3 + ${composition.maskedCells} candidate cells).`,
                )
              }}
            </p>
          </div>
          <div>
            <h3>{{ t('Sources des données', 'Data sources') }}</h3>
            <ul>
              <li>
                <a href="https://firms.modaps.eosdis.nasa.gov/" target="_blank" rel="noreferrer">
                  NASA FIRMS (MODIS & VIIRS)
                </a>
              </li>
              <li>
                <a
                  href="https://www.spaceappschallenge.org/"
                  target="_blank"
                  rel="noreferrer"
                >
                  NASA Space Apps Challenge
                </a>
              </li>
              <li>{{ t('Limites provinciales du Gabon (9 provinces)', 'Gabon provincial boundaries (9 provinces)') }}</li>
              <li>{{ t('Évaluation exploratoire sur 72 mois (2020–2025)', 'Exploratory evaluation over 72 months (2020–2025)') }}</li>
            </ul>
          </div>
          <div>
            <h3>{{ t('À retenir', 'Key notes') }}</h3>
            <ul>
              <li>{{ t('Un point chaud = une alerte de chaleur vue depuis l’espace', 'One hotspot = one heat alert seen from space') }}</li>
              <li>{{ t('Les sources de chaleur persistantes candidates sont isolées pour ne pas fausser les saisons', 'Candidate persistent heat sources are isolated to keep seasons accurate') }}</li>
              <li>{{ t('Code, pipeline et documentation bilingue assistés par IA (Gemini 4 Hydrogen, Gemini 4 Argon, Deepseek 4.1 Flash 1017, Claude Opus 5.5, GPT 6 Luna & GPT 6 Terra) ; données NASA FIRMS authentiques', 'Code, pipeline & bilingual docs assisted by AI (Gemini 4 Hydrogen, Gemini 4 Argon, Deepseek 4.1 Flash 1017, Claude Opus 5.5, GPT 6 Luna & GPT 6 Terra); authentic NASA FIRMS data') }}</li>
              <li>{{ t('Projet prototype — non affilié ni certifié par la NASA', 'Prototype project — not affiliated with or endorsed by NASA') }}</li>
            </ul>
          </div>
        </div>
        <div class="footer-bottom">
          <span>FirePulse · {{ t('Gabon 2000–2025', 'Gabon 2000–2025') }}</span>
          <span>{{ t('Type 0 hors sources persistantes vs sources candidates', 'Type 0 outside persistent sources vs candidate sources') }}</span>
          <span>{{ t('Données ouvertes NASA FIRMS', 'Open NASA FIRMS data') }}</span>
        </div>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.app {
  position: relative;
  overflow-x: clip;
}

.skip-link {
  position: fixed;
  top: 10px;
  left: 10px;
  z-index: 100;
  padding: 10px 14px;
  border-radius: 8px;
  background: var(--ink);
  color: #0a0a0a;
  font-size: 0.82rem;
  font-weight: 600;
  transform: translateY(-220%);
  transition: transform 0.25s var(--ease-out);
}

.skip-link:focus {
  transform: translateY(0);
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid rgba(255, 196, 107, 0.34);
  background: rgba(255, 196, 107, 0.08);
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--gold);
  width: fit-content;
}

.hero-badge-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--gold);
  box-shadow: 0 0 10px rgba(255, 196, 107, 0.75);
}

.hero-meta-pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, max-content));
  gap: 24px 44px;
}

.value-sub {
  font-size: 0.62em;
  color: var(--gold);
  font-weight: 400;
  margin-left: 4px;
}

.chapter-note {
  margin-top: 24px;
  padding-left: 14px;
  border-left: 2px solid rgba(255, 196, 107, 0.45);
  font-size: 0.78rem;
  line-height: 1.6;
  color: var(--dim);
  max-width: 52ch;
}

.chapter-note strong {
  color: var(--muted);
  font-weight: 500;
}

.benchmark-note {
  margin-top: 14px;
  max-width: 60ch;
  font-family: var(--font-mono);
  font-size: 0.56rem;
  line-height: 1.65;
  letter-spacing: 0.02em;
  color: var(--dim);
}

.stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: 28px 46px;
  margin-top: 32px;
  padding-top: 22px;
  border-top: 1px solid var(--line);
}

.panel-caption {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  font-size: 0.68rem;
  line-height: 1.6;
  color: var(--dim);
}

.steps {
  display: grid;
  gap: 0;
  margin-top: 28px;
  border-top: 1px solid var(--line);
}

.steps li {
  display: flex;
  gap: 16px;
  padding: 14px 0;
  border-bottom: 1px solid var(--line);
}

.step-index {
  flex: none;
  font-family: var(--font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.08em;
  color: var(--gold);
}

.steps strong {
  display: block;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--ink);
}

.steps span:not(.step-index) {
  display: block;
  margin-top: 3px;
  font-size: 0.72rem;
  line-height: 1.55;
  color: var(--dim);
}

.section-head {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  gap: 32px 64px;
  align-items: end;
  margin-bottom: 34px;
}

.section-head .lede {
  margin-top: 0;
  max-width: 56ch;
}

.calendar-shell {
  padding: clamp(16px, 2.4vw, 28px);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background:
    linear-gradient(180deg, rgba(244, 241, 232, 0.035), transparent 30%),
    var(--panel);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.04) inset,
    0 40px 100px -60px rgba(0, 0, 0, 0.9);
}

.calendar-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px 20px;
  margin-bottom: 18px;
}

.calendar-head-left {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.calendar-note {
  margin-top: 12px;
  max-width: 80ch;
  font-size: 0.66rem;
  line-height: 1.6;
  color: var(--dim);
}

.season-cards-head {
  margin-top: 28px;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: baseline;
  gap: 6px 18px;
}

.season-cards-head h3 {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 500;
  color: var(--ink);
}

.season-cards-head p {
  margin: 0;
  font-size: 0.82rem;
  color: var(--muted);
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 12px;
}

.feature-card {
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: rgba(244, 241, 232, 0.025);
}

.feature-label {
  font-family: var(--font-mono);
  font-size: 0.54rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--dim);
}

.feature-card h3 {
  margin-top: 7px;
  font-family: var(--font-display);
  font-size: 1.25rem;
  font-weight: 400;
  letter-spacing: -0.02em;
}

.feature-values {
  margin-top: 6px;
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--gold);
}

.feature-note {
  margin-top: 6px;
  font-size: 0.68rem;
  line-height: 1.5;
  color: var(--dim);
}

.feature-card.hot {
  border-color: rgba(255, 122, 61, 0.28);
  background: linear-gradient(160deg, rgba(255, 122, 61, 0.08), transparent 70%);
}

.feature-card.warm {
  border-color: rgba(255, 196, 107, 0.2);
}

.feature-card.cool {
  border-color: rgba(94, 234, 212, 0.16);
}

.map-shell {
  min-height: 560px;
  border-radius: var(--radius);
  background:
    radial-gradient(ellipse 60% 50% at 50% 50%, rgba(255, 94, 26, 0.05), transparent 70%),
    rgba(5, 7, 11, 0.5);
}

.geo-cards-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 20px;
}

.geo-card {
  padding: 20px 22px;
  border-radius: 16px;
  border: 1px solid var(--line);
  background: rgba(11, 16, 22, 0.86);
  display: grid;
  align-content: start;
  gap: 8px;
}

.geo-card.is-flare {
  border-color: rgba(56, 189, 248, 0.34);
  background: linear-gradient(160deg, rgba(56, 189, 248, 0.08), rgba(11, 16, 22, 0.9));
}

.geo-card.is-savanna {
  border-color: rgba(255, 138, 61, 0.36);
  background: linear-gradient(160deg, rgba(255, 138, 61, 0.09), rgba(11, 16, 22, 0.9));
}

.geo-card-tag {
  font-family: var(--font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--gold);
}

.geo-card.is-flare .geo-card-tag {
  color: #7dd3fc;
}

.geo-card h3 {
  margin: 0;
  font-size: 1.06rem;
  font-weight: 500;
  color: var(--ink);
}

.geo-card-provinces {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: #dce3eb;
}

.geo-card-desc {
  margin: 0;
  font-size: 0.84rem;
  line-height: 1.5;
  color: var(--muted);
}

.trap-subsection {
  margin-top: clamp(72px, 10vh, 120px);
  padding-top: clamp(56px, 8vh, 96px);
  border-top: 1px solid var(--line);
}

.future-subsection {
  margin-top: clamp(64px, 9vh, 110px);
  padding-top: clamp(48px, 7vh, 88px);
  border-top: 1px solid var(--line);
}

.proof-final {
  padding-bottom: clamp(90px, 11vh, 140px);
}

.map-cta-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 14px 24px;
  margin-top: 22px;
  padding: 18px 22px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: rgba(244, 241, 232, 0.025);
}

.map-cta-bar p {
  font-size: 0.8rem;
  color: var(--muted);
}

.map-cta-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.protocol {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid var(--line);
}

.protocol-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.protocol-value {
  font-family: var(--font-display);
  font-size: 1.55rem;
  line-height: 1;
  letter-spacing: -0.02em;
}

.protocol-label {
  font-family: var(--font-mono);
  font-size: 0.54rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dim);
}

.proof-delta {
  display: flex;
  flex-wrap: wrap;
  gap: 18px 38px;
  margin-top: 24px;
  padding: 16px 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}

.proof-delta > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.proof-number {
  font-family: var(--font-mono);
  font-size: 0.86rem;
  color: var(--muted);
}

.proof-number strong {
  color: var(--gold);
  font-weight: 600;
}

.caveats {
  display: grid;
  gap: 7px;
  margin-top: 18px;
}

.caveats li {
  position: relative;
  padding-left: 14px;
  font-size: 0.68rem;
  line-height: 1.55;
  color: var(--dim);
}

.caveats li::before {
  content: '—';
  position: absolute;
  left: 0;
  color: var(--gold);
  opacity: 0.6;
}

.proof-foot {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 8px;
  margin-top: 22px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
  font-family: var(--font-mono);
  font-size: 0.54rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--dim);
}

.roadmap {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 26px;
}

.roadmap-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: rgba(244, 241, 232, 0.025);
}

.roadmap-horizon {
  font-family: var(--font-mono);
  font-size: 0.54rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--gold);
}

.roadmap-card h3 {
  font-family: var(--font-display);
  font-size: 1.25rem;
  font-weight: 400;
  letter-spacing: -0.02em;
}

.roadmap-card p {
  flex: 1;
  font-size: 0.72rem;
  line-height: 1.6;
  color: var(--muted);
}

.explorer {
  padding-bottom: clamp(100px, 12vh, 150px);
}

.explorer-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 30px;
}

.recap {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;
  margin-top: 42px;
  border-top: 1px solid var(--line);
  border-left: 1px solid var(--line);
}

.recap > div {
  display: flex;
  gap: 14px;
  padding: 18px;
  border-right: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}

.recap-number {
  font-family: var(--font-mono);
  font-size: 0.56rem;
  letter-spacing: 0.08em;
  color: var(--gold);
}

.recap p {
  font-size: 0.74rem;
  line-height: 1.55;
  color: var(--muted);
}

.final-quote {
  margin-top: 54px;
  color: var(--muted);
  text-align: left;
}

.final-quote em {
  color: var(--gold);
}

.footer-lede {
  margin-top: 14px;
  max-width: 38ch;
}

.footer-note {
  margin-top: 16px;
  padding-left: 12px;
  border-left: 2px solid rgba(255, 196, 107, 0.35);
  max-width: 46ch;
  font-size: 0.68rem;
  line-height: 1.6;
  color: var(--dim);
}

.proof-context {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 18px;
}

.proof-disclaimer {
  margin-top: 18px;
  padding: 14px 16px;
  border-left: 2px solid rgba(94, 234, 212, 0.4);
  background: rgba(244, 241, 232, 0.02);
  max-width: 92ch;
  font-size: 0.66rem;
  line-height: 1.65;
  color: var(--dim);
}

.contribution-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 26px;
}

.contribution-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 22px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background:
    linear-gradient(160deg, rgba(255, 196, 107, 0.04), transparent 60%),
    rgba(244, 241, 232, 0.025);
}

.contribution-card h3 {
  font-family: var(--font-display);
  font-size: 1.35rem;
  font-weight: 400;
  letter-spacing: -0.02em;
  line-height: 1.1;
}

.contribution-card p {
  max-width: 52ch;
  font-size: 0.74rem;
  line-height: 1.6;
  color: var(--muted);
}

.contribution-quote {
  margin-top: 48px;
  max-width: 900px;
  color: var(--muted);
}

.contribution-quote em {
  color: var(--gold);
}

.contribution-note {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
  max-width: 82ch;
  font-size: 0.72rem;
  line-height: 1.65;
  color: var(--muted);
}

.contribution-note strong {
  color: var(--ink);
  font-weight: 600;
}

@media (max-width: 1024px) {
  .section-head {
    grid-template-columns: minmax(0, 1fr);
    gap: 18px;
  }
  .feature-grid,
  .geo-cards-grid,
  .roadmap,
  .contribution-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 760px) {
  .map-shell {
    min-height: 480px;
  }
  .hero-meta-pair {
    grid-template-columns: minmax(0, 1fr);
    gap: 18px;
  }
}

@media (max-width: 640px) {
  .stat-row {
    gap: 18px 26px;
  }
  .protocol {
    grid-template-columns: 1fr 1fr;
  }
  .recap {
    grid-template-columns: 1fr;
  }
  .final-quote {
    font-size: 1.8rem;
  }
}
</style>
