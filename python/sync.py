#!/usr/bin/env python
import sys
import os
import argparse

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


Example use:

fswatch .| xargs -n 1  ~/bin/sync.py --remote-host 54.160.179.162

"""
class DirSynch(object):
    """Synchronize a project to the home directory of a remote server"""
    def __init__(self, remote_addr, files):
        '''Sync a directory to a given host'''
        self.remote_addr = remote_addr
        self.files = files

    def sync_dir(self, dir_name):
        """Synch the directory.  Please note: if you are on a mac and the
        remote is linux, if you use --delete to keep things
        pedantically in synch, you will nuke your venv every single
        time you save a file.
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
                # This file is updated every time you move around the dir in a shell.
                if line.endswith(".git/index.lock"):
                    continue
                # This subdir is bullshit.
                if -1 != line.rfind("/.venv/"):
                    continue
                filename = line.split(SOURCE_DIR)[1]
                changed_root = filename.split("/")[0]
                changed_files.append(filename)
            if len(changed_files):
                print "Need to sync {root} due to {files}".format(root=changed_root,
                                                                  files=changed_files)
                self.sync_dir(changed_root)

if "__main__" == __name__:
    parser = argparse.ArgumentParser(description='Sync directory to remote host')
    parser.add_argument('--remote-host', help='host to sync to')
    args, files = parser.parse_known_args()
    runner = DirSynch(args.remote_host, files)
    sys.exit(runner.main())
