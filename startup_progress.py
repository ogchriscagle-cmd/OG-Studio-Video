"""Lightweight progress bridge; safe when running from Python without a splash."""
try:
    import pyi_splash
except ImportError:
    pyi_splash = None


def startup_stage(percent, message):
    try:
        if pyi_splash is not None and pyi_splash.is_alive():
            pyi_splash.update_text(f"OGSTART|{max(0, min(100, int(percent)))}|{message}")
    except (OSError, RuntimeError):
        pass


def close_startup():
    try:
        if pyi_splash is not None and pyi_splash.is_alive():
            pyi_splash.close()
    except (OSError, RuntimeError):
        pass
