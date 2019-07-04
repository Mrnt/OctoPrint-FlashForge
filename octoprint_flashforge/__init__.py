# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from . import flashforge


class FlashForgePlugin(octoprint.plugin.SettingsPlugin,
                       octoprint.plugin.AssetPlugin,
                       octoprint.plugin.TemplatePlugin):

	FILE_PACKET_SIZE = 1024 * 4


	def __init__(self):
		import logging
		#logging.basicConfig(level=logging.DEBUG, format='%(relativeCreated)6d %(threadName)s %(message)s')
		self._logger = logging.getLogger("octoprint.plugins.flashforge")
		self._logger.debug("__init__")
		self._initialized = False
		self._comm = None
		self._serial_obj = None
		self._currentFile = None
		self._upload_percent = 0


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


	# main serial connection hook
	def printer_factory(self, comm, port, baudrate, read_timeout, *args, **kwargs):

		if not port == "AUTO":
			return None

		self._logger.debug("printer_factory")
		self._logger.debug("printer_factory port {}s".format(port))

		from . import flashforge
		self._comm = comm
		serial_obj = flashforge.FlashForge(self, comm, read_timeout=float(read_timeout))
		return serial_obj


	def get_extension_tree(self, *args, **kwargs):
		return dict(
			machinecode=dict(
				gx=["gx"]
			)
		)


	def on_connect(self, serial_obj):
		self._serial_obj = serial_obj


	def on_disconnect(self):
		self._serial_obj = None


	# stub for uploading files directly to SD card
	def upload_to_sd(self, printer, filename, path, sd_upload_started, sd_upload_succeeded, sd_upload_failed, *args,
						 **kwargs):
		import threading
		from octoprint import util as util
		from octoprint.util import comm as comm

		gcode = ""
		file_size = 0
		remote_name = ""


		def process():
			error = ""

			# rewrite:
			self._upload_percent = 0
			chunk_start_index = 0
			counter = 0

			self._serial_obj.makeexclusive(True)
			error = "could not start tx"

			ok, answer = self._serial_obj.send_and_wait("M28 {} 0:/user/{}".format(file_size, remote_name), 5000)
			if not ok:
				error = "file transfer not started {}".format(answer)
			else:
				self._logger.debug("M28 success")
				error = ""

				while chunk_start_index < file_size:
					#if self.stop_flag:
					#	return False
					chunk_end_index = min(chunk_start_index + self.FILE_PACKET_SIZE, file_size)
					chunk = gcode[chunk_start_index:chunk_end_index]
					if not chunk:
						error = "unexpected eof"
						break
					if self._serial_obj.writeraw(chunk):#, endpoint=self.connection.file_transfer_endpoint_out, raw=True):
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
				if self._serial_obj.send_and_wait("M29", 10000):
					ok, answer = self._serial_obj.send_and_wait("M23 0:/user/{}".format(remote_name), 10000)
					if not answer:
						error = "Printer did not answer to file print M23 {}".format(answer)
					elif "Disk read error" in answer:
						error = "Disk read error"
					elif "File selected" in answer:
						self._logger.debug("And done!")

						self._comm.external_streaming(False)
						self._serial_obj._fileTX = False

						sd_upload_succeeded(filename, remote_name, 10)
						self._serial_obj.makeexclusive(False)
						return


			self._logger.debug("Upload failed: {}".format(error))

			self._comm.external_streaming(False)
			#self._serial_obj._fileTX = False

			sd_upload_failed(filename, remote_name, 10)
			self._serial_obj.makeexclusive(False)

			raise FlashForgeError(error, None)

		if self._serial_obj:
			existingSdFiles = map(lambda x: x[0], self._comm.getSdFiles())
			remote_name = util.get_dos_filename(filename,
								  existing_filenames=existingSdFiles,
								  extension="gx",
								  whitelisted_extensions=["gx"])
			#file = comm.StreamingGcodeFileInformation(path, filename, remote_name)
			#self._comm._currentFile = file

			file = open(path, "r")
			gcode = file.read()
			file_size = len(gcode)
			file.close()



			#file.start()
			self._logger.info("Starting SDCard upload from {} to {}".format(filename, remote_name))
			sd_upload_started(filename, remote_name)

			#printer.on_comm_file_transfer_started(filename,
			#							  remote_name,
			#							  file.getFilesize(),
			#							  user=file.getUser())

			#self._comm.external_streaming(True)
			#self._serial_obj._fileTX = True

			"""
			# make sure heaters are off
			self._serial_obj.send_and_wait("M104 S0 T0")
			self._serial_obj.send_and_wait("M104 S0 T1")
			self._serial_obj.send_and_wait("M140 S0")
			
			if self._serial_obj.send_and_wait("M28 {} 0:/user/{}".format(file_size, remote_name)):
				self._logger.debug("M28 success")
				thread = threading.Thread(target=process)
				thread.daemon = True
				thread.start()
			else:
				self._logger.debug("Upload failed to get M28 response")
				self._comm.external_streaming(False)
				self._serial_obj._fileTX = False
				sd_upload_failed(filename, remote_name, 10)
				self._serial_obj.makeexclusive(False)
			"""
			thread = threading.Thread(target=process)
			thread.daemon = True
			thread.start()

			return remote_name


	def timedupload_to_sd(self, printer, filename, path, sd_upload_started, sd_upload_succeeded, sd_upload_failed, *args, **kwargs):
		import threading
		import time

		remote_name = printer._get_free_remote_name(filename)
		self._logger.info("Starting dummy SDCard upload from {} to {}".format(filename, remote_name))

		#self._comm.external_streaming(True)
		self._serial_obj.makeexclusive(True)
		#self._serial_obj._fileTX = True
		sd_upload_started(filename, remote_name)

		def process():
			self._logger.info("Sleeping 10s...")
			time.sleep(10)
			self._logger.info("And done!")
			#self._comm.external_streaming(False)
			#self._serial_obj._fileTX = False
			sd_upload_succeeded(filename, remote_name, 10)
			self._serial_obj.makeexclusive(False)

		thread = threading.Thread(target=process)
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
		#"octoprint.printer.sdcardupload": __plugin_implementation__.timedupload_to_sd,
		"octoprint.printer.sdcardupload": __plugin_implementation__.upload_to_sd
	}

