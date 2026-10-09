<script setup>
import HelpTip from './HelpTip.vue'
import { workshopHelp } from '../utils/workshopHelp'
defineProps({topic:{type:String,required:true}})
</script>
<template><span class="workshop-help" :data-help="topic"><HelpTip :text="workshopHelp[topic] || 'Consultez les preuves de la campagne pour comprendre ce résultat.'"/></span></template>
<style scoped>.workshop-help{display:inline-flex;vertical-align:middle;margin-left:5px;flex-shrink:0}</style>
