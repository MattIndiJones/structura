<template>
  <div class="min-h-screen bg-slate-950 flex items-center justify-center px-4">
    <div class="w-full max-w-sm flex flex-col gap-6">

      <!-- Logo -->
      <div class="flex flex-col items-center gap-3">
        <div class="w-12 h-12 bg-blue-600 rounded-xl flex items-center justify-center font-display font-black text-white text-xl">S</div>
        <div class="text-center">
          <div class="text-xl font-display font-black text-slate-100 tracking-tight">Structura</div>
          <div class="text-xs text-slate-500 mt-0.5">Pricing Engine for Structured Products</div>
        </div>
      </div>

      <!-- Tabs -->
      <div class="flex border-b border-slate-800">
        <button
          :class="['flex-1 py-2 text-xs font-semibold transition-colors border-b-2 -mb-px',
                   mode === 'login' ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-500 hover:text-slate-400']"
          @click="mode = 'login'; error = ''"
        >Connexion</button>
        <button
          :class="['flex-1 py-2 text-xs font-semibold transition-colors border-b-2 -mb-px',
                   mode === 'register' ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-500 hover:text-slate-400']"
          @click="mode = 'register'; error = ''"
        >Créer un compte</button>
      </div>

      <!-- Login form -->
      <div v-if="mode === 'login'" class="card flex flex-col gap-4">
        <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>

        <div class="flex flex-col gap-1">
          <label class="label">Identifiant</label>
          <input v-model="username" type="text" class="input" placeholder="admin" @keyup.enter="submit" autofocus />
        </div>
        <div class="flex flex-col gap-1">
          <label class="label">Mot de passe</label>
          <input v-model="password" type="password" class="input" placeholder="••••••••" @keyup.enter="submit" />
        </div>

        <button class="btn-primary w-full" :disabled="loading" @click="submit">
          <span v-if="loading" class="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-2"></span>
          Se connecter
        </button>
      </div>

      <!-- Register form -->
      <div v-else class="card flex flex-col gap-4">
        <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>

        <div class="flex flex-col gap-1">
          <label class="label">Identifiant *</label>
          <input v-model="regUsername" type="text" class="input" placeholder="ex: jdupont" autofocus />
        </div>
        <div class="flex flex-col gap-1">
          <label class="label">E-mail *</label>
          <input v-model="regEmail" type="email" class="input" placeholder="ex: j.dupont@banque.fr" />
        </div>
        <div class="flex flex-col gap-1">
          <label class="label">Mot de passe * <span class="text-slate-600">(min. 6 car.)</span></label>
          <input v-model="regPassword" type="password" class="input" placeholder="••••••••" @keyup.enter="register" />
        </div>
        <div class="flex flex-col gap-1">
          <label class="label">Entité / équipe <span class="text-slate-600">(optionnel)</span></label>
          <input v-model="regEntity" type="text" class="input" placeholder="ex: Desk Structuration" />
          <span class="text-[10px] text-slate-600">Laissez vide pour rejoindre l'entité Demo.</span>
        </div>

        <button class="btn-primary w-full" :disabled="loading" @click="register">
          <span v-if="loading" class="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-2"></span>
          Créer mon compte
        </button>
      </div>

      <!-- Quick login (démo) — visible en mode connexion seulement -->
      <div v-if="mode === 'login'" class="flex flex-col gap-2">
        <div class="text-[10px] text-slate-600 text-center uppercase tracking-widest">Accès rapide (démo)</div>
        <div class="grid grid-cols-2 gap-2">
          <button
            class="btn-secondary text-xs py-2 flex flex-col items-center gap-0.5"
            :disabled="loading"
            @click="quickLogin('admin', 'admin123')"
          >
            <span class="font-bold text-blue-400">Admin</span>
            <span class="text-[10px] text-slate-600">Tous les droits</span>
          </button>
          <button
            class="btn-secondary text-xs py-2 flex flex-col items-center gap-0.5"
            :disabled="loading"
            @click="quickLogin('test', 'test123')"
          >
            <span class="font-bold text-slate-300">Utilisateur test</span>
            <span class="text-[10px] text-slate-600">Droits standard</span>
          </button>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import AlertMessage from '../components/ui/AlertMessage.vue'

const router   = useRouter()
const auth     = useAuthStore()
const mode     = ref('login')  // 'login' | 'register'
const loading  = ref(false)
const error    = ref('')

// Login fields
const username = ref('')
const password = ref('')

// Register fields
const regUsername = ref('')
const regEmail    = ref('')
const regPassword = ref('')
const regEntity   = ref('')

async function submit() {
  if (!username.value || !password.value) return
  loading.value = true
  error.value = ''
  try {
    await auth.login(username.value, password.value)
    router.push('/')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function quickLogin(u, p) {
  username.value = u
  password.value = p
  await submit()
}

async function register() {
  if (!regUsername.value || !regEmail.value || !regPassword.value) {
    error.value = 'Identifiant, e-mail et mot de passe sont obligatoires'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: regUsername.value,
        email: regEmail.value,
        password: regPassword.value,
        entity_name: regEntity.value || null,
      }),
    })
    const data = await res.json()
    if (!res.ok) { error.value = data.detail || 'Erreur lors de la création du compte'; return }
    // Auto-login with the fresh credentials
    await auth.login(regUsername.value, regPassword.value)
    router.push('/')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>
