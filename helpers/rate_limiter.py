import time
import random
import threading

class RateLimiter:
    def __init__(self, min_interval=1.1, jitter_range=(0.05, 0.15), max_requests_per_minute=None,name=None):
        self.min_interval = min_interval
        self.jitter_range = jitter_range
        self.max_requests_per_minute = max_requests_per_minute
        self.last_call = 0
        self.lock = threading.Lock()
        self.request_times = []  # list of timestamps of the last 60s
        self.total_requests = 0      # tracks full session
        self.name = name

    def wait(self):
        with self.lock:
            now = time.time()

            # Purge old timestamps (only keep last 60s)
            self.request_times = [t for t in self.request_times if now - t < 60]

            # Enforce RPM limit
            if self.max_requests_per_minute and len(self.request_times) >= self.max_requests_per_minute:
                sleep_time = 60 - (now - self.request_times[0])
                time.sleep(sleep_time)
                now = time.time()
                self.request_times = [t for t in self.request_times if now - t < 60]

            # Enforce spacing
            elapsed = now - self.last_call
            jitter = random.uniform(*self.jitter_range)
            wait_time = max(0, (self.min_interval + jitter) - elapsed)
            if wait_time > 0:
                time.sleep(wait_time)

            # Record this call
            self.last_call = time.time()
            self.request_times.append(self.last_call)
            self.total_requests += 1

    def get_stats(self) -> dict:
        """Return current limiter stats for monitoring."""
        with self.lock:
            now = time.time()
            self.request_times = [t for t in self.request_times if now - t < 60]
            return {
                "name": self.name,
                "last_60s": len(self.request_times),
                "limit_per_minute": self.max_requests_per_minute,
                "total_requests": self.total_requests,
                "last_call": self.last_call,
            }
