/*
 * View model for OctoPrint-FlashForge
 *
 */
$(function () {
	function FlashForgeViewModel(parameters) {
		var self = this;

		self.controlViewModel = parameters[0];
		self.settingsViewModel = parameters[1];
		self.printerProfileViewModel = parameters[2];

		// LED Controls

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

		// Printer Profile Tweaking

		self.editor = self.printerProfileViewModel.editor;
		if (self.editor.fromProfileData !== undefined && self.editor.toProfileData !== undefined) {
			// override the functions for syncing profile data with the page
			self.editor.origFromProfileData = self.editor.fromProfileData;
			self.editor.origToProfileData = self.editor.toProfileData;

            // load profile
			self.editor.fromProfileData = function(data) {
				this.origFromProfileData(data);
				if ($('#ff_noG91').length)
					$('#ff_noG91').prop('checked', data.ff.noG91);
			};

            // save profile
			self.editor.toProfileData = function() {
				profile = this.origToProfileData();
				profile.ff = {};
				if ($('#ff_noG91').length)
					profile.ff.noG91 = $('#ff_noG91').prop('checked');
				return profile;
			};
		}

		// callbacks

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

			// hack in our printer profile controls
			$("#settings_printerProfiles_editDialog_axes .form-horizontal").prepend(
				'<div class="control-group">' +
					'<label class="control-label">G91 Not Supported</label>' +
					'<div class="controls"><label class="checkbox">' +
						'<input id="ff_noG91" type="checkbox" data-bind="checked: ff_noG91">' +
						'Select if movement buttons do not work (FlashForge Finder 2, Guider 2, etc)' +
					'</label></div>' +
				'</div>');
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
		dependencies: ["controlViewModel", "settingsViewModel", "printerProfilesViewModel"],
		elements: []
	});
});
