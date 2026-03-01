from .help import router as help_router
from .info import router as info_router
from .statistics import router as statistics_router

from .toggle_bot import router as toggle_bot_router
from .toggle_errors import router as toggle_errors_router
from .toggle_notifications import router as toggle_notification_router

command_routers = [
    help_router,
    info_router,
    statistics_router,
    
    toggle_bot_router,
    toggle_errors_router,
    toggle_notification_router
]

__all__ = ["command_routers"]