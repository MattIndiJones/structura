# RFQ réseau — lot 8 : recette et ouverture progressive

Clôture documentaire : 13/10/2026. Recette API et masques : 12/10 ; contrôle
final de l'heure bancaire : 13/10. Branche `codex/rfq-network-lot-0`, sans commit
ni push. **La tranche V1 est qualifiée sur installations fictives isolées.**
L'ouverture vers une véritable installation BNP reste à réaliser.

## Périmètre qualifié

Trois serveurs Structura natifs : ClientTech fictif, BNP fictif et SocGen fictif.
Chacun dispose de sa base, de son identité d'installation, de ses comptes et clés
de pricing. Les identifiants d'organisation, de desk et de relation diffèrent.
Les appels passent par les API authentifiées et le transport signé existant.
Les Product, reçus de pricing et moteurs sont ceux de l'application.

Les échanges entre serveurs ont utilisé HTTPS avec vérification du certificat et
du nom activée. Une autorité privée jetable a été fournie **au runtime de recette
uniquement**, via les clients de transport. La confiance TLS de production n'a
pas changé. Le client par défaut refuse ce certificat privé sans cette autorité.
Le navigateur a utilisé un proxy HTTP de boucle locale vers ces serveurs HTTPS ;
aucun interstitiel de certificat n'a été contourné.

Le produit de recette est l'Athena du catalogue existant : coupon cumulé de 8 %,
rappel annuel à 100 %, barrière européenne finale à 60 %, nominal 1 000 000 EUR,
fixing et valeur le 12/10/2026, maturité le 12/10/2029, paiement le 17/10/2029.
Le calendrier annuel et sa convention `none` sont explicitement renseignés.
Le sous-jacent est synthétique. Aucun téléchargement de marché n'est requis.

À termes identiques, deux calculs privés natifs donnent **98,7643 %** pour une
volatilité de 20 % et **92,2289 %** pour 30 %, avec taux 3 %, dividende 1 %, modèle
constant, 2 000 chemins, antithétiques et seed 42. Ces chiffres démontrent la
séparation des hypothèses ; ils ne qualifient pas la précision quantitative du modèle.

## Résultats obtenus

Les preuves contiennent **16 scénarios distincts réussis**. La qualification a
été réalisée par phases sur les mêmes bases persistantes, avec reprise de la
comparaison mixte après ajustements du script de recette. La phase de booking
déjà réussie n'a pas été rejouée lors de ces reprises.

| Scénario | Résultat mesuré |
| --- | --- |
| Appairage HTTPS et identifiants locaux différents | Trois installations, deux canaux reconnus, certificat contrôlé |
| Banque indisponible puis redémarrage des deux parties | Demande persistée puis reçue, sans ressaisie |
| Calcul bancaire privé sans publication | Aucun prix visible chez le demandeur |
| Validation puis publication | Prix commercial 98,50 % reçu automatiquement |
| Autre organisation et édition d'une quote réseau | Accès et modification refusés |
| Traitement demandé, confirmation absente | Booking refusé HTTP 409 |
| Accord confirmé avant expiration, booking après expiration | Deux appels simultanés renvoient le même Deal ; prix différent refusé HTTP 409 |
| Remise répétée et contenu/signature altérés | Boîte inchangée après doublon ; signature et contenu conflictuel refusés |
| Même Athena chez deux banques | Empreinte identique ; calculs privés différents |
| Préparation modifiée après validation | Ancienne décision de publication refusée ; nouvelle validation nécessaire |
| Droit du validateur révoqué | Action refusée ; réhabilitation explicite pour poursuivre |
| Seconde validation configurable et comparaison mixte | Auto-validation refusée chez SocGen ; collègue habilité valide ; deux prix réseau et un manuel visibles |
| Retrait avant acceptation | Retrait reçu et prix rendu inactif chez le demandeur |
| Canal suspendu | Préparation d'envoi refusée ; saisie manuelle disponible |
| Booking manuel avec réseau suspendu | Deal créé avec calcul signé, validité et contrôles habituels |
| Clôture du tour mixte | Travail bancaire fermé chez les deux banques |

La base de recette contient deux Deals : `CLIE-20261012-001` pour l'accord réseau
et `CLIE-20261012-002` pour le manuel. Une seule inscription d'exécution formelle
est présente pour le premier accord. Le second parcours conserve le fonctionnement
manuel sans imposer la nouvelle consignation. Une quote manuelle sans validité
connue a été refusée ; la recette a ensuite saisi son échéance explicitement.

## Contrôle des masques obtenu à l'écran

| Vue | Fenêtre | Page | Zone interne |
| --- | --- | --- | --- |
| Demandeur | 1 280 × 720 | Hauteur 720 | Liste et dossier : hauteur 591, scroll propre |
| Modale de demande de traitement | 760 × 600 | Hauteur 600 | Corps `overflow:auto`, hauteur 351, boutons visibles |
| Modale bancaire | 1 280 × 720 | Hauteur 720 | Corps hauteur 594, contenu 1 310 |
| Modale bancaire étroite | 760 × 600 | Hauteur 600 | Corps hauteur 474, contenu 1 366 |

Après défilement bancaire, le corps de modale est à 600 pixels et les positions
de scroll du document et du body restent à zéro. Le nominal est affiché avec
séparateurs `1 000 000 EUR`. Les masques existants sont conservés.

Le contrôle final du 13/10 conserve l'historique expiré sans réactiver l'offre.
Le calcul du 12/10 à 20:31 UTC s'affiche correctement **22:31** en Europe/Berlin,
comme la publication correspondante.

## Deux corrections issues de la recette

1. Un `CONSTAT()` recevant une liste ou une valeur simple provoquait un
   `AttributeError`. Le résolveur refuse maintenant cette forme avec une erreur
   explicite ; l'API RFQ répond 422 `CONTRACT_CALENDAR_INVALID`, avant création
   du Product et de la RFQ. Le langage et le moteur de payoff restent inchangés.
2. La projection du calcul privé bancaire exposait une heure UTC sans fuseau.
   Elle renvoie maintenant un instant UTC explicite, y compris pour les calculs
   déjà conservés. Les heures ne sont ni déplacées ni réécrites en base.

Vérification ciblée : **19 tests réussis** — 18 pour le refus de calendrier et la
référence PayScript, puis un pour calcul privé, confidentialité et instant UTC.
Aucune suite backend complète n'a été lancée. Aucun fichier Vue n'a été modifié
pour ce lot ; le frontend déjà construit a servi aux contrôles visuels.

## Livrables et preuves

- Script versionnable : `scripts/check_rfq_network_pilot.py`.
- [Procédure d'exploitation et de reprise](RFQ_NETWORK_OPERATIONS_2026-10-12.md).
- Preuves privées : `tmp/rfq-lot8/20261012-222512-8143dd/evidence.json`,
  `acceptance-summary.json`, `ui-scroll.json`, captures et journaux.
- Le répertoire réel `backend/data/` n'a pas été utilisé pour seeder ni tester.
  Une lecture SQLite en mode `ro` le 13/10 confirme une organisation locale
  nommée BNP et **zéro canal interinstallation**.
- Les serveurs, lanceurs et ports privés ont été vérifiés arrêtés au terme du
  contrôle final. Les preuves locales restent disponibles ; les clés fictives
  et journaux privés ne doivent pas être publiés en bloc.

Reproduction depuis la racine, avec l'environnement Python du projet et
`cryptography` disponible pour la PKI jetable :

```powershell
.venv/Scripts/python.exe scripts/check_rfq_network_pilot.py
```

`--checkpoint-seconds 900` ouvre une fenêtre de contrôle visuel bornée sur les
origines privées indiquées dans `browser_ready.json`. `browser_done` termine
cette fenêtre. `--resume-work <répertoire privé>` reprend uniquement une recette
déjà arrivée à la comparaison mixte, sur ses mêmes origines ; il n'est pas un
outil de reprise de production.

## Ce qui reste avant une vraie BNP

1. **Participant bancaire réel.** BNP doit disposer d'une installation Structura
   compatible, d'un administrateur d'organisation et d'un desk répondant convenu.
   La BNP créée localement dans le référentiel n'est pas cette installation.
2. **Accord et habilitations.** Reconnaître le même périmètre sur les deux côtés,
   mapper les contreparties juridiques, définir contacts, fraîcheur, fermeté et
   seconde validation. Autoriser la sollicitation ; le traitement exige aussi
   les accords locaux correspondants. La simple demande de prix peut précéder
   l'ouverture du traitement.
3. **Connectivité exploitable.** Obtenir les deux origines HTTPS accessibles,
   certificats et chaîne acceptée par le client réellement déployé, exposition
   du point de réception, règles réseau, horloges et responsables d'exploitation.
   La PKI privée de recette ne constitue pas cette configuration.
4. **Appairage bilatéral.** Échanger les identités d'installation, créer le canal
   demandeur, transmettre sa clé par le canal convenu, l'importer chez BNP,
   rapprocher les identités juridiques puis vérifier la reconnaissance mutuelle.
5. **Recette bilatérale puis ouverture.** Envoyer une demande fictive désignée,
   vérifier réception, prix publié, retour et reprise. Valider la procédure avec
   les responsables, puis ouvrir seulement la relation choisie aux vraies RFQ.

Il n'existe pas de connecteur natif vers les systèmes de pricing BNP dans cette
tranche. La banque price dans Structura avec ses hypothèses, puis publie
humainement. L'accord avant booking reste une preuve externe consignée.

## Compléments non qualifiés par ce lot

Les messages natifs d'acceptation/confirmation, le rapprochement explicite entre
manuel et réseau, les précisions/déclin/contre-propositions, la résolution gouvernée
des contestations, la rotation de clés et le rapprochement bilatéral des books
restent des travaux séparés. L'accusé perdu après commit et les révisions reçues
dans le désordre gardent la couverture ciblée du lot 6 ; ce rapport ne prétend
pas les avoir rejoués dans la recette HTTPS à trois serveurs. Aucun déploiement
externe, accord BNP réel ou résultat de système bancaire n'est revendiqué.
