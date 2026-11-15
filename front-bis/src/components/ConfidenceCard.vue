<script setup lang="ts">
import { computed } from 'vue'
import {
  composition,
  dataSourceMode,
  formatCount,
  formatDecimal,
  methodology,
} from '@/lib/data'
import { t } from '@/lib/i18n'
import { provenance } from '@/lib/provenance'
import { validation } from '@/lib/validation'

const props = withDefaults(
  defineProps<{
    compact?: boolean
    context?: 'series' | 'map' | 'export'
  }>(),
  {
    compact: false,
    context: 'series',
  },
)

const archive = `${provenance.archiveStart} → ${provenance.archiveEnd}`
const candidateCells = computed(() => composition.value.maskedCells)
const liveVersion = computed(() => methodology.value.active_run?.method_version ?? 'v2.0')
const liveMae = computed(
  () =>
    methodology.value.active_run?.metrics.models_out_of_sample?.power_law_log1p?.mae ??
    validation.models.power_law_log1p.raw.mae ??
    0,
)
const validationMaeBefore = computed(() => validation.models.naive.raw.mae ?? 0)
const validationMaeAfter = computed(() => validation.models.power_law_log1p.raw.mae ?? 0)
const r2Raw = computed(() => validation.models.power_law_log1p.raw.r2 ?? 0)
const r2Anomaly = computed(() => validation.models.power_law_log1p.anomaly.r2 ?? 0)
const coverage = computed(() => validation.conformal.coverage_test_q80_calibration ?? 0)
const validationDate = validation.generated_at.slice(0, 10)
const liveNoaaRatio = computed(() => methodology.value.active_run?.params?.noaa20_to_snpp_ratio ?? null)
const validationNoaaRatio = computed(
  () => validation.held_out.noaa20.ratio_noaa20_to_snpp_calibration ?? null,
)

const contextLabel = computed(() => {
  if (props.context === 'map') {
    return t('Carte · lecture descriptive', 'Map · descriptive read')
  }
  if (props.context === 'export') {
    return t('Export CSV · données brutes et harmonisées', 'CSV export · raw and harmonized data')
  }
  return t('Séries · lecture historique', 'Series · historical read')
})
</script>

<template>
  <aside v-if="compact" class="confidence-compact" :aria-label="t('Fiche de confiance', 'Confidence note')">
    <span class="confidence-compact-tag">{{ t('Fiche de confiance', 'Confidence note') }}</span>
    <span>{{ contextLabel }}</span>
    <span class="confidence-sep" aria-hidden="true">·</span>
    <span>{{ t(`Archive SP ${archive}`, `SP archive ${archive}`) }}</span>
    <span class="confidence-sep" aria-hidden="true">·</span>
    <span>{{ candidateCells }} {{ t('cellules candidates', 'candidate cells') }}</span>
    <span class="confidence-sep" aria-hidden="true">·</span>
    <span>{{ t('pas de 2026 / NRT', 'no 2026 / NRT') }}</span>
    <a href="#proof" class="confidence-link">{{ t('Méthode & limites', 'Method & limits') }} →</a>
  </aside>

  <section v-else class="confidence-card" :aria-label="t('Fiche de confiance', 'Confidence note')">
    <header class="confidence-head">
      <div>
        <span class="confidence-eyebrow">{{ contextLabel }}</span>
        <h3>{{ t('Fiche de confiance', 'Confidence note') }}</h3>
      </div>
      <span class="confidence-badge">{{ t('Prototype · non opérationnel', 'Prototype · not operational') }}</span>
    </header>

    <div class="confidence-grid">
      <article class="confidence-item">
        <span class="confidence-item-label">{{ t('D’où viennent les données ?', 'Where does the data come from?') }}</span>
        <p>
          {{
            t(
              `NASA FIRMS, archive standard (SP), ${provenance.files} CSV pays, ${archive}. Les données 2026 et le temps quasi réel (NRT) ne sont pas intégrés à cette démonstration.`,
              `NASA FIRMS, standard product (SP) archive, ${provenance.files} country CSVs, ${archive}. 2026 data and near real-time (NRT) are not included in this demo.`,
            )
          }}
        </p>
        <p class="confidence-muted">
          {{ dataSourceMode === 'live' ? t('Source : base PostGIS en direct.', 'Source: live PostGIS database.') : t('Source : instantané de base vérifié (SHA-256).', 'Source: verified database snapshot (SHA-256).') }}
        </p>
      </article>

      <article class="confidence-item">
        <span class="confidence-item-label">{{ t('Quel capteur, quelle période ?', 'Which sensor, which period?') }}</span>
        <p>
          {{
            t(
              'MODIS Terra/Aqua (2000–2025) est l’entrée du modèle. VIIRS S-NPP (2012–2025) est la référence cible. VIIRS NOAA-20 (2018–2025) est le relais post-2026.',
              'MODIS Terra/Aqua (2000–2025) is the model input. VIIRS S-NPP (2012–2025) is the target reference. VIIRS NOAA-20 (2018–2025) is the post-2026 relay.',
            )
          }}
        </p>
      </article>

      <article class="confidence-item">
        <span class="confidence-item-label">{{ t('Quel traitement ?', 'What processing?') }}</span>
        <p>
          {{
            t(
              `Le filtre complet écarte les détections type 2/3 et les type 0 situées dans ${candidateCells} cellules candidates (~5 km). Ce sont des cellules, pas des torchères confirmées une par une.`,
              `The full filter removes type 2/3 detections and type-0 detections inside ${candidateCells} candidate cells (~5 km). These are cells, not individually confirmed flares.`,
            )
          }}
        </p>
        <p class="confidence-muted">
          {{ t(`Masque live : ${candidateCells} cellules (toutes années). Validation gelée : 61 cellules (2000–2019).`, `Live mask: ${candidateCells} cells (all years). Frozen validation: 61 cells (2000–2019).`) }}
        </p>
      </article>

      <article class="confidence-item is-highlight">
        <span class="confidence-item-label">{{ t('Quelle validation ?', 'What validation?') }}</span>
        <p>
          {{
            t(
              `Validation renforcée (artefact du ${validationDate}) : 72 mois de test (2020–2025), MAE ${formatDecimal(validationMaeBefore, 1)} → ${formatDecimal(validationMaeAfter, 1)}, R² saisons ${formatDecimal(r2Raw, 3)}, R² anomalies ${formatDecimal(r2Anomaly, 3)}, couverture q80 ${formatDecimal(coverage * 100, 1)} %.`,
              `Reinforced validation (artifact dated ${validationDate}): 72 test months (2020–2025), MAE ${formatDecimal(validationMaeBefore, 1)} → ${formatDecimal(validationMaeAfter, 1)}, seasonal R² ${formatDecimal(r2Raw, 3)}, anomaly R² ${formatDecimal(r2Anomaly, 3)}, q80 coverage ${formatDecimal(coverage * 100, 1)}%.`,
            )
          }}
        </p>
        <p class="confidence-muted">
          {{
            t(
              `La série live des graphiques principaux suit le protocole base ${liveVersion} (masque toutes années, MAE ${formatDecimal(liveMae, 1)}). Les deux protocoles ne se comparent pas sans le dire.`,
              `The live series in the main charts follows database protocol ${liveVersion} (all-years mask, MAE ${formatDecimal(liveMae, 1)}). The two protocols are not directly comparable without saying so.`,
            )
          }}
        </p>
      </article>
    </div>

    <div class="confidence-conclusions">
      <article>
        <span class="confidence-item-label is-good">{{ t('Ce qu’on peut conclure', 'What you can conclude') }}</span>
        <ul>
          <li>{{ t('L’évolution saisonnière et les années atypiques.', 'Seasonal evolution and atypical years.') }}</li>
          <li>{{ t('La rupture de 2012 est d’abord un changement de capteur.', 'The 2012 break is first a sensor change.') }}</li>
          <li>{{ t('La part des détections dans les cellules persistantes candidates.', 'The share of detections inside candidate persistent cells.') }}</li>
        </ul>
      </article>
      <article>
        <span class="confidence-item-label is-warn">{{ t('Ce qu’on ne peut pas conclure', 'What you cannot conclude') }}</span>
        <ul>
          <li>{{ t('Le nombre d’incendies distincts ou la surface brûlée.', 'The number of distinct fires or burned area.') }}</li>
          <li>{{ t('Une couverture exhaustive : nuages, fumée et canopée masquent des détections.', 'Exhaustive coverage: clouds, smoke and canopy hide detections.') }}</li>
          <li>{{ t('La cause certaine de chaque détection, ni une calibration par polygone.', 'The certain cause of each detection, nor per-polygon calibration.') }}</li>
          <li>{{ t('Une continuité 2026 démontrée : le relais est préparé, pas encore validé.', 'Demonstrated 2026 continuity: the relay is prepared, not yet validated.') }}</li>
        </ul>
      </article>
    </div>

    <p class="confidence-footnote">
      {{
        t(
          `Pont NOAA-20 : ratio ${validationNoaaRatio ? formatDecimal(validationNoaaRatio, 3) : '—'} sur la calibration 2018–2019 ; la reconstruction live utilise ${liveNoaaRatio ? formatDecimal(liveNoaaRatio, 3) : '—'} sur 2019–2025. Le type 0 est une classification du produit, pas une validation terrain.`,
          `NOAA-20 bridge: ratio ${validationNoaaRatio ? formatDecimal(validationNoaaRatio, 3) : '—'} over the 2018–2019 calibration; the live reconstruction uses ${liveNoaaRatio ? formatDecimal(liveNoaaRatio, 3) : '—'} over 2019–2025. Type 0 is a product classification, not field validation.`,
        )
      }}
    </p>
  </section>
</template>

<style scoped>
.confidence-compact {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
  margin-top: 10px;
  padding: 9px 12px;
  border: 1px dashed var(--line-strong);
  border-radius: 9px;
  font-size: 0.7rem;
  line-height: 1.4;
  color: var(--dim);
}

.confidence-compact-tag {
  font-family: var(--font-mono);
  font-size: 0.6rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--gold);
}

.confidence-sep {
  color: var(--line-strong);
}

.confidence-link {
  margin-left: auto;
  color: var(--gold);
  text-decoration: none;
  white-space: nowrap;
}

.confidence-link:hover {
  text-decoration: underline;
}

.confidence-card {
  display: grid;
  gap: 16px;
  padding: 22px;
  border: 1px solid var(--line-strong);
  border-radius: 16px;
  background: linear-gradient(160deg, rgba(255, 196, 107, 0.045), rgba(11, 16, 22, 0.94));
}

.confidence-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.confidence-eyebrow {
  display: block;
  font-family: var(--font-mono);
  font-size: 0.6rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--dim);
  margin-bottom: 4px;
}

.confidence-head h3 {
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(1.35rem, 2vw, 1.7rem);
  font-weight: 400;
  color: var(--ink);
}

.confidence-badge {
  padding: 5px 10px;
  border: 1px solid rgba(255, 196, 107, 0.38);
  border-radius: 999px;
  font-family: var(--font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--gold);
  background: rgba(255, 196, 107, 0.08);
}

.confidence-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.confidence-item {
  padding: 14px 15px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: rgba(244, 241, 232, 0.025);
}

.confidence-item.is-highlight {
  border-color: rgba(255, 196, 107, 0.34);
  background: rgba(255, 196, 107, 0.05);
}

.confidence-item-label {
  display: block;
  margin-bottom: 6px;
  font-family: var(--font-mono);
  font-size: 0.6rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--gold);
}

.confidence-item-label.is-good {
  color: #7dd3a7;
}

.confidence-item-label.is-warn {
  color: #ffb37a;
}

.confidence-item p {
  margin: 0;
  font-size: 0.8rem;
  line-height: 1.55;
  color: #cdd6df;
}

.confidence-item p + p {
  margin-top: 7px;
}

.confidence-muted {
  color: var(--dim) !important;
  font-size: 0.74rem !important;
}

.confidence-conclusions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.confidence-conclusions article {
  padding: 14px 15px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: rgba(5, 7, 11, 0.4);
}

.confidence-conclusions ul {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 5px;
  font-size: 0.79rem;
  line-height: 1.5;
  color: #cdd6df;
}

.confidence-footnote {
  margin: 0;
  font-size: 0.72rem;
  line-height: 1.55;
  color: var(--dim);
}

@media (max-width: 760px) {
  .confidence-grid,
  .confidence-conclusions {
    grid-template-columns: 1fr;
  }

  .confidence-link {
    margin-left: 0;
  }
}
</style>
