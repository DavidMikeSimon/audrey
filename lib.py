#!/usr/bin/python

import feedparser, time, datetime, traceback, urllib, os, random, subprocess, re, processing, Queue


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
	"""An AudreyProcess for checking RSS/Atom feeds with the feedparser module and finding new podcasts to be downloaded.
	
	Reads the following working files:
	feedchk-url-* - Files containing a url to an RSS/Atom feed. These are not deleted.
	
	Writes the following working files:
	feedchk-status-* - Text files each describing how up-to-date we are on feeds, corresponding to feedchk-url-* files.
	fetch-desc-* - Read by the fetch process.
	"""
	
	def __init__(self, workingDir):
		super(FeedchkProcess, self).__init__(workingDir)
	
	def _checkFeed(self, fn):
		self.logMsg("Reading feed url file %s" % fn)
		
		statusPath = os.path.join(self.workingDir, fn.replace("-url-", "-status-", 1))
		
		fh = open(os.path.join(self.workingDir, fn))
		url = fh.read().strip()
		fh.close()
		
		http_etag = None
		http_modified = None
		last_entry_date = None
		
		if os.path.exists(statusPath):
			fh = open(statusPath)
			etag_line = fh.readline().strip()
			if etag_line != "None":
				http_etag = etag_line # E-Tags are just strings for universal feed parser
			modified_line = fh.readline().strip()
			if modified_line != "None":
				http_modified = tuple([int(x) for x in modified_line.split(",")]) # Modified headers are tuples of integers for universal feed parser
			last_entry_line = fh.readline().strip()
			if last_entry_line != "None":
				last_entry_date = datetime.datetime(*tuple([int(x) for x in last_entry_line.split(",")]))
			fh.close()
		
		d = feedparser.parse(
			url,
			etag = http_etag,
			modified = http_modified,
			agent = "Audrey/0.1"
		)
		
		if "status" not in d:
			raise IOError("Unable to retrieve feed at url \"%s\"" % url)
		
		if d.status // 100 == 4 or d.status // 100 == 5:
			raise IOError("Got error status code %u when retrieving feed at url \"%s\"" % (d.status, url))
		
		if "etag" in d:
			http_etag = d.etag
		
		if "modified" in d:
			http_modified = d.modified
		
		if "status" in d and d.status == 301 and "href" in d:
			self.logMsg("Server status code 301 requesting we switch to url %s" % d.href)
		
		files = [] # A list of (edate, url, title) tuples
		
		newest_entry = None
		for entry in d.entries:
			if "date_parsed" not in entry or "title" not in entry or len(entry.enclosures) < 1:
				continue
			edate = datetime.datetime.fromtimestamp(time.mktime(entry.date_parsed))
			if newest_entry is None or edate > newest_entry:
				newest_entry = edate
			if last_entry_date is not None and edate > last_entry_date:
				files.append(edate, entry.enclosures[0].href, "%s - %s" % (d.feed.title, entry.title))
		if newest_entry is not None:
			last_entry_date = newest_entry
		
		# Pick only the 3 most recent podcasts retrieved (in case of a mishap where the archives are marked by the source as new again)
		files.sort(cmp = lambda x, y: cmp(x[0], y[0]))
		n = 0
		for (file_date, file_url, file_title) in files[-3:]:
			n += 1
			fh = open(os.path.join(self.workingDir, "fetch-desc-%s-%03u" % (str(datetime.datetime.now()).replace(" ", "-"), n)))
			fh.write("%s\n", file_url)
			fh.write("%s\n", file_title)
			fh.close()
		
		fh = open(statusPath, "w")
		if http_etag is not None:
			fh.write("%s\n" % http_etag)
		else:
			fh.write("None\n")
		if http_modified is not None:
			fh.write("%s\n" % (",".join(str(i) for i in http_modified)))
		else:
			fh.write("None\n")
		if last_entry_date is not None:
			fh.write("%i,%i,%i,%i,%i,%i\n" % (
				last_entry_date.year, last_entry_date.month, last_entry_date.day,
				last_entry_date.hour, last_entry_date.minute, last_entry_date.second,
			))
		else:
			fh.write("None\n")
		fh.close()
	
	def doStuff(self):
		while True:
			self.pullEvent()
			self.logMsg("Checking feeds")
			for fn in os.listdir(self.workingDir):
				if fn.startswith("feedchk-url-"):
					try:
						self._checkFeed(fn)
					except IOError, e:
						self.logMsg("Error with %s - %s" % (fn, str(e)))
			time.sleep(3600)


class FetchProcess(AudreyProcess):
	"""An AudreyProcess for downloading files.
	
	Reads the following working files:
	fetch-desc-* - Files each containing two lines: URL, title. Read in lexicographical order. Deleted once corresponding isobuild-item-* files are created.
	
	Writes the following working files:
	isobuild-item-* - Read by the isobuild process.
	"""
	
	def __init__(self, workingDir):
		super(FetchProcess, self).__init__(workingDir)
	
	def doStuff(self):
		while True:
			self.pullEvent()
			time.sleep(1)


class IsobuildProcess(AudreyProcess):
	"""An AudreyProcess for building ISO9660 images from downloaded files.

	Reads the following working files:
	isobuild-item-* - Files containing actual content. The name of the file after "item-" will be the in-ISO name. Deleted once put into an ISO.

	Writes the following working files:
	discburn-iso-* - Read by the discburn process.
	"""

	def __init__(self, workingDir):
		super(IsobuildProcess, self).__init__(workingDir)
	
	def doStuff(self):
		while True:
			self.pullEvent()
			time.sleep(1)


class DiscburnProcess(AudreyProcess):
	"""An AudreyProcess for burning ISO9660 images to disc, and also controlling the opening and closing of the tray.

	Reads the following working files:
	discburn-iso-* - Files containing ISO images to burn. Read in lexciographical order. Deleted once successfully burned.
	"""

	def __init__(self, workingDir):
		super(DiscburnProcess, self).__init__(workingDir)
	
	def doStuff(self):
		while True:
			self.pullEvent()
			time.sleep(0.5)


class AudreyController:
	"""Class that starts up and runs the various audrey processes.
	
	Instantiate this class and then call start(). After that, periodically call pump() to get new status messages and keep everything going.
	"""
	
	def __init__(self):
		# Create the working directory if necessary
		self._workingDir = os.path.expanduser("~/audrey-working")
		if not os.path.isdir(self._workingDir):
			try:
				os.mkdir(self._workingDir)
			except:
				pass
		if not os.path.isdir(self._workingDir):
			raise IOError("Unable to find or create directory \"%s\"" % self._workingDir)

		# Delete any left-over temp files from possible prior crashes
		for fn in os.listdir(self._workingDir):
			if fn.startswith("temp-"):
				os.unlink(os.path.join(self._workingDir, fn))
		
		self._statusMsg = "Initializing controller..."
		self._subprocs = [
			FeedchkProcess(self._workingDir),
			FetchProcess(self._workingDir),
			IsobuildProcess(self._workingDir),
			DiscburnProcess(self._workingDir),
		]
	
	def _addToLog(self, msg):
		fn = file(os.path.join(self._workingDir, "log"), "a")
		fn.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
		fn.close()
	
	def start(self):
		self._addToLog("AudreyController starting")
		for p in self._subprocs:
			p.start()
	
	def pump(self):
		"""Checks for messages from the subprocesses and returns the current status string."""
		for p in self._subprocs:
			if not p.isAlive():
				raise IOError("Subprocess of type %s died" % p.__class__.__name__)
			
			try:
				while True:
					self._statusMsg = p._statusQueue.get_nowait()
			except Queue.Empty:
				pass
			
			try:
				while True:
					self._addToLog("%s: %s" % (p.__class__.__name__, p._logQueue.get_nowait()))
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
		time.sleep(0.1)
