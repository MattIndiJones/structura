# Lot 1 — C03 : identifiants juridiques et gouvernance des référentiels

**20 octobre 2026 — implémentation locale, sans commit ni push.**

Les neuf constats de C03 ont reçu un correctif et une validation ciblée. Le
[registre](remediation-lot-0-2026-10-20/REGISTER.json) conserve les autres chantiers
ouverts. Les commandes, résultats et empreintes sont regroupés dans
[C03_VALIDATION.json](remediation-lot-0-2026-10-20/C03_VALIDATION.json).
Le complément D01 est détaillé dans
[C03_D01_VALIDATION.json](remediation-lot-0-2026-10-20/C03_D01_VALIDATION.json).

## D01 — décision confirmée et exception administrateur

Philippe a confirmé le 20/10/2026 : **« Prévoir une exception administrateur
explicite, motivée et auditée »**. L’identifiant local de contrepartie actif reste
la règle générale. Un espace final ne modifie ni la banque identifiée ni ses limites.

Pour un **booking direct hors référentiel**, l’administrateur métier peut cocher
l’exception, saisir le nom juridique et un motif de 10 à 2 000 caractères, puis
confirmer explicitement le booking. Ce geste est disponible pour
`organization_admin` dans son organisation et pour l’administrateur d’un workspace
autonome. Front, Opérations, Contrôle et administrateur de plateforme ne peuvent
pas s’attribuer cette autorisation dans la requête.

Le serveur refuse cette exception si un identifiant ou un netting set est fourni,
si le nom correspond à une banque connue, même inactive (comparaison normalisée
sur casse, espaces et caractères Unicode), ou si le booking référence une RFQ ou
un accord de traitement. Une RFQ conserve son parcours de qualification explicite
de la banque ; l’exception ne remplace pas l’identité figée sur une cotation ou
un accord. Prix, reçu signé, termes Product et contrôles économiques restent requis.

Le contrôle CCR est marqué **non évalué**, sans résultat de crédit favorable.
Le Deal conserve un ID juridique nul et une attestation figée : auteur, rôle,
organisation, horodatage, nom, motif, nominal, devise et empreinte de la requête.
L’attestation entre dans le snapshot contractuel et la projection Product.
L’événement `BOOKING_LEGAL_IDENTITY_EXCEPTION_APPROVED` est écrit dans la même
transaction que le booking ; un échec d’écriture d’audit annule le Deal et le Product.
Les refus métier suivent l’audit de refus du booking existant.

L’écran Pricer et la liste Booking signalent le dossier à qualifier et le crédit
non évalué. L’exception est remise à zéro lors d’un changement d’utilisateur,
de Product, de RFQ, de mode note ou de droits. Elle ne se reconduit pas sur un autre
trade. La régularisation utilise l’amendement juridique gouverné : le contrôle
crédit destination doit réussir et le snapshot initial conserve l’exception.

La détection des alias commerciaux ou de noms volontairement différents ne
constitue pas une certification d’identité juridique. L’exception engage une
attestation de l’administrateur ; le suivi consolidé des dossiers non qualifiés
et de leur exposition reste à compléter dans C04/C21. Aucun ancien deal ne reçoit
d’autorisation reconstruite au cours de la migration additive.

## Correctifs et critères couverts

| Constat | Comportement obtenu et preuve ciblée |
|---|---|
| M02-05 — sélection du sous-jacent | Pricer et RFQ partagent la sélection ticker/libellé/devise. Un alias utilisé dans le script est conservé et affiché ; une devise surchargée est signalée. Un catalogue contradictoire ne produit aucune sélection partielle. Tests frontend du catalogue et build des consommateurs. |
| M02-06 — lien explicite invalide | Un lien fournisseur vers une banque inactive ou absente ne retombe pas sur une autre banque homonyme. Le générateur UAT applique également cette règle. Test de non-substitution. |
| M02-08 — cotations dépendantes des libellés | Les nouvelles cotations figent l'identifiant fournisseur, l'identifiant juridique et le nom juridique. Renommer ou réaffecter le fournisseur ne réattribue pas son historique ; une nouvelle cotation utilise son nouveau lien. Le last look conserve l'identité de son parent. |
| M02-11 — métadonnées permissives | Libellés/groupes vides, devise inconnue et limite négative ou non finie refusés. Devise et type d'un ticker sont communs à ses groupes et modifiés ensemble avec audit. Les métadonnées absentes restent « À qualifier ». |
| M02-12 — gouvernance incomplète | Motif obligatoire, auteur et état avant/après conservés pour les créations, modifications et désactivations des trois catalogues. Le seed initialise une seule fois ou adopte le catalogue existant. Déplacement, désactivation et retrait de toutes les entrées ne sont pas annulés au redémarrage. |
| M02-13 — groupe local dépendant du réseau | Un ticker local connu réutilise ses métadonnées, y compris son libellé si omis. La recherche UI privilégie les entrées locales. La revalidation externe est une action distincte, auditée, sans application automatique de son résultat. Test avec l'appel externe rendu impossible. |
| M10-02 — rapprochement réseau par nom exact | Publication et réception figent les identifiants **locaux** issus du mapping bilatéral. Le traitement et le CCR lisent cette identité, indépendamment du libellé juridique publié par la banque. Une identité inactive ou un mapping insuffisant empêche un nouveau traitement. |
| M11-01 — limites évitables par libellé | Le formulaire, la revue Opérations, le générateur et l'adaptateur de simulation transmettent l'identifiant. ID actif ou exception administrateur D01 explicite pour un booking direct hors référentiel. Refus par défaut, limites connues préservées, crédit non évalué affiché, attestation et audit transactionnels testés. |
| M11-03 — ancienne banque conservée après amendement | L'amendement juridique modifie ensemble ID, nom et rattachement de netting compatible, puis la projection Product. Le contrôle CCR destination précède les mutations contractuelles. Les snapshots antérieurs restent inchangés ; un refus réel de limite ne modifie ni Deal, ni Product, ni version. |

## Identités et historique

Le fournisseur est un canal de cotation, distinct de la contrepartie juridique.
Le rapprochement par nom identique n'est encore utilisé que lors de la création
d'une nouvelle cotation auprès d'un fournisseur sans lien explicite et sans
ambiguïté. Cette décision est immédiatement figée par ID. Un lien explicite
invalide n'est jamais remplacé par ce rapprochement.

Les anciennes cotations sans identité figée restent lisibles, mais ne reçoivent
aucune identité reconstruite depuis le catalogue actuel. Leur utilisation pour
le traitement/CCR/booking exige une qualification explicite, motivée et auditée.
Le parcours manuel expose ce geste dans la RFQ. Une banque déjà figée ne peut
pas être remplacée sur la même cotation. La migration additive conserve les
anciennes cotations en état « À qualifier », y compris après une seconde exécution.

La confirmation conserve son snapshot et sa banque d'origine si un libellé du
catalogue change. Une nouvelle relation ou un autre mapping ne réécrit pas un
accord déjà confirmé. Les contrôles de version et d'éligibilité du traitement
restent en place.

## Gouvernance et métadonnées

Le périmètre gouverné est constitué des sous-jacents, contreparties et fournisseurs
RFQ. Leur suppression API devient une désactivation afin de préserver les IDs,
les contacts et les liens historiques. Les opérations d'administration requièrent
un motif de 3 à 500 caractères, conservé dans l'audit.

À son premier démarrage après cette livraison, un catalogue non vide est adopté
tel quel. Aucune correction de ticker, inférence supplémentaire de type, restauration
de groupe ou remise à zéro de mot de passe n'est appliquée. En particulier, une
ancienne entrée AXA erronée doit être qualifiée explicitement. Une base neuve
reçoit le catalogue initial ; ses initialisations suivantes sont marquées et ne
réinsèrent plus les suppressions. Les nouveaux ajouts au catalogue standard devront
passer par une évolution de référentiel explicite.

Les devises de cotation appartiennent à une liste projet explicite, distincte des
calendriers de règlement disponibles. Ce contrôle ne certifie ni l'existence du
fixing, ni la fraîcheur d'un cours, ni la qualification économique d'un modèle.
Un champ absent n'est pas remplacé silencieusement par EUR. Une revalidation externe
renvoie sa source et son diagnostic ; une correction demeure un geste administrateur.

Le cache frontend conserve sa référence réactive et vérifie son âge à chaque
chargement : il est réutilisé pendant 30 secondes au maximum avant une nouvelle
demande. L'administration force son rafraîchissement ;
la déconnexion le vide. Les réponses d'une ancienne session sont écartées. Un
échec de rafraîchissement retire le catalogue périmé au lieu de le présenter comme
actuel. Les contrats et paramètres déjà conservés ne sont pas réécrits par ce cache.

## Contrats API et amendement juridique

- `DealCreate.counterparty_id` devient nécessaire pour un booking ordinaire ;
  `contrepartie` reste le libellé descriptif concordant. Les clients doivent envoyer
  l'ID de la liste des contreparties actives.
- Pour l’exception D01, `counterparty_id=null`, `ccr_netting_set_id=null`,
  `contrepartie` contient le nom juridique et `legal_identity_exception={"reason":"…"}`.
  L’objet n’accepte aucun champ d’auteur, de rôle ou d’approbation fourni par le client.
  La réponse et le contrat exposent l’attestation sous `legal_identity_exception` ;
  son `credit_status=NOT_ASSESSED` décrit le contrôle **au booking**, y compris après
  une régularisation ultérieure. Le rattachement courant est donné par `counterparty_id`.
- Les créations/modifications des trois référentiels et les requêtes de
  désactivation portent un `reason` explicite.
- La qualification d'une ancienne cotation porte `counterparty_id` et
  `identity_reason`. Les gestes refusés ne changent pas sa banque d'origine.
- Pour `field_name="contrepartie"`, `new_value` est un objet contenant
  `counterparty_id` et, si nécessaire, le nouveau `ccr_netting_set_id`. Un ancien
  set de la banque source n'est pas transféré à la destination : en l'absence de
  nouveau set explicite, la destination est traitée sans netting. Le résultat
  normalisé est visible dès l'approbation. Une destination identique est refusée
  comme absence de transfert juridique.

## Interactions avec les chantiers suivants

| Chantier ou scénario | Interface sécurisée ici | Travail restant |
|---|---|---|
| C01/C02 | Permissions et isolation préservées ; cache vidé à la déconnexion ; contrôle d'identité avant migration revalidé | Recette graphique/transverse complète |
| C04 / T05 | Identité Deal/Product stable, exception D01 visible et contrôle CCR destination avant transfert/régularisation | Concentration encore calculée par libellé dans certains consommateurs, suivi consolidé des dossiers hors référentiel, hausse du nominal et autres amendements économiques |
| C11 / T04 | Métadonnées locales réutilisées et absences explicites | Fraîcheur, couverture et provenance complète des observations de marché |
| C21 / T05 | Garde CCR existante utilisée avec les IDs ; vrais tests de limites nominales configurées | Qualification numérique PFE/CVA et leurs effets sur les décisions |
| C06/C08/C23 / T12 | Identité locale figée dans les cotations et accords | Qualification complète des versions, répétitions de commandes et clôtures bilatérales |
| C19 | Migration additive sans invention d'identité historique | Reprise des anciennes preuves et formats d'archives, sans qualification automatique |

T04, T05 et T12 sont donc **partiellement validés sur le périmètre C03**. Leur
clôture exige les autres chantiers indiqués dans le registre.

## Validation et conditions de livraison

La livraison initiale avant l’arbitrage D01 a validé **189 tests backend distincts**,
dont le groupe consolidé de 183 tests,
la migration de cotations historiques et cinq cas de migration/identité C02.
Elle comptait **461 tests frontend sur 60 fichiers** et un build Vite réussi.

Le complément D01 valide **93 tests backend distincts** : 18 cas dédiés aux
exceptions, permissions HTTP réelles, refus, audit transactionnel, migration et
régularisation, ainsi que 75 régressions ciblées RFQ/CCR/référentiels/permissions.
Le groupe de 93 a d’abord donné 92 succès et une assertion de code d’erreur à
adapter ; le fichier des 18 cas a ensuite passé intégralement. Les corrections
intermédiaires d’assertions sont conservées dans les journaux, hors preuves positives.
**470 tests frontend sur 61 fichiers** et le build Vite passent en sortie
temporaire. Les neuf tests de DealTab ont été rejoués après renforcement d’une
assertion de refus. Ces chiffres ne s’additionnent pas à ceux de la livraison
initiale : les campagnes se recouvrent et les 189 cas initiaux n’ont pas tous été
relancés après D01.

Les validations sont exécutées depuis la racine avec des données et une clé JWT
temporaires isolées. Les tests ciblés couvrent les référentiels, les RFQ manuelles
et réseau, le transport, le booking, le CCR, les amendements, les permissions C01
et les migrations d'identité C02. La chaîne UAT retenue exerce réellement le
parcours natif et le nettoyage de son lot.

Les premiers essais ont nécessité l'adaptation de fixtures aux motifs et IDs
explicites. Deux fixtures antérieures à C03 utilisaient encore un ancien périmètre
de desk et l'ancienne signature de rafraîchissement des alertes : elles sont
alignées sur C01, sans élargissement des droits. Un premier lanceur temporaire
Windows relançait pytest lors du spawn des workers UAT ; il a été corrigé avec
une garde `__main__`. Ces essais incomplets ne constituent pas des preuves positives.

Aucune suite backend complète ni campagne IA n'a été lancée. Aucune base métier
existante n'a été migrée ou modifiée ; le build frontend sort dans un dossier
temporaire et conserve le `dist` préexistant. Les travaux C01/C02 sont préservés.
La recette graphique manuelle reste ouverte. D01 est arbitrée ; la qualification
de production et les scénarios transverses des autres chantiers restent ouverts.
