import json
import time
import requests
from helpers.logging_manager import LoggingHandler

# set up logger
logger = LoggingHandler.get_logger()


class RequestsUtility:
    _backoff_until = 0       
    _backoff_delay = 0       
    _max_backoff = 60        

    def __init__(self, base_url: str):
        self.base_url = base_url

    def assert_status_code(self) -> None:
        assert self.rs_status_code == self.expected_status_code, (
            f"Expected status code {self.expected_status_code} but actual status code is {self.rs_status_code}\n"
            f"URL:{self.url}, Response Json: {self.rs_json}"
        )

    @classmethod
    def _apply_backoff(cls):
        """If a global cooldown is active, wait until it's over."""
        now = time.time()
        if now < cls._backoff_until:
            sleep_time = cls._backoff_until - now
            logger.warning(f"⏳ Backing off requests for {sleep_time:.1f}s...")
            time.sleep(sleep_time)

    @classmethod
    def _set_backoff(cls, base_seconds: int):
        """Activate or increase global cooldown after 429."""
        if cls._backoff_delay == 0:
            cls._backoff_delay = base_seconds
        else:
            cls._backoff_delay = min(cls._backoff_delay * 2, cls._max_backoff)

        cls._backoff_until = time.time() + cls._backoff_delay
        logger.warning(f"🚦 Progressive backoff set: {cls._backoff_delay}s")

    @classmethod
    def _reset_backoff(cls):
        """Reset backoff after a successful request."""
        if cls._backoff_delay > 0:
            logger.info("✅ Request succeeded, resetting backoff")
        cls._backoff_delay = 0
        cls._backoff_until = 0

    def get(self, endpoint:str=None, payload:dict=None, headers:dict=None, expected_status_code:int=200) -> json:
        if not headers:
            headers = {"Content-Type": "application/json"}
        self.url = self.base_url + endpoint
        logger.debug(f"Sending GET request to: {self.url} with params: {payload}")

        try:
            self._apply_backoff()

            rs_api = requests.get(url=self.url, params=payload, headers=headers) if payload else requests.get(url=self.url)
            self.rs_status_code = rs_api.status_code
            self.expected_status_code = expected_status_code

            if self.rs_status_code == 429:
                retry_after = int(rs_api.headers.get("Retry-After", 5))
                self._set_backoff(retry_after)
                time.sleep(self._backoff_delay)
                return self.get(endpoint, payload, headers, expected_status_code)

            try:
                self.rs_json = rs_api.json()
            except requests.exceptions.JSONDecodeError:
                logger.error(f"❌ Failed to decode JSON from {self.url}")
                logger.debug(f"🔻 Response body:\n{rs_api.text[:300]}...")
                self.rs_json = {}

            self.assert_status_code()
            self._reset_backoff() 
            logger.debug(f"✅ API GET Response is: {self.rs_json}")
            return self.rs_json

        except Exception as e:
            logger.error(f"❌ GET request to {self.url} failed: {e}", exc_info=True)
            return {}

    def post(self, endpoint: str, payload=None, headers=None, expected_status_code=200) -> json:
        if not headers:
            headers = {"Content-Type": "application/json"}
        self.url = self.base_url + endpoint
        logger.debug(f"Sending POST request to: {self.url}")

        try:
            self._apply_backoff()

            rs_api = requests.post(url=self.url, data=json.dumps(payload), headers=headers)
            self.rs_status_code = rs_api.status_code
            self.expected_status_code = expected_status_code
            if self.rs_status_code == 429:
                retry_after = int(rs_api.headers.get("Retry-After", 5))
                self._set_backoff(retry_after)
                time.sleep(self._backoff_delay)
                return self.post(endpoint, payload, headers, expected_status_code) 

            self.rs_json = rs_api.json()
            self.assert_status_code()
            self._reset_backoff()
            logger.debug(f"✅ API POST Response is: {self.rs_json}")
            return self.rs_json

        except Exception as e:
            logger.error(f"❌ POST request to {self.url} failed: {e}", exc_info=True)
            return {}
