# Valo Explain — 17 septembre 2026

Module Life Cycle accessible à `#/valo-explain`, depuis « Note de valo » dans
Booking, ou depuis deux calculs sélectionnés dans l'historique des MtM.

## Parcours

Le choix des calculs se fait dans un tableau de MtM enregistrés, du calcul le plus
récent au plus ancien, filtrable par base et date de valorisation. Une case cochée
propose la note ; deux cases proposent l'explication. Le sens initial suit les
dates de valorisation (heure de calcul puis identifiant en cas d'égalité), avec
une commande pour inverser le départ et l'arrivée. Les différences de modèles,
de bases et de paramètres enregistrés sont signalées avant génération.
« Calculer un MtM du jour » ajoute le résultat au tableau et le sélectionne ;
la génération du document reste une action distincte.

- Note simple : reprendre un calcul enregistré, ou calculer à la date du jour
  avec les paramètres du marché actuel. Les étapes de préparation sont diffusées
  au navigateur ; le compteur est un temps écoulé, pas un pourcentage estimé.
- Comparaison : choisir deux calculs du même deal et leur ordre. Le module
  conserve les deux prix et les entrées archivées. Il ne recharge pas le marché.
- Édition : titre, synthèse, analyse, contexte et conclusion. Les figures,
  calculs, dates, références et avertissements factuels ne sont pas éditables.
- Enregistrement automatique du brouillon, contrôle de révision pour éviter
  l'écrasement entre fenêtres, sauvegarde avant aperçu ou action IA.
- Aperçu PDF à actualiser après édition. Une version figée conserve le fichier
  PDF lui-même ; le téléchargement utilise exactement le document affiché.
- IA facultative : Ollama, Claude ou OpenAI via les clients existants. Envoi
  explicite du passage et des chiffres utiles. Proposition à accepter ou écarter.
  Aucun changement du prix et aucune transmission automatique. Le contexte
  automatique exclut identité du client, contrepartie, référence et nominal ;
  le texte rédigé par l'utilisateur peut en contenir, ce que l'interface indique.
  Les clés restent transitoires ; elles ne sont pas enregistrées dans les notes.

Les notes archivées ont une durée de vie distincte du cache quotidien des MtM
de Booking. Leur date de valorisation et l'heure du calcul sont toujours visibles.

## Méthode de comparaison

L'écart observé est `100 × (MtM arrivée − MtM départ)`, en points du nominal.
Il exclut les flux déjà payés et ne constitue pas un P&L total.

L'attribution exige des versions contractuelles, termes, modèle et réglages
numériques compatibles, ainsi que le même moteur que celui des calculs archivés.
Les deux prix sont d'abord reproduits avec une tolérance absolue de `1e-10`.
À défaut, seuls l'écart observé et la raison de la non-comparabilité sont présentés.

Les réévaluations successives utilisent le pricer résiduel existant, avec les mêmes
trajectoires et la même graine. Ordre déclaré :

1. Temps et état réalisé, déplacés ensemble pour conserver un état cohérent
   lors du franchissement d'une observation ou d'une fenêtre de fixing.
2. Spots normalisés.
3. Dividendes : rendement, courbe et décroissance.
4. Paramètres de diffusion et de change restants, adaptés au modèle utilisé.
5. Corrélations.
6. Taux et courbe sans risque, avec les paramètres de taux stochastiques.
7. Courbe et spread de financement, distincts du drift.
8. Valeur actuelle des flux constatés restant à recevoir.

La somme des contributions et du résidu reproduit l'écart observé. L'ordre affecte
l'attribution des interactions ; un résidu n'est jamais renommé en facteur causal.
Les sensibilités de la note utilisent `compute_greeks` par l'adaptateur existant,
avec le contexte résiduel archivé. Aucun nouveau modèle de prix n'est introduit.

## Persistance et compatibilité

- `valuation_notes` : preuve figée copiée des calculs, texte courant, auteur,
  révision et clé d'idempotence.
- `valuation_note_versions` : titre, texte, auteur, révision et PDF figés.
- Accès aux brouillons réservé à leur auteur, avec contrôle d'accès au deal
  revérifié pour chaque opération.
- Les nouveaux MtM/REPORT archivent aussi l'identité, le calendrier, les
  barrières et le graphique nécessaires à la note. L'historique de cours n'est
  pas renvoyé dans la liste compacte utilisée par le sélecteur du module.
- Les anciens calculs restent utilisables : tout élément non archivé est omis
  et signalé. Aucun historique actuel n'est présenté comme une preuve ancienne.
- Les notes empêchent une suppression administrative ordinaire du deal.
  La purge explicite d'un lot UAT enlève ses versions et notes avant ses deals.
- Tables créées par `init_db()` au prochain démarrage normal. Aucune modification
  de la base réelle n'est effectuée par les tests ou par un script de migration
  lancé pendant cette intervention.

## Vérification

Tests isolés : prix figé, historique, Greeks, progression, idempotence, droits,
rejet de modification des preuves, conflit de révision, PDF de version identique,
attribution nulle, spot/funding séparés, somme des effets, sens inverse, roll du
calendrier, refus des comparaisons incompatibles, échec de reproduction, IA simulée,
compatibilité des anciens calculs et nettoyage du lot UAT.

Frontend : test de sauvegarde pendant une requête en cours, conservation du texte
après conflit, sauvegarde automatique ; compilation de production obligatoire.
PDF : rendu visuel de notes simples et comparatives sur données synthétiques.
Le test d'un fournisseur IA réel nécessite sa configuration et un appel explicite.

L'activation et la recette dans l'instance locale nécessitent le démarrage du
backend par Philippe, conformément à `CLAUDE.md` ; l'agent ne lance pas le serveur.
