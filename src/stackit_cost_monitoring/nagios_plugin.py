#!/usr/bin/python3
from enum import Enum
from pathlib import Path
from sys import exit
import argparse
from datetime import datetime, timedelta, timezone
from typing import NoReturn

from pydantic import BaseModel

from stackit_cost_monitoring.cost_api import CostApi, CostApiGranularity, CostApiItemWithDetails, CostApiException, \
    CostApiDepth
from stackit_cost_monitoring.auth import Auth, AuthException

SECONDS_PER_DAY = 24 * 3600
CENTS_PER_EURO = 100

DEFAULT_WARNING_EUROS = 10.0
DEFAULT_CRITICAL_EUROS = 50.0
DEFAULT_SA_KEY_JSON = Path.home() / ".stackit" / "sa-key.json"


class NagiosExitCodes(Enum):
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3


class ParsedArguments(BaseModel):
    customer_account_id: str
    project_id: str
    warning: float
    critical: float
    sa_key_json: Path


class NagiosReporter:
    def __init__(self, args: ParsedArguments):
        self.args = args
        self.today = datetime.now(timezone.utc).date()
        self.yesterday = self.today - timedelta(days=1)
        self.today_cost = 0.0
        self.yesterday_cost = 0.0

    def book_cost_item(self, cost_item: CostApiItemWithDetails):
        for report_data in cost_item.reportData:
            # ToDo: Should we add discounted costs?
            if report_data.timePeriod.start == self.today:
                self.today_cost += report_data.charge / CENTS_PER_EURO
            elif report_data.timePeriod.start == self.yesterday:
                self.yesterday_cost += report_data.charge / CENTS_PER_EURO
            else:
                raise Exception(f"CostApi returned unexpected date: {report_data.timePeriod.start}")

    def do_report(self) -> NoReturn:
        total_cost = self._estimate_24h_cost()
        if total_cost >= self.args.critical:
            exit_code = NagiosExitCodes.CRITICAL
            message = f"24h cost {total_cost:.2f} EUR >= {self.args.critical} EUR"
        elif total_cost >= self.args.warning:
            exit_code = NagiosExitCodes.WARNING
            message = f"WARNING: 24h cost {total_cost:.2f} EUR >= {self.args.warning} EUR"
        else:
            exit_code = NagiosExitCodes.OK
            message = f"24h cost {total_cost:.2f} EUR"
        return self._finish(exit_code, message, total_cost)

    def _estimate_24h_cost(self) -> float:
        now = datetime.now(timezone.utc)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        seconds_today = (now - midnight).total_seconds()
        seconds_yesterday = SECONDS_PER_DAY - seconds_today
        estimated_24h_cost = self.today_cost + self.yesterday_cost * seconds_yesterday / SECONDS_PER_DAY
        return estimated_24h_cost

    def _finish(self, status: NagiosExitCodes, message: str, total_cost: float) -> NoReturn:
        perf_data = f"cost_24h={total_cost:.2f};{self.args.warning};{self.args.critical};0;"
        print(f"{status.name}: {message} | {perf_data}")
        return exit(status.value)


def main():
    try:
        args = get_arguments()
        cost_item = get_cost(args)
        reporter = NagiosReporter(args)
        reporter.book_cost_item(cost_item)
        reporter.do_report()
    except (AuthException, CostApiException) as e:
        print(f"{NagiosExitCodes.UNKNOWN.name}: {e} |")
        exit(NagiosExitCodes.UNKNOWN.value)


def get_arguments() -> ParsedArguments:
    parser = argparse.ArgumentParser(
        description='Nagios plugin to monitor StackIT costs. The costs are estimated'
        ' by adding the costs of today and the weighted costs of yesterday.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--customer-account-id',
        required=True,
        help='StackIT customer account ID'
    )
    parser.add_argument(
        '--project-id',
        required=True,
        help='StackIT project ID'
    )
    parser.add_argument(
        '-w', '--warning',
        type=float,
        default=DEFAULT_WARNING_EUROS,
        help=f"Warning threshold for 24h cost in EUR (default: {DEFAULT_WARNING_EUROS:.2f})"
    )
    parser.add_argument(
        '-c', '--critical',
        type=float,
        default=DEFAULT_CRITICAL_EUROS,
        help=f"Critical threshold for 24h cost in EUR (default: {DEFAULT_CRITICAL_EUROS:.2f})"
    )
    parser.add_argument(
        '--sa-key-json',
        type=Path,
        default=DEFAULT_SA_KEY_JSON
    )

    parsed_arguments = ParsedArguments(**parser.parse_args().__dict__)
    if parsed_arguments.warning < 0.0:
        raise ValueError("Warning threshold must be >= 0.0")
    if parsed_arguments.critical <= parsed_arguments.warning:
        raise ValueError("Critical threshold must be > warning threshold")
    return parsed_arguments


def get_cost(args) -> CostApiItemWithDetails:
    auth = Auth(args.sa_key_json)
    cost_api = CostApi(auth)
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)

    result = cost_api.get_project_costs(
        args.customer_account_id,
        args.project_id,
        from_date=yesterday,
        to_date=today,
        granularity=CostApiGranularity.DAILY,
        depth=CostApiDepth.PROJECT,
        include_zero_costs=False,
    )

    if not isinstance(result, CostApiItemWithDetails):
        raise Exception("CostAPI returned item without report data!")
    return result


if __name__ == '__main__':
    main()
