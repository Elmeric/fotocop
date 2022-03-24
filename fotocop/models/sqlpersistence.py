import sqlite3
import datetime
import logging
from typing import Optional, NamedTuple, Tuple, List

from fotocop.models import settings as Config

SQLITE3_TIMEOUT = 10.0
SQLITE3_RETRY_ATTEMPTS = 5


class FileDownloaded(NamedTuple):
    downloadName: str
    downloadDatetime: datetime.datetime


class DownloadedDB:
    """
    Previous image file download detection.

    Used to detect if an image file has been downloaded before. A file is the same if
    the file name (excluding path), size and modification time are the same.
    For performance reasons, Exif information is never checked.
    """

    def __init__(self) -> None:
        settings = Config.fotocopSettings
        self._db = settings.appDirs.user_data_dir / "downloaded_images.sqlite"
        self._tableName = "downloaded"
        self.updateTable()

    def updateTable(self, reset: bool = False) -> None:
        """Create or update the database table

        Args:
            reset: if True, delete the contents of the table and re-build it.
        """

        conn = sqlite3.connect(self._db, detect_types=sqlite3.PARSE_DECLTYPES)

        if reset:
            conn.execute(fr"""DROP TABLE IF EXISTS {self._tableName}""")
            conn.execute("VACUUM")

        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS {self._tableName} (
                file_name TEXT NOT NULL,
                mtime REAL NOT NULL,
                size INTEGER NOT NULL,
                download_name TEXT NOT NULL,
                download_datetime timestamp,
                PRIMARY KEY (file_name, mtime, size)
            )"""
        )

        conn.execute(
            f"""CREATE INDEX IF NOT EXISTS download_datetime_idx ON
                {self._tableName} (download_name)
            """
        )

        conn.commit()
        conn.close()

    # @retry(stop=stop_after_attempt(SQLITE3_RETRY_ATTEMPTS))
    def addDownloadedFile(
        self, name: str, size: int, modificationTime: float, downloadedAs: str
    ) -> None:
        """
        Add file to database of downloaded files.

        Args:
            name: original image filename without path.
            size: image file size.
            modificationTime: image file modification time.
            downloadedAs: renamed file including path, or the character '.' when the
                user manually marked the file as previously downloaded.
        """
        conn = sqlite3.connect(self._db, timeout=SQLITE3_TIMEOUT)

        logging.debug(f"Adding {name} to downloaded files")

        try:
            conn.execute(
                fr"""INSERT OR REPLACE INTO {self._tableName} (file_name, size, mtime,
                    download_name, download_datetime) VALUES (?,?,?,?,?)
                """,
                (name, size, modificationTime, downloadedAs, datetime.datetime.now()),
            )
        except sqlite3.OperationalError as e:
            logging.warning(
                f"Database error adding downloaded file {downloadedAs}: {e}. May retry."
            )
            conn.close()
            raise sqlite3.OperationalError from e
        else:
            conn.commit()
            conn.close()

    # @retry(stop=stop_after_attempt(SQLITE3_RETRY_ATTEMPTS))
    def addDownloadedFiles(
        self, records: List[Tuple[str, int, float, str, datetime.datetime]]
    ) -> None:
        """
        Add multiple files to database of downloaded files.

        Args:
            records: images data to be added.
        """
        conn = sqlite3.connect(self._db, timeout=SQLITE3_TIMEOUT)

        logging.debug(f"Adding {len(records)} images to downloaded files")

        try:
            conn.executemany(
                fr"""INSERT OR REPLACE INTO {self._tableName} (file_name, size, mtime,
                    download_name, download_datetime) VALUES (?,?,?,?,?)
                """,
                records,
            )
        except sqlite3.OperationalError as e:
            logging.warning(
                f"Database error adding downloaded files: {e}. May retry."
            )
            conn.close()
            raise sqlite3.OperationalError from e
        else:
            conn.commit()
            conn.close()

    def fileIsPreviouslyDownloaded(
        self, name: str, size: int, modificationTime: float
    ) -> Optional[FileDownloaded]:
        """
        Returns download path and filename if a file with matching
        name, modification time and size has previously been downloaded.

        Args:
            name: image filename without path.
            size: image file size in bytes.
            modificationTime: image file modification time.

        Returns:
            image download name (including path) and when it was downloaded, None if
            never downloaded.
        """
        conn = sqlite3.connect(self._db, detect_types=sqlite3.PARSE_DECLTYPES)
        c = conn.cursor()
        c.execute(
            f"""SELECT download_name, download_datetime as [timestamp]
                FROM {self._tableName} WHERE file_name=? AND size=? AND mtime=?
            """,
            (name, size, modificationTime),
        )
        row = c.fetchone()
        if row is not None:
            return FileDownloaded(*row)
        else:
            return None
