"""
robots.txt cache and can_fetch() helper.
Retained from original bot with improvements: per-domain caching, warning on failure.
"""
import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)
_cache: dict[str, RobotFileParser] = {}


def _get_parser(url: str) -> RobotFileParser | None:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    if base not in _cache:
        rp = RobotFileParser()
        rp.set_url(f"{base}/robots.txt")
        try:
            rp.read()
            _cache[base] = rp
        except Exception as exc:
            logger.warning("Could not read robots.txt for %s: %s", base, exc)
            return None
    return _cache.get(base)


def can_fetch(url: str, user_agent: str = "*") -> bool:
    """Return True if robots.txt permits fetching the given URL."""
    parser = _get_parser(url)
    if parser is None:
        return True  # Fail open — log warning already emitted
    try:
        return parser.can_fetch(user_agent, url)
    except Exception as exc:
        logger.warning("robots.txt evaluation error for %s: %s", url, exc)
        return True
