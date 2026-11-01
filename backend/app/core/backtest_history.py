"""Explicit observation substitutions for exploratory historical backtests only."""
from bisect import bisect_left
from datetime import date, timedelta


BACKTEST_HISTORY_VERSION = "backtest-following-v1"
BACKTEST_HISTORY_DISCLAIMER = (
    "Historique ajusté : certaines observations utilisent le premier cours "
    "commun disponible suivant. Ces décalages peuvent modifier les coupons, "
    "le rappel et les rendements. Les paiements concernés sont décalés du même "
    "nombre de jours calendaires ; aucun cours futur n’est antidaté. "
    "Le suivi des barrières reste limité aux clôtures disponibles."
)


class BacktestHistoryError(ValueError):
    pass


class BacktestObservationReader:
    """Keep the original calendar and resolve each required fixing lazily.

    The input axis contains only simultaneous genuine observations. There is
    no filled price matrix and no change to the official lifecycle reader.
    """
    def __init__(self, calendar, dates, tickers, *, mode="following", max_delay_days=10,
                 observation_dates=None, maturity_payment_t=None):
        if mode not in {"following", "strict"} or not 0 <= max_delay_days <= 31:
            raise ValueError("Convention historique ou décalage maximal invalide.")
        self.calendar, self.dates = calendar, dates
        self.tickers = list(dict.fromkeys(tickers))
        self.mode, self.max_delay_days = mode, max_delay_days
        self.available = {tk: set((observation_dates or {}).get(tk, dates)) for tk in self.tickers}
        self.indices, self.adjustments = {}, {}
        self.maturity_payment_t = maturity_payment_t

    def jour(self, t):
        return self.calendar.jour(t)

    def indice(self, t):
        if t in self.indices:
            return self.indices[t]
        requested = self.jour(t)
        index = bisect_left(self.dates, requested.isoformat())
        if index >= len(self.dates):
            raise BacktestHistoryError(
                f"Observation du {requested.isoformat()} : aucun cours commun suivant "
                "avant la fin de l’historique. Réduisez la période de lancement.")
        effective = date.fromisoformat(self.dates[index])
        delay = (effective-requested).days
        missing = [tk for tk in self.tickers if requested.isoformat() not in self.available[tk]]
        if delay and self.mode == "strict":
            raise BacktestHistoryError(
                f"Mode strict : cours manquant le {requested.isoformat()} pour "
                f"{', '.join(missing or self.tickers)} (fenêtre du {self.calendar._origine.isoformat()}).")
        if delay > self.max_delay_days:
            raise BacktestHistoryError(
                f"Following : {requested.isoformat()} → {effective.isoformat()} "
                f"pour {', '.join(missing or self.tickers)}, soit {delay} jours calendaires "
                f"(maximum {self.max_delay_days}). Aucun remplacement appliqué ; "
                "vérifiez l’historique ou ajustez explicitement la limite.")
        self.indices[t] = index
        if delay:
            for ticker in self.tickers:
                self.adjustments[(requested.isoformat(), ticker)] = {
                    "ticker": ticker, "requested_date": requested.isoformat(),
                    "effective_date": effective.isoformat(), "delay_days": delay,
                    "window_start": self.calendar._origine.isoformat(),
                    "reason": ("MISSING_QUOTE" if ticker in missing else "COMMON_BASKET_DATE"),
                }
        return index

    def effective_time(self, t):
        day = date.fromisoformat(self.dates[self.indice(t)])
        return (day-self.calendar._origine).days/365.25

    def payment(self, observation_t, payment_t):
        index = self.indice(observation_t)
        delay = (date.fromisoformat(self.dates[index])-self.jour(observation_t)).days
        requested = self.jour(payment_t)
        effective = requested+timedelta(days=delay)
        return (effective-self.calendar._origine).days/365.25, effective.isoformat(), requested.isoformat()

    def a_sa_date(self, t, index):
        return self.dates[index] == self.jour(t).isoformat()

    def passe_jusqu_a(self):
        # A rolling backtest is never a partial official history of one deal.
        return None

    def report(self):
        return sorted(self.adjustments.values(), key=lambda row: (row["requested_date"], row["ticker"]))
