from .search import router as search_router
from .chat import router as chat_router
from .analysis import router as analysis_router
from .admin import router as admin_router
from .stats import router as stats_router
from .graph import router as graph_router
from .preview import router as preview_router
from .evaluation import router as evaluation_router

# Export routers for easy import in main.py
__all__ = [
    "search_router", "chat_router", "analysis_router", "admin_router",
    "stats_router", "graph_router", "preview_router", "evaluation_router",
]
