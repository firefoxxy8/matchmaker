#!/usr/bin/env python

import logging
logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.WARN)

import os, sys, re
from subprocess import Popen, PIPE
import shlex

def execute_external_cmd(cmd):
    """
    Execute the external command and get its exitcode, stdout and stderr.
    """
    logger.debug(cmd)
    args = shlex.split(cmd)
    proc = Popen(args, stdout=PIPE, stderr=PIPE)
    out, err = proc.communicate()
    exitcode = proc.returncode
    return exitcode, out, err

if __name__ == '__main__':
    for line in sys.stdin:
        fields = line.strip().split(',')
        if len(fields) == 2:
            title = fields[0]
            search_expr = fields[1]
            cmd = 'solr -q ty:research-article -l 10 %s' % search_expr
            exitcode, stdout, stderr = execute_external_cmd('solr -q ty:research-article -n %s' % search_expr)
            sys.stderr.write(stdout)

            exitcode, stdout, stderr = execute_external_cmd('solr -q ty:research-article -l 1000000 %s' % search_expr)
            for doi in stdout.split():
                sys.stdout.write(doi+'\n')
