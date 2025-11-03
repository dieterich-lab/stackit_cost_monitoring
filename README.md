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

This example assumes that a system is available that can genrate
alarms and distribute them via suitable channels such as email,
chat systems, or SMS. Many such systems can either use Nagios plugins
(aka Nagios checks) directly (CheckMK, Icinga2) or at least supply
instructions on how to integrate or adapt them. So this example just
implements a Nagios plugin based on the StackIT Cost API and explains
how to configure it.

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

The script uses Python 3 — most likely any version newer than 3.10 will work:

```shell
python -m venv /usr/local/lib/venvs/stackit_monitoring
. /usr/local/lib/venvs/stackit_monitoring/bin/activate
pip install .
```

The source code is not needed after installation. To get exactly the same versions as used during development,
use poetry instead of pip.

### Option 2: OS packages for the dependencies

If you prefer to manage the dependencies via your OS package manager,
you can install them e.g. on Debian like this:

```shell
apt-get install python3-jwt python3-pydantic
```

To run the script without an installation, you may have to set the `PYTHONPATH` environment
variable to include the `cost_monitoring/src/stackit_cost_monitoring directory`.

## Usage

```
$ check_stackit_costs --help
usage: check_stackit_costs [-h] --customer-account-id CUSTOMER_ACCOUNT_ID --project-id PROJECT_ID [-w WARNING] [-c CRITICAL] [--sa-key-json SA_KEY_JSON]

Nagios plugin to monitor StackIT costs. The costs are estimated by adding the costs of today and the weighted costs of yesterday.

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
```

## Remarks

Unfortunately, when this code was written, no Python bindings existed for the
StackIT Cost API. So we decided to manually code the API call.

It seems that service accounts are always tied to a project. Using a user
for monitoring seems unsuitable for security reasons. So this plugin only
can monitor one project at a time. 

## Resources

* https://docs.api.stackit.cloud/documentation/cost/version/v3
* https://github.com/stackitcloud/stackit-sdk-python
