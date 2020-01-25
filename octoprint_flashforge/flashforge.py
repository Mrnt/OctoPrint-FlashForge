import usb1
import threading

try:
	import queue
	import re
except ImportError:
	import Queue as queue


regex_SDPrintProgress = re.compile("(?P<current>[0-9]+)/(?P<total>[0-9]+)")
"""
Regex matching SD print progress from M27.
"""


class FlashForgeError(Exception):
	def __init__(self, message, error=0):
		super(FlashForgeError, self).__init__(("{} ({})" if error else "{}").format(message, error))
		self.error = error


class FlashForge(object):
	ENDPOINT_CMD_IN = 0x81
	ENDPOINT_CMD_OUT = 0x01
	ENDPOINT_DATA_IN = 0x83
	ENDPOINT_DATA_OUT = 0x03
	BUFFER_SIZE = 128

	STATE_UNKNOWN = 0
	STATE_READY = 1
	STATE_BUILDING = 2
	STATE_SD_BUILDING = 3
	STATE_SD_PAUSED = 4
	STATE_HOMING = 5
	STATE_BUSY = 6

	PRINTING_STATES = (STATE_BUILDING, STATE_SD_BUILDING, STATE_HOMING)


	def __init__(self, plugin, comm, vendor_id, device_id, seriallog_handler=None, read_timeout=10.0, write_timeout=10.0):
		import logging
		self._logger = logging.getLogger("octoprint.plugins.flashforge")
		self._logger.debug("FlashForge.__init__()")

		self._plugin = plugin
		self._comm = comm
		self._read_timeout = read_timeout
		self._write_timeout = write_timeout
		self._incoming = queue.Queue()
		self._readlock = threading.Lock()
		self._writelock = threading.Lock()
		self._printerstate = self.STATE_UNKNOWN

		self._context = usb1.USBContext()
		try:
			self._handle = self._context.openByVendorIDAndProductID(vendor_id, device_id)
		except usb1.USBError as usberror:
			if usberror.value == -3:
				raise FlashForgeError("Unable to connect to FlashForge printer - permission error.\r\n\r\n"
									  "On OctoPi/Linux add the following line to\r\n /etc/udev/rules.d/99-octoprint.rules:\r\n\r\n"
									  "SUBSYSTEM==\"usb\", ATTR{{idVendor}}==\"{:04x}\", MODE=\"0666\"\r\n\r\nThen reboot your system for the rule to take effect.\r\n\r\n".format(vendor_id))
			else:
				raise FlashForgeError('Unable to connect to FlashForge printer - may already be in use', usberror)
		else:
			if self._handle:
				try:
					self._handle.claimInterface(0)
					self._plugin.on_connect(self)
				except usb1.USBError as usberror:
					raise FlashForgeError('Unable to connect to FlashForge printer - may already be in use', usberror)
			else:
				self._logger.debug("No FlashForge printer found")
				raise FlashForgeError('No FlashForge Printer found')


	@property
	def timeout(self):
		self._logger.debug("FlashForge.timeout()")
		return self._read_timeout


	@timeout.setter
	def timeout(self, value):
		self._logger.debug("Setting read timeout to {}s".format(value))
		self._read_timeout = value


	@property
	def write_timeout(self):
		return self._write_timeout


	def is_ready(self):
		self._logger.debug("is_ready()")
		return self._printerstate == self.STATE_READY


	def is_printing(self):
		self._logger.debug("is_printing()")
		return self._printerstate in self.PRINTING_STATES


	@write_timeout.setter
	def write_timeout(self, value):
		self._logger.debug("Setting write timeout to {}s".format(value))
		self._write_timeout = value


	def write(self, data):
		import time

		self._logger.debug("FlashForge.write() called by thread {}".format(threading.currentThread().getName()))

		# save the length for return on success
		data_len = len(data)
		self._writelock.acquire()

		'''
		if re.match(r'^G\d+', data):
			while not self.is_ready():
				try:
					self._logger.debug("FlashForge.write() wait for ready")
					# success, result = self.sendcommand('~M119\r\n')
					self._handle.bulkWrite(self.ENDPOINT_CMD_IN, '~M119\r\n', int(self._write_timeout * 1000.0))
					time.sleep(0.3)
				except usb1.USBError as usberror:
					self._writelock.release()
					raise FlashForgeError('USB Error write()', usberror)
		'''

		# strip carriage return, etc so we can terminate lines the FlashForge way
		data = data.strip(' \r\n')

		try:
			self._logger.debug("FlashForge.write() {0}".format(data))
			self._handle.bulkWrite(self.ENDPOINT_CMD_IN, '~{}\r\n'.format(data).encode(), int(self._write_timeout * 1000.0))
			# if re.match(r'^(M6|M7|G28)', data):
			#	self._printerstate = self.STATE_UNKNOWN
			self._writelock.release()
			return data_len
		except usb1.USBError as usberror:
			self._writelock.release()
			raise FlashForgeError('USB Error write()', usberror)


	def writeraw(self, data):
		self._logger.debug("FlashForge.writeraw() called by thread {}".format(threading.currentThread().getName()))

		try:
			self._handle.bulkWrite(self.ENDPOINT_CMD_IN, data)
			return len(data)
		except usb1.USBError as usberror:
			raise FlashForgeError('USB Error writeraw()', usberror)


	def readline(self):
		"""
		Supports serial factory - read response from the printer as a \r\n terminated line
		Returns:
			List of lines returned from the printer
		"""
		self._logger.debug("FlashForge.readline() called by thread {}".format(threading.currentThread().getName()))

		self._readlock.acquire()

		if not self._incoming.empty():
			self._readlock.release()
			return self._incoming.get_nowait()

		data = self.readraw()
		if not data.strip().endswith('ok') and len(data):
			data += self.readraw()

		# translate returned data into something Octoprint understands
		if len(data):
			if 'CMD M27 ' in data:
				# need to filter out bogus SD print progress from cancelled or paused prints
				if 'printing byte' in data and self._printerstate in [self.STATE_READY, self.STATE_SD_PAUSED]:
					match = regex_SDPrintProgress.search(data)
					if match:
						try:
							current = int(match.group("current"))
							total = int(match.group("total"))
						except:
							pass
						else:
							if self._printerstate == self.STATE_READY and current >= total:
								# Ultra 3D: after completing print it still indicates SD card progress
								data = "CMD M27 Received.\r\nDone printing file\r\nok\r\n"
							elif self._printerstate == self.STATE_SD_PAUSED:
								# when paused still iindicates printing
								data = "CMD M27 Received.\r\nPrinting paused\r\nok\r\n"
							else:
								# after print is cancelled M27 always looks like its printing from sd card
								data = "CMD M27 Received.\r\nNot SD printing\r\nok\r\n"

			elif 'CMD M114 ' in data:
				# looks like get current position returns A: and B: for extruders?
				data = data.replace(' A:', ' E0:').replace(' B:', ' E1:')

			elif 'CMD M105 ' in data:
				if self._plugin._temp_interval:
					# this was generated as an auto temp report by our keep alive so filter out the CMD and OK
					# so as not to confuse the OctoPrint buffer counter
					data = data.replace('CMD M105 Received.\r\n', '').replace('\r\nok', '')

			elif 'CMD M115 ' in data:
				# Try to make the firmware response more readable by OctoPrint
				# Fake autotemp reporting capability - we can do it as part of the keep alive
				data = data.replace('Firmware:', 'FIRMWARE_NAME: FlashForge VER:').\
					replace('\r\nok', '\r\nCap:AUTOREPORT_TEMP:1\r\nok')

			elif 'CMD M119 ' in data:
				# this was generated by us so do not return anything to OctoPrint
				if 'MachineStatus: READY' in data and 'MoveMode: READY' in data:
					self._printerstate = self.STATE_READY
				elif 'MachineStatus: BUILDING_FROM_SD' in data:
					if 'MoveMode: PAUSED' in data:
						self._printerstate = self.STATE_SD_PAUSED
					else:
						self._printerstate = self.STATE_SD_BUILDING
				else:
					self._printerstate = self.STATE_BUSY
				data = ''

			if len(data):
				# turn data into list of lines
				datalines = data.splitlines()
				for i, line in enumerate(datalines):
					self._incoming.put(line)

					# if M20 (list SD card files) does not return anything, make it look like an empty file list
					if 'CMD M20 ' in line and datalines[i+1] and datalines[i+1] == "ok":
						# fetch SD card list does not get anything so fake out a result
						self._incoming.put('Begin file list')
						self._incoming.put('End file list')
			else:
				self._incoming.put(data)

		else:
			self._incoming.put(data)

		self._readlock.release()
		return self._incoming.get_nowait()


	def readraw(self, timeout=-1):
		"""
		Read everything available from the from the printer
		Returns:
			String containing response from the printer
		"""

		data = ''
		if timeout == -1:
			timeout = int(self._read_timeout * 1000.0)
		self._logger.debug("FlashForge.readraw() called by thread: {}, timeout: {}".format(threading.currentThread().getName(), timeout))

		try:
			# read data from USB until ok signals end or timeout
			while not data.strip().endswith('ok'):
				data += self._handle.bulkRead(self.ENDPOINT_CMD_OUT, self.BUFFER_SIZE, timeout).decode()

		except usb1.USBError as usberror:
			if not usberror.value == -7:  # LIBUSB_ERROR_TIMEOUT:
				raise FlashForgeError('USB Error readraw()', usberror)
			else:
				self._logger.debug("FlashForge.readraw() error: {}".format(usberror))

		self._logger.debug("FlashForge.readraw() {}".format(data.replace('\r\n', ' | ')))
		return data


	def sendcommand(self, cmd, timeout=-1, readresponse=True):
		self._logger.debug("FlashForge.sendcommand() {}".format(cmd).encode())

		self.writeraw("~{}\r\n".format(cmd).encode())
		if not readresponse:
			return True, None

		# read response, make sure we are getting the command we sent
		gcode = "CMD {} ".format(cmd.split(" ", 1)[0])
		response = " "
		while response and gcode not in response:
			response = self.readraw(timeout)
		if "ok\r\n" in response:
			self._logger.debug("FlashForge.sendcommand() got an ok")
			return True, response
		return False, response


	# Obtain exclusive use of the connection for the current thread
	def makeexclusive(self, exclusive):
		if exclusive:
			self._readlock.acquire()
			self._writelock.acquire()
		else:
			self._readlock.release()
			self._writelock.release()


	def close(self):
		self._logger.debug("FlashForge.close()")
		self._incoming = None
		self._plugin.on_disconnect()
		if self._handle:
			try:
				self._handle.releaseInterface(0)
			except Exception:
				pass
			try:
				self._handle.close()
			except usb1.USBError as usberror:
				raise FlashForgeError('Error releasing USB', usberror)
			self._handle = None
