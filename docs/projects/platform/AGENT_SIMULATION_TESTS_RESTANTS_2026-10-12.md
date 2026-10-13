# Simulation entre agents — tests restants et reprise RFQ

Date : 12 octobre 2026. Cette note accompagne la livraison du pilotage de campagne,
du rapprochement des books et de l'ouverture des installations en consultation.
Elle sert de feuille de recette pour les prochains chats. La publication dans
`main` ne signifie pas que la campagne annuelle, tous les produits ou tous les
scénarios de risque sont qualifiés.

Le prochain chantier demandé par Philippe est **l'échange automatique de prix
lors des RFQ entre les installations Structura**. Il sera développé dans une
autre branche, à partir d'un autre chat. Les tests RFQ décrits ci-dessous restent
à réaliser après cette implémentation ; ils ne sont pas présentés comme livrés.

Actualisation du chantier RFQ : le [lot 6](RFQ_NETWORK_LOT_6_IMPLEMENTATION_2026-10-12.md)
sur `codex/rfq-network-lot-0` réalise désormais les échanges signés et la reprise,
avec recette sur deux serveurs fictifs indépendants. Leur utilisation par les agents
de campagne n’est pas intégrée à ce stade ; les scénarios de simulation ci-dessous
restent à qualifier après la confirmation de traitement du lot 7.

## Acquis à conserver

| Validation déjà réalisée | Résultat et portée |
| --- | --- |
| Backend du module | 68 tests ciblés passent : agents, gestion des campagnes, rapprochement et consultation. La suite backend complète n'a pas été demandée. |
| Frontend | 380 tests passent ; build effectué après les modifications Vue. |
| Campagne avec modèle réel | Essai `2c09009e5b984e43aaabef795ba26561`, Qwen2.5-Coder 7B via Ollama, arrêté à la demande de Philippe au début du sixième mois. |
| Books de cet essai | Cinq dossiers reverse convertible, 50 M€ de volume client, vingt écritures natives rapprochées et réglées. BNP : cinq deals ; Hector : dix ; client : cinq. |
| Valorisation | 105 MtM natifs archivés ; vingt fixings officiels. Aucun remboursement final n'est démontré par cet essai arrêté avant les maturités. |
| CCR | Quatorze calculs natifs sur des calls OTC hypothétiques, dans un périmètre distinct des notes. Ce ne sont pas les AR produit du Pricer. |
| Consultation | Booking, restauration des MtM à la date figée et historique ouverts pour BNP/Hector ; blocage des écritures et fermeture vérifiés. Bases des acteurs et fichier de campagne identiques par SHA-256 ; compteur IA inchangé. |

Voir le [bilan de l'essai](AGENT_SIMULATION_BILAN_2026-10-12.md), la
[livraison du pilote](AGENT_SIMULATION_PILOT_2026-10-12.md) et la
[consultation après arrêt](AGENT_SIMULATION_CONSULTATION_2026-10-12.md).
Les preuves d'exécution restent locales dans les installations isolées ; les
bases, clés de session et secrets de contrôle ne sont pas publiés dans Git.

## Règles communes de recette

- Utiliser des bases et campagnes isolées. Ne pas préparer, nettoyer ou corriger
  un scénario dans `backend/data/structura.db`.
- Conserver la graine, la configuration, le modèle, les versions des termes,
  l'empreinte des sources, les décisions et les reçus des API natives.
- Distinguer une recette native aux décisions imposées d'une exécution avec
  décisions IA réelles. Un scénario imposé aide à couvrir une branche du payoff,
  mais ne démontre pas l'autonomie des agents.
- Vérifier les objets et calculs persistés dans Structura : une conversation,
  un compteur ou un HTTP 200 ne suffit pas à prouver un booking ou un paiement.
- Garder les refus attendus dans la recette ; ne pas changer les droits ou
  contrats pour forcer une banque à coter ou le client à accepter.
- Relever les empreintes avant et après chaque recette de consultation. Toute
  variation due à une activité extérieure doit être expliquée, pas écrasée.
- Ne pas relancer l'ensemble des tests. Choisir les tests du domaine modifié ;
  une suite complète reste soumise à une demande explicite de Philippe.
- Ne pas lancer une nouvelle année IA avant une recette courte, un budget de
  temps et un motif précis. Aucun essai IA n'est lancé par cette note.

## Lots prioritaires du module livré

| Lot | Priorité | État / prérequis | Tests restants et critères de validation | Impact métier |
| --- | --- | --- | --- | --- |
| SIM-01 — Cycle complet court | P0 | Les API natives existent ; le parcours IA jusqu'au paiement final reste à démontrer. Préparer une avance du calendrier explicite si nécessaire. | Un ou deux dossiers : RFQ, acceptations, quatre jambes, règlements, MtM, fixings échus, propositions validées/appliquées, coupons et paiement final. Constater les flux natifs et la clôture, sans correction manuelle des décisions. Aucun événement échu oublié ; aucune position active après sa clôture appliquée. | Démontrer rapidement une autonomie complète et détecter les blocages avant un essai annuel. |
| SIM-02 — AR produit | P0 | L'outil du Pricer existe ; son utilisation par la simulation reste à intégrer et à qualifier. | Appeler l'Analyse du risque sur le produit réellement pricé et sa version ; conserver résumé, payoff, sensibilités utilisées, réponse et provenance modèle. Qualifier les Greeks/stress natifs séparément du commentaire IA et du CCR. | Vérifier le risque des notes effectivement traitées. |
| SIM-03 — Discours et supervision | P0 | Défaut constaté sur le modèle 7B ; garde-fous à renforcer. | Injecter des argumentaires erronés, notamment « barrière 60 % = perte maximale 40 % ». Le superviseur doit signaler et corriger l'interprétation à partir du payoff natif, sans inventer une garantie, un prix ou une sensibilité. Tester coupon conditionnel, mémoire, rappel et risque émetteur. | Éviter qu'un workflow réussi véhicule une fausse promesse commerciale. |
| SIM-04 — Audit des refus | P0 | Correctif à réaliser : un refus natif perd actuellement les métadonnées modèle. | Déclencher un refus légal, un échec API et un timeout modèle. Conserver la décision obtenue et ses métadonnées quand seule l'API échoue ; distinguer absence de décision et rejet d'une décision. Aucun token de connexion dans les preuves exportées. | Rendre chaque succès et refus explicable et vérifiable. |
| SIM-05 — Durée et appels inutiles | P1 | Mesure disponible ; orchestration à améliorer. | Comparer la même recette avant/après : durée totale, temps modèle/API, nombre d'appels, opérations sans avancement et latences par acteur. Ne pas solliciter le modèle sans tâche ou information nouvelle. Les choix commerciaux restent libres. Fixer et valider un budget avec Philippe avant l'année complète. | Rendre la simulation utilisable et limiter le coût des diagnostics. |
| SIM-06 — Diversité du payoff | P1 | Couverture native partielle ; nouvelle matrice de recettes nécessaire. | RC et Phoenix, rappel et absence de rappel, coupon payé/non payé, mémoire, scénario sous barrière et remboursement défavorable. Comparer flux réalisés et payoff contractualisé, pas uniquement le statut final. Distinguer cas imposés et choix IA. | Éviter de généraliser cinq RC gagnés par une seule banque. |
| SIM-07 — Gestion et consultation | P1 | Tests ciblés et recette BNP/Hector déjà passés ; cas opérationnels supplémentaires. | Serveur contrôleur redémarré avec une consultation ouverte, deux acteurs consultés simultanément, popup bloquée, compte désactivé, book absent, serveur de consultation indisponible, plusieurs clics d'ouverture/fermeture. Le verrou OS interdit reprise/suppression pendant la consultation ; aucun changement des books ; aucun appel IA. | Permettre une inspection fiable des anciennes campagnes. |
| SIM-08 — Reproductibilité et historique | P1 | À qualifier ; une même graine ne garantit pas les mêmes décisions LLM. | Rejouer les mêmes inputs et comparer le marché, les calendriers et les calculs natifs. Conserver séparément les écarts de décisions IA. Vérifier exports, historique complet, source des fixings, pagination, filtres et liens vers les preuves. | Retrouver et expliquer un résultat de recette. |
| SIM-09 — Année complète | P1 | Après SIM-01 à SIM-05 et validation du budget. | Une exécution vierge jusqu'à toute la période, sans reprise humaine ; rapprochement de chaque dossier ou refus explicite, revues à la dernière date, règlements et événements échus traités. Les produits postérieurs à l'horizon restent correctement ouverts. Vérifier la fermeture des installations. | Qualifier l'autonomie sur la durée sans confondre fin de campagne et maturité de tous les produits. |
| SIM-10 — Périmètres complémentaires | P2 | Certaines fonctions de scénario restent à développer. | Appels de marge, défaut de contrepartie, émission propre Hector et couverture OTC, réinvestissement, données historiques. Définir d'abord instruments, accords, flux et assertions applicables ; ne pas convertir les notes en exposition OTC par simple présence d'ISDA/CSA. | Étendre la couverture avec des responsabilités et risques correctement définis. |

## Futur échange automatique de prix RFQ — autre branche, autre chat

Ce lot est un **nouveau développement**, séparé de la livraison actuelle.
Branche proposée pour le prochain chat : `codex/automatic-rfq-price-exchange`,
à créer depuis `main` après intégration de cette livraison. Le présent chat ne
démarre pas ce développement et ne crée pas le prochain chat.

La cible est : **RFQ dans le Structura d'Hector → réception dans le Structura
de la banque → pricing natif local → réponse de prix ou refus → retour automatique
dans la RFQ d'Hector**. Le choix de banque, la marge et l'acceptation restent des
décisions explicites. Les messages actuels du pilote ne démontrent pas ce flux
natif de transport entre entités.

Relire le [besoin inter-entités](INTER_ENTITY_RFQ_BACKLOG_2026-10-08.md) et les
documents Product avant de coder. Conserver une identité d'échange commune,
les références locales et la version/empreinte des termes. Les hypothèses de
pricing et les marges internes restent privées ; elles ne sont pas des termes
contractuels à transmettre automatiquement.

Le [plan de réalisation du 12/10](RFQ_NETWORK_ACTION_PLAN_2026-10-12.md) et la
[spécification du lot 0](RFQ_NETWORK_LOT_0_SPECIFICATION_2026-10-12.md) précisent
désormais la cible et les règles actées de fermeté, retrait et confirmation.
La matrice ci-dessous couvre aussi la confirmation native et le rapprochement
bilatéral ultérieurs ; la V1 de retour automatique des prix peut consigner une
confirmation externe ou un accord téléphonique déclaré avant booking local.

| Test | Priorité | Scénario et validation attendue |
| --- | --- | --- |
| RFQ-01 — Aller-retour natif | P0 | Hector envoie depuis sa RFQ ; BNP reçoit un dossier local, utilise son Pricer et répond. Hector reçoit automatiquement une cotation liée à sa RFQ, sans recopie de prix. Preuves persistées dans les deux installations. |
| RFQ-02 — Intégrité Product | P0 | Identité d'échange, version des termes et empreinte identiques de bout en bout. Vérifier script, paramètres effectifs, sous-jacents, notionnel, devise, sens, dates, calendrier et format. Une variation matérielle crée une version/renégociation explicite, pas un remplacement silencieux. |
| RFQ-03 — Convention de prix | P0 | Distinguer prix moteur et prix proposé. Tester prix en % du pair, fractions internes, unités et sens BUY/SELL vus par chaque partie. Vérifier validité, prix indicatif/ferme et conditions ; rejeter une convention absente ou ambiguë. |
| RFQ-04 — Droits et confidentialité | P0 | Seules les parties destinataires autorisées voient la demande et la réponse. Une banque ne voit ni le book d'Hector, ni sa marge de revente, ni les cotations concurrentes. Mauvaise identité, session et autre campagne refusées. Aucun secret dans payload, journal ou export. |
| RFQ-05 — Relation et refus | P0 | Relation complète, relation incomplète, limite/périmètre/document requis manquant et refus volontaire. Appliquer les mêmes contrôles qu'en UI et distinguer refus commercial/légal d'une panne réseau. Les autres banques peuvent poursuivre. |
| RFQ-06 — Idempotence | P0 | Répéter demande, réception et réponse, y compris après timeout et redémarrage. Une référence de message traitée ne crée ni doublon de RFQ/cotation ni deal supplémentaire. Un retry conserve la preuve originale et son résultat. |
| RFQ-07 — Péremption et révision | P0 | Réponse expirée avant acceptation, retirée, retardée ou calculée sur une ancienne version : empêcher une nouvelle acceptation et afficher le motif. Une acceptation valide reçue avant expiration et retrait réserve le prix ; un accord confirmé peut être booké après expiration sans proroger la quote. Tester retrait/acceptation concurrents, nouvelle cotation et renégociation en conservant les preuves. |
| RFQ-08 — Acceptation et booking | P0 | La sélection/acceptation est explicite. Confirmer la version et la cotation retenues dans les deux parties ; rapprocher banque SELL/Hector BUY puis Hector SELL/client BUY. Aucun booking déclenché par une simple réponse de prix. Refuser tout changement des termes acceptés. |
| RFQ-09 — Plusieurs banques | P1 | BNP, SG et CA répondent/refusent indépendamment, dans un ordre variable. Conserver toutes les réponses autorisées et le statut par destinataire ; permettre un choix motivé sans imposer un gagnant ni atteindre artificiellement les objectifs de marché. |
| RFQ-10 — Pannes et reprise | P1 | Banque hors ligne, arrêt pendant envoi/pricing/réponse, interruption du contrôleur et reprise. Afficher reçu/en cours/en échec/à reprendre ; les accusés techniques et la réponse métier restent distincts. Réconcilier une réponse déjà traitée mais dont l'accusé s'est perdu. |
| RFQ-11 — Booking asymétrique | P1 | Une partie a booké, l'autre échoue ou conteste la confirmation. Signaler et conserver l'écart, ne pas annoncer un dossier complet. La reprise réutilise la confirmation d'origine et n'ajoute aucune jambe en double. |
| RFQ-12 — Interface et preuves | P1 | Depuis les deux RFQ, montrer parties, versions, derniers statuts, prix, validité, historique et refus. Relier réponse, pricing, acceptation et deal. Sur desktop/mobile, aucune action silencieuse, aucun statut de réussite fondé seulement sur un message. |
| RFQ-13 — Régression après transport | P1 | Vérifier Product, RFQ local, booking, règlements, MtM, consultation et rapprochement avec le nouveau transport. Les anciens dossiers et leurs archives restent consultables. Réseau désactivé : le workflow existant reste explicite. |

Le premier scénario RFQ doit être un aller-retour Hector–BNP court, puis un refus
CA et une cotation SG concurrente. Avant d'étendre les campagnes, couvrir
expiration, doublon et panne/reprise. Le transport local de recette ne vaut pas
validation d'une connexion à une banque externe réelle.

## Définition de fin de recette

Chaque fiche de test doit contenir : ID du test et du scénario, prérequis,
installation/acteur, configuration/graine/modèle, version des sources, actions,
résultats natifs attendus et observés, preuves, durée et décision PASS/FAIL/BLOCKED.
BLOCKED précise le développement manquant ; un indicateur EXERCISED ne devient
pas automatiquement PASS.

Pour le futur lot RFQ, une livraison peut être qualifiée après RFQ-01 à RFQ-08,
puis les contrôles de pannes et de non-régression applicables. La recette du
transport ne valide pas à elle seule la qualité des décisions IA, les AR produit
ou l'année complète. Les défauts connus du bilan restent ouverts jusqu'à leur
propre validation.

Commandes ciblées disponibles pour une reprise ultérieure, **sans les exécuter
automatiquement lors de la publication de cette note** :

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_agent_workshop.py backend/tests/test_workshop_management.py backend/tests/test_workshop_reconciliation.py backend/tests/test_workshop_consultation.py -q
.venv/Scripts/python.exe scripts/check_workshop_consultation_ui.py backend/data/agent_workshop/<campagne-arrêtée>
.venv/Scripts/python.exe scripts/check_workshop_campaign.py backend/data/agent_workshop/<campagne-terminée>
```

Après une modification Vue, lancer le build frontend conformément à `CLAUDE.md`.
Pour le nouveau transport, ajouter des tests ciblés de ses endpoints et de ses
transitions ; sélectionner la portée de non-régression selon les changements,
sans déclencher toute la suite backend par défaut.
