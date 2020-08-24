# OctoPrint-FlashForge

Adds support to the [OctoPrint](https://octoprint.org) 3D printer web interface for communication with closed source printers such as the:
- FlashForge Finder, FlashForge Dreamer, FlashForge Dreamer NX, FlashForge Inventor, FlashForge Creator Max, FlashForge Ultra 2.0, FlashForge Guider II, FlashForge Guider IIs
- PowerSpec Ultra 3DPrinter 2.0
- Dremel Idea Builder 3D20, 3D45

These printers are not supported by [Octoprint-GPX](https://github.com/markwal/OctoPrint-GPX).  Octoprint-GPX works on older printers such as the FlashForge Creator Pro and a few similar printers which use the GPX protocol.

## Current Capabilities

- Automatically detect and connect to the above printers
- Use Octoprint Control UI to:
    - Set and monitor printer temperature
    - Move extruder, bed*
    - Turn fans on and off
    - Extrude, retract*
    - Set color of the enclosure light, turn it on/off
- Upload a FlashPrint prepared .gx or .g file using the "Upload to SD" button which will immediately start a print (like FlashPrint), you should be able to pause, resume, cancel the print using the respective buttons.
- Upload a Cura prepared .gcode file using the "Upload to SD" button or directly to the SD card from Cura (see [Wiki](https://github.com/Mrnt/OctoPrint-FlashForge/wiki) for details).

***This may not work on FlashForge Finder II, Guider II, Guider IIs.**

**PLEASE NOTE: At this time it will NOT print directly from within OctoPrint - i.e. using the "Upload" button to upload a file into OctoPrint and then selecting file within OctoPrint and trying to print, will NOT work. Hopefully this functionality will be available soon.**

## Install

Install via the OctoPrint [Plugin Manager](https://docs.octoprint.org/en/master/bundledplugins/pluginmanager.html)
by clicking "Get More" and entering "FlashForge" to search the Plugin Repository, or in the box "...enter URL" put:

    https://github.com/Mrnt/OctoPrint-FlashForge/archive/master.zip

then click "Install".

Plugin requires the libusb1 library: https://pypi.org/project/libusb1/
 which should install automatically if you install the plugin via the Octoprint UI.

## Configuration

The following steps should get you up and running on OctoPrint/OctoPi:

### Settings

The plugin attempts to set default values for the following (so on a fresh install, no tweaking should be necessary):

* Under OctoPrint > Settings > Serial Connection > Intervals & Timeouts:
    * Temperature Interval (polling) 5s When printing or idle
    * Temperature Interval (polling) 2s When idle and a target temperature is set
    * Temperature Interval (autoreport) 2s Autoreport interval to request from firmware

* Under OctoPrint > Settings > Serial Connection > Firmware & Protocol:
    * Disable "Enable automatic firmware detection"
    * Enable "Always assume SD card is present"
    * Change "Send a checksum with the command" to "Never"
    * Under "Protocol fine tuning" click "Advanced" and make sure the "Hello" command is set to `M601 S0`

* Under OctoPrint > Settings > Serial Connection > Behaviour:
    * Un-check "Attempt to abort any blocking heatups on cancel via M108."

* Under OctoPrint > Settings > GCODE Scripts:
    * Make sure all the script fields are empty (the default "After print job is cancelled" script generates commands
    that causes the printer to hang). You can tweak this after you have the plugin working - use the G-code Dictionary
    in the Wiki to help you.

* Under OctoPrint > Settings > Printer Profiles:
Edit the default printer profile or create a new one to reflect the number of extruders, build volume, etc.

* Under Octoprint > Settings > Features:
    * Edit "Terminal Auto Uppercase Blacklist" to display `M146` (to allow the control of the lights inside the printer).

* Under OctoPrint > Settings > Plugin Manager:
Verify that the FlashForge plugin is enabled

### Connection

Under the main interface select "Auto" for "Serial Port".

### Additional Information

Additional information on g-code supported by the printers, etc can be found in the [Wiki](https://github.com/Mrnt/OctoPrint-FlashForge/wiki).

Plugin was inspired by work by [Noneus](https://github.com/Noneus) and information on these printers provided by users. If you discover an issue, figured out how to make out how to make it work better or have an idea for improvement please raise it as an [issue](https://github.com/Mrnt/OctoPrint-FlashForge/issues).

## Known Issues

* Currently will only print using the "Upload to SD Card" button.
* Clicking any button in the "Control" tab after clicking a "Home" button may cause the printer to drop the connection if it has not finished "homing".
* Cannot use any controls (besides Pause, Cancel) while a print is in progress. Temperatures, and printer status CAN be monitored because these rely on  *unbuffered* g-code commands - see [G Code Commands](https://github.com/Mrnt/OctoPrint-FlashForge/wiki/G-Code-Dictionary) for a list of unbuffered commands that should work via the Terminal tab when a print is in progress.
* Cannot currently connect to the printer while a print is in progress.

## Troubleshooting

* Verify the plugin is enabled (Settings > Plugin Manager - "FlashForge" should be enabled), Octoprint may need to be restarted.
If plugin does not appear in Plugin Manager list `libusb1` may need to be installed manually - current version of plugin should do this automatically.

* If the plugin fails to detect or connect to the printer check the Terminal tab in Octoprint for errors and verify that you set up the Serial Connection settings as described in the Configuration section above.

* If you are on OctoPi/Linux and see a USB permissions error then you will need to add a udev rule to allow access to the printer - see error message in the Terminal tab of Octoprint for instructions.

* Verify that the Serial Connection settings are set correctly, in particular the "Send a checksum with the command" setting.

* Turn on debug messages for the plugin (Settings > Logging, under "Logging Levels" set [octoprint.plugins.flashforge](https://github.com/Mrnt/OctoPrint-FlashForge/wiki/images/LoggingSettings.png) to "DEBUG" and then click the "+" sign next to it, then click "Save") to help troubleshoot connection issues.

* After attempting to connect to the printer with debug messages turned on, review the log (Settings > Logging, octoprint.log) for clues. If you cannot resolve it, create an [Issue](https://github.com/Mrnt/OctoPrint-FlashForge/issues) in github providing the platform (Windows/OctoPi/etc), hardware (PC/Raspberry Pi 3b/etc), Printer Model, Printer Firmware Version and upload the octoprint.log as a zip file.

* If you have a printer such as Finder II, Guider II and find that the movement controls under the "Control" tab do not seem to work,
there is a setting under "Settings" > "Printer Profiles" > "Axes" where you can select G91 (relative positioning) not supported.

## Support Further Development

This plugin was/is developed by painstakingly reverse engineering the communication
between FlashPrint and FlashForge printers with much trial and error. If you find it
useful and/or want to see continued development, please consider making a donation.

[More chocolate, more code](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=S4TNWVKFLPL5C&source=url)




