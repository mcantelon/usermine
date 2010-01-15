#!/usr/bin/env python
import sqlite3, urllib2, simplejson, sys, os.path
from calais import Calais
from operator import itemgetter
from optparse import OptionParser

"""
change logic:
  on update:
    pull comments
    add new comments to db

  add to semantic logic to only scan new comments, marking comment read after scan

document usage in readme

add options to toggle services (Reddit, Twitter)

add option to output as human readable

add extraction of URLs

add GPL license
"""

def get_command_line_arguments():

	services = {}

	usage = "usage: %prog [options] <username> <Calais API key>"

	parser = OptionParser()

	parser.add_option('-u', '--user', action='store', type='string', dest='user',
	  help='specify Reddit username to investigate')

	parser.add_option('-a', '--api_key', action='store', type='string', dest='api_key',
	  help='specify OpenCalais API key')

	parser.add_option('-d', action='store_true', dest='debug',
	  help='display debug information during processing')

	parser.add_option('-r', action='store_true', dest='reddit', default=False,
	  help='fetch comments from Reddit')

	parser.add_option('-t', action='store_true', dest='twitter', default=False,
	  help='fetch comments from Twitter')

	(options, args) = parser.parse_args(sys.argv)

	if options.user == None:
		command_line_error_then_die(parser, 'Username is required.')

	if options.api_key == None:
		command_line_error_then_die(parser, 'API key is required.')

	if options.reddit == None and options.twitter == None:
		command_line_error_then_die(parser, 'You must specific at least one service, Reddit or Twitter, to pull comments from.')

	services['reddit'] =  options.reddit
	services['twitter'] = options.twitter

	return options.user, options.api_key, services

def command_line_error_then_die(parser, error_message):
	print 'ERROR: ' + error_message
	print
	parser.print_help()
	sys.exit()

def populate_database_with_reddit_comments(username, db_cursor):

	print 'Getting comment data...'

	after = ''

	while True:

		url = 'http://www.reddit.com/user/' + username + '/comments.json?limit=100'

		if len(after):
			url = url + '&after=' + after

		print url

		f = urllib2.urlopen(url)

		comments = simplejson.loads(f.read())

		for comment in comments['data']['children']:
			db_cursor.execute('INSERT INTO comments VALUES (NULL, ?)', [comment['data']['body']])

		after = comments['data']['after']

		if not after:
			break

def populate_database_with_tweets(username, db_cursor):

	print 'Getting tweets...'

	url = '?rpp=100&q=from%3A' + username

	while True:

		feed = 'http://search.twitter.com/search.json' + url

		f = urllib2.urlopen(feed)

		comments = simplejson.loads(f.read())

		try:
			for comment in comments['results']:
				db_cursor.execute('INSERT INTO comments VALUES (NULL, ?)', [comment['text']])

			try:
				url = comments['next_page']

				print url
			except:
				url = False

			if not url:
				break
		except:
			pass

def create_semantic_data_tables(db_cursor):

	db_cursor.execute('CREATE TABLE topics (id INTEGER PRIMARY KEY, topic TEXT)')
	db_cursor.execute('CREATE TABLE entities (id INTEGER PRIMARY KEY, entity TEXT)')

def populate_database_with_semantic_data_from_comments(calais_api_key, db_cursor):

	calais = Calais(calais_api_key, submitter='usermine')

	db_cursor.execute('SELECT comment FROM comments')

	for comment_data in db_cursor.fetchall():

		comment = comment_data[0]

		try:
			result = calais.analyze(comment)

			if hasattr(result, 'entities'):
				for entity in result.entities:
					entity_name = entity['name']
					db_cursor.execute('INSERT INTO entities VALUES (NULL, ?)', [entity_name])

			if hasattr(result, 'topics'):
				for topic in result.topics:
					topic_name = topic['categoryName']
					db_cursor.execute('INSERT INTO topics VALUES (NULL, ?)', [topic_name])

			print '.'

		except:
			print sys.exc_info()[0]

def main():

	try:

		username, calais_api_key, services = get_command_line_arguments()

		db_filename = 'usermine-' + username + '.db'

		updating = os.path.isfile(db_filename)

		connection = sqlite3.connect(db_filename)
		cursor = connection.cursor()

		if not updating:

			cursor.execute('CREATE TABLE comments (id INTEGER PRIMARY KEY, comment TEXT)')

			if services['reddit']:
				populate_database_with_reddit_comments(username, cursor)

			if services['twitter']:
				populate_database_with_tweets(username, cursor)

			create_semantic_data_tables(cursor)
			populate_database_with_semantic_data_from_comments(calais_api_key, cursor)

			connection.commit()

		# Summarize data
		#
		entity_count = {}

		cursor.execute("SELECT entity FROM entities")

		for entity_data in cursor.fetchall():

			entity_name = entity_data[0]

			try:
				entity_count[entity_name] = entity_count[entity_name] + 1

			except KeyError:
				entity_count[entity_name] = 1

		summary = {}
		summary['entities'] = sorted(entity_count.iteritems(), key=itemgetter(1), reverse=True)

		print simplejson.dumps(summary)
		#for entity_data in  sorted(entity_count.iteritems(), key=itemgetter(1), reverse=True):
		#  entity_name = entity_data[0]
		#  print entity_name + ':' + str(entity_count[entity_name])
	except:
		print sys.exc_info()[0]

if __name__ == '__main__':
	main()
