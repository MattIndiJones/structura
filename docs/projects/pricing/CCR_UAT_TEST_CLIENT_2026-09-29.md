# Jeu de données CCR du compte `test`

Le compte `test` possède 23 deals UAT sur UBS, BNP Paribas et Société Générale dans l'entité Demo. Le paramétrage CCR est commun à **toute l'entité**, et non propre à l'utilisateur : ces données sont des hypothèses de recette fictives, pas des informations de crédit, contrats ou limites réels. Les ratings externes et LEI restent volontairement vides. Les courbes et recouvrements sont déclarés `MANUAL` / `USER_ASSUMPTION`.

| Contrepartie | Cas couvert | Profil crédit | Documentation / collatéral |
| --- | --- | --- | --- |
| Société Générale | Note émise en cours de vie, exposition non collatéralisée | PD cumulée **risk-neutral** fictive sur 10 ans, recouvrement 40 %, CVA disponible | `has_isda=false`, `has_csa=false` ; aucun netting set |
| BNP Paribas | CVA par spreads et scénarios juridiques OTC simulés | Spreads fictifs sur 10 ans, recouvrement 40 %, CVA disponible | Accord UAT simulé actif ; deux sets OTC fictifs, avec ou sans CSA. CSA avec VM, IM, seuils, MTA, haircut, délai de règlement et MPOR ; positions de collatéral fictives au 28 et 29/09/2026, sans collatéral posté hors du portefeuille de notes |
| UBS | Alerte sur donnée impropre à la CVA marchande | PD **historique** fictive sur 10 ans, recouvrement 25 % ; PFE disponible, CVA non calculable faute de PD risk-neutral | Accord UAT en attente, netting set inactif ; aucun netting reconnu |

Quatorze limites informatives en EUR couvrent nominal, exposition courante, PFE 95/99, CVA et exposition stressée. Elles sont applicables dès le 01/09/2026. Les montants et seuils (alerte à 80 %, limite à 100 %) sont purement pédagogiques ; plusieurs valeurs peuvent donc afficher `OK`, `WARNING`, `BREACH` ou `MISSING_DATA` selon le calcul. L'action `INFORMATION_ONLY` évite qu'une limite fictive bloque un flux de production.

Les sets juridiques simulés n'acceptent que le type de produit artificiel `UAT_CCR_OTC_ONLY`. **Aucun des 23 deals de notes existants n'est rattaché à un set** : détenir une note crée un risque de crédit sur son émetteur, mais ne prouve pas qu'elle relève d'un accord ISDA/CSA de dérivés OTC. Pour exercer les chemins positifs de netting/collatéral, utiliser une proposition de test portant explicitement ce type de produit dans le moteur/API CCR. La position de collatéral est datée : pour une autre date d'arrêté, renseigner une position de recette à cette date.

Le script [seed_ccr_test_client.py](../../../backend/scripts/seed_ccr_test_client.py) contrôle le périmètre avant toute écriture, sauvegarde la base SQLite, puis utilise les services CCR audités. Sans `--apply`, il ne fait qu'un précontrôle. Il refuse de rejouer si un paramétrage CCR existe déjà sur ces contreparties et ne remplace aucune donnée.
