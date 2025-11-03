from datetime import date
from enum import Enum

import requests
from pydantic import BaseModel

from stackit_cost_monitoring.auth import Auth


STACKIT_API_BASE_URL = 'https://cost.api.stackit.cloud/v3'


class CostApiException(Exception):
    pass


class CostApiItem(BaseModel):
    customerAccountId: str
    projectId: str
    projectName: str
    totalCharge: float
    totalDiscount: float


class CostApiTimePeriod(BaseModel):
    end: date
    start: date


class CostApiDetails(BaseModel):
    charge: float
    discount: float
    quantity: int
    timePeriod: CostApiTimePeriod


class CostApiItemWithDetails(CostApiItem):
    reportData: list[CostApiDetails]


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
    def __init__(self, auth: Auth):
        self._auth = auth

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
        try:
            response = requests.get(
                url,
                params=params,
                headers={
                    'Authorization': f'Bearer {bearer_token}',
                    'Content-Type': 'application/json'
                }
            )
            response.raise_for_status()
        except Exception as e:
            raise CostApiException(f"GET {url} failed: {e}")
        data = response.json()
        if granularity == CostApiGranularity.NONE:
            return CostApiItem(**data)
        else:
            return CostApiItemWithDetails(**data)
