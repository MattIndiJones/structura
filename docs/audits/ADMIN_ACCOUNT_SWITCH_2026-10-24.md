# Changement de compte depuis Admin et retour après erreur — 24/10/2026

Correctif local, sans commit ni push, dans le prolongement de la
[recette des accès du launcher](LAUNCHER_ACCESS_ACCEPTANCE_2026-10-24.md).

## Problème et résultat

La première recette vérifiait les destinations alors que les six organisations
étaient démarrées. La capture de Philippe révèle le cas manquant : ouvrir
uniquement Admin démarre l’Admin et le portail, pas les six services métier.
Les cartes du portail obtenaient un ticket, puis tentaient de contacter une
organisation arrêtée. « Failed to fetch » s’affichait sans retour explicite.
Le sélecteur du workspace Admin était en outre désactivé, car son indicateur
d’accès développeur est distinct de celui des installations métier.

Depuis Admin, **Changer de compte** et le menu du compte ouvrent maintenant le
portail. Le profil à ouvrir se choisit explicitement : **Super utilisateur,
Front, Opérations ou Contrôleur**. Le service de l’organisation choisie est démarré
à la demande avant l’émission du ticket ; les autres organisations restent arrêtées.

Le portail propose **← Retour** et **Retour à Structura Admin**, y compris après
une erreur. L’adresse de retour publiée par le serveur permet de revenir au
workspace sans nouvel appel au portail. Les erreurs réseau sont formulées en
français ; l’ouverture est signalée et le retour reste disponible pendant
l’attente lorsque sa destination est connue.

## Intégrité des accès et des saisies

- `start_if_needed` est explicite et vaut faux par défaut. L’émission d’un ticket
  seule ne change pas de contrat pour les anciens appelants.
- Le démarrage exige toujours le mode développeur, la requête locale explicite,
  une origine autorisée et un profil admis. Le manifeste local doit correspondre
  exactement au descripteur de l’annuaire ; un occupant étranger est préservé.
- Le démarrage précède le ticket : une indisponibilité retourne 503 sans émettre
  de ticket. L’origine d’audit demeure `DEVELOPMENT_PORTAL` ou `CENTRAL_ADMIN`
  suivant la session effectivement présentée ; aucune identité centrale n’est
  créée pour contourner le problème.
- Le nouveau compte n’est activé qu’après validation de sa session. Un échec
  conserve le compte courant. Le départ d’Admin demande toujours confirmation
  si des saisies métier ont été modifiées ; annuler conserve le contexte.
- Le choix du profil n’est pas une saisie métier à sauvegarder. Il est exclu de
  la garde des formulaires pour éviter une fausse alerte lors du retour.
- La navigation recharge le contexte ; les sessions et données privées des
  installations restent séparées. Aucun rôle ni mot de passe n’est restauré ou
  modifié pour rendre le parcours possible.

## Validation

Les résultats agrégés et les identités dédupliquées figurent dans
[la preuve structurée](remediation-lot-0-2026-10-20/LAUNCHER_ACCESS_VALIDATION.json).

Le complément backend couvre le démarrage explicite et sa réutilisation, l’ancien
contrat sans démarrage, les refus d’origine/profil, le retour 503 sans ticket,
la divergence annuaire/manifeste et le lien Admin limité au développement. Les
tests Vue couvrent les quatre profils, la conservation du compte après panne,
les deux retours, l’annulation de saisies et le message destiné à un ancien
portail encore actif. La compilation obligatoire publie les nouveaux assets ;
les anciens assets ont été sauvegardés avant remplacement.

La recette B01–B09 part seulement d’Admin et du portail, avec les organisations
arrêtées. Un service de fixture occupe le port Société Générale : l’ouverture
échoue proprement, le service étranger reste intact et le retour vers Admin
fonctionne. BNP Front est ensuite ouverte à froid. Après libération explicite du
port de fixture, Société Générale Opérations s’ouvre à son tour ; le retour à
Admin et le choix de profil au clavier sont vérifiés. Aucun agent IA ni aucune
campagne ne démarre. Les quatre services créés pour ce complément et la fixture
sont arrêtés à la fin.

Les captures et journaux restent sous
`.runtime/diagnostic-acceptance/launcher-access-2026-10-24`.
Les preuves A01–A19 de la recette précédente sont conservées avec leur portée.

## Activation sur la session actuellement ouverte

Le frontend a été reconstruit. Les processus Admin et portail relancés par
Philippe pendant l’intervention ont été préservés, conformément à `CLAUDE.md`.
Le portail déjà en mémoire doit donc être relancé pour charger le nouveau
contrat serveur : **Arrêter Structura** dans son launcher, puis **Entrer dans
Structura**, et recharger l’onglet si nécessaire.

Si un ancien portail répond encore à la nouvelle interface, elle indique de
relancer Structura, avec les retours disponibles. Aucun redémarrage forcé,
déploiement distant, commit ou push n’a été effectué.
