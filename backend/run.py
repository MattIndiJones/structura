import uvicorn

if __name__ == "__main__":
    # reload=False : sous Windows, le reloader WatchFiles détecte les modifs mais ne
    # redémarre jamais le worker → serveur qui sert du code périmé sans erreur visible.
    # Redémarrage manuel assumé après chaque modif backend.
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
