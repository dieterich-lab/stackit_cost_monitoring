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
        self.today_discounted_cost = 0.0
        self.yesterday_cost = 0.0
        self.yesterday_discounted_cost = 0.0

    def book_cost_item(self, cost_item: CostApiItemWithDetails):
        for report_data in cost_item.reportData:
            if report_data.timePeriod.start == self.today:
                self.today_cost += report_data.charge / CENTS_PER_EURO
                self.today_discounted_cost += report_data.discount / CENTS_PER_EURO
            elif report_data.timePeriod.start == self.yesterday:
                self.yesterday_cost += report_data.charge / CENTS_PER_EURO
                self.yesterday_discounted_cost += report_data.discount / CENTS_PER_EURO
            else:
                raise Exception(f"CostApi returned unexpected date: {report_data.timePeriod.start}")

    def do_report(self) -> NoReturn:
        today_cost = self.today_cost
        yesterday_cost = self.yesterday_cost
        """"
            StackIt's answer to ticket SSD-13595:
            
                The totalCharge value in the API response already includes all granted discounts.
                
            To detect pathological effects we should add the discounted costs to get an
            alarm before all our free budget has been used. By default we add the discounts.
        """
        if not self.args.skip_discount:
            today_cost += self.today_discounted_cost
            yesterday_cost += self.yesterday_discounted_cost
        total_cost = max(today_cost, yesterday_cost)
        if total_cost >= self.args.critical:
            exit_code = NagiosExitCodes.CRITICAL
            message = f"Daily costs {total_cost:.2f} EUR >= {self.args.critical} EUR"
        elif total_cost >= self.args.warning:
            exit_code = NagiosExitCodes.WARNING
            message = f"Daily costs {total_cost:.2f} EUR >= {self.args.warning} EUR"
        else:
            exit_code = NagiosExitCodes.OK
            message = f"Daily costs {total_cost:.2f} EUR"
        return self._finish(exit_code, message)

    def _finish(self, status: NagiosExitCodes, message: str) -> NoReturn:
        perf_data_items = [
            f"yesterday_cost={self.yesterday_cost:.2f};;;",
            f"yesterday_discounted_cost={self.yesterday_discounted_cost:.2f};;;",
            f"today_cost={self.today_cost:.2f};;;",
            f"today_discounted_cost={self.today_discounted_cost:.2f};;;",
        ]
        perf_data = ' '.join(perf_data_items)
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
        description='Nagios plugin to monitor StackIT costs. The higher value '
        'of the cost of the present day (always 0?) and yesterday is used.',
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
        default=DEFAULT_SA_KEY_JSON,
        help=f"Path to StackIT credentials in JSON format (default: {DEFAULT_SA_KEY_JSON})"
    )
    parser.add_argument(
        '--skip-discount',
        action='store_true',
        help='Skip discounted costs in calculation.'
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
    today = datetime.now(timezone.utc).date()  # StackIT, ticket SSD-13595: UTC is used
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
