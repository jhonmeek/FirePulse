import { test as base, expect } from '@playwright/test'

/**
 * Chaque test tourne « sans réseau NASA ni Internet » : toute requête qui ne vise pas le
 * serveur local de la démo est coupée (fond de carte compris). On vérifie ainsi que la démo
 * reste complète hors ligne, et on relève les erreurs JS de la page.
 *
 * `auto: true` : le blocage s'applique à tous les tests, même ceux qui ne lisent pas
 * `pageErrors` (sans cela, un test pouvait passer grâce au réseau).
 */
export const test = base.extend<{ pageErrors: string[] }>({
  pageErrors: [
    async ({ page }, use) => {
      const errors: string[] = []
      page.on('pageerror', (e) => errors.push(e.message))
      await page.route(
        (url) => !['127.0.0.1', 'localhost'].includes(url.hostname),
        (route) => route.abort('internetdisconnected'),
      )
      await use(errors)
    },
    { auto: true },
  ],
})

export { expect }
