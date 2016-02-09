'''
	EMR job that extracts inline and block quotes from JSTOR documents with text coordinates.

	Run example:  python extract_quotes_labsemr.py -c matchmaker_mrjob.conf -r emr --work XXXX --version XXXX --no-output s3://ithaka-labs/matchmaker/XXXX/docids -o s3://ithaka-labs/matchmaker/XXXX/extracted-quotes

'''

from mrjob.job import MRJob
import mrjob.protocol
import os, sys, traceback
basedir = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.getcwd())
sys.path.insert(0, '%s/matchmaker'%basedir)

from quotes import QuoteFinder
import botocore.session
import requests
import json

class Job(MRJob):
	OUTPUT_PROTOCOL = mrjob.protocol.JSONValueProtocol

	def get_named_passages_text(self, work, version=None):
		try:
			works = requests.get('https://raw.githubusercontent.com/JSTOR-Labs/matchmaker/master/works/index.json').json()
			work = works.get(work)
			if version and 'named_passages_url' in work['versions'][version]:
				return requests.get(work['versions'][version]['named_passages_url']).content
			else: # get default version
				for version in work['versions'].values():
					if version.get('default') == True and 'named_passages_url' in version:
						return requests.get(version['named_passages_url']).content
				if 'named_passages_url' in work['versions'].values()[0]:
					return requests.get(work['versions'].values()[0]['named_passages_url']).content
		except:
			sys.stderr.write(traceback.format_exc()+'\n')
		return None

	def configure_options(self):
		super(Job, self).configure_options()
		self.add_passthrough_option('--work', type='str', default='', help='Work to process')
		self.add_passthrough_option('--version', type='str', default='', help='Work version to process')

	def load_options(self, args):
		super(Job, self).load_options(args)
		self.work = self.options.work
		self.version = self.options.version

	def mapper_init(self):
		try:
			self.named_passages_text = self.get_named_passages_text(self.work, self.version)
			session = botocore.session.get_session()
			aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
			aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
			if aws_access_key_id == None:
				aws_access_key_id, aws_secret_access_key = self._get_s3_credentials()
			session.set_credentials(aws_access_key_id,aws_secret_access_key)
			self.s3_client = session.create_client('s3', region_name='us-east-1')
		except:
			sys.stderr.write(traceback.format_exc()+'\n')
			#raise

	def mapper(self, key, docid):
		self.increment_counter('counters', 'all_docs', 1)
		try_plain = True
		try:
			response_data = self.s3_client.get_object(Bucket='ithaka-labs', Key='files/coord-text/%s'%(docid))
			if response_data['ResponseMetadata']['HTTPStatusCode'] == 200 and response_data:
				serialized_doc = response_data['Body'].read()
				if serialized_doc:
					coords_text_doc = json.loads(serialized_doc)
					quotes = QuoteFinder(is_coords=True, named_passages=self.named_passages_text).quotes_from_coords_doc(coords_text_doc)
					try_plain = False
					self.increment_counter('counters', 'coords_docs', 1)
					self.increment_counter('counters', 'coords_quotes', len(quotes))
					if quotes:
						yield key, {'id': docid, 'quotes': quotes}
		except:
			self.increment_counter('counters', 'failed_coords_doc', 1)
			sys.stderr.write(traceback.format_exc())
			sys.stderr.write(docid)
			#raise

		if try_plain:
			try:
				response_data = self.s3_client.get_object(Bucket='ithaka-labs', Key='files/text/%s'%(docid))
				if response_data['ResponseMetadata']['HTTPStatusCode'] == 200 and response_data:
					serialized_doc = response_data['Body'].read()
					if serialized_doc:
						text_doc = json.loads(serialized_doc)
						quotes = QuoteFinder(is_coords=False).quotes_from_plain_doc(text_doc['text'])
						self.increment_counter('counters', 'plain_docs', 1)
						self.increment_counter('counters', 'plain_quotes', len(quotes))
						if quotes:
							yield key, {'id': docid, 'quotes': quotes}
			except:
				self.increment_counter('counters', 'failed_processing', 1)
				sys.stderr.write(traceback.format_exc())
				sys.stderr.write(docid)

	def _get_s3_credentials(self):
		'''Get S3 credentials from credentials file.  Assumes credentials are stored in format used by
		AWS CLI tool (http://aws.amazon.com/cli/).'''
		aws_access_key_id = None
		aws_secret_access_key = None
		for aws_credentials_path in [os.path.join(os.getcwd(),'credentials'),]:
			if os.path.exists(aws_credentials_path):
				with open (aws_credentials_path, 'r') as s3_creds:
					in_profile = None
					for line in s3_creds:
						line = line.strip()
						if line.startswith('['): in_profile = line[1:-1]
						if in_profile == 'default':
							if line.startswith('aws_access_key_id'): aws_access_key_id = line.split('=')[-1].strip()
							if line.startswith('aws_secret_access_key'): aws_secret_access_key = line.split('=')[-1].strip()
				break
		return aws_access_key_id, aws_secret_access_key

if __name__ == '__main__':
	Job.run()