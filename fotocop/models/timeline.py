import logging
from enum import IntEnum
from copy import copy, deepcopy
from datetime import datetime
from calendar import monthrange

from typing import Optional, Tuple, List
from functools import total_ordering

from fotocop.util import nodemixin as nd
from fotocop.util import qtutil as QtUtil

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


class SelectionState(IntEnum):
    Unselected = 0
    PartiallySelected = 1
    Selected = 2


class SelectionFlag(IntEnum):
    Clear = 1
    Select = 2
    ClearAndSelect = 3
    Deselect = 4
    Toggle = 8


class TimeRange:
    def __init__(self, start=None, end=None):
        self.start = start or datetime.min
        self.end = end or datetime.today()

    def __eq__(self, other) -> bool:
        if not isinstance(other, TimeRange):
            return NotImplemented

        return other.start == self.start and other.end == self.end

    def __repr__(self) -> str:
        return f"<TimeRange({self.start}, {self.end})>"


class TimelineNodeSelection():

    selectionChanged = QtUtil.QtSignalAdapter(set, set, set)    # selected, partially selected, deselected
    timeRangeChanged = QtUtil.QtSignalAdapter(list)             # list of ordered TimeRange

    def __init__(self):
        self.selected = dict()
        self.partiallySelected = dict()

        self._selectedChildCount = dict()

        self._newSelected = set()
        self._newPartiallySelected = set()
        self._newDeselected = set()

    def select(self, itemSelection: List["TimelineNode"], command:SelectionFlag):
        # https://code.woboq.org/qt5/qtbase/src/corelib/itemmodels/qitemselectionmodel.cpp.html
        self._newSelected = set()
        self._newPartiallySelected = set()
        self._newDeselected = set()

        if command == SelectionFlag.Clear:
            command = SelectionFlag.Deselect

        if command == SelectionFlag.ClearAndSelect:
            for item in itemSelection:
                self._internalSelect(item, SelectionFlag.Clear)
            command = SelectionFlag.Select

        for item in itemSelection:
            self._internalSelect(item, command)

        self.selectionChanged.emit(self._newSelected, self._newPartiallySelected, self._newDeselected)
        self.timeRangeChanged.emit(self.selectedRanges())

    def clearSelection(self):
        self.select(list(self.selected.values()), SelectionFlag.Clear)

    def selectionState(self, item: "TimelineNode") -> SelectionState:
        date_ = item.date

        if date_ in self.selected:
            return SelectionState.Selected

        if date_ in self.partiallySelected:
            return SelectionState.PartiallySelected

        return SelectionState.Unselected

    def createPreselection(self) -> "TimelineNodeSelection":
        presel = TimelineNodeSelection()
        presel.selected = copy(self.selected)
        presel.partiallySelected = copy(self.partiallySelected)
        presel._selectedChildCount = copy(self._selectedChildCount)
        return presel

    def selectedRanges(self) -> List[TimeRange]:
        selectedRanges = list()
        for item in self.selected.values():
            if item.is_root:
                continue
            selectedRanges = self._mergeToRanges(item.timeRange, selectedRanges)
        return selectedRanges

    def _mergeToRanges(self, timeRange: TimeRange, timeRanges: List[TimeRange]) -> List[TimeRange]:
        if timeRanges:
            head = timeRanges[0]
            tail = timeRanges[1:]
            mergedRanges = self._mergeRanges(timeRange, head)

            if len(mergedRanges) == 1:
                # timeRange and head overlapped: merge result with tail.
                return self._mergeToRanges(mergedRanges[0], tail)

            # timeRange and head disjointed.
            if mergedRanges[0] == timeRange:
                # timeRange is before head: merge is completed.
                mergedRanges.extend(tail)
                return mergedRanges

            # timeRange is after head: continue merging with tail.
            head = [head]
            merged = self._mergeToRanges(timeRange, tail)
            head.extend(merged)
            return head

        return [timeRange]

    @staticmethod
    def _mergeRanges(r1: TimeRange, r2: TimeRange) -> List[TimeRange]:
        if r1.end < r2.start:
            # r1 before r2.
            return [r1, r2]
        if r1.start > r2.end:
            # r1 after r2.
            return [r2, r1]
        # r1 and r2 overlapped
        if r1.start < r2.start:
            # r1 starts before r2
            if r1.end < r2.end:
                # s1, s2, e1, e2: return s1, e2
                return [TimeRange(r1.start, r2.end)]
            # s1, s2, e2, e1: return s1, e1
            return [TimeRange(r1.start, r1.end)]
        # r1 starts after r2
        if r1.end < r2.end:
            # s2, s1, e1, e2: return
            return [TimeRange(r2.start, r2.end)]
        # s2, s1, e2, e1: return s2, e1
        return [TimeRange(r2.start, r1.end)]

    def _internalSelect(self, item: "TimelineNode", command: SelectionFlag):
        if command == SelectionFlag.Clear:
            # Deselect all selected items.
            for selectedItem in list(self.selected.values()):
                self._internalSelect(selectedItem, SelectionFlag.Deselect)

        elif command == SelectionFlag.Toggle:
            # Toggle item selection state id selected or unselected.
            # If item is partially selected, toggle all its children.
            if item.date in self.selected:
                self._internalSelect(item, SelectionFlag.Deselect)
            elif item.date in self.partiallySelected:
                for child in item.children:
                    self._internalSelect(child, SelectionFlag.Toggle)
            else:   # Item is unselected
                self._internalSelect(item, SelectionFlag.Select)

        elif command == SelectionFlag.Select:
            self._downwardSelect(item)
            self._upwardSelect(item.parent)

        elif command == SelectionFlag.Deselect:
            self._downwardDeselect(item)
            self._upwardDeselect(item.parent)

        else:
            logger.warning(
                f"{command.name} command is not supported by _internalSelect"
            )

    def _downwardSelect(self, item: "TimelineNode"):
        # Make item selected if not already and propagate selection on its children
        if self.selectionState(item) != SelectionState.Selected:
            self._select(item)
            for child in item.children:
                self._downwardSelect(child)

    def _upwardSelect(self, item: Optional["TimelineNode"]):
        # Item may be None if call from the root node
        if item is not None:
            # An items' child has been selected: increment its selected child count
            childCount = item.childCount()
            try:
                selectedChildCount = self._selectedChildCount[item.date]
            except KeyError:
                selectedChildCount = 0
            selectedChildCount = min(selectedChildCount + 1, childCount)
            # selectedChildCount = min(item._selectedChildCount + 1, childCount)
            self._selectedChildCount[item.date] = selectedChildCount
            # item._selectedChildCount = selectedChildCount
            if selectedChildCount == childCount:
                # All item's children are now selected: make it selected and propagate
                # selection on its parent
                self._select(item)
                self._upwardSelect(item.parent)
            else:
                # At least one item's child is not selected: make it partially selected
                # and propagate partial selection on its parent
                self._partialSelect(item)
                self._upwardPartialSelect(item.parent)

    def _upwardPartialSelect(self, item: Optional["TimelineNode"]):
        # Item may be None if call from the root node
        if item is not None:
            self._partialSelect(item)
            self._upwardPartialSelect(item.parent)

    def _downwardDeselect(self, item: "TimelineNode"):
        # Make item unselected if not already and propagate deselection on its children
        if self.selectionState(item) != SelectionState.Unselected:
            self._deselect(item)
            for child in item.children:
                self._downwardDeselect(child)

    def _upwardDeselect(self, item: Optional["TimelineNode"]):
        # Item may be None if call from the root node
        if item is not None:
            # An item's child has been deselected: decrement its selected child count
            try:
                selectedChildCount = self._selectedChildCount[item.date]
            except KeyError:
                selectedChildCount = 0
            selectedChildCount = max(0, selectedChildCount - 1)
            # selectedChildCount = max(0, item._selectedChildCount - 1)
            self._selectedChildCount[item.date] = selectedChildCount
            # item._selectedChildCount = selectedChildCount
            if selectedChildCount == 0:
                # All item's children are unselected: deselect it and propagate
                # deselection on its parent
                self._deselect(item)
                self._upwardDeselect(item.parent)
            elif self.selectionState(item) == SelectionState.Selected:
                # Item was previously selected: make it partially selected and propagate
                # partial selection on its parent
                self._partialSelect(item)
                self._upwardPartialSelect(item.parent)
            else:
                # Item was already partially selected: it remains in the same state
                pass

    def _select(self, item: "TimelineNode"):
        # Children of a selected item are necessarily all selected
        self._selectedChildCount[item.date] = item.childCount()
        # item._selectedChildCount = item.childCount()
        try:
            # If item was partially selected, it is no more so
            del self.partiallySelected[item.date]
        except KeyError:
            pass
        # Item is no more partially selected
        if self.selectionState(item) == SelectionState.Selected:
            # Item was already selected: nothing to do
            return
        else:
            # Item was unselected or partially selected: make it selected and add it to
            # the newly selected collection
            self.selected[item.date] = item
            self._newSelected.add(item)

    def _deselect(self, item: "TimelineNode"):
        # An unselected item cannot have selected children
        self._selectedChildCount[item.date] = 0
        # item._selectedChildCount = 0
        try:
            # If item was selected, it is no more so
            del self.selected[item.date]
        except KeyError:
            # Item was not selected
            try:
                # If item was partially selected, it is no more so
                del self.partiallySelected[item.date]
            except KeyError:
                # Item was already unselected: nothing to do
                return
        # Item has been deselected: add it to the newly deselected collection
        self._newDeselected.add(item)

    def _partialSelect(self, item: "TimelineNode"):
        try:
            # If item was selected, it is no more so
            del self.selected[item.date]
        except KeyError:
            pass
        # Item is no more selected
        if self.selectionState(item) == SelectionState.PartiallySelected:
            # Item was already partially selected: nothing to do
            return
        else:
            # Item was unselected or selected: make it partially selected and add it to
            # the newly partially selected collection
            self.partiallySelected[item.date] = item
            self._newPartiallySelected.add((item))

    def _partialDeselect(self, item: "TimelineNode"):
        try:
            del self.partiallySelected[item.date]
        except KeyError:
            pass
        else:
            self._newPartiallySelected.discard(item)


@total_ordering
class TimelineNode(nd.NodeMixin):
    """A node of the timeline has a unique id and a weight (images count).

    The depth of the node defines its kind: 0 for the timeline'root, 1 for YEAR,
        2 for MONTH, 3 for DAY and 4 for HOUR.
    """

    def __init__(self, id_: str, weight: int = 1):
        self._id = id_
        self.weight = weight

    def __hash__(self) -> int:
        return id(self)

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
        if depth == 0:  # root
            return self.key
        if depth == 1:  # year
            return self.key
            # return f"{self.key}: {self.weight}"
        if depth == 2:  # month
            return f"{self.parent.key}/{MONTH_AS_TEXT[self.key][1]}"
        if depth == 3:  # day
            return f"{self.parent.asText}/{self.key}"
        if depth == 4:  # hour
            return f"{self.parent.asText}-{self.key}h"
        return ""

    @property
    def date(self) -> str:
        if self.is_root:
            return "/"
        return f"{self.parent.date}/{self._id}"

    @property
    def timeRange(self):
        depth = self.depth
        if depth == 0:  # root
            return TimeRange()
        if depth == 1:  # year
            return TimeRange(
                start=datetime(int(self.key), 1, 1),
                end=datetime(int(self.key), 12, 31, 23, 59, 59)
            )
        if depth == 2:  # month
            year = int(self.parent.key)
            month = int(self.key)
            lastDay = monthrange(year, month)[1]
            return TimeRange(
                start=datetime(year, month, 1),
                end=datetime(year, month, lastDay, 23, 59, 59)
            )
        if depth == 3:  # day
            return TimeRange(
                start=datetime(
                    int(self.parent.parent.key),
                    int(self.parent.key),
                    int(self.key)
                ),
                end=datetime(
                    int(self.parent.parent.key),
                    int(self.parent.key), int(self.key),
                    23, 59, 59
                )
            )
        if depth == 4:  # hour
            return TimeRange(
                start=datetime(
                    int(self.parent.parent.parent.key),
                    int(self.parent.parent.key),
                    int(self.parent.key),
                    int(self.key)
                ),
                end=datetime(
                    int(self.parent.parent.parent.key),
                    int(self.parent.parent.key),
                    int(self.parent.key),
                    int(self.key),
                    59, 59
                )
            )
        return TimeRange()

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
        """Method called after attaching to `parent` to sort children."""
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
        self._selection = TimelineNodeSelection()
        self._oldSelection = None

    def selectionModel(self) -> TimelineNodeSelection:
        return self._selection

    def setPreselectionMode(self, isPresel: bool):
        if isPresel:
            assert self._oldSelection is None, "Cannot enter twice in preselection mode!"
            presel = self._selection.createPreselection()
            self._oldSelection = deepcopy(self._selection)
            self._selection = presel
        else:
            assert self._oldSelection is not None, "Not in preselection mode: cannot quit it!"
            self._selection = self._oldSelection
            self._oldSelection = None

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
        self.weight = 0
        self.maxWeightByDepth = [1, 1, 1, 1]
        self._selection = TimelineNodeSelection()
