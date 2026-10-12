# Consultation des installations après arrêt d'une campagne

L'admin peut ouvrir le Structura sauvegardé d'un acteur sans redémarrer les IA.
Dans **Simulation entre agents**, sélectionner l'essai arrêté, puis dans
**Vue d'ensemble** cliquer **Ouvrir en consultation** sur la carte BNP ou Hector.
Le Booking natif s'ouvre dans un nouvel onglet, déjà connecté au compte conservé
de l'acteur. Le même accès existe pour les autres acteurs disposant d'un compte.
Achille n'a pas d'installation.

Un bandeau permanent indique l'entité, la date simulée figée, les IA arrêtées et
l'interdiction d'écriture/recalcul. Les références ouvrent les deals et leurs
historiques de MtM natifs. Le bouton **Fermer la consultation** dans la campagne
arrête uniquement cette installation. Fermer l'onglet ne ferme pas le serveur ;
utiliser ce bouton. La fermeture du backend contrôleur ferme aussi les
consultations qu'il a lancées.

L'ouverture est réservée au propriétaire de la campagne, après STOPPED,
COMPLETED ou ATTENTION, sans lease de contrôleur actif. Elle vérifie la présence
du book et du compte sauvegardés ; elle ne recrée aucun acteur, contrat, catalogue
ou deal. Un second clic réutilise la consultation déjà ouverte. Les consultations
doivent être fermées avant le redémarrage des IA, le rejeu ou la suppression de
l'essai. Un verrou OS propre à la consultation protège ces opérations même si
le serveur ne répond pas ou si le contrôleur redémarre. Les API des installations
acteurs ne peuvent pas piloter les campagnes.

Le démarrage de consultation utilise la base existante via SQLite `mode=ro` et
`PRAGMA query_only=ON`. Les migrations, seeds, reprises de recherches et scheduler
de lifecycle sont désactivés. Les requêtes HTTP mutantes sont refusées avec 403,
y compris booking, suppression, MtM, refresh et inscription. Seules la connexion
sans écriture et les commandes privées de session/fermeture sont permises.
La protection SQLite empêche aussi une écriture SQL hors middleware.

Les serveurs de consultation ont leurs identités, secrets, logs et horloges dans
un dossier latéral `consultations/<actor>`. Le fichier de campagne et les bases
des acteurs ne sont pas modifiés. Les secrets de contrôle ne figurent pas dans
les états exportés. La connexion automatique utilise une session propre à ce
serveur ; son jeton passe dans le fragment de navigation, puis disparaît de
l'adresse avant l'ouverture du Booking. Aucun mot de passe acteur n'est exposé.

Le calendrier du Booking reste à la date de l'essai. Les MtM archivés à cette date
peuvent avoir une date d'enregistrement réelle différente : leur restauration en
consultation filtre la date de valorisation, sans imposer le jour réel de création.
Les contrôles ordinaires du MtM quotidien sont conservés hors consultation. Les
résultats ne sont jamais recalculés pour compléter les archives manquantes.

Validation locale : 68 tests backend ciblés, dont 11 de consultation avec une
installation native temporaire ; 380 tests frontend et build. La recette navigateur
`scripts/check_workshop_consultation_ui.py` ouvre aussi les books conservés de BNP
(5 deals) et Hector (10 deals), leurs historiques de MtM, vérifie le blocage d'une
écriture, la fermeture, les nouveaux onglets et la largeur mobile. Le fichier de
campagne et les deux bases doivent rester identiques par SHA-256, et le compteur
d'appels modèle doit rester inchangé. Les preuves sont dans
`output/agent-workshop-consultation-ui/`.

Pour utiliser la livraison, redémarrer le backend habituel et recharger la page.
La campagne reste arrêtée ; aucune nouvelle campagne IA n'est lancée.
