# OctoPrint-FlashForge Changelog

## 0.1.3 (2019-09-03)

* Support for OctoPi/Linux (where USB access requires OS permission)
* Automatically install `libusb1` if missing

## 0.1.2 (2019-09-03)

* Detect two versions of FlashForge Finder
* Pausing/Cancelling the print triggered by "Upload to SD Card" should now work
* **NB: Printing still only supported via "Upload to SD Card" button!**

## 0.1.1 (2019-08-01)

* Automatically detect printer (no hardcoding of USB ID's)
* Initial support for "Upload to SD" button: requires .gx file prepared using FlashPrint, print starts after upload **NB Pause, Cancel buttons do not work!**

## 0.1.0 (2019-06-01)

Initial commit:

* Connect to printer if USB ID matches hard coded ID
* Monitor & set temperatures
* Move extruder, bed
* Turn fan on/off