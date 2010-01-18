#!/usr/bin/env python
import sqlite3
import urllib2
import simplejson
import sys
from calais import Calais
from operator import itemgetter
from optparse import OptionParser

"""
To-do:
  *document usage in readme
  *add GPL license
"""

def get_command_line_arguments():

	services = {}

	usage = "usage: %prog [options] <username> <Calais API key>"

	parser = OptionParser()

	parser.add_option('-u', '--user', action='store', type='string', dest='user',
	  help='specify Reddit username to investigate')

	parser.add_option('-a', '--api_key', action='store', type='string', dest='api_key',
	  help='specify OpenCalais API key')

	parser.add_option('-f', '--file', action='store', type='string', dest='file', default=None,
	  help='specify database file (default is "usermine-<username>.db")')

	parser.add_option('-d', action='store_true', dest='debug', default=False,
	  help='display debug information during processing')

	parser.add_option('-r', action='store_true', dest='reddit', default=False,
	  help='fetch comments from Reddit')

	parser.add_option('-t', action='store_true', dest='twitter', default=False,
	  help='fetch comments from Twitter')

	parser.add_option('-o', action='store_true', dest='human_readable', default=False,
	  help='display output as human-readable text instead of JSON')

	(options, args) = parser.parse_args(sys.argv)

	if options.user == None:
		command_line_error_then_die(parser, 'Username is required.')

	if options.api_key == None:
		command_line_error_then_die(parser, 'API key is required.')

	if options.reddit == None and options.twitter == None:
		command_line_error_then_die(parser, 'You must specific at least one service, Reddit or Twitter, to pull comments from.')

	services['reddit'] =  options.reddit
	services['twitter'] = options.twitter

	return {
		'user': options.user,
		'api_key': options.api_key,
		'file': options.file,
		'services': services,
		'debug': options.debug,
		'human_readable': options.human_readable
	}

def command_line_error_then_die(parser, error_message):
	print 'ERROR: ' + error_message
	print
	parser.print_help()
	sys.exit()

def populate_database_with_reddit_comments(username, db_cursor, debug):

	if debug:
		print 'Getting comment data...'

	after = ''

	while True:

		url = 'http://www.reddit.com/user/' + username + '/comments.json?limit=100'

		if len(after):
			url = url + '&after=' + after

		if debug:
			print url

		f = urllib2.urlopen(url)

		comments = simplejson.loads(f.read())

		for comment in comments['data']['children']:
			db_cursor.execute('SELECT id FROM comments WHERE api_id = ?', [comment['data']['id']])

			if db_cursor.fetchone() == None:
				db_cursor.execute('INSERT INTO comments (id, comment, updated, api_id) VALUES (NULL, ?, ?, ?)', [comment['data']['body'], 0, comment['data']['id']])

		after = comments['data']['after']

		if not after:
			break

def populate_database_with_tweets(username, db_cursor, debug):

	if debug:
		print 'Getting tweets...'

	url = '?rpp=100&q=from%3A' + username

	while True:

		feed = 'http://search.twitter.com/search.json' + url
		f = urllib2.urlopen(feed)
		comments = simplejson.loads(f.read())

		if comments.has_key('results'):

			for comment in comments['results']:
				db_cursor.execute('SELECT id FROM comments WHERE api_id = ?', [comment['id']])

				if db_cursor.fetchone() == None:
					db_cursor.execute('INSERT INTO comments (id, comment, updated, api_id) VALUES (NULL, ?, ?, ?)', [comment['text'], 0, comment['id']])

			if comments.has_key('next_page'):

				url = comments['next_page']

				if debug:
					print url

			else:
				url = False

			if not url:
				break
		else:
			break

def create_semantic_data_tables(db_cursor):

	db_cursor.execute('CREATE TABLE IF NOT EXISTS topics (id INTEGER PRIMARY KEY, topic TEXT)')
	db_cursor.execute('CREATE TABLE IF NOT EXISTS entities (id INTEGER PRIMARY KEY, entity TEXT)')

def populate_database_with_semantic_data_from_comments(calais_api_key, db_cursor, debug):

	calais = Calais(calais_api_key, submitter='usermine')

	db_cursor.execute('SELECT id, comment FROM comments WHERE updated = 0')

	for comment_data in db_cursor.fetchall():

		id = comment_data[0]
		comment = comment_data[1]

		try:
			result = calais.analyze(comment)

			if hasattr(result, 'entities'):
				for entity in result.entities:
					entity_name = entity['name']
					db_cursor.execute('INSERT INTO entities (id, entity) VALUES (NULL, ?)', [entity_name])

			if hasattr(result, 'topics'):
				for topic in result.topics:
					topic_name = topic['categoryName']
					db_cursor.execute('INSERT INTO topics (id, topic) VALUES (NULL, ?)', [topic_name])
		except:
			if debug:
				print sys.exc_info()

		db_cursor.execute('UPDATE comments SET updated=1 WHERE id = ?', [id])

		if debug:
			print '.'

def summarize_data(db_cursor):

	topic_count  = {}
	entity_count = {}
	url_count    = {}

	db_cursor.execute("SELECT topic FROM topics")

	for topic_data in db_cursor.fetchall():
		increment_dictionary_counter(topic_count, topic_data[0])

	db_cursor.execute("SELECT entity FROM entities")

	for entity_data in db_cursor.fetchall():

		entity_name = entity_data[0]

		if entity_name.find('http://') == 0:
			increment_dictionary_counter(url_count, entity_name)
		else:
			increment_dictionary_counter(entity_count, entity_name)

	return {
		'topics': reverse_sort_dictionary_by_values(topic_count),
		'entities': reverse_sort_dictionary_by_values(entity_count),
		'urls': reverse_sort_dictionary_by_values(url_count)
	}

def increment_dictionary_counter(dictionary, key):
	dictionary.setdefault(key, 0)
	dictionary[key] += 1

def reverse_sort_dictionary_by_values(hash):
	return sorted(hash.iteritems(), key=itemgetter(1), reverse=True)

def main():

	try:
		options = get_command_line_arguments()

		username = options['user']
		calais_api_key = options['api_key']
		db_filename = options['file']
		services = options['services']
		debug = options['debug']
		human_readable = options['human_readable']

		if db_filename == None:
			db_filename = 'usermine-' + username + '.db'

		# create/open database
		connection = sqlite3.connect(db_filename)
		cursor = connection.cursor()

		cursor.execute('CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY, comment TEXT, api_id VARCHAR(255), updated BOOLEAN)')

		if services['reddit']:
			populate_database_with_reddit_comments(username, cursor, debug)

		if services['twitter']:
			populate_database_with_tweets(username, cursor, debug)

		create_semantic_data_tables(cursor)
		populate_database_with_semantic_data_from_comments(calais_api_key, cursor, debug)

		connection.commit()

		# summarize data
		if human_readable:
			summary = summarize_data(cursor)
			for data_type in summary:
				print data_type.title() + ':'
				for count in summary[data_type]:
					print '    ' + count[0] + ' (' + str(count[1]) + ')'
				print
		else:
			print simplejson.dumps(summarize_data(cursor))
	except SystemExit:
		pass

	except:
		print sys.exc_info()[0]

if __name__ == '__main__':
	main()
