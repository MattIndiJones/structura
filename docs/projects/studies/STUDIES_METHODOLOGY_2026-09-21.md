# Studies 2.3 — VAG, Brinson et ratio FX

## VAG et score du manager

Le bloc E était calculé mais exclu du score lorsque `comparable_costs=false`. Cette exclusion retirait ses 20 % et renormalisait les cinq autres dimensions. Dans le jeu long only, le score passait ainsi à 55 alors que le VAG était négatif.

Le score est un indicateur **descriptif**. E y contribue désormais lorsque ses résultats, sa période et sa base de comparaison sont documentés, même si cette base est fonds net / panier brut. Le tableau et l’interprétation signalent explicitement que les frais et la politique de dividendes participent à cet écart : il ne mesure pas le talent isolément. Une comparaison non documentée reste exclue.

La conversion conserve la formule existante : score VAG = 50 + 50 × tanh(écart annuel linéaire / 20). La durée est désormais celle du bloc E, et non celle de l’ensemble du fonds. L’écart annuel linéaire est l’écart cumulé **en points** divisé par les années calendaires (365,25 jours) ; ce n’est pas une différence de CAGR.

Sur la recette : VAG −13,93 points ; environ −2,32 points/an ; sous-score 44,2/100 ; poids 20 % ; contribution 8,8 points. Le score global devient **53/100**, contre 55 auparavant. Les autres dimensions conservent leur méthode. En cas de données réellement manquantes, leurs règles de couverture et de renormalisation restent applicables.

## Brinson et couverture

Le résultat G est maintenant transmis au calcul de couverture. Il apparaît une seule fois dans le tableau pour l’étude complète. Un résultat calculé est marqué **indicatif**, avec une couverture documentaire distincte de sa fiabilité méthodologique. Sur le dossier complet, 100 % de couverture ne signifie pas 100 % de confiance statistique.

Libellé : « Attribution indicative calculée sur proxies — non intégrée au scoring : portée méthodologique insuffisante pour mesurer la gestion effective. » G ne fait pas partie des six dimensions du Manager Skill Score. Un G non calculé ou en erreur reste indisponible, avec sa cause.

Les effets restent inchangés : allocation −10,25, sélection −4,08, interaction +0,79 point.

## FX réalisé

L’ancien ratio était `abs(FX réalisé) / (abs(P&L prix réalisé) + abs(FX réalisé))`. Ce n’était ni un ratio signé ni, en général, une part du P&L total incluant le latent. La proximité avec 6,8 % du total était ici fortuite.

Le ratio est désormais **FX réalisé / P&L réalisé signé × 100**, hors latent et dividendes. Sur le dossier : −296 121,97 / 3 777 696,13 = **−7,84 %**. L’interface, les données destinées à la synthèse et le PDF utilisent ce même indicateur.

Si le P&L réalisé est nul, le ratio est non défini. S’il est négatif, le dénominateur inverse le signe du ratio ; le montant monétaire FX conserve son signe économique. Le libellé indique donc « FX / P&L réalisé signé ».

## Validation et références

Tests ciblés : VAG négatif conservé avec 20 % de poids, bornes propres à E, comparaison non documentée, G indicatif et G indisponible, FX négatif, dénominateur nul ou négatif, et présence du libellé dans la synthèse.

La référence originale V1 reste conservée. `methodology_reference.py` calcule indépendamment l’attendu du score descriptif 2.3 depuis les métriques de référence figées ; il n’importe pas le moteur. Le dossier de recette et son guide reprennent la nouvelle valeur 53. Les trois écarts antérieurs F/J restent suivis séparément.

Après redémarrage du backend, recalculer l’étude et régénérer le rapport. Les anciens rapports et sauvegardes sont des instantanés : ils ne sont pas réécrits silencieusement.


## Mise à jour 2.4 — corrections des fonctions existantes

Les résultats 2.3 décrits plus haut sont historiques. La version 2.4 corrige les drawdowns A/J, les arrondis F, les épisodes J, les sources des calculs complémentaires et plusieurs interprétations. Voir `STUDIES_EXISTING_FIXES_2026-09-21.md` pour le détail, les tests et les limites. Sur la recette complète : J = 56, Manager Skill = 53, VAG = −13,93 points et 85/85 comparaisons conformes.
