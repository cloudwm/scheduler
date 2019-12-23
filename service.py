#!/usr/bin/python
from __future__ import print_function
import sys
import json
import logging
import re
from subprocess import Popen, PIPE

serviceletd = "/opt/servicelet/serviceletd"
clipath = "/opt/servicelet/cloudwmcli"
logpath = "/opt/servicelet/service.log"
crontab = "/opt/servicelet/crontab"


def update_service(client_id, client_secret, tasks):
    with open(crontab, 'w') as f:
        for t in tasks:
            print("%s root %s --api-clientid %s --api-secret %s server %s --name %s > %s 2>&1"
                  % (t["expression"], clipath, client_id, client_secret, t["action"], t["serverName"], logpath), file=f)


def crontab_regex():
    return re.compile(
        "^\\s*($|#|\\w+\\s*=|(\\?|\\*|(?:[0-5]?\\d)(?:(?:-|\/|\\,)(?:[0-5]?\\d))?(?:,(?:[0-5]?\\d)(?:(?:-|\/|\\,)(?:[0-5]?\\d))?)*)\\s+(\\?|\\*|(?:[0-5]?\\d)(?:(?:-|\/|\\,)(?:[0-5]?\\d))?(?:,(?:[0-5]?\\d)(?:(?:-|\/|\\,)(?:[0-5]?\\d))?)*)\\s+(\\?|\\*|(?:[01]?\\d|2[0-3])(?:(?:-|\/|\\,)(?:[01]?\\d|2[0-3]))?(?:,(?:[01]?\\d|2[0-3])(?:(?:-|\/|\\,)(?:[01]?\\d|2[0-3]))?)*)\\s+(\\?|\\*|(?:0?[1-9]|[12]\\d|3[01])(?:(?:-|\/|\\,)(?:0?[1-9]|[12]\\d|3[01]))?(?:,(?:0?[1-9]|[12]\\d|3[01])(?:(?:-|\/|\\,)(?:0?[1-9]|[12]\\d|3[01]))?)*)\\s+(\\?|\\*|(?:[1-9]|1[012])(?:(?:-|\/|\\,)(?:[1-9]|1[012]))?(?:L|W)?(?:,(?:[1-9]|1[012])(?:(?:-|\/|\\,)(?:[1-9]|1[012]))?(?:L|W)?)*|\\?|\\*|(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(?:(?:-)(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC))?(?:,(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(?:(?:-)(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC))?)*)\\s+(\\?|\\*|(?:[0-6])(?:(?:-|\/|\\,|#)(?:[0-6]))?(?:L)?(?:,(?:[0-6])(?:(?:-|\/|\\,|#)(?:[0-6]))?(?:L)?)*|\\?|\\*|(?:MON|TUE|WED|THU|FRI|SAT|SUN)(?:(?:-)(?:MON|TUE|WED|THU|FRI|SAT|SUN))?(?:,(?:MON|TUE|WED|THU|FRI|SAT|SUN)(?:(?:-)(?:MON|TUE|WED|THU|FRI|SAT|SUN))?)*)(|\\s)+(\\?|\\*|(?:|\\d{4})(?:(?:-|\/|\\,)(?:|\\d{4}))?(?:,(?:|\\d{4})(?:(?:-|\/|\\,)(?:|\\d{4}))?)*))$")


def exec_command(cmd, config_file):
    data = None
    with open(config_file, 'r') as json_file:
        data = json.load(json_file)
    if not data:
        logging.error("empty data file, could not write configuration")
        return 1
    # validate auth
    if "auth" not in data:
        logging.error("invalid data format, missing auth section")
        return 1
    if "clientId" not in data["auth"] or "clientSecret" not in data["auth"]:
        logging.error("invalid auth format, missing auth clientId or clientSecret")
        return 1

    # validate tasks
    if "tasks" not in data:
        logging.error("invalid data format, missing tasks section")
        return 1
    if not isinstance(data["tasks"], list):
        logging.error("invalid data format, tasks must be a list")
        return 1
    rg = crontab_regex()
    for task in data["tasks"]:
        if "action" not in task or "expression" not in task or "serverName" not in task:
            logging.error("invalid task format, tasks requires: action, expression, serverName")
            return 1
        if not task["action"] or not task["expression"] or not task["serverName"]:
            logging.error("invalid data format, tasks required fields are: action, expression, serverName")
            return 1
        if task["action"] not in ["poweron", "poweroff", "reboot"]:
            logging.error("invalid task format, poweron, poweroff and reboot are the only allowed operations")
            return 1
        if not rg.match(task["expression"]):
            logging.error("invalid task format, task expression is not valid")
            return 1

    return update_service(data["auth"]["clientId"], data["auth"]["clientSecret"], data["tasks"])


def update_schema():
    pass


def service_status():
    process = Popen("service crond status", shell=True, stdout=PIPE, stderr=PIPE, stdin=PIPE)
    stdout, stderr = process.communicate()
    exit_code = process.returncode
    if "running" in stdout:
        print("service ok")
        return 0
    if "stopped" in stdout:
        print("service stopped")
        return 0
    print("error retrieving status")
    print(stdout)
    return exit_code


def usage():
    print("Usage:")
    print("  service.py schema")
    print("  - updates configuration schema on management service")
    print("  service.py --exec <command> --path <config_json_file>")
    print("  - exec operation from json configuration file")
    return 1


def main():
    n_args = len(sys.argv)
    if n_args == 5 and sys.argv[1] == "--exec" and sys.argv[3] == "--path":
        return exec_command(sys.argv[2], sys.argv[4])
    if n_args == 2 and sys.argv[1] == "--schema":
        return update_schema()
    if n_args == 2 and sys.argv[1] == "--status":
        return service_status()
    return usage()


if __name__ == "__main__":
    logging.basicConfig(filename=logpath, filemode='a', format='%(name)s - %(levelname)s - %(message)s')
    try:
        rg = crontab_regex()
        result = main()
        sys.exit(result)
    except Exception as e:
        logging.critical("command failed, %s" % e)
