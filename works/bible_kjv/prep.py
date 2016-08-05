#!/usr/bin/env python

import os, sys

if __name__ == '__main__':
    for line in sys.stdin:
        tokens = line.strip().split('{')[0].split()
        if len(tokens) >= 3:
            chunkId = '-'.join(tokens[:2]).lower()
            text = ' '.join(tokens[2:]).replace('[','<i>').replace(']','</i>')
            print('<p id="%s">%s</p>\n' % (chunkId, text))