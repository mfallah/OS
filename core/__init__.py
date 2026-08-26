"""myos Personal OS — dependency-free domain core package."""
from .app import PersonalOS
from .permissions import PERMISSIONS, RISK
from .entities import ENTITY_KINDS
from .graph import RELATIONS
from .memory import CATEGORIES as MEMORY_CATEGORIES

__all__ = ["PersonalOS", "PERMISSIONS", "RISK", "ENTITY_KINDS", "RELATIONS",
           "MEMORY_CATEGORIES"]
__version__ = "2.0.0"
