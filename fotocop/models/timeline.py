import logging

from typing import Optional, Tuple, List
from functools import total_ordering

from fotocop.util import nodemixin as nd

logger = logging.getLogger(__name__)


NODE_KIND = {
    0:  "ROOT",
    1:  "YEAR",
    2:  "MONTH",
    3:  "DAY",
    4:  "HOUR",
}


MONTH_AS_TEXT = {
    "01": ("January", "Jan"),
    "02": ("February", "Feb"),
    "03": ("March", "Mar"),
    "04": ("April", "Apr"),
    "05": ("May", "May"),
    "06": ("June", "Jun"),
    "07": ("July", "Jul"),
    "08": ("August", "Aug"),
    "09": ("September", "Sep"),
    "10": ("October", "Oct"),
    "11": ("November", "Nov"),
    "12": ("December", "Dec"),
}


@total_ordering
class TimelineNode(nd.NodeMixin):
    """A node of the timeline has a unique id and a weight (images count).

    The depth of the node defines its kind: 0 for the timeline'root, 1 for YEAR,
        2 for MONTH, 3 for DAY and 4 for HOUR.
    """

    def __init__(self, id_: str, weight: int = 1):
        self._id = id_
        self.weight = weight

    @property
    def key(self) -> str:
        return self._id

    @property
    def kind(self) -> str:
        try:
            return NODE_KIND[self.depth]
        except KeyError:
            return "UNKNOWN"

    @property
    def asText(self) -> str:
        depth = self.depth
        if depth == 0:
            return self.key
        if depth == 1:
            return f"{self.key}: {self.weight}"
        if depth == 2:
            return f"{self.parent.key}/{MONTH_AS_TEXT[self.key][1]}"
        if depth == 3:
            return f"{self.parent.asText}/{self.key}"
        if depth == 4:
            return f"{self.parent.asText}-{self.key}h"
        return ""

    def __eq__(self, other: "TimelineNode") -> bool:
        if not isinstance(other, TimelineNode):
            return NotImplemented
        if other.parent != self.parent:
            return False
        return self.key == other.key

    def __lt__(self, other: "TimelineNode") -> bool:
        if not isinstance(other, TimelineNode):
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
        return f"<TimelineNode({self._id}, {self.weight})>"

    def __str__(self) -> str:
        return f"{self.asText}: {self.weight}"

    def _post_attach(self, parent: "TimelineNode"):
        """Method call after attaching to `parent` to sort children."""
        parent._NodeMixin__children = sorted(parent.children)

    def childByKey(self, key: str) -> Optional["TimelineNode"]:
        """Returns the node's children having the given key, None if not found"""
        for child in self.children:
            if child.key == key:
                return child
        return None

    def addChild(self, maxWeightByDepth: List[int], key: str, *args):
        """Add (or increment weight) a child with key id to the current node.

        Recursively add child with key in args to the new child.
        Create the new child if none exists with a key id, oherwise, it only increments
        its weight.
        Update the new max weight of children at this depth (depth = kind of child).

        Args:
            maxWeightByDepth: max weight of children for each depth.
            key: id of the child to add / update.
            *args: if not empty, list of node's key to recursively add / update.
        """
        child = self.childByKey(key)
        if child is not None:
            # A child exists with that key: update its weight and the max weight of
            # children at this depth
            weight = child.weight
            weight += 1
            depth = child.depth - 1
            maxWeightAtDepth = maxWeightByDepth[depth]
            if weight > maxWeightAtDepth:
                maxWeightByDepth[depth] = weight
            child.weight = weight
            logger.debug(
                f"{child.kind} {key} exists for {self.kind} {self.key}, weight is now: {weight}"
            )
            # Recursively add children in args to the updated child
            if args:
                child.addChild(maxWeightByDepth, *args)
        else:
            # Create a new child. Its weight is set to 1 by the constructor
            child = TimelineNode(key)
            child.parent = self
            logger.debug(
                f"New {child.kind} {key} added to {self.kind} {self.key}"
            )
            # Recursively add children in args to the created child
            if args:
                child.addChild(maxWeightByDepth, *args)

    def childCount(self):
        return len(self.children)


class Timeline(TimelineNode):
    """A container for the Timeline years.

    The container is the root of a tree whose children are the Year elements,
    Year children are Month elements, Month children are Day elements and Day children
    are Hour elements.
    """
    def __init__(self):
        super().__init__("Timeline")
        self.weight = 0
        self.maxWeightByDepth = [1, 1, 1, 1]

    def addDatetime(self, dateTime: Tuple[str, str, str, str, str, str]):
        """Add a image date/time to the timeline.

        Image's date/time are added as they are retrieved from exif data.

        Args:
            dateTime: the exif date/time to add to the timeline.
        """
        self.addChild(self.maxWeightByDepth, *dateTime[:4])
        self.weight += 1

    def clear(self):
        self.children = []
