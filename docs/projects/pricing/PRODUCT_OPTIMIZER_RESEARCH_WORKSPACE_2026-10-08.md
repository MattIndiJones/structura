# Optimizer — dossiers de recherche et page de résultats

État du **08/10/2026** : implémenté localement à la demande de Philippe, après validation du parcours séparant demande, résultats et bibliothèque. Aucun commit ni déploiement. Les décisions antérieures reportant la conservation des recherches sont remplacées, pour ce lot, par cette demande explicite.

## Parcours et affichage

- `/structuring/optimizer` : formulaire dédié, nom facultatif et intention métier en texte libre. Le lancement sauvegarde la demande avant de démarrer le calcul, puis ouvre sa page de résultats.
- `/structuring/researches/:researchId` : résultats sauvegardés. Compteurs, résumé repliable de la demande, puis trois vues : **Structures**, **Comparaison & graphiques**, **Marché & calcul**.
- `/structuring/researches` : bibliothèque **Recherches & pricings**, accessible depuis Structuring Intelligence et l’Optimizer. Recherche sur nom/résumé/intention, filtres famille/état/archive, pagination, ouvrir, reprendre, archiver/restaurer.

Les écrans utilisent le viewport fixe déjà employé dans l’application. Après le retour de Philippe sur les barres imbriquées, la page de résultats garde **un seul défilement vertical**, au niveau de son espace de travail. Ses panneaux et diagnostics n’ajoutent plus de défilement vertical interne. Le tableau de prix est paginé par 10 ou 25 structures ; le tri et la taille de page ramènent à la première page, tandis que les sélections de comparaison sont conservées entre pages. Un défilement horizontal reste disponible pour les tableaux larges. Le formulaire conserve ses panneaux bornés.

Les prix calculés sont présentés avant les détails techniques. Le résumé, les diagnostics, les structures sans prix, les comparaisons détaillées et le script sauvegardé sont ouvrables et refermables au clavier avec des éléments `details` natifs.

Les meilleures structures selon l’objectif restent visibles même si elles sont hors conditions. Vert : contraintes satisfaites **et** validation indépendante réussie ; rouge : hors conditions, contrôle non concluant ou erreur ; ambre : validation manquante. Les erreurs sans prix complet restent distinctes des structures effectivement pricées. Les couleurs sont accompagnées d’un statut et de motifs lisibles ; elles ne remplacent pas les contrôles quantitatifs.

Les aides `HelpTip` existantes expliquent paramètres, conventions, unités, budget, sources et métriques Q. Elles restent accessibles au clavier et sortent des conteneurs scrollables grâce à leur placement partagé dans le `body`. Les hypothèses affichées continuent à être arrondies à deux décimales ; les références sources conservent leur précision.

## Interprétation du résultat et reprise de précision

Pendant l’exploration, le résumé affiche les structures admissibles **provisoirement** et annonce la validation indépendante à venir. Pendant cette validation, il indique son avancement. Le nombre de structures confirmées reste distinct du nombre de solutions trouvées en exploration ; une validation manquante n’est pas présentée comme une impossibilité économique.

Le retour utilisateur du 08/10 a été vérifié en lecture seule dans un dossier sauvegardé : 75 candidats évalués, 60 prix complets, 35 structures admissibles en exploration, cinq sélectionnées pour validation et aucune confirmée. Les cinq rejets de validation concernaient uniquement l’incertitude Monte-Carlo, sans échec technique ; les 30 autres structures admissibles n’avaient pas été validées indépendamment. Exemple : prix central **96,66 %**, intervalle de contrôle **96,13–97,20 %**, plage admise **96,00–97,00 %** autour de la cible nette de **96,50 %**. L’absence de confirmation ne démontre donc pas l’absence de solution économique.

Lorsque tous les contrôles terminés ont échoué uniquement pour `MC_UNCERTAINTY`, le résumé explique ce motif, reprend un exemple chiffré et propose de **préparer un nouveau calcul** à quatre fois N, plafonné à 20 000 paires. Pour N = 4 000, le brouillon propose 16 000 paires. La demande d’origine, son marché daté et ses contraintes sont repris ; seul N est modifié. Le formulaire reste à vérifier puis à lancer par l’utilisateur. Aucun calcul n’est déclenché par ce bouton, aucune contrainte n’est assouplie et une confirmation n’est pas garantie. La sélection indépendante figée et les critères numériques restent identiques.

Les diagnostics nomment explicitement l’intervalle de contrôle simultané pour les prix issus d’une validation indépendante, distinct de l’IC95 d’exploration. Pendant un calcul en cours, une structure sans validation invite à attendre la sélection et les contrôles plutôt qu’à lancer déjà un nouveau calcul.

## Comparaison par radar

Le tableau permet de sélectionner deux à cinq structures. Le radar représente les quatre premières au maximum, avec au moins trois métriques communes disponibles. Les axes suivent le payoff : coupon/participation/cap, perte Q, durée moyenne, et, si applicables, barrière de protection, rappel Q, perte en capital moyenne Q.

Les échelles sont explicitement affichées et communes à la demande : bornes du paramètre résolu, probabilités sur 0–100 %, durée sur 0–maturité contractuelle maximale, protection sur 0–100 %. La sélection d’autres candidats ne redéfinit pas les bornes. Une valeur hors échelle est limitée au bord du radar ; sa valeur réelle reste consultable au survol et dans le tableau.

Une barrière/perte/durée faible est représentée vers l’extérieur ; un coupon/participation/cap/rappel élevé l’est également. Le texte précise que durée courte et rappel fréquent ne constituent pas des préférences universelles. Aucune note globale ni classement selon la surface du radar n’est produit. La frontière concerne les candidats confirmés seulement.

## Dossier sauvegardé

La table `optimizer_researches` conserve, par utilisateur authentifié :

- identifiant, date de création/fin, état, archive, parent éventuel et clé de lancement ;
- nom, intention libre et résumé normalisé généré côté serveur ;
- demande effective complète : payoff, plages/fixes/fréquences, date, panier, courbes, funding, surcharges, coûts, contraintes et budget ;
- famille et script figés, empreinte du script, snapshot de marché avec données utilisées/références/provenance et empreinte ;
- avancement, candidats calculés, motifs de rejet, erreurs publiques, résultat final et validations indépendantes.

Le résumé reprend les axes, bornes de résolution, fréquence, paramètres fixes, limites de risque renseignées, prix cible/budget net, tolérances, coûts et budget de calcul. Les valeurs détaillées restent disponibles dans la demande structurée et l’export JSON, qui comprend tout le dossier.

Les références de marché, les entrées et les résultats terminaux sont immuables. Un trigger SQLite protège également ces données contre une réécriture directe ; l’archive reste modifiable. **Reprendre** ouvre les hypothèses effectives et leurs références datées ; le lancement crée un nouvel identifiant relié à l’origine, sans altérer les anciens prix. L’actualisation des références est explicite dans ce parcours. Une modification de date/panier reprend le chargement automatique en conservant les surcharges. Un changement de script est signalé avant le nouveau calcul.

Un dossier est une trace d’exploration, distincte d’un Product canonique, d’une déclinaison et d’un Deal. Il ne crée aucun booking. Les données structurées fourniront un contexte daté au futur Copilot ; aucune intégration LLM ni réutilisation des anciens prix comme prix actuels n’est ajoutée dans ce lot. Un nouveau marché exige un nouveau calcul. Les intentions sauvegardées restent des données utilisateur, pas des instructions système pour une future AI.

## Calcul en arrière-plan et API

Le job est détaché de la connexion HTTP et de la page Vue. Les candidats sont sauvegardés progressivement, y compris les contrôles de validation ; une erreur conserve les prix déjà reçus. Navigation ou fermeture de l’onglet ne demande aucune annulation. L’arrêt explicite utilise une route propriétaire et conserve un résultat partiel.

États : `RUNNING`, `COMPLETED`, `PARTIAL`, `FAILED`, `INTERRUPTED`. `COMPLETED` signifie calcul terminé, indépendamment du nombre de structures confirmées. Au redémarrage du serveur, les jobs inachevés sont marqués interrompus avec leurs résultats reçus ; ils ne sont pas relancés automatiquement. Un arrêt normal du serveur demande l’annulation et attend le nettoyage des processus.

Routes authentifiées : création/liste `/api/product-optimizer/researches`, lecture/archive `/{id}`, arrêt `/{id}/cancel`. Chaque accès vérifie le propriétaire, y compris le parent d’une reprise. La clé de lancement est unique par utilisateur : un retry identique restitue le même dossier ; une autre demande sous cette clé est refusée.

L’admission globale reste commune avec l’ancienne API streaming : un calcul Optimizer à la fois par processus serveur, avec un à quatre processus de pricing bornés comme avant. L’ancien streaming reste compatible ; l’inclusion de chaque candidat dans ses événements est activée seulement pour la sauvegarde. Aucune modification de payoff, de simulateur, de solveur, de sélection holdout ou de seuil de validation.

**Activation locale :** redémarrer le backend pour charger les nouvelles routes et créer la nouvelle table via `init_db`. Le backend déjà présent sur le port 8000 n’a pas été arrêté ni remplacé par cette tâche.

## Vérifications

- **346 tests frontend réussis et build de production réussi**. Tests Vue/utilitaires : contrôle du lancement sauvegardé, retry, reprise fidèle avec courbes/surcharges, marché non remplacé silencieusement, tri des prix rejetés, panneaux, comparaison progressive, échelles du radar, polling, arrêt explicite, navigation et mode Démo.
- **59 tests backend ciblés distincts** : contrats/moteur/validation existants et sept tests des dossiers. Deux exécutions : 58 tests avant l’ajout de la recette réelle parallèle, puis les sept tests de dossiers, dont six déjà exécutés.
- Recette réelle : deux Athena, 1 000 paires, deux processus demandés et utilisés, calcul détaché via API, résultats/inputs/scripts/market hash sauvegardés, aucun échec.
- Bases SQLite temporaires isolées uniquement. La base réelle n’a pas été utilisée par les tests ; aucun dossier de recette n’y a été inséré.
- Recette visuelle non refaite : l’accès navigateur à localhost avait été bloqué sur cette session. Les tests de rendu et de lifecycle ne constituent pas une inspection visuelle desktop/mobile.

Correctif du retour utilisateur sur le défilement et l’absence de confirmation : **355 tests frontend réussis et build de production réussi**. Neuf tests supplémentaires couvrent les états provisoires/définitifs, les rejets uniquement statistiques, les erreurs et rejets métier distincts, la couverture partielle, la pagination avec sélection conservée, l’absence de hauteurs scrollables imbriquées et la préparation fidèle du brouillon à 16 000 paires sans lancement automatique. Aucun changement backend et aucun test backend supplémentaire pour ce correctif ; le dossier réel a seulement été lu pour le diagnostic. L’inspection visuelle navigateur reste à réaliser.

Limites conservées : GBM, hypothèses historiques non implicites de booking, convergence temporelle à qualifier, smile actions urgent et différé. La persistance locale n’est pas un gestionnaire distribué de jobs : pas de reprise automatique d’un processus tué ni d’ordonnanceur multi-instance.
