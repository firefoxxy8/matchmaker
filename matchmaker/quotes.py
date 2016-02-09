#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s')
logger = logging.getLogger()

import os, sys, re, getopt, traceback

import json
import Levenshtein

#quoted_text_regex = re.compile('[ \']"([^"]*)"')
quoted_text_regex = re.compile('"([^"]*)"')
snippet_size = 500

def calc_line_boundingbox(word_bounding_boxes):
	all_lx = []
	all_rx = []
	all_ty = []
	all_by = []

	if word_bounding_boxes:
		for b in word_bounding_boxes:
			if len(b) >= 4:
				all_lx.append(b[1])
				all_rx.append(b[3])
				all_ty.append(b[0])
				all_by.append(b[2])

		if all_lx and all_rx and all_ty and all_by:
			return (min(all_lx), max(all_rx), min(all_ty), max(all_by))
		else:
			return None
	else:
		return None

def coords_to_plain_pages(coords_pages):
	text_pages = []
	for page in coords_pages:
		if isinstance(page, dict):
			lines = []
			for region in page['regions']:
				for line in region['lines']:
					words = []
					for word in line['words']:
						if word['text']: words.append(word['text'])
					if words: lines.append(' '.join(words))
			text_pages.append('\n'.join(lines))
		else:
			text_pages.append(page)
	return text_pages

def find_running_headers_footers(coord_text_doc, max_lines_to_check=2):
	'''Identifies running headers and footers in OCR pages.'''

	header_footer_lines = {}

	def remove_numeric(tokens):
		return [t for t in tokens if not t.isdigit()]

	def duplicate_lines(pages, lnum, max_edit_distance=0):
		'''Used to find repeating lines in headers and footers.'''
		dups = set()
		for pagenum in range(0, len(pages)):
			for j in range(pagenum+1, len(pages)):
				if len(pages[pagenum]) >= abs(lnum) and len(pages[j]) >= abs(lnum):
					try:
						if max_edit_distance == 0:
							if pages[pagenum][lnum] == pages[j][lnum]:
								dups.update([pagenum,j])
						else:
							if Levenshtein.distance(pages[pagenum][lnum], pages[j][lnum]) <= max_edit_distance:
								dups.update([pagenum,j])
					except:
						pass
		return dups

	complete_pages = [p.split('\n') for p in coords_to_plain_pages(coord_text_doc['coord_text'])]

	lines_to_check = []
	for i in range(len(complete_pages)):
		if len(complete_pages[i]) > max_lines_to_check*2:
			lines_to_check.append(complete_pages[i][:max_lines_to_check] + complete_pages[i][len(complete_pages[i])-max_lines_to_check:])
		else:
			lines_to_check.append(complete_pages[i])

	lines_to_check = [[[t for t in line.split()] for line in page] for page in lines_to_check]
	lines_to_check = [[remove_numeric(line) for line in page] for page in lines_to_check]
	lines_to_check = [[[token.lower() for token in line] for line in page] for page in lines_to_check]
	lines_to_check = [[' '.join(line) for line in page] for page in lines_to_check]

	for i in range(max_lines_to_check):
		for lnum in (i, -(i+1)):
			for pnum in duplicate_lines(lines_to_check, lnum):
				if not pnum in header_footer_lines: header_footer_lines[pnum] = set()
				if lnum < 0:
					header_footer_lines[pnum].add(len(complete_pages[pnum])+lnum)
				else:
					header_footer_lines[pnum].add(lnum)

	return header_footer_lines

def clean_pages(coord_text_doc):
	'''Remove references and running headers/footers from coords doc, if possible.'''

	headers_and_footers = find_running_headers_footers(coord_text_doc)

	refcoords = {}

	# Attempt to infer coord space for reference coord comparison
	max_coord_b = 0
	max_coord_r = 0
	for page in coord_text_doc.get('coord_text',[]):
		for region in page.get('regions',[]):
			for line in region.get('lines',[]):
				for word in line.get('words',[]):
					if len(word['coords']) == 5:
						t,l,b,r,fs = word['coords']
						if b > max_coord_b: max_coord_b = b
						if r > max_coord_r: max_coord_r = r
	coords_scale = 2 if max_coord_b > 6000 or max_coord_r > 4000 else 1

	for rc in coord_text_doc.get('refcoords',[]):
		if not rc['pagenum'] in refcoords: refcoords[rc['pagenum']] = []
		refcoords[rc['pagenum']].append(dict([(k,int(v)) for k,v in list(rc.items())]))

	def is_ref(pagenum, t, l, b, r):
		if not pagenum in refcoords: return False
		is_ref = False
		for rc in refcoords[pagenum]:
			is_ref = (t >= rc['y1']*coords_scale and l >= rc['x1']*coords_scale and b <= rc['y2']*coords_scale and r <= rc['x2']*coords_scale)
			if is_ref: break
		return is_ref

	cleaned_text_pages = []

	for page_seq, page in enumerate(coord_text_doc.get('coord_text',[])):
		cleaned_page = {'pagenum':int(page.get('pagenum',0)), 'height':int(page.get('height',0)), 'width':int(page.get('width',0)), 'res':int(page.get('res',0)), 'regions':[]}
		cleaned_text_pages.append(cleaned_page)
		if isinstance(page,dict):
			line_seq = 0
			pagenum = page.get('pagenum')
			for region in page.get('regions',[]):
				cleaned_region = {'coords':region['coords'], 'lines':[]}
				cleaned_page['regions'].append(cleaned_region)
				for line in region.get('lines',[]):
					if not line_seq in headers_and_footers.get(page_seq,set()):
						cleaned_line = {'coords':line['coords'], 'words':[]}
						cleaned_region['lines'].append(cleaned_line)
						for word in line.get('words',[]):
							if len(word['coords']) == 5:
								t,l,b,r,fs = word['coords']
								if not is_ref(pagenum, t,l,b,r):
									cleaned_line['words'].append(word)
					line_seq += 1
	return cleaned_text_pages

white_space = (' ','\t','\n','\f')
def get_snippet(text, start_pos, end_pos, snippet_size):
	'''
	Get snippet, breaking on word boundaries.
	'''
	exact = text[start_pos:end_pos]

	snippet_start_pos = start_pos - snippet_size if start_pos > snippet_size else 0
	while snippet_start_pos > 0 and text[snippet_start_pos] not in white_space: snippet_start_pos -= 1
	if text[snippet_start_pos] in white_space: snippet_start_pos += 1

	prefix = text[snippet_start_pos : start_pos].replace('- ','')
	#if prefix[-1] == '"': prefix = prefix[0:-1].strip()

	snippet_end_pos = end_pos + snippet_size if (end_pos + snippet_size) < len(text) else len(text)-1
	while snippet_end_pos < len(text)-1 and text[snippet_end_pos] not in white_space: snippet_end_pos += 1
	if text[snippet_end_pos] in white_space: snippet_end_pos -= 1

	suffix = text[end_pos : snippet_end_pos+1].replace('- ','')
	#if suffix[0] == '"': suffix = suffix[1:].strip()

	snippet = '%s<em>%s</em>%s' % (prefix, exact, suffix)
	snippet = snippet.replace('- ','')
	return snippet, exact, prefix, suffix

class QuoteFinder(object):

	def __init__(self, **kwargs):
		self.verbose        = kwargs.get('verbose', False)
		self.debug          = kwargs.get('debug', False)
		self.logger         = kwargs.get('logger')
		if self.verbose:    logger.setLevel(logging.INFO)
		if self.debug:      logger.setLevel(logging.DEBUG)
		self.is_coords      = kwargs.get('coords', False)

		self.named_passages = []

		if kwargs.get('named_passages'):
			for line in kwargs.get('named_passages', '').split('\n'):
				if line:
					fields = line.strip().split('\t')
					self.named_passages.append({
						'passage_id': fields[0],
						'label': fields[1],
						'to_match': [m.strip() for m in fields[2].split('|')],
						'source_ids': [id.strip() for id in fields[3].split('|')]})

		if not self.named_passages and kwargs.get('named_passages_path'):
			named_passage_path = kwargs.get('named_passages_path')
			if os.path.exists(named_passage_path):
				with open(named_passage_path,'rb') as named_passages_file:
					for line in named_passages_file:
						fields = line.strip().split('\t')
						self.named_passages.append({
							'passage_id': fields[0],
							'label': fields[1],
							'to_match': [m.strip() for m in fields[2].split('|')],
							'source_ids': [id.strip() for id in fields[3].split('|')]})

		logger.info('coords=%s named_passages=%s'%(self.is_coords, len(self.named_passages)))

	def __call__(self, input_lines, docid=None):
		logger.info('num_lines=%s'%(len(input_lines)))
		if self.is_coords:
			coords_text_doc = json.loads(' '.join(input_lines))
			for quote in self.quotes_from_coords_doc(coords_text_doc):
				if docid: quote['id'] = docid
				sys.stdout.write('%s\n'%json.dumps(quote,sort_keys=True))
		else:
			pages = [' '.join(input_lines).replace('- ','')]
			for quote in self.quotes_from_plain_doc(pages):
				if docid: quote['id'] = docid
				sys.stdout.write('%s\n'%json.dumps(quote,sort_keys=True))

	def get_inline_named_passages_plain(self, pages):
		'''Get named passages from plain text (no coords).'''
		page_indexes = [0]
		for i, page in enumerate(pages):
			page_indexes.append(page_indexes[i] + len(pages[i]) + 1)

		lines = [line for page in pages for line in page.split('\n')]
		combined_text = ' '.join(' '.join(lines).split()) # join line and collapse white space
		to_search = combined_text.lower()

		matches = []

		for np in self.named_passages:
			for to_match in np['to_match']:
				idx = 0
				while True:
					try:
						idx = to_search.index(to_match.lower(),idx)
						start_pos = idx
						end_pos = idx+len(to_match)
						start_page = min([i+1 for i in range(len(page_indexes)-1) if start_pos < page_indexes[i+1]])
						end_page = min([i+1 for i in range(len(page_indexes)-1) if end_pos < page_indexes[i+1]])
						snippet, exact, prefix, suffix = get_snippet(combined_text, start_pos, end_pos, snippet_size)
						matches.append({'quoted_text':          exact.strip(),
						   				'source':               'named_passage_inline_plain',
						   				'pages':                [start_page,end_page],
						   				'quote_start_pos':      start_pos,
						   				'quote_start_pos':      end_pos,
						   				'quote_start_page_pos': start_pos-page_indexes[start_page-1],
						   				'quote_snippet':        snippet,
						   				'quote_exact':          exact,
						   				'quote_prefix':         prefix,
						   				'quote_suffix':         suffix,
						   				'named_passage_id':     np['passage_id'],
										'chunk_ids':            np['source_ids'],
										'similarity':           1.0,
										'matched_text':			exact.strip()})
						idx = end_pos
					except:
						break
		return matches

	def get_inline_quotes_plain(self, pages):
		'''Get inline quotes from plain text (no coords).'''
		page_indexes = [0]
		for i, page in enumerate(pages):
			page_indexes.append(page_indexes[i] + len(pages[i]) + 1)

		lines = [line for page in pages for line in page.split('\n')]
		combined_text = ' '.join(' '.join(lines).split()) # join line and collapse white space
		quotes = []
		pos = 0
		while True:
			match = quoted_text_regex.search(combined_text, pos)
			if match is None: break
			start_pos = match.start()+1
			end_pos = match.end()-1
			start_page = min([i+1 for i in range(len(page_indexes)-1) if start_pos < page_indexes[i+1]])
			end_page = min([i+1 for i in range(len(page_indexes)-1) if end_pos < page_indexes[i+1]])
			snippet, exact, prefix, suffix = get_snippet(combined_text, start_pos, end_pos, snippet_size)
			quotes.append({'quoted_text':          match.group(1).strip(),
						   'source':               'quote_inline_plain',
						   'pages':                [start_page,end_page],
						   'quote_start_pos':      start_pos,
						   'quote_start_pos':      end_pos,
						   'quote_start_page_pos': start_pos-page_indexes[start_page-1],
						   'quote_snippet':        snippet,
						   'quote_exact':          exact,
						   'quote_prefix':         prefix,
						   'quote_suffix':         suffix,
						   })
			pos = end_pos
		return quotes

	def get_inline_named_passages(self, coords_pages):
		combined_text = ' '.join([line for page in coords_to_plain_pages(coords_pages) for line in page.split('\n')])
		page_num = 0
		running_line_num = 0

		matches = []

		# generate word vector
		work_words = []
		work_data = []
		for page in coords_pages:
			page_num += 1
			page_offset = 0
			if page['regions']:
				page_line_num = 0
				for region in page['regions']:
					for line in region['lines']:
						running_line_num += 1
						page_line_num += 1
						for wnum, word_dict in enumerate(line['words']):
							if word_dict['text']:
								work_words.append(word_dict['text'].lower())
								work_data.append([page_num,running_line_num,page_line_num,page_offset,word_dict['coords']])
								page_offset += len(word_dict['text'])+1

		for np in self.named_passages:
			for tm in np['to_match']:
				to_match = [w.lower() for w in tm.split()]
				idx = 0
				while True:
					try:
						idx = work_words.index(to_match[0],idx)
						if work_words[idx:idx+len(to_match)] == to_match:

							try:
								bounding_boxes = []
								pages = set()
								lines = set()
								line_bounding_boxes = {}
								for widx in range(idx, idx+len(to_match)):
									page_num, running_line_num, page_line_num, page_offset, coords = work_data[widx]
									pages.add(page_num)
									lines.add(running_line_num)
									if not running_line_num in line_bounding_boxes: line_bounding_boxes[running_line_num] = []
									line_bounding_boxes[running_line_num].append(coords)
								for line_key in sorted(line_bounding_boxes):
									bounding_boxes.append({'page': page_num,
												   		   'width':page['width'],
												   		   'height':page['height'],
												   		   'bounding_box': calc_line_boundingbox(line_bounding_boxes[line_key])})

								start_pos = sum([len(w) for w in work_words[0:idx]])+idx
								end_pos = start_pos + sum([len(w) for w in to_match]) + len(to_match)-1
								snippet, exact, prefix, suffix = get_snippet(combined_text, start_pos, end_pos, snippet_size)

								match = {'pages':                (min(pages), max(pages)),
										 'lines':                (min(lines), max(lines)),
										 'quoted_text':          exact.strip(),
										 'source':               'named_passage_inline_coords',
										 'quote_start_pos':      start_pos,
										 'quote_end_pos':        end_pos,
										 'quote_start_page_pos': page_offset,
										 'quote_snippet':        snippet,
										 'quote_exact':          exact,
										 'quote_prefix':         prefix,
										 'quote_suffix':         suffix,
										 'bounding_boxes':       bounding_boxes,
										 'named_passage_id':     np['passage_id'],
										 'chunk_ids':            np['source_ids'],
										 'similarity':           1.0,
										 'matched_text':		 exact.strip()}
								logger.info(json.dumps(match,sort_keys=True,indent=2))
								matches.append(match)
							except:
								logger.warning(traceback.format_exc())
						idx += 1
					except:
						break
		return matches

	def get_inline_quotes(self, coords_pages):
		combined_text = ' '.join([line for page in coords_to_plain_pages(coords_pages) for line in page.split('\n')])
		line_num = 0
		pg = 0
		left_quotation_seen = False
		right_quotation_seen = True
		quoted_text = ''
		quote_first_page = 0
		quote_first_line = 0
		quotes = []
		bounding_boxes = []
		for page in coords_pages:
			start_page_pos = 0
			pg += 1
			if page['regions']:
				for rnum, region in enumerate(page['regions']):

					for lnum, line in enumerate(region['lines']):
						line_num += 1
						added_word_bounding_boxes = []
						word_added = False

						for wnum, word_dict in enumerate(line['words']):
							word = word_dict['text']
							word_added = False

							if word:
								for c in word:
									start_page_pos += 1
									if c == '"' and right_quotation_seen:
										left_quotation_seen = True
										right_quotation_seen = False
										quoted_text = ''
										bounding_boxes = []
										word_added = True
										quote_first_page = pg
										quote_first_line = line_num
										continue

									if left_quotation_seen and not right_quotation_seen:
										if not c == '"': quoted_text += c
										word_added = True

										if (line_num - quote_first_line) >= 4: # if the quotes span 4 or more lines, there is likely an OCR error.
											left_quotation_seen = False
											right_quotation_seen = True
											quoted_text = ''

										if c == '"':
											left_quotation_seen = False
											right_quotation_seen = True
											added_word_bounding_boxes.append(word_dict['coords'])
											bounding_boxes.append({'page': pg,
																   'width':page['width'],
																   'height':page['height'],
																   'bounding_box': calc_line_boundingbox(added_word_bounding_boxes)})

											start_pos = combined_text.find(quoted_text)
											end_pos = start_pos + len(quoted_text)

											snippet, exact, prefix, suffix = get_snippet(combined_text, start_pos, end_pos, snippet_size)
											quotes.append({'pages':               (quote_first_page, pg),
														   'lines':               (quote_first_line, line_num),
														   'quoted_text':          quoted_text.replace('- ','').strip(),
														   'source':              'quote_inline_coords',
														   'quote_start_pos':      start_pos,
														   'quote_end_pos':        end_pos,
														   'quote_start_page_pos': start_page_pos,
														   'quote_snippet':        snippet,
														   'quote_exact':          exact,
														   'quote_prefix':         prefix,
														   'quote_suffix':         suffix,
														   'bounding_boxes':       bounding_boxes})

							quoted_text += ' '
							if word_added:
								added_word_bounding_boxes.append(word_dict['coords'])

						if word_added:
							bounding_boxes.append({'page': pg,
												   'width':page['width'],
												   'height':page['height'],
												   'bounding_box': calc_line_boundingbox(added_word_bounding_boxes)})

		return [quote for quote in quotes if sum([1 for box in quote['bounding_boxes'] if box['bounding_box'] == None]) == 0]

	def get_block_quotes(self, coords_pages):
		combined_text = ' '.join([line for page in coords_to_plain_pages(coords_pages) for line in page.split('\n')])
		pg = 0
		for page in coords_pages:
			pg += 1
			all_left = []
			all_right = []

			for region in page['regions']:
				for line in region['lines']:
					line_left = line['coords'][0]
					line_right = line['coords'][2]
					all_left.append(line_left)
					all_right.append(line_right)

					line_words = []
					for word in line['words']:
						line_words.append(word['text'])

			if all_left and all_right:
				left_threshold = min(all_left) + 100
				right_threshold = max(all_right) - 100

				page['thresholds'] = (left_threshold, right_threshold)

		line_num = 0
		lines = []
		pg = 0
		pos = 0
		page_idx = 0
		for page in coords_pages:
			if pg > 0: pos += 1
			pg += 1
			left_threshold = right_threshold = None
			if 'thresholds' in page:
				left_threshold, right_threshold = page['thresholds']
			if page['regions']:
				for rnum, region in enumerate(page['regions']):
					if rnum > 0: pos += 1
					for lnum, line in enumerate(region['lines']):
						if lnum > 0: pos += 1
						line_num += 1
						line_left = line['coords'][0]
						line_right = line['coords'][2]
						line_words = []
						font_sizes = []

						for wnum, word in enumerate(line['words']):
							if wnum > 0: pos += 1
							if word['text']:
								line_words.append(word['text'])
								pos += len(word['text'])
							fsize = 8
							if len(word['coords']) == 5:
								fsize = word['coords'][4]
							font_sizes.append(fsize)

						avg_font = 10
						if len(font_sizes) != 0:
							avg_font = sum(font_sizes)/len(font_sizes)

						if (left_threshold is not None and line_left >= left_threshold) and (right_threshold is not None and line_right <= right_threshold) and avg_font <= 12 and avg_font >= 9:
							if len(line_words) >= 2:
								word_bounding_boxes = [word_dict['coords'] for word_dict in line['words']]
								start_pos = pos-len(' '.join(line_words))
								start_page_pos = start_pos-page_idx
								lines.append([line_num, ' '.join(line_words), calc_line_boundingbox(word_bounding_boxes), pg, start_pos, start_page_pos, page['height'], page['width']])
			page_idx = pos

		quotes = [] # supposed to be a list of lists
		for line in lines:
			if len(quotes) == 0:
				quotes.append([line])
			else:
				if line[0] == quotes[-1][-1][0] + 1:
					if quotes[-1][-1][1][-1] != ')':
						quotes[-1].append(line)
					else:
						quotes.append([line])
				else:
					quotes.append([line])

		# produce the final output
		final_quotes = []
		for quote in quotes:
			quote_words = ''
			pages = []
			bounding_boxes = []
			line_nums = []

			for line in quote:
				quote_words = quote_words + ' ' + line[1]
				pages.append(line[3])
				line_nums.append(line[0])
				bounding_boxes.append({'page':         line[3],
									   'height':       line[6],
									   'width':        line[7],
									   'bounding_box': line[2]})

			if not quote_words.isupper() and not (max(pages) == 1 and max(line_nums) <= 3):
				#start_pos = quote[0][4]
				start_page_pos = quote[0][5]
				#end_pos = start_pos + len(quote_words.strip())
				quoted_text = quote_words.strip()
				start_pos = combined_text.find(quoted_text)
				end_pos = start_pos + len(quoted_text)
				snippet, exact, prefix, suffix = get_snippet(combined_text, start_pos, end_pos, snippet_size)
				final_quotes.append({'pages':                (min(pages), max(pages)),
									 'lines':                (min(line_nums), max(line_nums)),
									 'quoted_text':          quoted_text,
									 'source':               'quote_block_coords',
									 'quote_start_pos':      start_pos,
									 'quote_end_pos':        end_pos,
									 'quote_start_page_pos': start_page_pos,
									 'quote_snippet':        snippet,
									 'quote_exact':          exact,
									 'quote_prefix':         prefix,
									 'quote_suffix':         suffix,
									 'bounding_boxes':       bounding_boxes})

		return final_quotes

	def quotes_from_coords_doc(self, coords_text_doc):
		coords_pages = clean_pages(coords_text_doc)
		return self.get_inline_quotes(coords_pages) + self.get_block_quotes(coords_pages) + self.get_inline_named_passages(coords_pages)

	def quotes_from_plain_doc(self, pages):
		return self.get_inline_quotes_plain(pages) + self.get_inline_named_passages_plain(pages)

def usage():
	print(' %s [hvdi:cn:]' % sys.argv[0])
	print('   -h --help           Print help message')
	print('   -v --verbose        Info logging output')
	print('   -d --debug          Debug logging output')
	print('   -i --id             Doument ID')
	print('   -c --coords         Input is coordinate OCR')
	print('   -n --named_passages Path to optional file containing named passages to find')

if __name__ == '__main__':
	kwargs = {}
	try:
		opts, docids = getopt.getopt(sys.argv[1:], 'hvdi:cn:', ['help','verbose','debug','id','coords','named_passages'])
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
		elif o in ("-i", "--id"):
			kwargs['id'] = a
		elif o in ("-c", "--coords"):
			kwargs['coords'] = True
		elif o in ("-n", "--named_passages"):
			kwargs['named_passages_path'] = a
		elif o in ("-h", "--help"):
			usage()
			sys.exit()
		else:
			assert False, "unhandled option"

	QuoteFinder(**kwargs)([line for line in sys.stdin],docid=kwargs.get('id'))