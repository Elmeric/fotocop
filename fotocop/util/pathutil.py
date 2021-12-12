"""Global constants, enum and generic classes and types.
"""
from pathlib import Path


def makeAbsolute(path: Path, rootPath: Path) -> Path:
    """Make a 'relative to rootpath' path absolute.

    Args:
        path: a path relative to rootPath.
        rootPath: the rootPath of the project.

    Returns:
        An absolute path from rootPath
    """
    if not path.is_absolute():
        path = rootPath / path
    return path


def rmtree(root: Path):
    """Recursively delete a directory and all its content.

    Args:
        root: the Path of the directory to delete.
    """
    for p in root.iterdir():
        if p.is_dir():
            rmtree(p)
        else:
            p.unlink()
    root.rmdir()


def _copy(self: Path, target: Path):
    """Copy 'self' file into 'target'.

    Args:
        self: Path to an existing file.
        target: Path of the file's copy.

    Raises:
        AssertionError if 'self' is not an existing file.
    """
    import shutil
    assert self.is_file()
    shutil.copy(str(self), str(target))  # str() only there for Python < (3, 6)


# Monkey patch of pathlib.Path to add a copy method
Path.copy = _copy


def _copytree(self, target: Path):
    """Copy 'self' directory into 'target'.

    Args:
        self: Path to an existing directory.
        target: Path of the directory's copy.

    Raises:
        AssertionError if 'self' is not an existing directory.
    """
    import shutil
    assert self.is_dir()
    shutil.copytree(str(self), str(target))  # str() only there for Python < (3, 6)


# Monkey patch of pathlib.Path to add a copytree method
Path.copytree = _copytree
