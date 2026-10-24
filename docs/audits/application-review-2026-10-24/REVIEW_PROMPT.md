# Prompt complet de contre-revue métier et quantitative de Structura

Tu réalises une contre-revue indépendante de Structura, une application de structuration, pricing et gestion du cycle de vie de produits structurés.

Je te fournis un rapport détaillé de l’application, éventuellement accompagné d’inventaires, d’extraits de code et de preuves de tests historiques.

Ton objectif est d’évaluer sa validité métier et quantitative, d’identifier les vrais problèmes et de les distinguer des limites assumées, des choix de convention et des questions encore insuffisamment documentées.

Je veux une revue exigeante, argumentée et force de proposition. Une liste générique de bonnes pratiques ne suffit pas.


1. TON RÔLE

Agis comme une équipe de revue réunissant :

- un structureur senior de produits structurés ;
- un quant spécialiste des méthodes numériques et du Monte Carlo ;
- un spécialiste du risque de marché et de contrepartie ;
- un responsable des opérations et du cycle de vie ;
- un développeur senior capable de suivre les données jusqu’au calcul effectivement exécuté.

Raisonne d’abord sur le contrat, les flux, les risques et les sensibilités, puis sur l’implémentation.

L’examen technique doit servir à déterminer si l’outil calcule et conserve correctement les faits métier. Ne transforme pas cette mission en revue stylistique du code.


2. STATUT DES DOCUMENTS FOURNIS

Le rapport décrit une photographie locale de Structura au 24 octobre 2026 :

- branche : codex/hybrid-saas-foundation ;
- HEAD : 7dce3021a88feb4f0021ca3de8f3596277bc72a5 ;
- modifications locales non committées importantes.

Le HEAD seul ne décrit donc pas l’intégralité du code examiné. Utilise les manifestes et empreintes disponibles pour identifier les fichiers concernés.

Le rapport repose sur une inspection statique approfondie. Ses résultats de tests sont des preuves historiques datées ; ils ne constituent pas une nouvelle exécution de tous les tests sur la photographie décrite.

Considère le rapport comme un ensemble d’affirmations à examiner, et non comme un oracle.

Ne reprends pas mécaniquement ses conclusions ni ses priorités. Les points signalés sont des pistes de revue : tu dois vérifier leur raisonnement, leur portée et leurs conséquences.

Distingue systématiquement :

- ce qui est annoncé ;
- ce qui est décrit ;
- ce qui est visible dans les sources ;
- ce qui a été effectivement testé ;
- ce qui est qualifié pour un usage donné.

Une classe, un champ, un endpoint ou un nom de modèle ne prouve pas qu’une fonctionnalité est opérationnelle ou valide.


3. QUESTION CENTRALE

Pour chaque domaine, réponds à cette question :

« Quels résultats de Structura sont justifiés, pour quels contrats, avec quelles hypothèses, quelles données, quelles approximations et quelles garanties opérationnelles ? »

Évite les verdicts globaux « tout est valide » ou « tout est invalide ».

Une fonctionnalité peut être :

- correcte et utilisable dans un domaine défini ;
- correcte mais insuffisamment expliquée ;
- acceptable pour l’exploration seulement ;
- insuffisamment prouvée ;
- incorrecte dans une configuration précise ;
- inadaptée à un usage particulier, sans être défectueuse dans son usage annoncé.


4. CLASSIFICATION OBLIGATOIRE DES CONSTATS

Classe chaque point dans l’une des catégories suivantes.

A — Défaut établi

Le comportement contredit le contrat, une identité mathématique, une convention annoncée ou une exigence fonctionnelle applicable.

Il faut une démonstration, un chemin de code suffisamment complet ou une reproduction.

B — Défaut probable à reproduire

Le mécanisme paraît incorrect, mais une dépendance, un appelant, une donnée ou un résultat manque pour conclure.

Indique exactement ce qui permettrait de confirmer ou d’écarter le problème.

C — Limite assumée et cohérente

Le domaine est explicitement restreint et le comportement respecte cette restriction.

N’en fais pas artificiellement un bug. Vérifie néanmoins que la restriction est visible, appliquée et compatible avec l’usage proposé.

D — Limite mal annoncée ou mal appliquée

L’approximation peut être acceptable, mais l’interface, le document, l’API ou un consommateur laisse croire à une capacité plus large.

Identifie précisément l’écart entre capacité réelle et promesse.

E — Convention ou arbitrage métier

Plusieurs choix peuvent être légitimes. Évalue cohérence, visibilité, conservation et conséquences.

Ne remplace pas une convention explicite par ta préférence personnelle sans justification.

F — Preuve insuffisante

Tu ne peux pas conclure avec les éléments disponibles.

Une absence de preuve n’est pas automatiquement un défaut, et un résultat plausible n’est pas une preuve de validité.


5. MÉTHODE DE REVUE

Pour chaque sujet matériel :

1. Définis le résultat attendu à partir du contrat ou de la méthode annoncée.
2. Identifie les hypothèses qui conditionnent ce résultat.
3. Suis les inputs jusqu’au consommateur effectif.
4. Vérifie les unités, dates, signes et états transmis.
5. Examine l’oracle et le domaine des tests disponibles.
6. Recherche un contre-exemple minimal.
7. Conclus avec un niveau de certitude explicite.
8. Propose une correction ou une restriction uniquement si nécessaire.

Lorsque c’est pertinent, suis toute la chaîne :

interface → store → requête → schéma → résolution du contrat →
contexte de calcul → moteur → résultat → snapshot →
réouverture/MtM/risque/document.

Un champ correctement affiché mais ignoré par le moteur est un vrai problème. Un calcul correct mais réinterprété avec une autre unité ou un autre périmètre peut l’être aussi.


6. REVUE MÉTIER ET CONTRACTUELLE

Examine en priorité les éléments suivants.

6.1 Définition du produit

- Le payoff représente-t-il correctement les conditions contractuelles ?
- Les paramètres matériels sont-ils identifiables et explicables ?
- Les valeurs effectives sont-elles distinguées des défauts du script ?
- Le nominal, la devise, les actifs et leur ordre sont-ils conservés ?
- Les barrières européennes et américaines sont-elles distinguées ?
- Le coupon mémoire, les accumulations et les remboursements sont-ils exacts ?
- Le capital est-il payé une seule fois ?
- Le remboursement anticipé arrête-t-il réellement les flux suivants ?
- Les égalités aux seuils sont-elles traitées conformément au contrat ?

6.2 Calendriers

Distingue :

- date de trade ;
- fixing initial / strike ;
- date de valeur ;
- observations ;
- maturité ;
- paiements ;
- date de valorisation.

Vérifie :

- origine de l’axe temporel ;
- conventions de jours ouvrés ;
- places d’observation et centres de règlement ;
- combinaisons de calendriers ;
- stubs et fins de mois ;
- délais de paiement ;
- événements simultanés ;
- conservation du calendrier booké.

Ne considère pas une convention différente de ton habitude comme une erreur si elle est explicite et appliquée de façon cohérente.

6.3 Dossier et exécution

Reconstitue les responsabilités respectives de Product, calcul, Indicative, RFQ, quote, accord d’exécution et Deal.

Vérifie :

- identité et version des termes ;
- gel des faits envoyés et exécutés ;
- sélection de la bonne révision de quote ;
- fermeté et validité ;
- identité juridique de contrepartie ;
- cohérence du contexte commercial ;
- distinction entre confirmation, booking et règlement ;
- idempotence et absence de doubles inscriptions.

6.4 Cycle de vie et valorisation résiduelle

Vérifie :

- autorité des fixings officiels ;
- séparation entre observations indicatives et faits contractuels ;
- conservation des versions et preuves ;
- fenêtres de constatation complètes ;
- reprise de mémoire, extrema et autres états réalisés ;
- séparation entre flux payés, créances acquises et vie optionnelle restante ;
- traitement des produits rappelés ou échus ;
- correction après consommation d’un fixing ;
- invalidation des résultats courants sans effacement des archives.

Une échéance contractuelle ou une référence saisie ne prouve pas un virement bancaire.


7. REVUE QUANTITATIVE

7.1 Unités, signes et statistiques

Contrôle explicitement :

- fractions contre pourcentages ;
- points de prix contre points de base ;
- volatilité contre variance ;
- sensibilités par unité contre sensibilités par point ;
- prix actualisé contre somme des paiements ;
- TRI contre rendement calculé sur un horizon arbitraire ;
- quantile de payoff contre VaR monétaire ;
- mesure risque-neutre Q contre probabilité physique ;
- sens banque contre position économique du détenteur.

Respecte la convention particulière de Structura sur le sens des Deals : vérifie sa traduction dans les calculs avant de conclure à une inversion de risque.

7.2 Actualisation et forwards

Examine :

- taux sans risque dans le drift et l’actualisation ;
- funding exclu du drift ;
- capitalisation et interpolation des courbes ;
- date de paiement des flux ;
- rebasage à la date de valeur ;
- décalage des courbes en vie ;
- dividendes ;
- carry ;
- ajustement quanto ;
- cohérence des taux stochastiques et de leurs corrélations.

N’impose pas une direction universelle des sensibilités : leur signe dépend du payoff.

7.3 Modèles

Évalue séparément GBM, Heston, SABR, Local Vol et LSV.

Pour chacun :

- quelle dynamique est réellement simulée ?
- quel domaine de paramètres est autorisé ?
- quelles discrétisations sont utilisées ?
- quels planchers, écrêtages et extrapolations modifient la dynamique ?
- les martingales attendues sont-elles préservées ?
- quelles corrélations sont effectivement reproduites ?
- quels benchmarks indépendants sont pertinents ?
- la calibration concerne-t-elle le modèle complet ou une composante ?
- les limites sont-elles visibles pour l’utilisateur ?

Une formule Hagan n’est pas un oracle exact universel pour toute implémentation SABR. Une reproduction d’une ancienne boucle de code n’est pas une validation indépendante du modèle financier.

7.4 Monte Carlo

Distingue :

- bruit d’échantillonnage ;
- biais de discrétisation ;
- erreur de calibration ;
- erreur d’interpolation/extrapolation ;
- biais de simulation imbriquée ;
- erreur de méthode particulaire ;
- risque de modèle.

Vérifie :

- définition de N et du nombre effectif d’observations ;
- traitement statistique des antithétiques ;
- calcul des intervalles de confiance ;
- indépendance réellement justifiée ;
- Common Random Numbers dans les comparaisons ;
- stabilité selon seeds ;
- convergence en nombre de trajectoires et en pas de temps.

Pour LSV, examine spécifiquement les dépendances entre particules et la validité des intervalles publiés.

Un IC étroit n’est pas une preuve de faible erreur totale.

7.5 Barrières et fenêtres

Examine :

- grille de diffusion et dates contractuelles ;
- fenêtres demandées contre points effectivement utilisés ;
- extrema discrets contre continus ;
- exactitude marginale contre loi jointe ;
- approximation de dépendance dans les paniers ;
- qualification locale contre garantie générale ;
- comportement hors domaine supporté.

Une approximation explicitement admise peut être acceptable. Elle devient problématique si son erreur est incontrôlée pour l’usage visé ou si elle est annoncée comme exacte.

7.6 Greeks et solveurs

Vérifie :

- définition de chaque bump ;
- normalisation et unités ;
- centre de différence recalculé de façon cohérente ;
- conservation de l’état réalisé ;
- portée du vega Heston et LSV ;
- theta en présence d’événements ;
- bumps de corrélation admissibles ;
- bruit et arrondis.

Pour les solveurs, distingue convergence du paramètre et convergence du prix. Vérifie que le statut publié correspond au critère réellement satisfait.


8. DONNÉES DE MARCHÉ

Distingue observation, estimation historique, calibration, hypothèse et override.

Vérifie :

- prix nus contre prix ajustés ;
- splits et autres opérations sur titres ;
- unités monétaires, notamment GBX ;
- dividendes historiques contre hypothèses futures ;
- volatilité réalisée contre implicite ;
- alignement causal des paniers ;
- absence de backfill avant introduction ;
- dates demandées et effectives ;
- fraîcheur et reports ;
- réutilisation locale ;
- comportement en panne fournisseur ;
- provenance et conservation des inputs.

Distingue une série historique actuellement disponible d’une véritable archive point-in-time de ce qui était connu à une date passée.

Évalue séparément la donnée suffisante pour un pricing indicatif et celle nécessaire pour officialiser un événement contractuel.


9. RISQUE, OPTIMIZER ET ÉTUDES

9.1 Risque de portefeuille

Vérifie :

- univers et droits ;
- origines Production/UAT ;
- statuts à la date d’arrêté ;
- couvertures partielles ;
- FX manquant ;
- données périmées ;
- agrégation de sensibilités homogènes ;
- concentration par identité juridique ;
- limites sur la position résultante.

9.2 VaR et ES

Examine :

- scénarios historiques et paramétriques ;
- proxies de volatilité/corrélation ;
- horizons chevauchants ;
- ageing et événements pendant l’horizon ;
- cash ;
- FX et funding ;
- bruit de repricing ;
- quantiles et masse exacte de queue ;
- exclusions et scénarios incomplets.

Ne reproche pas à une mesure économique annoncée comme telle de ne pas être un calcul réglementaire. Vérifie en revanche que sa présentation ne suggère pas cette équivalence.

9.3 CCR

Examine :

- valeurs clean de crédit ;
- netting juridiquement admissible ;
- scénarios communs ;
- EE/EPE/PFE ;
- CVA, mesure des PD et recouvrement ;
- dates exactes des créances ;
- collatéral, lag, MTA, MPOR et IM ;
- dépendance défaut/exposition ;
- données manquantes et décisions de limites.

Le SA-CCR est annoncé absent : son absence n’est pas un bug du PFE économique. Une présentation qui assimilerait les deux serait un problème.

9.4 Optimizer

Vérifie :

- familles et objectifs effectivement supportés ;
- budget du payoff, frais et marge ;
- contraintes et paramètres résolus ;
- grille finie ;
- biais de sélection ;
- validation indépendante des candidats ;
- multiplicité statistique ;
- convergence temporelle ;
- budget et résultats partiels.

Ne confonds pas recherche de contrats, validation Monte Carlo et robustness autour d’une référence officielle.

9.5 AMC/FIFO

Examine :

- complétude du carnet ;
- positions initiales et synthétiques ;
- prix d’exécution et marks ;
- splits, FX, frais et dividendes ;
- rapprochement avec la NAV ;
- benchmark et bases brut/net ;
- inférence factorielle ;
- horizons chevauchants ;
- caractère ex post du timing ;
- proxies de Brinson ;
- pondérations et seuils des scores.

Un score descriptif n’est pas une preuve de compétence du gérant. Une couverture documentaire de 100 % n’est pas une confiance statistique de 100 %.


10. DOCUMENTS ET GOUVERNANCE

Examine les KID, EMT, notes de valorisation et propositions selon leur usage annoncé.

Distingue :

- analyse interne indicative ;
- brouillon commercial ;
- document figé ;
- document réglementaire qualifié.

Si le KID est explicitement présenté comme indicatif/non conforme, classe cette frontière correctement. Examine néanmoins les incohérences internes et la propagation des hypothèses depuis le Pricer.

Vérifie que les archives correspondent aux calculs sélectionnés et ne changent pas lors d’un nouveau téléchargement ou d’une évolution du moteur.

Les politiques configurables, comme la seconde signature des amendements, ne sont pas des défauts par principe. Évalue leur adéquation à l’organisation et la fidélité de leur présentation.

Si tu formules une conclusion réglementaire actuelle, appuie-la sur des sources officielles primaires et identifie la version applicable.


11. EXIGENCES DE PREUVE

Pour chaque problème significatif, fournis :

- l’usage concerné ;
- le comportement attendu ;
- les hypothèses ;
- le comportement observé ou déduit ;
- les références exactes disponibles ;
- le mécanisme de l’erreur ;
- son impact économique ou opérationnel ;
- les conditions de déclenchement ;
- une reproduction minimale ;
- un niveau de certitude ;
- une correction ou une restriction proportionnée.

Si tu n’as pas exécuté un test, écris « test proposé ».

Si tu n’as qu’un extrait, ne prétends pas avoir lu toute la chaîne.

Ne fabrique pas de numéros de ligne, de résultats ou de montants d’impact.

Un test qui reproduit la formule de l’implémentation sans oracle distinct ne prouve pas son exactitude.

Les succès de campagnes, HTTP 200, statuts COMPLETE et nombres de tests ne sont pas des certifications générales.

Si des sources manquent, demande les fichiers précis nécessaires à la conclusion et poursuis les autres analyses indépendantes.


12. LIVRABLE ATTENDU

Rédige en français un rapport structuré comprenant :

A. Appréciation générale

Explique ce que l’outil paraît pouvoir faire de façon justifiée, les principaux blocages et les conclusions impossibles avec les preuves disponibles.

B. Carte de validité

Pour chaque domaine, donne :

- usage ;
- capacités ;
- hypothèses et restrictions ;
- niveau de preuve ;
- décision d’usage ;
- validations encore nécessaires.

C. Registre des constats

Utilise un tableau avec :

ID | Domaine | Catégorie A–F | Gravité | Certitude |
Déclencheur | Attendu | Comportement/preuve |
Impact | Reproduction | Action proposée.

Réserve les gravités les plus élevées aux erreurs susceptibles de changer matériellement un prix, un flux, un risque, une décision d’exécution ou une vérité contractuelle.

D. Revue des limites assumées

Pour chaque limite importante, indique :

- si elle est financièrement cohérente ;
- si elle est correctement annoncée ;
- si elle est effectivement appliquée ;
- dans quels usages elle reste acceptable ;
- à partir de quel usage elle devient bloquante.

E. Plan de validation indépendant

Propose des cas déterministes et quantitatifs prioritaires, avec données synthétiques, oracle, unités, seeds, tolérances et critères d’acceptation.

Sépare correction du payoff, convergence numérique, calibration, données et workflow.

F. Priorités d’action

Distingue :

- corrections nécessaires ;
- restrictions d’usage ;
- améliorations de transparence ;
- validations complémentaires ;
- arbitrages métier ;
- évolutions facultatives.

G. Critique du rapport fourni

Identifie ses erreurs éventuelles, conclusions trop fortes, omissions et points insuffisamment étayés. Ne te limite pas à le reformuler.


13. CONSIGNE FINALE

Sois précis et contradictoire lorsque les preuves le justifient.

Reconnais les mécanismes solides et les restrictions raisonnables.

Ne cherche ni à défendre l’application ni à multiplier artificiellement les anomalies.

La qualité de ta revue se mesure à ta capacité à distinguer :

- une erreur réelle ;
- une approximation acceptable ;
- une convention cohérente ;
- une promesse excessive ;
- une preuve manquante.

Commence par reconstruire les invariants métier et quantitatifs, puis confronte-les aux éléments fournis.
