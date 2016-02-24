#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s')
logger = logging.getLogger(__name__)

import os
import sys
import getopt
import traceback
import json
import slumber

DEFAULT_API_HOST = 'https://labs.jstor.org'
FIELDS           = 'article_type,discipline_names,journal,keyterms,_keyterms,keyterm_weights,pubdate,publisher,tags,title,topics,_topics,topic_weights'

class Metadata(object):
	def __init__(self, **kwargs):
		self.verbose             = kwargs.get('verbose', False)
		self.debug               = kwargs.get('debug', False)
		self.api_host            = kwargs.get('api_host', DEFAULT_API_HOST)
		self.api_user            = kwargs.get('api_user', os.environ.get('API_USER'))
		self.api_password        = kwargs.get('api_password', os.environ.get('API_PASSWORD'))
		logger.setLevel(logging.DEBUG if self.debug else logging.INFO if self.verbose else logging.WARNING)

		self.api                 = slumber.API('%s/api/'%self.api_host, auth=(self.api_user, self.api_password))

	def _get_metadata(self, docid):
		try:
			metadata = self.api.metadata(docid).get(fields=FIELDS)
		except KeyboardInterrupt:
			logger.info(traceback.format_exc())
		except:
			metadata = {}
		return metadata

	def add_metadata(self, obj):
		metadata = self._get_metadata(obj['id'])
		logger.info('id=%s has_metadata=%s'%(obj['id'],metadata is not None))
		if metadata:
			if 'pubdate' in metadata:
				metadata['pubdate'] = '%s-%s-%s'%(metadata['pubdate'][:4],metadata['pubdate'][4:6],metadata['pubdate'][6:8])
				metadata['pubyear'] = int(metadata['pubdate'][:4])
			if 'discipline_names' in metadata:
				metadata['disciplines'] = metadata['discipline_names']
				del metadata['disciplines']
			obj.update(metadata)
		return obj

def deserialize(s):
	try:
		return json.loads(s)
	except:
		return eval(s)

def usage():
	print(('%s [hvd:a:u:p:]' % sys.argv[0]))
	print('   -h --help            Print help message')
	print('   -v --verbose         Verbose output')
	print('   -d --debug           Debug output')
	print('   -a --api             API host (%s)'%DEFAULT_API_HOST)
	print('   -u --user            API user (%s)'%os.environ.get('API_USER'))
	print('   -p --password        API password')

if __name__ == '__main__':
	kwargs = {}
	try:
		opts, works = getopt.getopt(sys.argv[1:], 'hvd:a:u:p:', ['help', 'verbose', 'debug', 'api', 'user', 'password'])
	except getopt.GetoptError as err:
		# print help information and exit:
		print(str(err)) # will print something like "option -a not recognized"
		usage()
		sys.exit(2)

	for o, a in opts:
		if o in ('-v', '--verbose'):
			kwargs['verbose'] = True
		elif o in ('-d', '--debug'):
			kwargs['debug'] = True
		elif o in ('-a', '--api'):
			kwargs['api_host'] = a
		elif o in ('-u', '--user'):
			kwargs['api_user'] = a
		elif o in ('-p', '--password'):
			kwargs['api_password'] = a
		elif o in ('-h', '--help'):
			usage()
			sys.exit()
		else:
			assert False, "unhandled option"

	metadata = Metadata(**kwargs)
	for lineno, line in enumerate(sys.stdin):
		try:
			sys.stdout.write('%s\n'%(json.dumps(metadata.add_metadata(deserialize(line)), sort_keys=True)))
		except:
			logger.debug(traceback.format_exc())
			logger.debug('line=%s'%lineno)