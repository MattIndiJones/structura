# RFQ réseau — lot 5 : validation et publication bancaire

Date : 12/10/2026. Branche : `codex/rfq-network-lot-0`. Changements locaux, sans commit ni push.

## Périmètre livré

BNP peut préparer un prix commercial à partir de son dernier calcul Product conservé, faire valider le récapitulatif exact et publier. Le prix est enregistré automatiquement dans la RFQ du demandeur, à côté des réponses manuelles. Les deux organisations utilisent la même installation Structura ; le transport entre installations reste le lot 6.

Préparer, valider et publier sont trois actions distinctes. Une préparation ou une validation ne crée aucune cotation chez le demandeur. La publication et sa réception sont atomiques dans cette installation, avec identifiant de message et heures UTC distinctes dans le modèle. Le demandeur voit le prix commercial et les conditions publiées, jamais le calcul théorique ni son reçu détaillé.

## Configuration du desk BNP

Dans **Administration → Utilisateurs → desks RFQ**, accorder explicitement :

- `validate_quote` : valider une cotation bancaire ;
- `publish_quote` : publier et retirer une cotation bancaire.

Les droits `read`, `prepare` et `price` du lot 4 restent nécessaires pour prendre en charge, calculer et préparer. Les anciens membres ne reçoivent aucun nouveau droit automatiquement. Le rôle administrateur ne remplace pas une habilitation bancaire.

Dans le détail d’une **RFQ reçue**, **Réponse commerciale bancaire → Politique du desk** permet à l’administrateur de l’organisation bancaire de choisir :

- seconde validation obligatoire ou validation possible par le même utilisateur ;
- âge maximal autorisé du calcul, en minutes ;
- motif de configuration.

La politique est explicite et versionnée, sans durée de fraîcheur matérielle inventée. Elle doit être enregistrée avant la première préparation. Changer la politique invalide les validations effectuées sous une ancienne version. La validité d’une cotation reste saisie explicitement pour chaque réponse ; elle n’est pas déduite du délai de réponse de la RFQ.

## Parcours bancaire

1. Prendre en charge, calculer avec le Product/moteur natifs et conserver le calcul privé du lot 4.
2. **Préparer le prix commercial** : sélectionner le calcul, saisir prix en % du nominal all-in, fermeté, validité locale, émetteur/garant applicables, référence documentaire, conditions explicites et commentaire partagé.
3. **Enregistrer la préparation** : conserver le contenu commercial, son empreinte, le calcul lié et la responsabilité courante. Nominal entier, devise, sens du demandeur, tour et termes viennent de la demande figée.
4. Examiner **Récapitulatif commercial** et son contenu exact.
5. **Valider ce récapitulatif** : avec seconde validation désactivée, le même utilisateur habilité peut calculer, préparer, valider et publier. Si elle est activée, un autre utilisateur habilité valide ; l’auto-validation du préparateur est refusée côté serveur.
6. Avec un second utilisateur, le préparateur/publieur utilise **Actualiser le contrôle** pour retrouver la validation dans le masque ouvert.
7. **Publier le prix au demandeur** : recontrôler tous les prérequis au moment effectif, publier et livrer une réponse attribuable, versionnée et persistante.

Les rôles de valideur et de publieur peuvent être distincts. Lire le reçu détaillé ou le prix théorique exige toujours `price` ; les droits de contrôle commercial ne donnent pas accès au détail privé du calcul.

## Contrôles avant validation et publication

Les contrôles portent sur :

- habilitation du desk, organisation et utilisateur actifs ;
- responsabilité inchangée, dossier bancaire actif, tour/consultation ouverts et délai de réponse non dépassé ;
- relation bilatérale active, périmètre autorisé et version reconnue identique à celle de la sollicitation ;
- calcul Product appartenant au dossier bancaire, termes et empreinte identiques à la demande reçue, dernier calcul conservé et fraîcheur conforme à la politique ;
- prix fini, positif et borné en points de pourcentage du nominal ;
- validité postérieure à la publication, avec fuseau explicite ;
- absence explicite de conditions supplémentaires ou liste structurée de conditions ;
- contrepartie juridique issue du rapprochement reconnu ; émetteur et documentation obligatoires pour une note ;
- pour une offre ferme, relation et accords locaux de traitement autorisés, documentation et quatre dates contractuelles complètes ;
- empreinte recalculée du contenu exact, validation actuelle de cette empreinte et de la politique, valideur encore habilité, séparation des acteurs lorsqu’elle est exigée.

Un nouveau calcul, une réaffectation, une modification de préparation, un changement de politique ou une révocation du valideur empêche la publication de l’ancienne validation. Il faut préparer/recontrôler la réponse appropriée. Le prix commercial ne réécrit jamais le prix théorique.

## Contenu partagé

La réponse conserve référence de réponse, révision, message, référence d’échange et tour, version/empreinte des termes, organisation/desk répondants, sens du demandeur, nominal entier, devise, prix et convention, fermeté, expiration, parties juridiques déclarées, documentation, conditions et commentaire. La publication ajoute son auteur partagé et son heure ; la réception conserve son heure d’enregistrement.

Aucune donnée CRM, cotation concurrente, hypothèse de marché, modèle, calibration, Greeks, marge interne, identifiant de calcul ou validation interne ne figure dans cette projection publiée. Le demandeur conserve son propre prix modèle.

Le périmètre de cette tranche est une réponse aux termes reçus. Les contre-propositions restent un complément du lot 4 ; les conditions supplémentaires sont identifiées séparément, sans modifier le payoff en commentaire.

## Parcours demandeur et manuel

Une publication alimente les `RfqQuote` existantes avec une liaison persistante à son message. La RFQ passe à **Cotée**. La table montre **Réseau**, révision et état, avec détail des parties, documentation et conditions. Prix, fermeté, dates, statut et suppression d’une cotation réseau sont protégés dans l’interface et les API ; le demandeur ne peut pas la réécrire en saisie manuelle.

La RFQ réseau actuellement ouverte recharge ses réponses toutes les cinq secondes. Le timer est arrêté en quittant la vue et suspendu lorsque la page est cachée ou un champ est en saisie. Le rafraîchissement conserve les hypothèses locales, ignore une réponse visant un ancien dossier et ne remplace pas une mutation manuelle en cours.

Les réponses manuelles conservent leurs formulaires et leurs contrôles actuels. Les cotations réseau actives sans condition supplémentaire peuvent être comparées et retenues ; réponses conditionnelles, retirées, expirées ou remplacées restent visibles hors classement conforme.

**Retenue** reste une sélection locale, distincte d’une acceptation reçue par BNP. Le booking d’une cotation réseau publiée est provisoirement bloqué dans l’interface et l’API jusqu’au parcours de confirmation du lot 7. Cette tranche ne crée aucun accord ni Deal automatiquement et ne remplace pas le parcours manuel historique.

## Révisions, retrait et traces

Une nouvelle préparation incrémente la révision et efface la validation précédente. Une nouvelle publication conserve intégralement les réponses antérieures, expire leur projection active et efface une sélection de l’ancienne réponse ; elle ne sélectionne pas la nouvelle à la place du demandeur.

**Retirer cette cotation** exige `publish_quote`, un motif partagé et aucune acceptation reçue/traitement booké. Le retrait est transmis immédiatement dans la même transaction. Le prix et le message d’origine subsistent ; l’heure et le motif de retrait sont ajoutés et la réponse n’est plus sélectionnable.

Le garde contre retrait/remplacement après acceptation utilise un fait d’acceptation enregistré, distinct de `selected_quote_id`, et refuse aussi un dossier déjà booké. L’enregistrement opérationnel des demandes de traitement et confirmations appartient au lot 7 ; cette protection n’est pas une qualification de ce futur parcours ni de la course acceptation/retrait entre serveurs.

Le rejeu d’une publication déjà effectuée de la même révision retrouve le même message et la même quote, sans doublon. Les contrôles d’habilitation restent appliqués. Politique, préparation, validation, publication/livraison et retrait disposent d’un audit. Le verrou de sollicitation sérialise les mutations locales.

Les tables additives sont `rfq_bank_publication_policies`, `rfq_bank_quote_drafts` et `rfq_quote_publications`. Aucun dossier ancien n’est migré.

## Masques et vérification

Le panneau commercial s’insère dans `BaseModal` du dossier bancaire, avec détails repliables et scroll interne. La table du demandeur reste dans le viewport RFQ existant. Les libellés d’état et les formats numériques sont français.

- Tests backend ciblés : groupe de **143**, puis **20** scénarios sur publication/habilitations et **2** sur offre ferme/nouveau calcul ; **156 scénarios distincts réussis** au total. Aucune suite backend complète.
- Build frontend réussi : **427 tests**, compilation Vite. Le rafraîchissement a un scénario de conservation des hypothèses et de non-écrasement du dossier actif.
- Recette HTTP authentifiée sur `tmp/rfq-lot5-uat/data/structura.db`, chemin engine vérifié avant seeding et identité d’instance vérifiée : calcul natif QA BNP, politique à seconde validation, auto-validation refusée, contrôle par un second compte, publication, réception côté QA ClientTech, rejeu sans doublon, champs reçus immuables et retrait conservant le prix.
- Cas fictif de recette : prix théorique privé **91,3537 %**, prix commercial saisi et publié **98,50 %**. Le demandeur reçoit seulement le second. Ces chiffres ne sont pas des cotations BNP réelles.
- La recette navigateur est bloquée par l’outil (`ERR_BLOCKED_BY_CLIENT`). Scroll réel, clavier et mobile restent à qualifier à l’écran. L’instance de recette est arrêtée ; la base locale réelle n’a pas été utilisée.

Le transport distribué, ses signatures et reprises sont le lot 6. La confirmation de traitement et le booking contrôlé sont le lot 7. Précisions/déclin, contre-propositions et qualification générale des exports/tâches longues restent également à compléter selon les notes précédentes.
