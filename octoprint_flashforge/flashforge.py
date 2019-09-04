import usb1
import threading

try:
	import queue
except ImportError:
	import Queue as queue



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
	STATE_PAUSED = 3
	STATE_HOMING = 4
	STATE_BUSY = 5

	PRINTING_STATES = (STATE_BUILDING, STATE_HOMING)


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
		self._handle = self._context.openByVendorIDAndProductID(vendor_id, device_id)
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
		return self._printerstate == self.STATE_READY


	def is_printing(self):
		return self._printerstate in self.PRINTING_STATES


	@write_timeout.setter
	def write_timeout(self, value):
		self._logger.debug("Setting write timeout to {}s".format(value))
		self._write_timeout = value


	def write(self, data):
		self._logger.debug("FlashForge.write() called by thread {}".format(threading.currentThread().getName()))

		# save the length for return on success
		data_len = len(data)
		self._writelock.acquire()

		# strip carriage return, etc so we can terminate lines the FlashForge way
		data = data.strip(' \r\n')

		try:
			self._logger.debug("FlashForge.write() {0}".format(data))
			self._handle.bulkWrite(self.ENDPOINT_CMD_IN, '~{}\r\n'.format(data).encode(), int(self._write_timeout * 1000.0))
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

		# translate returned data into something Octoprint understands
		if len(data):
			if 'CMD M119 ' in data:
				if 'MachineStatus: READY' in data:
					self._printerstate = self.STATE_READY
				elif 'MachineStatus: BUILDING_FROM_SD' in data:
					if 'MoveMode: PAUSED' in data:
						self._printerstate = self.STATE_PAUSED
					else:
						self._printerstate = self.STATE_BUILDING
				else:
					self._printerstate = self.STATE_BUSY

			elif data.find("CMD M27 ") != -1 and not self._printerstate in self.PRINTING_STATES:
				# after print is cancelled M27 always looks like its printing from sd card
				data = "CMD M27 Received.\r\nok"

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
			data = self._handle.bulkRead(self.ENDPOINT_CMD_OUT, self.BUFFER_SIZE, timeout).decode()
			# read data from USB until ok signals end or timeout
			cmd_done = False
			while not cmd_done:
				newdata = self._handle.bulkRead(self.ENDPOINT_CMD_OUT, self.BUFFER_SIZE, timeout).decode()
				if newdata.strip().endswith('ok'):
					cmd_done = True
				data = data + newdata

		except usb1.USBError as usberror:
			if not usberror.value == -7: # LIBUSB_ERROR_TIMEOUT:
				raise FlashForgeError('USB Error readraw()', usberror.value)

		self._logger.debug("FlashForge.readraw() {}".format(data.replace('\r\n', '  ')))
		return data


	def sendcommand(self, cmd, timeout=-1, readresponse=True):
		self._logger.debug("FlashForge.sendcommand() {}".format(cmd).encode())

		self.writeraw("~{}\r\n".format(cmd).encode())
		if not readresponse:
			return True, None

		# read response
		data = self.readraw(timeout)
		if "ok\r\n" in data:
			self._logger.debug("FlashForge.sendcommand() got an ok")
			return True, data
		return False, data


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
		try:
			self._handle.releaseInterface(0)
		except usb1.USBError as usberror:
			raise FlashForgeError('Error releasing USB', usberror)
