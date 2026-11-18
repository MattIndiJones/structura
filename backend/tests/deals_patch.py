"""Replace a dependency of the deals API, wherever the package uses it.

`backend/app/api/deals.py` was one module: `monkeypatch.setattr(deals, name, v)`
was seen by every function in it. Since its split into a package (18/11/2026),
a name is bound separately in each submodule that uses it, and replacing it on
the package alone would leave those bindings untouched — the test would then
silently reach the real dependency (a Yahoo download, an audit write...).
`patch_deals` restores the former semantics.
"""
from backend.app.api import deals


def _calibration_from(load_prices):
    """The realized recalibration of the MtM reads its own, session-qualified
    history (`load_session_calibration_history`). A test that fakes the price
    history fed that recalibration too, since the route passed the same loader
    to the core: keep that, with the same fallback for three-argument fakes."""
    def calibration(tickers, start, asof, provider=None):
        try:
            return load_prices(tickers, start, asof.isoformat(), adjusted=True)
        except TypeError:
            return load_prices(tickers, start, asof.isoformat())
    return calibration


def _set(monkeypatch, name, value):
    monkeypatch.setattr(deals, name, value, raising=False)
    for module in deals.SUBMODULES:
        if name in vars(module):
            monkeypatch.setattr(module, name, value)


def patch_deals(monkeypatch, name, value):
    """Replace `name` on the package and in every submodule that binds it."""
    monkeypatch.setattr(deals, name, value)
    for module in deals.SUBMODULES:
        if name in vars(module):
            monkeypatch.setattr(module, name, value)
    if name == "load_hist_prices":
        _set(monkeypatch, "load_session_calibration_history", _calibration_from(value))
