"""An explicit allow-list, not a reflection of every model in the engine."""
from .contracts import MAX_CANDIDATES, MAX_SECONDS, MAX_WORK


def capabilities():
    return {
        "schema_version": 1,
        "families": [{
            "product_family": "autocall_athena", "status": "SUPPORTED",
            "label": "Autocall Athena — barrière européenne",
            "models": ["constant"], "underlying_types": ["equity", "index"],
            "basket_types": ["single_asset", "worst_of"], "max_underlyings": 3,
            "observation_months": [1, 3, 6, 12],
            "optimization_parameters": ["maturity_months", "protection_barrier", "autocall_trigger", "observation_months"],
            "solved_parameters": ["coupon"],
        }, {"product_family": "phoenix", "status": "UNSUPPORTED",
            "label": "Phoenix / mémoire — qualification Optimizer différée"}],
        "objectives": ["maximize_coupon", "maximize_protection", "target_coupon"],
        "available_analytics": ["fair_value", "price_ic95", "probability_loss", "probability_autocall", "expected_maturity"],
        "unavailable_analytics": ["physical_probability", "expected_return", "VaR", "ES", "continuous_barrier_breach", "greeks"],
        "limitations": [
            "Probabilités risque-neutres sous GBM, pas des prévisions ni une recommandation personnalisée.",
            "Hypothèses manuelles explicites : taux et dividendes plats, volatilités constantes ; aucun téléchargement automatique.",
            "Même devise pour les actifs et le règlement ; aucun smile, funding, FX/quanto, frais ou crédit émetteur.",
            "Barrière européenne. Grille Monte-Carlo hebdomadaire : observations approchées, paiements contractuels actualisés.",
            "Coupon nominal annualisé, accumulé et payé seulement au rappel (y compris à maturité). Aucun coupon si jamais rappelé.",
            "Le rappel à maturité est exclu de la probabilité de remboursement anticipé.",
            "IC95 ponctuels : aucune correction pour la sélection parmi plusieurs candidats. Résolution et contrôle du coupon utilisent les mêmes tirages.",
            "Résultats temporaires dans la page ; exporter le JSON avant de la quitter.",
            "Le meilleur résultat est relatif à la grille explorée ; aucune optimalité globale ni validation de convergence.",
        ],
        "limits": {"max_candidates": MAX_CANDIDATES, "max_seconds": MAX_SECONDS,
                   "max_work_units": MAX_WORK, "max_simulations": 20000},
        "model_resolution": "auto → constant (GBM), seule configuration qualifiée ; aucun repli après erreur",
    }
