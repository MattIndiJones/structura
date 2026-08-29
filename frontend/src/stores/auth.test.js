/**
 * Ce que la déconnexion doit garantir.
 *
 * Le jeton vit dans `localStorage`, donc il survit à un rechargement : s'il
 * n'est pas effacé, le compte suivant repart sur la session du précédent. C'est
 * la seule partie de la déconnexion qui touche à la sécurité, et la seule que
 * le rechargement ne rattrape pas — il faut donc qu'elle soit faite AVANT.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useAuthStore } from './auth.js'

describe('la déconnexion ne laisse rien derrière', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('efface le jeton du stockage, pas seulement de la mémoire', () => {
    localStorage.setItem('auth_token', 'jeton-du-compte-A')
    const auth = useAuthStore()
    auth.logout()

    // Un jeton laissé en stockage reconnecterait le compte A au prochain
    // chargement, y compris après que quelqu'un d'autre se soit assis devant.
    expect(localStorage.getItem('auth_token')).toBeNull()
  })

  it('oublie le jeton et le profil en mémoire', () => {
    const auth = useAuthStore()
    auth.token = 'x'
    auth.user = { id: 1, username: 'phil' }
    auth.logout()

    expect(auth.token).toBeNull()
    expect(auth.user).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
  })
})
