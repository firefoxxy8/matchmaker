#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

import os, sys, json, re, traceback, getopt
import Levenshtein
import bs4
from bs4 import BeautifulSoup
from copy import deepcopy

#import textile
from markdown2 import Markdown

rex = re.compile(r'\W+')
whitespace_regex = re.compile('\s+')

def normalize(s):
	return whitespace_regex.sub(' ',s).lower().strip()

ws = set([u'\n',u'\r',u'\t',u' ',u'\f'])

def prep_text(indata, combine=False):
	if isinstance(indata,str): indata = unicode(indata,'utf-8')

	def _parse(elem, ids, text_chunks, id_seqs):
		for child in elem.children:
			if isinstance(child, bs4.element.NavigableString):
				text = child.string.strip()
				if text:
					expanded_ids = []
					for id in ids:
						expanded_ids.append('%s%s'%(id,'' if id_seqs[id] == 0 else '_%s'%id_seqs[id]))
						id_seqs[id] = id_seqs[id]+1
					text_chunks.append([expanded_ids, text])
			elif isinstance(child, bs4.element.Tag) and \
							'nomatch' not in child.attrs.get('class',[]) and\
							child.name in ('p', 'span'):

				chunk_id = child.attrs['id'] if 'id' in child.attrs else 'p%s'%(len(id_seqs)+1)
				id_seqs[chunk_id] = 0
				_parse(child, deepcopy(ids)+[chunk_id], text_chunks, id_seqs)

	text = u'\n'.join([l.rstrip() for l in indata.split(u'\n')])
	#html = textile.textile(text)
	#sys.stderr.write(html+'\n')
	html = Markdown().convert(text)
	#sys.stderr.write(html+'\n')
	if combine: html = html.replace(u'<br />','')
	text_chunks = []

	_parse(BeautifulSoup(html, 'html.parser'), [], text_chunks, {})

	original_text = u' '.join([tc[1] for tc in text_chunks])

	normalized_text = []
	pos_map = []
	pos = 0
	chunks = {}
	for rec in text_chunks:
		chunk_ids = rec[0]
		text_chunk = rec[1]
		normalized_chunk = []
		chunk_offset = 0
		for char in text_chunk:
			pos += 1
			if char in ws and (len(normalized_chunk) == 0 or normalized_chunk[-1] == u' '): continue
			if char in ws or char.isalnum():
				normalized_chunk.append(u' ' if char in ws else char.lower())
				pos_map.append([pos-1,chunk_ids,chunk_offset])
			chunk_offset += 1
		if normalized_chunk:
			if not normalized_chunk[-1] == u' ':
				normalized_chunk.append(u' ')
				pos_map.append([pos,chunk_ids,chunk_offset])
			normalized_text.append(u''.join(normalized_chunk))
		normalized_chunk = u''.join(normalized_chunk).strip()
		for chunk_id in chunk_ids:
			chunks[chunk_id] = normalized_chunk
		pos += 1
	return original_text, u''.join(normalized_text), pos_map, chunks

def find_best_match(original_text, normalized_text, pos_map, quote):
	text_size = len(normalized_text)
	quote = u''.join([c for c in normalize(quote) if c.isalnum() or c in ws])
	qlen = len(quote)
	min_distance = None
	start_pos = end_pos = None
	for i in range(0, text_size-qlen):
		try:
			dist = Levenshtein.distance(quote, normalized_text[i:i+qlen])
			if min_distance is None or dist < min_distance:
				min_distance = dist
				start_pos = i
				end_pos = i+qlen
				if min_distance == 0: break
		except KeyboardInterrupt:
			raise
		except:
			print >> sys.stderr, traceback.format_exc()

	similarity_score = 1.0 - (min_distance/float(qlen) if min_distance > 0 else 0)
	chunk_ids = []
	for pos in range(start_pos,end_pos+1):
		if original_text[pos] not in ws:
			chunk_id = pos_map[pos][1]
			if not chunk_id in chunk_ids: chunk_ids.append(pos_map[pos][1])
	return round(similarity_score,3), pos_map[start_pos][0], pos_map[end_pos][0], chunk_ids, pos_map[start_pos][2], pos_map[end_pos][2]

class QuoteMatcher(object):

	def __init__(self, **kwargs):
		self.verbose        = kwargs.get('verbose', False)
		self.debug          = kwargs.get('debug', False)
		if self.verbose:    logger.setLevel(logging.INFO)
		if self.debug:      logger.setLevel(logging.DEBUG)
		self.work_path      = kwargs.get('work_path')
		self.work           = kwargs.get('work')
		self.combine        = kwargs.get('combine', False)

		logger.info('work_path=%s combine=%s'%(self.work_path, self.combine))

		if self.work_path and os.path.exists(self.work_path):
			with open(self.work_path,'rb') as work_file:
				self.work = work_file.read()
		self.original_text, self.normalized_text, self.pos_map, self.chunks = prep_text(self.work, self.combine)

	def match_quote(self, quote):
		try:
			if quote['source'] in ('named_passage_inline_plain', 'named_passage_inline_coords'):
				return True
			else:
				quoted_text = quote['quoted_text']
				if not isinstance(quoted_text,unicode): quoted_text = unicode(quoted_text,'utf-8')
				quoted_text = quoted_text\
								.replace(u'\n',u' ')\
								.replace(u'- ',u'')\
								.replace(u' . . .',u'')\
								.replace(u'. . .',u'')\
								.replace(u'...',u'')
				quoted_text =  whitespace_regex.sub(u' ',quoted_text).strip()
				qlen = len(quoted_text)
				if qlen >= 15:
					similarity, start_pos, end_pos, chunk_ids, first_chunk_offset, last_chunk_offset = find_best_match(self.original_text, self.normalized_text, self.pos_map, quoted_text[:30])
					if similarity >= 0.7:
						if qlen > 30:
							similarity, start_pos, end_pos, chunk_ids, first_chunk_offset, last_chunk_offset = find_best_match(self.original_text, self.normalized_text, self.pos_map, quoted_text[:500])
							if similarity >= 0.7:
								quote['matched_text'] = self.original_text[start_pos:end_pos]
								quote['chunk_ids'] = chunk_ids
								quote['first_chunk_offset'] = first_chunk_offset
								quote['last_chunk_offset'] = last_chunk_offset
								quote['similarity'] = similarity
								quote['work_start_pos'] = start_pos
								quote['work_end_pos'] = end_pos
								quote['work_exact'] = self.original_text[start_pos:end_pos]
								quote['work_prefix'] = self.original_text[start_pos-32 if start_pos>32 else 0:start_pos]
								quote['work_suffix'] = self.original_text[end_pos+1:end_pos+32]
								return True
						else:
							quote['matched_text'] = self.original_text[start_pos:end_pos]
							quote['chunk_ids'] = chunk_ids
							quote['first_chunk_offset'] = first_chunk_offset
							quote['last_chunk_offset'] = last_chunk_offset
							quote['similarity'] = similarity
							quote['work_start_pos'] = start_pos
							quote['work_end_pos'] = end_pos
							quote['work_exact'] = self.original_text[start_pos:end_pos]
							quote['work_prefix'] = self.original_text[start_pos-32 if start_pos>32 else 0:start_pos]
							quote['work_suffix'] = self.original_text[end_pos+1:end_pos+32]
							return True
		except KeyboardInterrupt:
			raise
		except:
			sys.stderr.write(traceback.format_exc()+'\n')
			sys.stderr.write('%s\n'%id)
			#raise
		return False


def usage():
	print(' %s [hvdw:c]' % sys.argv[0])
	print('   -h --help           Print help message')
	print('   -v --verbose        Info logging output')
	print('   -d --debug          Debug logging output')
	print('   -w --work           Path to work file')
	print('   -c --combine        Combine adjacent lines into singleparagraph')

if __name__ == '__main__':
	kwargs = {}
	try:
		opts, docids = getopt.getopt(sys.argv[1:], 'hvdw:c', ['help','verbose','debug','work','combine'])
	except getopt.GetoptError as err:
		# print help information and exit:
		print(str(err)) # will print something like "option -a not recognized"
		usage()
		sys.exit(2)

	for o, a in opts:
		if o in ("-v", "--verbose"):
			kwargs['verbose'] = True
		elif o in ("-d", "--debug"):
			kwargs['debug'] = True
		elif o in ("-w", "--work"):
			kwargs['work_path'] = a
		elif o in ("-c", "--combine"):
			kwargs['combine'] = True
		elif o in ("-h", "--help"):
			usage()
			sys.exit()
		else:
			assert False, "unhandled option"

	quote_matcher = QuoteMatcher(**kwargs)
	for line in sys.stdin:
		quote = json.loads(line)
		if quote_matcher.match_quote(quote):
			sys.stdout.write('%s\n'%(json.dumps(quote,sort_keys=True)))