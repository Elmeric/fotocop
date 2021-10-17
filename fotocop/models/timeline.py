from typing import Optional, List, Tuple, Dict

from fotocop.util import nodemixin as nd


class TimelineNode(nd.NodeMixin):
    """ A node of the timeline has a unique id and a weight (images count)."""
    def __init__(self, id_: str):
        self._id = id_
        self.weight = 1

    @property
    def key(self) -> str:
        return self._id

    @property
    def record(self) -> Tuple[str, int]:
        return self._id, self.weight

    @property
    def childrenDict(self) -> Dict[str, 'TimelineNode']:
        return {child.key: child for child in self.children}

    def __len__(self) -> int:
        return len(self.children)

    def __iter__(self) -> 'TimelineNode':
        for child in self.children:
            yield child

    def __contains__(self, key: str) -> bool:
        return any(child.key == key for child in self)

    def __repr__(self) -> str:
        return f'<{self._id}: {self.weight}>'

    def __str__(self) -> str:
        return f'{self._id}: {self.weight}'

    def childByKey(self, key: str) -> Optional['TimelineNode']:
        for child in self.children:
            if child.key == key:
                return child
        return None

    def add(self, key: str, *args):
        child = self.childByKey(key)
        if child is not None:
            if args:
                child.add(*args)
            child.weight += 1
            print(f"  Child {key} added to {self.key}, weight is now: {child.weight}")
        else:
            child = TimelineNode(key)
            child.parent = self
            if args:
                child.add(*args)
            print(f"  New child {key} added to {self.key}")


class Year(TimelineNode):
    """ A Year has a unique id, a weight (images count) and a list of image keys."""

    @property
    def months(self) -> Dict[str, TimelineNode]:
        return {child.key: child for child in self.children}

    # def add(self, *args):
    #     monthKey, *others = args
    #     month = self.childByKey(monthKey)
    #     if month:
    #         month.add(*others)
    #         month.weight += 1
    #         print(f"  Month {monthKey} added to {self.key}, weight is now: {month.weight}")
    #     else:
    #         month = Month(monthKey)
    #         month.parent = self
    #         month.add(*others)
    #         print(f"  New month {monthKey} added to {self.key}")


class Month(TimelineNode):
    """ A Month has a unique id and owns Days.
    Its parent property identifies the Year its belongs to."""

    @property
    def days(self) -> Dict[str, TimelineNode]:
        return {child.key: child for child in self.children}

    # def add(self, *args):
    #     dayKey, *others = args
    #     day = self.childByKey(dayKey)
    #     if day:
    #         day.add(*others)
    #         day.weight += 1
    #         print(f"    Day {dayKey} added to {self.key}, weight is now: {day.weight}")
    #     else:
    #         day = Day(dayKey)
    #         day.parent = self
    #         day.add(*others)
    #         print(f"    New day {dayKey} added to {self.key}")


class Day(TimelineNode):
    """ A Day has a unique id and owns Hours.
    Its parent property identifies the Month its belongs to."""

    @property
    def hours(self) -> Dict[str, TimelineNode]:
        return {child.key: child for child in self.children}

    # def add(self, *args):
    #     hourKey, *others = args
    #     hour = self.childByKey(hourKey)
    #     if hour:
    #         hour.weight += 1
    #         print(f"      Hour {hourKey} {others} added to {self.key}, weight is now: {hour.weight}")
    #     else:
    #         hour = Hour(hourKey)
    #         hour.parent = self
    #         print(f"      New hour {hourKey} {others} added to {self.key}")


class Hour(TimelineNode):
    """ A Hour has a unique id and is a leaf.
    Its parent property identifies the Day its belongs to."""


class Timeline(TimelineNode):
    """A container for the Timeline years.

    The container is the root of a tree whose children are the Year elements,
    Year children are Month elements, Month children are Day elements and Day children
    are Hour elements.
    """
    def __init__(self):
        super().__init__("Timeline")
        self.weight = 0

    @property
    def years(self) -> Dict[str, Year]:
        return {child.key: child for child in self.children}

    def addDatetime(self, dateTime: Tuple[str, str, str, str, str, str]):
        self.add(*dateTime[:4])
        self.weight += 1

    def addYear(self, year: Year):
        """Adds the given year to the year's container."""
        year.parent = self

    @staticmethod
    def removeYear(year: Year):
        """Deletes the given year from the year's container."""
        year.parent = None
        year.children = []

    def clear(self):
        self.children = []
