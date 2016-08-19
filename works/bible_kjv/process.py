#!/usr/bin/env python

import logging
logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

import os, sys, re
import sys, subprocess

basedir = os.path.dirname(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

def _execute(cmd, debug=True):
    logger.debug(cmd+'\n')
    p = subprocess.Popen(cmd, shell=True, bufsize=8096)
    p.wait()

if __name__ == '__main__':
    for line in sys.stdin:
        work = line.strip().split('.')[0].split('/')[0]
        label = work[0] + work[1:].title() if work[0].isdigit() else work.title()
        srcdir = os.path.join(basedir,'works','bible_kjv')
        rawdir = os.path.join(basedir,'works','bible_kjv','raw')
        mddir = os.path.join(basedir,'works','bible_kjv','markdown')
        src = os.path.join(rawdir,'%s.txt'%work)
        mdfile = os.path.join(mddir,'%s.md'%work)
        dest = os.path.join(basedir,'data','bible-%s.json'%work)
        logger.info('basedir=%s work=%s label=%s src=%s mdfile=%s dest=%s process=%s'%(basedir, work, label, src, mdfile, dest, not os.path.exists(dest)))
        emrdir = os.path.join(basedir,'emr')
        if not os.path.exists(dest):
            #_execute('echo "# %s" > %s; echo "" >> %s; cat %s | %s >> %s' % (label, mdfile, mdfile, src, os.path.join(srcdir,'prep.py'), mdfile))
            _execute('cd %s; source /opt/python2/bin/activate; python match_quotes_labsemr.py -c matchmaker_mrjob.conf -r emr --no-output -o s3://ithaka-labs/matchmaker/bible_kjv/matches/%s --work %s s3://ithaka-labs/matchmaker/bible_kjv/extracted-quotes/*; cd %s' % (emrdir, work, mdfile, srcdir))
            _execute('mkdir tmp; aws s3 sync s3://ithaka-labs/matchmaker/bible_kjv/matches/%s/ tmp; aws s3 sync s3://ithaka-labs/matchmaker/bible_kjv/matches/%s/ tmp; cat tmp/part-* > %s; rm -rf tmp' % (work, work, dest))
            _execute('cd ../matchmaker; cat %s | ./metadata.py | ./indexer.py -w bible-%s -v; cd ../emr' % (dest,work))