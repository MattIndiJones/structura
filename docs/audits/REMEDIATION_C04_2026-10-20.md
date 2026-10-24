# Lot 1 — C04 : limites et amendements économiques

**20 octobre 2026 — implémentation et validation locales, sans commit ni push.**

Les trois constats C04 sont corrigés sur le périmètre ci-dessous. Le
[registre](remediation-lot-0-2026-10-20/REGISTER.json) conserve les dépendances et
les recettes transverses ouvertes. Les commandes, cas collectés, empreintes et
résultats figurent dans [C04_VALIDATION.json](remediation-lot-0-2026-10-20/C04_VALIDATION.json).

## Correctifs et résultats

| Constat | Résultat obtenu | Validation ciblée |
|---|---|---|
| M02-07 — concentration perdue au renommage | Agrégation et limite de suivi retrouvées par `counterparty_id`, indépendamment du nom figé dans les Deals. Le nom courant est affiché ; les noms historiques restent consultables. | Renommage puis désactivation : mêmes IDs, Deals, exposition de 1,6 M€, limite de 1,5 M€ et dépassement. |
| M11-02 — amendement de nominal hors limite | Contrôle serveur du portefeuille résultant à l’application, avant mutation contractuelle. L’ancienne position est remplacée et non ajoutée une seconde fois. | Sous limite de 1,5 M€, 1 M€ → 2 M€ est refusé sans mutation ; 1 M€ → 1,4 M€ passe avec preuve et version v2. Autres positions, politique courante, mesures et concurrence exercées. |
| M15-06 — alerte disparue au renommage | Même correction de concentration que M02-07 ; une banque inactive conserve l’exposition historique et sa limite de suivi. | Identité et alerte stables, nom historique conservé ; aucun élargissement implicite à une certification générale du CCR. |

## Contrôle des amendements

Les modifications de **nominal, contrepartie et date de paiement** passent par le
contrôle crédit à l’application. Le changement du prix traité ne modifie pas
l’exposition CCR clean ; l’attribution commerciale ne modifie pas le risque.
Les valeurs numériques d’amendement doivent être finies et strictement positives.
Ce contrôle partagé ne clôture pas les autres entrées numériques de C07/M11-06.

Le serveur acquiert le même verrou d’écriture que le booking et la configuration
des limites, relit le contrat, la politique et les positions, puis évalue une
copie de la position amendée. Le contrat courant n’est pas modifié pour simuler
le résultat. Le remplacement est un argument interne du moteur de contrôle,
absent du contrat de requête public. Le périmètre reste celui de l’organisation,
de la contrepartie et de Production ou du lot UAT concerné.

Le contrôle nominal peut réussir sans MtM lorsque la somme des nominaux suffit
à la politique configurée. Une limite fondée sur l’exposition courante utilise
une valorisation figée à la date et à la version du contrat ; les limites futures
utilisent le mode FULL existant. Aucune valeur de booking ne remplace un MtM
manquant. Une mesure absente bloque `HARD_BLOCK` et le circuit `REQUIRE_APPROVAL` ;
les politiques informatives et d’alerte conservent leur sémantique existante.
L’absence de limite reste affichée comme telle, sans devenir un avis de crédit.

Un changement de date de paiement ne peut pas réutiliser la mesure calculée
sur l’ancien horizon. Sous limite mesurée, il reste refusé tant que le nouveau
calendrier n’est pas qualifié : le parcours actuel demande alors une
annulation/remplacement contrôlée. C04 ne crée pas de nouvel écran de qualification
avant amendement. Un contrat déjà dénoué nécessite également une reprise contrôlée.

Un refus conserve le Deal, la révision Product, le nominal, la version contractuelle
et les snapshots ; la demande reste approuvée, sans preuve d’application, et le
refus est audité. Une application conserve `credit_check` dans la demande,
`amendment_credit_check` dans le snapshot de la nouvelle version et dans
l’exécution Product, ainsi que dans l’événement d’audit. La preuve contient la
politique datée et ses versions, les métriques, la décision, les empreintes du
calcul/configuration/moteur et la référence de valorisation du Deal. Elle ne
retourne pas les hypothèses de pricing privées des autres positions.

## Dépendances C01 et C03

En installation métier gérée, `operations.prepare` prépare les demandes et
permet les décisions en mode mono-signature. En mode quatre yeux,
`operations.validate` décide, avec un acteur distinct du demandeur. Les droits
de lecture du Deal et de son desk restent nécessaires aux actions et à la file
Contrôle. Opérations peut préparer un contrat partagé lisible ; Front et Contrôle
ne s’attribuent pas le droit de préparation. Le mode autonome conserve le parcours
propriétaire antérieur. La politique d’activation des quatre yeux n’est pas changée.

Les identifiants et snapshots C03 restent autoritaires. L’écran d’amendement
juridique choisit une contrepartie active par ID et retire le netting set de la
banque source. Un dossier D01 sans ID doit être qualifié avant un nouvel amendement
économique : l’attestation du booking n’est pas reconduite comme autorisation
permanente de modifier le risque. La régularisation juridique C03 reste exercée.

## Concentration et couverture

La limite historique `Counterparty.limit_eur` reste une **limite de suivi du
nominal EUR**, distincte des limites CCR bloquantes. C04 ne transforme pas cette
alerte de suivi en nouveau refus de booking.

Les dossiers sans ID, y compris les exceptions D01, restent visibles sans être
rattachés par homonymie. Le diagnostic fournit les dossiers à qualifier et leur
statut non évalué. Les IDs absents du catalogue sont également signalés. Les
positions sans FX restent signalées et les contrôles concernés sont incomplets ;
un dépassement déjà certain reste visible. HHI, nombre effectif et Top 3 ne sont
pas publiés comme complets lorsque l’identité ou les conversions manquent.
Les agrégats sont toujours filtrés selon les droits C01 avant restitution.

## Validation et limites de livraison

**164 tests backend ciblés réussis en 76,70 s**, dont **30 cas C04** : nominal,
renommage, données manquantes, exposition courante/PFE/CVA après qualification,
date de paiement, D01, droits HTTP, isolation UAT, migration et concurrence.
Deux amendements concurrents de 0,5 M€ à 0,9 M€, sous une capacité totale de
1,5 M€, donnent une application et un refus ; le nominal résultant reste 1,4 M€.
Les régressions couvrent C01/C03, les amendements, les portefeuilles, le CCR et sa
préparation/reprise de calculs. Deux anciennes fixtures CCR ont été alignées sur
les rôles C01 et l’ID juridique C03 ; aucun droit de production n’a été assoupli.

**475 tests frontend sur 63 fichiers** et build Vite réussis en **16,03 s**, dans
un dossier temporaire. Cinq nouveaux tests couvrent le formulaire gouverné,
les habilitations, le transfert juridique et le rendu des diagnostics de couverture.

La migration additive ajoute une preuve nullable aux demandes d’amendement ; elle
est idempotente et ne reconstruit aucune décision sur une ancienne demande. Les
tests utilisent exclusivement des données temporaires. La base métier réelle,
le `dist` existant, les preuves C01/C02/C03 et HEAD sont préservés. Aucune suite
backend complète, aucun service manuel ni campagne IA n’a été lancé.

| Suite du plan | Interface apportée par C04 | Travail restant |
|---|---|---|
| T05 / C21 | Décision sur portefeuille résultant ; données insuffisantes bloquantes et relecture des mesures natives | Qualification numérique générale PFE/CVA, dont grille et paiement proche ; les tests de circuit ne la remplacent pas. |
| C05 | Ancien horizon de paiement non réutilisé comme mesure du nouvel horizon | Conventions calendaires et éventuel parcours de qualification avant amendement. |
| C27 | Contrôle d’amendement isolé entre Production et lot UAT | Filtrage Production/UAT des agrégats historiques et autres consommateurs, inchangé ici. |
| C06/C23 | Versions et historique d’accords conservés | Reconfirmation externe et réconciliation bilatérale : un amendement local ne vaut pas nouvel accord de la banque. |

Les trois constats sont **validés localement** ; la recette graphique manuelle,
la recette transverse T05 complète et la qualification en production restent ouvertes.
