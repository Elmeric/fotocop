import json
import re
from typing import Tuple, List, Dict, Optional, NamedTuple, Union
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path

from fotocop.util.basicpatterns import visitable
from fotocop.models import settings as Config
from fotocop.models.sources import Datation, Image


ORIGINAL_CASE = "Original Case"
UPPERCASE = "UPPERCASE"
LOWERCASE = "lowercase"


class FormatSpec(NamedTuple):
    name: str
    spec: Optional[str]


@visitable
@dataclass()
class TokenNode:
    name: str

    def __post_init__(self):
        self.parent: Optional["TokenNode"] = None
        self.children: Tuple["TokenNode"] = tuple()

    @property
    def isLeaf(self) -> bool:
        return len(self.children) == 0


@dataclass()
class TokenTree(TokenNode):
    pass

    def __post_init__(self):
        self.tokensByName: Dict[str, Token] = dict()


@dataclass()
class TokenFamily(TokenNode):
    pass


@dataclass()
class TokenGenus(TokenNode):
    pass


@dataclass()
class Token(TokenNode):
    genusName: str
    formatSpec: Optional[FormatSpec]

    def asText(self):
        if self.genusName == "Free text":
            return self.name
        return f"<{self.name}>"

    def format(self, image: Image, seq: int, downloadTime: datetime) -> str:
        genusName = self.genusName
        if genusName == "Image date":
            return image.datetime.asDatetime().strftime(self.formatSpec.spec)

        if genusName == "Today":
            return datetime.now().strftime(self.formatSpec.spec)

        if genusName == "Yesterday":
            delta = timedelta(days=1)
            d = datetime.now() - delta
            return d.strftime(self.formatSpec.spec)

        if genusName == "Download time":
            return downloadTime.strftime(self.formatSpec.spec)

        if genusName == "Name":
            filename = image.stem
            fmt = self.formatSpec.spec
            if fmt == "%F":  # UPPERCASE
                filename = filename.upper()
            elif fmt == "%f":    # lowercase
                filename = filename.lower()
            return filename

        if genusName == "Image number":
            n = re.search("(?P<imageNumber>[0-9]+$)", image.stem)
            if not n:
                return ""

            imageNumber = n.group("imageNumber")
            fmt = self.formatSpec.spec
            if fmt == "%NN":
                return imageNumber

            assert fmt in ("%N1", "%N2", "%N3", "%N4")
            d = int(fmt[-1])
            return imageNumber[-d:]

        if genusName == "Downloads today":
            return "????"

        if genusName == "Stored number":
            return "????"

        if genusName == "Session number":
            return f"{seq:{self.formatSpec.spec}}"

        if genusName == "Sequence letter":
            return "????"

        if genusName == "Session":
            return image.session

        if genusName == "Free text":
            return self.name


DATE_TIME_FORMATS = (
    FormatSpec("YYYYmmDD", "%Y%m%d"),
    FormatSpec("HHMMSS", "%H%M%S"),
    FormatSpec("YYYY", "%Y"),
    FormatSpec("YY", "%y"),
    FormatSpec("Month", "%B"),
    FormatSpec("mm", "%m"),
    FormatSpec("DD", "%d"),
    FormatSpec("Weekday", "%j"),
    FormatSpec("HH", "%H"),
    FormatSpec("MM", "%M"),
    FormatSpec("SS", "%S"),
)
NAME_FORMATS = (
    FormatSpec("Original Case", "%ff"),
    FormatSpec("UPPERCASE", "%F"),
    FormatSpec("lowercase", "%f"),
)
IMAGE_NUMBER_FORMATS = (
    FormatSpec("All digits", "%NN"),
    FormatSpec("Last digit", "%N1"),
    FormatSpec("Last 2 digits", "%N2"),
    FormatSpec("Last 3 digits", "%N3"),
    FormatSpec("Last 4 digits", "%N4"),
)
SEQUENCE_FORMATS = (
    FormatSpec("One digit", "01"),
    FormatSpec("Two digits", "02"),
    FormatSpec("Three digits", "03"),
    FormatSpec("Four digits", "04"),
    FormatSpec("Five digits", "05"),
    FormatSpec("Six digits", "06"),
)
SESSION_FORMATS = (
    FormatSpec("Session", None),
)

TOKEN_FAMILIES = ("Date time", "Filename", "Sequences", "Session")
TOKEN_GENUS = {
    "Date time": ("Image date", "Today", "Yesterday", "Download time"),
    "Filename": ("Name", "Image number"),
    "Sequences": ("Downloads today", "Stored number", "Session number", "Sequence letter"),
    "Session": ("Session",),
}

TOKEN_FORMATS = {
    "Image date": DATE_TIME_FORMATS,
    "Today": DATE_TIME_FORMATS,
    "Yesterday": DATE_TIME_FORMATS,
    "Download time": DATE_TIME_FORMATS,
    "Name": NAME_FORMATS,
    "Image number": IMAGE_NUMBER_FORMATS,
    "Downloads today": SEQUENCE_FORMATS,
    "Stored number": SEQUENCE_FORMATS,
    "Session number": SEQUENCE_FORMATS,
    "Sequence letter": SEQUENCE_FORMATS,
    "Session": SESSION_FORMATS,
}

TOKENS_ROOT_NODE = TokenTree("Tokens")
tokensByName = dict()
families = list()
for familyName in TOKEN_FAMILIES:
    family = TokenFamily(familyName)
    family.parent = TOKENS_ROOT_NODE
    families.append(family)
    children = list()
    for genusName in TOKEN_GENUS[familyName]:
        genus = TokenGenus(genusName)
        genus.parent = family
        children.append(genus)
        grandChildren = list()
        for formatSpec in TOKEN_FORMATS[genusName]:
            tokenName = f"{genusName} ({formatSpec[0]})"
            token = Token(tokenName, genusName, formatSpec)
            tokensByName[tokenName] = token
            token.parent = genus
            grandChildren.append(token)
        genus.children = tuple(grandChildren)
    family.children = tuple(children)
TOKENS_ROOT_NODE.children = families
TOKENS_ROOT_NODE.tokensByName = tokensByName


class Boundary(NamedTuple):
    start: int
    end: int


@dataclass()
class NamingTemplate:
    key: str
    name: str
    template: Tuple[Token, ...]

    def __post_init__(self):
        self.extension = LOWERCASE

    def asText(self) -> str:
        return "".join(token.asText() for token in self.template)

    def boundaries(self) -> List[Boundary]:
        start = 0
        boundaries = list()
        for token in self.template:
            end = start + len(token.asText())
            boundaries.append(Boundary(start, end))
            start = end
        return boundaries

    def format(self, image: Image, seq: int, downloadTime: datetime) -> str:
        name = "".join(token.format(image, seq, downloadTime) for token in self.template)
        if self.extension == LOWERCASE:
            extension = image.extension.lower()
        elif self.extension == UPPERCASE:
            extension = image.extension.upper()
        else:
            extension = image.extension
        return "".join((name, extension))


def namingTemplateHook(obj):
    if "__naming_template__" in obj:
        return NamingTemplate(
            obj["key"],
            obj["name"],
            obj["template"],
        )
    if "__token__" in obj:
        return Token(
            obj["name"],
            obj["genusName"],
            obj["formatSpec"],
        )
    return obj


class NamingTemplateEncoder(json.JSONEncoder):
    """A JSONEncoder to encode a NamingTemplate object in a JSON file.

    The NamingTemplate object is encoded into a string using its as_posix() method or into
    an empty string if the path name is not defined.
    """

    def default(self, obj):
        """Overrides the JSONEncoder default encoding method.

        Non NamingTemplate objects are passed to the JSONEncoder base class, raising a
        TypeError if its type is not supported by the base encoder.

        Args:
            obj: the object to JSON encode.

        Returns:
             The string-encoded Path object.
        """
        if isinstance(obj, NamingTemplate):
            obj.__dict__.update({"__naming_template__": True})
            return obj.__dict__
        if isinstance(obj, Token):
            obj.__dict__.update({"__token__": True})
            return obj.__dict__
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)


class NamingTemplatesError(Exception):
    """Exception raised on naming templates saving error."""

    pass


class NamingTemplates:

    builtinImageNamingTemplates = {
        "TPL_1": NamingTemplate(
            "TPL_1",
            "Original Filename - IMG_1234",
            (
                TOKENS_ROOT_NODE.tokensByName["Name (Original Case)"],
            ),
        ),
        "TPL_2": NamingTemplate(
            "TPL_2",
            "Date-Time and Downloads today - YYYYmmDD-HHMM-1",
            (
                TOKENS_ROOT_NODE.tokensByName["Image date (YYYYmmDD)"],
                Token("-", "Free text", None),
                TOKENS_ROOT_NODE.tokensByName["Image date (HH)"],
                TOKENS_ROOT_NODE.tokensByName["Image date (MM)"],
                Token("-", "Free text", None),
                TOKENS_ROOT_NODE.tokensByName["Downloads today (One digit)"],
            ),
        ),
        "TPL_3": NamingTemplate(
            "TPL_3",
            "Date and Downloads today - YYYYmmDD-1",
            (
                TOKENS_ROOT_NODE.tokensByName["Image date (YYYYmmDD)"],
                Token("-", "Free text", None),
                TOKENS_ROOT_NODE.tokensByName["Downloads today (One digit)"],
            ),
        ),
        "TPL_4": NamingTemplate(
            "TPL_4",
            "Date-Time and Image number - YYYYmmDD-HHMM-1234",
            (
                TOKENS_ROOT_NODE.tokensByName["Image date (YYYYmmDD)"],
                Token("-", "Free text", None),
                TOKENS_ROOT_NODE.tokensByName["Image date (HH)"],
                TOKENS_ROOT_NODE.tokensByName["Image date (MM)"],
                Token("-", "Free text", None),
                TOKENS_ROOT_NODE.tokensByName["Image number (All digits)"],
            ),
        ),
        "TPL_5": NamingTemplate(
            "TPL_5",
            "Date-Time and Session - YYYYmmDD-HHMM-Session-1",
            (
                TOKENS_ROOT_NODE.tokensByName["Image date (YYYYmmDD)"],
                Token("-", "Free text", None),
                TOKENS_ROOT_NODE.tokensByName["Image date (HH)"],
                TOKENS_ROOT_NODE.tokensByName["Image date (MM)"],
                Token("-", "Free text", None),
                TOKENS_ROOT_NODE.tokensByName["Session (Session)"],
                Token("-", "Free text", None),
                TOKENS_ROOT_NODE.tokensByName["Downloads today (One digit)"],
            ),
        ),
        "TPL_6": NamingTemplate(
            "TPL_6",
            "Date and Session - YYYYmmDD-Session-1",
            (
                TOKENS_ROOT_NODE.tokensByName["Image date (YYYYmmDD)"],
                Token("-", "Free text", None),
                TOKENS_ROOT_NODE.tokensByName["Session (Session)"],
                Token("-", "Free text", None),
                TOKENS_ROOT_NODE.tokensByName["Downloads today (One digit)"],
            ),
        ),
        # "TPL_7": NamingTemplate(
        #     "TPL_7",
        #     "Date-time (YYYYmmDD-HHMMSS)",
        #     (
        #         TOKENS_ROOT_NODE.tokensByName["Image date (YYYYmmDD)"],
        #         Token("-", None),
        #         TOKENS_ROOT_NODE.tokensByName["Image date (HHMMSS)"],
        #     ),
        # ),
    }
    # PHOTO_SUBFOLDER_MENU_DEFAULTS = (
    #     (_('Date'), _('YYYY'), _('YYYYMMDD')),
    #     (_('Date (hyphens)'), _('YYYY'), _('YYYY-MM-DD')),
    #     (_('Date (underscores)'), _('YYYY'), _('YYYY_MM_DD')),
    #     (_('Date and Job Code'), _('YYYY'), _('YYYYMM_Job Code')),
    #     (_('Date and Job Code Subfolder'), _('YYYY'), _('YYYYMM'), _('Job Code'))
    # )
    builtinDestinationNamingTemplates = {}
    defaultImageNamingTemplate = "TPL_1"

    def __init__(self):
        settings = Config.fotocopSettings
        self._templatesFile = settings.appDirs.user_config_dir / "templates.json"

        self.image, self.destination = self._load()

    def _load(self):
        try:
            with self._templatesFile.open() as fh:
                templates = json.load(fh, object_hook=namingTemplateHook)
                return templates["image"], templates["destination"]
        except (FileNotFoundError, json.JSONDecodeError):
            return dict(), dict()

    def save(self):
        """Save the custom naming templates on a JSON file.

        Use a dedicated JSONEncoder to handle NamingTemplate and Token objects.

        Raises:
            A NamingTemplatesError exception on OS or JSON encoding errors.
        """
        templates = {
            "image": self.image,
            "destination": self.destination,
        }
        try:
            with self._templatesFile.open(mode="w") as fh:
                json.dump(templates, fh, indent=4, cls=NamingTemplateEncoder)
        except (OSError, TypeError) as e:
            raise NamingTemplatesError(e)

    @staticmethod
    def listBuiltinImageNamingTemplates() -> List[NamingTemplate]:
        return list(NamingTemplates.builtinImageNamingTemplates.values())

    @staticmethod
    def listBuiltinDestinationNamingTemplates():
        return list(NamingTemplates.builtinDestinationNamingTemplates)

    def listImageNamingTemplates(self) -> List[NamingTemplate]:
        return list(self.image.values())

    def listDestinationNamingTemplates(self):
        return list(self.destination)

    def addImageNamingTemplate(self, template: NamingTemplate):
        self.image[template.key] = template

    def addDestinationNamingTemplate(self, template: NamingTemplate):
        self.destination[template.key] = template

    def getImageNamingTemplate(self, key: str) -> NamingTemplate:
        try:
            template = NamingTemplates.builtinImageNamingTemplates[key]
        except KeyError:
            try:
                template = self.image[key]
            except KeyError:
                template = None
        return template


class ImageNameGenerator:
    def __init__(self, template: NamingTemplate):
        self.template = template

    def generate(self, image: Image, seq: int, downloadTime: datetime) -> str:
        return self.template.format(image, seq, downloadTime)


class DestinationNameGenerator(ImageNameGenerator):
    def generate(self, image: Image, seq: int, downloadTime: datetime) -> Path:
        return Path(self.template.format(image, seq, downloadTime))
