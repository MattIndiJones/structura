# F07 — relevés/lifecycle : fixture et contrôles d’accès

**23 octobre 2026 — correction locale et tests ciblés, sans commit ni push.**

L’échec documenté est **reproduit puis résolu**, avec son identifiant de test
conservé. La validation comprend **20 cas distincts réussis** : 11 dans le fichier
des relevés et 9 contrôles voisins. La correction porte uniquement sur
[`test_fixings_releves.py`](../../backend/tests/test_fixings_releves.py) ; aucun
code applicatif ni contrôle d’accès n’a été modifié.

Le [registre courant](remediation-lot-0-2026-10-20/FAILURE_REGISTER.json) passe de
**2 à 1 cas ouvert : F01**, non relancé ici. Les
[preuves F07](remediation-lot-0-2026-10-20/F07_VALIDATION.json) conservent les
identités, résultats, commandes et empreintes.

## Diagnostic et correction

Le test de booking de la fenêtre de départ fournissait un
`SimpleNamespace(id=1, entity_id=1)` dépourvu de `role`. Le passage dans C01
échoue avant construction des événements avec l’erreur
`AttributeError: 'types.SimpleNamespace' object has no attribute 'role'`.
Cet échec ne démontrait donc pas une régression du calendrier ou du lifecycle.

La fixture utilise désormais une organisation et un utilisateur persistés,
avec le rôle métier requis, ainsi qu’une contrepartie BNP Paribas active et son
identifiant juridique explicite. SQLite applique les clés étrangères et les
gardes Product/version existantes sur son schéma isolé. Il n’y a ni rôle par
défaut ajouté au moteur d’accès, ni exception juridique, ni garde neutralisée.

La construction de la demande et de son reçu signé est partagée entre le test
initial et les nouveaux contrôles HTTP. Session et moteur sont fermés à la fin
de la fixture. Aucun arbitrage métier nouveau n’a été nécessaire.

## Parcours et dépendances vérifiés

Le cas initial vérifie une fenêtre de départ `STRIKE_FIX AVG 10D` : les dix dates
contractuelles ont chacune une ligne, le strike apparaît une seule fois et les
neuf autres relevés sont enfants de cet événement. La réduction `AVG` reste
portée par le parent ; les enfants n’ont pas de réduction autonome et restent
`EXPECTED` tant qu’aucun fixing n’est établi. Le Deal porte la contrepartie
attendue, la version Product 1 et un lien réciproque avec l’exécution Product.
Le contrôle SQLite des clés étrangères ne remonte aucune violation.

Deux nouveaux cas HTTP, en autonome et en installation gérée, passent par les
vrais JWT de la fixture C01 :

- booking anonyme refusé avec 401 ;
- booking par Contrôle refusé avec 403, sans Deal ni Product créé ;
- booking par Opérations accepté avec 201 ;
- lecture par Contrôle autorisée avec 200 et neuf relevés enfants ;
- lecture étrangère refusée avec 404 en autonome ou 401 selon la politique
  d’identité de l’installation gérée.

| Correctif | Critère réexercé |
|---|---|
| C01 | Identité réelle, droits de booking et lecture, cloisonnement entre organisations/installations. |
| C03 | Contrepartie juridique active et identifiant explicite au booking. |
| C06 | Deal lié à Product/version ; contraintes SQL actives et exécution réciproque. |
| C13 | Registre officiel prioritaire, version en attente bloquante, exception annulée puis rejouable. |
| C26 | Relevés de départ complets sans doublon ; signalement des manquants et de leur effet sur S0 ; corrections officielles et résistance à une panne du fournisseur. |

Les neuf tests voisins vérifient notamment que la correction officielle actualise
la watchlist sans réécrire son résultat antérieur, qu’une version officielle en
attente ne retombe pas sur le fournisseur, et qu’un fixing officiel conserve
sa priorité face à un cours reporté ou absent. Les règles de finalité C13 et les
seuils de report C11 restent inchangés.

## Preuves et limites

| Artefact local | Résultat | Portée |
|---|---:|---|
| `baseline.xml` | 1 échec | Reproduction exacte du cas F07 avant correction. |
| `releves-first.xml` | **11 succès** | Neuf cas existants, dont F07, et deux nouveaux cas HTTP. |
| `dependencies-final.xml` | **9 succès** | Fenêtre de départ, finalité et registre officiel, correction et watchlist. |

Les artefacts sont conservés dans `.runtime/diagnostic-acceptance/f07-2026-10-23/`.
Les 20 identités finales sont distinctes. `qualified-distinct.xml` est leur union
dérivée, pas une nouvelle exécution. Aucun appel HTTP externe n’a été tenté.
Les tests utilisent des bases isolées et un environnement `STRUCTURA_*` assaini.

Le booking utilise un reçu signé de fixture à **97,9 %**, pas une validation de
prix par le moteur quantitatif. La création des dix lignes et les contrôles
voisins du registre officiel sont vérifiés séparément : ces résultats ne
qualifient pas de bout en bout une moyenne sur dix fixings officiels.
Ils ne constituent pas non plus une recette graphique, une qualification de
l’identité déployée ou une validation générale du lifecycle. Aucune suite
backend globale ni build frontend n’a été lancé.

## Solde et préservation

Il reste **F01 : un cas de fixture d’inscription publique**, à diagnostiquer
séparément. Le registre courant comporte **120 cas résolus localement sur les
121 cas initiaux**, sans clôture globale ou qualification de production.

La référence figée de l’étape 1, les preuves C01–C27 et F02/F03/F04/F05/F06,
les décisions métier et le graphe de dépendances sont conservés. Aucune base
métier n’a été ouverte, aucun service démarré, aucun commit ni push effectué.
