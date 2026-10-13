# Structura — atlas fonctionnel et comptes au 13/10/2026

## Livrable

[Ouvrir la présentation HTML globale](application-map-2026-10-13/index.html).
Le dossier contient une vue globale, l’inventaire des comptes/environnements,
un plan d’action, la méthode et **24 fiches de module**, soit 28 pages HTML.
Navigation locale, filtres, onglets et impression ; aucune dépendance réseau.

Chaque fiche décrit son objectif, ses acteurs/droits, ses écrans, ses entrées,
ses sorties, ses interactions, le code présent, les preuves datées et les
ajustements/compléments proposés. Les volumes sont des comptages de lignes,
pas des preuves de fonctionnement en production.

## Comptes de la base principale

Lecture SQLite `mode=ro`, sans import du bootstrap de l’application, sur
`backend/data/structura.db`. Dix comptes, tous actifs au relevé :

| Identifiant | Organisation | Rôle global | Desk RFQ actuel |
| --- | --- | --- | --- |
| admin | Demo | admin | Aucun |
| test | Demo | user | Sales : lire, préparer, pricer, envoyer |
| uat.ops.maker | Demo | ops_maker | Aucun |
| uat.ops.checker | Demo | checker | Aucun |
| rc_independent_scope_20261002 | RC Independent Access Control Entity 20261002 | user | Aucun |
| rc_20261002_ops_maker | Demo | ops_maker | Aucun |
| rc_20261002_checker | Demo | checker | Aucun |
| rc_independent_deal_scope_20261002 | RC Independent Access Control Entity 20261002 | user | Aucun |
| bnp.admin | BNP | admin | Aucun |
| bnp.pricing | BNP | user | Pricing : lire, préparer, pricer, valider, publier |

`test` porte les 38 Deals, 72 Product, 42 RFQ et 21 notes de valorisation.
`admin` porte les six campagnes de simulation, quatre Product et une RFQ, mais certaines API lui donnent encore
une vue globale. Les nouvelles RFQ ont des habilitations par organisation/desk,
sans override automatique pour admin. Hors RFQ, la séparation admin système /
admin organisation et la propriété organisationnelle restent à harmoniser.

Les mots de passe et clés n’ont pas été lus ni intégrés au livrable.

## Environnements isolés

- Six campagnes de simulation `STOPPED`, chacune avec cinq bases d’acteurs :
  30 bases, 90 comptes locaux (admin, test et agent par base). Les six campagnes
  appartiennent au compte principal `admin` ; leur consultation est propriétaire.
- 23 bases de recette RFQ sous `tmp`, avec 77 comptes de fixtures/QA/transport.
- Total secondaire : 53 fichiers `structura.db` et 167 lignes de comptes,
  distincts des dix comptes de la base principale. Ce ne sont pas 167 personnes.
- Archives compressées et état des sessions/processus non audités.

## Écarts actuels à comprendre

- Le code des lots RFQ 7–8 est dans la branche locale, mais les tables
  `rfq_execution_agreements` et `rfq_execution_bookings` sont absentes de la base
  principale. Le démarrage normal du backend initialise le schéma moderne ;
  aucun démarrage/ALTER de cette base n’a été effectué pour l’inventaire.
- La RFQ #91 `RFQ-20261012-003` a un desk pilote Sales et un tour remis au desk
  BNP Pricing dans la **même installation**. Son délai du 12/10/2026 19:33 UTC
  est dépassé, sa lecture n’est pas consignée et aucun cas/calcul/prix bancaire
  n’est conservé dans la base principale.
- `test` n’a pas les droits select/book/organize sur ces nouveaux dossiers.
- La relation RFQ locale est CHF, nominal 1 000 000, traitement interdit.
  L’accord local de trading `Test BNP` est EUR, documentation de test `TOTO`.
  Ces configurations ne forment pas une chaîne prête au traitement.
- Aucun canal interinstallation n’est configuré. Le pilote réel BNP reste
  distinct de la banque locale et des banques fictives de simulation.

## Méthode et limites

Branche `codex/rfq-network-lot-0`, HEAD `e5b17c8` et changements locaux.
Lecture du code, du référentiel documentaire et des données filtrées en lecture
seule. Les recettes antérieures sont citées comme preuves datées avec leur
périmètre ; aucun pytest, build Vue, pricing ou téléchargement externe relancé.

L’application et ses comptes/droits/données n’ont pas été modifiés. Seuls les
documents de cet atlas et leur index ont été ajoutés. Aucun nettoyage ni aucune
migration historique des dossiers de test n’est proposé comme préalable RFQ.

Le relevé filtré se trouve dans `application-map-2026-10-13/database_snapshot.json`.
`build_presentation.py` reconstruit les pages de cette photographie ; il ne
réalise pas un nouvel audit et ses textes doivent être revus si les données changent.
