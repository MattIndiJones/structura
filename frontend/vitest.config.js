import { defineConfig } from 'vitest/config'

// Tests unitaires du front. Le pricing lui-même est testé côté Python — ici on
// couvre ce que la suite backend ne peut PAS voir : le store et les composables,
// c'est-à-dire les endroits où une saisie se perd ou une requête se construit
// mal. Trois défauts de ce chantier vivaient exactement là, et aucun test ne
// pouvait les attraper.
export default defineConfig({
  test: {
    // Le store n'a pas besoin du DOM. `localStorage`, seul emprunt au
    // navigateur (utils/api.js y lit le jeton), est bouchonné dans setup.js —
    // installer jsdom pour une seule fonction coûterait plus qu'il ne rend.
    environment: 'node',
    include: ['src/**/*.test.js'],
    setupFiles: ['./src/test/setup.js'],
    restoreMocks: true,
  },
})
