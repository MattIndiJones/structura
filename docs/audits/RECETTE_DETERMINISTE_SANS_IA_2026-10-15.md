# Recette déterministe sans IA — 15 octobre 2026

## Périmètre

Le pilote réutilise `scripts/check_workshop_diagnostic.py` et les modules natifs de Structura, dans des bases privées sous `.runtime/diagnostic-acceptance/03fb0248a8a349edbce11254398416c1/14df9b4ea56f4452abb6ac080be31831/`. Il ne touche ni aux six installations d'essai manuel, ni à `backend/data/structura.db`, ni à la campagne IA arrêtée `b567dd8d1ad84d9fa74823796ca23858`.

La configuration garde un premier mois vide, puis une reverse convertible demandée par Leonteq et un Phoenix demandé par Kepler au deuxième mois, enfin un Athena classique demandé par Kepler au troisième. BNP, Société Générale et Citi sont répondants. Les décisions commerciales de ce pilote sont fixées explicitement par le script ; aucun agent ni appel de modèle n'intervient.

## Résultats observés

- Exécution `PASS` du 15/10/2026, de 06:43:07 à 06:44:58 UTC, soit environ 111 secondes ; **zéro appel IA et zéro coût API**.
- Trois RFQ, neuf cotations natives et trois deals de 10 M€ ; quatre jambes par dossier, toutes `COMPLETE` selon le rapprochement, sans écart ni doublon après une demande de booking répétée.
- Relation juridique BNP suspendue : refus attendu, sans création de nouvelle contrepartie. Limite de notionnel Citi abaissée : refus de booking HTTP 422, sans écriture ; les paramètres privés sont restaurés ensuite.
- Historique local `AIR.PA` réutilisé. Le point trimestriel et la date finale du 14/10/2026 ont été exercés. Lecture finale des six SQLite en mode lecture seule : douze positions, dont quatre `échu` et huit `callé` ; aucune position active.
- L'interface de **configuration** s'affiche en pleine largeur et son estimation réagit sans démarrer d'agent. Les routes des autres modules sont signalées `EXERCISED` par le contrôle technique existant, ce qui ne vaut pas validation de leurs formulaires par un utilisateur.
- Les six processus d'acteur ont été fermés ; les ports enregistrés sont libres. Les bases, le rapport `acceptance-result.json`, les journaux et les captures sont conservés dans le dossier de preuve ci-dessus.

## Limites et prochaine vérification

Ce pilote n'utilise qu'**AIR.PA** : il ne valide pas encore un panier multi-sous-jacents. `lifecycle` et `valuations` restent `NOT_TESTED` dans la matrice de couverture ; le CCR est `NOT_APPLICABLE` à ces notes. Le scénario saute directement d'un point trimestriel représentatif au cutoff final ; il ne démontre pas soixante mois continus ni tous les événements contractuels intermédiaires. La colonne historique `close` ne certifie pas un fixing brut non ajusté.

La prochaine recette doit porter sur un panier à plusieurs sous-jacents et sur un parcours **humain** dans les écrans RFQ reçues/envoyées, Product, Booking, événements et valorisations. Il faudra vérifier la saisie, les messages, la validité et les preuves visibles, en distinguant ce contrôle utilisateur des succès API ci-dessus. Aucun commit ni push.
