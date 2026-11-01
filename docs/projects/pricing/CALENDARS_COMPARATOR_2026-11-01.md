# Calendriers compacts et comparateur Following

État local au 01/11/2026, en prolongement de
[la correction du backtest principal](BACKTEST_HISTORY_FOLLOWING_2026-11-01.md).

## Défauts de calendrier et interface

Les places d'observation et les centres de règlement restent deux paramètres
distincts. Pour les nouveaux calendriers, le formulaire propose :

- la place déduite du suffixe connu du ticker ou de son identifiant de marché,
  par exemple `STMMI.MI` → Milan (`XMIL`), `.PA` → Paris (`XPAR`) ;
- le calendrier bancaire correspondant à la devise du deal pour le règlement,
  avec `TARGET` en EUR ;
- `all_open` (« toutes ouvertes ») comme proposition conservatrice, visible et
  modifiable dès que plusieurs calendriers sont sélectionnés.

Les listes sont repliées par défaut et leur résumé affiche les sélections et le
statut « Défaut » ou « Personnalisé ». La combinaison est masquée avec un seul
calendrier car `all_open` et `any_open` donnent alors les mêmes jours. Les deux
combinaisons demeurent indépendantes. Une sélection explicitement vide reste
vide et bloque la résolution ; le composant n'invente pas de sélection après
une suppression manuelle.

Les défauts automatiques suivent la devise et les titres jusqu'à une surcharge.
Le bouton « Utiliser le défaut proposé » réactive ce suivi pour le champ choisi.
Les nouveaux calendriers reçoivent les mêmes valeurs avant calcul, même sans
visite de l'onglet Economics. Les fonctions de sérialisation et de photographie
des inputs restent en lecture seule : elles ne doivent pas invalider un aperçu
de maturité déjà résolu.

Les calendriers chargés conservent leurs paramètres explicites et leur éventuel
ancien héritage bancaire. Aucun choix d'un contrat figé n'est remplacé. Un
calendrier chargé peut recevoir la proposition par une action explicite dans un
contexte éditable ; les contrôles d'un contrat figé restent désactivés.

Un titre sans place identifiable reçoit une approximation bancaire signalée dans
le formulaire, avec les tickers concernés. Une devise inconnue ne conserve pas
silencieusement le précédent défaut de règlement. Les propositions restent à
confronter aux termes du produit et à son lieu effectif de cotation.

`XMIL` et `XPAR` sont ajoutés au catalogue des **places d'observation**. Ils
utilisent les sessions `exchange-calendars` déjà dépendance du projet et le même
cache annuel que la qualification des clôtures. Ils ne sont pas ajoutés aux
centres de règlement. Le calendrier bancaire EUR/TARGET existant reste inchangé.
Les tests distinguent notamment les clôtures de Milan des séances de Paris et
des jours TARGET les 24 et 31 décembre 2026. Une demi-séance reste une séance ;
ce choix ne certifie pas la publication effective d'un cours.

## Comparateur historique

Le comparateur utilise désormais le même lecteur d'observations explicite que le
backtest principal : Following par défaut, maximum **10 jours calendaires**
réglable entre 0 et 31, ou strict sans substitution. Il conserve ses propres
contrôles et résultats ; les autres consommateurs de `_windowed_backtest`, dont
les propositions de réinvestissement, gardent leur comportement précédent.

Le début au 01/01/2010 est supprimé. La prévisualisation lit les historiques
locaux uniquement. Une date vide signifie un chargement automatique au lancement
explicite ; une date saisie est préservée. Le téléchargement fournisseur reste un
recours au lancement, après examen des données déjà stockées.

Pour rendre les classements comparables, l'échantillon est l'intersection des
clôtures réelles de l'univers disposant d'un historique. Tous les candidats et
les combinaisons utilisent ces mêmes dates et la même période. Un candidat sans
historique est exclu explicitement de l'univers exploratoire ; cela n'autorise
pas un backtest principal à perdre un constituant. Les dates initiales par titre,
les sources, les exclusions et les bornes utilisées sont conservées dans la réponse.

L'ancienne qualification globale `UNBOUNDED_HISTORY_GAP` ne rejette plus une série
du comparateur avant lecture du payoff. Chaque observation requise recherche sa
prochaine clôture commune réelle. Un dépassement de la limite ou une substitution
en mode strict fait échouer explicitement la comparaison. Une fermeture ne
crée aucun fixing fictif. Les dates de constatation et de paiement suivent la
convention décrite dans la note du backtest principal ; le TRI utilise le paiement.

Le contexte `strike_date`, `value_date`, `payment_date` et `settlement_ccy`, déjà
envoyé par le frontend mais auparavant absent du schéma du comparateur, est
maintenant validé et conservé. Le règlement final et les décalages des calendriers
ne sont donc plus perdus à cette frontière.

Le résultat contient un disclaimer visible, un panneau repliable des dates et un
export JSON complet. Les mêmes ajustements sont dédupliqués entre les calculs
individuels et les combinaisons. Les fenêtres dont le TRI est indéfini sont
comptées par ligne et datées dans l'export. Les pertes totales restent des TRI de
−100 %, elles ne sont pas traitées comme des valeurs indéfinies. Un candidat sans
aucune fenêtre exploitable est signalé dans les exclusions. Un changement de
panier, d'inputs ou de formulaire pendant un calcul empêche l'application tardive
du résultat devenu obsolète.

Le prix indicatif et la consultation graphique d'une ligne sont prolongés par
[la correction dédiée du 01/11](COMPARATOR_DETAILS_PRICING_2026-11-01.md) : les
fermetures de bourse ne sont plus confondues avec une lacune pour cette estimation
de volatilité, et le détail reprend les observations communes du classement.

## Validation et limites

- 125 tests backend ciblés réussis : comparateur, Following principal, calendriers,
  oracles de replay, cache et conservation des exclusions d'univers.
- 950 tests frontend réussis puis `npm run build` / Vite réussis, dont les nouveaux
  cas de défauts, surcharges, contrats figés, formulaire et contexte du comparateur.
- Cinq contrôles navigateur sur les fichiers compilés : défauts Milan/TARGET et
  compacité ; surcharge d'observation et changement de devise ; début commun et
  strict ; disclaimer, dates et export complet ; contrôles en largeur réduite.

Les tests backend utilisent un runtime temporaire avec réseau externe bloqué et
interdiction d'accès SQLite à `backend/data`. Le navigateur intercepte toutes les
requêtes et utilise une identité et des données fictives. Aucun historique réel
de STM, AXA, BNP ou Generali n'est qualifié par ces tests. Aucun nouveau serveur
applicatif n'est lancé ni aucune instance préexistante arrêtée.

Preuves locales : `.runtime/comparator-calendar-targeted.xml`,
`.runtime/comparator-following-new.xml`, `.runtime/comparator-calendar-frontend-build.log`
et `.runtime/diagnostic-acceptance/calendar-comparator-2026-11-01/`.

La suite backend complète n'est pas exécutée. Le test de booking préexistant
documenté dans la note précédente n'est pas inclus dans ce périmètre. Aucun
commit, push ou déploiement. Relancer le backend par le workflow habituel puis
actualiser le navigateur pour charger les routes, schémas et calendriers locaux.
