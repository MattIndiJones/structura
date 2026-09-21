# Studies 2.4 — fiabilisation des fonctions existantes

## Périmètre

Corrections de calcul et de restitution sur les blocs déjà présents. Aucune nouvelle fonction de la roadmap (Skill vs Luck, Decision Analysis, portefeuille investissable, etc.) n’est ajoutée. Le score composite reste descriptif.

## Modifications

| Partie | Correction | Limite maintenue |
|---|---|---|
| A — Drawdown | NAV / plus-haut − 1, au lieu d’une différence de performances cumulées ; première perte conservée sur la période factorielle. Annualisation de la performance complète sur le nombre de rendements. | Facteurs et NAV comparés dans la devise d’analyse documentée. |
| A — Ajout des frais | Libellé « ajusté des seuls frais de gestion » ; précision taux annuel / 252. | Ni performance fees ni transactions réintégrées ; pas une NAV brute comptable. |
| F — Réplicabilité | Coefficients et rendements non arrondis dans les calculs ; arrondi final de l’écart seulement. Couverture de performance symétrique : signes opposés = 0, deux performances nulles = 100. | Ajustement sur le même échantillon ; portefeuille théorique, non investissable. |
| F — Restitution | Fourchette appelée sensibilité au R² ; profils renommés selon le niveau d’explication factorielle. | La fourchette ne constitue pas un IC du score global. Les performances des expositions isolées ne sont pas additives. |
| J — Drawdowns | Tous les épisodes comptés et utilisés dans le score ; cinq pires conservés pour le détail. | Le calibrage du score reste heuristique. |
| J — Durées | Jours calendaires entre premier point sous le plus-haut et récupération ou arrêté. Durée en observations également disponible. | Le score conserve son unité d’origine, les observations, sur tous les épisodes. Une perte non récupérée est identifiée explicitement. |
| J — Benchmark | Rendements du benchmark calculés avant l’alignement, sans perdre la première variation comparable. | Taux sans risque nul pour les ratios descriptifs J, explicite dans les résultats. |
| G — Sources | Calcul complémentaire dans le contexte de marché du dossier ; même date et panier de référence que le calcul automatique. | Attribution statique et indicative sur proxies, exclue du scoring. |
| G — Poids | Cash résiduel conservé ; poids manquants ou positions non couvertes refusés. Suppression du faux chemin de reconstruction « achats des 60 premiers jours ». | Sans TS, approximation par composition actuelle signalée. |
| G — Cohérence | Le calcul complémentaire met à jour bloc G, statut, couverture sauvegardée et empreinte du résultat. | Les autres lignes de couverture sont conservées ; l’export utilise la couverture sauvegardée. |
| Attribution complémentaire | Contributions rétrospectives des achats/ventes, total rapporté à l’AUM déclaré. | Hors dividendes/frais ; distinct du VAG E ; pas une mesure isolée de timing ou de sélection. |
| D / Manager Skill | Dimension renommée « taux de titres gagnants ». Texte explicite sur poids courant OU durée maximale et P&L réalisé + latent. | Ce n’est pas un test d’alpha de conviction ni une preuve des intentions du gérant. |
| I / scores | Interprétations statistiques limitées au test réalisé, sans assimiler un résultat à un talent durable. | Un score descriptif peut être publié malgré des résultats non significatifs ; lire les p-values séparément. |
| K — Chocs | Plusieurs ordres du même titre le même jour ne s’écrasent plus dans la moyenne de timing. Libellés d’activité descriptifs. | L’activité observée ne prouve ni sur-réaction ni discipline. |

Les calculs complémentaires refusent des fichiers dont les empreintes ont changé depuis l’étude. Ils n’écrivent pas dans les caches partagés lorsqu’un dossier de marché autonome est utilisé. Une synthèse existante doit être relue ou régénérée après recalcul G ; une réponse IA liée à l’ancienne empreinte est refusée.

## Recette indépendante

Les inputs et l’oracle V1 restent figés dans `artifacts/studies/LO_EXTENDED_BLOCKS_2020_2025_V1`. Le script indépendant `methodology_reference.py` recalcule uniquement les conséquences de la politique 2.4 à partir des métriques, épisodes et séries de référence. Il n’importe pas le moteur Studies et ne lit pas ses résultats.

Le dossier à scanner reste `artifacts/studies/LO_ALL_BLOCKS_2020_2025`. Les résultats attendus sont dans `RESULTATS_ATTENDUS`, le contrôle effectif dans `RESULTATS_ATTENDUS/CONTROLE_OUTIL`.

| Indicateur | Résultat attendu affiché |
|---|---:|
| NAV finale | 138,065178 |
| VAG E | −13,93 points |
| F — écart de performance | 19,42 points |
| J — information ratio | −1,074 |
| J — épisodes de drawdown | 36 |
| J — durée moyenne | 58,3 jours calendaires |
| J — score drawdown | 50 |
| J — score global | 56 |
| Manager Skill | 53 |
| VAG dans Manager Skill | poids 20 %, sous-score 44,2 |
| FX réalisé | −296 121,97 USD ; −7,84 % du réalisé signé |

## Vérifications et utilisation

Tests ciblés : formules de drawdown avec NAV 100 → 50 → 100 → 200 → 150, conservation du premier rendement benchmark, récupération après un week-end, plus de cinq épisodes, arrondis du réplicant, signes opposés, cash et positions manquantes Brinson, cohérence couverture/empreinte, contexte marché des endpoints et refus de sources modifiées, ordres intrajournaliers multiples.

La recette complète passe par le scanner et le moteur ordinaires avec accès réseau interdits : **85/85 comparaisons conformes**, avec les tolérances publiées dans `checks.csv`. Cela valide ce scénario, pas tous les fonds possibles.

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_studies_methodology.py backend/tests/test_studies_market_bundle.py backend/tests/test_amc_studies.py backend/tests/test_studies_reconciliation.py backend/tests/test_studies_dividends.py -q
.venv/Scripts/python.exe scripts/studies_reference/setup_unified.py
.venv/Scripts/python.exe scripts/studies_reference/verify_unified.py
```

Les 111 cas de tests backend ciblés ont été validés au cours des passes de contrôle. Le frontend a été compilé avec `npm run build` (201 tests réussis). Un export PDF complet a été généré, puis les pages modifiées A/D/F/J/Manager Skill/couverture ont été contrôlées visuellement. Validation visuelle dans le navigateur utilisateur restant à effectuer.

Pour appliquer : redémarrer le backend, actualiser avec Ctrl+F5, scanner le dossier puis **relancer l’étude complète**. Les études et PDF déjà sauvegardés ne sont pas recalculés automatiquement. Relire/régénérer la synthèse puis exporter un nouveau PDF. Aucun commit, push ou redémarrage de serveur n’a été effectué par l’assistant.
