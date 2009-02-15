#!/usr/bin/python

import feedparser, time, datetime, traceback, urllib, os, random, subprocess, re, pickle, processing, Queue


def tupleToDatetime(t):
	try:
		return datetime.datetime.fromtimestamp(time.mktime(t))
	except:
		return None


class AudreyProcess(processing.Process):
	"""Base class for the various Audrey sub-processes.
	
	Sub-classes must implement the doStuff() function, which must call pullEvent() periodically.
	
	Data attributes:
	workingDir - Path to the working directory.
	"""
	
	def __init__(self, workingDir):
		super(AudreyProcess, self).__init__()
		self.workingDir = workingDir
		self._logQueue = processing.Queue()
		self._statusQueue = processing.Queue()
		self._eventQueue = processing.Queue()
	
	def run(self):
		self.doStuff()
	
	def pullEvent(self):
		"""Returns a string with the latest input event, or None if there is no such event.
		
		Must be called periodically by doStuff()."""
		r = None
		try:
			while True:
				r = self._eventQueue.get_nowait()
		except Queue.Empty:
			return r
	
	def logMsg(self, msg):
		"""Emits a log message."""
		self._logQueue.put(msg)
	
	def statusMsg(self, msg):
		"""Sets a status message. This is used for showing cd burner state information."""
		self._statusQueue.put(msg)
	
	def doStuff(self):
		raise NotImplementedError


class FeedchkProcess(AudreyProcess):
	"""A Process for checking RSS/Atom feeds with the feedparser module and finding new podcasts to be downloaded.
	
	Reads the following queue files:
	feedchk-url-* - Each such file should contain a url to an RSS/Atom feed. These are not deleted.
	
	Writes the following queue files:
	feedchk-status-* - Pickle files each containing a FeedStatus object, corresponding to feedchk-url-* files.
	podfetch-desc-* - Read by the podfetch process.
	"""
	
	def __init__(self, workingDir):
		super(FeedchkProcess, self).__init__(workingDir)
	
	def doStuff(self):
		while True:
			self.logMsg("Feed check!")
			self.pullEvent()
			time.sleep(5)


class AudreyController:
	"""Class that starts up and runs the various audrey processes.
	
	Instantiate this class and then call start(). After that, periodically call pump() to get new status messages and keep everything going.
	"""
	
	def __init__(self):
		workingDir = os.path.expanduser("~/audrey-working")
		if not os.path.isdir(workingDir):
			try:
				os.mkdir(workingDir)
			except:
				pass
		if not os.path.isdir(workingDir):
			raise IOError("Unable to find or create directory \"%s\"" % workingDir)
		
		self._statusMsg = "Initializing controller..."
		self._subprocs = [
			FeedchkProcess(workingDir),
		]
	
	def start(self):
		for p in self._subprocs:
			p.start()
	
	def pump(self):
		"""Checks for messages from the subprocesses and returns the current status string."""
		for p in self._subprocs:
			try:
				while True:
					self._statusMsg = p._statusQueue.get_nowait()
			except Queue.Empty:
				pass

			try:
				while True:
					print p._logQueue.get_nowait()
			except Queue.Empty:
				pass
			
		return self._statusMsg


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
	"""Retrieves Podcasts from an RSS/Atom/etc. feed."""
	def __init__(self, url):
		"""Creates a FeedSource which reads from the XML document at the given URL."""
		self.url = url
		self.http_etag = None
		self.http_modified = None
		self.last_entry_date = None
	
	def read(self):
		"""Returns a sequence of any new Podcasts found since the last read(), blocking while doing so.
		
		If the retrieval failed, raises an IOError.
		
		The very first read() returns nothing, but establishes the point at which updates begin."""
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


def createIso(podcasts, isoPath):
	"""Given a sequence of Podcasts, creates an ISO image at the target path with those podcasts on it.

	Blocks during this entire procedure.
	
	Returns True on success. On failure, throws IOError. 
	"""
	try:
		proc = subprocess.Popen(("genisoimage", "-l", "-r", "-J", "-graft-points", "-o", isoPath, "-path-list", "-"), stdin = subprocess.PIPE, stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
	except OSError, e:
		raise IOError("Unable to run genisoimage : %s" % str(e))

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


def burnDisc(isoPath):
	"""Given a path to an ISO, burns it to disc.
	
	Blocks during this entire procedure.

	Returns True on success. On failure, throws IOError.
	"""
	if not os.path.exists(isoPath):
		raise IOError("No such file %s" % isoPath)
	
	try:
		proc = subprocess.Popen(("wodim", "-tao", "-eject", "speed=10", "dev=/dev/cdrw", isoPath), stdin = subprocess.PIPE, stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
	except OSError, e:
		raise IOError("Unable to run wodim : %s" % str(e))
	
	(stdout, stderr) = proc.communicate()
	if proc.returncode != 0:
		raise IOError("Wodim reported an error! Return code %s, output %s" % (proc.returncode, stdout))
	return True


if __name__ == "__main__":
#	s = Source("http://www.theskepticsguide.org/5x5/rss_5x5.xml")
#	s.last_entry_date = datetime.datetime(2009, 1, 25)
#	s.http_etag = None
#	s.http_modified = None
#	podcasts = [p for p in s.read()]
#	for p in podcasts:
#		print p
#		p.download()
#	createIso(podcasts, os.path.join(queueDir(), "test.iso"))
#	burnDisc(os.path.join(queueDir(), "test.iso"))
	controller = AudreyController()
	controller.start()
	while True:
		controller.pump()
		time.sleep(1)
		print ".",
