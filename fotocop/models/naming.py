import logging
import json
import re
from typing import TYPE_CHECKING, Tuple, List, Dict, Optional, NamedTuple
from dataclasses import dataclass
from enum import Enum, auto
from datetime import datetime, timedelta

from fotocop.util.basicpatterns import visitable
from fotocop.models import settings as Config

if TYPE_CHECKING:
    from fotocop.models.sources import Image
    from fotocop.models.downloader import Sequences

__all__ = [
    "Case",
    "TemplateType",
    "TokensDescription",
    "TokenTree",
    "TokenFamily",
    "TokenGenus",
    "Token",
    "NamingTemplate",
    "NamingTemplates",
]

logger = logging.getLogger(__name__)


class Case(Enum):
    ORIGINAL_CASE = "Original Case"
    UPPERCASE = "UPPERCASE"
    LOWERCASE = "lowercase"


class TemplateType(Enum):
    IMAGE = auto()
    DESTINATION = auto()


class FormatSpec(NamedTuple):
    name: str
    spec: Optional[str]


@visitable
@dataclass()
class TokenNode:
    name: str
    notAllowed = {
        TemplateType.IMAGE: (),
        TemplateType.DESTINATION: (),
    }

    def __post_init__(self):
        self.parent: Optional["TokenNode"] = None
        self.children: Tuple["TokenNode"] = tuple()

    @property
    def isLeaf(self) -> bool:
        return len(self.children) == 0

    def isAllowed(self, kind: TemplateType) -> bool:
        return self.name not in self.notAllowed[kind]


@dataclass()
class TokenTree(TokenNode):
    pass

    def __post_init__(self):
        self.tokensByName: Dict[str, Token] = dict()


@dataclass()
class TokenFamily(TokenNode):
    notAllowed = {
        TemplateType.IMAGE: (),
        TemplateType.DESTINATION: ("Sequences",),
    }


@dataclass()
class TokenGenus(TokenNode):
    notAllowed = {
        TemplateType.IMAGE: ("Extension",),
        TemplateType.DESTINATION: ("Name", "Image number"),
    }


@dataclass()
class Token(TokenNode):
    genusName: str
    formatSpec: Optional[FormatSpec]

    def asText(self):
        if self.genusName == "Free text":
            return self.name
        return f"<{self.name}>"

    def format(self, image: "Image", sequences: "Sequences", downloadTime: datetime) -> str:
        genusName = self.genusName

        # Date Time family
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

        # Filename family
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

        if genusName == "Extension":
            extension = image.extension[1:]
            fmt = self.formatSpec.spec
            if fmt == "%F":  # UPPERCASE
                extension = extension.upper()
            elif fmt == "%f":    # lowercase
                extension = extension.lower()
            return extension

        # Sequences family
        if genusName == "Downloads today":
            return f"{sequences.downloadsToday.get():{self.formatSpec.spec}}"

        if genusName == "Stored number":
            return f"{sequences.storedNumber:{self.formatSpec.spec}}"

        if genusName == "Session number":
            return f"{sequences.sessionNumber:{self.formatSpec.spec}}"

        if genusName == "Sequence letter":
            return sequences.sequenceLetter

        # Session family
        if genusName == "Session":
            return image.session

        # Free text token
        if genusName == "Free text":
            return self.name


class TokensDescription:
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
        "Filename": ("Name", "Image number", "Extension"),
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
        "Extension": NAME_FORMATS,
        "Downloads today": SEQUENCE_FORMATS,
        "Stored number": SEQUENCE_FORMATS,
        "Session number": SEQUENCE_FORMATS,
        "Sequence letter": SEQUENCE_FORMATS,
        "Session": SESSION_FORMATS,
    }

    @classmethod
    def buildTokensTree(cls) -> TokenTree:
        root = TokenTree("Tokens")
        tokensByName = dict()
        families = list()
        for familyName in cls.TOKEN_FAMILIES:
            family = TokenFamily(familyName)
            family.parent = root
            families.append(family)
            genuses = list()
            for genusName in cls.TOKEN_GENUS[familyName]:
                genus = TokenGenus(genusName)
                genus.parent = family
                genuses.append(genus)
                tokens = list()
                for formatSpec in cls.TOKEN_FORMATS[genusName]:
                    tokenName = f"{genusName} ({formatSpec[0]})"
                    token = Token(tokenName, genusName, formatSpec)
                    tokensByName[tokenName] = token
                    token.parent = genus
                    tokens.append(token)
                genus.children = tuple(tokens)
            family.children = tuple(genuses)
        root.children = families
        root.tokensByName = tokensByName
        return root


class Boundary(NamedTuple):
    start: int
    end: int


@dataclass()
class NamingTemplate:
    key: str
    name: str
    template: Tuple[Token, ...]

    def __post_init__(self):
        self.extension = Case.LOWERCASE
        self.isBuiltin = True

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

    def format(self, image: "Image", sequences: "Sequences", downloadTime: datetime, kind: TemplateType = TemplateType.IMAGE) -> str:
        name = "".join(token.format(image, sequences, downloadTime) for token in self.template)
        if kind == TemplateType.IMAGE:
            if self.extension == Case.LOWERCASE:
                extension = image.extension.lower()
            elif self.extension == Case.UPPERCASE:
                extension = image.extension.upper()
            else:
                extension = image.extension
            return "".join((name, extension))
        else:
            assert kind == TemplateType.DESTINATION
            return name


class NamingTemplateDecoder(json.JSONDecoder):
    """A JSONDecoder to decode a NamingTemplate object in a JSON file.
    """
    def __init__(self):
        super().__init__(object_hook=self.namingTemplateHook)

    @staticmethod
    def namingTemplateHook(obj):
        if "__naming_template__" in obj:
            template = NamingTemplate(
                obj["key"],
                obj["name"],
                obj["template"],
            )
            template.isBuiltin = False
            return template

        if "__token__" in obj:
            try:
                token = NamingTemplates.getToken(obj["name"])
            except KeyError:
                token = Token(obj["name"], "Free text", None)
            return token

        if "__case__" in obj:
            return Case[obj["name"]]

        return obj


class NamingTemplateEncoder(json.JSONEncoder):
    """A JSONEncoder to encode a NamingTemplate object in a JSON file.
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
            return {"__token__": True, "name": obj.name}

        if isinstance(obj, Case):
            return {"__case__": True, "name": obj.name}

        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)


class NamingTemplates:

    # Build the tokens tree and keep its root node reference
    tokensRootNode = TokensDescription.buildTokensTree()

    builtinImageNamingTemplates = {
        "TPL_1": NamingTemplate(
            "TPL_1",
            "Original Filename - IMG_1234",
            (
                tokensRootNode.tokensByName["Name (Original Case)"],
            ),
        ),
        "TPL_2": NamingTemplate(
            "TPL_2",
            "Date-Time and Downloads today - YYYYmmDD-HHMM-1",
            (
                tokensRootNode.tokensByName["Image date (YYYYmmDD)"],
                Token("-", "Free text", None),
                tokensRootNode.tokensByName["Image date (HH)"],
                tokensRootNode.tokensByName["Image date (MM)"],
                Token("-", "Free text", None),
                tokensRootNode.tokensByName["Downloads today (One digit)"],
            ),
        ),
        "TPL_3": NamingTemplate(
            "TPL_3",
            "Date and Downloads today - YYYYmmDD-1",
            (
                tokensRootNode.tokensByName["Image date (YYYYmmDD)"],
                Token("-", "Free text", None),
                tokensRootNode.tokensByName["Downloads today (One digit)"],
            ),
        ),
        "TPL_4": NamingTemplate(
            "TPL_4",
            "Date-Time and Image number - YYYYmmDD-HHMM-1234",
            (
                tokensRootNode.tokensByName["Image date (YYYYmmDD)"],
                Token("-", "Free text", None),
                tokensRootNode.tokensByName["Image date (HH)"],
                tokensRootNode.tokensByName["Image date (MM)"],
                Token("-", "Free text", None),
                tokensRootNode.tokensByName["Image number (All digits)"],
            ),
        ),
        "TPL_5": NamingTemplate(
            "TPL_5",
            "Date-Time and Session - YYYYmmDD-HHMM-Session-1",
            (
                tokensRootNode.tokensByName["Image date (YYYYmmDD)"],
                Token("-", "Free text", None),
                tokensRootNode.tokensByName["Image date (HH)"],
                tokensRootNode.tokensByName["Image date (MM)"],
                Token("-", "Free text", None),
                tokensRootNode.tokensByName["Session (Session)"],
                Token("-", "Free text", None),
                tokensRootNode.tokensByName["Downloads today (One digit)"],
            ),
        ),
        "TPL_6": NamingTemplate(
            "TPL_6",
            "Date and Session - YYYYmmDD-Session-1",
            (
                tokensRootNode.tokensByName["Image date (YYYYmmDD)"],
                Token("-", "Free text", None),
                tokensRootNode.tokensByName["Session (Session)"],
                Token("-", "Free text", None),
                tokensRootNode.tokensByName["Downloads today (One digit)"],
            ),
        ),
    }

    builtinDestinationNamingTemplates = {
        "TPL_1": NamingTemplate(
            "TPL_1",
            "Date - YYYY/YYYYmmDD",
            (
                tokensRootNode.tokensByName["Image date (YYYY)"],
                Token("/", "Free text", None),
                tokensRootNode.tokensByName["Image date (YYYYmmDD)"],
            ),
        ),
        "TPL_2": NamingTemplate(
            "TPL_2",
            "Date (hyphens) - YYYY/YYYY-mm-DD",
            (
                tokensRootNode.tokensByName["Image date (YYYY)"],
                Token("/", "Free text", None),
                tokensRootNode.tokensByName["Image date (YYYY)"],
                Token("-", "Free text", None),
                tokensRootNode.tokensByName["Image date (mm)"],
                Token("-", "Free text", None),
                tokensRootNode.tokensByName["Image date (DD)"],
            ),
        ),
        "TPL_3": NamingTemplate(
            "TPL_3",
            "Date (underscores) - YYYY/YYYY_mm_DD",
            (
                tokensRootNode.tokensByName["Image date (YYYY)"],
                Token("/", "Free text", None),
                tokensRootNode.tokensByName["Image date (YYYY)"],
                Token("_", "Free text", None),
                tokensRootNode.tokensByName["Image date (mm)"],
                Token("_", "Free text", None),
                tokensRootNode.tokensByName["Image date (DD)"],
            ),
        ),
        "TPL_4": NamingTemplate(
            "TPL_4",
            "Date and Session - YYYY/YYYYmm_Session",
            (
                tokensRootNode.tokensByName["Image date (YYYY)"],
                Token("/", "Free text", None),
                tokensRootNode.tokensByName["Image date (YYYY)"],
                tokensRootNode.tokensByName["Image date (mm)"],
                Token("_", "Free text", None),
                tokensRootNode.tokensByName["Session (Session)"],
            ),
        ),
        "TPL_5": NamingTemplate(
            "TPL_5",
            "Date and Session Subfolder - YYYY/YYYYmm/Session",
            (
                tokensRootNode.tokensByName["Image date (YYYY)"],
                Token("/", "Free text", None),
                tokensRootNode.tokensByName["Image date (YYYY)"],
                tokensRootNode.tokensByName["Image date (mm)"],
                Token("/", "Free text", None),
                tokensRootNode.tokensByName["Session (Session)"],
            ),
        ),
    }
    defaultImageNamingTemplate = "TPL_1"
    defaultDestinationNamingTemplate = "TPL_1"

    def __init__(self):
        settings = Config.fotocopSettings
        self._templatesFile = settings.appDirs.user_config_dir / "templates.json"

        self.image, self.destination = self._load()

    @classmethod
    def getToken(cls, name: str) -> "Token":
        return cls.tokensRootNode.tokensByName[name]

    @classmethod
    def listBuiltins(cls, kind: TemplateType) -> List[NamingTemplate]:
        if kind == TemplateType.IMAGE:
            return list(cls.builtinImageNamingTemplates.values())
        else:
            assert kind == TemplateType.DESTINATION
            return list(cls.builtinDestinationNamingTemplates.values())

    def _load(self):
        try:
            with self._templatesFile.open() as fh:
                templates = json.load(fh, cls=NamingTemplateDecoder)
                # templates = json.load(fh, object_hook=namingTemplateHook)
                return templates["image"], templates["destination"]
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Cannot load custom naming templates: {e}")
            return dict(), dict()

    def save(self) -> Tuple[bool, str]:
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
            msg = f"Cannot save custom naming templates: {e}"
            logger.warning(msg)
            return False, msg
            # raise NamingTemplatesError(msg)
        else:
            return True, "Custom naming templates successfully saved."

    def listCustoms(self, kind: TemplateType) -> List[NamingTemplate]:
        if kind == TemplateType.IMAGE:
            return list(self.image.values())
        else:
            assert kind == TemplateType.DESTINATION
            return list(self.destination.values())

    def add(
            self,
            kind: TemplateType,
            name: str, template: Tuple[Token, ...]
    ) -> NamingTemplate:
        key = f"TPL_{id(name)}"
        namingTemplate = NamingTemplate(key, name, template)
        namingTemplate.isBuiltin = False
        if kind == TemplateType.IMAGE:
            self.image[key] = namingTemplate
        else:
            assert kind == TemplateType.DESTINATION
            self.destination[key] = namingTemplate
        return namingTemplate

    def delete(self, kind: TemplateType, templateKey: str) -> None:
        if kind == TemplateType.IMAGE:
            del self.image[templateKey]
        else:
            assert kind == TemplateType.DESTINATION
            del self.destination[templateKey]

    def change(
            self,
            kind: TemplateType,
            templateKey: str,
            template: Tuple[Token, ...]
    ) -> NamingTemplate:
        if kind == TemplateType.IMAGE:
            namingTemplate = self.image[templateKey]
            # self.image[templateKey].template = template
        else:
            assert kind == TemplateType.DESTINATION
            namingTemplate = self.destination[templateKey]
            # self.destination[templateKey].template = template
        namingTemplate.template = template
        return namingTemplate

    def getByKey(self, kind: TemplateType, key: str) -> Optional[NamingTemplate]:
        if kind == TemplateType.IMAGE:
            try:
                template = NamingTemplates.builtinImageNamingTemplates[key]
            except KeyError:
                try:
                    template = self.image[key]
                except KeyError:
                    template = None

        else:
            assert kind == TemplateType.DESTINATION
            try:
                template = NamingTemplates.builtinDestinationNamingTemplates[key]
            except KeyError:
                try:
                    template = self.destination[key]
                except KeyError:
                    template = None

        return template

    def getDefault(self, kind: TemplateType) -> NamingTemplate:
        if kind == TemplateType.IMAGE:
            return self.builtinImageNamingTemplates[self.defaultImageNamingTemplate]
        else:
            assert kind == TemplateType.DESTINATION
            return self.builtinDestinationNamingTemplates[self.defaultDestinationNamingTemplate]
