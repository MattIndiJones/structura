# Integration FRED dans STRUCTURA

> Document de cadrage pour un chantier futur. Aucune integration FRED n'est
> implementee a la date de redaction.

- Date de l'etude : 2026-08-29
- Site etudie : [FRED, Federal Reserve Bank of St. Louis](https://fred.stlouisfed.org/)
- Objectif : identifier les donnees FRED qui pourraient ameliorer le pricing,
  le risque, les scenarios et les backtests de STRUCTURA.

## 1. Conclusion

FRED est surtout utile a STRUCTURA comme **source macroeconomique et source de
facteurs de risque historiques**. Il complete Yahoo Finance, qui fournit deja
les cours, volatilites realisees, dividendes et correlations des sous-jacents.

Les quatre usages prioritaires sont :

1. enrichir la VaR et les scenarios historiques avec les mouvements de taux,
   de change, de volatilite implicite et de spreads de credit ;
2. construire un tableau de regime macro et financier ;
3. utiliser les vintages ALFRED pour des backtests sans biais d'anticipation ;
4. controler la coherence des hypotheses de taux et d'inflation saisies dans
   STRUCTURA.

FRED ne doit pas devenir la source de production de la courbe de pricing. Les
taux directeurs, rendements Treasury et rendements obligataires mensuels ne
constituent pas une courbe OIS/ESTR complete et executable. Ils peuvent servir
de reference, de controle ou de facteur de stress, mais pas remplacer une
source ECB/ESTR ou un fournisseur de donnees de marche adapte au pricing.

## 2. Etat actuel de STRUCTURA

### 2.1 Donnees deja disponibles

`backend/app/services/market_data.py` charge aujourd'hui via Yahoo Finance :

- les cours historiques ;
- les volatilites realisees ;
- les rendements de dividende ;
- les correlations historiques ;
- les cours de reference et les operations sur titres.

Ces donnees sont pertinentes pour les actions, indices, matieres premieres,
devises et cryptomonnaies, mais elles ne forment pas un referentiel macro
homogene.

### 2.2 VaR et scenarios actuels

`backend/app/core/var_engine.py` genere des scenarios historiques a partir des
variations des sous-jacents. Il reconstruit egalement des approximations de
chocs de volatilite realisee et de correlation.

Le type `MarketScenario` possede deja un champ `dr_frac`, mais les scenarios
historiques produits par `generate_historical_scenarios()` ne lui affectent pas
de choc de taux. Le taux reste donc neutre dans ces scenarios.

Les presets de `frontend/src/stores/portfolios.js` sont actuellement statiques :

- crash actions ;
- rally actions ;
- choc de volatilite ;
- choc de taux ;
- choc de correlation ;
- crise systemique.

FRED permettrait de completer ces presets par des scenarios observes et dates.

### 2.3 Capacites de pricing deja presentes

Les schemas de STRUCTURA portent deja :

- une courbe de taux `yield_curve` ;
- une volatilite de taux `sigma_r` ;
- un parametre de retour a la moyenne `a_r` ;
- une courbe de financement `funding_curve` ;
- un spread de financement `funding_spread`.

L'integration FRED peut donc alimenter des controles, des historiques et des
scenarios sans modifier les conventions fondamentales du moteur.

## 3. Catalogue initial de series

Les identifiants ci-dessous doivent former une liste blanche explicite. Chaque
serie doit conserver sa source, ses unites, sa frequence, ses droits et sa date
de mise a jour.

| Priorite | Serie | Frequence | Usage envisage | Limite principale |
|---|---|---:|---|---|
| P1 | [`ECBDFR`](https://fred.stlouisfed.org/series/ECBDFR) | Quotidienne, 7 jours | Regime monetaire EUR, controle du taux court, scenarios BCE | Taux directeur, pas une courbe ESTR |
| P1 | [`DGS2`](https://fred.stlouisfed.org/series/DGS2) | Quotidienne | Chocs de taux USD court/moyen, pente de courbe | Rendement Treasury, pas taux swap/OIS |
| P1 | [`DGS10`](https://fred.stlouisfed.org/series/DGS10) | Quotidienne | Chocs de taux long USD et pente 2-10 ans | Rendement Treasury, pas courbe executable |
| P1 | [`SOFR`](https://fred.stlouisfed.org/series/SOFR) | Quotidienne | Regime de taux USD et controle du taux monetaire | Ne donne pas a lui seul la courbe SOFR |
| P1 | [`DEXUSEU`](https://fred.stlouisfed.org/series/DEXUSEU) | Quotidienne | Historique EUR/USD et scenarios FX | Cotation USD pour 1 EUR a normaliser explicitement |
| P1 | [`VIXCLS`](https://fred.stlouisfed.org/series/VIXCLS) | Quotidienne, cloture | Regime de volatilite, stress et controle de la proxy de vol | VIX concerne le S&P 500, pas chaque sous-jacent |
| P1 | [`STLFSI4`](https://fred.stlouisfed.org/series/STLFSI4) | Hebdomadaire | Classification du stress financier | Indicateur principalement centre sur les marches USD |
| P2 | [`BAMLC0A0CM`](https://fred.stlouisfed.org/series/BAMLC0A0CM) | Quotidienne, cloture | Spread corporate Investment Grade | Donnee ICE sous droits ; historique FRED limite |
| P2 | [`BAMLH0A0HYM2`](https://fred.stlouisfed.org/series/BAMLH0A0HYM2) | Quotidienne, cloture | Spread High Yield et regime de credit | Donnee ICE sous droits ; historique FRED limite |
| P2 | [`T10YIE`](https://fred.stlouisfed.org/series/T10YIE) | Quotidienne | Anticipation d'inflation US a 10 ans | Mesure de marche US, pas inflation zone euro |
| P2 | [`T5YIFR`](https://fred.stlouisfed.org/series/T5YIFR) | Quotidienne | Inflation forward 5 ans dans 5 ans | Mesure construite a partir de Treasuries US |
| P2 | [`CP0000EZ19M086NEST`](https://fred.stlouisfed.org/series/CP0000EZ19M086NEST) | Mensuelle | HICP zone euro, regimes inflationnistes | Publication mensuelle et revisions possibles |
| P3 | [`IRLTLT01EZM156N`](https://fred.stlouisfed.org/series/IRLTLT01EZM156N) | Mensuelle | Reference macro du taux souverain 10 ans zone euro | Trop agregee et trop lente pour le pricing |

### Extension eventuelle de la courbe Treasury

Apres verification individuelle des metadonnees FRED, la liste blanche pourra
etre etendue aux autres maturites Treasury, par exemple 1 mois, 3 mois, 6 mois,
1 an, 5 ans, 7 ans, 20 ans et 30 ans. Cette extension servirait a mesurer les
deformations historiques de la courbe USD, pas a construire automatiquement
une courbe de valorisation.

## 4. Cas d'usage recommandes

### 4.1 VaR historique multi-facteurs

C'est le premier usage recommande.

Pour chaque date historique et chaque horizon VaR, STRUCTURA pourrait joindre
aux rendements des sous-jacents :

- la variation de taux sur l'horizon ;
- la variation EUR/USD ;
- la variation du VIX ;
- la variation des spreads IG et HY ;
- le niveau du stress financier.

Le scenario deviendrait conceptuellement :

```text
spot_pct
+ vol_pts
+ corr_delta
+ dr_frac
+ fx_pct
+ credit_spread_delta
+ regime_metadata
```

Le choc de taux doit etre une **variation historique sur l'horizon**, et non la
difference entre un ancien niveau et le niveau actuel :

```text
dr_frac = (taux[t] - taux[t - horizon]) / 100
```

Les series FRED sont exprimees en pourcentage. La division par 100 est donc
necessaire avant d'alimenter le moteur, qui travaille en fraction.

### 4.2 Scenarios historiques nommes

Un catalogue de crises peut etre construit a partir de fenetres historiques
reelles. Chaque scenario conserve :

- la date ou la fenetre historique ;
- les mouvements observes des facteurs ;
- les series sources ;
- la methode d'alignement ;
- la date de recuperation ou le vintage ;
- une description lisible dans l'interface.

Exemples de familles de scenarios :

- crise de liquidite et hausse du stress financier ;
- choc de volatilite actions ;
- choc inflationniste et remontee des taux ;
- choc de credit Investment Grade ou High Yield ;
- forte variation EUR/USD ;
- combinaison systemique spot, vol, correlation, taux et credit.

Ces scenarios doivent completer les presets manuels, pas les supprimer. Le
scenario manuel reste utile pour une sensibilite isolee et reproductible.

### 4.3 Tableau de regime macro et financier

Un panneau de risque peut presenter un regime simple, explicable et date :

- politique monetaire EUR : `ECBDFR` ;
- politique monetaire USD : `SOFR` ;
- pente USD : `DGS10 - DGS2` ;
- inflation anticipee : `T10YIE` ou `T5YIFR` ;
- volatilite : `VIXCLS` ;
- credit : spreads IG et HY ;
- stress global : `STLFSI4` ;
- change : `DEXUSEU`.

`STLFSI4` est construit de sorte que zero represente des conditions financieres
normales. Une valeur positive indique un stress superieur a la moyenne et une
valeur negative un stress inferieur a la moyenne. Il peut servir de signal de
regime, mais ne doit pas etre transforme directement en choc de pricing.

### 4.4 Controle de coherence des hypotheses de marche

FRED peut fournir des bornes ou des references :

- alerter si le taux plat EUR est tres eloigne du taux directeur BCE ;
- comparer la direction de la courbe saisie au regime Treasury observe ;
- afficher l'inflation courante ou anticipee a cote d'un scenario inflation ;
- signaler qu'un stress de taux est faible par rapport aux variations
  historiques recentes.

Ces controles doivent rester informatifs. Une serie FRED ne doit jamais
ecraser silencieusement une hypothese saisie, une courbe de contrepartie ou un
snapshot de marche attache a un deal.

### 4.5 Backtests sans biais d'anticipation avec ALFRED

ALFRED archive les versions successives des donnees FRED. Il permet de demander
ce qui etait effectivement connu a une date historique, avant les revisions
ulterieures.

C'est indispensable pour :

- selectionner un regime macro dans un backtest ;
- tester une strategie conditionnee par l'inflation ou le PIB ;
- reproduire un tableau de risque tel qu'il aurait ete affiche a l'epoque ;
- eviter d'utiliser retrospectivement une valeur revisee ou publiee plus tard.

Une observation macro ne devient disponible qu'a sa date de publication. Il ne
faut pas l'aligner sur sa seule periode economique, qui peut etre anterieure de
plusieurs semaines ou mois.

## 5. Architecture cible

### 5.1 Service backend separe

Creer un service dedie, par exemple :

```text
backend/app/services/macro_data.py
```

Il ne faut pas melanger cette logique avec le service Yahoo : les instruments,
frequences, droits, conventions de date et politiques de cache sont differents.

Interface de service envisagee :

```python
get_series(series_id, start=None, end=None, vintage=None)
get_latest(series_id)
get_panel(series_ids, start, end, vintage=None)
get_series_metadata(series_id)
refresh_allowlisted_series()
```

### 5.2 Configuration

La cle doit rester cote backend :

```text
FRED_API_KEY=<cle API FRED>
```

Elle ne doit jamais etre envoyee au front, stockee dans un deal ou ecrite dans
les logs.

La liste blanche doit definir pour chaque serie :

```text
series_id
label
category
expected_units
expected_frequency
transform
cache_ttl
license_note
enabled
```

### 5.3 API interne envisagee

Les routes suivantes sont suffisantes pour un premier lot :

```text
GET  /api/macro/series
GET  /api/macro/series/{series_id}
GET  /api/macro/latest
GET  /api/macro/regime
POST /api/admin/macro/refresh
```

La route de rafraichissement doit etre reservee a l'administration. Les routes
utilisateur ne doivent exposer que les series autorisees.

### 5.4 Persistance et provenance

Chaque observation conserve au minimum :

```text
series_id
observation_date
value
units
frequency
source
release
realtime_start
realtime_end
vintage_date
fetched_at
```

Deux options sont acceptables :

- tables SQL pour faciliter les recherches et les jointures ;
- fichiers Parquet par serie, coherents avec le Price Store existant.

La provenance doit rester visible jusque dans les exports ou rapports qui
utilisent la donnee.

### 5.5 Cache et disponibilite

FRED ne doit jamais etre appele pendant chaque pricing Monte-Carlo.

Politique possible :

- series quotidiennes : rafraichissement planifie une ou quelques fois par jour ;
- serie hebdomadaire : rafraichissement quotidien ou le jour de publication ;
- series mensuelles : rafraichissement selon le calendrier de publication ;
- cache local persistant ;
- dernier succes conserve si FRED est temporairement indisponible ;
- affichage explicite de l'age de la donnee.

Une panne FRED ne doit pas bloquer le pricing. Elle doit desactiver ou marquer
comme indisponibles les fonctions macro qui en dependent.

## 6. Regles de qualite des donnees

### 6.1 Valeurs manquantes

L'API FRED represente une valeur manquante par `.`. Cette valeur doit devenir
`None` ou `NaN`, jamais zero.

### 6.2 Frequences

Les frequences quotidiennes, hebdomadaires et mensuelles ne doivent pas etre
fusionnees sans convention explicite.

- Un jour ferme peut reprendre la derniere valeur connue par forward-fill.
- Une publication mensuelle peut rester en vigueur jusqu'a la suivante.
- Le backward-fill est interdit, car il injecte une information future.
- La date d'observation et la date de disponibilite doivent rester distinctes.

### 6.3 Unites et sens de cotation

Les metadonnees doivent etre controlees a chaque rafraichissement :

- les taux FRED sont generalement en pourcentage ;
- `DEXUSEU` est cote en dollars pour un euro ;
- `VIXCLS` est un indice, pas une volatilite directement exprimee en fraction ;
- les OAS sont exprimes en pourcentage, pas automatiquement en points de base.

Une modification inattendue des unites ou de la frequence doit mettre la serie
en erreur plutot que modifier silencieusement les calculs.

### 6.4 Donnees revisees

Pour une vue courante, utiliser la derniere version FRED.

Pour un backtest ou une reproduction historique, utiliser un vintage ALFRED ou
une periode temps-reel explicite. Le choix doit etre stocke avec le resultat.

### 6.5 Droits et attribution

FRED agrege des donnees provenant de plusieurs producteurs. Les droits ne sont
pas identiques pour toutes les series.

- Les pages FRED doivent etre consultees pour chaque nouvelle serie.
- Les mentions de source et les citations recommandees doivent etre conservees.
- Les series ICE BofA et VIX ont des mentions de droits specifiques.
- A partir d'avril 2026, les series ICE BofA consultees annoncent seulement
  trois ans d'observations disponibles sur FRED.
- Un export ou un rapport ne doit pas republier une serie complete sans verifier
  ses conditions d'utilisation.

## 7. Ce que FRED ne doit pas faire

### 7.1 Ne pas construire automatiquement la courbe de pricing EUR

`ECBDFR` est un taux de facilite de depot. La serie 10 ans zone euro disponible
dans le catalogue initial est mensuelle et agregee. Ces deux points ne suffisent
pas pour bootstrapper une courbe OIS/ESTR de production.

Pour le pricing, privilegier :

- une source ECB/ESTR suffisamment granulaire ;
- des taux swaps/OIS fournis par un vendor ;
- une courbe utilisateur ou contrepartie versionnee ;
- des conventions explicites de day count, interpolation et calendrier.

FRED peut seulement produire un indicateur de coherence ou un fallback manuel
clairement signale comme non executable.

### 7.2 Ne pas assimiler le VIX a la volatilite de tous les actifs

Le VIX mesure l'anticipation de volatilite a court terme derivee des options sur
indice actions americain. Il est utile comme facteur de regime ou comme proxy de
stress, mais ne remplace pas la volatilite implicite propre a un sous-jacent.

### 7.3 Ne pas assimiler un indice de credit au spread d'un emetteur

Les OAS IG et HY representent des indices larges. Ils peuvent choquer un bucket
de credit ou un spread de financement, mais ils ne donnent ni la probabilite de
defaut ni le spread specifique d'une banque ou d'un emetteur.

### 7.4 Ne pas rendre le pricing dependant du reseau

Un appel FRED ne doit pas se trouver dans la boucle de pricing, de Greeks, de
MTF ou de comparaison de variantes. Le moteur consomme un snapshot local et
versionne.

## 8. Feuille de route

### Phase 0 - Gouvernance

- creer la cle API et definir son stockage ;
- valider les droits et attributions de chaque serie ;
- valider la liste blanche initiale ;
- choisir SQL ou Parquet pour le cache persistant ;
- documenter les unites et conventions de date.

### Phase 1 - Connecteur et catalogue

- implementer `macro_data.py` ;
- implementer la gestion des erreurs et de `.` ;
- stocker metadonnees et observations ;
- ajouter les routes de lecture et de rafraichissement ;
- afficher fraicheur, source et disponibilite dans l'administration.

Cette phase ne modifie aucun calcul de pricing ou de risque.

### Phase 2 - Tableau de regime

- produire les indicateurs taux, pente, inflation, VIX, credit, stress et FX ;
- afficher date, source et fraicheur ;
- definir des seuils versionnes et explicables ;
- conserver la valeur brute derriere chaque classification.

### Phase 3 - VaR et scenarios

- enrichir `MarketScenario` avec taux, FX et credit si necessaire ;
- aligner les facteurs FRED avec les dates des sous-jacents ;
- injecter `dr_frac` dans les scenarios historiques ;
- comparer la proxy de volatilite realisee au VIX sans la remplacer aveuglement ;
- ajouter des scenarios historiques nommes ;
- mesurer l'impact sur VaR et Expected Shortfall.

### Phase 4 - ALFRED et backtests

- prendre en charge `vintage_date` et les periodes temps-reel ;
- stocker la date de disponibilite de l'information ;
- rejouer les signaux macro avec les seules informations connues a l'epoque ;
- ajouter des tests anti-look-ahead.

### Phase 5 - Extensions

- controle de coherence des courbes de taux ;
- produits ou rapports lies a l'inflation ;
- stress de funding par bucket de credit ;
- calendrier de publications macro ;
- extension a d'autres series apres revue de qualite et de droits.

## 9. Strategie de tests

### Tests unitaires du connecteur

- reponse JSON valide ;
- valeur manquante `.` ;
- valeur non numerique ;
- changement inattendu d'unites ;
- pagination ;
- timeout et erreur HTTP ;
- cache frais, expire et rafraichi ;
- preservation du dernier succes apres une panne ;
- cle absente ou invalide ;
- serie hors liste blanche.

### Tests de dates

- absence de backward-fill ;
- forward-fill uniquement apres disponibilite ;
- week-ends et jours feries ;
- observation mensuelle publiee plus tard ;
- vintage ALFRED ;
- absence de fuite d'information future.

### Tests de scenarios

- conversion pourcentage vers fraction ;
- sens de `DEXUSEU` ;
- calcul de la variation de taux sur l'horizon ;
- reproductibilite d'un scenario historique ;
- scenario sans serie disponible ;
- aucune modification du pricing de base sous un choc nul ;
- coherence entre scenario deal, portefeuille et global.

### Tests de non-regression

- Yahoo reste la source des cours et volatilites realisees existants ;
- une panne FRED ne bloque pas `/price` ;
- aucune hypothese utilisateur n'est ecrasee silencieusement ;
- les snapshots attaches aux deals restent reproductibles ;
- les exports affichent la provenance et le vintage.

## 10. Criteres d'acceptation du premier lot

Le premier lot peut etre considere termine lorsque :

1. les series P1 sont chargees depuis le backend avec une cle non exposee ;
2. les observations et metadonnees sont mises en cache et versionnees ;
3. les valeurs manquantes, unites et frequences sont controlees ;
4. une panne FRED ne bloque aucune fonction de pricing existante ;
5. l'administration affiche la source, la derniere observation et sa fraicheur ;
6. un endpoint restitue un snapshot macro coherent et date ;
7. la provenance accompagne tout indicateur calcule ;
8. les tests anti-look-ahead sont verts ;
9. aucune serie FRED n'est encore injectee automatiquement dans une courbe de
   pricing de production.

## 11. Decisions a prendre avant implementation

- Le premier usage doit-il etre le tableau de regime ou la VaR historique ?
- Quelle source executable sera utilisee a terme pour la courbe EUR ?
- Faut-il stocker les observations en SQL ou dans le Price Store Parquet ?
- Quels utilisateurs peuvent rafraichir ou ajouter une serie ?
- Quelles series sous droits peuvent apparaitre dans les exports et PDF ?
- Comment mapper un choc de credit indiciel au funding d'un emetteur ?
- Le scenario FX doit-il choquer directement les sous-jacents ou devenir un
  facteur distinct dans `MarketScenario` ?
- Quels seuils de regime doivent etre fixes, calibres ou administrables ?

## 12. Documentation officielle

- [Vue d'ensemble de l'API FRED](https://fred.stlouisfed.org/docs/api/fred/overview.html)
- [Observations d'une serie](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)
- [API FRED version 2](https://fred.stlouisfed.org/docs/api/fred/v2/)
- [Periodes temps-reel](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)
- [Dates de vintage](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html)
- [FRED et ALFRED](https://fred.stlouisfed.org/docs/api/fred/fred_vs_alfred.html)
- [Presentation d'ALFRED](https://fred.stlouisfed.org/docs/api/fred/alfred.html)
- [Dates de publication](https://fred.stlouisfed.org/docs/api/fred/release_dates.html)

## 13. Recommandation finale

Lors de la reprise, commencer par un connecteur FRED strictement en lecture,
avec cache et provenance, puis l'utiliser dans un tableau de regime. Une fois
les dates, unites et vintages fiabilises, enrichir la VaR historique avec les
variations de taux et de change. Cette progression apporte rapidement de la
valeur tout en evitant de melanger une source macro de reference avec une source
de marche executable pour le pricing.
