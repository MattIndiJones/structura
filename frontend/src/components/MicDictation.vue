<!--
  Dictée d'un champ texte.

  Le transcrit s'INSÈRE à la position du curseur, il ne remplace jamais le
  contenu : on dicte un premier jet, on corrige au clavier, on repositionne le
  curseur, on dicte un complément. Le champ reste la seule source de vérité, et
  reste éditable de bout en bout.

  Rien ne part au modèle de langage : la transcription remonte brute. Une dictée
  qui avale « à tout moment » décrit un autre produit — c'est exactement ce que
  l'aide de l'écran appelle « la différence entre deux produits qui ne valent
  pas le même prix ». La faire relire par un modèle donnerait une description
  plus jolie et parfois d'un autre produit ; c'est à l'utilisateur de relire.

  Deux dispositifs servent à SAVOIR ce qui s'est passé quand rien ne sort : un
  indicateur de niveau pendant l'enregistrement, et la réécoute du dernier
  enregistrement. Sans eux, « Rien n'a été entendu » ne distingue pas un micro
  muet d'un moteur qui a échoué — et on cherche du mauvais côté.

  L'audio ne quitte pas la machine (Whisper local, cf. services/transcription).
-->
<template>
  <span class="inline-flex items-center gap-2">
    <!-- Tant que les poids ne sont pas là, on ne propose PAS le micro : le
         téléchargement lancé au milieu d'une dictée la faisait échouer. -->
    <button v-if="needsPrepare" type="button"
            class="btn-secondary text-[11px] px-2 py-1 whitespace-nowrap"
            :disabled="preparing"
            title="Télécharge le modèle de dictée, une fois pour toutes."
            @click="preparer">
      <template v-if="preparing">
        <span class="w-3 h-3 border border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
        Téléchargement du modèle…
      </template>
      <template v-else>⤓ Préparer la dictée (≈ 480 Mo)</template>
    </button>

    <button v-else type="button" class="btn-secondary text-[11px] px-2 py-1 whitespace-nowrap"
            :disabled="disabled || busy || !ready"
            :title="boutonTitre"
            :style="recording ? recStyle : null"
            @click="toggle">
      <template v-if="recording">■ Arrêter · {{ chrono }}</template>
      <template v-else-if="busy">
        <span class="w-3 h-3 border border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
        Transcription…
      </template>
      <template v-else>🎤 Dicter</template>
    </button>

    <!-- Niveau du micro. Le chrono qui défile ne prouve que l'ouverture du
         flux ; cette barre prouve qu'un son y arrive. C'est toute la différence
         entre « le moteur a échoué » et « le micro est muet ». -->
    <span v-if="recording" class="inline-flex items-center gap-1"
          :title="`Niveau du micro : ${Math.round(level * 100)} %`">
      <span class="block rounded-full overflow-hidden bg-slate-300"
            style="width: 54px; height: 6px;">
        <span class="block h-full" style="transition: width 80ms linear;"
              :style="{ width: Math.round(level * 100) + '%',
                        background: level > MUET ? 'var(--positive)' : 'var(--negative)' }"></span>
      </span>
      <!-- Le NOM du périphérique retenu. Chrome garde un micro par site : c'est
           la première chose à regarder quand « le micro marche partout
           ailleurs » mais pas ici. -->
      <span class="text-[10px] text-slate-500 max-w-[170px] truncate"
            :title="deviceLabel">{{ deviceLabel }}</span>
      <span v-if="trackMuted" class="text-[10px]" style="color: var(--negative)">
        — source coupée
      </span>
    </span>

    <button v-if="lastUrl && !recording" type="button"
            class="text-[11px] text-slate-500 hover:underline whitespace-nowrap"
            title="Réécouter le dernier enregistrement. Si vous vous entendez, la capture est hors de cause."
            @click="reecouter">▶ réécouter</button>

    <button v-if="undoState" type="button"
            class="text-[11px] text-slate-500 hover:underline whitespace-nowrap"
            title="Remettre le champ dans l'état d'avant la dernière dictée"
            @click="annuler">↶ annuler la dictée</button>

    <span v-if="message" class="text-[11px]" :style="{ color: messageColor }">
      {{ message }}
    </span>
  </span>
</template>

<script setup>
import { ref, computed, onBeforeUnmount, nextTick } from 'vue'
import { usePricingStore } from '../stores/pricing.js'

const props = defineProps({
  // Texte courant du champ dicté (v-model).
  modelValue: { type: String, default: '' },
  // L'élément <textarea>/<input> lui-même : sans lui on ne connaît pas la
  // position du curseur et l'insertion ne pourrait qu'ajouter à la fin.
  targetEl: { type: Object, default: null },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const store = usePricingStore()

const state = ref('idle')          // idle | recording | transcribing
const seconds = ref(0)
const message = ref('')
const messageKind = ref('info')
const undoState = ref(null)        // { texte, caret } d'avant la dernière dictée
const preparing = ref(false)
const level = ref(0)               // niveau instantané, 0..1
const peak = ref(0)                // niveau maximal de l'enregistrement en cours
const lastUrl = ref(null)          // dernier enregistrement, pour la réécoute
// Le compteur a-t-il RÉELLEMENT tourné ? Sans cette réserve, un AudioContext
// suspendu ferait conclure « micro muet » alors que l'enregistrement capte très
// bien. Un diagnostic qui peut se tromper est pire que pas de diagnostic.
const meterOk = ref(false)
const deviceLabel = ref('')        // le micro que le NAVIGATEUR a choisi
const trackMuted = ref(false)

// Seuil au-dessous duquel on considère qu'aucune parole n'est arrivée. Le bruit
// de fond d'une pièce calme tourne autour de 0,01–0,03 sur cette échelle ; une
// voix normale dépasse 0,3 sans effort.
const MUET = 0.06

let stream = null
let recorder = null
let chunks = []
let timer = null
let audioCtx = null
let analyser = null
let rafId = null
let buffer = null
let player = null

const recording = computed(() => state.value === 'recording')
const busy = computed(() => state.value === 'transcribing')
const engine = computed(() => store.transcribeEngines?.engines?.[0] || null)
const ready = computed(() => !!engine.value?.ready)
// Paquet installé mais poids absents : c'est le cas qui a produit un « Failed
// to fetch » — les 480 Mo partaient dans la requête de transcription, qui
// pendait jusqu'à ce que le navigateur lâche.
const needsPrepare = computed(() =>
  ready.value && !!engine.value && !engine.value.model_downloaded)
const messageColor = computed(() =>
  messageKind.value === 'error' ? 'var(--negative)' : 'var(--gold)')

const recStyle = {
  background: 'var(--negative-light)',
  color: 'var(--negative)',
  borderColor: 'var(--negative)',
}

const chrono = computed(() => {
  const m = Math.floor(seconds.value / 60)
  const s = String(seconds.value % 60).padStart(2, '0')
  return `${m}:${s}`
})

const boutonTitre = computed(() => {
  if (!ready.value) return engine.value?.hint || 'Moteur de dictée indisponible.'
  if (engine.value && !engine.value.model_downloaded) return engine.value.hint
  return 'Dicter la description au micro. L\'audio ne quitte pas cette machine.'
})

store.loadTranscribeEngines()

async function preparer() {
  preparing.value = true
  message.value = ''
  const res = await store.prepareTranscribe()
  preparing.value = false
  if (res?.error) signale(res.error, 'error')
  else signale('Moteur prêt.', 'info')
}

// ── Niveau du micro ────────────────────────────────────────────────
// Confort de diagnostic, jamais un prérequis : si WebAudio échoue, la dictée
// continue sans barre plutôt que de refuser d'enregistrer.
async function startMeter(flux) {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext
    if (!Ctx) return
    audioCtx = new Ctx()
    // INDISPENSABLE. On arrive ici après un `await getUserMedia`, donc hors du
    // geste utilisateur : Chrome crée alors le contexte en état « suspended »,
    // et l'analyseur ne rend que du silence — pendant que MediaRecorder, lui,
    // enregistre parfaitement. C'est exactement le piège qui fait accuser un
    // micro qui marche.
    if (audioCtx.state === 'suspended') await audioCtx.resume()
    analyser = audioCtx.createAnalyser()
    analyser.fftSize = 512
    audioCtx.createMediaStreamSource(flux).connect(analyser)
    buffer = new Uint8Array(analyser.fftSize)
    meterOk.value = audioCtx.state === 'running'
    tick()
  } catch {
    stopMeter()
  }
}

function tick() {
  if (!analyser) return
  analyser.getByteTimeDomainData(buffer)
  let somme = 0
  for (let i = 0; i < buffer.length; i++) {
    const v = (buffer[i] - 128) / 128
    somme += v * v
  }
  // RMS mis à l'échelle : la parole tourne entre 0,05 et 0,15 en RMS brut, une
  // barre linéaire y resterait plate et n'apprendrait rien.
  level.value = Math.min(1, Math.sqrt(somme / buffer.length) * 6)
  if (level.value > peak.value) peak.value = level.value
  rafId = requestAnimationFrame(tick)
}

function stopMeter() {
  if (rafId) cancelAnimationFrame(rafId)
  rafId = null
  analyser = null
  buffer = null
  if (audioCtx) {
    audioCtx.close().catch(() => {})
    audioCtx = null
  }
  level.value = 0
}

// ── Enregistrement ─────────────────────────────────────────────────
// Clic pour démarrer, clic pour arrêter — pas de maintien enfoncé : décrire un
// payoff prend 30 à 60 s, on ne tient pas un bouton pendant ce temps-là.
function toggle() {
  if (recording.value) stopRecording()
  else startRecording()
}

function pickMime() {
  const candidats = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
  return candidats.find(t => window.MediaRecorder?.isTypeSupported?.(t)) || ''
}

async function startRecording() {
  message.value = ''
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    signale('Ce navigateur ne sait pas enregistrer le micro.', 'error')
    return
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch {
    // Refus, absence de micro, ou page non sécurisée : localhost est un
    // contexte sûr, mais l'app ouverte depuis une autre machine par son IP ne
    // l'est pas et le navigateur bloque alors le micro sans autre explication.
    signale("Micro inaccessible. Autorisez le microphone pour cette page "
            + '(et ouvrez l\'app sur localhost, pas par une adresse IP).', 'error')
    return
  }
  chunks = []
  peak.value = 0
  meterOk.value = false

  // QUEL micro le navigateur a-t-il pris ? Chrome garde un périphérique par
  // SITE, qui n'est pas forcément le défaut de Windows : un casque débranché ou
  // une webcam restés sélectionnés ici donnent un silence parfait pendant que
  // le micro « qui marche partout ailleurs » n'est simplement pas celui-là.
  const piste = stream.getAudioTracks()[0] || null
  deviceLabel.value = piste?.label || 'micro inconnu'
  // `muted` sur une piste ne veut pas dire « coupé par l'utilisateur » : la
  // source est temporairement incapable de fournir des données — coupure
  // matérielle, ou application qui tient le périphérique en exclusif.
  trackMuted.value = !!piste?.muted
  if (piste) {
    piste.onmute = () => { trackMuted.value = true }
    piste.onunmute = () => { trackMuted.value = false }
  }

  const mimeType = pickMime()
  recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
  recorder.ondataavailable = e => { if (e.data?.size) chunks.push(e.data) }
  recorder.onstop = envoyer
  recorder.start()
  startMeter(stream)
  state.value = 'recording'
  seconds.value = 0
  timer = setInterval(() => { seconds.value += 1 }, 1000)
}

function stopRecording() {
  clearInterval(timer); timer = null
  stopMeter()
  // Basculer TOUT DE SUITE : `onstop` est asynchrone, et entre le clic et son
  // arrivée le bouton afficherait encore « Arrêter », cliquable une seconde
  // fois — donc un second enregistrement lancé sur le premier.
  state.value = 'transcribing'
  if (recorder && recorder.state !== 'inactive') recorder.stop()   // -> envoyer()
}

// Couper les pistes rend la main sur le micro. Sans cela le voyant du
// navigateur reste allumé après la fermeture de la fenêtre, ce qui donne
// l'impression — justifiée — que l'application écoute encore.
function releaseMic() {
  if (stream) {
    stream.getTracks().forEach(t => t.stop())
    stream = null
  }
}

function abandonner() {
  clearInterval(timer); timer = null
  stopMeter()
  if (recorder && recorder.state !== 'inactive') {
    recorder.onstop = null          // ne pas transcrire ce qu'on abandonne
    try { recorder.stop() } catch { /* déjà arrêté */ }
  }
  recorder = null
  releaseMic()
  if (lastUrl.value) { URL.revokeObjectURL(lastUrl.value); lastUrl.value = null }
  if (player) { player.pause(); player = null }
}

onBeforeUnmount(abandonner)

async function envoyer() {
  const blob = new Blob(chunks, { type: recorder?.mimeType || 'audio/webm' })
  recorder = null
  releaseMic()                       // dès la fin de l'enregistrement, pas après
  if (!blob.size) { signale('Enregistrement vide.', 'error'); state.value = 'idle'; return }

  // Gardé pour la réécoute : s'entendre soi-même met la capture hors de cause
  // et fait chercher du bon côté.
  if (lastUrl.value) URL.revokeObjectURL(lastUrl.value)
  lastUrl.value = URL.createObjectURL(blob)

  // On ne conclut au silence que si le compteur a réellement tourné.
  const mesure = meterOk.value
  const muet = mesure && peak.value < MUET

  state.value = 'transcribing'
  const res = await store.transcribeAudio(blob)
  state.value = 'idle'

  if (res?.error) { signale(res.error, 'error'); return }
  const texte = (res?.text || '').trim()
  if (!texte) {
    // Distinguer les deux causes, sinon on cherche du mauvais côté. Le niveau
    // maximal mesuré pendant l'enregistrement tranche : micro muet, ou moteur
    // qui n'a rien reconnu.
    if (muet) {
      signale(`Aucun son n'est arrivé depuis « ${deviceLabel.value} » pendant `
              + "l'enregistrement. Chrome retient un micro PAR SITE, qui n'est "
              + 'pas forcément celui de Windows : changez-le par le cadenas de '
              + 'la barre d\'adresse → Microphone.', 'error')
    } else if (!mesure) {
      // Le compteur n'a pas tourné : on ne sait pas si du son est arrivé, et on
      // ne va pas l'inventer. La réécoute, elle, tranche pour de bon.
      signale("Rien n'a été reconnu, et le niveau du micro n'a pas pu être "
              + 'mesuré. Réécoutez l\'enregistrement : c\'est lui qui tranche.',
              'error')
    } else {
      // Le serveur rend aussi un texte vide quand le moteur n'a fait que
      // recracher son amorce de vocabulaire : mieux vaut rien qu'une phrase
      // crédible et inventée dans une description de produit.
      signale(`Du son a bien été capté depuis « ${deviceLabel.value} », mais `
              + 'rien n\'a été reconnu. Réécoutez pour vérifier, puis reparlez '
              + 'plus distinctement.', 'error')
    }
    return
  }
  inserer(texte)
}

function reecouter() {
  if (!lastUrl.value) return
  if (!player) player = new Audio()
  player.src = lastUrl.value
  player.play().catch(() => signale('Lecture impossible dans ce navigateur.', 'error'))
}

function signale(txt, kind = 'info') {
  message.value = txt
  messageKind.value = kind
}

// ── Insertion au curseur ───────────────────────────────────────────
function inserer(texte) {
  const el = props.targetEl
  const courant = props.modelValue || ''
  let debut = courant.length
  let fin = courant.length
  if (el && typeof el.selectionStart === 'number') {
    debut = el.selectionStart
    fin = el.selectionEnd
  }
  const avant = courant.slice(0, debut)
  const apres = courant.slice(fin)
  // Espaces de jonction : on dicte un complément au milieu d'une phrase déjà
  // écrite aussi souvent qu'en fin de champ.
  const sep1 = avant && !/\s$/.test(avant) ? ' ' : ''
  const sep2 = apres && !/^\s/.test(apres) ? ' ' : ''
  const morceau = sep1 + texte + sep2

  undoState.value = { texte: courant, caret: debut }
  emit('update:modelValue', avant + morceau + apres)
  message.value = ''

  nextTick(() => {
    if (!el?.setSelectionRange) return
    el.focus()
    const pos = debut + morceau.length
    el.setSelectionRange(pos, pos)
  })
}

// Une transcription ratée ne doit pas se rattraper à la main : on garde l'état
// d'avant insertion, un clic le restitue.
function annuler() {
  if (!undoState.value) return
  const { texte, caret } = undoState.value
  emit('update:modelValue', texte)
  undoState.value = null
  message.value = ''
  nextTick(() => {
    const el = props.targetEl
    if (el?.setSelectionRange) { el.focus(); el.setSelectionRange(caret, caret) }
  })
}
</script>
