#!/usr/bin/python

import feedparser, pickle, time, datetime, traceback, urllib, os, random, subprocess, re


def tupleToDatetime(t):
	try:
		return datetime.datetime.fromtimestamp(time.mktime(t))
	except:
		return None


def queueDir():
	dirPath = os.path.expanduser("~/feedmeQueue")
	if not os.path.isdir(dirPath):
		try:
			os.mkdir(dirPath)
		except:
			pass
	if not os.path.isdir(dirPath):
		raise IOError("Unable to find or create directory \"%s\"" % dirPath)
	return dirPath


class Podcast:
	"""A single podcast retrieved from a Source.
	
	When downloaded, a Podcast keeps the audio file on disk. In addition, the Podcast
	objects themselves are picklable, so that they can be saved to disk and re-loaded later.

	Data attributes (read-only):
	source - The Source that this Podcast came from.
	sourceTitle - The title of the Source.
	title - The title of this particular episode.
	url - The URL to the audio file.
	ext - The 3-letter filename extension corresponding to the audio file's type.
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
		self.ext = url[-3:]
		self.date = date
		self.localPath = None
		self.deleted = False
	
	def download(self):
		"""Attempts to download the given Podcast, blocking while doing so.
		
		Raises an IOError if the download failed. If the downloaded succeeded, localPath is set."""
		destFile = "podcast-%s-%08u" % (str(datetime.datetime.now()), random.randint(1,10000000))
		destPath = os.path.join(queueDir(), destFile)
		try:
			(fn, headers) = urllib.urlretrieve(self.url, destPath)
			self.localPath = destPath
		except:
			if os.path.isfile(destPath):
				os.unlink(destPath)
			raise
	
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
		
		if d.status // 100 == 4 or d.status // 100 == 5:
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


def createIso(podcasts, path):
	"""Given a sequence of Podcasts, creates an ISO image at the target path with those podcasts on it.
	
	Returns True on success. On failure, throws IOError. 
	"""
	try:
		proc = subprocess.Popen(("mkisofs", "-l", "-r", "-J", "-graft-points", "-o", path, "-path-list", "-"), stdin = subprocess.PIPE, stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
	except OSError, e:
		raise IOError("Unable to run mkisofs : %s" % str(e))

	if proc.poll() is not None: # None means the process hasn't returned a return code yet
		raise IOError("Mkisofs died immediately!")
	
	cleanPat = re.compile(r"[^A-Za-z0-9 ._-]")
	def cleanStr(s, maxLen):
		return cleanPat.sub("", s)[:maxLen]
	
	idx = 1
	for p in podcasts:
		if p.localPath is not None:
			proc.stdin.write("%s - %s - %02u-%02u-%02u (%03u).%s=%s\n" % (cleanStr(p.sourceTitle, 35), cleanStr(p.title, 50), p.date.year, p.date.month, p.date.day, idx, p.ext, p.localPath))
			idx += 1
	(stdout, stderr) = proc.communicate()
	
	if proc.returncode != 0:
		raise IOError("Mkisofs reported an error! Return code %s, output %s" % (proc.returncode, stdout))
	return True


class SourceList(list):
	"""A list of Sources.
	
	SourceLists can be pickled.
	"""

if __name__ == "__main__":
	s = FeedSource("http://www.theskepticsguide.org/5x5/rss_5x5.xml")
	s.last_entry_date = datetime.datetime(2008, 12, 25)
	s.http_etag = None
	s.http_modified = None
	podcasts = [p for p in s.read()]
	for p in podcasts:
		print p
		p.download()
	createIso(podcasts, "/home/localuser/test.iso")
