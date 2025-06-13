import json
import requests
from helpers.logging_manager import LoggingHandler

# set up logger
logger = LoggingHandler.get_logger()


class RequestsUtility:

    def __init__(self, base_url: str):
        self.base_url = base_url

    def assert_status_code(self) -> None:
        assert self.rs_status_code == self.expected_status_code, (
            f"Expected status code {self.expected_status_code} but actual status code is {self.rs_status_code}\n"
            f"URL:{self.url}, Response Json: {self.rs_json}"
        )

    def get(
        self, endpoint: str, payload=None, headers=None, expected_status_code=200
    ) -> json:
        if not headers:
            headers = {"Content-Type": "application/json"}
        self.url = self.base_url + endpoint
        logger.debug(f"Sending GET request to: {self.url} with params: {payload}")
        try:
            if payload:
                rs_api = requests.get(url=self.url, params=payload, headers=headers)
            else:
                rs_api = requests.get(url=self.url)
            self.rs_status_code = rs_api.status_code
            self.expected_status_code = expected_status_code
            try:
                self.rs_json = rs_api.json()
            except requests.exceptions.JSONDecodeError:
                 logger.error(f"❌ Failed to decode JSON from {self.url}")
                 logger.debug(f"🔻 Response body:\n{rs_api.text[:300]}...")
                 self.rs_json = {}
    
            self.assert_status_code()
            logger.debug(f"✅ API GET Response is: {self.rs_json}")
            return self.rs_json
    
        except Exception as e:
                logger.error(f"❌ GET request to {self.url} failed: {e}")
                return {}
    
    def post(
        self, endpoint: str, payload=None, headers=None, expected_status_code=200
    ) -> json:
        if not headers:
            headers = {"Content-Type": "application/json"}
        self.url = self.base_url + endpoint
        rs_api = requests.post(url=self.url, data=json.dumps(payload), headers=headers)
        self.rs_status_code = rs_api.status_code
        self.expected_status_code = expected_status_code
        self.rs_json = rs_api.json()
        self.assert_status_code()

        logger.debug(f"Api POST Response is:{rs_api.json()}")

        return rs_api.json()
