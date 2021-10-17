import logging

from typing import Optional, Tuple, Dict
from enum import Enum, auto
from functools import total_ordering

from fotocop.util import nodemixin as nd

logger = logging.getLogger(__name__)


class NodeKind(Enum):
    ROOT = auto()
    YEAR = auto()
    MONTH = auto()
    DAY = auto()
    HOUR = auto()


@total_ordering
class TimelineNode(nd.NodeMixin):
    """A node of the timeline has a unique id and a weight (images count)."""

    def __init__(self, id_: str, kind: NodeKind):
        self._id = id_
        self.kind = kind
        self.weight = 1

    @property
    def key(self) -> str:
        return self._id

    @property
    def record(self) -> Tuple[NodeKind, str, int]:
        return self.kind, self._id, self.weight

    @property
    def childrenDict(self) -> Dict[str, "TimelineNode"]:
        return {child.key: child for child in self.children}

    @property
    def years(self) -> Dict[str, "TimelineNode"]:
        assert self.kind == NodeKind.ROOT
        return self.childrenDict

    @property
    def months(self) -> Dict[str, "TimelineNode"]:
        assert self.kind == NodeKind.YEAR
        return self.childrenDict

    @property
    def days(self) -> Dict[str, "TimelineNode"]:
        assert self.kind == NodeKind.MONTH
        return self.childrenDict

    @property
    def hours(self) -> Dict[str, "TimelineNode"]:
        assert self.kind == NodeKind.DAY
        return self.childrenDict

    def __len__(self) -> int:
        return len(self.children)

    def __eq__(self, other: "TimelineNode") -> bool:
        if not isinstance(other, TimelineNode):
            return NotImplemented
        if other.kind != self.kind:
            return NotImplemented
        if other.parent != self.parent:
            return NotImplemented
        return self.key == other.key

    def __lt__(self, other: "TimelineNode") -> bool:
        if not isinstance(other, TimelineNode):
            return NotImplemented
        if other.kind != self.kind:
            return NotImplemented
        if other.parent != self.parent:
            return NotImplemented
        return self.key < other.key

    def __iter__(self) -> "TimelineNode":
        for child in sorted(self.children):
            yield child

    def __contains__(self, key: str) -> bool:
        return any(child.key == key for child in self)

    def __repr__(self) -> str:
        return f"<{self._id}: {self.weight}>"

    def __str__(self) -> str:
        return f"{self._id}: {self.weight}"

    def childByKey(self, key: str) -> Optional["TimelineNode"]:
        for child in self.children:
            if child.key == key:
                return child
        return None

    def addChild(self, key: Tuple[str, NodeKind], *args):
        child = self.childByKey(key[0])
        if child is not None:
            if args:
                child.addChild(*args)
            child.weight += 1
            logger.debug(
                f"{key[1].name} {key[0]} added to {self.kind.name} {self.key}, weight is now: {child.weight}"
            )
        else:
            child = TimelineNode(*key)
            child.parent = self
            if args:
                child.addChild(*args)
            logger.debug(
                f"New {key[1].name} {key[0]} added to {self.kind.name} {self.key}"
            )


class Timeline(TimelineNode):
    """A container for the Timeline years.

    The container is the root of a tree whose children are the Year elements,
    Year children are Month elements, Month children are Day elements and Day children
    are Hour elements.
    """

    def __init__(self):
        super().__init__("Timeline", NodeKind.ROOT)
        self.weight = 0

    def addDatetime(self, dateTime: Tuple[str, str, str, str, str, str]):
        kind = (NodeKind.YEAR, NodeKind.MONTH, NodeKind.DAY, NodeKind.HOUR)
        nodes = [(key, kind[i]) for i, key in enumerate(dateTime[:4])]
        self.addChild(*nodes)
        self.weight += 1

    def addYear(self, year: TimelineNode):
        """Adds the given year to the year's container."""
        assert year.kind == NodeKind.YEAR
        year.parent = self

    @staticmethod
    def removeYear(year: TimelineNode):
        """Deletes the given year from the year's container."""
        assert year.kind == NodeKind.YEAR
        year.parent = None
        year.children = []

    def clear(self):
        self.children = []
