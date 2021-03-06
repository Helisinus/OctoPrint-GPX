# coding=utf-8
from __future__ import absolute_import
__author__ = "Mark Walker <markwal@hotmail.com> based on work by Gina Häußge" 
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'

import os
import logging
import time
import Queue
import re

try:
	import gpx
except:
	pass

class GpxPrinter():
	def __init__(self, logger = None, settings = None, printer = None, port = None, baudrate = None, timeout = 0):
		if logger is None:
			self._logger = logging.getLogger(__name__)
		else:
			self._logger = logger
		self._settings = settings
		self._printer = printer
		if not gpx:
			self._logger.info("Unable to import gpx module")
			raise ValueError("Unable to import gpx module")
		self.port = port
		self.baudrate = self._baudrate = baudrate
		self.timeout = timeout
		self._logger.info("GPXPrinter created, port: %s, baudrate: %s" % (self.port, self.baudrate))
		self.outgoing = Queue.Queue()
		self.baudrateError = False;
		data_folder = self._settings.get_plugin_data_folder()
		self.profile_path = os.path.join(data_folder, "gpx.ini")
		log_path = self._settings.get_plugin_logfile_path()
		try:
			self._append(gpx.connect(port, baudrate, self.profile_path, log_path,
				self._logger.getEffectiveLevel() == logging.DEBUG))
		except Exception as e:
			self._logger.info("gpx.connect raised exception = %s" % e)
			raise
		self._regex_linenumber = re.compile("N(\d+)")

	def refresh_ini(self):
		if not self._printer.is_printing() and not self._printer.is_paused():
			gpx.reset_ini()
			gpx.read_ini(self.profile_path)

	def _append(self, s):
		if (s != ''):
			for item in s.split('\n'):
				self.outgoing.put(item)

	def write(self, data):
		data = data.strip()
		# strip checksum
		if "*" in data:
			data = data[:data.rfind("*")]
		if (self.baudrate != self._baudrate):
			try:
				self._baudrate = self.baudrate
				self._logger.info("new baudrate = %d" % self.baudrate)
				gpx.set_baudrate(self.baudrate)
				self.baudrateError = False
			except ValueError:
				self.baudrateError = True
				self.outgoing.put('')
				pass
				return

		# look for a line number
		# line number means OctoPrint is streaming gcode at us (gpx.ini flavor)
		# no line number means OctoPrint is generating the gcode (reprap flavor)
		match = self._regex_linenumber.match(data)
		if match is not None:
			lineno = int(match.group(1))
			if lineno == 1:
				currentJob = self._printer.get_current_job()
				if currentJob is not None and "file" in currentJob.keys() and "name" in currentJob["file"]:
					gpx.write("M136 %s" % os.path.basename(currentJob["file"]["name"]))
				else:
					gpx.write("M136")

		# try to talk to the bot
		while True:
			try:
				if match is None:
					reprapSave = gpx.reprap_flavor(True)
				self._append(gpx.write("%s" % data))
				break
			except gpx.BufferOverflow:
				self._append("buffer overflow")
				time.sleep(1)
				pass
			finally:
				if match is None:
					gpx.reprap_flavor(reprapSave)

	def readline(self):
		while (self.baudrateError):
			if (self._baudrate != self.baudrate):
				self.write("M105")
			return ''
		try:
			s = self.outgoing.get_nowait()
			self._logger.debug("readline: %s" % s)
			return s
		except Queue.Empty:
			pass
		s = gpx.readnext()
		timeout = self.timeout
		append_later = None
		if gpx.waiting():
			append_later = s
			timeout = 2
		else:
			self._append(s)
		try:
			s = self.outgoing.get(timeout=timeout)
			self._logger.debug("readline: %s" % s)
			return s
		except Queue.Empty:
			if append_later is not None:
				self._append(append_later)
			self._logger.debug("timeout")
			pass
		return ''

	def close(self):
		gpx.disconnect()
		return
