from .help import router as help_router
from .start import router as start_router
from .status import router as status_router
from .toggle_errors import router as toggle_errors_router

command_routers = [
    help_router,
    start_router,
    status_router,
    toggle_errors_router
]

__all__ = ["command_routers"]