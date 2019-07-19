import os
import time
import subprocess
import io
import tarfile
from pathlib import Path
from subprocess import CalledProcessError
import docker
import asyncio
from async_generator import yield_

from .utils import (
    pool_helper, wallet_helper, default_trustee, ensure_pool_is_functional,
    NodeHost
)

import logging
logger = logging.getLogger(__name__)

DOCKER_BUILD_CTX_PATH = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), 'docker', 'node'
)
DOCKER_IMAGE_NAME = os.environ.get('INDY_SYSTEM_TESTS_DOCKER_NAME', 'hyperledger/indy-test-automation:node')
NETWORK_NAME = os.environ.get('INDY_SYSTEM_TESTS_NETWORK', 'indy-test-automation-network')
# TODO limit subnet range to reduce risk of overlapping with system resources
NETWORK_SUBNET = os.environ.get('INDY_SYSTEM_TESTS_SUBNET', '10.0.0.0/24')
NODE_NAME_BASE = 'node'
NODES_NUM = int(os.environ.get('INDY_SYSTEM_NODES_NUM', 7))


client = docker.from_env()


def network_builder(network_subnet, network_name):
    client.networks.prune()

    try:
        client.networks.get(network_name)
        return network_name
    except docker.errors.NotFound:
        ipam_pool = docker.types.IPAMPool(subnet=network_subnet)
        ipam_config = docker.types.IPAMConfig(pool_configs=[ipam_pool])
        return client.networks.create(name=network_name,
                                      ipam=ipam_config).name


def pool_builder(docker_build_ctx_path, node_image_name, node_name_base, network_name, nodes_num):
    try:
        image = client.images.get(node_image_name)
    except docker.errors.ImageNotFound:
        # build image from the Dockerfile
        output = []
        try:
            image, output = client.images.build(path=docker_build_ctx_path, tag=node_image_name)
        except Exception as exc:
            print("Failed to build docker image for Indy Node: {}".format(exc))
            raise
        finally:
            print(
                "Docker build logs ...\n:"
                "=====================\n"
            )
            for line in output:
                print(line)

    # enable systemd
    client.containers.run(image,
                          'setup',
                          remove=True,
                          privileged=True,
                          volumes={'/': {'bind': '/host', 'mode': 'rw'}})
    # run pool containers
    return [client.containers.run(image,
                                  name=node_name_base+str(i),
                                  detach=True,
                                  tty=True,
                                  network=network_name,
                                  volumes={'/sys/fs/cgroup': {'bind': '/sys/fs/cgroup', 'mode': 'ro'}},
                                  security_opt=['seccomp=unconfined'],
                                  tmpfs={'/run': '',
                                         '/run/lock': ''})
            for i in range(1, nodes_num+1)]


def pool_starter(node_containers):
    for node in node_containers:
        node.start()
    return node_containers


def pool_initializer(node_containers):
    ips = []
    for i in range(len(node_containers)):
        ips.append('.'.join(NETWORK_SUBNET.split('/')[0].split('.')[:3] + [str(i + 2)]))
    ips = ','.join(ips)
    init_res = [node.exec_run(['generate_indy_pool_transactions',
                               '--nodes', str(len(node_containers)),
                               '--clients', '1',
                               '--nodeNum', str(i+1),
                               '--ips', ips],
                              user='indy')
                for i, node in enumerate(node_containers)]
    start_res = [node.exec_run(['systemctl', 'start', 'indy-node'], user='root') for node in node_containers]
    assert all([res.exit_code == 0 for res in init_res])
    assert all([res.exit_code == 0 for res in start_res])
    return init_res, start_res


def pool_stop():
    containers = subprocess.check_output([
        'docker', 'ps', '-a', '-q', '-f', "name={}*".format(NODE_NAME_BASE)
    ]).decode().strip().split()
    outputs = [subprocess.check_call(['docker', 'rm', container, '-f']) for container in containers]
    assert outputs is not None
    # Uncomment to destroy all images too
    # images = subprocess.check_output(['docker', 'images', '-q']).decode().strip().split()
    # try:
    #     outputs = [subprocess.check_call(['docker', 'rmi', image, '-f']) for image in images]
    #     assert outputs is not None
    # except CalledProcessError:
    #     pass


def main(nodes_num=None):
    nodes_num = NODES_NUM if nodes_num is None else nodes_num
    print(pool_initializer(
            pool_starter(
                pool_builder(
                    DOCKER_BUILD_CTX_PATH,
                    DOCKER_IMAGE_NAME,
                    NODE_NAME_BASE,
                    network_builder(NETWORK_SUBNET,
                                    NETWORK_NAME),
                    nodes_num))))


async def wait_until_pool_is_ready():
    wallet_handle, _, _ = await wallet_helper()
    trustee_did, _ = await default_trustee(wallet_handle)
    pool_handle, _ = await pool_helper()
    await ensure_pool_is_functional(pool_handle, wallet_handle, trustee_did)



def gather_logs(nodes_num, target_dir):
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    tmp_tar =  target_dir / 'tmp.tar'

    hosts = [NodeHost(node_id + 1) for node_id in range(nodes_num)]

    try:
        for host in hosts:
            logs_path = host.generate_logs()
            bits, stat = client.containers.get(host.name).get_archive(logs_path)
            with open(str(tmp_tar), 'w+b') as f:
                for chunk in bits:
                    f.write(chunk)

            with tarfile.open(str(tmp_tar)) as tar:
                tar.extractall(str(target_dir))
    finally:
        if tmp_tar.exists():
            tmp_tar.unlink()


async def setup(nodes_num):
    pool_stop()

    main(nodes_num=nodes_num)
    await wait_until_pool_is_ready()
    logger.info('DOCKER SETUP HAS BEEN FINISHED!')


def teardown(nodes_num, nodes_logs_dir=None):
    try:
        if nodes_logs_dir:
            gather_logs(nodes_num, nodes_logs_dir)
    finally:
        pool_stop()
        logger.info('DOCKER TEARDOWN HAS BEEN FINISHED!\n')

if __name__ == '__main__':
    main()
