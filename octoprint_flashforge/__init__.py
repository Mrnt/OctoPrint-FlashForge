# coding=utf-8
from __future__ import absolute_import

import threading
import usb1
import re
import octoprint.plugin
from octoprint.settings import default_settings
from octoprint.util import dict_merge
from octoprint.events import Events, eventManager

from . import flashforge

'''
Special case support:

G91 (relative positioning) appears not to be supported by Finder 2, Guider 2 (F2G2). Made into printer profile option
(ff.noG91) so users can enable as appropriate. Flag is also used to special case other F2G2 issues such as:
- F2G2 does not appear to support "G28 X Y"
'''


class FlashForgePlugin(octoprint.plugin.SettingsPlugin,
					   octoprint.plugin.AssetPlugin,
					   octoprint.plugin.TemplatePlugin):
	VENDOR_IDS = {0x0315: "PowerSpec", 0x2a89: "Dremel", 0x2b71: "FlashForge"}
	PRINTER_PROFILES = {
		0x0315: {
			0x0001: {"name": "Ultra 3DPrinter (C)"}},  # PowerSpec
		0x2a89: {
			0x8889: {"name": "Dremel IdeaBuilder 3D20"}, 0x888d: {"name": "Dremel IdeaBuilder 3D45"}},  # Dremel
		0x2b71: {
			0x0001: {"name": "Dreamer"}, 0x0002: {"name": "Finder v1"},  # FlashForge
			0x0004: {"name": "Guider II"}, 0x0005: {"name": "Inventor"},
			0x0007: {"name": "Finder v2", "noG28XY": True, "noM132": True},
			0x0009: {"name": "Guider IIs"}, 0x000A: {"name": "Dreamer NX"},
			0x00e7: {"name": "Creator Max"}, 0x00ee: {"name": "Finder v2.12"},
			0x00f6: {"name": "PowerSpec Ultra 3DPrinter (B)"},
			0x00ff: {"name": "PowerSpec Ultra 3DPrinter (A)"}}}
	FILE_PACKET_SIZE = 1024


	def __init__(self):
		import logging

		self._logger = logging.getLogger("octoprint.plugins.flashforge")
		self._logger.debug("__init__")
		self._comm = None
		self._serial_obj = None
		self._currentFile = None
		self._usbcontext = None
		self._printers = {}
		self._printer_profile = {}
		# FlashForge friendly default connection settings
		self._conn_settings = {
			'firmwareDetection': False,				# do not try to auto detect firmware
			'sdAlwaysAvailable': True,				# FF printers always(?) have the internal SD card available
			'neverSendChecksum': True,				# FF protocol does not use command checksums
			'helloCommand': "M601 S0",				# FF hello command and set communication to USB
			'abortHeatupOnCancel': False			# prevent sending of M108 command which doesn't work
		}
		self._feature_settings = {
			'autoUppercaseBlacklist': ['M146']		# LED control requires lowercase r,g,b
		}
		default_settings["serial"] = dict_merge(default_settings["serial"], self._conn_settings)
		default_settings["feature"] = dict_merge(default_settings["feature"], self._feature_settings)

		self._logger.info("libusb1: {}".format(usb1.__version__))


	##~~ SettingsPlugin mixin
	def get_settings_defaults(self):
		# add default value ff.noG91 to printer profiles or the setting won't get saved by OctoPrint
		profiles = self._printer_profile_manager.get_all()
		self._printer_profile_manager.default["ff"] = dict(noG91=False)
		for k, profile in profiles.items():
			profile = dict_merge(self._printer_profile_manager.default, profile)
			self._printer_profile_manager.save(profile, True)

		# plugin default settings here
		return dict(
			ledStatus=1,
			ledColor=[255, 255, 255]
		)


	##~~ AssetPlugin mixin
	def get_assets(self):
		# List of plugin asset files to automatically include in the core UI.
		return dict(
			js=["js/flashforge.js", "js/color-picker.min.js"],
			css=["css/color-picker.min.css"]
		)


	##~~ Softwareupdate hook
	def get_update_information(self):
		# Plugin specific configuration to use with the Software Update Plugin.
		# See https://github.com/foosel/OctoPrint/wiki/Plugin:-Software-Update for details.
		return dict(
			flashforge=dict(
				displayName="FlashForge Plugin",
				displayVersion=self._plugin_version,

				# version check: github repository
				type="github_release",
				user="Mrnt",
				repo="OctoPrint-FlashForge",
				current=self._plugin_version,

				# update method: pip
				pip="https://github.com/Mrnt/OctoPrint-FlashForge/archive/{target_version}.zip"
			)
		)


	# Look for a supported printer
	def detect_printer(self):
		self._logger.debug("detect_printer()")
		if self._serial_obj:
			return self._printers

		self._printers = {}
		if not self._usbcontext:
			self._usbcontext = usb1.USBContext()
			self._usbcontext.open()

		for device in self._usbcontext.getDeviceIterator(skip_on_error=True):
			vendor_id = device.getVendorID()
			device_id = device.getProductID()
			device_name = 'unknown device'
			try:
				# this will typically fail if we don't have permission to access this USB device
				device_name = device.getProduct()
			except usb1.USBError as usberror:
				self._logger.debug('Unable to get device name {}'.format(usberror))
			self._logger.debug(
				"Found device '{}' with Vendor ID: {:#06X}, USB ID: {:#06X}".format(device_name, vendor_id,
																					device_id))

			if vendor_id in self.VENDOR_IDS:
				# we have a printer of some kind
				bus = device.getBusNumber()
				addr = device.getDeviceAddress()
				device_name += ", port:{}:{}".format(bus, addr)
				vendor_name = self.VENDOR_IDS[vendor_id]
				self._logger.info("Found a {} {}".format(vendor_name, device_name))
				self._printers[device_name] = {'bus': bus, 'addr': addr, 'vid': vendor_id, 'did': device_id}


	def printer_factory(self, comm, portname, baudrate, read_timeout, *args, **kwargs):
		""" OctoPrint hook - Called when creating printer connection

			Test for presence of a supported printer and then try to connect
		"""
		if portname not in self._printers:
			# requested port not in our list
			return None

		self._comm = comm
		serial_obj = flashforge.FlashForge(self, comm, self._usbcontext, portname, self._printers[portname],
										   read_timeout=float(read_timeout))
		if self._printers[portname]["did"] in self.PRINTER_PROFILES[self._printers[portname]["vid"]]:
			self._printer_profile = self.PRINTER_PROFILES[self._printers[portname]["vid"]][self._printers[portname]["did"]]
		else:
			self._printer_profile = {}
		return serial_obj


	def get_additional_port_names(self, *args, **kwargs):
		""" OctoPrint hook - Called when populating Serial Port list
		"""
		self.detect_printer()
		printers = self._printers.keys()
		return printers


	def printer_capabilities(self, comm_instance, capability, enabled, already_defined, *args, ** kwargs):
		""" OctoPrint hook - Called with printer capabilities
		"""
		if capability == "AUTOREPORT_TEMP":
			self._serial_obj.disable_autotemp()


	def get_extension_tree(self, *args, **kwargs):
		""" OctoPrint hook - Return supported file extensions for SD upload

			Note not called when printer connects, only when starting up and when the printer disconnects
		"""
		self._logger.debug("get_extension_tree()")
		return dict(
			machinecode=dict(
				g3drem=["g3drem"],	# Dremel
				gx=["gx"]			# Every other FlashForge based printer
			)
		)


	def on_connect(self, serial_obj):
		self._logger.debug("on_connect()")
		self._serial_obj = serial_obj


	def on_disconnect(self):
		self._logger.debug("on_disconnect()")
		self._serial_obj = None


	# Flag F2G2
	def G91_disabled(self):
		profile = self._printer_profile_manager.get_current_or_default()
		return "ff" in profile and "noG91" in profile["ff"] and profile["ff"]["noG91"]


	# Called when gcode commands are being placed in the queue by OctoPrint:
	# Mostly important for control panel or translating and printing non FlashPrint file directly from OctoPrint
	def rewrite_gcode(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
		if self._serial_obj:

			# Commands should begin with G,M,T
			if not re.match(r'^[GMT]\d+', cmd):
				# most likely part of the header in a .gx FlashPrint file
				self._logger.debug("rewrite_gcode(): unrecognized command")
				return []

			self._logger.debug("rewrite_gcode(): gcode:{}, cmd:{}".format(gcode, cmd))

			# TODO: detect printer state earlier in connection process and don't send M146, etc if the printer
			#  is already busy when we connect
			# TODO: filter M146 and other commands? when printing from SD because they cause comms to hang

			# allow a very limited set of commands while printing from SD to minimize problems...
			if self._serial_obj.is_sd_printing() and gcode not in ["M24", "M25", "M26", "M27", "M105", "M110", "M112", "M114", "M115", "M117", "M400"]:
				cmd = []

			# homing
			elif gcode == "G28":
				cmd = cmd.replace('0', '')
				if cmd == "G28 X Y" and "noG28XY" in self._printer_profile:
					# F2G2: does not support "G28 X Y"?
					cmd = ["G28 X", "G28 Y"]

			# relative positioning
			elif gcode == "G91":
				if self.G91_disabled():
					# F2G2: try to convert relative positioning to absolute so add in some commands
					self._serial_obj.disable_G91(True)
					cmd = [("G91", cmd_type), "M114"]
				else:
					self._serial_obj.disable_G91(False)

			# M20 list SD card, M21 init SD card - do not work and some printers may not respond causing timeouts,
			# so ignore them
			elif (gcode == "M20" or gcode == "M21"):
				cmd = []

			# M25 = pause
			elif gcode == "M25":
				# pause during cancel causes issues
				if comm_instance.isCancelling():
					cmd = []

			# M26 is sent by OctoPrint during SD prints:
			# M26 in Marlin = set SD card position : FlashForge = cancel
			elif gcode == "M26":
				# M26 S0 generated during OctoPrint cancel - use it to send cancel
				if (cmd == "M26 S0" and comm_instance.isCancelling()) or cmd == "M26":
					cmd = [("M26", cmd_type)]
				else:
					cmd = []

			# M82 in Marlin = extruder abs positioning : FlashForge = undefined?
			elif gcode == "M82":
				cmd = []

			# M83 in Marlin = extruder rel positioning : FlashForge = undefined?
			elif gcode == "M83":
				cmd = []

			# M84 by default sent when OctoPrint cancelling print
			# M84 in Marlin = disable steppers : M18 is FlashForge equivalent
			elif gcode == "M84":
				cmd = ["M18"]

			# M106 S0 is sent by OctoPrint control panel:
			# M106 S0 in Marlin = fan off : M107 is FlashForge equivalent
			elif gcode == "M106":
				if "S0" in cmd:
					cmd = ["M107"]

			# M108 is sent by OctoPrint during SD cancel if abortHeatupOnCancel is set:
			# M108 in Marlin = stop heat wait & continue : FlashForge M108 Tx = change toolhead (no equivalent?),
			# drop if this is the command
			elif cmd == "M108":
				cmd = []

			# M109 in Marlin = wait for extruder temp : M6 in FlashForge (this may need to be moved to the write() method)
			elif gcode == "M109":
				cmd = [cmd.replace("M109", "M6")]

			# M110 is sent by OctoPrint as default hello but also when connected:
			# M110 Set line number/hello in Marlin : FlashForge uses M601 S0 to take control via USB
			elif gcode == "M110":
				# if we connected and the printer is already printing then trigger an M27 so we can trigger a file open
				# for OctoPrint
				if self._serial_obj.is_sd_printing() and not self._comm.isSdFileSelected():
					cmd = ["M27"]
				else:
					cmd = []

			# M119 get status we generate automatically so skip this
			elif gcode == "M119":
				cmd = []

			# M132 load default positions does not work at command line for some printers
			elif gcode == "M132" and "noM132" in self._printer_profile:
				cmd = []

			# M146 = set LED colors: do not send while printing from SD (does not work, may cause issues)
			elif gcode == "M146" and self._serial_obj.is_sd_printing():
				cmd = []

			# M190 in Marlin = wait for bed temp : M7 in FlashForge
			elif gcode == "M190":
				cmd = [cmd.replace("M190", "M7")]

			# Tx = select extruder : FlashForge uses M108
			elif gcode == "T":
				cmd = [("M108 %s" % cmd, cmd_type)]

			if cmd == []:
				self._logger.debug("rewrite_gcode(): dropping command")

		return cmd


	# Uploading files directly to internal SD card
	def upload_to_sd(self, printer, filename, path, sd_upload_started, sd_upload_succeeded, sd_upload_failed, *args,
					 **kwargs):
		""" OctoPrint hook - Called when uploading to SD card

		Note the filename can contain a sub-folder path to the place on OctoPrint where the file is located!
		"""
		from timeit import default_timer as timer

		if not self._serial_obj:
			return

		def process_upload():
			error = ""
			errormsg = "Unable to upload to SD card"

			# TODO: should be able to remove this if we can detect and notify if a print job is running when we connect
			#  to the printer or if the job is started manually on the printer display because we should never get this far
			if not self._serial_obj.is_ready():
				self._logger.info("aborting: print already in progress")
				sd_upload_failed(filename, remote_name, timer()-start)
				eventManager().fire(Events.ERROR, {"error":  errormsg + " - printer is busy.", "reason": "start_print"})
				return

			# there must be something coming back from the printer (eg keep alive) or we will block here until the
			# Octoprint comm monitor readline times out
			self._serial_obj.makeexclusive(True)
			self._serial_obj.enable_keep_alive(False)

			# make sure heaters are off
			ok, answer = self._serial_obj.sendcommand(b"M104 S0 T0")
			if not ok:
				error = "{}: {}".format(errormsg, answer)
				errormsg += " - printer busy."
			else:
				self._serial_obj.sendcommand(b"M104 S0 T1")
				self._serial_obj.sendcommand(b"M140 S0")

				ok, answer = self._serial_obj.sendcommand(b"M28 %d 0:/user/%s" % (file_size, remote_name.encode()), 5000)
				if not ok or b"open failed" in answer:
					error = "{}: {}".format(errormsg, answer)
					errormsg += " - could not create file on printer SD card."

			if not error:
				self._logger.debug("M28 file tx started")

				try:
					chunk_start_index = 0
					while chunk_start_index < file_size:
						chunk_end_index = min(chunk_start_index + self.FILE_PACKET_SIZE, file_size)
						chunk = bgcode[chunk_start_index:chunk_end_index]
						if not chunk:
							error = "unexpected eof"
							break

						if self._serial_obj.writeraw(chunk, False):
							upload_percent = int(100.0 * chunk_end_index / file_size)
							self._logger.debug("Sent: %d%% %d/%d" % (upload_percent, chunk_end_index, file_size))
						else:
							error = "file transfer interrupted"
							break

						chunk_start_index += self.FILE_PACKET_SIZE

					if not error:
						result, response = self._serial_obj.sendcommand(b"M29", 10000)
						if result and b"CMD M28" in response:
							response = self._serial_obj.readraw(1000)
						if result and b"failed" not in response:
							sd_upload_succeeded(filename, remote_name, timer()-start)
						else:
							error = "file transfer incomplete"

				except flashforge.FlashForgeError:
					error = "file transfer incomplete"

				errormsg = "{} - {}.".format(errormsg, error)

			if error:
				self._logger.info("Upload failed: {}".format(error))
				sd_upload_failed(filename, remote_name, timer()-start)
				self._serial_obj.makeexclusive(False)
				self._serial_obj.enable_keep_alive(True)
				eventManager().fire(Events.ERROR, {"error": errormsg, "reason": "start_print"})
				return

			self._serial_obj.makeexclusive(False)
			self._serial_obj.enable_keep_alive(True)
			# NB M23 select will also trigger a print on FlashForge
			self._comm.selectFile("0:/user/%s\r\n" % remote_name, True)
			# TODO: need to set the correct file size for the progress indicator


		# TODO: test printer status and do not proceed if not ready - eg homing after cancelling an SD print

		start = timer()
		# Unfortunately we cannot get the list of files on the SD card from FlashForge so we just name the remote
		# file the same as the source and hope for the best
		bgcode = b""
		file_size = 0
		remote_name = filename.split("/")[-1]

		self._logger.info("Starting SDCard upload from {} to {}".format(filename, remote_name))
		sd_upload_started(filename, remote_name)

		try:
			file = open(path, "rb")
			bgcode = file.read()
			file_size = len(bgcode)
			file.close()
		except:
			errormsg = "could not open local file."
			self._logger.info("aborting: " + errormsg)
			sd_upload_failed(filename, remote_name, timer()-start)
			eventManager().fire(Events.ERROR, {"error": errormsg, "reason": "start_print"})
		else:
			thread = threading.Thread(target=process_upload, name="FlashForge.SD_Uploader")
			thread.daemon = True
			thread.start()

		return remote_name



# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "FlashForge Plugin"
__plugin_pythoncompat__ = ">=2.7,<4"


def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = FlashForgePlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
		"octoprint.comm.transport.serial.factory": __plugin_implementation__.printer_factory,
		"octoprint.comm.transport.serial.additional_port_names": __plugin_implementation__.get_additional_port_names,
		"octoprint.comm.protocol.firmware.capabilities": __plugin_implementation__.printer_capabilities,
		"octoprint.filemanager.extension_tree": __plugin_implementation__.get_extension_tree,
		"octoprint.comm.protocol.gcode.queuing": __plugin_implementation__.rewrite_gcode,
		"octoprint.printer.sdcardupload": __plugin_implementation__.upload_to_sd
	}
