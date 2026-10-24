# C11 — Données de marché datées et couverture

Les sept constats C11 sont traités et validés localement. Philippe a confirmé
**3 jours calendaires maximum pour les cours EOD et le FX de reporting**, borne
incluse : J+3 accepté, J+4 exclu. Cette règle est versionnée et testée.
T04/T10 et la qualification production restent ouverts ; la finalité officielle
relève de C13. Travail autorisé avec modifications et tests ciblés, **sans commit ni push**.

## Résultat par constat

| Constat | Comportement obtenu | État |
|---|---|---|
| M03-02 — dividende inconnu remplacé par zéro | Le rendement absent est omis avec son diagnostic. La RFQ conserve sa saisie et affiche une alerte. Comparateur et proposition de réinvestissement refusent un pricing sans hypothèse explicite. Un zéro sourcé reste admissible. | Validé localement |
| M03-04 — prolongation illimitée d’un cours | Les reports sont bornés par une politique explicite ; dates sources, anciennetés et lacunes restent disponibles. Une interruption prolongée exclut le titre, y compris au milieu d’une série mono-sous-jacent. Aucun remplissage avant sa première observation. | Validé localement — seuil confirmé de 3 jours |
| M03-05 — FX ancien dans les agrégats | La cotation retourne date demandée, date effective, âge, taux brut, qualification et taux utilisable. Un taux non qualifié retourne `rate=null` et laisse l’exposition/limite incomplète. L’explain utilise la date de fin demandée. | Validé localement — seuil confirmé de 3 jours |
| M03-06 — deux volatilités réalisées | Voies datée et courante utilisent le même RMS des log-rendements, annualisé à 252, et le même échantillon commun. Corrélations contrôlées et conservées sans arrondi destructeur. Le comparateur réutilise le contrôle sur son échantillon de backtest complet. | Validé localement |
| M03-07 — historique partiel ambigu | `coverage`, manquants et motifs sont explicites. Le calcul du panier complet refuse ; la comparaison exploratoire peut réduire l’univers, conserve les exclusions et les affiche. Le démarrage commun tronqué est indiqué. | Validé localement |
| M03-08 — origine perdue au booking | Référence, source, méthode, date, diagnostic, surcharge et valeur moteur sont séparés. Les métadonnées traversent requête, calcul Product, réouverture, preuve signée et snapshot de booking. Les références restent masquées en mode démo. | Validé localement |
| M03-10 — cache administré différent du cache consommé | Les téléchargements alimentent un stock partagé brut/ajusté ; les consommateurs relisent également le stock AMC existant lorsque sa convention est connue. L’administration expose les deux bases et leur qualité ; un succès HTTP seul ne produit plus « OK ». Reprise locale démontrée sans fournisseur. | Validé localement — seuil confirmé de 3 jours |

## D03 — seuils confirmés et limites de cette décision

Philippe a répondu explicitement : « 3 jours calendaires pour les cours et le FX ».
`core/market_policy.py` applique la version `D03-C11-2026-10-21-3D` aux cours EOD
et au FX de reporting. L’ancienneté se mesure depuis la date réelle de la source
jusqu’à la date demandée : zéro jour est frais, un à trois jours constitue un
report admissible, quatre jours ou plus est hors politique. Une donnée manquante
ou future n’est pas utilisable. Chaque réponse expose la limite, l’âge et la version.

Les tests de frontière couvrent J+3/J+4 pour les deux usages. Ils utilisent
maintenant la règle réellement confirmée, sans seuil de cinq jours injecté.
Un contrôle conserve également le comportement fermé si la politique venait à
être non configurée. Les lacunes entre observations ne permettent pas de
recycler indéfiniment un ancien cours dans un historique.

D03 est **partiellement confirmée** dans le registre : ses seuils C11 sont acquis ;
les horaires, fuseaux, délais après clôture et conditions de finalité C13 restent
à préciser. La finalité demeure `UNVERIFIED_PROVIDER_BAR` : une clôture Yahoo datée
n’est pas certifiée officielle. La limite d’âge ne remplace pas le registre officiel.

## Données, conventions et conservation

- Les historiques ajustés servent aux statistiques ; les cours bruts servent au
  rejeu de payoff. Le nouveau stock utilise une clé par ticker et convention.
  Les cours AMC de Londres sont reconvertis dans l’unité du fournisseur avant
  réutilisation, sans mélanger GBP et pence.
- Le stock local est consulté avant le fournisseur. Les profils de dividendes
  datés sont conservés ; leur construction réutilise les séries locales avant
  de demander les événements de dividendes. Une panne ne transforme jamais
  un taux absent ou ancien en hypothèse qualifiée.
- Les cours ajustés ne sont pas concaténés entre deux époques d’ajustement : un
  rafraîchissement remplace leur lot. Une fenêtre plus large peut donc exiger un
  nouveau téléchargement si elle n’est plus couverte. Les cours bruts peuvent
  compléter leur historique. Les fichiers du nouveau stock sont remplacés
  atomiquement et les réponses mémoire sont copiées défensivement.
- La provenance transmise par l’interface est déclarative
  (`CLIENT_DECLARED_REFERENCE`). Le serveur recalcule surcharge et valeur
  effective depuis les entrées validées ; la preuve signée fige ces entrées.
  Elle ne constitue pas une attestation cryptographique du fournisseur.
  Une référence historique de dividende demeure une référence pour l’hypothèse
  forward, pas la connaissance des futurs dividendes.
- Les dossiers historiques sans métadonnées ne reçoivent aucune origine
  inventée. L’absence du nouveau champ n’altère pas la sérialisation des
  anciennes entrées. Aucun snapshot métier existant n’a été repris.

## Dépendances et limites de portée

**C03/C04 :** l’identité juridique et l’exception administrateur restent intactes.
Un FX non qualifié empêche de conclure à tort qu’une limite est respectée ; les
tests ciblés d’amendement passent. Aucune nouvelle permission n’est introduite.

**C06/C07 :** la source enrichit le contexte de calcul ; elle ne modifie pas les
termes contractuels. Référence et surcharge survivent aux passages Product/RFQ
et au booking. La reprise RFQ conserve les décimales utiles sans arrondi métier
caché. Le snapshot conserve exactement les nombres effectivement reçus par
le moteur, avec la précision flottante habituelle des conversions de pourcentages.

**C10 :** gardes de contexte Pricer conservées ; les chargements RFQ sont également
liés à la date, au panier, au dossier et à une révision. Une saisie modifiée puis
remise à sa valeur initiale invalide aussi l’ancienne réponse.

**T04 reste partiel** : les mécanismes C11 de fraîcheur, lacunes et reprise locale
complètent C03/C05 ; l’import atomique C12 et la recette transverse complète
restent ouverts. Le remplacement atomique du nouveau stock et sa copie défensive
ne clôturent pas C12 : l’ancien import AMC, ses collisions et les réponses
simultanées restent à vérifier dans ce chantier.

**T10 reste partiel** : l’exclusion d’un FX ancien et le maintien d’une limite
incomplète sont démontrés. Le scénario Production/UAT, les facteurs et métriques
C21, et le profil CRM C27 restent ouverts. Le lien conditionnel vers C24 demeure
limité aux restitutions converties. C13, C17 et C26 restent consommateurs du
contrat de données ; leurs qualifications propres ne sont pas acquises ici.

## Validation

- **235 cas backend distincts ciblés sur 16 fichiers**, dont **33 nouveaux cas C11**.
  Les échecs initiaux des nouveaux tests ont été corrigés et rejoués ; les rapports
  initiaux restent conservés. La dernière sélection passe avec la politique confirmée de trois jours, des données isolées et les appels HTTP externes bloqués ; aucune tentative externe n’a été nécessaire.
- **631 tests frontend sur 71 fichiers**, puis build Vite réussi en **11,03 s**.
  Les **16 nouveaux tests C11** couvrent provenance, surcharge, zéro connu,
  données absentes, refus de pricing, réponses tardives, administration et mode
  démo. Sortie de build dans un répertoire temporaire ; `frontend/dist` préservé.
- Une sélection initiale incluait aussi tout `test_amc_studies.py` : son test
  `test_public_registration_requires_explicit_enable` échoue sur une fixture de
  mot de passe de 11 caractères, incompatible avec la règle C02. Ce cas auth est
  hors C11, non corrigé et non compté dans les 235 cas de validation ciblée.
- Lecture des chemins avant correction et tests de régression après correction ;
  aucune nouvelle exécution avant correction n’est revendiquée.

Les [preuves consolidées](remediation-lot-0-2026-10-20/C11_VALIDATION.json)
détaillent les critères, résultats, empreintes et contrôles de conservation.
Journaux locaux : `.runtime/diagnostic-acceptance/c11-2026-10-21/`.
Les rapports et preuves C01 à C10 sont préservés.

Pas de suite backend complète, de recette graphique manuelle, de campagne IA,
de migration ou d’utilisation de la base métier. Aucun service démarré.
La disponibilité réelle de Yahoo, les fermetures propres à chaque place et
la qualification production restent à valider dans leurs périmètres dédiés.
