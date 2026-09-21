# Studies 2.2 — dividendes, créances et réinvestissement

## Relancer le fonds de référence

Philippe redémarre le backend puis recharge Studies. Aucun serveur n'a été lancé ou redémarré par cette livraison.

Dans **Client → Chemin manuel**, scanner :

```text
C:\Users\Admin\GitHub\structura\artifacts\studies\LO_BASE_2020_2025_STUDIES_DIVIDENDS
```

Le manifeste configure le registre daté, la conservation du dividende en cash, une retenue fiscale nulle et le paiement au détachement, conformément au scénario indépendant. Lancer l'étude B/C/D. Les données et scripts de référence `LO_BASE_2020_2025_V1`, ainsi que le dossier d'import V2, restent inchangés.

Dans **B — Attribution**, le tableau conserve le réalisé, le latent et le total hors dividendes, puis ajoute **Dividendes nets (FX inclus)** et **Résultat avec dividendes**. Les frais du fonds restent dans le rapprochement global. La colonne des poids conserve désormais sa précision jusqu'à l'affichage.

| Contrôle | Attendu |
|---|---:|
| Événements de dividende | 480 |
| Revenus nets acquis | 917 678,53 USD |
| Encaissés | 917 678,53 USD |
| Créances restantes | 0,00 USD |
| Réinvestissement automatique identifié/reconstruit | 0,00 USD |
| Écart de rapprochement NAV | 0,00 USD |
| Entreprise 03 : P&L hors dividendes | 616 359,80 USD |
| Entreprise 03 : dividendes nets | 43 907,06 USD |
| Entreprise 03 : résultat dividendes inclus | 660 266,87 USD |

Les achats mensuels du scénario peuvent employer le cash disponible, dont des dividendes. Ils ne sont pas qualifiés de réinvestissements automatiques : leur affectation à un dividende n'est pas documentée.

## Paramétrage du fonds

La section **Dividendes — convention du fonds** contient `params.dividends`, sauvegardé dans le manifeste et dans la provenance de l'étude.

| Paramètre | Valeurs / fonctionnement |
|---|---|
| `status` | `unknown` : non renseigné ; `none` : absence confirmée ; `provided` : registre daté fourni |
| `treatment` | `cash`, `automatic`, `discretionary` |
| `destination` | `same_asset` ou `basket` |
| `allocations` | Pour un panier, objet identifiant → fraction positive, somme égale à 1 |
| `execution_source` | `orders` : achats déjà au carnet ; `reconstruct` : achats à reconstruire |
| `delay_weekdays` | Nombre de jours de semaine après paiement, entre 0 et 365 |
| `fractional_shares` | Fractions autorisées ; sinon arrondi inférieur et cash résiduel |
| `reinvestment_fee_pct` | Taux spécifique facultatif ; sinon taux de transaction du fonds |
| `documentation` | Référence libre à la clause de la note du fonds/AMC |

Le délai zéro signifie le paiement, reporté au lundi si le paiement tombe un week-end. Le calendrier exclut samedi/dimanche ; les jours fériés des places et les règles contractuelles plus complexes nécessitent une extension. Aucun change n'est récupéré ou remplacé par 1 par défaut entre devises différentes : les événements et exécutions fournissent les changes utilisés.

Une décision discrétionnaire du gérant est décrite par les achats du carnet. La reconstruction est réservée à une convention automatique explicite. Les distributions du fonds aux investisseurs sont hors de ce registre : elles demandent un traitement distinct des flux et de la performance.

## Fichier des événements

`files.dividends` désigne un JSON UTF-8 contenu dans le dossier de l'étude. Son chemin est confiné et son empreinte est conservée. Format : `{"events": [...]}`, maximum 20 000 événements.

Exemple pour dix actions donnant droit à un dividende brut de 10 USD par action, avec une retenue de 10 % :

```json
{
  "events": [
    {
      "id": "DIV-X-20240105",
      "asset_id": "X",
      "currency": "USD",
      "ex_date": "2024-01-05",
      "payment_date": "2024-01-10",
      "eligible_quantity": 10,
      "gross_per_share": 10,
      "withholding_rate": 0.10
    }
  ]
}
```

Les identifiants de titres doivent correspondre au carnet. `id` est unique ; un même titre/détachement/paiement doit être agrégé en un événement unique. Les champs inconnus, dates inversées et montants non finis sont rejetés.

Montants possibles :

- `gross_per_share`, calculé sur la quantité éligible ;
- `gross_local`, montant brut total, contrôlé contre le montant par action si les deux sont fournis ;
- `net_local`, montant net total ;
- `withholding_local` **ou** `withholding_rate` (fraction de 0 à 1).

L'absence de retenue n'est pas supposée : avec uniquement un brut, renseigner zéro si le dividende n'est pas taxé. Un net seul est accepté ; le brut et la fiscalité restent alors non renseignés. Si brut et net sont fournis, leur différence donne la retenue ; une retenue explicite contradictoire est rejetée.

La quantité éligible provient du panier initial déclaré et des exécutions **strictement antérieures au détachement**. Les trades du jour ex ne changent pas cette quantité. `eligible_quantity`, si fourni, doit se rapprocher de la quantité reconstruite. Le registre est long only : une quantité éligible négative est rejetée.

Les ordres utilisés sont normalisés dans les unités du carnet corrigé des splits. Si le montant par action se rapporte à d'autres unités, `entitlement_unit_factor` convertit la quantité normalisée vers les actions à la date ex. Exemple : carnet exprimé après un split 2:1 ultérieur, facteur d'éligibilité `0.5`. Le facteur vaut 1 par défaut ; aucune transformation implicite des montants par action.

## Détachement, paiement et change

Le registre calcule un état à l'arrêté, pas un nouveau moteur quotidien de NAV : les NAV fournies demeurent l'entrée de Studies.

1. Au détachement, le dividende net devient une créance et un revenu acquis.
2. Au paiement, la créance est soldée et devient du cash. Ce transfert n'est pas un deuxième revenu.
3. À l'arrêté, un dividende détaché mais non payé reste une créance. Un dividende non encore détaché n'est pas reconnu.
4. Les effets de change entre détachement et règlement, ou entre détachement et arrêté pour une créance impayée, sont exposés séparément.

Changes en devise du fonds par unité de devise locale : `fx_at_ex`, `fx_at_payment`, et, pour une créance impayée, `fx_at_valuation` avec `fx_valuation_date` égale à l'arrêté. En même devise, le change vaut 1. Entre devises, les taux applicables sont obligatoires. La source et la pertinence économique des quotes fournies restent à contrôler par l'utilisateur.

Le revenu net acquis à l'arrêté comprend le revenu au détachement et son effet change. C'est ce montant qui alimente la colonne « dividendes nets (FX inclus) » et le rapprochement. Le cash payé est supposé converti dans la devise du fonds au taux de paiement fourni ; un compte cash multidevise conservé après paiement demanderait un grand livre supplémentaire.

Une créance détachée avant le début des NAV et payée pendant l'étude est refusée : son bilan d'ouverture doit être modélisé, sinon le revenu de la période serait surévalué.

## Réinvestissement

Chaque événement automatique peut contenir `executions`, une ligne par destination. Les dates doivent correspondre au délai de la convention. Si le réinvestissement devrait déjà avoir eu lieu mais n'est pas documenté, l'étude le signale comme incomplet sans inventer d'achat.

### Achat déjà présent

```json
"executions": [
  {"asset_id": "X", "date": "2024-01-10", "order_id": "ORDRE-123"}
]
```

L'ordre doit être un achat exécuté, sur le bon titre et à la bonne date. Son prix et sa quantité font foi. L'ordre n'est jamais ajouté de nouveau. Un ordre ne peut pas financer plusieurs événements ; un ordre global regroupant plusieurs dividendes exige une ventilation préalable. Le coût ne peut pas dépasser le budget attribué au dividende. Le reliquat reste en cash.

### Achat reconstruit

```json
"executions": [
  {"asset_id": "X", "date": "2024-01-10", "price_local": 20, "currency": "USD", "fx_to_fund": 1}
]
```

Pour 90 USD nets et sans frais : 4,5 actions si les fractions sont autorisées, ou 4 actions et 10 USD de reliquat sinon. Avec des frais proportionnels, le budget d'achat est réduit pour financer les frais. Un panier applique les allocations configurées à ce budget ; les reliquats ne sont pas réalloués silencieusement entre titres.

Prix, devise et change applicables doivent être fournis ; aucune quote de marché fictive n'est inventée. Les unités de prix/quantité doivent être celles de l'arrêté du carnet. Si un achat existe déjà au même titre et à la même date, la reconstruction est refusée comme ambiguë : il faut lier l'ordre réel.

Les achats construits portent le préfixe `DIV_REINVEST:`, sont ajoutés au FIFO en mémoire et enregistrés dans le résultat comme reconstruits. Ils ne modifient pas les fichiers du carnet. Ils entrent dans les positions, les statistiques d'activité et les frais ; leur impact sur l'éligibilité des dividendes ultérieurs est pris en compte. Une étude contenant ces achats conserve un statut de revue des hypothèses.

Le taux spécifique de réinvestissement remplace, pour les ordres identifiés, le taux standard de transaction par un ajustement de frais ; il ne s'y ajoute pas une seconde fois. L'affectation à un dividende ne doit jamais transformer l'achat lui-même en revenu.

## Compatibilité et écrans

L'ancien `files.cash_events` reste accepté. Ses dividendes sont détaillés par titre selon les paiements, mais le statut est « Paiements seuls — créances non documentées ». Ce fichier ne prouve pas les dates de détachement ni l'absence de dividendes à recevoir. Quand les deux fichiers sont fournis, le registre daté fait foi et les totaux encaissés par titre doivent se rapprocher du fichier cash ; les paiements ne sont pas additionnés deux fois.

Statut `unknown` sans registre : montants affichés « — », pas zéro. Statut `none` : zéro explicite. La couverture ajoute une ligne « Dividendes et créances » ; son taux est nul pour les informations manquantes ou les paiements seuls. Une couverture à 100 % signifie données déclarées disponibles pour les calculs, pas vérification indépendante de leur exhaustivité.

Dans B, le panneau **Dividendes** affiche les revenus acquis, encaissés, créances, effets FX, montants réinvestis et frais. Le tableau d'événements détaille brut, retenue, net, dates, reliquat et liens aux achats. Le résultat sauvegardé comprend le registre et les ordres reconstruits. Les anciennes sauvegardes restent consultables ; il faut relancer pour produire ces nouveaux champs.

La matrice D reste une classification du P&L sur prix, hors dividendes, comme auparavant ; les nouvelles colonnes sont dans B. Les exports PDF existants conservent leur présentation d'attribution hors dividendes : le détail événementiel est consultable dans l'écran et la sauvegarde JSON, pas encore dans un tableau PDF dédié.

## Vérifications

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_studies_dividends.py backend/tests/test_studies_reconciliation.py backend/tests/test_amc_studies.py -q
```

79 tests backend ciblés réussis, dont des cas indépendants à la main et le rapprochement des 20 titres avec le jeu de référence sur six ans. Couverture : absence/information manquante, dates ex/paiement, éligibilité, splits, fiscalité, devises, arrêtés partiels, panier, frais, fractions, reliquat, double import et achats déjà présents. Les tests intégrés vérifient le FIFO et le rapprochement avant et après réinvestissement.

`npm run build` depuis `frontend/` : 194 tests frontend réussis et build Vite réussi, avec les avertissements habituels sur des imports mixtes. Pas de suite backend complète. Pas de commit ni push. La recette visuelle par Philippe reste à effectuer après son redémarrage du backend.
