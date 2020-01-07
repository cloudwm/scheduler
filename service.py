#!/usr/bin/python3
import json
import logging
import re
import sys
import tempfile
import os
import traceback
from subprocess import Popen, PIPE
from croniter import croniter

# service path definitions
serviceletd = "/opt/servicelet/serviceletd"
schema = "/opt/servicelet/schema.json"
clipath = "/opt/servicelet/cloudwmcli"
logpath = "/opt/servicelet/service.log"


def update_service(client_id, client_secret, tasks):
    # todo: make sure user spool directory exists
    with tempfile.NamedTemporaryFile(delete=False, suffix='.ctab', prefix=os.path.join(tempfile.gettempdir(), "")) as tmp:
        for t in tasks:
            tmp.write(("%s root %s --api-clientid %s --api-secret %s server %s --name %s > %s 2>&1\n"
                    % (t["expression"], clipath, client_id, client_secret, t["action"], t["serverName"], logpath)).encode('utf-8'))

        # update cron
        tmp.close()
        code, out = exec_cmd("crontab %s" % (tmp.name))
        # os.remove(tmp.name)
        if code != 0:
            raise Exception("cron update error: %s" % (out.decode("utf-8")))


def valid_cron_expr(expr):
    try:
        croniter(expr)
        return True
    except Exception as e:
        logging.critical("invalid expression: %s", e)
        return False


def exec_command(cmd, config_file):
    # read command parameters
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
        if not valid_cron_expr(task["expression"]):
            logging.error("invalid task format, task expression is not valid")
            return 1

    # write new crontab for user
    update_service(data["auth"]["clientId"], data["auth"]["clientSecret"], data["tasks"])
    return 0


def exec_cmd(cmd):
    """
    executes shell command
    returns process exit code and stdout on success or stderr on failure
    """
    process = Popen(cmd, shell=True, stdout=PIPE, stdin=PIPE, stderr=PIPE)
    stdout, stderr = process.communicate()
    return process.returncode, stdout if process.returncode == 0 else stdout + stderr


def update_schema():
    try:
        cmd = "%s schema %s" % (serviceletd, schema)
        process = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE, stdin=PIPE)
        stdout, stderr = process.communicate()
        if stderr and len(stderr) > 0 or process.returncode != 0:
            logging.critical("failed to push schema, %s", stderr)
            return 1
        return 0
    except Exception as e:
        logging.critical("failed to push schema, %s", e)
        return 1


def parse_service_status(output):
    for l in output.split("\n"):
        m = re.match("^.*Active: (.+)", l)
        if m:
            return m.group(1)
    return "error retrieving status"


def service_status():
    exit_code, out = exec_cmd("systemctl status cron")
    status = parse_service_status(out.decode("utf-8"))
    print(status)
    if exit_code != 0:
        return exit_code
    if "active (running)" in status:
        # this is the only healthy status
        return 0
    return 1


def usage():
    print("Usage:")
    print("  service.py --schema")
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
        result = main()
        sys.exit(result)
    except Exception as e:
        msg = "command failed, %s" % e
        logging.critical(msg)
        print(msg, file=sys.stderr)
        formatted_lines = traceback.format_exc().splitlines()
        for l in formatted_lines:
            logging.error(l)
        sys.exit(1)
