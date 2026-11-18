# Structura — Audit exécutif

**Date : 16 novembre 2026 · Commit audité : `eca6f52` (`main`) · Détail et preuves : [AUDIT_GLOBAL_TECHNIQUE_2026-11-16.md](AUDIT_GLOBAL_TECHNIQUE_2026-11-16.md)**

**État : Suivi.**

Même cahier des charges que l'audit de QISTRA du même jour : lecture du code, des configurations, des tests et des notes, sans rien modifier au code. Le moteur a été sondé contre des formules indépendantes. L'application n'a pas été lancée dans un navigateur, et la suite backend complète n'a pas été jouée, conformément à la règle du projet.

---

## 1. Verdict

**Structura est un atelier complet de structuration et de suivi de produits structurés, réellement fonctionnel sur un poste, dont le moteur de pricing tient la comparaison avec des références indépendantes. Ce n'est pas encore un outil que l'on installe chez un tiers, ni une source de prix opposable.**

- Le cœur — PayScript, moteur Monte Carlo, conventions de dates et de funding, traçabilité des valorisations — est solide et vérifié par le calcul.
- La couche « plusieurs organisations » — six installations, réseau RFQ, confirmation électronique — est bien conçue et **simulée sur un seul poste**.
- Les entrées de marché sont le maillon faible : une seule source, non officielle, et des volatilités saisies.
- Le contrôle ne suit plus la cadence de production. La suite complète, rejouée le 17/11, donne **69 échecs sur 4 393** et révèle **deux écrans cassés sans que rien le signale** : le Product Optimizer depuis le 05/11, le générateur UAT depuis le 24/10.

| Dimension | Maturité | Commentaire |
|---|---|---|
| Moteur de pricing et conventions | ●●●●○ | Recoupé sur GBM, Heston, barrière continue, funding ; pas de barrière en clôture quotidienne |
| Couverture du cycle de vie | ●●●●○ | Du payoff à la note de valorisation ; large part lue en surface |
| Données de marché | ●●○○○ | Yahoo seul, fixings officiels compris ; volatilité saisie |
| Documents réglementaires | ●●○○○ | KID et EMT indicatifs |
| Interface | ●●●○○ | Complète et soignée dans le code ; non observée à l'écran |
| Sécurité applicative | ●●●●○ | Conception soignée ; protections web à compléter |
| Base de données | ●●●○○ | Intégrité active et preuves immuables ; ni sauvegarde ni migrations versionnées |
| Industrialisation | ●●○○○ | Beaucoup de tests, peu de garde-fous ; aucun déploiement |
| Plusieurs organisations | ●●○○○ | Bien conçu, simulé sur un poste |

---

## 2. Ce qui fonctionne réellement

Vérifié par exécution pendant cet audit.

- **Le moteur est juste là où il a été sondé.** Call européen contre Black-Scholes : écart de 3 pb, dans l'intervalle de confiance. Heston contre son prix semi-analytique : 1 pb. Barrière continue contre la formule fermée : 2 pb. Mark-to-Future d'un zéro-coupon : exact.
- **La règle du funding tient sur un produit qu'elle n'avait pas servi à écrire.** Autocall 3 ans worst-of : 100 pb de taux coûtent 13 pb, 100 pb de spread émetteur en coûtent 189.
- **Un prix est reproductible et traçable.** Même graine, même prix au dernier chiffre. Chaque valorisation enregistre le commit, l'empreinte des fichiers du moteur et son contexte rejouable.
- **Tests** : 159 réussis sur 160 dans le lot ciblé (moteur, PayScript, comptes, permissions) ; 997 sur 997 côté interface ; build identique au bundle livré.
- **Accès** : toutes les routes métier exigent une identité ; aucun compte par défaut ; sessions révocables ; mot de passe de 12 caractères.
- **Intégrité** : clés étrangères appliquées, preuves d'exécution et termes des produits immuables par déclencheur, audit écrit dans la transaction de l'action.
- **Échanges entre installations** signés, HTTPS exigé, expéditeur et destinataire liés.
- **Documentation franche** : chaque note écrit ce qu'elle ne prouve pas.

## 3. Ce qui est simulé, partiel ou seulement prévu

| Fonction annoncée | Réalité |
|---|---|
| SaaS hybride à six organisations | **Simulé.** Six dossiers et un annuaire central sur un seul poste, tous en adresse locale |
| Réseau RFQ entre banques, confirmation électronique | **Simulé.** Transport signé réel, jamais sorti du poste ; banques fictives |
| Recette institutionnelle de 100 M EUR | **Simulé**, déclaré tel |
| Données de marché | **Partiel.** Yahoo Finance seul, y compris pour les fixings officiels |
| Surfaces de volatilité, calibration du smile | **Partiel.** Hypothèses saisies ; aucune volatilité implicite de marché |
| KID PRIIPs, EMT | **Partiel.** Indicatifs ; la VEV n'est pas celle du règlement |
| Barrières américaines | **Partiel.** Grille de diffusion ou continu ; pas de clôture quotidienne |
| Booking | **Partiel.** Complet en interne, sans connecteur tiers ni preuve de règlement |
| Campagnes d'agents IA | **Simulé.** C'est un outil de recette |
| Registre central des RFQ, facturation | **Prévu** |
| Installation chez un tiers | **Absent.** Ni paquet, ni TLS, ni sauvegarde |
| Term sheets | **Non vérifié** |

## 4. Les sept risques qui comptent

1. **Le contrôle ne suit plus la cadence.** Verte le 23 octobre, la suite complète donne 69 échecs le 17 novembre. Deux livraisons ont chacune cassé un écran : **le Product Optimizer ne résout plus aucun candidat** depuis l'ajout des grilles de diffusion, et **le générateur UAT ne peut plus booker** depuis l'ajout du contrôle juridique. Les autres échecs sont des tests que ces contrôles ont rendus périmés, et quatre attentes numériques dont trois restent à qualifier.
2. **Un prix Structura est un prix d'hypothèses, pas un prix de marché.** Volatilité historique ou saisie, taux saisis, cours Yahoo. La précision du moteur dépasse celle de ses entrées.
3. **La barrière américaine est mal servie.** Sur un PDI à 70 %, 1 an, vol 25 % : 4,01 % en mode par défaut, 4,20 % en observation quotidienne, 4,43 % en continu. Le mode par défaut **surévalue la note de 19 pb** sur cette instance ; aucun mode ne reproduit la convention la plus courante.
4. **Un fixing contractuel repose par défaut sur Yahoo.** Les clôtures de cette source deviennent officielles automatiquement, après contrôles. Elle n'est ni officielle ni licenciée pour un usage commercial.
5. **Les documents réglementaires ne sont pas conformes.** Le code du KID le dit lui-même. À ne remettre à personne sans la mention.
6. **Perte de données.** Aucune sauvegarde périodique. Sur ce poste, la base historique n'a qu'une copie manuelle, dans le même dossier.
7. **Dépendance à une seule personne et commits non relisibles.** Une livraison de 774 fichiers réunit 27 chantiers ; aucune correction ne peut être isolée ni annulée seule.

S'y ajoutent deux points à connaître avant tout partage. **Le dépôt n'est pas partageable en l'état** : 45 Mo de bundles empilés, des journaux, une étude AMC sur ISIN réel dans l'historique, et des organisations fictives qui portent des noms de banques réelles. **Un script PayScript peut bloquer le serveur** : aucune injection de code n'a abouti aux tests, mais un calcul sans fin reste possible pour un utilisateur habilité.

## 5. Forces à préserver

- Les **conventions de pricing écrites, expliquées et recoupées** : quatre dates, funding en actualisation seule, magnitudes présentées comme des mesures d'instance.
- La **continuité** du payoff à la note de valorisation, sans ressaisie.
- La **traçabilité de chaque valorisation**, plus poussée que dans QISTRA.
- Le **refus plutôt que la valeur par défaut** : modèle inconnu, paramètre hors domaine, identifiant non déclaré, devise sans calendrier.
- Le modèle **« une organisation, une installation, une base »**, qui évite le cloisonnement par le seul code.
- La **culture de la limite écrite** dans les notes de recette.

## 6. Structura peut-il devenir un produit commercialisable ?

**Oui comme outil d'un conseil en structuration, dès maintenant ou presque. Non, en l'état, comme logiciel installé chez un tiers.**

| Scénario | Faisabilité | Ce qu'il faut |
|---|---|---|
| **Outil interne** d'un structureur ou d'un conseil, sur un poste | Prêt après durcissement | P0 : environ deux semaines |
| **Service de conseil** : Structura reste chez vous, vous livrez analyses d'appels d'offres, pricings indépendants, notes de valorisation, études AMC | 2 à 3 mois | P0 + données sourcées et tracées + dossier de validation + documents marqués |
| **Installation chez un client pilote**, supervisée | 4 à 6 mois | P0 + P1 : données licenciées, moteur vectorisé, sauvegardes, journaux, parcours testés de bout en bout |
| **Réseau RFQ entre organisations réelles** | 9 à 12 mois, avec une équipe | P2 : déploiement, TLS, identité déléguée, supervision |
| **Offre hébergée multi-clients** | Au-delà | À ne viser qu'après un premier client payant |

Le second scénario est le plus court chemin vers un revenu. Il valorise ce qui est déjà bon — le moteur, les conventions, la preuve — sans exiger ce qui manque : l'exploitation chez autrui.

## 7. Recommandations

### Décisions à prendre

1. **Geler les nouvelles fonctions deux à trois semaines** au profit de P0. L'outil a plus de surface que de garde-fous.
2. **Choisir le scénario cible.** Il décide si l'effort va aux données et à la validation, ou au déploiement et au réseau.
3. **Choisir une source de données licenciée** et son budget. Sans elle, aucun prix ni aucun fixing n'est présentable à un tiers.
4. **Fixer une règle de livraison** : suite complète chaque nuit sur GitHub, un commit par chantier, une étiquette par livraison. La règle locale des tests ciblés reste intacte.
5. **Trancher la convention de barrière par défaut** et le marquage des documents réglementaires.
6. **Décider du sort de l'historique Git** et renommer les organisations fictives avant toute démonstration.

### Actions immédiates (P0, environ deux semaines)

| Action | Bénéfice |
|---|---|
| Réparer le Product Optimizer et le générateur UAT | Deux écrans rendus au métier |
| Mettre les 69 tests en échec au niveau du code, puis rejouer la suite | Un état vert connu |
| Suite complète nocturne en CI, déclenchée aussi sur `main` | Plus de test rouge invisible |
| Sauvegarde quotidienne par installation, restauration testée, mode WAL | Plus de perte de travail |
| Mode de barrière en clôture quotidienne, affiché dans chaque document | Un prix conforme au contrat |
| Mention « indicatif » imposée sur KID et EMT | Risque réglementaire levé |
| Un seul bundle suivi ; journaux et fichiers de travail retirés du dépôt | Dépôt partageable |
| Borner les expressions PayScript ; délai sur le pricing interactif | Serveur non bloquable |
| Une version unique, une étiquette par livraison | Livraisons nommables |

### Ensuite (P1, deux à trois mois)

Second fournisseur de données et surfaces implicites importées, KID conforme, dossier de validation du moteur, évaluation vectorisée du payoff, découpage du module de cycle de vie, tests sous intégrité référentielle, migrations versionnées, protections web et secrets, journaux, parcours d'interface automatisés.

### Évolutions métier les plus rentables (P3)

1. **Portail client en lecture seule** : notes de valorisation, cycle de vie, documents.
2. **Marché secondaire** : politique d'écart acheteur-vendeur et de rachat, à partir du MtM résiduel existant.
3. **Chaîne documentaire de production** : KID, EMT et term sheets par émetteur.
4. **Premier connecteur de booking**, avec un client pilote.

La roadmap complète, avec fichiers, effort et dépendances pour chaque action, figure dans [le rapport technique, section 9](AUDIT_GLOBAL_TECHNIQUE_2026-11-16.md#9-roadmap-priorisée).

## 8. Limites de cet audit

- **Suite backend complète** : lancée le 17/11 à la demande de Philippe, sur données isolées : 4 323 réussis, 69 échecs, 1 ignoré, en 50 minutes. Lecture détaillée dans le rapport technique, section 6.1 bis.
- **Non vérifié** : rendu et ergonomie dans le navigateur, fonctionnement des six installations, réseau RFQ entre deux machines, exécution de la CI sur GitHub, appels aux fournisseurs d'IA.
- **Non sondé numériquement** : SABR, Local Vol, LSV, Greeks, quanto.
- **Lu en surface** : AMC, FIFO, Fama-French, CCR, VaR, Product Optimizer, CRM, EMT, cycle de vie.
- **Mesures d'instance** : tous les chiffres de pricing valent pour le produit, les paramètres et la graine indiqués dans le rapport technique, pas comme constantes.
- Les délais supposent une personne expérimentée à plein temps, assistée d'agents, hors temps de décision et de contractualisation.
