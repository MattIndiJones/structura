"""Bound document bodies before multipart parsing and copy files in bounded chunks."""
from tempfile import SpooledTemporaryFile

from fastapi import HTTPException
from starlette.responses import JSONResponse


MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_DOCUMENT_BODY_BYTES = MAX_DOCUMENT_BYTES + 1024 * 1024
UPLOAD_CHUNK_BYTES = 64 * 1024


class DocumentUploadLimitMiddleware:
    """Spool at most the body budget before invoking the multipart parser.

    Counting actual bytes also covers missing or misleading Content-Length.
    The temporary body is always closed, including disconnects and refusals.
    """
    def __init__(self, app, max_body_bytes=MAX_DOCUMENT_BODY_BYTES):
        self.app, self.max_body_bytes = app, max_body_bytes

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        root = scope.get('root_path', '').rstrip('/')
        if root and path.startswith(root + '/'):
            path = path[len(root):]
        if scope['type'] != 'http' or scope['method'] != 'POST' or path.rstrip('/') != '/api/documents':
            return await self.app(scope, receive, send)

        async def reject():
            await JSONResponse({'detail': 'Document trop volumineux : 20 Mio maximum par fichier.'},
                               status_code=413)(scope, receive, send)
        for name, value in scope.get('headers', []):
            if name.lower() == b'content-length':
                try:
                    length = int(value)
                except ValueError:
                    length = -1
                if length < 0:
                    return await JSONResponse({'detail': 'Content-Length invalide.'}, status_code=400)(scope, receive, send)
                if length > self.max_body_bytes:
                    return await reject()
        with SpooledTemporaryFile(max_size=UPLOAD_CHUNK_BYTES) as body:
            total = 0
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                chunk = message.get('body', b'')
                total += len(chunk)
                if total > self.max_body_bytes:
                    return await reject()
                body.write(chunk)
                if not message.get('more_body', False):
                    break
            body.seek(0)
            remaining = total

            async def replay():
                nonlocal remaining
                if remaining == 0:
                    return await receive()
                chunk = body.read(UPLOAD_CHUNK_BYTES)
                remaining -= len(chunk)
                return {'type': 'http.request', 'body': chunk, 'more_body': remaining > 0}
            if total == 0:
                async def replay():
                    return {'type': 'http.request', 'body': b'', 'more_body': False}
            await self.app(scope, replay, send)


async def copy_document(file, destination):
    if file.size is not None and file.size > MAX_DOCUMENT_BYTES:
        raise HTTPException(413, 'Document trop volumineux : 20 Mio maximum par fichier.')
    created = False
    try:
        with destination.open('xb') as output:
            created = True
            size = 0
            while chunk := await file.read(UPLOAD_CHUNK_BYTES):
                size += len(chunk)
                if size > MAX_DOCUMENT_BYTES:
                    raise HTTPException(413, 'Document trop volumineux : 20 Mio maximum par fichier.')
                output.write(chunk)
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise
