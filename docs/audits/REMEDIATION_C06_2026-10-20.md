# Lot 2 — C06 : versions Product et intégrité des transitions

**20 octobre 2026 — implémentation et validation locales, sans commit ni push.**

Les cinq constats C06 sont traités sur le périmètre ci-dessous. Le
[registre](remediation-lot-0-2026-10-20/REGISTER.json) conserve les dépendances,
les décisions déjà prises et les recettes transverses restantes. Les résultats,
cas exécutés, empreintes et limites figurent dans
[C06_VALIDATION.json](remediation-lot-0-2026-10-20/C06_VALIDATION.json).

## Résultats par constat

| Constat | Correction et résultat vérifié |
|---|---|
| M04-01 — ancienne RFQ faisant régresser Product | La synchronisation reprend le dossier courant et remplace uniquement sa projection RFQ. Une RFQ v1 reste v1 lorsque Product est v2 ; ses mises à jour de nom ou de marché ajoutent une révision cohérente sans rétrograder les termes ni recopier un ancien contexte. Une promotion de termes depuis cette RFQ reçoit un conflit 409, sans mutation persistée. |
| M04-02 — contexte perdu entre Product et RFQ | Le serveur hérite des champs omis depuis l'intention et le contexte conservés ; l'interface les préremplit. Cas vérifié : SELL, 2 M€, Client/mandat, format OTC, Swap et documentation ISDA restent vente, 2 M€ et même contexte dans la RFQ et Product. Les références héritées passent toujours la validation commerciale existante. |
| M04-03 — seconde vérité après booking | Le PATCH générique refuse toute soumission de `intent` ou `commercial` sur un Product exécuté. Nom et visibilité documentaire restent modifiables. Le Deal, son intention, son contexte et ses snapshots ne changent pas sous une modification cosmétique. Les rectifications passent par les workflows gouvernés existants. |
| M04-07 — version contractuelle absente ou inexistante | Les six tables durables vérifient à l'insertion et au changement de lien le couple Product/version, avec refus de NULL, 999 et d'une version appartenant uniquement à un autre Product. Une version historique valide du même Product reste admise. Le pointeur courant ne peut pas rétrograder ; les insertions de révisions et de calculs vérifient aussi leur version. |
| M09-01 — contournement par `pricing_params` | Liste explicite des seules hypothèses et options de calcul admises. Refus des dates, calendriers figés, paramètres contractuels, nominal, identité de sous-jacent et champs inconnus, même mélangés à une mise à jour cosmétique. Les taux, volatilités, dividendes, courbes, funding et options numériques autorisés restent modifiables sans déplacer les termes. |

## Autorité des transitions

La version des termes définit le contrat ; la révision assemble le dossier.
Lire une ancienne version pour une RFQ n'autorise pas à la promouvoir en version
courante. Le dépôt vérifie aussi que l'empreinte du candidat correspond à la
version stockée. Le contrôle optimiste de révision reste actif ; un changement
concurrent donne un conflit plutôt qu'une fusion implicite.

La projection RFQ, le contexte commercial et les termes ont des opérations
distinctes. Les mises à jour de cotation, d'exécution RFQ, de nom ou de marché
ne recopient plus automatiquement nominal, sens et Client dans Product.
Une modification explicite du contexte d'une RFQ courante peut être synchronisée
avant booking, sous les habilitations existantes. Une RFQ historique ou un
Product booké ne peut pas réécrire le contexte courant par ce chemin.

La création d'une RFQ à partir d'un Product exécuté est refusée : une autre
opération nécessite un nouveau dossier Product. Les anciennes RFQ restent
consultables et leurs annotations documentaires autorisées restent possibles.

Le handler de mise à jour RFQ effectue un rollback sur refus. Une requête mêlant
`params` et `pricing_params` est refusée pour éviter une priorité implicite entre
deux définitions. Le navigateur sépare désormais les hypothèses de sous-jacent
de ses champs d'identité. Les anciens clients qui envoient des termes ou des
clés inconnues dans `pricing_params` doivent respecter ce contrat ; ils
reçoivent une erreur explicite plutôt qu'une acceptation partielle silencieuse.

## Compatibilité et données historiques

La migration ajoute des protections, sans compléter ni réécrire les anciennes
lignes non qualifiées. Un test conserve une RFQ historique avec Product et
version NULL après migration : aucune version n'est inventée. Ces dossiers
doivent être requalifiés explicitement avant une transition qui exige un lien
canonique valide.

Les versions, révisions et calculs restent append-only ; l'exception de purge
des Products explicitement rattachés à un lot UAT reste en place. Les nouvelles
contraintes garantissent les références et le pointeur ; elles ne remplacent
pas les contrôles métier de booking ni la qualification économique des snapshots.
Aucun portefeuille réel n'a été analysé ou migré. L'installation des protections
en environnement réel et la revue des dossiers historiques restent à organiser.

## Interactions avec C01 à C05

- **C01 :** droits métier, scopes RFQ et confidentialité conservés. Les nouveaux cas HTTP passent par de vrais desks et l'authentification des fixtures, en installation autonome et gérée ; les contrôles ne sont pas neutralisés.
- **C02 :** initialisation et verrouillage de l'organisation gérée exercés en complément, dans un runtime de test isolé.
- **C03 :** références commerciales et identifiants juridiques continuent à être validés par leurs propriétaires. Aucun rapprochement par nom ne remplace un ID actif.
- **C04 :** un test applique réellement un amendement de 1 M€ à 1,4 M€, puis annote sa RFQ. Nominal, preuve crédit, exécution, lifecycle et snapshots du contrat restent ceux de l'amendement ; seule la projection RFQ ajoute une révision. Un changement de date de paiement est aussi appliqué sous les protections SQL : Product reste v2, la RFQ reste v1, et les deux snapshots conservent leurs dates respectives.
- **C05 :** termes et calendriers figés ne sont pas recalculés par une synchronisation RFQ. Les 46 cas calendaires, dont la transmission de la version rattachée au Deal, sont inclus dans la sélection.

## Validation et limites

- **307 cas backend distincts validés sur 14 fichiers**, dont **72 nouveaux cas C06**. La sélection principale a donné 300 succès et trois refus C01 sur d'anciennes fixtures de marché dépourvues de rôle. Leur création a été alignée sur les termes canoniques et un rôle habilité ; une relance de six cas donne six succès, incluant les trois corrections de fixtures et trois vérifications complémentaires. Un contrôle supplémentaire du changement de paiement sous protections SQL passe séparément. Aucun contrôle d'autorisation neutralisé. Ce total agrège les résultats ciblés ; ce n'est pas une suite complète exécutée en une seule passe.
- **494 tests frontend sur 65 fichiers**, dont **3 nouveaux cas C06**, puis **build Vite réussi en 11,81 s** dans un répertoire temporaire. Le `frontend/dist` existant est conservé.
- Clés étrangères et protections SQLite actives dans les tests de liens ; migration répétée ; refus d'écritures invalides sans consommation de version ; conservation d'une version historique valide ; héritage Product → RFQ ; synchronisation ancienne RFQ ; modification de marché ; booking et amendement gouverné.
- Rapports et preuves C01 à C05 conservés ; HEAD inchangé ; données de test en mémoire ou en répertoires isolés. Aucune base métier utilisée comme fixture et aucun service réel lancé.

**T02 reste partiel** : versions C06 qualifiées localement, retries, concurrence
des commandes et filiation C08 restant à qualifier. **T12 reste partiel** : les
tests RFQ réseau et publication ne clôturent pas toutes les révisions de quotes,
clôtures, réouvertures et rapprochements bilatéraux. **T13 n'est pas qualifié
dans son ensemble** : la garde des références versionnées ne prouve pas le
rejeu des archives ni l'identité écran/PDF des chantiers C18/C19.

Pas de recette graphique manuelle, de redémarrage d'installation réelle ni de
qualification globale en production. Les autres constats du registre restent
dans leurs chantiers respectifs.
