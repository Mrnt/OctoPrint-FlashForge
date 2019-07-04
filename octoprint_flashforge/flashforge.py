import usb1
import threading


try:
	import queue
except ImportError:
	import Queue as queue



class FlashForgeError(Exception):
	def __init__(self, message, error=0):
		super(FlashForgeError, self).__init__("{0} ({1})".format(message, error))
		self.error = error



class FlashForge(object):
	ENDPOINT_CMD_IN = 0x81
	ENDPOINT_CMD_OUT = 0x01
	ENDPOINT_DATA_IN = 0x83
	ENDPOINT_DATA_OUT = 0x03
	BUFFER_SIZE = 128


	def __init__(self, plugin, comm, seriallog_handler=None, read_timeout=10.0, write_timeout=10.0):
		import logging
		self._logger = logging.getLogger("octoprint.plugins.flashforge")
		self._logger.debug("FlashForge.__init__()")

		# USB ID's - device ID will need to be changed to match printer model
		self.vendorid = 0x2b71		# FlashForge
		# self.deviceid = 0x0001	# Dreamer
		self.deviceid = 0x00ff		# PowerSpec Ultra

		self._plugin = plugin
		self._comm = comm
		self._read_timeout = read_timeout
		self._write_timeout = write_timeout
		self._incoming = queue.Queue()
		self._fileTX = False
		self._readlock = threading.Lock()
		self._writelock = threading.Lock()

		self._context = usb1.USBContext()
		self._handle = self._context.openByVendorIDAndProductID(self.vendorid, self.deviceid)
		if self._handle:
			try:
				self._handle.claimInterface(0)
				self._plugin.on_connect(self)
				# self.send_and_wait("M601 S0")
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
		if not self._fileTX:
			data = data.strip(' \r\n')

			# change the default hello
			if len(data) == 0 or data.find("M110") != -1:
				# replace the default hello command with something recognized
				data = "M601 S0"

			#			elif data.find("M28 /") != -1:
			#				data = data.replace("M28 /", "M28 {} 0:/user/".format(self._comm._currentFile.getFilesize()))

			elif data.find("M29") != -1:
				self._fileTX = False

			# FlashForge uses "M107" to turn fan off not "M106 S0"
			elif data.find("M106") != -1:
				if "S0" in data:
					data = "M107"

		try:
			self._logger.debug("FlashForge.write() {0}".format(data))
			#			if self._fileTX:
			#				self._handle.bulkWrite(self.ENDPOINT_CMD_IN, data, int(self._write_timeout * 1000.0))
			#			else:
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
		import time

		"""
		#self._logger.debug("FlashForge.readline()")
		if self._fileTX:
			self._logger.debug("FlashForge.readline() returning on _fileTX")
			time.sleep(self._read_timeout)
			return "ok"
		"""
		if not self._incoming.empty():
			return self._incoming.get_nowait()
		"""
		ext = 'false'
		if self._comm._extStreaming:
			ext = 'true'
		#self._logger.debug("FlashForge.readline() _extStreaming:{}".format(ext))
		if self._comm.isStreaming():
			return "ok"
		"""
		self._logger.debug("FlashForge.readline() called by thread {}".format(threading.currentThread().getName()))
		"""
		if self._comm.isStreaming():
			self._logger.debug("FlashForge.readline() _comm.isStreaming")
			data = "ok"
		else:
			data = self.readraw()
		"""

		self._readlock.acquire()
		data = self.readraw()

		# decode data
		datalines = data.splitlines()
		for i, line in enumerate(datalines):
			self._incoming.put(line)

			if not line.find("CMD M20 ") == -1 and datalines[i+1] and datalines[i+1] == "ok":
				# fetch SD card list does not get anything so fake out a result
				self._incoming.put('Begin file list')
				self._incoming.put('End file list')

			#if not line.find("CMD M28 ") == -1 and datalines[i+2] and datalines[i+2] == "ok":
			#	self._fileTX = False

		self._readlock.release()
		return self._incoming.get_nowait()


	def readraw(self, timeout=-1):
		"""
		Read everything available from the from the printer
		Returns:
			String containing response from the printer
		"""
		self._logger.debug("FlashForge.readraw() called by thread {}".format(threading.currentThread().getName()))

		data = ''
		if timeout == -1:
			timeout = int(self._read_timeout * 1000.0)

		try:
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
			#elif self._fileTX:
			#	return "ok"

		self._logger.debug("FlashForge.readraw() {}".format(data.replace('\r\n', '  ')))
		return data


	def send_and_wait(self, cmd, timeout=-1):
		self._logger.debug("FlashForge.send_and_wait() {}".format(cmd).encode())

		self.writeraw("~{}\r\n".format(cmd).encode())

		# read response
		"""
		while True:
			data = self.readraw()
			if data.find(" ok\r\n"):
				self._logger.debug("FlashForge.send_and_wait() got an ok")
				break
		return True
		"""
		data = self.readraw(timeout)
		if data.find("ok\r\n") != -1:
			self._logger.debug("FlashForge.send_and_wait() got an ok")
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
