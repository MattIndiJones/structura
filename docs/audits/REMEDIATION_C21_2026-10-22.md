# C21 — couverture des risques, CVA et fraîcheur

Livraison locale du **22 octobre 2026**, à partir du registre consolidé du lot 0.
Quatre constats traités ; aucune clôture globale ni qualification production.
Branche `codex/hybrid-saas-foundation`, HEAD `7dce3021a88feb4f0021ca3de8f3596277bc72a5`.
Aucun commit, push, serveur démarré ou accès à la base réelle.

## Résultats et critères de validation

| Constat | Comportement obtenu | Preuve principale |
|---|---|---|
| M15-01 | Refus HTTP 422 avant soumission si un scénario ne couvre pas tous les facteurs spot/vol requis. Séries non finies, non positives ou absentes exclues de la génération ; aucun choc nul implicite. | TK1 présent/TK2 absent, aucun job soumis ; zéro explicite accepté. |
| M15-02 | Le dernier snapshot valable est utilisé sans compléter ses trous par un ancien calcul. Gamma/rho absents deviennent `null`, jamais zéro. Chaque métrique expose disponibilité, couverture, composantes absentes et références des calculs. | Calcul complet puis delta seul ; gamma/rho indisponibles, delta courant et run exact conservés. |
| M15-04 | Dates de paiement exactes pour les créances déterministes. EE actualisée à gauche pour la CVA, EPE à gauche, profil après paiement. | 1 M€, deux jours, r=0, récupération 40 %, PD 20 %/an : **657,0841889 €**, limite dure 100 € dépassée et décision bloquée. |
| M15-05 | Une même empreinte de dépendances qualifie préparation et moniteur. Correction de fixing à contrat inchangé : obsolescence, cache invalidé et recalcul distinct. | Fixing version 1→2 sur le même événement, archive initiale strictement identique après nouveau calcul. |

La couverture des Greeks compte les composantes nécessaires : sous-jacent/métrique,
scalaire par position, paire de corrélation. Les vrais zéros sont disponibles.
Un total incomplet est `null` ; les sommes calculables restent séparées sous
`available_*` ou `available_sum_eur`. Les vegas de périmètres différents restent
séparés selon C18. Les sources legacy sans identifiant restent explicitement
étiquetées ; aucune référence de run n'est inventée. La vue Risk affiche
la couverture et les sources en complément du tiret pour une valeur absente.
La fraîcheur calendaire existante des calculs reste signalée séparément.

## Paiements et domaine CCR

Le profil à une échéance est après paiement. Utiliser son zéro sur tout
l'intervalle précédent effaçait la créance ; la nouvelle intégration conserve
l'EE actualisée de gauche jusqu'à la prochaine frontière. Pour une créance
déterministe à taux plat, l'EE actualisée est constante avant paiement : ce
contrôle est analytique, sans bruit Monte Carlo. Les échéances de 1, 2, 3, 7
et 9 jours, un taux non nul et deux créances opposées payées à des dates
différentes sont exercés. La compensation cesse au paiement de la créance
opposée ; elle ne se prolonge pas artificiellement. Version de méthode :
`ccr-1.3-payment-exposure`, intégration publiée dans les hypothèses sauvegardées.

La projection optionnelle reste un replay hebdomadaire borné. Une option de
moins d'une semaine ou un portefeuille mixte incluant une créance payée hors
de sa grille produit un diagnostic et des mesures futures indisponibles.
Les limites contraignantes deviennent MISSING_DATA et bloquent ; aucun
allongement de maturité ni déplacement de paiement n'est appliqué implicitement.
L'intégration discrète des options ne constitue pas une qualification de
convergence. VaR sur photo résiduelle, risque de traduction FX, ageing et
funding portefeuille gardent leurs limites existantes ; SA-CCR, modèle joint
WWR et extensions IM/MPOR ne sont pas ajoutés. **D08 reste ouvert pour toute
qualification au-delà de ce domaine**, sans nouvelle approbation implicite.

## Interactions et dépendances

- **C01/C03** : visibilité métier réutilisée au lancement VaR ; identité juridique et cloisonnement des contreparties conservés.
- **C04** : les limites PFE/CVA sont relues et recalculées sur le portefeuille résultant. Un amendement de la créance courte à 1,1 M€ donne 722,7926078 € de CVA et est bloqué ; Deal et Product restent identiques. Les autres tests d'amendement et d'exception juridique passent.
- **C13/C19** : fixing corrigé sans nouvelle version contractuelle ; ancien MtM/Greeks incompatibles non repris comme courants. Runs CCR conservés intégralement et anciens dossiers toujours consultables.
- **C14/C18** : horizon exact des créances, actualisation et métriques communes préservés ; les autres fonctions de pricing ne sont pas modifiées.
- **C27** : prérequis traité sur le périmètre nécessaire : Greeks/VaR en Production par défaut, UAT explicite côté API, périmètre sauvegardé pour VaR. Le CCR disposait déjà de cette séparation. Tests HTTP sur Production/UAT et exclusion d'une autre organisation. Les autres agrégats, historiques, sélecteurs transversaux et le CRM de démonstration restent à traiter dans C27.

T05, T08, T09 et T10 restent **partiels** : leurs preuves antérieures sont
conservées et complétées par C21. La réconciliation des paiements et du P&L
C22 ainsi que les consommateurs C26 et la recette complète restent ouverts.

## Validation

**226 cas backend distincts réussis dans 16 fichiers**, dont **20 nouveaux cas
C21**. La suite backend complète n'a pas été lancée. Les quatre JUnit finaux
font foi, sans additionner deux exécutions d'un même cas :

- `dependencies-final.xml` : 116 cas C03/C04/C18/C19 et archives ;
- `ccr-final.xml` : 70 cas CCR et C21 ;
- `regressions-final.xml` : 62 cas VaR, chocs, dates, corrélation et migration CCR ;
- `c21-scope-final.xml` : 20 cas C21, dont périmètres HTTP et confidentialité.

Les **20 nouveaux cas exécutés sur une copie des sources initiales** donnent
19 échecs attendus et un succès de garde, puis tous passent sur les sources
corrigées (`baseline-final-c21.xml`). Les essais intermédiaires avec fixtures
incomplètes et le premier essai de baseline sans référentiel partagé ne sont
pas utilisés comme preuve des anomalies.

Un échec préexistant du test de migration CCR a été reproduit sur les sources
initiales (`baseline-migration.xml`) : sa reconstruction de l'ancienne table
`deals` rencontrait le trigger d'archivage C19. La fixture retire ce trigger
uniquement dans la base mémoire avant de simuler l'ancien schéma, puis vérifie
sa réinstallation par la migration idempotente. Les protections applicatives
et les migrations de production ne sont pas modifiées.

Le build requis depuis `frontend/` a exécuté **660 tests dans 75 fichiers**,
tous réussis, puis compilé Vue/Vite dans un répertoire temporaire extérieur
à `frontend/dist`. Le nouveau cas de rendu vérifie l'indisponibilité de
gamma/rho, le delta complet et le numéro de calcul. Pas de recette graphique
interactive ni de connexion à un fournisseur externe. Les tests backend sont
protégés par un garde HTTP hors réseau ; aucune tentative externe enregistrée.

## Conservation et limites

[Preuves structurées](remediation-lot-0-2026-10-20/C21_VALIDATION.json),
[registre](remediation-lot-0-2026-10-20/REGISTER.json) et
[dépendances](remediation-lot-0-2026-10-20/DEPENDENCIES_AND_VALIDATION.md).
Les empreintes initiales des fichiers existants et les sources avant modification
sont conservées dans une baseline temporaire. Le contrôle final distingue les
seuls fichiers attendus modifiés des autres fichiers préservés ; il inclut les
preuves C01–C20 et les anciens fichiers générés. La base réelle est absente
avant et après ; aucun fichier de données réelles n'est utilisé comme fixture.

La livraison valide ces critères localement. Elle ne clôt pas C27, D08, la
qualification de modèles hors domaine ou l'acceptation métier de production.
