import json
import requests
import logging as logger


class RequestsUtility:

    def __init__(self):
        self.base_url = "https://api.dexscreener.com/"

    def assert_status_code(self):
        assert self.rs_status_code == self.expected_status_code, (
            f"Expected status code{self.expected_status_code} but actual status code is{self.rs_status_code}"
            f"URL:{self.url}, Response Json: {self.rs_json}"
        )

    def get(self, endpoint, headers=None, expected_status_code=200) -> json:
        if not headers:
            headers = {"Content-Type": "application/json"}
        self.url = self.base_url + endpoint
        rs_api = requests.get(url=self.url)
        self.rs_status_code = rs_api.status_code
        self.expected_status_code = expected_status_code
        self.rs_json = rs_api.json()
        self.assert_status_code()

        logger.debug(f"Api GET Response is:{rs_api.json()}")

        return rs_api.json()
