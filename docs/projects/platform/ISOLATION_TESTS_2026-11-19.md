# Isolation des tests et intégrité référentielle par défaut

État local au 19/11/2026. Réponse à P1-6 de l'[audit technique du 16/11](../../audits/AUDIT_GLOBAL_TECHNIQUE_2026-11-16.md),
constats D2 et D5.

## 1. Les données du poste sont hors d'atteinte (D5)

Plusieurs modules figent un chemin au premier import : la base, le magasin AMC, les
documents, la clé de signature, les clés LLM. Un `monkeypatch.setenv` posé dans un test
arrive trop tard pour eux. Le risque n'était pas théorique. Le 18/11, selon l'ordre de
collecte, des tests lisaient les vraies séries GLE.PA et CS.PA du magasin AMC, et un test
a écrit la série Yahoo d'`AAA` dans `backend/data/market_storage`.

`backend/tests/conftest.py` fait désormais trois choses avant tout import de l'application :

- il retire les variables `STRUCTURA_*` héritées du shell, sauf les deux qui coupent
  l'ordonnanceur et le transport RFQ ;
- il pointe `STRUCTURA_DATA_DIR` vers un dossier temporaire propre à la session, un par
  processus sous xdist, en n'y recopiant que les facteurs Fama-French versionnés ;
- il lève une erreur si un module `backend.app` a déjà été importé.

La suite voit donc ce que voit la CI. Un test qui veut son propre dossier pose toujours
le sien.

## 2. L'intégrité référentielle par défaut (D2)

SQLite n'applique les clés étrangères que connexion par connexion, sur demande. La
production le fait (`db/database.py`). Les moteurs en mémoire des tests ne le faisaient
pas, d'où le retrait du jeu de démonstration, vert en test et en échec sur la vraie base.

`sqlalchemy.create_engine` et `sqlmodel.create_engine` sont enveloppés. Tout moteur SQLite
**créé depuis un fichier de `backend/tests`** pose `PRAGMA foreign_keys=ON` à la connexion
et à chaque prise dans le pool.

Trois choix, chacun issu d'une mesure fausse :

- **L'appelant est reconnu par le chemin du fichier, pas par le nom du module.** Pytest
  importe les tests sous `tests.test_x`, alors que les modules qui réutilisent leurs aides
  les importent sous `backend.tests.test_x`. La première version ne reconnaissait que le
  second nom : sa mesure ne couvrait que les moteurs des aides partagées.
- **L'exemption suit le test en cours**, pas le module qui a créé le moteur. La plupart des
  moteurs viennent d'aides partagées (`test_workflow_controls`, `test_ccr`…) dont les
  propres tests sont conformes : ce sont leurs utilisateurs qui insèrent des lignes orphelines.
- **Une exemption ne retire que ce que la règle a posé.** Un test qui active lui-même la
  contrainte la garde. Sans cela, deux tests qui vérifient justement l'échec d'une contrainte
  (`test_lifecycle_c26`, `test_workflow_controls`) échouaient dans leur module exempté.

L'application ne crée elle-même que le moteur de production, qui applique déjà la
contrainte : la règle ne peut pas rendre un test plus strict que la production.

`backend/tests/sqlite_engines.py` porte `moteur_sqlite(integrite=…)`, importable sans
réexécuter le `conftest`. `test_client_demo_seed` importait le `conftest` lui-même, ce qui
le rejouait sous un autre nom de module.

## Mesure du 19/11/2026

Suite complète en parallèle, règle active partout et liste d'exemption vide : 4 122 réussis,
1 ignoré, **275 échecs et 189 erreurs, tous `FOREIGN KEY constraint failed`** sauf un. Ils
se répartissent sur 49 fichiers. Le cas dominant est un `User` inséré avec un `entity_id`
dont l'`Entity` n'est jamais créée, puis des `Product` et des appartenances à un desk sans
leur parent. L'exception, `no such table: main.users`, vient d'un fichier aussi exempté.

Ces 49 fichiers forment `SANS_INTEGRITE` dans le `conftest`. Les plus touchés :
`test_workflow_controls` (50), `test_client_api` (37), `test_variantes_comparaison` (31),
`test_variantes_filiation` (30), `test_client_import` (29).

Vérification après remplissage :

- les 49 fichiers exemptés : 1 129 réussis ;
- un échantillon non exempté (CCR, comparateur, places de cotation) : 78 réussis, avec une
  sonde temporaire, depuis retirée, qui vérifie qu'un `User` orphelin y est refusé.

La suite complète n'a pas été relancée après le remplissage ; la nocturne le fera.

## Reste à faire

La liste ne doit que raccourcir. Un fichier en sort quand ses fixtures créent ce qu'elles
référencent. L'ordre utile est celui des aides partagées d'abord : une aide qui crée
l'`Entity` de ses `User` peut libérer plusieurs fichiers à la fois. `test_client_demo_seed`
et `test_mtm_realized_sessions` sont dans la liste pour un seul et trois tests
respectivement ; ce sont les premiers candidats.
