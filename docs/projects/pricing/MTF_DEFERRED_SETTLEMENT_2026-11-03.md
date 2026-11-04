# MTF : paiements différés, créances et deux populations

État local vérifié le 03/11/2026. Philippe a validé le principe d'une valeur
résiduelle excluant le cash déjà échu et a demandé le support des délais de
paiement quelconques dans l'éventail et le drill-down. Sans commit ni push.

## Convention financière

À chaque date, le mark additionne la valeur des flux encore conditionnels et
la valeur actualisée des montants constatés dont le paiement est futur.
`STOP` arrête les observations futures ; il ne supprime pas une créance.
Un flux sort de la valeur résiduelle à son règlement contractuel.

La convention est **après les observations et les paiements dus ce jour** : un
paiement à la date de marque est dans le cash échu et plus dans le mark.
Il s'agit de l'échéancier contractuel modélisé, pas d'une preuve de virement.
Les délais viennent des dates résolues/figées du contrat ; le moteur ne rajoute
pas arbitrairement trois jours calendaires. Le paiement final explicite reste
prioritaire selon la convention du pricer canonique.

Le cas de référence est un remboursement de 108 acquis à l'observation :
avant paiement, valeur `108 × exp(-r × temps restant)` en taux plat ; après
paiement, mark nul et 108 dans le cash. Pour un coupon sans rappel, seul le
coupon quitte le mark ; le reliquat continue d'être valorisé.

## Moteur et API

- Le rejeu extérieur, l'actualisation intérieure et le détail partagent
  `_mtf_payment_args`, `_mtf_replay` et `_mtf_claim_rows` dans `engine.py`.
- Le journal par scénario porte observation, paiement, montant et libellé.
  Les créances acquises sont ajoutées une seule fois, même après rappel ou
  maturité. Le cash échu est présenté séparément, sans capitalisation implicite.
- Les états `alive` (payoff actif), `pending_settlement` (payoff arrêté mais
  créance impayée), `outstanding` et règlement complet restent distincts.
  Des créances signées se compensant en valeur ne disparaissent pas du périmètre
  des engagements avant leurs paiements.
- `stats_all` représente tous les scénarios initiaux, avec les zéros après
  règlement complet. `stats_outstanding` représente les seuls engagements non
  réglés. Les masques, effectifs et seuils d'échantillon sont explicites.
  `stats`/`pvs_alive` restent des champs historiques de payoffs actifs ; le
  nouveau frontend sélectionne les champs explicites des deux nouvelles vues.
- Les contrats crédit/KID existants conservent leur tableau `realized_flows`,
  constitué de flux acquis datés au paiement ; l'interface utilise les nouvelles
  partitions `settled_flows` et `unsettled_flows` pour éviter toute ambiguïté.
- `mtm_dates` peut demander des dates exactes via l'API. La grille automatique
  conserve ses dates de base et ajoute maturité, milieu du délai final et dernier
  paiement quand celui-ci est différé. Le budget prend le nombre effectif de
  dates en compte. Le drill-down reprend la même grille et les mêmes tirages.
- En cours de vie, l'éventail et le détail reprennent le même état réalisé et
  les créances déjà constatées. Un contexte déjà rappelé/échu utilise un calcul
  analytique des créances, y compris quand la date initiale dépasse la maturité.
  Ce chemin est une option MTF : les autres analytiques gardent leurs refus
  antérieurs et les workflows de booking/fixings ne changent pas.
- Une empreinte du script, calendrier, marché, état réalisé, créances, grille et
  tirages est rendue avec l'éventail, puis renvoyée par le frontend au détail.
  Un contexte modifié entraîne un refus 409 demandant de relancer l'éventail.

## Interface

Un sélecteur distingue **Tous les scénarios initiaux** (défaut) et
**Engagements non encore réglés**. Graphique, statistiques, histogramme,
sélection des trajectoires et exports CSV utilisent tous le même masque.
Les valeurs résiduelles sous le pair ne sont pas appelées pertes de
l'investissement : les cash-flows antérieurs sont hors du mark.

Le graphique utilise un axe temporel numérique, pour respecter les intervalles
inégaux et ne pas étirer artificiellement trois jours de règlement. Les dates
calendaires sont affichées quand l'origine est disponible, notamment pour
distinguer les points proches de la dernière constatation et du paiement.
Un ancien résultat ne contenant pas les deux populations affiche un avertissement
et reste identifié comme une ancienne vue de payoffs actifs.

Le détail affiche séparément créances acquises impayées (probabilité 100 %),
flux encore conditionnels et cash contractuellement échu. Dates de constatation,
dates de paiement, montants, facteurs d'actualisation et contributions sont
visibles. Leur somme reconstitue le mark du scénario de l'éventail.

## Validation

207 cas backend distincts des dix fichiers ciblés sont passés :
`test_mtf_settlement`, `test_mtf_drilldown`, `test_mtf_fenetres`,
`test_mtf_audit_2026_08_03`, `test_review_fixes_2026_10_24`, `test_ccr`,
`test_analytics_calendrier`, `test_inlife_pricing`, `test_settlement_discounting`
et `test_valuation_context`. Pas de suite backend complète.

L'exécution groupée avait 203 succès et trois échecs : déclaration manquante
dans la nouvelle fixture de mémoire, empreinte d'un calendrier résiduel sans
objet `echeancier`, et ancien mock de backtest incompatible avec le début
automatique du chantier Yahoo précédent. Après correction, les cas concernés
ont été rejoués avec succès ; le cas supplémentaire d'origine après maturité
a également réussi. Les derniers 14 cas de règlement et l'identité analytique
ci-dessous sont passés après les ajustements de frontières calendaires.

Oracles : J+0/J+3/J+10 ouvrés EUR/TARGET, taux zéro/3 %, avant/à/après
constatation et paiement, coupon échu plus coupon impayé plus continuation,
paiement final explicite, créances signées, deux populations différentes,
mémoire héritée, contexte modifié refusé et valorisation initiale après maturité.
Les montants publiés sont rapprochés à leur précision d'arrondi.
Sur un payoff déterministe, `PV(mark futur) + PV(cash échu) = prix initial`.

`npm run build` a réussi avec **966 tests frontend**, dont sélection cohérente
des quantiles/histogrammes entre les deux vues, transmission de l'empreinte et
affichage des dates et créances après arrêt du payoff. `dist` est reconstruit.

La recette navigateur utilise les composants Vue réels avec des réponses
calculées par le moteur sur données synthétiques : 100 scénarios/100 chemins
intérieurs, avec 38 règlements complets après le premier rappel et 62 créances
terminales avant le paiement final, puis 100 règlements complets.
Contrôles desktop, sélection des deux populations, ouverture d'un quantile
impayé et largeur 390 px. Captures et réponses locales non versionnées dans
`.runtime/mtf-settlement-preview/` : `all-scenarios.jpg`, `outstanding.jpg`,
`drill-pending.jpg`, `drill-ledger.jpg`, `mobile.jpg`, `fan.json` et `detail-*.json`.

## Domaine et activation

Le traitement reste celui d'un MTF risque-neutre avec hypothèses gelées.
Les autres restrictions existantes (funding, courbes de taux, taux stochastiques,
LSV, monitoring continu, value date décalée/strike différé) restent refusées
explicitement selon les contrôles existants. Aucun défaut/retard de paiement
réel ni compte cash capitalisé n'a été ajouté.

### Corrections à la suite de l'audit quantitatif du 03/11

Philippe a autorisé le premier lot de corrections et le défaut des indicateurs
nuls à l'arrivée du résultat. Les corrections précédentes sur les créances et
les deux populations sont conservées.

- La maturité exacte est maintenant incluse dans l'axe extérieur du MTF et du
  drill-down, même si aucune marque demandée ne tombe ce jour. Le budget utilise
  le même axe ; les scénarios extérieurs fournis par un autre calcul doivent
  également contenir ce nœud. Cela empêche de perdre un bloc `AT MATURITY` et de
  laisser le payoff artificiellement actif après son règlement.
- Reproduction par l'API : coupon de 1 à t=1, remboursement de 100 à maturité
  t=1,105, paiement au 14/01/2028 depuis le strike du 03/11/2026, taux plat 3 %.
  Sur la grille [1,05 ; 1,15 ; 1,20], la créance à t=1,15 passait à zéro ; elle
  vaut désormais 99,860774 %, puis zéro après règlement. Le détail retrouve le
  même montant et le statut `PENDING_SETTLEMENT`.
- Le MTF et son détail sont désormais limités au modèle Constant/GBM : les
  scénarios extérieurs GBM ne permettaient pas de justifier les repricings
  intérieurs Heston, SABR ou Local Vol. Le refus s'applique aussi aux consommateurs
  utilisant cette même analyse, notamment les horizons intermédiaires KID.
  Les pricers initiaux conservent leurs modèles. L'interface indique le domaine
  et ne modifie jamais automatiquement le modèle sélectionné.
- Le MTF refuse un prix de référence périmé. Le résumé capture les paramètres
  de taux effectivement transmis : sigma_r et a_r nuls en mode déterministe,
  a_r nul en Brownien arithmétique. Les anciens snapshots sont interprétés selon
  leur sélecteur de taux. Les N observations antithétiques sont nommées N paires,
  soit 2N trajectoires simulées.
- L'affichage à zéro provenait de la sélection automatique de la dernière date,
  après paiement final, tandis qu'un remontage de l'onglet sélectionnait la
  première. Un nouvel éventail sélectionne maintenant sa première date éligible
  dans les deux cas. La date finale et ses zéros restent accessibles ; le passage
  entre populations conserve la date si elle est disponible, sinon revient à la
  première date éligible. Un libellé explique l'extinction après règlement complet.

Validation de ce lot : 98 cas backend distincts ciblant le MTF, le règlement et
les consommateurs CCR ; aucune suite backend complète. Les régressions ajoutées
reproduisent les défauts avant correction. Les tests incluent l'identité de valeur
totale sur payoff déterministe, le rapprochement éventail/détail, le refus des
modèles incohérents et le maintien des pricers initiaux Heston/SABR/Local Vol.
Le build frontend et ses 976 tests passent après modification.

La recette navigateur utilise le vrai composant et des réponses moteur synthétiques
dans `.runtime/mtf-fixes-preview/`. Dès réception, E(MTM)=99,49 % au premier horizon,
avec un graphique et un histogramme peuplés ; l'aller-retour Flux/MTF conserve le
même horizon et la même valeur. Le test unitaire couvre aussi la sélection de la
date finale à zéro et le recalcul sans remontage. Le serveur temporaire est arrêté
après recette, sans intervention sur les services métier.

Restent hors de ce premier lot : diffusion extérieure et états de volatilité
pour les autres modèles, diagnostic de martingale dans l'interface et intervalles
d'incertitude des quantiles. L'audit indépendant demeure dans
`.runtime/mtf-audit-2026-11-03/` ; les chiffres d'un ancien tirage ne constituent
pas une référence exacte à imposer aux nouveaux tirages.

Les services métier préexistants n'ont pas été arrêtés ni remplacés. Le serveur
frontend temporaire de recette est arrêté à l'issue des contrôles. Démarrer ou
relancer le workspace Admin avec le launcher, puis recharger le navigateur,
pour charger le nouveau backend et relancer un MTF.

### Sélection et comparaison des modèles dans le Pricer — 04/11

Le sélecteur MTF ouvre GBM, Heston QE, SABR et Local Vol. En mode simple,
il suit par défaut le modèle du Pricer. La comparaison A/B utilise deux
processus au maximum, un contexte contractuel et de marché commun, une grille
identique et des tirages reproductibles. Chaque modèle calcule son propre
P₀, affiche son éventail et ouvre son détail. La réussite partielle conserve
le résultat disponible. Les dossiers périmés demandent un nouveau calcul.

La grille du P₀ et de la diffusion extérieure inclut les dates de marque.
Le repricing intérieur reprend les pas restants, le spot et, selon le modèle,
la variance ou le facteur SABR atteints. Local Vol reprend la portion de la
grille de volatilité correspondant au temps écoulé. Le moteur traite aussi
l'arrondi d'une dernière observation à la frontière de maturité comme le
pricer initial. L'API accepte `reference_paths` pour cette méthode et expose
`/api/mtf/compare` avec deux entrées `a` et `b`. Le mode historique reste
utilisable par les consommateurs KID et CCR dans leur domaine GBM.

Sur l'Athena BNP, deux graines et deux tailles supplémentaires ont contrôlé
les 8 dates des quatre modèles. Avec les paramètres avancés synthétiques
de la recette, les 128 écarts entre l'espérance actualisée et le P₀ sont
restés en deçà de 1,91 erreur standard combinée. Le test en cours de vie
rapproche les créances déjà acquises et la valorisation à toutes les dates.
La recette navigateur locale a utilisé l'API et les processus réels pour
GBM/Heston, le drill-down et le refus d'une jambe SABR invalide.

LSV reste soumis à qualification. Une simulation indépendante du prototype
à levier figé a mesuré un écart absolu de 24,49 pb sur la digitale à six mois
de strike 120 %, avec une erreur standard de 4,62 pb. Ce point dépasse le
seuil de 10 pb. Preuves de recette et scripts locaux dans `.runtime/mtf-models-*`
et `.runtime/mtf-lsv-qualification.*`.

### LSV à levier figé

À l’émission, le Pricer LSV utilise la cible Dupire SSVI, y compris son
prolongement borné, et estime le levier sur un échantillon indépendant.
Le calcul utilise les paramètres de variance du dossier, avec taux et
dividendes plats, sans quanto et en monitoring hebdomadaire.

Le comparateur autorise la jambe LSV lorsque les intervalles de confiance
à 95 % des écarts avec Dupire restent dans ±5 pb sur les vanilles et
±10 pb sur les digitales, sur la grille du calcul. Une preuve signée
lie le contexte de l’éventail au levier. Le drill-down reprend la variance
et le spot atteints, puis vérifie que le levier rejoué est identique.
