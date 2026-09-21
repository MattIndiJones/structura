# Studies — processus, corrections et recette

Date : 20 septembre 2026. Version de méthode : `studies-2.0`.

Ce document complète l’[audit du 20 septembre](../../audits/AUDIT_STUDIES_2026-09-20.md). Le module reste générique : chaque étude fournit son identité, sa devise, ses fichiers, son panier initial et ses paramètres. Aucun des correctifs ne dépend du portefeuille d’un AMC déjà étudié. La recette utilise des produits fictifs.

## 1. Ce qui change

Les calculs utilisent une date d’arrêté commune, contrôlent les données manquantes et distinguent résultat descriptif, inférence statistique et couverture documentaire. Les compléments et les rapports peuvent être conservés avec la version de l’étude. Les fichiers sélectionnés dans le manifeste définissent effectivement le périmètre.

**Une correction ne peut pas créer des transactions, dividendes ou relevés absents.** Dans ce cas, le module signale une analyse indisponible ou un rapprochement à revoir, au lieu de produire une conclusion apparemment certaine. Les analyses détaillées restent consultables lorsque leur calcul est possible.

## 2. Préparer une étude générique

1. Créer un dossier pour le produit et la période de travail.
2. Déposer la composition, la série de NAV et les carnets d’ordres nécessaires. Conserver une copie datée des fichiers d’origine.
3. Détecter le dossier, puis vérifier les rôles de fichiers proposés. Une détection n’est pas une validation économique des données.
4. Renseigner le produit, la devise de NAV, le benchmark et les frais connus. Une valeur de frais absente reste une information manquante ; elle ne prouve pas l’absence de frais.
5. Fournir `params.termsheet_positions` pour reconstruire le panier initial et calculer le Buy & Hold. Ce panier du manifeste prévaut sur un fichier de panier différent laissé dans le dossier.
6. Choisir les blocs nécessaires. Une analyse reposant uniquement sur la NAV ne requiert plus systématiquement un carnet et un FIFO.
7. Facultativement saisir `params.as_of` dans le manifeste, au format `YYYY-MM-DD`. À défaut, l’arrêté est la dernière date de NAV. Si la date demandée tombe entre deux NAV, la dernière NAV antérieure devient l’arrêté effectif, visible dans le résultat.

### Formats actuellement pris en charge

- **Composition** : JSON d’export dans `data.products.items[0]`, avec devise du produit, `netAssetValue`, encours et composants. L’extension peut être `.txt`.
- **NAV** : CSV avec colonnes `Date`, `Price`, et éventuellement `Outstanding quantity`. Dates `DD.MM.YYYY`, `YYYY-MM-DD` ou `MM/DD/YYYY`. La NAV doit être positive et finie, les dates uniques ; un encours explicite peut être zéro.
- **Ordres** : JSON `data.orders.items[]`. Les états exécutés reconnus sont Done, Executed, Filled et Completed. La quantité exécutée signée fait foi. Une quantité commandée ne remplace jamais une quantité exécutée nulle. Prix d’exécution et date valides sont requis pour une exécution.
- **FX d’exécution** : `usedFxRate` multiplie le prix local pour donner le prix dans la devise du produit. Il peut être omis uniquement si la devise d’exécution est explicitement celle du produit.
- **Panier initial** : ISIN, nom, poids en %, quantité par certificat, devise et fixing éventuel. Les poids doivent être finis, positifs ou nuls, sans ISIN dupliqué et totaliser au plus 100 %. Le reliquat est du cash dans la devise du produit.

Le format d’import reste un format d’export déterminé. « Générique » signifie utilisable pour différents AMC avec ces données, pas un lecteur universel de tous les formats des émetteurs. Un autre format nécessite un adaptateur explicite.

## 3. Déroulement du calcul

```text
Manifeste validé et empreintes des fichiers
                ↓
NAV contrôlée → arrêté effectif
                ↓
Ordres sélectionnés, exécutés, datés au plus tard à l’arrêté
                ↓
Cours, FX et splits → même arrêté et unités compatibles
                ↓
Blocs demandés → calcul, indisponibilité explicite ou bloc non demandé
                ↓
Rapprochement positions / NAV + limites des données
                ↓
Scores descriptifs, inférence éventuelle, couverture documentaire
                ↓
Résultat versionné → compléments → revue → rapport → sauvegarde
```

Les fichiers relatifs doivent rester dans le dossier d’étude. Un motif ambigu ou un fichier absent est rejeté. Une sélection vide ne déclenche pas une nouvelle recherche implicite des carnets. Les empreintes sont comparées avant et après calcul : si un fichier change pendant l’étude, il faut relancer.

### Dates et devises

Les prix et changes recherchés à une date sont les derniers disponibles **à cette date ou avant**, dans une tolérance de sept jours calendaires. Une donnée postérieure n’est pas utilisée pour remplir un trou antérieur. Une donnée trop ancienne ou un change manquant rend le calcul concerné indisponible.

Le FIFO, E, H, I et les compléments utilisent l’arrêté NAV. H exclut les ordres dont la fenêtre future de trente jours calendaires n’est pas entièrement observable à l’arrêté. I utilise des dates communes titre/benchmark et une devise commune USD. J convertit le benchmark USD dans la devise du produit. A convertit une NAV non-USD en USD avant la régression sur facteurs USD ; les résultats factoriels correspondent donc à cette devise d’analyse, indiquée dans le résultat.

### Cours, unités et rapprochement

Deux usages sont séparés : les rendements totaux ajustés servent au Buy & Hold et à la sélection ; les cours hors dividendes servent aux prix d’exécution, aux lots FIFO et au timing. Les téléchargements explicites conservent `close` et, lorsque disponible, `price_close`. Les anciens parquets restent lisibles ; le calcul nécessitant des cours hors dividendes peut les récupérer séparément.

Les splits intervenus jusqu’à l’arrêté ajustent les quantités et prix des ordres, en conservant le notionnel. Les splits postérieurs à l’arrêté ne doivent pas modifier la valorisation historique. Le panier initial est dimensionné à partir du budget de chaque ligne et d’un prix initial dans la devise du produit ; la décomposition locale/FX est conservée. Ce dimensionnement à partir de poids reste une reconstruction, à comparer aux quantités du dépositaire.

Le mode strict est le défaut des nouveaux manifestes. Le mode synthétique reste possible lorsqu’il est demandé explicitement ; il produit une reconstruction estimée et une revue requise. Des quantités non rapprochées, un cours manquant ou un écart de NAV dépassant la tolérance indicative d’un point de base d’AUM empêchent la publication d’un score global sans réserve. La différence de date entre relevé de composition et arrêté est également signalée.

Les dividendes encaissés, retenues fiscales, autres opérations sur titres, frais réellement prélevés et mouvements de trésorerie ne sont pas reconstitués comme un grand livre exhaustif. Les P&L sur prix ne deviennent donc pas une attribution complète de NAV par simple changement de libellé. Le contrôle de rapprochement sert précisément à détecter cette limite. Un remboursement complet conserve un encours et un AUM nuls ; il ne reconstitue pas artificiellement les parts précédentes.

### Statistiques et interprétation

- Drawdown : la perte dès le premier rendement est incluse.
- Downside deviation : racine de la moyenne des carrés des rendements sous une cible nulle, sur toutes les observations.
- Rendements cinq et vingt-et-un séances : composition multiplicative, pas somme.
- Calmar : rendement composé annualisé sur drawdown. Le taux sans risque nul des ratios descriptifs de J est explicite.
- Annualisation quotidienne : une fréquence médiane supérieure à un jour calendaire ou une interruption de plus de sept jours est rejetée pour A/J. Les NAV mensuelles demandent une méthode séparée, pas une annualisation 252 appliquée par défaut.
- Les rendements fournis sont comparés aux rendements dérivés des NAV, avec une tolérance de 1 bp ; les niveaux NAV font foi.
- Facteurs : rang et taille d’échantillon contrôlés ; covariance HAC, cinq retards maximum ; régression benchmark uniquement sur ses observations disponibles. Une date de fin des facteurs antérieure à la NAV est signalée.
- H/I : les répétitions par titre ne sont pas assimilées à autant d’échantillons indépendants. Le test porte sur les moyennes par titre, avec au moins dix titres et une variance exploitable. Les p-values sont exploratoires : cette règle n’élimine pas toute dépendance entre titres ni les effets de sélection.
- H : le repère 0,5 est géométrique. Il n’est pas présenté comme une stratégie aléatoire simulée.
- Score global : minimum quatre dimensions et 75 % des poids de base, qualité contrôlée ; A/J exigent 120 observations pour contribuer et H/I une couverture minimale de 60 % avec inférence disponible. Les pondérations restent heuristiques, sans calibration commerciale de « talent ».
- « Couverture documentaire » remplace la confiance arbitraire : elle inclut les blocs demandés indisponibles à zéro. Elle n’est ni une probabilité de compétence, ni une probabilité de succès futur.

E compare la NAV nette à un panier passif brut avec cash non rémunéré. La différence de frais est explicitement conservée et E ne contribue pas au score global tant que les coûts ne sont pas comparables. F est une explication factorielle ajustée sur le même échantillon, pas un portefeuille négociable validé hors échantillon. G est une simulation statique sur proxies sectoriels : ses effets se rapprochent de son propre benchmark reconstruit. Le rendement du benchmark coté et l’écart au proxy sont exposés séparément.

## 4. Compléments, synthèse et archivage

Les calculs d’attribution et de chocs relisent les ordres figés dans le résultat, sans rescanner les carnets du dossier. Pour une ancienne sauvegarde sans ordres figés, il faut relancer l’étude avant ces calculs.

Un nouveau calcul ou le chargement d’une autre étude invalide les anciens compléments. Les réponses asynchrones tardives sont ignorées. La synthèse IA est associée à l’empreinte de l’étude ; les informations de génération et le texte retenu sont sauvegardés avec les compléments. Les consignes IA exigent de distinguer faits, hypothèses, données absentes et conclusions conditionnelles. La validation humaine du texte reste nécessaire.

Séquence conseillée :

1. Calculer et examiner les avertissements et les rapprochements.
2. Calculer les compléments souhaités.
3. Générer ou rédiger la synthèse, puis la relire.
4. Renseigner le cabinet et le client du rapport.
5. Exporter le PDF. Le tableau de couverture sauvegardé est repris sans recalcul opportuniste.
6. **Sauvegarder après l’export** pour conserver les octets exacts du PDF et son SHA-256, en plus des résultats et des compléments. Une nouvelle sauvegarde crée une nouvelle version.
7. Recharger la version puis utiliser « Télécharger le PDF archivé » pour obtenir les mêmes octets, sans régénération.

L’archive conserve le dernier PDF exporté avant sauvegarde. Si le texte ou les paramètres d’export changent, réexporter puis sauvegarder une nouvelle version. Une ancienne étude reste consultable ; ses chiffres ne sont pas automatiquement migrés ni recalculés.

API utiles, avec contrôle du propriétaire :

- `GET /api/amc/studies/{id}` : version complète.
- `GET /api/amc/studies/{id}/archive` : JSON de la version, compléments et PDF éventuel ; SHA-256 du fichier dans `X-Content-SHA256`.
- `GET /api/amc/studies/{id}/compare/{other_id}` : différences de résultats entre deux versions accessibles au même utilisateur.

La provenance contient version de méthode, date UTC, manifeste, empreintes des fichiers, ordres/NAV figés et empreintes des séries de marché instrumentées. **Une empreinte ne remplace pas la donnée source** : conserver les fichiers et les caches nécessaires à une reproduction indépendante. L’archivage applicatif n’est pas un stockage réglementaire WORM ni une signature par un tiers de confiance.

## 5. Accès et exploitation

Les dossiers sont accessibles à l’administrateur ; un utilisateur standard est limité à `STRUCTURA_STUDIES_ROOT/<user_id>/`. L’absence de configuration empêche la lecture arbitraire du disque par un compte standard. Les imports, suppressions et mises à jour manuelles du magasin de prix partagé, ainsi que le rafraîchissement des facteurs, sont réservés aux administrateurs. Les sauvegardes restent privées à leur propriétaire.

L’inscription publique est désactivée par défaut. `STRUCTURA_ALLOW_REGISTRATION=1` la réactive explicitement si l’installation le souhaite. Les origines CORS par défaut sont localhost/127.0.0.1 sur les ports 5173 et 8000 ; les autres origines doivent figurer dans `STRUCTURA_CORS_ORIGINS`, séparées par des virgules.

Exemple PowerShell avant de démarrer le backend :

```powershell
$env:STRUCTURA_STUDIES_ROOT = 'D:\StructuraStudies'
$env:STRUCTURA_CORS_ORIGINS = 'https://structura.exemple.fr'
```

Bornes actuelles : 20 Mo par fichier source ou upload, 20 000 NAV, 100 fichiers de carnet, 500 positions initiales et 30 Mo par sauvegarde applicative. Deux calculs principaux Studies simultanés au maximum par processus ; un troisième reçoit 429 et peut être relancé. Ce mécanisme ne constitue pas une file de tâches durable multi-serveurs. Les caches de benchmark H/I/J et de splits expirent après une heure ; les prix en parquet restent des sources datées à contrôler et rafraîchir.

Le redémarrage du backend appartient à Philippe. Aucun serveur n’a été lancé ou redémarré par ce chantier. Aucun commit ni push automatique.

## 6. Sauvegarde et restauration

Le script `backend/scripts/studies_backup.py` réalise une sauvegarde SQLite cohérente via l’API de backup, contrôle l’intégrité, ajoute les dossiers explicitement choisis et calcule leurs empreintes. Il ne modifie pas la base source. La restauration écrit exclusivement dans un **nouveau dossier**, après vérification des empreintes et des chemins.

Depuis la racine du dépôt, en adaptant les chemins :

```powershell
.venv/Scripts/python.exe backend/scripts/studies_backup.py backup --database backend/data/structura.db --archive D:/Sauvegardes/structura-20260920.zip --source D:/StructuraStudies --source backend/data/underlying_prices --source backend/data/fx_rates --source backend/data/ff_factors
.venv/Scripts/python.exe backend/scripts/studies_backup.py restore --archive D:/Sauvegardes/structura-20260920.zip --destination D:/RecetteRestauration/structura-20260920
```

Créer le répertoire parent de l’archive au préalable. Ne pas modifier les dossiers sources pendant leur copie ; seule la cohérence SQLite est transactionnelle. Contrôler la restauration dans un environnement séparé. Le remplacement de la base de production n’est pas automatisé. Les clés d’API et secrets de l’installation ne sont pas inclus par défaut. Le test de restauration de ce chantier utilise une base temporaire fictive, jamais les données réelles.

## 7. Correspondance avec les dix-huit constats

| Point | Traitement livré |
|---|---|
| S01 | Arrêté NAV commun, ordre futur exclu, cours/FX causaux, fenêtres H/I et événements K bornés. |
| S02 | Aucun change absent assimilé à 1 ; données inconnues signalées. |
| S03 | Benchmark obligatoire pour I, p-value cohérente, regroupement par titre, limites d’inférence explicites. |
| S04 | Drawdown initial, downside deviation, rendements composés, Calmar et convention RF corrigés. |
| S05 | Encours nul conservé, absence initiale non remplie avec un encours futur, rapprochement à remboursement complet. |
| S06 | Normalisation commune des exécutions, quantité exécutée seule, doublons contradictoires rejetés. |
| S07 | Carnets, NAV et panier du manifeste transmis au FIFO ; compléments sur ordres figés. |
| S08 | Cours hors dividendes distincts des rendements totaux, splits bornés, FX initial conservé, contrôle des positions et du rapprochement ; absence de grand livre exhaustif explicitée. |
| S09 | Aucune fabrication de rendement benchmark avant régression. |
| S10 | Brinson réconcilié avec son proxy sectoriel, cash conservé au panier initial, absence de remplissage par des cours futurs, devise commune et écart au benchmark coté exposé. |
| S11 | Couverture documentaire observable, seuils de publication MSS, score déclaré heuristique. |
| S12 | Invalidation des compléments, protection contre réponses tardives, sauvegarde/restauration des résultats et de la génération IA. |
| S13 | Dossiers utilisateurs confinés, prix partagés administrés, CORS explicite et inscription publique opt-in. |
| S14 | NAV convertie en USD pour A, contrôle de fréquence/rang/échantillon, HAC et avertissement sur facteurs anciens. |
| S15 | Cash passif conservé ; frais différents explicites ; F/H/D présentés comme analyses descriptives, sans promesse de réplication investissable ni d’intention révélée. |
| S16 | Bornes d’entrée, NAV seule possible, statut des blocs, périmètre historique des titres et concurrence limitée. |
| S17 | Cabinet/client configurables, couverture non recalculée dans le PDF, consignes IA révisées, provenance et PDF exact archivable. |
| S18 | Tests génériques hors réseau, scénario intégré, tests d’ownership, PDF et sauvegarde/restauration ; processus d’exploitation documenté. |

Ce tableau décrit le traitement des défauts et des risques identifiés. Il ne signifie pas que toutes les extensions évoquées dans l’audit ont été développées : attribution dynamique multi-périodes avec grand livre de flux, panier de réplication négociable testé hors échantillon, calibration empirique des scores, file de tâches distribuée et archivage réglementaire spécialisé restent des développements distincts. Les droits de redistribution des données et le contrat du partenaire nécessitent un accord externe ; aucune modification logicielle ne les confère.

## 8. Recette et commandes de vérification

Depuis la racine du dépôt :

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_amc_studies.py backend/tests/test_ai_workbench.py -q
.venv/Scripts/python.exe -m pytest backend/tests/test_remediation_2026_08_02.py -k "secret or signing or unknown_currency" -q
```

Depuis `frontend/` :

```powershell
npm run build
```

Résultats de recette : 54 tests Studies/IA et 5 tests ciblés auth/FX réussis ; 194 tests frontend réussis et build de production généré. Les avertissements Vite concernent les imports mixtes de modules existants.

Les tests couvrent des données fictives USD/EUR/JPY, le remboursement complet, les cours futurs, les doublons, le cash Buy & Hold, la décomposition prix/FX, les splits, Brinson, les scores incomplets, le périmètre de fichiers, la concurrence, la propriété des sauvegardes, l’export PDF et la restauration SQLite. Les appels marché sont remplacés par des fixtures déterministes. La suite backend entière n’est pas exécutée, conformément à `CLAUDE.md`.

Pour la recette fonctionnelle après redémarrage : ouvrir une ancienne étude, lancer une étude fictive ou une copie de travail, inspecter l’arrêté et les avertissements, changer de produit, vérifier la remise à zéro des compléments, produire le rapport avec deux noms libres, sauvegarder, recharger et télécharger le PDF archivé. Aucun résultat sur des données fictives ne certifie à lui seul le rapprochement des données réelles de tous les émetteurs.
