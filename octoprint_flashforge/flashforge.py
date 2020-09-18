import usb1
import threading
import re

try:
	import queue
except ImportError:
	import Queue as queue

from octoprint.settings import settings
from octoprint.events import Events, eventManager


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
	STATE_WAIT_ON_TEMP = 7

	PRINTING_STATES = [STATE_BUILDING, STATE_SD_BUILDING, STATE_SD_PAUSED, STATE_HOMING]

	regex_SDPrintProgress = re.compile(b"(?P<current>[0-9]+)/(?P<total>[0-9]+)")
	""" Regex matching SD print progress from M27. """
	regex_gcode = re.compile(b"^(?P<gcode>[GM][0-9]+)")
	""" Regex matching gcodes in write(). """
	regex_g1 = re.compile(
		b"G[01](?=.* X(?P<X>-?[0-9.]+))?(?=.* Y(?P<Y>-?[0-9.]+))?(?=.* Z(?P<Z>-?[0-9.]+))?(?=.* E(?P<E>-?[0-9.]+))?(?=.* F(?P<F>[0-9.]+))?")
	""" Regex matching move G1 commands for noG91 handling. """
	regex_M114position = re.compile(
		b"X:(?P<X>-?[0-9.]+) Y:(?P<Y>-?[0-9.]+) Z:(?P<Z>-?[0-9.]+) E0:(?P<E0>-?[0-9.]+)( E1:(?P<E1>-?[0-9.]+))?")
	""" Regex matching position values from M114 """

	def __init__(self, plugin, comm, usbcontext, portname, printer, read_timeout=10.0, write_timeout=10.0):
		import logging
		self._logger = logging.getLogger("octoprint.plugins.flashforge")
		self._logger.debug("__init__()")

		self._plugin = plugin
		self._comm = comm
		self._usbcontext = usbcontext
		self._portname = portname
		self._read_timeout = read_timeout
		self._write_timeout = write_timeout
		self._keep_alive_enabled = False
		self._status_time = 0.0
		self._temp_time = 0.0
		self._temp_interval = 0.0
		self._autotemp_enabled = True
		self._is_autotemp = False
		self._incoming = queue.Queue()
		self._readlock = threading.Lock()
		self._writelock = threading.Lock()
		self._printerstate = self.STATE_UNKNOWN
		self._disconnect_event = False

		self._noG91 = False
		self._relative_pos = False
		self._pos = {"X": 0.0, "Y": 0.0, "Z": 0.0, "E0": 0.0, "E1": 0.0}
		self._extruder = "E0"

		self._usb_cmd_endpoint_in = 0
		self._usb_cmd_endpoint_out = 0
		self._usb_sd_endpoint_in = 0
		self._usb_sd_endpoint_out = 0

		for device in self._usbcontext.getDeviceIterator(skip_on_error=True):
			if printer["bus"] == device.getBusNumber() and printer["addr"] == device.getDeviceAddress():
				try:
					self._handle = device.open()
				except usb1.USBErrorAccess:
					eventManager().fire(Events.ERROR, {
						"error": "Found printer but there is a connection problem - check Terminal window for details.",
						"reason": "connection"})
					raise FlashForgeError("\r\n>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>\r\n\r\n"
										  "Unable to connect to FlashForge printer - permission error.\r\n\r\n"
										  "If you are using OctoPi/Linux add permission to access this device by editing file:\r\n /etc/udev/rules.d/99-octoprint.rules\r\n\r\n"
										  "and adding the line:\r\n"
										  "SUBSYSTEM==\"usb\", ATTR{{idVendor}}==\"{:04x}\", MODE=\"0666\"\r\n\r\n"
										  "You can do this as follows:\r\n"
										  "1) Connect to your OctoPi/Octoprint device using ssh\r\n"
										  "2) Type the following to open a text editor:\r\n"
										  "sudo nano /etc/udev/rules.d/99-octoprint.rules\r\n"
										  "3) Add the following line:\r\n"
										  "SUBSYSTEM==\"usb\", ATTR{{idVendor}}==\"{:04x}\", MODE=\"0666\"\r\n"
										  "4) Save the file and close the editor\r\n"
										  "5) Verify the file permissions are set to \"rw-r--r--\" by typing:\r\n"
										  "ls -al /etc/udev/rules.d/99-octoprint.rules\r\n"
										  "6) Reboot your system for the rule to take effect.\r\n\r\n"
										  "<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<\r\n\r\n".format(printer.vid, printer.vid))
				except usb1.USBError as usberror:
					raise FlashForgeError('Unable to connect to FlashForge printer - may already be in use', usberror)
				break

		if not self._handle:
			self._logger.debug("No FlashForge printer found")
			raise FlashForgeError('No FlashForge Printer found')

		try:
			self._handle.claimInterface(0)
		except usb1.USBError as usberror:
			raise FlashForgeError('Unable to connect to FlashForge printer - may already be in use', usberror)

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
							if address & usb1.ENDPOINT_IN:
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


	@property
	def timeout(self):
		"""Return timeout for reads. OctoPrint Serial Factory property"""

		self._logger.debug("timeout()")
		return self._read_timeout


	@timeout.setter
	def timeout(self, value):
		"""Set timeout for reads. OctoPrint Serial Factory property"""

		self._logger.debug("Setting read timeout to {}s".format(value))
		self._read_timeout = value


	@property
	def write_timeout(self):
		"""Return timeout for writes. OctoPrint Serial Factory property"""

		self._logger.debug("write_timeout()")
		return self._write_timeout


	@write_timeout.setter
	def write_timeout(self, value):
		"""Set timeout for writes. OctoPrint Serial Factory property"""

		self._logger.debug("Setting write timeout to {}s".format(value))
		self._write_timeout = value


	@property
	def port(self):
		"""port name. OctoPrint Serial Factory property"""
		return self._portname


	def _valid_command(self, command):
		""" Check if command is valid for FF

		"""
		gcode = command.split(b' ', 1)[0]
		return (gcode[0] in b"GM") and gcode not in [b"M117"]


	def keep_alive(self):
		"""Keep printer connection alive

		Some printers drop the connection if they don't receive something at least every 4s, so we will send M119 to
		get status every few seconds.
		Also use for auto-reporting temperature so we can pass temp to Octoprint when the print queue is blocked by
		printer waiting for heatup, etc otherwise OctoPrint will think the printer is not responding...
		"""
		exit_flag = threading.Event()
		self._status_time = 0.0
		self._temp_time = 0.0
		keep_alive = 0.5
		self._logger.debug("keep_alive() set to:{}".format(keep_alive))
		# do not queue commands if the connection is going away
		while self._handle and not self._disconnect_event:
			if self._keep_alive_enabled:
				# even though we have blocking on the write() routine we do not want to try to write while uploading to
				# SD etc since it can generate confusion when the upload completes and a keep alive goes through at the
				# same time
				self._temp_time += keep_alive
				if self._temp_interval and self._temp_time >= self._temp_interval:
					# do the fake auto reporting of temp OctoPrint
					self._is_autotemp = True
					self.write(b"M105")
					self._temp_time = 0.0
				self._status_time += keep_alive
				if self._status_time >= 2.0:
					# get status every 2s so printer gets something during long ops
					# Dremel 3D20 seems to require something at least every 2s - other FF printers seem to be able to wait up to 3.5s
					# may want to make this a setting
					self.write(b"M119")
					self._status_time = 0.0
			if exit_flag.wait(timeout=keep_alive):
				exit()


	def enable_keep_alive(self, enable):
		"""Disable keep alive if we are streaming to the printer - eg file upload
		Even though there is blocking on the read/write this helps prevent issues/simplifies
		debugging during file upload and triggering a print
		"""

		self._keep_alive_enabled = enable
		self._temp_time = 0.0
		self._status_time = 0.0


	def on_disconnect_event(self):
		"""Called to signal we are disconnecting"""

		self._disconnect_event = True


	def is_ready(self):
		"""Return true if the printer is idle"""

		self._logger.debug("is_ready()")
		return self._printerstate == self.STATE_READY


	def is_printing(self):
		"""Return true if the printer is in any printing state"""

		self._logger.debug("is_printing()")
		return self._printerstate in self.PRINTING_STATES


	def is_sd_printing(self):
		"""Return true if the printer is in any printing state"""

		self._logger.debug("is_sd_printing()")
		return self._printerstate in [self.STATE_SD_PAUSED, self.STATE_SD_BUILDING]


	def disable_autotemp(self):
		"""Disable simulated auto temp reporting if printer claims to do it"""
		self._autotemp_enabled = False


	def disable_G91(self, disable):
		"""Disable G91 support if prefs indicate printer does not support relative positioning"""
		self._noG91 = disable


	def write(self, data):
		"""Write commands to printer. OctoPrint Serial Factory method

		Formats the commands sent by OctoPrint to make them FlashForge friendly.
		"""

		self._logger.debug("write() called by thread {}".format(threading.currentThread().getName()))
		if not self._handle:
			# do not queue commands if the connection is going away
			return

		# save the length for return on success
		data_len = len(data)

		match = FlashForge.regex_gcode.search(data)
		if match:
			try:
				gcode = match.group("gcode")
			except:
				pass

		self._writelock.acquire()

		# strip carriage return, etc so we can terminate lines the FlashForge way
		data = data.strip(b" \r\n")
		# try to filter out garbage commands (we need to replace with something harmless)
		# do this here instead of octoprint.comm.protocol.gcode.sending hook so DisplayLayerProgress plugin will work
		if len(data) and not self._valid_command(data):
			self._logger.debug("filtering command {0}".format(data.decode()))
			data = b"G4 S0"
		else:
			# special handling for relative positioning support
			cmd = data.split(b' ', 1)
			payload = b"" if len(cmd) == 1 else cmd[1]
			gcode = cmd[0]

			if gcode in [b"G0", b"G1"] and self._noG91 and self._relative_pos:
				# try to convert relative positioning to absolute
				self._logger.debug("G1 with rel pos")
				match = FlashForge.regex_g1.search(data)
				if match:
					self._logger.debug("G1 {0}".format(match.groupdict()))
					data = b"G1"
					for k, v in match.groupdict().items():
						if v != None:
							if k in ['X', 'Y', 'Z']:
								v = self._pos[k] + float(v)
								data += b" %s%06.4f" % (k.encode(), v)
							elif k == 'E':
								self._logger.debug("extruder {}, {}".format(self._extruder, self._pos[self._extruder]))
								v = self._pos[self._extruder] + float(v)
								data += b" %s%06.4f" % (k.encode(), v)
							else:
								v = int(v)
								data += b" %s%d" % (k.encode(), v)
			elif gcode == b"G90":
				self._relative_pos = False
			elif gcode == b"G91":
				self._relative_pos = True
				if self._noG91:
					data = b"G90"
			elif gcode == b"M23":
				# we started an SD print - make sure to set printer state
				self._status_time = 0.0
				data += b"\r\nM119"
			elif gcode == b"M27":
				# make sure we have the current printer status before getting SD card progress, because SD card
				# progress reports printing when cancelled or finished...
				self._status_time = 0.0
				data = b"M119\r\n~M27"
				self._status_time = 0.0
			elif gcode == b"M105":
				self._temp_time = 0.0
			elif gcode == b"M108":
				self._extruder = "E1" if b"T1" in payload else "E0"
				self._logger.debug("select extruder {0}".format(self._extruder))

		try:
			self._logger.debug("write() {0}".format(data.decode()))
			self._handle.bulkWrite(self._usb_cmd_endpoint_out, b"~%s\r\n" % data, int(self._write_timeout * 1000.0))
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

		self._logger.debug("writeraw() called by thread {}".format(threading.currentThread().getName()))

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

		self._logger.debug("readline() called by thread {}".format(threading.currentThread().getName()))

		self._readlock.acquire()

		# return any line we have buffered
		if not self._incoming.empty():
			self._readlock.release()
			return self._incoming.get_nowait()

		# fetch some data
		data = self.readraw()
		# parse and buffer it
		data = self._parse_data(data)

		self._logger.debug("readline() returning: {}".format(data.decode().replace('\r\n', ' | ')))
		self._readlock.release()
		# return the buffer
		return self._incoming.get_nowait()


	def _parse_data(self, data):
		"""Parse raw data from printer into lines and buffer them

		Manipulates printer response if necessary into something OctoPrint understands, breaks into lines and stores
		in a buffer for readline() method.
		"""
		if len(data):
			if b"CMD M27 " in data:
				# need to filter out bogus SD print progress from cancelled or paused prints
				if b"printing byte" in data and self._printerstate in [self.STATE_UNKNOWN, self.STATE_READY, self.STATE_SD_PAUSED]:
					match = FlashForge.regex_SDPrintProgress.search(data)
					if match:
						try:
							current = int(match.group("current"))
							total = int(match.group("total"))
						except:
							pass
						else:
							# Note: there is an issue with .gx files indicating the current byte size is greater than the
							# total when the print is started
							if self._printerstate == self.STATE_READY and current >= total:
								# Ultra 3D: after completing print it still indicates SD card progress
								data = b"CMD M27 Received.\r\nDone printing file\r\nok\r\n"
							elif self._printerstate == self.STATE_SD_PAUSED:
								# when paused still indicates printing
								data = b"CMD M27 Received.\r\nPrinting paused\r\nok\r\n"
							elif self._printerstate != self.STATE_UNKNOWN:
								# after print is cancelled M27 always looks like its printing from sd card
								data = b"CMD M27 Received.\r\nNot SD printing\r\nok\r\n"
				elif not data.strip().endswith(b"ok"):
					# for Dremel 3D20 not responding correctly when not printing from SD card:
					if self._printerstate == self.STATE_READY:
						data = b"CMD M27 Received.\r\nDone printing file\r\nok\r\n"
					else:
						data += b"ok\r\n"

			elif b"CMD M105 " in data:
				if self._is_autotemp:
					# this was generated as an auto temp report by our keep alive so filter out the CMD and OK
					# so as not to confuse the OctoPrint buffer counter
					data = data.replace(b"CMD M105 Received.\r\n", b"")
					# TODO: add " W:?" to the string to indicate that the printer is waiting to get to temp if state
					#  indicates waiting on tool or bed. This should prevent OctoPrint from triggering timeouts?
					if not (b"CMD " in data and self._printerstate in [self.STATE_SD_BUILDING, self.STATE_SD_PAUSED]):
						# do not drop the "ok" if there is the response to another command in here and we are printing from SD?
						data = data.replace(b"\r\nok", b"")
				self._is_autotemp = False

			elif b"CMD M114 " in data:
				# looks like get current position returns A: and B: for extruders?
				data = data.replace(b" A:", b" E0:").replace(b" B:", b" E1:")
				match = FlashForge.regex_M114position.search(data)
				if match:
					for k, v in match.groupdict().items():
						if v != None:
							self._pos[k] = float(v)
					self._logger.debug("pos: {}".format(self._pos))

			elif b"CMD M115 " in data:
				# Try to make the firmware response more readable by OctoPrint
				data = data.replace(b"Firmware:", b"FIRMWARE_NAME: FlashForge VER:")

			elif b"CMD M119 " in data:
				# this was generated by us so do not return anything to OctoPrint
				oldstate = self._printerstate
				if b"MachineStatus: READY" in data:
					if b"MoveMode: READY" in data:
						self._printerstate = self.STATE_READY
					elif b"MoveMode: WAIT_ON_" in data:
						# printing directly and printer waiting for bed or extruder to heat up
						self._printerstate = self.STATE_WAIT_ON_TEMP
					else:
						self._printerstate = self.STATE_BUSY
				elif b"MachineStatus: BUILDING_FROM_SD" in data:
					if b"MoveMode: PAUSED" in data:
						self._printerstate = self.STATE_SD_PAUSED
					else:
						self._printerstate = self.STATE_SD_BUILDING
				else:
					self._printerstate = self.STATE_BUSY
				# Remove M119 response (assuming it is the last part of the response, other command may be at the front)
				# Typically if something is prepended, it will be a move related command.
				data = data.split(b"CMD M119 ")[0]
				if len(data) and (self._printerstate == self.STATE_READY or self._printerstate == self.STATE_SD_PAUSED):
					# If the printer is still moving it will send the ok associated with the command later. If it has
					# completed the movement a separate ok is never sent so we add it here
					data += b"ok\r\n"

				if oldstate != self._printerstate:
					self._logger.debug("state changed from {} to {}".format(oldstate, self._printerstate))
					# force temp reporting if busy while direct printing and waiting for extruder/bed to heat up
					# (unless printer reports autotemp) so OctoPrint sees something.
					# TODO: use OctoPrint state instead to decide when to do the temp check - ie if printing and temp wait
					if self._printerstate == self.STATE_WAIT_ON_TEMP and self._autotemp_enabled:
						self._temp_interval = settings().getFloat(["serial", "timeout", "temperatureAutoreport"])
					else:
						self._temp_interval = 0.0

			if len(data):
				# turn data into list of lines
				datalines = data.splitlines()
				for i, line in enumerate(datalines):
					self._logger.debug("buffering: {}".format(line))
					self._incoming.put(line)

					# if M20 (list SD card files) does not return anything, make it look like an empty file list
					if b"CMD M20 " in line and datalines[i+1] and datalines[i+1] == b"ok":
						# fetch SD card list does not get anything so fake out a result
						self._incoming.put(b"Begin file list")
						self._incoming.put(b"End file list")
			else:
				self._incoming.put(data)

		else:
			self._incoming.put(data)

		return data


	def readraw(self, timeout=-1):
		"""
		Read everything available from the from the printer

		Returns:
			String containing response from the printer
		"""

		data = b""
		if timeout == -1:
			timeout = int(self._read_timeout * 1000.0)
		self._logger.debug("readraw() called by thread: {}, timeout: {}".format(threading.currentThread().getName(), timeout))

		try:
			# read data from USB until ok signals end or timeout
			while not data.strip().endswith(b"ok"):
				data += self._handle.bulkRead(self._usb_cmd_endpoint_in, self.BUFFER_SIZE, timeout)

		except usb1.USBError as usberror:
			if not usberror.value == -7:  # LIBUSB_ERROR_TIMEOUT:
				raise FlashForgeError("USB Error readraw()", usberror)
			else:
				self._logger.debug("readraw() error: {}".format(usberror))

		self._logger.debug("readraw() {}".format(data.decode().replace("\r\n", " | ")))
		return data


	def sendcommand(self, cmd, timeout=-1, readresponse=True):
		self._logger.debug("sendcommand() {}".format(cmd.decode()))

		self.writeraw(b"~%s\r\n" % cmd)
		if not readresponse:
			return True, None

		# read response, make sure we are getting the command we sent
		gcode = b"CMD %s " % cmd.split(b" ", 1)[0]
		response = b""
		while True:
			response = self.readraw(timeout)
			# TODO: if response is multiline and contains response to a previous command as well as this one then
			#  we lose the previous command. We might need to parse each line and save old responses into the buffer
			if not response or gcode in response:
				break
			# we got the response from some previous OctoPrint command so parse it into the buffer used for
			# OctoPrint listener so it will be read later
			self._parse_data(response)
		if b"ok\r\n" in response:
			self._logger.debug("sendcommand() got an ok")
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

		self._logger.debug("close()")
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
				raise FlashForgeError("Error releasing USB", usberror)
			self._handle = None
