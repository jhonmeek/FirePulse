<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { fetchRecentUnknownDetections, USE_MOCKS, type RecentUnknownFeature } from '@/lib/api'
import { locale, t } from '@/lib/i18n'

const detections = ref<RecentUnknownFeature[]>([])
const state = ref<'loading' | 'ready' | 'empty' | 'error' | 'demo'>('loading')
const checkedAt = ref<Date | null>(null)
const now = ref(Date.now())
let refreshTimer: ReturnType<typeof setInterval> | null = null
let clockTimer: ReturnType<typeof setInterval> | null = null
let active = true

const lastAcquisition = computed(() => detections.value[0]?.properties.acquired_at ?? null)
const lastAge = computed(() => {
  if (!lastAcquisition.value) return null
  const minutes = Math.max(0, Math.floor((now.value - Date.parse(lastAcquisition.value)) / 60_000))
  if (!Number.isFinite(minutes)) return null
  return minutes < 60 ? t(`il y a ${minutes} min`, `${minutes} min ago`) : t(`il y a ${Math.floor(minutes / 60)} h`, `${Math.floor(minutes / 60)} h ago`)
})

function utc(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat(locale.value === 'en' ? 'en-GB' : 'fr-FR', {
    timeZone: 'UTC', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(date) + ' UTC'
}

async function refresh(): Promise<void> {
  if (USE_MOCKS) { state.value = 'demo'; return }
  state.value = 'loading'
  try {
    const payload = await fetchRecentUnknownDetections(2, 200)
    if (!active) return
    detections.value = payload.features.filter((feature) => feature.geometry?.type === 'Point')
    checkedAt.value = new Date()
    now.value = Date.now()
    state.value = detections.value.length ? 'ready' : 'empty'
  } catch {
    if (active) state.value = 'error'
  }
}

onMounted(() => {
  void refresh()
  refreshTimer = setInterval(() => { void refresh() }, 5 * 60_000)
  clockTimer = setInterval(() => { now.value = Date.now() }, 60_000)
})
onBeforeUnmount(() => {
  active = false
  if (refreshTimer) clearInterval(refreshTimer)
  if (clockTimer) clearInterval(clockTimer)
})
</script>

<template>
  <section class="recent-panel" aria-labelledby="recent-title">
    <div class="recent-head">
      <div>
        <p class="recent-kicker">NASA FIRMS NRT · NOAA-20</p>
        <h3 id="recent-title">{{ t('Détections thermiques récentes non classées', 'Recent unclassified thermal detections') }}</h3>
      </div>
      <button type="button" class="recent-refresh" :disabled="state === 'loading' || state === 'demo'" @click="refresh">
        {{ t('Actualiser', 'Refresh') }}
      </button>
    </div>
    <p class="recent-caution">{{ t('Points satellites des dernières 48 h au Gabon. Leur type FIRMS est inconnu : ce ne sont pas des incendies confirmés. Les données NRT peuvent être révisées.', 'Satellite points from the last 48 h in Gabon. Their FIRMS type is unknown: they are not confirmed wildfires. NRT records may be revised.') }}</p>
    <div class="recent-status" role="status" aria-live="polite">
      <template v-if="state === 'loading'">{{ t('Recherche des dernières données…', 'Checking recent data…') }}</template>
      <template v-else-if="state === 'demo'">{{ t('Données récentes indisponibles dans la démonstration hors ligne.', 'Recent data is unavailable in the offline demo.') }}</template>
      <template v-else-if="state === 'error'">{{ t('API indisponible. Les données récentes ne peuvent pas être vérifiées pour le moment.', 'API unavailable. Recent data cannot be checked right now.') }}</template>
      <template v-else-if="state === 'empty'">{{ t('Aucun point reçu dans les dernières 48 h. Cela ne prouve pas une absence de feu ni une couverture complète.', 'No points received in the last 48 h. This does not prove an absence of fire or complete coverage.') }}</template>
      <template v-else>{{ detections.length }} {{ t('points reçus', 'points received') }} · {{ t('dernier point', 'latest point') }} {{ lastAge }} ({{ lastAcquisition ? utc(lastAcquisition) : '—' }})</template>
    </div>
    <p v-if="checkedAt" class="recent-check">{{ t('Dernière vérification de l’API', 'Last API check') }} : {{ utc(checkedAt) }}</p>
    <ul v-if="state === 'ready'" class="recent-list">
      <li v-for="feature in detections.slice(0, 12)" :key="feature.properties.id" class="recent-item">
        <strong>{{ feature.properties.satellite || feature.properties.source }}</strong>
        <span>{{ utc(feature.properties.acquired_at) }}</span>
        <span>{{ feature.geometry.coordinates[1].toFixed(3) }}°, {{ feature.geometry.coordinates[0].toFixed(3) }}°</span>
        <span>FRP {{ feature.properties.frp == null ? '—' : `${feature.properties.frp.toFixed(1)} MW` }}</span>
      </li>
    </ul>
    <p v-if="state === 'ready' && detections.length > 12" class="recent-check">{{ t('12 points affichés sur', 'Showing 12 of') }} {{ detections.length }}.</p>
    <p class="recent-source">{{ t('Source : NASA FIRMS via l’API FirePulse. Heure d’acquisition et heure de vérification affichées en UTC. Une réponse vide ou une erreur ne renseigne pas la couverture satellite.', 'Source: NASA FIRMS via the FirePulse API. Acquisition and check times are shown in UTC. An empty response or error does not establish satellite coverage.') }}</p>
  </section>
</template>

<style scoped>
.recent-panel{margin:2rem 0;padding:1.5rem;border:1px solid rgba(124,177,195,.3);border-radius:1.25rem;background:rgba(8,26,42,.88);color:#eef7fa}
.recent-head{display:flex;justify-content:space-between;align-items:start;gap:1rem}
.recent-head h3{font-size:clamp(1.2rem,2vw,1.8rem);line-height:1.2;margin:.25rem 0 .75rem}
.recent-kicker{color:#8bd5e9;font-size:.78rem;letter-spacing:.08em;text-transform:uppercase}
.recent-caution,.recent-source{line-height:1.55;color:#c4d7df;max-width:70ch}
.recent-refresh{border:1px solid #8bd5e9;border-radius:.65rem;background:transparent;color:#e7f8ff;padding:.55rem .85rem;cursor:pointer}
.recent-refresh:disabled{opacity:.55;cursor:default}
.recent-refresh:focus-visible{outline:3px solid #f7ce75;outline-offset:3px}
.recent-status{margin:1rem 0 .4rem;padding:.8rem 1rem;border-radius:.65rem;background:#133b50;font-weight:700}
.recent-check,.recent-source{font-size:.86rem;color:#b8d0d9}
.recent-list{list-style:none;padding:0;margin:1rem 0;display:grid;gap:.45rem;max-height:22rem;overflow:auto}
.recent-item{display:grid;grid-template-columns:5.5rem 1fr 1fr 6rem;gap:.65rem;align-items:center;padding:.6rem .8rem;border:1px solid rgba(124,177,195,.2);border-radius:.5rem;font-size:.85rem}
@media(max-width:700px){.recent-head{flex-direction:column}.recent-item{grid-template-columns:1fr 1fr}.recent-panel{padding:1rem}}
</style>
