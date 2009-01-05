#!/usr/bin/python

import feedparser, pickle, time, datetime, traceback, urllib

def tupleToDatetime(t):
	try:
		return datetime.datetime.fromtimestamp(time.mktime(t))
	except:
		return None


class Podcast:
	"""A single podcast retrieved from a Source.
	
	When downloaded, a Podcast keeps the audio file on disk. In addition, the Podcast
	objects themselves are picklable, so that they can be saved to disk and re-loaded later.

	Data attributes (read-only):
	source - The Source that this Podcast came from.
	sourceTitle - The title of the Source.
	title - The title of this particular episode.
	url - The URL to the audio file.
	date - The date this Podcast was made available.
	localPath - Once downloaded, this attribute contains the path to the local copy of the audio file. None before download() is called.
	deleted - A boolean value; true if the Podcast has already been deleted from disk.
	"""

	def __init__(self, source, sourceTitle, title, url, date):
		"""Creates a Podcast with the given url and date."""
		self.source = source
		self.sourceTitle = sourceTitle
		self.title = title
		self.url = url
		self.date = date
		self.localPath = None
		self.deleted = False
	
	def download(self):
		"""Attempts to download the given Podcast, blocking while doing so.
		
		Raises an IOError if the download failed. If the downloaded succeeded, localPath is set."""
	
	def __str__(self):
		return "%s - %s - %s - %s" % (self.sourceTitle, self.title, self.date, self.url) 


class Source:
	"""Base class for classes that fetch information from the web to create Podcasts.
	
	Sources can be pickled.
	"""
	def read(self):
		"""Returns a sequence of any new Podcasts found since the last read(), blocking while doing so.
		
		If the retrieval failed, raises an IOError.
		
		The very first read() returns nothing, but establishes the point at which updates begin."""
		pass


class FeedSource(Source):
	"""A Source that retrieves Podcasts from an RSS/Atom/etc. feed."""
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
			agent = "Audrey/0.1"
		)

		if "status" not in d:
			raise IOError("Unable to retrieve feed at url \"%s\"" % self.url)
		
		if d.status // 100 == 4:
			raise IOError("Got error status code %u when retrieving feed at url \"%s\"" % (d.status, self.url))
		
		if "etag" in d:
			self.http_etag = d.etag
		
		if "modified" in d:
			self.http_modified = d.modified
		
		if "status" in d and d.status == 301 and "href" in d:
			self.url = d.href
		
		newest_entry = None
		for entry in d.entries:
			if "date_parsed" not in entry or "title" not in entry or len(entry.enclosures) < 1:
				continue
			edate = tupleToDatetime(entry.date_parsed)
			if newest_entry is None or edate > newest_entry:
				newest_entry = edate
			if self.last_entry_date is not None and edate > self.last_entry_date:
				r.append(Podcast(self, d.feed.title, entry.title, entry.enclosures[0].href, edate))
		if newest_entry is not None:
			self.last_entry_date = newest_entry
		
		return r


class SourceList(list):
	"""A list of Sources.
	
	SourceLists can be pickled.
	"""

if __name__ == "__main__":
	s = FeedSource("http://www.theskepticsguide.org/rss.xml")
	s.last_entry_date = datetime.datetime(2008, 12, 15)
	s.http_etag = None
	s.http_modified = None
	for p in s.read():
		print p
