# RFQ réseau — lot 4 : prise en charge et pricing bancaire privé

Date : 12/10/2026. Branche : `codex/rfq-network-lot-0`. Changements locaux, sans commit ni push.

## Périmètre de cette tranche

Une banque reçoit la demande persistante du lot 3, la prend en charge et ouvre les termes Product exacts dans le Pricer natif. Les calculs signés peuvent être conservés et retrouvés dans son dossier bancaire. Le demandeur ne reçoit aucun prix à ce stade.

La file de desk, la responsabilité, la réaffectation, l’ouverture dans le Pricer et la conservation privée sont codées. Les échanges de précision, le déclin et les contre-propositions du cadrage complet du lot 4 restent des compléments à développer. La validation humaine, le prix commercial et la publication relèvent du lot 5.

## Parcours BNP

1. **RFQ reçues · banque** : liste des demandes adressées aux desks habilités, avec demandeur, nominal, échéance, responsable et présence d’un calcul privé conservé.
2. **Ouvrir** : consulter le message exact et ses termes figés. La première lecture reste tracée séparément de la prise en charge.
3. **Prendre en charge** : créer une seule fois le Product interne de BNP et enregistrer le responsable. Un second clic du même responsable retrouve le dossier ; un autre collaborateur ne peut pas le prendre implicitement.
4. **Réaffecter** : sélectionner un membre actif du même desk disposant de `read`, `prepare` et `price`, avec motif. Le responsable ou un membre habilité `organize` effectue cette réaffectation. Une révision devenue obsolète est refusée. Le Product et ses calculs ne changent pas d’identité.
5. **Ouvrir dans le Pricer bancaire** : ouverture native du Product, onglet **Marché & Paramètres**. Script, paramètres effectifs, panier, dates et calendrier sont verrouillés ; les hypothèses et le modèle bancaire restent éditables.
6. **Pricer**, puis **Conserver ce calcul privé** : le moteur et la signature de reçu existants sont réutilisés. Le résultat daté est conservé dans les enregistrements de calcul Product.
7. **Revenir à la RFQ reçue** : revoir l’historique des prix théoriques conservés. À la réouverture, le dernier calcul restitue ses hypothèses privées.

Au premier calcul, aucun marché du demandeur n’est importé. Les contrôles natifs présentent leurs hypothèses initiales et doivent être vérifiés par le structureur. L’ouverture du Product ne déclenche aucun re-fetch externe ajouté par ce lot ; la réouverture utilise le calcul déjà en base. Le bouton explicite de rechargement du marché et les comportements natifs de changement de date restent ceux du Pricer.

## Product et définitions contractuelles

La table additive `rfq_bank_cases` relie un message reçu à un Product bancaire et à un responsable du desk. Le Product est créé par `stage_internal_product`, avec `data_origin="imported"` et `listed=False`. Il n’est ni un Deal ni une nouvelle demande envoyée à un tiers.

La définition transmise est validée par `ProductTerms`, sans remplacer ses valeurs. Son empreinte doit correspondre à la demande ; sa compatibilité avec le parseur et le calendrier courants est vérifiée. Une version de format/PayScript inconnue ou une définition inexploitable reste consultable, mais la prise en charge ne fabrique aucun produit de remplacement.

Le Product interne a sa référence et sa version de termes locale. L’identité commune, le tour, la version de termes du demandeur et le message restent dans la sollicitation liée. Les deux versions locales peuvent avoir des numéros différents ; la définition et l’empreinte contractuelles restent égales. Les quatre dates et les calendriers figés sont conservés exactement.

Le nominal vient de la demande. Le sens du Product bancaire prend la perspective opposée au demandeur : achat client implique vente banque. Aucun contexte CRM, calcul, marché, modèle ou Product complet du demandeur n’est copié.

Les API Product de composition de pricing et de conservation d’un reçu sont réutilisées. Le résultat théorique reste distinct d’un futur prix commercial. Aucune cotation `RfqQuote` n’est ajoutée chez le demandeur par cette prise en charge ou ce calcul.

## Droits et contrôles

| Action | Droit et contrôle |
| --- | --- |
| Lire la demande et voir le responsable | `read` sur le desk destinataire actif, dans la bonne organisation. |
| Prendre en charge | `prepare`, demande et tour actifs, délai non dépassé. |
| Réaffecter | `prepare` et être responsable ou disposer de `organize` sur ce desk ; cible habilitée. |
| Lire le Product et ses calculs privés | `price` sur le desk bancaire. Pas de dérogation par le rôle admin, même pour un ancien créateur. |
| Composer un nouveau pricing ou conserver un résultat | `price`, être le responsable courant, dossier actif et délai ouvert. |
| Modifier les termes reçus ou l’intention commerciale | Refus côté serveur, y compris via les API Product génériques. |

Le verrou d’écriture sur la sollicitation sérialise la prise en charge et la réaffectation, puis les habilitations sont relues. Les mutations disposent d’un audit. Le Product est créé et lié à son dossier dans la même transaction.

Les historiques restent lisibles aux membres habilités après remplacement du tour ou dépassement du délai ; les nouveaux calculs et leur conservation sont alors refusés. Une révocation du desk supprime l’accès au Product et aux calculs, même pour le créateur.

Les caches frontend du pricing, des Products et des RFQ sont vidés à la déconnexion. Le nettoyage invalide aussi les réponses de pricing en cours par le mécanisme de révision déjà présent. Les endpoints Product conservent leur contrôle d’accès indépendant du cache de l’interface.

## Manuel et masques

Le parcours RFQ manuel du demandeur reste disponible. La banque utilise les composants actuels du Pricer, `ProductContextBar`, `MarketParams`, Economics et les moteurs existants. Le bandeau bancaire explique le caractère privé et permet le retour au dossier reçu.

La liste bancaire et ses modales conservent le scroll interne. Les colonnes du Pricer sont bornées avec `min-height: 0` et leurs contenus défilent intérieurement, y compris avec le bandeau bancaire supplémentaire. Les nominaux et prix utilisent le formatage français. La compilation ne remplace pas une vérification visuelle de ces comportements.

## Vérifications

- Groupe backend ciblé : 39 tests réussis, 2 fixtures Product historiques sans organisation/desk à adapter. Ces 2 tests ont été corrigés uniquement dans leur contexte de test et repassent. Les 7 tests bancaires comprennent un pricing réel et la conservation de son reçu signé, les droits, le gel, la réaffectation, la révocation et une version non prise en charge. Aucune suite backend complète.
- `npm run build` réussi, avec tests frontend et compilation Vite. Les deux tests historiques de déconnexion sont conservés ; un scénario de nettoyage du pricing bancaire a été ajouté et les tests de déconnexion sont rejoués séparément.
- Recette HTTP authentifiée sur `tmp/rfq-lot4-uat/data/structura.db`, avec assertion du chemin de l’engine **avant** création des objets et contrôle de l’identité d’instance : envoi QA ClientTech → QA BNP, prise en charge, ouverture du Product, moteur natif, reçu signé conservé, réouverture, refus de lecture par le demandeur et refus d’une surcharge contractuelle dans les hypothèses.
- Dans cette recette fictive de remboursement de capital à maturité, le moteur donne **91,3537 %** avec les hypothèses explicites utilisées. Ce chiffre est une preuve de fonctionnement sur ce cas de test, pas une cotation BNP réelle.
- La recette navigateur reste bloquée par l’outil (`ERR_BLOCKED_BY_CLIENT`). Scroll réel, mobile et clavier restent à vérifier à l’écran. La base locale réelle n’a pas été utilisée pour cette recette.

Le transport entre installations, la publication et la confirmation de traitement restent dans les lots suivants. La qualification générale des exports et tâches longues de l’installation reste distincte du contrôle de ces endpoints bancaires.
