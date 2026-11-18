"""Replace a dependency of the Monte Carlo engine, wherever the engine uses it.

`backend/app/core/payscript/engine.py` was one module: `monkeypatch.setattr(
engine, name, v)` was seen by every function in it. Since its split into
modules (18/11/2026), a name is bound separately in each module that uses it,
and replacing it on the facade alone would leave those bindings untouched —
the test would then silently reach the real function, or run at a setting it
believes it changed. `patch_engine` restores the former semantics, as
`deals_patch.patch_deals` does for the deals API.
"""
from backend.app.core.payscript import engine


def patch_engine(monkeypatch, name, value):
    """Replace `name` on the facade and in every engine module that binds it."""
    monkeypatch.setattr(engine, name, value)
    for module in engine.SUBMODULES:
        if name in vars(module):
            monkeypatch.setattr(module, name, value)
