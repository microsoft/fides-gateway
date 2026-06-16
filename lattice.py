from collections.abc import Iterable
from enum import Enum
from abc import ABC, abstractmethod
from typing import (
    Any,
    ClassVar,
    Generic,
    Self,
    TypeVar,
)

from pydantic import BaseModel, Field

## Bounded lattices


class Lattice(ABC):
    """Abstract base class for (bounded) IFC lattices."""

    @abstractmethod
    def leq(self, other: Any) -> bool:
        """Returns True if self <= other in the lattice."""
        pass

    @abstractmethod
    def join(self, other: Any) -> Any:
        """Returns the least upper bound of self and other."""
        pass

    @abstractmethod
    def meet(self, other: Any) -> Any:
        """Returns the greatest lower bound of self and other."""
        pass

    @abstractmethod
    def __repr__(self) -> str:
        pass

    @abstractmethod
    def __eq__(self, other: object) -> bool:
        pass

    @abstractmethod
    def to_json(self) -> Any:
        """Returns a JSON-serializable representation of this lattice element."""
        pass

    # --- Syntax sugar ---
    def __le__(self, other: "Lattice") -> bool:
        """Returns True if self <= other."""
        return self.leq(other)


## Standard confidentiality lattice


class ConfidentialityLattice(Lattice):
    class Level(Enum):
        LOW = 0
        HIGH = 1

    def __init__(self, level: "ConfidentialityLattice.Level"):
        self.level = level

    def leq(self, other: "ConfidentialityLattice") -> bool:
        return self.level.value <= other.level.value

    def join(self, other: "ConfidentialityLattice") -> "ConfidentialityLattice":
        if self.leq(other):
            return other
        else:
            return self

    def meet(self, other: "ConfidentialityLattice") -> "ConfidentialityLattice":
        if self.leq(other):
            return self
        else:
            return other

    def __repr__(self) -> str:
        return f"{self.level.name.lower()}"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ConfidentialityLattice) and self.level == other.level

    def __hash__(self) -> int:
        return hash((type(self), self.level))

    def to_json(self) -> str:
        return self.level.name.lower()

    # --- Class constructors ---
    @classmethod
    def low(cls) -> Self:
        return cls(cls.Level.LOW)

    @classmethod
    def high(cls) -> Self:
        return cls(cls.Level.HIGH)

    @classmethod
    def from_string(cls, s: str) -> Self:
        normalized = s.strip().lower()
        if normalized == "low":
            return cls.low()
        if normalized == "high":
            return cls.high()
        raise ValueError(f"Invalid confidentiality level: {s!r}")


## Standard integrity lattice


class IntegrityLattice(Lattice):
    class Level(Enum):
        TRUSTED = 0
        UNTRUSTED = 1

    def __init__(self, level: "IntegrityLattice.Level"):
        self.level = level

    def leq(self, other: "IntegrityLattice") -> bool:
        return self.level.value <= other.level.value

    def join(self, other: "IntegrityLattice") -> "IntegrityLattice":
        if self.leq(other):
            return other
        else:
            return self

    def meet(self, other: "IntegrityLattice") -> "IntegrityLattice":
        if self.leq(other):
            return self
        else:
            return other

    def __repr__(self) -> str:
        return f"{self.level.name.lower()}"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, IntegrityLattice) and self.level == other.level

    def __hash__(self) -> int:
        return hash((type(self), self.level))

    def to_json(self) -> str:
        return self.level.name.lower()

    # --- Class constructors ---
    @classmethod
    def trusted(cls) -> Self:
        return cls(cls.Level.TRUSTED)

    @classmethod
    def untrusted(cls) -> Self:
        return cls(cls.Level.UNTRUSTED)

    @classmethod
    def from_string(cls, s: str) -> Self:
        normalized = s.strip().lower()
        if normalized == "trusted":
            return cls.trusted()
        if normalized == "untrusted":
            return cls.untrusted()
        raise ValueError(f"Invalid integrity level: {s!r}")


## Inverse of a lattice

L = TypeVar("L", bound="Lattice")


class InverseLattice(Lattice, Generic[L]):
    def __init__(self, inner: L):
        self.inner = inner

    def _check_compatible(self, other: "InverseLattice[L]") -> None:
        if type(self) is not type(other):
            raise TypeError(
                f"Cannot combine {type(self).__name__} with {type(other).__name__}: "
                f"different inverse lattices"
            )

    def leq(self, other: Self) -> bool:
        self._check_compatible(other)
        return other.inner.leq(self.inner)  # Invert the order

    def join(self, other: Self) -> Self:
        self._check_compatible(other)
        return type(self)(self.inner.meet(other.inner))  # Invert operation

    def meet(self, other: Self) -> Self:
        self._check_compatible(other)
        return type(self)(self.inner.join(other.inner))  # Invert operation

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.inner!r})"

    def __eq__(self, other: object) -> bool:
        if type(self) is not type(other):
            return False
        return self.inner == other.inner  # type: ignore[attr-defined]

    def __hash__(self) -> int:
        return hash((type(self), self.inner))

    def to_json(self) -> Any:
        return {"inverse": self.inner.to_json()}


## Powerset lattice ordered by subset inclusion

T = TypeVar("T")  # The type of elements in the base set


class PowersetLattice(Lattice, Generic[T]):
    """Powerset lattice ordered by subset inclusion.

    The universe is not stored explicitly; instead, the top element is marked
    by placing :attr:`SENTINEL` inside ``subset``.

    The sentinel is a property of the *lattice* (the class), not of any single
    element. To use a different marker, subclass and override
    :attr:`SENTINEL`. Operations between two ``PowersetLattice`` instances
    require them to be of the same (sub)class.
    """

    SENTINEL: ClassVar[Any] = "public"

    def __init__(self, subset: Iterable[T]):
        self.subset: frozenset[Any] = frozenset(subset)

    @property
    def is_top(self) -> bool:
        return type(self).SENTINEL in self.subset

    def _check_compatible(self, other: "PowersetLattice[T]") -> None:
        if type(self) is not type(other):
            raise TypeError(
                f"Cannot combine {type(self).__name__} with {type(other).__name__}: "
                f"different powerset lattices"
            )

    def leq(self, other: Self) -> bool:
        self._check_compatible(other)
        if other.is_top:
            return True
        if self.is_top:
            return False
        return self.subset.issubset(other.subset)

    def join(self, other: Self) -> Self:
        self._check_compatible(other)
        cls = type(self)
        if self.is_top or other.is_top:
            return cls.top()
        return cls(self.subset.union(other.subset))

    def meet(self, other: Self) -> Self:
        self._check_compatible(other)
        cls = type(self)
        # top is the identity for meet
        if self.is_top:
            return cls(other.subset)
        if other.is_top:
            return cls(self.subset)
        return cls(self.subset.intersection(other.subset))

    def __repr__(self) -> str:
        name = type(self).__name__
        if self.is_top:
            return f"{name}({{{type(self).SENTINEL}}})"
        try:
            sorted_items = sorted(map(str, self.subset))
        except TypeError:
            sorted_items = [str(x) for x in self.subset]
        return f"{name}({{{', '.join(sorted_items)}}})"

    def __eq__(self, other: object) -> bool:
        if type(self) is not type(other):
            return False
        # All "top" values are equal regardless of any other members.
        if self.is_top or other.is_top:  # type: ignore[attr-defined]
            return self.is_top and other.is_top  # type: ignore[attr-defined]
        return self.subset == other.subset  # type: ignore[attr-defined]

    def __hash__(self) -> int:
        if self.is_top:
            return hash((type(self), "⊤"))
        return hash((type(self), self.subset))

    def to_json(self) -> list[Any]:
        if self.is_top:
            return [type(self).SENTINEL]
        try:
            return sorted(self.subset)
        except TypeError:
            return sorted(self.subset, key=str)

    @classmethod
    def bottom(cls) -> Self:
        return cls(frozenset())

    @classmethod
    def top(cls) -> Self:
        return cls(frozenset({cls.SENTINEL}))

    @classmethod
    def from_list(cls, items: Iterable[T]) -> Self:
        return cls(items)


## Product lattice

L1 = TypeVar("L1", bound=Lattice)
L2 = TypeVar("L2", bound=Lattice)


class ProductLattice(Lattice, Generic[L1, L2]):
    def __init__(self, left: L1, right: L2):
        self.left = left
        self.right = right

    def leq(self, other: Self) -> bool:
        return self.left <= other.left and self.right <= other.right

    def join(self, other: Self) -> Self:
        cls = type(self)
        return cls(self.left.join(other.left), self.right.join(other.right))

    def meet(self, other: Self) -> Self:
        cls = type(self)
        return cls(self.left.meet(other.left), self.right.meet(other.right))

    def __repr__(self) -> str:
        return f"({self.left!r}, {self.right!r})"

    def __eq__(self, other: object) -> bool:
        if type(self) is not type(other):
            return False
        return self.left == other.left and self.right == other.right  # type: ignore[attr-defined]

    def __hash__(self) -> int:
        return hash((type(self), self.left, self.right))

    def to_json(self) -> Any:
        return {"left": self.left.to_json(), "right": self.right.to_json()}


## Users lattice: powerset of strings denoting authorized readers,
## with a "public" sentinel for the universe of readers.


class Users(PowersetLattice[str]):
    """Powerset lattice of users (strings) with the ``"public"``
    sentinel marking the universe of users.

    Used as the inner lattice of the confidentiality dimension in
    :class:`SecurityLattice`; the inversion (via :class:`InverseLattice`) is
    what turns "more users" into "lower / less confidential".
    """

    SENTINEL: ClassVar[str] = "public"


## Security label: product of integrity and confidentiality


class SecurityLattice(ProductLattice[IntegrityLattice, InverseLattice[Users]]):
    """Product lattice combining integrity and confidentiality dimensions.

    Confidentiality is modeled as an *inverse* powerset of user strings
    (see :class:`Users`).

        A ⊑ B iff B ⊆ A (fewer readers ⇒ higher / more confidential)
        join (LUB) = intersection of users  (restricts audience)
        meet (GLB) = union of users         (relaxes audience)
        "public" sentinel = universe of users = bottom (least restrictive)
    """

    def __init__(
        self,
        integrity: IntegrityLattice,
        confidentiality: InverseLattice[Users],
    ):
        super().__init__(integrity, confidentiality)

    @property
    def integrity(self) -> IntegrityLattice:
        return self.left

    @property
    def confidentiality(self) -> InverseLattice[Users]:
        return self.right

    def __repr__(self) -> str:
        readers = self.confidentiality.inner
        if readers.is_top:
            conf_str = f"[{Users.SENTINEL}]"
        else:
            conf_str = f"[{', '.join(sorted(readers.subset))}]"
        return f"{{integrity: {self.integrity!r}, confidentiality: {conf_str}}}"

    def to_json(self) -> Any:
        # Flatten the inverse wrapper so confidentiality serializes as a plain
        # sorted list of reader strings (matching lattice.ts).
        return {
            "integrity": self.integrity.to_json(),
            "confidentiality": self.confidentiality.inner.to_json(),
        }

    # --- Convenience constructors ---

    @classmethod
    def with_readers(
        cls,
        integrity: IntegrityLattice,
        readers: Iterable[str],
    ) -> "SecurityLattice":
        """Build a label from an integrity level and an explicit set of readers."""
        return cls(integrity, InverseLattice(Users.from_list(readers)))

    @classmethod
    def public(cls, integrity: IntegrityLattice | None = None) -> "SecurityLattice":
        """Lattice whose confidentiality is the universe of readers (bottom)."""
        i = integrity if integrity is not None else IntegrityLattice.trusted()
        # public = bottom of confidentiality = InverseLattice(top of Users)
        return cls(i, InverseLattice(Users.top()))

    @classmethod
    def default(cls) -> "SecurityLattice":
        """``(trusted, public)`` — the most permissive label in both dimensions."""
        return cls.public()


## Wire-format IFC labels backed by SecurityLattice


class IFCLabels(BaseModel):
    """Information-flow-control labels produced by a labeling function.

    Pydantic model used as the wire / ``_meta`` representation of an IFC
    label. Lattice operations (join, equality) are delegated to
    :class:`SecurityLattice` via :meth:`to_security_lattice` so callers can
    rely on the lattice's comparison and join semantics instead of
    re-implementing them.
    """

    integrity: str = Field(
        default="trusted",
        description=(
            "Integrity level of the associated data (e.g. 'trusted', 'untrusted')."
        ),
    )
    confidentiality: list[str] = Field(
        default_factory=list,
        description=(
            "Set of principal identifiers (e.g. AAD user GUIDs) to whom the"
            " associated data is considered confidential."
        ),
    )

    def to_security_lattice(self) -> "SecurityLattice":
        """Build the :class:`SecurityLattice` representation of this label."""
        return SecurityLattice.with_readers(
            IntegrityLattice.from_string(self.integrity),
            self.confidentiality,
        )

    @classmethod
    def from_security_lattice(cls, label: "SecurityLattice") -> "IFCLabels":
        """Recover an :class:`IFCLabels` from its :class:`SecurityLattice` form."""
        readers = label.confidentiality.inner
        if readers.is_top:
            conf: list[str] = [Users.SENTINEL]
        else:
            conf = sorted(readers.subset)
        return cls(integrity=label.integrity.to_json(), confidentiality=conf)

    def join(self, other: "IFCLabels") -> "IFCLabels":
        """Lattice join (lub) computed via :class:`SecurityLattice`."""
        return IFCLabels.from_security_lattice(
            self.to_security_lattice().join(other.to_security_lattice())
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, IFCLabels):
            return NotImplemented
        return self.to_security_lattice() == other.to_security_lattice()

    def __hash__(self) -> int:
        return hash(self.to_security_lattice())


def join_label_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Join two label dicts (as carried in ``_meta``) via :class:`SecurityLattice`."""
    return IFCLabels(**left).join(IFCLabels(**right)).model_dump()


def labels_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Lattice-aware equality on label dicts (confidentiality is set-valued)."""
    return IFCLabels(**left) == IFCLabels(**right)
