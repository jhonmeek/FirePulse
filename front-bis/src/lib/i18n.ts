import { ref } from 'vue'

export type Locale = 'fr' | 'en'

const FRANCOPHONE_COUNTRIES = new Set([
  'GA', 'FR', 'CM', 'CG', 'CD', 'CI', 'SN', 'BE', 'MC', 'LU',
  'MG', 'ML', 'BF', 'NE', 'TG', 'BJ', 'GN', 'TD', 'CF', 'DJ',
  'GQ', 'RW', 'BI', 'KM', 'SC', 'MU', 'HT', 'GF', 'GP', 'MQ',
  'RE', 'YT', 'NC', 'PF', 'PM', 'WF', 'BL', 'MF',
])

const BILINGUAL_COUNTRIES = new Set(['CA', 'CH', 'VU', 'MA', 'DZ', 'TN', 'MR', 'LB'])

const FRANCOPHONE_TIMEZONES = new Set([
  'Africa/Libreville',
  'Africa/Douala',
  'Africa/Brazzaville',
  'Africa/Kinshasa',
  'Africa/Lubumbashi',
  'Africa/Bangui',
  'Africa/Ndjamena',
  'Africa/Niamey',
  'Africa/Porto-Novo',
  'Africa/Lome',
  'Africa/Ouagadougou',
  'Africa/Bamako',
  'Africa/Abidjan',
  'Africa/Dakar',
  'Africa/Conakry',
  'Africa/Nouakchott',
  'Africa/Djibouti',
  'Africa/Malabo',
  'Africa/Kigali',
  'Africa/Bujumbura',
  'Europe/Paris',
  'Europe/Brussels',
  'Europe/Monaco',
  'Indian/Antananarivo',
  'Indian/Comoro',
  'Indian/Mayotte',
  'Indian/Reunion',
  'Indian/Mauritius',
  'Indian/Mahe',
  'America/Cayenne',
  'America/Guadeloupe',
  'America/Martinique',
  'America/Port-au-Prince',
  'America/Miquelon',
  'Pacific/Noumea',
  'Pacific/Tahiti',
  'Pacific/Wallis',
])

const BILINGUAL_TIMEZONES = new Set([
  'Europe/Zurich',
  'Europe/Luxembourg',
  'America/Montreal',
  'America/Toronto',
  'Africa/Casablanca',
  'Africa/Algiers',
  'Africa/Tunis',
  'Asia/Beirut',
])

const LEGACY_LOCAL_KEY = 'fp_locale'
const MANUAL_SESSION_KEY = 'fp_locale_manual'

function readUrlLocale(): Locale | null {
  if (typeof window === 'undefined') return null
  try {
    const param = new URLSearchParams(window.location.search).get('lang')?.toLowerCase()
    return param === 'fr' || param === 'en' ? param : null
  } catch {
    return null
  }
}

function readManualSessionLocale(): Locale | null {
  if (typeof window === 'undefined') return null
  try {
    const stored = window.sessionStorage.getItem(MANUAL_SESSION_KEY)
    return stored === 'fr' || stored === 'en' ? stored : null
  } catch {
    return null
  }
}

function prefersFrenchBrowser(): boolean {
  if (typeof navigator === 'undefined') return true
  const list =
    Array.isArray(navigator.languages) && navigator.languages.length > 0
      ? navigator.languages
      : [navigator.language]
  return list.some((tag) => typeof tag === 'string' && tag.toLowerCase().startsWith('fr'))
}

function getBrowserRegionCode(): string | null {
  if (typeof navigator === 'undefined') return null
  const list =
    Array.isArray(navigator.languages) && navigator.languages.length > 0
      ? navigator.languages
      : [navigator.language]
  for (const tag of list) {
    if (typeof tag !== 'string') continue
    const match = tag.match(/[-_]([A-Za-z]{2})\b/)
    if (match?.[1]) return match[1].toUpperCase()
  }
  return null
}

function localeForCountry(countryCode: string): Locale {
  const code = countryCode.toUpperCase()
  if (FRANCOPHONE_COUNTRIES.has(code)) return 'fr'
  if (BILINGUAL_COUNTRIES.has(code)) return prefersFrenchBrowser() ? 'fr' : 'en'
  return 'en'
}

function detectInitialLocale(): Locale {
  if (typeof window === 'undefined') return 'fr'

  try {
    window.localStorage.removeItem(LEGACY_LOCAL_KEY)
  } catch {
    // Ignore storage errors in restricted environments.
  }

  const fromUrl = readUrlLocale()
  if (fromUrl) return fromUrl

  const fromManual = readManualSessionLocale()
  if (fromManual) return fromManual

  let tz = ''
  try {
    tz = Intl.DateTimeFormat().resolvedOptions().timeZone || ''
  } catch {
    tz = ''
  }

  if (tz) {
    if (FRANCOPHONE_TIMEZONES.has(tz)) return 'fr'
    if (BILINGUAL_TIMEZONES.has(tz)) return prefersFrenchBrowser() ? 'fr' : 'en'
    const region = getBrowserRegionCode()
    if (region && FRANCOPHONE_COUNTRIES.has(region)) return 'fr'
    return 'en'
  }

  return prefersFrenchBrowser() ? 'fr' : 'en'
}

function updateDocumentMetadata(next: Locale): void {
  if (typeof document === 'undefined') return
  document.documentElement.lang = next
  document.title =
    next === 'en'
      ? 'FirePulse · 25 years of Gabon fires from space'
      : 'FirePulse · 25 ans de feux au Gabon'
}

export const locale = ref<Locale>(detectInitialLocale())
updateDocumentMetadata(locale.value)

export function setLocale(next: Locale, manual = true): void {
  locale.value = next
  if (manual && typeof window !== 'undefined') {
    try {
      window.sessionStorage.setItem(MANUAL_SESSION_KEY, next)
    } catch {
      // Ignore storage errors in private mode.
    }
  }
  updateDocumentMetadata(next)
}

export function toggleLocale(): void {
  setLocale(locale.value === 'fr' ? 'en' : 'fr', true)
}

export function t(fr: string, en: string): string {
  return locale.value === 'en' ? en : fr
}

async function detectRegionFromEdge(): Promise<void> {
  if (typeof window === 'undefined' || typeof fetch === 'undefined') return
  if (readUrlLocale() || readManualSessionLocale()) return

  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), 2500)
  try {
    const res = await fetch('/cdn-cgi/trace', {
      cache: 'no-store',
      signal: controller.signal,
    })
    if (!res.ok) return
    const text = await res.text()
    const match = text.match(/^loc=([A-Z]{2})$/m)
    if (!match?.[1]) return
    if (readManualSessionLocale()) return
    const detected = localeForCountry(match[1])
    if (detected !== locale.value) {
      setLocale(detected, false)
    }
  } catch {
    // Ignore when running outside Cloudflare or offline; timezone detection remains active.
  } finally {
    window.clearTimeout(timer)
  }
}

void detectRegionFromEdge()
