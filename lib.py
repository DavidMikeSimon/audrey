#!/usr/bin/python

import feedparser, pickle, time, datetime, traceback

def tupleToDatetime(t):
	try:
		return datetime.datetime.fromtimestamp(time.mktime(t))
	except:
		return None


class Article:
	"""A single post, submission, podcast, etc. retrieved from a Source.
	
	A Article keeps its actual data on-disk in its own directory. In addition, the Article
	objects themselves are picklable, so that they can be saved to disk and re-loaded later.
	"""


class Source:
	"""Base class for classes that fetch information from the web to create Articles.
	
	Sources can be pickled.
	"""
	def read(self):
		"""Returns a sequence of any new Articles found since the last read().
		
		The very first read() returns nothing, but establishes the point at which updates begin."""


class FeedSource(Source):
	"""A Source that retrieves articles from an RSS/Atom/etc. feed."""
	def __init__(self, url):
		"""Creates a FeedSource which reads from the XML document at the given URL."""
		self.url = url
		self.http_etag = None
		self.http_modified = None
		self.last_entry_date = None
	
	def read(self):
		r = []
		
		d = feedparser.parse(
			self.url,
			etag = self.http_etag,
			modified = self.http_modified,
			agent = "Audrey/1.0"
		)
		
		if "etag" in d:
			self.http_etag = d.etag
		
		if "modified" in d:
			self.http_modified = d.modified
		
		if "status" in d and d.status == 301 and "href" in d:
			self.url = d.href
		
		newest_entry = None
		for entry in d.entries:
			if "date_parsed" not in entry:
				continue
			edate = tupleToDatetime(entry.date_parsed)
			if newest_entry is None or edate > newest_entry:
				newest_entry = edate
			if self.last_entry_date is not None and edate > self.last_entry_date:
				r.append(entry.id)
		if newest_entry is not None:
			self.last_entry_date = newest_entry
		
		return r


class StaticSource(Source):
	"""A Source that considers a new 'Article' to have been created when a given webpage is updated.
	
	The nature of StaticSource means that read() will return a sequence of, at most, one Article.
	"""
	def __init__(self, url):
		"""Creates a StaticSource which checks the HTML document at the given URL."""
		self.url = url
		self.prevPageContents = None
	
	def read(self):
		pass


class SourceList(list):
	"""A list of Sources.
	
	SourceLists can be pickled.
	"""

if __name__ == "__main__":
	s = FeedSource("http://feedproxy.google.com/ICanHasCheezburger")
	print "1: %s" % str(s.read())
	print "LATEST ENTRY %s" % (str(s.last_entry_date))
	s.last_entry_date = datetime.datetime(2008, 11, 15)
	s.http_etag = None
	s.http_modified = None
	print "2: %s" % str(s.read())