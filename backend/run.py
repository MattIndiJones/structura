import uvicorn
import os

if __name__ == "__main__":
    # reload=False : sous Windows, le reloader WatchFiles détecte les modifs mais ne
    # redémarre jamais le worker → serveur qui sert du code périmé sans erreur visible.
    # Redémarrage manuel assumé après chaque modif backend.
    from app.main import app
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1",
                port=int(os.environ.get("STRUCTURA_PORT", "8000")), reload=False))
    app.state.instance_server = server
    server.run()
