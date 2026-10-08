"""An explicit allow-list, not a reflection of every model in the engine."""
from .contracts import MAX_CANDIDATES, MAX_SECONDS, MAX_WORK, MAX_PARALLEL_WORKERS
from .families import ADAPTERS, family_schema


def capabilities():
    families = []
    for key in ADAPTERS:
        try:
            families.append(family_schema(key))
        except ValueError as error:
            families.append(dict(product_family=key, status="UNSUPPORTED", label=key, reason=str(error)))
    return {
        "schema_version": 1,
        "families": families,
        "objectives": ["maximize_coupon", "maximize_protection", "target_coupon", "maximize_participation", "maximize_cap"],
        "available_analytics": ["fair_value", "price_ic95", "probability_loss", "probability_autocall", "expected_maturity"],
        "unavailable_analytics": ["physical_probability", "expected_return", "VaR", "ES", "continuous_barrier_breach", "greeks"],
        "limitations": [
            "Probabilités risque-neutres sous GBM, pas des prévisions ni une recommandation personnalisée.",
            "Marché historique chargé par panier et date ; volatilités réalisées utilisées comme hypothèses GBM, dividendes historiques à confirmer, taux et funding manuels. Références et overrides figés au lancement.",
            "Même devise pour les actifs et le règlement ; aucun smile, FX/quanto ou modèle de défaut émetteur. Funding appliqué à l'actualisation seule.",
            "Budget du payoff = prix d'émission moins frais et marge initiaux en fractions du nominal ; perte investisseur mesurée sur le prix d'émission brut.",
            "Barrière européenne. Grille Monte-Carlo hebdomadaire : observations approchées, paiements contractuels actualisés.",
            "Coupon, participation ou cap résolu selon le script ; coupon annuel nominal sauf gear put à coupon unique, hors défaut émetteur.",
            "Le rappel à maturité est exclu de la probabilité de remboursement anticipé.",
            "Exploration à graine 42, puis sélection figée de cinq candidats au maximum : paramètres résolus conservés, validation indépendante à N et 2N paires.",
            "Bonferroni sur la sélection : prix et compatibilité N/2N par approximation normale ; probabilités et durée par bornes empiriques de Bernstein.",
            "Résultats temporaires dans la page ; exporter le JSON avant de la quitter.",
            "Recommandation limitée aux candidats confirmés de la sélection ; compatibilité Monte-Carlo, sans certification du classement ni convergence temporelle automatique.",
        ],
        "limits": {"max_candidates": MAX_CANDIDATES, "max_seconds": 3600, "default_seconds":MAX_SECONDS,
                   "advisory_work_units": MAX_WORK, "max_simulations": 20000,
                   "max_parallel_workers": MAX_PARALLEL_WORKERS},
        "execution": "Calculs directs ; 2 candidats simultanés par défaut, nombre réduit selon CPU/mémoire ; aucun ratio entre modèles.",
        "model_resolution": "auto → constant (GBM), seule configuration qualifiée ; aucun repli après erreur",
    }
