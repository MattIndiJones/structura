# Cycle de vie des deals — booking, valorisation quotidienne, alertes barrières

**Statut** : investigation faite le 17.07.2026, tests et suite à planifier — reprise le 18.07.2026.

## 1. Objectif

Le booking de deals a été développé mais **jamais testé de bout en bout**. Le besoin exprimé va au-delà du simple booking : pouvoir suivre un book de produits structurés au quotidien — valorisation mark-to-market automatique chaque jour, et alertes quand un sous-jacent approche ou franchit une barrière (knock-in, autocall...).

Avant de construire quoi que ce soit de nouveau, il fallait d'abord établir avec précision ce qui existe déjà dans le code, ce qui manque, et comment tester la chaîne actuelle sans polluer les données réelles.

## 2. État des lieux — ce qui existe

### Booking (complet et fonctionnel a priori)
- `POST /api/deals` (`backend/app/api/deals.py`) : depuis un script pricé dans le Pricer, fige le script (`script_snapshot`), crée une ligne `Deal` (`backend/app/db/models.py`) et génère automatiquement le calendrier de constatations : un `DealEvent` à t=0 (date de strike / fixing S₀), puis un `DealEvent` par date d'observation détectée dans le script (libellés "Obs. N (t Y)" et "Maturité" pour le dernier).
- Interface : onglet **Deal** dans le Pricer (`frontend/src/components/DealTab.vue`), formulaire de booking (contrepartie, nominal, prix traité, dates, sens achat/vente).

### Suivi des constatations (onglet Events)
- `frontend/src/components/EventsTab.vue` : sélecteur de deal (simple liste de boutons, pas un tableau de bord), puis tableau des constatations du deal sélectionné.
- Saisie du spot par constat : **manuelle** (case à case, avec performance % vs S₀ affichée) ou **automatique** via le bouton "Actualiser spots Yahoo" (`POST /api/deals/{id}/events/refresh`) qui va chercher les clôtures historiques Yahoo Finance pour les constats déjà passés dans le calendrier (`load_hist_prices`).
- Statut par constat (`futur` / `observé` / `callé` / `ki` / `final`) : un menu déroulant, **basculé manuellement par l'utilisateur** — aucun calcul automatique ne compare le spot à une barrière.
- Statut global du deal (`actif` / `callé` / `échu` / `résilié`) : également manuel.

### Re-pricing (semi-manuel, non persisté)
- `GET /api/deals/{id}/reprice` renvoie le T restant, les spots normalisés (spot actuel / S₀ du strike event), le script figé et le snapshot marché.
- Le bouton "↺ Re-pricer" (EventsTab.vue) recharge ces valeurs dans le Pricer et dépose l'utilisateur dans l'onglet Marché & Paramètres — **il faut ensuite cliquer manuellement sur "Pricer"** pour obtenir un prix.
- **Important** : `fair_value` sur la ligne `Deal` n'est écrit qu'**une seule fois, au booking**. `DealUpdate` (le schéma de patch du deal) n'autorise même pas de le modifier. Le résultat d'un re-pricing est un affichage éphémère à l'écran — rien n'est sauvegardé, il n'existe aucun historique de valorisation.

### Outils annexes utiles pour les tests
- `/admin/browse/{table}` (`AdminBrowseView.vue`) : navigateur générique des tables de la base — permet d'inspecter directement les lignes `deals` et `deal_events` sans requête SQL manuelle.
- `/register` ou Admin > Users : création d'un utilisateur de test dédié.

## 3. Ce qui n'existe pas

- **Aucun job planifié** : ni cron, ni scheduler (APScheduler/Celery), ni script batch. Rien ne tourne automatiquement en fin de journée.
- **Aucun historique de valorisation** : pas de table `deal_valuations` ou équivalent, pas de série de fair_value dans le temps, pas de P&L quotidien calculé ni stocké.
- **Aucune détection automatique de barrière** : le statut "ki" d'un événement est purement déclaratif (choisi à la main). Aucun code ne parse le script pour en extraire un niveau de barrière et le comparer au spot du jour.
- **Aucune vue portefeuille agrégée** : pas de page listant tous les deals actifs avec leur M2M du jour, leur distance à une barrière, ou un P&L consolidé. Le seul "listing" est le sélecteur simple dans l'onglet Events (référence/contrepartie/nominal/statut uniquement).
- **Aucun mécanisme d'alerte** : pas d'email, de notification in-app, de webhook — recherché explicitement dans le code, absent.

**Conclusion** : le booking et le suivi manuel constat-par-constat sont testables dès maintenant. La valorisation quotidienne automatisée et les alertes de barrière ne sont pas des fonctionnalités buguées à corriger — ce sont des fonctionnalités **à concevoir et construire**.

## 4. Plan proposé pour demain

### Étape 1 — Tester la chaîne existante
Utilisateur de test dédié (ne pas polluer les données réelles), puis booker une poignée de produits volontairement différents pour couvrir les chemins distincts du code :

| Produit | Objectif du test |
|---|---|
| Vanille simple (1 échéance) | Chemin minimal : booking → 1 événement → maturité |
| Autocall multi-observations | Génération complète du calendrier (plusieurs `DealEvent`, libellés corrects) |
| Reverse convertible à barrière | Bascule manuelle du statut "ki", vérifier l'affichage (couleur, perf%) partout où c'est utilisé |
| Strike date dans le passé | `refresh_events` doit remplir plusieurs constats historiques d'un coup via Yahoo |
| Une date d'observation = aujourd'hui | Badge "aujourd'hui", bascule automatique futur → observé |

Parcours à dérouler sur chacun : pricer → booker → vérifier le calendrier généré (dates, T en années, libellés) → actualiser spots Yahoo / saisie manuelle → re-pricer → vérifier que T restant et spots normalisés atterrissent correctement dans le Pricer → changer un statut d'événement → contrôler l'état en base via `/admin/browse`.

### Étape 2 — Concevoir la valorisation quotidienne + alertes
À partir de ce que l'étape 1 aura révélé (bugs éventuels sur le calendrier, le refresh Yahoo, etc.), discuter et trancher :
- **Déclenchement** : job planifié côté serveur (nécessite un scheduler à introduire) vs. calcul à la demande quand l'utilisateur ouvre une vue portefeuille.
- **Persistance** : nouvelle table d'historique de valorisation (une ligne par deal actif par jour) — champs a minima : date, fair_value du jour, spots du jour, P&L vs prix traité.
- **Détection de barrière** : il faut d'abord déterminer si c'est extractible automatiquement du script PayScript (repérer les comparaisons à `WOF_MIN`/barrières dans le code compilé) ou si ça doit rester une saisie assistée par l'utilisateur avec un simple calcul de distance affiché.
- **Alertes** : canal de notification (in-app suffit probablement pour commencer, pas besoin d'email/webhook immédiatement) et seuil de déclenchement (barrière franchie vs. barrière approchée à X%).
- **Vue portefeuille** : nouvelle page listant tous les deals actifs avec leur état du jour — c'est le morceau d'UI qui manque le plus visiblement aujourd'hui.

## 5. Décisions encore ouvertes
- Scheduler côté serveur ou recalcul à la demande — dépend du volume de deals et de la fraîcheur de valorisation réellement nécessaire (fin de journée vs. temps réel à l'ouverture de la page).
- Faut-il persister un historique complet (audit-friendly) ou seulement la dernière valorisation connue par deal.
- Portée de la détection automatique de barrière : fiable seulement pour des scripts au pattern standard (WOF_MIN < niveau), ou generalisable à tout PayScript ?
