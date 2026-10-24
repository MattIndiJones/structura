# Campagne complète RFQ native — lancement du 13/10/2026

Autorisation de Philippe : actualiser les consignes, raccorder la simulation au
parcours RFQ actuel, réutiliser les contreparties puis lancer une campagne complète.
Kepler est demandeur ; BNP, SG, Citi, UBS et Leonteq sont répondants.
Aucun commit ou push. Les essais manuels et leurs six bases ne sont pas utilisés.

## Qualification préalable

La [note de raccordement](../projects/platform/AGENT_WORKSHOP_NATIVE_RFQ_2026-10-13.md)
consigne le contrôle dirigé `2804592ee1bd44a9b12a7ed714bf97a9` : cinq cotations
publiées et validées par des Contrôleurs distincts, confirmation avant booking,
quatre jambes rapprochées et retries sans doublon. Les sept services privés de
ce contrôle ont été arrêtés. L'écart de contrat historique de CASE-001 est conservé ;
CASE-002 reprend les termes Product canoniques et passe le rapprochement.
Le build frontend et l'analyse syntaxique Python réussissent ; aucune suite de
tests backend/frontend n'a été lancée.

## Lancement effectif

Campagne `37a56209c1604d3c84541d260870a80e`, démarrée le 13/10/2026 à
18:23:50 UTC par l'API de Structura Admin. Statut initial RUNNING, contrôleur actif.
Adresse : `http://127.0.0.1:8000/#/agent-workshop`.

Observation à 18:26:54 UTC : sept installations privées répondent avec leur
identité attendue ; quatre premières actions autonomes `register` réussies
(Kepler, BNP, Citi, SG), quatre tours, aucun incident. Statut RUNNING, agent client
en réflexion. Aucun besoin, prix ou booking annuel à cette observation initiale.

Paramètres : douze mois commerciaux à partir du 13/10/2025, objectif indicatif
100 000 000 EUR, tickets 10 000 000 EUR, scénario `all_complete`, graine 42,
Qwen2.5-Coder 7B, 1 200 tours maximum et six heures réelles maximum. Le suivi
contractuel continue après l'horizon commercial si des produits restent actifs.
Les décisions commerciales ne sont pas forcées pour atteindre le volume cible.

Preuves locales :
`.runtime/hybrid-saas/admin-workbench/campaigns/37a56209c1604d3c84541d260870a80e/`.
`full-launch-manifest.json` conserve le choix des rôles, le hash des consignes et
les identités des services ; `full-progress.json` est mis à jour par le superviseur.
`campaign.json`, journaux IA, appels HTTP et captures restent dans ce dossier privé.
Un export et `full-result.json` seront écrits à l'arrêt effectif.

Le superviseur `scripts/run_workshop_campaign.py`, PID 6556 au lancement, possède
uniquement les services qu'il vient de démarrer : Admin PID 26292 (processus lanceur
13932) et portail PID 30216 (processus lanceur 22768). Les autres services et Ollama
préexistants ne sont pas arrêtés. Les acteurs sont suivis séparément par leur campagne.
Pour arrêter : Structura Admin → Simulation → sélectionner la campagne → Arrêter.
Le superviseur demande un arrêt propre et nettoie ses services à la fin ; une pause
de sécurité ou le plafond horaire conserve les preuves et déclenche cet arrêt.

## Résultats restant à relever

La campagne annuelle est lancée, sans résultat final à ce stade. Relever séparément
les décisions autonomes, refus, erreurs, volume exécuté, fixings, paiements et statut
final. Le succès du contrôle dirigé ne constitue pas une année complète réussie.
Les confirmations sont déclarées avec preuves fictives explicites ; aucun nouveau
protocole de confirmation bancaire signé n'est prétendu livré. Révisions/retraits,
pannes réseau/reprise, défaut, réinvestissement, appels de marge et précision quant
ne sont pas qualifiés par ce seul contrôle. Registre RFQ central, conservation de
production et facturation restent ouverts ; aucune facturation réelle n'est activée.
