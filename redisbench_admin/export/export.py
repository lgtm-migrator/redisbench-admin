#  Apache License Version 2.0
#
#  Copyright (c) 2021., Redis Labs Modules
#  All rights reserved.
#


import json
import logging
import datetime

import redis
from redistimeseries.client import Client

from redisbench_admin.export.common.common import split_tags_string
from redisbench_admin.run.git import git_vars_crosscheck

from redisbench_admin.run.redistimeseries import timeseries_test_sucess_flow
from redisbench_admin.utils.benchmark_config import (
    get_defaults,
    parse_exporter_timemetric,
)


def export_command_logic(args, project_name, project_version):
    logging.info(
        "Using: {project_name} {project_version}".format(
            project_name=project_name, project_version=project_version
        )
    )
    benchmark_file = args.benchmark_result_file
    results_format = args.results_format
    (_, tf_github_branch, tf_github_org, tf_github_repo, _,) = git_vars_crosscheck(
        None, args.github_branch, args.github_org, args.github_repo, None
    )
    results_dict = {}
    if results_format == "json":
        with open(benchmark_file, "r") as json_file:
            results_dict = json.load(json_file)
    extra_tags_dict = split_tags_string(args.extra_tags)
    logging.info("Using the following extra tags: {}".format(extra_tags_dict))

    logging.info(
        "Checking connection to RedisTimeSeries to host: {}:{}".format(
            args.redistimeseries_host, args.redistimeseries_port
        )
    )
    rts = Client(
        host=args.redistimeseries_host,
        port=args.redistimeseries_port,
        password=args.redistimeseries_pass,
    )
    try:
        rts.redis.ping()
    except redis.exceptions.ConnectionError as e:
        logging.error(
            "Error while connecting to RedisTimeSeries data sink at: {}:{}. Error: {}".format(
                args.redistimeseries_host, args.redistimeseries_port, e.__str__()
            )
        )
        exit(1)

    benchmark_duration_seconds = None
    exporter_spec_file = args.exporter_spec_file
    (
        _,
        metrics,
        exporter_timemetric_path,
        _,
        _,
    ) = get_defaults(exporter_spec_file)
    if args.override_test_time:
        datapoints_timestamp = int(args.override_test_time.timestamp() * 1000.0)
        logging.info(
            "Overriding test time with the following date {}. Timestamp {}".format(
                args.override_test_time, datapoints_timestamp
            )
        )
    else:
        logging.info(
            "Trying to parse the time-metric from path {}".format(
                exporter_timemetric_path
            )
        )
        datapoints_timestamp = parse_exporter_timemetric(
            exporter_timemetric_path, results_dict
        )
        if datapoints_timestamp is None:
            datapoints_timestamp = int(
                datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000.0
            )
            logging.warning(
                "Error while trying to parse datapoints timestamp. Using current system timestamp Error: {}".format(
                    datapoints_timestamp
                )
            )

    timeseries_test_sucess_flow(
        True,
        args.deployment_version,
        None,
        benchmark_duration_seconds,
        None,
        metrics,
        args.deployment_name,
        args.deployment_type,
        exporter_timemetric_path,
        results_dict,
        rts,
        datapoints_timestamp,
        args.test_name,
        tf_github_branch,
        tf_github_org,
        tf_github_repo,
        args.triggering_env,
        extra_tags_dict,
        None,
        None,
    )
