# F06 — chaîne CRM historique et booking canonique

**23 octobre 2026 — correction locale et tests ciblés, sans commit ni push.**

Les **14 échecs documentés sont reproduits puis résolus**, avec leurs identifiants
de test conservés. La validation finale comprend **32 cas distincts réussis** :
19 sur la chaîne CRM et 13 contrôles voisins. Aucun code applicatif n’a été
modifié ; la correction porte sur
[`test_client_chain.py`](../../backend/tests/test_client_chain.py).

Le [registre courant](remediation-lot-0-2026-10-20/FAILURE_REGISTER.json) passe de
**16 à 2 cas ouverts**, F01 et F07. Les
[preuves F06](remediation-lot-0-2026-10-20/F06_VALIDATION.json) conservent les cas,
commandes, empreintes et limites.

## Diagnostic

Deux prérequis omis expliquent les créations refusées : les requêtes RFQ ne
désignent aucun desk pilote habilité ; les bookings Marex ne transmettent aucun
identifiant juridique actif. C01/C03 refusent correctement ces requêtes.

Des tests consommaient ensuite directement `.json()` comme un objet créé. Les
`KeyError`, erreurs de lecture de `detail` et suppression d’opportunité acceptée
en sont des conséquences : dans ce dernier cas, aucun Deal n’avait effectivement
été booké pour protéger l’opportunité.

Deux tests hors des 14 échecs documentés passaient même sur le mauvais refus :
le mélange de clients et le contact sans client recevaient 422 à cause de
l’identité juridique absente. Ils vérifient désormais respectivement
`OPPORTUNITY_CLIENT_MISMATCH` et `DEAL_CONTACT_WITHOUT_CLIENT` avec des données
juridiques et un mandat cohérents. Ils ne sont pas ajoutés artificiellement au
nombre d’échecs du registre.

Enfin, le précédent test de chaîne créait une RFQ puis un Deal direct, aux termes
différents, sans lien entre eux. Il prouvait le rattachement à l’opportunité, mais
pas le passage RFQ → Deal. Cette limite de couverture est corrigée.

## Fixtures conformes

- Organisations, utilisateurs, desks, memberships et contrepartie Marex sont
  persistés. Les requêtes passent par de vrais JWT et les contrôles d’accès
  actuels ; aucun remplacement permissif de `get_current_user` ne subsiste.
- Les nouvelles requêtes RFQ désignent le desk habilité de leur organisation.
  Le test de rattachement étranger possède lui aussi un desk valide, pour
  atteindre le refus d’accès au dossier visé.
- Le booking transmet l’ID juridique Marex ; le fournisseur porte son lien
  explicite. Aucune exception juridique ni réaffectation implicite n’est ajoutée.
- SQLite applique les clés étrangères et les protections Product/version
  existantes, installées uniquement sur le schéma de test.
- Les clients représentant l’activité réelle sont explicitement `native` ;
  mandats et opportunités héritent de cette provenance conformément à C24.
- Chaque création consommée par le contexte est vérifiée avant lecture de son
  identifiant. Le booking préparatoire du test de suppression est lui aussi
  vérifié. La fixture ferme le client, la session et son moteur isolé.

## Chaîne et refus vérifiés

Le test existant `test_la_chaine_se_remonte_du_trade_jusqu_a_la_personne` exécute
désormais : Client/mandat/contact → Opportunité → RFQ et Product interne →
composition canonique → calcul → reçu signé conservé → cotation Marex → sélection
de la révision → booking du même Product/version.

Le contexte commercial est hérité côté serveur de la RFQ. Le Deal, l’opportunité,
la RFQ et l’exécution Product se retrouvent dans les deux sens. Un seul Product
est créé. Opérations et Contrôle peuvent lire le Deal autorisé, avec le prix modèle
RFQ masqué ; un utilisateur hors desk et une autre organisation reçoivent 404
sur les accès directs Deal/RFQ/Product.

Le calcul utilise réellement `/api/price/in-life`, avec un strike futur, une date
de valorisation explicite et le seed 42. Ce parcours existant ne demande aucun
historique avant strike. Le fixing initial reste inconnu (`s0_abs=null`), sans
clôture future inventée. Les premiers essais du nouveau test utilisaient le
pricing neuf, dont le reçu ne portait pas la date attendue par la RFQ : le refus
`valuation_date` a été conservé et le test a été raccordé au parcours daté prévu.
Aucun contrôle de reçu n’a été assoupli.

Trois nouveaux cas présentent ensuite un client/mandat contradictoire, une autre
banque active ou un nominal contradictoire. Chaque refus est contrôlé et laisse :

- aucun Deal ni commande de booking réussie ;
- Product, RFQ et opportunité inchangés ;
- compteurs de référence inchangés ;
- un audit `BOOKING_REJECTED` conservé.

Le même parcours peut ensuite réussir avec la requête correcte ; son retry exact
renvoie le même Deal, sans seconde commande. Le test historique d’allocation de
référence vérifie aussi le refus commercial précis, l’absence de Product orphelin
et le premier numéro réellement booké. Le cliché du client d’origine après
changement d’employeur et le refus de suppression d’une opportunité exécutée
restent validés.

## Dépendances et preuves

| Correctif | Critère réexercé |
|---|---|
| C01 | JWT, habilitations de desk, accès opérationnel et confidentialité des prix privés. |
| C03 | Contrepartie active et identité figée de la cotation ; banque contradictoire refusée. |
| C06 | Même Product/version ; contraintes SQL actives ; anciennes RFQ incapables de rétrograder les termes courants. |
| C08 | Refus atomique, reprise propre et retry sans double booking ni référence consommée. |
| C24 | Attribution figée, contexte hérité, affiliation historique et T14 dates/devises/Demo. |
| C27 | Activité native explicite et séparation Production/UAT maintenue. |

| Artefact local | Résultat | Portée |
|---|---:|---|
| `baseline.xml` | 14 échecs | Reproduction exacte du groupe F06. |
| `chain-first.xml` | 16 succès | Qualification des fixtures avant renforcement de la couverture. |
| `chain-third.xml` | **19 succès** | 16 cas existants, dont la chaîne et les refus renforcés, et trois nouveaux refus/reprises. |
| `dependencies-final.xml` | **13 succès** | Attribution C24 et T14, versions Product C06, séparation C27. |

Les artefacts se trouvent dans `.runtime/diagnostic-acceptance/f06-2026-10-23/`.
Les 32 identités finales sont distinctes. `qualified-distinct.xml` est leur union
dérivée, pas une nouvelle exécution. Les essais intermédiaires ne sont pas
additionnés. Les logs, sélections, commandes, empreintes et contrôles de
préservation accompagnent les XML.

Aucun appel HTTP externe n’a été tenté. Les helpers des bookings directs anciens
utilisent toujours des reçus signés de fixture ; le parcours RFQ renforcé utilise
le calcul hors ligne réel décrit ci-dessus. Ces preuves ne qualifient pas la
convergence numérique, d’autres payoffs, le transport RFQ réel, l’authentification
déployée ou la recette graphique. Aucune suite backend globale n’a été lancée.

## Solde et préservation

Il reste **F01 : 1 cas de fixture d’inscription publique**, et **F07 : 1 cas de profil
acteur du parcours relevés/lifecycle**. Ces deux cas n’ont pas été relancés ici.

La référence figée de l’étape 1 conserve ses 121 cas initiaux. Les preuves C01–C27
et F02/F03/F04/F05 restent datées et inchangées. Aucun nouvel arbitrage métier
n’a été nécessaire. Aucune base métier n’a été ouverte, aucun service n’a été
démarré, aucun commit ni push effectué.
