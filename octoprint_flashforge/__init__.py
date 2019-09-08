# coding=utf-8
from __future__ import absolute_import

import usb1
import octoprint.plugin
from . import flashforge


class FlashForgePlugin(octoprint.plugin.SettingsPlugin,
                       octoprint.plugin.AssetPlugin,
                       octoprint.plugin.TemplatePlugin):


	VENDOR_IDS = {0x2b71: "FlashForge", 0x2a89: "Dremel"}
	PRINTER_IDS = {
		"Dremel": {0x8889: "Dremel IdeaBuilder"},
		"FlashForge": {0x0001: "Dreamer", 0x0002: "Finder (v1)?", 0x0007: "Finder (v2)?", 0x00ff: "PowerSpec Ultra"}}
	FILE_PACKET_SIZE = 1024 * 4


	def __init__(self):
		import logging
		import octoprint.settings

		# set FlashForge friendly default settings
		#octoprint.settings.default_settings['serial']['waitForStartOnConnect'] = False
		#octoprint.settings.default_settings['serial']['firmwareDetection'] = False
		octoprint.settings.default_settings['serial']['neverSendChecksum'] = True
		octoprint.settings.default_settings['serial']['sdAlwaysAvailable'] = True
		octoprint.settings.default_settings['serial']['timeout']['temperature'] = 2

		self._logger = logging.getLogger("octoprint.plugins.flashforge")
		self._logger.debug("__init__")
		self._initialized = False
		self._comm = None
		self._serial_obj = None
		self._currentFile = None
		self._upload_percent = 0
		self.device_id = 0


	# internal initialize
	def _initialize(self):
		self._logger.debug("_initialize")
		if self._initialized:
			return
		self._initialized = True


	# StartupPlugin
	def on_after_startup(self, *args, **kwargs):
		self._logger.debug("on_after_startup")
		self._initialize()


	##~~ SettingsPlugin mixin
	def get_settings_defaults(self):
		return dict(
			# put your plugin's default settings here
		)


	##~~ AssetPlugin mixin
	def get_assets(self):
		# Define your plugin's asset files to automatically include in the
		# core UI here.
		return dict(
		)


	##~~ Softwareupdate hook
	def get_update_information(self):
		# Define the configuration for your plugin to use with the Software Update
		# Plugin here. See https://github.com/foosel/OctoPrint/wiki/Plugin:-Software-Update
		# for details.
		return dict(
			helloworld=dict(
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


	def detect_printer(self):
		usbcontext = usb1.USBContext()
		for device in usbcontext.getDeviceIterator(skip_on_error=True):
			vendor_id = device.getVendorID()
			device_id = device.getProductID()
			try:
				device_name = device.getProduct()
			except:
				device_name = 'unknown'
			self._logger.debug("Found device '{}' with Vendor ID: {:#06X}, USB ID: {:#06X}".format(device_name, vendor_id, device_id))
			if vendor_id in self.VENDOR_IDS:
				vendor_name = self.VENDOR_IDS[vendor_id]
				if device_id in self.PRINTER_IDS[vendor_name]:
					self._logger.info("Found a {} {}".format(vendor_name, self.PRINTER_IDS[vendor_name][device_id]))
					self.vendor_id = vendor_id
					self.device_id = device_id
					break
				else:
					raise flashforge.FlashForgeError("Found an unsupported {} printer '{}' with USB ID: {:#06X}".format(vendor_name, device_name, device_id), None)

		if self.device_id == 0:
			raise flashforge.FlashForgeError("No FlashForge printer detected - please ensure it is connected and turned on.", None)


	# main serial connection hook
	def printer_factory(self, comm, port, baudrate, read_timeout, *args, **kwargs):

		if not port == "AUTO":
			return None

		self._logger.debug("printer_factory")
		self._logger.debug("printer_factory port {}s".format(port))

		self.detect_printer()

		self._comm = comm
		serial_obj = flashforge.FlashForge(self, comm, self.vendor_id, self.device_id, read_timeout=float(read_timeout))
		return serial_obj


	def get_extension_tree(self, *args, **kwargs):
		return dict(
			machinecode=dict(
				gx=["gx"]
			)
		)


	def on_connect(self, serial_obj):
		self._logger.debug("on_connect()")
		self._serial_obj = serial_obj


	def on_disconnect(self):
		self._logger.debug("on_disconnect()")
		self._serial_obj = None


	def rewrite_gcode(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
		if self._serial_obj:

			self._logger.debug("rewrite_gcode(): gcode:{}, cmd:{}".format(gcode, cmd))

			# M20 list SD card, M21 init SD card - do not do if we are busy
			if (gcode == "M20" or gcode == "M21") and not self._serial_obj.is_ready():
				cmd = []

			# M25 = pause
			elif gcode == "M25":
				# pause during cancel causes issues
				if comm_instance.isCancelling():
					cmd = []

			# M26 in Marlin = set SD card position : Flashforge = cancel
			elif gcode == "M26":
				# M26 S0 generated during cancel - use it to send cancel
				if cmd == "M26 S0" and comm_instance.isCancelling():
					cmd = "M26"
				else:
					cmd = []

			# M82 in Marlin = extruder abs positioning : Flashforge = undefined?
			elif gcode == "M82":
				cmd = []

			# M82 in Marlin = extruder rel positioning : Flashforge = undefined?
			elif gcode == "M83":
				cmd = []

			# M84 in Marlin = disable steppers : M18 in Flashforge
			elif gcode == "M84":
				cmd = ["M18"]

			# also get printer status when getting temp status
			elif gcode == "M105":
				cmd = [("M119", "status_polling"),(cmd, cmd_type)]

			# M106 S0 in Marlin = fan off : Flashforge uses M107 for fan off
			elif gcode == "M106":
				if "S0" in cmd:
					cmd = ["M107"]

			# M108 in Marlin = stop loop & continue : Flashforge=change toolhead, no equivalent?
			elif gcode == "M108":
				cmd = []

			# M109 in Marlin = wait for extruder temp : M6 in Flashforge
			elif gcode == "M109":
				cmd = [cmd.replace("M109", "M6")]

			# change the default hello - M601 S0 takes control via USB
			elif gcode == "M110":
				cmd = ["M601 S0"]

			# also get printer status when connecting
			elif gcode == "M115":
				cmd = [("M119", "status_polling"), ("M27", "sd_status_polling"), (cmd, cmd_type)]

			# M190 in Marlin = wait for bed temp : M7 in Flashforge
			elif gcode == "M190":
				cmd = [cmd.replace("M190", "M7")]

			# M400 in Marlin=wait for moves to finish : Flashforge=? - send something inert so on_M400_sent is triggered
			elif gcode == "M400":
				cmd = "M27"

		return cmd


	def sending_gcode(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
		from octoprint.util import monotonic_time

		if gcode:
			if gcode == "M6" or gcode == "M7":
				self._comm._heatupWaitStartTime = monotonic_time()
				self._comm._long_running_command = True
				self._comm._heating = True


	# uploading files directly to internal SD card
	def upload_to_sd(self, printer, filename, path, sd_upload_started, sd_upload_succeeded, sd_upload_failed, *args,
						 **kwargs):

		if not self._serial_obj:
			return

		def process_upload():
			error = ""

			# rewrite:
			self._upload_percent = 0
			chunk_start_index = 0
			counter = 0

			self._serial_obj.makeexclusive(True)
			error = "could not start tx"

			# make sure heaters are off
			self._serial_obj.sendcommand("M104 S0 T0")
			self._serial_obj.sendcommand("M104 S0 T1")
			self._serial_obj.sendcommand("M140 S0")

			ok, answer = self._serial_obj.sendcommand("M28 {} 0:/user/{}".format(file_size, remote_name), 5000)
			if not ok:
				error = "file transfer not started {}".format(answer)
			else:
				self._logger.debug("M28 success")
				error = ""

				while chunk_start_index < file_size:
					chunk_end_index = min(chunk_start_index + self.FILE_PACKET_SIZE, file_size)
					chunk = gcode[chunk_start_index:chunk_end_index]
					if not chunk:
						error = "unexpected eof"
						break
					if self._serial_obj.writeraw(chunk):
						counter += 1
						if counter > 0:
							counter = 0
							upload_percent = 100.0 * chunk_end_index / file_size
							self.upload_percent = int(upload_percent)
							self._logger.debug("Sent: %.2f%% %d/%d" % (self.upload_percent, chunk_end_index, file_size))
					else:
						error = "File transfer interrupted"
						break
					chunk_start_index += self.FILE_PACKET_SIZE

			if not error:
				if self._serial_obj.sendcommand("M29", 10000)[0]:
					sd_upload_succeeded(filename, remote_name, 10)
					self._serial_obj.makeexclusive(False)
					# NB M23 select will also trigger a print on Flashforge
					self._comm.selectFile("0:/user/{}\r\n".format(remote_name), True)
					return
				else:
					error = "File transfer incomplete"

			self._logger.debug("Upload failed: {}".format(error))
			sd_upload_failed(filename, remote_name, 10)
			self._serial_obj.makeexclusive(False)
			raise flashforge.FlashForgeError(error, None)


		import threading
		from octoprint import util as util

		gcode = ""
		file_size = 0
		remote_name = ""

		existing_sd_files = map(lambda x: x[0], self._comm.getSdFiles())
		remote_name = util.get_dos_filename(filename,
							  existing_filenames=existing_sd_files,
							  extension="gx",
							  whitelisted_extensions=["gx"])

		file = open(path, "r")
		gcode = file.read()
		file_size = len(gcode)
		file.close()

		self._logger.info("Starting SDCard upload from {} to {}".format(filename, remote_name))
		sd_upload_started(filename, remote_name)

		thread = threading.Thread(target=process_upload, name="SD Uploader")
		thread.daemon = True
		thread.start()

		return remote_name



# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "FlashForge Plugin"

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = FlashForgePlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
		"octoprint.comm.transport.serial.factory": __plugin_implementation__.printer_factory,
		"octoprint.filemanager.extension_tree": __plugin_implementation__.get_extension_tree,
		"octoprint.comm.protocol.gcode.queuing": __plugin_implementation__.rewrite_gcode,
		"octoprint.comm.protocol.gcode.sent": __plugin_implementation__.sending_gcode,
		"octoprint.printer.sdcardupload": __plugin_implementation__.upload_to_sd
	}

