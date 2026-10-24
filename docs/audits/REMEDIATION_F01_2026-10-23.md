# F01 — inscription publique : fixture et contrôles d’authentification

**23 octobre 2026 — correction locale et tests ciblés, sans commit ni push.**

L’échec documenté est **reproduit puis résolu**, avec son identifiant de test
conservé. **21 cas ciblés distincts réussissent** : le cas initial, 14 nouveaux
cas d’inscription HTTP et 6 contrôles voisins de C01/C02. Aucun code applicatif
ni règle de sécurité n’a été modifié.

Le [registre courant](remediation-lot-0-2026-10-20/FAILURE_REGISTER.json) passe de
**1 à 0 cas ouverts**. Les sept groupes F01–F07 couvrent désormais les **121 cas
historiques résolus localement**. Les
[preuves F01](remediation-lot-0-2026-10-20/F01_VALIDATION.json) conservent les
identités, résultats, commandes et empreintes ; la référence figée de l’étape 1
reste inchangée.

## Diagnostic et correction

Le test `test_public_registration_requires_explicit_enable` construisait une
demande avec `password123`, soit **11 caractères**. Le validateur C02 impose
**12 caractères minimum et 72 octets UTF-8 maximum** : Pydantic levait donc une
`ValidationError` avant l’appel à `register`. Le test n’atteignait ni le contrôle
d’ouverture publique ni son assertion attendue de refus 403.

Dans [`test_amc_studies.py`](../../backend/tests/test_amc_studies.py), la demande
utilise désormais un mot de passe conforme. Elle est construite avant la zone
qui attend l’exception HTTP. Le test fixe explicitement le contexte autonome,
retire le drapeau d’ouverture et exige le motif précis « Inscription publique
désactivée ». Son identifiant est conservé ; il ne peut plus passer sur un autre
refus, notamment celui d’une installation gérée. La session `None` reste un
garde-fou : ce refus doit intervenir avant tout accès à la base.

Les nouvelles régressions sont regroupées dans
[`test_public_registration.py`](../../backend/tests/test_public_registration.py).
Elles utilisent le routeur d’authentification réel, sans remplacement de
`get_current_user`, et une base SQLite isolée avec clés étrangères actives.
La fixture ferme son client et son moteur. Aucun abaissement du minimum de
mot de passe, privilège supplémentaire ou changement du provisionnement
n’a été nécessaire.

## Critères vérifiés

| Contrôle | Résultat vérifié |
|---|---|
| Ouverture absente ou invalide | Drapeau absent, `0`, `false` ou valeur inconnue : options désactivées, requête valide refusée avec 403, aucun utilisateur ni organisation créé. |
| Ouverture explicitement autorisée | `1`, `true`, `yes`, dans le contexte de simulation prévu : réponse 201, organisation et utilisateur ordinaires persistés, mot de passe haché et JWT utilisable. |
| Sessions C02 | Le JWT d’inscription porte une identité de session et sa version ; une connexion par mot de passe fonctionne ; logout révoque ce seul jeton et conserve la seconde session. |
| Unicité | Identifiant déjà pris puis e-mail déjà pris refusés avec 400, sans utilisateur ou organisation supplémentaire. |
| Limite minimale | 11 caractères refusés avec 422 sans écriture ; 12 caractères acceptés et connexion réussie. |
| Limites maximales | 72 caractères ASCII ou 36 `é` acceptés ; 73 caractères ASCII ou 37 `é` refusés avec 422 sans écriture. |
| Installation gérée | Même avec les trois drapeaux de simulation/ouverture actifs, inscription publique refusée avec le motif d’admission par administrateur local ; comptes et organisation inchangés. |

Les six contrôles voisins réexercent les profils et limites d’administration
locale, les options de connexion gérée, la révocation persistante et limitée au
jeton courant, les mots de passe provisoires/changement personnel/reset, le refus
des anciens jetons antérieurs à C02 et l’audit de connexion sans secrets.

## Preuves et limites

| Artefact local | Résultat | Portée |
|---|---:|---|
| `baseline.xml` | 1 échec | Reproduction exacte de la `ValidationError` de F01. |
| `registration-final.xml` | **15 succès** | Identité initiale conservée et 14 nouveaux cas HTTP. |
| `dependencies-final.xml` | **6 succès** | Contrôles C01/C02 voisins, sans relance des autres domaines. |

Les artefacts se trouvent dans `.runtime/diagnostic-acceptance/f01-2026-10-23/`.
Les 21 identités finales sont distinctes ; `qualified-distinct.xml` est leur
union dérivée, pas une exécution supplémentaire. Les tests assainissent
`STRUCTURA_*` avant import de l’application et bloquent les appels HTTP externes.
Aucun appel externe n’a été tenté, aucune base métier ouverte, aucun service
démarré. Aucune suite backend globale ni build frontend n’a été lancé.

La résolution des 121 échecs historiques repose sur les preuves ciblées datées
de F01–F07. Elle ne signifie pas que toute la suite actuelle a été rejouée et
réussie, ni que les 27 chantiers ont reçu une qualification de production.
Recette graphique/transverse, adoption des anciens workspaces Admin et
qualification déployée restent distinctes et conservent leurs limites dans le
registre. Aucun nouvel arbitrage métier n’a été requis.

Les autres modifications locales, décisions, dépendances, critères, rapports
C01–C27 et preuves F02/F03/F04/F05/F06/F07 sont préservés. Aucun commit ni push.
