/*
 * View model for OctoPrint-FlashForge
 *
 */
$(function () {
    function LEDViewModel(parameters) {
        var self = this;

        self.controlViewModel = parameters[0];
        self.settingsViewModel = parameters[1];

        self.ledStatus = ko.observable();
        self.ledColor = ko.observable();

        self.pickerButton = false;
        self.picker = false;

        self.ledOff = function() {
            self.ledStatus(0);
            self.setLed(0, 0, 0);
            self.saveData();
        }

        self.ledOn = function() {
            self.ledStatus(1);
            self.setLed(self.ledColor());
            self.saveData();
        }

        self.pickColor = function() {
            self.picker[self.picker.visible ? 'exit' : 'enter']();
            self.picker.fit([self.pickerButton.offsetLeft, self.pickerButton.offsetTop + self.pickerButton.offsetHeight + 2]);
            self.pickerButton.textContent = self.picker.visible ? 'Done' : self.pickerButton.originalText;
            if (!self.picker.visible) {
                self.setLed(self.ledColor());
            }
        }

        self.setLed = function(rgb) {
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
                            name: "Lights Off"
                        },
                        {
                            javascript: function() { self.ledOn(); },
                            name: "Lights On"
                        },
                        {
                            javascript: function() { self.pickColor(); },
                            name: "Change Color",
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

            self.picker = new CP(colorinput, false);
            self.picker.self.classList.add('no-alpha');

            self.pickerButton.originalText = self.pickerButton.textContent;
            self.picker.on('change', function(r, g, b) {
                self.ledColor([r, g, b]);
                this.source.value = this.color(r, g, b, 1);
            });

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
        construct: LEDViewModel,
        dependencies: ["controlViewModel","settingsViewModel","printerStateViewModel"],
        elements: []
    });
});
