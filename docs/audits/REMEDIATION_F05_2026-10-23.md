# F05 — analyses Product : fixture et permissions

**23 octobre 2026 — correction locale, tests ciblés, sans commit ni push.**

Les **cinq échecs sont reproduits puis résolus**. Le fichier complet passe avec
**58 tests distincts**, sans échec, erreur ou skip. Les cinq identifiants initiaux
sont conservés. La correction concerne uniquement
[`test_product_analysis.py`](../../backend/tests/test_product_analysis.py) ; aucun
code applicatif ni contrôle d’accès n’est modifié.

Le [registre courant](remediation-lot-0-2026-10-20/FAILURE_REGISTER.json) passe de
**21 à 16 cas ouverts**, dans F01, F06 et F07. Les
[preuves F05](remediation-lot-0-2026-10-20/F05_VALIDATION.json) relient les identités,
commandes, empreintes, critères et résultats.

## Cause et périmètre

Les tests HTTP remplaçaient `get_current_user` par une fonction retournant
`object()`. Depuis C01, le routeur Pricing exige `get_current_pricer`, qui vérifie
la capacité `business.price`. Cet objet sans rôle reçoit donc correctement 403,
avant d’atteindre les assertions sur le contenu.

| Cas initial | Comportement attendu pour un acteur habilité | Reproduction |
|---|---:|---:|
| Aperçu sans appel au modèle | 200 | 403 |
| Résumé vide | 422 | 403 |
| Intention inconnue | 422 | 403 |
| Question libre vide | 422 | 403 |
| Liste des intentions | 200 | 403 |

Les routes concernées sont `GET /api/product/analyse/intentions`,
`POST /api/product/analyse/prompt` et `POST /api/product/analyse`.
Elles travaillent sur un résumé textuel envoyé pour un second avis. Elles ne
chargent ni ne modifient une version contractuelle Product. La cause est la fixture
d’authentification ; aucune incompatibilité de versions Product ou modification de
PayScript n’a été constatée sur ce périmètre.

## Correction et validations

La fixture des cinq cas crée une organisation et un utilisateur Front persistés
dans SQLite en mémoire, avec les clés étrangères activées. Le JWT traverse les
vrais contrôles de session et de permission. Seule la dépendance de base de données
est redirigée vers cette session isolée. Une application locale inclut le vrai
routeur Pricing ; elle ne démarre pas toute l’application métier ni ses services.
Le client et le moteur de base sont fermés à la sortie de la fixture.

Les **24 tests existants** passent après cette correction. **34 cas supplémentaires**
utilisent la fixture C01 existante, en mode autonome et en installation gérée :

| Contrôle | Cas nouveaux | Critère |
|---|---:|---|
| Authentification des trois routes | 12 | Token absent ou invalide : 401, avec challenge Bearer. |
| Profils secondaires sur les trois routes | 12 | Opérations et Contrôle : 403, sans appel au modèle. |
| Parcours autorisé Front / super utilisateur métier | 4 | Intentions accessibles ; aperçu sans appel ; envoi simulé unique ; messages, hash, version et provenance cohérents. |
| État courant de l’utilisateur après émission du JWT | 6 | Déclassement de rôle : 403 ; désactivation ou révocation des sessions : 401. |

Le test de bout en bout HTTP compare les messages réellement transmis au transport
LLM simulé avec ceux de l’aperçu et de la réponse. Il conserve le résumé exact,
le cadre système, le fournisseur, les modèles demandé/effectif, l’intention,
l’horodatage et l’identifiant de génération. Il ne prétend pas qualifier la réponse
d’un modèle réel.

| Dépendance | Résultat |
|---|---|
| C01 | Permissions réelles conservées ; Front et super utilisateur autorisés, profils secondaires refusés. |
| C02 | État courant et révocation relus après émission du token. |
| C09 | Tests existants du cadre textuel et de cohérence aperçu/envoi conservés. Aucun avis LLM ne devient une validation de prix ou de payoff. |
| C06 et autres correctifs | Sources applicatives, contrats, versions et preuves antérieures préservés. |

## Preuves et limites

Les artefacts sont dans `.runtime/diagnostic-acceptance/f05-2026-10-23/` :

- `baseline.xml` : **5 échecs**, exactement les identités du registre ;
- `analysis-first.xml` : **24 succès** après correction de la fixture ;
- `analysis-final.xml` : **58 succès distincts**, dont les cinq cas initiaux et
  34 nouveaux contrôles ; les passages précédents ne sont pas additionnés ;
- sélections, commandes, logs, garde réseau, diff incrémental et contrôle de
  préservation des fichiers et preuves antérieurs.

Aucun appel HTTP externe n’a été tenté ; aucun LLM réel n’a été sollicité. Un
avertissement Pydantic préexistant sur la métadonnée `repr=False` reste présent.
Seul le fichier de tests concerné a été exécuté. Aucune suite backend globale,
recette graphique, qualification quantitative ou qualification déployée n’a été
réalisée. Aucune base métier n’a été ouverte et aucun service n’a été démarré.

Le premier lanceur a produit le XML des cinq échecs, puis rencontré une erreur de
nettoyage Windows : le pool du moteur global conservait le fichier SQLite temporaire
ouvert. Le lanceur isolé dispose désormais ce moteur après pytest ; les deux
passages suivants se terminent normalement. La suppression récursive du répertoire
initial a ensuite été **refusée par le contrôle d’approbation automatique**
(`blocked by policy`). Aucun autre procédé de suppression n’a été tenté. Le dossier
isolé `C:/Users/phili/AppData/Local/Temp/structura-f05-runtime-qe5ilp3_` reste présent ;
aucun processus Python ou service de développement ne subsiste après validation.

## Solde documenté

| Groupe restant | Cas | Objet |
|---|---:|---|
| F01 | 1 | Fixture de mot de passe et inscription publique. |
| F06 | 14 | Chaîne CRM historique et fixtures associées. |
| F07 | 1 | Profil acteur du parcours relevés/lifecycle. |

Ces **16 cas n’ont pas été relancés dans F05**. La référence figée de l’étape 1
conserve ses 121 cas initiaux ; les preuves C01–C27 et F02/F03/F04 restent datées
et inchangées. Aucun nouvel arbitrage métier n’a été nécessaire. Aucun commit
ni push n’a été effectué.
