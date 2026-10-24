# C24 — Attribution CRM, analyses datées et devises

Livraison locale du **22 octobre 2026**, sans commit ni push. Les trois constats
C24 et le prérequis CRM M16-05 de C27 sont corrigés. C27 reste ouvert pour les
autres agrégats et historiques. Branche `codex/hybrid-saas-foundation`, HEAD
`7dce3021a88feb4f0021ca3de8f3596277bc72a5`. Aucun serveur ni migration de données
d’exploitation n’a été lancé ; aucune lecture/écriture de la base réelle.

## Résultat métier et critères

| Constat | Comportement obtenu | Preuve |
|---|---|---|
| M16-02 | Changer le client revalide les participants persistés quand leur liste est omise, ainsi que contact principal et mandat. Remplacement ou suppression explicite requis. Client et mandat sont figés dès qu’une preuve Deal/RFQ/Indicative/interaction/Product existe. | Refus avec Deal, RFQ native ou Product canonique ; participants et snapshots conservés. Déplacement sans lien accepté après remplacement cohérent. |
| M16-03 | Les observations Client/personne/affiliation/analytiques/signaux sont limitées aux dates de transaction ≤ asof. Les dates futures et inconnues sont exclues ; aucun délai négatif dans le cycle. | Au 01/02/2026, le trade du 15/01/2027 ne compte pas ; celui du 15/01/2026 donne 17 jours. Affiliation de la personne choisie à la date demandée. |
| M16-04 | Pipeline, tickets médians et fourchettes sont séparés par devise. Aucune conversion implicite, aucun scalaire multidevise. Les repères déclarés n’atteignent que leur devise. | 1 M EUR et 100 M JPY donnent deux valeurs ; ni pipeline 101 M, ni médiane 50,5 M. Une borne EUR n’est pas appliquée au groupe JPY. |
| M16-05 / C27 | Un import sur mandat Demo hérite de la provenance Demo et reste exclu du profil réel. Le portefeuille est réel par défaut, même si toutes ses transactions sont Demo. | Import via le vrai moteur, puis lecture du profil ; inclusion diagnostique explicite `include_demo=true`, origine conservée. |

## Attribution et interactions avec C01/C03/C06

Le déplacement est refusé dès qu’un fait lié existe, y compris un snapshot
historique Product même détaché dans une révision ultérieure. Le refus ne révèle
aucun contenu privé ni identifiant du dossier qui bloque. Créer une nouvelle
opportunité exprime une nouvelle intention ; une correction du passé nécessite
une rectification gouvernée distincte, non implémentée implicitement dans C24.

Les modifications sont sérialisées avec les consommateurs Product/RFQ/Deal.
Le contrôle commun d’attribution recharge l’opportunité après verrouillage ; le
Product recontrôle organisation, client et mandat avant d’enregistrer sa révision.
Le test concurrent, sur SQLite temporaire avec clés étrangères actives et barrière
de départ, permet une seule réussite : déplacement ou création avec l’ancienne
attribution. Aucun couple Product A / opportunité B n’est conservé.

L’audit d’un changement accepté conserve client, mandat, contact principal et
participants avant/après. Les rejets laissent l’historique du Deal, les snapshots
Product et les participants intacts. Les tests des permissions et transitions
C01/C03/C04/C06/C23 passent ; aucune permission ni exception juridique n’est
assouplie. Les termes et calculs quantitatifs restent inchangés.

## Sens de la date et limite de reconstruction

`asof` borne les **dates économiques de transaction**. Une ligne importée après
cette date peut documenter un trade antérieur : C24 ne reconstruit pas le contenu
de la base tel qu’il était connu à l’époque. Cette limite est exposée par
`knowledge_time_reconstructed=false`.

Les statuts d’opportunité, les listes RFQ et le référentiel commercial sont des
**états courants**, datés comme tels. `temporal_basis`, `state_basis=CURRENT_STATE`
et `historical_opportunity_state_reconstructed=false` les distinguent des
observations à asof. L’interface nomme le pipeline et la conversion actuels.
C24 ne déduit aucun ancien statut à partir d’un état courant non historisé ; la
réponse ne doit pas être présentée comme un pipeline historique reconstitué.
Les suivis et états lifecycle restent également courants ; leurs projections de
transactions excluent les trades futurs ou Demo non admissibles.

Les profils conservent les déclarations et leur historique existants. Les bornes
de ticket déclarées restent visibles même sans transaction. Les exclusions de
dates futures, dates absentes et Demo sont distinguées dans la réponse, et les
exclusions de dates sont indiquées dans la fiche.

## Unités et compatibilité

Le choix autorisé au registre est la **restitution par devise**. La dépendance
conditionnelle C11 pour un FX daté n’est donc pas activée : aucun fetch ni taux
de conversion n’est introduit. Les seuils de report C11 ne sont pas modifiés.

- `pipeline_by_currency`, `median_ticket_by_currency` et `ticket_by_currency`
  portent les montants ou statistiques avec leur unité.
- `pipeline_amount` et `median_ticket` restent des scalaires pour une seule
  devise qualifiée ; ils valent `null` lorsque l’unité commune n’existe pas ou
  qu’une donnée non qualifiée empêcherait un montant honnête.
- Une devise absente ou un montant non fini ne devient pas EUR ou zéro. Les
  montants non qualifiés sont dénombrés ; les groupes qualifiés restent lisibles.
- Une borne déclarée EUR ne limite pas une observation JPY. Les consommateurs
  doivent lire les nouveaux groupes et unités, comme les vues mises à jour.

## Validation mesurée

- État initial des trois points d’entrée : **40 réussites, 14 échecs préexistants**.
- **5 reproductions backend valides échouent avant correction**, sur participants
  omis, futur dans le profil/cycle, somme multidevise et import Demo. Le premier
  essai d’import avait un mandat sans `entity_id` ; sa fixture a été corrigée et
  cet essai est exclu de la preuve métier.
- **342 cas backend distincts qualifiés réussis dans 12 fichiers**, dont **29
  nouveaux cas C24**. Le dernier sous-ensemble CRM contient 162 cas ; le passage
  final C24 en contient 29 et les dépendances 179. Les recouvrements ne sont pas
  additionnés deux fois ; `latest-distinct.xml` contient le résultat consolidé.
- **681 tests frontend dans 77 fichiers**, dont **7 nouveaux cas** sur les unités,
  puis build Vite temporaire réussi. `frontend/dist` n’est pas modifié.
- Les anciennes fixtures qui représentent une activité réelle sont désormais
  explicitement `native`, pour Clients et opportunités. Deux tests de cadence
  demandaient une date antérieure à leur dernière observation ; leurs dates ont
  été rendues cohérentes sans supprimer les assertions de confiance/explication.
- Le fichier ancien `test_client_chain.py` conserve **14 échecs et 2 réussites**,
  avec exactement les mêmes nœuds et messages avant/après. Il est séparé du
  périmètre qualifié, pas déclaré vert. Les messages incluent les parcours sans
  desk pilote exigé par les correctifs précédents. Aucun contrôle n’est affaibli
  pour les faire passer.
- Les premiers essais de deux nouvelles fixtures répétaient le contact principal
  comme participant, ce que le domaine refuse déjà ; cette fixture a été corrigée.
- Bases synthétiques isolées, parcours C24 avec clés étrangères actives, concurrence
  sur copie temporaire. Garde requests/curl active ; **zéro tentative externe** dans
  les passages finaux. Aucun serveur, navigateur ou processus de production utilisé.

Le scénario **T14 combiné** conserve un Deal et les participants chez A malgré la
tentative de déplacement vers B ; à asof 01/02/2026 il ne retient que le Deal EUR
et l’historique JPY, exclut le trade 2027 et l’import sur mandat Demo et respecte
le refus de lecture d’un autre périmètre. T14 reste partiel pour la recette
graphique et la qualification déployée. Le reste de C27 demeure ouvert.

Les résultats, commandes, empreintes, conservation et limites figurent dans
[C24_VALIDATION.json](remediation-lot-0-2026-10-20/C24_VALIDATION.json) et
`.runtime/diagnostic-acceptance/c24-2026-10-22/`. Les correctifs et preuves C01–C23
sont conservés hors des fichiers partagés explicitement modifiés pour C24.

## Limites et suite

Pas de recette graphique interactive ni de qualification de déploiement. Les
14 tests anciens de chaîne restent à moderniser séparément. Aucun historique
manquant de statuts n’est fabriqué. Aucun workflow de rectification d’un ancien
rattachement ni conversion FX n’est ajouté. C27 global, ses agrégats/historiques
restants et la clôture générale du registre restent ouverts.
