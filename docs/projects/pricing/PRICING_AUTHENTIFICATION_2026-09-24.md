# Authentification des appels du pricer — 24/09/2026

## Incident et cause

Un clic sur Pricer avec le script Athena initial affichait « Le script a changé
pendant sa validation », sans modification du texte. Le serveur exige désormais
un jeton sur les routes de pricing et de données de marché, mais certains appels
frontend utilisaient encore `fetch` sans en-tête Authorization.

La requête `/api/parse` non authentifiée a été vérifiée sur le serveur local :
HTTP 401, `{"detail":"Not authenticated"}`. Le frontend traitait ce corps comme
un résultat de parsing ; l'absence du champ `errors` déclenchait ensuite le
message trompeur sur une modification du script.

## Correction

- 30 appels dans le store de pricing, Economics, ObservationSchedule,
  useObservationPreview et RfqView utilisent désormais `apiFetch` : validation,
  prix, profil, chemins, probabilités, backtest, Mark to Future, solveur, grille,
  scénarios, transcription, calendriers et données de marché.
- La validation distingue erreur HTTP/réseau, réponse inattendue et erreur de
  syntaxe. Un HTTP 401 demande de se reconnecter ; un HTTP 403 signale les droits
  manquants. Les déclarations et les saisies précédentes restent conservées.
- Les réponses de validation devenues obsolètes restent ignorées.
- Un test parcourt les sources frontend pour détecter les appels directs à
  `fetch` hors du transport commun et des écrans dédiés à l'authentification.
  Les tests du transport vérifient aussi le renouvellement du jeton et le
  maintien des options JSON/multipart.

## Vérification

- Tests ciblés pricing et transport : 71/71.
- `npm run build` : 217/217 tests frontend et compilation réussie.
- Recette navigateur avec le serveur préexistant et la version reconstruite :
  Nouveau Pricing, Athena par défaut, clic Pricer sans modifier le script ni
  les paramètres : prix 97,91 %, IC 95 % [97,76 % ; 98,05 %], 20 000 chemins,
  2 585 ms. Ces chiffres décrivent cette exécution, pas une valeur générale.
- Profil de payoff : calcul réussi, valeur ATM affichée 108,00 %.
- Toutes les fonctions corrigées n'ont pas fait l'objet d'une recette UI
  individuelle ; le contrôle transversal et les tests couvrent le mécanisme
  d'authentification partagé.

Le frontend compilé est actualisé. Recharger l'onglet utilisateur pour charger
les nouveaux fichiers ; aucun redémarrage backend n'est nécessaire.
