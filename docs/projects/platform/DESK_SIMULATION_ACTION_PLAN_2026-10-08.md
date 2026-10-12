# Plan de simulation du desk pour tester et améliorer Structura

Date : 08/10/2026. Statut : cadrage historique, à reprendre.

Le laboratoire développé après ce plan a été retiré le 08/10/2026. Philippe
redéfinit les spécifications autour d'agents qui utilisent chacun leur propre
Structura, par les écrans et les API. Hector remplace Alex et Achille remplace
Camille. Les nouvelles décisions et le chantier RFQ différé sont conservés dans
[la note multi-entités](INTER_ENTITY_RFQ_BACKLOG_2026-10-08.md). Le présent plan
ne constitue plus la spécification active à implémenter. Le
[plan d'action multi-Structura](MULTI_STRUCTURA_AGENT_ACTION_PLAN_2026-10-08.md)
définit désormais l'ordre de développement.

La simulation doit exercer les fonctions de Structura, découvrir leurs défauts,
conserver des preuves et mesurer les améliorations après correction. Son aspect
de jeu permet de suivre une année d'activité commerciale et de vie des produits.
Le nombre de transactions ou la fluidité des dialogues ne constituent pas, à eux
seuls, des critères de réussite de la recette.

Alex représente une maison de structuration, d'émission et de distribution,
attentive à ses clients et exigeante avec les banques lors des appels d'offres.
Camille supervise l'utilisation de Structura. Les agents clients et banques
portent des profils et des informations distincts. Les agents opérations,
crédit et trésorerie exercent les responsabilités de contrôle et de règlement.

## 1 Décisions retenues et périmètre

- Les relations contractuelles nécessaires sont mises en place avant toute
  première requête de pricing ou RFQ du jeu. Cette règle de campagne ne change
  pas implicitement la liberté de pricing des utilisateurs ordinaires.
- Alex utilise Clients, Contacts, Mandats, Interactions et Opportunities,
  puis les mêmes parcours produit, RFQ, booking et lifecycle que l'application.
- Alex peut émettre ses notes, acheter des notes externes et rechercher des
  couvertures externes. Chaque mode exige une représentation économique propre.
- Une année virtuelle est la cible initiale ; départ, horizon, activité et
  durée réelle visée sont modifiables. Une à deux heures est un objectif à
  qualifier sur une campagne définie, pas une durée garantie pour tout volume.
- Le temps métier attend la fin des calculs, dialogues et contrôles nécessaires
  à l'événement courant. Des délais commerciaux peuvent être simulés explicitement.
- Chaque acteur peut signaler erreurs et améliorations à chaque étape.
- Camille propose des corrections d'usage et des procédures apprises. Les
  premières erreurs, limitations et contournements restent dans les preuves.
- Les calculs et transitions sont exécutés par Structura. Les décisions IA ne
  remplacent ni un prix, ni un fixing, ni un contrôle d'accès ou une exécution.
- L'environnement utilise une base de recette isolée. Une étiquette UAT seule
  ne constitue pas la frontière d'isolation de cette simulation.
- La couverture des services métier et celle des interfaces sont publiées
  séparément. Un parcours API réussi ne valide pas automatiquement son écran.

La première campagne couvre les produits structurés et leur chaîne commerciale.
Les autres fonctions de Structura entrent dans un inventaire de couverture ;
Studies/AMC disposent de campagnes spécifiques ultérieures. Les payoffs et
modèles sont activés uniquement après qualification de leurs adaptateurs.

## 2 Points de départ et adaptations nécessaires

Les repères suivants proviennent d'une lecture ciblée du code disponible le
08/10/2026. Leur présence ne constitue pas une nouvelle validation d'exécution.

| Sujet | Point de départ | Travail nécessaire |
|---|---|---|
| Product et booking | `api/deals.py` refuse `PRODUCT_ALREADY_BOOKED` ; Product porte une exécution | Préserver cette règle et relier des dossiers d'exécution distincts à une même opération commerciale |
| Sens des positions | `Deal.sens` est exprimé du point de vue de la contrepartie ; RFQ utilise notre sens | Centraliser la traduction et tester positions, flux et montants signés |
| Relations de crédit | Contrats CCR pour profils, accords, CSA, sets, limites et collatéral | Qualifier les formats notes/OTC, les acteurs, les dates et les conventions propres au jeu |
| Horloge | RFQ, lifecycle et alertes lisent encore `date.today()` ou `datetime.utcnow()` | Inventorier et remplacer les seules décisions temporelles métier concernées par un contexte explicite |
| Scheduler | `main.py` lance une passe quotidienne ; `STRUCTURA_DISABLE_SCHEDULER` existe | Désactiver le scheduler réel dans l'instance de recette et déclencher les événements selon l'horloge virtuelle |
| Flux réalisés | Deal conserve `realized_payout` et `settlement_amount` | Vérifier chaque flux et sa date ; prévoir des règlements et rapprochements datés sans assimiler constatation et paiement |
| Intelligence client | API de signaux et de lecture avec date d'analyse ; interactions et relances présentes | Vérifier le transport de la date virtuelle et la continuité commerciale jusqu'au deal |
| Générateur UAT | Parcours Product/RFQ/booking, profils lifecycle, lots reproductibles | Réutiliser les préparations qualifiées ; ne pas remplacer une année jouée par des enregistrements rétrospectivement vieillis |
| Calculs | Exécuteur parallèle commun ; recherches Optimizer persistantes | Réutiliser les mécanismes adaptés et ajouter une persistance propre aux événements et actions de campagne |
| Reprise | Les recherches Optimizer en cours sont marquées interrompues après redémarrage | Définir la reprise de la campagne et des actions ambiguës ; ne pas présumer un redémarrage automatique exact |
| IA | Clients communs de génération de texte et workbench | Ajouter décisions structurées, validation, outils autorisés, mémoire par acteur et messagerie |
| Interface | Routes Administration/UAT et composants partagés ; thème clair dans `style.css` | Ajouter un cockpit institutionnel cohérent et des ouvertures des écrans dans le contexte de recette |

Le modèle de financement du Pricer et le CCR clean doivent rester cohérents :
le service CCR refuse certains contextes contenant funding/spread émetteur.
Le plan prévoit une valorisation clean distincte lorsque nécessaire, avec ses
preuves et ses conventions, pour éviter une double prise en compte du crédit.
L'EAD SA-CCR reste une extension séparée selon la feuille de route dédiée.

## 3 Relations contractuelles et opérations liées

### Préparer les relations

Chaque partie a une identité juridique, un rôle daté, une devise, des droits,
un profil de crédit et un lien explicite avec ses identités commerciales.
Client commercial, contrepartie juridique, émetteur, garant et fournisseur de
cotation restent des rôles distincts, même lorsqu'ils désignent la même entité.

Le dossier bilatéral décrit la documentation applicable, les produits et
devises autorisés, les dates d'effet et de fin lorsqu'applicables, les conditions
de règlement, les limites, les garanties éventuelles et les responsabilités.
Pour les OTC, il précise master agreement, opposabilité, set de netting et CSA.
Les conventions de collatéral détaillent seuils, MTA, VM/IM, éligibilité, haircut,
fréquence, délais, MPOR et positions initiales connues, y compris zéro explicite.

La phase initiale comporte demande, négociation, vérification, décision et
activation. États proposés : en préparation, à vérifier, accepté, actif,
expiré, suspendu, refusé. La campagne reste en préparation si une relation
nécessaire à son scénario est incomplète. Une relation exclue doit entraîner
une révision explicite du périmètre avant lancement.

Une obligation non collatéralisée peut être contractuellement valide. L'absence
de CSA n'est donc pas systématiquement une anomalie. Les notes ne reçoivent
pas automatiquement une qualification OTC ou un avantage de netting.

### Représenter les opérations

| Mode d'Alex | Objets à relier | Contrôles spécifiques |
|---|---|---|
| Distribution externe | Acquisition d'une note puis cession au client du même instrument | Identité de l'instrument et de l'émetteur, position détenue, quantité, prix et règlements de chaque opération |
| Émission propre | Engagement émis au client et position du desk | Dette envers le porteur, funding, payoff, flux signés et risque restant chez Alex |
| Émission couverte | Émission au client et une ou plusieurs couvertures externes | Payoffs, calendriers, notionnels et créances de chaque contrat ; exposition résiduelle et conditions bilatérales propres |

Une référence d'opération commerciale relie les dossiers Product et les
exécutions, avec le rôle de chaque jambe. Les termes de couverture peuvent
différer des termes de la note. Un même RFQ ne sert pas à contourner la règle
d'un booking unique. Alex doit savoir si une jambe a été traitée et l'autre
refusée ; aucune transaction partielle n'est effacée ou présentée comme couverte.

Un journal de règlements et de positions, avec déduplication et rapprochement,
sera nécessaire pour les assertions qui vont au-delà des flux contractuels.
Il doit être qualifié comme extension de recette ou fonction métier partagée.
Les capacités de paiement, inventaire et émission absentes doivent être
identifiées avant de prétendre tester ces parcours de bout en bout.

## 4 Matrice des actions et preuves attendues

Chaque ligne devient une fiche de scénario comprenant acteur, préconditions,
objet/version, commande, résultat attendu, preuve et cas de refus. Statuts de
couverture : à inventorier, disponible, à adapter, absent, qualifié, non testé,
réussi, échec, refus attendu, bloqué, non applicable. Une commande disponible
ne devient pas automatiquement une capacité qualifiée du jeu.

| Domaine | Actions à exercer | Preuve et contrôle |
|---|---|---|
| Identités et droits | Créer les intervenants, affecter les rôles, refuser les accès étrangers | Auteur, acteur métier, entité et droits contrôlés côté serveur |
| Accords | Demander, négocier, valider, activer, suspendre, faire expirer | Contrat/version applicable ; pricing initial bloqué avant préparation |
| Crédit initial | Profils, courbes, recouvrement, limites, collatéral initial | Provenance, mesure de PD et données manquantes explicites |
| Clients | Clients, contacts, affiliations et mandats | Périmètres cohérents et données fictives identifiées |
| Préférences | Déclarations, confirmations et contradictions | Historique conservé ; préférence non transformée en interdiction |
| Interactions | Rendez-vous, messages, relances, fermeture et reprogrammation | Même date virtuelle et lien vers client/contact/mandat |
| Opportunities | Besoin spontané ou proposition proactive d'Alex | Attribution commerciale conservée jusqu'aux transactions |
| Produit | Bibliothèque, brouillon, paramètres requis, calendrier et conservation | Product/version, ordre du panier, paramètres effectifs et unités |
| Payoff | Athena, Phoenix, mémoire, RC puis autres adaptateurs qualifiés | Branches déterministes, égalités aux barrières, coupon/capital/put séparés |
| Marché | Chargement daté, surcharges, absence de données, indisponibilité fournisseur | Informations connues à la date ; cours nus pour fixings ; origine par champ |
| Pricing | Prix direct, solveur, limites de précision | Entrées réellement consommées, seed, N, pas, paiements et intervalle |
| Optimizer | Explorer, confirmer, comparer, conserver/reprendre une recherche | Capacités autorisées, validation indépendante et traçabilité vers le produit |
| Indicatif | Proposition sans exécution et conversion vers RFQ | Aucun faux deal ; termes et contexte conservés |
| AO | Solliciter plusieurs banques, collecter, refuser et réviser les quotes | Même version des termes ; prix/coupon, sens et validité comparables |
| Négociation | Last look, contre-proposition, alternative de payoff | Historique des offres ; alternative identifiée et versionnée |
| Sélection | Comparer économie, crédit, documentation et contraintes | Raison de sélection ; meilleur prix non retenu expliqué |
| Offre client | Présenter prix, marge, émetteur, risques et documents | Version proposée identifiable ; acceptation, refus ou modification explicite |
| Exécution | Bookings liés, émission, acquisition, cession et couverture | Sens, nominal, devise, lien sélection et booking exactement une fois |
| Incident d'exécution | Une jambe échoue, quote expirée, limite dépassée | Position effectivement ouverte et procédure de reprise conservées |
| Positions et trésorerie | Affecter portefeuille, constater primes et règlements | Stocks et cash signés ; marge commerciale distincte du P&L de valorisation |
| Fixings | Initial, observations, fenêtres, validation et correction | Versions officielles ; maker/checker distincts lorsque requis |
| Monitoring | Barrières, watchlist, alertes et données anciennes | Indication distincte du fixing contractuel ; déclenchement daté |
| Lifecycle | Coupons, mémoire, KI, rappel, maturité et résolution | État path-dependent, flux exacts et annulation des observations postérieures |
| Paiements | Constaté, dû, payé, en retard, rapprochement | Créance conservée jusqu'au règlement ; absence de double paiement |
| Relation client en vie | Information, réponse à demande, explication, suivi | Message fondé sur faits connus ; attribution commerciale et relance |
| MtM et Greeks | Marché booking/actualisé, état résiduel et sensibilités | Origine résiduelle, passé réalisé, fixings initiaux conservés |
| Valo Explain | Calculs archivés, comparaison et PDF | Preuves choisies, reproduction, décomposition et résidu explicites |
| CCR | Avant/après, netting, collatéral, stress et limites | Perspective par partie, scénarios communs ; aucune compensation entre sets distincts |
| Marge et crédit en vie | Appels VM, transferts, retard, contestation, dégradation | Règles CSA et exposition ; incident scénarisé distinct d'un défaut de l'application |
| Risque portefeuille | Agrégation, shocks, VaR/ES, concentrations | Sens des positions, périmètre commun, métriques comparables |
| Réinvestissement | Rappel, cash reçu, nouvelle opportunité et structure | Disponibilité réelle du cash ; préférences client et filiation |
| Déclinaisons et amendements | Proposition, validation, application, roll | Termes bookés immuables ; capacités manquantes signalées, aucune annulation/remplacement inventée |
| Documents | Term sheet, confirmation, KID, EMT et notes | Termes/valeurs effectifs ; référence à la preuve applicable |
| IA métier | PayScript, second avis et rédaction | Adoption explicite, valeurs financières conservées, erreurs de prose signalées |
| Administration et audit | Référentiels, historique, calculs et purge de recette | Droits, protections des preuves, nettoyage strict du périmètre |
| Interfaces | Saisie, navigation, restauration, chargement et erreur | Vrais écrans, réponse tardive, doubles clics, clavier et largeur étroite |
| Reprise | Pause, arrêt, fermeture de page et redémarrage | Actions engagées réconciliées ; résultats partiels et couverture manquante visibles |
| Studies et AMC | Import, FIFO, facteurs, analyses, archivage et PDF | Campagne séparée avec oracles indépendants ; statut non couvert tant qu'elle n'est pas exécutée |

## 5 Orchestration et communication entre agents

Le moteur de campagne gère l'horloge, les événements, les destinataires et les
actions. Il s'appuie sur une messagerie persistante et des commandes métier
validées. Chaque message comporte campagne, conversation, émetteur, destinataire,
date virtuelle, horodatage réel, réponse au message précédent, références
d'objet et version des termes. Le texte lisible accompagne les données structurées.

Le cycle est : événement reçu, contexte autorisé chargé, décision structurée,
validation, commande métier, résultat effectif, message de réponse et contrôles.
Une affirmation textuelle n'est jamais une preuve de booking, de prix ou de fixing.
La banque ne voit que ses RFQ et informations communiquées ; Alex garde sa marge
interne ; les agents ne lisent pas le futur du scénario.

Chaque banque a une politique datée de marge, funding, produits acceptés,
durée de validité et négociation. Les hypothèses qu'elle utilise pour calculer
sont conservées avec sa cotation. Les communications des personnages restent
dans la campagne ; les messages commerciaux alimentent les objets Clients
appropriés et les messages techniques restent dans le journal de recette.

Chaque action possède une clé d'idempotence et une version d'entrée. Résultat
métier et notification sont réconciliés après interruption : si le booking a
réussi avant une panne de messagerie, la reprise retrouve le deal au lieu de
le recréer. Les décisions modifiant un même objet sont ordonnées ; calculs et
réponses indépendants peuvent être parallèles. Aucun appel IA/MC ne conserve
une transaction SQLite d'écriture ouverte.

L'identité de l'agent est tracée avec l'utilisateur technique qui exécute.
Une banque simulée ne reçoit pas un rôle administrateur pour pouvoir répondre.
L'adaptateur contrôle ses droits et conserve les contrôles des services/API.
La V1 peut utiliser une file persistante locale et des workers bornés ; un bus
distribué et plusieurs serveurs ne sont pas nécessaires au premier scénario.

Les budgets bornent messages, tours de négociation, appels IA, coûts, calculs
et mémoire. Une sortie IA invalide, un fournisseur indisponible ou une boucle
sans décision produit une erreur qualifiée et une reprise bornée. Les messages
d'autres acteurs sont des informations, pas une autorisation de changer les droits.

Le budget de calcul porte sur toute la campagne : les trois banques ne doivent
pas chacune ouvrir un pool maximal concurrent avec celui du risque. Il inclut
les appels IA locaux et l'admission des calculs existants. Le manifeste conserve
version du code et différences locales pertinentes, version frontend/moteur,
scénario, acteurs, contrats, procédures de Camille, paramètres numériques,
graines, hypothèses, tolérances et métadonnées des réponses IA, sans secrets.
Le rejeu fidèle utilise les décisions et entrées archivées ; une nouvelle
exécution exploratoire crée une variante explicitement liée à la précédente.

## 6 Horloge virtuelle et données de marché

Le contexte de campagne porte la date métier, son fuseau, le scénario, le
marché accessible et l'identité de l'acteur. L'horodatage réel reste utilisé
pour les traces, délais techniques, verrous et authentification. Il n'y a pas
de modification globale de l'horloge du processus ou du système d'exploitation.

États de campagne proposés : brouillon, préparation des contrats, prête,
en cours, en pause, arrêt en cours, terminée, partielle, interrompue, en échec.
La raison de suspension est distincte : calcul, décision IA, contrôle, saisie
de Philippe ou incident. Plusieurs calculs simultanés maintiennent la même
date ; une barrière de dépendances n'est libérée qu'après leurs contrôles requis.

Pour chaque instant, un ordre explicite traite disponibilité du marché,
fixings et observations, flux dus, règlements, valorisations, collatéral,
limites et information commerciale. Les heures, calendriers et conventions
peuvent changer cet ordre ; un fixing de clôture n'est pas disponible le matin.
Les échéances de quotes et de contrats suivent le temps virtuel. Un transfert
ou une réponse volontairement retardés sont des événements futurs du scénario.

Deux modes : marché synthétique contrôlé et rejeu historique daté. Le premier
garantit des branches attendues pour la recette. Le second explore des
conditions observées, avec qualification des données historiques reconstituées.
Les volatilités/dividendes estimés, données implicites absentes et courbes
manuelles gardent leur nature ; une estimation historique n'est pas une cotation.
La fenêtre de calibration antérieure au départ doit être disponible et figée.

Références, valeurs utilisées, changements de fournisseurs, cache et surcharges
sont archivés. Les données postérieures à l'instant courant ne servent pas à
remplir un trou ; une donnée manquante ne devient pas un zéro ou un défaut caché.
Les calendriers figés des deals restent ceux du booking.

Une année ne clôture pas automatiquement des notes de trois ou cinq ans.
Le setup inclut, si nécessaire, un book d'ouverture documenté, des produits
courts et des scénarios de rappel pour exercer maturités et paiements. À la
fin, les positions encore vivantes et créances restant dues sont inventoriées.
L'extension jusqu'au règlement final est une option explicite, pas un saut caché.

## 7 Camille et apprentissage des agents

Camille utilise un catalogue versionné de commandes et capacités : schéma,
unités, acteur autorisé, préconditions, objets affectés, résultat, refus et
procédure de reprise. Ce catalogue relie documentation, code et cas de
qualification. Une API présente mais non qualifiée reste indiquée comme telle.

Camille vérifie les préparations, repère les actions mal formées, explique les
refus et propose les outils adaptés. Il distingue mauvais usage, défaut de
l'application, limite fonctionnelle, donnée insuffisante et incident du banc.
Il respecte l'autonomie commerciale des clients et banques : il ne transforme
pas un refus client ou bancaire légitime en acceptation pour réussir le test.

L'apprentissage porte sur des procédures et mémoires persistantes, sans
réentraînement des poids du modèle. Cycle : incident, explication, règle
proposée, contrôle sur cas ciblé, nouvelle version activée. La campagne conserve
la version applicable à chaque décision. Les faits contractuels et seuils
d'acceptation ne sont pas réécrits pour rendre les résultats conformes.

Trois modes sont prévus : diagnostic sans intervention, coaching avec première
erreur conservée, régression avec procédures figées. On mesure réussite au
premier essai, réussite après aide, nombre d'interventions et récurrence.
Camille peut contenir un incident selon la politique choisie ; toute correction
du code de Structura passe par un chantier de développement séparé.

## 8 Contrôles indépendants et amélioration de Structura

Les contrôles associent invariants métier, scénarios déterministes, oracles
financiers indépendants et recettes d'écran. Agents et Camille produisent des
signalements ; le verdict provient des contrôles et preuves applicables.
Repricer avec le même moteur ne constitue pas, à lui seul, un oracle indépendant.

Une anomalie conserve contexte, acteur, date virtuelle/réelle, commande,
version du contrat, entrée, attendu, observé, preuve, gravité, reproduction,
intervention, cause et état de résolution. Les états séparent signalé,
à reproduire, confirmé, accepté en backlog, corrigé et vérifié après rejeu.
Catégories : application, usage agent, amélioration UX/métier, capacité absente,
données, infrastructure de recette, incident attendu du scénario.

Les preuves comprennent réponses API, instantanés des objets, reçus de pricing,
entrées effectives, calculs, journaux, documents et captures pour les cas UI.
Les symptômes sont regroupés sans perdre les occurrences d'origine. Un incident
de banque simulé n'est un défaut applicatif que si Structura le traite mal.

La boucle d'amélioration est : reproduire, minimiser le scénario, qualifier,
prioriser, corriger dans Structura, ajouter le contrôle pertinent, rejouer,
comparer puis fermer. Le même dossier d'anomalie conserve les preuves avant/après.
Les corrections du banc de recette sont identifiées séparément.

Les indicateurs principaux sont couverture exercée, défauts confirmés et
vérifiés après correction, refus attendus correctement traités, qualité des
rapprochements et stabilité de reprise. Le résultat commercial et la satisfaction
simulée sont secondaires. Les cases non exécutées restent non testées.

## 9 Interface proposée

### Accès et séparation de la recette

Entrée proposée : Administration, carte « Laboratoire de tests », à côté du
Générateur UAT. Le générateur existant reste utilisable ; le laboratoire peut
reprendre ses préparations qualifiées. Nom technique de route à confirmer au lot 0.

La base et les services de campagne sont dans une instance isolée. Le cockpit
et les écrans ordinaires ouverts pour la recette doivent viser cette même
instance, avec session/stockage navigateur distincts lorsque nécessaire. Un
bandeau permanent affiche « RECETTE », campagne et date virtuelle. Aucun lien
« Ouvrir dans Clients/Pricer/Booking » ne doit basculer sur les données réelles.

### Préparation de la campagne

Une liste présente scénarios, périodes, périmètres, résultats, versions et
campagnes précédentes. « Nouvelle campagne » ouvre une préparation par étapes :
acteurs et modes d'Alex ; dates/marché/book d'ouverture ; périmètre des actions ;
contrats et limites ; agents/coaching ; budget et contrôles préalables.

L'écran affiche capacités disponibles/absentes, dépendances, relations prêtes,
données manquantes et coût estimé. « Démarrer » devient disponible seulement
quand les préconditions requises sont satisfaites. Les valeurs proposées
restent des hypothèses visibles ; aucune limite n'est assouplie automatiquement.

### Cockpit de campagne

Le bandeau reste visible : date virtuelle et réelle, phase, état, raison de
pause, activité en cours et calculs attendus. Commandes : pause, reprendre,
prochain événement, avancer jusqu'à une date en traitant les événements,
arrêter avec bilan partiel, exporter. La progression temporelle et la couverture
des tests sont deux indicateurs distincts.

| Espace | Contenu | Action utile |
|---|---|---|
| Vue d'ensemble | Chronologie, actions ouvertes, résultats de contrôle, calculs et files d'agents | Aller au prochain travail ou incident |
| Acteurs et contrats | Parties, rôles, accords, limites, readiness, mémoire/procédures | Examiner un blocage ou l'accord applicable |
| Activité | Échanges regroupés par dossier et interlocuteur ; commandes/résultats associés | Filtrer, ouvrir la preuve, suivre une négociation |
| Dossiers | Opportunity, Product, RFQ, quotes, offres, exécutions et couvertures liées | Ouvrir le même objet dans l'écran de recette |
| Vie et risques | Échéances, fixings, coupons, règlements, cash, positions, MtM et CCR | Examiner un flux, une exposition ou un écart de rapprochement |
| Anomalies et bilan | Signalements, triage, coaching, couverture et comparaison avant/après | Rejouer le cas minimal et vérifier la correction |

La vue d'ensemble réserve l'espace principal à la chronologie et aux dossiers,
avec un volet pour Camille, les tâches bloquées et les incidents prioritaires.
Les messages répétitifs sont regroupés ; une commande et ses preuves restent
accessibles. Les suggestions d'amélioration ne prennent pas la place des
anomalies bloquantes. Le détail technique est dépliable.

Maquette de structure, sans implémentation :

```text
Laboratoire de tests    RECETTE    Campagne sélectionnée
Date virtuelle   Phase   Pause pour calcul   Temps réel écoulé
Pause / Reprendre   Prochain événement   Arrêter   Exporter
Contrats prêts   Contrôles exercés   Défauts confirmés   À vérifier

Vue d'ensemble | Acteurs et contrats | Activité | Dossiers | Vie et risques | Bilan

Chronologie et dossiers                    Camille et tâches en attente
Client -> Alex -> AO -> banques             Calculs requis à terminer
Actions métier et résultats                 Incidents prioritaires
Flux, paiements et relances                 Prochaine décision

Objet sélectionné : termes / actions / résultats / preuves / incidents
```

### Recette de l'interface

Utiliser le thème institutionnel clair, les composants et unités existants.
Les états comportent libellé et icône, sans dépendre uniquement de la couleur.
Les prix, intervalles, marges, sens, devises, dates et modèles sont lisibles.
Un état vide distingue aucune activité, absence de donnée et erreur.

Tester desktop et largeur étroite, clavier, focus, chargement, erreur,
déconnexion, rechargement, changement de campagne, réponses tardives, double
clic et navigation aller-retour. La fermeture de la page ne perd pas le run.
Les données sensibles suivent les conventions existantes et le Mode Démo.
Archive/purge utilisent une confirmation avec périmètre concret ; archiver
conserve les preuves, purger supprime uniquement le périmètre autorisé.

## 10 Plan de livraison par lots

| Lot | Livraison | Dépendances | Critère de sortie |
|---|---|---|---|
| 0 | Inventaire des commandes, droits, dates, capacités et scénarios ; conventions d'Alex et maquette | Cadrage présent | Matrice reliée aux consommateurs, manques priorisés et périmètre pilote explicite |
| 1 | Instance/base isolée, campagne persistante, horloge et reprise ; shell du cockpit | Lot 0 | Aucun accès aux données réelles ; pause calcul et reprise sans action dupliquée |
| 2 | Préparation des acteurs, contrats, limites et relations ; écran de readiness | Lot 1 | Zéro pricing/RFQ de jeu avant readiness ; droits et accords applicables revérifiés |
| 3 | Clients, messagerie et commandes ; agents déterministes ; premier AO complet | Lot 2 | Contexte client intact, quotes comparables, sélection/acceptation et refus tracés |
| 4 | Opérations liées, positions et règlements ; distribution puis émission/couverture selon capacité | Lot 3 et qualification des fonctions manquantes | Sens et flux rapprochés ; échec d'une jambe visible ; booking exactement une fois |
| 5 | Année virtuelle, lifecycle, MtM, CCR, collatéral et suivi/réinvestissement client | Lot 4 | Événements exécutés aux bonnes dates, état hérité, cash/créances et risques rapprochés |
| 6 | Camille, IA exploratoire, apprentissage versionné et triage des défauts | Commandes qualifiées des lots 2 à 5 | Mauvais usage corrigé sans masquer un bug ; limites et premières erreurs conservées |
| 7 | Recettes des vrais écrans, export/rejeu, comparaison après correction et benchmark | Lots précédents | Campagne complète avec couverture explicite, preuves avant/après et performance mesurée |

Le contrôleur déterministe et la remontée des anomalies commencent au lot 1.
Camille peut être présent avec des règles fixes dès les premiers lots ; les
dialogues IA et mémoires apprises arrivent après la fiabilisation des actions.
Le cockpit progresse avec chaque lot, sans attendre la fin pour voir les preuves.

Le pilote proposé utilise EUR, GBM, deux clients aux mandats différents et trois
banques simulées. Il inclut demande client, proposition proactive, AO avec
amélioration, refus de crédit attendu, opération liée, coupon/rappel ou maturité,
MtM expliqué et proposition de réinvestissement. Le book d'ouverture et le
marché synthétique assurent les branches nécessaires. La volumétrie est fixée
après estimation mesurée ; aucune promesse de toute la couverture en deux heures.

## 11 Scénarios de refus et incidents à prévoir

| Famille | Cas indispensables |
|---|---|
| Contractuel | Accord non actif, expiré, produit hors périmètre, garantie absente, netting non opposable |
| Commercial | Client refuse, préférence contredite, mauvais mandat, attribution perdue, relance oubliée |
| Pricing | PARAM requis manquant, série mal dimensionnée, convention absente, donnée ancienne/manquante, prix non concluant |
| AO | Quote expirée, alternative non comparable, mauvais sens/devise, doublon, réponse tardive, amélioration non enregistrée |
| Exécution | Acceptation sur ancienne version, double clic, premier deal traité et second refusé, limite concurrente dépassée |
| Lifecycle | Fixing manquant, rejet checker, correction officielle, rappel à maturité, mémoire non payée, événement passé non rejoué |
| Règlement | Flux constaté non payé, paiement partiel/en retard, doublon, créance après rappel, trésorerie insuffisante |
| Crédit | MtM absent, funding incompatible avec CCR clean, collatéral inconnu, VM tardive, données PD impropres à une CVA marchande |
| Technique | IA indisponible, sortie invalide, calcul trop long, fermeture UI, redémarrage après exécution avant notification |
| Interface | Champ masqué conservé, prix d'ancien dossier affiché, navigation perdant l'état, erreur API illisible |

Un défaut bancaire ou client est injecté comme événement connu du scénario.
Sa prise en charge est évaluée, sans prétendre simuler un processus de défaut
ou un close-out réglementaire complet si les fonctions ne sont pas qualifiées.

## 12 Critères de validation et budget

- Chaque scénario sélectionné a un résultat attendu et un moyen de le vérifier.
- La préparation contractuelle bloque toutes les premières commandes concernées.
- La date virtuelle reste fixe pendant toute action bloquante ; l'heure réelle
  continue. Expiration de quotes, fixing et paiement suivent les bons temps.
- Les rôles, versions de termes, liens commerciaux et identités traversent les modules.
- Positions et flux de chaque jambe sont signés, rapprochés et non dupliqués.
- Les refus attendus sont expliqués et n'améliorent pas artificiellement le hit ratio.
- Aucun état corrigé par Camille n'efface le premier échec.
- Les assertions de prix utilisent des références indépendantes adaptées et
  des tolérances fixées avant mesure ; le biais temporel est distinct de l'IC MC.
- Prix d'émission, funding, marge et CVA ne sont pas déduits deux fois.
- Pause, arrêt et reprise conservent résultats partiels et commandes engagées.
- Les liens de recette ouvrent la bonne campagne et la bonne base.
- La fin de campagne publie positions vivantes, créances, événements non traités,
  scénarios non testés et incidents ouverts ; elle ne signifie pas zéro risque.

Le benchmark mesure temps total, préparation, IA, pricing, risques, UI, files
d'attente, ressources et coût des appels. La cible d'une à deux heures se
rapporte à un setup/version matériel précis. Une réduction de couverture ou
de précision pour respecter ce budget exige une variante de campagne explicite.
Les délais produisent un bilan partiel plutôt qu'un succès artificiel.

Pendant le développement, tests ciblés par lot depuis la racine. Après une
modification Vue, `npm run build` dans `frontend/`. La suite backend complète
reste réservée à une demande explicite de Philippe, conformément à CLAUDE.md.
Les bases de tests et serveurs temporaires suivent les règles du dépôt.

## 13 Décisions de conception encore à préciser

Les principes précédents sont retenus ; ces choix doivent être fermés au lot 0 :

1. Représentation de l'émission propre, de l'inventaire et du règlement : services
   disponibles, extensions métier nécessaires et oracles. Aucun faux parcours réussi.
2. Distribution du cockpit et des écrans de recette : instance locale dédiée,
   stockage/session isolés et accès administrateur du pilote.
3. Jeux de contrats et profils de crédit synthétiques, conventions de marge,
   limites d'Alex et état du book d'ouverture.
4. Volume pilote, budget par commande et cadence des CCR complets, avec
   contrôles aux événements critiques et couverture quotidienne explicite.
5. Fournisseur/modèle IA, capacité du poste, budgets et politique de coaching.
   Le premier parcours déterministe reste reproductible sans appel IA.
6. Durée de conservation, format d'export des preuves et procédure de purge.

Avant développement, relire la matrice contre l'inventaire réel des commandes
et matérialiser les transitions et écrans de chaque lot. Les nouvelles demandes
entrent dans le périmètre/version de campagne et la matrice, pas seulement dans
le prompt d'un agent.

## 14 Références de conception

- [Conventions du projet](../../../CLAUDE.md).
- [Objet Product](PLAN_IMPLEMENTATION_OBJET_PRODUCT.md).
- [Socle IA](IA_COMMUNE_2026-09-17.md).
- [Organisations et accès](ORGANIZATION_ACCESS_DESIGN_2026-09-24.md).
- [CCR économique](../pricing/CCR_IMPLEMENTATION_2026-09-28.md).
- [Portefeuille notes et OTC](../pricing/SA_CCR_PORTEFEUILLE_MIXTE_ROADMAP_2026-09-29.md).
- [Doctrine Clients](../clients/CLIENTS_LOT_0_DOCTRINE_METIER.md).
- [Chaîne commerciale](../clients/CLIENTS_LOT_1_CHAINE_COMMERCIALE.md).
- [Clients et lifecycle](../clients/CLIENTS_LOT_3_INTEGRATION_LIFECYCLE.md).
- [MtM quotidien](../lifecycle/BOOKING_MTM_QUOTIDIEN_2026-09-17.md).
- [Valo Explain](../lifecycle/VALO_EXPLAIN_2026-09-17.md).
- [Gouvernance des amendements](../../reference/GOUVERNANCE_AMENDEMENTS.md).
- [Générateur UAT](../../audits/AUDIT_GENERATEUR_UAT_2026-10-07.md).
- [PayScript](../../reference/PAYSCRIPT_REFERENCE.md).

L'inventaire technique du lot 0 part notamment de `api/deals.py`, `api/rfq.py`,
`api/ccr.py`, `api/clients.py`, `api/interactions.py`, `api/client_intelligence.py`,
`core/product/`, `core/ccr/`, `services/product_repository.py`,
`services/uat_generation.py`, `services/lifecycle_alerts.py`,
`services/optimizer_research.py`, `services/llm/`, `core/compute/`, `main.py`,
`frontend/src/router/index.js`, des vues correspondantes et `frontend/src/style.css`.
