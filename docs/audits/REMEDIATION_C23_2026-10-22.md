# C23 — Cotations, tours RFQ et exécutions réseau

Livraison locale du **22 octobre 2026**, sans commit ni push. Les six constats
C23 sont corrigés ; contrôles C01/C03/C06 et condition C04 préservés et réexercés.
Branche `codex/hybrid-saas-foundation`, HEAD
`7dce3021a88feb4f0021ca3de8f3596277bc72a5`. Aucun serveur démarré ni accès à la base réelle.

## Comportements obtenus

| Constat | Correction et preuve ciblée |
|---|---|
| M09-02 | `history_eligible` distingue l’observation historique de `comparable`, réservé aux réponses actuellement sélectionnables. Les réponses conformes `RESERVED` et `ROUND_CLOSED` restent dans l’analyse, avec leur gain ; révisions remplacées, réponses retirées/conditionnelles et devises divergentes sont exclues. |
| M09-03 | Une cotation manuelle porte une révision, conservée dans l’audit avant/après. Une modification matérielle invalide la sélection et son motif. La sélection stocke la révision exacte ; traitement, revue et booking la recontrôlent. Un last look devenu moins favorable que l’originale révisée est conservé, expiré et désélectionné ; aucune suppression de sa réponse. |
| M09-04 | La devise est reprise explicitement des termes Product figés lorsqu’elle manque. Une quote USD sur une RFQ EUR reste visible mais n’est pas sélectionnable ni bookable comme conforme. Aucune conversion implicite ; une contre-proposition contractuelle exige un nouveau tour. |
| M09-07 | Le graphique annonce et calcule une moyenne quotidienne de toutes les observations admissibles du fournisseur, avec leur nombre dans l’infobulle. +100/−300 pb donnent −100 pb, dans les deux ordres. L’extrait initial donnait −300 puis +100 : reproduction archivée. |
| M09-08 | Chaque patch normalise les heures en UTC et valide le couple final cotation/validité après fusion. Modifier uniquement `quoted_at` au-delà de `valid_until` est refusé. `created_at` reste la date de saisie. |
| M10-01 | « Sans suite » clôture durablement le tour figé. `auto` ne peut le réouvrir ; les cotations anciennes restent inactives. Un nouveau dossier/tour lié est envoyé explicitement. Sur deux bases, ancien tour fermé et nouveau tour ouvert convergent, avec identifiants et historique locaux conservés. |

Une note seule conserve la révision commerciale et la décision. Répéter une
mise à jour identique ne crée ni nouvelle révision de quote ni révision Product.
Les écrans envoient la révision affichée ; deux éditions concurrentes du même
état donnent une réussite et un conflit 409. Une réponse tardive ne modifie pas
un autre dossier. L’état de décision et les last looks invalidés reviennent du
serveur dans la réponse du patch ; l’interface n’invente pas la décision.

## Dépendances et transitions

- **C01** : habilitations réelles de lecture/préparation/sélection/booking et cloisonnement des calculs privés maintenus. Les fixtures C23 accordent explicitement leurs droits ; aucun contrôle de production assoupli.
- **C03** : rapprochements juridiques par identifiants locaux, indépendants des libellés ; refus si mapping absent ou inactif. La révision réseau conserve le mapping de la première réponse.
- **C06** : devise et version contractuelle lues depuis le Product figé de la RFQ. Une révision commerciale ne change ni l’identité Product, ni ses termes ; la projection RFQ est synchronisée avec la décision révoquée.
- **C04 → C23** : contrôles sur la position résultante réexercés via les tests de booking et d’amendement économique, avec refus atomiques et concurrence. Aucun nouveau domaine CCR n’est déclaré qualifié.
- **C08** : reprises réseau, accusé perdu, livraison dupliquée, bail du worker, booking RFQ idempotent et concurrence vérifiés sur le sous-ensemble utile. **C08 reste ouvert** pour ses trois constats : clé d’intention de création Product, booking direct sans Product préalable et nouveau dossier depuis un calcul déjà exécuté. Aucune clôture globale par déduction.

La clôture et son audit appartiennent à la transaction RFQ locale ; la file
durable existante transmet ensuite le fait. La réception ne réactive jamais
un tour fermé. Un successeur d’un ancien dossier « sans suite » dont le tour
était encore `OPEN` préserve aussi la clôture, sans intervention manuelle SQL.
Les publications réseau restent immuables : leurs révisions créent des quotes
distinctes et ne transfèrent pas la sélection à la nouvelle réponse.

## Migration et conservation

Migration additive : `rfq_quotes.revision` et
`rfq_requests.selected_quote_revision`. Les quotes anciennes commencent à r1 ;
les anciennes décisions ne reçoivent aucune qualification inventée. Avant un
nouveau traitement ou booking, le desk doit **Retenir à nouveau** la révision.
Les anciens accords demandés mais non finalisés dont la sélection n’est pas
qualifiée exigent une revue explicite ; aucune preuve existante n’est réécrite.
Les deals déjà bookés et leurs preuves restent consultables.

Les valeurs d’une cotation manuelle révisée sont conservées dans les événements
d’audit avant/après ; la ligne courante garde son identifiant et sa révision.
Ce correctif ne crée pas une seconde table d’archives de quotes et ne prétend
pas ajouter une immutabilité SQL générale au journal d’audit. Les archives de
valorisation, preuves réseau, correctifs précédents et fichiers dist existants
sont conservés.

## Validation mesurée

- État initial : **38 tests RFQ existants passent**. Les **8 reproductions backend valides échouent** sur les défauts attendus ; les premiers essais de fixtures invalides sont conservés séparément et exclus de cette preuve. Le défaut du graphique est reproduit à partir de l’extrait exact de la source initiale et de son SHA-256.
- État final : **271 cas backend distincts réussis dans 12 fichiers**, dont **32 cas C23 nouveaux**. Le dernier passage RFQ compte 70 réussites ; les 201 cas de dépendances sont réussis. Les résultats distincts sont conservés dans `latest-distinct.xml`.
- Un passage intermédiaire de 270 cas compte 269 réussites et un défaut de fixture : accès depuis un thread à un objet SQLAlchemy expiré de la session principale. L’identifiant est désormais capturé avant les threads ; le contrôle avec barrière de concurrence passe. Ce défaut de fixture n’est pas présenté comme une anomalie métier.
- **674 tests frontend dans 76 fichiers**, dont **12 nouveaux cas**, puis build Vite temporaire réussis. Aucun build dans `frontend/dist`.
- Les cas couvrent révisions, motifs, note seule, reprise identique, concurrence, devise, horaires, last look, clôture, successeur, publications réseau et migration additive/idempotente.
- Bases synthétiques isolées, clés étrangères actives pour les parcours réseau, concurrence sur une copie SQLite temporaire. Garde requests/curl active, **zéro tentative externe** dans les passages finaux ; HTTPX utilise un transport simulé pour les deux bases.

Les entrées, résultats, empreintes, commandes et contrôles de conservation sont
dans [C23_VALIDATION.json](remediation-lot-0-2026-10-20/C23_VALIDATION.json) et
`.runtime/diagnostic-acceptance/c23-2026-10-22/`.

## Limites et suite

T12 est validé sur le périmètre applicatif local exercé, mais reste **partiel**
pour la qualification déployée. Les tests à deux bases utilisent le protocole
signé et HTTP simulé ; ils ne prouvent ni TLS, ni DNS, ni synchronisation des
horloges de deux services, ni interaction graphique réelle. Aucune négociation
réelle ni migration de données d’exploitation n’a été effectuée. Une copie
d’exploitation devra être vérifiée avant déploiement, notamment les sélections
anciennes à requalifier et les accords en attente. C08 reste un chantier ouvert.

La suite du registre conserve les dépendances existantes. Le périmètre C23 ne
clôt ni l’audit global ni la qualification de production.
