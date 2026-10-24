import os
import sys

def main():
    from pathlib import Path
    if not os.environ.get("STRUCTURA_INSTALLATION_CONFIG") and not os.environ.get("STRUCTURA_DATA_DIR"):
        # The historical entry point opens the same launcher as the desktop
        # shortcut. Explicit actor/consultation environments remain services.
        import runpy
        runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "launch_structura.py"), run_name="__main__")
        return
    import uvicorn
    # reload=False : sous Windows, le reloader WatchFiles détecte les modifs mais ne
    # redémarre jamais le worker → serveur qui sert du code périmé sans erreur visible.
    # Redémarrage manuel assumé après chaque modif backend.
    from app.hybrid.config import current_config
    config = current_config()
    lease = None
    if config:
        from app.services.agent_workshop.lease import CampaignLease
        lease = CampaignLease(config.data_dir)
    try:
        if config and config.service == "admin_workbench":
            # Run the complete historical application against its own local
            # development database, without organization-role restrictions.
            os.environ["STRUCTURA_ADMIN_WORKBENCH_CONFIG"] = os.environ.pop("STRUCTURA_INSTALLATION_CONFIG")
            from app.main import app
            if "--initialize-only" in sys.argv:
                from app.db.database import init_db
                import json
                print(json.dumps(init_db() or {"initialized": True}))
                return
        elif config and config.service == "portal_redirect":
            from app.hybrid.control_services import redirect_app
            app = redirect_app(config)
        elif config and config.service == "simulation_controller":
            from app.hybrid.simulation import create_app
            app = create_app(config)
        elif config and config.kind == "platform":
            from app.hybrid.platform import create_app, initialize
            if "--initialize-only" in sys.argv:
                import json
                print(json.dumps(initialize(config)))
                sys.exit(0)
            app = create_app()
        else:
            from app.main import app
            if "--initialize-only" in sys.argv:
                from app.db.database import init_db
                import json
                print(json.dumps(init_db() or {"initialized": True}))
                sys.exit(0)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1",
                    port=config.port if config else int(os.environ.get("STRUCTURA_PORT", "8000")), reload=False,
                    timeout_graceful_shutdown=5 if config or os.environ.get("STRUCTURA_WORKSHOP_CHILD") == "1" else None))
        app.state.instance_server = server
        server.run()
    finally:
        if lease:
            lease.close()


if __name__ == "__main__":
    main()
