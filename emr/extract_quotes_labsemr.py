'''
	EMR job that extracts inline and block quotes from JSTOR documents with text coordinates.

	Run example:  python extract_quotes_labsemr.py -c matchmaker_mrjob.conf -r emr --named-passages XXXX ---no-output s3://ithaka-labs/matchmaker/XXXX/docids -o s3://ithaka-labs/matchmaker/XXXX/extracted-quotes

'''

from mrjob.job import MRJob
import mrjob.protocol
import os, sys, traceback, json
basedir = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.getcwd())
sys.path.insert(0, '%s/matchmaker'%basedir)

from quotes import QuoteFinder
import botocore.session

class Job(MRJob):
	OUTPUT_PROTOCOL = mrjob.protocol.JSONValueProtocol

	def configure_options(self):
		super(Job, self).configure_options()
		self.add_file_option('--named-passages', type='str', default='', help='Path to optional named passages file')

	def load_options(self, args):
		super(Job, self).load_options(args)
		self.named_passages_filename = self.options.named_passages

	def mapper_init(self):
		self.named_passages_text = None
		try:
			if self.named_passages_filename and os.path.exists(os.path.join(os.getcwd(),self.named_passages_filename)):
				with open(os.path.join(os.getcwd(),self.named_passages_filename),'r') as named_passages_file:
					self.named_passages_text = named_passages_file.read()
				sys.stderr.write('named_passages_filename=%s size=%s\n'%(self.named_passages_filename,len(self.named_passages_text)))
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
		try_plain = True
		quotes = None
		try:
			self.increment_counter('counters', 'all_docs', 1)
			self.increment_counter('counters', 'coords_docs_attempted', 1)
			response_data = self.s3_client.get_object(Bucket='ithaka-labs', Key='files/coord-text/%s'%(docid))
			if response_data['ResponseMetadata']['HTTPStatusCode'] == 200 and response_data:
				serialized_doc = response_data['Body'].read()
				if serialized_doc:
					coords_text_doc = json.loads(serialized_doc)
					quotes = QuoteFinder(is_coords=True, named_passages=self.named_passages_text).quotes_from_coords_doc(coords_text_doc)
					try_plain = False
					self.increment_counter('counters', 'coords_docs_processed', 1)
					self.increment_counter('counters', 'coords_quotes', len(quotes))
					if quotes:
						yield key, {'id': docid, 'quotes': quotes}
		except:
			self.increment_counter('counters', 'coords_docs_failed', 1)
			sys.stderr.write(traceback.format_exc())
			sys.stderr.write(docid)
			#raise

		if try_plain:
			try:
				self.increment_counter('counters', 'plain_docs_attempted', 1)
				response_data = self.s3_client.get_object(Bucket='ithaka-labs', Key='files/text/%s'%(docid))
				if response_data['ResponseMetadata']['HTTPStatusCode'] == 200 and response_data:
					serialized_doc = response_data['Body'].read()
					if serialized_doc:
						text_doc = json.loads(serialized_doc)
						quotes = QuoteFinder(is_coords=False).quotes_from_plain_doc(text_doc['text'])
						self.increment_counter('counters', 'plain_docs_processed', 1)
						self.increment_counter('counters', 'plain_quotes', len(quotes))
						if quotes:
							yield key, {'id': docid, 'quotes': quotes}
			except:
				self.increment_counter('counters', 'plain_docs_failed', 1)
				self.increment_counter('counters', 'all_docs_failed', 1)
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