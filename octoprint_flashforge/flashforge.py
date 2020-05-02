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
	BUFFER_SIZE = 512

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
		self._usb_cmd_endpoint_in = 0
		self._usb_cmd_endpoint_out = 0
		self._usb_sd_endpoint_in = 0
		self._usb_sd_endpoint_out = 0

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
					self._logger.debug("claimed USB interface")
					device = self._handle.getDevice()
					# look for an in and out endpoint pair:
					for configuration in device.iterConfigurations():
						for interface in configuration:
							for setting in interface:
								self._logger.debug(" setting number: 0x{:02x}, class: 0x{:02x}, subclass: 0x{:02x}, protocol: 0x{:02x}, #endpoints: {}".format(
									setting.getNumber(), setting.getClass(), setting.getSubClass(), setting.getProtocol(), setting.getNumEndpoints()))
								endpoint_in = 0
								endpoint_out = 0
								for endpoint in setting:
									self._logger.debug("  found endpoint type {} at address 0x{:02x}, max packet size {}".
										format(usb1.libusb1.libusb_transfer_type.get(endpoint.getAttributes()),
										endpoint.getAddress(),
										endpoint.getMaxPacketSize()))
									if usb1.libusb1.libusb_transfer_type.get(endpoint.getAttributes()) == 'LIBUSB_TRANSFER_TYPE_BULK':
										address = endpoint.getAddress()
										if address & usb1.libusb1.LIBUSB_ENDPOINT_IN:
											endpoint_in = address
										else:
											endpoint_out = address
										if endpoint_in and endpoint_out:
											# we have a pair of endpoints, assign them as needed
											# assume first pair is for commands, second for SD upload
											if not self._usb_cmd_endpoint_out:
												self._usb_cmd_endpoint_in = endpoint_in
												self._usb_cmd_endpoint_out = endpoint_out
												endpoint_in = endpoint_out = 0
											elif not self._usb_sd_endpoint_out:
												self._usb_sd_endpoint_in = endpoint_in
												self._usb_sd_endpoint_out = endpoint_out
												break
								else:
									continue
								break
							else:
								continue
							break
						else:
							continue
						break
					# if we don't have endpoints for SD upload then use the regular ones
					if not self._usb_sd_endpoint_out:
						self._usb_sd_endpoint_in = self._usb_cmd_endpoint_in
						self._usb_sd_endpoint_out = self._usb_cmd_endpoint_out
					self._logger.debug(
						"  cmd_endpoint_out 0x{:02x}, cmd_endpoint_in 0x{:02x}".
						format(self._usb_cmd_endpoint_out, self._usb_cmd_endpoint_in))
					self._logger.debug(
						"  sd_endpoint_out 0x{:02x}, sd_endpoint_in 0x{:02x}".
						format(self._usb_sd_endpoint_out, self._usb_sd_endpoint_in))
					if not (self._usb_cmd_endpoint_in and self._usb_cmd_endpoint_out):
						self.close()
						raise FlashForgeError('Unable to find USB endpoints - turn on debug output and check octoprint.log')
					self._plugin.on_connect(self)

				except usb1.USBError as usberror:
					raise FlashForgeError('Unable to connect to FlashForge printer - may already be in use', usberror)

			else:
				self._logger.debug("No FlashForge printer found")
				raise FlashForgeError('No FlashForge Printer found')


	@property
	def timeout(self):
		"""Return timeout for reads. OctoPrint Serial Factory property"""

		self._logger.debug("FlashForge.timeout()")
		return self._read_timeout


	@timeout.setter
	def timeout(self, value):
		"""Set timeout for reads. OctoPrint Serial Factory property"""

		self._logger.debug("Setting read timeout to {}s".format(value))
		self._read_timeout = value


	@property
	def write_timeout(self):
		"""Return timeout for writes. OctoPrint Serial Factory property"""

		self._logger.debug("FlashForge.write_timeout()")
		return self._write_timeout


	@write_timeout.setter
	def write_timeout(self, value):
		"""Set timeout for writes. OctoPrint Serial Factory property"""

		self._logger.debug("Setting write timeout to {}s".format(value))
		self._write_timeout = value


	def is_ready(self):
		"""Return true if the printer is idle"""

		return self._printerstate == self.STATE_READY


	def is_printing(self):
		"""Return true if the printer is in any printing state"""

		return self._printerstate in self.PRINTING_STATES


	def write(self, data):
		"""Write commands to printer. OctoPrint Serial Factory method

		Formats the commands sent by OctoPrint to make them FlashForge friendly.
		"""

		self._logger.debug("FlashForge.write() called by thread {}".format(threading.currentThread().getName()))

		# save the length for return on success
		data_len = len(data)
		self._writelock.acquire()

		# strip carriage return, etc so we can terminate lines the FlashForge way
		data = data.strip(' \r\n')

		try:
			self._logger.debug("FlashForge.write() {0}".format(data))
			self._handle.bulkWrite(self._usb_cmd_endpoint_out, '~{}\r\n'.format(data).encode(), int(self._write_timeout * 1000.0))
			self._writelock.release()
			return data_len
		except usb1.USBError as usberror:
			self._writelock.release()
			raise FlashForgeError('USB Error write()', usberror)


	def writeraw(self, data, command = True):
		"""Write raw data to printer.

		data: bytearray to send
		command: True to send g-code, False to send to upload SD card
		"""

		self._logger.debug("FlashForge.writeraw() called by thread {}".format(threading.currentThread().getName()))

		try:
			self._handle.bulkWrite(self._usb_cmd_endpoint_out if command else self._usb_sd_endpoint_out, data)
			return len(data)
		except usb1.USBError as usberror:
			raise FlashForgeError('USB Error writeraw()', usberror)


	def readline(self):
		"""Read line worth of response from printer. OctoPrint Serial Factory method

		Read response from the printer and store as a series of \r\n terminated lines
		OctoPrint reads response line by line..

		Returns:
			List of lines returned from the printer
		"""

		self._logger.debug("FlashForge.readline() called by thread {}".format(threading.currentThread().getName()))

		self._readlock.acquire()

		if not self._incoming.empty():
			self._readlock.release()
			return self._incoming.get_nowait()

		data = self.readraw()

		# translate returned data into something OctoPrint understands
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
								# when paused still indicates printing
								data = "CMD M27 Received.\r\nPrinting paused\r\nok\r\n"
							else:
								# after print is cancelled M27 always looks like its printing from sd card
								data = "CMD M27 Received.\r\nNot SD printing\r\nok\r\n"

			elif 'CMD M114 ' in data:
				# looks like get current position returns A: and B: for extruders?
				data = data.replace(' A:', ' E0:').replace(' B:', ' E1:')

			elif 'CMD M119 ' in data:
				if 'MachineStatus: READY' in data:
					self._printerstate = self.STATE_READY
				elif 'MachineStatus: BUILDING_FROM_SD' in data:
					if 'MoveMode: PAUSED' in data:
						self._printerstate = self.STATE_SD_PAUSED
					else:
						self._printerstate = self.STATE_SD_BUILDING
				else:
					self._printerstate = self.STATE_BUSY


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
			# read data from USB until ok signals end or timeout
			while not data.strip().endswith('ok'):
				data += self._handle.bulkRead(self._usb_cmd_endpoint_in, self.BUFFER_SIZE, timeout).decode()

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


	def makeexclusive(self, exclusive):
		"""	Obtain exclusive use of the connection for the current thread"""

		if exclusive:
			self._readlock.acquire()
			self._writelock.acquire()
		else:
			self._readlock.release()
			self._writelock.release()


	def close(self):
		"""	Close USB connection and cleanup. OctoPrint Serial Factory method"""

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
