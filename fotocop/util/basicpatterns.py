class Singleton(type):
    """A Standard Singleton metaclass."""
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class ObjectFactory(object):
    """A general purpose object factory."""
    def __init__(self):
        self._builders = {}

    def register_builder(self, key, builder):
        self._builders[key] = builder

    def create(self, key, *args, **kwargs):
        builder = self._builders.get(key)
        if not builder:
            raise ValueError(key)
        return builder(*args, **kwargs)


class Visitor(object):
    """Base class for visitors.
    """
    def visit(self, node, *args, **kwargs):
        """Visit a node.

        Calls 'visitClassName' on itself passing 'node', where 'ClassName' is
        the node's class.
        If the visitor does not implement an appropriate visitation method,
        will go up the `MRO` until a match is found.

        Args:
            node: The node to visit.

        Raises:
            NotImplementedError exception if the search exhausts all classes
                of 'node'.

        Returns:
            The return value of the called visitation method.
        """
        if isinstance(node, type):
            mro = node.mro()
        else:
            mro = type(node).mro()

        for cls in mro:
            clsName = cls.__name__
            clsName = clsName[0].upper() + clsName[1:]
            meth = getattr(self, 'visit' + clsName, None)
            if meth is not None:
                return meth(node, *args, **kwargs)

        clsName = node.__class__.__name__
        clsName = clsName[0].upper() + clsName[1:]
        raise NotImplementedError(f'No visitation method visit{clsName}')


def visitable(cls):
    """A decorator to make a class 'visitable'.

    Args:
        cls: the class to decorate.

    Returns:
        the decorated class.
    """
    def accept(self, visitor: Visitor, *args, **kwargs):
        return visitor.visit(self, *args, **kwargs)
    cls.accept = accept
    return cls
