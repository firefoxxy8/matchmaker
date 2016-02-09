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
import math

BASE_DIR = os.path.dirname(os.path.abspath(os.path.dirname(os.path.realpath(__file__))))
sys.path.append(BASE_DIR)

from labs_core.db import KyotocabinetDatabase as DB
from labs_core.solr import SOLR

LOCAL_METADATA_CACHE_DB  = 'matchmaker-metadata'

class Metadata(object):
	def __init__(self, **kwargs):
		self.verbose             = kwargs.get('verbose', False)
		self.debug               = kwargs.get('debug', False)
		logger.setLevel(logging.DEBUG if self.debug else logging.INFO if self.verbose else logging.WARNING)

		self.update              = kwargs.get('update', False)

		self.metadata_cache      = DB(name=LOCAL_METADATA_CACHE_DB)
		self.metadata_db         = DB(name='metadata')
		self.keyterms_db         = DB(name='terms-tfidf')
		self.topics_db           = DB(name='topics')

		self.solr_host           = kwargs.get('solr_host', os.environ.get('SOLR_HOST'))
		self.solr_core           = kwargs.get('solr_core', os.environ.get('SOLR_CORE'))
		self.solr_user           = kwargs.get('solr_user', os.environ.get('SOLR_USER'))
		self.solr_password       = kwargs.get('solr_password', os.environ.get('SOLR_PASSWORD'))
		self.solr                = SOLR(server=self.solr_host, core=self.solr_core, user=self.solr_user, password=self.solr_password, verbose=self.debug)

		self.updated             = set()

	def _get_keyterms(self, docid):
		values = []
		weight_strs = []
		weighted_values = []
		try:
			obj = json.loads(self.keyterms_db.get(docid))
			logger.debug(json.dumps(obj,sort_keys=True,indent=2))
			#keyterms = [term['term'] for term in obj['terms']]
			terms = obj['terms']
			weight_sum = sum([v['tfidf'] for v in terms])
			for term in terms:
				label = term['term']
				tweight = term['tfidf']
				weight = int(math.ceil(tweight / weight_sum * 50.0))
				if weight >= 1.0:
					values.append(label)
					weight_strs.append('%s^%s'%(label,weight))
					for i in range(weight):
						weighted_values.append(label)
		except:
			logger.debug(traceback.format_exc())
		return values, weighted_values, '|'.join(sorted(weight_strs))

	def _get_topics(self, docid):
		values = []
		weight_strs = []
		weighted_values = []
		try:
			obj = json.loads(self.topics_db.get(docid))
			logger.debug(json.dumps(obj,sort_keys=True,indent=2))
			#topics = [topic[0].replace('_',' ') for topic in obj.get('topic_models',{}).get('llda',[])]
			topics = obj.get('topic_models',{}).get('llda',[])
			weight_sum = sum([v[1] for v in topics])
			for topic in topics:
				label = topic[0].replace('_',' ')
				tweight = topic[1]
				weight = int(math.ceil(tweight / weight_sum * 50.0))
				if weight >= 1.0:
					values.append(label)
					weight_strs.append('%s^%s'%(label,weight))
					for i in range(weight):
						weighted_values.append(label)
		except:
			logger.debug(traceback.format_exc())
		return values, weighted_values, '|'.join(sorted(weight_strs))

	def _get_metadata(self, docid):
		try:
			metadata = json.loads(self.metadata_cache.get(docid))
		except KeyboardInterrupt:
			logger.info(traceback.format_exc())
			raise
		except:
			metadata = {}
		if (not metadata) or (self.update and not docid in self.updated):
			logger.debug('updating cache for %s'%docid)
			try:
				meta_source = json.loads(self.metadata_db.get(docid))

				#meta_source = json.loads(S3().get(docid, folder='files/base'))
				logger.debug(json.dumps(meta_source,sort_keys=True,indent=2))

				if meta_source:
					metadata.update(dict([(k,meta_source[k]) for k in ('article_type','authors','disciplines','journal','title') if k in meta_source]))
					if 'publisher_name' in meta_source: metadata['publisher'] = meta_source['publisher_name']
					if 'pubdate' in meta_source: metadata['pubdate'] = meta_source['pubdate'][0] if isinstance(meta_source['pubdate'],list) else meta_source['pubdate']
					metadata['keyterms'], metadata['_keyterms'], metadata['keyterm_weights'] = self._get_keyterms(docid)
					metadata['topics'], metadata['_topics'], metadata['topic_weights'] = self._get_topics(docid)
					#metadata['page_info'] = self._get_page_info(docid)
					metadata['tags'] = self.solr.get(docid, fields=['tags'], debug=self.debug).get('tags',[])
					self.metadata_cache[docid] = json.dumps(metadata)
					self.updated.add(docid)
			except KeyboardInterrupt:
				raise
			except:
				logger.debug(traceback.format_exc())
				logger.debug(docid)
		return metadata

	def add_metadata(self, obj):
		metadata = self._get_metadata(obj['id'])
		logger.info('docid=%s has_metadata=%s'%(obj['id'],metadata is not None))
		if metadata:
			obj.update(dict([(k,metadata[k]) for k in ('article_type','authors','disciplines','journal','keyterms','_keyterms','keyterm_weights','pubdate','publisher','tags','title','topics','_topics','topic_weights') if k in metadata]))
			if 'pubdate' in obj:
				obj['pubdate'] = obj['pubdate'][:10]
				obj['pubyear'] = int(obj['pubdate'][:4])
		return obj

def deserialize(s):
	try:
		return json.loads(s)
	except:
		return eval(s)

def usage():
	print(('%s [hvdus:c:n:p:]' % sys.argv[0]))
	print('   -h --help            Print help message')
	print('   -v --verbose         Verbose output')
	print('   -d --debug           Debug output')
	print('   -u --update          Update cache')
	print('   -s --solr            SOLR host (%s)'%os.environ.get('SOLR_HOST'))
	print('   -c --core            SOLR core (%s)'%os.environ.get('SOLR_CORE'))
	print('   -n --user            SOLR user (%s)'%os.environ.get('SOLR_USER'))
	print('   -p --password        SOLR password (%s)'%os.environ.get('SOLR_PASSWORD'))

if __name__ == '__main__':
	kwargs = {}
	try:
		opts, works = getopt.getopt(sys.argv[1:], 'hvdus:c:n:p:', ['help', 'verbose', 'debug', 'update', 'solr', 'core', 'user', 'password'])
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
		elif o in ('-u', '--update'):
			kwargs['update'] = True
		elif o in ('-s', '--solr'):
			kwargs['solr_host'] = a
		elif o in ('-c', '--core'):
			kwargs['solr_core'] = a
		elif o in ('-n', '--user'):
			kwargs['solr_user'] = a
		elif o in ('-p', '--password'):
			kwargs['solr_password'] = a
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