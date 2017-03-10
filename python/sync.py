#!/usr/bin/env python
import sys
import os
import argparse
import datetime
import time
import select
import paramiko

from contextlib import closing
from paramiko.client import AutoAddPolicy
from paramiko.client import SSHClient
from subprocess import call

SOURCE_DIR="{home}/projects/".format(home=os.environ.get("HOME"))

"""I got really sick of uploading code to linux boxes to test it out. Vagrant helps, but sometimes  you just need a dev box in aws.

So, develop locally and every time you save a file, this tool will rsync it up to your remote.

This assumes a few things.

* I assume you stick your code in $HOME/projects/
* I assume you want $HOME/projects/foo to end up in you@remote:/home/you/foo/
* I assume you want to ignore a .venv dir at the project root.
* I assume you have ssh keys or this is going to suck.
* I assume you use inotify or fswatch or some other simlar tool to detect filesystem change.
* You may add a post-sync command if needed.

Example use:

fswatch .|  ~/bin/sync.py --remote-host 54.160.179.162 --post-sync /usr/local/bin/restart-services.sh

"""
class DirSync(object):
    """Synchronize a project to the home directory of a remote server"""
    def __init__(self, remote_addr, files):
        '''Sync a directory to a given host'''
        self.remote_addr = remote_addr
        self.files = files

    def sync_dir(self, dir_name):
        """Synch the directory.

        Please note: I'm ignoring dir_name/.venv because that's
        usually a mac locally and linux remotely in my case.

        """
        cmd = ['rsync', '-av', '--delete', '--exclude', '.venv', "{root}/{target_dir}".format(root=SOURCE_DIR,
                                                                        target_dir=dir_name),
               "{address}:".format(address=self.remote_addr)]
        rv = call(cmd)
        if 0 != rv:
            print "Error returned: {rv}".format(rv=rv)


    def main(self):
        if len(self.files) > 0:
            changed_files = []
            for line in self.files:
                # Ignore changes in .git. only update when live files change.
                if -1 != line.rfind("/.git/"):
                    continue
                # This subdir is bullshit.
                if -1 != line.rfind("/.venv/"):
                    continue
                filename = line.split(SOURCE_DIR)[1]
                changed_root = filename.split("/")[0]
                changed_files.append(filename)
            if len(changed_files):
                #print "Need to sync {root} due to {files}".format(root=changed_root,
                #                                                  files=changed_files)
                self.sync_dir(changed_root)

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
    # # NB: i suppose in theory more than 1k of data could be buffered. Drain it all
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


if "__main__" == __name__:
    parser = argparse.ArgumentParser(description='Sync directory to remote host')
    parser.add_argument('--remote-host', help='host to sync to')
    parser.add_argument("--post-sync", help="Command to execute on remote host post-sync")
    args  = parser.parse_args()
    # Queue date math. Only synch at some reasonable interval.
    # roll up updates over say 5 seconds so git checkouts don't dogpile
    files = []
    t0 = datetime.datetime.now()
    while True:
        while sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            line = sys.stdin.readline()
            files.append(line)
        size = len(files)
        if size:
            now = datetime.datetime.now()
            delta = now - t0
            if 5.0 < delta.total_seconds():
                runner = DirSync(args.remote_host, files)
                runner.main()
                if args.post_sync:
                    print "Running ({cmd})".format(cmd=args.post_sync)
                    with closing(SSHClient()) as client:
                        client.load_system_host_keys()
                        client.set_missing_host_key_policy(AutoAddPolicy())
                        print "Attempting to connect"
                        client.connect(args.remote_host, allow_agent=True, username=os.getenv('USER'))
                        print "Connected"
                        with closing(client.get_transport().open_session()) as chan:
                            chan.set_combine_stderr(True)
                            chan.exec_command(args.post_sync)
                            dump_channel(chan)
                            rv = chan.recv_exit_status()
                            print "Remote command exited with {rv}".format(rv=rv)
                        print "Done executing command"
                files = []
                t0 = datetime.datetime.now()
        # yeild a little or we just chew cpu in a tight loop and kill battery.
        time.sleep(0.25)

    sys.exit(0)
