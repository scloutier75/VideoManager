"""
VideoManager score fetcher.

Connects to the VideoManager PostgreSQL database and looks up the quality
score (0–10) for a given file path.  Falls back to filename-only matching
when the full path is not found (useful if Plex and VideoManager mount the
same NAS at different paths, or when Plex is on Windows and VideoManager on Linux).
"""

import logging
from pathlib import Path, PureWindowsPath
from typing import Optional

logger = logging.getLogger(__name__)


def _extract_filename(filepath: str) -> str:
    """
    Extract just the filename from a path that may use Windows (backslash)
    or Unix (forward slash) separators.

    On Linux, pathlib.Path does NOT split on backslashes, so
    Path('V:\\Movies\\foo.mkv').name returns the entire string unchanged.
    We detect Windows-style paths by the presence of a backslash and use
    PureWindowsPath in that case.
    """
    if '\\' in filepath:
        return PureWindowsPath(filepath).name
    return Path(filepath).name


def _windows_to_unix_relative(filepath: str) -> Optional[str]:
    """
    Convert a Windows absolute path to a Unix-relative suffix suitable for a
    LIKE query.  E.g. ``V:\\Movies\\Foo\\bar.mkv`` → ``/Movies/Foo/bar.mkv``.
    Returns None if the path doesn't look like a Windows absolute path.
    """
    if '\\' not in filepath:
        return None
    # Strip drive letter (e.g. "V:") then replace backslashes with forward slashes
    after_drive = filepath[2:] if len(filepath) > 2 and filepath[1] == ':' else filepath
    return after_drive.replace('\\', '/')


class VMGRFetcher:
    """Fetch quality and BRISQUE scores from the VideoManager PostgreSQL DB."""

    def __init__(self, db_url: str):
        """
        Args:
            db_url: A standard psycopg2-compatible DSN, e.g.
                    postgresql://postgres:password@localhost:5433/video_manager
                    (strip any +asyncpg driver prefix if copied from VideoManager config)
        """
        # Normalise: strip SQLAlchemy driver prefix if present
        self.db_url = db_url.replace("postgresql+asyncpg://", "postgresql://").replace(
            "postgres+asyncpg://", "postgresql://"
        )
        self._psycopg2_available = self._check_psycopg2()

    def _check_psycopg2(self) -> bool:
        try:
            import psycopg2  # noqa: F401
            return True
        except ImportError:
            logger.warning(
                "psycopg2 not installed — VideoManager score lookup will be disabled. "
                "Install it with: pip install psycopg2-binary"
            )
            return False

    def _connect(self):
        import psycopg2
        return psycopg2.connect(self.db_url)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_scores(self, filepath: str) -> dict:
        """
        Return a dict of available scores for *filepath*.

        Lookup strategy (first hit wins):
          1. Exact filepath match
          2. Windows→Linux path transform: strip drive letter, replace \\ with /,
             then match using a LIKE suffix query (handles Plex on Windows +
             VideoManager on Linux with different mount prefixes)
          3. Filename-only match (last resort)

        Returned keys (all optional):
            'score'        – quality score 0–10  (float)
            'brisque_score'– BRISQUE perceptual score 0–10 (float)

        Returns an empty dict on any failure.
        """
        if not self._psycopg2_available:
            return {}

        try:
            conn = self._connect()
            try:
                with conn.cursor() as cur:
                    # 1. Exact path match
                    cur.execute(
                        "SELECT score, brisque_score FROM videos WHERE filepath = %s",
                        (filepath,),
                    )
                    row = cur.fetchone()

                    # 2. Windows→Linux suffix match
                    if row is None:
                        unix_rel = _windows_to_unix_relative(filepath)
                        if unix_rel:
                            cur.execute(
                                "SELECT score, brisque_score FROM videos "
                                "WHERE filepath LIKE %s ORDER BY id LIMIT 1",
                                (f'%{unix_rel}',),
                            )
                            row = cur.fetchone()
                            if row:
                                logger.debug(
                                    f"VMGRFetcher: matched via path-transform for "
                                    f"'{_extract_filename(filepath)}'"
                                )

                    # 3. Filename-only match (handles any remaining mount-point differences)
                    if row is None:
                        filename = _extract_filename(filepath)
                        cur.execute(
                            "SELECT score, brisque_score FROM videos "
                            "WHERE filename = %s ORDER BY id LIMIT 1",
                            (filename,),
                        )
                        row = cur.fetchone()
                        if row:
                            logger.debug(
                                f"VMGRFetcher: matched via filename for '{filename}'"
                            )

                    if row is None:
                        return {}

                    result = {}
                    if row[0] is not None:
                        result["score"] = float(row[0])
                    if row[1] is not None:
                        result["brisque_score"] = float(row[1])
                    return result

            finally:
                conn.close()

        except Exception as e:
            logger.warning(f"VMGRFetcher: error looking up '{_extract_filename(filepath)}': {e}")
            return {}

    def get_quality_score(self, filepath: str) -> Optional[float]:
        """Convenience wrapper — returns only the quality score (0–10) or None."""
        return self.get_scores(filepath).get("score")


    def get_quality_score(self, filepath: str) -> Optional[float]:
        """Convenience wrapper — returns only the quality score (0–10) or None."""
        return self.get_scores(filepath).get("score")
