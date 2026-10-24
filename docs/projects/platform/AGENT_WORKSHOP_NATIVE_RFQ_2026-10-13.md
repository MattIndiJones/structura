# Campagnes agents — environnement hybride et RFQ natives

Consignes actualisées le 13/10/2026, sur autorisation de Philippe. Aucun commit
ni push. Simulation exclusivement fictive ; aucune facturation ou opération réelle.

## Organisations et rôles confirmés

Kepler Cheuvreux Solutions est demandeur. BNP Paribas, Société Générale, Citi,
UBS et Leonteq répondent aux RFQ. Un client fictif exprime ses besoins et décide
sur les offres. Achille supervise les signalements. Les identifiants internes
`hector` et `ca` désignent désormais Kepler et Citi ; les noms de l'organisation
font foi. Citi est explicitement rapproché de la contrepartie existante Citigroup.

Les sept acteurs métier disposent de bases, services, clés et sessions privés,
séparés des six installations d'essais manuels. Chaque banque possède un compte
Contrôleur distinct pour la seconde validation. L'admin de développement dirige
ces installations fictives ; cela ne donne aucun accès permanent aux books de production.

## Consignes obligatoires

1. Relire l'existant avant toute création. Réutiliser contreparties, comptes,
   desks, relations, RFQ et Product déjà présents avec leurs identifiants locaux.
   Créer uniquement les éléments manquants. Ne pas restaurer un droit révoqué,
   remettre une base à zéro ou refaire une action réussie pour avancer.
2. Utiliser les termes Product figés. Le calendrier, le panier et les paramètres
   contractuels restent propriété du Product. Chaque acteur garde ses prix
   théoriques, hypothèses, modèles, marges, clients et books dans sa base.
3. Envoyer une projection d'échange par le transport RFQ signé existant. Les
   banques prennent en charge les demandes dans RFQ reçues. Le journal de
   conversation sert aux précisions ; une conversation ne remplace pas une
   réception native, une cotation publiée ou un booking.
4. Calculer dans le Product privé de la banque, préparer le prix commercial avec
   validité et conditions explicites, faire valider par le Contrôleur puis
   publier. Ne pas consulter les cotations concurrentes. Toute révision ou
   tout retrait doit emprunter le workflow natif et conserver son historique.
5. Comparer les prix effectivement publiés, motiver le choix et proposer au
   client. Le client reste libre d'accepter ou refuser ; ne pas fabriquer son
   accord pour atteindre le volume commercial.
6. Après accord client, demander le traitement. La banque retenue confirme
   explicitement prix, nominal et termes. Le demandeur consigne la confirmation
   avec sa preuve fictive avant booking. Ne pas présenter cette preuve de
   simulation comme une confirmation bancaire de production.
7. Acheter avant de revendre. Conserver le lien RFQ, la version Product et
   l'accord confirmé pour l'achat. La distribution au client utilise un dossier
   commercial distinct reprenant exactement les mêmes termes figés. Réconcilier
   banque vendeuse/demandeur acheteur et demandeur vendeur/client acheteur.
8. Réutiliser les références lors des retries. Un rejeu ne doit créer ni nouvelle
   contrepartie, ni nouvelle RFQ, ni double booking. Refuser les données ambiguës
   et les snapshots devenus incohérents ; ne pas désactiver les contrôles.
9. Suivre fixings, coupons, autocalls et remboursement final avec sources
   synthétiques explicites. Ne jamais les qualifier de cours Yahoo réels. La
   fin de la période commerciale n'arrête pas les produits encore vivants.
10. Distinguer refus métier attendu, erreur d'utilisation d'agent, défaut du
    raccordement et bug applicatif. Conserver décisions, identités habilitées,
    appels HTTP, horodatages et preuves. Un HTTP 200 ou un statut de campagne
    terminée ne qualifie pas à lui seul le produit ou la précision quantitative.

## Raccordement et horloges

Le catalogue existant est relu dans chaque installation. Le répertoire local
des partenaires contient uniquement les noms d'organisation et les desks publics,
sans comptes ou books distants. Les accords de distribution et RFQ sont reconnus
par les deux parties, avec canaux privés signés. HTTP de boucle locale est activé
uniquement dans ces installations de simulation ; HTTPS reste requis en production.
Les adresses sont conservées lors d'une reprise pour préserver les canaux.

Les calculs et leurs reçus utilisent UTC opérationnel pour leur ancienneté et
leur authentification. La date métier accélérée gouverne les échéances, la
validité commerciale et les fixings. La correction de fraîcheur ne supprime
ni le contrôle de calcul futur, ni celui de calcul périmé, ni les limites du desk.

Les états suivis sont NOT_EXERCISED, QUEUED, DELIVERED, publié, accepté,
confirmation attendue, confirmé, booké, rapproché et produit résolu, d'après les
faits natifs. Une interruption conserve outbox, accusés et identités de canaux.
Les données et preuves restent conservées jusqu'à suppression explicite. Les
habilitations de développement n'expirent pas automatiquement, mais restent
révocables ; aucune reconnexion ne doit les rétablir implicitement.

## Campagne complète demandée

Douze mois commerciaux à partir du 13/10/2025, tickets fictifs de 10 000 000 EUR,
objectif indicatif de 100 000 000 EUR, graine 42, modèle local Qwen2.5-Coder 7B.
Tous les accords du scénario principal sont complets. Reverse convertibles et
Phoenix réutilisent les templates, moteurs et masques existants. Les décisions
commerciales sont autonomes et peuvent laisser l'objectif de volume non atteint.
Le suivi se prolonge jusqu'aux derniers paiements. Plafond : 1 200 tours et six
heures réelles ; une pause de sécurité conserve les preuves et arrête les acteurs.

Le registre RFQ central et son raccordement durable restent un chantier distinct.
Cette campagne ne livre pas le registre, la tarification, une compilation
commerciale ou un nouveau moteur de calcul confidentiel. Default, réinvestissement,
margin calls et précision quantitative ne sont pas déclarés qualifiés par défaut.

Le superviseur `scripts/run_workshop_campaign.py` lance la campagne par l'API admin,
consigne les processus qu'il possède, écrit les progrès et exports dans le dossier
privé de la campagne et ferme ses services à la fin. Dans Structura Admin,
Simulation → campagne → Arrêter permet de demander l'arrêt propre. Les suites
de tests backend/frontend restent suspendues ; le build frontend est effectué.

## Qualification dirigée du 13/10/2026

Campagne privée `2804592ee1bd44a9b12a7ed714bf97a9`, dossier de preuve
`.runtime/hybrid-saas/native-rfq-qualification/2804592ee1bd44a9b12a7ed714bf97a9/`.
Le résultat `qualification-result.json` contient 46 actions et leurs appels HTTP.
Sur CASE-002 : cinq cotations publiées après validation par cinq comptes Contrôleur
distincts, traitement et confirmation explicites, quatre bookings et leurs rejeux,
règlements initiaux et rapprochement COMPLETE sans anomalie. Le rejeu RFQ conserve
la demande existante ; les rejeux booking conservent les identifiants de deals.
Un booking avant confirmation est refusé par le raccordement de simulation.
Les sept services de qualification ont été arrêtés ; aucune erreur de nettoyage.

Les blocages de raccordement rencontrés ont été corrigés : identité du demandeur,
rejeu du besoin, contexte de calcul, fraîcheur du reçu, preuve de prix du demandeur,
dossier distinct de distribution et sérialisation des dates contractuelles.
CASE-001 conserve un écart historique de contrat investisseur dû à un arrondi de
tenor ; ses deals n'ont pas été réécrits. CASE-002 reprend les termes canoniques
Product chez l'investisseur et les quatre empreintes de contrat concordent.

Ce contrôle dirigé ne qualifie pas les décisions autonomes, les révisions/retraits,
la reprise après panne réseau ou le cycle jusqu'au dernier paiement. Ces résultats
doivent être relevés séparément pendant la campagne complète. Analyse syntaxique
Python et build frontend réussis ; aucune suite pytest ou vitest exécutée.

## Choix du modèle et plafond de campagne — 14/10/2026

Dans **Structura Admin → Simulation**, une nouvelle campagne peut choisir Ollama
local ou OpenAI, puis un modèle du fournisseur sélectionné. Le modèle OpenAI
proposé par défaut est GPT-6 Luna ; GPT-5 nano (déprécié), GPT-6 Sol et GPT-6.1
Sol restent sélectionnables. La clé OpenAI déjà configurée pour Structura est
réutilisée dans le processus admin : aucune nouvelle clé à saisir dans l'écran.
Les anciennes campagnes sans champ `provider` restent sur Ollama.

Le formulaire permet de fixer les mois commerciaux (1 à 60), la durée des nouveaux
produits (6 à 60 mois), les deux familles natives déjà raccordées au RFQ
(reverse convertible et Phoenix), le nombre maximal d'appels IA et un plafond
OpenAI par campagne. Le scénario alterne les familles cochées par mois ; l'accord
commercial du client reste libre. Ces deux familles ne constituent pas une
qualification des autres payoffs du catalogue. Le marché synthétique couvre la
période commerciale et la durée contractuelle finale.

Chaque appel OpenAI utilise Responses avec un schéma de sortie strict et
`store: false`. Les
jetons facturés par l'API et un coût estimé aux tarifs standards du modèle sont
consignés dans la campagne et affichés dans l'atelier. Le contrôleur réserve
le coût maximal estimé du prochain appel avant son envoi ; il interrompt la
campagne lorsque le plafond local ou le nombre d'appels est atteint. Il conserve
les preuves et ferme ses services. Ce plafond local n'est pas un contrôle de
facturation du compte OpenAI : les appels interrompus après envoi peuvent avoir
un coût non remonté. Garder également la limite de dépense du projet OpenAI.

Vérification ciblée du 14/10 : cinq tests backend ciblés et le build frontend
(435 tests Vue) réussis. Un appel minimal réel à GPT-6 Luna a répondu en 2,375 s,
26 jetons en entrée et 12 en sortie, coût estimé 0,0000086 $. Il vérifie
l'accès API et le format JSON, pas la durée ou la réussite d'une campagne RFQ.
Un appel identique à GPT-5 nano a également fonctionné (2,281 s), mais a
consommé 166 jetons de sortie dont 128 de raisonnement, soit environ 0,0000677 $
malgré son tarif unitaire inférieur. C'est pourquoi Luna reste le choix initial
économique ; le coût réel dépend des jetons consommés par décision.
Aucune campagne complète OpenAI n'a été lancée par cette modification.
Le [pilote réel du 14/10](../../audits/CAMPAIGN_OPENAI_PILOT_2026-10-14.md)
a ensuite atteint une RFQ rapprochée. Le contrôle suivant, après correction du
schéma des arguments et du déclenchement des agents, a de nouveau rapproché
la RFQ avec cinq cotations et quatre bookings : 19 appels modèle au lieu de 69,
sans sortie malformée. Les agents sont sollicités pour un travail métier ou un
message direct, et les initiatives spontanées sont optionnelles. La campagne
longue et le suivi jusqu'aux paiements restent à qualifier.
