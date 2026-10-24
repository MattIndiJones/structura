# Lot 2 — C07 : conservation et reprise des saisies

**21 octobre 2026 — implémentation et validation locales, sans commit ni push.**

Les douze constats C07 ont reçu un correctif sur le périmètre décrit ci-dessous.
Le prérequis C06 est conservé : une copie de travail n'écrit pas les termes
enregistrés ; une sauvegarde explicite passe par les contrôles de version du
serveur. Le [registre](remediation-lot-0-2026-10-20/REGISTER.json) et les
[preuves](remediation-lot-0-2026-10-20/C07_VALIDATION.json) distinguent cette
validation locale de la qualification graphique, transverse et de production.

## Résultats par constat

| Constat | Correction et résultat vérifié |
|---|---|
| M04-04 — ancien prix et réouverture | La reprise automatique choisit un calcul des termes ouverts. Sans calcul compatible, elle charge les termes et annonce les hypothèses de marché à vérifier. La bibliothèque distingue le prix historique de la version courante. Une erreur d'ouverture conserve la session antérieure, affiche une erreur et permet de réessayer sur la même route. |
| M04-05 — brouillon difficile à compléter | L'action « Modifier les termes » ouvre une copie de travail d'un Product non exécuté. La conservation exige un motif et la révision attendue ; le serveur crée la version applicable. Un conflit conserve les saisies. Prix et transfert attendent la sauvegarde. Nominal et contexte commercial ne sont pas édités par ce geste. |
| M04-08 — comparaison incomplète | La comparaison restitue notamment les nœuds ATM, eta, rho et l'échelle de surface, ainsi que le modèle de taux, sigma_r et a_r. Unités et paramètres inactifs sont identifiés. Modèle et réglages numériques apparaissent aussi dans les comparaisons. La comparaison avec le calcul précédent fonctionne au-delà d'une page. |
| M04-10 — bibliothèque sans dossier ni pagination | La ligne se déplie en dossier avec RFQ, exécution, références documentaires et historique des versions/actions. Les documents de type DOCUMENT se téléchargent par leur route habilitée existante ; KID/EMT restent des références conservées. Les produits, calculs et révisions sont paginés ; les inputs et résultats détaillés ne sont lus qu'à la demande. La volumétrie de production reste à qualifier. |
| M05-02 — changements de forme destructifs | Une série vers un scalaire exige de choisir la ligne retenue ; le calcul reste bloqué avant confirmation. La série précédente reste disponible dans la session. Les formes de calendriers restent distinctes, leurs champs compatibles sont conservés et une date unique ne devient pas implicitement un échéancier daté. |
| M05-03 — série partielle perdue | `[8, vide, 12]` devient `[0.08, null, 0.12]` dans le brouillon. La réouverture conserve les cellules présentes. La complétude identifie la cellule manquante ; le pricing canonique et le booking incomplet sont refusés. |
| M05-04 — configuration partiellement appliquée | Tous les JSON, leurs structures et le parsing sont contrôlés avant mutation du store. Un refus laisse script, valeurs, marché et résultat inchangés. Une saisie effectuée pendant cette préparation empêche son remplacement. L'installation de la configuration validée est synchrone. |
| M05-05 — portée cachée des configurations | L'aperçu expose devise, dates, taux, courbes, funding, modèles et réglages enregistrés. « Termes seulement » conserve les hypothèses courantes ; leur remplacement exige la portée complète. L'inclusion d'un panier transporte aussi ses corrélations. Les blocs de marché non enregistrés restent conservés. |
| M07-07 — champ vide devenu zéro | Vider rho ou eta conserve la dernière hypothèse et affiche une explication, sans appel de validation. Un zéro explicitement saisi reste admis lorsqu'il respecte les contrôles de surface existants. |
| M08-06 — précision de reprise | La reprise d'une recherche ne tronque plus ses inputs aux deux décimales affichées. `q = 2.001 %` et son premier bucket restent identiques ; le simple focus ne modifie pas la donnée. Une saisie utilisateur reste un changement explicite. |
| M11-06 — nombres non finis au booking | Infinity, -Infinity et NaN, y compris imbriqués, sont refusés avant l'empreinte et la sérialisation de la demande. Le refus 422 donne les chemins concernés et conserve BOOKING_REJECTED en JSON valide. Aucun Deal ni Product partiel n'est créé. |
| M13-04 — funding personnalisé restauré comme standard | Serveur et navigateur excluent toute surcharge de funding, même zéro ou une courbe vide explicites, ainsi qu'une référence de source personnalisée. Une option matérielle inconnue est également exclue. Un run personnalisé plus récent ne masque plus le dernier run standard compatible ; l'historique complet reste disponible. |

## Autorité et conservation

La nouvelle édition ne déverrouille pas un Product exécuté, un Deal ou les
termes reçus d'une banque. Les contrôles serveur C06 restent l'autorité, avec
droits de préparation et révision attendue. Une ancienne RFQ garde sa version.
Une configuration ne remplace pas un dossier Product déjà ouvert.

Si l'utilisateur continue à saisir pendant une sauvegarde de termes, la version
envoyée est conservée et les saisies plus récentes restent en copie de travail.
Si un autre dossier a été ouvert entre-temps, la réponse ne le remplace pas.
Les anciennes versions et leurs calculs restent consultables.

Les paramètres partiels sont des données de brouillon ; ils ne deviennent pas
des zéros ni des valeurs initiales du script. Le contrôle de complétude reste
obligatoire pour les étapes qui exigent un contrat qualifié. Les calculs et les
hypothèses de marché restent distincts des termes.

La reprise Product conserve aussi la précision des hypothèses et les buckets
de dividendes enregistrés, sans reconstruire implicitement une courbe géométrique.
Une modification explicite de rendement ou de décroissance retrouve le mode
de construction existant. Les choix de calendrier sont copiés : éditer la copie
de travail ne modifie pas l'objet Product reçu.

## Interactions avec les corrections précédentes

- **C01 :** accès aux produits, à l'historique, aux calculs et aux documents contrôlés côté serveur ; les droits bancaires privés et scopes RFQ restent exercés par les tests concernés.
- **C02 :** aucune modification des sessions, de l'identité d'installation ni des règles de nom canonique.
- **C03 :** identités juridiques et exception administrateur D01 passent toujours par leur workflow ; le contrôle des nombres non finis intervient après l'habilitation de booking.
- **C04 :** aucune voie d'amendement ni de limites n'est ajoutée. Les cas d'amendements économiques et leurs preuves restent validés ; la nouvelle copie de travail ne s'applique qu'aux termes non bookés.
- **C05 :** aucune régénération des calendriers bookés n'est introduite. Places d'observation, centres de règlement et règles de combinaison survivent aux conversions et reprises.
- **C06 :** version des termes, révision et Product ID restent distincts. Un refus de sauvegarde ne consomme pas implicitement une version, et un ancien calcul n'est pas attribué aux nouveaux termes.

## Validation

- **303 cas backend distincts validés sur 10 fichiers**, dont **47 nouveaux cas C07**. Une sélection de 301 cas passe ; un complément de 45 cas confirme 43 cas existants et deux cas supplémentaires. Ce total est une agrégation des cas distincts, pas une suite complète exécutée d'un bloc.
- **541 tests frontend sur 67 fichiers**, dont **47 nouveaux cas C07**, et build Vite réussi dans un répertoire temporaire. Le `frontend/dist` préexistant est conservé.
- Parsing invalide, structures de configuration invalides, préservation de session, conversion explicite, cellules partielles, précision et buckets, sauvegardes concurrentes à la saisie, navigation, pagination et refus de restauration de funding personnalisé sont exercés.
- Les 36 cas de booking non fini passent par l'authentification et les rôles réels des fixtures C01, en installation autonome et gérée. Clés étrangères actives dans ces fixtures. Aucun contrôle de permission neutralisé.
- Mesure isolée : **220 dossiers synthétiques**, page de **20**, environ **66 ms** pour la première page et environ **10 ko** de JSON ; seules les 20 projections demandées sont matérialisées. Pages bornées à 100 côté serveur, produits à 50 par défaut, calculs et historique à 20 dans la bibliothèque.
- Les données sont en mémoire ou en répertoires de test isolés. Aucun service réel n'a été lancé et aucune base métier n'a été utilisée comme fixture.

## Limites maintenues dans le registre

**M04-10 n'est pas qualifié pour la volumétrie de production.** La mesure sur
220 dossiers et la borne de matérialisation sont acquises localement ; le budget
de temps convenu pour les volumes et droits réels reste à définir. Le filtrage
d'habilitation précède la pagination visible et peut parcourir des identités
supplémentaires. Une grande profondeur de pagination n'est pas un accès constant.
Les blocs RFQ/documents d'un dossier restent des références du snapshot ; leur
historique exhaustif et les archives documentaires relèvent des travaux suivants.

**T11 reste partiel :** les champs de forme vides sont sécurisés ; les réponses
hors contexte et la qualification des calibrations restent dans C10/C17.
**T15 reste partiel :** la précision de reprise est validée ; compilation,
budgets et immutabilité des archives restent dans C09/C19/C20. Ces travaux ne
qualifient pas les modèles ni l'exactitude économique de leurs prix.

Pas de recette graphique manuelle, de migration des données historiques réelles
ni de qualification globale de production. Pas de commit ni de push.
