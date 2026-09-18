# Socle IA commun — 17 septembre 2026

## Périmètre livré

Les cinq usages de génération de texte utilisent `AiWorkbench.vue` et
`useAiWorkbench.js` : création/affinage PayScript, second avis produit, synthèse
AMC, description EMT et rédaction Valo Explain. La dictée locale conserve son
moteur distinct.

Le panneau commun porte le fournisseur, le modèle, l'actualisation du catalogue,
la connexion, l'aperçu éditable des deux messages, la copie, le retour au défaut,
les états de préparation/génération avec durée, les erreurs et le dernier appel.
Ce dernier inclut le prompt exact, la version et le modèle résolu communiqué par
le fournisseur. Les tentatives de réparation PayScript sont consultables séparément.

Les choix fournisseur/modèle/adresse sont partagés réactivement et mémorisés sous
`ai_settings_v1`. Les anciennes préférences AMC/EMT servent à initialiser ces choix.
Les clés sont chargées côté serveur selon le mécanisme existant, ou saisies en
mémoire pour la session ; aucune nouvelle clé n'est enregistrée dans le navigateur.
Les anciennes clés stockées par AMC/EMT ne sont ni relues ni supprimées par cette
migration. Si elles étaient la seule configuration disponible, il faut les
ressaisir dans le panneau commun ou les configurer côté serveur.

## Contrat technique

- Catalogue unique : `services/llm/providers.py`, exposé par `/api/ai/providers`.
  `/api/script/providers` reste un alias compatible. Les identifiants cloud sont
  ceux du catalogue existant, sans vérification de disponibilité en ligne lors
  de cette livraison. Le champ modèle personnalisé permet un identifiant hors liste.
- Ollama : découverte à l'adresse configurée. Un modèle choisi explicitement
  et absent de la liste n'est jamais remplacé silencieusement.
- Transport HTTP unique pour les trois fournisseurs. `claude` reste un alias
  d'entrée de `anthropic`. Les anciens helpers AMC délèguent au service commun.
- Contrat `core/ai_contract.py` : options de connexion et `prompt_override`.
- `services/llm/workbench.py` : aperçu, empreinte du contexte, validation de
  la personnalisation et métadonnées de génération. Aucun secret de connexion
  n'est inclus dans la réponse ou le message d'erreur du fournisseur.
- Aperçus sans appel au modèle : `/api/script/prompt`,
  `/api/product/analyse/prompt`, `/api/amc/synthesize/prompt`,
  `/api/emt/synthesize/prompt`, `/api/valuation-notes/{id}/assist/prompt`.

Chaque module garde son constructeur de prompt et son contexte métier. Le hash
du prompt par défaut lie une personnalisation à son contexte et à sa version.
Après changement de contexte, les modifications restent visibles mais un envoi
nécessite de reconstruire le prompt. Un résultat reçu après changement des inputs
ou fermeture de l'écran n'est pas inséré. Les double-clics ne doublent pas l'appel.
Les modifications de prompt sont propres à la demande, sans bibliothèque de
templates personnalisés persistants.

## Contrôles métier conservés

PayScript conserve parsing, contrôles métier, pricing de contrôle, reprise unique,
acknowledgement des avertissements et adoption explicite. L'aperçu d'affinage
inclut désormais le script proposé et la demande d'affinage.

Valo Explain sauvegarde le brouillon avant de préparer le prompt, vérifie les
droits et la révision côté serveur, utilise les calculs figés et garde l'acceptation
explicite du passage. Aucun prix ni document figé n'est modifié par l'appel IA.
AMC et EMT gardent l'insertion explicite du texte proposé.

Le dernier appel est consultable pendant la présence du panneau à l'écran.
Il ne s'agit pas d'un nouveau journal durable de tous les appels IA. La provenance
du script adopté reste conservée par le circuit existant, enrichie du statut de
personnalisation et de l'empreinte du prompt.

## Vérification et activation

Tests offline : transport commun, modèle effectivement retourné, prompts édités
transmis, refus des contextes périmés, aperçu sans génération, contrôles PayScript,
absence de mutation du brouillon, erreurs sans secrets, changement de compte,
partage des réglages, requêtes concurrentes et résultats tardifs.

Résultats : 101 tests backend ciblés validés (dont 45 rejoués après l'ajustement
final des contrats), 188 tests frontend validés et build Vite réussi.

Commandes : `npm run build` dans `frontend`, et depuis la racine
`.venv/Scripts/python.exe -m pytest backend/tests/test_ai_workbench.py backend/tests/test_product_analysis.py backend/tests/test_emt.py backend/tests/test_valuation_notes.py backend/tests/test_llm_scripting.py -q`.

Activation : démarrer ou redémarrer le backend puis recharger l'application.
L'instance `127.0.0.1:8000` refusait la connexion lors de la tentative de recette
visuelle ; elle n'a pas été démarrée par cette intervention. Aucun appel réel à
un fournisseur IA n'a été effectué.
