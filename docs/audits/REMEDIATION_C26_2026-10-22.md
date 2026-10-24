# C26 — Surveillance lifecycle et comptes rendus

Date : 22 octobre 2026. Livraison locale sans commit ni push.

Les deux constats **M12-03** et **M12-04** sont corrigés et validés localement.
Les prérequis sont C01, C11 et C13 ; les transitions, références Product et
archives apportées par les correctifs précédents sont conservées.

## Observables et barrières — M12-03

Chaque sous-jacent garde sa position dans le contrat, y compris lorsque son
ticker, son niveau initial ou son cours est absent. `S[1]` ne reçoit plus la
performance de `S[2]`. WOF, BOF et BASKET ne sont disponibles que pour le panier
complet ; une mesure individuelle reste utilisable si son propre titre est couvert.

`S_MIN[i]` et `S_MAX[i]` lisent des séries distinctes du cours courant. La fenêtre
est explicitement bornée par le strike et la date du bilan ; le niveau initial
est inclus. Aucun cours antérieur au strike ou postérieur au bilan ne fabrique
un extremum. Une fenêtre vide, trop tardive, trouée ou contenant des prix invalides
reste indisponible. La politique C11 de trois jours calendaires reste applicable
aux cours et à la couverture des clôtures ; aucune tolérance supplémentaire
n'est introduite pour les longs jours fériés ou interruptions de cotation.

Exemple reproduit : **100 → 50 → 100**, barrière KI à **60 %**. Le minimum vaut
**50 %**, soit **−10 points**, et le cours courant vaut **100 %**. L'ancienne
distance de +40 points n'est plus affichée pour ce minimum.

La source reste le service de marché existant, qui privilégie ses copies locales
et ses caches C12 : clôtures **non ajustées**, couverture partielle explicite,
dates sources et âge conservés. Les valeurs indisponibles restent `null`, jamais zéro.

Le registre officiel C13 est contrôlé et superposé aux dates contractuelles :
une correction change le nouveau bilan sans modifier l'ancien résultat ni les
anciennes versions. Une version en attente ne devient pas un cours fournisseur.
Un fixing officiel récent reste utilisable pendant une panne fournisseur ; une
ligne reportée plus ancienne ne prend pas sa place au motif que sa date alignée
serait plus récente.

Les minima/maxima sont qualifiés comme **clôtures indicatives depuis le strike**
dans les badges et les alertes. Ils ne certifient pas un monitoring continu et
ne modifient pas les qualifications quantitatives C16 ni le rejeu officiel.

## Traitement quotidien et reprise — M12-04

Le bilan manuel et le journal du scheduler utilisent la même classification :

| État | Condition |
|---|---|
| SUCCESS | Tous les dossiers sélectionnés sont traités sans erreur, y compris un book vide |
| PARTIAL | Au moins un dossier traité sans erreur et au moins un dossier en erreur |
| FAILED | Tous les dossiers sélectionnés sont en erreur, ou panne globale |
| SKIPPED | Créneau déjà réussi sans erreur, ou détenu par un worker encore actif |
| SUPERSEDED | Un ancien worker termine après la reprise de son créneau ; son bilan n'écrase pas le nouveau propriétaire |

La couverture donne le total, les succès complets et les échecs. Le détail par
deal conserve identité, étape, résultat, erreurs et compteurs. Un refresh réussi
suivi d'une surveillance en erreur conserve son compteur de refresh mais n'est
pas compté comme dossier intégralement réussi. Les observables requis indisponibles
sont signalés ; un strike futur demeure une attente normale.

Chaque échec annule les écritures non validées de sa session avant de poursuivre
sur le dossier suivant, y compris après un échec SQL ou un échec de règlement.
Les faits officiels déjà validés par le service C13 restent acquis. Les alertes
ne sont comptées qu'après validation de leur transaction.

FAILED et PARTIAL sont rejouables sur le même créneau. Un ancien SUCCESS dont le
résumé contient des erreurs est également reprenable. Les alertes conservent leurs
clés de déduplication ; le rejeu ne les duplique pas. La finalisation du journal
vérifie toujours l'identité et l'heure de prise du créneau, afin qu'un worker
retardataire ne puisse pas écraser une reprise.

L'interface restitue succès, partiel ou échec avec couverture, propositions,
résolutions et détail consultable des erreurs. Elle ne déduit plus le succès du
seul HTTP 200. Un double lancement dans la même vue est bloqué.

**D07 reste ouvert.** La transition existante à la date contractuelle est conservée.
Le bilan parle d'« échéances atteintes » ; ce compteur n'est pas une preuve de
paiement bancaire confirmé. Aucune nouvelle convention de règlement n'est décidée.

## Validation et preuves

- Avant correction : quatre échecs de reproduction sur cinq cas, portant sur
  l'index déplacé, le minimum faux, le faux succès total et le faux succès partiel.
- **101 tests backend distincts réussis**, dont **44 nouveaux cas C26**, sur huit
  fichiers ciblés. Les nouveaux scénarios de book utilisent une SQLite en mémoire
  avec clés étrangères actives ; les scénarios officiels réemploient aussi les
  fixtures C13 existantes. Aucun test n'utilise la base réelle.
- Un échec préexistant est conservé et reproduit avant/après :
  `test_fixings_releves.py::test_la_fenetre_de_depart_a_ses_releves_bookes_sous_le_strike`,
  dont le faux utilisateur `SimpleNamespace` ne porte pas le rôle requis par C01.
  Aucun contrôle d'autorisation n'est assoupli pour faire passer cette fixture.
- **720 tests frontend réussis**, dont huit nouveaux, et `npm run build` réussi
  avec sortie temporaire ; les fichiers `frontend/dist` existants sont préservés.
- Les requêtes HTTP externes requests/curl sont bloquées durant les tests backend ;
  aucune tentative n'est constatée. Aucun serveur ni service n'a été démarré.

T08 est complété localement pour le consommateur surveillance : correction
officielle, panne fournisseur, donnée reportée et conservation du résultat précédent.
Les régressions C13 vérifient aussi les archives de valorisation. Ce n'est pas une
nouvelle recette complète de la chaîne MtM/P&L/CCR en environnement déployé.

Les tests frontend vérifient le rendu des états et messages ; la recette graphique
interactive et la qualification déployée restent à réaliser. La suite backend
complète n'a pas été lancée. **Le solde de C27 reste ouvert.**

Preuves structurées : [C26_VALIDATION.json](remediation-lot-0-2026-10-20/C26_VALIDATION.json).
Les sorties brutes et la comparaison de préservation sont conservées dans
`.runtime/diagnostic-acceptance/c26-2026-10-22/`.
