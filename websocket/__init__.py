"""
WebSocket command registration for Dashboard.

Importing this package automatically registers all
WebSocket commands via their decorators.
"""

from .blueprints import *
from .configuration import *
from .more_pages import *
from .configuration import *
from .sorting import *
from .devices import *
from .entities import *
from .areas import *
from .cards import *

__all__ = [name for name in globals() if name.startswith(("ws_", "websocket_"))]