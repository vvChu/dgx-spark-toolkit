from .search import router as search_router
from .chat import router as chat_router
from .analysis import router as analysis_router
from .admin import router as admin_router
from .visualization import router as visualization_router

# Export routers for easy import in main.py
__all__ = ["search_router", "chat_router", "analysis_router", "admin_router", "visualization_router"]
