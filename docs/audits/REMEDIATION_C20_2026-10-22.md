# C20 — Recherche Optimizer et budgets

Livraison locale du 22 octobre 2026, sans commit ni push. Les quatre constats
M08-01, M08-02, M08-05 et M08-07 sont traités. Les hypothèses de marché, graines,
tailles Monte Carlo, tolérances économiques et contrôles indépendants N/2N sont
conservés. Aucune base métier ni archive historique n'a été modifiée.

## Résultat métier

Les **20 couples famille/objectif proposés** peuvent être sauvegardés puis lancés.
Le résumé lit correctement les réglages de payoff dans leur dictionnaire :
décrément/plancher/rang de l'Athena dégressif et participation imposée du booster
à cap maximal. Les demandes et réglages conservés correspondent à ceux soumis.
Un retry avec la même clé restitue le dossier existant.

La dichotomie n'est plus limitée arbitrairement à 18 itérations. Sa limite est
dimensionnée selon la largeur des bornes, en unités du paramètre PayScript, et
la tolérance numérique existante. L'estimation de charge utilise cette même
limite. Le cas publié de **reverse convertible à 48 mois**, volatilité 20 %,
dividende 2 %, taux 3 %, protection 60 % et N = 1 000, est résolu puis confirmé
sur les deux jeux indépendants. Le prix est contrôlé à nouveau après arrondi du
paramètre ; une réponse « convergé » du solveur ne suffit pas à le rendre admissible.
Les diagnostics conservés comprennent bornes, tolérance, limite/itérations,
trace du solveur, paramètre arrondi et résidu du repricing.

Le budget saisi reste intégralement conservé. Un dépassement à la fin du dernier
calcul ou de la dernière validation entraîne **`complete=false` et `TIME_BUDGET`**,
même si tous les calculs attendus ont fini. Les résultats effectivement reçus
restent consultables ; seuls les candidats réellement confirmés peuvent être
recommandés. Le job sauvegardé devient `PARTIAL` et conserve budget, temps écoulé,
dépassement et politique d'exécution. L'écran affiche ces durées sans annoncer
des travaux restants lorsque tout a effectivement été évalué.

**Limite opérationnelle explicite :** en séquentiel, le budget est une limite
souple contrôlée avant/après les calculs ; un appel numérique engagé peut finir
au-delà. Les workers parallèles conservent leur mécanisme d'interruption et de
nettoyage. La finition du job et le nettoyage peuvent dépasser l'échéance ; ce
dépassement est également signalé. Aucun arrêt à la seconde n'est promis.
Les bornes existantes **30–3 600 secondes**, avec défaut **120 secondes**, sont
inchangées. Cette clarification de D12 n'approuve aucun nouveau plafond métier.

Les capacités et l'aide décrivent désormais la conservation côté serveur,
la navigation sans perte, la reprise comme nouveau calcul lié et l'export comme
copie du dossier. Le conseil erroné présentant les résultats comme temporaires
dans la page est supprimé. La conservation n'implique aucun booking automatique.

## Interaction de dates détectée pendant la validation

Quatre tests Phoenix/Phoenix mémoire échouaient déjà avant C20. Le contrôle des
coupons arrondissait les dates contractuelles à la grille hebdomadaire alors
que C14 enregistre les flux et STOP à la date contractuelle exacte. Une observation
arrondie vers le futur pouvait donc ne plus être comptée dans le droit à coupon
au moment du rappel, ce qui rejetait un coupon effectivement payé.

Le consommateur statistique utilise maintenant les dates contractuelles reçues.
Un cas déterministe avec observation/STOP à `t=0,249`, entre deux nœuds, conserve
le coupon de 2 % et ne crée aucun coupon impayé. Les quatre cas réels sous courbes,
funding, coûts et panier passent à nouveau, avec leurs assertions financières
existantes. Aucun script catalogue ni calcul du moteur Monte Carlo n'est changé.

## Registre et dépendances

| Constat | Validation locale |
|---|---|
| M08-01 — modes sauvegardés | 20 couples famille/objectif : création, lancement détaché, paramètres/résumé conservés et retry idempotent. |
| M08-02 — plafond du solveur | RC 48 mois résolu et validé indépendamment ; estimation alignée sur les bornes ; prix après arrondi vérifié, y compris avec succès du solveur volontairement trompeur. |
| M08-05 — budget | Horloges déterministes 30 → 60 secondes, après exploration ou dernière validation, séquentiel et orchestration parallèle ; résultat partiel et conservation côté serveur. Tests existants de workers réels, annulation et nettoyage. |
| M08-07 — persistance annoncée | Texte des capacités, formulaire et résultats cohérent avec sauvegarde automatique et reprise explicite. |

- **C09 :** scripts et qualification exacte des payoffs conservés, vérification
  du catalogue et des champs liés. Aucun élargissement des familles/modèles.
- **C18/C14 :** taux, courbes, funding et coûts restent communs à la résolution,
  au repricing et à la validation ; droit à coupon raccordé aux dates exactes.
- **C19 :** anciennes recherches terminales inchangées ; nouvelle méthode
  identifiée `optimizer-v2-resolution-budget` dans les nouveaux dossiers/résultats.
  Les protections SQL contre réécriture, NULL et suppression restent actives.
- **C07/C08 conditionnelle :** précision `q=2,001 %` conservée, retries sans
  duplication et reprise créant un nouveau dossier. C08 n'est pas clôturé globalement.

T15 est couvert localement avec les preuves cumulées de C07/C09/C19/C20 ; la
recette graphique et la qualification de production restent distinctes. D12 est
précisée techniquement pour le budget existant ; les autres choix métier de
sensibilités et toute nouvelle limite restent hors de cette livraison.

## Vérifications et limites

**219 cas backend distincts réussis dans dix fichiers**, dont **28 nouveaux cas
C20**. **28 tests frontend réussis dans cinq fichiers**, dont deux nouveaux cas
d'affichage du budget et de compatibilité des archives. Build Vue/Vite réussi
dans un répertoire temporaire, sans réécrire le `frontend/dist` existant.

Avant correction, neuf nouveaux cas reproduisent les anomalies : quatre modes,
un RC et quatre dépassements. Les quatre erreurs Phoenix antérieures sont aussi
reproduites sur la copie d'avant intervention, puis corrigées. Les deux premiers
échecs des nouveaux tests de contrôle d'arrondi/date sont consignés et suivis de
leurs validations finales ; aucun échec ne reste dans la sélection finale.

Les 20 modes sauvegardés sont exercés avec le runner déterministe des tests du
parcours détaché ; les suites financières utilisent séparément le moteur réel,
les huit familles et les validations indépendantes. Les horloges de dépassement
sont simulées ; elles ne constituent pas une mesure de durée maximale garantie.
Pas de recette navigateur ni de fournisseur réel. Les bases sont isolées, les
appels HTTP externes bloqués, aucun serveur n'a été lancé. La suite backend
complète et les 104 échecs antérieurs documentés dans C19 n'ont pas été relancés
ou clôturés par C20.

Preuves : [C20_VALIDATION.json](remediation-lot-0-2026-10-20/C20_VALIDATION.json).
Les journaux, JUnit, reproductions, patch C20 et contrôle de préservation sont
dans `.runtime/diagnostic-acceptance/c20-2026-10-22`.
