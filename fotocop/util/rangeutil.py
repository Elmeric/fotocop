from itertools import groupby


# http://stupidpythonideas.blogspot.com/2014/01/grouping-into-runs-of-adjacent-values.html
class AdjacentKey:
    r"""
    >>> [list(g) for k, g in groupby([0, 1, 2, 3, 5, 6, 7, 10, 11, 13, 16], AdjacentKey)]
    [[0, 1, 2, 3], [5, 6, 7], [10, 11], [13], [16]]
    """
    __slots__ = ["obj"]

    def __init__(self, obj) -> None:
        self.obj = obj

    def __eq__(self, other) -> bool:
        ret = self.obj - 1 <= other.obj <= self.obj + 1
        if ret:
            self.obj = other.obj
        return ret


def first_and_last(iterable):
    start = end = next(iterable)
    for end in iterable:
        pass
    return start, end


def runs(iterable):
    r"""
    identify adjacent elements in pre-sorted data

    :param iterable: sorted data

    >>> list(runs([0, 1, 2, 3, 5, 6, 7, 10, 11, 13, 16]))
    [(0, 3), (5, 7), (10, 11), (13, 13), (16, 16)]
    >>> list(runs([0]))
    [(0, 0)]
    >>> list(runs([0, 1, 10, 100, 101]))
    [(0, 1), (10, 10), (100, 101)]
    """

    for k, g in groupby(iterable, AdjacentKey):
        yield first_and_last(g)
