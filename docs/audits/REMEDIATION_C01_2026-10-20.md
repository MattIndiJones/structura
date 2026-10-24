# Lot 1 — C01 : permissions métier et confidentialité

**20 octobre 2026 — implémentation locale et tests ciblés ; sans commit ni push.**

Les sept constats de C01 ont reçu un correctif et une validation locale. Le
[registre](remediation-lot-0-2026-10-20/REGISTER.json) conserve les autres chantiers
ouverts. Cette livraison ne clôture ni C02, ni les recettes transverses T12/T14,
ni la qualification en production.

## Règle d’accès explicitée pour D05

La propriété organisationnelle et le partage par habilitation reprennent les
décisions de la [note organisations](../projects/platform/ORGANIZATION_ACCESS_DESIGN_2026-09-24.md)
et le périmètre des [desks RFQ](../projects/platform/RFQ_NETWORK_LOT_1_SPECIFICATION_2026-10-12.md).
Les précisions suivantes sont implémentées localement et restent identifiables
pour la revue métier de D05 ; elles ne constituent pas une nouvelle approbation
implicite de Philippe.

| Objet ou action | Règle implémentée |
|---|---|
| Accords, documentation et limites de relation de trading | Super utilisateur métier, via `trading.relationships.manage`. Front, Opérations et Contrôle refusés et audités. |
| Déclaration de règlement | Opérations ou super utilisateur, via `trading.settle`. Date de valeur, date contractuelle de règlement et instant réel de déclaration distincts. |
| Calcul libre de structuration | `business.price`, également sur in-life, implied funding, Optimizer, solveur, grille, scénarios et soumission/reprise de calculs batch. |
| Valorisation opérationnelle | Les routes MtM d’un Deal existant restent accessibles selon le droit de lecture de ce contrat. Elles ne donnent pas accès au Pricer libre. |
| Product de RFQ | Lecture complète et calculs réservés au profil de pricing, avec droits `read` et `price` sur les RFQ rattachées. Les modifications de contexte/termes demandent aussi `prepare`. Le créateur n’a aucun droit résiduel après révocation du desk. |
| Product sans RFQ et sans espace bancaire | Partage dans l’organisation pour les profils de pricing. Les secondaires utilisent les projections contractuelles nécessaires à leur workflow. |
| Deal de RFQ avec desk | Organisation concordante et droit `read` sur la RFQ source. Même prédicat pour accès direct, listes et projections dérivées. |
| Deal sans périmètre RFQ par desk | Lecture métier dans l’organisation. Les anciennes RFQ sans desk conservent leur périmètre personnel et les accès opérationnels antérieurs de leurs Deals. Un dossier sans organisation identifiable conserve le repli personnel existant. |
| Espace Product bancaire | Périmètre destinataire et droit de pricing conservés ; aucune ouverture générale par le partage organisationnel. |
| CRM | Les Deals sont filtrés avant calcul des détails, comportements, agrégats, cadence et signaux. Aucun agrégat supplémentaire ne résume les contrats exclus. Les RFQ liées sont filtrées et leur prix modèle reste privé. |
| Documents et notes de valorisation | Lecture selon les droits sur leurs contrats ; le rattachement Product bancaire reste protecteur. |
| Portefeuilles | Collections organisationnelles ; seuls les Deals lisibles contribuent aux compteurs et agrégats. Affectation par Front/Opérations/super utilisateur ; le Contrôle conserve la lecture. |
| Études AMC sauvegardées | Lecture organisationnelle, création/auteur conservés. La suppression personnelle existante n’est pas élargie. |
| Alertes | Visibilité et refresh manuel selon le Deal ; lecture acquittée séparément pour chaque utilisateur. |

Les anciennes RFQ sans desk ne sont pas migrées vers le partage collectif. Leurs Product et projections contractuelles restent soumis au périmètre historique.

Les installations métier gérées réservent le booking aux profils habilités
`book`. La compatibilité du mode autonome est conservée pour le Front et
l’administrateur technique local. Les profils secondaires n’acquièrent pas de
droit de structuration dans ce mode. L’admin central n’obtient aucun accès
supplémentaire aux installations métier ; le workspace technique autonome
conserve son périmètre historique.

## Correctifs et preuves par constat

| Constat | Correctif | Validation ciblée |
|---|---|---|
| M01-01 | Permission dédiée avant mutation ; refus persistés dans l’audit. | Matrice Front/Contrôle/Opérations/super utilisateur/admin technique ; aucune limite ni version modifiée après refus. |
| M01-02 | Permission de règlement, preuve idempotente et `settled_at`. | Refus Front/Contrôle, succès Opérations, rejeu sans nouvel instant ni double audit, preuve contradictoire refusée. |
| M01-03 | Dépendance réelle `get_current_pricer` sur toutes les voies alternatives identifiées. | Appels HTTP authentifiés aux huit entrées de calcul, refus secondaires, passage du Front jusqu’à la validation de contenu. MtM borné à un Deal lisible maintenu. |
| M01-04 | Route `/rfq/:rfqId/booking`, revue contractuelle et commande serveur ; preuve signée conservée sans retour de ses hypothèses au navigateur. | Calcul in-life réel sur historique déterministe, cotation ferme datée, revue Opérations, booking unique, refus si dossier modifié ou preuve absente. Aucun calcul libre donné aux Opérations. |
| M01-05 | Prédicats partagés, accès Product fondé sur le desk et l’action ; documents/notes/portefeuilles/études/alertes raccordés. | Création Front, reprise et modification par collègue, booking Opérations, lecture Contrôle ; révocation effective ; refus hors périmètre ; lecture individuelle des alertes. |
| M10-05 | Un seul prédicat de validation actuelle pour workspace et publication. | Révocation, expiration ou désactivation du validateur : indicateur faux et publication refusée ; historique gardé ; nouvelle validation autorisée possible. |
| M16-01 | Filtrage des transactions avant les projections CRM et des liens dans les opportunités. | Liens directs et projections client/personne/affiliation/analytics/signaux cohérents ; un collègue hors desk ne reçoit ni détail ni agrégat du Deal interdit. |

L’autorisation HTTP est exercée avec les vrais contrôles d’authentification,
des JWT et des fixtures comprenant organisations, utilisateurs et desks ; les
nouveaux tests activent les clés étrangères. Les dépendances de permission ne
sont pas remplacées par des stubs permissifs.

## Parcours Opérations et conservation de preuve

Le calcul RFQ conserve son reçu signé dans `rfq_booking_evidence`, après contrôle
des hypothèses et des termes courants. La revue transmet le contrat, la réponse
retenue, les dates et les références de preuve. Le prix modèle, les hypothèses
privées et la signature restent côté serveur.

Le booking relit les habilitations, verrouille le dossier, compare l’empreinte
de revue puis appelle le booking canonique. Les contrôles de prix, dates,
contrat, cotation, crédit et unicité restent actifs. Une preuve incompatible
ou périmée est refusée ; aucun recalcul silencieux ni réparation de calendrier
n’est ajouté. Le workflow nécessite un nouveau calcul conservé pour les RFQ
qui n’ont encore qu’un prix scalaire historique.

Le reçu in-life peut exprimer l’horizon par ses dates, sans champ `T` : sa
projection contractuelle sert à la comparaison. Le reçu signé reste inchangé.
Une contradiction entre horizon numérique et calendrier n’est pas tolérée.

## Migrations préparées

- `portfolios.entity_id` et `amc_studies.entity_id` figent le rattachement des
  anciennes collections lors de l’ajout des colonnes. Une exécution ultérieure
  ne les réattribue pas quand leur auteur change d’organisation.
- `trading_executions.settled_at` conserve l’instant réel des nouvelles
  déclarations. Une ancienne déclaration sans instant connu reste à `NULL`.
- Deux tables additives conservent la preuve RFQ et les lectures personnelles
  d’alertes. La suppression autorisée d’une RFQ et la purge UAT retirent sa
  nouvelle preuve ; les lectures d’alertes suivent la suppression de l’alerte.

La reprise initiale des portefeuilles et études utilise le rattachement de leur auteur connu au moment de la migration. Elle ne peut pas reconstruire une organisation historique absente des anciennes tables : les collections dont l’auteur a déjà changé d’organisation nécessitent une vérification de rattachement avant déploiement.

Ces migrations sont testées sur des bases temporaires. **Aucune migration ni
écriture n’a été exécutée sur une base métier du poste.** Le démarrage normal
d’une installation mise à jour appliquera ces évolutions additives.

## Validation et limites

Les résultats détaillés et empreintes sont dans
[C01_VALIDATION.json](remediation-lot-0-2026-10-20/C01_VALIDATION.json).

**Dernier passage backend : 113/113 tests réussis**, sur les cinq fichiers concernés par l’ajustement final des périmètres historiques. La campagne représente **213 cas distincts** dans onze fichiers ; les résultats antérieurs et les reprises sont distingués dans le JSON, sans addition de leurs totaux.

La campagne ciblée couvre onze fichiers backend. Les trois derniers échecs
étaient des assertions : deux attendaient à tort un historique de comparaison
privé pour les Opérations, alors que sa réponse doit rester vide ; une ancienne
assertion des options de login omettait les options du workspace technique déjà
présentes avant C01. Leur reprise ciblée est conservée séparément dans la preuve
de validation. Les totaux des passages ne s’additionnent pas.

Le build obligatoire est lancé depuis `frontend/` avec `npm run build -- --outDir`
vers un répertoire temporaire. Il comprend **57 fichiers et 444 tests frontend**
réussis. Les bundles préexistants de `frontend/dist` sont préservés.

Les limites suivantes restent explicites :

- Pas de suite backend complète, de serveur métier lancé, d’appel marché externe
  ou d’appel IA. Le test de calcul in-life utilise un historique déterministe.
- La vérification d’accès à la route MtM remplace seulement le calcul numérique
  de ce scénario ; elle ne requalifie pas les modèles quantitatifs.
- La route Vue est compilée et ses droits/bascules de contexte sont testés ;
  aucune recette graphique manuelle du nouveau formulaire n’est revendiquée.
- Pas de recette bilatérale complète sur deux installations physiques pour T12,
  ni de test de charge ou de campagne de concurrence multi-processus.

## Dépendances et suite

| Scénario / chantier | État à la sortie de C01 |
|---|---|
| T01 | Périmètre C01 validé localement : rôles, relais, confidentialité et révocation des desks/validateurs. Le travail propre aux sessions C02 reste ouvert. |
| T12 | Contrôles unitaires de publication et de confidentialité conservés ; recette bilatérale complète à faire avec C03/C06/C08/C23. |
| T14 | Confidentialité des projections validée ; attribution, as-of, devises et séparation des origines restent à traiter dans C24/C27. |
| C04 / C06 / C08 | Réutiliser les permissions et prédicats communs avant de modifier limites, versions et idempotence. |
| C05 / C14 / C18 | Préserver la concordance des termes, calendriers et reçus. Un prix scalaire ne remplace pas la preuve conservée. |
| C19 / C23 / C24 / C26 | Réutiliser l’accès au contrat pour archives, réseau, CRM et surveillance ; ne pas réintroduire de filtre personnel divergent. |

Les sept constats portent le statut **corrigé localement — tests ciblés validés**.
La clôture globale de C01 reste distincte de cette livraison : revue métier D05,
recette graphique et qualification des interfaces transverses restent visibles.
