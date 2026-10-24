# Rapports sources des audits des modules 1 à 17

Ces textes reprennent les conclusions rendues dans la conversation **Proposer une séquence d'audit**, chat `01a1540a-fff0-70c1-8bc5-e21d30a77d18`, le 19 octobre 2026. Les identifiants de section ont été ajoutés pour la traçabilité. Les textes sont des rapports d'audit, pas des journaux bruts d'exécution ni des preuves nouvelles au 20 octobre.

Les réserves des rapports demeurent applicables. Les chemins absolus et numéros de ligne désignent l'état examiné à leur date. Les citations de mémoire propres au fonctionnement de l'assistant sont exclues de cette copie.

[Registre consolidé](ANOMALY_REGISTER.md) · [Critères et dépendances](DEPENDENCIES_AND_VALIDATION.md)

## M01

**Le socle d’isolation est bien construit, mais le module n’est pas encore cohérent pour un usage métier à plusieurs collaborateurs.** Les principales faiblesses concernent les permissions sur certaines actions sensibles, le parcours Opérations et la reprise des dossiers entre collègues.

L’audit porte sur l’état local de `codex/hybrid-saas-foundation`, avec ses changements non commités, au **19 octobre 2026**. J’ai examiné l’authentification, les services hybrides, les sessions navigateur, les contrôles d’accès métier et les tests existants, avec un inventaire statique de 403 déclarations de routes API. Les bases ont été ouvertes exclusivement en lecture seule. Aucun code modifié, service démarré ou test exécuté.

**État des installations constaté**

Les six installations métier présentent chacune :

- une identité d’installation et d’organisation conforme à leur manifeste ;
- quatre comptes actifs : Super utilisateur, Front, Opérations et Contrôleur ;
- deux desks et huit appartenances aux desks ;
- aucun compte rattaché à une organisation étrangère ;
- aucun Product, Deal, RFQ, script, document ou portefeuille dans les tables contrôlées.

Les identités, répertoires et ports des sept installations principales sont distincts. L’administration centrale et le workspace Admin complet sont séparés des six bases métier. Cette photographie confirme leur configuration sur disque ; les parcours métier ci-dessous sont analysés dans le code.

**Les points solides**

| Point | Appréciation |
|---|---|
| **Isolation des installations** | Manifestes stricts, répertoires privés, clés locales et contrôle de l’identité de la base avant migration dans les installations métier. Une base étrangère est refusée. |
| **Authentification serveur** | Vérification de la signature, de l’expiration, de l’émetteur, du destinataire et de l’organisation. Le compte actif et son rôle sont relus en base à chaque requête authentifiée. |
| **Séparation des administrations** | Le super utilisateur métier ne peut pas attribuer le rôle technique `admin`, déplacer un compte vers une autre organisation ou utiliser le navigateur SQL technique. |
| **Habilitations RFQ** | Contrôles par organisation et desk, droits explicites, expiration et révocation. L’administrateur ne bénéficie pas d’un accès RFQ universel ; l’auto-attribution de droits est refusée. |
| **Accès développeur** | Activation explicite, restriction locale, origines autorisées, ticket signé de 60 secondes, destiné à une identité précise et consommable une seule fois. Émission et consommation auditées. |
| **Sessions navigateur** | Stockage par onglet, annulation des requêtes lors d’une bascule, rejet des réponses tardives et rechargement complet du contexte lors du changement confirmé. |
| **Réinitialisation contrôlée** | Le bootstrap ne réactive pas silencieusement les comptes ou permissions retirés. Il signale les écarts de configuration. |
| **Consultation protégée** | Double protection : refus des mutations par l’API et ouverture SQLite en lecture seule avec `query_only`. |

Ces protections sont visibles notamment dans [l’authentification](C:/Users/admin/GitHub/structura/backend/app/api/auth.py:172), [le contrôle préalable des bases](C:/Users/admin/GitHub/structura/backend/app/hybrid/business.py:36), [les habilitations RFQ](C:/Users/admin/GitHub/structura/backend/app/services/rfq_access.py:23) et [les sessions navigateur](C:/Users/admin/GitHub/structura/frontend/src/utils/session.js:23).

**Les anomalies prioritaires**

P1 désigne ici une action sensible insuffisamment protégée ou un parcours métier bloqué. P2 désigne une incohérence ou un manque à traiter avant qualification opérationnelle.

### S-M01-01

**1. P1 — La gestion des relations de trading ne demande aucune permission spécifique**

Les routes de création et de modification des relations exigent uniquement un utilisateur connecté. Les contrôles vérifient l’organisation et les références, mais aucun rôle habilité à administrer ces accords.

Un profil Front ou Contrôleur peut donc soumettre une modification du statut, de l’autorisation de distribution, de la documentation ou de la limite de notionnel de son organisation. Or ces valeurs conditionnent ensuite l’autorisation de traiter.

**Recommandation :** réserver ces modifications à une habilitation explicite de gestion des accords et limites, avec une politique de validation définie. Conserver les contrôles d’organisation et l’audit déjà présents. [Création et modification des relations](C:/Users/admin/GitHub/structura/backend/app/api/trading.py:97).

### S-M01-02

**2. P1 — Tout profil connecté peut déclarer un règlement**

La route de règlement vérifie l’organisation, la date de valeur et la cohérence d’une éventuelle preuve existante. Elle ne vérifie pas une habilitation Opérations.

Un Front peut ainsi faire passer une exécution de son organisation à `SETTLED` en fournissant une référence. Cette action ne réalise aucun virement, mais elle modifie l’état opérationnel conservé.

**Recommandation :** attribuer une permission spécifique d’enregistrement du règlement et distinguer, selon la politique retenue, saisie de la référence et validation du règlement. [Enregistrement du règlement](C:/Users/admin/GitHub/structura/backend/app/api/trading.py:248).

### S-M01-03

**3. P1 — L’interdiction de pricing des profils secondaires est partielle**

Le routeur principal du Pricer utilise correctement `get_current_pricer`. Plusieurs autres chemins de calcul exigent seulement une connexion :

- pricing en cours de vie et funding implicite ;
- Product Optimizer ;
- solveur, grilles et scénarios ;
- dépôt de batches de repricing.

Opérations et Contrôleur peuvent donc accéder à des calculs alors que leurs capacités déclarées excluent `business.price`.

**Recommandation :** appliquer une politique commune aux différentes entrées de calcul. Préciser séparément les calculs de structuration et les valorisations opérationnelles autorisées sur un deal existant. [Pricing en cours de vie](C:/Users/admin/GitHub/structura/backend/app/api/inlife.py:405), [Optimizer](C:/Users/admin/GitHub/structura/backend/app/api/product_optimizer.py:25), [batches](C:/Users/admin/GitHub/structura/backend/app/api/compute.py:73).

### S-M01-04

**4. P1 — Le parcours de booking Opérations est bloqué par l’interface**

Le profil Opérations reçoit le droit de booking. Le bouton RFQ « Booker cette réponse » ouvre pourtant `/pricer`, et le garde de navigation interdit précisément cette page au profil sans `business.price`.

Le blocage est explicite dans l’enchaînement du code, indépendamment de la validité du dossier.

**Recommandation :** fournir un écran de contrôle et de booking adapté aux Opérations, alimenté par les termes et le calcul validés. Il doit permettre de traiter sans ouvrir tout le pricing privé. [Action de booking RFQ](C:/Users/admin/GitHub/structura/frontend/src/views/RfqView.vue:2751), [restriction du Pricer](C:/Users/admin/GitHub/structura/frontend/src/router/index.js:258).

### S-M01-05

**5. P1 — La propriété organisationnelle n’est pas appliquée uniformément**

Les RFQ disposent d’un partage par desk, mais plusieurs consommateurs restent liés au créateur :

- le Product générique demeure largement réservé à son auteur ; un collègue du même desk peut avoir accès à la RFQ sans pouvoir reprendre son Product ;
- le super utilisateur n’a pas systématiquement accès aux Products de ses collaborateurs ;
- un Front ne dispose pas automatiquement de l’accès au Deal booké par un collègue Opérations ;
- portefeuilles, documents, études sauvegardées et notes de valorisation restent souvent personnels ;
- les alertes et le rafraîchissement manuel du book utilisent encore le propriétaire utilisateur, alors qu’Opérations et Contrôleur peuvent consulter des deals plus largement.

Les données restent stockées, mais leur continuité d’utilisation par l’organisation est incomplète.

**Recommandation :** harmoniser les accès autour de l’organisation propriétaire, du desk et de l’action autorisée. Préserver les restrictions propres aux calculs bancaires privés. Traiter ensemble consultation, listes, liens directs, alertes et reprise du dossier. [Accès Product](C:/Users/admin/GitHub/structura/backend/app/services/product_repository.py:29), [accès Deal](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:1063), [alertes](C:/Users/admin/GitHub/structura/backend/app/api/alerts.py:20).

**Les autres anomalies et limites**

### S-M01-06

**6. P2 — Les sessions ne disposent pas de révocation serveur**

Les jetons durent sept jours. La déconnexion supprime la session du navigateur, mais aucune révocation serveur n’est enregistrée.

La désactivation d’un compte bloque bien les requêtes suivantes. En revanche, sa réactivation permet de réutiliser ses anciens jetons encore valides : aucune version de session ne les invalide définitivement.

**Recommandation :** ajouter un mécanisme simple d’invalidation des sessions, utilisable lors d’un incident, d’une suspension et d’une réinitialisation de mot de passe. [Émission des jetons](C:/Users/admin/GitHub/structura/backend/app/api/auth.py:156), [déconnexion locale](C:/Users/admin/GitHub/structura/frontend/src/stores/auth.js:112).

### S-M01-07

**7. P2 — Le portail commun perd le choix de l’installation hors mode développeur**

Le formulaire récupère la liste des organisations depuis le catalogue développeur. Lorsque ce mode est désactivé, la liste est vide ; une connexion depuis le portail central envoie alors les identifiants à la plateforme centrale.

La connexion directe à l’URL de chaque installation reste possible. Le parcours commun par mot de passe est incomplet.

**Recommandation :** définir une orientation vers l’installation indépendante des raccourcis privilégiés : URL dédiée, code d’installation ou autre mécanisme contrôlé. [Catalogue désactivé](C:/Users/admin/GitHub/structura/backend/app/hybrid/platform.py:153), [soumission du formulaire](C:/Users/admin/GitHub/structura/frontend/src/views/LoginView.vue:104).

### S-M01-08

**8. P2 — Les comptes créés manuellement ont une politique de mot de passe insuffisante**

Le bootstrap génère des mots de passe aléatoires longs. L’API administrative de création ne prévoit toutefois aucune longueur minimale : son contrat accepte un mot de passe d’un caractère.

Je n’ai identifié aucun parcours dédié de changement ou de réinitialisation de mot de passe dans les API d’authentification et d’administration examinées.

**Recommandation :** appliquer une politique commune côté serveur et prévoir activation initiale, changement personnel et réinitialisation contrôlée, avec invalidation des anciennes sessions. [Création des utilisateurs](C:/Users/admin/GitHub/structura/backend/app/api/admin.py:451).

### S-M01-09

**9. P2 — Les connexions métier ordinaires ne sont pas auditées comme les accès développeur**

Les accès développeur et les modifications de comptes sont audités. La connexion métier par mot de passe gère le compteur anti-bruteforce, puis émet le jeton sans événement d’audit métier pour le succès ou l’échec.

La plateforme centrale possède déjà une journalisation des connexions.

**Recommandation :** harmoniser ces événements entre services : compte, installation, résultat, horodatage et origine pertinente, sans enregistrer mot de passe ou jeton. [Connexion métier](C:/Users/admin/GitHub/structura/backend/app/api/auth.py:235).

### S-M01-10

**10. P2 — L’administration des entités contredit le modèle mono-organisation**

Un super utilisateur local peut appeler les routes de création et de renommage des entités. L’authentification de l’installation reste pourtant attachée à l’unique organisation du bootstrap.

Il peut donc créer une entité qui ne constitue pas une nouvelle installation utilisable. Le renommage local peut également diverger du nom porté par le manifeste.

**Recommandation :** limiter l’administration locale à son organisation et encadrer son renommage. Réserver l’ouverture d’une nouvelle organisation au processus de provisionnement. [Administration des entités](C:/Users/admin/GitHub/structura/backend/app/api/admin.py:558).

### S-M01-11

**11. P2 — Le workspace Admin ne bénéficie pas du même contrôle préalable d’identité de base**

Pour lancer l’application complète, ce workspace retire le manifeste du mécanisme standard. L’initialisation ne passe donc pas par le contrôle préalable des six installations métier ; le contrôle spécifique intervient après la création/migration du schéma et accepte un compte nommé `admin` déjà présent.

Une restauration de base au mauvais emplacement pourrait ainsi subir des modifications avant un éventuel refus.

**Recommandation :** conserver le fonctionnement de l’Admin complet, avec une identité de base dédiée vérifiée avant toute migration. [Lancement du workspace](C:/Users/admin/GitHub/structura/backend/run.py:23), [initialisation spécifique](C:/Users/admin/GitHub/structura/backend/app/hybrid/admin_workbench.py:28).

### S-M01-12

**12. P2 — Quatre routes de calendrier restent accessibles sans connexion**

Les routes de génération et de résolution des calendriers n’ont aucune dépendance d’authentification. Elles sont stateless ; le risque identifié porte sur l’accès au calcul et la consommation de ressources.

**Recommandation :** exiger une session et borner le travail demandé avant la génération. L’entrée de transport RFQ sans session utilisateur relève d’un autre mécanisme : elle vérifie une signature d’échange. [Routes de calendrier](C:/Users/admin/GitHub/structura/backend/app/api/schedule.py:14).

**Ordre de traitement recommandé**

1. **Sécuriser les actions sensibles** : gestion des accords et limites, règlement, permissions sur toutes les entrées de calcul.
2. **Rendre le travail collectif cohérent** : parcours Opérations, reprise Product/RFQ/Deal, visibilité des alertes et portefeuilles.
3. **Compléter la gestion des identités** : mots de passe, révocation des sessions, journalisation et connexion normale au portail.
4. **Uniformiser les installations** : administration mono-organisation et contrôle préalable du workspace Admin.

Avant un usage nominatif, il faudra également arrêter les règles d’admission, de suspension d’une organisation et de séparation des personnes. Les quatre comptes génériques actuels conviennent aux environnements fictifs ; deux identifiants différents ne prouvent pas que deux personnes distinctes ont effectué une validation.

**Ce qui reste à vérifier en exécution**

Les tests existants couvrent plusieurs protections importantes : jetons croisés, tickets expirés ou rejoués, refus du rôle technique, auto-attribution RFQ et sessions par onglet. Leur couverture des profils secondaires vérifie notamment le garde du Pricer, sans qualifier toutes les autres entrées de calcul.

La recette complémentaire devrait cibler :

- chaque action sensible avec les quatre profils, par appel API direct ;
- un dossier créé par un Front, repris par un collègue, booké par Opérations puis suivi par Contrôleur ;
- la déconnexion, suspension, réactivation et révocation avec un ancien jeton ;
- le portail sans accès développeur et la restauration d’une base incompatible.

**Mon avis : conserver ce socle et achever son application transversale.** Les contrôles d’installation et de session constituent une bonne base. Les cinq constats P1 empêchent aujourd’hui de qualifier une chaîne métier complète avec plusieurs profils.

## M02

**Le module possède de bonnes fondations, mais plusieurs défauts peuvent modifier les dates contractuelles, la contrepartie retenue ou les alertes de concentration.** Les priorités sont la génération des échéanciers, la validation des paiements et la stabilité des identités de référentiel.

Audit réalisé sur l’état local de `codex/hybrid-saas-foundation`, avec ses changements non commités. J’ai lu le code, la documentation et les tests existants, puis effectué des contrôles ponctuels des fonctions de calendrier et des calculs sur une base exclusivement en mémoire. Les six bases métier ont été consultées en lecture seule. **Aucun fichier modifié, service démarré, appel Yahoo ou suite pytest lancé.**

**État des référentiels constaté**

Les six installations présentent le même contenu :

| Référentiel | État |
|---|---|
| Sous-jacents | 65 entrées pour 59 tickers ; les appartenances à plusieurs groupes expliquent l’écart. |
| Métadonnées | Aucun conflit constaté entre groupes sur devise, classe et place. Les 65 champs de place de cotation sont toutefois vides. |
| Classification | Six entrées restent « à qualifier ». |
| Contreparties | 16 entrées, sans doublon de nom normalisé constaté. |
| Fournisseurs RFQ | Six entrées, aucun rattachement juridique explicite. UBS, BNP Paribas et Société Générale sont rapprochés par leur nom. |
| Rattachements manquants | Vontobel et Leonteq ne correspondent à aucune contrepartie éligible dans l’état lu. « Saisie manuelle » reste un canal générique. |

**Les points solides**

- **Les référentiels sont administrables en base.** Le catalogue de sous-jacents alimente les menus du Pricer et des RFQ. La réponse serveur exclut les entrées désactivées.
- **L’ajout d’un ticker comporte une vérification de disponibilité.** Un historique absent ou sans clôture exploitable entraîne un refus explicite.
- **Le fournisseur de cotation et la contrepartie juridique sont distingués.** Un lien explicite existe et le booking RFQ contrôle la contrepartie attendue.
- **Les primitives de jours ouvrés couvrent cinq conventions**, les décalages de règlement et six devises. Les chemins utilisant effectivement un calendrier refusent une devise non couverte.
- **La génération sépare grille brute et ajustement en jours ouvrés.** Les dates brutes et ajustées sont conservées ensemble.
- **L’échéancier distingue observation, relevé de fenêtre et paiement.** Plusieurs calendriers peuvent partager une date tout en conservant leurs rangs.
- **Les calendriers résolus peuvent être figés et restaurés.** La version récente lie également le calendrier au script et à son origine.
- **StartDate est séparée de la première observation.** Le moteur refuse notamment une première observation incompatible avec le fixing initial.

Ces mécanismes sont présents dans [les calendriers](C:/Users/admin/GitHub/structura/backend/app/core/calendars.py:58), [l’échéancier](C:/Users/admin/GitHub/structura/backend/app/core/payscript/schedule_model.py:1) et [son gel contractuel](C:/Users/admin/GitHub/structura/backend/app/core/product/calendar.py:13).

**Les anomalies prioritaires**

P1 désigne ici un risque sur les termes, les flux, l’identité juridique ou un contrôle financier. P2 désigne une incohérence ou une faiblesse de gouvernance.

### S-M02-01

**1. P1 — Un échéancier mensuel perd son ancrage après un mois court**

Le générateur avance depuis la date précédente. Après février, il conserve le jour raccourci au lieu de repartir de l’ancre initiale.

Cas reproduit, avant ajustement en jours ouvrés :

| Mensuel ancré au 31 janvier, jusqu’au 31 mai 2026 | Dates |
|---|---|
| Grille conservant l’ancre du 31 | 31/01 · 28/02 · 31/03 · 30/04 · 31/05 |
| Résultat actuel | 31/01 · 28/02 · 28/03 · 28/04 · 28/05 · 31/05 |

Le défaut déplace les observations et ajoute ici une sixième date. Il peut donc modifier les coupons, les possibilités de rappel et les rangs `INDEX`. La génération arrière présente également une dérive.

**Recommandation :** calculer chaque échéance depuis l’ancre originale et rendre explicite la règle de fin de mois. [Génération principale](C:/Users/admin/GitHub/structura/backend/app/core/schedule.py:87).

### S-M02-02

**2. P1 — Les paramètres de règlement ne sont pas validés uniformément**

L’API d’aperçu borne le délai de règlement. Le résolveur PayScript reçoit un dictionnaire libre et applique simplement une conversion en entier.

Contrôles reproduits :

- `−3` produit un paiement antérieur à l’observation ;
- `1,8` est silencieusement transformé en `1` ;
- `100` est accepté malgré la borne de l’aperçu.

Un Product portant le délai `−3` est accepté par `require_complete()`, avec une observation au **31 janvier 2026** et son paiement au **28 janvier**.

**Recommandation :** partager une validation typée entre aperçu, pricing et Product ; contrôler chaque couple observation/paiement. Le contrôle de la seule date de paiement finale ne suffit pas. [Résolution du délai](C:/Users/admin/GitHub/structura/backend/app/core/payscript/parser.py:1163).

### S-M02-03

**3. P1 — Le Pricer propose silencieusement une date de paiement avec un calendrier dégradé**

Lorsque le service de calendrier échoue, Economics calcule J+3 en excluant uniquement les week-ends.

Cas reproduit avec la fonction existante :

| Départ | Repli du frontend | Fonction TARGET |
|---|---|---|
| 02/04/2026, J+3 | 07/04/2026 | 09/04/2026 |

La date dégradée est proposée sans signaler que les jours fériés ont été ignorés. Ce comportement contredit la règle de `CLAUDE.md`.

**Recommandation :** signaler l’indisponibilité et demander une saisie explicite lorsque le calendrier ne peut pas être résolu. [Proposition de paiement](C:/Users/admin/GitHub/structura/frontend/src/components/EconomicsTab.vue:409).

### S-M02-04

**4. P1 — Les calendriers d’observation et de règlement sont confondus**

Le même argument de devise sert à ajuster les observations, échantillonner les fenêtres et calculer les paiements. Le modèle ne permet pas de choisir séparément les places d’observation et les centres de règlement, ni une combinaison de places pour un panier.

Le calendrier USD illustre cette limite :

- le code considère le **3 avril 2026** comme ouvré, alors que le NYSE est fermé ;
- il considère le **3 juillet 2026** comme fermé, alors que le calendrier publié par les Federal Reserve Financial Services prévoit l’ouverture le vendredi précédant un férié du samedi. [NYSE](https://www.nyse.com/trade/hours-calendars), [Federal Reserve Financial Services](https://www.frbservices.org/about/holiday-schedules/).

**Recommandation :** identifier séparément le calendrier d’observation et celui de paiement, avec les règles de combinaison nécessaires. Chaque calendrier doit désigner une référence précise. [Référentiel actuel](C:/Users/admin/GitHub/structura/backend/app/core/calendars.py:25), [utilisation dans PayScript](C:/Users/admin/GitHub/structura/backend/app/core/payscript/parser.py:1196).

### S-M02-05

**5. P1 — Choisir un sous-jacent dans le Pricer ne reprend pas sa devise**

Le sélecteur Economics remplace seulement le ticker. Le nom et la devise précédents restent en place.

Reproduction isolée : après sélection d’AAPL depuis une ligne BNP Paribas en EUR, l’état devient :

`ticker = AAPL ; nom = BNP Paribas ; devise = EUR`

Le formulaire RFQ reprend, lui, le nom et la devise du catalogue. Cette divergence peut affecter l’identité contractuelle, les libellés et les hypothèses de change.

**Recommandation :** appliquer ensemble les métadonnées du titre sélectionné et identifier explicitement les éventuelles surcharges manuelles. [Sélection dans le Pricer](C:/Users/admin/GitHub/structura/frontend/src/components/EconomicsTab.vue:469).

### S-M02-06

**6. P1 — Un lien juridique explicite invalide peut provoquer une substitution de contrepartie**

La résolution essaie le lien explicite vers une contrepartie active. Si ce lien vise une entité désactivée, elle retombe ensuite sur le rapprochement par nom.

Cas reproduit en mémoire : un fournisseur « Bank A » lié explicitement à « Issuer B » désactivé est finalement résolu vers « Bank A » actif.

**Recommandation :** lorsqu’un lien explicite existe, son indisponibilité doit bloquer la résolution. Une substitution d’entité doit être décidée et tracée. [Résolution fournisseur–contrepartie](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:384).

### S-M02-07

**7. P1 — Renommer une contrepartie fait disparaître son contrôle historique de concentration**

L’agrégat historique regroupe les deals par nom et retrouve la limite par nom actuel.

Cas fictif reproduit en mémoire :

| Situation | Exposition | Limite retrouvée | Dépassement |
|---|---:|---:|---|
| Avant renommage | 150 | 100 | Oui |
| Après renommage | 150 | Absente | Non |

Le Deal conserve son identifiant de contrepartie, mais cet agrégat ne l’utilise pas. Le moteur CCR dispose d’un autre chemin utilisant l’identifiant : le défaut ne doit donc pas être généralisé à tous les contrôles CCR.

**Recommandation :** agréger et retrouver les limites par identité stable, tout en conservant le nom historique pour la restitution. [Agrégation concernée](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:680).

**Les autres anomalies et limites**

### S-M02-08

**8. P2 — Les cotations manuelles restent dépendantes de libellés et de rattachements courants**

Les quotes conservent le fournisseur en texte. Le renommage d’un fournisseur peut rompre le rapprochement d’une cotation existante ; son rerattachement peut modifier la contrepartie attendue avant booking.

Les accords réseau confirmés bénéficient d’un snapshot spécifique.

**Recommandation :** conserver des identifiants stables et figer l’identité juridique associée à la réponse lors du geste métier approprié. [Construction des réponses](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:421).

### S-M02-09

**9. P2 — L’aperçu et le contrat ont des conventions par défaut différentes**

Sans convention fournie, l’aperçu utilise « suivant modifié », tandis que PayScript conserve les dates brutes.

Sur un calendrier quotidien du 29 mai au 2 juin 2026, j’obtiens **trois dates dans l’aperçu et cinq dans le contrat**. Les formulaires partagés envoient explicitement une convention ; l’écart concerne les appels qui l’omettent.

**Recommandation :** unifier ce contrat d’entrée et rendre le choix matériel identifiable. [Schéma de l’aperçu](C:/Users/admin/GitHub/structura/backend/app/core/schemas.py:583), [résolveur](C:/Users/admin/GitHub/structura/backend/app/core/payscript/parser.py:1121).

### S-M02-10

**10. P2 — « Stub long » applique une heuristique insuffisamment visible**

La fusion dépend d’un seuil égal à la moitié de la période régulière. Un choix « Long en fin » peut ainsi conserver un stub court.

Cas reproduit : du 15 janvier au 5 mars 2026, avec fréquence mensuelle, `short_last` et `long_last` donnent les mêmes dates.

**Recommandation :** définir la sémantique contractuelle attendue et aligner le libellé avec la règle appliquée. [Traitement des stubs](C:/Users/admin/GitHub/structura/backend/app/core/schedule.py:111).

### S-M02-11

**11. P2 — La qualification des métadonnées reste trop permissive**

Un même ticker peut porter des devises ou classifications différentes selon son groupe. Aucun conflit n’existe dans les bases lues, mais les modifications administratives peuvent en créer.

L’ajout utilise aussi EUR lorsque ni la saisie ni la sonde ne donnent de devise. Les mises à jour acceptent plusieurs valeurs insuffisamment contrôlées : noms vides, devises arbitraires ou limites négatives. Les noms de fournisseurs ne bénéficient pas d’une unicité en base.

**Recommandation :** centraliser l’identité du titre, séparer ses appartenances aux groupes, valider les champs matériels et afficher une donnée manquante comme « à qualifier ». [Ajout et modification des sous-jacents](C:/Users/admin/GitHub/structura/backend/app/api/admin.py:780).

### S-M02-12

**12. P2 — Les modifications du référentiel ne suivent pas un cycle de gouvernance complet**

Trois comportements restent à traiter :

- les CRUD directs des sous-jacents, fournisseurs et contreparties ne produisent pas d’événement métier avant/après avec auteur et motif ;
- le seed des sous-jacents réinsère au démarrage les couples ticker/groupe d’origine supprimés ou déplacés ;
- le catalogue frontend, chargé une fois, n’est pas invalidé après une modification administrative.

**Recommandation :** tracer les changements, préserver les décisions administratives au redémarrage et rafraîchir les consommateurs concernés. Privilégier la désactivation des entrées déjà utilisées. [Seed](C:/Users/admin/GitHub/structura/backend/app/db/database.py:896), [cache frontend](C:/Users/admin/GitHub/structura/frontend/src/data/commonUnderlyings.js:20).

### S-M02-13

**13. P2 — Ajouter un groupe à un titre connu dépend encore d’un appel externe**

L’ajout d’un ticker déjà présent dans un autre groupe déclenche une nouvelle sonde Yahoo. Une indisponibilité externe bloque donc une opération de classement alors que l’identité existe localement.

**Recommandation :** réutiliser l’instrument connu et proposer séparément sa revalidation. [Création d’une entrée](C:/Users/admin/GitHub/structura/backend/app/api/admin.py:780).

**14. Choix métier à arbitrer — Le booking direct autorise une contrepartie hors catalogue**

Cette autorisation est historique, explicite et couverte par un test. Elle contredit toutefois l’aide du formulaire annonçant que seules les contreparties actives peuvent faire face à un Deal. Sans contrepartie reconnue et sans netting set, le contrôle CCR peut sortir sans politique applicable.

**Recommandation :** décider si les nouveaux bookings exigent une contrepartie active ou une exception autorisée et auditée. La conservation du nom historique peut être assurée indépendamment. [Contrôle économique](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:246), [contrôle CCR](C:/Users/admin/GitHub/structura/backend/app/core/ccr/service.py:770).

**Ordre de traitement recommandé**

1. **Sécuriser les dates contractuelles** : ancrage mensuel, délais de paiement, suppression du repli silencieux.
2. **Qualifier les calendriers** : observation, règlement, places et combinaisons.
3. **Stabiliser les identités** : sélection du sous-jacent, lien juridique et agrégation par identifiant.
4. **Compléter la gouvernance** : validation, historique, initialisation et rafraîchissement du référentiel.

Les recettes complémentaires devront couvrir les fins de mois et années bissextiles, les divergences bourse/règlement, les paramètres de calendrier invalides, puis les renommages, désactivations et rerattachements sur des dossiers existants. Les plafonds de génération méritent également un contrôle en amont : certaines limites interviennent après la construction des dates.

**Je traiterais les sept P1 avant de considérer ce module qualifié pour les calendriers et parcours juridiques concernés.** Les mécanismes de gel et de traçabilité contractuelle sont utiles ; ils doivent recevoir des dates et des identités correctement validées.

## M03

**Le module 3 possède de bonnes briques, mais la chaîne de données reste trop hétérogène entre Pricer, RFQ, valorisation et reporting.** Les principaux risques concernent la qualification d’une clôture, les données anciennes et la conservation de leur provenance.

Audit effectué sur le code actuel, après lecture des consignes et du skill `structura-market-data`, **sans modification du code ni des données**. Les **12 tests ciblés sur les dividendes et la calibration passent**. J’ai complété cette vérification par des reproductions synthétiques, sans appel aux fournisseurs externes.

**Les points solides**

- **La distinction entre historiques ajustés et clôtures contractuelles est explicite.** La calibration utilise les séries ajustées ; les fixings disposent d’un chargement indépendant, par titre et par date, sans remplissage entre sous-jacents. [Chargement des historiques](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:252)

- **Les principaux biais d’alignement sont traités.** Normalisation des fuseaux horaires, absence de remplissage avant la première observation et signalement de certaines fenêtres tronquées : le panier ne reçoit plus artificiellement un passé antérieur à ses constituants.

- **Le dividende est devenu vérifiable dans le Pricer.** Le service reconstruit un rendement historique daté, conserve les détachements, calcule une seconde estimation et signale les divergences. Une erreur du flux de dividendes n’est pas automatiquement assimilée à une absence de distribution. [Profil de dividende](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:549)

- **La calibration datée est indépendante de l’âge du deal.** Elle utilise une fenêtre de marché dédiée, contrôle un minimum d’observations et produit une matrice de corrélation exploitable numériquement. [Calibration commune](C:/Users/admin/GitHub/structura/backend/app/core/calibration.py:41)

- **Les fixings disposent de contrôles métier substantiels.** Valeurs finies et positives, ancienneté maximale, devise, split et mouvement exceptionnel sont contrôlés. Une révision du fournisseur ne remplace pas silencieusement un fixing déjà officiel. [Contrôles Yahoo](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:4528)

- **Les valeurs utilisées sont largement reproductibles.** Le booking conserve les entrées de pricing ; le MtM expose ses paramètres effectifs et ses sources de repli. Les taux nuls et négatifs sont correctement préservés. L’Optimizer distingue déjà référence, surcharge et valeur utilisée. [Snapshot de pricing](C:/Users/admin/GitHub/structura/backend/app/core/valuation_context.py:298), [provenance Optimizer](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/market.py:27)

**Les anomalies prioritaires**

P1 désigne ici un risque sur une valeur utilisée ou une décision métier ; P2, une faiblesse de qualité, de cohérence ou de traçabilité.

### S-M03-01

**1. P1 — La clôture du jour n’est pas qualifiée comme définitive**

En politique `AUTO_YAHOO`, le contrôle de publication vérifie essentiellement que la valeur porte la date du jour. Il ne vérifie pas que la séance est terminée ni que la barre quotidienne est définitive. Or le chargement Yahoo peut contenir les données de la séance en cours.

**Reproduction :** une valeur synthétique datée du jour passe les contrôles, sans information d’heure de clôture ou de finalité. Cela démontre une lacune du contrôle ; je n’ai pas exécuté une validation officielle en base.

**Recommandation :** distinguer explicitement cours indicatif et clôture admissible au fixing. L’automatisation doit attendre la clôture de la place, avec fuseau horaire et délai de publication définis. [Contrôle de publication](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:4564)

### S-M03-02

**2. P1 — La RFQ peut remplacer un dividende inconnu par zéro**

La RFQ utilise encore l’ancienne voie : rendement Yahoo instantané, sans profil historique daté. Si la métadonnée manque ou si son chargement échoue, le backend renvoie `0.0`, puis la RFQ l’affiche comme un chargement réussi.

Cette voie reste également utilisée dans le réinvestissement. Le même sous-jacent peut donc recevoir un `q` différent selon son point d’entrée.

**Reproduction :** indisponibilité de la métadonnée Yahoo → rendement retourné égal à zéro.

**Recommandation :** faire converger ces consommateurs vers le profil daté du Pricer. Une donnée inconnue doit rester inconnue, avec conservation explicite de l’hypothèse précédente ou saisie manuelle. [Valeur de repli backend](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:138), [chargement RFQ](C:/Users/admin/GitHub/structura/frontend/src/views/RfqView.vue:2141)

### S-M03-03

**3. P1 — Une réponse peut alimenter le mauvais sous-jacent après un changement de ticker**

Le Pricer protège contre deux chargements successifs, mais pas contre une modification du ticker pendant un chargement. La réponse est appliquée à la ligne d’origine sans revérifier son identité actuelle.

**Reproduction :** chargement de A, remplacement du ticker par B avant réception, puis réponse de A : B reçoit la volatilité et le dividende de A. Une saisie manuelle effectuée entre-temps peut également être écrasée.

**Recommandation :** vérifier l’identité du sous-jacent, le ticker, la date demandée et la version des champs avant d’appliquer une réponse. [Application de la réponse](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:2037)

### S-M03-04

**4. P1 — Un cours interrompu peut être prolongé sans limite dans l’historique**

Le chargement propage le dernier cours connu sur les dates suivantes. Ce mécanisme convient à certaines fermetures de marché, mais il ne distingue pas une fermeture normale d’une suspension ou d’une panne prolongée.

**Reproduction :** un titre arrêté au 29 janvier est prolongé jusqu’au 23 avril, soit **60 jours de semaine**, avec une succession de rendements nuls.

Le backend émet bien un avertissement. Toutefois, le Pricer ne le restitue pas dans son message de chargement. Booking affiche une alerte pour l’historique de rejeu, mais le calcul reste possible.

**Recommandation :** conserver le masque des observations réellement reçues, limiter la propagation selon l’usage et exclure les prolongations excessives de la calibration. Prévoir une dérogation explicite lorsque le métier souhaite valoriser sur un dernier cours connu. [Alignement et ancienneté](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:324)

### S-M03-05

**5. P1 — Les conversions de reporting acceptent un change arbitrairement ancien**

Le service distingue correctement un change manquant d’une conversion à parité. En revanche, il accepte la dernière valeur disponible sans limite d’ancienneté. Après échec du fournisseur, un ancien cache peut donc continuer à alimenter les agrégats.

**Reproduction :** un change du 2 janvier 2020 est accepté pour une conversion au 19 octobre 2026.

La faiblesse concerne notamment les consommateurs de `fx_rate_to`. Les traitements Studies utilisant `price_at` disposent, eux, d’un contrôle d’ancienneté.

**Recommandation :** retourner avec le change sa date effective, sa source et son statut de fraîcheur. Un total incomplet ou calculé sur un change périmé doit être identifiable. [Conversion de reporting](C:/Users/admin/GitHub/structura/backend/app/core/amc_prices.py:320)

**Les autres anomalies et recommandations**

### S-M03-06

**6. P2 — Deux définitions différentes de la volatilité « réalisée » coexistent**

La voie sans date calcule un écart-type centré ; la voie datée utilise un estimateur quadratique non centré. Les corrélations de la première voie sont calculées paire par paire, sur des échantillons potentiellement différents.

**Reproduction :** trois périodes de recouvrement différentes produisent une matrice de corrélation dont la valeur propre minimale vaut **−1**. Le moteur possède heureusement une protection qui refuse une correction excessive : le risque est ici notamment un chargement apparemment réussi suivi d’un échec de pricing.

Par ailleurs, une demande de 252 rendements peut réussir avec seulement **20 rendements**, sans avertissement spécifique de faible profondeur ; le nombre réel reste disponible dans la réponse.

**Recommandation :** une seule méthode canonique, documentée, avec échantillon commun et qualification de sa profondeur. Ne pas choisir implicitement la méthode selon la présence d’un paramètre de date. [Ancienne voie](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:111), [protection du moteur](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:85)

### S-M03-07

**7. P2 — Le contrat de réponse est incomplet pour les historiques partiels**

Un historique demandé pour A et B peut être renvoyé avec A seulement, sans erreur ni liste des tickers manquants.

Certains consommateurs compensent : le backtest standard vérifie la présence de tous les titres, et le MtM refuse un spot absent. Le scanner de paniers retire en revanche les titres indisponibles de l’univers avant de poursuivre.

**Recommandation :** retourner systématiquement les titres demandés, disponibles et exclus, avec leur motif. Une recherche peut continuer sur un univers réduit, mais cette réduction doit figurer dans le résultat. [Réponse historique](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:346), [réduction de l’univers](C:/Users/admin/GitHub/structura/backend/app/api/pricing.py:995)

### S-M03-08

**8. P2 — Le booking conserve mieux les valeurs que leur origine**

La chaîne ordinaire conserve les paramètres nécessaires au calcul. En revanche, les données de référence chargées dans le Pricer — date effective par champ, observation initiale, diagnostic, détail du dividende — ne suivent pas toutes le chemin vers les entrées de pricing et le snapshot serveur.

On peut donc reproduire une valeur sans pouvoir expliquer complètement pourquoi telle volatilité ou tel dividende avait été retenu. L’Optimizer offre déjà un modèle de provenance plus complet.

**Recommandation :** conserver, séparément, la référence reçue, l’hypothèse choisie et la valeur utilisée, avec date, méthode et éventuelle surcharge. [Construction des entrées du Pricer](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:588)

### S-M03-09

**9. P2 — Le stockage de prix accepte des imports insuffisamment contrôlés**

**Reproduction :** l’import JSON accepte des dates dupliquées et une valeur infinie. Il ne demande pas de devise ni de convention d’ajustement.

Deux fragilités supplémentaires sont confirmées :

- `A/B` et `A B` deviennent la même clé de fichier ;
- un téléchargement échoué peut déjà avoir modifié l’association entre clé et ticker, alors que l’ancienne série reste stockée.

**Recommandation :** contrôler les données avant remplacement, exiger les métadonnées matérielles, utiliser une identité sans collision et publier série et association ticker ensemble. Les règles de positivité doivent dépendre du type d’instrument. [Import](C:/Users/admin/GitHub/structura/backend/app/core/amc_prices.py:176), [ordre de mise à jour](C:/Users/admin/GitHub/structura/backend/app/core/amc_prices.py:129)

### S-M03-10

**10. P2 — L’administration ne supervise pas toute la chaîne de marché**

L’écran administré suit un catalogue fixe de **66 entrées** et un stockage Parquet. Les chargements ordinaires du Pricer et du MtM passent principalement par un autre service, avec un cache mémoire de deux minutes.

Un cache affiché comme disponible en administration ne garantit donc pas sa réutilisation par ces calculs. Le statut « OK » repose essentiellement sur une ancienneté inférieure ou égale à sept jours, sans qualification complète de la série. [Catalogue administré](C:/Users/admin/GitHub/structura/backend/app/api/admin.py:679)

**État local constaté :**

| Emplacement | Observation |
|---|---|
| Ancien stockage `backend/data` | 209 séries de prix, arrêtées entre le 15 et le 29 juillet 2026 |
| Même stockage | 15 séries FX, arrêtées entre le 23 juin et le 11 septembre 2026 |
| Six installations d’organisations | Aucun Parquet de prix ou de change ; 11 fichiers de facteurs chacune |
| 209 séries historiques de prix | Aucune colonne distincte `price_close` |

Ces constats décrivent les fichiers présents, pas la disponibilité actuelle de Yahoo ni des installations en fonctionnement.

**Recommandation :** rapprocher la supervision des services réellement consommés : couverture, convention, fraîcheur et dépendances par usage. Réutiliser les séries autorisées dans chaque installation avant un téléchargement, en préservant leur isolation.

### S-M03-11

**11. P3 — Le cache mémoire peut être modifié par un appelant**

La copie retournée est superficielle : les listes de prix restent partagées avec le cache.

**Reproduction :** modifier un prix dans une réponse modifie celui retourné au prochain appel identique. Je n’ai pas identifié de consommation courante exploitant effectivement cette possibilité.

**Recommandation :** rendre les résultats indépendants ou immuables. [Lecture du cache](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:284)

**Les limites à conserver explicitement dans le produit**

- Les volatilités chargées sont **réalisées**. Les surfaces automatiques restent des hypothèses de modèle, sans flux de cotations d’options démontré dans cette chaîne.
- Le rendement historique de dividende reste une **hypothèse forward à confirmer**. Le moteur utilise un rendement continu, éventuellement dégressif, sans calendrier de sauts de dividendes cash.
- Les taux et le funding restent principalement saisis ou repris du booking. Une valorisation historique ne constitue donc pas une reconstitution automatique de toutes les courbes de cette date.
- L’annualisation à 252 et les indicateurs d’ancienneté fondés sur les jours de semaine doivent être qualifiés selon les instruments, notamment pour les actifs cotant sept jours sur sept.

**L’ordre de correction que je recommande**

1. **Sécuriser les valeurs utilisées :** finalité des clôtures automatiques, dividende inconnu, réponses appliquées après changement de ticker, cours et changes périmés.
2. **Unifier la chaîne :** même service daté pour Pricer, RFQ, réinvestissement et calibration ; réponses complètes sur les exclusions et la profondeur disponible.
3. **Compléter l’auditabilité :** provenance par champ, distinction référence/hypothèse/valeur utilisée, imports contrôlés et remplacement atomique des séries.
4. **Rapprocher administration et consommateurs :** supervision commune de la qualité et réutilisation explicite des données locales autorisées.

La recette devra vérifier ces cas de bout en bout, notamment qu’un cours intrajournalier ne devient pas un fixing officiel, qu’une donnée absente ne devient pas zéro et qu’une référence ancienne reste visible dans les résultats et les documents.

**Aucun correctif n’a été appliqué.** Les tests réussis confortent les briques de dividendes et de calibration ; ils ne valident pas la disponibilité des fournisseurs ni l’ensemble des parcours UI et opérationnels.

## M04

**Le module 4 — Objet Product et bibliothèque — possède un socle solide, mais deux transitions peuvent compromettre la cohérence du dossier : la synchronisation d’une ancienne RFQ et la reprise du contexte commercial vers une nouvelle RFQ.**

J’ai audité l’identité Product, les versions contractuelles, les révisions, les calculs conservés, la bibliothèque et les passages vers RFQ, indicatif et booking. La revue porte sur l’état actuel de la branche, changements locaux compris.

**Aucun code ni aucune donnée réelle n’a été modifié.** Les neuf tests frontend ciblés passent. Les anomalies ci-dessous ont été vérifiées par lecture du code et, lorsqu’indiqué, reproduites avec des données synthétiques en mémoire.

**Les points solides**

- **Les notions métier sont correctement séparées.** Une session de pricing peut rester temporaire ; un Product peut être persisté sans être affiché dans la bibliothèque ; un Product conservé ne constitue pas un Deal. La séparation entre persistance et visibilité évite de créer artificiellement une position pour garder une idée. [Création interne](C:/Users/admin/GitHub/structura/backend/app/services/product_repository.py:136)

- **L’identité est stable, avec deux niveaux de version distincts.** La version des termes décrit le contrat ; la révision décrit l’évolution du dossier. Plusieurs RFQ et calculs peuvent enrichir le même Product. La limitation à un Deal par dossier est explicite dans cette première version.

- **L’immutabilité est réelle.** Les objets métier sont figés, les projections JSON sont indépendantes et les historiques de termes, révisions et calculs sont protégés contre les modifications SQL. Mes vérifications ont confirmé ces protections. [Modèles immuables](C:/Users/admin/GitHub/structura/backend/app/core/product/models.py:15), [protections SQL](C:/Users/admin/GitHub/structura/backend/app/db/product_migrations.py:77)

- **Les écritures concurrentes sont contrôlées.** Une révision attendue devenue ancienne est refusée. Le contrôle et l’ajout de l’historique participent à la transaction métier ; il ne s’agit pas d’un simple contrôle visuel. [Écriture de révision](C:/Users/admin/GitHub/structura/backend/app/services/product_repository.py:81)

- **Les calculs conservés portent une preuve serveur.** La signature couvre le prix, l’empreinte des entrées et celle du résultat. Une altération du prix a été refusée lors de la reproduction. Les calculs détaillés sont stockés séparément des termes contractuels. [Reçus signés](C:/Users/admin/GitHub/structura/backend/app/services/product_receipts.py:38)

- **Le serveur reprend l’autorité sur les termes.** Lors du pricing d’un Product, les hypothèses externes sont assemblées avec son panier, son script, ses paramètres et son calendrier. Le contexte de marché ne peut pas directement remplacer ces éléments. [Composition des entrées](C:/Users/admin/GitHub/structura/backend/app/core/product/inputs.py:101)

- **La bibliothèque restitue les résultats sans recalcul implicite.** Les calculs anciens restent consultables et la comparaison signale les différences de version contractuelle. L’archivage concerne la bibliothèque et ne prétend pas terminer un Deal actif.

**Les anomalies prioritaires**

P1 désigne un risque sur la cohérence métier du dossier ; P2, une faiblesse de workflow, de restitution ou de protection.

### S-M04-01

**1. P1 — Une ancienne RFQ peut faire régresser la version courante du Product**

La mise à jour d’une RFQ recharge sa version historique des termes, puis transmet cet objet à la synchronisation du dossier. Cette synchronisation écrit une nouvelle révision et remplace également le pointeur de version contractuelle courante.

**Reproduction en base mémoire :**

1. Product en termes v1, avec une RFQ portant v1.
2. Révision explicite du Product vers v2.
3. Synchronisation de la RFQ restée en v1.
4. Le Product courant revient en **v1**, alors que v2 existe toujours dans l’historique.

Le contrôle de concurrence ne bloque pas ce cas : la révision du dossier est récente, mais les termes injectés sont anciens. Cette régression peut ensuite mettre le dossier en contradiction avec d’autres RFQ ou une exécution.

**Recommandation :** mettre à jour la projection de la RFQ dans le dossier courant sans modifier sa version de termes. Réserver le changement de version courante aux opérations contractuelles explicites, avec un contrôle central dans le service de persistance. [Chargement de la version RFQ](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1603), [synchronisation du Product](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:332)

### S-M04-02

**2. P1 — Product → RFQ perd le sens et plusieurs informations commerciales**

Le formulaire RFQ est initialisé avec ses valeurs par défaut, puis reprend principalement les termes, le nominal et les hypothèses de calcul. Il ne reprend pas correctement le sens de transaction, le contexte client et plusieurs informations juridiques du Product.

**Reproduction avec les fonctions frontend actuelles :**

| Information | Product d’origine | RFQ préremplie |
|---|---|---|
| Sens | `SELL` | « achat » |
| Client | Identifiant renseigné | Vide |
| Format | `OTC` | Vide |
| Nominal | 2 000 000 | 2 000 000 |

Si l’utilisateur poursuit sans corriger ces champs, la création de la RFQ peut ensuite réécrire l’intention et le contexte commercial du Product.

**Recommandation :** reprendre explicitement tous les faits appartenant au dossier. Les informations volontairement différentes doivent faire l’objet d’un changement visible, expliqué et validé. [Préremplissage RFQ](C:/Users/admin/GitHub/structura/frontend/src/views/RfqView.vue:1782), [réécriture du contexte](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1008)

**Les autres anomalies**

### S-M04-03

**3. P2 — Le contexte d’un Product booké reste modifiable par l’API générique**

La modification générale du Product accepte encore une nouvelle intention et un nouveau contexte commercial lorsque son bloc d’exécution est présent.

**Reproduction :** un dossier portant une exécution de 2 M et un client donné accepte une intention de 9 M et un autre client, sans modifier son bloc d’exécution.

Les termes du Deal ne sont pas réécrits par cette opération. En revanche, le dossier présente désormais plusieurs réponses incompatibles à la question « quel nominal et quel client concernent cette affaire ? ».

**Recommandation :** définir précisément les informations encore éditables après booking. Les conditions exécutées doivent rester sous l’autorité du Deal et du workflow d’amendement ; l’intention historique doit conserver une qualification claire. [Modification du contexte Product](C:/Users/admin/GitHub/structura/backend/app/api/products.py:233)

### S-M04-04

**4. P2 — Le dernier prix peut appartenir à une ancienne version, puis empêcher la réouverture**

La bibliothèque affiche le dernier calcul ajouté sans vérifier qu’il correspond aux termes courants.

**Reproduction :** après passage en v2, la ligne affiche encore **98 %**, provenant d’un calcul de v1.

À la réouverture, le store sélectionne automatiquement ce calcul ancien, constate l’incompatibilité et refuse le chargement. Le parcours ordinaire retombe alors sur un Pricer réinitialisé, sans présenter correctement l’erreur dans cet écran.

**Recommandation :**

- afficher le dernier prix de la version courante, avec sa date ;
- identifier séparément les prix historiques ;
- permettre l’ouverture des termes courants sans calcul compatible ;
- conserver un écran d’erreur explicite lorsqu’un chargement échoue.

[Prix de la bibliothèque](C:/Users/admin/GitHub/structura/backend/app/api/products.py:120), [sélection automatique du calcul](C:/Users/admin/GitHub/structura/frontend/src/stores/products.js:62), [réinitialisation après échec](C:/Users/admin/GitHub/structura/frontend/src/views/PricerView.vue:111)

### S-M04-05

**5. P2 — Un brouillon incomplet peut être conservé, mais reste difficile à compléter**

Le backend accepte volontairement un Product incomplet et conserve son diagnostic. J’ai confirmé le cas d’un produit sans date d’ancrage.

À sa réouverture, la présence du Product verrouille cependant les termes dans l’interface, y compris les dates et le panier. La révision existe par API, mais le parcours utilisateur pour compléter ou réviser le brouillon manque.

Le champ de filiation `origin_product_id` existe également, sans parcours Product de duplication raccordé.

**Recommandation :** proposer des actions distinctes selon l’état : « Compléter le brouillon », « Réviser les termes » avant exécution et « Créer un nouveau dossier à partir de celui-ci », avec filiation. [Gestion des brouillons](C:/Users/admin/GitHub/structura/backend/app/core/product/inputs.py:21), [verrouillage global](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:439)

### S-M04-06

**6. P2 — L’idempotence backend n’est pas conservée lors d’une nouvelle tentative frontend**

Le serveur sait reconnaître une commande déjà exécutée. Mais chaque appel frontend à « Conserver le produit » génère une nouvelle clé.

**Reproduction :** après simulation d’une réponse perdue suivant l’enregistrement, une nouvelle tentative utilise une autre clé. Le serveur ne peut donc pas reconnaître la répétition de la même intention de création.

**Recommandation :** conserver la clé pendant toute la durée d’une opération, y compris après une erreur réseau dont l’issue serveur est inconnue. [Création de la commande frontend](C:/Users/admin/GitHub/structura/frontend/src/stores/products.js:90)

### S-M04-07

**7. P2 — Les protections SQL exigent un Product, mais pas une version contractuelle valide**

Les protections d’insertion imposent un `product_id`. Elles ne garantissent pas que le couple Product/version désigne une version existante.

**Reproduction avec les protections actives et les clés étrangères activées :** insertion d’un document lié au Product avec une version `NULL`, puis avec la version inexistante `999`, toutes deux acceptées.

Les API courantes effectuent des vérifications supplémentaires ; cette observation concerne la protection structurelle contre un futur consommateur ou une écriture erronée.

**Recommandation :** contrôler également la validité du couple Product/version pour les enregistrements durables concernés. [Protections des liens](C:/Users/admin/GitHub/structura/backend/app/db/product_migrations.py:47)

### S-M04-08

**8. P2 — La comparaison omet certains paramètres matériels de calcul**

La comparaison reprend les paramètres historiques des modèles, mais ne parcourt pas les paramètres de surface `vol_surface`. Certains réglages du modèle de taux sont également absents.

**Reproduction :** modification du paramètre `eta` d’une surface utilisée en volatilité locale, avec les autres champs inchangés : la comparaison retourne **zéro ligne modifiée**.

**Recommandation :** construire la comparaison depuis l’ensemble des entrées effectives du calcul, en distinguant paramètres actifs, inactifs et changement de modèle. Un écart inexpliqué ne doit pas apparaître comme une absence de modification des hypothèses. [Comparaison des hypothèses](C:/Users/admin/GitHub/structura/frontend/src/utils/productCalculations.js:32)

### S-M04-09

**9. P2 — La version du moteur n’est pas conservée avec le calcul**

Les entrées, résultats, dates, empreintes et versions de schéma sont conservés. Je n’ai pas trouvé de version du moteur ou du compilateur dans cette chaîne d’enregistrement.

Cela permet de restituer fidèlement un résultat enregistré, mais ne garantit pas de le recalculer à l’identique après une évolution du moteur.

**Recommandation :** conserver une version des conventions de calcul et une référence du moteur. Distinguer la restitution du résultat archivé, son rejeu avec le moteur compatible et une nouvelle valorisation. [Enregistrement des calculs](C:/Users/admin/GitHub/structura/backend/app/services/product_repository.py:236)

### S-M04-10

**10. P2 — La bibliothèque reste surtout une liste de produits et de calculs**

Le dossier contient davantage d’informations que celles accessibles depuis la bibliothèque : contexte commercial, RFQ, exécution, documents et cycle de vie. La liste fournit peu de navigation vers ces faits.

Elle charge aussi tous les produits visibles et leurs dossiers, sans pagination ni recherche serveur. Les historiques de calculs sont également récupérés en bloc. Le risque de volume reste à mesurer ; je n’ai pas effectué de test de charge.

**Recommandation :** proposer une fiche dossier compacte avec les faits et liens utiles, une chronologie des versions et des listes paginées. La propriété collective par organisation ou desk reste aussi à harmoniser, dans le prolongement du module 1. [Liste serveur](C:/Users/admin/GitHub/structura/backend/app/api/products.py:193), [bibliothèque](C:/Users/admin/GitHub/structura/frontend/src/views/ProductsView.vue:31)

**L’ordre de correction recommandé**

1. **Protéger les transitions contractuelles et commerciales** : empêcher la régression depuis une ancienne RFQ, préserver le sens et le contexte lors des transferts, encadrer les modifications après booking.
2. **Fiabiliser la reprise** : prix rattaché à la bonne version, ouverture sans calcul compatible, erreur visible et parcours de complétion des brouillons.
3. **Compléter les garanties de conservation** : idempotence frontend, intégrité Product/version et identification du moteur.
4. **Rendre la bibliothèque exploitable comme dossier métier** : navigation, historique, comparaison complète, recherche et pagination.

La recette prioritaire devrait suivre un même Product de v1 à v2, conserver une RFQ en v1, puis exercer sélection, modification de statut, réouverture et booking. Elle devra vérifier que chaque action enrichit le dossier sans remplacer les faits appartenant à une autre version ou à un autre module.

Les six bases d’organisations inspectées ne contiennent actuellement aucun Product. Les preuves fonctionnelles de cet audit reposent donc sur les reproductions synthétiques et les tests ciblés, sans qualification complète des parcours dans le navigateur.

## M05

**Le module 5 dispose d’un bon socle métier, mais un défaut du compilateur peut modifier silencieusement le payoff exécuté.** C’est le point prioritaire. Les autres fragilités concernent surtout la conservation des Economics, le chargement des configurations et la fidélité des dates affichées.

Aucun code ni donnée métier n’a été modifié. L’audit porte sur PayScript, Economics, les modèles de produits et l’assistant de scripting. La validation numérique des modèles de pricing relève du module 6.

**Les points solides**

- **La distinction entre modèle générique et exemple prérempli est réelle.** Le catalogue comprend 19 modèles génériques et 15 exemples préremplis. Les modèles génériques laissent les termes matériels à renseigner ; les exemples proposent des hypothèses explicites. Les coupons des exemples sont définis par observation, sans annualisation implicite. [Catalogue et préparation des exemples](C:/Users/admin/GitHub/structura/frontend/src/utils/payscriptPresets.js)

- **Les unités et les paramètres requis sont correctement structurés.** Un défaut exprimé en pourcentage est distingué d’une valeur brute. Un paramètre sans défaut doit être renseigné. Le backend contrôle les valeurs finies, les séries vides et leur compatibilité avec une déclaration scalaire. [Contrôle des paramètres](C:/Users/admin/GitHub/structura/backend/app/core/payscript/bindings.py:115)

- **Le fixing initial est séparé des observations du payoff.** Les niveaux initiaux individuels sont conservés pour calculer les performances du panier. Les propriétés non prises en charge et les références futures interdites sont rejetées.

- **Les payoffs du catalogue bénéficient de contrôles économiques utiles.** Les tests couvrent notamment les remboursements des 19 modèles, les égalités à certaines barrières, le rattrapage mémoire, le rappel à la dernière observation et la distinction entre barrières européenne et américaine. Ils vérifient aussi la réconciliation de jambes de cash avec le prix. [Tests d’acceptation](C:/Users/admin/GitHub/structura/backend/tests/test_payscript_acceptance.py:90)

- **Economics constitue bien le lieu central de saisie.** La validation du script est explicite et les réponses de parsing périmées sont écartées. La politique actuelle — dernière modification explicite de déclaration prioritaire, avec restitution des valeurs remplacées — est implémentée et testée. Je ne considère donc pas cette politique comme une anomalie. [Application des déclarations](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:100)

- **L’assistant possède de bons mécanismes de traçabilité.** Adoption volontaire, distinction entre compilation, contrôles et pricing de contrôle, conservation des prompts, réponses, modèles effectifs et empreintes : l’utilisateur peut retrouver l’origine du script proposé. [Provenance de génération](C:/Users/admin/GitHub/structura/backend/app/services/llm/__init__.py)

**Les anomalies et mes recommandations**

### S-M05-01

**1. P1 — Une surindentation peut supprimer silencieusement un paiement ou un arrêt**

Le compilateur ignore les instructions dont l’indentation dépasse le niveau attendu sans être rattachée à un bloc conditionnel.

J’ai reproduit deux conséquences à taux nul :

- Capital de 100 % et coupon de 8 % : le résultat passe de **108 % à 100 %** lorsque la ligne du coupon est trop indentée.
- Un `STOP` trop indenté disparaît de l’exécution : le script paie **100 % au rappel, puis encore 100 % à maturité**.

Dans ce second cas, les métadonnées annoncent pourtant `has_stop = True`. Le payoff exécuté et sa description divergent.

**Recommandation :** rejeter toute indentation sans bloc parent valide, avec la ligne concernée. La validation doit garantir qu’aucune instruction écrite n’est silencieusement abandonnée. Ajouter ces deux scénarios aux tests économiques prioritaires. [Instructions actuellement ignorées](C:/Users/admin/GitHub/structura/backend/app/core/payscript/parser.py:458)

### S-M05-02

**2. P2 — Les changements de type de déclaration ne préservent pas correctement les termes**

Deux cas sont reproduits :

- Passer de `PARAM()` à `PARAM` conserve seulement la première valeur. Une série `[8, 10, 12]` devient `8`, sans signalement dans le compte rendu de validation.
- Passer d’une date unique à un échéancier sous le même nom conserve l’ancienne chaîne de date. L’interface attend ensuite un objet contenant une fréquence ; l’accès à ce champ échoue.

**Impact :** perte de termes saisis ou rupture de l’édition après une modification pourtant acceptée.

**Recommandation :** traiter ces changements comme des conversions explicites : annoncer les valeurs abandonnées, proposer la valeur scalaire retenue et reconstruire les champs nécessaires au nouveau calendrier. [Conversion des paramètres](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:64), [synchronisation des calendriers](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:187)

### S-M05-03

**3. P2 — Une série partiellement renseignée perd ses valeurs lors de la préparation d’un brouillon Product**

En mode autorisant les termes incomplets, une seule ligne vide entraîne la conversion de **toute la série en `null`**.

Par exemple, `[8, vide, 12]` devient une valeur absente. Cette transformation alimente la préparation des brouillons Product. Le modèle backend conserve ensuite cette absence ; les valeurs déjà renseignées ne figurent plus dans les termes transmis.

**Recommandation :** conserver les lignes renseignées et identifier précisément les lignes manquantes. Le caractère incomplet doit empêcher les étapes exigeant un contrat complet, tout en préservant le travail de saisie. [Préparation des paramètres](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:553), [construction des termes](C:/Users/admin/GitHub/structura/backend/app/core/product/inputs.py:22)

### S-M05-04

**4. P2 — Le chargement d’une configuration peut laisser une session partiellement remplacée**

Le chargement réinitialise les inputs **avant** de vérifier le JSON et le script. De plus, le résultat négatif du parsing n’interrompt pas le chargement.

Reproductions effectuées :

- Un JSON invalide provoque une erreur après réinitialisation du script et du panier.
- Un parsing retournant `false` n’empêche pas l’installation du texte invalide et des autres paramètres de la configuration.

L’interface affiche éventuellement une erreur, mais ne restaure pas la session précédente.

**Recommandation :** préparer et contrôler la configuration dans un état temporaire, puis remplacer la session uniquement après réussite des contrôles. Une configuration invalide doit laisser le pricing courant intact. [Chargement](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:2871), [application depuis l’interface](C:/Users/admin/GitHub/structura/frontend/src/components/PayScriptConfigurations.vue:64)

### S-M05-05

**5. P2 — L’application d’une configuration remplace davantage d’hypothèses que ne le montre l’aperçu**

Même sans inclure le panier, une configuration conserve et recharge notamment :

- la devise de règlement ;
- le taux et les courbes de taux ;
- le funding ;
- le modèle et certains paramètres de calcul.

L’aperçu annonce principalement le remplacement du script, des paramètres et des dates. Le panier peut donc rester identique tandis que son contexte de valorisation change sensiblement.

**Recommandation :** afficher les changements matériels avant application et distinguer clairement l’application des termes économiques de celle des hypothèses de marché et de calcul. [Contenu sauvegardé](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:2936), [aperçu présenté](C:/Users/admin/GitHub/structura/frontend/src/components/PayScriptConfigurations.vue:14)

### S-M05-06

**6. P2 — Les dates affichées à côté des paramètres par observation peuvent correspondre au mauvais calendrier**

Economics utilise une liste commune regroupant les dates de tous les calendriers. Cette même liste sert à annoter chaque série de paramètres.

Avec des coupons trimestriels et des rappels annuels, la première barrière de rappel annuelle peut ainsi être affichée à côté de la première date trimestrielle. J’ai reproduit cette association incorrecte.

Le moteur possède sa propre logique de rang par calendrier : le défaut démontré concerne ici la **lecture et la saisie des termes dans l’interface**.

**Recommandation :** associer chaque `PARAM()` au calendrier depuis lequel il est utilisé et afficher exclusivement ses dates. Cette association devrait être fournie par le parsing. [Annotation des lignes](C:/Users/admin/GitHub/structura/frontend/src/components/EconomicsTab.vue:136), [agrégation des dates](C:/Users/admin/GitHub/structura/frontend/src/composables/useObservationPreview.js:43)

### S-M05-07

**7. P2 — L’aperçu des observations peut revenir à un ancien calendrier**

L’aperçu partagé ne protège pas ses réponses asynchrones contre les changements de contexte.

J’ai reproduit une ancienne réponse arrivant après la plus récente et remplaçant ses dates. Par ailleurs, changer uniquement la devise ne déclenche pas le recalcul, alors que celle-ci intervient dans les conventions de calendrier.

En cas d’échec de génération, l’aperçu peut aussi se rabattre sur les flux du dernier résultat, sans établir qu’ils correspondent aux termes actuellement affichés.

**Recommandation :** intégrer la devise aux dépendances, écarter les réponses périmées et afficher un état explicite lorsque le calendrier courant n’est pas résolu. [Chargement et dépendances de l’aperçu](C:/Users/admin/GitHub/structura/frontend/src/composables/useObservationPreview.js:43)

### S-M05-08

**8. P2 — Certains contrôles de l’assistant affichent une assurance économique excessive**

Le contrôle « Coupon à mémoire » recherche essentiellement une affectation à une variable dont le nom contient `MEMO`.

J’ai reproduit un statut vert **« Mémoire mise à jour après versement »** avec une variable `MEMO` qui ne participe jamais au calcul du coupon. La présence du motif est détectée ; le mécanisme de mémoire n’est pas démontré.

**Recommandation :** présenter ces résultats comme des indices de structure à confirmer. Pour les modèles reconnus, compléter par des trajectoires déterministes : coupon manqué, récupération, remise à zéro, rappel et maturité. [Contrôles structurels](C:/Users/admin/GitHub/structura/backend/app/services/llm/validate.py:130)

**Les lacunes de gouvernance à traiter ensuite**

La bibliothèque personnelle reste modifiable directement, sans contrôle de concurrence ni historique de révisions dans le chemin d’enregistrement examiné. Les configurations contiennent une empreinte du script, mais elle n’est pas vérifiée à l’application et ne couvre pas l’ensemble des paramètres et calendriers.

Pour une bibliothèque institutionnelle, je recommande des états **brouillon / validé / retiré**, des révisions identifiables, une empreinte de la configuration complète et une protection contre l’écrasement d’une version plus récente. Les snapshots contractuels des Products constituent déjà un socle utile ; cette gouvernance doit être ajoutée au niveau des modèles réutilisables. [Enregistrement des scripts](C:/Users/admin/GitHub/structura/backend/app/api/scripts_db.py:147), [métadonnées des configurations](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:3120)

Deux défauts secondaires sont également confirmés :

- **Analyse des libellés :** un `#` dans un libellé de paiement est traité comme un commentaire ; le mot `INDEX` dans un simple libellé peut déclencher une erreur de portée. Le traitement lexical doit distinguer texte et expressions. [Commentaires](C:/Users/admin/GitHub/structura/backend/app/core/payscript/parser.py:632), [analyse des références](C:/Users/admin/GitHub/structura/backend/app/core/payscript/parser.py:943)
- **Information sur l’IA :** l’aide de l’éditeur affirme que la description ne quitte pas la machine, alors que l’assistant permet de sélectionner un fournisseur distant. Le panneau détaillé donne une information plus juste ; les deux messages doivent être alignés. [Aide de l’éditeur](C:/Users/admin/GitHub/structura/frontend/src/components/PayScriptEditor.vue:25)

**L’ordre de correction recommandé**

1. **Sécuriser l’exécution du payoff** : indentation stricte et cohérence entre instructions exécutées et métadonnées.
2. **Préserver les Economics** : conversions de types explicites et conservation des séries incomplètes.
3. **Fiabiliser les configurations** : chargement atomique, contrôles de contenu et aperçu complet des changements.
4. **Rendre les dates affichées fiables** : rattachement des séries à leur calendrier et protection des réponses asynchrones.
5. **Renforcer la qualification des modèles** : révisions, scénarios économiques de référence et formulation précise des contrôles IA.

**Validation réalisée : 321 tests Python et 123 tests frontend réussis**, soit 444 tests ciblés ; un test ignoré et sept tests hors de cette sélection. Les anomalies décrites ont été vérifiées par des reproductions complémentaires isolées ou par lecture du chemin concerné, comme précisé ci-dessus.

Cette validation couvre la logique locale examinée. Elle ne constitue pas une recette complète dans le navigateur, une évaluation des réponses réelles d’un LLM ou une validation de la précision des modèles quantitatifs.

## M06

**Le module 6 possède un socle quantitatif sérieux, mais je ne le considérerais pas comme qualifié pour l’ensemble des combinaisons proposées dans le Pricer.** J’ai reproduit cinq anomalies prioritaires touchant directement les prix ou les flux exécutés, puis plusieurs divergences entre le prix, les probabilités et les sensibilités.

Aucun code ni donnée métier n’a été modifié. Les constats ci-dessous reposent sur le code actuel, des tests ciblés et des calculs synthétiques isolés. La calibration et la qualité des surfaces seront approfondies au module 7.

**Les points solides**

- **Les conventions de valorisation sont explicitement représentées.** Strike, value date, constatation et paiement disposent de champs distincts. Sur le chemin déterministe contrôlé, le décalage du paiement, le funding et le rebasage à la value date reproduisent exactement le résultat analytique attendu. [Contexte de valorisation](C:/Users/admin/GitHub/structura/backend/app/core/valuation_context.py:72)

- **La courbe sans risque alimente une construction commune du drift et de l’actualisation.** Les tests couvrent notamment le forward prépayé, la parité call-put, les courbes plates et pentues, ainsi que le déplacement parallèle de courbe. Cette architecture est saine, sous réserve du défaut de combinaison avec le funding décrit plus bas. [Construction des taux](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:1087)

- **Les protections d’entrée sont substantielles.** Modèles inconnus refusés, paramètres de diffusion contrôlés, matrices de corrélation vérifiées, réparation limitée et publiée, bornes de dimensions et budgets de calcul. Une dépendance fortement incohérente est rejetée. [Validation des requêtes](C:/Users/admin/GitHub/structura/backend/app/core/schemas.py:42)

- **Le Monte Carlo bénéficie de contrôles économiques utiles.** Black-Scholes, martingale du spot, limites dégénérées, antithétiques, réconciliation des flux et régressions numériques sont couverts. Les sondes supplémentaires réalisées sur le forward Heston restent cohérentes avec la référence dans les régimes examinés.

- **Les Greeks utilisent des tirages communs entre repricings.** Leur centre est recalculé avec le même nombre de trajectoires que les jambes bumpées. Le moteur prévoit aussi la transmission de l’état contractuel passé et refuse certains theta lorsque le franchissement d’une observation nécessiterait d’inventer une transition. [Calcul des sensibilités](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:2693)

- **L’interface protège le résultat principal contre certains changements de contexte.** Les réponses de pricing devenues périmées sont écartées ; les inputs du calcul sont conservés avec le résultat. C’est une bonne base pour la reproductibilité.

**Les anomalies prioritaires**

### S-M06-01

**1. P1 — Sous taux stochastiques, le funding contamine le drift et est compté deux fois dans l’actualisation**

La branche stochastique reconstruit ses forwards depuis des facteurs d’actualisation auxquels le funding a déjà été appliqué. Elle multiplie ensuite les facteurs stochastiques par le funding une seconde fois.

Sur un remboursement certain de 100 % à un an, avec taux sans risque de 3 % et funding de 2 % :

| Configuration | Prix obtenu |
|---|---:|
| Taux déterministes | **95,1229 %** |
| Taux stochastiques de volatilité presque nulle | **93,2394 %** |
| Référence attendue dans cette limite | **95,1229 %** |

L’écart atteint **1,88 point de nominal**. La convention « funding dans l’actualisation seule » n’est donc pas respectée dans cette branche.

**Recommandation :** construire les taux stochastiques exclusivement depuis la courbe sans risque, puis appliquer une seule fois le facteur de funding. Ajouter un contrôle de continuité lorsque la volatilité des taux tend vers zéro. [Branche concernée](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:2333)

### S-M06-02

**2. P1 — En mono-sous-jacent, la corrélation taux/action gonfle la variance du spot**

Le moteur construit un facteur adapté à la corrélation taux/action, mais les simulateurs ignorent ce facteur lorsqu’il n’existe qu’un sous-jacent. Le choc de taux est ensuite ajouté au choc de spot sans réduction correspondante de sa composante indépendante.

La variance du Brownien devient ainsi supérieure à celle demandée.

Sur un forward prépayé sans dividende, dont la valeur attendue est 100 % :

- corrélation taux/action nulle : **100,0111 %** ;
- corrélation de 80 % : **101,3188 %**, avec un IC95 excluant 100 %.

**Recommandation :** appliquer la factorisation conjointe également en dimension un, puis vérifier variance du spot, corrélation réalisée et martingale pour chaque modèle proposé. [Traitement mono-sous-jacent](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:429)

### S-M06-03

**3. P1 — Le pont brownien ne conserve pas la dépendance des extrema entre actifs**

Les extrema intra-pas sont tirés indépendamment pour chaque actif. Cette construction ne respecte pas leur loi jointe, même lorsque les trajectoires doivent être identiques.

Contrôle reproduit sur deux actifs parfaitement corrélés, avec mêmes extrémités et même volatilité :

- probabilité conditionnelle correcte de franchissement : environ **8,29 %** ;
- probabilité obtenue pour le franchissement par au moins un des deux actifs : **15,80 %**.

Dupliquer un actif identique augmente donc artificiellement le risque de barrière. Un calcul complet confirme également une différence entre le mono et son panier dupliqué en monitoring continu.

**Recommandation :** qualifier séparément les barrières mono et panier, reconstruire une dépendance intra-pas cohérente et expliciter les limites concernant les extrema conjoints. La mention actuelle d’exactitude sous diffusion lognormale est trop générale pour ces usages. [Pont brownien](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:857)

### S-M06-04

**4. P1 — Hull-White devient numériquement instable lorsque le retour à la moyenne approche zéro**

La correction de convexité contient des soustractions et divisions sensibles lorsque `a_r` devient petit. Des paramètres admis par l’API produisent alors des prix faux ou non finis.

Pour un zéro-coupon à un an, taux de 3 % et volatilité des taux de 3 % :

| Retour à la moyenne | Prix obtenu |
|---|---:|
| `0` | **97,0446 %** |
| `0,0001` | **97,0445 %** |
| `0,000001` | **148,4102 %** |
| `0,00000001` | **NaN** |

**Recommandation :** utiliser une formulation stable et une limite analytique vers le cas sans retour à la moyenne. Contrôler systématiquement la finitude des facteurs, trajectoires et résultats avant publication. [Correction de convexité](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:984)

### S-M06-05

**5. P1 — Deux dates contractuelles rapprochées peuvent être exécutées hors ordre chronologique**

Les événements sont regroupés sur les pas hebdomadaires. Lorsque deux dates distinctes tombent sur le même pas, leur exécution suit l’ordre des blocs dans le script.

Reproduction avec deux constatations aux **31 janvier et 1er février** :

- mise à jour d’une mémoire le 31 janvier, puis paiement le 1er février : **100 %** ;
- mêmes dates et mêmes instructions, mais blocs déclarés dans l’ordre inverse : **0 %**.

Les dates contractuelles sont pourtant différentes et déterminent sans ambiguïté l’ordre attendu.

**Recommandation :** préserver la chronologie exacte des événements, indépendamment de la grille utilisée pour la diffusion et le monitoring. L’ordre du texte peut départager des événements simultanés, pas inverser deux dates distinctes. [Regroupement sur la grille](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:2231)

**Les autres anomalies significatives**

### S-M06-06

**6. P2 — Les analyses annexes n’utilisent pas toujours le même horizon que le prix**

Le pricing principal ajuste son pas pour terminer exactement à l’horizon demandé. Les fonctions de trajectoires et de probabilités conservent un pas fixe de `1/52`.

Sur une option digitale à **un jour**, sans volatilité, avec taux de 5 % :

- prix principal : **0 %** ;
- analyse probabiliste : **99,9039 %** ;
- les trajectoires affichées vont jusqu’à environ **une semaine**.

Une incohérence d’annualisation existe également pour `REALVOL` entre un bloc terminal daté et `AT MATURITY`.

**Recommandation :** partager une définition commune de l’axe temporel entre prix, probabilités, trajectoires et variables annualisées. Ajouter des contrôles sur les maturités courtes et non rondes. [Trajectoires](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:3070), [probabilités](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:3208), [REALVOL terminal](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:1838)

### S-M06-07

**7. P2 — Les probabilités et les trajectoires peuvent décrire d’autres hypothèses que celles du prix affiché**

Le chemin probabiliste ne reprend pas le funding, les taux stochastiques et l’ensemble des conventions de paiement/rebasage du calcul principal. La visualisation des trajectoires ignore également la courbe de taux, pourtant reçue par l’API.

Sur un remboursement certain, une même requête peut ainsi produire **93,2394 % dans le prix principal et 97,0446 % dans l’analyse probabiliste**. Cet écart cumule ici le défaut de funding déjà identifié et l’absence de sa transmission à l’analytique.

**Recommandation :** faire consommer un même contexte de valorisation aux calculs annexes. Toute simplification volontaire doit être annoncée précisément à l’écran. L’existence d’un échantillon dédié ne justifie pas un changement d’hypothèses. [Appel des trajectoires](C:/Users/admin/GitHub/structura/backend/app/api/pricing.py:342), [appel des probabilités](C:/Users/admin/GitHub/structura/backend/app/api/pricing.py:398)

### S-M06-08

**8. P2 — Plusieurs conventions des Greeks restent incohérentes**

Trois écarts sont confirmés :

- **Corrélation :** un bump demandé de +5 points est plafonné, mais la dérivée reste divisée par 5 points. À une corrélation initiale de 100 %, le « bump positif » devient même une baisse à 99,9 %. Une sensibilité négative est alors publiée sur un worst-of dont la valeur augmente avec la corrélation.
- **Antithétiques :** l’API ne transmet pas le choix au calcul des Greeks, qui conserve son défaut activé lorsque le prix principal a été calculé sans antithétiques.
- **Vega LSV :** il est annoncé comme limité à la jambe indépendante, avec une couverture `1 − rho_h²`, alors que le bump LSV modifie toute la volatilité diffusée. Cette restriction décrit le traitement Heston, pas celui du LSV actuel.

**Recommandation :** employer des bumps admissibles avec leur amplitude réellement utilisée, assurer la continuité du contexte numérique et définir le périmètre du vega séparément pour chaque modèle. [Greeks et métadonnées](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:2693), [appel API](C:/Users/admin/GitHub/structura/backend/app/api/pricing.py:182)

### S-M06-09

**9. P2 — Certaines statistiques sont affichées avec une interprétation économique incorrecte**

Deux cas sont reproduits :

- Une option versant certainement **10 % du nominal** est classée par le moteur dans la catégorie « sous le pair ». L’interface réutilise cette catégorie comme **OTM** : elle affiche donc 100 % OTM pour une option certainement ITM.
- La tuile « VaR 5 % » est décrite comme un quantile non actualisé, alors que le moteur lui fournit un quantile actualisé. Un remboursement certain de 100 % à un an donne ainsi **97,0446 %** à 3 %.

**Recommandation :** distinguer explicitement ITM/OTM, remboursement sous le pair, perte en capital et quantile de valeur actualisée. Ces catégories doivent dépendre de la nature du payoff et de la grandeur mesurée. [Classification affichée](C:/Users/admin/GitHub/structura/frontend/src/components/ProbaTab.vue:155), [tuile de quantile](C:/Users/admin/GitHub/structura/frontend/src/components/ResultsPanel.vue:111)

**La précision et la qualification restent à renforcer**

L’IC95 du moteur mesure l’incertitude d’échantillonnage de son estimateur. Il ne couvre pas le biais de discrétisation, les écarts de calibration ou les défauts de modèle. Augmenter le nombre de trajectoires ne corrige pas ces écarts.

Pour le LSV, les trajectoires interagissent dans l’estimation de la fonction de levier. L’IC calculé depuis la dispersion d’un seul nuage de particules mérite donc une qualification spécifique. Le benchmark interne utilise déjà des réplications indépendantes ; cette approche n’est pas celle du résultat standard du Pricer. Je n’ai pas mesuré ici sa couverture statistique effective. [Calcul de l’IC](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:2576), [méthode du benchmark interne](C:/Users/admin/GitHub/structura/docs/audits/AUTOCALL_SURFACE_COMMUNE_2026-10-07.md)

Je recommande un statut de qualification fondé sur le modèle, le payoff, le monitoring, la convergence temporelle et la précision recherchée. Le seul choix « 50–100k trajectoires pour un prix final » est insuffisant.

Deux aides métier doivent aussi être rectifiées : **un modèle de taux déterministe peut avoir un rho non nul**, et **rho et sensibilité crédit peuvent avoir le même signe**. Un zéro-coupon le démontre immédiatement. [Aide sur les taux](C:/Users/admin/GitHub/structura/frontend/src/components/MarketParams.vue:98), [aide sur le crédit](C:/Users/admin/GitHub/structura/frontend/src/components/ResultsPanel.vue:877)

**L’ordre de correction recommandé**

1. Corriger les combinaisons taux/funding et la factorisation mono-sous-jacent.
2. Stabiliser Hull-White près de sa limite sans retour à la moyenne.
3. Garantir la chronologie contractuelle et qualifier les barrières continues sur panier.
4. Unifier les horizons et les hypothèses entre prix et analytiques.
5. Corriger les conventions des Greeks et des statistiques affichées.
6. Introduire une qualification numérique explicite, distincte de la réussite technique du calcul.

**Validation réalisée : 114 tests Python et 94 tests frontend réussis, soit 208 tests ciblés**, avec trois tests MTF exclus de la sélection. Les sondes complémentaires ont porté sur les identités économiques, les limites de paramètres et les combinaisons décrites ci-dessus.

Il n’y a eu ni lancement de services, ni appel à un fournisseur de marché, ni modification de base. Cette revue ne constitue pas une certification exhaustive de tous les modèles ou une recette complète du navigateur.

## M07

**Le module 7 dispose d’un bon socle SSVI, mais la qualification des calibrations reste insuffisante pour un usage institutionnel général.** Les principales réserves concernent la couverture de la matrice cible, la cohérence entre calibration et pricing, et le maintien d’un ancien chemin Local Vol qui peut masquer une surface invalide.

Aucun code ni donnée métier n’a été modifié. Les chiffres ci-dessous proviennent de contrôles synthétiques sur l’implémentation actuelle ; ils ne représentent pas des cotations de marché.

**Les points solides**

- **La distinction entre hypothèse synthétique et donnée de marché est claire.** Les profils Actions/Indices sont présentés comme indicatifs. Une volatilité réalisée peut servir de niveau de départ sans être qualifiée de volatilité implicite observée. C’est une distinction métier essentielle.

- **La construction SSVI possède de véritables contrôles d’arbitrage.** Variance ATM totale croissante, interpolation explicite et conditions suffisantes de calendrier/butterfly sur l’horizon déclaré : la démarche est cohérente avec la référence de [Gatheral et Jacquier](https://arxiv.org/pdf/1204.0646). Il faut conserver le terme « conditions suffisantes », qui ne signifie pas qu’une représentation rejetée constitue nécessairement une cotation arbitrable. [Implémentation SSVI](C:/Users/admin/GitHub/structura/backend/app/core/volatility_surface.py:16)

- **Les dérivées analytiques sont contrôlées.** Les tests rapprochent les dérivées de variance totale et les digitaux de différences finies indépendantes. Ils vérifient aussi la parité call-put et la limite de surface plate.

- **La surface atteint effectivement Local Vol et LSV.** Une cible plate retrouve le GBM avec les mêmes aléas ; modifier le smile change le prix. Le nouveau chemin SSVI refuse une densité invalide ou une grille hors domaine, sans substitution automatique. [Construction de la grille](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:359)

- **Les unités sont maîtrisées dans les principaux échanges.** Les piliers de surface restent en fractions moteur, tandis que les paramètres d’écran suivent leurs conversions propres. Les chemins RFQ et snapshots transportent la surface et le mode manuel/automatique.

- **L’éditeur annonce certaines limites de sa représentation.** Les paramètres de forme sont communs aux maturités ; une édition d’aile peut donc modifier plusieurs cellules. Le mode manuel des paramètres Heston/SABR est respecté par la fonction de calibration.

- **La documentation quantitative distingue correctement plusieurs erreurs.** Résidu de calibration, erreur numérique du simulateur et risque de dynamique ne sont pas confondus. Le benchmark historique à 208 pas/an n’est pas présenté comme une certification générale de l’application à 52 pas/an.

**Les anomalies prioritaires**

### S-M07-01

**1. P1 — Une modification matérielle de la matrice peut être complètement invisible pour la calibration**

L’ajustement utilise une grille fixe de maturités : 6 mois, 1 an, 2 ans, 4 ans et l’horizon demandé. Elle ne reprend pas tous les piliers éditables.

Reproduction sur un horizon de dix ans :

- ATM 7 ans relevée de **30 % à 35 %** ;
- surface modifiée acceptée ;
- paramètres Heston **strictement identiques** ;
- erreur maximale annoncée **strictement identique** ;
- déplacement du prix cible du call ATM forward à sept ans : **418,24 bps du spot initial**.

La calibration ne voit simplement aucun des points modifiés.

**Recommandation :** inclure les piliers matériels de la surface et les échéances pertinentes du produit dans l’objectif et dans les contrôles. Publier la grille réellement utilisée ; l’expression « erreur maximale » doit préciser son domaine. [Grille de calibration](C:/Users/admin/GitHub/structura/backend/app/core/smile_calibration.py:37)

### S-M07-02

**2. P1 — Une calibration peut être acceptée alors que le contexte de pricing a changé**

La protection contre les réponses périmées fonctionne pour des changements portés par le sous-jacent, comme la surface ou le passage en mode manuel. Elle ne couvre pas correctement les paramètres globaux capturés au lancement.

J’ai reproduit ce déroulement dans les fonctions réelles :

1. préparation d’un pricing et calibration avec un taux de **3 %** ;
2. taux porté à **4 %** pendant l’attente ;
3. calibration à 3 % appliquée avec statut `ready` ;
4. préparation du calcul déclarée réussie, sans erreur, alors que le taux courant est 4 %.

Deux calibrations qui se chevauchent peuvent aussi se perturber : la première modifie les paramètres et provoque le rejet de la seconde, pourtant demandée pour le contexte le plus récent.

**Recommandation :** identifier une révision complète du contexte de calibration, vérifier cette révision avant application et avant construction de la requête de pricing. Le serveur devrait également pouvoir vérifier le lien entre cible, paramètres et contexte déclaré. [Application des résultats](C:/Users/admin/GitHub/structura/frontend/src/utils/smileCalibration.js:5), [préparation du pricing](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:1003)

### S-M07-03

**3. P1 — L’ancien chemin Local Vol accepte encore des smiles invalides et utilise une valeur de repli**

Les garanties du nouveau chemin SSVI ne s’appliquent pas au chemin historique fondé sur `sigma`, `skew` et `curvature`, toujours utilisable sans surface SSVI.

Sur une cible avec niveau de 20 %, skew −0,20 et courbure 0,10 :

- la convexité du prix de call devient négative dans l’aile basse à quatre ans ;
- l’inversion Dupire retourne alors la volatilité implicite comme valeur de repli ;
- le moteur poursuit le pricing sans signalement de surface ou de fallback.

Un calcul quatre ans sur cette configuration produit effectivement un prix fini, sans avertissement.

**Recommandation :** appliquer au chemin historique des contrôles explicites de validité et de domaine. Identifier les anciens dossiers concernés et organiser leur qualification ; une migration ne doit pas remplacer silencieusement leurs hypothèses. [Inversion historique et replis](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:238)

**Les autres anomalies significatives**

### S-M07-04

**4. P2 — « Optimisation terminée » et « calibration acceptable » restent insuffisamment séparées**

La fonction frontend applique les paramètres reçus et passe à `ready`, même lorsque le serveur renvoie `success = false`. L’interface affiche bien « optimisation non convergée », mais ce résultat reste utilisable par la préparation du pricing.

Avec une réponse simulée non convergée présentant 500 bps d’erreur, les paramètres sont remplacés et le statut devient `ready`.

Par ailleurs, une convergence réussie peut laisser un résidu matériel. Sur le profil Actions à 30 %, horizon quatre ans, taux 3 % et dividende 2 %, le service actuel annonce :

| Modèle | Convergence | Erreur vanille maximale annoncée |
|---|---|---:|
| Heston | Réussie | **34,94 bps** |
| SABR spot | Réussie | **163,54 bps** |

Un contrôle Heston par intégration adaptative distincte mesure aussi **103,60 bps d’écart sur un digital**, à un an et strike égal au spot initial.

**Recommandation :** distinguer résultat disponible, convergence numérique et qualification économique. Prévoir des seuils par usage et des contrôles de digitaux aux niveaux de protection et de rappel. L’exploration peut conserver un ajustement imparfait ; son exploitation doit porter cette réserve explicitement. [Résultat d’optimisation](C:/Users/admin/GitHub/structura/backend/app/core/smile_calibration.py:85), [statut frontend](C:/Users/admin/GitHub/structura/frontend/src/utils/smileCalibration.js:24)

### S-M07-05

**5. P2 — L’intégration Fourier Heston manque de contrôles dans certains régimes**

La fonction servant à la calibration emploie une quadrature fixe et une borne d’intégration fixe. Elle vérifie la finitude des prix, mais pas leur positivité, leur monotonie ou leur convergence numérique.

Avec une variance initiale et long terme de `0,0001`, des paramètres admissibles produisent à un an :

- call strike 120 % : **prix négatif**, environ −0,46 bp ;
- call strike 150 % : prix artificiellement positif d’environ +0,35 bp.

Une intégration adaptative étendue retrouve des valeurs pratiquement nulles.

**Recommandation :** contrôler les bornes d’arbitrage et la convergence de l’intégration, puis adapter la méthode aux régimes de faible variance et de courte maturité. Un optimiseur ne doit pas ajuster les erreurs de son propre évaluateur. [Évaluation Fourier](C:/Users/admin/GitHub/structura/backend/app/core/smile_calibration.py:13)

### S-M07-06

**6. P2 — La preuve de pricing ne conserve pas le dossier de calibration**

La surface et les paramètres numériques sont transmis, mais la requête typée et la preuve serveur ne portent pas le rapport complet de calibration : grille, objectif, résidus, convergence, paramètres de calcul et contexte précis de l’ajustement.

Le diagnostic peut exister dans l’état frontend ou un snapshot d’édition. Cela ne constitue pas une preuve serveur attachée au prix conservé.

**Recommandation :** enregistrer un résultat de calibration identifié et lié aux empreintes de la cible et du contexte. Conserver au minimum méthode/version, points ajustés, pondérations, paramètres, convergence et erreurs de validation. [Paramètres transmis au moteur](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:613), [preuve de pricing](C:/Users/admin/GitHub/structura/backend/app/core/valuation_context.py:301)

### S-M07-07

**7. P2 — Vider un champ de forme peut modifier matériellement le smile**

Les champs d’asymétrie et d’intensité convertissent directement leur texte avec `Number()`. Une chaîne vide devient zéro.

Sur le profil Actions à 30 %, vider l’intensité puis valider peut donc transformer une aile 60 % de **42,25 % de volatilité en 30 %**, en aplatissant la surface.

**Recommandation :** distinguer une valeur absente d’un zéro explicitement saisi. Restaurer la dernière valeur valide ou demander de renseigner le champ avant application. [Conversion des champs](C:/Users/admin/GitHub/structura/frontend/src/components/VolSurfaceEditor.vue:24)

**Les limites de conception qui restent à traiter**

**La représentation des ailes est encore restrictive.** Le tableau reste limité à 60/80/100/120/140 % du forward, sans 50 %. Une cellule ajuste un paramètre global de forme ; la matrice ne permet donc pas de reproduire librement une cible de desk. Cette réserve, déjà documentée le 8 octobre, reste actuelle. [Diagnostic des ailes basses](C:/Users/admin/GitHub/structura/docs/projects/pricing/SMILE_ACTIONS_URGENT_2026-10-08.md)

Je recommande de partir d’une matrice cible contextualisée — sous-jacent, date, maturités, ATM et convention de moneyness — puis de mesurer son résidu de représentation. Un échec de représentation dans la famille actuelle doit rester distinct d’un diagnostic d’arbitrage.

**La calibration utilise des taux et dividendes plats.** Les courbes peuvent ensuite intervenir dans le pricing, mais elles ne font pas partie du contexte d’ajustement ni de sa clé d’invalidation. L’interface le précise, ce qui est positif ; cette limite empêche toutefois de considérer les paramètres comme calibrés sur le contexte complet du calcul.

**L’horizon et la précision restent bornés.** L’ajustement est limité à dix ans. SABR utilise 3 000 paires et 104 pas/an dans son objectif, tandis que le pricing standard reste à 52 pas/an. L’erreur annoncée sur les points ajustés ne couvre ni les autres points, ni le biais temporel, ni l’incertitude de l’ajustement.

**L’absence d’arbitrage ne certifie pas la dynamique.** Une cible SSVI valide et des marginales correctement reproduites ne suffisent pas à qualifier les rappels conditionnels, les barrières sur panier ou toutes les combinaisons avec taux stochastiques. Les réserves du module 6 restent applicables.

**L’ordre de correction recommandé**

1. Faire couvrir à la calibration les piliers matériels et sécuriser son contexte asynchrone.
2. Supprimer les replis silencieux sur les surfaces historiques invalides.
3. Séparer disponibilité technique, convergence et qualification économique.
4. Renforcer l’évaluateur Heston et les contrôles de vanilles/digitaux hors grille d’ajustement.
5. Conserver une preuve de calibration attachée au prix.
6. Reprendre la représentation des ailes avec une matrice cible explicite, puis intégrer les courbes complètes.

**Validation réalisée : 29 tests backend et 11 tests frontend réussis, complétés par sept fonctions de test exécutées isolément.** Les sondes complémentaires ont vérifié les piliers non échantillonnés, les changements de contexte, les résidus de calibration, l’intégration Fourier et le chemin historique.

Aucun service n’a été lancé et aucune cotation réelle n’a été acquise. La recette visuelle complète, la validation indépendante exhaustive du SABR et la qualification des régimes extrêmes restent hors de cette vérification.

## M08

**Le Product Optimizer présente une bonne architecture de recherche, mais son parcours sauvegardé et certains contrôles numériques doivent être corrigés avant une utilisation institutionnelle régulière.** Le principal défaut bloque deux modes pourtant proposés dans l’interface.

Audit réalisé sur le code actuel, après lecture de `CLAUDE.md` et des notes du domaine. Aucun fichier source ni donnée métier modifié.

**Périmètre examiné**

J’ai suivi les huit familles proposées, les objectifs coupon/participation/cap/protection, la génération des candidats, les conventions de paiement, le marché utilisé, la résolution numérique, la validation indépendante, le classement et le parcours de sauvegarde/reprise.

Le périmètre annoncé reste explicite : GBM, barrières européennes, un à trois actifs de même devise, recherche à l’émission.

**Points solides**

- **Un seul moteur de payoff.** L’Optimizer réutilise les scripts du catalogue, leur résolution de calendrier et le moteur PayScript. Les conversions de coupon distinguent correctement coupon annuel, coupon unique de reverse convertible et coupon unique du gear put. Cela limite les divergences avec le Pricer. [Construction et pricing des candidats](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/service.py:109)

- **Une validation indépendante bien structurée.** La recherche utilise une graine d’exploration, puis fige au maximum cinq candidats. Leur paramètre résolu reste inchangé pendant deux nouvelles simulations, à N puis 2N. Les candidats rejetés ne sont pas remplacés après consultation des résultats de validation. [Validation](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/validation.py:77)

- **Un traitement statistique sérieux des trajectoires antithétiques.** Les métriques utilisent les deux jambes et calculent leur variance sur les paires. Les bornes de Bernstein évitent notamment de conclure à une probabilité nulle simplement parce qu’aucune perte n’a été observée. La correction simultanée tient compte de la taille de la sélection. [Statistiques](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/statistics.py:14)

- **Une économie d’émission lisible.** Le budget du payoff correspond au prix d’émission moins frais et marge initiaux. La perte investisseur reste comparée au prix brut, tandis que la perte de la jambe put dispose de métriques distinctes sur booster et gear put. Les courbes et le funding suivent le candidat jusqu’à la validation.

- **Un marché traçable.** Références, valeurs utilisées, surcharges, dates et sources sont conservées dans un snapshot avec empreinte. Les valeurs absentes restent à renseigner. Le contrat contrôle les devises, les courbes, les doublons et la corrélation, sans réparation implicite. [Contrat de marché](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/contracts.py:89), [snapshot](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/market.py:25)

- **Un parcours de recherche distinct du booking.** Propriété des dossiers, clé de lancement idempotente, calcul détaché de la page, conservation progressive et interruption après redémarrage sont prévus. Les tests isolés exécutés confirment ces mécanismes sur les scénarios couverts. [Service de recherche](C:/Users/admin/GitHub/structura/backend/app/services/optimizer_research.py:58)

- **Des résultats exploitables même après rejet.** L’interface conserve les prix calculés et leurs diagnostics, distingue exploration et confirmation, et réserve recommandation et frontière aux candidats confirmés. Le radar possède des échelles explicites, sans score composite mélangeant risque et rendement.

**Anomalies constatées**

### S-M08-01

**1. P1 — Deux modes ne peuvent pas être lancés depuis le parcours sauvegardé**

La création du résumé utilise `getattr` sur `payoff_settings`, qui est un dictionnaire.

Reproduction en SQLite isolée :

- Athena standard : sauvegarde réussie ;
- Athena dégressif : `AttributeError` sur `decrement` ;
- booster « cap maximal » : `AttributeError` sur `participation`.

Le parcours principal sauvegarde la demande avant de lancer le calcul : ces deux modes échouent donc avant le pricing, malgré leur présence dans les capacités proposées. Les tests quantitatifs directs ne détectent pas ce défaut.

**Recommandation :** corriger la lecture des réglages et couvrir la création d’une recherche pour chaque couple famille/objectif, avec vérification du résumé et des paramètres conservés. [Ligne concernée](C:/Users/admin/GitHub/structura/backend/app/services/optimizer_research.py:90)

### S-M08-02

**2. P2 — Le plafond du solveur écarte des structures finançables**

L’Optimizer impose 18 itérations avec une tolérance interne de `1e-6`, indépendamment de la largeur de l’intervalle de résolution.

Cas réel reproduit : reverse convertible à 48 mois, volatilité 20 %, dividende 2 %, taux 3 %, protection 60 %, N = 1 000.

À la 18e itération, le prix atteint **99,9998 %**, mais le candidat est abandonné pour non-convergence. À la **19e**, la résolution converge à 100 %. Avec ce seul changement en mémoire, le candidat passe ensuite la validation indépendante, pour un coupon annuel d’environ **4,6547 %**.

L’écart ayant déclenché l’abandon était de **0,02 bp**, alors que la tolérance de prix demandée était de trois points de nominal. Ce défaut peut retirer un candidat pertinent de la recherche.

**Recommandation :** dimensionner le nombre d’itérations selon les bornes et la précision nécessaire, puis contrôler le résidu de prix après arrondi. Conserver le diagnostic numérique sans présenter ce cas comme une impossibilité économique. [Appel du solveur](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/service.py:150)

### S-M08-03

**3. P2 — La qualification d’une famille ne protège pas suffisamment ses hypothèses économiques**

Les contrôles vérifient les déclarations, les calendriers, la présence de `STOP` et certains libellés. Ils ne comparent pas le script à une version économiquement approuvée.

Dans une expérience isolée en mémoire, j’ai remplacé le coupon Athena linéaire par un coupon non linéaire, en conservant déclarations et libellés. La famille est restée `SUPPORTED`, le candidat a passé la validation et le diagnostic a continué à appliquer la règle réservée au coupon affine.

Cela ne démontre pas une erreur dans les scripts actuels. Cela démontre qu’un changement matériel du payoff peut traverser la protection annoncée sans requalification de son adaptateur.

**Recommandation :** associer chaque adaptateur à une version qualifiée du script, avec empreinte approuvée et invariants économiques. Les diagnostics de pente doivent dépendre de propriétés effectivement qualifiées. [Qualification](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/families.py:70), [diagnostic du paramètre](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/validation.py:17)

### S-M08-04

**4. P2 — L’immutabilité SQL des résultats terminaux est contournable**

Le déclencheur compare notamment `NEW.result_json != OLD.result_json`. Or cette comparaison ne détecte pas correctement les transitions impliquant `NULL`, et la colonne accepte cette valeur.

Reproduction sur un dossier terminé :

- modification directe du résultat : refusée ;
- passage du résultat à `NULL`, puis remplacement par un autre résultat : accepté.

Le contournement nécessite un accès SQL en écriture. Il fragilise néanmoins la garantie explicite de conservation des preuves jusque dans la base.

**Recommandation :** utiliser des comparaisons compatibles avec `NULL`, rendre les champs de preuve obligatoires et vérifier l’installation des protections lors des migrations. Ajouter ce scénario aux tests d’immutabilité. [Déclencheur](C:/Users/admin/GitHub/structura/backend/app/services/optimizer_research.py:26), [colonnes](C:/Users/admin/GitHub/structura/backend/app/db/models.py:95)

### S-M08-05

**5. P2 — Le budget temps maximal n’est pas garanti en séquentiel**

L’arrêt est contrôlé entre les candidats et entre les validations. Un appel numérique déjà engagé poursuit son travail.

Avec une horloge simulée, j’ai reproduit une recherche disposant de **30 secondes** de budget, dont la dernière validation finit à **60 secondes** : le résultat reste `complete=true`, sans motif de dépassement.

Le nombre de processus retenu peut être ramené à un, notamment pour une recherche à un seul candidat. Ce comportement concerne donc un usage courant.

**Recommandation :** prévoir une interruption pendant les calculs longs, ou isoler également les calculs unitaires dans un processus interruptible. En attendant, présenter le budget comme une limite souple et enregistrer systématiquement son dépassement. [Contrôles d’arrêt](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/service.py:274), [statut final](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/service.py:385)

### S-M08-06

**6. P2 — La reprise peut rendre invalide un dossier initialement valide**

La reprise arrondit certains scalaires aux deux décimales affichées, tout en conservant la précision des courbes.

Exemple reproduit :

- dossier valide avec `q = 2,001 %` et premier bucket de dividendes à `2,001 %` ;
- reprise du scalaire à `2,00 %` ;
- premier bucket conservé à `2,001 %` ;
- rejet backend puisque le premier bucket doit correspondre à `q`.

Le cas concerne les dossiers ayant une précision supérieure à celle du formulaire, notamment ceux créés par API.

**Recommandation :** conserver les valeurs effectives exactes lors d’une reprise. L’arrondi d’affichage doit rester distinct de la valeur envoyée, jusqu’à une modification explicite. [Reprise](C:/Users/admin/GitHub/structura/frontend/src/utils/optimizerResume.js:6)

### S-M08-07

**7. P3 — Un avertissement contredit la sauvegarde automatique**

Les capacités annoncent encore : « Résultats temporaires dans la page ; exporter le JSON avant de la quitter. » Ce texte est également repris dans les résultats sauvegardés.

**Recommandation :** distinguer les limites de l’ancien flux temporaire de celles des recherches persistantes et harmoniser la documentation. [Avertissement](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/capabilities.py:29)

**Limites de qualification à conserver explicitement**

La confirmation actuelle signifie que le candidat satisfait les contrôles implémentés **sous le modèle et le marché choisis**. Elle ne certifie pas :

- une cotation exécutable : les volatilités restent des estimations réalisées utilisées comme hypothèses GBM ;
- la robustesse du résultat aux dividendes, à la volatilité, à la corrélation ou au funding ;
- la convergence temporelle des observations approchées sur une grille hebdomadaire ;
- un optimum global : la recherche porte sur une grille finie, puis une sélection limitée à cinq candidats.

Ces limites sont globalement documentées. Elles doivent rester visibles près de la recommandation. L’incertitude Monte-Carlo ne couvre pas l’incertitude de marché ou de modèle.

**Ordre de traitement recommandé**

1. **Rétablir le parcours complet** des huit familles et corriger le rejet numérique des candidats finançables.
2. **Renforcer la conservation des preuves** : immutabilité SQL, reprise exacte des entrées et version qualifiée du script, de l’adaptateur et du moteur.
3. **Fiabiliser l’exploitation** : arrêt effectif, dépassement de budget explicite et avertissements cohérents.
4. **Compléter la qualification quantitative** par une convergence temporelle et des perturbations locales autour des candidats retenus, distinctes de l’exploration large.

**Vérifications réalisées**

- **125 tests backend ciblés réussis** sur contrats, payoffs, marché, validation et orchestration.
- **6 tests supplémentaires de persistance/API réussis**, avec SQLite isolée et dépendances d’authentification/session substituées.
- **71 tests frontend réussis** sur les utilitaires, formulaires et résultats.
- Reproductions complémentaires des anomalies décrites ci-dessus, en mémoire ou en base isolée.

La suite backend complète, les processus de calcul réels et la recette navigateur n’ont pas été relancés. Aucun service applicatif démarré, aucun appel fournisseur effectué, aucune base métier modifiée.

## M09

**Le module 9 — RFQ fournisseurs et analyse des cotations — possède de bons contrôles de sélection et de traçabilité, mais plusieurs incohérences fragilisent la comparaison des réponses et les statistiques fournisseurs.** La priorité concerne le gel des termes, puis la conservation des décisions et des références de prix.

L’audit porte sur l’état actuel du code, changements locaux compris. **Aucun fichier source ni donnée métier modifié.**

**Périmètre examiné**

Création et préparation des RFQ, sollicitation manuelle, réception des réponses, validité, last look, sélection, prix modèle, historique et analyse fournisseurs. Les interfaces avec les réponses réseau ont été examinées lorsqu’elles alimentent cette comparaison ; le transport et la confirmation d’exécution restent au module 10.

**Points solides**

- **La RFQ s’appuie sur un Product et une version contractuelle identifiés.** La composition du pricing reprend les termes canoniques et leur associe les hypothèses privées. La préparation distingue correctement ce qui est demandé de la manière dont Structura le valorise. [Composition du pricing](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1328)

- **Les termes sont normalement figés dès la sollicitation.** Les modifications contractuelles, juridiques et commerciales sont contrôlées côté serveur. Les nouveaux dossiers conservent également un tour figé, ce qui protège les termes même après suppression de leurs lignes de cotation.

- **Plusieurs sélections incohérentes sont refusées.** Réponse sans prix, quote d’une autre RFQ, réponse déclinée, expirée ou remplacée : les contrôles ne reposent pas uniquement sur les boutons de l’interface. Le changement de réponse retenue efface normalement la justification de l’ancien choix. [Sélection](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1747)

- **Le sens économique est correctement traité.** Le meilleur prix est le plus bas à l’achat et le plus haut à la vente. L’écart favorable au modèle possède un signe cohérent entre ces deux directions. Les prix moteur sont convertis en points de nominal avant comparaison.

- **Le last look conserve les deux réponses.** La contre-cotation est liée à l’originale, les chaînes supplémentaires sont refusées et la réponse initiale est exclue du comptage lorsqu’elle est remplacée. Une contre-cote dégradant le prix est normalement refusée.

- **Les droits et la confidentialité sont intégrés.** Les dossiers récents appartiennent à un périmètre organisation/desk ; les données privées de pricing et le contexte client sont filtrés selon les habilitations.

- **La piste après booking est protégée.** Les modifications structurelles des cotations et de la sélection sont refusées lorsqu’un Deal existe. Les annotations restent possibles. Les publications réseau conservent leur propre historique et ne sont pas éditables comme une réponse manuelle.

**Anomalies constatées**

### S-M09-01

**1. P1 — Le gel contractuel peut être contourné dans la copie RFQ par `pricing_params`**

La fusion des hypothèses de pricing utilise une liste locale de champs contractuels à ignorer. Cette liste omet notamment `payment_date`, `maturity_date` et `frozen_schedule`.

**Reproduction sur un dossier avec desk habilité et fournisseur déjà sollicité :** une modification de `payment_date` transmise par `pricing_params` est acceptée. La date stockée dans la RFQ change, tandis que le Product conserve sa date initiale et sa version contractuelle.

Le pricing canonique continue à reprendre la date du Product. La RFQ affichée et les termes effectivement pricés peuvent donc se contredire.

**Recommandation :** limiter strictement cette opération aux hypothèses de marché et de modèle autorisées, réutiliser la définition centrale des termes et refuser explicitement toute tentative de modification contractuelle. [Fusion concernée](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:591)

### S-M09-02

**2. P2 — L’analyse historique écarte les réponses réseau après leur traitement**

Le filtre de l’analyse fournisseurs exclut les réponses réseau dont `comparable` est faux. Or cet indicateur décrit leur éligibilité **actuelle** à une nouvelle sélection.

Une réponse réservée au traitement devient `RESERVED`. Une réponse d’un tour terminé devient également inactive. Ces états ne doivent pas faire disparaître leur contribution historique.

**Reproduction isolée :** une réponse réseau gagnante est restituée avec `won=true`, `rfq_status=clos` et `comparable=false`, puis éliminée par le filtre frontend. Une réponse manuelle équivalente reste comptée.

Cela biaise volumes, écarts moyens et hit ratios selon le canal utilisé.

**Recommandation :** séparer l’éligibilité courante, le rôle historique de la réponse et le résultat de la consultation. Calculer les statistiques sur les réponses finales retenues pour chaque fournisseur et chaque tour. [Filtre historique](C:/Users/admin/GitHub/structura/frontend/src/views/RfqAnalysisView.vue:160), [états de publication](C:/Users/admin/GitHub/structura/backend/app/services/rfq_publication.py:110)

### S-M09-03

**3. P2 — Les modifications des réponses manuelles ne réévaluent pas suffisamment la décision**

Deux cas reproduits :

- RFQ acheteuse, réponse initiale à **100**, last look à **99** ; modifier ensuite l’originale à **98** est accepté. La réponse à 98 reste marquée remplacée et celle à 99 demeure comparable.
- Une réponse sélectionnée à **99**, avec motif « Prix », peut être modifiée à **105** tout en conservant sa sélection et son motif.

Les contrôles examinent la modification d’une contre-cote, mais ne protègent pas symétriquement ses dépendances. La sélection porte sur une ligne mutable plutôt que sur une réponse économique précise.

**Recommandation :** versionner les révisions matérielles, conserver l’ancienne réponse et invalider ou faire reconfirmer la sélection lorsqu’un prix ou une condition change. Recontrôler également la relation parent/last look. [Mise à jour des cotations](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1959)

### S-M09-04

**4. P2 — Une réponse dans une autre devise peut être comparable et sélectionnée**

Une quote portant `currency=USD` a été acceptée, déclarée comparable et sélectionnée sur une RFQ en EUR.

La devise de la réponse n’entre pas dans le contrôle courant de comparabilité. Elle n’est pas non plus visible dans la table principale des cotations. Un contrôle existe plus tard dans la préparation du traitement, mais l’incohérence traverse déjà la comparaison et la sélection.

**Recommandation :** reprendre explicitement la devise demandée lorsqu’elle n’est pas renseignée et refuser une devise différente dans ce parcours. Toute contre-proposition doit conserver une qualification distincte et visible. [Comparabilité](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:411)

### S-M09-05

**5. P2 — La référence modèle historique reste mutable et insuffisamment documentée**

L’historique compare toutes les réponses au `model_price` actuellement stocké sur la RFQ.

**Reproduction :** pour une réponse à 99, un modèle passant de 100 à 105 fait évoluer l’écart favorable de **100 à 571,4 bps**, sans changement de date de cotation. L’historique ne restitue pas la date du prix modèle permettant d’expliquer cette révision.

Par ailleurs, l’API accepte un prix modèle scalaire sans reçu de calcul, puis lui associe l’empreinte courante des paramètres. Cette empreinte ne démontre pas que le chiffre provient du moteur. La réponse détaillée et son intervalle restent principalement en mémoire côté navigateur.

**Recommandation :** rattacher le prix à un calcul archivé : entrées effectives, résultat, intervalle, date de marché, moteur et reçu serveur. Distinguer la référence historique de décision d’une nouvelle valorisation. [Historique](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1100), [enregistrement du prix](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1723)

### S-M09-06

**6. P2 — Le panneau de contrôle peut afficher un ancien calcul face au nouveau prix serveur**

Le cache détaillé est essentiellement associé à l’identifiant de la RFQ. Recharger le même dossier ne vérifie pas qu’il correspond toujours au prix et aux hypothèses reçus.

**Reproduction avec le store actuel :** le serveur restitue un modèle à **105**, tandis que le panneau conserve un calcul à **100** et son ancien intervalle de confiance.

Le tableau et le panneau censé expliquer le prix peuvent donc présenter deux références différentes.

**Recommandation :** associer la décomposition à l’identifiant du calcul et à son empreinte. L’invalider si la référence serveur change, puis charger le calcul correspondant. [Rechargement du dossier](C:/Users/admin/GitHub/structura/frontend/src/stores/rfq.js:50)

### S-M09-07

**7. P2 — Le graphique écrase les cotations d’un même fournisseur le même jour**

Le graphique conserve une seule valeur par fournisseur et date, par affectation successive. Le tableau de synthèse utilise pourtant toutes les observations.

**Reproduction :** deux écarts de **+100 et −300 bps** donnent une moyenne de −100 bps dans la synthèse. Le graphique affiche −300 ou +100 selon l’ordre des lignes reçues.

**Recommandation :** afficher chaque observation horodatée ou définir une agrégation quotidienne explicite, avec nombre d’observations et dispersion. Le résultat doit être indépendant de l’ordre technique des lignes. [Construction du graphique](C:/Users/admin/GitHub/structura/frontend/src/views/RfqAnalysisView.vue:238)

### S-M09-08

**8. P2 — La cohérence des horaires n’est contrôlée que dans un sens**

La relation entre réception et expiration est vérifiée lorsque `valid_until` est envoyé. Modifier uniquement `quoted_at` ne rejoue pas ce contrôle.

J’ai pu déplacer la réception après la fin de validité enregistrée, sans refus.

**Recommandation :** valider l’état final complet après fusion des changements, quelle que soit la donnée modifiée. Conserver distinctement heure déclarée de réponse et heure de saisie. [Contrôle chronologique](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:2001)

### S-M09-09

**9. P2 — Plusieurs refus de mise à jour ne sont pas restitués dans l’écran**

Les gestionnaires de prix, statut et dates appellent la mise à jour sans attendre ni traiter son rejet. L’ajout, la suppression et la sélection présentent aussi des chemins sans gestion locale d’erreur.

Le serveur peut correctement refuser une opération sans que l’utilisateur dispose d’un message métier exploitable ou d’une restauration explicite du champ.

**Recommandation :** afficher le refus près de la ligne, distinguer saisie en cours/enregistrée/refusée et recharger la valeur serveur après échec. [Gestionnaires concernés](C:/Users/admin/GitHub/structura/frontend/src/views/RfqView.vue:2538)

**Points déjà identifiés dans les modules précédents**

Les réserves du module 2 restent applicables au rapprochement fournisseur/contrepartie : lien juridique explicite invalide pouvant provoquer un repli par nom, et cotations manuelles dépendantes de libellés courants.

La synchronisation d’une ancienne RFQ vers le Product conserve également le risque de régression de version signalé au module 4.

À l’inverse, **le motif de sélection facultatif et la qualification de fermeté au booking correspondent à des choix métier explicites**. Je ne les classe pas comme défauts. La ligne de crédit envisagée dans la documentation reste un chantier distinct, à qualifier avant de l’utiliser comme contrôle.

**Ordre de traitement recommandé**

1. **Sécuriser la comparaison contractuelle** : fermeture de `pricing_params`, cohérence de devise et contrôle complet des horaires.
2. **Attacher chaque décision à une réponse précise** : révisions manuelles, sélection et last look.
3. **Fiabiliser les références et statistiques** : calcul modèle archivé, historique indépendant de l’état actif courant, graphique déterministe.
4. **Rendre les échecs visibles** : erreurs de saisie, décomposition périmée et état d’enregistrement.

La recette prioritaire devrait suivre une RFQ mêlant réponses manuelles et réseau, avec révision, expiration, sélection, traitement puis consultation historique. Les réponses finales et leur résultat commercial doivent rester correctement comptés à chaque étape.

**Vérifications réalisées**

- **58 tests backend ciblés réussis**, avec dépendances de connexion et de base isolées.
- **49 tests frontend réussis**.
- Reproductions complémentaires en SQLite mémoire, notamment avec desk habilité et clés étrangères actives.
- Vérifications des fonctions frontend de filtrage, de graphique et de cache.

Aucune suite backend complète, aucun service applicatif ni appel fournisseur lancé. Le rendu navigateur et la chaîne réelle de transport/exécution restent à recetter.

## M10

**Module 10 — RFQ reçues, réseau et exécutions**

Le module possède une base solide : termes figés, calcul bancaire privé, publication explicitement validée, transport persistant et protection contre le double booking. La séparation entre réception technique, sélection commerciale et confirmation de traitement est correctement conçue.

**J’ai néanmoins confirmé cinq anomalies, dont deux prioritaires avant un pilote de traitement entre installations.** Elles concernent la réouverture des consultations, le rapprochement juridique et la fiabilité de certains états d’interface.

L’audit porte sur le code actuel, la documentation et des vérifications isolées. Aucun code ni aucune donnée métier n’a été modifié.

**Les points solides**

- **La demande reçue conserve son identité contractuelle.** Le transport vérifie les termes, leur empreinte, les conventions de prix, le nominal, la devise et les adresses commerciales. Les identifiants propres à chaque installation sont rapprochés localement. La prise en charge bancaire contrôle ensuite la compatibilité des termes avec le moteur. [Réception réseau](C:/Users/admin/GitHub/structura/backend/app/services/rfq_transport.py:210), [prise en charge bancaire](C:/Users/admin/GitHub/structura/backend/app/services/rfq_bank.py:94).

- **Le calcul bancaire reste privé.** La banque travaille dans un Product natif distinct, avec un sens économique inversé par rapport au demandeur. Ses hypothèses et ses calculs ne réécrivent pas la demande reçue. Les accès distinguent consultation, préparation et pricing ; la responsabilité du dossier doit être transférée explicitement avant qu’un autre utilisateur le calcule. [Contrôles bancaires](C:/Users/admin/GitHub/structura/backend/app/services/rfq_bank.py:1).

- **La publication constitue une action commerciale explicite.** Le prix commercial peut différer du prix théorique conservé. La préparation référence un calcul signé, récent selon la politique du desk, portant sur les bons termes. La validation couvre le contenu exact ; une modification du prix ou de la politique impose une nouvelle validation. La seconde validation peut être exigée. [Contrôles de publication](C:/Users/admin/GitHub/structura/backend/app/services/rfq_publication.py:167), [validation et publication](C:/Users/admin/GitHub/structura/backend/app/services/rfq_publication.py:256).

- **La reprise réseau est sérieusement traitée.** Les messages sortants sont persistés avec l’action métier. La réception et son reçu durable sont atomiques. Le dispositif couvre les doublons, les contenus contradictoires, les séquences, la perte d’accusé, les tentatives différées et les travailleurs concurrents. Les messages et reçus bénéficient de protections SQLite. [Transport persistant](C:/Users/admin/GitHub/structura/backend/app/services/rfq_transport.py:378), [gardes d’intégrité](C:/Users/admin/GitHub/structura/backend/app/db/rfq_transport_integrity.py:1).

- **L’authentification du canal et la confidentialité sont cohérentes avec cette architecture.** Les enveloppes sont authentifiées avec une clé propre au canal et liées aux installations attendues. Le client HTTPS conserve la vérification du certificat, refuse les redirections et ignore les proxys hérités de l’environnement. Les projections commerciales excluent les références de calcul privé. [Vérification des enveloppes](C:/Users/admin/GitHub/structura/backend/app/services/rfq_transport.py:95), [client réseau](C:/Users/admin/GitHub/structura/backend/app/services/rfq_transport.py:543).

- **Le traitement et le booking disposent de protections utiles.** Une demande déclarée ne vaut pas confirmation. La confirmation exige une référence, des preuves et une chronologie compatible avec la validité du prix. Elle fige le contenu économique. Le booking peut ensuite être repris sans créer un deuxième Deal ; une reprise portant un contenu différent produit un conflit. Un retrait ou une révision reçu après confirmation conserve l’accord et déclenche une revue. [Confirmation](C:/Users/admin/GitHub/structura/backend/app/services/rfq_execution.py:186), [booking et conflits](C:/Users/admin/GitHub/structura/backend/app/services/rfq_execution.py:279).

**Les anomalies confirmées**

### S-M10-01

**1. P1 — Une réouverture locale peut réactiver une cotation alors que la banque conserve le tour fermé**

J’ai reproduit la séquence suivante sur deux bases indépendantes :

1. Publication et réception d’un prix bancaire.
2. Passage de la RFQ en « sans suite ».
3. Transmission effective de la clôture à la banque.
4. Réouverture de la RFQ côté demandeur.

Résultat : la publication passe de `ROUND_CLOSED` à `ACTIVE` chez le demandeur, tandis que le dossier bancaire reste fermé au travail.

La clôture repose localement sur le statut de la RFQ, sans fermer définitivement l’état du tour. La réouverture efface ce statut terminal ; aucun événement de réouverture ne rétablit l’état distant. Le contrôle qui interdit de rouvrir un tour fermé ne couvre donc pas ce parcours. [Réouverture](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1793), [propagation de clôture](C:/Users/admin/GitHub/structura/backend/app/services/rfq_transport.py:518), [état des publications](C:/Users/admin/GitHub/structura/backend/app/services/rfq_publication.py:110).

**Impact :** les deux parties n’ont plus la même consultation active. Une ancienne réponse peut retrouver une apparence de disponibilité chez le demandeur après une clôture déjà reçue par la banque.

**Recommandation :** rendre la clôture définitive pour le tour concerné. La reprise commerciale doit créer un nouveau tour explicitement lié au précédent, avec de nouvelles réponses. Une réouverture ne doit pas réactiver les prix de l’ancien tour.

### S-M10-02

**2. P1 — Le traitement réseau dépend du nom juridique exact fourni par la banque**

Le résolveur de contrepartie recherche une contrepartie active dont le nom correspond exactement au `counterparty_name` publié. Il n’utilise pas le rapprochement juridique local déjà enregistré dans la relation RFQ. [Résolution juridique](C:/Users/admin/GitHub/structura/backend/app/services/rfq_execution.py:85).

Reproduction : le demandeur connaît sa contrepartie sous « BNP juridique », tandis que la banque publie « BNP Paribas SA — dénomination banque ». L’appairage et la réception du prix fonctionnent. Le résolveur utilisé avant traitement renvoie ensuite une erreur 422 demandant un rapprochement juridique.

**Impact :** un écart de libellé entre deux référentiels locaux suffit à bloquer une relation pourtant configurée. Le problème apparaît tard, au moment du traitement.

**Recommandation :** résoudre la contrepartie à partir du rapprochement local de la relation reconnue. Conserver séparément le nom juridique déclaré par la banque et contrôler sa cohérence avec une identité juridique partagée. Le nom affiché doit rester un attribut descriptif.

### S-M10-03

**3. P2 — Les preuves saisies pour une RFQ restent présentes lors du passage à une autre**

Le panneau de traitement ferme la modale et efface quelques états lors d’un changement de RFQ, mais conserve les formulaires de demande et de confirmation : référence externe, référence d’exécution, heures et textes de preuve. [État du formulaire](C:/Users/admin/GitHub/structura/frontend/src/components/RfqExecutionPanel.vue:20).

J’ai reproduit le passage d’une RFQ A à une RFQ B : les éléments saisis pour A restent présents et le formulaire de confirmation conserve son indicateur « complet ».

**Impact :** l’utilisateur peut reprendre involontairement des références ou des preuves appartenant au mauvais dossier. Les contrôles backend de chronologie et d’unicité restent actifs ; ils ne peuvent pas déterminer à quelle opération se rapporte réellement un texte de preuve.

**Recommandation :** réinitialiser ces champs à chaque changement de RFQ et de demande de traitement. Les brouillons éventuellement conservés doivent être rattachés explicitement à l’identifiant de l’accord concerné.

### S-M10-04

**4. P2 — Une réponse tardive de réaffectation peut remplacer le dossier actuellement affiché**

La réaffectation applique sa réponse au dossier sélectionné sans vérifier que l’utilisateur consulte toujours la même RFQ. [Réaffectation](C:/Users/admin/GitHub/structura/frontend/src/views/RfqInboxView.vue:82), [application de la réponse](C:/Users/admin/GitHub/structura/frontend/src/views/RfqInboxView.vue:62).

Reproduction : lancer une réaffectation sur A, fermer sa modale, ouvrir B, puis recevoir la réponse tardive de A. Le détail affiché revient à A dans la modale ouverte pour B.

**Impact :** le contexte de travail change sous les yeux de l’utilisateur. La réaffectation initiale cible bien A, mais une action ultérieure peut être engagée sur un dossier que l’utilisateur ne pensait plus consulter.

**Recommandation :** associer chaque opération asynchrone à son identifiant de dossier et à un jeton d’ouverture. Une réponse tardive peut actualiser la ligne correspondante dans la liste ; elle ne doit remplacer le détail que si ce dossier est toujours sélectionné.

### S-M10-05

**5. P2 — Une validation reste annoncée comme actuelle après révocation du valideur**

L’indicateur `validation_current` vérifie l’empreinte de la préparation et la version de politique. Il ne recontrôle pas les habilitations du valideur. La publication effectue bien ce contrôle supplémentaire. [Indicateur exposé](C:/Users/admin/GitHub/structura/backend/app/services/rfq_publication.py:370), [contrôle effectif](C:/Users/admin/GitHub/structura/backend/app/services/rfq_publication.py:294).

Après validation puis désactivation de l’habilitation du valideur, j’obtiens :

- préparation toujours annoncée comme validée ;
- dossier toujours ouvert ;
- publication refusée en 409.

**Impact :** le contrôle financier tient, mais l’écran donne une information devenue fausse et propose une publication qui échouera.

**Recommandation :** exposer une éligibilité de publication calculée côté serveur, avec ses motifs de blocage. L’interface doit distinguer une validation historiquement enregistrée d’une validation encore utilisable.

**Les limites fonctionnelles à conserver clairement dans le périmètre**

Ces points sont documentés comme incomplets ; je les distingue des anomalies précédentes.

- **L’exécution reste une confirmation externe consignée localement.** Les messages réseau natifs couvrent demande, lecture, prix, retrait et clôture. Ils ne couvrent pas encore la demande de traitement, l’acceptation et la confirmation bancaire. La preuve dépend donc de l’attestation de l’utilisateur habilité et des références qu’il saisit. [Périmètre du protocole](C:/Users/admin/GitHub/structura/backend/app/services/rfq_transport.py:34), [limites du traitement](C:/Users/admin/GitHub/structura/docs/projects/platform/RFQ_NETWORK_LOT_7_IMPLEMENTATION_2026-10-12.md:51).

- **Le circuit de résolution reste incomplet.** Les contestations peuvent bloquer un booking, mais leur résolution gouvernée reste à construire. L’indicateur « confirmation écrite à suivre » ne dispose pas d’un circuit documentaire complet. Le rapprochement bilatéral des books et les exécutions partielles restent également hors périmètre.

- **L’exploitation entre partenaires réels nécessite une qualification supplémentaire.** La rotation des clés et le changement d’adresse d’un canal existant n’ont pas encore leur parcours administratif dédié. La recette documentée avec des installations fictives ne constitue pas un raccordement à une banque réelle. [Qualification et travaux restants](C:/Users/admin/GitHub/structura/docs/projects/platform/RFQ_NETWORK_LOT_8_ACCEPTANCE_2026-10-13.md:124).

- **Le registre central et la facturation ne sont pas actifs.** La configuration conserve `registry_state=NOT_CONFIGURED` et `billing_enabled=false`. Les preuves locales de transport ne doivent donc pas être présentées comme un registre central opérationnel. [Configuration actuelle](C:/Users/admin/GitHub/structura/backend/app/hybrid/config.py:26).

**Vérifications réalisées**

- **61 tests backend ciblés réussis**, couvrant pricing bancaire, publication, livraison, transport et exécutions.
- **50 tests frontend réussis**, portant sur les stores RFQ/authentification et le prototype réseau.
- Reproductions supplémentaires des cinq anomalies décrites, dont les parcours réseau sur deux bases indépendantes et les états d’interface à partir du code Vue réel.

Les vérifications ont utilisé des bases temporaires, des dépendances isolées et un transport HTTP simulé. Elles ne constituent pas une recette navigateur complète ni une qualification d’une installation bancaire réelle. La suite backend complète n’a pas été lancée.

**Ordre de traitement recommandé**

1. **Sécuriser les deux invariants prioritaires :** clôture définitive d’un tour et résolution juridique par rapprochement local.
2. **Fiabiliser les parcours opérateur :** isolation des preuves par accord, protection contre les réponses tardives et affichage fidèle des validations.
3. **Qualifier le parcours complet entre installations isolées :** publication, clôture, nouveau tour, libellés juridiques différents, révocation de droits, perte d’accusé et conflit après confirmation.
4. **Préparer l’exploitation réelle :** résolution des contestations, suivi des confirmations écrites, rotation des clés et procédure de rapprochement des exécutions.

Le socle technique permet de poursuivre ce travail sans refonte générale. Les corrections prioritaires portent sur la cohérence des états commerciaux et juridiques entre les deux parties.

## M11

**Module 11 — Booking**

Le module protège sérieusement le contrat et le calcul utilisés au booking. Le lien avec le Product, les termes exécutés, le reçu de pricing et la provenance RFQ sont contrôlés côté serveur.

**J’ai néanmoins confirmé six anomalies : quatre P1 et deux P2.** Les plus importantes concernent l’application des limites, la cohérence de la contrepartie après amendement et la reprise d’un booking direct.

Le périmètre couvre les entrées depuis le Pricer, les indicatifs et les RFQ, le journal de notes, la création du Deal, ainsi que les protections et corrections après booking. Aucun code ni aucune donnée métier n’a été modifié.

**Les points solides**

- **Un booking accepté possède un Product canonique.** Le serveur réutilise le dossier source ou crée un Product interne pour un booking direct. Il refuse les contradictions entre Product, RFQ et indicatif, une version contractuelle périmée et un Product déjà exécuté. Des contraintes SQL protègent également le lien Product et l’unicité du Deal par dossier. [Contrôles du dossier](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:1871), [protections SQL](C:/Users/admin/GitHub/structura/backend/app/db/product_migrations.py:1).

- **Le pricing utilisé doit être vérifiable.** Un reçu serveur signé est obligatoire. Le serveur contrôle notamment le script, les quatre dates, la devise, le panier, la maturité et la fair value. Il reconstruit le snapshot de marché depuis les entrées du calcul, puis conserve ces entrées et le résultat dans le Product. [Contrôle du reçu](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:1533), [vérification de signature](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:1895).

- **Le passage RFQ → Deal comporte plusieurs protections indépendantes.** Le serveur vérifie les droits de booking, la sélection, la validité de la réponse, le sens économique, les termes et le contexte commercial. Une réponse réseau exige son accord de traitement confirmé. Le prix, le nominal, les parties et le sens doivent alors correspondre à cet accord. [Contrôles RFQ](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:1693), [accord confirmé](C:/Users/admin/GitHub/structura/backend/app/services/rfq_execution.py:279).

- **Le contrat conservé contient les éléments nécessaires au suivi.** Script, paramètres effectifs, marché de pricing, calendrier résolu et dates sont figés. Les événements sont créés depuis le calendrier contractuel ; les points de grille transmis par le navigateur ne servent pas de calendrier de remplacement. La provenance concurrentielle et le contexte client sont également conservés. [Calendrier et contrôles](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:1973), [snapshot contractuel](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:902).

- **Les limites sont recalculées côté serveur lorsqu’une contrepartie est reconnue.** Le booking ne reprend pas simplement une décision de crédit affichée auparavant. Le contrôle relit la politique et le portefeuille dans la transaction de booking. Le test ciblé confirme qu’une limite bloquante empêche la création du Deal. [Contrôle CCR](C:/Users/admin/GitHub/structura/backend/app/core/ccr/service.py:770).

- **Les modifications directes sont refusées et les amendements sont versionnés.** Le parcours d’amendement conserve demande, décision, motif, version de départ et snapshots avant/après. Il contrôle les bases périmées et les applications concurrentes. Les pointeurs de valorisation et sensibilités courantes sont invalidés après modification du contrat. [Frontière de refus](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:2987), [application versionnée](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:3243).

- **Le journal de notes possède une reprise mieux protégée.** Dans ma vérification isolée, le rejeu d’une même référence retrouve la même exécution et conserve un seul Deal. Une nouvelle opération dépassant la limite de notionnel de la relation est refusée. [Booking des notes](C:/Users/admin/GitHub/structura/backend/app/api/trading.py:173).

**Les anomalies confirmées**

### S-M11-01

**1. P1 — Un libellé de contrepartie non reconnu permet d’éviter le contrôle des limites**

Le booking direct accepte une contrepartie sous forme de texte libre. Le contrôle CCR recherche une correspondance exacte ; lorsqu’il ne trouve rien et qu’aucun netting set n’est demandé, il quitte le contrôle sans bloquer le booking. [Sortie du contrôle CCR](C:/Users/admin/GitHub/structura/backend/app/core/ccr/service.py:770).

Reproduction avec une limite bloquante :

- `BNP Paribas` : booking refusé pour dépassement ;
- `BNP Paribas `, avec un espace final : booking accepté et `counterparty_id` absent.

J’ai également confirmé qu’une contrepartie référencée mais inactive pouvait être bookée directement. L’interface filtre les contreparties actives ; cette éligibilité n’est pas imposée par la frontière serveur. [Liste proposée à l’écran](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:2537), [rattachement du Deal](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:2126).

**Impact :** une variation de libellé suffit à créer une position hors du périmètre de limites attendu. L’exposition peut ensuite rester sans rattachement juridique exploitable.

**Recommandation :** exiger une identité de contrepartie active pour chaque nouveau booking et contrôler son éligibilité côté serveur. Le libellé doit être conservé comme photographie descriptive. Un rapprochement absent doit produire un refus ou une exception explicitement autorisée et auditée.

### S-M11-02

**2. P1 — Un amendement de nominal peut dépasser une limite bloquante**

Le contrôle de crédit intervient lors du booking initial, mais n’est pas rejoué lors de l’application d’un amendement.

Reproduction : avec une limite bloquante de **1,5 M€**, un Deal de **1 M€** est amendé à **2 M€**. La demande devient `APPLIED` et le nouveau nominal est enregistré. [Validation de la valeur](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:990), [application](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:3272).

**Impact :** une limite qui empêcherait une nouvelle opération peut être dépassée par correction d’une position existante.

**Recommandation :** évaluer la position résultant de l’amendement avant son application, dans la même transaction. Les changements de nominal et de contrepartie doivent notamment repasser les contrôles de crédit et de périmètre juridique. La décision doit être conservée avec la nouvelle version contractuelle.

### S-M11-03

**3. P1 — Un amendement de contrepartie conserve l’identifiant de l’ancienne banque**

L’application modifie le champ texte `contrepartie`, mais ne met pas à jour `counterparty_id`. Le Product reprend ensuite cette combinaison incohérente. [Mise à jour du Deal](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:3331), [projection dans le Product](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:3369).

Reproduction d’un passage de BNP Paribas à Société Générale :

- le Deal affiche Société Générale ;
- son identifiant juridique désigne toujours BNP Paribas ;
- le Product porte également le nouveau nom avec l’ancien identifiant ;
- le CCR retrouve le Deal chez BNP et ne le retrouve pas chez Société Générale.

**Impact :** le contrat affiché et l’agrégation du risque désignent deux contreparties différentes.

**Recommandation :** résoudre la nouvelle contrepartie et actualiser atomiquement son identifiant, son libellé figé et les projections du Product. Vérifier aussi la compatibilité des rattachements juridiques et des limites avant application. Les snapshots historiques doivent conserver l’ancienne identité.

### S-M11-04

**4. P1 — Le booking direct sans Product préexistant n’est pas idempotent**

Les protections « un Deal par RFQ » et « un Deal par Product » fonctionnent. Elles ne couvrent pas une commande directe dont le Product est créé pendant le booking.

J’ai transmis deux fois le même contenu, avec le même reçu signé et sans Product préexistant : **deux Deals et deux Products distincts ont été créés**. [Création interne du Product](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:2044), [entrée du booking](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:2396).

**Impact :** après un enregistrement réussi dont la réponse réseau est perdue, une nouvelle tentative peut doubler la position. Le verrou du bouton protège le double clic local, mais ne résout pas cette situation.

**Recommandation :** ajouter une clé de commande persistante au booking direct. Une reprise avec la même clé et le même contenu doit retrouver le Deal ; un contenu différent doit produire un conflit. Une deuxième opération commerciale volontaire reçoit une nouvelle clé.

### S-M11-05

**5. P2 — « Booker un autre deal à partir de ce pricing » conserve le dossier déjà exécuté**

Le réarmement efface les indicateurs locaux du Deal existant, mais conserve `currentProduct`. Le prochain envoi référence donc le Product déjà booké. [Réarmement](C:/Users/admin/GitHub/structura/frontend/src/components/DealTab.vue:607), [construction de la demande](C:/Users/admin/GitHub/structura/frontend/src/components/DealTab.vue:751).

La reproduction confirme ce maintien du Product ; le serveur refuse ensuite avec `PRODUCT_ALREADY_BOOKED`.

**Impact :** l’interface propose un parcours qui ne permet pas de créer la nouvelle opération annoncée.

**Recommandation :** faire de cette action une duplication explicite du dossier, avec filiation vers le Product d’origine et sans reprendre son exécution. Les éventuels liens RFQ et indicatif doivent être traités à cette même frontière.

### S-M11-06

**6. P2 — Une valeur numérique non finie provoque une exception technique**

Le schéma et les premiers contrôles économiques acceptent un nominal transmis sous la forme `"Infinity"`. La sérialisation ultérieure échoue avec une `ValueError`, au lieu d’un refus métier contrôlé. [Schéma](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:83), [contrôles économiques](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:246).

Dans la reproduction, aucun Deal n’a été conservé, mais aucun événement `BOOKING_REJECTED` n’a été enregistré.

**Impact :** l’entrée invalide sort du circuit normal de validation et d’audit et entraîne une erreur technique.

**Recommandation :** refuser les nombres non finis dès la validation des montants et appliquer la même règle aux amendements numériques.

**Les limites et choix de gouvernance**

La seconde signature des amendements est **désactivée par défaut**, conformément au choix documenté pour un poste mono-opérateur. Je ne classe pas ce choix comme une anomalie. Son activation n’ajoute toutefois pas les contrôles économiques manquants décrits ci-dessus. [Politique de signature](C:/Users/admin/GitHub/structura/backend/app/core/workflow.py:13).

Le parcours d’annulation/remplacement reste également incomplet : certains changements de script, de dates ou de marché sont refusés avec une demande de rebooking, sans circuit complet pour remplacer l’opération erronée. Cette limite est explicitement documentée. [Gouvernance des corrections](C:/Users/admin/GitHub/structura/docs/reference/GOUVERNANCE_AMENDEMENTS.md:25).

Enfin, l’absence de limite configurée n’équivaut pas à une autorisation de crédit formalisée. Ce statut devrait être visible au moment de confirmer le booking.

**Vérifications réalisées**

- **75 tests backend ciblés réussis** : booking RFQ, identité contractuelle, refus, provenance, amendements, limite CCR et chaîne pricing → booking → MtM au strike.
- **89 tests frontend réussis** sur les stores Deals et Pricing.
- Reproductions supplémentaires des six anomalies et contrôle du rejeu et de la limite du journal de notes.
- Les reproductions métier ont utilisé des bases temporaires avec clés étrangères et protections Product actives.

Aucun service n’a été démarré. Aucun appel à un fournisseur externe ni aucune recette navigateur complète n’a été réalisé. La suite backend complète n’a pas été lancée.

**Ordre de traitement recommandé**

1. **Fiabiliser l’identité juridique** à l’entrée et lors des amendements.
2. **Rejouer les contrôles de risque sur toute modification d’exposition.**
3. **Généraliser l’idempotence** au booking direct.
4. **Raccorder le réarmement à une vraie duplication**, puis durcir les validations numériques.
5. **Compléter le circuit d’annulation/remplacement** pour disposer d’une sortie opérationnelle aux erreurs contractuelles irréparables en place.

## M12

**Module 12 — Fixings, événements et alertes**

Le module dispose d’un socle sérieux : observations versionnées, provenance conservée, rejeu du payoff depuis les fixings officiels et application transactionnelle des résolutions.

**J’ai confirmé six anomalies, dont deux P1.** Les principales concernent l’officialisation prématurée d’une donnée du jour et le déclassement d’un fixing déjà validé lorsque le fournisseur ne le restitue plus.

L’audit est resté sans modification du code ni des données métier.

**Le fonctionnement actuel à retenir**

Le parcours opérationnel est désormais **automatique avec exceptions utilisateur** : les clôtures Yahoo peuvent devenir officielles et déclencher un rappel ou une échéance. Une actualisation convertit également les anciens dossiers `FOUR_EYES` vers `AUTO_YAHOO`.

Les documents historiques décrivant Yahoo comme exclusivement indicatif et une autorisation Checker systématique ne représentent donc plus le fonctionnement courant. [Politique appliquée à l’actualisation](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:4460).

**Les points solides**

- **Les cours contractuels utilisent un flux distinct des historiques de backtest.** Le chargement demande les clôtures non ajustées et conserve une série indépendante par sous-jacent, avec les splits et les devises disponibles. Cela évite de fabriquer directement un fixing par alignement entre titres. [Flux de référence](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:395).

- **Des contrôles de qualité existent avant l’officialisation.** Valeurs non positives ou non finies, ancienneté excessive, devise incohérente, split et variation quotidienne importante peuvent déclencher une exception. La règle de report utilisée est inscrite dans la preuve archivée. [Contrôles automatiques](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:4528).

- **Les décisions conservent leur provenance.** Les versions portent les valeurs, la source, les références, les preuves hashées et les acteurs. Une décision utilisateur crée une nouvelle version. Les observations déjà consommées par une résolution appliquée sont protégées contre la correction ordinaire. [Décision sur exception](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:4768).

- **La résolution repose sur un rejeu officiel.** Le traitement réutilise le script et les paramètres figés, vérifie les observations nécessaires et conserve le résultat avec son empreinte. Les payoffs nécessitant un chemin continu non prouvé restent bloqués. Le traitement s’arrête au rappel, sans officialiser inutilement les observations suivantes. [Rejeu officiel](C:/Users/admin/GitHub/structura/backend/app/core/lifecycle_controls.py:218), [application automatique](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:5467).

- **Les fenêtres de constatation sont représentées explicitement.** Les relevés sont distingués des constatations et rattachés à leur parent. Les réductions sont calculées par sous-jacent ; l’interface les regroupe sans les compter comme des observations supplémentaires. Les tests ciblés couvrent notamment moyennes, extrema et corrections.

- **Le Product reçoit les faits de cycle de vie.** Les événements, versions de fixing et propositions sont projetés dans une révision du dossier canonique, dans la transaction métier concernée. [Projection du cycle de vie](C:/Users/admin/GitHub/structura/backend/app/services/product_lifecycle.py:1).

- **Les alertes et le traitement quotidien disposent de mécanismes de reprise.** Les alertes sont dédoublonnées par fait logique. Les rappels peuvent alerter de nouveau à l’observation suivante. Le scheduler journalise ses passages et reprend le dernier créneau manqué au démarrage. [Traitement quotidien](C:/Users/admin/GitHub/structura/backend/app/services/lifecycle_alerts.py:67), [journalisation](C:/Users/admin/GitHub/structura/backend/app/services/lifecycle_alerts.py:183).

**Les anomalies confirmées**

### S-M12-01

**1. P1 — Une barre du jour peut devenir officielle avant la clôture de séance**

Le système vérifie qu’une valeur existe à la date attendue, mais ne vérifie pas que la séance correspondante est terminée et que cette valeur est définitive. Le chargement fournisseur transforme les lignes quotidiennes en couples date/prix sans conserver ce contrôle de finalité. [Chargement](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:427), [officialisation](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:5220).

Dans une reproduction avec un fournisseur simulé :

- récupération à **15 h UTC**, avec une séance déclarée ouverte jusqu’à **20 h UTC** ;
- présence d’une barre datée du jour ;
- officialisation des observations ;
- résolution `APPLIED`, avec un payout de **1,20**.

**Impact :** une valeur encore susceptible de varier peut fixer définitivement le remboursement. Le passage quotidien à 23 h ne protège pas les actualisations manuelles ; l’ouverture d’un dossier peut elle-même déclencher une actualisation. [Ouverture du dossier](C:/Users/admin/GitHub/structura/frontend/src/components/EventsTab.vue:810).

**Recommandation :** vérifier la fin de séance, le fuseau, le calendrier et la finalité de publication par marché. Pour un panier, attendre que chaque observation requise soit disponible comme clôture définitive.

### S-M12-02

**2. P1 — Une lacune du fournisseur peut déclasser un fixing déjà officiel**

Les contrôles sur la nouvelle réponse fournisseur interviennent avant la réutilisation de la version officielle existante.

Reproduction :

1. Un fixing est validé et archivé.
2. Le fournisseur ne restitue ensuite plus cette date historique.
3. L’événement passe de `VALIDATED` à `MANUAL_REVIEW_REQUIRED`.

La version du registre reste pourtant `VALIDATED`, avec le même identifiant et les mêmes valeurs. [Ordre des contrôles](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:5228).

**Impact :** une dégradation de disponibilité du flux remet en cause le statut opérationnel d’une observation acquise et peut bloquer le cycle de vie.

**Recommandation :** réutiliser prioritairement le registre officiel. Une observation fournisseur absente doit produire un diagnostic de disponibilité ; une valeur différente doit ouvrir une contestation distincte. Ces deux situations ne doivent pas modifier de la même manière l’état du fixing conservé.

### S-M12-03

**3. P2 — La surveillance des barrières peut utiliser le mauvais observable**

Deux erreurs sont confirmées dans le calcul de proximité :

- Quand un sous-jacent manque, le tableau des performances est raccourci. `S[1]` peut alors recevoir la performance du deuxième titre. Le worst-of peut également être calculé sur un panier incomplet.
- `S_MIN[i]` et `S_MAX[i]` sont ramenés à la performance courante, au lieu de leur minimum ou maximum historique. [Calcul des performances](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:2663), [résolution des observables](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:2702).

Reproduction : un titre a parcouru **100 → 50 → 100**, avec une barrière KI à **60 %**. La surveillance de `S_MIN[1]` affiche une distance de **+40 points**, alors que le minimum historique est **50 %**, soit **−10 points** sous la barrière.

**Impact :** alertes et distances de surveillance peuvent être fausses. Cette anomalie concerne la surveillance indicative ; elle ne constitue pas une preuve de contournement du rejeu officiel.

**Recommandation :** conserver une correspondance stable par identité de sous-jacent, séparer valeurs courantes et extrema, et rendre indisponible un observable de panier lorsque sa couverture est insuffisante.

### S-M12-04

**4. P2 — Un traitement quotidien en erreur peut être journalisé comme réussi**

Les erreurs par Deal sont collectées, mais le passage global reçoit néanmoins `SUCCESS`. Ce statut empêche ensuite la reprise du même créneau. [Résultat du scheduler](C:/Users/admin/GitHub/structura/backend/app/services/lifecycle_alerts.py:220).

Avec une indisponibilité fournisseur simulée, j’obtiens :

- zéro Deal actualisé ;
- une erreur et une alerte technique ;
- un journal `SUCCESS` ;
- une nouvelle tentative sur ce créneau renvoyant `SKIPPED`.

L’interface affiche également un message commençant par `✓`, sans restituer les erreurs du bilan. [Restitution du refresh](C:/Users/admin/GitHub/structura/frontend/src/views/BookingView.vue:1567).

**Impact :** la supervision peut annoncer un succès alors que des dossiers restent sans traitement.

**Recommandation :** distinguer réussite, réussite partielle et échec. Afficher les dossiers concernés et permettre une reprise ciblée des échecs sans retraiter les opérations déjà terminées.

### S-M12-05

**5. P2 — Une décision de fixing peut être enregistrée malgré une réponse d’échec**

La décision sur exception est commitée avant le rejeu et l’application éventuelle de la résolution. [Premier commit](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:5124), [traitement suivant](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:5132).

J’ai injecté un incident après ce premier commit :

- l’appel échoue ;
- le fixing reste enregistré comme officiel ;
- la répétition de la commande est refusée en 409 pour statut et version incompatibles.

**Impact :** l’utilisateur reçoit une erreur alors que sa décision est déjà acquise, et sa nouvelle tentative ne constitue pas une reprise utilisable.

**Recommandation :** retourner explicitement « fixing enregistré, résolution en échec », avec la version créée et une possibilité de relancer le rejeu. La commande de décision doit aussi pouvoir reconnaître sa propre répétition.

### S-M12-06

**6. P2 — Une alerte disparaît de l’écran même si son acquittement échoue**

Les actions « marquer lu » et « tout marquer lu » ne vérifient pas le succès HTTP avant de retirer les alertes de l’affichage. [Acquittement](C:/Users/admin/GitHub/structura/frontend/src/views/BookingView.vue:1557).

Une réponse 500 simulée retire bien l’alerte de la liste locale.

**Impact :** l’écran annonce implicitement un acquittement qui n’a pas été enregistré.

**Recommandation :** vérifier la réponse avant de modifier la liste et conserver l’alerte visible en cas d’échec. Le statut de lecture doit rester distinct du statut de résolution de l’incident métier.

**Les limites métier à rendre explicites**

**Le règlement est aujourd’hui principalement calendaire.** Le traitement fait sortir un Deal de `en_reglement` lorsque la date prévue est atteinte et écrit `DEAL_SETTLED`. J’ai confirmé cette transition sans preuve d’encaissement. [Transition de règlement](C:/Users/admin/GitHub/structura/backend/app/services/lifecycle_alerts.py:89).

Ce comportement ne prouve pas que le cash a été reçu. Pour une exploitation institutionnelle, il faut distinguer montant dû, date prévue, paiement confirmé et retard ou impayé.

**Les règles de report sont matérielles.** Le dernier cours antérieur peut être retenu jusqu’à quatre jours calendaires, et certains relevés manquants de fenêtres peuvent être reportés avec avertissement. Le report est un choix déjà assumé dans les tests du projet ; l’enjeu est de conserver sa visibilité et sa justification, particulièrement pour les minima et maxima susceptibles de changer une décision.

**La doctrine documentaire doit être actualisée.** Il faut une référence unique décrivant la politique automatique, les exceptions utilisateur, les règles de report, les contrôles de séance et leurs versions. Les anciennes garanties de séparation Maker/Checker ne doivent plus être revendiquées pour le parcours courant.

Enfin, les corrections après consommation d’un fixing restent dépendantes du circuit d’annulation/remplacement encore incomplet.

**Vérifications réalisées**

- **94 tests backend ciblés réussis** : fixings, exceptions, rejeu, résolutions, fenêtres, agrégats, barrières et scheduler.
- **10 tests frontend réussis** : restitution des événements et store Deals.
- Reproductions complémentaires des six anomalies, avec données fournisseur et incidents simulés.
- Vérification séparée de la transition calendaire de règlement.

Les reproductions métier ont utilisé des bases temporaires avec intégrité référentielle. Aucun fournisseur réel n’a été appelé, aucun service n’a été démarré et aucune suite backend complète n’a été lancée. Les contrôles frontend complémentaires portent sur le code des fonctions, sans recette navigateur complète.

**Ordre de traitement recommandé**

1. **Sécuriser la finalité des clôtures et la réutilisation des fixings officiels.**
2. **Corriger les observables de surveillance**, notamment paniers incomplets et extrema individuels.
3. **Fiabiliser les reprises et la supervision**, avec des résultats partiels explicites.
4. **Corriger les acquittements d’alertes** et distinguer lecture, prise en charge et résolution.
5. **Formaliser le suivi des paiements et la politique de fixing versionnée.**

## M13

**Le module 13 possède une bonne architecture de valorisation résiduelle, mais deux anomalies peuvent fausser directement le prix : la reprise des fixings officiels et l’horizon simulé juste avant maturité.** J’ai également confirmé cinq anomalies concernant les valorisations historiques, leur restauration et leur reproductibilité.

L’audit a été réalisé sans modifier le code ni les données métier, avec les skills de cycle de vie et de pricing quantitatif.

**Points solides**

- **Le Product canonique encadre la valorisation.** Le calcul exige un produit lié, contrôle sa version contractuelle et utilise son calendrier figé. Il refuse les dossiers incomplets plutôt que de reconstruire silencieusement leurs termes. [Source](C:/Users/admin/GitHub/structura/backend/app/core/deal_valuation.py:130)
- **La reprise du payoff est substantielle.** Le résiduel transporte la mémoire des coupons, l’index des observations, les accumulations, les extrema et les états de fixing. Il valorise bien la vie restante d’un contrat, avec son passé. [Source](C:/Users/admin/GitHub/structura/backend/app/core/inlife_valuation.py:333)
- **Le régime pré-strike est traité explicitement.** Le fixing initial futur est simulé ; aucune mémoire réalisée n’est artificiellement créée avant le départ du produit.
- **Les créances détachées sont distinguées de la jambe optionnelle.** Les flux constatés mais dont la date de paiement reste future sont ajoutés en valeur actualisée. Une créance terminale connue bénéficie également d’un calcul déterministe avec taux et funding. [Sources](C:/Users/admin/GitHub/structura/backend/app/core/deal_valuation.py:151), [traitement des flux](C:/Users/admin/GitHub/structura/backend/app/core/deal_valuation.py:478)
- **Les hypothèses du calcul sont visibles.** Le résultat expose modèle, volatilités, dividendes, corrélations, funding, seed et provenance disponible. Le passage au GBM après recalibration réalisée est explicite.
- **L’historique constitue une vraie base de preuve.** Chaque calcul explicite conserve un run distinct, son contexte, sa version contractuelle et ses empreintes. Les accès sont contrôlés, et la restauration quotidienne gère les dates locales, les réponses tardives et le changement de journée. [Sources](C:/Users/admin/GitHub/structura/backend/app/core/valuation_runs.py:98), [restauration](C:/Users/admin/GitHub/structura/frontend/src/composables/useBookingMtm.js:94)

**Anomalies confirmées**

### S-M13-01

**1. P1 — Le passé du MtM peut contredire les fixings officiels**

Le calcul reprend le fixing initial enregistré, mais reconstruit ensuite les coupons et la mémoire depuis l’historique de cours chargé. Les autres fixings officiels validés ne gouvernent donc pas cette reconstruction.

Reproduction sur un produit avec mémoire :

- fixing initial officiel : **100** ;
- fixing officiel du coupon : **90**, au-dessus de la barrière de **80** ;
- historique fourni au MtM à cette observation : **40**.

Le rejeu officiel reconnaît un coupon détaché de **10 %**. Le MtM ne reconnaît aucun coupon réalisé, conserve **10 % en mémoire** et valorise le remboursement futur à **110 % au lieu de 100 %**, dans ce cas à taux nul.

Le run conserve pourtant les références du fixing officiel du coupon, ce qui peut laisser croire que celui-ci a servi au calcul.

**Recommandation :** imposer les observations officielles validées aux dates contractuelles pour reconstruire les coupons, la mémoire et les décisions déjà acquises. Utiliser l’historique pour les spots courants et le chemin intermédiaire, avec une qualification indicative explicite lorsque nécessaire. Les références archivées doivent identifier les données effectivement consommées.

[Lecture du fixing initial](C:/Users/admin/GitHub/structura/backend/app/core/deal_valuation.py:251), [reconstruction du passé](C:/Users/admin/GitHub/structura/backend/app/core/inlife_valuation.py:425), [archivage des références](C:/Users/admin/GitHub/structura/backend/app/core/valuation_runs.py:85).

### S-M13-02

**2. P1 — À moins d’une semaine de maturité, le résiduel simule trop longtemps**

La durée restante est définie avec un plancher de `1 / 52` année. Un produit à **un jour de maturité** est donc encore simulé sur environ **7,02 jours**.

Sur un call simple à la monnaie, avec volatilité de 50 %, taux nul et mêmes paramètres numériques :

| Horizon | Valeur en % du nominal |
|---|---:|
| Horizon actuellement transmis au moteur | 2,7499 % |
| Horizon réel d’un jour | 1,0378 % |
| Écart | **1,7121 point** |

Cela représente environ **17 121 € par million de nominal** sur cet exemple. La date de paiement correcte ne corrige pas cette dispersion supplémentaire du sous-jacent.

**Recommandation :** transmettre la durée contractuelle exacte. Le moteur sait déjà utiliser au moins un pas de simulation sans imposer une semaine entière. Couvrir spécifiquement les derniers jours avant échéance, notamment pour les payoffs digitaux et les barrières.

[Plancher de durée](C:/Users/admin/GitHub/structura/backend/app/core/deal_valuation.py:244), [construction du pas moteur](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:2221).

### S-M13-03

**3. P2 — Une créance historique devient impossible à recalculer après le solde du deal**

La branche de valorisation des créances certaines dépend du **statut courant** `en_reglement`.

Dans le cas testé :

- observation terminale le **9 octobre** ;
- règlement prévu le **14 octobre** ;
- valorisation demandée au **10 octobre**.

Avec le statut `en_reglement`, la créance est correctement actualisée. Avec le statut courant `échu`, la même demande historique renvoie **422 — « Terminé le 2026-10-09 »**.

La valeur sauvegardée reste consultable ; c’est le recalcul de cette période passée qui devient inaccessible.

**Recommandation :** déterminer l’état économique à la date demandée : option vivante, créance certaine entre constatation et règlement, puis exposition soldée. Cette reconstruction doit également rendre explicite la version contractuelle utilisée.

[Branche dépendante du statut courant](C:/Users/admin/GitHub/structura/backend/app/core/deal_valuation.py:151), [exclusion après événement terminal](C:/Users/admin/GitHub/structura/backend/app/core/risk_lifecycle.py:38).

### S-M13-04

**4. P2 — Un funding personnalisé passe le filtre de restauration du booking standard**

Les filtres serveur et navigateur vérifient les surcharges de taux, de sous-jacents et la fenêtre de calibration, mais ignorent les surcharges de funding.

J’ai exécuté deux véritables calculs sur le même produit :

| Calcul | MtM |
|---|---:|
| Paramètres ordinaires du booking | 116,5995 % |
| Funding personnalisé de 10 % | 105,9684 % |

La recherche du dernier MtM compatible avec le mode booking sélectionne le second run. Il peut donc être restauré dans une sélection qui n’a pas demandé cette surcharge.

Le funding reste présent dans le détail du résultat ; le défaut concerne l’admissibilité du run à la restauration standard.

**Recommandation :** comparer une requête normalisée complète, incluant courbe et spread de funding. Une surcharge doit correspondre au contexte demandé avant toute restauration automatique.

[Filtre serveur](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:7614), [filtre navigateur](C:/Users/admin/GitHub/structura/frontend/src/composables/useBookingMtm.js:125).

### S-M13-05

**5. P2 — Le rejeu d’un run ne réutilise pas entièrement son calendrier figé**

Le MtM courant restaure le calendrier contractuel sauvegardé. Le rejeu du run recompilé résout en revanche les conventions calendaires à nouveau.

J’ai simulé l’ajout d’un jour fermé sur une date de paiement :

- MtM original : **1,165995** ;
- rejeu avant changement : **1,165995** ;
- rejeu après changement : **1,165991** ;
- nouveau MtM utilisant le calendrier contractuel figé : **1,165995**.

L’écart est faible dans cet exemple, mais il démontre une dépendance du rejeu aux calendriers disponibles au moment de sa réexécution.

**Recommandation :** archiver et restaurer les dates résolues utilisées par le calcul : observations, paiements et relevés des fenêtres. Compléter l’identité du moteur par les dépendances nécessaires à leur reproduction.

[Calendrier figé du MtM](C:/Users/admin/GitHub/structura/backend/app/core/inlife_valuation.py:358), [reconstruction du rejeu](C:/Users/admin/GitHub/structura/backend/app/core/compute/pricers/var_scenario.py:41).

### S-M13-06

**6. P2 — Pour une créance certaine, le « rejeu identique » ne vérifie pas l’actualisation**

Dans ce régime, le contexte archivé se réduit à un indicateur de créance et au **prix déjà calculé**. Le rejeu retourne directement ce prix, puis le compare au résultat enregistré.

Le résultat `identical: true` est donc obtenu sans recalculer la valeur depuis le montant, les dates, les taux et le funding.

**Recommandation :** conserver les entrées déterministes nécessaires et refaire l’actualisation lors du rejeu. La restitution d’un montant sauvegardé doit être distinguée d’une reproduction numérique vérifiée.

[Contexte archivé](C:/Users/admin/GitHub/structura/backend/app/core/valuation_runs.py:48), [retour direct du prix](C:/Users/admin/GitHub/structura/backend/app/core/compute/pricers/var_scenario.py:80).

### S-M13-07

**7. P2 — L’historique peut étiqueter un calcul booking comme « Marché actualisé »**

Un appel MtM sans corps de requête utilise correctement le mode booking par défaut. Il archive cependant une requête vide.

L’écran d’historique considère toute requête ne contenant pas explicitement `recalibrate: 'none'` comme un calcul de marché actualisé. Le même run possède donc une source effective `booking` et une étiquette contraire dans l’historique.

**Recommandation :** sauvegarder systématiquement les paramètres effectifs normalisés et construire les libellés depuis les hypothèses réellement utilisées. Prévoir un traitement explicite des anciens runs incomplets.

[Archivage de la requête](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:6915), [qualification dans l’historique](C:/Users/admin/GitHub/structura/frontend/src/views/DealValuationsView.vue:264).

**Recommandations d’ensemble**

Je traiterais d’abord **la fidélité au passé officiel et l’horizon exact**, car ces deux sujets peuvent modifier matériellement le prix. Ensuite viendraient la reconstruction historique après règlement et les filtres de restauration, puis le renforcement du rejeu et des libellés.

Trois distinctions méritent également d’être formalisées dans le workflow :

- **Valeur archivée** et **recalcul à une date passée** : le second utilise aujourd’hui les termes Product courants et les historiques disponibles ; il ne garantit pas une reconstruction de ce qui était connu à l’époque.
- **Marché actualisé** : volatilités, corrélations et dividendes peuvent être actualisés, tandis que taux et funding restent ceux du booking en l’absence de surcharge. Ce comportement est annoncé dans l’interface.
- **Mouvement de MtM** et **P&L total** : les coupons détachés doivent rester identifiables séparément.

La documentation du MtM quotidien doit enfin être réalignée : elle décrit encore un défaut « Marché actuel », alors que le code propose désormais le mode booking.

**Vérifications effectuées**

**77 tests backend et 24 tests frontend ciblés ont réussi**, couvrant notamment le pré-strike, la reprise d’état, les paiements, le contexte numérique, les archives et la restauration quotidienne. Les anomalies ci-dessus ont été examinées avec des reproductions complémentaires isolées.

Aucun service n’a été démarré, aucun fournisseur réel appelé et aucune donnée métier modifiée. Cette validation ne comprend pas de recette navigateur sur un portefeuille réel.

## M14

**Le module dispose d’un bon socle pour comparer des valorisations archivées. Le principal risque concerne le parcours P&L encore accessible depuis Booking : son traitement des coupons peut produire une performance fictive.**

Deux implémentations coexistent : **Valo Explain**, fondé sur les calculs sauvegardés, et **l’explication entre deux dates**, qui recalcule les valorisations et alimente aussi l’agrégation portefeuille. J’ai confirmé **cinq anomalies**, dont une P1.

Aucun code ni donnée métier n’a été modifié.

**Points solides**

- **La comparabilité est contrôlée avant attribution.** Versions contractuelles, termes, univers, modèle, graine, nombre de trajectoires et conventions numériques doivent être compatibles. Les deux prix archivés doivent également être reproduits à une tolérance absolue de `1e-10`. Sinon, un écart numérique conduit à désactiver l’attribution. [Source](C:/Users/admin/GitHub/structura/backend/app/core/valuation_notes.py:95)
- **La décomposition couvre les principaux facteurs.** Elle distingue temps et état réalisé, spots, dividendes, diffusion et change, corrélations, taux, financement et créances à recevoir. Le funding conserve ainsi son rôle distinct de celui des taux.
- **Les contrôles économiques supplémentaires sont concluants sur le parcours archivé.** Un changement de dividende est correctement attribué aux dividendes. Le passage d’un coupon futur à une créance certaine est identifié séparément, avec un résidu nul dans le cas testé.
- **La méthode est annoncée.** L’ordre des réévaluations est documenté, son influence sur les interactions est reconnue et le résidu reste non attribué. L’interface précise que la variation de MtM ne constitue pas un P&L total.
- **Les preuves et le commentaire éditorial sont séparés.** Les prix et hypothèses archivés ne sont pas éditables. Les brouillons disposent d’un contrôle de révision, d’une sauvegarde sérialisée et d’une protection contre les écrasements entre fenêtres. [Source](C:/Users/admin/GitHub/structura/backend/app/api/valuation_notes.py:181)
- **Les versions PDF figées sont réellement conservées.** Leur téléchargement restitue les octets sauvegardés, même après modification du brouillon. Les droits sur la note et sur le deal sont revérifiés. [Source](C:/Users/admin/GitHub/structura/backend/app/api/valuation_notes.py:197)
- **L’assistance IA reste facultative et encadrée.** Sauvegarde préalable, contexte automatique limité, proposition à accepter explicitement et rejet des réponses devenues obsolètes. Aucun appel IA réel n’a été nécessaire pour cet audit.

### S-M14-01

**1. P1 — Le P&L du parcours Booking confond constatation et paiement des coupons**

L’ancien calcul sélectionne les flux selon leur **date de constatation**, alors que les MtM incluent déjà les coupons constatés mais restant à recevoir.

J’ai reproduit le problème avec un coupon certain de **10 %**, constaté le **15 juillet**, payable le **22 juillet**, sur un marché figé à taux nul :

| Période | Variation du MtM | P&L calculé | P&L attendu |
|---|---:|---:|---:|
| 14 → 16 juillet | 0 point | **+10 points** | 0 |
| 21 → 23 juillet | −10 points | **−10 points** | 0 |

Dans le premier cas, le coupon devient une créance incluse dans le MtM, puis est ajouté une seconde fois au P&L. Dans le second, son paiement fait disparaître la créance du MtM, mais le cash correspondant n’est pas ajouté.

**Cela représente 100 000 € d’erreur pour un million de nominal**, avant application du sens de la position.

La cascade intermédiaire omet également cette créance : le premier scénario affiche **−10 points en effet temps et +10 points en résidu**, présenté comme « effets croisés ». Ce résidu provient ici d’un flux oublié dans les réévaluations.

Le même cœur de calcul alimente le P&L portefeuille : le défaut dépasse donc la fiche individuelle. [Sélection des flux](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:7292), [agrégation portefeuille](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:553).

**Recommandation :** construire le P&L avec les paiements appartenant à la période, selon la convention de règlement retenue, et tenir compte des créances déjà incluses aux deux dates. Réutiliser le traitement explicite des créances du moteur d’attribution archivé.

### S-M14-02

**2. P2 — Un changement de dividende peut être présenté comme un effet véga**

Dans l’ancien parcours, l’étape « Effet volatilité » remplace tout le bloc des paramètres des sous-jacents, notamment les dividendes.

Reproduction :

- volatilité inchangée à **20 %** ;
- dividende passant de **0 % à 10 %** ;
- contribution affichée : **−11,73 points en “Effet volatilité”**, commentée comme du véga.

Le prix d’arrivée reflète bien le nouveau dividende, mais l’explication causale est incorrecte.

Sur les mêmes contextes archivés, Valo Explain attribue correctement **−11,7334 points aux dividendes**, avec une contribution « Diffusion et change » nulle et un résidu nul.

**Recommandation :** faire converger les deux parcours vers une attribution commune distinguant dividendes, paramètres de diffusion et éventuel changement de modèle. Un changement de modèle doit rester identifiable dans la comparaison.

[Ancienne étape volatilité](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:7266), [séparation dans Valo Explain](C:/Users/admin/GitHub/structura/backend/app/core/valuation_notes.py:164).

### S-M14-03

**3. P2 — Le PDF d’explication Booking peut différer du résultat affiché**

Le bouton d’export relance les calculs et les chargements de marché. Il utilise également les sélecteurs courants, qui peuvent avoir changé depuis l’explication affichée.

Avec une révision simulée des cours, à dates et paramètres demandés identiques :

- MtM d’arrivée affiché : **99,9710 %** ;
- MtM repris dans le PDF : **119,9651 %**.

Ces endpoints ne conservent aucun run permettant de rattacher le document au résultat initial. Le bouton annonce pourtant les mêmes chiffres que l’écran.

**Recommandation :** produire l’export depuis une preuve sauvegardée de la comparaison affichée. Tout changement de dates ou de base doit invalider le résultat précédent avant export.

Les **versions figées du nouveau Valo Explain** bénéficient déjà du mécanisme de conservation nécessaire.

[Recalcul lors de l’export](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:7386), [paramètres utilisés par le bouton](C:/Users/admin/GitHub/structura/frontend/src/views/BookingView.vue:1775).

### S-M14-04

**4. P2 — Une exception de rejeu bloque toute la note au lieu de conserver l’écart observé**

Le nouveau module prévoit un repli lorsque les prix recalculés diffèrent des prix archivés : il conserve l’écart observé et désactive l’attribution.

Ce repli ne couvre pas les exceptions levées pendant la reproduction. Une erreur peut survenir dès le calcul des sensibilités, avant la comparaison.

Avec une erreur de reconstruction injectée sur deux runs valides :

- réponse **422** ;
- aucune note créée ;
- impossibilité de produire le document limité aux prix archivés, pourtant exploitables.

**Recommandation :** séparer la disponibilité des prix enregistrés de celle du rejeu, des sensibilités et de l’attribution. Si la reconstruction échoue, conserver une comparaison « écart observé uniquement », avec la raison et les éléments techniques omis.

[Recalcul des sensibilités](C:/Users/admin/GitHub/structura/backend/app/core/valuation_notes.py:71), [reproduction des références](C:/Users/admin/GitHub/structura/backend/app/core/valuation_notes.py:130), [traitement API](C:/Users/admin/GitHub/structura/backend/app/api/valuation_notes.py:108).

### S-M14-05

**5. P2 — Certaines bases de calcul sont mal qualifiées dans Valo Explain**

L’interface traite toute source renseignée différente de `booking` comme du « Marché actualisé ».

Un véritable calcul avec **volatilité manuelle de 30 %**, sans recalibration réalisée, produit la source `booking+overrides`. Il est néanmoins étiqueté **« Marché actualisé »**. Une créance certaine, source `known_settlement`, reçoit également ce libellé.

**Recommandation :** distinguer au minimum paramètres booking, paramètres surchargés manuellement, marché recalibré et créance certaine. Conserver ces qualifications dans le sélecteur, les preuves affichées et les documents.

[Qualification actuelle](C:/Users/admin/GitHub/structura/frontend/src/views/ValoExplainView.vue:148).

**Recommandations d’ensemble**

Je commencerais par **corriger l’identité de P&L autour des dates de paiement**, puis par faire converger les parcours Booking et portefeuille vers les mécanismes d’attribution et d’archivage déjà présents dans Valo Explain. Cela éviterait de maintenir deux définitions concurrentes des effets et des flux.

Il faut également expliciter trois limites métier :

- **L’attribution archivée explique une variation de MtM.** Le P&L total nécessite les paiements de la période et, au niveau de la position, le sens achat/vente ainsi que les conventions de conversion.
- **Les contributions dépendent de l’ordre déclaré.** Une somme réconciliée constitue un contrôle arithmétique ; elle ne suffit pas à valider l’interprétation économique de chaque ligne.
- **L’ancien choix “booking” ne pilote que la seconde date.** À la première date, le code impose une calibration réalisée sauf si elle correspond à la date de valeur. Les deux bases devraient être affichées explicitement. [Source](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:7227)

Les réserves du module 13 restent aussi applicables : une attribution reproductible peut expliquer des valorisations affectées par une mauvaise reprise des fixings ou un horizon résiduel incorrect. Leur correction conditionne la fiabilité économique de l’ensemble.

**Vérifications effectuées**

**43 tests backend et 20 tests frontend ciblés ont réussi**, couvrant les comparaisons, les incompatibilités, les révisions, les PDF, l’agrégation portefeuille et les protections de l’assistance IA. Les reproductions complémentaires ci-dessus ont utilisé des bases temporaires et des données synthétiques.

Aucun service n’a été démarré et aucun fournisseur de marché ou d’IA réel n’a été appelé. La validation ne comprend pas de recette visuelle dans le navigateur.

## M15

**Module 15 — Risques portefeuille et CCR**

Le module possède des contrôles sérieux sur les signes, les dates, le netting juridique et la conservation des calculs. **J’ai néanmoins confirmé sept anomalies, dont quatre P1 : couverture VaR surestimée, sensibilités manquantes présentées à zéro, mélange Production/UAT et CVA nulle sur certaines créances courtes.**

Le périmètre couvre les portefeuilles, les sensibilités agrégées, les chocs, la VaR/ES, la concentration par contrepartie et le CCR : préparation des valorisations, exposition future, collatéral, CVA et limites.

L’audit porte sur l’état local actuel. Aucun code ni aucune donnée métier n’a été modifié.

**Points solides**

- **Les signes économiques sont correctement centralisés.** Le sens bancaire du Deal est traduit en position longue ou courte, puis appliqué aux sensibilités, aux chocs et aux scénarios VaR. Les tests couvrent également la compensation économique de positions opposées. [Source](C:/Users/admin/GitHub/structura/backend/app/db/models.py:1103)
- **Les portefeuilles sont des vues sans duplication économique.** L’appartenance multiple est dédupliquée par Deal ; supprimer un portefeuille conserve les positions et leur historique.
- **L’agrégation des Greeks respecte la date sélectionnée et la version contractuelle.** Elle distingue les calculs absents, les positions hors de leur vie économique et les devises non convertibles. Les périmètres de véga incompatibles sont présentés séparément. [Source](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:261)
- **La VaR utilise des réévaluations du résiduel.** Les méthodes historique et paramétrique restent séparées. Le calcul d’ES pondère correctement la fraction de scénario située à la frontière de la queue.
- **Les échecs de jobs VaR sont traités prudemment.** Un portefeuille incomplet ne reçoit pas une VaR globale. Un résultat distinct peut être publié sur un univers réduit, identique dans tous les scénarios. [Source](C:/Users/admin/GitHub/structura/backend/app/api/var.py:200)
- **Le CCR impose une compensation juridiquement définie.** Il exige un netting set éligible, un accord actif et des autorisations explicites. Les scénarios sont communs aux facteurs partagés ; les incohérences de marché et les corrélations jointes invalides sont refusées.
- **Les capacités CCR absentes restent identifiables.** Les données de crédit inconnues ne deviennent pas automatiquement zéro. La CVA marchande exige une PD qualifiée risque neutre ; l’EAD SA-CCR reste explicitement indisponible.
- **La préparation CCR conserve une preuve détaillée.** Entrées, paramètres, historiques et empreintes sont sauvegardés. Le cache tient compte des termes et des événements et privilégie les données disponibles avant une récupération externe autorisée.

### S-M15-01

**1. P1 — La VaR peut annoncer 100 % de couverture avec un facteur totalement absent**

Lorsqu’un historique manque pour un sous-jacent, les générateurs de scénarios travaillent avec les tickers disponibles. L’application du scénario attribue ensuite un **choc nul** aux tickers absents.

Reproduction complète en base temporaire :

- deux Deals portant respectivement sur `TK1` et `TK2` ;
- historiques de scénario disponibles uniquement pour `TK1` ;
- **30 jobs** calculés ;
- tous les scénarios de `TK2` restent sans choc et produisent un P&L nul ;
- publication : **`complete`, couverture 100 %, aucune exclusion**.

Le contrôle de complétude vérifie les jobs, mais pas la couverture des facteurs qui les alimentent.

**Recommandation :** vérifier la couverture de chaque facteur requis avant de générer les scénarios. Un historique absent doit conduire à une exclusion explicitement qualifiée ou à un refus. Réserver les chocs nuls aux facteurs volontairement inchangés.

[Filtrage des tickers](C:/Users/admin/GitHub/structura/backend/app/core/var_engine.py:184), [choc nul par défaut](C:/Users/admin/GitHub/structura/backend/app/core/var_engine.py:168).

### S-M15-02

**2. P1 — Un calcul partiel peut faire disparaître gamma et rho sans signalement adapté**

Le dernier calcul de Greeks d’un Deal peut ne contenir que les sensibilités demandées. L’agrégation initialise pourtant plusieurs totaux à zéro et considère le Deal comme couvert dès qu’un calcul compatible existe.

Reproduction :

1. calcul complet d’un call ;
2. nouveau calcul limité au delta ;
3. lecture du risque global.

Le rho, auparavant équivalent à **5 023 € pour +100 bp**, apparaît alors à **0 €**. Le gamma devient également nul dans l’agrégat. Le Deal figure parmi les positions incluses, sans être signalé « sans Greeks ».

La couverture partielle du theta est déjà signalée ; ce contrôle n’est pas généralisé aux autres sensibilités.

**Recommandation :** publier une disponibilité et une couverture par sensibilité. Une mesure absente doit rester inconnue. Un calcul partiel ne doit pas remplacer implicitement la référence complète du portefeuille.

[Choix du snapshot](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:261), [initialisation des agrégats](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:338).

### S-M15-03

**3. P1 — Les agrégats historiques mélangent Production et Recette UAT**

Le CCR possède une séparation explicite Production/UAT. Les chemins historiques de risque global, chocs et VaR ne proposent pas la même frontière et ne filtrent pas `uat_batch_id`.

Avec un Deal de production de **1 M€** et un Deal UAT de **1 M€**, le risque global retourne :

- **2 M€ de nominal** ;
- les deux positions incluses ;
- la somme de leurs sensibilités.

Une campagne de recette peut donc modifier les chiffres présentés dans le même écran que le portefeuille réel.

**Recommandation :** généraliser un périmètre explicite, avec Production par défaut et Recette UAT distincte. Le même choix doit gouverner les positions, les agrégats, les lancements de calcul et leur historique.

[Sélection globale des positions](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:87), [lancement VaR](C:/Users/admin/GitHub/structura/backend/app/api/var.py:421).

### S-M15-04

**4. P1 — La grille CCR peut produire une CVA nulle avant un paiement proche**

Les dates de projection sont ramenées sur une grille hebdomadaire. La CVA utilise ensuite l’exposition à droite de chaque intervalle. Lorsqu’un paiement précède le premier point futur, l’exposition y est déjà nulle.

Cas déterministe testé :

| Hypothèse ou résultat | Valeur |
|---|---:|
| Créance certaine payable dans deux jours | 1 M€ |
| Recouvrement | 40 % |
| PD cumulée linéaire à un an, hypothétique | 20 % |
| Exposition courante calculée | 1 M€ |
| CVA calculée | **0 €** |
| CVA de référence sur les deux jours, à taux nul | **657,08 €** |

Une limite CVA de **100 €** ressort à **« OK »** et la décision calculée autorise le booking.

**Recommandation :** conserver les dates exactes de règlement et intégrer l’exposition avant les sauts de paiement. Ajouter la date de paiement seule ne suffit pas si l’intégration ne lit que l’exposition après règlement. Ce cas dispose d’une référence déterministe simple.

[Construction de la grille](C:/Users/admin/GitHub/structura/backend/app/core/ccr/service.py:496), [intégration CVA](C:/Users/admin/GitHub/structura/backend/app/core/ccr/exposure.py:110).

### S-M15-05

**5. P2 — Le moniteur CCR peut conserver un résultat comme actuel après changement de fixing**

Le moniteur vérifie la date, la configuration et l’identité/version des positions. Il ne vérifie pas l’ensemble des événements et fixings ayant servi au calcul.

Après une nouvelle validation officielle du fixing initial :

- exposition sauvegardée : **999 151 €** ;
- exposition recalculée avec le nouveau fixing : **832 626 €** ;
- moniteur : **`stale = false`**.

L’empreinte du cache de préparation change correctement dans ce scénario. Le moniteur n’utilise pas cette même frontière de validité.

**Recommandation :** rattacher son statut de fraîcheur aux preuves contractuelles et aux versions de fixings consommées. Réutiliser les critères du cache pour éviter deux définitions différentes d’un calcul encore valable.

[Contrôle du moniteur](C:/Users/admin/GitHub/structura/backend/app/api/ccr.py:158), [empreinte de préparation](C:/Users/admin/GitHub/structura/backend/app/core/ccr/cache.py:13).

### S-M15-06

**6. P2 — Un renommage de contrepartie fait disparaître une alerte de concentration**

L’onglet historique de concentration regroupe les positions par libellé et retrouve les limites par le nom courant du référentiel.

Reproduction sur une position conservant le bon `counterparty_id` :

- avant renommage : nominal **1 M€**, limite **500 000 €**, dépassement signalé ;
- après renommage : même position, limite affichée absente et dépassement à `false`.

Ce constat concerne le contrôle de concentration historique ; le CCR possède ses propres limites et rattachements.

**Recommandation :** agréger et rechercher les limites par identifiant juridique stable. Conserver le libellé historique comme information descriptive.

[Regroupement et recherche des limites](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:700).

### S-M15-07

**7. P2 — Le choc de taux ne réactualise pas les coupons détachés restant à recevoir**

Pour un produit encore actif, le choc réévalue la jambe résiduelle, puis ajoute la valeur actuelle initiale des coupons détachés. Cette créance reste donc inchangée sous choc de taux.

Sur un coupon de **10 %**, payable six jours après la valorisation :

- PV initiale : `0,1` ;
- PV attendue après +100 bp : `0,099983574…` ;
- PV réinjectée : toujours `0,1`.

L’erreur est de **16,43 € par million de nominal** dans cet exemple. Son amplitude dépend du montant et du délai restant. Les créances terminales disposent déjà d’un traitement spécifique du choc de taux.

**Recommandation :** réactualiser chaque créance déterministe sous les hypothèses choquées, en conservant sa date de paiement et les conventions de courbe du calcul.

[Réinjection de la PV initiale](C:/Users/admin/GitHub/structura/backend/app/api/shocks.py:192).

**Limites de couverture à rendre explicites**

La VaR applique des chocs à la photo résiduelle courante : elle ne déroule pas les événements et paiements jusqu’au terme de l’horizon demandé. La conversion en EUR utilise le taux retenu, sans simuler systématiquement le risque de traduction dans la devise de reporting. La sensibilité au spread émetteur n’est pas agrégée dans le risque portefeuille.

Le CCR reste un moteur économique à capacités encadrées : projection GBM compatible, valorisation sans ajustement de crédit émetteur, collatéral sur grille, IM fixe et indépendance du défaut. Le taux commun provisoire de **3 %** est un choix documenté et surchargeable. Le modèle joint de wrong-way risk et l’EAD SA-CCR sont absents ; le code l’annonce.

Les anomalies de booking du module 11 et de P&L du module 14 restent également des dépendances de la fiabilité du risque.

**Ordre de traitement recommandé**

1. **Sécuriser les couvertures** : facteurs VaR, sensibilités disponibles et séparation Production/UAT.
2. **Corriger les expositions proches des paiements**, puis leur intégration dans la CVA et les chocs.
3. **Unifier les critères de fraîcheur** entre préparation, calcul et moniteur.
4. **Remplacer les rapprochements par libellé** par les identifiants stables.
5. **Afficher les limites méthodologiques et la couverture effective** à côté des mesures publiées.

**Vérifications réalisées**

**97 tests backend et 5 tests frontend ciblés ont réussi.** Quatre autres cas ont échoué dans le banc initial : trois dépendent des composants d’authentification ou de migration volontairement remplacés pour isoler la base réelle ; un utilise une fixture RFQ sans le desk désormais obligatoire.

Les sept anomalies ont fait l’objet de reproductions complémentaires isolées, dont le calcul des 30 jobs VaR et la comparaison déterministe de CVA. Aucun service ni fournisseur externe n’a été sollicité. La recette navigateur et une étude de convergence complète du CCR restent hors de cette validation.

## M16

Les modules **16 et 17 sont audités**, sans modification du code ni de ta base métier.

Je retiens **10 constats : 4 P1 et 6 P2**. Les P1 touchent à la confidentialité ou à des chiffres susceptibles de fausser une décision. Les exemples ci-dessous proviennent de cas synthétiques isolés.

**Module 16 — Clients / CRM**

Le socle métier est solide : les principales faiblesses concernent les droits sur les données restituées et la cohérence des analyses.

**Points solides**

- La séparation **Client / Personne / Affiliation / Mandat** préserve correctement l’historique lorsqu’un contact change d’employeur.
- Les préférences déclarées, les observations et les déductions restent distinctes. Les habitudes sont accompagnées de preuves, de dénominateurs et d’indications de récence.
- Les préférences sont historisées et les écritures de listes protégées contre les écrasements concurrents.
- L’historique importé reste séparé du book : importer une transaction commerciale ne crée aucune position de risque.
- L’import comporte aperçu, contrôles, détection des doublons et annulation des transactions d’un lot.
- Les signaux Clients réutilisent le calendrier Life Cycle. Ils présentent une observation future comme conditionnelle, sans promettre un coupon ou un rappel.
- Le booking fige le contexte commercial ; une modification ultérieure du profil client ne réécrit pas ce snapshot.

### S-M16-01

**16.1 — P1 : le CRM restitue des détails de Deals interdits en consultation directe**

Un utilisateur ordinaire de la même entité, sans accès au Deal, obtient néanmoins dans la fiche CRM sa référence, son nominal, sa contrepartie, ses sous-jacents et son prix traité.

Le cas reproduit porte sur un booking natif avec Product canonique : accès direct refusé, mais restitution CRM d’un nominal de **1 M€** et du prix traité de **98 %**.

**Recommandation :** appliquer les droits des objets sources aux restitutions CRM. Si un partage commercial plus large est souhaité, il doit relever d’une habilitation explicite, avec un niveau de détail défini.

Sources : [autorisation Deal](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:1063), [entrée CRM](C:/Users/admin/GitHub/structura/backend/app/api/client_intelligence.py:51), [chargement des transactions](C:/Users/admin/GitHub/structura/backend/app/core/client_intelligence.py:325).

### S-M16-02

**16.2 — P2 : changer le client d’une opportunité peut casser ses rattachements**

Deux incohérences sont reproduites :

- une opportunité déplacée de **Client A vers Client B** conserve un participant affilié à A ;
- une opportunité déjà liée à un Deal peut être déplacée vers B alors que le Deal reste attribué à A.

Le snapshot du Deal reste préservé, mais la chaîne commerciale devient contradictoire.

**Recommandation :** revalider tous les participants existants lors d’un changement de client. Dès qu’une RFQ ou une exécution est attachée, remplacer le changement libre par une procédure explicite de rectification d’attribution.

Source : [changement de client de l’opportunité](C:/Users/admin/GitHub/structura/backend/app/api/opportunities.py:410).

### S-M16-03

**16.3 — P2 : une analyse historique inclut des transactions futures**

Une analyse demandée au **1er février 2026** compte une transaction du **15 janvier 2027**. Elle affiche cette dernière comme dernière transaction et calcule **−348 jours** depuis celle-ci.

La date `asof` intervient dans les calculs de récence, sans borner préalablement les faits analysés. Les habitudes et fenêtres de contact historiques peuvent donc bénéficier d’informations futures.

**Recommandation :** filtrer les transactions à la date choisie avant toute analyse. Pour les opportunités, distinguer une véritable restitution historique d’une lecture de leur état courant.

Sources : [sélection des transactions](C:/Users/admin/GitHub/structura/backend/app/core/client_intelligence.py:1493), [calcul du cycle](C:/Users/admin/GitHub/structura/backend/app/core/client_cycle.py:175).

### S-M16-04

**16.4 — P2 : les montants de devises différentes sont agrégés sans conversion**

Avec **1 million EUR** et **100 millions JPY** :

- le pipeline affiche un montant global de **101 millions** ;
- le ticket médian ressort à **50,5 millions**.

Ces chiffres additionnent des unités différentes et ne représentent aucun montant économique exploitable.

**Recommandation :** restituer les montants par devise. Un agrégat converti doit porter une devise de référence et des taux de change datés, avec une couverture explicite des conversions disponibles.

Sources : [pipeline](C:/Users/admin/GitHub/structura/backend/app/api/client_intelligence.py:227), [ticket médian](C:/Users/admin/GitHub/structura/backend/app/core/client_intelligence.py:456).

### S-M16-05

**16.5 — P2 : un historique importé sur un mandat fictif entre dans le profil réel**

Sur un client natif, une transaction importée via le véritable moteur d’import et rattachée à un mandat **Demo** est comptée dans l’analyse **réelle** : une transaction retenue, aucune donnée fictive exclue.

La provenance du mandat est examinée pour les Deals natifs, mais pas pour les historiques importés.

**Recommandation :** appliquer une règle commune d’éligibilité aux deux sources, en tenant compte du client, du mandat et de la provenance de la transaction.

Source : [normalisation des provenances](C:/Users/admin/GitHub/structura/backend/app/core/client_intelligence.py:282).

**Appréciation du module 16**

Le CRM fournit une bonne mémoire commerciale. La première correction à préparer concerne **la confidentialité des données sources** ; viennent ensuite les rattachements et la fiabilité temporelle et monétaire des analyses.

---

## M17

**Module 17 — Réinvestissement et déclinaisons**

Les mécanismes d’exploration sont utiles et plusieurs précautions quantitatives sont bien présentes. En revanche, certaines restitutions donnent aujourd’hui une précision économique supérieure à ce que leurs hypothèses permettent.

**Points solides**

- Les parcours de reconduction, scan et comparaison restent des études : ils ne bookent pas automatiquement une nouvelle opération.
- Une déclinaison conserve ses écarts par rapport au parent, sans modifier celui-ci.
- L’avenant distingue les termes utilisés pour rejouer le passé de ceux appliqués à la vie restante.
- Des modifications incompatibles avec un avenant, notamment certains changements de panier, sont refusées.
- Le roll recale les dates et retire les anciens niveaux initiaux.
- La probabilité de récupération du pair d’origine tient compte du nombre d’unités nouvelles acquises.
- Les candidats rejetés restent expliqués ; le solveur signale une cible non encadrée.
- La limitation du scan au mono-sous-jacent est annoncée.
- La reconduction simple transporte déjà davantage d’hypothèses de marché que le scan.

### S-M17-01

**17.1 — P1 : le scan abandonne des hypothèses matérielles de valorisation**

Le scan transmet au solveur et au calcul de probabilités le taux plat, mais omet notamment les courbes de taux et de funding ainsi que certains paramètres de taux et de règlement.

L’interface ne transmet pas non plus le modèle : la requête prend **`constant` par défaut**, y compris lorsque le Deal source utilise Heston.

Cas déterministe reproduit : pour un remboursement de 100 % dans trois ans, le scan trouve un coupon nul et affiche un prix de **100 %**. En réappliquant au même moteur l’hypothèse de funding de **10 %**, le remboursement vaut **74,0818 %**.

Le défaut est l’abandon implicite de ces hypothèses ; celles d’une nouvelle proposition doivent pouvoir être reconduites ou actualisées explicitement.

**Recommandation :** construire un contexte complet et visible, commun au prix, au solveur et aux probabilités. Toute simplification de modèle doit être choisie et affichée.

Sources : [appels du solveur et des probabilités](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:6593), [modèle par défaut](C:/Users/admin/GitHub/structura/backend/app/core/schemas.py:496), [requête de l’écran](C:/Users/admin/GitHub/structura/frontend/src/views/ReinvestView.vue:505).

### S-M17-02

**17.2 — P1 : le roll est financé au prix modèle, sans coût de sortie ni marge d’entrée**

Le comparateur utilise toujours :

`quantité nouvelle = prix modèle de l’origine / prix modèle de la nouvelle note`

Il ne dispose pas d’un bid de débouclage, d’une décote de liquidité ou d’un coût d’entrée. La valeur effectivement réinvestissable peut donc être surestimée.

Ce manque était déjà documenté en août ; il demeure présent dans le code actuel.

**Recommandation :** distinguer prix modèle, prix de sortie retenu, frais de sortie et prix d’entrée. Les hypothèses doivent être datées, sourcées ou clairement présentées comme manuelles.

Sources : [financement du roll](C:/Users/admin/GitHub/structura/backend/app/api/variants.py:250), [point ouvert documenté](C:/Users/admin/GitHub/structura/docs/projects/lifecycle/DECLINAISONS_POINTS_OUVERTS.md:102).

### S-M17-03

**17.3 — P1 : le « plafond de récupération » n’est pas un plafond**

Le champ affiche le nombre d’unités nouvelles achetées, sans tenir compte du remboursement total possible de chaque unité.

Un calcul réel du comparateur, avec un remboursement déterministe de **120 %** sur la nouvelle note, donne :

| Restitution | Résultat |
|---|---:|
| « Plafond » affiché | **95,6635 %** |
| Probabilité affichée de récupérer le pair | **100 %** |
| Récupération déterministe effective | **114,7961 %** |

L’écran présente donc un maximum inférieur à 100 % tout en affirmant que le pair sera récupéré avec certitude.

**Recommandation :** renommer le rapport des prix en « nominal réinvesti ». Un plafond de récupération doit provenir du payoff contractuel ; lorsqu’il n’est pas déterminable, afficher cette absence plutôt qu’une borne artificielle.

Sources : [calcul du champ](C:/Users/admin/GitHub/structura/backend/app/api/variants.py:248), [définition affichée](C:/Users/admin/GitHub/structura/frontend/src/components/VariantCompareTab.vue:75).

### S-M17-04

**17.4 — P2 : modifier la maturité ne redimensionne pas toujours les observations**

Sur un calendrier trimestriel de trois ans, utilisant `CONSTAT` sans fixing initial explicite :

- demander **un an** conserve environ **trois ans** de calendrier ;
- demander **cinq ans** conserve les **douze observations initiales**, dont la dernière reste à trois ans.

La maturité demandée et le produit effectivement calculé peuvent ainsi diverger.

**Recommandation :** reconstruire ensemble calendrier, observations, échéance et paiements. Si une structure ne peut pas être redimensionnée automatiquement, refuser la modification et orienter vers le Pricer.

Source : [adaptation du calendrier](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:6641).

### S-M17-05

**17.5 — P2 : les propositions ne sont pas figées et le PDF peut différer de l’écran**

Le téléchargement PDF relance le calcul et recharge les hypothèses de marché.

Avec la même requête et une volatilité synthétique révisée de 10 % à 60 %, j’ai reproduit :

- coupon affiché : **14,1602 %** ;
- coupon utilisé dans le PDF généré ensuite : **28,0762 %**.

Les comparaisons de déclinaisons ne disposent pas non plus d’un archivage complet de l’étude : origine, variantes examinées, hypothèses et décision. Les écarts restent modifiables et suivent leur parent.

**Recommandation :** créer une proposition versionnée et figée, distincte du brouillon vivant. Le PDF doit utiliser cette proposition. Archiver également les comparaisons retenues et leurs références sources.

Sources : [recalcul lors du PDF](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:6844), [modification d’une variante](C:/Users/admin/GitHub/structura/backend/app/api/scripts_db.py:470).

**Appréciation du module 17**

Le module convient à l’exploration interne, avec des réserves sur ses chiffres de décision. Les corrections prioritaires portent sur **les hypothèses réellement utilisées, le financement du roll et la définition de la récupération**. Le gel des propositions permettra ensuite d’en conserver une preuve fiable.

**Vérifications et limites**

- **439 tests backend ciblés réussis**, sur les domaines Clients, import, analyses, déclinaisons et bindings.
- **24 tests frontend réussis**.
- **Six tests de chaîne CRM/RFQ restent en échec** : leurs fixtures ne renseignent pas le desk pilote désormais obligatoire et sont arrêtées avant les assertions attendues. Ils ne valident donc pas ces parcours.
- Les reproductions complémentaires utilisent des bases temporaires, avec intégrité référentielle pour les cas de booking, et des données de marché synthétiques.
- La qualification utilise les routeurs réels dans une application de test isolée ; elle ne remplace pas une recette complète des écrans.
- Aucun appel externe, aucune suite backend complète et aucune modification du code ou de la base métier.

Les constats sont identifiés **16.1 à 16.5** et **17.1 à 17.5** pour les intégrer au prochain bilan transversal des urgences.


