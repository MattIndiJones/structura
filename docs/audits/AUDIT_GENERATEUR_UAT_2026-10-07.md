# Générateur UAT — alignement PayScript au 07/10/2026

## Périmètre

Vérification de `backend/app/services/uat_generation.py`, de son masque
Administration et de ses adaptateurs CLI, après les changements Basket / StartDate
et l'ajout des exemples préremplis. Aucun lot créé dans la base réelle.

Le générateur avait déjà adopté `UNDERLYING Basket`, `Basket.yield`, le fixing
initial explicite, les `PARAM` sans défaut et les jambes PAY séparées.
StartDate est renseignée indépendamment de la première observation ; cette
observation est incluse et son INDEX commence à 1. Les valeurs contractuelles
sont fournies par `user_params` en fractions, avec les conversions d'affichage
du parcours ordinaire Product / RFQ / Booking.

## Écarts corrigés

- **Phoenix Mémoire** : le libellé désignait un produit à mémoire, mais le
  générateur sélectionnait `phoenix`, sans rattrapage. Il sélectionne maintenant
  `phoenix_memoire`. Un coupon trimestriel de 2,5 %, manqué au premier constat
  puis acquis au deuxième, verse 5 % au deuxième ; un rappel au troisième verse
  ensuite 2,5 % et le capital, sans nouveau remboursement à maturité.
- **Capital garanti** : le générateur réécrivait localement le script du catalogue,
  remplaçant PART par M_PARTICIPATION et supprimant STRIKE. Il reprend désormais
  le script exact ; Economics fournit PART et STRIKE (100 % pour ce jeu de test).
- Les quatre familles utilisent une correspondance explicite avec le catalogue,
  sans remplacement de texte ni sélection implicite du capital garanti pour
  une famille inconnue. Le constructeur de scripts ne reçoit plus de valeurs
  contractuelles : celles-ci restent dans Economics.

Ces corrections concernent les futurs lots. Aucun snapshot contractuel existant
n'est réécrit.

## Contrôles

- `backend/tests/test_uat_scripts.py` : 65 cas sans fournisseur ni base persistante.
  Identité avec le catalogue, paramètres requis en %, calendriers des huit profils
  compatibles en mono et multi, fixing séparé, rang 1, première observation incluse,
  rattrapage mémoire, STOP, capital et put séparés, participation du capital garanti.
- `backend/tests/test_uat_generation.py` : parcours des quatre familles,
  Product → RFQ → Booking, conservation des valeurs effectives et du script exact,
  cinq modes d'entrée, fixings, valorisations et nettoyage isolé des lots.

Commande de validation depuis la racine :

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest backend/tests/test_uat_generation.py backend/tests/test_uat_scripts.py -q --tb=short
```

Résultat : **98 tests passés en 198,98 secondes**. Le contrôle ciblé
`test_la_copie_serveur_est_synchrone_avec_le_catalogue` passe également :
**99 tests distincts au total**. Aucune suite backend complète ni nouvelle
recette navigateur ; aucune modification Vue.

## Limites conservées

Le générateur propose Athena, Phoenix Mémoire, Reverse Convertible et Capital
garanti. Il ne constitue pas une recette exhaustive des 19 scripts génériques ou
des 15 exemples préremplis, et utilise le modèle constant avec ses hypothèses UAT.
Il ne valide donc pas les nouveaux profils de smile ni les autres moteurs de vol.
Les profils historiques utilisent le fournisseur de fixings : leur nom ne force
pas un rappel ou un KI, l'issue résulte des cours effectivement obtenus.

La vérification des calendriers couvre ici les hypothèses EUR proposées par
défaut ; les calendriers de toutes les devises et toutes les conventions n'ont
pas fait l'objet d'une recette exhaustive dans cet audit.

Le CLI `seed_workflow_uat.py` appelle le même service. Le générateur historique
`generate_demo_deals.py` reste retiré. Pour charger les corrections dans un
backend déjà ouvert, redémarrer cette instance ; elle n'a pas été arrêtée par
l'assistant pendant cet audit.
