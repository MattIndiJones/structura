# Reprise de la campagne historique multi-produits — 15 octobre 2026

Campagne `b567dd8d1ad84d9fa74823796ca23858`, fenêtre contractuelle du 14/10/2021 au 14/10/2026, 12 mois commerciaux actifs et 36 RFQ prévues. Ce document est un **point d'étape**, pas un bilan final.

## Reprise contrôlée

- Les trois premiers dossiers avaient quatre jambes cohérentes chacun. Le dossier `CASE-0006` attendait la cotation SG, sans appel HTTP métier pendant l'échec OpenAI. Les processus privés étaient fermés et le verrou de campagne libre.
- Une copie du JSON de campagne, des revues d'incidents, du marché historique et des sept bases privées a été conservée dans `.runtime/diagnostic-acceptance/resume-20261015/b567dd8d1ad84d9fa74823796ca23858/` avant modification de l'état. Les 24 décisions déjà appliquées, les écritures et le coût IA ont été préservés. Une seule décision `CALLING`, celle de SG sur `CASE-0006`, a été libérée avec un événement d'opérateur tracé.
- Le premier nouvel appel OpenAI a encore renvoyé une sortie non décodable (`Extra data`), sans appel HTTP métier. La campagne s'est arrêtée proprement. Son état après cet arrêt est conservé dans `second-provider-stop.json`. Il ne faut pas multiplier les retries identiques.
- Le parseur accepte désormais une réponse constituée de deux objets JSON **strictement identiques** ; il refuse deux décisions différentes ou du texte supplémentaire. Comme les deux sorties précédentes n'avaient pas été enregistrées, leur duplication exacte demeure une hypothèse, non une preuve. Une future sortie invalide est sauvegardée dans le dossier privé `provider-responses/`, avec son empreinte dans l'action échouée.
- Après deux tests ciblés réussis, les deux services de contrôle lancés pour la reprise ont été redémarrés sur le nouveau code. Une seule nouvelle sollicitation SG a été autorisée. Elle a franchi la cotation et la campagne a poursuivi les dossiers du deuxième mois.

## État observé pendant la reprise

À la dernière lecture du 15/10, la campagne était `RUNNING` au 14/01/2022 (mois 3). Six dossiers sur six étaient complets, sans écart de rapprochement ni jambe dupliquée ; 27 cotations avaient été publiées. Le compteur cumulé indiquait 41 appels IA et 0,0154107 $ estimés, 45 pricings, 14 MtM et 15 rapports de risque. Les deux incidents fournisseur restent dans l'historique. Aucun nouveau RFQ n'est prévu avant le mois 12 ; les mois intermédiaires servent au suivi contractuel.

La fin des cinq ans, les dix autres mois commerciaux actifs, les flux contractuels ultérieurs et les contrôles visuels ne sont **pas encore validés** à ce point d'étape. Le contrôleur doit s'arrêter au prochain blocage et conserver les preuves ; aucune correction de code pendant son exécution. Aucun commit ni push.
