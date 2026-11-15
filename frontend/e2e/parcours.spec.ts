import { expect, test } from './fixtures'

/**
 * Parcours d'un utilisateur naïf sur la démo hors ligne (Gabon, données FIRMS embarquées) :
 * il découvre l'écran, explore un mois, filtre, compare, zoome, exporte et lit la méthode.
 */
test.describe('parcours utilisateur (démo hors ligne)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: /Points de feu chaque mois - Gabon/ })).toBeVisible()
  })

  test('découvre l’écran : provenance, calendrier, ligne de référence', async ({ page, pageErrors }) => {
    await expect(page.getByRole('status').filter({ hasText: 'Démo hors ligne' })).toBeVisible()
    const grid = page.getByRole('grid', { name: /Calendrier des points de feu/ })
    await expect(grid.locator('button[data-month]')).toHaveCount(25 * 12)
    await expect(grid.getByRole('rowheader').last()).toHaveText('Normale')
    await expect(page.locator('text=—')).toHaveCount(0) // plus de tiret cadratin
    expect(pageErrors).toEqual([])
  })

  test('lecture grand public : réponse en une phrase, technique replié', async ({ page }) => {
    const summary = page.getByRole('region', { name: /En bref - Gabon/ })
    await expect(summary).toContainText(/En 2025, environ [\d\s]+ points de feu détectés/)
    await expect(summary).toContainText(/année normale/)
    // Colonne de droite déjà utile au chargement : dernier mois disponible
    await expect(page.locator('aside')).toContainText('Dernier mois disponible')
    await expect(page.locator('aside')).toContainText('Décembre 2025', { ignoreCase: true })
    // Régimes capteurs repliés par défaut, dépliables
    const satellites = page.getByText('Quels satellites ont observé ?')
    await expect(page.getByText("Régimes d'observation")).toBeHidden()
    await satellites.click()
    await expect(page.getByText("Régimes d'observation")).toBeVisible()
    // « Comment c'est calculé ? » mène à l'onglet Méthodologie, sans le réglage de couleur
    await page.getByRole('button', { name: "Comment c'est calculé ?" }).click()
    await expect(page.getByRole('tab', { name: 'Méthodologie & évaluation' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    await expect(page.getByText('Colorer le calendrier selon')).toHaveCount(0)
  })

  test('explore un mois atypique', async ({ page }) => {
    await page.locator('[data-month="2024-01"]').click()
    const detail = page.locator('aside')
    await expect(detail).toContainText('Mois sélectionné')
    await expect(detail).toContainText('Janvier 2024', { ignoreCase: true })
    await expect(detail).toContainText(/\+\d+,\d %/)
    await expect(detail).toContainText(/2e janvier le plus actif sur 25/)
    await expect(page.getByText("Comparaison avec l'année type")).toHaveCount(0) // supprimé
  })

  test('calendrier avant / après, synchronisé avec le graphe', async ({ page }) => {
    const calendar = page.locator('section[aria-labelledby="calendar-title"]')
    const chart = page.locator('section[aria-labelledby="chart-title"]')
    const cell2005 = page.locator('[data-month="2005-08"]')
    await expect(cell2005).toHaveAttribute('aria-label', /points de feu, /)
    const colorAfter = await cell2005.evaluate((el) => getComputedStyle(el).backgroundColor)

    // Bascule depuis le calendrier : brut MODIS, rupture 2012, le graphe suit
    await calendar.getByText('Données brutes', { exact: true }).click()
    await expect(cell2005).toHaveAttribute('aria-label', /points de feu bruts MODIS \(Terra \+ Aqua\)/)
    await expect(page.locator('[data-month="2013-08"]')).toHaveAttribute('aria-label', /bruts VIIRS S-NPP/)
    await expect(calendar).toContainText('Changement de satellite : MODIS → VIIRS (février 2012)')
    expect(await cell2005.evaluate((el) => getComputedStyle(el).backgroundColor)).not.toBe(colorAfter)
    await expect(page.getByRole('radio', { name: 'Écart à la normale' })).toBeDisabled()
    await chart.scrollIntoViewIfNeeded()
    await expect(chart.getByText(/crée une rupture/)).toBeVisible()

    // Bascule depuis le graphe : le calendrier revient en vue harmonisée
    await chart.getByText('Données corrigées', { exact: true }).click()
    await expect(cell2005).toHaveAttribute('aria-label', /points de feu, /)
    await expect(page.getByRole('radio', { name: 'Écart à la normale' })).toBeEnabled()
  })

  test('filtre : torchères, couleur, période', async ({ page }) => {
    const counter = page.locator('#filter-static-count')
    await expect(counter).toContainText('détections retirées')
    await page.getByRole('checkbox', { name: /Exclure les sources industrielles/ }).uncheck()
    await expect(counter).toContainText('que le filtre retirerait')

    await page.locator('label.segmented-item', { hasText: 'Écart à la normale' }).click()
    await expect(page.getByText('Par rapport à la normale')).toBeVisible()

    await page.getByRole('combobox', { name: 'Année de début' }).selectOption('2015')
    await page.getByRole('combobox', { name: 'Année de fin' }).selectOption('2020')
    await expect(page.locator('button[data-month]')).toHaveCount(6 * 12)
  })

  test('navigue au clavier dans le calendrier', async ({ page }) => {
    await page.locator('[data-month="2024-01"]').click()
    await page.keyboard.press('ArrowRight')
    await expect(page.locator('[data-month="2024-02"]')).toBeFocused()
    await page.keyboard.press('ArrowUp')
    await expect(page.locator('[data-month="2023-02"]')).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(page.locator('aside')).toContainText('Février 2023', { ignoreCase: true })
  })

  test('graphe : la bascule avant / après conserve le zoom', async ({ page, isMobile }) => {
    test.skip(isMobile, 'Glisser le curseur ECharts : vérifié sur desktop')
    const chart = page.locator('x-vue-echarts')
    await chart.scrollIntoViewIfNeeded()
    await expect(chart.locator('canvas').first()).toBeVisible()
    const box = (await chart.boundingBox())!
    // Zoom à la molette au centre du tracé (dataZoom « inside », même effet que le curseur)
    await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.45)
    for (let i = 0; i < 4; i++) await page.mouse.wheel(0, -300)
    const label = page.getByText(/Zoom conservé :/)
    await expect(label).toBeVisible()
    const before = await label.textContent()
    const chartSection = page.locator('section[aria-labelledby="chart-title"]')
    await chartSection.getByText('Données brutes', { exact: true }).click()
    await expect(page.getByText(/crée une rupture/)).toBeVisible()
    await expect(label).toHaveText(before!)
  })

  test('carte hors ligne : grille et sites statiques sans fond de carte', async ({ page }) => {
    const map = page.getByRole('region', { name: /Carte des détections/ })
    await map.scrollIntoViewIfNeeded()
    await expect(page.getByText(/352 cellules de 0,25°.*183 sites industriels exclus/)).toBeVisible()
    await expect(page.getByText('Fond de carte (hors ligne)')).toBeVisible()
    await expect(map.locator('canvas')).toBeVisible()
  })

  test('exporte le CSV de la zone et de la période', async ({ page }) => {
    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Exporter CSV' }).click()
    const file = await download
    expect(file.suggestedFilename()).toBe('firepulse_GA_2001-01_2025-12_filtre.csv')
    const text = await (await file.createReadStream())!.toArray()
    const lines = Buffer.concat(text).toString('utf-8').trim().split('\n')
    expect(lines[0]).toMatch(/^region,month,filter_static,modis_count/)
    expect(lines).toHaveLength(1 + 25 * 12)
  })

  test('lit la méthode et ses réserves', async ({ page }) => {
    await page.getByRole('tab', { name: 'Méthodologie & évaluation' }).click()
    const panel = page.getByRole('tabpanel', { name: 'Méthodologie & évaluation' })
    await expect(panel).toContainText('protocole en revue scientifique (M1)')
    await expect(panel.locator('tbody tr')).toHaveCount(5)
    await expect(panel).toContainText('Points en cours de revue avant validation')
  })

  test('tient en largeur sur mobile', async ({ page, isMobile }) => {
    test.skip(!isMobile, 'Contrôle propre au gabarit mobile')
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
  })
})
