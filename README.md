# OctoPrint-FlashForge

Add support to the [Octoprint](https://octoprint.org) 3D printer web interface for communication with closed source printers such as the:
- FlashForge Finder, FlashForge Dreamer, FlashForge Dreamer NX, FlashForge Inventor, FlashForge Creator Max, FlashForge Ultra 2.0
- PowerSpec Ultra 3DPrinter 2.0
- Dremel Idea Builder 3D20

Based on work by [Noneus](https://github.com/Noneus)

## Current Capabilities

- Automatically detect and connect to the above printers
- Use Octoprint Control UI to:
    - Set and monitor printer temperature
    - Move extruder, bed
    - Turn fans on and off
    - Extrude, retract
- Upload a FlashPrint prepared .gx or .g file using the "Upload to SD" button which will immediately start a print (like FlashPrint), you should be able to pause, resume, cancel the print using the respective buttons.
- Upload a Cura prepared .gcode file using the "Upload to SD" button or directly to the SD card from Cura (see [Wiki](https://github.com/Mrnt/OctoPrint-FlashForge/wiki) for details).

## Install

Install via the bundled [Plugin Manager](https://github.com/foosel/OctoPrint/wiki/Plugin:-Plugin-Manager)
by selecting "Install new Plugins" and in the box "...enter URL" put:

    https://github.com/Mrnt/OctoPrint-FlashForge/archive/master.zip

then click "Install".

Plugin requires the libusb1 library: https://pypi.org/project/libusb1/
 which should install automatically if you install the plugin via the Octoprint UI.

## Configuration

Additional information can be found in the [Wiki](https://github.com/Mrnt/OctoPrint-FlashForge/wiki), but the following steps should get you up and running on OctoPrint/OctoPi.

### Settings

The plugin attempts to set default values for the following (so on a fresh install, no tweaking should be necessary):

* Under OctoPrint > Settings > Serial Connection > Intervals & Timeouts:
    * Temperature Interval (polling) 2s When printing or idle
    * Temperature Interval (polling) 2s When idle and a target temperature is set
    * Temperature Interval (autoreport) 2s Autoreport interval to request from firmware

* Under OctoPrint > Settings > Serial Connection > Firmware & Protocol:
    * Disable "Enable automatic firmware detection"
    * Enable "Always assume SD card is present"
    * Change "Send a checksum with the command" to "Never"
    * Under "Protocol fine tuning" click "Advanced" and make sure the "Hello" command is set to `M601 S0`

* Under OctoPrint > Settings > Serial Connection > Behaviour:
    * Disable "Attempt to abort any blocking heatups on cancel via M108."

* Under OctoPrint > Settings > GCODE Scripts:
    * Make sure all the script fields are empty (the default "After print job is cancelled" script generates commands that causes the printer to hang)

* Under OctoPrint > Settings > Printer Profiles:
Edit the default printer profile or create a new one to reflect the number of extruders, build volume, etc.

* Under OctoPrint > Settings > Plugin Manager:
Verify that the FlashForge plugin is enabled

### Connection

Under the main interface select "Auto" for "Serial Port".

## Troubleshooting

* Verify the plugin is enabled (Settings > Plugin Manager - "FlashForge" should be enabled), Octoprint may need to be restarted.
If plugin does not appear in Plugin Manager list `libusb1` may need to be installed manually - current version of plugin should do this automatically.

* If the plugin fails to detect or connect to the printer check the Terminal tab in Octoprint for errors and verify that you set up the Serial Connection settings as described in the Configuration section above.

* If you are on OctoPi/Linux and see a USB permissions error then you will need to add a udev rule to allow access to the printer - see error message in the Terminal tab of Octoprint for instructions.

* Verify that the Serial Connection settings are set correctly, in particular the "Send a checksum with the command" setting.

* Turn on debug messages for the plugin (Settings > Logging, under "Logging Levels" set [octoprint.plugins.flashforge](https://github.com/Mrnt/OctoPrint-FlashForge/wiki/images/LoggingSettings.png) to "DEBUG" and then click the "+" sign next to it, then click "Save") to help troubleshoot connection issues.

* After attempting to connect to the printer with debug messages turned on, review the log (Settings > Logging, octoprint.log) for clues. If you cannot resolve it, create an [Issue](https://github.com/Mrnt/OctoPrint-FlashForge/issues) in github providing the platform (Windows/OctoPi/etc), hardware (PC/Raspberry Pi 3b/etc), Printer Model, Printer Firmware Version and upload the octoprint.log as a zip file.


