"""Checkpointing and compound cursor primitives for lossless, resumable ingestion."""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any


@dataclass
class CompoundCursor:
    """Compound cursor tracking incremental pagination position (watermark, unique_id)."""
    watermark: Optional[str] = None
    last_id: Optional[str] = None
    offset: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "CompoundCursor":
        if not data:
            return cls()
        return cls(
            watermark=data.get("watermark"),
            last_id=data.get("last_id"),
            offset=data.get("offset", 0),
        )


@dataclass
class CheckpointState:
    """Compact checkpoint state avoiding unbounded array growth in database columns."""
    cursor: CompoundCursor = field(default_factory=CompoundCursor)
    high_watermark: Optional[str] = None
    discovery_complete: bool = False
    total_discovered: int = 0
    processed_count: int = 0
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cursor": self.cursor.to_dict(),
            "high_watermark": self.high_watermark,
            "discovery_complete": self.discovery_complete,
            "total_discovered": self.total_discovered,
            "processed_count": self.processed_count,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "CheckpointState":
        if not data:
            return cls()
        return cls(
            cursor=CompoundCursor.from_dict(data.get("cursor")),
            high_watermark=data.get("high_watermark"),
            discovery_complete=data.get("discovery_complete", False),
            total_discovered=data.get("total_discovered", 0),
            processed_count=data.get("processed_count", 0),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
        )
