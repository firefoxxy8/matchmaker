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
import hashlib
from copy import deepcopy

BASE_DIR = os.path.dirname(os.path.abspath(os.path.dirname(os.path.realpath(__file__))))
sys.path.append(BASE_DIR)

from labs_core.solr import SOLR

DEFAULT_MIN_SIMILARITY   = 0.6

class Indexer(object):
	def __init__(self, **kwargs):
		self.verbose             = kwargs.get('verbose', False)
		self.debug               = kwargs.get('debug', False)
		self.logger              = kwargs.get('logger')
		logger.setLevel(logging.DEBUG if self.debug else logging.INFO if self.verbose else logging.WARNING)
		self.dryrun              = kwargs.get('dryrun', False)
		self.force               = kwargs.get('force', False)
		self.clean               = kwargs.get('clean', False)
		self.work                = kwargs.get('work')
		self.min_similarity      = float(kwargs.get('min_similarity', DEFAULT_MIN_SIMILARITY))

		self.api_server          = kwargs.get('api_server', os.environ.get('API_HOST'))
		protocol = 'https' if self.api_server in ('labs.jstor.org','labstest.jstor.org') else 'http'
		self.api_endpoint        = '%s://%s/api' % (protocol, self.api_server)
		self.api_client          = slumber.API(self.api_endpoint, auth=(os.environ.get('API_ADMIN_USER'), os.environ.get('API_ADMIN_PASSWORD')))

		self.solr_host           = kwargs.get('solr_server', os.environ.get('SOLR_HOST'))
		self.solr_core           = kwargs.get('solr_core', os.environ.get('SOLR_CORE'))
		self.solr_user           = kwargs.get('solr_user', os.environ.get('SOLR_USER'))
		self.solr_password       = kwargs.get('solr_password', os.environ.get('SOLR_PASSWORD'))
		self.solr                = SOLR(server=self.solr_host, core=self.solr_core, user=self.solr_user, password=self.solr_password, verbose=self.debug)

		self.batch               = []
		self.docs_indexed        = 0

		if self.clean: self._delete_recs(self.work)

		logger.info('Indexer: api_server=%s min_similarity=%s clean=%s force=%s' % (self.api_server, self.min_similarity, self.clean, self.force))

	def expand_chunk_ids(self, doc):
		if 'chunk_ids' in doc:
			expanded = set()
			for cid_list in doc['chunk_ids']:
				for cid in cid_list:
					if 'clause_' in cid: cid = cid[0:cid.find('clause_')+6]
					expanded.add(cid)
					if '-' in cid:
						parts = cid.split('-')
						for i in range(1,len(parts)):
							expanded.add('-'.join(parts[0:i]))
			doc['chunk_ids'] = sorted(expanded)

	def indexable_doc(self, doc, work, version):
		workid = work.replace('_','/',1) if _is_doi(work.replace('_','/',1)) else work

		work_text = doc['matched_text'].strip()
		match_text = doc['quoted_text'].strip()
		match_size = len(work_text.strip())
		if doc['similarity'] >= self.min_similarity and len(doc.get('chunk_ids',[])) > 0:
			pagenums = sorted(set([int(pnum) for pnum in range(doc['pages'][0],doc['pages'][1]+1)]))
			quote_start_pos = int(doc['quote_start_pos']) if 'quote_start_pos' in doc else 0
			quote_id = hashlib.md5(''.join([workid,doc['doi'],str(quote_start_pos)])).hexdigest()
			if version is None: version = ''
			id = hashlib.md5(''.join([str(v) for v in [workid,doc['doi'],version,quote_start_pos]])).hexdigest()
			doc.update({'id'          : id,
						'docid'		  : doc['doi'],
						'match_text'  : match_text,
						'match_size'  : match_size,
						'pages'       : pagenums,
						'work'        : workid,
						'version'     : version,
						'work_text'   : work_text,
						'chunk_ids'   : [cid for cid in doc.get('chunk_ids',[]) if cid is not None],
						'quote_id'    : quote_id,
						})

			if 'quote_snippet' in doc: doc['snippet'] = doc['quote_snippet']
			if 'quote_exact' in doc: doc['match_exact'] = doc['quote_exact']
			if 'quote_prefix' in doc: doc['match_prefix'] = doc['quote_prefix']
			if 'quote_suffix' in doc: doc['match_suffix'] = doc['quote_suffix']
			if 'quote_start_pos' in doc: doc['match_start_pos'] = doc.get('quote_start_pos')
			if 'quote_end_pos' in doc: doc['match_end_pos'] = doc.get('quote_end_pos')
			if 'quote_start_page_pos' in doc: doc['match_start_page_pos'] = doc.get('quote_start_page_pos')

			regions = set()
			for bb in doc.get('bounding_boxes',[]):
				pnum = bb['page']
				image_width = int(bb.get('width',0))
				image_height = int(bb.get('height',0))
				ratio = left = width = top = height = 0
				if image_height > 0 and image_width > 0:
					#ratio = round(image_height/image_width,5)
					left = round(float(bb['bounding_box'][0])/float(image_width),5)
					width = round((float(bb['bounding_box'][1])-float(bb['bounding_box'][0]))/float(image_width),5)
					top = round(float(bb['bounding_box'][2])/float(image_height),5)
					height = round((float(bb['bounding_box'][3])-float(bb['bounding_box'][2]))/float(image_height),5)
					regions.add(' '.join([str(val) for val in [pnum, ratio, left, width, top, height]]))
			doc['regions'] = sorted(regions)

		self.expand_chunk_ids(doc)

		return doc

	def add_to_index(self, retries=1):
		if len(self.batch) > 0:
			attempts = 0
			while attempts <= retries:
				try:
					attempts += 1
					if self.dryrun:
						print(json.dumps(self.batch, sort_keys=True, indent=2))
					else:
						res = self.api_client.matchmaker.post(self.batch)
						self.docs_indexed += len(res)
						logger.info(self.docs_indexed)
						return res
				except:
					if attempts > retries: raise
					self.api_client = slumber.API(self.api_endpoint, auth=(os.environ.get('API_ADMIN_USER'), os.environ.get('API_ADMIN_PASSWORD')))
				finally:
					self.batch = []

	def _delete_recs(self, work):
		docids = [doc['id'] for doc in self.api_client.matchmaker.get(work=work, fields='id', limit=10000)['docs']]
		for ctr, docid in enumerate(docids):
			self.api_client.matchmaker(docid).delete()
			logger.debug('Deleting %s of %s'%(ctr+1, len(docids)))

	def index_data(self, doc, work, version=None):
		try:
			metadata = deepcopy(doc)
			metadata['doi'] = metadata['id']
			del metadata['quotes']

			for quote in doc['quotes']:
				quote.update(metadata)
				self.batch.append(self.indexable_doc(quote, work, version))
				if len(self.batch) >= 200: self.add_to_index()
		except KeyboardInterrupt:
			raise
			#except KeyError:
			#pass
		except:
			logger.warning(traceback.format_exc())
			logger.warning(doc['id'])
			#raise

def _is_doi(arg):
	return arg.count('/') == 1 and len(arg) > 8 and arg[2] == '.' and arg[7] == '/' and arg[0:2].isdigit() and arg[3:7].isdigit()

def usage():
	print(('%s [hvda:cfnm:w:e:] work' % sys.argv[0]))
	print('   -h --help            Print help message')
	print('   -v --verbose         Verbose output')
	print('   -d --debug           Debug output')
	print('   -a --api_server      API Server (%s)'%os.environ.get('API_HOST'))
	print('   -c --clean           Delete existing records')
	print('   -f --force           Force metadata update')
	print('   -n --dryrun          Test mode, no updates applied to index')
	print('   -m --min_similarity  Minimum similarity score (%s)' % DEFAULT_MIN_SIMILARITY)
	print('   -w --work            Work ID')
	print('   -e --version         Work version')

if __name__ == '__main__':
	kwargs = {}
	try:
		opts, works = getopt.getopt(sys.argv[1:], 'hvda:cfnm:w:e:', ['help', 'verbose', 'debug', 'api_server', 'clean', 'force', 'dryrun', 'min_similarity', 'work', 'version'])
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
		elif o in ('-a', '--api_server'):
			kwargs['api_server'] = a
		elif o in ('-c', '--clean'):
			kwargs['clean'] = True
		elif o in ('-f', '--force'):
			kwargs['force'] = a
		elif o in ('-n', '--dryrun'):
			kwargs['dryrun'] = True
		elif o in ('-m', '--min_similarity'):
			kwargs['min_similarity'] = a
		elif o in ('-w', '--work'):
			kwargs['work'] = a
		elif o in ('-e', '--version'):
			kwargs['version'] = a
		elif o in ('-h', '--help'):
			usage()
			sys.exit()
		else:
			assert False, "unhandled option"

	indexer = Indexer(**kwargs)
	for line in sys.stdin:
		work = kwargs.get('work')
		version = kwargs.get('version')
		indexer.index_data(json.loads(line), work, version)
	indexer.add_to_index()
