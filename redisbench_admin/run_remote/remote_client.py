#  BSD 3-Clause License
#
#  Copyright (c) 2021., Redis Labs Modules
#  All rights reserved.
#
import datetime
import logging

from redisbench_admin.run.common import (
    prepare_benchmark_parameters,
)
from redisbench_admin.run.run import calculate_client_tool_duration_and_check
from redisbench_admin.run_remote.remote_helpers import (
    benchmark_tools_sanity_check,
    remote_tool_pre_bench_step,
    post_process_remote_run,
)
from redisbench_admin.utils.benchmark_config import extract_benchmark_tool_settings
from redisbench_admin.utils.redisgraph_benchmark_go import (
    get_redisbench_admin_remote_path,
)
from redisbench_admin.utils.remote import (
    execute_remote_commands,
    fetch_file_from_remote_setup,
)


def run_remote_client_tool(
    allowed_tools,
    artifact_version,
    benchmark_config,
    client_public_ip,
    cluster_api_enabled,
    local_bench_fname,
    remote_results_file,
    return_code,
    server_plaintext_port,
    server_private_ip,
    start_time_ms,
    start_time_str,
    username,
    config_key,
    os_str,
    arch_str,
    step_name,
    warn_min_duration,
    client_ssh_port,
    private_key,
):
    (
        benchmark_min_tool_version,
        benchmark_min_tool_version_major,
        benchmark_min_tool_version_minor,
        benchmark_min_tool_version_patch,
        benchmark_tool,
        benchmark_tool_source,
        _,
        _,
    ) = extract_benchmark_tool_settings(benchmark_config, config_key)
    benchmark_tools_sanity_check(allowed_tools, benchmark_tool)
    local_output_artifacts = []
    remote_output_artifacts = []
    # setup the benchmark tool
    remote_tool_pre_bench_step(
        benchmark_config,
        benchmark_min_tool_version,
        benchmark_min_tool_version_major,
        benchmark_min_tool_version_minor,
        benchmark_min_tool_version_patch,
        benchmark_tool,
        client_public_ip,
        username,
        benchmark_tool_source,
        config_key,
        os_str,
        arch_str,
        client_ssh_port,
        private_key,
    )
    if "ann-benchmarks" in benchmark_tool:
        logging.info(
            "Ensuring that the ann-benchmark being used is the latest version release within the redisbench-admin package"
        )
        setup_remote_benchmark_ann(
            client_public_ip, username, private_key, client_ssh_port
        )

    command, command_str = prepare_benchmark_parameters(
        benchmark_config,
        benchmark_tool,
        server_plaintext_port,
        server_private_ip,
        remote_results_file,
        True,
        None,
        cluster_api_enabled,
        config_key,
        client_public_ip,
        username,
        private_key,
        client_ssh_port,
    )
    tmp = None
    if benchmark_tool == "redis-benchmark":
        tmp = local_bench_fname
        local_bench_fname = "result.csv"
    commands = [command_str]
    if "ann" in benchmark_tool:
        pkg_path = get_ann_remote_pkg_path(
            client_public_ip, client_ssh_port, private_key, username
        )
        benchmark_suffix = local_bench_fname[: len(local_bench_fname) - 5]
        create_website_path = pkg_path + "/run/ann/pkg/"
        logging.info("Remote create website path: {}".format(create_website_path))
        website_outputdir = "/tmp/website-{}".format(benchmark_suffix)
        website_outputdir_zip = "/tmp/website-{}.zip".format(benchmark_suffix)
        website_outputdir_zip_local = "website-{}.zip".format(benchmark_suffix)
        results_outputdir = pkg_path + "/run/ann/pkg/results"
        results_outputdir_zip = "/tmp/results-{}.zip".format(benchmark_suffix)
        results_outputdir_zip_local = "results-{}.zip".format(benchmark_suffix)

        mkdir_command = "mkdir -p {}".format(website_outputdir)
        create_website_command = (
            "cd {} && sudo python3 create_website.py --outputdir {}".format(
                create_website_path, website_outputdir
            )
        )
        zip_website_command = "zip -r {} {}".format(
            website_outputdir_zip, website_outputdir
        )

        zip_results_command = "zip -r {} {}".format(
            results_outputdir_zip, results_outputdir
        )
        commands.append(mkdir_command)
        commands.append(create_website_command)
        commands.append(zip_website_command)
        commands.append(zip_results_command)

        local_output_artifacts.append(website_outputdir_zip_local)
        local_output_artifacts.append(results_outputdir_zip_local)
        remote_output_artifacts.append(website_outputdir_zip)
        remote_output_artifacts.append(results_outputdir_zip)

    benchmark_start_time = datetime.datetime.now()
    # run the benchmark
    remote_run_result, stdout, _ = run_remote_benchmark(
        client_public_ip,
        username,
        private_key,
        remote_results_file,
        local_bench_fname,
        commands,
        client_ssh_port,
    )
    benchmark_end_time = datetime.datetime.now()
    benchmark_duration_seconds = calculate_client_tool_duration_and_check(
        benchmark_end_time, benchmark_start_time, step_name, warn_min_duration
    )
    results_dict = None
    if remote_run_result is True:
        (
            artifact_version,
            local_bench_fname,
            results_dict,
            return_code,
        ) = post_process_remote_run(
            artifact_version,
            benchmark_config,
            benchmark_tool,
            local_bench_fname,
            return_code,
            start_time_ms,
            start_time_str,
            stdout,
            tmp,
        )
    else:
        logging.error(
            "Given the remote tool failed, inspecting the remote results file content ({})".format(
                remote_results_file
            )
        )
        command = ["cat {}".format(remote_results_file)]
        recv_exit_status, stdout, stderr = execute_remote_commands(
            client_public_ip, username, private_key, [command], client_ssh_port
        )[0]
        logging.warning("Remote results file content: {}".format(stdout))

    final_local_output_artifacts = []
    if len(remote_output_artifacts) > 0:
        logging.info(
            "Retrieving a total of {} remote client artifacts".format(
                len(remote_output_artifacts)
            )
        )
    for client_artifact_n, client_remote_artifact in enumerate(remote_output_artifacts):
        client_local_artifact = local_output_artifacts[client_artifact_n]
        logging.info(
            "Retrieving remote client artifact: {} into local file {}".format(
                client_remote_artifact, client_local_artifact
            )
        )
        fetch_file_from_remote_setup(
            client_public_ip,
            username,
            private_key,
            client_local_artifact,
            client_remote_artifact,
        )
        final_local_output_artifacts.append(client_local_artifact)

    return (
        artifact_version,
        benchmark_duration_seconds,
        local_bench_fname,
        remote_run_result,
        results_dict,
        return_code,
        final_local_output_artifacts,
    )


def setup_remote_benchmark_ann(
    client_public_ip, username, private_key, client_ssh_port
):
    commands = [
        "sudo apt install python3-pip -y",
        "sudo pip3 install redisbench-admin>=0.7.0",
    ]
    # last argument (get_pty) needs to be set to true
    # check: https://stackoverflow.com/questions/5785353/paramiko-and-sudo
    execute_remote_commands(
        client_public_ip, username, private_key, commands, client_ssh_port, True
    )
    pkg_path = get_ann_remote_pkg_path(
        client_public_ip, client_ssh_port, private_key, username
    )
    logging.info("ensuring there is a clean results folder on ann-benchmarks pkg")
    commands = [
        "sudo rm -rf {}/results/*".format(pkg_path),
    ]
    execute_remote_commands(
        client_public_ip, username, private_key, commands, client_ssh_port, True
    )


def get_ann_remote_pkg_path(client_public_ip, client_ssh_port, private_key, username):
    [recv_exit_status, stdout, stderr] = get_redisbench_admin_remote_path(
        client_public_ip, username, private_key, client_ssh_port
    )[0]
    pkg_path = stdout[0].strip()
    return pkg_path


def run_remote_benchmark(
    client_public_ip,
    username,
    private_key,
    remote_results_files,
    local_results_files,
    commands,
    ssh_port=22,
):
    remote_run_result = False
    res = execute_remote_commands(
        client_public_ip, username, private_key, commands, ssh_port
    )
    recv_exit_status, _, _ = res[0]

    if recv_exit_status != 0:
        logging.error(
            "Exit status of remote command execution {}. Printing stdout and stderr".format(
                recv_exit_status
            )
        )
        stderr, stdout = print_commands_outputs(commands, True, res)
    else:
        logging.info(
            "Remote process exited normally. Exit code {}. Printing stdout.".format(
                recv_exit_status
            )
        )
        stderr, stdout = print_commands_outputs(commands, False, res)

        logging.info("Extracting the benchmark results")
        remote_run_result = True
        if "ycsb" not in commands[0]:
            if type(local_results_files) == str:
                local_results_file = local_results_files
                remote_results_file = remote_results_files
                fetch_file_from_remote_setup(
                    client_public_ip,
                    username,
                    private_key,
                    local_results_file,
                    remote_results_file,
                )
            if type(local_results_files) == list:
                assert len(local_results_files) == len(remote_results_files)
                for pos, local_results_file in enumerate(local_results_files):
                    remote_results_file = remote_results_files[pos]
                    fetch_file_from_remote_setup(
                        client_public_ip,
                        username,
                        private_key,
                        local_results_file,
                        remote_results_file,
                    )
    return remote_run_result, stdout, stderr


def print_commands_outputs(commands, print_err, res):
    bench_stdout = ""
    bench_stderr = ""
    for pos, res_tuple in enumerate(res):
        recv_exit_status, stdout, stderr = res_tuple
        if pos == 0:
            stderr, stdout = stderr, stdout
        logging.info(
            "Exit status for command {}: {}".format(commands[pos], recv_exit_status)
        )
        logging.info("\tremote process stdout:")
        for line in stdout:
            print(line.strip())
        if print_err:
            logging.error("\tremote process stderr:")
            for line in stderr:
                print(line.strip())
    return bench_stderr, bench_stdout
