"""A simple signal/slot implementation.

From https://github.com/mdomke/signaling

Usage:
    Define a signal by instanciating a `Signal` object:
        ``modelChanged = signal.Signal()``
    The signal object can be optionnaly named:
        ``modelChanged = signal.Signal(name='SessionChanged')``
    A signal object can accept an arguments list:
        ``modelChanged = signal.Signal(name='ProjectChanged', args=['reason'])``
    Connect functions to the signal using 'connect':
        ``project.modelChanged.connect(self.updateUI)``
    Any callable can be connected to a Signal but it **must** accept keywords
    ('**kwargs'):
    Emit the signal to call all connected callbacks using `emit`:
        ``project.modelChanged.emit(reason=dt.ProjectChange.NEW)``
"""
import inspect
import logging
from typing import List, Callable
from copy import copy

logger = logging.getLogger(__name__)


class SignalSlotException(Exception):
    """Base signal/slot exception."""
    pass


class InvalidSlot(SignalSlotException):
    """Indicates that the slot implementation is invalid."""
    pass


class InvalidEmit(SignalSlotException):
    """Indicates that the emit method was called with invalid arguments."""
    pass


class Signal(object):
    """A Signal class for basic event-style programming.

    Define a signal by instantiating a `Signal` object.
    Optionaly, you can declare a list of argument names for this signal.
    Any callable can be connected to a Signal, it **must** accept keywords
    ('**kwargs').
    Connect your function to the signal using 'connect'.
    Emit the signal to call all connected callbacks using `emit`.
    Processing signal emit events can be pause / resume.

    Attributes:
        name (str): the optional signal name.
        args (List[str]): the signal specification (no args by default).
        slots (List[Callable]): the functions to be called on signal emission.
        _paused (bool): When True, slots are not called on signal emission.
    """
    def __init__(self, args: List[str] = None, name: str = None):
        self.name = name
        self.args = args
        self.slots = []
        self._paused = False

    def connect(self, slot: Callable):
        """Connect 'slot' to this signal.

        Args:
            slot: Callable object which accepts keyword arguments.

        Raises:
            InvalidSlot: If 'slot' doesn't accept keyword arguments.
        """
        self._check_slot_args(slot)

        if not self.is_connected(slot):
            self.slots.append(slot)

    def _check_slot_args(self, slot: Callable):
        """Check the slot signature match this signal specification.

        As the slot argument will be passed as keyword, the slot shall accept
        Keyword Args or **kwargs.

        Args:
            slot: Callable object to ckeck arguments compatibility.

        Raises:
            InvalidSlot: If 'slot' doesn't match.
        """
        sig = inspect.signature(slot)
        args = []
        varkw = None
        for p in sig.parameters.values():
            if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,
                          inspect.Parameter.KEYWORD_ONLY):
                args.append(p.name)
            elif p.kind == inspect.Parameter.VAR_KEYWORD:
                varkw = p.name

        if self.args and self.args != args and not varkw:
            raise InvalidSlot(f"Slot '{slot.__name__}' has to accept args "
                              f"{self.args} or **kwargs.")

        if not self.args and args:
            raise InvalidSlot(f"Slot '{slot.__name__}' has to be callable "
                              f"without arguments")

    def is_connected(self, slot):
        """Check if a callback 'slot' is connected to this signal."""
        return slot in self.slots

    def disconnect(self, slot):
        """"Disconnect 'slot' from this signal."""
        if inspect.ismethod(slot) and self.is_connected(slot):
            self.slots.remove(slot)
        elif inspect.isfunction(slot):
            for s in self.slots:
                if s.__func__ == slot:
                    self.slots.remove(s)

    def clearConnection(self):
        """"Disconnect all slots from this signal."""
        self.slots = []

    def pause(self):
        """"Pause connected slots calls from this signal."""
        self._paused = True

    def resume(self):
        """"Resume connected slots calls from this signal."""
        self._paused = False

    def is_paused(self):
        """"Check if connected slots calls is paused for this signal."""
        return self._paused

    def emit(self, **kwargs):
        """Emit signal by calling all connected slots, if not paused.

        The arguments supplied have to match the signal specification.

        Args:
            kwargs: Keyword arguments to be passed to connected slots.

        Raises:
            'InvalidEmit': If arguments don't match signal specification.
        """
        if self.is_paused():
            return

        self._check_emit_kwargs(kwargs)
        logger.debug(f'Signal **{self.name}** emitted with args {kwargs}')

        slots = copy(self.slots)
        if not slots:
            logger.debug(f'Signal **{self.name}** is emitted but has no slots')

        for slot in slots:
            logger.debug(
                f'==> Signal [{self.name}]: '
                f'calling slot **{slot.__name__}** '
                f'of {".".join(slot.__self__.__module__.split(".")[2:])}'
                f'.{slot.__self__.__class__.__name__}')
            slot(**kwargs)

    def _check_emit_kwargs(self, kwargs):
        """Check the emit kwargw match this signal specification.

        Args:
            kwargs: Keyword arguments to check against this signal specification.
        """
        if self.args and set(self.args).symmetric_difference(kwargs.keys()):
            raise InvalidEmit(f"Emit has to be called with args '{self.args}'")

        if not self.args and kwargs:
            raise InvalidEmit("Emit has to be called without arguments.")

    def __eq__(self, other) -> bool:
        """Return True if other has the same slots connected."""
        if not isinstance(other, Signal):
            return False
        return self.slots == other.slots

    def __repr__(self) -> str:
        return f"<Signal: '{self.name or 'anonymous'}'. Slots={len(self.slots)}>"
