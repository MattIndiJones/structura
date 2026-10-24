# C09 — Compilation PayScript et qualification du payoff

Livraison locale du 21 octobre 2026. Les trois constats C09 sont corrigés et
validés sur le périmètre annoncé, sans commit ni push. Les travaux précédents
du répertoire sont conservés.

Le registre ne déclare aucun prérequis bloquant pour C09. Les interfaces C05,
C06 et C07 restent cependant exercées. C14 et C20 consomment cette correction ;
leur qualification complète reste à faire.

| Constat | Avant, reproduit localement | Comportement obtenu |
|---|---|---|
| M05-01 — instruction ignorée | `PAY 1` suivi d'un `PAY 0.08` trop indenté compile et paie 100 %. | Toute indentation inattendue du corps provoque une erreur avec le numéro de ligne. PAY, STOP, SET et ACCRUE sont couverts dans AT, IF, ELSE IF et ELSE. Un bloc vide et une tabulation d'indentation sont également refusés. Le script correctement indenté paie 108 % à taux nul ; STOP empêche le paiement ultérieur à maturité. |
| M05-08 — assurance excessive de l'assistant | Un simple `SET MEMO = 0`, jamais lu, suffit à afficher « Mémoire mise à jour après versement ». | Une affectation MEMO seule reste un indicateur structurel et produit un avertissement lorsque la mémoire est demandée. Le Phoenix mémoire reconnu ne reçoit une assurance limitée qu'après réussite du panel de sa source exacte. L'écran distingue compilation, exécution de contrôle, revue structurelle et qualification du payoff. |
| M08-03 — adaptateur insuffisamment qualifié | Transformer `COUPON * INDEX` en `COUPON * COUPON * INDEX` laisse Athena pris en charge. | L'empreinte approuvée et le panel versionné sont obligatoires pour chaque famille. Une modification économique refuse la famille, une nouvelle demande et la validation d'un candidat déjà créé. Un diagnostic dont le script compilé ou l'input ne correspond pas à la preuve devient indisponible. |

## Qualification du script

Le manifeste `APPROVED_SOURCES` fixe les empreintes des huit scripts pris en
charge. Il ne reconstruit pas automatiquement une approbation à partir du
catalogue courant. Les déclarations, calendriers et libellés gardent leurs
contrôles préexistants, puis la vérification de la source et le panel s'appliquent.

Le panel `C09-v1` exécute **552 trajectoires déterministes** : 78 pour chacun
des cinq payoffs à rappel, 54 pour chacun des trois payoffs à maturité unique.
Il compare les montants, les rangs des flux, les libellés, le remboursement
total et le rang d'arrêt à des formules contractuelles de référence indépendantes
du script exécuté. Les cas comprennent :

- rappel aux quatre rangs et suppression des flux suivants ;
- coupon manqué, rattrapage, remise à zéro et mémoire impayée à maturité ;
- niveaux juste sous, égaux et juste au-dessus des seuils ;
- rappel dégressif, nominal protégé, participation, cap et put avec levier ;
- pire sous-jacent changeant d'identité, coupons nuls et plusieurs valeurs du paramètre.

Un résultat non fini ou un échec du panel empêche la qualification. Le cache
est borné ; sa preuve est copiée avant restitution. L'empreinte normalise
uniquement CRLF/LF et les retours finaux : espaces, commentaires et instructions
restent matériels pour l'approbation. La résolution des calendriers conserve
l'identité de source ; les transformations résiduelles sans cette preuve ne
reçoivent pas implicitement cette identité.

La preuve contient la famille, l'empreinte de source, la version et l'empreinte
du panel, son nombre de cas et la portée du diagnostic. Les coupons et la
participation du capital garanti sont explicitement affines ; le booster reste
affine par morceaux et ses diagnostics restent locaux. La preuve accompagne
les capacités, la validation du candidat et les diagnostics du paramètre. Le
contexte de recherche existant conserve aussi cette information ; l'immutabilité
de l'archive demeure du ressort de C19.

Pour modifier un script approuvé : relire son payoff, adapter les formules et
trajectoires nécessaires, vérifier les hypothèses de son adaptateur, puis mettre
à jour explicitement son empreinte et la version du panel. Modifier uniquement
l'empreinte pour faire passer un script ne constitue pas une qualification.

## Interactions avec les corrections précédentes

- **C01 à C04 :** aucune route d'accès, identité, habilitation ou voie d'amendement supplémentaire. L'adoption conserve l'acquittement explicite des avertissements déjà en place.
- **C05 :** les calendriers sont toujours résolus par le moteur existant. Les places, conventions, stubs et calendriers bookés ne sont pas réécrits. Les tests des calendriers contractuels passent.
- **C06 :** les transitions et révisions Product gardent leurs contrôles serveur. La qualification d'une famille ne constitue pas une autorisation de modifier un contrat. Les tests Product passent.
- **C07 :** un refus de compilation reste un refus ; il ne devient pas une déclaration vide qui effacerait les saisies. Les tests de conservation, reprise, configurations et précision passent. L'adoption IA copie la preuve et conserve le script adopté ; une modification ultérieure reste signalée par `modified_after_adoption` et ne qualifie pas la nouvelle source.

T03 devient partiellement validé sur les dates/rangs C05, l'indentation et le
payoff mémoire C09. La chronologie C14, notamment plusieurs observations dans
un même pas et l'ordre des blocs, reste ouverte. T15 conserve les acquis C07
et ajoute le refus d'un payoff modifié ; les archives C19 et budgets C20 restent
ouverts. Aucun statut extérieur à ces trois constats et à ces deux recettes
transverses n'est clos par C09.

## Validation et preuves

- **845 cas backend distincts validés sur 19 fichiers, un cas ignoré**, dont 48 nouveaux cas C09. La sélection principale donne 844 succès et un cas ignoré en 153,91 s. Après ajout du contrôle des résultats non finis, un complément de 63 succès en 5,58 s reprend 62 cas et ajoute un cas. Le total distinct ne cumule pas les recouvrements.
- Le cas ignoré est le jeu paramétré des exemples LLM complémentaires, actuellement vide. Aucun appel à un modèle externe n'est utilisé comme preuve. Dix avertissements de dépréciation FastAPI `on_event` sont présents, sans échec.
- **546 tests frontend sur 68 fichiers**, dont 5 nouveaux cas C09, et build Vite réussi en 11,98 s. La sortie du build est temporaire ; le `frontend/dist` préexistant reste conservé.
- Les premières reproductions sont confirmées avant correction, puis rejouées après correction. Le comparateur du test booster utilise une tolérance de 1e-12 sur les montants, identique au panel, pour les écarts d'arrondi flottant.

La [preuve consolidée](remediation-lot-0-2026-10-20/C09_VALIDATION.json) relie
chaque critère aux tests, aux résultats avant/après, aux empreintes des sources
et aux journaux. Les journaux, rapports JUnit et le détail des 552 trajectoires
sont dans `.runtime/diagnostic-acceptance/c09-2026-10-21/`, un répertoire local
ignoré par Git. Les entrées et formules du panel ainsi que ses tests sont dans
le code source ; les empreintes et résumés du panel sont conservés dans la preuve.

## Limites de qualification

Le panel utilise une grille synthétique avec calendriers de référence explicites
et taux nul. Il qualifie les branches testées du payoff approuvé, sans certifier
les termes d'un produit particulier, la chronologie Monte-Carlo, la surveillance
continue, la convergence numérique ou le modèle de pricing. Un script hors
manifeste reste utilisable dans le workflow existant, avec une qualification
structurelle explicitement limitée ; il n'entre pas dans les adaptateurs Optimizer
approuvés par simple similitude.

Aucune suite backend complète, recette graphique manuelle, migration des données
métier, mise en production ou ouverture de service n'a été effectuée. T03/C14,
T15/C19/C20 et la qualification de production restent à traiter.
