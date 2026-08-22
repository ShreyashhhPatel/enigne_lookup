"""engine_lookup — an entity-centric agent for finding and tracking people
across news and social media.

Public surface is deliberately tiny for now; it grows one step at a time.
"""

from engine_lookup.entity import (
    Affiliation,
    EntityProfile,
    EntityType,
    Handle,
)

__all__ = [
    "Affiliation",
    "EntityProfile",
    "EntityType",
    "Handle",
]

__version__ = "0.0.1"
