# F02 — fixture de migration historique — 23 octobre 2026

**F02 provenait d’une fixture incomplète : le test appelait `_migrate()` sans l’étape préalable `create_all()` du démarrage normal.** L’échec est reproduit sur la source initiale, puis corrigé dans le test. Le code applicatif et les migrations restent inchangés.

La sélection finale passe : **7 tests ciblés, dont un nouveau test de démarrage réel**. F02 est résolu localement sur ce périmètre ; le solde courant passe de **121 à 120 cas documentés, dans 6 groupes encore ouverts**. Les autres cas n’ont pas été relancés. [Registre courant](remediation-lot-0-2026-10-20/FAILURE_REGISTER.json) · [preuve structurée F02](remediation-lot-0-2026-10-20/F02_VALIDATION.json).

## Diagnostic et décision de correction

Le [test initial](../../backend/tests/test_workflow_controls.py) créait quatre tables minimales, puis appelait directement la migration interne. Il échouait en installant le trigger `protect_products_terms_pointer` sur la table absente `products` : `sqlite3.OperationalError: no such table: main.products`.

Le chemin réel de [init_db](../../backend/app/db/database.py) crée d’abord les tables manquantes avec `SQLModel.metadata.create_all(engine)`, installe les gardes réseau/exécution puis appelle `_migrate()`. Cette dernière ajoute les colonnes et protections aux tables déjà présentes ; elle n’est pas une initialisation autonome de schéma.

| Contrôle | Résultat observé |
|---|---|
| Test initial inchangé sur base temporaire | 1 échec, même erreur `main.products` ; [baseline](../../.runtime/diagnostic-acceptance/f02-2026-10-23/baseline.xml). |
| Même test avec la phase de création des tables avant `_migrate()` | Succès sans modifier la migration ; [première reprise](../../.runtime/diagnostic-acceptance/f02-2026-10-23/fixture-recheck.xml). |
| Démarrage réel, base isolée sans tables Product et sans plusieurs colonnes historiques | Deux appels réels à `init_db()` réussissent, sans neutraliser migrations, seeds ni gardes. |
| Conservations métier et intégrité | Cotation inconnue, fixing à revue manuelle, données originales inchangées, aucune version Product ni fixing officiel inventé ; clés étrangères actives et cohérentes. |

Le diagnostic est donc un défaut du scénario de test, avec le prérequis d’initialisation omis. Aucune incompatibilité du démarrage normal n’a été reproduite sur les schémas isolés examinés. Ce résultat ne qualifie pas tous les schémas historiques possibles et ne vaut pas migration d’une installation réelle.

## Correction et protection contre une régression

Seul `backend/tests/test_workflow_controls.py` change côté code :

- La fixture F02 respecte l’ordre `create_all()` puis `_migrate()`. La création des nouvelles tables ne modifie pas les colonnes ou lignes historiques existantes.
- La migration est exécutée deux fois ; les résultats métier sont identiques après chaque passage. La référence RFQ et les spots d’origine restent inchangés ; les liens Product/version restent NULL, sans création de Product artificiel.
- Un nouveau test part d’une base temporaire avec organisation/utilisateur/RFQ/Deal/cotation/événement cohérents. Il simule un ancien état sans les quatre tables Product et sans les colonnes de qualification concernées, puis appelle deux fois le vrai `init_db()`.
- Le nouveau test vérifie `foreign_keys=ON` et `foreign_key_check` vide, la conservation des prix/spots et des états non qualifiés, ainsi que l’absence de fixing officiel ou version Product généré.
- Après chacun des deux démarrages, une insertion RFQ sans Product et un rattachement à une version inexistante sont refusés par les gardes SQL. Les moteurs temporaires sont fermés en fin de test.

La suppression de tables/colonnes sert uniquement à construire cet ancien schéma dans la fixture temporaire, avant le démarrage. Aucune donnée de l’installation réelle n’est utilisée ni modifiée. Aucun trigger applicatif n’est supprimé pour contourner le contrôle testé.

## Tests exécutés

Les tests sont lancés depuis la racine avec environnement `STRUCTURA_*` hérité retiré, répertoire de données temporaire et secret JWT de test. Aucun serveur n’est démarré ; les HTTP externes sont bloqués et **aucune tentative n’est enregistrée**.

La [sélection finale](../../.runtime/diagnostic-acceptance/f02-2026-10-23/final-backend.xml) contient exactement sept identités distinctes :

1. F02 : migration des lignes anciennes ambiguës.
2. Nouveau test : démarrage réel, création des tables Product manquantes et conservation des lignes historiques.
3. Migration de politique de fixing : retrait de FOUR_EYES et obsolescence des propositions.
4. C06 : conservation d’une RFQ historique non qualifiée sans inventer de version.
5. C06 : refus d’un pointeur de version Product rétrograde.
6. C19 : ajout de colonne d’archive et réinstallation des protections.
7. C21/CCR : migration additive conservant les données anciennes inconnues.

**Résultat final : 7 succès, 0 échec, 0 erreur, 0 ignoré.** Durée affichée : **16,71 s**. Deux avertissements SQLModel préexistants sur `session.query()` sont conservés dans le journal. Les essais intermédiaires et la baseline ne sont pas additionnés à ces sept cas. La suite backend complète et le frontend ne sont pas relancés : aucune modification applicative ou Vue.

## Suivi et limites

Le [registre consolidé](remediation-lot-0-2026-10-20/REGISTER.json), son [suivi lisible](remediation-lot-0-2026-10-20/ANOMALY_REGISTER.md) et la [matrice de validation](remediation-lot-0-2026-10-20/DEPENDENCIES_AND_VALIDATION.md) renvoient au registre courant des échecs. Les inventaires et manifestes figés de l’étape 1 restent inchangés : leurs 121 cas constituent la situation avant F02, et non le solde après cette correction.

Aucun autre arbitrage métier n’est nécessaire pour cette correction de fixture. Le domaine des anciennes bases à reprendre en production, la procédure de sauvegarde/restauration et l’adoption des installations anciennes restent des travaux distincts. Aucun contrat, cash, fixing consommé ou archive n’a été réécrit.

La préservation des travaux antérieurs, des sources applicatives, de la référence consolidée et des anciennes preuves est vérifiée par empreintes. HEAD et branche inchangés ; aucun commit ni push. La base métier est absente avant et après et n’a pas été ouverte.
