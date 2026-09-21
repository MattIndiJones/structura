# Studies 2.1 — rapprochement et conventions de frais

Cette correction fait suite à la comparaison du fonds fictif long only avec la référence indépendante. Les données et scripts de référence `LO_BASE_2020_2025_V1` restent inchangés.

## Relancer le test

1. Philippe redémarre son backend pour charger le nouveau code, puis recharge la page Studies.
2. Dans **Client → Chemin manuel**, saisir :

```text
C:\Users\Admin\GitHub\structura\artifacts\studies\LO_BASE_2020_2025_STUDIES_V2
```

3. Cliquer **Scanner le dossier**. Le scan lit désormais `manifest.json`, valide ses paramètres et ses fichiers. Le produit doit être `SYNTH_LO_BASE`, et non le nom du dossier.
4. Les réglages du dossier sont : gestion 1 %, actif net précédent ACT/365 ; performance 15 %, annuelle ; transactions 0,05 % ; valorisation sur relevé ; carnet déjà ajusté des splits ; fichier `cash_events.csv`. Le panier initial reste vide. B, C et D sont activés ; les autres blocs sont désactivés pour cette recette de rapprochement.
5. Cliquer **Lancer l'étude complète**. Il faut recalculer : une ancienne sauvegarde conserve ses anciens résultats.

Résultats vérifiés par un appel au moteur Studies, hors serveur et sans données de marché externes :

| Résultat | Attendu |
|---|---:|
| Réalisé FIFO | 3 777 696,13 USD |
| Latent | 567 572,09 USD |
| Total FIFO hors dividendes | 4 345 268,22 USD |
| Dividendes intégrés au rapprochement | 917 678,53 USD |
| Gestion | 660 069,40 USD |
| Performance | 671 738,44 USD |
| Transactions | 124 621,11 USD |
| Gain net | 3 806 517,80 USD |
| Écart de rapprochement | **0,00 USD ; 0,00 bp d'AUM** |
| Appariements FIFO | 1 341 |
| Hit ratio / profit factor | 59,1 % / 1,72 |
| Durée médiane / moyenne des appariements | 151 jours / 145,8 jours |
| Long terme / tactique, appariements clôturés | 521 / 820 |
| Positions titres encore ouvertes | 18 |

## Conventions paramétrables par étude

Ces paramètres sont exposés dans l'écran, envoyés au moteur et conservés dans le manifeste sauvegardé. Les valeurs par défaut restent les conventions historiques pour ne pas changer silencieusement les anciennes études.

### Gestion

`params.management_fee_basis` :

| Valeur | Assiette et calcul |
|---|---|
| `nav_252` — défaut historique | Chaque actif net publié × taux annuel / 252, y compris la première observation |
| `previous_nav_act365` | Actif net précédent × taux annuel × jours calendaires écoulés / 365 |
| `current_nav_act365` | Actif net courant × taux annuel × jours calendaires écoulés / 365 |
| `previous_nav_act360` | Actif net précédent × taux annuel × jours calendaires écoulés / 360 |
| `current_nav_act360` | Actif net courant × taux annuel × jours calendaires écoulés / 360 |

L'actif net est NAV par part × nombre de parts à la date de l'assiette. Les bases ACT incluent week-ends et jours bissextiles au numérateur, conservent un dénominateur fixe et ne facturent pas le jour initial. Les taux saisis à zéro sont distincts d'un taux absent.

### Performance

`params.performance_crystallization` : `daily` (défaut historique), `monthly`, `quarterly`, `annual`.

HWM permanent initialisé à la première NAV nette, taux constant, aucune hurdle, aucune remise à zéro automatique en cas de perte. Pour les périodicités civiles, une clôture est la dernière observation avant changement de période. Pour un arrêté terminal, le dernier jour de semaine de la période est considéré comme sa clôture ; ce calendrier ne représente pas tous les jours fériés des places financières.

À une clôture, la commission par part est estimée depuis la NAV nette par :

```text
max(0, NAV nette de clôture − HWM précédent) × taux / (1 − taux)
```

Le HWM devient le maximum de son niveau précédent et de la NAV nette de clôture. À un arrêté partiel, la même formule donne la provision en cours sans cristalliser le HWM. Le total de frais inclut les commissions cristallisées et la provision restante ; il ne cristallise pas les plus-hauts intermédiaires. La reconstruction repose sur la convention du fonds : ce n'est pas une comptabilité quotidienne des dettes et paiements.

Les frais périodiques avec variation du nombre de parts sont **rejetés explicitement**, car l'égalisation ou les séries/classes investisseurs ne sont pas encore modélisées. La méthode quotidienne historique reste compatible avec les études antérieures, sans prétendre résoudre l'équité entre investisseurs.

### Limites explicites

Ces options ne couvrent pas tous les contrats possibles. Restent à développer : actif brut, assiette moyenne intrajournalière, ACT/ACT et 30/360, calendrier contractuel spécifique, taux variant dans le temps, barèmes par tranches, minimums/plafonds, frais fixes, TVA, remises, hurdle simple/composée, catch-up, reset/expiration de HWM, classes de parts et égalisation. Ne pas utiliser une option voisine comme substitution implicite.

La fréquence de paiement des frais de gestion n'est pas un paramètre de cette attribution : leur charge réduit la performance, et le règlement d'une dette déjà provisionnée ne doit pas réduire le P&L une seconde fois. Un échéancier complet de dettes et paiements demandera un grand livre dédié.

## Dividendes et cash

`files.cash_events` est un fichier CSV optionnel, résolu dans le dossier de l'étude et couvert par les empreintes de provenance. Colonnes : `date` ISO, `type`, `asset_id`, `amount_local`, `currency`, `amount_prod` dans la devise du fonds. Le fichier du scénario USD peut utiliser `amount_usd` et `usd_per_local` ; cette variante n'est acceptée que pour un fonds USD. Les conversions fournies sont contrôlées lorsque le taux est présent.

Types reconnus : `INITIAL_CAPITAL`, `DIVIDEND`, `MANAGEMENT_FEE_PAYMENT`, `PERFORMANCE_FEE_PAYMENT`. Une seule ligne agrégée par date/type/titre ; doublons, types inconnus, dates invalides et montants non finis sont rejetés. Seuls les dividendes compris entre le début des NAV et l'arrêté alimentent le revenu du rapprochement. Les autres lignes sont reconnues mais ne sont pas additionnées au P&L : les paiements de frais ne doublonnent pas les charges et le capital initial figure déjà dans les flux déduits des NAV.

Un fichier absent produit un avertissement « dividendes non renseignés ». Un fichier fourni doit couvrir tous les dividendes pertinents ; le logiciel ne peut pas prouver l'exhaustivité d'un relevé. Les dividendes sont présentés séparément des P&L FIFO par titre, puis intégrés au gain net global.

## Valorisations et unités

`params.valuation_source` choisit `market` (défaut) ou `composition`. Le second mode exige un relevé à la date exacte de l'arrêté et calcule le mark dans la devise du fonds par `valeur de la ligne / quantité`. La valeur provient du poids × actif net du relevé. Il ne consulte pas les cours externes pour le mark : les quantités, coûts et P&L sont rapprochés au relevé, mais les marks ne sont pas indépendamment validés contre le marché. Ce choix doit donc être explicite, daté et conservé dans la provenance.

`params.orders_split_adjusted` indique que le carnet est déjà exprimé dans les unités de l'arrêté et interdit une nouvelle correction de splits. Cela correspond au JSON fourni, pas aux CSV originaux du générateur. Pour changer l'arrêté, il faut un carnet exprimé dans les unités de ce nouvel arrêté. Le mode n'invente pas de cours pour H/I et les autres blocs de marché.

Un latent non valorisable reste `null`, affiché « — » ; le total et le rapprochement qui en dépendent ne sont pas présentés comme complets. Le moteur conserve aussi l'absence lorsque seule une partie des positions est valorisée.

## FIFO et comportement

Les reliquats de calcul flottant étaient appariés comme de nouvelles transactions, modifiant le décompte et le hit ratio sans changer sensiblement le P&L. La tolérance est désormais liée à la précision numérique des quantités, plafonnée pour conserver les petites transactions explicitement présentes. Les agrégats utilisent les montants non arrondis ; les arrondis interviennent à la sortie.

La distribution de durée porte sur les appariements clôturés ; le nombre de positions ouvertes est distinct. La matrice comportementale reste une agrégation par titre : P&L réalisé + latent hors dividendes, conviction si poids actuel au-dessus du seuil **OU** durée maximale au-dessus du seuil. Ce choix conserve la règle de calcul existante en corrigeant sa présentation. Cash, P&L nuls et titres non valorisés sont exclus du classement gains/pertes. La matrice ne démontre pas l'intention ou la discipline d'un gérant.

## Tests et portée

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_amc_studies.py backend/tests/test_studies_reconciliation.py -q
```

55 tests backend ciblés réussis. `npm run build` depuis `frontend/` : 194 tests frontend réussis, compilation Vite réussie. Avertissements Vite existants sur des imports mixtes. Aucune suite backend complète, aucun redémarrage de serveur, aucun commit/push.

Les cas couvrent les assiettes/bases, les week-ends, les périodicités de cristallisation, les reprises/HWM, un arrêté partiel, le rejet des flux investisseurs non modélisés, les dividendes et doubles paiements, les doublons, le confinement des fichiers, les marks manquants, un relevé postérieur, les reliquats et les petites quantités réelles. Le test de bout en bout utilise l'archive figée `backend/tests/fixtures/studies_long_only_reference.zip`, issue de la référence indépendante, avec blocage des appels de valorisation externe. L'archive ne contient aucun résultat produit par Studies comme valeur attendue.

La référence d'origine et le nouveau dossier d'import sont conservés séparément. Les résultats visibles dans le navigateur devront être recalculés après le redémarrage utilisateur pour confirmer la recette de l'interface.
