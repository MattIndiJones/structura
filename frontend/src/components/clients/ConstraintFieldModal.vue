<!--
  Déclarer un champ de préférence propre à la maison ou au client.

  Le choix de PORTÉE est la seule vraie décision de cet écran, et c'est celle
  qu'on prend mal si on ne la nomme pas : un champ « maison » apparaît sur
  toutes les fiches, un champ « ce client » n'apparaît que sur la sienne. Les
  deux se justifient, mais pas pour la même chose — une politique interne d'un
  côté, le vocabulaire d'un client de l'autre.
-->
<template>
  <BaseModal :model-value="true" title="Ajouter un champ de préférence"
             max-width="34rem" @close="$emit('close')">
    <div class="flex flex-col gap-4">

      <div>
        <label class="label">Libellé</label>
        <input v-model="form.label" class="input" ref="premier"
               placeholder="Poche défensive max" @keyup.enter="enregistrer" />
        <p class="echo">
          Clé technique : <code>{{ cleProbable || '—' }}</code>
          — elle ne changera plus, c'est elle qui est écrite dans la fiche de
          chaque client.
        </p>
      </div>

      <div>
        <label class="label">Portée</label>
        <div class="flex flex-col gap-2">
          <label class="portee" :class="{ actif: form.scope === 'client' }">
            <input v-model="form.scope" type="radio" value="client" />
            <span>
              <strong>Propre à ce client</strong>
              <span class="block text-xs" style="color: var(--muted)">
                Un nom convenu entre vous et lui — sa « poche défensive », sa
                « limite Rouge ». N'apparaît que sur sa fiche.
              </span>
            </span>
          </label>
          <label class="portee" :class="{ actif: form.scope === 'entity' }">
            <input v-model="form.scope" type="radio" value="entity" />
            <span>
              <strong>Toute la maison</strong>
              <span class="block text-xs" style="color: var(--muted)">
                Une politique que le desk suit partout. Le champ apparaît sur
                toutes les fiches clients.
              </span>
            </span>
          </label>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="label">Type</label>
          <select v-model="form.kind" class="select">
            <option v-for="type in types" :key="type.value" :value="type.value">
              {{ type.label }}
            </option>
          </select>
        </div>
        <div>
          <label class="label">Unité (facultative)</label>
          <input v-model="form.unit" class="input" placeholder="%, mois, EUR…" />
        </div>
      </div>

      <!-- Une liste puise ses valeurs quelque part : un catalogue vivant, ou
           une liste écrite ici. Sans l'un ni l'autre, elle serait ouverte à
           tout et ne standardiserait rien. -->
      <div v-if="estListe">
        <label class="label">Valeurs proposées</label>
        <select v-model="form.catalog" class="select">
          <option :value="null">Aucune source — liste écrite à la main</option>
          <option v-for="cat in catalogues" :key="cat" :value="cat">
            {{ LIBELLE_CATALOGUE[cat] || cat }}
          </option>
        </select>
        <textarea v-if="!form.catalog" v-model="optionsBrutes" class="input mt-2" rows="2"
                  placeholder="Défensif, Équilibré, Dynamique"></textarea>
        <label v-if="form.kind !== 'list_enum'"
               class="flex items-center gap-2 text-sm mt-2 cursor-pointer">
          <input v-model="form.free_entry" type="checkbox" />
          <span>
            Autoriser une valeur hors liste
            <span class="block text-xs" style="color: var(--muted)">
              À laisser coché pour les émetteurs : l'historique d'un client
              nomme « Citi » ce que notre catalogue appelle « Citigroup ».
            </span>
          </span>
        </label>
      </div>

      <div>
        <label class="label">Aide affichée sous le champ (facultative)</label>
        <textarea v-model="form.help_text" class="input" rows="2"></textarea>
      </div>

      <AlertMessage v-if="erreur" kind="error">{{ erreur }}</AlertMessage>
    </div>

    <template #footer>
      <button class="btn-ghost" @click="$emit('close')">Annuler</button>
      <button class="btn-primary" :disabled="!form.label.trim() || envoi"
              @click="enregistrer">Ajouter le champ</button>
    </template>
  </BaseModal>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useClientsStore } from '../../stores/clients.js'
import AlertMessage from '../ui/AlertMessage.vue'
import BaseModal from '../ui/BaseModal.vue'

const props = defineProps({
  clientId: { type: [Number, String], required: true },
})
const emit = defineEmits(['close', 'created'])

const LIBELLE_CATALOGUE = {
  underlyings: 'Catalogue des sous-jacents',
  counterparties: 'Catalogue des contreparties',
  currencies: 'Devises couvertes par un calendrier',
  ratings: 'Échelle de notation S&P / Fitch',
}

const store = useClientsStore()
const premier = ref(null)
const types = ref([])
const catalogues = ref([])
const optionsBrutes = ref('')
const erreur = ref('')
const envoi = ref(false)

const form = reactive({
  label: '', kind: 'percent', scope: 'client', unit: '',
  catalog: null, free_entry: true, help_text: '',
})

const estListe = computed(() => form.kind.startsWith('list_'))

// Reproduit `normalize_key` du serveur — à titre indicatif seulement. La clé
// qui fait foi est celle que le serveur renvoie ; l'afficher ici sert à ce que
// personne ne découvre après coup le nom technique de son champ.
const cleProbable = computed(() => form.label
  .normalize('NFD').replace(/[̀-ͯ]/g, '')
  .toLowerCase().replace(/[^a-z0-9]+/g, '_')
  .replace(/^_+|_+$/g, '').slice(0, 60))

async function enregistrer() {
  erreur.value = ''
  envoi.value = true
  try {
    const cree = await store.declarerChamp({
      label: form.label.trim(),
      kind: form.kind,
      client_id: form.scope === 'client' ? Number(props.clientId) : null,
      unit: form.unit.trim() || null,
      catalog: estListe.value ? form.catalog : null,
      options: estListe.value && !form.catalog
        ? optionsBrutes.value.split(',').map(o => o.trim()).filter(Boolean)
        : [],
      free_entry: form.kind === 'list_enum' ? false : form.free_entry,
      help_text: form.help_text.trim() || null,
    })
    emit('created', cree)
  } catch (e) {
    erreur.value = e.message || 'Le champ n’a pas pu être déclaré.'
  } finally {
    envoi.value = false
  }
}

onMounted(async () => {
  premier.value?.focus()
  try {
    const meta = await store.lireMetaContraintes()
    types.value = meta.kinds || []
    catalogues.value = meta.catalogs || []
  } catch {
    // Les types viennent du serveur pour ne pas diverger. S'ils manquent, on
    // laisse un repli minimal plutôt qu'un écran mort.
    types.value = [{ value: 'text', label: 'Texte libre' },
                   { value: 'percent', label: 'Pourcentage' }]
  }
})
</script>

<style scoped>
.echo { font-size: .7rem; color: var(--subtle); margin-top: .25rem; }
.portee {
  display: flex; gap: .6rem; align-items: flex-start; cursor: pointer;
  padding: .6rem; border: 1px solid var(--border); border-radius: .5rem;
}
.portee.actif { border-color: var(--accent); background: var(--accent-light); }
</style>
