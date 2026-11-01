# Accès au Pricer et cohérence des routes — 1er novembre 2026

Le retour à l’accueil depuis « Nouveau Pricing » est reproduit et corrigé.
La vérification initiale confirme que le service existant sur le port 8000
est le workspace Admin complet ; aucun service préexistant n’a été arrêté.

## Cause et correction

Le workspace Admin possède un descripteur d’installation `kind=platform`,
mais fonctionne avec les droits historiques de l’application autonome.
Le serveur autorisait son rôle `admin` à pricer tout en publiant une liste
de capacités vide. Le frontend interprétait la présence du descripteur comme
une installation métier et refusait donc `/pricer` et les routes Optimizer.

La liste serveur reflète désormais les capacités métier déjà autorisées à
l’Admin autonome. Un compte technique dans une installation métier ou centrale
n’acquiert aucun droit supplémentaire. Les comptes désactivés restent refusés.

Le frontend reconnaît explicitement le workspace Admin complet, son rôle et son
type d’installation. Cette compatibilité permet aussi de charger la nouvelle
interface avec le serveur déjà en mémoire, dont la réponse conserve l’ancienne
liste vide. Les profils Opérations/Contrôle et la console centrale conservent
leurs restrictions. Les autres consommateurs de la liste serveur actualisée
en bénéficieront au prochain redémarrage normal du backend.

Un second défaut est trouvé dans Trading : le lien vers les accords pointait
sur `/ccr`, inexistant et redirigé vers l’accueil. Il pointe sur `/risk/ccr`.

## Validation

- Avant correction : neuf échecs dans les nouveaux tests de routes, dont huit
  accès Admin/restauration et le lien Trading ; 96 autres contrôles réussis.
- Après correction et extension du périmètre : 134 tests du routeur couvrent
  les accès Pricer/variantes/Product/Optimizer, les routes voisines, la revue
  de booking par profil, la restauration de session et les liens statiques Vue.
- Onze tests backend ciblés réussis sur les capacités publiées et effectives,
  en contexte autonome, organisation et plateforme, avec comptes actifs/inactifs.
- `npm run build` : 924 tests frontend réussis dans 89 fichiers et compilation
  de production réussie ; `frontend/dist` régénéré par le build.
- Navigateur Chromium isolé sur les fichiers effectivement servis par le backend
  existant : carte « Nouveau Pricing », rechargement de `/pricer` et bouton
  « Nouveau pricing » vérifiés, sans retour à l’accueil ni erreur JavaScript.

La vérification navigateur utilise une identité Admin synthétique reproduisant
l’ancienne réponse et intercepte les quinze requêtes API. Elle valide le routage
et le chargement de l’interface ; elle ne valide ni un prix réel ni une session
métier active. Preuves locales :
`.runtime/diagnostic-acceptance/routes-2026-11-01/browser-check.json` et
`pricer-open.png`. Le contexte et le navigateur de contrôle sont fermés.

Aucune base métier ouverte par les outils de contrôle, aucun appel de calcul
réel, aucune suite backend complète, aucun commit ni push. Les services
préexistants des ports 8000 et 8100 sont préservés. Recharger la page permet de
charger le frontend corrigé ; un rechargement peut abandonner une saisie en cours.
