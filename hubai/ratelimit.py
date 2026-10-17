"""Fixed-window rate limits on Django's cache (the database cache in production, shared by all workers)."""

import time

from django.core.cache import cache


def client_ip(request):
    # The platform's nginx appends the real client address last; earlier entries can be forged by the client.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "")


def hit(scope, key, limit, seconds):
    """Count one request; True if this one goes over `limit` per `seconds` window."""
    window = int(time.time() // seconds)
    cache_key = f"rl:{scope}:{key}:{window}"
    if cache.add(cache_key, 1, seconds + 5):
        return limit < 1
    try:
        return cache.incr(cache_key) > limit
    except ValueError:  # expired between add and incr
        cache.add(cache_key, 1, seconds + 5)
        return False
