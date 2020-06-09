import datetime as dt
import json
import operator
import os
import os.path
import os.path
import tarfile
from functools import reduce
from zipfile import ZipFile

import boto3
import requests
from tqdm import tqdm

EPOCH = dt.datetime.utcfromtimestamp(0)


def upload_artifacts_to_s3(artifacts, s3_bucket_name, s3_bucket_path):
    print("-- uploading results to s3 -- ")
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(s3_bucket_name)
    progress = tqdm(unit="files", total=len(artifacts))
    for input in artifacts:
        object_key = '{bucket_path}{filename}'.format(bucket_path=s3_bucket_path, filename=input)
        bucket.upload_file(input, object_key)
        object_acl = s3.ObjectAcl(s3_bucket_name, object_key)
        response = object_acl.put(ACL='public-read')
        progress.update()
    progress.close()


def whereis(program):
    for path in os.environ.get('PATH', '').split(':'):
        if os.path.exists(os.path.join(path, program)) and \
                not os.path.isdir(os.path.join(path, program)):
            return os.path.join(path, program)
    return None


# Check if system has the required utilities: ftsb_redisearch, etc
def required_utilities(utility_list):
    result = 1
    for index in utility_list:
        if whereis(index) == None:
            print('Cannot locate ' + index + ' in path!')
            result = 0
    return result


def decompress_file(compressed_filename, uncompressed_filename):
    if compressed_filename.endswith(".zip"):
        with ZipFile(compressed_filename, 'r') as zipObj:
            zipObj.extractall()

    elif compressed_filename.endswith("tar.gz"):
        tar = tarfile.open(compressed_filename, "r:gz")
        tar.extractall()
        tar.close()

    elif compressed_filename.endswith("tar"):
        tar = tarfile.open(compressed_filename, "r:")
        tar.extractall()
        tar.close()


def findJsonPath(element, json):
    return reduce(operator.getitem, element.split('.'), json)


def ts_milli(at_dt):
    return int((at_dt - dt.datetime(1970, 1, 1)).total_seconds() * 1000)


def retrieve_local_or_remote_input_json(config_filename, local_path, option_name):
    benchmark_config = None
    if config_filename.startswith("http"):
        print("retrieving benchmark config file from remote url {}".format(config_filename))
        r = requests.get(config_filename)
        benchmark_config = r.json()
        remote_filename = config_filename[config_filename.rfind('/') + 1:]
        local_config_file = "{}/{}".format(local_path, remote_filename)
        open(local_config_file, 'wb').write(r.content)
        print("To avoid fetching again the config file use the option {option_name} {filename}".format(
            option_name=option_name,
            filename=local_config_file))
    else:
        with open(config_filename, "r") as json_file:
            benchmark_config = json.load(json_file)
    return benchmark_config