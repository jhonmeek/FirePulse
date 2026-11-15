import AxeBuilder from '@axe-core/playwright'
import { expect, test } from './fixtures'

/**
 * Audit axe-core (WCAG 2.1 A/AA, dont contrastes) dans un vrai navigateur, après rendu des
 * graphes et de la carte. Échec sur toute violation « serious » ou « critical ».
 */
async function audit(page: import('@playwright/test').Page) {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    // Canvas ECharts / MapLibre : contenu graphique, décrit par aria-label et tables alternatives.
    .exclude('canvas')
    .analyze()
  // Trace lisible dans la sortie : preuve que l'audit a bien examiné la page.
  console.log(
    `[axe] ${results.passes.length} règles respectées, ${results.violations.length} violation(s) :`,
    results.violations.map((v) => `${v.id} (${v.impact}, ${v.nodes.length} nœud(s))`).join(', ') || 'aucune',
    `| contraste vérifié sur ${results.passes.find((r) => r.id === 'color-contrast')?.nodes.length ?? 0} nœud(s)`,
  )
  const unsure = results.incomplete.find((r) => r.id === 'color-contrast')
  if (unsure)
    console.log(
      `[axe] contraste non calculable (à vérifier) sur ${unsure.nodes.length} nœud(s) :`,
      unsure.nodes.slice(0, 12).map((n) => `${n.target.join(' ')} [${n.any[0]?.message?.slice(0, 70)}]`),
    )
  const blocking = results.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))
  const report = blocking.map((v) => ({
    id: v.id,
    impact: v.impact,
    help: v.help,
    nodes: v.nodes.slice(0, 5).map((n) => `${n.target.join(' ')} :: ${n.failureSummary?.split('\n')[1] ?? ''}`),
  }))
  return report
}

test.describe('accessibilité (axe-core, WCAG 2.1 AA)', () => {
  test('onglet Explorer', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('x-vue-echarts canvas').first()).toBeVisible()
    await page.locator('[data-month="2024-01"]').click()
    expect(await audit(page)).toEqual([])
  })

  test('onglet Méthodologie & évaluation', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('tab', { name: 'Méthodologie & évaluation' }).click()
    await expect(page.getByRole('tabpanel').locator('tbody tr')).toHaveCount(5)
    expect(await audit(page)).toEqual([])
  })
})
