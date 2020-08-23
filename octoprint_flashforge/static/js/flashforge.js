/*
 * View model for OctoPrint-FlashForge
 *
 */
$(function () {
    function FlashForgeViewModel(parameters) {
        var self = this;

        self.controlViewModel = parameters[0];
        self.settingsViewModel = parameters[1];

        self.ledStatus = ko.observable();
        self.ledColor = ko.observable();

        self.pickerButton = false;
        self.picker = false;

        self.ledOff = function() {
            self.ledStatus(0);
            self.setLed([0, 0, 0]);
            self.saveData();
        }

        self.ledOn = function() {
            self.ledStatus(1);
            self.setLed(self.ledColor());
            self.saveData();
        }

        self.pickColor = function() {
            if (self.pickerButton.textContent == self.pickerButton.originalText) {
                self.picker.enter();
                self.picker.fit([self.pickerButton.offsetLeft, self.pickerButton.offsetTop + self.pickerButton.offsetHeight + 2]);
                self.pickerButton.textContent = 'Done';
            } else {
                self.setLed(self.ledColor());
                self.pickerButton.textContent = self.pickerButton.originalText;
            }
        }

        self.setLed = function(rgb) {
            if (!!rgb && rgb.constructor === Array && rgb.length == 3)
                OctoPrint.control.sendGcode('M146 r'+rgb[0]+' g'+rgb[1]+' b'+rgb[2]);
        }

        self.saveData = function() {
            self.settingsViewModel.settings.plugins.flashforge.ledStatus(self.ledStatus());
            self.settingsViewModel.settings.plugins.flashforge.ledColor(self.ledColor());
            self.settingsViewModel.saveData();
        }

        self.getAdditionalControls = function() {
            return [{
                    name: 'Lights',
                    type: 'section',
                    layout: 'horizontal',
                    children: [
                        {
                            javascript: function() { self.ledOff(); },
                            name: "Lights Off",
                            enabled: "self.isOperational() && !self.isPrinting();"
                        },
                        {
                            javascript: function() { self.ledOn(); },
                            name: "Lights On",
                            enabled: "self.isOperational() && !self.isPrinting();"
                        },
                        {
                            javascript: function() { self.pickColor(); },
                            name: "Change Color",
                            enabled: "self.isOperational() && !self.isPrinting();",
                            additionalClasses: "ff_color_picker"
                        }
                    ]
                }
            ];
        }

        self.onBeforeBinding = function() {
            self.ledStatus(self.settingsViewModel.settings.plugins.flashforge.ledStatus());
            self.ledColor(self.settingsViewModel.settings.plugins.flashforge.ledColor());
        }

        self.onStartupComplete = function() {
            self.pickerButton = document.getElementsByClassName('ff_color_picker')[0];
            var colorinput = document.createElement("INPUT");
            colorinput.value = CP.HEX(self.ledColor());

            self.picker = new CP(colorinput, true);
            self.picker.self.getElementsByClassName('color-picker:a')[0].style.display = "none";

            self.pickerButton.originalText = self.pickerButton.textContent;
            self.picker.on('change', function(r, g, b) {
                self.ledColor([r, g, b]);
                this.source.value = this.color(r, g, b, 1);
            });
            self.picker.on('exit', function() {self.pickColor();});
        }

        self.onEventSettingsUpdated = function() {
            self.ledStatus(self.settingsViewModel.settings.plugins.flashforge.ledStatus());
            self.ledColor(self.settingsViewModel.settings.plugins.flashforge.ledColor());
        }

        self.onEventConnected = function() {
            if (self.ledStatus())
                self.setLed(self.ledColor())
            else
                self.setLed(0, 0, 0);
        }
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: FlashForgeViewModel,
        dependencies: ["controlViewModel","settingsViewModel","printerStateViewModel"],
        elements: []
    });
});
