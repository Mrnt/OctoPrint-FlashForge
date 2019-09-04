# OctoPrint-FlashForge

Add support to the [Octoprint](https://octoprint.org) 3D printer web interface for communication with closed source FlashForge printers such as Finder, Dreamer and rebranded printers such as the PowerSpec Ultra, Dremel Idea Builder.

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

Plugin requires the libusb1 library:
https://pypi.org/project/libusb1/

## Configuration

### Settings

Under OctoPrint > Settings > Serial Connection > Intervals & Timeouts:
Change all settings under "Query Intervals" to 1s.

Under OctoPrint > Settings > Serial Connection > Firmware & Protocol:
Disable "Enable automatic firmware detection"
Change "Send a checksum with the command" to "Never"

Under OctoPrint > Settings > Printer Profiles:
Edit the default printer profile or create a new to reflect the number of extruders, build volume, etc.

Under OctoPrint > Settings > Plugin Manager:
Verify that the FlashForge plugin is enabled

### Connection

Under the main interface select "Auto" for "Serial Port".

## Troubleshooting

Verify the plugin is enabled (Settings > Plugin Manager - "FlashForge" should be enabled), Octoprint may need to be restarted.

If it fails to detect or connect to the printer check the Terminal tab in Octoprint for errors.

Turn on debug messages for the plugin (Settings > Logging, under "Logging Levels" set octoprint.plugins.flashforge to "DEBUG" and then click "Save")

After attempting to connect to the printer with debug messages turned on, review the log (Settings > Logging, octoprint.log)
