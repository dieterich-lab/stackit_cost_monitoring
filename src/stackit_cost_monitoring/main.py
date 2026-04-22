#!/usr/bin/env python3
"""Main component."""

import time
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sys import exit as sys_exit

from pydantic import BaseModel

from stackit_cost_monitoring.auth import Auth, AuthException
from stackit_cost_monitoring.cost_api import (
    CostApi,
    CostApiDepth,
    CostApiException,
    CostApiGranularity,
    CostApiItem,
)
from stackit_cost_monitoring.reporter import Reporter
from prometheus_client import start_http_server, Gauge

SECONDS_PER_DAY = 24 * 3600
CENTS_PER_EURO = 100

DEFAULT_WARNING_EUROS = 10.0
DEFAULT_CRITICAL_EUROS = 50.0
DEFAULT_SA_KEY_JSON = Path.home() / ".stackit" / "sa-key.json"
SLEEP = 5  # seconds


class ParsedArguments(BaseModel):
    """Parsed arguments."""

    customer_account_id: str
    project_id: str
    warning: float
    critical: float
    sa_key_json: Path
    skip_discounts: bool
    api_log_file: Path | None
    mode: str


def main() -> None:
    """Run main function."""
    try:
        args = get_arguments()
        match args.mode:
            case "nagios":
                cost_item = get_cost(args)
                reporter = Reporter(args)
                reporter.book_cost_item(cost_item)
                reporter.do_NagiosReport()
            case "prometheus":
                print("Starting prometheus exporter.")
                start_http_server(8000)
                COST = Gauge("stackit_project_cost", "Costs for project in EUR")
                while True:
                    cost_item = get_cost(args)
                    reporter = Reporter(args)
                    reporter.book_cost_item(cost_item)
                    reporter.prometheus_export(COST)
                    time.sleep(SLEEP)
            case _:
                print(f"Unknown mode {args.mode} !")
                sys_exit(1)

    except (AuthException, CostApiException) as e:
        print(e)
        sys_exit(1)


def get_arguments() -> ParsedArguments:
    """Parse arguments."""
    parser = argparse.ArgumentParser(
        description="Monitor StackIT costs. The higher value "
        "of the cost of the present day (always 0?) and yesterday is used.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--customer-account-id", required=True, help="StackIT customer account ID"
    )
    parser.add_argument("--project-id", required=True, help="StackIT project ID")
    parser.add_argument(
        "-w",
        "--warning",
        type=float,
        default=DEFAULT_WARNING_EUROS,
        help=(
            "Warning threshold for 24h cost in EUR"
            f"(default: {DEFAULT_WARNING_EUROS:.2f})"
        ),
    )
    parser.add_argument(
        "-c",
        "--critical",
        type=float,
        default=DEFAULT_CRITICAL_EUROS,
        help=(
            "Critical threshold for 24h cost in EUR"
            f"(default: {DEFAULT_CRITICAL_EUROS:.2f})"
        ),
    )
    parser.add_argument(
        "--sa-key-json",
        type=Path,
        default=DEFAULT_SA_KEY_JSON,
        help=(
            "Path to StackIT credentials in JSON format"
            f"(default: {DEFAULT_SA_KEY_JSON})"
        ),
    )
    parser.add_argument(
        "--skip-discounts",
        action="store_true",
        help="Skip discounted costs in calculation.",
    )
    parser.add_argument(
        "--api-log-file",
        type=Path,
        required=False,
        help=(
            "Optional path to file where the API requests and responses will be logged."
        ),
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="nagios",
        help="Whether to run in nagios or prometheus mode. Default: nagios.",
    )

    parsed_arguments = ParsedArguments(**parser.parse_args().__dict__)
    if parsed_arguments.warning < 0.0:
        msg = "Warning threshold must be >= 0.0"
        raise ValueError(msg)
    if parsed_arguments.critical <= parsed_arguments.warning:
        msg = "Critical threshold must be > warning threshold"
        raise ValueError(msg)
    return parsed_arguments


def get_cost(args: ParsedArguments) -> CostApiItem:
    """Get costs."""
    auth = Auth(args.sa_key_json)
    api_log = None
    try:
        if args.api_log_file is not None:
            api_log = Path(args.api_log_file).open("a")  # noqa: SIM115
        cost_api = CostApi(auth, api_log=api_log)
        today = datetime.now(
            timezone.utc
        ).date()  # StackIT, ticket SSD-13595: UTC is used
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)

        return cost_api.get_project_costs(
            args.customer_account_id,
            args.project_id,
            from_date=two_days_ago,
            to_date=yesterday,
            granularity=CostApiGranularity.DAILY,
            depth=CostApiDepth.PROJECT,
            include_zero_costs=True,
        )

    finally:
        if api_log is not None:
            api_log.close()


if __name__ == "__main__":
    main()
