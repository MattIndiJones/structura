"""Stream actual valuation phases while a synchronous worker owns its session."""
import asyncio
import json
import logging

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse


def valuation_progress_response(compute, *, error_message="Erreur de calcul du MtM. Consultez les journaux serveur."):
    async def events():
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()

        def publish(event):
            loop.call_soon_threadsafe(queue.put_nowait, event)

        def worker():
            try:
                result = compute(lambda phase: publish({"type": "progress", "phase": phase}))
                publish({"type": "result", "data": result})
            except HTTPException as exc:
                publish({"type": "error", "detail": exc.detail, "status": exc.status_code})
            except Exception:
                logging.getLogger(__name__).exception("Valuation streaming failed")
                publish({"type": "error", "detail": error_message})
            finally:
                publish(None)

        task = asyncio.create_task(asyncio.to_thread(worker))
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield json.dumps(jsonable_encoder(event), ensure_ascii=False) + "\n"
        finally:
            # A disconnected browser does not roll back a completed valuation.
            # The worker closes its own session and persists at most one run.
            await asyncio.shield(task)

    return StreamingResponse(events(), media_type="application/x-ndjson", headers={
        "Cache-Control": "no-store", "X-Accel-Buffering": "no",
    })
