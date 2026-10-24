# Corrections des trois défauts majeurs — 24 octobre 2026

IA-01, IA-02 et IA-03 de la [recette institutionnelle](INSTITUTIONAL_ACCEPTANCE_2026-10-24.md)
sont corrigés et rejoués sur une nouvelle installation fictive isolée.
Les résultats de l'audit initial restent conservés comme observations historiques.
La livraison inclut, à la demande de Philippe, les autres travaux déjà présents dans
le checkout ; cette recette ciblée ne qualifie pas globalement ces travaux.

## Booking OTC et documentation

Le point commun de booking contrôle la classification après rapprochement avec la
RFQ et le Product canonique. Un appel direct ne peut pas remplacer un contexte OTC
existant par une note. Le format et la famille doivent être explicites :
EMTN/BMTN/NOTE avec famille Note, ou OTC avec une autre famille identifiée.

Un OTC exige une référence documentaire et un netting set explicite couvrant la
contrepartie, la devise et le type de produit. L'accord doit être ACTIVE et effectif
à la date métier ; une expiration, lorsqu'elle est renseignée, est contrôlée.
Un CSA sélectionné doit être actif et cohérent ; un CSA requis par une relation
bilatérale active applicable ne peut pas être omis. Une exception administrative
d'identité ne remplace pas ces exigences OTC.

Une note peut être bookée sans ISDA et ne peut pas être placée dans un set OTC.
L'existence d'un accord effectif n'accorde aucune compensation automatique : les
conditions d'opposabilité et de collatéral du calcul CCR restent distinctes.
Les contrats historiques sans classification doivent être qualifiés pour emprunter
les contrôles qui l'exigent ; aucun défaut Note n'est ajouté aux données réelles.

## Observations contractuelles

La politique moteur devient `EXACT-CONTRACT-DATES-2026-10-24`.
La grille de diffusion conserve ses nœuds hebdomadaires et ajoute les dates
contractuelles d'observation, les relevés des fenêtres, les fixings initiaux et
les dates de marque MTF. Chaque transition utilise sa durée effective. GBM,
Heston, SABR, Local Vol, LSV, taux stochastiques et ponts browniens consomment les
mêmes intervalles ; les taux, dividendes, réductions et annualisations utilisent
leur temps effectif. Les budgets de calcul portent sur la grille enrichie.

Le Mark-to-Future et son panneau explicatif partagent la même grille et séparent
le passé du futur à la date de marque. Le CCR conserve les dates d'observation,
de marque et de paiement sans les arrondir à la semaine. Le monitoring discret
des extrema entre ces dates et les restrictions des modèles restent documentés ;
une grille exacte aux fixings ne rend pas toute approximation de diffusion exacte.

Les quatre forwards déterministes de l'audit, à 19/30/31/183 jours, valent désormais
**1,000000** après actualisation, contre 1,000170 / 0,999844 / 0,999762 / 0,999969.
Les tests vérifient aussi deux niveaux distincts à un jour d'intervalle, les poids
des fenêtres quotidiennes, la variance/corrélation d'un panier, Black-Scholes sur
trois graines, les cinq modèles et le forward sous taux stochastiques.

Le nouveau module `payscript/time_grid.py` entre dans l'empreinte moteur des
valorisations. Les archives antérieures ne sont pas réécrites ni présentées comme
des rejeux qualifiés du nouveau moteur.

## Horloge CCR

Le défaut de `CalculationRequest`, la sélection des limites, les accords, les
contrôles de booking/amendement et la sélection historique suivent la date métier.
Une date d'arrêté explicite reste possible pour les calculs historiques.
L'UI CCR initialise sa date depuis `/api/ccr/context`, sans utiliser l'horloge du
navigateur. Les horodatages techniques UTC de création et d'audit restent séparés.
La version CCR devient `ccr-1.5-business-clock-exact-contract-dates`.

Dans la recette métier au **02/01/2024**, une limite future au 01/01/2025 et une
limite expirée au 31/12/2023 ne bloquent pas le booking ; la limite active de
10 M€ reste appliquée. Les deux preuves CCR de booking de la contrepartie finale
portent `as_of_date=2024-01-02`, avec une date système en 2026.

## Validation et limites

- **531 tests backend ciblés distincts réussis** : 505 cas de pricing, calendrier,
  CCR, RFQ, exceptions juridiques, permissions et amendements, plus 26 cas de limites
  de ressources et validation des modèles. Le dernier échec du lot de 505 provenait
  d'un wrapper de test de corrélation ne transmettant pas le nouvel axe extérieur ;
  les cinq tests de son fichier ont été corrigés et rejoués avec succès. Les
  résultats finaux sont consolidés par identifiant de test, sans addition des reprises.
- **784 tests frontend réussis**, 88 fichiers ; `npm run build` réussi.
- **10 contrôles de recette réussis**, dont huit contrôles RFQ/booking/date CCR,
  un calcul CCR complet dans l'UI et son rejeu figé. Les entrées et fixings du calcul
  complet sont synthétiques et préparés par API native ; les actions de calcul et
  de rejeu sont exécutées dans l'UI. PFE95 : **1 174 279,50 €** ; CVA :
  **2 033,5604348562406 €** ; 32 scénarios extérieurs, 32 trajectoires intérieures,
  1 000 trajectoires MtM. Ce petit budget valide le parcours et le déterminisme,
  sans qualifier la convergence des quantiles pour la production.

Les refus UI couvrent les accords PENDING, futurs et expirés ; un accord effectif
permet le booking OTC, puis une note est acceptée sans ISDA. Le pricing RFQ d'un
forward observé à 31 jours est égal à 1. Les contrôles CSA et le booking direct sont
également couverts par les tests backend. Aucune suite backend complète exécutée.

Les preuves locales sont dans
`output/structura-major-fixes-2026-10-24/` : XML et journaux des tests, catalogue
consolidé, captures UI, requêtes/réponses natives, contrôles CCR conservés, rejeu,
empreintes des sources et preuve d'arrêt. Ce dossier, les bases et les secrets
ne sont pas versionnés. `backend/data/structura.db` était absent avant et après
la mission ; aucune donnée réelle ni aucun fichier de marché réel n'a été modifié.
Les processus possédés sont arrêtés et le port 19585 est libéré.

Les autres limites de l'audit initial — trésorerie native, limite de groupe,
règlements et portail investisseur notamment — restent ouvertes. Cette correction
ne constitue pas une homologation du mandat institutionnel autonome.
