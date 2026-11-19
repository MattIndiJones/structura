"""Calculations for test_pricing_jobs.py, importable by a spawned worker."""
import os
import time


def run(kind, request):
    if kind == "price":                  # routes test: the validated request crossed over
        return dict(ok=True, result=dict(script=request.script, pid=os.getpid()))
    if kind == "echo":
        return dict(ok=True, result=dict(request=request, pid=os.getpid()))
    if kind == "sleep":
        time.sleep(request)
        return dict(ok=True, result=dict(slept=request, pid=os.getpid()))
    if kind == "refuse":
        return dict(ok=False, status_code=422, detail="Script invalide.")
    if kind == "crash":
        os._exit(3)
    raise RuntimeError("calcul cassé")
