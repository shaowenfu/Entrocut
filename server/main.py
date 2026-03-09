try:
    from server.app.main import app
except ModuleNotFoundError:
    from app.main import app
