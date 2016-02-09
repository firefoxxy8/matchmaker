#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''Match quoted text with document text

	Usage examples:

	python match_quotes_labsemr.py -c matchmaker_mrjob.conf -r emr --no-output -o s3://ithaka-labs/matchmaker/XXXX/matches --work XXXX --version XXXX --combine [true|false] s3://ithaka-labs/matchmaker/XXXX/extracted-quotes/*

'''

from mrjob.job import MRJob
from mrjob.protocol import RawValueProtocol, JSONValueProtocol
import os, sys, traceback
sys.path.insert(0, os.getcwd())
sys.path.insert(0, '%s/matchmaker'%os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

import requests
from matches import QuoteMatcher

import sys, json, traceback

class MatchQuotedText(MRJob):

	OUTPUT_PROTOCOL = JSONValueProtocol

	def get_work_doc(self, work, version=None):
		try:
			works = requests.get('http://raw.githubusercontent.com/JSTOR-Labs/matchmaker/master/works/index.json').json()
			work = works.get(work)
			if version:
				return requests.get(work['versions'][version]['url']).content
			else: # get default version
				for version in work['versions'].values():
					if version.get('default') == True:
						return requests.get(version['url']).content
				return requests.get(work['versions'].values()[0]['url']).content
		except:
			sys.stderr.write(traceback.format_exc()+'\n')
			return None

	def configure_options(self):
		super(MatchQuotedText, self).configure_options()
		self.add_passthrough_option('--work', type='str', default='', help='Work to process')
		self.add_passthrough_option('--version', type='str', default='', help='Work version to process')
		self.add_passthrough_option('--combine', type='str', default='true', help='Combine adjacent lines')

	def load_options(self, args):
		super(MatchQuotedText, self).load_options(args)
		self.work = self.options.work
		self.version = self.options.version
		self.combine = self.options.combine == 'true'

	def mapper_init(self):
		work = self.get_work_doc(self.work, self.version)
		sys.stderr.write('work=%s version=%s combine=%s len=%s\n'%(self.work,self.version,self.combine,len(work) if work else 0))
		if work:
			self.quote_matcher = QuoteMatcher(work=work, combine=self.combine)

	def mapper(self, _, line):
		try:
			self.increment_counter('counters', 'documents_evaluated', 1)
			quotes_data = json.loads(line)
			for quote in quotes_data['quotes']:
				quote['id'] = quotes_data['id']
				self.increment_counter('counters', 'quotes_evaluated', 1)
				if self.quote_matcher.match_quote(quote):
					self.increment_counter('counters', 'matches', 1)
					if len(quote['matched_text']) >= 20 and quote['similarity'] >= 0.90: self.increment_counter('counters', 'high_confidence_matches', 1)
					yield (quote['id'], quote)
		except KeyboardInterrupt:
			raise
		except:
			self.increment_counter('mapper1', 'fail', 1)
			sys.stderr.write(traceback.format_exc()+'\n')
			sys.stderr.write('%s\n'%id)
			#raise

	def reducer(self, id, quotesgen):
			try:
				has_high_confidence_match = False
				quotes = []
				for q in quotesgen:
					quotes.append(q)
					if q['similarity'] >= 0.90: has_high_confidence_match = True
				doc = {'id': id, 'quotes': quotes}
				#valuestr = json.dumps(doc)
				yield (None, doc)
				self.increment_counter('reducer2', 'matched_docs', 1)
				if has_high_confidence_match: self.increment_counter('counters', 'high_confidence_docs', 1)
			except:
				self.increment_counter('reducer', 'fail', 1)

if __name__ == '__main__':
	MatchQuotedText.run()