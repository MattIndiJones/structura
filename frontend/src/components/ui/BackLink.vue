<!--
  Le bouton « ← Retour », avec une seule sémantique pour toute l'application.

  Il en existait deux, sous la même flèche : le retour du navigateur ramenait à
  la page précédente, et ce bouton-ci ramenait toujours à l'ACCUEIL. Selon
  qu'on cliquait l'un ou l'autre on atterrissait ailleurs, ce qui donnait
  l'impression d'un comportement aléatoire.

  La flèche dit « en arrière » : elle revient donc en arrière. La destination
  passée en `fallback` ne sert que lorsqu'il n'y a nulle part où reculer — page
  ouverte par un lien direct, un signet, ou une redirection. Elle reste utile :
  c'est ce qui ramène à la bonne rubrique de l'accueil plutôt qu'à sa racine.
-->
<template>
  <button class="btn-secondary text-xs px-3 py-1.5 shrink-0" @click="revenir">
    <slot>← Retour</slot>
  </button>
</template>

<script setup>
import { useRouter } from 'vue-router'

const props = defineProps({
  // Où aller quand il n'y a pas d'historique interne. Même forme qu'un `to`
  // de RouterLink : une chaîne ou un objet {path, query}.
  fallback: { type: [String, Object], required: true },
})

const router = useRouter()

function revenir() {
  // `history.state.back` est posé par Vue Router : il vaut null quand l'entrée
  // courante est la PREMIÈRE de la session. Sans ce test, `router.back()`
  // ferait sortir de l'application — vers le site précédent, ou nulle part.
  const precedente = window.history.state?.back
  if (precedente) router.back()
  else router.push(props.fallback)
}
</script>
