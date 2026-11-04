# Historique maximal Yahoo et contrôle de tout le référentiel

État local vérifié le 03/11/2026, sans commit ni push. Philippe a demandé un
backtest sans limitation par un cache court, la conservation des observations
et le téléchargement de tous les titres du référentiel.

## Comportement

Le backtest, le comparateur et son détail demandent `full_history=True`, avec
`auto_adjust=False` : clôtures non ajustées des dividendes. Le mode automatique
`start=None, raw_history=True` applique également cette exigence. Un cache récent
sans preuve de demande maximale ne suffit plus : `period='max'` est demandé
jusqu'à la fin choisie, incluse par une fin fournisseur exclusive à J+1.

Les générations Parquet conservent `history_scope=MAX_AVAILABLE_REQUESTED`, la
fin demandée et l'heure du contrôle. Ces attributs attestent la **requête**, pas
l'absence de lacunes chez Yahoo ni la finalité officielle des barres. Après
validation et publication atomique, les calculs réutilisent ces observations
sur disque. Une fin postérieure à la dernière demande maximale impose un nouveau
contrôle. Une erreur fournisseur ou d'écriture ne promeut jamais un cache partiel.
Le backtest exige tout son panier ; le comparateur expose ses exclusions.

Une date manuelle limite le calcul, sans tronquer l'historique maximal acquis.
En mode automatique, les deux formulaires transmettent `null` même lorsqu'une
date locale est prévisualisée. Les mises à jour brutes partielles préservent
l'historique et sa preuve d'acquisition. Un nouveau maximum remplace la série
pour éviter de mélanger des bases antérieures à une correction de split.
Une calibration ajustée ordinaire garde sa fenêtre de calcul ; si elle doit
actualiser une série auparavant acquise au maximum, elle recharge le maximum
pour conserver les données anciennes sans fusionner des ajustements incompatibles.

Le début commun reste l'intersection des observations véritables. Aucun cours
n'est créé avant la première observation d'un titre. Following dix jours et
fixings officiels conservent leurs conventions respectives.

L'administration lit désormais tous les `Underlying` en base, inactifs inclus,
et déduplique les tickers présents dans plusieurs groupes. Les groupes
personnalisés sont affichés. L'ancien `_CATALOG` reste disponible pour les
libellés de portefeuilles, mais ne définit plus le téléchargement administratif.
Sans début explicite, celui-ci demande `max` en brut et ajusté au lieu de 2000.
L'écran montre les bornes et le périmètre acquis par base ; les résultats du
backtest exposent également la couverture par titre et l'origine cache/fournisseur.

## Contrôle réel du workspace Admin

Le référentiel contient **65 lignes, soit 59 tickers distincts**. Le script
`scripts/sync_reference_history.py` ouvre la base métier en lecture seule,
sans bootstrap ni migration. Il tente les bases séparément, reprend une fois les
erreurs, conserve les observations et relit les générations publiées. Un rapport
est enregistré après chaque titre, avec reprise courte du remplacement atomique
en cas de verrouillage Windows temporaire.

```powershell
.venv\Scripts\python.exe scripts/sync_reference_history.py --installation-config .runtime/hybrid-saas/admin-workbench/installation.json
```

| Base | Tickers conservés après demande maximale | Au moins deux cours | Échec de validation |
|---|---:|---:|---:|
| Brute | 59 | 58 | 0 |
| Ajustée | 58 | 57 | 1 |

- **BNP.PA** : 8 516 cours par base, du 18/10/1993 au 03/11/2026.
- **UCG.MI** : 6 857 cours bruts du 03/01/2000 au 03/11/2026, conservés et
  utilisables en backtest. L'ajusté maximal Yahoo contient des cours négatifs
  anciens : rejet sans effacer l'ancien cache valide, sans remplacer l'ajusté
  par le brut et sans supprimer silencieusement les dates.
- **000300.SS** : une seule barre le 03/11/2026. `max`, `5y` et une demande à
  partir de mars 2021 reproduisent cette limitation ; une demande s'arrêtant au
  01/01/2025 est vide. La barre est conservée, mais le titre n'est pas compté
  comme exploitable en backtest. Aucun autre indice ne lui est substitué.

Une relecture dans un autre processus avec `_HAS_YF=False` retrouve les 59 séries
brutes, soit **475 115 observations**, dont 58 séries avec au moins deux cours.
BNP / UniCredit / STMicro Paris ont 6 421 dates communes, du 03/09/2001 au
03/11/2026. Un rejeu `AT MATURITY: PAY WOF` de maturité trois ans, tous les 252
points, Following dix jours, a exécuté 23 fenêtres depuis ce cache sans réseau.
Ce contrôle ne qualifie pas économiquement tous les anciens cours ni tous les payoffs.

Preuves privées non versionnées dans `.runtime/hybrid-saas/admin-workbench/` :
`market-history-audit.json` (chaque ticker et chaque base),
`market-history-offline-verification.json` (relecture sans fournisseur) et
`market-history-replay-check.json` (23 fenêtres et flux du rejeu réel).

## Validation et mise en service

168 cas backend distincts du domaine sont passés : acquisition maximale,
backtest, comparateur/détail, gouvernance, intégrité du stockage et cache prix.
La dernière exécution groupée a donné 165 succès et trois cas en échec au
chargement de `_CATALOG` ; après restauration de cette constante partagée avec
les portefeuilles, les trois cas ont été rejoués avec succès. Les tests automatisés
simulent leurs réponses fournisseur.

`npm run build` a réussi avec 964 tests frontend et compilation de `dist`.
Les régressions ajoutées vérifient notamment le début automatique, le choix
manuel et les groupes personnalisés. Aucun contrôle visuel navigateur
supplémentaire n'a été effectué pour cette modification de provenance.

Les services préexistants n'ont pas été arrêtés ni remplacés. Les observations
réelles sont déjà conservées ; relancer le workspace Admin avec le launcher,
puis recharger le navigateur, pour activer le nouveau backend.
