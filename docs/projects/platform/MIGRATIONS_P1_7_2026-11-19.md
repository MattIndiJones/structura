# Migrations numérotées et version du schéma

État local au 19/11/2026. Ce chantier traite P1-7 de l'[audit technique du 16/11](../../audits/AUDIT_GLOBAL_TECHNIQUE_2026-11-16.md),
constat D3.

## Ce qui ne tenait pas

Chaque démarrage rejouait environ six cents lignes d'`ALTER TABLE` conditionnels, plus trois reprises
de données gardées par des marqueurs dans `app_migrations`. Trois conséquences :

- **Aucune version** : rien ne disait dans quel état était une base.
- **Aucune protection contre une version plus récente** : une base migrée par une version plus
  récente de Structura s'ouvrait avec du code qui ne connaissait pas ses colonnes.
- **Pas de migration atomique** : une évolution en deux étapes pouvait s'arrêter au milieu.

## Ce qui change

Le paquet `backend/app/db/migrations/` porte les migrations, une par fichier `mNNNN_<nom>.py`,
numérotées sans trou.

- **Enregistrement** : chacune est appliquée une seule fois par base et inscrite dans la table
  `schema_migrations`, avec sa version, son nom, l'empreinte de sa source, sa date et sa durée.
- **Migration 1, la base figée** (`m0001_baseline.py`) : elle reprend sans changement ce que
  `_migrate()` et les trois reprises de données faisaient au 19/11. Sur une base antérieure, elle la
  met à jour comme avant, puis ne tourne plus. Sur une base neuve, `create_all()` a déjà posé les
  tables et elle ne fait presque rien. Un test fige son empreinte ainsi que celle des quatre modules
  qu'elle appelle.
- **Migrations suivantes** : chacune tourne dans **une seule transaction**, DDL compris. Elle est
  appliquée entière ou pas du tout, et son enregistrement fait partie de la transaction.
  - `pysqlite` validant seul un `ALTER TABLE`, le moteur ouvre lui-même la transaction.
  - Une migration qui valide sa transaction elle-même est signalée.
- **Reconstruction de table** : une migration qui reconstruit une table déclare `FOREIGN_KEYS_OFF`.
  Le moteur suspend alors la contrainte, comme SQLite l'exige, et vérifie toutes les références avant
  de valider. Une référence rompue annule tout.
- **Copie avant montée de version** : avant de faire monter de version une base existante, le moteur
  la copie dans `backups/migrations/` du dossier de données, par l'API de sauvegarde de SQLite. Il
  garde les trois dernières copies. Une base neuve n'est pas copiée, ni le premier passage en v1, qui
  ne fait que ce que chaque démarrage faisait déjà.
- **Base d'une version plus récente** : elle est refusée **avant toute écriture**, `create_all()`
  compris, et l'erreur dit quelle version de Structura démarrer. La consultation en lecture seule
  applique le même refus et ne migre rien.
- **Trou dans la numérotation** : une base qui a la v3 sans la v2 est refusée.
- **Migration modifiée après application** : elle est signalée dans le journal.

**Les garde-fous restent réaffirmés à chaque démarrage**, après les migrations, dans
`database._ensure_invariants()`. Ce ne sont pas des migrations : ils se réparent ou se complètent
d'eux-mêmes.

- déclencheurs d'archives en ajout seul ;
- déclencheurs et chaînage de l'audit, qui scellent un événement inséré en SQL brut ;
- index d'unicité des références, créé dès que les doublons signalés sont corrigés ;
- unicité d'un deal par RFQ ;
- déclencheurs d'intégrité RFQ.

**Séquence de démarrage** (`init_db`) :

1. contrôles d'installation ;
2. refus d'une base plus récente ;
3. `create_all()` ;
4. gardes du transport et de l'exécution RFQ ;
5. migrations ;
6. garde-fous ;
7. amorçage.

**Autres effets** :

- `database.py` passe de 1 094 à 360 lignes.
- Les fonctions que les tests appelaient (`_migrate`, `_retire_four_eyes_fixing_policy`,
  `_backfill_*`, `_make_kid_vev_nullable`…) restent disponibles et délèguent à la base figée.
- `/health` donne la version du schéma et celle attendue par le code.
- `schema_migrations` est rangée avec `app_migrations` parmi les tables de tenue du schéma : les
  contrôles d'installation ne la prennent pas pour une donnée métier.

## Écrire une migration

Créer `backend/app/db/migrations/m0002_<nom>.py`, au numéro suivant :

```python
"""Ce que la migration change, et pourquoi."""
from sqlalchemy import text

VERSION = 2
NAME = "Devise de règlement des deals"
# FOREIGN_KEYS_OFF = True   # seulement pour reconstruire une table


def upgrade(conn):
    # Une base neuve a déjà la colonne (create_all) : vérifier avant d'ajouter.
    columns = {row[1] for row in conn.execute(text("PRAGMA table_info(deals)"))}
    if "settlement_ccy" not in columns:
        conn.execute(text("ALTER TABLE deals ADD COLUMN settlement_ccy TEXT"))
    # Pas de conn.commit() : le moteur valide tout, ou annule tout.
```

Règles à respecter :

- **Ordre** : la migration tourne une fois par base, après `create_all()`. Sur une base neuve, la
  table a déjà sa forme finale.
- **Base figée** : ne jamais modifier `m0001_baseline.py` ni les modules de son `FROZEN_WITH`.
  `test_schema_migrations` l'interdit.
- **Données reprises** : une donnée historique reprise sans certitude reste marquée comme telle
  (`UNKNOWN`, `NULL`), comme le faisaient déjà les étapes de la base figée.

## Vérification

- **Tests ciblés** : `test_schema_migrations`, 19 tests. Ils couvrent :
  - la numérotation et l'empreinte figée ;
  - le passage en v1 d'une base neuve et d'une installation antérieure, sans changement de schéma ;
  - le refus d'une base plus récente, aussi par `init_db`, avant toute écriture ;
  - l'atomicité d'un `ALTER TABLE` suivi d'une erreur ;
  - la reconstruction avec vérification des références ;
  - le trou dans la numérotation, la migration modifiée, la copie et sa rotation ;
  - `/health`.
- **Non-régression ciblée** : les tests qui appellent `_migrate`, `init_db`, les reprises de données,
  les contrôles d'installation et `/health` : 24 fichiers, 623 tests réussis.
- **Parcours de bout en bout** : 8 réussis sur une instance démarrée par le nouveau `init_db`, qui
  applique la migration 1 sous `run.py`.
- **Copies de deux bases réelles** : `backend/data/structura.db` du 09/10 et la base du workspace
  Admin. Les originaux ont été copiés et jamais ouverts en écriture.
  - **Ancien chemin de démarrage** (`database.py` de `main`) et **nouveau** ont été lancés chacun
    sur sa propre copie, pour comparer le résultat.
  - **Résultat** : schéma et contenu identiques, hors table de version. Intégrité `ok`, aucune
    référence rompue.
  - **Base d'octobre** : elle passe de 67 à 103 tables dans les deux cas.
  - **Second démarrage** : il n'applique rien et ne change rien.
- **Non fait** : la suite backend complète n'a pas été relancée.
