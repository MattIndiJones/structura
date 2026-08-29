# Sources gratuites de taux et de donnees options pour STRUCTURA

> Document de cadrage pour un chantier futur. Aucune nouvelle source de
> donnees n'est integree a STRUCTURA a la date de redaction.

- Date de l'etude : 2026-08-29
- Objectif : identifier des alternatives et complements a FRED pour les taux,
  les courbes, les scenarios historiques et les prix d'options.
- Priorite initiale : taux EUR et USD, puis donnees d'options US et Europe.

## 1. Conclusion

Pour les taux, les meilleures sources gratuites sont les institutions qui
produisent directement les indices et statistiques :

1. **ECB Data Portal** pour EUR, EUR/FX, EURSTR et les courbes souveraines ;
2. **New York Fed** pour SOFR et les taux monetaire USD ;
3. **US Treasury** pour les courbes souveraines nominales et reelles USD ;
4. **BIS**, **Bundesbank**, **Eurostat** et **Bank of Canada** pour completer
   les facteurs de risque et les scenarios macroeconomiques.

Pour les options, il n'existe pas de source gratuite equivalente fournissant
une chaine consolidee, temps reel, avec profondeur historique et droits
d'utilisation commerciale. Les solutions gratuites les plus interessantes
pour un prototype sont :

1. **MarketData.app** pour des chaines US retardees, avec volatilite implicite
   et Greeks selon l'offre disponible ;
2. **ThetaData** pour des prix options EOD et des validations historiques ;
3. **Tradier Sandbox** pour des chaines US retardees ;
4. **Alpaca Basic** pour un flux options indicatif ;
5. **Eurex** pour le referentiel, les volumes et l'open interest europeens.

Les pages de cotations Cboe, CME ou Eurex ne doivent pas etre scrapees sans
autorisation explicite. Une page consultable gratuitement n'est pas
necessairement une API reutilisable par une application.

## 2. Distinctions importantes

Avant d'integrer une source, il faut separer quatre usages :

- **pricing** : courbe de discounting et donnees de marche assez fiables pour
  valoriser un instrument ;
- **calibration** : prix ou volatilites permettant d'ajuster un modele ;
- **risque et scenarios** : historiques permettant de construire des chocs ;
- **controle** : comparaison avec une reference externe officielle.

Une courbe souveraine ECB ou Treasury est utile pour le controle et le risque,
mais ne constitue pas automatiquement une courbe OIS executable. Une courbe de
discounting EURSTR ou SOFR complete exige des instruments de marche adaptes,
des conventions precises et un bootstrap.

## 3. Sources de taux recommandees

| Priorite | Source | Donnees principales | Acces | Usage STRUCTURA |
| --- | --- | --- | --- | --- |
| P1 | [ECB Data Portal](https://data.ecb.europa.eu/help/api/data) | EURSTR, taux directeurs, FX, courbes zero-coupon, forward et par | API SDMX, CSV, JSON | Taux EUR, references, controles et scenarios |
| P1 | [New York Fed](https://www.newyorkfed.org/markets/reference-rates/sofr) | SOFR, SOFR Index, moyennes composees, EFFR, OBFR | API officielle | Taux courts et scenarios USD |
| P1 | [US Treasury](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed) | Courbes nominales et reelles, bills, taux longs | Flux XML | Courbe souveraine et risque USD |
| P2 | [BIS Data Portal](https://data.bis.org/) | Taux directeurs, credit, FX effectif, inflation | SDMX et telechargements | Regimes macro et comparaisons internationales |
| P2 | [Bundesbank](https://www.bundesbank.de/en/statistics/time-series-databases/help-for-sdmx-web-service/web-service-interface-data) | Taux allemands, obligations, FX, donnees macro | API SDMX | Complement EUR et donnees historiques revisees |
| P2 | [Bank of Canada Valet](https://www.bankofcanada.ca/valet-api-how-to/) | CORRA, taux CAD, FX, courbes zero-coupon | API sans cle | Extension future aux produits CAD |
| P3 | [Eurostat](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-introduction) | Inflation, PIB, emploi, indicateurs europeens | API REST et SDMX | Scenarios macroeconomiques |
| P3 | [Banque de France Webstat](https://webstat.banque-france.fr/api-console/explore/v2.1/?flg=fr-fr) | Taux, credit et obligations francaises | API a valider | Complement national |

### 3.1 ECB Data Portal

L'ECB Data Portal est la premiere source a tester pour l'euro. Son service
officiel suit le standard SDMX et permet de filtrer les series par date,
frequence et dimensions.

Donnees utiles :

- EURSTR quotidien ;
- indice EURSTR compose ;
- moyennes composees EURSTR a 1 semaine, 1, 3, 6 et 12 mois ;
- taux directeurs de la BCE ;
- courbes de rendement de la zone euro ;
- taux de change officiels de l'euro ;
- statistiques de marches financiers et de swaps de taux.

Liens utiles :

- [documentation de l'API](https://data.ecb.europa.eu/help/api/data) ;
- [page officielle EURSTR](https://www.ecb.europa.eu/stats/financial_markets_and_interest_rates/euro_short-term_rate/html/index.en.html) ;
- [courbes de rendement de la zone euro](https://www.ecb.europa.eu/stats/financial_markets_and_interest_rates/euro_area_yield_curves/html/index.en.html) ;
- [serie EURSTR quotidienne](https://data.ecb.europa.eu/data/datasets/EST/EST.B.EU000A2X2A25.WT) ;
- [indice EURSTR compose](https://data.ecb.europa.eu/data/datasets/EST/EST.B.EU000A2QQF08.CI).

Les courbes ECB sont publiees par maturite et peuvent servir de reference
officielle. Elles doivent rester identifiees comme des courbes souveraines ou
statistiques, et non comme une courbe OIS directement tradable.

### 3.2 New York Fed

La Federal Reserve Bank of New York administre plusieurs taux de reference
USD et publie les donnees associees.

Donnees utiles :

- SOFR quotidien ;
- SOFR Index ;
- moyennes SOFR composees ;
- Effective Federal Funds Rate ;
- Overnight Bank Funding Rate ;
- Tri-Party General Collateral Rate ;
- Broad General Collateral Rate.

Liens utiles :

- [SOFR](https://www.newyorkfed.org/markets/reference-rates/sofr) ;
- [API de marche de la New York Fed](https://markets.newyorkfed.org/static/docs/markets-api.html) ;
- [portail des donnees de marche](https://www.newyorkfed.org/markets/data-hub).

Cette source est adaptee a la construction des historiques de taux courts USD,
aux controles de donnees et a l'alimentation de chocs de taux observes.

### 3.3 US Treasury

Le Treasury publie des courbes quotidiennes sous forme de flux XML.

Donnees utiles :

- Daily Treasury Par Yield Curve Rates ;
- Daily Treasury Par Real Yield Curve Rates ;
- Daily Treasury Bill Rates ;
- Daily Treasury Long-Term Rates.

Liens utiles :

- [documentation des flux XML](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed) ;
- [taux quotidiens](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve).

Ces donnees sont utiles pour les scenarios USD, les controles de coherence et
la structure par terme sans risque souveraine. Elles ne remplacent pas une
courbe SOFR OIS de production.

### 3.4 BIS

La Bank for International Settlements fournit des series internationales
harmonisees et une API SDMX.

Usages possibles :

- historique des taux directeurs de plusieurs pays ;
- taux de change effectifs ;
- credit au secteur prive ;
- prix immobiliers ;
- indicateurs de liquidite et de stabilite financiere ;
- construction de regimes macro et de stress internationaux.

Liens utiles :

- [BIS Data Portal](https://data.bis.org/) ;
- [presentation des API et telechargements](https://www.bis.org/statistics/dataportal/index.htm) ;
- [conditions d'utilisation](https://www.bis.org/terms_statistics.htm).

### 3.5 Autres sources officielles

**Bundesbank** peut completer les donnees ECB avec des series allemandes et une
base macroeconomique en temps reel. Cette derniere est interessante pour des
backtests qui doivent tenir compte des revisions de donnees.

**Eurostat** convient aux scenarios d'inflation, d'activite et d'emploi. Les
API donnent principalement la version courante des jeux de donnees et ne
doivent pas etre supposees conserver tous les millesimes historiques.

**Bank of Canada Valet** est une excellente extension future pour le CAD : API
gratuite sans cle, CORRA, taux, change et courbes zero-coupon canadiennes.

**Banque de France Webstat** merite un proof of concept. Les contraintes
d'inscription, d'authentification et de reutilisation devront etre confirmees
avant de retenir cette source.

### 3.6 EURIBOR et EMMI

Les taux EURIBOR sont administres par l'European Money Markets Institute.
L'acces gratuit officiel est retarde et soumis a des conditions de
reutilisation.

- [consultation des taux EURIBOR](https://www.emmi-benchmarks.eu/benchmarks/euribor/rate/) ;
- inscription requise pour certaines donnees retardees ;
- automatisation et redistribution a ne pas mettre en place sans licence.

Pour STRUCTURA, EURIBOR ne doit pas etre ingere automatiquement tant que les
droits n'ont pas ete verifies. Les historiques mensuels publies par l'ECB
peuvent servir a des analyses moins frequentes.

## 4. Sources de donnees options

| Priorite POC | Source | Donnees gratuites | Limites principales |
| --- | --- | --- | --- |
| P1 | [MarketData.app](https://www.marketdata.app/pricing/) | Chaines US retardees, prix, IV et Greeks selon l'offre | Retard, quotas et droits a verifier |
| P1 | [ThetaData](https://docs.thetadata.us/Articles/Getting-Started/Subscriptions.html) | Historique EOD US limite, retard d'une journee | Pas de quotes intraday, IV ou Greeks complets dans l'offre gratuite |
| P2 | [Tradier](https://docs.tradier.com/docs/market-data) | Sandbox actions et options retardee | Compte et token, Greeks limites, restrictions d'usage |
| P2 | [Alpaca](https://docs.alpaca.markets/us/docs/about-market-data-api) | Flux options indicatif dans l'offre Basic | Pas un flux OPRA consolide complet |
| P2 | [Eurex](https://www.eurex.com/ex-en/data/free-reference-data-api) | Referentiel produits, volumes et statistiques | Prix de chaines complets non confirmes gratuitement |
| Controle | [Cboe](https://www.cboe.com/markets/us/options/market-statistics/reference-data/) | Referentiels et statistiques agregees | Extraction des pages de cotations interdite |
| Controle | [CME](https://www.cmegroup.com/market-data/browse-data/delayed-quotes.html) | Cotations retardees visibles sur le site | API et donnees detaillees principalement commerciales |

### 4.1 MarketData.app

MarketData.app semble etre le meilleur candidat pour un premier prototype de
chaines options US. Selon le niveau d'offre disponible, les reponses peuvent
inclure :

- symbole du contrat ;
- expiration, strike et type call/put ;
- bid, ask et dernier prix ;
- volume et open interest ;
- volatilite implicite ;
- Greeks.

Liens utiles :

- [tarification et offre gratuite](https://www.marketdata.app/pricing/) ;
- [documentation de l'API de chaines options](https://www.marketdata.app/docs/api/options/chain/).

Avant toute integration permanente, il faudra verifier les quotas, la
profondeur d'historique, le retard effectif et les droits d'utilisation par
STRUCTURA.

### 4.2 ThetaData

ThetaData propose une offre gratuite adaptee a l'exploration de donnees EOD et
a la validation historique. L'acces passe par son composant local Theta
Terminal.

Usages possibles :

- recuperer des prix de fin de journee ;
- comparer les prix du moteur avec des donnees observees ;
- construire un petit jeu de regression ;
- tester la qualite de reconstruction d'une volatilite implicite.

L'offre gratuite n'est pas suffisante pour une surface temps reel ou pour une
calibration intraday complete.

### 4.3 Tradier

La sandbox Tradier fournit des donnees actions et options US retardees. Elle
permet de tester les chaines, expirations et contrats via une API documentee.

Points de vigilance :

- compte et jeton d'acces necessaires ;
- retard de la sandbox ;
- disponibilite limitee des Greeks ;
- usage personnel par defaut, sauf accord partenaire.

Liens utiles :

- [documentation market data](https://docs.tradier.com/docs/market-data) ;
- [FAQ et restrictions](https://docs.tradier.com/docs/faq).

### 4.4 Alpaca

Alpaca offre une API techniquement simple, mais le niveau Basic fournit un flux
options indicatif et non l'ensemble du marche OPRA consolide.

Cette source peut servir a un prototype d'integration, mais elle ne doit pas
etre utilisee comme preuve qu'un prix represente l'ensemble du marche.

Liens utiles :

- [presentation de Market Data API](https://docs.alpaca.markets/us/docs/about-market-data-api) ;
- [presentation des options](https://docs.alpaca.markets/us/docs/options-trading-overview).

### 4.5 Eurex

Eurex est la source officielle a privilegier pour le referentiel des options
europeennes : specifications produits, calendrier, volumes et open interest.

Liens utiles :

- [API gratuite de referentiel](https://www.eurex.com/ex-en/data/free-reference-data-api) ;
- [statistiques de marche](https://www.eurex.com/ex-en/data/statistics) ;
- [fichiers de trading](https://www.eurex.com/ex-en/data/trading-files).

L'etude n'a pas confirme l'existence d'une API gratuite fournissant des chaines
completes de prix et une surface de volatilite. Une licence restera
probablement necessaire pour une integration de production.

### 4.6 Sources a ne pas confondre avec une API gratuite

**Cboe** affiche des chaines retardees comprenant prix, volume, open interest,
volatilite implicite et Greeks. La page indique toutefois que l'extraction ou
le telechargement automatises sont interdits. STRUCTURA ne doit donc pas
scraper ces pages.

**CME** propose des cotations retardees consultables. Les donnees detaillees et
les services API sont soumis a des offres et licences distinctes. Les pages
gratuites peuvent servir a un controle manuel, pas a une collecte automatisee.

**Alpha Vantage** dispose d'endpoints options historiques et temps reel, mais
ces fonctions sont classees dans les offres premium. Ce n'est donc pas une
solution gratuite pour ce besoin.

## 5. Usages possibles dans STRUCTURA

### 5.1 Taux

Les donnees officielles pourraient permettre de :

- renseigner un tableau de marche EUR et USD ;
- controler les courbes saisies par l'utilisateur ;
- alimenter `dr_frac` dans les scenarios historiques de VaR ;
- produire des chocs paralleles, de pente et de courbure observes ;
- comparer une courbe interne aux references ECB ou Treasury ;
- dater les scenarios avec le regime monetaire correspondant ;
- completer les backtests avec des donnees macro sans dependance a Yahoo.

### 5.2 Options

Les donnees options pourraient permettre de :

- comparer le prix STRUCTURA au bid, ask et mid observe ;
- reconstruire la volatilite implicite avec le moteur STRUCTURA ;
- comparer les Greeks calcules aux Greeks du fournisseur ;
- construire une surface strike/maturite ;
- detecter les arbitrages simples et les donnees incoherentes ;
- creer des jeux de tests de regression sur des snapshots dates.

Les prix retardes conviennent au controle, a la calibration EOD et aux tests.
Ils ne conviennent pas a une valorisation presentee comme temps reel.

## 6. Architecture proposee

L'integration devrait rester separee de `market_data.py` afin de distinguer les
responsabilites et les contraintes de licence.

Structure possible :

```text
backend/app/services/
  rates_data.py
  rates_providers/
    ecb.py
    new_york_fed.py
    us_treasury.py
    bis.py
  options_data.py
  options_providers/
    marketdata_app.py
    thetadata.py
    tradier.py
    alpaca.py
```

Chaque observation devrait conserver au minimum :

```text
provider
dataset_or_symbol
observation_date
retrieved_at
value
unit
currency
tenor_or_expiry
delay_class
license_class
raw_source_reference
```

Principes d'implementation :

- cache local avec duree differente pour les taux quotidiens et les options ;
- timeout, retries limites et circuit breaker ;
- validation des unites, calendriers et fuseaux horaires ;
- conservation de la provenance de chaque valeur ;
- affichage explicite du retard des donnees options ;
- aucun fallback silencieux vers une valeur ancienne ;
- secrets API uniquement dans les variables d'environnement ;
- tests avec fixtures locales, sans appel Internet dans la suite normale.

## 7. Feuille de route recommandee

### Phase 1 - Taux officiels

1. Implementer un client generique HTTP/SDMX avec cache.
2. Integrer EURSTR et l'indice compose depuis l'ECB.
3. Integrer SOFR et SOFR Index depuis la New York Fed.
4. Integrer les courbes ECB et Treasury comme references de risque.
5. Ajouter des controles de fraicheur, unite et calendrier.

### Phase 2 - Scenarios de taux

1. Mapper les maturites officielles vers les tenors STRUCTURA.
2. Calculer les variations quotidiennes de niveau, pente et courbure.
3. Alimenter les chocs de taux historiques dans `MarketScenario.dr_frac`.
4. Ajouter des scenarios dates et reproductibles.
5. Backtester les resultats sur plusieurs periodes de stress.

### Phase 3 - Prototype options US

1. Tester MarketData.app et ThetaData sur `SPY` et `AAPL`.
2. Comparer couverture, delai, erreurs, quotas et donnees manquantes.
3. Stocker un snapshot EOD de chaine dans une fixture locale.
4. Recalculer IV et Greeks avec STRUCTURA.
5. Mesurer les ecarts au mid et aux Greeks du fournisseur.

### Phase 4 - Options europeennes et licence

1. Utiliser Eurex pour le referentiel et les statistiques produits.
2. Identifier les instruments prioritaires, par exemple OESX.
3. Demander un devis uniquement si le besoin de prix de production est
   confirme.
4. Documenter les droits de stockage, redistribution et affichage.

## 8. Matrice de decision

| Besoin | Source recommandee | Decision |
| --- | --- | --- |
| Taux court EUR | ECB EURSTR | Integrer en premier |
| Taux court USD | New York Fed SOFR | Integrer en premier |
| Courbe souveraine EUR | ECB Yield Curves | Reference et scenarios |
| Courbe souveraine USD | US Treasury | Reference et scenarios |
| Regimes internationaux | BIS | Integrer apres les taux P1 |
| Inflation et macro Europe | Eurostat | Complement scenarios |
| Options US EOD avec IV/Greeks | MarketData.app | Proof of concept |
| Historique options EOD | ThetaData | Proof of concept compare |
| Sandbox de chaines US | Tradier | Option secondaire |
| Referentiel options Europe | Eurex | Utiliser pour les contrats |
| Options Europe avec prix complets | Source sous licence | Decision ulterieure |

## 9. Risques a traiter avant production

- changement de quotas ou de conditions commerciales ;
- interdiction de redistribution ou d'affichage ;
- donnees retardees presentees par erreur comme temps reel ;
- confusion entre courbe souveraine et courbe OIS ;
- changements de symboles, calendriers ou conventions de maturite ;
- survivorship bias dans les historiques d'options ;
- absence de bid/ask ou open interest nul ;
- erreurs d'unite entre pourcentage, points de base et valeur decimale ;
- utilisation d'une donnee revisee dans un backtest historique ;
- dependance a une API gratuite sans engagement de service.

## 10. Decision proposee

Le premier chantier devrait porter uniquement sur les sources officielles de
taux : ECB, New York Fed et US Treasury. Il apporte une valeur immediate aux
scenarios et aux controles, avec un risque juridique et technique faible.

Le second chantier devrait etre un prototype options strictement EOD, sans
promesse de temps reel. MarketData.app et ThetaData pourront etre compares
avant de choisir un fournisseur. L'utilisation en production ne devra etre
validee qu'apres lecture des conditions de licence applicables a STRUCTURA.
