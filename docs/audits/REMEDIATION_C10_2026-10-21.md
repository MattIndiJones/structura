# C10 — Réponses tardives et erreurs dans les interfaces

Livraison locale du 21 octobre 2026, sans commit ni push. Les huit constats
C10 sont corrigés et validés localement. Les points de départ ont été
revérifiés par lecture des gestionnaires avant correction ; les régressions
déterministes après correction sont reliées à chaque critère dans la preuve.

Le registre ne déclare aucun prérequis bloquant. C10 prépare la qualification
C17 en empêchant l'application d'une calibration hors contexte ; il ne qualifie
pas les modèles ni la qualité quantitative de la calibration.

| Constat | Correction et validation |
|---|---|
| M03-03 — marché appliqué au mauvais sous-jacent | Les chargements individuel et panier vérifient la révision de la demande et celle du contexte avant application, y compris après la requête dividendes. Changer ticker, remplacer une ligne, modifier une hypothèse, une corrélation ou la date empêche l'écrasement. Un aller-retour A → B → A est également protégé. Une réponse encore courante reste applicable. |
| M05-07 — ancien aperçu de calendrier | L'invalidation est synchrone aux changements des dates, de devise et de contexte. Une ancienne réponse ne remplace plus le calendrier courant. Un calendrier CONSTAT refusé n'est plus remplacé par les flux d'un ancien prix ; son erreur est affichée dans Economics et Events. Les clôtures historiques sont aussi liées aux dates et tickers de leur demande. |
| M07-02 — calibration hors contexte | Les appelants transmettent un contexte vivant : modèle, horizon, taux et, pour l'éditeur, sous-jacent affiché. La clé inclut les inputs de surface, les paramètres, l'identité et le niveau du sous-jacent. Seule la demande propriétaire peut appliquer son résultat. Une ancienne demande chevauchée ne remplace pas les paramètres, l'état ou l'erreur de la dernière. Pricer et RFQ contrôlent à nouveau le contexte avant transmission. |
| M09-06 — ancien détail face à un nouveau prix RFQ | La décomposition est liée au prix enregistré, à son horodatage, à l'empreinte d'entrée et à la version des termes. Recharger le même dossier invalide le détail si cette identité change. Un rafraîchissement des seules cotations conserve le détail compatible. L'empreinte est fournie par le serveur avec les mêmes restrictions que le prix modèle. |
| M09-09 — refus de saisie RFQ invisibles | Prix, statut, fermeté, dates, ajout, suppression et sélection attendent leur résultat et traitent le refus. Le sens et le last look suivent aussi ce chemin. L'erreur est affichée, la saisie refusée reste identifiable et la valeur serveur est rechargée. Si ce rechargement échoue, l'écran précise qu'il conserve la dernière valeur connue. Un ancien refus ne restaure pas une saisie plus récente ni un dossier quitté. |
| M10-03 — preuves d'exécution transportées entre dossiers | Changer de RFQ, de cotation sélectionnée ou d'accord réinitialise références, contacts, dates, preuves, canaux, clé de commande, motif d'annulation et complétude. Une réponse tardive de termes ne remplit pas le nouveau formulaire. Rafraîchir le même accord conserve les saisies en cours. Une confirmation incomplète n'est pas transmise. |
| M10-04 — réaffectation tardive remplaçant le dossier actif | Ouverture, prise en charge, membres et réaffectation sont liées au dossier ouvert et à une génération de consultation. Une réponse A peut actualiser sa ligne de liste sans remplacer B. Fermeture, erreur et réponse ancienne ne réouvrent pas A et n'altèrent pas l'état de chargement du nouveau dossier. |
| M12-06 — disparition d'une alerte malgré un refus | Acquittements individuel et global vérifient le succès HTTP avant retrait. Refus métier, HTTP 500/403 et erreur réseau conservent les alertes et affichent l'erreur. Les boutons évitent les doublons. Un ancien chargement ne ressuscite pas une alerte acquittée ; le retrait global local conserve les nouvelles alertes apparues pendant l'attente. |

## Autorité et gestion des états

Les protections sont locales à leurs demandes. Elles ne suppriment pas une
opération métier déjà acceptée par le serveur : une réponse de réaffectation
de A peut encore mettre à jour sa ligne. Elles empêchent son résultat de
prendre la place du dossier B et empêchent son erreur de contaminer B.

Le store RFQ conserve la sérialisation des modifications par cotation. Les
lectures et mutations sont liées au contexte courant ; une lecture antérieure
à une écriture réussie ne peut pas réinstaller son ancien état. Les refus sont
traités par les gestionnaires de l'écran. Les champs natifs reviennent à la
valeur relue ; la saisie refusée est présentée séparément, avec `SensitiveValue`
pour conserver les protections d'affichage.

La calibration vérifie le contexte vivant plutôt que de comparer uniquement
les arguments primitifs capturés au départ. Les demandes identiques restent
dédupliquées. Une demande remplacée rend la main sans publier un échec sur la
dernière. Un contexte modifié sans demande de remplacement signale une
calibration périmée et arrête la préparation du calcul. Les paramètres de modèle
explicitement manuels gardent leur traitement existant.

## Interactions et dépendances

- **C01 :** `model_input_hash` est privé au droit `price`, comme `model_price` et son horodatage. Les tests des droits de desk et de confidentialité des publications bancaires passent.
- **C02 à C04 :** sessions, identité d'installation, identifiants juridiques, exception administrateur et amendements gardent leurs contrôles existants. Aucun droit ni contournement serveur n'est ajouté.
- **C05 :** les calendriers sont toujours générés par les API existantes ; seules l'acceptation d'une réponse et la restitution d'un échec changent. Les calendriers contractuels figés ne sont pas régénérés.
- **C06 :** Product, version des termes et dossier courant restent distincts. Les termes privés ne sont pas reconstruits à partir d'une cotation ; les tests des transitions Product/RFQ passent.
- **C07 :** une réponse tardive ne remplace pas une saisie ni les hypothèses conservées. Un refus laisse le formulaire d'ajout ouvert ; un rafraîchissement du même accord conserve les preuves non envoyées. Les tests de conservation, configurations et reprises passent.
- **C09 :** compilation et qualification PayScript restent inchangées. Leurs tests frontend passent dans le build ; les rapports et preuves C09 sont conservés à l'identique.
- **C17 :** la condition d'actualité asynchrone de T11 est validée localement. La convergence, les bornes, le domaine et la qualification quantitative restent à traiter par C17.

La recette **T11 reste partielle** : champs de forme C07 et réponses hors
contexte C10 sont validés localement ; la qualification de calibration C17 reste
ouverte. Aucun autre chantier ou scénario transverse n'est clos par cette livraison.

## Validation et preuves

- **69 nouveaux tests frontend C10** : 33 dans `stores/asyncContext.test.js`, 36 dans `views/asyncInterfaces.test.js`. Ils contrôlent des promesses retardées, les réponses inversées, les changements de contexte, les refus HTTP/réseau et les chemins de succès courants.
- **615 tests frontend sur 70 fichiers**, tous réussis, puis build Vite en **12,58 s**. La sortie du build est dans un répertoire temporaire. Le `frontend/dist` préexistant reste conservé.
- **37 tests backend ciblés sur trois fichiers**, tous réussis en **13,50 s** : droits de desk RFQ, échanges Product/RFQ et confidentialité des publications bancaires. Un nouveau test contrôle l'empreinte privée ; le test de pricing natif existant contrôle aussi la cohérence du prix, de l'horodatage et de l'empreinte après rechargement.
- Les tests de refus/rechargement ont permis de corriger l'invalidation excessive d'un formulaire lors d'un rafraîchissement du même identifiant. Le test de conservation des preuves du même accord couvre explicitement ce cas.

La [preuve consolidée](remediation-lot-0-2026-10-20/C10_VALIDATION.json) contient
les critères, les tests, les résultats, les empreintes des fichiers et les contrôles
de conservation. Les journaux, le rapport JSON des 69 nouveaux tests et le JUnit
backend sont dans `.runtime/diagnostic-acceptance/c10-2026-10-21/`, répertoire local
ignoré par Git.

## Limites

La validation des interfaces repose sur les composants, stores et composables
réels avec des réponses réseau déterministes. Les éléments natifs des champs
sont représentés dans les tests ; une recette graphique manuelle, clavier et
viewport reste à effectuer. Les erreurs ne constituent pas une garantie de
livraison réseau : après une perte de réponse, une opération peut avoir été
acceptée par le serveur, d'où la relecture du dossier.

Aucune suite backend complète, base métier, migration, campagne IA ou ouverture
de service n'a été utilisée. La qualité quantitative de calibration C17 et la
qualification de production restent ouvertes. Aucun commit ni push.
