# C19 — Archives, rejeu et documents figés

Livraison locale du 21 octobre 2026, sans commit ni push. Les neuf constats
du chantier sont traités sur le périmètre ci-dessous. D10 et D11 sont confirmées
par Philippe. Aucune migration de la base métier, reprise des anciennes archives
ou qualification de production n'a été effectuée.

## Résultat métier et décisions

Un résultat conservé reste distinct d'un nouveau calcul. Le PDF Explain reprend
les octets conservés avec le résultat affiché. Une proposition de réinvestissement
est d'abord calculée, puis figée par une action manuelle explicite avant export.
Son coupon, ses hypothèses, son étude d'alternatives et son PDF ne suivent plus
les modifications du fournisseur ou du brouillon. Une nouvelle proposition
possède sa propre archive, avec une filiation vers la précédente lorsque fournie.
Les archives personnelles sont accessibles depuis l'écran de réinvestissement.

Le comparateur de déclinaisons permet également de figer puis rouvrir une étude.
Il conserve l'origine, les variantes examinées, leurs écarts, les entrées réellement
envoyées, les résultats, l'auteur et l'identité de méthode. Les brouillons peuvent
continuer à évoluer. Cette conservation ne qualifie pas les hypothèses de sortie,
de financement ou de récupération du roll : ces correctifs relèvent de C25.

**D10 :** Philippe retient « Gel manuel explicite avant export ».

**D11 :** résultats anciens consultables ; rejeu qualifié uniquement lorsque
l'identité du moteur et des conventions correspond, avec contrôle numérique.
Un recalcul sous une autre identité est une sonde distincte. Aucun résultat
archivé n'est écrasé et aucune version historique manquante n'est inventée.
Les anciennes créances ne contenant que `fixed_price` restent consultables,
mais ne peuvent pas prétendre à un rejeu numérique.

## Constats et validation

| Constat | Correction | Preuve ciblée |
|---|---|---|
| M04-09 — version du calcul Product | L'identité du moteur, du compilateur, des conventions et des bibliothèques est incluse dans le résultat signé et conservé. Les anciennes preuves sans identité sont signalées. | Signature refusée après modification de l'identité ; tests Product et transitions C06. |
| M08-04 — preuve terminale Optimizer | Triggers communs à la création et à la migration ; comparaisons SQL `IS NOT`, protection des identifiants et interdiction de supprimer une recherche terminale. L'archivage reste possible. | UPDATE direct, passage à NULL et DELETE refusés ; schéma migré et neuf protégés. |
| M09-05 — modèle daté RFQ | La réception d'une quote conserve sa référence de modèle datée, ses inputs et sa preuve disponible. L'historique utilise cette référence. Un scalaire sans reçu valide reste `UNVERIFIED_SCALAR`. | Changement du prix modèle courant sans changement de l'écart historique ; référence absente des restitutions sans droit de pricing. |
| M13-03 — créance historique | La fenêtre entre observation terminale et paiement est déterminée à la date demandée, même après règlement actuel du deal. | Créance valorisable avant paiement sur un deal actuellement échu. |
| M13-05 — calendrier de rejeu | Le run conserve le calendrier résolu complet. Le worker restaure ce calendrier, puis effectue la coupe résiduelle, sans résolution courante. Le contexte est vérifié par empreinte. | Résolveur courant rendu inutilisable ; prix archivé reproduit. Régressions VaR, CCR et calendrier. |
| M13-06 — créance certaine | Recalcul depuis montant, dates, taux, courbes et funding archivés ; aucune restitution de `fixed_price` comme prix recalculé. | Sondes distinctes sur montant, paiement, date de valeur, taux et funding : le prix change. |
| M14-03 — PDF Explain Booking | Le calcul crée une archive contenant chiffres, contextes numériques et PDF. L'export sélectionne son identifiant et restitue ses octets. | Export répété identique après interdiction de tout nouveau pricing ; test du bouton avec dates modifiées. |
| M14-04 — erreur de rejeu dans une note | Une erreur numérique de reproduction ou d'attribution laisse les deux MtM et l'écart observé disponibles, sans contribution causale inventée. Les incohérences contractuelles/calendaires restent bloquantes. | Erreur numérique injectée, PDF généré avec diagnostic ; calendrier incohérent refusé. |
| M17-05 — propositions et études vivantes | Preuve serveur des chiffres affichés ; gel manuel immuable ; PDF conservé ; origine, alternatives et variantes archivées séparément des brouillons. | Coupon affiché 14,1602 % conservé après changement de volatilité synthétique 10 → 60 % ; nouvelle proposition distincte ; modification d'une variante sans changement de l'étude figée. |

Le scénario du coupon contrôle l'archivage avec un calcul synthétique injecté ;
il ne constitue pas une nouvelle qualification économique du solveur. Les tests
existants de pricing en vie et du contexte C18 exercent séparément le moteur réel.

## Interactions avec les autres correctifs

- C01 : les preuves de modèle RFQ restent privées au droit de pricing ; archives
  et études sont personnelles, avec contrôle de visibilité de l'objet source.
- C02 : migrations préparées pour le démarrage normal ; aucune intervention sur
  une base d'installation réelle. La vérification d'identité existante est conservée.
- C05/C06 : calendriers figés et filiation Product/versions conservés. Les archives
  ne créent pas un second objet Product ni une nouvelle version de contrat.
- C13 : une correction officielle invalide la sélection du MtM courant lorsque
  ses versions de fixing diffèrent. Les anciens runs restent dans l'historique.
  Aucun événement consommé ou paiement n'est modifié ; D06 demeure ouvert.
- C15/C18 : le funding intervient dans l'actualisation, séparément du taux
  stochastique et du drift. Les créances détachées sont réactualisées au rejeu.
- C16/C17 : domaines et seuils inchangés ; conservation des dossiers et identités,
  sans extension de qualification par le seul fait d'archiver.

Les documents et études sont protégés contre UPDATE/DELETE SQL. Les documents
rattachés à un deal UAT peuvent être retirés dans la purge explicite de son lot ;
la suppression administrative ordinaire d'une source archivée est bloquée.
Les migrations sont additives, idempotentes et testées sur SQLite isolé.

## Vérifications et limites

**444 cas backend distincts réussis dans 20 fichiers**, dont **34 nouveaux cas C19**.
**55 tests frontend réussis dans quatre fichiers**, dont cinq nouveaux contrôles
du parcours d'archive. Compilation Vue/Vite réussie dans un répertoire temporaire ;
le `frontend/dist` existant est conservé.

La sélection élargie présente aussi **104 échecs préexistants**, reproduits avec
les mêmes messages sur la copie antérieure à C19 : 90 tests RFQ (habilitations,
rôle ou motif de gouvernance dans les anciennes fixtures), neuf UAT (références
Product et S0), cinq tests d'analyse produit (habilitation). Les contrôles réels
ne sont pas assouplis pour rendre ces fixtures vertes. Les résultats bruts et leur
comparaison sont conservés dans `C19_VALIDATION.json` et le dossier runtime indiqué.

Trois fixtures de tests existants ont été adaptées au contrat d'archive : export
Explain par identifiant, identité explicite du moteur dans une comparaison, contexte
compilé/daté complet pour l'archivage des sources C18. Les assertions financières
existantes sont conservées. Les premiers échecs de ces fixtures sont consignés,
puis remplacés par leurs validations réussies.

Le premier lanceur de comparaison UAT de baseline n'était pas protégé contre
le démarrage multiprocessing Windows ; ses résultats UAT sont écartés. Le rejeu
avec garde `__main__` reproduit les neuf erreurs d'origine à l'identique.

Les tests utilisent des bases temporaires et des données synthétiques. Aucun
serveur n'est lancé et les appels HTTP externes sont bloqués. Pas de recette
graphique avec navigateur, de test fournisseur réel, de migration métier ou de
qualification générale des documents. T08, T15 et T16 restent partiels avec leurs
consommateurs restants ; T13 est couvert localement, avec recette visuelle et
production restantes. Les 104 échecs antérieurs demeurent à traiter séparément.

Preuves : [C19_VALIDATION.json](remediation-lot-0-2026-10-20/C19_VALIDATION.json).
Le dossier `.runtime/diagnostic-acceptance/c19-2026-10-21` contient les résultats
JUnit, journaux, comparaison de baseline, patch C19 et contrôle de préservation.
