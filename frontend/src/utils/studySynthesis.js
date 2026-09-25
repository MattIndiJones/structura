export function acceptStudySynthesis(data, studyHash, existingText = '') {
  if (!studyHash || data.study_hash !== studyHash) {
    throw new Error('La réponse IA ne correspond pas à cette version de l’étude. Relancez la génération après avoir recalculé l’étude.')
  }
  const generated = (data.synthesis || data.text || '').trim()
  if (!generated) throw new Error('Le modèle a renvoyé une synthèse vide. Vérifiez le modèle sélectionné puis réessayez.')
  if (['length', 'max_tokens'].includes(data.finish_reason) || /^[{\[]|^```/.test(generated)
      || /"(?:sha256|n_obs|bundle:|execution:)/.test(generated)) {
    throw new Error('Synthèse inexploitable ou tronquée : aucun texte intégré. Vérifiez le modèle et le prompt.')
  }
  const inserted = false
  return { generated, synthesis: inserted ? generated : existingText, inserted }
}
