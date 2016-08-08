#!/usr/bin/env python

import os, sys, re

p = re.compile('(\s*\<.*\>\s*|\s*\{.*\}\s*)')

if __name__ == '__main__':
    for line in sys.stdin:
        #tokens = line.strip().split('{')[0].split()
        tokens = line.strip().split()
        if len(tokens) >= 3:
            chunkId = '-'.join(tokens[:2]).lower()
            #text = ' '.join(tokens[2:]).replace('[','<i>').replace(']','</i>')
            text = ' '.join(tokens[2:]).replace('[','').replace(']','')
            text = p.sub('', text)
            print('<p id="%s">%s</p>\n' % (chunkId, text))