# OctoPrint-FlashForge

Adds support to the [OctoPrint](https://octoprint.org) 3D printer web interface for communication with closed source
printers such as the:
- FlashForge Creator Max, FlashForge Dreamer, FlashForge Dreamer NX, FlashForge Finder, FlashForge Finder II, FlashForge
Guider II, FlashForge Guider IIs, FlashForge Inventor, FlashForge Ultra 2.0
- PowerSpec Ultra 3DPrinter 2.0
- Dremel Idea Builder 3D20, 3D40, 3D45

At the current time, plugin will only work with printers that support a connection to a host computer (eg RaspberryPi)
via a USB connection (using a USB type B connector on the printer).


These printers are not supported by [Octoprint-GPX](https://github.com/markwal/OctoPrint-GPX).  Octoprint-GPX works on
older printers such as the FlashForge Creator Pro and a few similar printers which use the GPX protocol.

## March 9th 2022 - IMPORTANT PLEASE READ
**Neither FlashForge or Dremel have provided details of the commands or protocol supported by the various models - almost 
all the work herein was done by reverse engineering the communication between FlashPrint and the two printers I had access 
too, trial and error, and subsequently spending many, many hours studying debug logs including those graciously provided by 
users.** 

**However, this is ultimately a losing battle - every new device or firmware change by FlashForge can and has broken the limited 
capabilities of this plugin. I have therefore made the decision not to spend more time on this plugin. I am grateful to the 
few users that were generous enough to send me a donation and I hope that they will understand this decision.
Moving forward, the best solution for FlashForge printers is to use a well documented, open source firmware such as Marlin, 
which will fully support OctoPrint, Cura, etc. I am working on converting my remaining FlashForge printer to use Marlin firmware
so that I can focus on using it to its full potential.**


## Current Capabilities

- Automatically detect and connect to the above printers
- Use Octoprint Control UI to:
    - Set and monitor printer temperature
    - Move extruder, bed*
    - Turn fans on and off
    - Extrude, retract*
    - Set color of the enclosure light, turn it on/off
- Upload a FlashPrint prepared .gx or .g file using the "Upload to SD" button which will immediately start a print (like
FlashPrint), you should be able to pause, resume, cancel the print using the respective buttons.
- Upload a Cura prepared .gcode file using the "Upload to SD" button or directly to the SD card from Cura (note that some 
Cura generated g-code commands are not compatable with FlashForge printers, see
[Wiki](https://github.com/Mrnt/OctoPrint-FlashForge/wiki) for details).
- Print directly from within OctoPrint - i.e. using the "Upload" button to upload a file into OctoPrint (prepared using
FlashPrint or another slicer) and then selecting file within OctoPrint. **Note: this is a new feature and there may be
issues with reliability or even whether it will work at all on a given printer (it has only been tested on a PowerSpec
Ultra 3D, FlashForge Finder v1) - please tread carefully and provide detailed bug reports.**
- Print directly from Cura via OctoPrint to SD card or direct (see warnings on previous 2 items).


### Printer Compatibility
**IMPORTANT: This plugin uses a USB connection to communicate with the printer - if the printer cannot be connected 
directly to a computer via USB, then it will not work with this plugin.**

Shows current state of printer Compatibility for core OctoPrint functionality and will be updated as users provide
feedback.
|Printer			|Upload File to SD Card |Control Movement and Temperature	|Print Directly From OctoPrint	|
|---				|---					|---								|---							|
|Adventurer 4 <br>**Not supported** *(no USB to host port)*|-|-|-|
|Adventurer 3 <br>**Not supported** *(no USB to host port)*|-|-|-|
|Adventurer 3C <br>**Not supported** *(no USB to host port)*|-|-|-|
|Adventurer 3 <br>**Not supported** *(no USB to host port)*|-|-|-|
|Creator 3 <br>**Not supported** *(no USB to host port)*|-|-|-|
|Creator Max		|Yes				    |Yes								|Yes, unreliably				|
|Creator Pro		|No	(Use GPX plugin)	|No	(Use GPX plugin)				|No	(Use GPX plugin)			|
|Creator Pro 2		|No	(Use GPX plugin)	|Yes                				|Yes (IDEX in development)		|
|Dreamer			|Yes					|?									|?								|
|Dreamer NX			|Yes					|?									|?								|
|Finder v1			|Yes					|Yes								|Yes, unreliably				|
|Finder v2*			|Yes					|Temp - Yes, Movement - ?			|?								|
|Explorer			|Yes					|?									|?								|
|Guider				|Yes					|?									|?								|
|Guider II*			|Yes					|Temp - Yes, Movement - ?			|?								|
|Guider II S*		|Yes					|Temp - Yes, Movement - ?			|?								|
|Inventor			|Yes					|?									|?								|
|Inventor II		|Yes					|?									|?								|
|Dremel 3D20		|Yes					|?									|?								|
|Dremel 3D40**		|?						|?									|?								|
|Dremel 3D45**		|?						|?									|?								|
|PowerSpec Ultra 3d	|Yes					|Yes								|Yes, unreliably				|

\* May be issues with FlashForge Finder II, Guider II, Guider IIs - these printers do not support relative positioning
so when you create your Printer Profile in OctoPrint you will need to go to the "Axes" tab and select "G91 Not Supported". 
If you still experience issues when using the controls please report with debug log files (see below for how to enable 
debugging).

\** Dremel 3D40, 3D45 seem to talk a little differently from the other printers and cannot be controlled directly. At the 
present time upload to SD card is not working either.


## Install

Install via the OctoPrint [Plugin Manager](https://docs.octoprint.org/en/master/bundledplugins/pluginmanager.html)
by clicking "Get More" and entering "FlashForge" to search the Plugin Repository, or in the box "...enter URL" put:

    https://github.com/Mrnt/OctoPrint-FlashForge/archive/master.zip

then click "Install".

Plugin requires the libusb1 library: https://pypi.org/project/libusb1/
 which should install automatically if you install the plugin via the Octoprint UI.
 
If you are using Linux (eg you installed OctoPi on a Raspberry Pi), then after installing the plugin (and restarting 
OctoPrint), you will need to access the Pi using SSH to give the OctoPrint permissions to access the printer. Instructions 
for adding a udev rule to allow configure permissions will appear in the "Terminal" tab of OctoPrint the first time you 
attempt to connect to your printer.

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

Additional information on g-code supported by the printers, etc can be found in the
[Wiki](https://github.com/Mrnt/OctoPrint-FlashForge/wiki).

Plugin was inspired by work by [Noneus](https://github.com/Noneus) and information on these printers provided by users.
If you discover an issue, figured out how to make out how to make it work better or have an idea for improvement please
raise it as an [issue](https://github.com/Mrnt/OctoPrint-FlashForge/issues).

## Known Issues

* Currently will only reliably print using the "Upload to SD Card" button. As described above, the print from OctoPrint
functionality is in place but is currently only tested (and somewhat reliable) on PowerSpec Ultra 3D, FlashForge Finder
v1.
* Clicking any button in the "Control" tab after clicking a "Home" button may cause the printer to drop the connection
if it has not finished "homing".
* Cannot use any controls (besides Pause, Cancel) while a print is in progress. Temperatures, and printer status CAN be
monitored because these rely on  *unbuffered* g-code commands - see
[G Code Commands](https://github.com/Mrnt/OctoPrint-FlashForge/wiki/G-Code-Dictionary) for a list of unbuffered commands
that should work via the Terminal tab when a print is in progress.

## Troubleshooting

* Verify the plugin is enabled (Settings > Plugin Manager - "FlashForge" should be enabled), Octoprint may need to be
restarted.
If plugin does not appear in Plugin Manager list `libusb1` may need to be installed manually - current version of
plugin should do this automatically.

* Verify that you are not connected to the printer using FlashPrint, Dremel Digilab, etc via WiFi or Ethernet while also 
trying to connect OctoPrint to the printer.

* If the plugin fails to detect or connect to the printer check the Terminal tab in Octoprint for errors and verify
that you set up the Serial Connection settings as described in the Configuration section above.

* If you are on OctoPi/Linux and see a USB permissions error then you will need to add a udev rule to allow access to
the printer - see error message in the Terminal tab of Octoprint for instructions.

* Verify that the Serial Connection settings are set correctly, in particular the "Send a checksum with the command"
setting.

* Turn on debug messages for the plugin (see Debugging below) to help troubleshoot connection issues.

* After attempting to connect to the printer with debug messages turned on, review the log (Settings > Logging,
octoprint.log) for clues. If you cannot resolve it, create an
[Issue](https://github.com/Mrnt/OctoPrint-FlashForge/issues) in github providing the platform (Windows/OctoPi/etc),
hardware (PC/Raspberry Pi 3b/etc), Printer Model, Printer Firmware Version and upload the octoprint.log as a zip file.

* If you have a printer such as Finder II, Guider II and find that the movement controls under the "Control" tab do not
seem to work,
there is a setting under "Settings" > "Printer Profiles" > "Axes" where you can select G91 (relative positioning) not
supported.


## Debugging
Turn on debug messages for the plugin by going to Settings > Logging and under "Logging Levels" set 
`octoprint.plugins.flashforge` to "DEBUG"

![](https://github.com/Mrnt/OctoPrint-FlashForge/wiki/images/LoggingSettings.png)

**IMPORTANT**: click the "+" sign next to it, then click "Save".


## Support Further Development

This plugin was/is developed by painstakingly reverse engineering the communication
between FlashPrint and FlashForge printers with much trial and error. If you find it
useful and/or want to see continued development, please consider making a donation.

[More chocolate, more code](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=S4TNWVKFLPL5C&source=url)




