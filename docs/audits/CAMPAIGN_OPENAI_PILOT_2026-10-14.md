# Pilote OpenAI du parcours RFQ natif — 14/10/2026

Campagnes fictives privées, sans facturation réelle et sans usage des six bases
d'essais manuels. Aucun commit ni push.

## Paramètres et résultat

GPT-6 Luna ; un mois commercial, reverse convertible à 12 mois, cinq répondants,
graine 42, plafond local 0,25 $ et 160 appels/décisions maximum. Le contrôleur
a arrêté l'essai dès le premier rapprochement complet.

Campagne `caa9c6c111d646d6b4b86288ffafb457` : 69 tours et 69 appels en 258 s,
coût IA estimé 0,0179933 $. Les sept comptes se sont connectés. Un besoin client
et une RFQ native ont été créés ; BNP, SG, Citi, UBS et Leonteq ont chacun publié
une cotation. Kepler a fait une offre, le client l'a acceptée, Leonteq a confirmé,
puis Kepler a consigné la confirmation. Quatre jambes ont été bookées : Leonteq
vendeur, Kepler acheteur puis vendeur, client acheteur. Le rapprochement de
`CASE-001` est `COMPLETE`, sans jambe ni preuve manquante, pour 10 000 000 EUR.

Cinq décisions ont échoué : le JSON externe respectait le schéma strict, mais la
chaîne `args_json` contenait des caractères supplémentaires après l'objet JSON.
Ces sorties n'ont déclenché aucune action métier ; les agents ont repris au tour
suivant. 63 actions ont réussi et une décision a été annulée pendant l'arrêt.
Le succès RFQ ne qualifie ni la précision du pricing, ni les autres payoffs, ni
le suivi jusqu'au remboursement final.

## Correction des appels superflus et second pilote

Le premier pilote appelait le modèle pour des attentes sans tâche (19 fois),
pour l'inscription et les relations déjà mandatées (19 fois), ainsi que pour
des initiatives non sollicitées de risque OTC et de proposition. La préparation
obligatoire des comptes, relations et CRM passe désormais par le contrôleur
déterministe, avec les mêmes actions métier et leur trace. Une notification
passive ne sollicite plus l'agent ; seuls un travail métier disponible ou un
message direct demandant une réponse le réveillent. Les propositions et revues
de risque spontanées sont désactivées par défaut et restent activables dans la
configuration de campagne. Les arguments des outils sont maintenant des objets
typés dans le schéma strict OpenAI, sans chaîne `args_json` à parser. Ce schéma
ne propose pas l'outil API générique ; les outils RFQ natifs restent disponibles.

Campagne de contrôle `e936501413fa4664b72c6fada1f8ce7c`, mêmes paramètres
bornés : 39 actions, 19 appels modèle comptabilisés, dont 18 décisions terminées
et un appel annulé à l'arrêt ; coût IA estimé 0,0063816 $ et durée totale 158 s.
Sept comptes connectés, cinq cotations publiées, quatre jambes bookées et
`CASE-001` rapproché `COMPLETE` pour 10 000 000 EUR, sans jambe ni preuve
manquante et sans incident. Aucun `wait`, aucune revue OTC et aucune proposition
spontanée ; zéro erreur de format. Cela représente 50 appels modèle en moins
sur cette RFQ (69 à 19) et une baisse d'environ 64 % du coût estimé. La mesure
inclut un appel annulé dont le coût éventuel n'est pas remonté.

Validation ciblée : sept tests backend, compilation Python, build frontend
(435 tests Vue) et un appel réel du nouveau schéma strict réussis. Ce contrôle
court ne qualifie toujours pas la campagne longue, les deux familles de payoff
sur plusieurs années, les paiements, ni la justesse quantitative du pricing.

## Blocage initial et correction

Le premier essai `23eb3e9818524a549abfad6ad39b13d3` s'est arrêté à zéro tour :
la clé OpenAI, accessible au processus de lancement, était volontairement retirée
de l'environnement du service Admin. Aucun appel facturé. Le lancement transmet
désormais la clé seulement aux contrôleurs centraux de campagne ; les installations
des organisations et les processus des agents ne la reçoivent pas. Deux tests
ciblés de frontière d'environnement ont réussi.

Le deuxième essai `45c4c51669a643f687708cd5b08a0659` a confirmé le défaut
du mode JSON libre : sept comptes connectés, un besoin, 25 décisions, puis
réponses malformées/incomplètes et arrêt `ATTENTION` ; coût estimé 0,0053866 $.
Le raccordement est passé au schéma de sortie strict. Quatre tests ciblés et un
appel réel au schéma strict ont réussi avant le pilote final.

## Nettoyage et preuves

Les quatre campagnes conservent leurs dossiers sous
`.runtime/hybrid-saas/admin-workbench/campaigns/<id>/`. Le second pilote est
`STOPPED` après arrêt demandé ; son contrôleur est inactif. Les ports privés des
sept agents sont fermés, ainsi que les ports Admin et portail ouverts pour le
pilote. Aucun service d'essai manuel n'a été démarré ou arrêté.
