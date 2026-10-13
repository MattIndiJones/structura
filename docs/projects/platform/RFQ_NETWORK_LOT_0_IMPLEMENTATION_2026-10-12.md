# Lot 0 RFQ — prototype et raccordement aux objets existants

Date : 12/10/2026. Branche : `codex/rfq-network-lot-0`.

Statut : parcours interactif de référence et préparation de demande intégrée aux RFQ enregistrées. Le récapitulatif utilise les termes Product épinglés ; le calcul privé utilise les moteurs existants. Le réseau inter-organisations réel reste à réaliser. Aucun commit ni push effectué dans cette session.

## Raccordement livré dans la RFQ existante

Depuis le détail d'une RFQ liée à Product, **Préparer la demande partagée** ouvre `BaseModal`. Les termes doivent être enregistrés avant cette ouverture. L'utilisateur choisit un intitulé partagé distinct du nom interne, une limite de réponse et des fournisseurs du référentiel manuel existant. Ce référentiel n'est pas encore l'annuaire des partenaires autorisés par organisation.

Le serveur prépare un récapitulatif et une projection individuelle par fournisseur, sans créer de sollicitation, de cotation ni d'envoi. Il reprend exactement `product_id` et `product_terms_version` du dossier, même lorsqu'une autre RFQ a fait évoluer ce Product depuis. Le nominal et le sens sont ceux de la RFQ, sans reprendre l'intention commerciale d'un autre dossier utilisant le même Product.

Le contenu commun porte référence RFQ, intitulé partagé, organisation du dossier, type de demande, sens, nominal, devise, unité de prix et convention all-in, limite UTC, contexte juridique explicite, version et empreinte des termes. Les paramètres effectifs, script, panier, dates et calendriers sont issus de Product. La projection ne contient ni nom interne, ni rattachement CRM, ni hypothèses de marché, ni modèle, ni résultats privés, ni liste de concurrents. Les champs libres explicitement partagés restent sous le contrôle de l'utilisateur.

La préparation refuse une version RFQ périmée, une limite passée ou sans fuseau, des destinataires inconnus, inactifs ou répétés. Elle expose les données contractuelles manquantes et les dossiers clôturés. `delivery_available=false` matérialise l'absence de transport connecté. Les contrôles d'accès sont ceux des RFQ/Product actuels ; les droits d'organisation et de desk du lot 1 ne sont pas encore implémentés.

**Calculer avec le moteur actuel** appelle le calcul RFQ existant et affiche son résultat dans `RfqPricingPanel`, avec hypothèses et décomposition des flux. Le serveur compose les termes Product avec les hypothèses privées RFQ enregistrées ; il ne crée aucun modèle de pricing. L'enregistrement du prix vérifie l'empreinte des hypothèses afin de refuser un résultat devenu périmé pendant son calcul. Aucun re-fetch de marché n'est nécessaire pour ce parcours.

**Ouvrir dans le Pricer** ouvre les Economics du Product lié, conserve la version des termes de cette RFQ et ses hypothèses privées, sans charger automatiquement le dernier calcul de la bibliothèque Product. Les analyses du Pricer utilisent la composition contractuelle serveur RFQ et ne modifient pas les hypothèses enregistrées de la RFQ. Le passage historique vers le Deal reste celui du traitement d'une réponse retenue.

## Hauteur et défilement des masques

RFQ, analyse RFQ, Pricer et Booking reprennent le cadre existant à hauteur fixe de l'application. La liste et le détail RFQ défilent à l'intérieur de ce cadre ; sur mobile, la liste et le dossier sont accessibles séparément. Le prototype demandeur/banque utilise également des panneaux bornés, avec onglets sur écran étroit.

`BaseModal` borne désormais aussi les modales ordinaires à la hauteur disponible. En-tête et pied d'actions restent hors du contenu défilant ; le verrou de défilement du document se restaure à la fermeture, y compris avec plusieurs modales ouvertes. Dans la préparation RFQ, configuration, termes communs et contrôle du prix disposent de leurs défilements internes ; des onglets remplacent les deux colonnes sur mobile.

## Validation du raccordement

- Tests backend ciblés : `backend/tests/test_rfq_product_exchange.py`, `backend/tests/test_rfq.py` et `backend/tests/test_products.py` — **154 tests réussis**. La suite backend complète n'a pas été lancée.
- `npm run build` — **424 tests frontend réussis**, puis build Vite réussi. Couverture ajoutée : composition canonique, refus de résultat périmé, préparation sans mutation, version Product épinglée sans reprise de marchés et passage du Pricer par le contrat RFQ, verrou de scroll.
- Recette navigateur sur une base temporaire neuve : préparation BNP Paribas/Société Générale depuis une RFQ indicative fictive liée à Product ; nom interne absent du contenu partagé ; aucune sollicitation créée ; prix de **91,369 %** calculé avec le moteur existant sur `PAY 1`, taux 3 %, nominal EUR 1 M et 1 000 chemins. Ce prix est uniquement un résultat de recette sur hypothèses fictives.
- À 1280 × 960, 390 × 844 et 1280 × 560, la hauteur du document est égale à celle de l'écran. Le dépliage d'une projection augmente uniquement le contenu du panneau ; le pied de la modale reste visible. Captures `rfq-product-desktop.jpg` et `rfq-product-mobile.jpg` conservées parmi les artefacts locaux du chat.

## Prototype de référence du premier incrément

### Accès et objectif

Depuis RFQ Fournisseurs, ouvrir **Parcours réseau · prototype**. La route `/rfq/prototype-reseau` conserve le contrôle de connexion de l'application. La page indique explicitement sa nature de maquette et permet de recommencer l'exercice.

Cette première réalisation concrétise les écrans et les transitions du [lot 0](RFQ_NETWORK_LOT_0_SPECIFICATION_2026-10-12.md) avant les habilitations, les relations et le transport des lots suivants. La sélection d'une perspective bancaire dans la maquette simule un rôle ; elle ne constitue pas une habilitation réelle.

### Parcours livré

| Étape | Comportement |
| --- | --- |
| Préparation | Organisation fictive ClientTech, deux banques proposées, nominal et sens du demandeur, récapitulatif avant envoi. |
| Demande partagée | Modèle Athena du catalogue, script existant, paramètres effectifs avec unités, quatre dates, observations et paiements, convention, nominal, sens, version et empreinte SHA-256 des termes. Chaque banque reçoit une projection individuelle sans la liste des concurrents. |
| Réception bancaire | Demande adressée à la banque choisie, sens bancaire explicite, consultation du contenu partagé et déclin sans prix. |
| Préparation privée | Résultat de calcul fictif séparé du prix commercial, validité et conditions ; aucune transmission avant contrôle et publication. |
| Contrôle | Même préparateur dans le circuit simple ; soumission puis second validateur simulé lorsque la politique est activée. Une modification invalide le contrôle. |
| Publication | Cotation attribuée à la banque et à une révision, retour immédiat dans la comparaison du demandeur ; publication et réception sont des événements distincts. Répéter la publication d'une même préparation ne la duplique pas. |
| Manuel | Réponse saisie avec interlocuteur, prix, fermeté et validité déclarés, origine visible et historique distinct d'une publication bancaire. |
| Comparaison | Réponses mixtes, meilleur prix ferme actif selon achat ou vente, sélection explicite ; aucun déplacement automatique vers une révision. |
| Fermeté et retrait | Retrait motivé possible avant acceptation, y compris après sélection ; prix réservé après une acceptation valide, retrait ou révision ordinaires refusés ensuite. |
| Confirmation | Source bancaire ou téléphone déclaré, interlocuteur et référence d'exécution obligatoires ; suivi écrit distinct pour le téléphone. |
| Booking | Simulation locale uniquement, après confirmation, une inscription par accord ; expiration ultérieure de l'offre sans prorogation ni effacement de l'acceptation. |
| Historique | Événements de la perspective choisie ; calculs et contrôles privés absents de l'historique du demandeur. |

L'horloge de l'exercice est explicite et peut avancer de six minutes. La période de réponse, la validité proposée et la fraîcheur maximale du calcul fictif sont visibles. Aucune cotation ni hypothèse n'est obtenue auprès d'un fournisseur externe.

### Validation du 12 octobre

- `npm run build` depuis `frontend/` : réussi, **415 tests frontend**, dont **35 nouveaux tests** portant sur le prototype et ses écrans. Le build exécute la suite frontend prévue par le projet ; aucun pytest backend lancé.
- Recette navigateur isolée : envoi à deux banques, publication simple, publication après seconde validation, réponse manuelle et comparaison commune.
- Acceptation fictive à 14 h 45 sur une offre valable jusqu'à 14 h 50, puis accord téléphonique déclaré et booking simulé à 14 h 51 : accord conservé, aucune prolongation de l'offre.
- Formulaire de confirmation incomplet : motif affiché dans la modale, sans confirmation enregistrée.
- Publication et retrait indisponibles côté banque après acceptation et confirmation.
- Présentation vérifiée à 1280 et 390 pixels, avec défilement interne du comparatif sur écran étroit. Captures conservées dans les artefacts locaux du chat.
- Page et serveur de recette temporaires fermés après vérification ; aucun backend lancé ni base utilisateur modifiée.

### Limites et suite

Ce prototype ne dispose ni de propriété organisationnelle persistante, ni de droits métier réels, ni d'annuaire bilatéral, ni de boîte bancaire persistante ou de transport réseau. Les prix de calcul sont des valeurs fictives identifiées comme telles ; aucun moteur n'est appelé. Les confirmations et bookings sont simulés et ne constituent pas des preuves d'exécution réelles.

La demande et les réponses montrent le contenu proposé pour le parcours. Le contrat d'API définitif et sa validation serveur restent à réaliser. L'empreinte de termes du prototype ne remplace pas une signature ou un contrôle d'accès.

Les précisions, contre-propositions détaillées, nouveaux tours, reprises réseau, rapprochements téléphone/réseau et contestations économiques restent décrits dans la spécification, sans écrans complets dans ce premier incrément. Les rôles multiples de l'exercice ne démontrent pas l'isolation d'une application multi-organisations.

Le [lot 1](RFQ_NETWORK_LOT_1_SPECIFICATION_2026-10-12.md) appliquera propriété et droits aux nouveaux dossiers. Les anciens dossiers de test ne font l'objet d'aucune reprise ou migration. Les étapes suivantes suivent le [plan de réalisation](RFQ_NETWORK_ACTION_PLAN_2026-10-12.md).

### Fichiers

- `frontend/src/views/RfqNetworkPrototypeView.vue` : maquettes demandeur et banque.
- `frontend/src/utils/rfqNetworkPrototype.js` : état fictif, projections et transitions locales.
- `frontend/src/utils/rfqNetworkPrototype.test.js` et `frontend/src/views/RfqNetworkPrototypeView.test.js` : règles métier et rendu des perspectives.
- `frontend/src/router/index.js` et `frontend/src/views/RfqView.vue` : route authentifiée et accès depuis les RFQ.

Les autres parcours RFQ, pricing et booking conservent leur fonctionnement. Le module de prototype ne doit pas être utilisé comme autorité d'exécution en production.

## Fichiers du raccordement natif

- `backend/app/api/rfq.py` et `backend/app/api/products.py` : projection en lecture seule, composition des entrées de calcul, contrôle d'empreinte et chargement de la version Product demandée.
- `frontend/src/components/RfqExchangePanel.vue`, `frontend/src/views/RfqView.vue`, `frontend/src/views/PricerView.vue` : masque de préparation, prix privé et reprise des Economics.
- `frontend/src/stores/rfq.js`, `frontend/src/stores/products.js`, `frontend/src/stores/pricing.js` : parcours RFQ/Product/moteur canonique.
- `frontend/src/components/ui/BaseModal.vue`, `frontend/src/composables/useDocumentScrollLock.js` et `frontend/src/router/index.js` : défilement interne et hauteur bornée.
