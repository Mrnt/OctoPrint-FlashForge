import usb1


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


	def __init__(self, seriallog_handler=None, read_timeout=10.0, write_timeout=10.0):
		import logging
		self._logger = logging.getLogger("octoprint.plugins.octoprint_flashforge")
		self._logger.debug("FlashForge.__init__()")

		# USB ID's - device ID will need to be changed to match printer model
		self.vendorid = 0x2b71		# FlashForge
		self.deviceid = 0x00ff		# Dreamer
		# self.deviceid = 0x0001	# PowerSpec Ultra

		self._read_timeout = read_timeout
		self._write_timeout = write_timeout
		self._incoming = queue.Queue()

		self._context = usb1.USBContext()
		self._handle = self._context.openByVendorIDAndProductID(self.vendorid, self.deviceid)
		if self._handle:
			try:
				self._handle.claimInterface(0)
				# self.gcodecmd("M601 S0")
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
		self._logger.debug("FlashForge.write() {0}".format(data))

		# we don't support these commands
		data_len = len(data)

		# strip carriage return, etc so we can terminate lines the FlashForge way
		data = data.strip(' \r\n')
		if len(data) == 0 or data.find("M110") != -1:
			# replace the default hello command with something recognized
			data = "M601 S0"

		# FlashForge uses "M107" to turn fan off not "M106 S0"
		elif data.find("M106") != -1:
			if "S0" in data:
				data = "M107"

		try:
			self._handle.bulkWrite(self.ENDPOINT_CMD_IN, '~{0}\r\n'.format(data).encode())
			return data_len
		except usb1.USBError as usberror:
			raise FlashForgeError('USB Error', usberror)


	def readline(self):
		self._logger.debug("FlashForge.readline()")

		if not self._incoming.empty():
			return self._incoming.get_nowait()

		try:
			# read data from USB until ok signals end
			data = ''
			cmd_done = False
			while not cmd_done:
				newdata = self._handle.bulkRead(self.ENDPOINT_CMD_OUT, self.BUFFER_SIZE, int(self._read_timeout * 1000.0)).decode()
				if newdata.strip().endswith('ok'):
					cmd_done = True
				data = data + newdata

			# decode data
			data = data.replace('\r', '')
			self._logger.debug(data.replace('\n', '  '))
			datalines = data.splitlines()
			for i, line in enumerate(datalines):
				self._incoming.put(line)

				if not line.find("CMD M20") == -1 and datalines[i+1] and datalines[i+1] == "ok":
					# fetch SD card list does not get anything so fake out a result
					self._incoming.put('Begin file list')
					self._incoming.put('End file list')

			return self._incoming.get_nowait()

		except usb1.USBError as usberror:
			if not usberror.value == -7: # LIBUSB_ERROR_TIMEOUT:
				raise FlashForgeError('USB Error', usberror.value)
		return ""


	def gcodecmd(self, cmd):
		self._logger.debug("FlashForge.gcodecmd() ~{0}".format(cmd).encode())

		self.write(cmd)
		# read response
		while True:
			if self.readline() == "":
				break


	def close(self):
		self._logger.debug("FlashForge.close()")
		self._incoming = None
		try:
			self._handle.releaseInterface(0)
		except usb1.USBError as usberror:
			raise FlashForgeError('Error releasing USB', usberror)
