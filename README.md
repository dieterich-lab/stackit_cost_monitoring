# StackIt Cost Monitoring

## Overview

This repository contains a Nagios Plugin to monitor costs in the StackIT cloud.

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

**Yesterday's Costs:** It seems that most (or all?) costs are only reported
with a daily granularity. So an alarm is given if yesterday's costs exceed the
given threshold. If today's costs are higher, that number would be used instead.
So far today's costs were always reported as 0. The UTC timezone is used for
date boundaries.

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

```shell
python3 -m venv /usr/local/lib/venvs/stackit_monitoring
. /usr/local/lib/venvs/stackit_monitoring/bin/activate
pip install stackit_cost_monitoring
```

To use the plugin with the Icinga example below, one will have to link
/usr/local/lib/venvs/stackit_monitoring/bin/check_stackit_costs to
/usr/lib/nagios/plugins.

## Usage

```
$ poetry run check_stackit_costs --help
usage: check_stackit_costs [-h] --customer-account-id CUSTOMER_ACCOUNT_ID --project-id PROJECT_ID [-w WARNING] [-c CRITICAL] [--sa-key-json SA_KEY_JSON]

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
                        Path to StackIT credentials in JSON format (default: /home/.../.stackit/sa-key.json)
```

## Icinga Example

Command definition:

```
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
  }
  vars.stackit_warning_eur = 2.0
  vars.stackit_critical_eur = 10.0
}
```

The actual checks may look like this:

```
apply Service "COST-test" {
  import "generic-service"

  check_command = "stackit_costs"
  vars += {
    stackit_account_id = "..."
    stackit_project_id = "..."
    stackit_credential_path = "/var/lib/nagios/.stackit/cost-monitoring-test.json"
    stackit_warning_eur = "1.0"
    stackit_critical_eur = "10.0"
  }
  assign where host.name == "..."
}
```

## Remarks

Unfortunately, when this code was written, no Python bindings existed for the
StackIT Cost API. So we decided to manually code the API call.

It seems that service accounts are always tied to a project. Using a user
for monitoring seems unsuitable for security reasons. So this plugin only
can monitor one project at a time.

**Unter investigation:**
The official documentation claims that for a given granularity and
depth='project' the response to Rest call will always contain the
reportData array. However, there seems to be a short time period
in the night, during which this data is missing. If this data is missing,
the plugin will use total cost fields to estimate yesterday's costs.

## Resources

* https://docs.api.stackit.cloud/documentation/cost/version/v3
* https://github.com/stackitcloud/stackit-sdk-python

## Acknowledgements

This tool was created by and with resources of University Hospital Heidelberg,
Klaus Tschira Institute for Computational Cardiology. StackIt GmbH supported
it by supplying the StackIT API and helping with some of the dirty details.
