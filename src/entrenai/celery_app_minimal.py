# Apply eventlet monkey patch before any imports
try:
    import eventlet

    eventlet.monkey_patch()
except ImportError:
    # eventlet not available, continue without patching
    pass

# Import the configured app from tasks_minimal
from src.entrenai.tasks_minimal import app

# Export the app for compatibility
__all__ = ["app"]

if __name__ == "__main__":
    app.start()
