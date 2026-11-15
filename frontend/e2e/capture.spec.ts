import { expect, test, type Page } from '@playwright/test'

/**
 * Captures pour le pitch et la vidéo (H34-H42), à partir du build de démo (données FIRMS
 * réelles du Gabon). Lancées seulement sur demande : `CAPTURE=1 npx playwright test capture`.
 * Fond de carte autorisé ici (réseau), contrairement aux tests de parcours.
 * Sortie : docs/demo/*.png en 1440×900, densité ×2.
 */
test.skip(!process.env.CAPTURE, 'Captures à la demande : CAPTURE=1')
test.use({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })

const OUT = '../docs/demo'

async function shot(page: Page, name: string, locator?: string) {
  await page.waitForTimeout(600) // fin des transitions (≤ 200 ms) et du rendu canvas
  const target = locator ? page.locator(locator).first() : page
  await target.screenshot({ path: `${OUT}/${name}.png`, animations: 'disabled' })
}

test('captures de démonstration', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('button[data-month]')).toHaveCount(25 * 12)

  // 1. Accueil : filtres, régimes capteurs, calendrier
  await shot(page, '01-accueil-calendrier')

  // Captures de sections : l'en-tête collant les recouvrirait (il redevient statique ici).
  await page.addStyleTag({ content: 'header { position: static !important; }' })

  // 2. Calendrier avant / après harmonisation (rupture MODIS → VIIRS de 2012)
  const calendarSection = 'section[aria-labelledby="calendar-title"]'
  await page.locator(calendarSection).getByText('Données brutes', { exact: true }).click()
  await page.locator(calendarSection).scrollIntoViewIfNeeded()
  await shot(page, '02-calendrier-avant-harmonisation', calendarSection)
  await page.locator(calendarSection).getByText('Données corrigées', { exact: true }).click()
  await shot(page, '02b-calendrier-apres-harmonisation', calendarSection)

  // 3-4. Rupture 2012 avant / après harmonisation
  const chartSection = 'section[aria-labelledby="chart-title"]'
  await page.locator(chartSection).scrollIntoViewIfNeeded()
  await page.locator(chartSection).getByText('Données brutes', { exact: true }).click()
  await expect(page.getByText(/crée une rupture/)).toBeVisible()
  await shot(page, '03-avant-harmonisation', chartSection)
  await page.locator(chartSection).getByText('Données corrigées', { exact: true }).click()
  await shot(page, '04-apres-harmonisation', chartSection)

  // 5. Carte : grille 0,25° et sites statiques (torchères)
  const mapSection = 'section[aria-labelledby="map-title"]'
  await page.locator(mapSection).scrollIntoViewIfNeeded()
  await expect(page.getByText(/352 cellules/)).toBeVisible()
  await page.waitForTimeout(2500) // tuiles du fond de carte
  await shot(page, '05-carte-grille-et-torcheres', mapSection)

  // 6. Méthodologie & évaluation
  await page.getByRole('tab', { name: 'Méthodologie & évaluation' }).click()
  await expect(page.getByRole('tabpanel').locator('tbody tr')).toHaveCount(5)
  await page.evaluate(() => window.scrollTo(0, 0))
  await shot(page, '06-methodologie-evaluation')
})
