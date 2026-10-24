# C25 — Économie du roll et récupération

Livraison locale du **22 octobre 2026**, sans commit ni push. Les deux constats
M17-02 et M17-03 sont corrigés dans le comparateur des déclinaisons.
Branche `codex/hybrid-saas-foundation`, HEAD
`7dce3021a88feb4f0021ca3de8f3596277bc72a5`. Aucune base d’exploitation ouverte,
aucun serveur lancé et aucune migration de données exécutée.

## Résultat métier

| Constat | Comportement obtenu | Preuve ciblée |
|---|---|---|
| M17-02 — financement au modèle sans frais | Choix explicite : hypothèse modèle, modèle avec décote, ou bid observé saisi avec source et horodatage. Frais de sortie et marge/frais d’entrée alimentent le budget effectif. Prix modèle et écart modèle restent identifiés séparément. | Chacun des coûts diminue réellement la quantité et la récupération ; les prix modèle et les avenants restent inchangés. Source, date du bid, âge calendaire et date de calcul modèle sont conservés et affichés. |
| M17-03 — quantité présentée comme plafond | Quantité réinvestie, récupération moyenne, probabilité du pair d’origine et plafond démontré sont distincts. Aucun plafond égal à 100 % n’est inventé pour l’origine ou un avenant. | PAY 120 % : quantité ≈ 0,956635 et récupération ≈ 1,147961, avec probabilité du pair de 100 %. Un payoff dépendant du sous-jacent ne reçoit pas le maximum de l’échantillon comme plafond. |

## Convention de financement et unités

**D09 confirmée explicitement par Philippe le 22 octobre 2026.** La convention
ci-dessous est celle retenue dans sa réponse, implémentée et testée localement.

Les prix moteur sont des fractions du nominal ; les saisies de coûts et de
décote sont des **points de prix**, pas des points de base.

```text
sortie_brute = bid_saisi / 100
             ou prix_modele_origine - decote_points / 100

produit_net = sortie_brute - frais_sortie_points / 100
prix_entree = prix_modele_note_neuve + marge_et_frais_entree_points / 100
quantite = produit_net / prix_entree

recuperation_scenario = quantite × somme_des_flux_futurs_non_actualises
```

Les frais de sortie sont rapportés au nominal d’origine ; les frais d’entrée au
nouveau nominal. Les hypothèses saisies s’appliquent aux rolls de cette comparaison.
Des hypothèses différentes demandent une autre comparaison. Aucun coût n’est
injecté dans les taux ou le funding du moteur. Le funding C15/C18 reste dans
l’actualisation ; le bid et les frais interviennent après le pricing, dans le
budget disponible et la quantité achetée.

Le bid est saisi tout compris sur les droits cédés, avant les frais indiqués,
dans la même devise et la même convention de valeur que le prix modèle.
Pas de conversion FX, d’apport de cash ou de réinvestissement implicite de coupons
déjà payés. Les récupérations portent sur les flux futurs de la comparaison,
sans les actualiser ; elles ne constituent pas une performance historique totale.

Sans bid, la restitution porte **« Hypothèse modèle »**, sa décote éventuelle et
son horodatage de calcul. Un bid observé exige niveau, source et fuseau horaire.
Un bid postérieur à la date de valorisation est refusé pour le roll ; l’âge d’un
bid antérieur reste visible. Cette saisie est une information fournie pour
l’étude, pas une cotation récupérée ou une preuve d’exécution. Aucun fournisseur
externe supplémentaire n’est sollicité.

Un budget négatif, un prix d’entrée non positif, des valeurs non finies ou des
hypothèses contradictoires donnent un refus explicite. Un bid nul sans frais
finance une quantité nulle, avec récupération et probabilité du pair nulles.
Les autres lignes du comparateur restent disponibles lorsqu’un roll est refusé.

## Quantité, distribution et plafond

Le cas synthétique du test moteur utilise une origine PAY 1,147961 et une nouvelle
note PAY 1,2, à taux et funding nuls. Il donne :

| Grandeur | Résultat |
|---|---:|
| Quantité réinvestie | 0,9566341667, soit 95,66341667 % du nominal d’origine |
| Récupération déterministe | 1,147961, soit 114,7961 % du nominal d’origine |
| Probabilité de récupérer le pair d’origine | 100 % |
| Plafond démontré pour ce contrat fixe | 114,7961 % |

Ces valeurs reproduisent le contresens économique du cas audité, avec des données
synthétiques et le moteur réel. Elles ne décrivent pas le portefeuille.

La démonstration du plafond est volontairement bornée aux scripts constitués de
flux PAY littéraux à maturité, sans état, condition, paramètre ou autre date.
Les flux identiques restent distincts et leur somme est conservée. Hors de ce
domaine, le plafond est **« Non établi »**. Cela ne signifie pas que le produit
est nécessairement sans borne. La moyenne, la médiane et le maximum de
l’échantillon sont conservés séparément ; aucun de ces estimateurs ne démontre
un plafond contractuel.

## Interactions et conservation

- **C05/C18 :** dates et marchés passent par les chemins de pricing existants.
  Les tests à un et cinq ans vérifient calendrier, paiement et funding explicites.
  Le solveur de réinvestissement et ses probabilités conservent leur contexte
  commun ; aucune modification de leurs moteurs.
- **C19 :** la preuve signée conserve hypothèses de financement, provenance,
  contexte, prix et résultats. Le gel est manuel et le retry du même gel retrouve
  la même étude. Changer sigma, funding ou variante ne réécrit pas l’archive.
  Le PDF de proposition figée reste exporté par identifiant, sans nouveau pricing.
- **C07/C10 :** saisies conservées au changement d’onglet, y compris après une
  nouvelle comparaison reprise depuis une archive. Elles sont séparées par source.
  Une modification des coûts invalide le résultat courant et sa preuve ; les
  réponses antérieures sont ignorées. Les droits des sources et archives restent
  contrôlés ; aucun assouplissement des permissions.
- **C06/C08 :** la comparaison reste une étude. Elle ne crée ni Deal ni Product
  exécuté, ne modifie pas le booking et ne transfère pas automatiquement ses coûts
  dans un autre parcours commercial.

Les nouvelles restitutions portent `comparison_schema_version = 2`. La lecture
d’une ancienne étude conserve ses octets et ses prix/probabilités. Son ancien
champ « plafond » reste non qualifié à l’affichage, avec un message explicite ;
aucune borne nouvelle n’est reconstruite à partir de cet historique.

## Validation et limites

**182 cas backend distincts réussis dans huit fichiers**, dont **34 nouveaux cas
C25**. Les quatre fichiers de variantes du registre comptaient 138 succès avant
correction et restent validés. Leurs assertions qui assimilaient quantité et
plafond ont été corrigées ; les contrôles de prix, de probabilités, de calendrier
et de filiation sont conservés.

**712 tests frontend dans 80 fichiers réussis**, dont **15 nouveaux cas**, puis
compilation Vite dans un répertoire temporaire. Le `frontend/dist` initial est
conservé. Le backend complet n’a pas été lancé. La preuve de modification des
coûts/signatures, le gel avant changement de marché, la reprise des saisies,
la lecture des anciennes études et le maintien des instants avec fuseau sont
exercés sur des données synthétiques.

Les deux constats ont d’abord été reproduits avant correction. Les essais ont
également isolé puis corrigé une reprise d’archive qui restaurait les anciennes
saisies de travail et un horodatage de calcul qui perdait son décalage horaire.
Une attente de statut HTTP dans le nouveau test d’accès a été alignée sur le
contrat existant : 403 pour la source inaccessible, 404 pour une preuve d’un autre
auteur. Aucun contrôle de production n’a été modifié pour satisfaire ce test.

Les appels `requests` et `curl_cffi` sont bloqués dans les validations backend ;
aucune tentative bloquée n’a été enregistrée. Les bases sont isolées, et les
nouveaux tests activent les clés étrangères. Il n’y a pas de recette graphique
interactive, de qualification d’un bid fournisseur réel, de nouvelle qualification
générale des modèles ou de test déployé. T16 est validé sur ses composantes locales
annoncées ; la qualification graphique et déployée reste ouverte.

Preuves : [C25_VALIDATION.json](remediation-lot-0-2026-10-20/C25_VALIDATION.json).
Journaux, résultats JUnit, patch incrémental et contrôles de conservation :
`.runtime/diagnostic-acceptance/c25-2026-10-22`.

Le manifeste vérifie les sources initiales, les preuves précédentes et le dist.
HEAD et branche sont conservés. Il reste **C26 et le solde C27**.
