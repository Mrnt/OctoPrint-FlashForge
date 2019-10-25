# OctoPrint-FlashForge

Add support to the [Octoprint](https://octoprint.org) 3D printer web interface for communication with closed source FlashForge printers such as Finder, Dreamer, Inventor and rebranded printers such as the PowerSpec Ultra, Dremel Idea Builder.

Based on work by [Noneus](https://github.com/Noneus)

## Current Capabilities

- Automatically detect and connect to Dremel IdeaBuilder, FlashForge Finder, FlashForge Dreamer, PowerSpec Ultra
- Use Octoprint Control UI to:
    - Set and monitor printer temperature
    - Move extruder, bed
    - Turn fans on and off
    - Extrude, retract
- Upload a FlashPrint prepared .gx file using the "Upload to SD" button which will immediately start a print (like FlashPrint), you should be able to pause, cancel the print using the respective buttons.



## Setup

Install via the bundled [Plugin Manager](https://github.com/foosel/OctoPrint/wiki/Plugin:-Plugin-Manager)
or manually using this URL:

    https://github.com/Mrnt/OctoPrint-FlashForge/archive/master.zip

Plugin requires the libusb1 library: https://pypi.org/project/libusb1/
Which should install automatically if you install the plugin via the Octoprint UI.

## Configuration

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

* Under OctoPrint > Settings > Printer Profiles:
Edit the default printer profile or create a new to reflect the number of extruders, build volume, etc.

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

* Turn on debug messages for the plugin (Settings > Logging, under "Logging Levels" set octoprint.plugins.flashforge to "DEBUG" and then click "Save") to help troubleshoot connection issues.

* After attempting to connect to the printer with debug messages turned on, review the log (Settings > Logging, octoprint.log) for clues.


