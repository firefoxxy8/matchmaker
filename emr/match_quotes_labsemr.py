#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''Match quoted text with document text

	Usage examples:

	python match_quotes_labsemr.py -c matchmaker_mrjob.conf -r emr --no-output -o s3://ithaka-labs/matchmaker/XXXX/matches --work XXXX --plain [true|false] s3://ithaka-labs/matchmaker/XXXX/extracted-quotes/*

'''

from mrjob.job import MRJob
from mrjob.protocol import RawValueProtocol, JSONValueProtocol
import os, sys, traceback, json
sys.path.insert(0, os.getcwd())
sys.path.insert(0, '%s/matchmaker'%os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

from matches import QuoteMatcher

class MatchQuotedText(MRJob):

	OUTPUT_PROTOCOL = JSONValueProtocol

	def configure_options(self):
		super(MatchQuotedText, self).configure_options()
		self.add_file_option('--work', type='str', default='', help='Path to work doc')
		self.add_passthrough_option('--plain', type='str', default='false', help='Source text is plain text')

	def load_options(self, args):
		super(MatchQuotedText, self).load_options(args)
		self.work_filename = self.options.work
		self.plain_text = self.options.plain == 'true'

	def mapper_init(self):
		#sys.stderr.write('work=%s plain=%s\n'%(self.work_filename,self.plain_text))
		work = None
		if self.work_filename and os.path.exists(os.path.join(os.getcwd(),self.work_filename)):
			with open(os.path.join(os.getcwd(),self.work_filename),'r') as work_file:
				work = work_file.read()
			self.quote_matcher = QuoteMatcher(work=work, plain_text=self.plain_text)

	def mapper(self, _, line):
		try:
			self.increment_counter('counters', 'documents_evaluated', 1)
			quotes_data = json.loads(line)
			if quotes_data['quotes']:
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
				yield (None, doc)
				self.increment_counter('reducer2', 'matched_docs', 1)
				if has_high_confidence_match: self.increment_counter('counters', 'high_confidence_docs', 1)
			except:
				self.increment_counter('reducer', 'fail', 1)

if __name__ == '__main__':
	MatchQuotedText.run()