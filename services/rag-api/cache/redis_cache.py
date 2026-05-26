import hashlib
import json
import logging
import redis

from config.settings import config

logger = logging.getLogger(__name__)

class QueryCache:
    """
    Redis-backed query cache.

    Key: SHA256(query_text) — deterministic, collision-resistant
    Value: serialized response dict
    TTL: 1 hour (configurable)

    Why cache at query level?
      - LLM inference is the most expensive step (~500ms-2s)
      - Repeated questions (FAQ patterns) hit >30% in production
      - Cache miss is transparent — falls through to full pipeline
    """

    def __init__(self):
        self._client = None

    @property
    def client(self):
        # Lazy init — don't fail at startup if Redis is down
        if self._client is None:
            self._client = redis.Redis(
                host=config.redis_host,
                port=config.redis_port,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
        return self._client

    def _make_key(self, query: str) -> str:
        return f"rag:query:{hashlib.sha256(query.encode()).hexdigest()}"

    def get(self, query: str) -> dict | None:
        try:
            key = self._make_key(query)
            value = self.client.get(key)
            if value:
                logger.info(f"Cache HIT for query hash {key[-8:]}")
                return json.loads(value)
        except Exception as e:
            # Never let cache errors break the pipeline
            logger.warning(f"Redis GET failed: {e}")
        return None

    def set(self, query: str, response: dict) -> None:
        try:
            key = self._make_key(query)
            self.client.setex(key, config.cache_ttl_sec, json.dumps(response))
            logger.info(f"Cache SET for query hash {key[-8:]}")
        except Exception as e:
            logger.warning(f"Redis SET failed: {e}")

cache = QueryCache()