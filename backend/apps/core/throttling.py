"""Atomic rate limits. DRF's ScopedRateThrottle reads and rewrites a history list, so parallel requests all see
the old count and pass together (a burst of 15 logins beat a 10/min limit in testing). This one counts with an
atomic cache increment in a fixed window, so the N+1th request in a window is refused however fast they arrive."""
import time

from django.core.cache import cache
from rest_framework.throttling import ScopedRateThrottle


class AtomicScopedRateThrottle(ScopedRateThrottle):
    def allow_request(self, request, view):
        self.scope = getattr(view, self.scope_attr, None)
        if not self.scope:
            return True
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)
        ident = self.get_ident(request)
        window = int(time.time() // self.duration)
        self.key = f"throttle:{self.scope}:{ident}:{window}"
        self.wait_for = self.duration - (time.time() % self.duration)
        if cache.add(self.key, 1, self.duration + 5):
            count = 1
        else:
            try:
                count = cache.incr(self.key)
            except ValueError:  # expired between add and incr
                cache.add(self.key, 1, self.duration + 5)
                count = 1
        return count <= self.num_requests

    def wait(self):
        return self.wait_for
