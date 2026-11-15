<script setup lang="ts">
import { computed } from 'vue'
import { formatDecimal } from '@/lib/data'
import { t } from '@/lib/i18n'
import { provenance } from '@/lib/provenance'

const props = withDefaults(
  defineProps<{
    reducedMotion?: boolean
    archiveEnd?: string
    noaaBridgeRatio?: number
  }>(),
  {
    reducedMotion: false,
    archiveEnd: provenance.archiveEnd,
    noaaBridgeRatio: 0.94,
  },
)

const noaaDiffPct = computed(() => Math.abs(Math.round((props.noaaBridgeRatio - 1) * 1000) / 10))
</script>

<template>
  <div class="relay-wrap" :aria-label="t('Le passage de relais entre satellites au Gabon', 'Satellite relay over Gabon')">
    <div class="relay-grid">
      <article class="relay-card">
        <div class="relay-top">
          <span class="relay-period">2000 – 2011</span>
          <span class="relay-tag">{{ t('Passé · Réaligné', 'Past · Aligned') }}</span>
        </div>
        <h3>{{ t('Ancien satellite (MODIS)', 'Older satellite (MODIS)') }}</h3>
        <p>
          {{
            t(
              'Première caméra spatiale sur le Gabon, avec une vue large (~1 km). Elle comptait environ 4 fois moins de détections : FirePulse remet cet historique au niveau actuel.',
              'First space camera watching Gabon at a wide resolution (~1 km). It counted roughly 4x fewer detections: FirePulse aligns this archive to today’s scale.',
            )
          }}
        </p>
        <div class="relay-foot">
          {{ t('Archive couverte dès novembre 2000', 'Archive starts November 2000') }}
        </div>
      </article>

      <div class="relay-arrow" aria-hidden="true">→</div>

      <article class="relay-card is-active">
        <div class="relay-top">
          <span class="relay-period">2012 – 2026</span>
          <span class="relay-tag is-active">{{ t('Référence de l’archive', 'Archive reference') }}</span>
        </div>
        <h3>{{ t('Satellite de référence (VIIRS S-NPP)', 'Reference satellite (VIIRS S-NPP)') }}</h3>
        <p>
          {{
            t(
              `Image beaucoup plus nette (375 m) qui sert de base à tous les graphiques. L'archive étudiée ici va jusqu'à ${archiveEnd}. La mission opérationnelle s'est arrêtée le 2 novembre 2026.`,
              `Much sharper view (375 m) serving as the baseline for every chart. This archive runs to ${archiveEnd}. Operational delivery ended on November 2, 2026.`,
            )
          }}
        </p>
        <div class="relay-foot is-warn">
          {{ t('Mission terminée le 2 novembre 2026', 'Mission ended November 2, 2026') }}
        </div>
      </article>

      <div class="relay-arrow" aria-hidden="true">→</div>

      <article class="relay-card is-next">
        <div class="relay-top">
          <span class="relay-period">{{ t('2026+', '2026+') }}</span>
          <span class="relay-tag is-next">{{ t('Relais préparé', 'Relay prepared') }}</span>
        </div>
        <h3>{{ t('Successeur (VIIRS NOAA-20)', 'Successor (VIIRS NOAA-20)') }}</h3>
        <p>
          {{
            t(
              `En orbite depuis 2018 à la même résolution (375 m). Sur la période commune 2018–2019, le ratio de calibration mesuré est de ${formatDecimal(props.noaaBridgeRatio, 3)} (~${formatDecimal(noaaDiffPct, 1)} % d'écart). Le relais reste à valider sur les données 2026, absentes de cette archive.`,
              `Operating since 2018 at the same resolution (375 m). Over the 2018–2019 overlap, the measured calibration ratio is ${formatDecimal(props.noaaBridgeRatio, 3)} (~${formatDecimal(noaaDiffPct, 1)}% gap). The relay still needs validation on 2026 data, absent from this archive.`,
            )
          }}
        </p>
        <div class="relay-foot is-next">
          {{ t('Relais préparé, validation 2026 à faire', 'Relay prepared, 2026 validation pending') }}
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.relay-wrap {
  width: 100%;
}

.relay-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 14px;
  align-items: stretch;
}

.relay-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.4rem;
  color: var(--gold);
  opacity: 0.7;
  user-select: none;
}

.relay-card {
  padding: 22px;
  border-radius: 16px;
  border: 1px solid var(--line);
  background: rgba(11, 16, 22, 0.88);
  display: grid;
  grid-template-rows: auto auto 1fr auto;
  gap: 10px;
}

.relay-card.is-active {
  border-color: rgba(255, 196, 107, 0.44);
  background: linear-gradient(160deg, rgba(255, 138, 61, 0.1), rgba(11, 16, 22, 0.92));
}

.relay-card.is-next {
  border-color: rgba(56, 189, 248, 0.36);
  background: linear-gradient(160deg, rgba(56, 189, 248, 0.08), rgba(11, 16, 22, 0.92));
}

.relay-top {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.relay-period {
  font-family: var(--font-mono);
  font-size: 0.76rem;
  font-weight: 600;
  color: var(--ink);
  letter-spacing: 0.04em;
}

.relay-tag {
  padding: 3px 9px;
  border-radius: 999px;
  border: 1px solid var(--line);
  font-family: var(--font-mono);
  font-size: 0.56rem;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--muted);
}

.relay-tag.is-active {
  border-color: rgba(255, 196, 107, 0.4);
  color: var(--gold);
  background: rgba(255, 196, 107, 0.1);
}

.relay-tag.is-next {
  border-color: rgba(56, 189, 248, 0.4);
  color: #7dd3fc;
  background: rgba(56, 189, 248, 0.1);
}

.relay-card h3 {
  margin: 0;
  font-size: 1.06rem;
  font-weight: 500;
  color: var(--ink);
}

.relay-card p {
  margin: 0;
  font-size: 0.88rem;
  line-height: 1.54;
  color: #cdd6df;
}

.relay-foot {
  padding-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  font-family: var(--font-mono);
  font-size: 0.66rem;
  color: var(--muted);
}

.relay-foot.is-warn {
  color: #ffb86c;
}

.relay-foot.is-next {
  color: #7dd3fc;
}

@media (max-width: 980px) {
  .relay-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 12px;
  }
  .relay-arrow {
    display: none;
  }
}
</style>
