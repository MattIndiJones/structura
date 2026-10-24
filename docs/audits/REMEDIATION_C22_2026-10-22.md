# C22 — P&L cash et attribution

Livraison locale du **22 octobre 2026**, sans commit ni push. Deux constats
traités, à partir du registre et des dépendances C13/C18/C19 ; C21 préservé.
Branche `codex/hybrid-saas-foundation`, HEAD `7dce3021a88feb4f0021ca3de8f3596277bc72a5`.
Aucun serveur démarré, aucune migration ni lecture/écriture de la base réelle.

## Résultats métier

| Constat | Comportement obtenu | Validation |
|---|---|---|
| M14-01 | Observation, créance et cash distingués. Cash sélectionné par date contractuelle de paiement dans ]date 1, date 2]. Le roll conserve ensemble calendrier, état réalisé et créances. | Coupon de 10 % observé le 15, payé le 22 : 14→16 et 16→21 donnent un P&L nul sans faux saut de 10 points ; 21→23 donne ΔMtM −10 points et cash +10, donc P&L nul. |
| M14-02 | Une étape « Effet dividendes » modifie q, courbe et décroissance avant le changement des paramètres de diffusion. Le portefeuille conserve cette contribution. | À sigma identique et q seul modifié, effet dividendes non nul, effet volatilité nul ; mêmes propriétés sur les comparaisons figées. |

La première contribution Booking reste nommée « Effet temps », mais sa phrase
explique qu'elle déplace aussi l'état réalisé et les créances. Elle n'est pas
un theta pur : cela évite de mélanger un nouveau calendrier avec une ancienne
mémoire de coupon. Les franchissements réalisés ne sont pas ajoutés une seconde
fois à l'effet spot. Les mêmes bornes de facteurs dividendes sont partagées
avec Valo Explain. Le prix, le modèle, les trajectoires, la graine et le funding
du calcul de référence ne sont pas modifiés.

## Cash et réconciliation

- Les flux observés mais non échus restent des créances dans le MtM et toutes les réévaluations intermédiaires.
- Le cash est pris dans les `settled_cash_flows` à leur `payment_date`, jamais dans le seul temps d'observation. Une date ou un montant manquant/invalide bloque le P&L cash.
- Intervalle ouvert à gauche et fermé à droite : le 22 est compté sur 21→22, puis exclu de 22→23.
- Deux PAY identiques restent deux flux ; un cash négatif conserve son signe. Le sens achat/vente s'applique une seule fois à toute la contribution EUR.
- `Σ facteurs + résidu = ΔMtM` ; `P&L contractuel = ΔMtM + cash contractuel`. Les agrégats EUR prennent les valeurs non arrondies ; l'affichage en points et en centimes reste séparé.

Les nouveaux résultats portent `cash_basis=CONTRACTUAL_PAYMENT_DATE` et
`attribution_version=pnl-payment-v2`. Le champ historique `flows_detached` reste
lisible ; sur les nouveaux calculs il contient les flux contractuels échus
dans la période, aussi publiés sous `cash_flows`. `unrounded` fournit les
contributions utilisées pour l'agrégation, sans arrondir prématurément les points.
Les anciens résultats sont étiquetés comme anciens, sans leur attribuer la
nouvelle sémantique. Booking affiche aussi le total lorsque le cash vaut zéro.

**Ce cash contractuel ne prouve pas un virement bancaire.** Aucun registre
bancaire, rapprochement de paiement réel ou financement implicite n'est ajouté.
La conversion EUR conserve la convention de reporting à la date 2 ; ce correctif
ne fournit pas une attribution exhaustive du P&L de change.

## Valo Explain, archives et corrections officielles

Valo Explain entre deux runs reste une comparaison de **MtM**, sans transformer
son résultat en P&L total. Son étape temps/état déplace désormais les créances
aussi ; l'ancienne étape finale PV qui créait une compensation artificielle
a été retirée des nouvelles attributions. La méthode et sa version sont
conservées avec la comparaison. Contrat, modèle, moteur/conventions et réglages
numériques doivent toujours être compatibles, et les deux prix se reproduire.
Une ancienne identité absente ne devient pas une identité actuelle.

Une recette C13/C19/C22 officialise un coupon, produit un Explain puis corrige
le fixing officiel par le workflow gouverné : le nouvel Explain utilise le
nouveau fixing et son nouveau cash ; l'archive initiale conserve exactement
son JSON, son empreinte et son PDF. Les autres tests C19 d'immuabilité, de
rejeu, de confidentialité et de différences non comparables passent.

Les interfaces et le PDF distinguent cash contractuel et anciens flux ; les
dividendes ont leur propre ligne. Le PDF montre aussi q dans le tableau de
marché, conserve le résidu non attribué et échappe le texte pour afficher
correctement « P&L ». Un saut de page conditionnel évite une page presque vide
avant l'annexe lorsque les nouvelles explications débordent.

## Validation ciblée

**161 cas backend distincts dans huit fichiers**, dont **22 nouveaux cas C22** :

- `test_pnl_c22.py` : bornes de cash, coupon observé/non payé, paiement, mémoire, signes, PAY identiques, cash négatif, dividendes scalaires/courbes, précision EUR, qualité des dates et correction officielle avec archive inchangée ;
- `test_mtm_explain.py`, `test_portfolio_pnl.py`, `test_valuation_notes.py` : parcours historiques, waterfall et export figé ;
- `test_fixing_finality_registry.py`, `test_valuation_semantics.py`, `test_c19_archives.py`, `test_risk_c21.py` : autorité C13, contexte C18, preuves C19 et contrôles C21, dont la CVA de la créance courte.

Les dix premières reproductions valides, avant correction, donnent **neuf
échecs attendus et un succès de garde** (`baseline-core.xml`). Le tout premier
essai utilisait une syntaxe PAY incorrecte dans la fixture ; il est écarté
comme preuve des anomalies. Trois tests portefeuille préexistants échouaient
également avec une identité de test sans rôle C01 ; la fixture a reçu le rôle
`user` et l'organisation legacy explicites, sans modifier les permissions.

Une fixture de courbe de dividendes a ensuite été corrigée pour respecter
les invariants existants : décroissance et premier bucket égal à q. Les
validateurs de production n'ont pas été affaiblis. Le dernier passage par cas
fait foi, conservé dans `latest-distinct.xml` ; les échecs intermédiaires de
fixture restent visibles dans les journaux, sans échec final non résolu.

`npm run build`, depuis `frontend/`, a passé **662 tests dans 75 fichiers**,
puis compilé Vue/Vite dans un répertoire temporaire extérieur à `frontend/dist`.
Deux nouveaux cas de rendu vérifient la distinction cash contractuel/ancien
calcul et la ligne dividendes ; les tests d'export figé C19 passent aussi.
Deux PDF synthétiques avant/après correction ont été rendus en PNG et leurs
quatre pages finales inspectées : textes, graphique, tableaux, annexes et
libellés lisibles. Pas de recette interactive dans l'instance de production.

La suite backend complète n'a pas été lancée. Chaque lot ciblé utilise un
répertoire de données isolé et un garde HTTP. Quatre tentatives de consultation
Yahoo d'une ancienne fixture portefeuille ont été bloquées ; le fournisseur
est maintenant injecté dans cette fixture et ses trois tests repassent sans
tentative réseau (`portfolio-offline-final.xml`). Aucun accès externe n'a été
autorisé. Les chiffres de validation sont dédupliqués par cas actuel,
sans additionner les répétitions d'un test.

## Dépendances et suite

T08 est complété localement pour le nouveau cash/Explain après correction
officielle ; C26 et la recette complète restent ouverts. T09 réunit maintenant
les contrôles déterministes C14/C18/C21 et C22 sur horizon, CVA et coupon payé
à échéance ; la recette transverse intégrale et la qualification production
restent à faire. C27 et les agrégats Production/UAT non couverts par C21 ne
sont pas clôturés ici. L'Explain historique reste borné aux situations
valorisables par son parcours ; une résolution terminale non disponible reste
explicitement indisponible. L'attribution de diffusion du parcours Booking
garde ses capacités existantes ; une comparaison stricte de modèle se fait
dans Valo Explain, qui refuse les contextes non comparables.

[Preuves structurées](remediation-lot-0-2026-10-20/C22_VALIDATION.json),
[registre](remediation-lot-0-2026-10-20/REGISTER.json) et
[dépendances](remediation-lot-0-2026-10-20/DEPENDENCIES_AND_VALIDATION.md).
Les empreintes finales vérifient les seuls fichiers attendus modifiés et la
conservation de toutes les preuves C01–C21, des sources initiales et de
`frontend/dist`. La base réelle est absente avant et après l'intervention.
