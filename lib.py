#!/usr/bin/python

import feedparser, time, datetime, traceback, urllib, os, random, subprocess, re, processing, Queue, socket


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
		try:
			self.doStuff()
		except:
			self.logMsg("Uncaught exception in subprocess! Traceback:\n%s" % traceback.format_exc())
	
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
		
		try:
			d = feedparser.parse(
				url,
				etag = http_etag,
				modified = http_modified,
				agent = "Audrey/0.1"
			)
		except socket.timeout:
			raise IOError("Timed out when retrieving feed at url \"%s\"" % url)
		
		if "status" not in d:
			raise IOError("Unable to retrieve feed at url \"%s\"" % url)
		
		if d.status // 100 == 4 or d.status // 100 == 5:
			raise IOError("Got error status code %u when retrieving feed at url \"%s\"" % (d.status, url))
		
		if "etag" in d:
			http_etag = d.etag
		
		if "modified" in d:
			http_modified = d.modified
		
		if "status" in d and d.status == 301 and "href" in d:
			self.logMsg("Writing to %s, status code 301 requesting we switch to url %s" % (fn, d.href))
			fh = open(os.path.join(self.workingDir, fn), "w")
			fh.write("%s\n" % d.href)
			fh.close()
		
		files = [] # A list of (edate, url, title) tuples
	
		cleanPat = re.compile(r"[^A-Za-z0-9 #()._-]")
		def cleanStr(s, maxLen):
			return cleanPat.sub("", s)[:maxLen]
		
		newest_entry = None
		for entry in d.entries:
			if "date_parsed" not in entry or "title" not in entry or "enclosures" not in entry or len(entry.enclosures) < 1:
				self.logMsg("Skipping weird entry")
				continue
			edate = datetime.datetime.fromtimestamp(time.mktime(entry.date_parsed))
			if newest_entry is None or edate > newest_entry:
				newest_entry = edate
			if last_entry_date is not None and edate > last_entry_date:
				fTitle = "%04u-%02u-%02u-%02u%02u %s - %s" % (
					edate.year,
					edate.month,
					edate.day,
					edate.hour,
					edate.minute,
					cleanStr(d.feed.title, 40),
					cleanStr(entry.title, 40),
				)
				files.append((edate, entry.enclosures[0].href, fTitle))
		if newest_entry is not None:
			last_entry_date = newest_entry
		
		if len(files) > 0:
			self.logMsg("Got %u seeming to be new" % len(files))
		
		# Pick only the 3 most recent podcasts retrieved (in case of a mishap where the archives are mistakenly presented by the source as new again)
		files.sort(cmp = lambda x, y: cmp(x[0], y[0]))
		n = 0
		for (file_date, file_url, file_title) in files[-3:]:
			n += 1
			targetFn = "fetch-desc-%s-%s-%03u" % (fn.replace("feedchk-url-", ""), str(datetime.datetime.now()).replace(" ", "-"), n)
			fh = open(os.path.join(self.workingDir, "temp-%s" % targetFn), "w")
			fh.write("%s\n" % file_url)
			fh.write("%s\n" % file_title)
			fh.close()
			os.rename(os.path.join(self.workingDir, "temp-%s" % targetFn), os.path.join(self.workingDir, targetFn)) # Give control to FetchProcess
			self.logMsg("Wrote %s" % targetFn)
		
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
			for fn in sorted(os.listdir(self.workingDir)):
				if fn.startswith("feedchk-url-"):
					try:
						self._checkFeed(fn)
					except IOError, e:
						self.logMsg("Error with %s - %s" % (fn, str(e)))
			self.logMsg("Finished checking feeds")
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
	
	def _fetch(self, fn):
		self.logMsg("Reading fetch description file %s" % fn)
		
		fh = open(os.path.join(self.workingDir, fn))
		url = fh.readline().strip()
		title = fh.readline().strip()
		fh.close()
		
		destPath = os.path.join(self.workingDir, "temp-fetch")
		try:
			self.logMsg("Fetching URL %s" % url)
			try:
				(retrFn, retrHeaders) = urllib.urlretrieve(url, destPath)
			except socket.timeout:
				raise IOError("Timed out when fetching URL %s" % url)
			self.logMsg("Done fetching URL %s" % url)
		except:
			if os.path.isfile(destPath):
				os.unlink(destPath)
			raise
		
		if not os.path.exists(destPath):
			raise IOError("Cannot find temp-fetch")
		
		finalName = title
		for knownExt in (".ogg", ".mp3", ".mp4", ".m4a", ".wma", ".flc", ".flac"):
			if url.lower().endswith(knownExt):
				finalName += knownExt
				break
		
		targetFn = "isobuild-item-%s" % finalName
		n = 0
		while os.path.exists(os.path.join(self.workingDir, targetFn)):
			n += 1
			targetFn = "isobuild-item-%s %03u" % (finalName, n)
		os.rename(os.path.join(self.workingDir, "temp-fetch"), os.path.join(self.workingDir, targetFn))
		self.logMsg("Wrote %s" % targetFn)
		
		os.unlink(os.path.join(self.workingDir, fn))
		self.logMsg("Deleted %s" % fn)
	
	def doStuff(self):
		while True:
			self.pullEvent()
			for fn in sorted(os.listdir(self.workingDir)):
				if fn.startswith("fetch-desc-"):
					try:
						self._fetch(fn)
					except IOError, e:
						self.logMsg("Error with %s - %s" % (fn, str(e)))
			time.sleep(60)


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
		socket.setdefaulttimeout(60)

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
			
			if not p.isAlive():
				self._addToLog("Subprocess %s died, killing all subprocesses and raising RuntimeError" % p.__class__.__name__)
				for p in self._subprocs:
					p.terminate()
				raise RuntimeError("Subprocess died")
			
		return self._statusMsg


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
	
	idx = 1
	for p in podcasts:
		if p.localPath is not None:
			proc.stdin.write("=%s\n" % (cleanStr(p.sourceTitle, 35), cleanStr(p.title, 50), p.date.year, p.date.month, p.date.day, idx, p.ext, p.localPath))
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
#	createIso(podcasts, os.path.join(queueDir(), "test.iso"))
#	burnDisc(os.path.join(queueDir(), "test.iso"))
	controller = AudreyController()
	controller.start()
	while True:
		controller.pump()
		time.sleep(0.1)
