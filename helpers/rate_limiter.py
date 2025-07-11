import time
import random
import threading

class RateLimiter:
    def __init__(self, min_interval=1.1, jitter_range=(0.05, 0.15), max_requests_per_minute=None):
        self.min_interval = min_interval
        self.jitter_range = jitter_range
        self.max_requests_per_minute = max_requests_per_minute
        self.last_call = 0
        self.lock = threading.Lock()
        self.request_times = []  # list of timestamps of the last 60s

    def wait(self):
        with self.lock:
            now = time.time()

            # Enforce RPM if needed
            if self.max_requests_per_minute:
                self.request_times = [t for t in self.request_times if now - t < 60]

                if len(self.request_times) >= self.max_requests_per_minute:
                    sleep_time = 60 - (now - self.request_times[0])
                    print(f"⏳ Jupiter RPM limit hit — sleeping {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                    now = time.time()
                    self.request_times = [t for t in self.request_times if now - t < 60]

                self.request_times.append(now)

            # Enforce min_interval + jitter (RPS control)
            elapsed = now - self.last_call
            jitter = random.uniform(*self.jitter_range)
            wait_time = max(0, (self.min_interval + jitter) - elapsed)

            if wait_time > 0:
                time.sleep(wait_time)

            self.last_call = time.time()
