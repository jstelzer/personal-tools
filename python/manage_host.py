#!/usr/bin/env python
"""
Module for executing arbitrary code on hosts by name prefix.
"""
import argparse
import boto
import boto.ec2
import itertools
import os
import select
import sys

from contextlib import closing
from collections import namedtuple
# NB: We have no way of distributing ssh pub keys a priori
from paramiko.client import SSHClient
from paramiko.client import AutoAddPolicy

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


Host = namedtuple('Host', ['name', 'address'])


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
    return parser.parse_args()




def get_host_info(args):
    """
    Look up all the matching host info for the specified host groups.
    args -- parsed command line args
    """
    host_info = {}
    filters = {'instance-state-name' : 'running'}
    with closing(boto.ec2.connect_to_region(args.region)) as conn:
        if conn is None:
            raise Exception("No connection to aws!")
        instances = itertools.chain.from_iterable([reservation.instances for
                                                   reservation in conn.get_all_reservations(filters=filters)])
        for inst in itertools.chain(instances):
            for pattern in args.hosts:
                host_info.setdefault(pattern, [])
                if inst.tags.get('Name', '').startswith(pattern):
                    host_info[pattern].append(Host(name=inst.tags.get('Name'),
                                                   address=inst.private_ip_address))
    return host_info


def dump_output(output):
    """Output stream dumper"""
    for line in output:
        print "\t%s" % line


def dump_channel(chan):
    """
    Keyword Arguments:
    chan -- ssh channel
    """
    temp_buffer = ''
    finished = False
    while not finished:
        if chan.recv_ready():
            temp_buffer = "%s%s" % (temp_buffer, chan.recv(1024))
            if temp_buffer.find("\n") > -1:
                tmp = temp_buffer[0:temp_buffer.find("\n")]
                print _color("\t%s" %  tmp, 'yellow')
                temp_buffer = temp_buffer[temp_buffer.find("\n"):len(temp_buffer) + 1]
        finished = chan.exit_status_ready()
    # Last sweep for straggler data that showed up during the race to complete
    # NB: i suppose in theory more than 1k of data could be buffered. Drain it all
    while len(temp_buffer) > 0:
        if temp_buffer.find("\n") > -1:
            tmp = temp_buffer[0:temp_buffer.find("\n")]
            print _color("\t%s" %  tmp.rstrip(), 'yellow')
            temp_buffer = temp_buffer[temp_buffer.find("\n"):len(temp_buffer) + 1]
        before = len(temp_buffer)
        temp_buffer = "%s%s" % (temp_buffer, chan.recv(1024))
        if len(temp_buffer) == before:
            if temp_buffer != "\n":
                print _color("\t%s" % temp_buffer.rstrip(), 'yellow')
            temp_buffer = ''


def _summarize_exit_code(rv):
    if 0 != rv:
        print _color("ERROR: %s" % rv, 'red')
    else:
        print _color("OK", 'green')


def run_remote_command(args, hostgroup_name, hostgroup, command):
    """Run the appropriate command on hosts in a given host group based on
the action being taken"""
    client = SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(AutoAddPolicy())
    ssh_key = None
    host_results = {}
    if args.ssh_key:
        ssh_key = "%s/.ssh/%s" % (os.environ['HOME'], args.ssh_key)
    for host in hostgroup:
        try:
            client.connect(host.address, allow_agent=True, username=os.getenv('USER'))
        except Exception, e:
            print "Error running remote command on (%s:%s) (%s)" % (host.name, host.address, e)
            continue
        print "(%s:%s) => (%s)" % (host.name, host.address, command)
        chan = client.get_transport().open_session()
        chan.set_combine_stderr(True)
        chan.exec_command(command)
        dump_channel(chan)
        rv = chan.recv_exit_status()
        host_results[host.name] = rv
        chan.close()
        client.close()
        _summarize_exit_code(rv)
    return any(host_results.values())


def main():
    """
    Run all the things
    """
    args = parse_arguments()
    if len(args.hosts) < 1:
        print "No hosts found. Did you pass --hosts"
        sys.exit(2)
    command = ' '.join(args.command)
    host_info = get_host_info(args)
    errors = []
    for k, v in host_info.iteritems():
        errors.append(run_remote_command(args, k, v, command))
    if any(errors):
        print "ERRORS DETECTED"
        sys.exit(1)


if __name__ == '__main__':
    main()
