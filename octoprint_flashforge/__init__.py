# coding=utf-8
from __future__ import absolute_import

### (Don't forget to remove me)
# This is a basic skeleton for your plugin's __init__.py. You probably want to adjust the class name of your plugin
# as well as the plugin mixins it's subclassing from. This is really just a basic skeleton to get you started,
# defining your plugin as a template plugin, settings and asset plugin. Feel free to add or remove mixins
# as necessary.
#
# Take a look at the documentation on what other plugin mixins are available.

import octoprint.plugin

class FlashForgePlugin(octoprint.plugin.SettingsPlugin,
                       octoprint.plugin.AssetPlugin,
                       octoprint.plugin.TemplatePlugin):


	def __init__(self):
		import logging
		self._logger = logging.getLogger("octoprint.plugins.octoprint_flashforge")
		self._logger.debug("__init__")
		self._initialized = False


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
		import logging

		if not port == "AUTO":
			return None

		self._logger.debug("printer_factory")
		self._logger.debug("printer_factory port {}s".format(port))

		from . import flashforge
		serial_obj = flashforge.FlashForge(read_timeout=float(read_timeout))
		return serial_obj


	# stub for uploading files directly to SD card
	def upload_to_sd(self, printer, filename, path, sd_upload_started, sd_upload_succeeded, sd_upload_failed, *args,
						 **kwargs):
		import threading
		import time

		remote_name = printer._get_free_remote_name(filename)
		self._logger.info("Starting dummy SDCard upload from {} to {}".format(filename, remote_name))
		sd_upload_started(filename, remote_name)

		def process():
			self._logger.info("Sleeping 10s...")
			time.sleep(10)
			self._logger.info("And done!")
			sd_upload_succeeded(filename, remote_name, 10)

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
		"octoprint.printer.sdcardupload": __plugin_implementation__.upload_to_sd
	}

