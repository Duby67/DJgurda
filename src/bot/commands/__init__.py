from .help import router as help_router
from .info import router as info_router
from .start import router as start_router
from .status import router as status_router
from .toggle_bot import router as toggle_bot_router
from .toggle_errors import router as toggle_errors_router

command_routers = [
    help_router,
    info_router,
    start_router,
    status_router,
    toggle_bot_router,
    toggle_errors_router
]

__all__ = ["command_routers"]