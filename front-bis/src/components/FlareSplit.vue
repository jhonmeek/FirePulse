<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  MONTH_NAMES,
  MONTH_NAMES_EN,
  MONTH_SHORT,
  MONTH_SHORT_EN,
  composition,
  formatCount,
  formatDecimal,
  monthlySeasonComparison,
} from '@/lib/data'
import { locale, t } from '@/lib/i18n'

const showMixed = ref(true)
const hoveredMonth = ref<number | null>(null)
const sensorPartition = computed(() => composition.value.excludedBySensorPartition)
const provenanceAudit = computed(() => composition.value.provenanceAudit)

const monthShort = computed(() => (locale.value === 'en' ? MONTH_SHORT_EN : MONTH_SHORT))
const monthNames = computed(() => (locale.value === 'en' ? MONTH_NAMES_EN : MONTH_NAMES))

const vegCount = computed(() => composition.value.gaClean)
const flareCount = computed(() => composition.value.gaExcluded)
const totalCount = computed(() => composition.value.gaTotal)
const vegShare = computed(() => composition.value.gaCleanShare)
const flareShare = computed(() => composition.value.gaExcludedShare)
const pctSuffix = computed(() => (locale.value === 'en' ? '%' : ' %'))

const maxBarValue = computed(() => {
  let max = 1
  for (const row of monthlySeasonComparison.value) {
    const val = showMixed.value ? row.veg + row.flare : row.veg
    if (val > max) max = val
  }
  return max
})

const bars = computed(() =>
  monthlySeasonComparison.value.map((row, idx) => {
    const flare = showMixed.value ? row.flare : 0
    const total = row.veg + flare
    return {
      index: idx,
      short: monthShort.value[idx] ?? '',
      name: monthNames.value[idx] ?? '',
      veg: Math.round(row.veg),
      flare: Math.round(row.flare),
      shownFlare: Math.round(flare),
      total: Math.round(total),
      vegPct: (row.veg / maxBarValue.value) * 100,
      flarePct: (flare / maxBarValue.value) * 100,
    }
  }),
)

const activeBar = computed(() => {
  const idx = hoveredMonth.value ?? 10 // Novembre par défaut (montre le contraste saison des pluies vs torchères)
  return bars.value[idx] ?? bars.value[7]!
})
</script>

<template>
  <div class="flare">
    <div class="flare-head">
      <div>
        <span class="flare-kicker">
          {{ t('Bilan complet au Gabon · 2000–2025 (tous satellites)', 'Full Gabon breakdown · 2000–2025 (all satellites)') }}
        </span>
        <div class="flare-total-line">
          <strong>{{ formatCount(totalCount) }}</strong>
          <span>{{ t('points chauds enregistrés au total', 'total thermal hotspots recorded') }}</span>
        </div>
      </div>
      <div class="flare-toggle-group" role="group" :aria-label="t('Affichage du profil mensuel', 'Monthly profile mode')">
        <button
          type="button"
          class="mode-btn"
          :class="{ active: showMixed }"
          @click="showMixed = true"
        >
          {{ t('Tout mélanger (trompeur)', 'Mix everything (misleading)') }}
        </button>
        <button
          type="button"
          class="mode-btn"
          :class="{ active: !showMixed }"
          @click="showMixed = false"
        >
          {{ t('Appliquer le filtre complet', 'Apply the full filter') }}
        </button>
      </div>
    </div>

    <!-- Barre proportionnelle unique des 285 013 détections au Gabon -->
    <div class="split-block">
      <div class="split-bar" role="img" :aria-label="t('Répartition entre type 0 hors sources persistantes et détections écartées par le filtre', 'Type-0 outside persistent sources vs detections excluded by the filter')">
        <div class="split-veg" :style="{ width: `${vegShare ?? 0}%` }"></div>
        <div class="split-flare" :style="{ width: `${flareShare ?? 0}%` }"></div>
      </div>

      <div class="split-stats">
        <div class="split-card veg">
          <span class="swatch-label"><i class="swatch hot"></i>{{ t('Détections thermiques · Type 0 hors sources persistantes (catégorie exploratoire)', 'Thermal detections · Type 0 outside persistent sources (exploratory category)') }}</span>
          <div class="split-numbers">
            <strong>{{ formatCount(vegCount) }}</strong>
            <span>{{ formatDecimal(vegShare, 1) }}{{ pctSuffix }}</span>
          </div>
          <p>{{ t('Série filtrée suivant les saisons sèches. Il s’agit de détections thermiques type 0 hors masque (candidats végétation), pas d’une validation causale terrain.', 'Filtered series tracking dry seasons. These are type-0 thermal detections outside the mask (vegetation candidates), not causal field validation.') }}</p>
        </div>

        <div class="split-card flare-card">
          <span class="swatch-label"><i class="swatch cool"></i>{{ t('Détections thermiques écartées (catégorie exploratoire : différence de séries)', 'Excluded thermal detections (exploratory category: series difference)') }}</span>
          <div class="split-numbers">
            <strong>{{ formatCount(flareCount) }}</strong>
            <span>{{ formatDecimal(flareShare, 1) }}{{ pctSuffix }}</span>
          </div>
          <p>
            {{
              t(
                `Partition exclusive par capteur/période : ${sensorPartition.map((s) => `${s.label.split(' (')[0]} (${s.period[0] ?? '—'} → ${s.period[1] ?? '—'}) : ${formatCount(s.excluded)}`).join(' · ')}. Toutes ne sont pas des torchères confirmées.`,
                `Exclusive partition by sensor/period: ${sensorPartition.map((s) => `${s.label.split(' (')[0]} (${s.period[0] ?? '—'} → ${s.period[1] ?? '—'}): ${formatCount(s.excluded)}`).join(' · ')}. Not all are confirmed flares.`,
              )
            }}
          </p>
        </div>
      </div>
    </div>

    <!-- Graphique 12 mois comparant l'effet du filtre sur la courbe saisonnière -->
    <div class="season-proof">
      <div class="season-proof-head">
        <div>
          <span class="season-title">
            {{
              showMixed
                ? t('Sans filtre : les sources persistantes ajoutent un bruit toute l’année', 'Unfiltered: persistent sources add year-round noise')
                : t('Avec filtre : la saison sèche et le creux des pluies ressortent nettement', 'Filtered: dry seasons and the rainy trough stand out clearly')
            }}
          </span>
          <span class="season-sub">
            {{ t('Médiane mensuelle au Gabon (2001–2025)', 'Monthly median in Gabon (2001–2025)') }}
          </span>
        </div>
        <div class="season-readout" aria-live="polite">
          <strong>{{ activeBar.name }}</strong> ·
          <span class="hot-txt">{{ t('Type 0 hors sources', 'Type 0 outside sources') }} : {{ formatCount(activeBar.veg) }}</span>
          <template v-if="showMixed">
            · <span class="cool-txt">{{ t('Écartées par le filtre', 'Excluded by filter') }} : {{ formatCount(activeBar.flare) }}</span>
          </template>
        </div>
      </div>

      <div class="bars-chart-layout">
        <div class="bars-y-axis" aria-hidden="true">
          <span>{{ formatCount(maxBarValue) }}</span>
          <span>{{ formatCount(Math.round(maxBarValue / 2)) }}</span>
          <span>0</span>
        </div>
        <div class="bars-grid">
          <button
            v-for="bar in bars"
            :key="bar.index"
            type="button"
            class="bar-col"
            :class="{ active: activeBar.index === bar.index }"
            :aria-label="`${bar.name} : ${formatCount(bar.veg)} ${t('détections type 0 hors sources persistantes', 'type-0 detections outside persistent sources')}${showMixed ? `, ${formatCount(bar.flare)} ${t('détections écartées par le filtre', 'detections excluded by the filter')}` : ''}`"
            @mouseenter="hoveredMonth = bar.index"
            @focus="hoveredMonth = bar.index"
            @mouseleave="hoveredMonth = null"
          >
            <span class="bar-track">
              <span class="bar-stack">
                <i class="seg-flare" :style="{ height: `${bar.flarePct}%` }"></i>
                <i class="seg-veg" :style="{ height: `${bar.vegPct}%` }"></i>
              </span>
            </span>
            <span class="bar-label">{{ bar.short }}</span>
          </button>
        </div>
      </div>
    </div>

    <p class="flare-note">
      {{
        t(
          `Audit indépendant de l’archive source SP (${provenanceAudit.period[0]}–${provenanceAudit.period[1]}, ${formatCount(provenanceAudit.scopeTotal)} lignes GA) : la NASA classe ${formatCount(provenanceAudit.type23Count)} détections en type 2/3 (${formatDecimal(provenanceAudit.type23ShareOfScope, 1)} %) et ${formatCount(provenanceAudit.type0InMaskCount)} en type 0 dans ${composition.maskedCells} cellules candidates 0,05° (${formatDecimal(provenanceAudit.type0InMaskShareOfScope, 1)} %). Ces sous-compteurs sont indépendants de la différence dynamique des séries : c’est une exposition au critère, pas un taux de faux positifs.`,
          `Independent SP source archive audit (${provenanceAudit.period[0]}–${provenanceAudit.period[1]}, ${formatCount(provenanceAudit.scopeTotal)} GA rows): NASA tags ${formatCount(provenanceAudit.type23Count)} detections as type 2/3 (${formatDecimal(provenanceAudit.type23ShareOfScope, 1)}%) and ${formatCount(provenanceAudit.type0InMaskCount)} type-0 detections inside ${composition.maskedCells} candidate 0.05° cells (${formatDecimal(provenanceAudit.type0InMaskShareOfScope, 1)}%). Reported independently of the dynamic series difference: this reflects criterion exposure, not a false-positive rate.`,
        )
      }}
    </p>
  </div>
</template>

<style scoped>
.flare {
  display: grid;
  gap: 18px;
}

.flare-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.flare-kicker {
  display: block;
  font-family: var(--font-mono);
  font-size: 0.62rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dim);
}

.flare-total-line {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
  margin-top: 4px;
}

.flare-total-line strong {
  font-family: var(--font-display);
  font-size: 1.9rem;
  font-weight: 400;
  color: var(--ink);
  line-height: 1;
}

.flare-total-line span {
  font-size: 0.85rem;
  color: var(--muted);
}

.flare-toggle-group {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 3px;
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  background: rgba(244, 241, 232, 0.03);
}

.mode-btn {
  padding: 7px 11px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--muted);
  font-size: 0.74rem;
  font-weight: 500;
  cursor: pointer;
  transition:
    background 0.2s ease,
    color 0.2s ease;
}

.mode-btn:hover {
  color: var(--ink);
}

.mode-btn.active {
  background: var(--ink);
  color: #05070b;
  font-weight: 600;
}

.split-block {
  display: grid;
  gap: 12px;
}

.split-bar {
  display: flex;
  height: 14px;
  border-radius: 999px;
  overflow: hidden;
  border: 1px solid var(--line-strong);
  background: rgba(244, 241, 232, 0.05);
}

.split-veg {
  background: linear-gradient(90deg, #e24e1b, #ff9e53);
  transition: width 0.5s var(--ease-out);
}

.split-flare {
  background: linear-gradient(90deg, #06b6d4, #22d3ee);
  transition: width 0.5s var(--ease-out);
}

.split-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.split-card {
  padding: 13px 15px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: rgba(244, 241, 232, 0.025);
}

.split-card.veg {
  border-color: rgba(255, 122, 61, 0.28);
}

.split-card.flare-card {
  border-color: rgba(34, 211, 238, 0.28);
}

.swatch-label {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 0.76rem;
  font-weight: 500;
  color: var(--muted);
}

.swatch {
  width: 8px;
  height: 8px;
  flex: none;
  border-radius: 50%;
}

.swatch.hot {
  background: var(--ember);
}

.swatch.cool {
  background: var(--cyan);
}

.split-numbers {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-top: 6px;
}

.split-numbers strong {
  font-family: var(--font-display);
  font-size: 1.5rem;
  font-weight: 400;
  color: var(--ink);
}

.split-numbers span {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--gold);
}

.split-card p {
  margin-top: 4px;
  font-size: 0.74rem;
  line-height: 1.45;
  color: var(--dim);
}

.season-proof {
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: rgba(5, 7, 11, 0.45);
}

.season-proof-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px 14px;
  margin-bottom: 14px;
}

.season-title {
  display: block;
  font-size: 0.84rem;
  font-weight: 600;
  color: var(--ink);
}

.season-sub {
  display: block;
  margin-top: 2px;
  font-size: 0.72rem;
  color: var(--dim);
}

.season-readout {
  font-size: 0.76rem;
  color: var(--muted);
}

.hot-txt {
  color: #ffb37a;
}

.cool-txt {
  color: #67e8f9;
}

.bars-chart-layout {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  align-items: stretch;
}

.bars-y-axis {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-end;
  padding: 2px 0 24px;
  font-family: var(--font-mono);
  font-size: 0.82rem;
  font-weight: 500;
  color: #dce5f0;
  font-variant-numeric: tabular-nums;
}

.bars-grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 6px;
  height: 162px;
  align-items: end;
}

.bar-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  height: 100%;
  padding: 2px 0;
  border: 0;
  background: transparent;
  cursor: pointer;
}

.bar-track {
  position: relative;
  width: 100%;
  flex: 1;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  border-radius: 4px;
  background: rgba(244, 241, 232, 0.04);
  overflow: hidden;
}

.bar-col.active .bar-track,
.bar-col:hover .bar-track {
  outline: 1px solid rgba(255, 196, 107, 0.5);
}

.bar-stack {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}

.seg-veg {
  display: block;
  width: 100%;
  background: linear-gradient(180deg, #ff9e53, #e24e1b);
  transition: height 0.45s var(--ease-out);
}

.seg-flare {
  display: block;
  width: 100%;
  background: linear-gradient(180deg, #67e8f9, #0891b2);
  transition: height 0.45s var(--ease-out);
}

.bar-label {
  font-family: var(--font-mono);
  font-size: 0.84rem;
  font-weight: 500;
  color: #dce5f0;
}

.bar-col.active .bar-label {
  color: var(--gold);
  font-weight: 600;
}

.flare-note {
  font-size: 0.78rem;
  line-height: 1.55;
  color: var(--muted);
}

@media (max-width: 640px) {
  .split-stats {
    grid-template-columns: 1fr;
  }
  .bars-y-axis {
    font-size: 0.72rem;
  }
  .bars-grid {
    gap: 3px;
  }
  .bar-label {
    font-size: 0.72rem;
  }
}
</style>
