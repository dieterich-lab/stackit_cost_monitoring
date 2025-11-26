from datetime import date, UTC, datetime, timezone
from enum import Enum
from time import localtime
from typing import Optional, TextIO

import requests
from pydantic import BaseModel

from stackit_cost_monitoring.auth import Auth


STACKIT_API_BASE_URL = 'https://cost.api.stackit.cloud/v3'


class CostApiException(Exception):
    pass


class CostApiTimePeriod(BaseModel):
    end: date
    start: date


class CostApiDetails(BaseModel):
    charge: float
    discount: float
    quantity: int
    timePeriod: CostApiTimePeriod


class CostApiItem(BaseModel):
    customerAccountId: str
    projectId: str
    projectName: str
    totalCharge: float
    totalDiscount: float
    reportData: Optional[list[CostApiDetails]] = None


class CostApiDepth(Enum):
    PROJECT = 'project'
    SERVICE = 'service'
    AUTO = 'auto'


class CostApiGranularity(Enum):
    NONE = 'none'
    DAILY = 'daily'
    WEEKLY = 'weekly'
    MONTHLY = 'monthly'
    YEARLY = 'yearly'


class CostApi:
    def __init__(self, auth: Auth, api_log: Optional[TextIO] = None):
        self._auth = auth
        self._api_log = api_log

    def get_project_costs(
            self,
            customer_account_id: str,
            project_id: str,
            from_date: date,
            to_date: date,
            depth: CostApiDepth = CostApiDepth.AUTO,
            granularity: CostApiGranularity = CostApiGranularity.NONE,
            include_zero_costs: bool = False,
    ) -> CostApiItem:
        """
        Use the StackIT Cost API to get costs for a customer account.
        If called with a granularity, returns a CostApiItemWithDetails
        is returned. Otherwise, no details will be present.
        """
        url = f"{STACKIT_API_BASE_URL}/costs/{customer_account_id}/projects/{project_id}"
        params = {
            'from': from_date.strftime('%Y-%m-%d'),
            'to': to_date.strftime('%Y-%m-%d'),
            'depth': depth.value,
            'granularity': granularity.value,
            'includeZeroCosts': include_zero_costs,
        }
        bearer_token = self._auth.get_bearer_token()
        self._log(f"Request GET {url} {params}\n")
        try:
            response = requests.get(
                url,
                params=params,
                headers={
                    'Authorization': f'Bearer {bearer_token}',
                    'Content-Type': 'application/json'
                }
            )
            self._log(f"Response {response.status_code} {response.text}\n")
            response.raise_for_status()
        except Exception as e:
            self._log(f"Error {e}\n")
            raise CostApiException(f"GET {url} failed: {e}")
        data = response.json()
        try:
            return CostApiItem(**data)
        except Exception as e:
            raise CostApiException(
                f"Failed to parse response as CostApiItem: {e}\n"
                f"Response: {response.text}"
            )

    def _log(self, message: str):
        if self._api_log is None:
            return
        now = datetime.now().astimezone().isoformat()
        self._api_log.write(f"{now} {message}\n")