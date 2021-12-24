import json
from typing import Tuple, List, Optional
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from fotocop.models import settings as Config
from fotocop.models.sources import Datation, Image


ORIGINAL_CASE = "Original Case"
UPPERCASE = "UPPERCASE"
LOWERCASE = "lowercase"


class TokenKind(Enum):
    DATE = auto()
    SEQUENCE = auto()
    SESSION = auto()
    FREETEXT = auto()


@dataclass()
class Token:
    key: str
    name: str
    formatSpec: Optional[str]

    def format(self, image: Image, _seq: int) -> str:
        raise NotImplementedError("'format' is an abstract method")


@dataclass()
class DateToken(Token):
    def format(self, image: Image, _seq: int) -> str:
        return image.datetime.asDatetime().strftime(self.formatSpec)


@dataclass()
class FreeTextToken(Token):
    def format(self, _image: Image, _seq: int) -> str:
        return self.name


@dataclass()
class SequenceToken(Token):
    def format(self, _image: Image, seq: int) -> str:
        return f"{seq:{self.formatSpec}}"


@dataclass()
class SessionToken(Token):
    def format(self, image: Image, _seq: int) -> str:
        return image.session


class BuiltinTokens:
    kind = (TokenKind.DATE, TokenKind.SEQUENCE, TokenKind.SESSION)
    # kind = ("Date", "Sequence", "Session")
    date = {
        "DATE": DateToken("DATE", "Date (YYYYMMDD)", "%Y%m%d"),
        "TIME": DateToken("TIME", "Time (HHMMSS)", "%H%M%S"),
        "YEAR_4": DateToken("YEAR_4", "Date (YYYY)", "%Y"),
        "YEAR_2": DateToken("YEAR_2", "Date (YY)", "%y"),
        "MONTH": DateToken("MONTH", "Date (Month)", "%B"),
        "MONTH_2": DateToken("MONTH_2", "Date (MM)", "%m"),
        "DAY_2": DateToken("DAY_2", "Date (DD)", "%d"),
        "DAY": DateToken("DAY", "Date (Day)", "%j"),
        "HOUR": DateToken("HOUR", "Hour (HH)", "%H"),
        "MINUTE": DateToken("MINUTE", "Minute (MM)", "%M"),
        "SECOND":DateToken("SECOND", "Second (SS)", "%S"),
    }
    sequence = {
        "SEQ_1": SequenceToken("SEQ_1", "Sequence (1 digit)", "01"),
        "SEQ_2": SequenceToken("SEQ_2", "Sequence (2 digits)", "02"),
        "SEQ_3": SequenceToken("SEQ_3", "Sequence (3 digits)", "03"),
        "SEQ_4": SequenceToken("SEQ_4", "Sequence (4 digits)", "04"),
    }
    session = {
        "SESSION": SessionToken("SESSION", "Session", None),
    }

    @staticmethod
    def listBuiltinTokensByKind(kind: TokenKind) -> Tuple[Token,...]:
        return tuple(getattr(BuiltinTokens, kind.name.lower()).values())


@dataclass()
class NamingTemplate:
    key: str
    name: str
    template: Tuple[Token, ...]

    def __post_init__(self):
        self.extension = LOWERCASE

    def format(self, image: Image, seq: int) -> str:
        name = ''.join(token.format(image, seq) for token in self.template)
        if self.extension == LOWERCASE:
            extension = image.extension.lower()
        elif self.extension == UPPERCASE:
            extension = image.extension.upper()
        else:
            extension = image.extension
        return ''.join((name, extension))


def namingTemplateHook(obj):
    if "__naming_template__" in obj:
        return NamingTemplate(
            obj["key"],
            obj["name"],
            obj["template"],
        )
    if "__date_token__" in obj:
        return DateToken(
            obj["key"],
            obj["name"],
            obj["formatSpec"],
        )
    if "__free_text_token__" in obj:
        return FreeTextToken(
            obj["key"],
            obj["name"],
            obj["formatSpec"],
        )
    if "__sequence_token__" in obj:
        return SequenceToken(
            obj["key"],
            obj["name"],
            obj["formatSpec"],
        )
    if "__session_token__" in obj:
        return SessionToken(
            obj["key"],
            obj["name"],
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
        if isinstance(obj, DateToken):
            obj.__dict__.update({"__date_token__": True})
            return obj.__dict__
        if isinstance(obj, FreeTextToken):
            obj.__dict__.update({"__free_text_token__": True})
            return obj.__dict__
        if isinstance(obj, SequenceToken):
            obj.__dict__.update({"__sequence_token__": True})
            return obj.__dict__
        if isinstance(obj, SessionToken):
            obj.__dict__.update({"__session_token__": True})
            return obj.__dict__
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)


class NamingTemplatesError(Exception):
    """Exception raised on naming templates saving error.
    """
    pass


class NamingTemplates:

    builtinImageNamingTemplates = {
        "DATE-TIME": NamingTemplate(
            "DATE-TIME",
            "By date and time (YYYYMMDD-HHMMSS)",
            (
                BuiltinTokens.date["DATE"],
                FreeTextToken("FREE_TEXT", "-", None),
                BuiltinTokens.date["TIME"],
            ),
        ),
    }
    builtinDestinationNamingTemplates = {
        "YEAR-MONTH-DAY-SESSION": NamingTemplate(
            "YEAR-MONTH-DAY-SESSION",
            "By year, month and time-session (YYYY/YYY-MM/YYYY-MM-DD-SESSION)",
            (
                BuiltinTokens.date["YEAR_4"],
                FreeTextToken("FREE_TEXT", "/", None),
                BuiltinTokens.date["YEAR_4"],
                FreeTextToken("FREE_TEXT", "-", None),
                BuiltinTokens.date["MONTH_2"],
                FreeTextToken("FREE_TEXT", "/", None),
                BuiltinTokens.date["YEAR_4"],
                FreeTextToken("FREE_TEXT", "-", None),
                BuiltinTokens.date["MONTH_2"],
                FreeTextToken("FREE_TEXT", "-", None),
                BuiltinTokens.date["DAY_2"],
                FreeTextToken("FREE_TEXT", "-", None),
                BuiltinTokens.session["SESSION"],
            ),
        )
    }
    defaultImageNamingTemplate = "DATE-TIME"

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
            with self._templatesFile.open(mode='w') as fh:
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

    def generate(self, image: Image, seq: int) -> str:
        return self.template.format(image, seq)


class DestinationNameGenerator(ImageNameGenerator):
    def generate(self, image: Image, seq: int) -> Path:
        return Path(self.template.format(image, seq))


# https://stackoverflow.com/questions/57570026/how-to-provide-custom-formatting-from-format-string
# https://tobywf.com/2015/12/custom-formatters/
# https://docs.python.org/3.7/library/string.html#custom-string-formatting
if __name__ == '__main__':
    for attr in ("date", "sequence", "session"):
        for t in getattr(BuiltinTokens, attr).values():
            print(f"{attr}: {t.name}")
    images = list()
    for i in range(10):
        image = Image(f"img_test_{i:02}", "path")
        image.datetime = Datation("2021", str((i % 3) + 1), "6", str(i+1), "8", "9")
        image.session = "Great session"
        images.append(image)
    image = images[0]
    namingTemplate = (
        BuiltinTokens.date["DATE"],
        BuiltinTokens.date["TIME"],
        BuiltinTokens.date["YEAR_2"],
        FreeTextToken("FREE_TEXT", "-", None),
        BuiltinTokens.date["MONTH"],
        BuiltinTokens.date["DAY"],
        BuiltinTokens.sequence["SEQ_4"],
        BuiltinTokens.session["SESSION"],
    )
    # namingTemplate = (
    #     tokenFactory.create("DATE", "YEAR_2", "Date (YY)", "%y"),
    #     tokenFactory.create("FREE_TEXT", "FREE_TEXT", "-", None),
    #     tokenFactory.create("DATE", "MONTH", "Date (Month)", "%B"),
    #     tokenFactory.create("DATE", "DAY", "Date (Day)", "%j"),
    #     tokenFactory.create("SEQUENCE", "SEQ_4", "Sequence (4 digits)", "04"),
    #     tokenFactory.create("SESSION", "SESSION", "Session", None),
    # )
    print("*"*10)
    seq = 0
    for token in namingTemplate:
        seq += 1
        print(f"{token.name}: {token.format(image, seq)}")

    print("*"*10)
    namingTemplate = (
        BuiltinTokens.date["DATE"],
        FreeTextToken("FREE_TEXT", "-", None),
        BuiltinTokens.date["TIME"],
    )
    name = ''.join(token.format(image, seq) for token in namingTemplate)
    print(name)

    print("*"*10)
    namingTemplates = NamingTemplates()
    for namingTemplate in namingTemplates.destination.values():
        name = ''.join(token.format(image, seq) for token in namingTemplate.template)
        print(Path(name).as_posix())

    for namingTemplate in namingTemplates.image.values():
        name = ImageNameGenerator(namingTemplate).generate(image, seq)
        print(name)

    print("*"*10)
    for namingTemplate in NamingTemplates.builtinDestinationNamingTemplates.values():
        name = ''.join(token.format(image, seq) for token in namingTemplate.template)
        print(Path(name).as_posix())

    for namingTemplate in NamingTemplates.builtinImageNamingTemplates.values():
        name = ImageNameGenerator(namingTemplate).generate(image, seq)
        print(name)

    namingTemplates.save()

    print("*"*10)
    nameGenerator = ImageNameGenerator(NamingTemplates.builtinImageNamingTemplates["DATE-TIME"])
    for image in images:
        print(nameGenerator.generate(image, 0))

    print("*"*10)
    nameGenerator = DestinationNameGenerator(
        NamingTemplates.builtinDestinationNamingTemplates["YEAR-MONTH-DAY-SESSION"]
    )
    for image in images:
        print(nameGenerator.generate(image, 0))

    print("*"*10)
    namingTemplates.addImageNamingTemplate(
        NamingTemplate(
            "DATE-SESSION",
            "By date and session (YYYYMMDD-SESSION)",
            (
                BuiltinTokens.date["DATE"],
                FreeTextToken("FREE_TEXT", "-", None),
                BuiltinTokens.session["SESSION"],
            ),
        )
    )
    for k in namingTemplates.listBuiltinImageNamingTemplates():
        print(k)
    for k in namingTemplates.listBuiltinDestinationNamingTemplates():
        print(k)
    for k in namingTemplates.listImageNamingTemplates():
        print(k)
    for k in namingTemplates.listDestinationNamingTemplates():
        print(k)

    print("*"*10)
    for tokenKind in BuiltinTokens.kind:
        for token in BuiltinTokens.listBuiltinTokensByKind(tokenKind):
            print(tokenKind.name, ": ", token.key, token.name, token.formatSpec)
