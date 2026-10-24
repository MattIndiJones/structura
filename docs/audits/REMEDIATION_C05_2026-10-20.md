# Lot 2 — C05 : calendriers contractuels et règlement

**20 octobre 2026 — implémentation et validation locales, sans commit ni push.**

Les huit constats C05 sont traités sur le périmètre ci-dessous. Le
[registre](remediation-lot-0-2026-10-20/REGISTER.json) conserve les dépendances et
les recettes transverses ouvertes. Les cas exécutés, résultats, empreintes et
limites figurent dans [C05_VALIDATION.json](remediation-lot-0-2026-10-20/C05_VALIDATION.json).

## Résultats par constat

| Constat | Correction et résultat vérifié |
|---|---|
| M02-01 — dérive mensuelle | Chaque date part de l'ancre originale, dans les deux sens et pour les sous-fréquences. Janvier au 31 retrouve mars au 31 après février ; cinq dates jusqu'au 31 mai, y compris en année bissextile. L'ajustement ouvré intervient ensuite. |
| M02-02 — règlement permissif | Entier strict de 0 à 30 jours ouvrés aux frontières API et PayScript partagées par Product, pricing et booking. Refus de −3, 1,8, 100, booléens, chaînes numériques et null explicite ; omission = 0. Le règlement est calculé après l'observation, sur ses centres propres. |
| M02-03 — repli silencieux | Suppression du calcul local limité aux week-ends. En cas d'échec serveur, la proposition automatique est retirée et une erreur demande une date vérifiée ou une nouvelle tentative. Les dates manuelles et figées sont conservées. TARGET, 02/04/2026 + 3 jours ouvrés = 09/04/2026. |
| M02-04 — calendriers confondus | Places d'observation et centres de règlement distincts, choix exposés dans Economics et conservés dans les termes, la RFQ et le Deal. NYSE fermé le 03/07/2026 alors que TARGET est ouvert : l'observation et le règlement ne suivent plus le même calendrier. |
| M02-09 — convention implicite différente | L'absence de convention signifie « aucun ajustement d'observation » en aperçu comme dans le résolveur contractuel. Les conventions sélectionnées donnent les mêmes dates et paiements dans les consommateurs testés. |
| M02-10 — stub long à seuil caché | Fusion systématique de la période irrégulière avec sa voisine, au début ou à la fin. Une frontière régulière ne fusionne pas. Cas du 15 janvier au 5 mars exercé, sans seuil de demi-période. |
| M05-06 — mauvaises étiquettes PARAM() | Le parser expose le calendrier nommé de chaque PARAM(). Economics prend les dates de ce calendrier ; coupons trimestriels et rappels annuels restent distincts. Sans association connue, aucune date n'est inventée. |
| M17-04 — maturité de scan incohérente | Demander 1 ou 5 ans sur un produit à calendrier 3 ans est refusé explicitement avant le scan. Reconstruire les termes dans le Pricer. Même sans changer T, un déplacement modifiant le nombre d'observations/relevés ou les rangs du snapshot est refusé. |

## Arbitrages D02 confirmés par Philippe

- **Combinaison choisie explicitement par produit**, sans imposer une règle globale aux paniers : `all_open` exige toutes les places ouvertes ; `any_open` en exige au moins une. Plusieurs calendriers sans règle sont refusés. Même choix distinct pour plusieurs centres de règlement.
- **Stub long à fusion systématique de la période irrégulière** avec la période régulière voisine, pour les nouveaux calendriers résolus.
- **Dates déjà figées conservées**, avec leurs paiements, rangs et relevés.

Les choix sont portés par chaque configuration CONSTAT dans les termes du
produit. Le catalogue serveur couvre les calendriers bancaires existants et
TARGET, NYSE, NASDAQ, XETR, JPX, HKEX, SGX, SIX. Il ne couvre pas toutes les places.
Les anciennes configurations sans sélection explicite conservent leur
correspondance bancaire par devise, signalée « Hérité » dans Economics. Une
sélection explicite vide, inconnue ou sans règle valide ne déclenche aucun repli.

Les fenêtres et relevés suivent les calendriers d'observation. Les paiements
suivent les centres de règlement, y compris à J+0 : une observation non ajustée
peut rester un samedi, mais son paiement attend l'ouverture du centre.
`any_open` ne fournit aucun cours pour une place fermée ; les contrôles de
fixing officiel et de couverture restent dans C11/C13.

## Conservation et interactions avec les autres correctifs

La restauration backend des calendriers figés conserve les dates existantes,
même lorsqu'elles contiennent l'ancienne dérive mensuelle. À la réouverture,
Economics et le tableau des calendriers lisent le snapshot Product ou Deal.
Ils ne demandent pas une nouvelle génération ; un snapshot absent est signalé
dans le tableau plutôt que remplacé par des dates recalculées. Une ancienne
réponse d'aperçu ne peut pas écraser un snapshot chargé entre-temps.

Le détail du Deal transmet au Pricer le calendrier de sa **version Product
rattachée**, même si le Product possède une version ultérieure. Les requêtes de
pricing et de vie résiduelle reprennent cette preuve. Si elle manque, ne peut
être lue dans le périmètre de l'utilisateur ou contredit le snapshot Deal, le
serveur signale son indisponibilité et le Pricer refuse le recalcul à partir des
seules anciennes configurations. Le dossier reste consultable ; sa
requalification explicite est nécessaire avant repricing.

Les nouvelles routes de catalogue et d'aperçu conservent le contrôle
`business.price` de C01. Les tests utilisent l'authentification et les sessions
réelles des fixtures, en installation autonome et gérée. Les permissions
Opérations/Contrôle ne sont pas élargies. Les contrôles de session et d'identité
C02 ainsi que les contrôles juridiques C03 sont inclus dans les non-régressions.

Le contrôle C04 des amendements de date de paiement reste en place : les choix
de calendrier ne contournent ni la limite, ni le besoin de mesure qualifiée
lorsque l'horizon change. Le réinvestissement reste une étude ; le refus de
redimensionnement ne crée aucun Deal ni amendement.

Les parcours ciblés conservent les politiques et dates dans Product, reçu de
pricing, RFQ avec desk réel et booking. Ces vérifications ne clôturent pas
l'ensemble de C06 sur les versions et transitions. Aucun calendrier historique
en base métier n'a été migré, réécrit ou régénéré.

## Validation et périmètre restant

- **454 cas backend distincts validés sur 18 fichiers**, dont **46 nouveaux cas C05**. La sélection initiale donne 450 succès et quatre refus dus à des fixtures Product sans identifiant juridique. Ajout de l'ID actif déjà présent dans leur référentiel de test, puis **4/4 succès** à la relance ciblée. Aucun contrôle C03 neutralisé. La suite backend complète n'a pas été lancée.
- **491 tests frontend sur 64 fichiers**, dont **16 nouveaux cas C05**, puis **build Vite réussi en 13,38 s** dans un répertoire temporaire. Le `frontend/dist` existant est conservé.
- Cas couverts : ancre et année bissextile, stubs, conventions, délais invalides, séparation de places/centres, deux règles de panier, fenêtres, Product/RFQ/booking, snapshots historiques, absence de repli en panne et réponses tardives sur les aperçus modifiés.
- Les anciens rapports et preuves C01 à C04 sont conservés ; HEAD inchangé. Tests en mémoire ou dans des répertoires de données isolés. Aucune donnée métier utilisée comme fixture.

**T03 reste partiel** : les dates et rangs C05 ne prouvent pas toute la chronologie
de paiement et le payoff mémoire de C09/C14. **T04 reste partiel** : le calendrier
ne qualifie pas la fraîcheur et l'atomicité des données C11/C12. **T16 reste
partiel** : refus de calendrier incohérent validé, financement, coûts,
récupération et PDF restant dans C18/C19/C25.

Pas de recette graphique manuelle, de redémarrage d'installations réelles, de
qualification globale des jours de fermeture, ni de qualification quantitative
en production. Les calendriers futurs dépendent du catalogue embarqué
`python-holidays` ; les dates contractuelles figées restent la référence.
