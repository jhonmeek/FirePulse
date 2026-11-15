<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from 'vue'
import ChapterNav from '@/components/ChapterNav.vue'
import CalendarHeatmap from '@/components/CalendarHeatmap.vue'
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
  formatCount,
  formatDecimal,
  gridCellMonthsDb,
  initLiveData,
  maskedCellsCount,
  methodology,
  methodologyRaw,
  metrics,
  monthlyMedians,
  params,
  regionsCount,
  staticSeries,
  totalDetectionsDb,
} from '@/lib/data'
import { USE_MOCKS, exportSeriesEndpoint } from '@/lib/api'
import { provenance } from '@/lib/provenance'
import { validation } from '@/lib/validation'
import { ScrollTrigger, gsap } from '@/lib/motion'

const reducedMotion = useReducedMotion()
useSmoothScroll()
useReveal()

void initLiveData()

const chapters = [
  { id: 'top', label: 'Ouverture' },
  { id: 'problem', label: 'Le saut de 2012' },
  { id: 'flares', label: 'Le piège' },
  { id: 'translate', label: 'La traduction' },
  { id: 'calendar', label: 'Le calendrier' },
  { id: 'map', label: 'La carte' },
  { id: 'proof', label: 'Analyse exploratoire' },
  { id: 'contribution', label: 'Notre apport' },
  { id: 'future', label: 'Demain' },
  { id: 'explorer', label: 'Explorer' },
]

const scrollProgress = ref(0)
const scrolled = ref(false)
const activeChapter = ref('top')
const cursor = ref({ x: 0, y: 0 })
const globePoints = computed(() => buildGlobePoints())
const validationCoverageLabel = `${(validation.conformal.coverage_test_q80_calibration * 100)
  .toFixed(1)
  .replace('.', ',')} %`
const validationAnomalyR2 = validation.models.power_law_log1p?.anomaly.r2
const validationAnomalyR2Label = validationAnomalyR2 == null
  ? '—'
  : validationAnomalyR2.toFixed(2).replace('.', ',')

const chartPoints = computed(() =>
  staticSeries.value.map((p) => ({
    month: p.month,
    raw: (p.modis_count ?? 0) + (p.viirs_snpp_count ?? 0),
    harm: p.harmonized_value,
    lo: p.ci_low,
    hi: p.ci_high,
    anomaly: p.anomaly_percent,
  })),
)

const rawChartPoints = computed(() =>
  allSeries.value.map((p) => ({
    month: p.month,
    raw: (p.modis_count ?? 0) + (p.viirs_snpp_count ?? 0),
    harm: p.harmonized_value,
    lo: p.ci_low,
    hi: p.ci_high,
    anomaly: p.anomaly_percent,
  })),
)

const maeBefore = computed(() => metrics.value['naive']?.mae ?? 355.72)
const maeAfter = computed(() => metrics.value['power_law_log1p']?.mae ?? 100.87)
const r2Before = computed(() => metrics.value['naive']?.r2 ?? 0.1426)
const r2After = computed(() => metrics.value['power_law_log1p']?.r2 ?? 0.9189)
const maeReduction = computed(() => Math.round((1 - maeAfter.value / maeBefore.value) * 100))

const globalRatioAlpha = computed(() => params.value?.global_ratio_alpha ?? 3.9328)
const rawGlobalRatioAlpha = computed(
  () => methodologyRaw.value.active_run?.params?.global_ratio_alpha ?? 4.6494,
)
const noaaBridgeRatio = computed(() => params.value?.noaa20_to_snpp_ratio ?? 1.0381)
const jumpRatioLabel = computed(() => `×${formatDecimal(globalRatioAlpha.value, 1)}`)
const rawJumpRatioLabel = computed(() => `×${formatDecimal(rawGlobalRatioAlpha.value, 1)}`)

const trainMonths = computed(() => methodology.value.active_run?.metrics.train_months ?? 95)
const testMonths = computed(() => methodology.value.active_run?.metrics.test_months ?? 72)
const trainWindow = computed(
  () => methodology.value.active_run?.train_window ?? ['2012-02-01', '2019-12-01'],
)
const testWindow = computed(
  () => methodology.value.active_run?.test_window ?? ['2020-01-01', '2025-12-01'],
)
const trainYears = computed(
  () => `${trainWindow.value[0].slice(0, 4)}–${trainWindow.value[1].slice(0, 4)}`,
)
const testYears = computed(
  () => `${testWindow.value[0].slice(0, 4)}–${testWindow.value[1].slice(0, 4)}`,
)
const gridDegLabel = `${String(provenance.gridDeg).replace('.', ',')}°`

const seasonCards = computed(() => {
  const m = monthlyMedians.value
  const july = m[6] ?? 0
  const august = m[7] ?? 0
  const february = m[1] ?? 0
  const march = m[2] ?? 0
  const november = m[10] ?? 0
  const december = m[11] ?? 0
  return [
    {
      label: 'Pic principal',
      months: 'Juillet – Août',
      values: `${formatCount(july)} · ${formatCount(august)}`,
      note: 'détections équiv. S-NPP, médianes 2001–2025',
      tone: 'hot',
    },
    {
      label: 'Second épisode',
      months: 'Février – Mars',
      values: `${formatCount(february)} · ${formatCount(march)}`,
      note: 'un second souffle, plus faible mais réel',
      tone: 'warm',
    },
    {
      label: 'Creux',
      months: 'Novembre – Décembre',
      values: `${formatCount(november)} · ${formatCount(december)}`,
      note: 'la saison des pluies coupe l’activité',
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
  for (const chapter of chapters) {
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
    <a class="skip-link" href="#explorer" @click.prevent="navigate('explorer')">
      Aller à l’explorateur
    </a>
    <div class="site-bg" aria-hidden="true"></div>
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
        <div class="hero-globe">
          <GlobeScene :points="globePoints" :reduced-motion="reducedMotion" />
        </div>

        <div class="shell hero-inner">
          <div class="hero-copy">
            <p class="kicker hero-kicker">
              NASA Space Apps 2026 · MODIS × VIIRS ·
              <span>{{ dataSourceMode === 'live' ? 'API et instantanés locaux possibles' : 'API partielle ou instantanés locaux' }}</span>
            </p>
            <h1 class="display display-xl hero-title">
              <span class="line"><span>One Planet.</span></span>
              <span class="line"><span>One Fire <em>History.</em></span></span>
            </h1>
            <p class="hero-sub">
              25 ans de feux vus par deux générations de satellites.
              <strong>Une seule histoire, enfin lisible.</strong>
            </p>
            <div class="hero-actions">
              <button type="button" class="btn btn-heat" @click="navigate('problem')">
                Entrer dans l’histoire
                <span aria-hidden="true">→</span>
              </button>
              <button type="button" class="btn btn-ghost" @click="navigate('proof')">
                Voir l’analyse exploratoire
              </button>
            </div>

            <div class="hero-meta">
              <div>
                <div class="value">
                  <CountUp :to="totalDetectionsDb" :reduced-motion="reducedMotion" />
                </div>
                <div class="label">détections (archive SP)</div>
              </div>
              <div>
                <div class="value">{{ provenance.files }}</div>
                <div class="label">fichiers FIRMS</div>
              </div>
              <div>
                <div class="value">2000–2025</div>
                <div class="label">25 ans d’archive</div>
              </div>
              <div>
                <div class="value">{{ regionsCount }}</div>
                <div class="label">régions en base</div>
              </div>
            </div>
          </div>
        </div>

        <div class="scroll-hint" aria-hidden="true">
          <span>Faites défiler — tout est expliqué</span>
          <span class="line"></span>
        </div>
      </section>

      <!-- ============================================================ 01 -->
      <section id="problem" class="chapter">
        <div class="shell chapter-grid">
          <div class="chapter-copy">
            <p class="kicker reveal">01 — Le problème</p>
            <h2 class="display display-lg reveal reveal-delay-1">
              En 2012, la courbe explose.<br /><em>Les feux, non.</em>
            </h2>
            <p class="lede reveal reveal-delay-2">
              MODIS voit à <strong>1 km</strong>. VIIRS à <strong>375 m</strong>. Le second détecte
              presque quatre fois plus de points chauds. Sur un graphique brut, cela ressemble à une
              explosion. C’est un changement de caméra.
            </p>

            <div class="stat-row reveal reveal-delay-3">
              <div>
                <div class="stat">{{ jumpRatioLabel }}</div>
                <div class="stat-label">
                  ratio VIIRS / MODIS (2012–2019, hors statiques · {{ rawJumpRatioLabel }} en brut)
                </div>
              </div>
              <div>
                <div class="stat stat-small">2 capteurs</div>
                <div class="stat-label">MODIS et VIIRS, mêmes feux</div>
              </div>
            </div>

            <p class="chapter-note reveal reveal-delay-4">
              Un point chaud n’est pas un incendie. C’est une <strong>détection thermique</strong>.
            </p>
          </div>

          <div class="chapter-visual reveal reveal-delay-2">
            <div class="panel panel-pad">
              <div class="panel-label">
                <span class="tiny-label">Série brute · toutes anomalies thermiques</span>
                <span class="tag dot">2000–2025</span>
              </div>
              <LineChart
                :points="rawChartPoints"
                :show-raw="true"
                :show-harmonized="false"
                :highlight2012="true"
                :reduced-motion="reducedMotion"
                title="Détections mensuelles brutes"
                raw-label="MODIS + VIIRS S-NPP, toutes anomalies"
              />
              <p class="panel-caption">
                Le saut de 2012 est un artefact de capteur. Pris pour un signal, il ferait croire
                que le Gabon a brûlé quatre fois plus. Les torchères sont encore incluses ici.
              </p>
            </div>
          </div>
        </div>
      </section>

      <!-- ============================================================ 02 -->
      <section id="flares" class="chapter">
        <div class="shell chapter-grid reverse">
          <div class="chapter-visual reveal reveal-delay-2">
            <div class="panel panel-pad">
              <div class="panel-label">
                <span class="tiny-label">VIIRS S-NPP · polygone GA · 2012–2025</span>
                <span class="tag cool">Filtre statique</span>
              </div>
              <FlareSplit
                :share="composition.snppExcludedShare"
                :static-count="composition.snppExcluded"
                :total-count="composition.snppTotal"
                :type23-count="composition.snppType23Count"
                :type23-share="composition.snppType23Share"
                :masked-cells="composition.maskedCells"
                :reduced-motion="reducedMotion"
              />
            </div>
          </div>

          <div class="chapter-copy">
            <p class="kicker reveal">02 — Le piège</p>
            <h2 class="display display-lg reveal reveal-delay-1">
              Tous les points chauds<br /><em>ne sont pas des feux.</em>
            </h2>
            <p class="lede reveal reveal-delay-2">
              Dans le polygone Gabon ({{ formatCount(composition.gaTotal) }} détections), une forte
              part provient de <strong>torchères</strong> et de <strong>sites persistants</strong>.
              Si on les compte comme des feux, la saison est faussée : au total,
              <strong>{{ formatDecimal(composition.gaExcludedShare, 1) }} %</strong>
              ({{ formatCount(composition.gaExcluded) }}) sont écartées tous capteurs confondus.
            </p>

            <div class="stat-row reveal reveal-delay-3">
              <div>
                <div class="stat stat-small">{{ formatCount(composition.snppExcluded) }}</div>
                <div class="stat-label">
                  détections S-NPP écartées en GA (dont {{ formatCount(composition.snppType23Count) }} type 2/3)
                </div>
              </div>
              <div>
                <div class="stat stat-small">{{ composition.maskedCells }}</div>
                <div class="stat-label">
                  cellules masquées à {{ String(provenance.staticGridDeg).replace('.', ',') }}°
                </div>
              </div>
            </div>

            <p class="chapter-note reveal reveal-delay-4">
              Le type FIRMS ne suffit pas : en 2017, MODIS n’a signalé aucune source type 2 au
              Gabon. D’où un masque de <strong>persistance spatiale</strong>, appliqué à tous les
              capteurs.
            </p>
          </div>
        </div>
      </section>

      <!-- ============================================================ 03 -->
      <section id="translate" class="chapter">
        <div class="shell chapter-grid">
          <div class="chapter-copy">
            <p class="kicker reveal">03 — L’algorithme</p>
            <h2 class="display display-lg reveal reveal-delay-1">
              Traduire MODIS en VIIRS,<br /><em>sans trahir les feux.</em>
            </h2>
            <p class="lede reveal reveal-delay-2">
              On apprend la conversion sur la période où les deux capteurs observent ensemble,
              <strong>{{ trainYears }}</strong>. Une loi de puissance, entraînée sur le passé,
              testée sur <strong>{{ testYears }}</strong>. Puis une marge d’incertitude.
            </p>

            <ol class="steps reveal reveal-delay-3">
              <li>
                <span class="step-index">01</span>
                <div>
                  <strong>Masque statique 0,05°</strong>
                  <span>Torchères et sites industriels retirés avant toute comparaison.</span>
                </div>
              </li>
              <li>
                <span class="step-index">02</span>
                <div>
                  <strong>Calibration puissance</strong>
                  <span>MODIS → échelle VIIRS, apprise sur le recouvrement {{ trainYears }}.</span>
                </div>
              </li>
              <li>
                <span class="step-index">03</span>
                <div>
                  <strong>Intervalle expérimental, cible 80 %</strong>
                  <span>Une bande d’incertitude sur la période reconstruite, pas une fausse précision.</span>
                </div>
              </li>
            </ol>

            <div class="stat-row reveal reveal-delay-4">
              <div>
                <div class="stat">−{{ maeReduction }} %</div>
                <div class="stat-label">d’erreur moyenne vs naïf</div>
              </div>
              <div>
                <div class="stat stat-small">
                  R² {{ formatDecimal(r2After, 3) }}
                </div>
                <div class="stat-label">sur {{ testMonths }} mois de test</div>
              </div>
            </div>

            <p class="benchmark-note reveal reveal-delay-4">
              Benchmark DB v2.0 : train 2012–2019, test 2020–2025, masque all-years — MAE
              {{ formatDecimal(maeBefore, 1) }} → {{ formatDecimal(maeAfter, 1) }}, R²
              {{ formatDecimal(r2Before, 3) }} → {{ formatDecimal(r2After, 3) }}. L’analyse exploratoire ci-dessous utilise un autre protocole : trois périodes et un masque
              gelé. Les résultats ne sont pas directement interchangeables.
            </p>
          </div>

          <div class="chapter-visual reveal reveal-delay-2">
            <div class="panel panel-pad">
              <div class="panel-label">
                <span class="tiny-label">Avant / après harmonisation</span>
                <span class="tag dot">Test {{ testYears }}</span>
              </div>
              <LineChart
                :points="chartPoints"
                :show-raw="true"
                :show-harmonized="true"
                :show-band="true"
                :highlight2012="true"
                mark-month="2024-08"
                :reduced-motion="reducedMotion"
                title="Le saut disparaît, la saison reste"
                raw-label="Brut après filtre torchères"
                harm-label="Harmonisé"
              />
              <p class="panel-caption">
                La ligne pointillée est la série brute après retrait des torchères. La ligne
                lumineuse est l’échelle VIIRS. La bande est celle de la baseline DB v2.0 ; sa
                couverture n’est pas établie par l’analyse exploratoire ci-dessous.
              </p>
            </div>
          </div>
        </div>
      </section>

      <!-- ============================================================ 04 -->
      <section id="calendar" class="chapter">
        <div class="shell">
          <div class="section-head">
            <div>
              <p class="kicker reveal">04 — La mémoire</p>
              <h2 class="display display-lg reveal reveal-delay-1">La saison apparaît.</h2>
            </div>
            <p class="lede reveal reveal-delay-2">
              Chaque case est un mois. Plus elle est claire, plus l’activité est forte. En un
              regard, la saison des feux se lit : pic en juillet–août, second épisode en
              février–mars, creux en novembre–décembre.
            </p>
          </div>

          <div class="calendar-shell reveal reveal-delay-2">
            <div class="calendar-head">
              <div class="calendar-head-left">
                <span class="tag dot">Calendrier Années × Mois</span>
                <span class="tiny-label">Cliquez un mois pour l’épingler</span>
              </div>
              <button type="button" class="btn btn-ghost btn-small" @click="downloadCsv">
                Télécharger le CSV
              </button>
            </div>
            <CalendarHeatmap :reduced-motion="reducedMotion" />
          </div>

          <p class="calendar-note reveal reveal-delay-2">
            Le calendrier et sa bande d’incertitude restent ceux de la baseline DB v2.0 (API live
            ou instantané), pour rester cohérents avec l’existant. L’analyse exploratoire ci-dessous rapporte une couverture de {{ validationCoverageLabel }}
            pour son propre intervalle ; elle ne valide pas cette bande.
          </p>

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

      <!-- ============================================================ 05 -->
      <section id="map" class="chapter">
        <div class="shell">
          <div class="section-head">
            <div>
              <p class="kicker reveal">05 — Le territoire</p>
              <h2 class="display display-lg reveal reveal-delay-1">La mémoire spatiale.</h2>
            </div>
            <p class="lede reveal reveal-delay-2">
              Où brûle-t-on ? La grille 0,25° agrège les détections par cellule et par mois. Les
              sites industriels persistants sont isolés en bleu. Le Gabon, ses provinces, ses zones
              sensibles.
            </p>
          </div>

          <div class="map-shell reveal reveal-delay-2">
            <HotspotMap :reduced-motion="reducedMotion" />
          </div>

          <div class="map-stats-row reveal reveal-delay-3">
            <div>
              <span class="stat stat-small">{{ composition.gaGridCells }}</span>
              <span class="stat-label">cellules actives dans GA (0,25°)</span>
            </div>
            <div>
              <span class="stat stat-small">{{ maskedCellsCount }}</span>
              <span class="stat-label">sites statiques (0,05°)</span>
            </div>
            <div>
              <span class="stat stat-small">{{ formatCount(gridCellMonthsDb) }}</span>
              <span class="stat-label">cellules-mois en base (filtrées + brutes)</span>
            </div>
            <div>
              <span class="stat stat-small">{{ gridDegLabel }}</span>
              <span class="stat-label">résolution de la grille</span>
            </div>
          </div>
        </div>
      </section>

      <!-- ============================================================ 06 -->
      <section id="proof" class="chapter">
        <div class="shell">
          <div class="section-head">
            <div>
              <p class="kicker reveal">06 — Analyse exploratoire</p>
              <h2 class="display display-lg reveal reveal-delay-1">
                Ce que nous explorons.<br /><em>Et les limites à vérifier.</em>
              </h2>
            </div>
            <p class="lede reveal reveal-delay-2">
              Cette analyse compare plusieurs modèles et documente leurs limites. L'artefact affiché
              reste exploratoire : la couverture des observations et l'indépendance de certaines étapes
              ne sont pas établies.
            </p>
          </div>

          <div class="proof-context reveal reveal-delay-2">
            <span class="tag dot">Analyse exploratoire en revue · 48 CSV pays</span>
            <span class="tag">
              {{ validation.split.n_train }} train · {{ validation.split.n_calibration }} calibration ·
              {{ validation.split.n_test }} test
            </span>
            <span class="tag cool">{{ validation.mask.cells_frozen }} cellules gelées</span>
            <span class="tag">couverture {{ validationCoverageLabel }}</span>
          </div>

          <ValidationProof :reduced-motion="reducedMotion" />

          <p class="proof-disclaimer reveal">
            L'artefact exploratoire initial a été calculé sur 48 CSV FIRMS pays (géométrie non rejointe,
            comme M1) avec
            {{ validation.split.n_train }} mois de train, {{ validation.split.n_calibration }} mois
            de calibration et {{ validation.split.n_test }} mois de test. Le calendrier et la carte
            peuvent utiliser l'API ou des instantanés ; leur périmètre GA diffère des fichiers pays. Le
            benchmark DB v2.0 du chapitre 03 (train 2012–2019, masque all-years) utilise une autre
            méthode ; les deux résultats restent à examiner et ne sont pas interchangeables.
          </p>
        </div>
      </section>

      <!-- ============================================================ 07 -->
      <section id="contribution" class="chapter">
        <div class="shell">
          <div class="section-head">
            <div>
              <p class="kicker reveal">07 — Notre apport</p>
              <h2 class="display display-lg reveal reveal-delay-1">
                Ce qui nous démarque,<br /><em>concrètement.</em>
              </h2>
            </div>
            <p class="lede reveal reveal-delay-2">
              Notre travail réunit une exploration historique et une documentation transparente
              de ses limites ; sa validation scientifique reste à compléter.
            </p>
          </div>

          <div class="contribution-grid">
            <article class="contribution-card reveal">
              <span class="roadmap-horizon">01 — Analyse</span>
              <h3>Un protocole en revue</h3>
              <p>
                L'artefact initial sépare les périodes d'ajustement et de test, mais son masque
                utilise la période de calibration. Une nouvelle évaluation est nécessaire.
              </p>
            </article>
            <article class="contribution-card reveal reveal-delay-1">
              <span class="roadmap-horizon">02 — Honnêteté</span>
              <h3>Nous publions les résultats négatifs</h3>
              <p>
                L'artefact initial rapporte une couverture inférieure à la cible et des limites
                de transfert entre plateformes ; ces chiffres sont exploratoires et à recalculer.
              </p>
            </article>
            <article class="contribution-card reveal reveal-delay-2">
              <span class="roadmap-horizon">03 — Produit</span>
              <h3>Un produit complet</h3>
              <p>
                Calendrier accessible, carte 0,25°, anomalies, export CSV, API Django/PostGIS,
                mode snapshot hors-ligne. La science n’est pas déconnectée de l’usage.
              </p>
            </article>
            <article class="contribution-card reveal reveal-delay-3">
              <span class="roadmap-horizon">04 — Passage à l’échelle</span>
              <h3>Une méthode à explorer ailleurs</h3>
              <p>
                L’application au Bassin du Congo, à la FRP, à NOAA-21 et à la surface brûlée reste
                à étudier et à valider.
              </p>
            </article>
          </div>

          <p class="contribution-quote display display-md reveal reveal-delay-4">
            « La différence n’est pas de promettre R² = 0,92.<br />
            <em>C’est de savoir ce que ce chiffre prouve — et ce qu’il ne prouve pas.</em> »
          </p>

          <p class="contribution-note reveal reveal-delay-4">
            <strong>Pour la NASA</strong> : un benchmark reproductible, un protocole de validation
            inter-capteurs et un cas d’usage dans un biome sous-surveillé.
            <strong>Pour les gestionnaires</strong> : un calendrier qui dit quand l’activité est
            inhabituelle, pas seulement où est le feu.
          </p>
        </div>
      </section>

      <!-- ============================================================ 08 -->
      <section id="future" class="chapter">
        <div class="shell">
          <div class="section-head">
            <div>
              <p class="kicker reveal">08 — Demain</p>
              <h2 class="display display-lg reveal reveal-delay-1">
                Le 2 novembre 2026,<br /><em>Suomi-NPP s’est tu.</em>
              </h2>
            </div>
            <p class="lede reveal reveal-delay-2">
              Archive SP ingérée jusqu’en déc. 2025 ; le pont NOAA-20 (ratio
              ×{{ formatDecimal(noaaBridgeRatio, 3) }} calibré sur 2019–2025) prend le relais après
              l’arrêt des livraisons S-NPP. Le prochain chapitre : flux NRT continu, Bassin du Congo,
              énergie des feux.
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
              <span class="roadmap-horizon">Maintenant</span>
              <h3>Continuité 2026</h3>
              <p>
                L’archive SP ingérée s’arrête en déc. 2025 ; prochaine étape : brancher le flux NRT
                NOAA-20 sans rupture et alerter quand un mois dépasse la médiane historique.
              </p>
              <span class="tag">Prototype</span>
            </article>
            <article class="roadmap-card reveal reveal-delay-1">
              <span class="roadmap-horizon">6 mois</span>
              <h3>Bassin du Congo</h3>
              <p>
                Passer d’un pays à un biome : 6–10 pays, même méthode, validation indépendante
                par surface brûlée.
              </p>
              <span class="tag">Roadmap</span>
            </article>
            <article class="roadmap-card reveal reveal-delay-2">
              <span class="roadmap-horizon">12 mois</span>
              <h3>Énergie des feux</h3>
              <p>
                Harmoniser la FRP, pas seulement les comptages. Ouvrir les émissions, la santé et
                la priorisation des zones sensibles.
              </p>
              <span class="tag">Recherche</span>
            </article>
          </div>
        </div>
      </section>

      <!-- ============================================================ 08 -->
      <section id="explorer" class="chapter explorer">
        <div class="shell-narrow">
          <p class="kicker reveal">09 — À vous de jouer</p>
          <h2 class="display display-lg reveal reveal-delay-1">
            Explorez 25 ans de feux.<br /><em>Et posez vos propres questions.</em>
          </h2>
          <p class="lede reveal reveal-delay-2">
            Le calendrier et la carte sont interactifs. Le CSV reprend les colonnes du contrat API.
            Tout est reproductible, tout est expliqué.
          </p>

          <div class="explorer-actions reveal reveal-delay-3">
            <button type="button" class="btn btn-heat" @click="navigate('calendar')">
              Ouvrir le calendrier
            </button>
            <button type="button" class="btn btn-ghost" @click="navigate('map')">
              Voir la carte
            </button>
            <button type="button" class="btn btn-ghost" @click="downloadCsv">
              Télécharger le CSV
            </button>
          </div>

          <div class="recap reveal reveal-delay-4">
            <div>
              <span class="recap-number">01</span>
              <p>Un artefact de 2012 supprimé, une saison révélée.</p>
            </div>
            <div>
              <span class="recap-number">02</span>
              <p>
                {{ formatDecimal(composition.gaExcludedShare, 1) }} % des détections GA écartées
                comme sources statiques probables ({{ formatDecimal(composition.snppExcludedShare, 1) }} %
                sur S-NPP).
              </p>
            </div>
            <div>
              <span class="recap-number">03</span>
              <p>
                Artefact historique exploratoire : couverture observée {{ validationCoverageLabel }}
                et R² {{ validationAnomalyR2Label }} sur les anomalies, résultats en revue.
              </p>
            </div>
            <div>
              <span class="recap-number">04</span>
              <p>
                Une évaluation exploratoire NOAA-20, un calendrier, une carte et un CSV.
              </p>
            </div>
          </div>

          <p class="final-quote display display-md">
            « One Planet. <em>One Fire History.</em> »
          </p>
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
              Un prototype de preuve de concept pour le défi NASA Space Apps 2026
              « Harmonization of MODIS and VIIRS Hot Spots ».
            </p>
            <p class="footer-lede">
              Données NASA FIRMS · MODIS C6.1 · VIIRS C2 · Gabon 2000–2025.
            </p>
            <p class="footer-note">
              Source :
              <strong>{{
                dataSourceMode === 'live'
                  ? 'API Django et instantanés locaux possibles ; provenance variable selon les données'
                  : 'API partielle ou instantanés locaux ; provenance variable selon les données'
              }}</strong>
              — Archive BBox : {{ formatCount(composition.archiveTotal) }} détections
              ({{ composition.archiveFiles }} fichiers FIRMS SP, 2000-11 → 2025-12). Polygone GA :
              {{ formatCount(composition.gaTotal) }} détections dont
              {{ formatCount(composition.gaClean) }} détections retenues après filtre
              ({{ composition.maskedCells }} mailles à 0,05° + tag FIRMS type ≠ 0).
            </p>
          </div>
          <div>
            <h3>Sources</h3>
            <ul>
              <li>
                <a href="https://firms.modaps.eosdis.nasa.gov/" target="_blank" rel="noreferrer">
                  NASA FIRMS
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
              <li>Backend PostGIS / Django — API v1</li>
              <li>Baseline harmonisée v2.0, en revue M1</li>
              <li>Analyse exploratoire : 3 temps, masque gelé, couverture à examiner</li>
            </ul>
          </div>
          <div>
            <h3>À propos</h3>
            <ul>
              <li>M1 — Data & Science</li>
              <li>M2 — Backend / Geo / Infra</li>
              <li>M3 — Frontend / UX / Pitch</li>
              <li>Prototype — ne pas citer comme produit opérationnel.</li>
            </ul>
          </div>
        </div>
        <div class="footer-bottom">
          <span>FirePulse · One Planet. One Fire History.</span>
          <span>NASA n’endosse pas ce projet.</span>
          <span>Fait avec des données ouvertes.</span>
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

.hero-kicker {
  opacity: 1;
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

.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 18px;
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

.map-stats-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 18px;
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
}

.map-stats-row > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
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
  .roadmap,
  .contribution-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .map-stats-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .map-shell {
    min-height: 480px;
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
  .map-stats-row {
    grid-template-columns: 1fr 1fr;
  }
  .final-quote {
    font-size: 1.8rem;
  }
}
</style>
