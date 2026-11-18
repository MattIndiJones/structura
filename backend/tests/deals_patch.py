"""Replace a dependency of the deals API, wherever the package uses it.

`backend/app/api/deals.py` was one module: `monkeypatch.setattr(deals, name, v)`
was seen by every function in it. Since its split into a package (18/11/2026),
a name is bound separately in each submodule that uses it, and replacing it on
the package alone would leave those bindings untouched — the test would then
silently reach the real dependency (a Yahoo download, an audit write...).
`patch_deals` restores the former semantics.
"""
from backend.app.api import deals


def patch_deals(monkeypatch, name, value):
    """Replace `name` on the package and in every submodule that binds it."""
    monkeypatch.setattr(deals, name, value)
    for module in deals.SUBMODULES:
        if name in vars(module):
            monkeypatch.setattr(module, name, value)
