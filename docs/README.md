# Notes du projet Structura

[Corrections des trois défauts majeurs — 24/10](audits/INSTITUTIONAL_MAJOR_FIXES_2026-10-24.md)
— Booking OTC avec accord effectif, diffusion aux dates contractuelles et horloge
CCR métier ; 531 tests backend ciblés, 784 frontend, parcours UI isolés et rejeu CCR.

[Recette institutionnelle 100 M EUR — 24/10](audits/INSTITUTIONAL_ACCEPTANCE_2026-10-24.md)
— Douze achats RFQ et six banques fictives sur installations isolées ; preuves UI,
oracles indépendants et rapprochements. Booking OTC sans accord effectif,
observation hors grille et horloge CCR historique corrigés dans le suivi ci-dessus ; mandat autonome
non qualifié. Rapport local, limites et preuves d'arrêt dans le dossier d'audit.

Toutes les notes de travail du dépôt, rangées par nature. Chaque note garde son nom
d'origine : seul son dossier a changé, le 14/09/2026. **Revue documentaire du
05/10/2026**, sur `main`, commit `15d7ccf` : les points revérifiés et leurs preuves
figurent dans [la revue de reprise](audits/REVUE_DOCUMENTAIRE_2026-10-05.md).
Il s'agit d'une lecture du code et des tests, sans nouvelle exécution ni recette UI.
Les autres états restent ceux des notes datées ; « vérifié » sans date désigne
le contrôle historique du 14/09, pas une validation actuelle.

**Une nouvelle note va dans le dossier de sa nature et entre dans cet index.** Rien à la
racine du dépôt, à part `CLAUDE.md`.

[Correction des quatre défauts de la contre-revue livrée - édition consolidée](audits/REVIEW_FIXES_2026-10-24.md)

Rapport d'application et contre-revue actualisés après deux phases ; ZIP consolidé avec preuves existantes de 285 tests backend ciblés, 782 tests frontend et compilation, limites restantes et sources avant/après. Les 118 cas de première phase restent historiques, sans addition de couvertures. Actualisation documentaire sans relance des tests, commit ni push.

## Arborescence

Correctif récent : [pricing avant strike et reprise de session (07/10/2026)](audits/RECETTE_FORWARD_SESSION_2026-10-07.md).

Vérification complémentaire : [générateur UAT et scripts actuels (07/10/2026)](audits/AUDIT_GENERATEUR_UAT_2026-10-07.md).

```text
docs/
├── README.md        cet index
├── audits/          constats datés et journal de recette client
├── projects/        chantiers : conception, plan, rapport d'implémentation
│   ├── pricing/     PayScript, éditeur, modèles de produits, assistant IA
│   ├── lifecycle/   booking, fixings, MtM, notes de valorisation, déclinaisons
│   ├── clients/     module Clients, lots 0 à 3
│   ├── platform/    objet Product, accueil, déploiement, sources de données
│   └── studies/     études AMC, moteurs en feuille de route
├── reference/       documentation tenue à jour
├── lessons/         retours d'expérience et post-mortem
├── handoffs/        points de reprise de fin de session
└── archive/         documents périmés, conservés pour l'historique
```

Hors de `docs/` : `CLAUDE.md` (racine, lu à chaque session),
`.claude/agents/client-tester.md` (agent de recette, qui écrit dans
`audits/TESTING_JOURNAL.md`) et `demo-video/` (storyboard, rangé avec la vidéo).

**États.** *Fait* : livré. *En cours* : livré en partie. *À faire* : rien de codé.
*Clos* : tous les constats de l'audit sont traités ou arbitrés. *Suivi* : des constats
restent ouverts. *Dépassé* : repris par une note plus récente. *Référence* : tenu à jour.
*Historique* : à lire pour le contexte. *Archivé* : ne pas s'y fier.

## Ce qui reste à faire

[Archives KID, uploads et bootstrap legacy — confrontation et corrections — 24/10](audits/REVIEW_PROBABLE_FIXES_2026-10-24.md)
— Trois défauts de contrôle établis et corrigés : preuve serveur des archives KID,
budgets documentaires et retrait des comptes implicites. 170 cas backend distincts
réussis, 784 tests frontend et compilation ; limites et compatibilité explicites.
La suite backend complète n'est pas relancée ; le ZIP précédent n'est pas régénéré.

[Rapport complet de l'application pour revue indépendante — 24/10](audits/APPLICATION_REVIEW_2026-10-24.md)
— 44 chapitres : fonctions, modèles, calculs, données, RFQ, lifecycle, risque,
CRM, AMC/FIFO, documents, IA et exploitation. Inspection statique du checkout
local, limites explicites, 25 points prioritaires et 90 scénarios proposés ;
[annexes](audits/application-review-2026-10-24/ANNEXES.md), inventaires et extraits de source.
Aucun nouveau test métier, service ou accès à une base privée.

[Contre-revue indépendante du rapport d'application — 24/10](audits/CONTRE_REVUE_APPLICATION_2026-10-24.md)
— Application du prompt de contre-revue : 22 constats classés A–F, six établis en catégorie A, cinq
sondes sur le moteur seul. Points durs : VEV du KID hors expression RTS sous les bandes MRM
réglementaires, funding ni porté ni refusé en Mark-to-Future, `converged` du solveur général satisfait
par la largeur d'intervalle. Les quatorze fichiers concernés sont inchangés depuis le gel d'empreintes
du passage de 3 943 tests : le point aveugle de la suite est localisé. Aucune correction appliquée.

[Correction des quatre défauts de la contre-revue livrée — 24/10](audits/REVIEW_FIXES_2026-10-24.md)
— CR01–CR04 du rapport `output/structura-counter-review-2026-10-24/COUNTER_REVIEW_FR.md` :
contexte KID/MTF transmis ou refusé, convergence du solveur au paramètre publié,
levier EMT indépendant de la notation et créances KID après STOP. Tests ciblés et
limites explicites ; ces identifiants sont distincts de ceux de la contre-revue ci-dessus.

[Corrections de la seconde confrontation — 24/10](audits/REVIEW_FOLLOWUP_FIXES_2026-10-24.md)
— Refus des observations non futures, y compris calendriers figés ; message de
règlement contractuel, seed MTF fixe explicite et métriques CCR distinctes.
285 tests backend ciblés, 782 tests frontend et compilation réussis ; limites
et preuves conservées, sans suite backend complète, commit ni push.

[Changement de compte depuis Admin — 24/10](audits/ADMIN_ACCOUNT_SWITCH_2026-10-24.md)
— Sélecteur Admin actif, profil explicite, organisation démarrée à la demande,
retour après panne et session conservée ; tests et build, cas à froid obtenu à l’écran.
Le portail utilisateur déjà ouvert est préservé et doit être relancé pour charger le serveur modifié.

[Recette des accès du launcher — 24/10](audits/LAUNCHER_ACCESS_ACCEPTANCE_2026-10-24.md)
— Six organisations et 24 profils, console SaaS et deux chemins de simulation
vérifiés sur copies puis runtime permanent ; script de recette corrigé,
45 tests ciblés et 19 jalons navigateur. Aucune IA démarrée ; services arrêtés.

[Reprise du launcher et du workspace Admin — 24/10](audits/LAUNCHER_RECOVERY_2026-10-24.md)
— Ancienne identité Admin reprise explicitement avec sauvegarde et audit, sans
assouplir C02 ; démarrage natif et connexion vérifiés, limites dans les preuves.

[Rapprochement RFQ et reprise des bookings — 24/10](audits/RFQ_RECONCILIATION_2026-10-24.md)
— États réciproques datés, champs divergents explicites, inventaire habilité et
reprise bancaire après clôture d’un accord confirmé. Panne réelle, déclaration
négative et retour à la concordance exercés entre deux installations isolées.
Tests ciblés dédupliqués, build et limites dans les preuves ; pas de qualification déployée.

[Confirmation électronique RFQ — 24/10](audits/ELECTRONIC_RFQ_EXECUTION_2026-10-24.md)
— Intention et décision bancaire natives, reprises après arrêt de chaque destinataire,
preuves authentifiées conservées et un seul Deal par installation. Tests ciblés,
756 tests frontend et build, 15 jalons graphiques ; périmètre et limites de
qualification locale décrits dans les preuves. La recette précédente reste historique.

[Recette RFQ bilatérale — 24/10](audits/BILATERAL_RFQ_ACCEPTANCE_2026-10-24.md)
— Transport natif entre deux installations isolées, reprise sur indisponibilité,
deux révisions puis deux bookings concordants de 1 M EUR à 98,50 %. Quatre anomalies
d’interface corrigées ; 138 tests backend et 149 tests frontend ciblés distincts,
build et rapprochement réussis. Accord externe fictif consigné, sans confirmation
électronique d’exécution native ni qualification TLS ; services arrêtés.

[Recette graphique des parcours métier — 23/10](audits/GRAPHICAL_ACCEPTANCE_2026-10-23.md)
— Neuf anomalies corrigées et revérifiées sur installations isolées ; 151 tests backend
ciblés distincts, 737 tests frontend et build réussis. Parcours obtenus à l’écran,
preuves conservées et compléments de qualification explicités ; services arrêtés.


[Suite backend complète et correctifs F08-F21 — 23/10](audits/BACKEND_FULL_VALIDATION_2026-10-23.md)
— Premier passage : 59 cas en échec ou erreur, corrigés et suivis séparément
des 121 cas historiques. 817 succès ciblés distincts, puis **3 943 succès,
3 ignorés conditionnels inchangés, aucun échec ni erreur** au passage complet final.
Registre courant : 0 cas ouvert sur 180 documentés ; preuves antérieures
conservées, recette graphique et qualification déployée distinctes. Sans commit ni push.

[F01 — inscription publique : fixture et sécurité — 23/10](audits/REMEDIATION_F01_2026-10-23.md)
— Dernier échec historique résolu : fixture de mot de passe conforme, refus précis
et 21 tests ciblés distincts réussis, dont 14 nouveaux cas HTTP. Aucun changement
applicatif ni assouplissement C02.
[Solde après F01](audits/remediation-lot-0-2026-10-20/FAILURE_REGISTER.json) :
0 cas historique ouvert, 121 résolus localement sur preuves F01–F07 datées ;
recette transverse et qualification déployée distinctes. Sans commit ni push.

[F07 — relevés/lifecycle : fixture et contrôles d’accès — 23/10](audits/REMEDIATION_F07_2026-10-23.md)
— Échec du faux utilisateur sans rôle résolu ; dix dates sans doublon au strike,
droits réels et autorité du registre officiel vérifiés. 20 tests ciblés distincts
réussis ; aucun changement applicatif.
[Solde après F07](audits/remediation-lot-0-2026-10-20/FAILURE_REGISTER.json) :
1 cas ouvert (F01), non relancé ici. Sans commit ni push.

[F06 — chaîne CRM historique et booking canonique — 23/10](audits/REMEDIATION_F06_2026-10-23.md)
— Quatorze échecs résolus par des fixtures conformes et des assertions renforcées.
Chaîne RFQ-Deal sur un seul Product/version, droits réels, identité juridique et
reprise après refus vérifiés. 32 tests ciblés distincts réussis ; aucun changement applicatif.
[Solde après F06](audits/remediation-lot-0-2026-10-20/FAILURE_REGISTER.json) :
2 cas dans 2 groupes ouverts (F01/F07), non relancés ici. Sans commit ni push.

[F05 — analyses Product : fixture et permissions — 23/10](audits/REMEDIATION_F05_2026-10-23.md)
— Cinq refus 403 résolus par une identité JWT réelle et une base isolée. Aucun
changement applicatif ni élargissement des droits ; 58 tests ciblés distincts réussis,
dont 34 nouveaux contrôles des accès, sessions et aperçu/envoi/provenance.
[Solde après F05](audits/remediation-lot-0-2026-10-20/FAILURE_REGISTER.json) :
16 cas dans 3 groupes ouverts (F01/F06/F07), non relancés ici. Sans commit ni push.

[F03 — tests RFQ et intégrité des suppressions — 23/10](audits/REMEDIATION_F03_2026-10-23.md)
— 90 échecs reproduits puis couverts ; acteurs/desks et identités qualifiés, attentes
alignées sur C03/C08/C23. Suppression du last look sous clés étrangères et protection
des réponses des tours clos corrigées. 212 cas ciblés distincts réussis, dont trois
correspondances de tests renommés documentées ; aucun appel HTTP externe.
[Solde après F03](audits/remediation-lot-0-2026-10-20/FAILURE_REGISTER.json) :
21 cas dans 4 groupes ouverts, non relancés ici. Sans commit ni push.

[F04 — générateur UAT, fixings et calendrier figé — 23/10](audits/REMEDIATION_F04_2026-10-23.md)
— Neuf échecs initiaux résolus, flux fournisseur simulé dans les tests, rollback du
refresh, couverture explicite et suppression du déplacement de dates après booking.
55 cas ciblés distincts réussis (37 générateur + 18 voisins), nettoyage sous clés
étrangères et données natives préservées. [Solde après F04](audits/remediation-lot-0-2026-10-20/FAILURE_REGISTER.json) :
111 cas dans 5 groupes ouverts. Sans commit ni push.

[F02 — fixture de migration historique — 23/10](audits/REMEDIATION_F02_2026-10-23.md)
— Omission de `create_all()` dans le test, démarrage réel confirmé sur base isolée.
7 tests ciblés réussis ; données anciennes et protections Product conservées,
aucune migration applicative modifiée. Solde après F02 : 120 cas documentés dans 6 groupes ouverts. Référence de l’étape 1 conservée.
Sans commit ni push.

[Étape 1 — référence et registre consolidés — 23/10](audits/REFERENCE_CONSOLIDATION_2026-10-23.md)
— 27 livraisons locales rapprochées, dépendances actualisées et référence de travail
figée par empreintes. 190 XML dépouillés : 14 304 occurrences ramenées à 3 046
identités de cas ; 121 échecs historiques sans succès ultérieur conservé, en 7 groupes.
Dernière preuve frontend utilisée une seule fois : 731 succès. Travail documentaire,
sans modification de code, nouvelle exécution, commit ni push ; qualification déployée ouverte.

[Lot 1 — solde C27 : Production, UAT et historiques — 22/10](audits/REMEDIATION_C27_2026-10-22.md)
— Production par défaut, UAT explicite sur les agrégats, chocs/smile/P&L et leurs
historiques ; univers et vues figés, anciennes études non qualifiées consultables,
archives de portefeuilles supprimés préservées et réponses tardives ignorées.
65 tests backend ciblés (26 nouveaux), 731 tests frontend et build temporaire réussis.
C21/C24/C26 réexercés, import Demo conservé. Les 27 chantiers ont leur livraison
locale ; recettes transverses, graphique et qualification déployée restantes.
Sans commit ni push.

[Lot 3 — C26 : surveillance lifecycle et comptes rendus — 22/10](audits/REMEDIATION_C26_2026-10-22.md)
— Sous-jacents stables, minima/maxima sur clôtures indicatives, registre officiel
prioritaire ; bilans SUCCESS/PARTIAL/FAILED, couverture et reprises sans doublons.
101 cas backend distincts réussis (44 nouveaux), un échec antérieur de fixture
conservé ; 720 tests frontend et build temporaire réussis. C01/C11/C13 et T08 local
réexercés ; D07 conservée sans preuve implicite de paiement. Recette graphique et
qualification déployée restantes. Il reste le solde C27. Sans commit ni push.

[Lot 7 — C25 : économie du roll et récupération — 22/10](audits/REMEDIATION_C25_2026-10-22.md)
— Bid/hypothèse, décote et frais alimentent la quantité achetée ; récupération et
plafond démontré sont séparés. Anciennes études conservées et plafond historique
non qualifié à l’affichage. 182 cas backend ciblés (34 nouveaux), 712 tests frontend
et build temporaire réussis. C05/C18/C19 et reprise C07/C10 réexercés ; recette
graphique et qualification déployée restantes. Il reste C26 et le solde C27.
Convention commerciale D09 confirmée par Philippe le 22/10/2026.
Sans commit ni push.

[Lot 6 — C08 : idempotence des commandes et filiation — 22/10](audits/REMEDIATION_C08_2026-10-22.md)
— Trois constats traités localement : clés reprises après réponse perdue, booking
atomique et nouvelle opération dans un dossier dérivé explicite. 317 cas backend
ciblés, 697 tests frontend et build temporaire réussis. C01/C06, interfaces
C03/C04/C07/C10/C19/C20/C23 et nettoyage UAT réexercés ; qualification graphique et
déployée restante. Il reste C25, C26 et le solde C27. Sans commit ni push.

[Lot 7 — C24 : attribution CRM, analyses datées et devises — 22/10](audits/REMEDIATION_C24_2026-10-22.md)
— Trois constats et le prérequis CRM M16-05/C27 traités localement : rattachements
protégés, futurs exclus, états courants identifiés, montants par devise et Demo
hors profil réel. 342 cas backend qualifiés, 681 tests frontend et build réussis ;
14 échecs anciens de chaîne client reproduits à l’identique. C27 global et
qualification déployée restent ouverts. Sans commit ni push.

[Lot 6 — C23 : cotations, tours RFQ et exécutions réseau — 22/10](audits/REMEDIATION_C23_2026-10-22.md)
— Six constats traités localement : sélection liée à la révision, devise Product,
horaires fusionnés, clôture définitive et nouveau tour explicite, historique conservé,
moyenne quotidienne explicite. 271 cas backend (32 nouveaux), 674 tests frontend
et build temporaire réussis. Deux bases avec HTTP simulé ; C08 global, recette
graphique et qualification déployée restants. Sans commit ni push.

[Lot 5 — C22 : P&L cash et attribution — 22/10](audits/REMEDIATION_C22_2026-10-22.md)
— Deux constats traités localement : cash à échéance contractuelle, créances
conservées dans le roll et dividendes isolés de la volatilité. 161 cas backend
distincts, dont 22 nouveaux ; 662 tests frontend et build temporaire réussis.
PDF synthétiques inspectés, archives préservées. T08/T09 et production restent
partiels ; aucune preuve de virement bancaire déduite. Sans commit ni push.

[Lot 5 — C21 : couverture des risques, CVA et fraîcheur — 22/10](audits/REMEDIATION_C21_2026-10-22.md)
— Quatre constats traités localement : facteurs VaR manquants refusés, Greeks
indisponibles distincts de zéro, CVA des créances à paiements exacts et moniteur
invalidation par les fixings. 226 cas backend, 660 tests frontend et build temporaire
réussis. C27 partiel, domaines CCR bornés, recette transverse et production restantes.
Sans commit ni push.

[Lot 7 — C20 : recherche Optimizer et budgets — 22/10](audits/REMEDIATION_C20_2026-10-22.md)
— Quatre constats traités : 20 modes sauvegardés lançables, résolution dimensionnée,
contrôle économique après arrondi, dépassements partiels explicites et messages de conservation cohérents.
Interaction Phoenix/C14 corrigée ; 219 cas backend et 28 tests frontend réussis, build temporaire validé.
Budget séquentiel souple, recette graphique et production restantes. Sans commit ni push.


[Lot 5 — C19 : archives, rejeu et documents figés — 21/10](audits/REMEDIATION_C19_2026-10-21.md)
— Neuf constats traités localement : identités de calcul, preuves SQL, historique RFQ daté,
calendriers de rejeu, créances, PDF et études conservés. D10/D11 confirmées.
444 cas backend et 55 tests frontend réussis ; 104 échecs antérieurs reproduits.
Compilation temporaire validée ; recette graphique et production restantes. Sans commit ni push.


[Lot 5 — C18 : contexte commun de valorisation et sémantique — 21/10](audits/REMEDIATION_C18_2026-10-21.md)
— Sept constats corrigés localement : prix et analyses alignés, Greeks explicites,
statistiques correctement nommées, sources effectives, créances réactualisées et
scan raccordé au modèle/funding du booking. 479 cas backend et 652 tests frontend
réussis ; compilation temporaire validée. Domaines C15–C17 préservés ; scénarios
transverses dépendants et recette graphique/production restants. Sans commit ni push.

[Lot 4 — C17 : surfaces, calibration et diagnostics — 21/10](audits/REMEDIATION_C17_2026-10-21.md)
— Cinq constats corrigés localement : piliers matériels, refus du Local Vol legacy
invalide, qualification distincte de la convergence, Fourier Heston adaptatif et
dossier signé conservé avec le prix. Seuils confirmés : 5 pb vanilles, 10 pb digitales.
323 cas backend et 643 tests frontend réussis ; compilation temporaire validée.
Qualification des contextes élargis C18 et recette graphique/production restantes.
Sans commit ni push.

[Lot 4 — C16 : dépendance des extrema et barrières — 21/10](audits/REMEDIATION_C16_2026-10-21.md)
— Copies équivalentes cohérentes avec le mono ; approximation panier corrélée
et domaine d'admission explicites. Seuil de qualification de 10 pb confirmé ;
319 cas backend ciblés et 7 tests frontend réussis, plus deux panels quantitatifs.
T07 partiel, extension de D04 et raccordement C18 ouverts. Sans commit ni push.

[Lot 4 — C15 : taux stochastiques, funding et corrélations — 21/10](audits/REMEDIATION_C15_2026-10-21.md)
— Trois constats corrigés localement : funding en actualisation seule, variance
mono préservée et limite Hull-White stable. 231 cas backend ciblés réussis,
dont 105 cas C15 ; références nominales conservées. T06 partiel, C18 et
qualification D04 ouverts. Sans commit ni push.

[Lot 4 — C14 : axe temporel et ordre des événements — 21/10](audits/REMEDIATION_C14_2026-10-21.md)
— Trois constats corrigés localement : chronologie par date, axe partagé entre
prix et analyses, retrait du plancher hebdomadaire du résiduel. 241 cas backend
ciblés et 18 tests frontend réussis. T03 validé localement ; T09 partiel et
qualification de production restante. Sans commit ni push.

[Lot 3 — C13 : finalité des cours et registre officiel — 21/10](audits/REMEDIATION_C13_2026-10-21.md)
— Cinq constats traités localement : clôture disponible sans délai ajouté après
séance, autorité du registre, décision atomique et passé du MtM cohérent avec les
versions officielles. 232 cas backend ciblés et 22 tests frontend réussis.
T08 partiel, un défaut préexistant de migration isolé ; recette de production ouverte.
Sans commit ni push.

[Lot 3 — C12 : stockage atomique des séries et caches — 21/10](audits/REMEDIATION_C12_2026-10-21.md)
— Deux constats traités localement : imports stricts et conventions explicites,
publication groupée, reprise après panne et caches indépendants. 160 tests backend
ciblés, 637 tests frontend et build réussis. T04 combiné validé localement ;
C11 conservé à 3 jours, recette graphique/production restante. Sans commit ni push.

[Lot 3 — C11 : données de marché datées et couverture — 21/10](audits/REMEDIATION_C11_2026-10-21.md)
— Sept constats traités et validés localement : références/surcharges conservées,
historiques et FX avec couverture explicite, stock local partagé, estimateur commun.
D03/C11 confirmé : reports de 3 jours calendaires maximum, borne incluse.
235 cas backend ciblés, 631 tests frontend et build réussis. Finalité prolongée
par C13 ci-dessus ; recettes transverses et qualification production ouvertes.
Sans commit ni push.

[Lot 2 — C10 : réponses tardives et erreurs dans les interfaces — 21/10](audits/REMEDIATION_C10_2026-10-21.md)
— Huit constats traités localement : réponses liées au contexte, erreurs RFQ restituées,
preuves d’exécution cloisonnées et acquittements confirmés. 69 nouveaux tests frontend,
615 tests frontend et build réussis ; 37 tests backend ciblés. T11/C17 et recette
graphique/production restent ouverts ; sans commit ni push.

[Lot 2 — C09 : compilation PayScript et qualification du payoff — 21/10](audits/REMEDIATION_C09_2026-10-21.md)
— Trois constats traités localement : indentation refusée, contrôles structurels explicites,
qualification du script par empreinte et 552 trajectoires de référence. 845 cas backend
distincts validés, un cas ignoré, 546 tests frontend et build réussis. T03/C14, T15/C19/C20
et recette graphique/production restent ouverts ; sans commit ni push.

[Lot 2 — C07 : conservation et reprise des saisies — 21/10](audits/REMEDIATION_C07_2026-10-21.md)
— Douze constats traités localement : brouillons partiels, configurations atomiques,
versions explicites, précision et reprise du funding. 303 cas backend distincts,
541 tests frontend et build réussis. Budget de volumétrie M04-10, T11/T15 et recette
graphique/production restants ; sans commit ni push.

[Lot 2 — C06 : versions Product et intégrité des transitions — 20/10](audits/REMEDIATION_C06_2026-10-20.md)
— Cinq constats traités localement : RFQ historique sans rétrogradation, contexte
conservé, dossier booké protégé, références Product/version et pricing cloisonné.
307 cas backend distincts, 494 tests frontend et build réussis ; C01 à C05 préservés.
Reprise historique et recettes T02/T12/T13 complètes restantes ; sans commit ni push.

[Lot 2 — C05 : calendriers contractuels et règlement — 20/10](audits/REMEDIATION_C05_2026-10-20.md)
— Huit constats traités localement ; D02 confirmée : combinaison choisie par produit,
stubs longs systématiques et conservation des dates figées. 454 cas backend ciblés
validés après alignement de quatre fixtures C03, 491 tests frontend et build réussis.
Recettes T03/T04/T16 complètes et qualification graphique/production restantes ; sans commit ni push.

[Lot 1 — C04 : limites et amendements économiques — 20/10](audits/REMEDIATION_C04_2026-10-20.md)
— Trois constats traités localement : concentration par ID, contrôle du portefeuille
après amendement et décision liée à la nouvelle version. 164 tests backend ciblés,
475 tests frontend et build réussis. T05 complet, recette graphique et qualification
numérique C21 encore ouverts ; sans commit ni push.

[Lot 1 — C03 : identifiants juridiques et référentiels — 20/10](audits/REMEDIATION_C03_2026-10-20.md)
— Neuf constats traités localement : identités figées, booking par ID actif ou
exception administrateur D01 explicite, motivée et auditée,
amendement juridique cohérent et référentiels gouvernés. Tests ciblés et build Vue ;
D01 confirmée par Philippe ; recette graphique et scénarios transverses encore ouverts.

[Lot 1 — C02 : sessions, portail et identité — 20/10](audits/REMEDIATION_C02_2026-10-20.md)
— Sept constats traités localement ; révocation, mots de passe, portail normal,
nom canonique verrouillé et contrôles avant migration. Tests ciblés et build Vue ;
recette graphique/transverse et reprise explicite des anciens workspaces Admin restantes.

[Lot 1 — C01 : permissions et confidentialité — 20/10](audits/REMEDIATION_C01_2026-10-20.md)
— Sept constats corrigés localement ; tests ciblés et build Vue. Revue D05 et recettes graphique/transverse restantes ; sans commit ni push.

[Lot 0 de remédiation des modules 1 à 17 — 20/10](audits/REMEDIATION_LOT_0_2026-10-20.md)
— Registre de 132 constats d'audit, 27 chantiers, dépendances et critères de validation.
Préparation documentaire livrée ; aucune correction du code ni mutation de données métier.

[Recette déterministe sans IA — 15/10](audits/RECETTE_DETERMINISTE_SANS_IA_2026-10-15.md)
— Pilote isolé de trois payoffs : trois RFQ, neuf cotations, douze jambes
rapprochées, refus juridique et limite de notionnel attendus, zéro appel IA.
Reste à exercer un panier multi-sous-jacents et les gestes utilisateur dans les écrans.

[Reprise de la campagne multi-produits — 15/10](audits/CAMPAIGN_MULTI_PRODUCT_RESUME_2026-10-15.md)
— Reprise contrôlée au dossier SG après deux réponses OpenAI non décodables ; six deals
sur six rapprochés au deuxième mois, suivi historique encore en cours. Les sorties
invalides futures sont conservées dans le dossier privé de campagne ; le bilan
de cinq ans et les contrôles visuels restent à faire.

[Préparation du rejeu historique et recette courte — 14/10](audits/CAMPAIGN_HISTORICAL_PREPARATION_2026-10-14.md)
— Historiques locaux et dernier cours connu, cutoff strict 2021–2026, décisions
IA enregistrées sans retries automatiques, calendriers et cash du rappel à J+3.
Recette isolée : trois RFQ, neuf cotations, douze bookings, zéro appel IA ; services
fermés. Brouillon historique enregistré depuis Simulation, non démarré.
CCR OTC, Valo Explain entre deux valorisations et qualification humaine restent
à exercer ; les 46 tests ciblés ne certifient pas la campagne complète.

[Bilan de la campagne de cinq ans — 14/10](audits/CAMPAIGN_DIAGNOSTIC_5Y_BILAN_2026-10-14.md)
— Terminaison technique sur marché synthétique, 4 RFQ, 16 bookings, 120 MtM,
48 appels IA ; les six installations sont fermées. Le rejeu historique attendu
2021–2026 n'est pas validé. Date/source de marché, preuves visuelles, limites de
couverture et règlement après rappel à reprendre avant une nouvelle campagne.

[Campagne courte RFQ jusqu'à maturité — 14/10](audits/CAMPAIGN_LIFECYCLE_SHORT_2026-10-14.md)
— Une reverse convertible, cinq cotations, quatre bookings rapprochés,
52 MtM natifs, fixings finaux appliqués et quatre deals `échu` après paiement
contractuel. 67 appels IA, coût estimé 0,0210054 $. Campagne `COMPLETED` après
reprise, mais cinq erreurs de format de décision, AR produit non exercée et
absence de preuve externe du virement final ; qualification globale non acquise.

[Pilotes OpenAI RFQ natif — 14/10](audits/CAMPAIGN_OPENAI_PILOT_2026-10-14.md)
— GPT-6 Luna : après correction des sollicitations inutiles et du schéma des
arguments, 19 appels contre 69, coût estimé 0,0063816 $ contre 0,0179933 $ ;
cinq cotations et quatre bookings rapprochés sur une RFQ, sans erreur de format.
Campagne longue, paiements et autres payoffs encore à qualifier. Services arrêtés.

[Choix Ollama/OpenAI et plafond IA dans les campagnes — 14/10](projects/platform/AGENT_WORKSHOP_NATIVE_RFQ_2026-10-13.md#choix-du-modèle-et-plafond-de-campagne--14102026)
— sélection du modèle dans l'atelier admin, réutilisation de la clé existante,
compteur de jetons/coût estimé et arrêt au plafond local ; jusqu'à 60 mois
commerciaux et 60 mois de durée contractuelle, sur les deux payoffs RFQ natifs.
Contrôles ciblés et appel API minimal réussis ; campagne complète OpenAI à qualifier.

[Campagnes agents — consignes hybrides et parcours RFQ natif, 13/10](projects/platform/AGENT_WORKSHOP_NATIVE_RFQ_2026-10-13.md)
— Kepler demandeur, BNP/SG/Citi/UBS/Leonteq répondants ; catalogue réutilisé,
réception et publication natives, Contrôleur distinct, confirmation avant booking
et suivi jusqu'au dernier paiement. Qualification dirigée réussie : cinq cotations,
quatre jambes rapprochées et rejeux sans doublon.
[Campagne complète lancée](audits/CAMPAIGN_NATIVE_RFQ_FULL_2026-10-13.md)
le 13/10 à 18:23:50 UTC, résultats annuels en cours.
Registre central et facturation non livrés par cette campagne.

[Vérification des corrections — pilote court du 13/10](audits/CAMPAIGN_CORRECTIONS_PILOT_2026-10-13.md)
— Blocage avant connexion : conflit entre l'attente IA annulable et Playwright,
corrigé après arrêt et vérifié par un diagnostic ponctuel. Création RFQ et rejeu
restent non exercés. Arrêt du pilote en 5,719 s ; tous les processus de recette
fermés, preuves conservées. Nouvelle campagne de qualification à reprendre.

[Campagne réelle de diagnostic — pilote du 13/10](audits/CAMPAIGN_PILOT_2026-10-13.md)
— 39 tours et 45 appels IA en 12 min 21 s. Création RFQ bloquée par l'absence
de desks et de `pilot_desk_id` ; aucun booking. Correctifs du bootstrap, du rejeu,
de la connexion, de la provenance IA et de l'arrêt implémentés ensuite,
sans nouvelle campagne : qualification en exécution à reprendre.
Sept services de recette arrêtés, preuves conservées ; année complète non lancée.

[Navigation RFQ — demandes et réception, 13/10](projects/platform/RFQ_NAVIGATION_2026-10-13.md)
— Entrée directe « RFQ reçues » dans le menu RFQ, au même niveau que les demandes
aux fournisseurs ; écran et droits existants réutilisés. Compilation seule, tests suspendus.

[Lanceur Python et Structura Admin complet — 13/10](projects/platform/STRUCTURA_LAUNCHER_2026-10-13.md)
— Double-clic et `backend/run.py` sans arguments ouvrent un menu ; accès Admin complet,
administration et simulation dans un workspace séparé des six organisations.
Lanceur modernisé avec aides « ? » ; arrêt en parallèle limité aux espaces ouverts
depuis cette fenêtre, vérifications de ports bornées et durée réelle affichée.
Console SaaS distincte. Compilation seule après le dernier correctif, tests suspendus
à la demande de Philippe ; recette de ce parcours différée. Étape 5 partielle, étapes 6 à 8 ouvertes.

[SaaS hybride — remise à zéro et accès commun, 13/10](projects/platform/HYBRID_SAAS_ACCESS_2026-10-13.md)
— Étapes 3 et 4 livrées : retrait ciblé des anciens jeux fictifs, login à sept cartes,
sélecteur organisation/profil, sessions par onglet, accès développeur explicites
et audités. Recettes backend/frontend et navigateur réalisées ; services arrêtés.
Partage, parcours Opérations complet, simulation centrale, RFQ entre les six bases
et registre restent à réaliser. Facturation désactivée.

[Socle SaaS hybride — étapes 1 et 2, 13/10](projects/platform/HYBRID_SAAS_FOUNDATION_2026-10-13.md)
— Six installations privées et service central d'annuaire, 24 comptes métier et
un admin central, bootstrap idempotent, droits et signatures par installation.
Recette locale sur sept serveurs réussie ; runtime permanent initialisé, arrêté.
Nettoyage et login commun repris par la livraison ci-dessus ; supervision/partage,
configuration RFQ des six bases et registre central restent à réaliser. Aucun tarif ni débit activé.

[Reprise SaaS hybride et prompt pour un nouveau chat — 13/10](handoffs/HYBRID_SAAS_HANDOFF_2026-10-13.md)
— Décisions retenues : données et traitements privés chez le client, six installations
isolées, super utilisateurs, profils secondaires, accès rapides, supervision et
simulation réservée à l'admin. Registre RFQ central pour facturation et litiges,
avec contenu des échanges, droits, reprise et comptage sans doublons ; unité tarifaire
proposée à valider. Plan en huit étapes, remise à zéro des données fictives sans
migration et prompt prêt à copier. Cadrage repris par la livraison des étapes 1 et 2 ci-dessus ;
compilation commerciale et calcul confidentiel différés.

[Atlas de l'application et des comptes — 13/10](projects/platform/STRUCTURA_APPLICATION_OVERVIEW_2026-10-13.md)
— [Présentation HTML globale](projects/platform/application-map-2026-10-13/index.html),
inventaire exact des 10 comptes principaux, 3 organisations, droits RFQ et
53 bases secondaires ; 24 fiches de module, interactions, preuves datées,
ajustements et plan de reprise. Lecture de base/code uniquement, sans modification
de l'application ni nouvelles suites de tests. Distingue les lots livrés dans le
code de leur activation/configuration dans la base principale.

[Réseau RFQ entre organisations — plan de réalisation du 12/10](projects/platform/RFQ_NETWORK_ACTION_PLAN_2026-10-12.md)
et [spécification complète du lot 0](projects/platform/RFQ_NETWORK_LOT_0_SPECIFICATION_2026-10-12.md)
— Cadrage fonctionnel consolidé : destinataires propres à l'organisation,
réception bancaire, pricing privé, publication humaine avec seconde validation
configurable, retour automatique et maintien du manuel. Fermeté révocable avant
acceptation valide, confirmation bancaire ou téléphone déclaré et validité à
l'accord intégrés. Le [lot 1](projects/platform/RFQ_NETWORK_LOT_1_SPECIFICATION_2026-10-12.md)
est détaillé : nouveaux dossiers appartenant à l'organisation, visibilité au
desk pilote et partage explicite. Aucune migration des anciens tests n'est
demandée. Le [premier incrément du lot 1](projects/platform/RFQ_NETWORK_LOT_1_IMPLEMENTATION_2026-10-12.md)
ajoute la propriété organisationnelle, les habilitations de desk et le partage
révocable des nouvelles RFQ. Le [lot 2 livré](projects/platform/RFQ_NETWORK_LOT_2_IMPLEMENTATION_2026-10-12.md)
ajoute relations bilatérales reconnues, périmètres, suspension et destinataires
autorisés dans la préparation. Affectation et transfert du lot 1 sont codés et
recettés sur base fictive ; exports et tâches longues restent à qualifier.
Le [lot 3](projects/platform/RFQ_NETWORK_LOT_3_IMPLEMENTATION_2026-10-12.md)
ajoute envoi explicite dans la même installation, termes Product figés par tour,
suivi individuel livré/lu et boîte bancaire par desk. Nouveau tour dans un dossier
lié, manuel conservé. Recette HTTP authentifiée réussie ; recette visuelle bloquée
par l’outil. Le pricing/publication bancaire et le transport entre installations
restent les lots suivants.
La [tranche bancaire du lot 4](projects/platform/RFQ_NETWORK_LOT_4_IMPLEMENTATION_2026-10-12.md)
ajoute prise en charge et réaffectation au sein du desk, Product bancaire aux termes
reçus verrouillés, ouverture dans le Pricer existant et calculs privés conservés.
La recette HTTP authentifiée passe ; la recette visuelle reste bloquée par l’outil.
Précisions/déclin restent à compléter ; la publication humaine est ajoutée au lot 5.
Le [lot 5](projects/platform/RFQ_NETWORK_LOT_5_IMPLEMENTATION_2026-10-12.md)
ajoute prix commercial, validation exacte, seconde validation configurable par desk,
publication et réception automatiques dans la même installation, révisions et retrait
tracés. Les quotes réseau sont non éditables et coexistent avec le manuel ; leur
booking attend la confirmation du lot 7. Recette API et build réussis, recette visuelle
bloquée par l’outil.
Le [lot 6](projects/platform/RFQ_NETWORK_LOT_6_IMPLEMENTATION_2026-10-12.md)
ajoute l’appairage des installations, des échanges HTTPS signés, files persistantes,
accusés liés au contenu, reprise après interruption, dédoublonnage et ordre des
révisions. Demandes, lectures, prix, retraits et clôtures ont un suivi de livraison.
Recette sur deux vrais serveurs fictifs avec arrêt/redémarrage et contrôle visuel
réussis ; scroll interne des masques confirmé. Manuel conservé ; confirmation
avant booking complétée par le lot 7 ci-dessous, déploiement réel et pilote encore à qualifier.
Le [lot 7](projects/platform/RFQ_NETWORK_LOT_7_IMPLEMENTATION_2026-10-12.md)
ajoute demande externe déclarée, confirmation identifiée avant booking réseau,
accord Product figé, conservation des refus et booking local unique par exécution.
Le manuel et les masques à défilement interne sont conservés. Les messages natifs
de traitement, le rapprochement des réponses et la résolution des contestations
restent des compléments. 19 scénarios backend ciblés réussis, build frontend réussi
et masque de confirmation vérifié sur base fictive ; page fixe et scroll interne confirmés.
Le [lot 8 — recette clôturée le 13/10](projects/platform/RFQ_NETWORK_LOT_8_ACCEPTANCE_2026-10-13.md)
qualifie la tranche V1 sur trois installations fictives : 16 scénarios API,
booking unique, deux banques et manuel, droits, reprise, retrait et suspension.
Scroll interne mesuré à 1 280 × 720 et 760 × 600 ; deux corrections et 19 tests
ciblés réussis. La [procédure d'exploitation et de reprise](projects/platform/RFQ_NETWORK_OPERATIONS_2026-10-12.md)
et le script de recette sont livrés. La vraie BNP exige encore une installation
compatible, les accords, les accès HTTPS et l'appairage bilatéral.
Le [lot 0 implémenté](projects/platform/RFQ_NETWORK_LOT_0_IMPLEMENTATION_2026-10-12.md)
est livré sur `codex/rfq-network-lot-0` : prototype demandeur/banque et préparation
intégrée aux RFQ existantes depuis Product, calcul privé par les moteurs actuels
et reprise dans le Pricer. Écrans et modales à défilement interne, hauteur bornée.
154 tests backend ciblés, 424 tests frontend et build réussis ; recette bureau,
mobile et écran bas sur base temporaire. L’envoi et la réception minimale sont
désormais ajoutés au lot 3 ; la publication et le transport restent à réaliser.

[Simulation entre agents — tests restants et futur échange RFQ (12/10)](projects/platform/AGENT_SIMULATION_TESTS_RESTANTS_2026-10-12.md)
— Recette priorisée : cycle jusqu'au paiement, AR produit, discours, audit,
durée, consultation et année complète. Matrice dédiée à l'échange automatique
de prix RFQ, prévu dans une autre branche et un autre chat.

[Consultation des installations BNP/Hector après arrêt (12/10)](projects/platform/AGENT_SIMULATION_CONSULTATION_2026-10-12.md)
— Boutons d'ouverture et de fermeture des books natifs conservés, connexion
automatique, calendrier figé et lecture seule SQLite/API, sans relance des IA.

[Bilan de l'essai réel arrêté le 12/10](projects/platform/AGENT_SIMULATION_BILAN_2026-10-12.md)
— Cinq dossiers, 50 M€, vingt écritures réglées et 105 MtM natifs ; limites,
durées et priorités de reprise. La campagne annuelle n'est pas qualifiée.

[Simulation entre agents — pilotage du 12/10](projects/platform/AGENT_SIMULATION_PILOT_2026-10-12.md)
— Première consolidation locale : avancement permanent, reprise vierge conservant
l’ancien essai, suppression sauvegardée, historique intégral paginé, diagnostics
persistants, books lisibles et rapprochement durci. 47 tests backend ciblés,
379 tests frontend et build, deux recettes UI isolées et parcours natif Phoenix
jusqu’à échéance. Horloge événementielle, diversité des acteurs, flux financiers
et rejeu déterministe restent à développer ; détail et limites dans la note.

Simulation de recette : [livraison multi-Structura du 09/10](projects/platform/MULTI_STRUCTURA_AGENT_IMPLEMENTATION_2026-10-09.md)
— **Implémentée localement** : utilisateurs IA de leurs installations distinctes,
inscription UI, contrats, CRM, pricing natif, conversations, quatre books,
suivi de vie, Achille, horloge suspendue et preuves. Configurations contractuelles
choisies ou tirées au sort. Accès depuis l'accueil avec un compte utilisateur,
campagnes privées à leur propriétaire. Recettes natives RC/Phoenix et émission
Hector par UI réussies ; année autonome terminée en 57 min, 120 M€, 12 opérations
et 48 écritures rapprochées, sans reprise humaine ni échec technique. Références
consultables par Philippe ; preuves et limites détaillées dans le rapport. Le
suivi visuel a été repris le 09/10 au matin : activité courante publiée avant
exécution, parcours métier, preuves écrans/API, états synchronisés et contrôleur
actif vérifié. 24 tests workshop, 366 tests frontend et recette UI ; courte
qualification avec vrais comptes IA et contrats natifs, installations fermées. Le
registre des problèmes et les aides « ? » ont ensuite été ajoutés : accès direct
aux signalements, catégories lisibles, action liée et export texte ; 372 tests
frontend et recette navigateur. Un signalement n'est pas un bug confirmé. Le
nettoyage des essais est aussi disponible : réinitialiser la vue et les champs,
recommencer une campagne aux mêmes paramètres avec des installations vierges,
ou la retirer de la liste avec sauvegarde locale. Opérations réservées aux
campagnes sans contrôleur actif ; 36 tests backend ciblés et recette UI contre
les vraies routes avec données temporaires. Le
[flux RFQ natif entre entités](projects/platform/RFQ_NETWORK_ACTION_PLAN_2026-10-12.md)
est cadré au 12/10, sans implémentation du réseau. Défauts, appels de marge, réinvestissement et couverture exhaustive
restent non exercés. Le [plan multi-Structura](projects/platform/MULTI_STRUCTURA_AGENT_ACTION_PLAN_2026-10-08.md)
conserve le cadrage ; le premier laboratoire a été retiré.

**URGENT — smile actions et ailes basses** : [diagnostic et méthode de reprise
du 08/10](projects/pricing/SMILE_ACTIONS_URGENT_2026-10-08.md). Profils synthétiques
trop modérés pour les exemples de desk décrits, matrice contrainte par une forme
commune et strike 50 % absent. Reprendre matrice cible, représentation, digitaux
et effets de rappel avant de généraliser les comparatifs. Développement différé
par Philippe ; priorité immédiate à l'Optimizer en calcul direct parallèle.

PayScript : [implémentation Basket / StartDate du 06/10](projects/pricing/PAYSCRIPT_STARTDATE_IMPLEMENTATION_2026-10-06.md)
— **Implémenté sur `codex/payscript-basket-startdate`** : 19 modèles génériques,
panier Economics, fixing initial explicite, paramètres requis en %, première
observation incluse et flux séparés. L’[éditeur unique et ses 15 exemples préremplis](projects/pricing/PAYSCRIPT_PRESETS_EDITOR_2026-10-07.md)
sont livrés le 07/10 : réglages avancés locaux, exemples facultatifs dans le
Pricer et la RFQ, panier et hypothèses de marché conservés. Pricer, RFQ, Product et
consommateurs de calendriers adaptés ; tests ciblés et recette navigateur réalisés.
Les 42 deals de test, 41 RFQ et leurs dossiers associés ont été supprimés après
sauvegarde. Les référentiels sont conservés. Le rapport précise la couverture
effective, les limites et la procédure de reprise ; aucune suite backend complète.
La [recette complémentaire du 06/10](audits/RECETTE_PAYSCRIPT_2026-10-06.md)
valide 514 cas backend distincts, 233 tests frontend et un parcours navigateur
jusqu’au booking isolé. Trois anomalies corrigées : erreurs de paramètres requis,
ancre de fenêtre sur jour fermé et conservation des termes lors des changements
de type/conversions RFQ. Base réelle inchangée pendant cette recette.
Retour utilisateur traité ensuite : StartDate manquante signalée avant calcul,
erreurs API lisibles et cours en devise clarifiés ; 243 tests frontend passent
avec les dix cas complémentaires, décrits dans le même rapport.
Le [cadrage](projects/pricing/PAYSCRIPT_STARTDATE_UNDERLYING_DESIGN_2026-10-06.md)
et la [revue transversale](audits/AUDIT_TRANSVERSAL_PAYSCRIPT_2026-10-06.md)
restent des photographies de l'état antérieur à cette implémentation.

Product Optimizer : [V1 — architecture, capacités et recette](PRODUCT_OPTIMIZER_V1.md)
— **Implémenté localement le 05/10** : Athena mono-actif / worst-of sous GBM,
résolution du coupon, contraintes avec IC95, classement, comparaison et Pareto.
Hypothèses explicites ; convergence temporelle précise, marché qualifié et extensions restent à faire.
Priorités confirmées le 08/10 : validation quantitative, enrichissement du marché
et extension des payoffs. Conservation/exploitation des recherches dans un second
temps ; Copilot après l'Optimizer.
Calcul direct parallèle livré le 08/10 : 1 à 4 candidats simultanés (défaut 2),
budget CPU/mémoire, annulation et équivalence séquentielle vérifiés. 48 tests
Optimizer, 5 tests de l'exécuteur et build avec 287 tests frontend réussis.
Benchmark synthétique de quatre Athena : 26,3 s → 15,4 s avec deux processus.
[Validation quantitative indépendante du 08/10](projects/pricing/PRODUCT_OPTIMIZER_QUANT_VALIDATION_2026-10-08.md)
livrée ensuite : cinq candidats au maximum, coupons conservés, nouveaux tirages
N/2N, métriques par paire, correction de sélection et diagnostic du classement.
65 tests backend ciblés distincts et 288 tests frontend réussis. Référence GBM
aux dates contractuelles sur trois scénarios, 60 contrôles compatibles ;
convergence temporelle à quelques bps encore à qualifier. Benchmark complet
avec validation : 31,4 s → 17,9 s, résultats identiques et classement signalé
incertain lorsque les intervalles se recouvrent.
[Marché et économie d’émission du 08/10](projects/pricing/PRODUCT_OPTIMIZER_MARKET_ECONOMICS_2026-10-08.md)
livrés ensuite : copie explicite de la session Pricer GBM, snapshot tracé par
champ, courbes de taux/dividendes, funding en actualisation et budget payoff net
de frais/marge. 95 tests backend ciblés distincts et build avec 299 tests frontend
réussis ; équivalence des processus avec courbes et coûts vérifiée. Les sources
restent des hypothèses, sans certification de marché ; prochaine extension Phoenix.
[Payoffs et champs dynamiques du 08/10](projects/pricing/PRODUCT_OPTIMIZER_PAYOFFS_2026-10-08.md)
livrés ensuite : Phoenix, mémoire, Athena dégressif et reverse convertible européenne.
Champs issus des paramètres du script sélectionné, refus des champs inapplicables,
coupons Phoenix à plusieurs dates et mémoire qualifiés, séries de rappel explicites.
142 tests backend ciblés distincts et build avec 305 tests frontend réussis.
[Participation, cap et gear put du 08/10](projects/pricing/PRODUCT_OPTIMIZER_PARTICIPATION_GEAR_2026-10-08.md)
complète les huit familles et précise les quantités résolues, les unités et la perte en capital.
164 tests backend ciblés distincts et build avec 308 tests frontend réussis.
Recette navigateur des quatre modes de ce lot sur base isolée ; smile et convergence temporelle restent ouverts.
[Marché automatique et recherche complète du 08/10](projects/pricing/PRODUCT_OPTIMIZER_AUTOMATIC_MARKET_SEARCH_2026-10-08.md)
ajoute le chargement par panier et date, la classification du référentiel,
les surcharges tracées, les axes fixes / explorés, 256 candidats au maximum,
le budget temps configurable et l’arrêt avec résultat partiel.
193 tests backend ciblés et 321 tests frontend avec build réussis ; recette API
isolée de 135 Phoenix terminée en environ 17 minutes, aucun échec, un candidat
confirmé parmi cinq validations indépendantes terminées. Date de pricing explicite, parcours
à l’émission ; taux et funding manuels, volatilités réalisées non implicites.
Recette visuelle bloquée par l’accès navigateur à localhost.
[Dossiers et page de résultats du 08/10](projects/pricing/PRODUCT_OPTIMIZER_RESEARCH_WORKSPACE_2026-10-08.md)
implémentés à la demande suivante de Philippe : résultats sur page dédiée,
radar à échelles explicites, panneaux repliables/scrollables et aides de champs.
Bibliothèque **Recherches & pricings** : sauvegarde propriétaire de la demande,
de l’intention, du marché figé et des prix, versions liées, archive et export.
Calcul détaché de la page, résultats partiels conservés et reprise explicite.
59 tests backend ciblés distincts, dont une recette réelle à deux processus,
et 346 tests frontend avec build réussis ;
activation de ces nouvelles routes et de la table au redémarrage du backend.
Le Copilot et l’exploitation AI des dossiers restent à réaliser.

Retour utilisateur traité dans la même note : un seul défilement vertical sur les
résultats, tableau paginé par 10/25, admissibilité provisoire distincte de la
confirmation et diagnostic explicite des rejets Monte-Carlo. Reprise proposée à
16 000 paires depuis 4 000, à contraintes et marché conservés, sans lancement
automatique. Dossier utilisateur lu seulement pour le diagnostic ; 355 tests
frontend et build réussis après ce correctif, sans modification backend.

[Contrôles de fusion PayScript / Optimizer du 08/10](audits/RECETTE_FUSION_PAYSCRIPT_OPTIMIZER_2026-10-08.md) :
deux échecs du premier contrôle GitHub corrigés, date de paiement final transmise
au solveur et à la grille résiduelle, réponse fictive AMC conforme au validateur ;
32 tests backend ciblés distincts réussis. État GitHub et fusion dans la PR #1.

État au contrôle final du lot précédent (historique) :
Backend à lancer pour utiliser ce lot (aucun serveur actif au contrôle final) ;
recette visuelle non refaite après le blocage d’accès localhost du navigateur.
Note placée à ce chemin sur demande explicite de Philippe.

Modèles de volatilité : [validation du 07/10](audits/VALIDATION_MODELES_VOL_2026-10-07.md)
et [autocalls sur cible commune](audits/AUTOCALL_SURFACE_COMMUNE_2026-10-07.md)
— **Benchmark hors interface exécuté** : référence SABR spot indépendante par PDE,
estimation conditionnelle LSV corrigée, cible SSVI sans arbitrage et dix prix
d'autocalls quatre ans mono / worst-of. Calls, puts, digitaux et convergence
temporelle passent les seuils retenus à 208 pas/an dans les régimes testés.
Local Vol et LSV reproduisent la cible ; Heston reste approximatif et SABR à
paramètres constants insuffisant. Ces écarts de calibration limitent le comparatif.
Le [workflow de surface du 07/10](projects/pricing/VOL_SURFACE_EDITOR_2026-10-07.md)
est désormais intégré : profils Actions/Indices selon le niveau de vol, édition
à la souris, matrice synchronisée, cible transmise à LV/LSV et ajustement
indicatif Heston/SABR. Build avec 254 tests frontend et recette navigateur
isolée. Les ajustements paramétriques et la précision restent à améliorer ;
le défaut de l'application reste 52 pas/an.

La [recette quantitative des profils intégrés du 07/10](audits/RECETTE_SMILE_INTEGRE_2026-10-07.md)
reprend l'autocall quatre ans à 20 % et 30 % ATM, mono et worst-of :
20 calculs API, flux réconciliés, contrôles indépendants de vanilles/digitaux,
édition de courbe effectivement consommée et convergence 52/104/208 pas/an.
Les petites alertes de la passe principale ne sont pas reproduites après
augmentation des trajectoires ; elles restent consignées. À 30 %, Local Vol
coûte seulement 0,08 point en mono et 0,39 en multi face au constant ;
à 20 %, les écarts sont 0,97 et 1,86 point. Hypothèses synthétiques.
SABR reste insuffisamment calibré (jusqu'à 143 bps vanille / 403 bps digital).
Les prix affinés utilisent 208 pas/an ; la revue dédiée LV à 30 % mesure
encore 6–8 bps entre 52 et 208, sans franchissement du seuil statistique retenu.

CCR : [Intégration du risque de contrepartie](projects/pricing/CCR_IMPLEMENTATION_2026-09-28.md)
— **Socle et extensions CCR 1.2 présents dans le code au 05/10** : référentiel
juridique/crédit, préparation des MtM, marché commun, exposition GBM, CVA simple,
contrôles Pricing/RFQ/deal booké et limites au booking. Taux commun provisoire
de 3 % lors de la préparation, explicitement qualifié comme hypothèse.
Recette visuelle complète et convergence restent ouvertes selon le rapport.

SA-CCR : [Portefeuille mixte notes / OTC](projects/pricing/SA_CCR_PORTEFEUILLE_MIXTE_ROADMAP_2026-09-29.md)
— **Cadrage seulement, confirmé au 05/10** : l'EAD réglementaire reste absente
du moteur ; ne pas la confondre avec la PFE économique du CCR.

Organisations et accès : [Cadrage de l'admission et des habilitations](projects/platform/ORGANIZATION_ACCESS_DESIGN_2026-09-24.md)
— **À faire, développement différé, confirmé au 05/10**. L'existant conserve
`User.entity_id` et un rôle global ; invitations, approbations, propriété stable
des données par organisation et habilitations par desk restent à construire.

Dernière correction Pricing : [Authentification des appels et erreurs de validation](projects/pricing/PRICING_AUTHENTIFICATION_2026-09-24.md)
— 30 appels harmonisés ; 217 tests frontend et build réussis ; pricing initial et profil de payoff vérifiés dans le navigateur.

Studies : [Audit métier et technique du 20/09/2026](audits/AUDIT_STUDIES_2026-09-20.md)
— constats initiaux ; corrections et contrôles décrits dans le [processus Studies](projects/studies/STUDIES_PROCESS_ET_CORRECTIONS_2026-09-20.md), avec limites de données et extensions restantes.
[Pitch de partenariat consulting](projects/studies/STUDIES_CONSULTING_PITCH_2026-09-20.md)
— préparation du rendez-vous du 23/09 : argumentaire, démonstration et pilote accompagné.
La [recette UI du 22/09](projects/studies/COMPTE_RENDU_RECETTE_UI_2026-09-22.md)
et ses [corrections en méthode 2.5](projects/studies/CORRECTIONS_RECETTE_2026-09-22.md)
prolongent les notes du 21/09 : elles consignent une exécution, une réouverture
et les comparaisons du jeu long-only. `studies-2.5` est confirmé dans le code
au 05/10 ; ces résultats historiques n'ont pas été réexécutés lors de cette revue.

IA : [Socle commun aux cinq assistants](projects/platform/IA_COMMUNE_2026-09-17.md)
— implémenté selon la note du 17/09/2026 ; catalogue, éditeur de prompt et suivi partagés. L'état du serveur local n'est pas vérifié par cet index.

Nouveau module Life Cycle : [Valo Explain — édition, comparaison et PDF figés](projects/lifecycle/VALO_EXPLAIN_2026-09-17.md)
— implémenté selon la note du 17/09/2026 ; l'état du serveur local n'est pas vérifié par cet index.

Dernière correction Booking : [MtM quotidien et progression du calcul](projects/lifecycle/BOOKING_MTM_QUOTIDIEN_2026-09-17.md)
— implémenté selon la note du 17/09/2026 ; l'état du serveur local n'est pas vérifié par cet index.

### Avant toute ouverture hors du poste local

- **Revérifié au 05/10** : les routeurs Pricing, Simulation et Scénarios imposent
  `get_current_user`. Les **quatre routes Schedule** restent sans dépendance
  d'authentification. Ce contrôle ne constitue pas un inventaire de toutes les API.
- CORS limité par défaut aux origines locales 5173/8000 ; surcharge possible par
  `STRUCTURA_CORS_ORIGINS`, avec credentials. Configuration déployée non inspectée.
- Inscription publique désactivée par défaut (`STRUCTURA_ALLOW_REGISTRATION`).
  Si activée, une entité non renseignée retombe encore sur « Demo », sans admission
  contrôlée par organisation.
- Aucun middleware global de durcissement HTTP identifié dans `main.py`
  (CSP, `X-Frame-Options`…). Un `nosniff` local existe dans `api/deals.py`.

Sources : audit de production du 31/07, audit du 02/08, contre-expertise du 11/09 (F01).

### Risque et portefeuille

- **Revérifié au 05/10** : les chemins historiques `portfolios.py`, `shocks.py`
  et `var.py` n'appliquent pas de filtre `uat_batch_id`. En revanche, le **CCR**
  sépare explicitement Production / Recette UAT dans son API et son service.
- Aucun branchement au Mode Démo identifié dans BookingView, EventsTab, RfqView
  et RiskManagementView au 05/10 ; comportement visuel non recetté dans cette revue.
- La sensibilité au spread émetteur n'est pas agrégée dans `api/portfolios.py`
  au 05/10.
- La reprise du 27/07 demandait une recette VaR réelle. Ne pas transformer ce
  constat daté en « jamais testé » : la couverture et les évolutions ultérieures
  doivent être examinées avant un nouveau verdict méthodologique.

### Moteur

- Monitoring continu par pont brownien : l'écart de −14,3 % est une mesure historique
  des audits du 01/08 et du 02/08, **non reproduite au 05/10**. Le moteur expose
  aujourd'hui une note sur les limites de l'interpolation ; le défaut chiffré reste
  à requalifier par une mesure, sans le déclarer corrigé ni encore reproduit.
- Vega Heston : la couverture est annoncée par `vega_scope`, sans vega sur les paramètres
  calibrés.
- Mark-to-Future du Pricer : `n_outer` à 200 et grille uniforme par défaut, confirmés
  au 05/10. Le moteur accepte aussi des dates explicites ; le CCR enrichit sa grille.
  `run_mc_proba` conserve des quantiles sans interpolation ; ceux du MTF utilisent
  `np.quantile`. Ces chemins ne doivent pas être confondus.
- Pas de champ repo distinct du rendement de dividende `q`. Vérifié.
- Constatations sur période : `_age_compiled_script` conserve désormais fenêtres,
  rangs, relevés passés et paiements. Le theta refuse explicitement les transitions
  de fenêtre/observation non résolues ; tests dédiés présents. P&L explain, KID et
  `REALVOL` à fenêtre de départ ouverte restent à recetter selon les cas du §24.
- Règle A7 : quatre tests dédiés existent dans `test_inlife_pricing.py` (horizon
  résiduel, flux depuis la valorisation, passé depuis le strike, déplacement de la
  frontière). Présence et assertions lues au 05/10 ; aucune nouvelle mesure ici.

### Éditeur, Economics et modèles

- EMT corrigé dans le code au 05/10 : levier sur `user_params`, export des
  `effective_parameters`, priorité à ces valeurs dans la synthèse. Les défauts du
  script ne servent que de repli ; les autres lecteurs du 11/09 restent à contrôler.
- Changement de forme d'un CONSTAT (P2 du 11/09) : conversion single → schedule
  toujours à traiter. `_buildUserParams` refuse les chaînes vides et les tableaux
  vides/non numériques ; `null`/`undefined` utilisent encore le défaut via `??`.
  Ne plus affirmer globalement qu'un champ vidé ne bloque jamais le calcul.
- Modèles de produits : questions ouvertes du §6.2 et vérification à l'écran après
  redémarrage du backend.
- Mode debug : dernière priorité, à redemander avant de le coder.

### Cycle de vie et RFQ

- Source officielle de chemin pour les produits path-dependent, annulation et
  remplacement d'un deal, propagation aval (confirmations, comptabilité), file Checker
  dédiée, identifiant de corrélation (rapports du 31/07).
- Déclinaisons : coût de débouclage, gel d'une proposition client, traçabilité. Aucune
  trace dans l'API des variantes. Vérifié.
- Les constructeurs locaux de calendriers de `RfqView.vue` omettent toujours les
  champs de fenêtre. En revanche, une RFQ liée à un Product reprend ses termes
  côté serveur. Le risque concerne les parcours locaux de saisie/restauration ;
  un refus systématique de toute RFQ à fenêtre n'est pas établi.
- Mineurs RFQ du 30/07 : nom d'AO vide et script non compilable acceptés par le serveur,
  mode Expert détecté par la seule chaîne `CONSTAT`, devise de cotation morte,
  numérotation globale des références, conversion indicatif → to trade sans lien avec
  l'AO d'origine, cotation ajoutable après booking. Non revérifiés.

### Chantiers non commencés ou à poursuivre

- Objet Product : RFQ, indicatif, booking, lifecycle, MtM/VaR et documents sont
  reliés dans le code au 05/10. Création interne lors d'un geste métier durable ;
  « Conserver » contrôle la visibilité dans la bibliothèque. Restent la reprise
  historique et la consolidation des consommateurs secondaires. Les anciens deals
  sans Product sont refusés par MtM/VaR, sans repli automatique.
- Déploiement on-premise : installeur, service Windows, sauvegarde de la base, mises à
  jour, journaux.
- Données de marché : FRED, taux officiels, données d'options.
- Études AMC : quatre moteurs en feuille de route ; FIFO, décomposition prix/FX du lot T0.

### Travaux sans fichier dans le dépôt

Pages publiées : contre-expertise de l'audit externe du 11/09 (P0 retenus F01, F03, F06,
F14, F20, F28 ; arbitrages A0 à A10 en attente), audit qualité du 30/08, analyse SaaS du
11/09, étude de l'objet Product du 13/09, plan Client Intelligence du 31/08.

## Historique des travaux des 14 et 15/09

Les puces suivantes décrivent la session de septembre. **Elles ne sont plus un état
Git actuel** : au début de la revue du 05/10, `main` pointe sur `15d7ccf` et aucun
fichier suivi n'est modifié. Product et les modèles sont présents sur cette branche.

- Modèles de produits, lots 1 à 4 : `projects/pricing/MODELES_PRODUITS_DESIGN.md`, §9.
- Booking d'une RFQ à échéancier CONSTAT, refusé depuis le 10/09 (« termes contractuels
  figés : T, constats ») : le contrôle compare désormais le contrat et non son écriture,
  T en jours et constats sans leurs clés vides (`core/rfq_controls.py`,
  `booking_terms_differences`). Un vrai changement reste refusé ; tests dans
  `test_rfq.py`, §18.
- Forward start : fenêtre de calibration réalisée indépendante de l'âge du deal
  (`core/calibration.py`), prix du Pricer avant la date de strike égal au MtM de Booking
  (`api/inlife.py`), date de valorisation proposée à la réouverture du deal.
- Objet Product sur la branche `codex/product-workflow` : modifications d'une autre
  session.
- Ce classement : notes déplacées sans `git mv`, chemin de la référence PayScript mis à
  jour dans `services/llm/prompt.py` et dans son test.

Le besoin de redémarrage était celui de cette session ; aucun état de processus
local n'a été contrôlé lors de la revue documentaire du 05/10.

## Détail par dossier

### `audits/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `AUDIT_PRICING_2026-07.md` | 17/07 | Moteur Monte Carlo : 9 défauts corrigés le jour même, puis barrières continues, Heston/SABR vectorisés, backtest intra-période | Clos | Mémoire non bornée à N élevé ; transpileur fondé sur `exec` (assumé) |
| `AUDIT_RFQ_2026-07-29.md` | 29/07 | Module RFQ, 6 constats | Clos le 30/07 | Voir les mineurs de l'audit du 30/07 |
| `TESTING_JOURNAL.md` | 29/07 | Journal de l'agent client-tester : pricing, booking, cycle de vie, RFQ | Clos | Sélecteur d'exemples sans confirmation visuelle, jugé mineur |
| `AUDIT_CHAINE_RFQ_2026-07-30.md` | 30/07 | Chaîne RFQ → pricing → booking, 9 constats | Clos | Mineurs du §10 ; ténor du Pricer contre calendrier, à revoir avec la règle de maturité du 14/09 |
| `AUDIT_COMPLET_PRICING_RFQ_LIFECYCLE_2026-07-31.md` | 31/07 | Audit fonctionnel et quantitatif, 11 P0, NO-GO | Dépassé | Repris par les audits du 01/08, du 02/08 et du 07/08 |
| `AUDIT_PRODUCTION_COMPLET_HORS_AMC_2026-07-31.md` | 31/07 | Production : sécurité, performance, pricing, lifecycle, KID, NO-GO historique | Suivi | Revue 05/10 : Pricing/Simulation/Scénarios authentifiés, CORS restreint par défaut, inscription désactivée par défaut ; Schedule public et durcissement global restent ouverts. Budget de calcul présent |
| `AUDIT_QUANTITATIF_COMPLET_HORS_AMC_2026-07-31.md` | 31/07 | 40 constats quantitatifs, dont 12 critiques | Dépassé | Repris par la vague 1 du 31/07 et l'audit du 01/08 |
| `AUDIT_QUANTITATIF_2026-08-01.md` | 01/08 | Revérification : 6 bloquants sur 12 fermés | Dépassé | Repris par l'audit du 02/08 |
| `AUDIT_COMPLET_2026-08-02.md` | 02/08 | 20 constats rejoués ; lots 1 et 2 corrigés selon le rapport | Suivi | Revue 05/10 : CORS restreint par défaut ; pont brownien à remesurer, vega Heston partiel, grille hebdomadaire et durcissement HTTP global restent ouverts ; vol locale non revalidée |
| `AUDIT_MTF_2026-08-03.md` | 03/08 | Mark-to-Future : 5 défauts corrigés (double comptage, STRIKE_FIX, courbe, quantile, date proche) | Suivi | `n_outer` par défaut, grille de dates, quantile de `run_mc_proba` (vérifié) ; valorisation risque-neutre ou projection client |
| `AUDIT_FRONT_TO_RISK_2026-08-07.md` | 07/08 | RFQ → booking → MtM → Greeks → risque : 6 P1, 13 P2, 6 P3 | Suivi | Revue 05/10 : CORS restreint par défaut ; UAT filtré dans CCR, pas dans les agrégats historiques ; Mode Démo non branché dans les vues inspectées. Autres P2/P3 non revérifiés |
| `AUDIT_CONVENTIONS_PRICING_2026-09-08.md` | 08/09 | Conventions de `CLAUDE.md` mesurées : code conforme, 4 écarts de documentation | Clos selon le rapport | Revue 05/10 : quatre tests A7 existent ; assertions lues, sans nouvelle exécution |
| [REVUE_DOCUMENTAIRE_2026-10-05.md](audits/REVUE_DOCUMENTAIRE_2026-10-05.md) | 05/10 | Confrontation des points de reprise au code et aux tests présents | Lecture statique terminée | Recettes et mesures restant ouvertes distinguées des corrections implémentées |
| [AUDIT_AUTOCALL_SMILE_2026-10-06.md](audits/AUDIT_AUTOCALL_SMILE_2026-10-06.md) | 06/10 | Revue des prix mono / multi, référence GBM indépendante, arbitrage de la cible et contrôle du pas | GBM corroboré ; comparatif smile non validé en l’état | Surface sans arbitrage, calibration commune et convergence à reprendre |
| [AUDIT_CALLS_MODELES_2026-10-07.md](audits/AUDIT_CALLS_MODELES_2026-10-07.md) | 07/10 | Première grille calls / puts sur cinq modèles et cas limites | Diagnostic initial | Prolongé par la validation du même jour |
| [VALIDATION_MODELES_VOL_2026-10-07.md](audits/VALIDATION_MODELES_VOL_2026-10-07.md) | 07/10 | Correction LSV, référence SABR/PDE, vanilles et digitaux mono / marginales multi | Premier lot historique ; prolongé par le benchmark de cible commune | Limites de précision initiales traitées à 208 pas/an sur la grille du benchmark |
| [AUTOCALL_SURFACE_COMMUNE_2026-10-07.md](audits/AUTOCALL_SURFACE_COMMUNE_2026-10-07.md) | 07/10 | SSVI sans arbitrage, calibration, vanilles, convergence, dix autocalls et flux séparés | Benchmark hors interface exécuté ; 29 tests ciblés passent | Ajustements Heston/SABR imparfaits ; workflow surface et précision à intégrer |
| [CONTRE_REVUE_APPLICATION_2026-10-24.md](audits/CONTRE_REVUE_APPLICATION_2026-10-24.md) | 24/10 | Contre-revue du rapport d'application : 22 constats A–F, carte de validité par domaine, plan de validation et critique du rapport | Six constats de catégorie A établis, aucun corrigé | CR01–CR08 ouverts ; arbitrages CR02 (statistique VEV), CR10 (graine), CR19 ; E.1 et N3/N5/W1 à exécuter |

### `projects/pricing/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| [COMPARAISON_AUTOCALL_4ANS_MODELES_2026-10-06.md](projects/pricing/COMPARAISON_AUTOCALL_4ANS_MODELES_2026-10-06.md) | 06/10 | Athena 4 ans, cinq modèles de vol, mono et worst-of à deux actifs | Dix prix calculés et flux réconciliés | Hypothèses explicites non calibrées ; convergence du pas et calibration hors périmètre |
| [VOL_SURFACE_EDITOR_2026-10-07.md](projects/pricing/VOL_SURFACE_EDITOR_2026-10-07.md) | 07/10 | Profils indicatifs Actions/Indices par niveau de vol, courbes éditables, matrice et consommation moteur | Implémenté ; tests ciblés, build et recette navigateur | Ajustements paramétriques approximatifs, précision et chocs de forme SSVI à approfondir |
| [PAYSCRIPT_PRESETS_EDITOR_2026-10-07.md](projects/pricing/PAYSCRIPT_PRESETS_EDITOR_2026-10-07.md) | 07/10 | Éditeur unique, réglages avancés locaux et 15 exemples préremplis partagés Pricer/RFQ | Implémenté ; 109 tests backend ciblés, build avec 284 tests frontend et recette navigateur | Termes illustratifs à adapter ; pas de nouvelle recette de booking/cycle de vie |
| [COMPARAISON_AUTOCALL_SMILE_ACTIONS_2026-10-06.md](projects/pricing/COMPARAISON_AUTOCALL_SMILE_ACTIONS_2026-10-06.md) | 06/10 | Même Athena avec skew actions renforcé ; prix, écarts et smile implicite simulé | Sorties conservées avec réserve après audit | Cible invalide dans l’aile basse ; calibration commune et validation numérique restent à faire |
| `PAYSCRIPT_PARAM_PAR_OBSERVATION.md` | 18/07 | `PARAM()` à une valeur par observation, convention `M_` ; valeur initiale obligatoire depuis le 14/09 | Fait | — |
| `SCRIPTING_IA_DESIGN.md` | 03/08 | Assistant de scripting : référence sous test, fournisseurs (Ollama par défaut), fiche de contrôle, écho d'intention ; phases 0 à 4 codées | Fait | Choisir le modèle local (`backend/scripts/eval_script_assistant.py`) ; aligner le corpus sur le catalogue de modèles |
| `CONSTATATIONS_PERIODE_DESIGN.md` | 10-11/09, suivi 05/10 | MIN/MAX/AVG, PERIOD, INDEX, calendriers et fixings ; theta conserve désormais les métadonnées | En cours | Recette P&L explain/KID et REALVOL à fenêtre de départ ouverte ; theta indisponible sur transitions non résolues |
| `EDITEUR_ECONOMICS_DESIGN.md` | 11/09, suivi 05/10 | Règle « Economics fait foi », validation explicite, EMT effectif et contrôles de PARAM implémentés | En cours | P2 single → schedule, cas null/undefined, autres consommateurs et mode debug différé |
| `MODELES_PRODUITS_DESIGN.md` | 14/09, suivi 05/10 | Ctrl+S, « Valider », maturité et catalogue présents sur main | En cours | Questions du §6.2 et recette UI ; état complet du lot 5 non revérifié |
| [CCR_IMPLEMENTATION_2026-09-28.md](projects/pricing/CCR_IMPLEMENTATION_2026-09-28.md) | 28/09, suivi 05/10 | CCR économique et extensions de préparation MtM / marché commun / deal booké | Code présent | Recette visuelle complète, convergence, taux du jour ; aucune EAD SA-CCR |
| [CCR_UAT_TEST_CLIENT_2026-09-29.md](projects/pricing/CCR_UAT_TEST_CLIENT_2026-09-29.md) | 29/09 | Hypothèses fictives de recette partagées au niveau de Demo ; notes exclues des sets OTC simulés | État de données historique | Base réelle non relue au 05/10 |
| [SA_CCR_PORTEFEUILLE_MIXTE_ROADMAP_2026-09-29.md](projects/pricing/SA_CCR_PORTEFEUILLE_MIXTE_ROADMAP_2026-09-29.md) | 29/09 | Projet futur : classement notes/OTC, portefeuille mixte et SA-CCR equity sans produits de taux | À faire | Lots 0 à 5 ; juridiction, premier produit OTC et qualification des historiques à décider |

### `projects/lifecycle/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `DEAL_LIFECYCLE_2026-07.md` | 17/07 | État des lieux initial : booking, events, repricing | Dépassé | Plan réalisé : MtM résiduel, job quotidien, alertes, preuves de valorisation (`ValuationRun`) |
| `MTM_RESIDUEL_DESIGN.md` | 19/07 | MtM d'un deal vivant : rejeu du passé et Monte Carlo résiduel | Fait | — Prolongé depuis : état complet au Mark-to-Future (01/08), deal non striké (03/09), Pricer avant strike (14/09) |
| `NOTE_VALO_DESIGN.md` | 19/07 | Note de valorisation client en PDF, v1.2 | Fait | v2 : version anglaise, envoi par e-mail |
| `EXPLICATION_VALO_DESIGN.md` | 19/07 | P&L explain entre deux dates, waterfall en PDF | Fait | v2 : effet spot par sous-jacent, ligne rho |
| `SPECIFICATION_REMEDIATION_VAGUE_1_LIFECYCLE_HORS_AMC_2026-07-31.md` | 31/07 | Spécification : quatre yeux sur les fixings, registre officiel, rejeu borné, application atomique | Fait | Réalisée par les trois rapports suivants |
| `IMPLEMENTATION_RFQ_BOOKING_LIFECYCLE_PHASE_0_1_2026-07-31.md` | 31/07 | Contrôles RFQ, booking gate, statuts de fixing, audit persistant | Fait | Risques résiduels repris par la phase 2 |
| `RAPPORT_IMPLEMENTATION_LOT_1_FIXING_LIFECYCLE_HORS_AMC_2026-07-31.md` | 31/07 | Registre immuable des fixings, pièces sources, décision Checker, application atomique | Fait | Durcissement (§5) : stockage chiffré des pièces, référentiel fournisseurs, migrations versionnées, tests E2E, identifiant de corrélation |
| `IMPLEMENTATION_RFQ_BOOKING_LIFECYCLE_PHASE_2_2026-07-31.md` | 31/07 | Rejeu officiel, sémantique KI/final, amendements maker-checker, consultation de l'audit | Fait | Source officielle de chemin, annulation/remplacement, propagation aval, file Checker |
| `DECLINAISONS_POINTS_OUVERTS.md` | 29/08 ; état 22/10 | Historique des manques autour des variantes et état courant | Traité localement C19/C25 | Gel manuel, traçabilité et économie du roll livrés ; qualification graphique et déployée restante |

### `projects/clients/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `CLIENTS_LOT_0_DOCTRINE_METIER.md` | 01/09 | Doctrine métier, vocabulaire, règles d'autorité | Fait | — |
| `CLIENTS_LOT_1_CHAINE_COMMERCIALE.md` | 02/09 | Contexte Client facultatif dans Produit → RFQ → Deal, recette acceptée | Fait | — |
| `CLIENTS_LOT_2_HABITUDES_TRADING.md` | 02/09 | Habitudes de trading et sélection des fournisseurs ; implémenté le 03/09 | Fait | L'en-tête dit encore « à valider avant codage » : le §18 fait foi |
| `CLIENTS_LOT_3_INTEGRATION_LIFECYCLE.md` | 05/09 | Événements des deals exploitables depuis le module Clients | Fait | — |

### `projects/platform/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| [WORKSHOP_DIAGNOSTIC_CONFIGURATION_2026-10-14.md](projects/platform/WORKSHOP_DIAGNOSTIC_CONFIGURATION_2026-10-14.md) | 14/10 | Paramètres pleine largeur, calendrier multi-RFQ, funding/marges, cadences, estimation et reprise | Raccordé localement ; recette ciblée sans IA | Lancer explicitement le suivi de cinq ans ; qualifier les branches non exercées et l’ergonomie détaillée |
| [RFQ_NETWORK_ACTION_PLAN_2026-10-12.md](projects/platform/RFQ_NETWORK_ACTION_PLAN_2026-10-12.md) | 12/10 | Destinataires par organisation, réception bancaire, publication contrôlée, retour automatique et manuel ; lots 0 à 8 | Lot 0 cadré avec premier prototype ; lot 1 cadré | Compléments d'écran, choix du pilote, réalisation des lots 1 à 8 et recette réseau ; aucune reprise des anciens tests |
| [RFQ_NETWORK_LOT_0_IMPLEMENTATION_2026-10-12.md](projects/platform/RFQ_NETWORK_LOT_0_IMPLEMENTATION_2026-10-12.md) | 12/10 | Prototype demandeur/banque ; préparation RFQ depuis Product, moteurs actuels, Pricer et scroll interne | Raccordement livré sur branche ; 154 tests backend ciblés, 424 frontend et build ; recette isolée | Propriété, droits, partenaires, réception bancaire, transport et booking réseau dans les lots suivants |
| [RFQ_NETWORK_LOT_0_SPECIFICATION_2026-10-12.md](projects/platform/RFQ_NETWORK_LOT_0_SPECIFICATION_2026-10-12.md) | 12/10 | Parcours, demandes/réponses, droits, transitions, confidentialité, fermeté, retrait et confirmation avant booking | Règles fonctionnelles actées, non implémentées | Maquettes, paramètres opérationnels et transport ; confirmation native et rapprochement ultérieurs |
| [RFQ_NETWORK_LOT_1_SPECIFICATION_2026-10-12.md](projects/platform/RFQ_NETWORK_LOT_1_SPECIFICATION_2026-10-12.md) | 12/10 | Propriété organisationnelle, desks, droits détaillés, profils, partage, affectation et révocation | Cadrage détaillé ; desk pilote et absence de migration actés | Réalisation et recette sur nouveaux dossiers fictifs, sans reprise des anciens tests |
| [MULTI_STRUCTURA_AGENT_IMPLEMENTATION_2026-10-09.md](projects/platform/MULTI_STRUCTURA_AGENT_IMPLEMENTATION_2026-10-09.md) | 09/10 | Livraison des agents IA utilisateurs, installations séparées, contrats, CRM, livres, lifecycle, interface et qualification | Implémenté localement | Couverture exhaustive, défauts, appels de marge, réinvestissement, historique réel et réseau RFQ différés |
| [MULTI_STRUCTURA_AGENT_ACTION_PLAN_2026-10-08.md](projects/platform/MULTI_STRUCTURA_AGENT_ACTION_PLAN_2026-10-08.md) | 08/10 | Cadrage des agents utilisateurs de leurs instances Structura : dialogues, contrats, books, vie, risques et preuves | Cadrage initial | État exécuté dans le rapport de livraison du 09/10 |
| [INTER_ENTITY_RFQ_BACKLOG_2026-10-08.md](projects/platform/INTER_ENTITY_RFQ_BACKLOG_2026-10-08.md) | 08/10, suivi 12/10 | Contexte initial du futur flux RFQ et de la recette multi-Structura | Cadrage initial prolongé | Réalisation selon le plan et la spécification du lot 0 du 12/10 ; contexte de simulation conservé |
| [DESK_SIMULATION_ACTION_PLAN_2026-10-08.md](projects/platform/DESK_SIMULATION_ACTION_PLAN_2026-10-08.md) | 08/10 | Premier cadrage de simulation du desk | Historique | À reprendre selon le cadrage multi-Structura ; le laboratoire développé ensuite a été retiré |
| `PLAN_IMPLEMENTATION_OBJET_PRODUCT.md` | 14/09, suivi 05/10 | Dossier canonique présent sur main : RFQ/indicatif/booking/lifecycle/MtM/VaR/documents ; création interne aux gestes durables | En cours | Reprise historique et consolidation des consommateurs secondaires ; aucun repli MtM/VaR pour un deal sans Product |
| [ORGANIZATION_ACCESS_DESIGN_2026-09-24.md](projects/platform/ORGANIZATION_ACCESS_DESIGN_2026-09-24.md) | 24/09, suivi 05/10 | Admission, propriété par organisation, habilitations et desks | Cadrage, non implémenté | Invitations, approbations, migration, isolation et recette |
| `HOME_REDESIGN_DESIGN.md` | 19/07 | Accueil en quatre catégories, drill-down | Fait | — |
| `DEPLOIEMENT_ONPREM.md` | 25/07 | Un serveur par client, sous Windows | À faire | Installeur, service Windows, sauvegarde de la base, mises à jour, journaux, cinq questions ouvertes. Fait depuis : secret JWT propre à chaque machine (02/08) |
| `FRED_INTEGRATION_ROADMAP.md` | 29/08 | Données FRED pour la VaR, les scénarios, les régimes et les backtests | À faire | Décisions du §11 ; rien de codé (vérifié) |
| `SOURCES_DONNEES_TAUX_OPTIONS.md` | 29/08 | Sources gratuites de taux et d'options | À faire | Feuille de route en quatre phases |

### `projects/studies/`

Les états du 21/09 ci-dessous sont historiques : la recette UI et les corrections
du 22/09 les prolongent. Ils ne signifient pas qu'aucune recette n'a eu lieu depuis.

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| [COMPTE_RENDU_RECETTE_UI_2026-09-22.md](projects/studies/COMPTE_RENDU_RECETTE_UI_2026-09-22.md) | 22/09 | Recette A–K du jeu long-only, sauvegarde et contrôles financiers | Exécution historique consignée | Constats repris dans les corrections suivantes |
| [CORRECTIONS_RECETTE_2026-09-22.md](projects/studies/CORRECTIONS_RECETTE_2026-09-22.md) | 22/09 | Méthode 2.5 : IA, PDF, turnover, affichage et frais/HWM | Code 2.5 confirmé au 05/10 ; résultats de septembre non rejoués | Limites des autres jeux et annexes PDF non intégralement inspectées |
| [STUDIES_DIVIDENDS_2026-09-21.md](projects/studies/STUDIES_DIVIDENDS_2026-09-21.md) | 21/09 | Studies 2.2 : dividendes par titre, créances, fiscalité, réinvestissement et contrôles | Livré ; 79 tests backend ciblés, 194 frontend et build réussis | Recette UI ; distributions investisseurs et calendriers contractuels étendus ultérieurs |
| [STUDIES_INTERFACE_2026-09-21.md](projects/studies/STUDIES_INTERFACE_2026-09-21.md) | 21/09 | Configuration en pleine largeur, tableaux et indicateurs harmonisés | 194 tests frontend ; build réussi | Recette visuelle dans le navigateur utilisateur |
| [STUDIES_EXISTING_FIXES_2026-09-21.md](projects/studies/STUDIES_EXISTING_FIXES_2026-09-21.md) | 21/09 | Méthode 2.4 : calculs, sources et restitution des blocs existants | Tests ciblés et recette indépendante | Guide des corrections et résultats attendus |
| [STUDIES_SETUP_COMPLET_2026-09-21.md](projects/studies/STUDIES_SETUP_COMPLET_2026-09-21.md) | 21/09 | Un dossier autonome : scan et lancement A à K, référence E/G séparée | Blocs calculés hors réseau ; 85 comparaisons | Recette utilisateur ; 85/85 comparaisons conformes en méthode 2.4 |
| [STUDIES_EXTENDED_REFERENCE_2026-09-21.md](projects/studies/STUDIES_EXTENDED_REFERENCE_2026-09-21.md) | 21/09 | Référence indépendante A–K, TS et import isolé E, benchmark synthétique | Banc isolé : 82/85 contrôles conformes | Recette E dans l’UI ; trois écarts F/J ; import de marchés complet |
| [STUDIES_RECONCILIATION_AND_FEES_2026-09-21.md](projects/studies/STUDIES_RECONCILIATION_AND_FEES_2026-09-21.md) | 21/09 | Studies 2.1 : frais paramétrables, dividendes, valorisation sur relevé, FIFO et recette indépendante | Corrigé ; 55 tests backend ciblés, 194 frontend et build réussis | Redémarrage utilisateur et nouvelle recette UI ; frais complexes/égalisation ultérieurs |
| [INDEPENDENT_LONG_ONLY_DATASET_2026-09-21.md](projects/studies/INDEPENDENT_LONG_ONLY_DATASET_2026-09-21.md) | 21/09 | Fonds fictif 2020–2025, CSV, FX BCE et comptabilité indépendante | Données générées et contrôlées | Test Studies par Philippe, comparaison puis diagnostic ; flux investisseurs et long/short ultérieurs |
| `DECISION_ANALYSIS_ENGINE.md` | 26/06 | Qualité des décisions d'un gérant AMC | À faire | Idée validée ; fichier non versionné (`.gitignore`) |
| `MANAGER_DNA_ENGINE.md` | 26/06 | Empreinte quantitative du style de gestion | À faire | Idée validée ; fichier non versionné |
| `SKILL_VS_LUCK_ENGINE.md` | 16/07 | Talent ou hasard, par bootstrap et Monte Carlo | À faire | Idée validée ; fichier non versionné |
| `STUDY_COMPARISON_ENGINE.md` | 16/07 | Comparer deux études du même AMC | À faire | Trois points à trancher |

### `reference/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `PAYSCRIPT_REFERENCE.md` | 03/08, revue le 14/09 | Référence du langage ; corps du prompt de l'assistant IA, lu par `services/llm/prompt.py` ; vocabulaire comparé au parser par `test_payscript_reference.py` | Référence | À mettre à jour à chaque évolution du langage |
| `GOUVERNANCE_AMENDEMENTS.md` | 07/08 | Amendement d'un deal booké : machine à états, garanties, seconde signature désarmée par défaut | Référence | Procédure de réarmement au §4 |
| `FIFO_MODULE.md` | 16/07 | Reconstruction FIFO d'un carnet d'ordres AMC | Référence | Décomposition prix/FX du lot T0 non corrigée ; écart de +23 % contre la NAV à expliquer ; autres AMC non testés |

### `lessons/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `PORTFOLIO_RECONCILIATION_LESSONS.md` | 16/07 | Pièges de la réconciliation FIFO contre NAV, avec checklist | Historique | Défaut prix/FX du lot T0 (§8) |
| `POSTMORTEM_2026-07-16_CH1352587724_PNL_RECONCILIATION.md` | 16/07 | Post-mortem de la réconciliation de CH1352587724 | Historique | Positions fantômes non résolues (§5) ; vérifier les études livrées avant le correctif de pricing des déficits |

### `handoffs/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `REPRISE_BOOKING_2026-07-19.md` | 18/07 | Booking, cycle de vie automatique, `PARAM()` | Historique | Traité depuis : sous-jacents complétés à la réouverture, `reload=False`, job quotidien, MtM résiduel |
| `REPRISE_2026-07-21.md` | 21/07 | Données de marché en administration, onglets Booking | Historique | — |
| `REPRISE_2026-07-27.md` | 27/07 | Deals de démo, exposition, VaR/ES, calcul parallèle | Historique | Écran VaR à tester en réel, méthodologie à challenger, calibration paramétrique recalculée à chaque étude ; bornes du formulaire ajoutées depuis (vérifié) |
| `REPRISE_2026-07-30.md` | 30/07 | Audits RFQ, défauts de booking | Historique | Arbitrage du ténor du Pricer, mineurs RFQ, module Réinvestissement non reconfirmé ; nettoyage des deals sans objet, la base ne contient que des tests |
| `REPRISE_2026-08-27.md` | 26-27/08 | Appels d'offres, conventions de dates, cours nus, dividendes, funding, note Marex | Historique | Champ repo et agrégation du spread au book (vérifié absents) ; deux conventions de maturité RFQ et Deal ; liste « À vérifier ». Fait depuis : calibration datée (`load_hist_vol(asof=…)`) |

### `archive/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `OLD_AVANCEMENT.md` | 27/06 | État du projet AMC | Archivé le 16/07 | Ne pas s'y fier |
| `OLD_REPRISE_TRAVAIL.md` | 26/06 | Fiche technique AMC, blocs A à J | Archivé le 16/07 | Deux formules fausses, signalées en tête |
