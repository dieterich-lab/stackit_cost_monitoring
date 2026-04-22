from enum import Enum
from typing import NoReturn

CENTS_PER_EURO = 100


class NagiosExitCodes(Enum):
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3


class Reporter:
    def __init__(self, args: ParsedArguments):
        self.args = args
        self._report_date = None
        self._cost = None
        self._discounted_cost = None
        self._report_data_message = None

    def book_cost_item(self, cost_item: CostApiItem):
        if cost_item.reportData is None:
            self._book_total_cost(cost_item, "CostApi returned no reportData")
            return
        if len(cost_item.reportData) == 0:
            self.__book_total_cost(cost_item, "CostApi returned empty reportData")
            return
        for report_data in cost_item.reportData:
            if (
                self._report_date is not None
                and report_data.timePeriod.start < self._report_date
            ):
                continue
            self._report_date = report_data.timePeriod.start
            self._cost = report_data.charge / CENTS_PER_EURO
            self._discounted_cost = report_data.discount / CENTS_PER_EURO

    def _book_total_cost(self, cost_item: CostApiItem, message: str):
        self._report_data_message = message
        self._cost = cost_item.totalCharge / CENTS_PER_EURO
        self._discounted_cost = cost_item.totalDiscount / CENTS_PER_EURO

    def prometheus_export(self, prometheus_metric) -> NoReturn:
        """Export prometheus metrics."""
        cost = self._cost
        """
            StackIt's answer to ticket SSD-13595:

                The totalCharge value in the API response already includes all granted discounts.

            To detect pathological effects we should add the discounted costs to get an
            alarm before all our free budget has been used. By default we add the discounts.
        """
        if self._cost is None:
            if self._report_data_message is None:
                print("Internal error: Have no data and do not know why")
            else:
                print(f"Zero costs ({self._report_data_message})")

        if not self.args.skip_discounts:
            cost += self._discounted_cost
        if self._report_date is None:
            report_date_str = "(unknown date - no detailed report data)"
        else:
            data_str = self._report_date.strftime("%Y-%m-%d")
            report_date_str = f"for {data_str}"

        if cost > 0 and self._report_data_message is not None:
            message = (
                f"No detailed reportData ({self._report_data_message}) "
                f"but non-zero costs {cost:.2f} EUR"
            )
        else:
            message = f"Daily costs {cost:.2f} EUR {report_date_str}"

        print(message)
        prometheus_metric.set(cost)

    def do_NagiosReport(self) -> NoReturn:
        cost = self._cost
        """"
            StackIt's answer to ticket SSD-13595:

                The totalCharge value in the API response already includes all granted discounts.

            To detect pathological effects we should add the discounted costs to get an
            alarm before all our free budget has been used. By default we add the discounts.
        """
        if self._cost is None:
            if self._report_data_message is None:
                return self._nagios_finish(
                    NagiosExitCodes.UNKNOWN,
                    "Internal error: Have no data and do not know why",
                )
            else:
                return self._nagios_finish(
                    NagiosExitCodes.OK, f"Zero costs ({self._report_data_message})"
                )

        if not self.args.skip_discounts:
            cost += self._discounted_cost
        if self._report_date is None:
            report_date_str = "(unknown date - no detailed report data)"
        else:
            data_str = self._report_date.strftime("%Y-%m-%d")
            report_date_str = f"for {data_str}"

        if cost >= self.args.critical:
            exit_code = NagiosExitCodes.CRITICAL
            message = f"Daily costs {cost:.2f} EUR >= {self.args.critical} EUR {report_date_str}"
        elif cost >= self.args.warning:
            exit_code = NagiosExitCodes.WARNING
            message = f"Daily costs {cost:.2f} EUR >= {self.args.warning} EUR {report_date_str}"
        elif cost > 0 and self._report_data_message is not None:
            exit_code = NagiosExitCodes.WARNING
            message = (
                f"No detailed reportData ({self._report_data_message}) "
                f"but non-zero costs {cost:.2f} EUR"
            )
        else:
            exit_code = NagiosExitCodes.OK
            message = f"Daily costs {cost:.2f} EUR {report_date_str}"

        return self._nagios_finish(exit_code, message)

    def _nagios_finish(self, status: NagiosExitCodes, message: str) -> NoReturn:
        warning = self.args.warning
        critical = self.args.critical
        if self._cost is not None:
            perf_data_items = [
                f"cost={self._cost:.2f};{warning:.2f};{critical:.2f};0",
                f"discounted_cost={self._discounted_cost:.2f};{warning:.2f};{critical:.2f};0",
            ]
        else:
            perf_data_items = []
        perf_data = " ".join(perf_data_items)
        print(f"{status.name}: {message} | {perf_data}")
        return exit(status.value)
