# StackIt Cost Monitoring

## Overview

This repository contains code to monitor costs in the StackIT cloud.

## Why?

A common problem with compute intensive cloud projects is
that expensive resources like GPU nodes may consume the
available budget quickly if left behind even if unused, e.g.:

* A node with eight H100 cards may cost 60 €/h
* Or 43.000 €/month

To prevent this, a cleanup is needed after each compute run.
If this is forgotten or fails (both have been seen in the wild), that
needs to be discovered early. Checking the monthly bill may be
too late.

For this reason it is recommended to set up alarms to detect
phases of high ressource usage. In e.G. AWS this can be done by
using Billing Alarms. For StackIT no such feature exists but can be
implemented by using the StackIT Cost API.

## General Approach

**Nagios Plugin:** This example assumes that a system is available that can
genrate alarms and distribute them via suitable channels such as email,
chat systems, or SMS. Many such systems can either use Nagios plugins
(aka Nagios checks) directly (CheckMK, Icinga2) or at least supply
instructions on how to integrate or adapt them. So this example just
implements a Nagios plugin based on the StackIT Cost API and explains
how to configure it.

**Prometheus exporter**: Metrics can also get exporter in a Prometheus format
which can then get scraped by Prometheus. Alerts can be setup in Prometheus
and processed with Alertmanager.

**Yesterday's Costs:** It seems that costs are only reported with a daily
granularity. Also, during the night the last day's cost may not be available.
So the costs for the last two days are requested via the API, and the latest
data available is used. For data boundaries UTC time is used.

## Prerequisites

To access the API, one needs to create a suitable service account and
assign the required permissions:

1. Create an account using the WebGUI, item IAM AND MANAGEMENT / Service Accounts / + Create Service Account.
   Make sure that you save the credentials before closing the form.
2. Use IAM AND MANAGEMENT / Access / + Grant Access to assign the
   cost-management.cost.reader role to that service account.
3. Set up the credentials on your monitoring system in the same way
   as for a user who wants to use the StackIT CLI. The tool expects to
   find the file ~/.stackit/sa-key.json. That may be overwritten by
   supplying the --sa-key-json option.

## Installation

The script uses Python 3 — most likely any version newer than 3.10 will work.
Best use a separate virtual environment:

```sh
python3 -m venv /usr/local/lib/venvs/stackit_monitoring
. /usr/local/lib/venvs/stackit_monitoring/bin/activate
pip install stackit_cost_monitoring
```

To use the plugin with the Icinga example below, one will have to link
/usr/local/lib/venvs/stackit_monitoring/bin/check_stackit_costs to
/usr/lib/nagios/plugins.

## Usage

```sh
$ check_stackit_costs --help
usage: check_stackit_costs [-h] --customer-account-id CUSTOMER_ACCOUNT_ID
  --project-id PROJECT_ID [-w WARNING] [-c CRITICAL] [--sa-key-json SA_KEY_JSON]
  [--skip-discounts] [--api-log-file API_LOG_FILE]

Nagios plugin to monitor StackIT costs. The higher value of the cost of the present day (always 0?) and yesterday is used.

options:
  -h, --help            show this help message and exit
  --customer-account-id CUSTOMER_ACCOUNT_ID
                        StackIT customer account ID
  --project-id PROJECT_ID
                        StackIT project ID
  -w, --warning WARNING
                        Warning threshold for 24h cost in EUR (default: 10.00)
  -c, --critical CRITICAL
                        Critical threshold for 24h cost in EUR (default: 50.00)
  --sa-key-json SA_KEY_JSON
                        Path to StackIT credentials in JSON format (default: /home/wilhelmh/.stackit/sa-key.json)
  --skip-discounts      Skip discounted costs in calculation.
  --api-log-file API_LOG_FILE
                        Optional path to file where the API requests and responses will be logged.
    --mode MODE           Whether to run in nagios or prometheus mode. Default: nagios.
```

## Prometheus exporter

Use the `--mode prometheus` parameter. Then metrics can get queried with i.e. `curl localhost:8000/metrics`.
Example output:

```sh
$ curl localhost:8000/metrics
# HELP python_gc_objects_collected_total Objects collected during gc
# TYPE python_gc_objects_collected_total counter
python_gc_objects_collected_total{generation="0"} 0.0
python_gc_objects_collected_total{generation="1"} 218.0
python_gc_objects_collected_total{generation="2"} 0.0
# HELP python_gc_objects_uncollectable_total Uncollectable objects found during GC
# TYPE python_gc_objects_uncollectable_total counter
python_gc_objects_uncollectable_total{generation="0"} 0.0
python_gc_objects_uncollectable_total{generation="1"} 0.0
python_gc_objects_uncollectable_total{generation="2"} 0.0
# HELP python_gc_collections_total Number of times this generation was collected
# TYPE python_gc_collections_total counter
python_gc_collections_total{generation="0"} 0.0
python_gc_collections_total{generation="1"} 5.0
python_gc_collections_total{generation="2"} 0.0
# HELP python_info Python platform information
# TYPE python_info gauge
python_info{implementation="CPython",major="3",minor="14",patchlevel="3",version="3.14.3"} 1.0
# HELP process_virtual_memory_bytes Virtual memory size in bytes.
# TYPE process_virtual_memory_bytes gauge
process_virtual_memory_bytes 2.2245376e+08
# HELP process_resident_memory_bytes Resident memory size in bytes.
# TYPE process_resident_memory_bytes gauge
process_resident_memory_bytes 5.640192e+07
# HELP process_start_time_seconds Start time of the process since unix epoch in seconds.
# TYPE process_start_time_seconds gauge
process_start_time_seconds 1.77687753051e+09
# HELP process_cpu_seconds_total Total user and system CPU time spent in seconds.
# TYPE process_cpu_seconds_total counter
process_cpu_seconds_total 0.42000000000000004
# HELP process_open_fds Number of open file descriptors.
# TYPE process_open_fds gauge
process_open_fds 6.0
# HELP process_max_fds Maximum number of open file descriptors.
# TYPE process_max_fds gauge
process_max_fds 1024.0
# HELP stackit_project_cost Costs for project in EUR
# TYPE stackit_project_cost gauge
stackit_project_cost 0.0
```

## Icinga Example

Command definition:

```txt
object CheckCommand "stackit_costs" {
  command = [ PluginDir + "/check_stackit_costs" ]
  arguments = {
    "--customer-account-id" = {
      description = "ID of the StackIt Cloud account to monitor (required)"
      value = "$stackit_account_id$"
    }
    "--project-id" = {
      description = "ID of the StackIt Cloud project to monitor (required)"
      value = "$stackit_project_id$"
    }
    "--sa-key-json" = {
      description = "JSON file with StackIt service account data to use (required)"
      value = "$stackit_credential_path$"
    }
    "-w" = {
      description = "Warning threshold for daily costs in EUR"
      value = "$stackit_warning_eur$"
    }
    "-c" = {
      description = "Critical threshold for daily costs in EUR"
      value = "$stackit_critical_eur$"
    }
    "--api-log-file" = {
      description = "Path to file where the API requests and responses will be logged"
      value = "$stackit_api_log_file$"
    }
  }
  vars.stackit_warning_eur = 2.0
  vars.stackit_critical_eur = 10.0
}
```

It makes no sense to check the costs every minute, as the data is only updated daily.
To recover form errors easier, we check hourly:

```txt
apply Service "COST-test" {
  import "generic-service"
  check_interval = 1h
  retry_interval = 1h
  check_command = "stackit_costs"
  vars += {
    stackit_account_id = "..."
    stackit_project_id = "..."
    stackit_credential_path = "/var/lib/nagios/.stackit/cost-monitoring-test.json"
    stackit_warning_eur = "1.0"
    stackit_critical_eur = "10.0"
  }
  assign where host.name == "..."   # Does not really matter ...
}
```

## Remarks

Unfortunately, when this code was written, no Python bindings existed for the
StackIT Cost API. So we decided to manually code the API call.

It seems that service accounts are always tied to a project. Using a user
for monitoring seems unsuitable for security reasons. So this plugin only
can monitor one project at a time.

## Resources

* [STACKIT Docs: Cost Api](https://docs.api.stackit.cloud/documentation/cost/version/v3)
* [STACKIT Python SDK](https://github.com/stackitcloud/stackit-sdk-python)

## Acknowledgements

This tool was created by and with resources of University Hospital Heidelberg,
Klaus Tschira Institute for Computational Cardiology. StackIt GmbH supported
it by supplying the StackIT API and helping with some of the dirty details.
