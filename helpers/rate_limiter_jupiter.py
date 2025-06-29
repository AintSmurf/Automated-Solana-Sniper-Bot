import time
import random
import threading

class RateLimiter:
    def __init__(self, min_interval=1.1, jitter_range=(0.05, 0.15)):
        self.min_interval = min_interval  
        self.jitter_range = jitter_range 
        self.last_call = 0
        self.lock = threading.Lock()    

    def wait(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_call
            jitter = random.uniform(*self.jitter_range)
            wait_time = max(0, (self.min_interval + jitter) - elapsed)
            if wait_time > 0:
                time.sleep(wait_time)
            self.last_call = time.time()
