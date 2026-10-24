# F03 — tests RFQ et intégrité des suppressions

**23 octobre 2026 — correction locale, tests ciblés, sans commit ni push.**

Les **90 échecs documentés sont reproduits puis couverts** : 87 gardent leur
identifiant de test et trois sont remplacés par des attentes conformes aux décisions
C03/C23, avec correspondance explicite. La validation finale comprend **212 cas
distincts réussis**, sans échec, erreur, skip ni appel HTTP externe tenté.

Les [preuves F03](remediation-lot-0-2026-10-20/F03_VALIDATION.json) conservent les
identités, empreintes et limites. Le [registre courant](remediation-lot-0-2026-10-20/FAILURE_REGISTER.json)
passe de **111 à 21 cas ouverts**, répartis dans quatre groupes. La référence figée
de l’étape 1 et les preuves C01–C27/F02/F04 restent inchangées.

## Diagnostic

Le premier rejeu conserve exactement les 90 identités du registre et donne :

| Premier obstacle rencontré | Cas | Cause |
|---|---:|---|
| Permission RFQ insuffisante | 67 | Acteur sans rôle métier ; la fixture neutralisait aussi le choix obligatoire du desk. |
| Attribut `role` absent au booking | 22 | Ancien `SimpleNamespace` limité aux identifiants. |
| Motif de référence absent | 1 | Création du fournisseur sans le motif exigé depuis C03. |

Ces obstacles masquaient d’autres incohérences : les bookings UBS désignaient BNP,
le helper réaffectait le fournisseur au moment du booking, et plusieurs attentes
précédaient C03/C08/C23. Après qualification des fixtures, un premier passage du
fichier complet donne **101 succès et 20 échecs**. Leur analyse met en évidence
deux défauts applicatifs réels ; les autres cas relèvent des données et attentes
anciennes. Les 90 échecs ne correspondent donc pas à 90 défauts indépendants.

## Corrections

### Suppression RFQ

Seul le handler `delete_quote` de
[`backend/app/api/rfq.py`](../../backend/app/api/rfq.py) change dans l’application.

- Il prend le verrou organisationnel et relit le droit `prepare`, comme les autres
  mutations du dossier.
- Il refuse la suppression si la RFQ est terminale ou son tour figé n’est plus
  ouvert. La protection des publications réseau et des preuves de traitement
  demeure active.
- Il retire d’abord la sélection éventuelle, puis supprime et flush le last look
  avant sa cotation parente. SQLite contrôle immédiatement cette référence :
  supprimer les deux objets dans un seul flush sans ordre explicite provoquait
  une violation de clé étrangère.

Le nettoyage et la révision Product restent dans la même transaction, sans commit
intermédiaire. Les autres cotations sont conservées. Aucune contrainte SQL n’est
désactivée et aucune migration n’est ajoutée.

### Fixtures et attentes

[`backend/tests/test_rfq.py`](../../backend/tests/test_rfq.py) utilise des utilisateurs
persistés, une organisation, deux desks distincts et des habilitations explicites.
Le monkeypatch permissif de `require_create_desk` est supprimé ; les clés étrangères
sont activées. Le Front reste `user` ; les gestes d’administration utilisent un
acteur `organization_admin` distinct et un motif explicite.

Les banques des exemples exécutés ont un ID juridique de fixture avant sollicitation.
Un gagnant UBS est booké contre UBS. Le helper ne réaffecte plus le fournisseur et
ne répare plus des paramètres contractuels manquants. Fermeté et validité sont
saisies par l’API de cotation avant sélection : aucune mutation directe ne conserve
artificiellement une sélection devenue périmée.

Le helper historique de booking continue de préparer les métadonnées scalaires du
prix modèle et un reçu signé de fixture. Ce dispositif vérifie le contrat technique
du booking ; il ne qualifie pas le prix économique ni le parcours complet de calcul
du Pricer. Les contrôles voisins utilisent aussi les parcours authentifiés existants.

[`backend/tests/test_ccr.py`](../../backend/tests/test_ccr.py) reçoit une adaptation
de deux lignes : le cas qui importe `USER` utilise désormais cet acteur déjà qualifié,
au lieu de lui ajouter une seconde fois un rôle. Le contrôle crédit et ses assertions
restent identiques.

## Requalification des attentes métier

Les identifiants de la table sont préfixés par `backend/tests/test_rfq.py::` dans les
preuves et le registre. Aucun test n’est ignoré ou déclaré réussi sans exécution.

| Ancien test | Test courant | Critère conservé ou actualisé |
|---|---|---|
| `test_sans_suite_is_terminal_until_reopened` | `test_closed_round_requires_an_explicit_successor` | Refus d’ajout, modification et réouverture du tour clos ; nouveau tour explicitement lié, anciennes preuves conservées. |
| `test_an_rfq_without_a_booked_deal_stays_deletable` | `test_only_an_unsolicited_unbooked_rfq_stays_deletable` | Brouillon non sollicité supprimable ; RFQ sollicitée et figée protégée même sans Deal. |
| `test_a_counterparty_outside_the_catalog_stays_accepted` | `test_unknown_counterparty_requires_explicit_audited_admin_exception` | Nom libre seul refusé ; Front refusé pour l’exception ; administrateur autorisé avec motif et audit, ID juridique nul. |
| `test_an_rfq_cannot_be_booked_twice` | Identifiant conservé | Même commande renvoie le Deal existant ; intention distincte sur la même RFQ refusée ; un seul Deal. |
| `test_deleting_the_selected_quote_takes_the_rfq_back_too` | Identifiant conservé | Sélection retirée ; statut `envoye`, puisque la sollicitation figée subsiste. |
| `test_deleted_rfq_and_quote_ids_are_never_reused_by_sqlite` | Identifiant conservé | Non-réutilisation après suppression autorisée d’un brouillon ou d’une cotation, sans supprimer une RFQ figée. |

Le refus de mutation d’une RFQ bookée contrôle désormais les objets persistés et la
révision Product, plutôt que d’exiger la référence Deal dans chaque libellé d’erreur.
Les refus 409 restent obligatoires. Aucun nouvel arbitrage métier n’a été nécessaire.

## Validation ciblée

Les exécutions utilisent un runtime temporaire, un secret de test, des bases isolées
et un garde qui refuse les appels HTTP externes. Les variables `STRUCTURA_*` héritées
sont supprimées avant import de l’application.

| Preuve | Résultat | Portée |
|---|---:|---|
| `baseline.xml` | 90 échecs | Reproduction exacte du groupe F03 avant modification. |
| `regressions-red.xml` | 3 échecs attendus | Suppression de la famille last look avec parent ou enfant sélectionné ; suppression indue après clôture. |
| `rfq-final.xml` | **129 succès** | 127 RFQ, dont six nouveaux cas, et deux tests CCR consommateurs de la fixture. |
| `dependencies-final.xml` | **83 succès** | C01, C03/D01, C04, C06, C08 et C23 : droits réels, confidentialité, identité figée, termes historiques, amendements, retries et révisions de cotation. |

Les six nouveaux cas couvrent les deux suppressions avec sélection, la clôture, puis
les refus de suppression pour un lecteur seul, un membre révoqué et un autre desk.
Ils vérifient aussi la conservation du Product et, pour les opérations concernées,
l’absence de violation de clé étrangère.

Les **212 identités finales sont distinctes**. `qualified-distinct.xml` est l’union
dérivée des deux passages finaux, pas une nouvelle exécution. Les passages de
diagnostic ne sont pas additionnés au nombre de succès. Chaque cas initial possède
un résultat final, avec mapping conservé pour les trois renommages.

Les artefacts locaux se trouvent dans `.runtime/diagnostic-acceptance/f03-2026-10-23/` :
sélections, commandes de lancement reproductibles, logs, XML, garde réseau,
correspondance des cas, diff incrémental, contrôles de préservation et manifeste.

## Dépendances et suite

| Dépendance | Résultat ciblé |
|---|---|
| C01 | Rôles, desks, accès privé, révocation et revue de booking authentifiée préservés. |
| C03 / D01 | Identité de cotation figée ; nom inconnu sans autorisation refusé ; exception directe motivée et auditée ; aucun bypass RFQ. |
| C04 | Amendement gouverné non écrasé par une annotation RFQ ; contrôle crédit réel conservé. |
| C06 | Ancienne RFQ incapable de rétrograder les termes Product ou d’imposer une nouvelle version. |
| C08 | Retry identique idempotent ; commande contradictoire refusée ; pas de double consommation des limites. |
| C23 | Révision matérielle invalidant la sélection, devise, timestamps et clôture conservés ; suppression du tour clos désormais protégée aussi. |

| Groupe encore ouvert | Cas documentés | Suite |
|---|---:|---|
| F01 | 1 | Fixture de mot de passe et contrôle d’inscription publique. |
| F05 | 5 | Permissions des analyses Product. |
| F06 | 14 | Chaîne CRM historique et fixtures associées. |
| F07 | 1 | Profil acteur du parcours relevés/lifecycle. |

Ces **21 cas n’ont pas été relancés dans F03**. Leurs causes et critères restent ceux
du registre jusqu’à leur diagnostic propre. La suite globale backend, la recette
graphique, le transport inter-installations réel et la qualification déployée n’ont
pas été exécutés ici. Aucune base métier n’a été ouverte, aucun service démarré,
aucun commit ni push effectué.
