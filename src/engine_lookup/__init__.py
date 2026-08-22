"""engine_lookup — an entity-centric agent for finding and tracking people
across news and social media.

Public surface is deliberately tiny for now; it grows one step at a time.
"""

from engine_lookup.dedup import (
    DuplicateCluster,
    canonicalize_url,
    cluster_near_duplicates,
    hamming_distance,
    simhash,
)
from engine_lookup.document import Document
from engine_lookup.entity import (
    Affiliation,
    EntityProfile,
    EntityType,
    Handle,
)

__all__ = [
    # entity
    "Affiliation",
    "EntityProfile",
    "EntityType",
    "Handle",
    # document
    "Document",
    # dedup
    "DuplicateCluster",
    "canonicalize_url",
    "cluster_near_duplicates",
    "hamming_distance",
    "simhash",
]

__version__ = "0.0.1"
