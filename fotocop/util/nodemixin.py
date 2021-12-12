#!/usr/bin/env python3
# -*- coding: utf-8 -*-

class TreeError(RuntimeError):

    """Tree Error."""

    pass


class LoopError(TreeError):

    """Tree contains infinite loop."""

    pass


class NodeMixin(object):

    __slots__ = ("__parent", "__children")

    u"""
    From https://github.com/c0fec0de/anytree/blob/master/anytree/node/nodemixin.py
    
    The :any:`NodeMixin` class extends any Python class to a tree node.

    The only tree relevant information is the `parent` attribute.
    If `None` the :any:`NodeMixin` is root node.
    If set to another node, the :any:`NodeMixin` becomes the child of it.

    The `children` attribute can be used likewise.
    If `None` the :any:`NodeMixin` has no children (unless the node is set *as* parent).
    If set to any iterable of :any:`NodeMixin` instances, the nodes become children.
    """

    @property
    def parent(self):
        u"""
        Parent Node.
        On set, the node is detached from any previous parent node and attached
        to the new node.
        """
        try:
            return self.__parent
        except AttributeError:
            return None

    @parent.setter
    def parent(self, value):
        if value is not None and not isinstance(value, NodeMixin):
            msg = "Parent node %r is not of type 'NodeMixin'." % value
            raise TreeError(msg)
        try:
            parent = self.__parent
        except AttributeError:
            parent = None
        if parent is not value:
            self.__check_loop(value)
            self.__detach(parent)
            self.__attach(value)

    def __check_loop(self, node):
        if node is not None:
            if node is self:
                msg = "Cannot set parent. %r cannot be parent of itself."
                raise LoopError(msg % self)
            if self in node.path:
                msg = "Cannot set parent. %r is parent of %r."
                raise LoopError(msg % (self, node))

    def __detach(self, parent):
        if parent is not None:
            self._pre_detach(parent)
            parentchildren = parent.__children_
            assert any([child is self for child in parentchildren]), "Tree internal data is corrupt."
            # ATOMIC START
            parentchildren.remove(self)
            self.__parent = None
            # ATOMIC END
            self._post_detach(parent)

    def __attach(self, parent):
        if parent is not None:
            self._pre_attach(parent)
            parentchildren = parent.__children_
            assert not any([child is self for child in parentchildren]), "Tree internal data is corrupt."
            # ATOMIC START
            parentchildren.append(self)
            self.__parent = parent
            # ATOMIC END
            self._post_attach(parent)

    @property
    def __children_(self):
        try:
            return self.__children
        except AttributeError:
            self.__children = []
            return self.__children

    @property
    def children(self):
        """
        All child nodes.
        Modifying the children attribute modifies the tree.
        """
        return tuple(self.__children_)

    @staticmethod
    def __check_children(children):
        seen = set()
        for child in children:
            if not isinstance(child, NodeMixin):
                msg = ("Cannot add non-node object %r. "
                       "It is not a subclass of 'NodeMixin'.") % child
                raise TreeError(msg)
            if child not in seen:
                seen.add(child)
            else:
                msg = "Cannot add node %r multiple times as child." % child
                raise TreeError(msg)

    @children.setter
    def children(self, children):
        # convert iterable to tuple
        children = tuple(children)
        NodeMixin.__check_children(children)
        # ATOMIC start
        old_children = self.children
        del self.children
        try:
            self._pre_attach_children(children)
            for child in children:
                child.parent = self
            self._post_attach_children(children)
            assert len(self.children) == len(children)
        except Exception:
            self.children = old_children
            raise
        # ATOMIC end

    @children.deleter
    def children(self):
        children = self.children
        self._pre_detach_children(children)
        for child in self.children:
            child.parent = None
        assert len(self.children) == 0
        self._post_detach_children(children)

    def _pre_detach_children(self, children):
        """Method call before detaching `children`."""
        pass

    def _post_detach_children(self, children):
        """Method call after detaching `children`."""
        pass

    def _pre_attach_children(self, children):
        """Method call before attaching `children`."""
        pass

    def _post_attach_children(self, children):
        """Method call after attaching `children`."""
        pass

    @property
    def path(self):
        """
        Path of this `Node`.
        """
        return self._path

    @property
    def _path(self):
        path = []
        node = self
        while node:
            path.insert(0, node)
            node = node.parent
        return tuple(path)

    @property
    def ancestors(self):
        """
        All parent nodes and their parent nodes.
        """
        return self._path[:-1]

    @property
    def descendants(self):
        """
        All child nodes and all their child nodes.
        """
        pass
#        return tuple(PreOrderIter(self))[1:]

    @property
    def root(self):
        """
        Tree Root Node.
        """
        if self.parent:
            return self._path[0]
        else:
            return self

    @property
    def siblings(self):
        """
        Tuple of nodes with the same parent.
        """
        parent = self.parent
        if parent is None:
            return tuple()
        else:
            return tuple([node for node in parent.children if node != self])

    @property
    def leaves(self):
        """
        Tuple of all leaf nodes.
        """
        pass
#        return tuple(PreOrderIter(self, filter_=lambda node: node.is_leaf))

    @property
    def is_leaf(self):
        """
        `Node` has no children (External Node).
        """
        return len(self.__children_) == 0

    @property
    def is_root(self):
        """
        `Node` is tree root.
        """
        return self.parent is None

    @property
    def height(self):
        """
        Number of edges on the longest path to a leaf `Node`.
        """
        if self.__children_:
            return max([child.height for child in self.__children_]) + 1
        else:
            return 0

    @property
    def depth(self):
        """
        Number of edges to the root `Node`.
        """
        return len(self._path) - 1

    def _pre_detach(self, parent):
        """Method call before detaching from `parent`."""
        pass

    def _post_detach(self, parent):
        """Method call after detaching from `parent`."""
        pass

    def _pre_attach(self, parent):
        """Method call before attaching to `parent`."""
        pass

    def _post_attach(self, parent):
        """Method call after attaching to `parent`."""
        pass
