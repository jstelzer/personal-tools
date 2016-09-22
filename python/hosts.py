#!/usr/bin/env python
"""
Display info about aws hosts.
"""
import argparse
import boto3
import os
import sys
from tabulate import tabulate
from collections import namedtuple

COLOR_CODE = {
    "green": 32,
    "red": 31,
    "yellow": 33,
}

def _color(string, color):
    if color:
        return '\x1b[%sm%s\x1b[0m' % (COLOR_CODE[color], string)
    else:
        return string

HOST_ATTRS = ['name', 'private_ip_address', 'public_ip_address', 'availability_zone', 'instance_id']
Host = namedtuple('Host', HOST_ATTRS)


def parse_arguments():
    parser = argparse.ArgumentParser(description='Manage hosts')
    parser.add_argument("--region",
                        dest='region',
                        default='us-east-1',
                        help="AWS region to connect to")
    parser.add_argument('--hosts',
                        nargs='+',
                        default=[],
                        help="Host patterns to match to find nodes.")
    parser.add_argument('--user',
                        dest='user',
                        default=os.environ.get("USER"),
                        help="Username to connect as.")
    parser.add_argument('--ssh-key',
                        dest='ssh_key',
                        default=None,
                        help="SSH key to auth.")
    parser.add_argument('--command',
                        nargs='*',
                        default=[],
                        help="Command strings to run.")
    parser.add_argument("--role",
                        default=None,
                        help='Name of aws role to assume')
    return parser.parse_args()


def _get_tags(tags):
    """Translate the {Name:x, Value:y} crap we get back from aws into a dictionary."""
    if tags is None:
        return {}
    return {x['Key']: x['Value'] for x in tags}

def _build_host(hostname, host_info, h):
    host_info.append(Host(name=hostname,
                          private_ip_address=h.private_ip_address,
                          public_ip_address=h.public_ip_address,
                          availability_zone=h.placement['AvailabilityZone'],
                          instance_id=h.id))


def get_host_info(args):
    """
    Look up all the matching host info for the specified host groups.
    args -- parsed command line args
    """
    host_info = []
    filters = [{'Name' : 'instance-state-name', 'Values': ['running']}]
    svc = None
    if args.role is not None:
        client = boto3.client('sts')
        assumedrole = client.assume_rule(args.role)
        credentials = assumedrole['Credentials']
        svc = boto3.resource('ec2', 'us-east-1',
                             aws_access_key_id = credentials['AccessKeyId'],
                             aws_secret_access_key = credentials['SecretAccessKey'],
                             aws_session_token = credentials['SessionToken'])
    else:
        svc = boto3.resource('ec2', 'us-east-1')
    for h in svc.instances.filter(Filters=filters):
        tags = _get_tags(h.tags)
        hostname = tags.get('Name')
        if len(args.hosts):
            for pattern in args.hosts:
                if tags.get('Name', '').find(pattern) > -1:
                    _build_host(hostname, host_info, h)
        else:
            _build_host(hostname, host_info, h)

    return host_info


def main():
    """
    Run all the things
    """
    args = parse_arguments()
    command = ' '.join(args.command)
    host_info = get_host_info(args)
    table = []
    table.append(HOST_ATTRS)
    for host in host_info:
        table.append([host.__getattribute__(x) for x in HOST_ATTRS])
    print tabulate(table, headers='firstrow')



if __name__ == '__main__':
    main()
