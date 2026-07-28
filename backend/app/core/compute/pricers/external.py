"""Extension point for pricing a product that ISN'T expressed as a PayScript
— a client's proprietary model, a competitor's structure to benchmark for a
pitch, a legacy Excel-based pricer, anything the DSL can't (yet, or ever)
express. Nothing here is wired to anything today — no external client has
been onboarded — this module documents the CONTRACT such a pricer must
satisfy to run through the same compute module (job/executor/queue_store) as
a PayScript reprice, without that client's code ever being imported into
backend/app/'s own process.

Two isolation levels — pick per situation, both slot into PRICERS the same
way (a plain `(payload: dict) -> dict` callable):

  1. Subprocess boundary (recommended default for anything client-provided).
     subprocess_pricer() below dispatches to a standalone script/executable
     that reads one JSON payload on stdin and writes one JSON result on
     stdout. Register a batch `kind` for it (e.g. "external:acme_capital_v1")
     mapped to a small wrapper `lambda payload: subprocess_pricer([...], payload)`
     in PRICERS. The client's code never gets imported into this process —
     a bug, an infinite loop, or a licensing concern on their side can't
     reach into Structura's own memory space, and it still gets the same
     ProcessPoolExecutor-level parallelism and per-job failure isolation as
     everything else (see executor.py).

  2. In-process adapter — only for pricing logic YOU wrote/control (e.g. a
     Python re-implementation of a client's published spec, not their actual
     code): a plain callable matching this same (payload) -> dict shape,
     registered directly in pricers/PRICERS, same pattern as payscript.py.

Adding a real external pricer later: drop its adapter next to this file and
add one line to PRICERS — nothing in executor.py, queue_store.py, or the
API layer needs to change, same "new product, zero core changes" contract
PayScript templates already have."""
from __future__ import annotations
import json
import subprocess


def subprocess_pricer(executable: list[str], payload: dict, timeout: float = 60.0) -> dict:
    """Runs `executable` (a full command line, e.g.
    [".venv/Scripts/python.exe", "clients/acme/price.py"]), feeding `payload`
    as one line of JSON on stdin and expecting one JSON object back on
    stdout. Any non-zero exit or unparsable stdout raises — executor.py's
    per-job isolation turns that into a failed job, not a crashed batch, so
    one misbehaving external pricer can't take down a whole VaR run's other
    scenarios."""
    proc = subprocess.run(
        executable, input=json.dumps(payload), capture_output=True,
        text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Pricer externe a échoué (code {proc.returncode}): {proc.stderr.strip()[:500]}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Pricer externe: sortie non-JSON ({e}): {proc.stdout[:200]!r}") from e
