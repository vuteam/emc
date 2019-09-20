from enigma import eListboxPythonMultiContent, gFont, eEnv
from boxbranding import getMachineBrand, getMachineName, getBoxType, getMachineBuild

from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.MultiContent import MultiContentEntryText
from Components.Network import iNetwork
from Components.NimManager import nimmanager
from Components.SystemInfo import SystemInfo
from Components.Sources.List import List

from Screens.Screen import Screen
from Screens.NetworkSetup import *
from Screens.PluginBrowser import PluginDownloadBrowser, PluginBrowser
from Screens.LanguageSelection import LanguageSelection
from Screens.ScanSetup import ScanSimple, ScanSetup
from Screens.Satconfig import NimSelection
from Screens.Setup import Setup
from Screens.HarddiskSetup import HarddiskSelection, HarddiskFsckSelection, HarddiskConvertExt4Selection
from Screens.SkinSelector import SkinSelector, LcdSkinSelector
from Screens.Standby import TryQuitMainloop, QUIT_FACTORY_RESET
from Screens.ButtonSetup import ButtonSetup

from Plugins.SystemPlugins.NetworkBrowser.MountManager import AutoMountManager
from Plugins.SystemPlugins.NetworkBrowser.NetworkBrowser import NetworkBrowser
from Plugins.SystemPlugins.NetworkWizard.NetworkWizard import NetworkWizard
from Screens.VideoMode import VideoSetup

from Plugins.SystemPlugins.SoftwareManager.plugin import UpdatePlugin, SoftwareManagerSetup
from Plugins.SystemPlugins.SoftwareManager.BackupRestore import BackupScreen, RestoreScreen, BackupSelection, getBackupPath, getBackupFilename

from os import path

import NavigationInstance

plugin_path_networkbrowser = eEnv.resolve("${libdir}/enigma2/python/Plugins/SystemPlugins/NetworkBrowser")

if path.exists("/usr/lib/enigma2/python/Plugins/SystemPlugins/PositionerSetup"):
	from Plugins.SystemPlugins.PositionerSetup.plugin import PositionerSetup, RotorNimSelection
	HAVE_POSITIONERSETUP = True
else:
	HAVE_POSITIONERSETUP = False

if path.exists("/usr/lib/enigma2/python/Plugins/SystemPlugins/SatFinder"):
	from Plugins.SystemPlugins.Satfinder.plugin import Satfinder
	HAVE_SATFINDER = True
else:
	HAVE_SATFINDER = False

if path.exists("/usr/lib/enigma2/python/Plugins/Extensions/AudioSync"):
	from Plugins.Extensions.AudioSync.AC3setup import AC3LipSyncSetup
	plugin_path_audiosync = eEnv.resolve("${libdir}/enigma2/python/Plugins/Extensions/AudioSync")
	AUDIOSYNC = True
else:
	AUDIOSYNC = False

if path.exists("/usr/lib/enigma2/python/Plugins/SystemPlugins/VideoEnhancement/plugin.pyo"):
	from Plugins.SystemPlugins.VideoEnhancement.plugin import VideoEnhancementSetup
	VIDEOENH = True
else:
	VIDEOENH = False

if path.exists("/usr/lib/enigma2/python/Plugins/SystemPlugins/VideoTune/plugin.pyo"):
	from Plugins.SystemPlugins.VideoTune.VideoFinetune import VideoFinetune
	VIDEOTUNE = True
else:
	VIDEOTUNE = False

if path.exists("/usr/lib/enigma2/python/Plugins/SystemPlugins/Blindscan/plugin.pyo"):
	from Plugins.SystemPlugins.Blindscan.plugin import Blindscan
	BLINDSCAN = True
else:
	BLINDSCAN = False

if path.exists("/usr/lib/enigma2/python/Plugins/Extensions/RemoteIPTVClient"):
	from Plugins.Extensions.RemoteIPTVClient.plugin import RemoteTunerScanner
	REMOTEBOX = True
else:
	REMOTEBOX = False

if path.exists("/usr/lib/enigma2/python/Plugins/SystemPlugins/IniLCNScanner"):
	from Plugins.SystemPlugins.IniLCNScanner.plugin import LCNScannerPlugin
	HAVE_LCN_SCANNER = True
	HAVE_LCN_SCANNER = False  # Disable for now...
else:
	HAVE_LCN_SCANNER = False

try:
	from Plugins.SystemPlugins.RemoteControlCode.plugin import RCSetupScreen
	HAVE_REMOTE_CONTROL_CODE = True
except:
	HAVE_REMOTE_CONTROL_CODE = False

try:
	from Plugins.SystemPlugins.FanControl.plugin import FanSetupScreen
	HAVE_FAN_CONTROL = True
except:
	HAVE_FAN_CONTROL = False

try:
	from Plugins.SystemPlugins.AutomaticVolumeAdjustment.AutomaticVolumeAdjustmentSetup import AutomaticVolumeAdjustmentConfigScreen
	HAVE_AUTOMATIC_VOLUME_ADJUSTMENT = True
except:
	HAVE_AUTOMATIC_VOLUME_ADJUSTMENT = False


def isFileSystemSupported(filesystem):
	try:
		for fs in open('/proc/filesystems', 'r'):
			if fs.strip().endswith(filesystem):
				return True
		return False
	except Exception, ex:
		print "[Harddisk] Failed to read /proc/filesystems:", ex

class GeneralSetup(Screen):
	skin = """
		<screen name="GeneralSetup" position="center,center" size="1195,600" backgroundColor="black" flags="wfBorder">
			<widget source="list" render="Listbox" position="21,32" size="400,400" itemHeight="50" scrollbarMode="showOnDemand" transparent="1" >
				# Eval is used to allow parameterisation of the
				# template used in the old embedded template to be
				# used in the same way here.
				# Functions imported into Components.Converter.TemplatedMultiContent
				# must also be forwarded into the eval().

				# Data indexes:
				# 1: item name
				# 2: item end text
				# 3: item short description
				<convert type="TemplatedMultiContent">
					eval('''{
						  "template": [
						    MultiContentEntryText(pos=(padding_width, 0), size=(width - scrollbar_width - 2 * padding_width - endtext_width, 32), text=1),
						    MultiContentEntryText(pos=(width - scrollbar_width - padding_width - endtext_width, 0), size=(endtext_width, 32), text=2),
						    MultiContentEntryText(pos=(padding_width, 32), size=(width - scrollbar_width - 2 * padding_width, 18), color=0x00AAAAAA, color_sel=0x00AAAAAA, font=1, text=3),
						  ],
						  "fonts": [gFont("Regular", 28), gFont("Regular", 14)],
						  "itemHeight": 50
						}''',
						dict(width=400, endtext_width=20, scrollbar_width=10, padding_width=10,
						     MultiContentEntryText=MultiContentEntryText, gFont=gFont)
					)
				</convert>
			</widget>
			<eLabel position="422,30" size="2,400" backgroundColor="darkgrey" zPosition="3" />
			<widget source="sublist" render="Listbox" position="425,32" size="320,400" itemHeight="45" scrollbarMode="showOnDemand" transparent="1" >
				<convert type="TemplatedMultiContent">
					eval('''{
						  "template": [
						    MultiContentEntryText(pos=(padding_width, 0), size=(width - scrollbar_width - 2 * padding_width, 23), text=1),
						    MultiContentEntryText(pos=(padding_width, 23), size=(width - scrollbar_width - 2 * padding_width, 17), color=0x00AAAAAA, color_sel=0x00AAAAAA, font=1, text=2),
						  ],
						  "fonts": [gFont("Regular", 20), gFont("Regular", 14)],
						  "itemHeight": 45
						}''',
						dict(width=320, scrollbar_width=10, padding_width=10,
						     MultiContentEntryText=MultiContentEntryText, gFont=gFont)
					)
				</convert>
			</widget>
			<widget source="session.VideoPicture" render="Pig" position="771,30" size="398,252" backgroundColor="transparent" zPosition="1" />
			<widget name="description" position="22,445" size="1150,110" zPosition="1" font="Regular;22" halign="center" backgroundColor="black" transparent="1" />
			<widget name="key_red" position="20,571" size="300,26" zPosition="1" font="Regular;22" halign="center" foregroundColor="white" backgroundColor="black" transparent="1" />
			<eLabel position="21,567" size="300,3" zPosition="3" backgroundColor="red" />
		</screen> """

	ALLOW_SUSPEND = True

	def __init__(self, session):
		Screen.__init__(self, session)
		Screen.setTitle(self, _("Setup"))

		self["key_red"] = Label(_("Exit"))
		self["description"] = Label()

		self.menu = 0
		self.list = []
		self["list"] = List(self.list, enableWrapAround=True)
		self.sublist = []
		self["sublist"] = List(self.sublist, enableWrapAround=True)
		self.selectedList = []
		self.onChangedEntry = []
		self["list"].onSelectionChanged.append(self.selectionChanged)
		self["sublist"].onSelectionChanged.append(self.selectionSubChanged)

		self["actions"] = ActionMap(["SetupActions", "WizardActions", "MenuActions", "MoviePlayerActions"], {
			"ok": self.ok,
			"back": self.keyred,
			"cancel": self.keyred,
			"left": self.goLeft,
			"right": self.goRight,
			"up": self.goUp,
			"down": self.goDown,
		}, -1)

		self.MainQmenu()
		self.selectedList = self["list"]
		self.onLayoutFinish.append(self.layoutFinished)

	def layoutFinished(self):
		self.selectionChanged()
		self["sublist"].setSelectionEnabled(0)

	def selectionChanged(self):
		if self.selectedList == self["list"]:
			item = self["list"].getCurrent()
			if item:
				self["description"].setText(_(item[0][1]))
				self.okList()

	def selectionSubChanged(self):
		if self.selectedList == self["sublist"]:
			item = self["sublist"].getCurrent()
			if item:
				self["description"].setText(_(item[0][1]))

	def goLeft(self):
		if self.menu != 0:
			self.menu = 0
			self.selectedList = self["list"]
			self["list"].setSelectionEnabled(1)
			self["sublist"].setSelectionEnabled(0)
			self.selectionChanged()

	def goRight(self):
		if self.menu == 0:
			self.menu = 1
			self.selectedList = self["sublist"]
			self["sublist"].setIndex(0)
			self["list"].setSelectionEnabled(0)
			self["sublist"].setSelectionEnabled(1)
			self.selectionSubChanged()

	def goUp(self):
		self.selectedList.selectPrevious()

	def goDown(self):
		self.selectedList.selectNext()

	def keyred(self):
		if self.menu != 0:
			self.goLeft()
		else:
			self.close()

# ####### Main Menu ##############################
	def MainQmenu(self):
		self.menu = 0
		self.list = []
		self.oldlist = []
		self.list.append(GeneralSetupEntryComponent(_("AV setup"), _("Set up video mode"), _("Set up your video mode, video output and other video settings")))
		self.list.append(GeneralSetupEntryComponent(_("System"), _("System setup"), _("Set up your system")))
		if not SystemInfo["IPTVSTB"]:
			self.list.append(GeneralSetupEntryComponent(_("Tuners"), _("Set up tuners"), _("Set up your tuners and search for channels")))
		else:
			self.list.append(GeneralSetupEntryComponent(_("IPTV configuration"), _("Set up tuners"), _("Set up your tuners and search for channels")))
		self.list.append(GeneralSetupEntryComponent(_("TV"), _("Set up basic TV options"), _("Set up your TV options")))
		self.list.append(GeneralSetupEntryComponent(_("Media"), _("Set up pictures, music and movies"), _("Set up picture, music and movie player")))
		# self.list.append(GeneralSetupEntryComponent(_("Mounts"), _("Mount setup"), _("Set up your mounts for network")))
		self.list.append(GeneralSetupEntryComponent(_("Network"), _("Set up your local network"), _("Set up your local network. For WLAN you need to boot with a USB-WLAN stick")))
		self.list.append(GeneralSetupEntryComponent(_("Storage"), _("Hard disk setup"), _("Set up your hard disk")))
		self.list.append(GeneralSetupEntryComponent(_("Plugins"), _("Download plugins"), _("Show download and install available plugins")))
		self.list.append(GeneralSetupEntryComponent(_("Software manager"), _("Update/backup/restore"), _("Update firmware. Backup / restore settings")))
		self["list"].list = self.list

# ####### TV Setup Menu ##############################
	def Qtv(self):
		self.sublist = []
		self.sublist.append(QuickSubMenuEntryComponent(_("Channel selection"), _("Channel selection configuration"), _("Set up your channel selection configuration")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Recording settings"), _("Recording setup"), _("Set up your recording configuration")))
		if SystemInfo["HDMIin"]:
			self.sublist.append(QuickSubMenuEntryComponent(_("HDMI Recording settings"), _("HDMI Recording setup"), _("Configure recording from HDMI input")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Timeshift settings"), _("Timeshift setup"), _("Set up your timeshift configuration")))
		if HAVE_AUTOMATIC_VOLUME_ADJUSTMENT:
			self.sublist.append(QuickSubMenuEntryComponent(_("Automatic volume settings"), _("Automatic volume setup"), _("Set up your automatic volume adjustment configuration")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Auto language"), _("Auto language selection"), _("Select your Language for audio/subtitles")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Subtitle settings"), _("Subtitle setup"), _("Set up subtitle behaviour")))
		self.sublist.append(QuickSubMenuEntryComponent(_("EPG settings"), _("EPG setup"), _("Set up your EPG configuration")))
		if not getMachineBrand() == "Beyonwiz":
			self.sublist.append(QuickSubMenuEntryComponent(_("Common Interface"), _("Common Interface configuration"), _("Active/reset and manage your CI")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Parental control"), _("Lock/unlock channels"), _("Set up parental controls")))
		self["sublist"].list = self.sublist

# ####### System Setup Menu ##############################
	def Qsystem(self):
		self.sublist = []
		self.sublist.append(QuickSubMenuEntryComponent(_("GUI settings"), _("GUI and on screen display"), _("Configure your user interface and OSD (on screen display)")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Button settings"), _("Button assignment"), _("Set up your buttons")))
#		self.sublist.append(QuickSubMenuEntryComponent(_("More button settings"), _("Button assignment"), _("Set up more of your buttons")))
		if not getMachineBrand() == "Beyonwiz":
			self.sublist.append(QuickSubMenuEntryComponent(_("Language settings"), _("Setup your language"), _("Set up menu language")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Time settings"), _("Time settings"), _("Set up date and time")))
		if SystemInfo["FrontpanelDisplay"] and SystemInfo["Display"]:
			self.sublist.append(QuickSubMenuEntryComponent(_("Front panel settings"), _("Front panel setup"), _("Set up your front panel")))
		if SystemInfo["GraphicLCD"]:
			self.sublist.append(QuickSubMenuEntryComponent(_("Front panel skin"), _("Skin setup"), _("Set up your front panel skin")))
		if SystemInfo["FanPWM"]:
			self.sublist.append(QuickSubMenuEntryComponent(_("Fan speed"), _("Fan speed control"), _("Configure the speed of the fan")))
		elif SystemInfo["Fan"] and HAVE_FAN_CONTROL:
			self.sublist.append(QuickSubMenuEntryComponent(_("Fan settings"), _("Fan setup"), _("Set up your fan")))
		if HAVE_REMOTE_CONTROL_CODE:
			self.sublist.append(QuickSubMenuEntryComponent(_("Remote control code settings"), _("Remote control code setup"), _("Set up your remote control")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Log settings"), _("Log settings"), _("Configure debug logging")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Factory reset"), _("Load default"), _("Reset all settings to defaults")))
		self["sublist"].list = self.sublist

# ####### Network Menu ##############################
	def Qnetwork(self):
		self.sublist = []
		self.sublist.append(QuickSubMenuEntryComponent(_("Network browser"), _("Search for network shares"), _("Search for network shares")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Mount manager"), _("Manage network mounts"), _("Set up your network mounts")))
		# self.sublist.append(QuickSubMenuEntryComponent(_("Network wizard"), _("Configure your network"), _("Use the Networkwizard to configure your Network. The wizard will help you to setup your network")))
		# if len(self.adapters) > 1: # Show adapter selection if more than 1 adapter is installed, not needed as eth0 is always present.
		self.sublist.append(QuickSubMenuEntryComponent(_("Network adapter selection"), _("Select LAN/WLAN"), _("Set up your network interface. If no USB WLAN stick is present, you can only select LAN")))
		if self.activeInterface is not None:  # Show only if there is already an adapter up.
			self.sublist.append(QuickSubMenuEntryComponent(_("Network interface"), _("Setup interface"), _("Setup network. Here you can setup DHCP, IP, DNS")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Password"), _("Set root password"), _("Set password for network access")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Network restart"), _("Restart network with current setup"), _("Restart network and remount connections")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Samba"), _("Set up Samba"), _("Set up Samba")))
		self.sublist.append(QuickSubMenuEntryComponent(_("NFS"), _("Set up NFS"), _("Set up NFS")))
		self.sublist.append(QuickSubMenuEntryComponent(_("FTP"), _("Set up FTP"), _("Set up FTP")))
		# self.sublist.append(QuickSubMenuEntryComponent(_("AFP"), _("Set up AFP"), _("Set up AFP")))
		# self.sublist.append(QuickSubMenuEntryComponent(_("OpenVPN"), _("Set up OpenVPN"), _("Set up OpenVPN")))
		self.sublist.append(QuickSubMenuEntryComponent(_("DLNA server"), _("Set up MiniDLNA"), _("Set up MiniDLNA")))
		self.sublist.append(QuickSubMenuEntryComponent(_("DYN-DNS"), _("Set up Inadyn"), _("Set up Inadyn")))
		# self.sublist.append(QuickSubMenuEntryComponent(_("SABnzbd"), _("Set up SABnzbd"), _("Set up SABnzbd")))
		# self.sublist.append(QuickSubMenuEntryComponent(_("uShare"), _("Set up uShare"), _("Set up uShare")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Telnet"), _("Set up Telnet"), _("Set up Telnet")))
		self["sublist"].list = self.sublist

# ####### Mount Settings Menu ##############################
	def Qmount(self):
		self.sublist = []
		self.sublist.append(QuickSubMenuEntryComponent(_("Mount manager"), _("Manage network mounts"), _("Set up your network mounts")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Network browser"), _("Search for network shares"), _("Search for network shares")))
		# self.sublist.append(QuickSubMenuEntryComponent(_("Device manager"), _("Mounts devices"), _("Set up your device mounts (USB, HDD, others...)")))
		self["sublist"].list = self.sublist

# ####### Media Menu ##############################
	def Qmedia(self):
		self.sublist = []
		self.sublist.append(QuickSubMenuEntryComponent(_("Picture player"), _("Set up picture player"), _("Configure timeout, thumbnails, etc. for picture slide show")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Media player"), _("Set up media player"), _("Manage play lists, sorting, repeat")))
		self["sublist"].list = self.sublist

# ####### A/V Settings Menu ##############################
	def Qavsetup(self):
		self.sublist = []
		self.sublist.append(QuickSubMenuEntryComponent(_("AV settings"), _("Set up video mode"), _("Set up your video mode, video output and other video settings")))
		if AUDIOSYNC:
			self.sublist.append(QuickSubMenuEntryComponent(_("Audio sync"), _("Set up audio sync"), _("Set up audio sync settings")))
		if VIDEOENH and os_path.exists("/proc/stb/vmpeg/0/pep_apply"):
			self.sublist.append(QuickSubMenuEntryComponent(_("Video enhancement"), _("Video enhancement setup"), _("Video enhancement setup")))
		if VIDEOTUNE:
			self.sublist.append(QuickSubMenuEntryComponent(_("Test screens"), _("Test screens"), _("Test screens that are helpful to fine-tune your display")))
		if config.usage.setup_level.getValue() == "expert":
			self.sublist.append(QuickSubMenuEntryComponent(_("OSD position"), _("Adjust OSD Size"), _("Adjust OSD (on screen display) size")))
		if SystemInfo["CanChange3DOsd"]:
			self.sublist.append(QuickSubMenuEntryComponent(_("OSD 3D setup"), _("OSD 3D mode and depth"), _("Adjust 3D OSD (on screen display) mode and depth")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Skin setup"), _("Choose menu skin"), _("Choose user interface skin")))
		self.sublist.append(QuickSubMenuEntryComponent(_("HDMI-CEC"), _("Consumer Electronics Control"), _("Control up to ten CEC-enabled devices connected through HDMI")))

		self["sublist"].list = self.sublist

# ####### Tuner Menu ##############################
	def Qtuner(self):
		self.sublist = []
		if not SystemInfo["IPTVSTB"]:
			self.sublist.append(QuickSubMenuEntryComponent(_("Tuner allocation"), _("Configure tuner use"), _("Customize how tuners are allocated and used")))
			dvbs_nimList = nimmanager.getNimListOfType("DVB-S")
			dvbt_nimList = nimmanager.getNimListOfType("DVB-T")
			if len(dvbs_nimList) != 0:
				self.sublist.append(QuickSubMenuEntryComponent(_("Tuner configuration"), _("Setup tuner(s)"), _("Setup each tuner for your satellite system")))
				self.sublist.append(QuickSubMenuEntryComponent(_("Automatic scan"), _("Service search"), _("Automatic scan for services")))
			if len(dvbt_nimList) != 0:
				self.sublist.append(QuickSubMenuEntryComponent(_("Tuner configuration"), _("Configure tuner(s)"), _("Select the tuner operating mode and delivery system")))
				self.sublist.append(QuickSubMenuEntryComponent(_("Location scan"), _("Automatic location scan"), _("Automatic scan for services based on your location")))
			self.sublist.append(QuickSubMenuEntryComponent(_("Manual scan"), _("Service search"), _("Manual scan for services")))
			if BLINDSCAN and len(dvbs_nimList) != 0:
				self.sublist.append(QuickSubMenuEntryComponent(_("Blind scan"), _("Blind search"), _("Blind scan for services")))
			if HAVE_SATFINDER and len(dvbs_nimList) != 0:
				self.sublist.append(QuickSubMenuEntryComponent(_("Sat finder"), _("Search sats"), _("Search sats, check signal and lock")))
			if HAVE_LCN_SCANNER:
				self.sublist.append(QuickSubMenuEntryComponent(_("LCN renumber"), _("Automatic LCN assignment"), _("Automatic LCN assignment")))
		if REMOTEBOX:
			self.sublist.append(QuickSubMenuEntryComponent(_("Remote IP channels"), _("Setup channel server IP"), _("Setup server IP for your IP channels")))
		self["sublist"].list = self.sublist

# ####### Software Manager Menu ##############################
	def Qsoftware(self):
		self.sublist = []
		self.sublist.append(QuickSubMenuEntryComponent(_("Create backup"), _("Backup your current settings"), _("Backup your current settings. This includes setup, channels, network and all files selected using the settings below")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Restore backup"), _("Restore settings from a backup"), _("Restore your settings from a backup. After restore your %s %s will reboot in order to activate the new settings") % (getMachineBrand(), getMachineName())))
		self.sublist.append(QuickSubMenuEntryComponent(_("Configure backups"), _("Choose the files to backup"), _("Select which files should be added to the backup option above.")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Check for updates now"), _("Online software update"), _("Check for and install online updates. You must have a working Internet connection.")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Configure update check"), _("Configure online update checks"), _("Configure periodical checks for online updates. You must have a working Internet connection.")))
		# self.sublist.append(QuickSubMenuEntryComponent(_("Complete backup"), _("Backup your current image"), _("Backup your current image to HDD or USB. This will make a 1:1 copy of your box")))
		self["sublist"].list = self.sublist

# ####### Plugins Menu ##############################
	def Qplugin(self):
		self.sublist = []
		self.sublist.append(QuickSubMenuEntryComponent(_("Plugin browser"), _("Open the plugin browser"), _("Shows plugins browser, where you can configure installed plugins")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Download plugins"), _("Download and install plugins"), _("Shows available plugins or download and install new ones")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Remove plugins"), _("Delete plugins"), _("Delete and uninstall plugins.")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Package installer"), _("Install local extension"), _("Scan HDD and USB media for local extensions and install them")))
		self["sublist"].list = self.sublist

# ####### Harddisk Menu ##############################
	def Qharddisk(self):
		self.sublist = []
		self.sublist.append(QuickSubMenuEntryComponent(_("Hard disk setup"), _("Hard disk setup"), _("Configure hard disk options, such as standby timeout")))
		self.sublist.append(QuickSubMenuEntryComponent(_("Format hard disk"), _("Format HDD"), _("Format your hard disk")))
		self.sublist.append(QuickSubMenuEntryComponent(_("File system check"), _("Check HDD"), _("Check the integrity of the file system on your hard disk")))
		# if isFileSystemSupported("ext4"):
		# 	self.sublist.append(QuickSubMenuEntryComponent(_("Convert ext3 to ext4"), _("Convert file system from ext3 to ext4"), _("Convert file system from ext3 to ext4")))
		self["sublist"].list = self.sublist

	def ok(self):
		if self.menu > 0:
			self.okSubList()
		else:
			self.goRight()


# ####################################################################
# ####### Make Selection MAIN MENU LIST ##############################
# ####################################################################

	def okList(self):
		item = self["list"].getCurrent()
		selected = item[0][0]

# ####### Select Network Menu ##############################
		if selected == _("Network"):
			self.GetNetworkInterfaces()
			self.Qnetwork()
# ####### Select System Setup Menu ##############################
		elif selected == _("System"):
			self.Qsystem()
# ####### Select TV Setup Menu ##############################
		elif selected == _("TV"):
			self.Qtv()
# ####### Select Mount Menu ##############################
		elif selected == _("Mounts"):
			self.Qmount()
# ####### Select Media Menu ##############################
		elif selected == _("Media"):
			self.Qmedia()
# ####### Select AV Setup Menu ##############################
		elif selected == _("AV setup"):
			self.Qavsetup()
# ####### Select Tuner Setup Menu ##############################
		elif selected == _("Tuners") or selected == _("IPTV configuration"):
			self.Qtuner()
# ####### Select Software Manager Menu ##############################
		elif selected == _("Software manager"):
			self.Qsoftware()
# ####### Select PluginDownloadBrowser Menu ##############################
		elif selected == _("Plugins"):
			self.Qplugin()
# ####### Select Storage Setup Menu ##############################
		elif selected == _("Storage"):
			self.Qharddisk()
		self["sublist"].setSelectionEnabled(0)

# ####################################################################
# ####### Make Selection SUB MENU LIST ##############################
# ####################################################################

	def okSubList(self):
		item = self["sublist"].getCurrent()
		selected = item[0][0]

# ####### Select Network Menu ##############################
		if selected == _("Network wizard"):
			self.session.open(NetworkWizard)
		elif selected == _("Network adapter selection"):
			self.session.open(NetworkAdapterSelection)
		elif selected == _("Network interface"):
			self.session.open(AdapterSetup, networkinfo=self.activeInterface)
		elif selected == _("Network restart"):
			self.session.open(RestartNetwork)
		elif selected == _("Samba"):
			self.session.open(NetworkSamba)
		elif selected == _("NFS"):
			self.session.open(NetworkNfs)
		elif selected == _("FTP"):
			self.session.open(NetworkFtp)
		elif selected == _("AFP"):
			self.session.open(NetworkAfp)
		elif selected == _("OpenVPN"):
			self.session.open(NetworkOpenvpn)
		elif selected == _("DLNA server"):
			self.session.open(NetworkMiniDLNA)
		elif selected == _("DYN-DNS"):
			self.session.open(NetworkInadyn)
		# elif selected == _("SABnzbd"):
		# 	self.session.open(NetworkSABnzbd)
		elif selected == _("uShare"):
			self.session.open(NetworkuShare)
		elif selected == _("Telnet"):
			self.session.open(NetworkTelnet)
		elif selected == _("Password"):
			self.session.open(NetworkPassword)
# ####### Select AV Setup Menu ##############################
		elif selected == _("AV setup"):
			self.Qavsetup()
# ####### Select System Setup Menu ##############################
		elif selected == _("Time settings"):
			self.openSetup("time")
		elif selected == _("Language settings"):
			self.session.open(LanguageSelection)
		elif selected == _("Front panel settings"):
			self.openSetup("display")
		elif selected == _("Skin setup"):
			self.session.open(SkinSelector)
		elif selected == _("Front panel skin"):
			self.session.open(LcdSkinSelector)
		elif selected == _("GUI settings"):
			self.openSetup("userinterface")
		elif selected == _("Button settings"):
			self.openSetup("buttonsetup")
		elif selected == _("More button settings"):
			self.session.open(ButtonSetup)
		elif selected == _("HDMI-CEC"):
			from Plugins.SystemPlugins.HdmiCEC.plugin import HdmiCECSetupScreen
			self.session.open(HdmiCECSetupScreen)
		elif selected == _("Remote control code settings"):
			self.session.open(RCSetupScreen)
		elif selected == _("Fan settings"):
			self.session.open(FanSetupScreen)
		elif selected == _("Fan speed"):
			self.openSetup("fanspeed")
		elif selected == _("Automatic volume settings"):
			self.session.open(AutomaticVolumeAdjustmentConfigScreen)
		elif selected == _("Log settings"):
			self.openSetup("logs")
		elif selected == _("Factory reset"):
			from Screens.FactoryReset import FactoryReset

			def deactivateInterfaceCB(data):
				if data is True:
					applyConfigDataAvail(True)

			def activateInterfaceCB(self, data):
				if data is True:
					iNetwork.activateInterface("eth0", applyConfigDataAvail)

			def applyConfigDataAvail(data):
				if data is True:
					iNetwork.getInterfaces(getInterfacesDataAvail)

			def getInterfacesDataAvail(data):
				if data is True:
					pass

			def msgClosed(ret):
				if ret:
					self.session.open(TryQuitMainloop, retvalue=QUIT_FACTORY_RESET)
			self.session.openWithCallback(msgClosed, FactoryReset)
# ####### Select TV Setup Menu ##############################
		elif selected == _("Channel selection"):
			self.openSetup("channelselection")
		elif selected == _("Recording settings"):
			from Screens.Recordings import RecordingSettings
			self.session.open(RecordingSettings)
		elif selected == _("HDMI Recording settings"):
			self.openSetup("hdmirecord")
		elif selected == _("Timeshift settings"):
			from Screens.Timeshift import TimeshiftSettings
			self.session.open(TimeshiftSettings)
		elif selected == _("Auto language"):
			self.openSetup("autolanguagesetup")
		elif selected == _("Subtitle settings"):
			self.openSetup("subtitlesetup")
		elif selected == _("EPG settings"):
			self.openSetup("epgsettings")
		elif selected == _("Common Interface"):
			from Screens.Ci import CiSelection
			self.session.open(CiSelection)
		elif selected == _("Parental control"):
			from Screens.ParentalControlSetup import ParentalControlSetup
			self.session.open(ParentalControlSetup)
# ####### Select Mounts Menu ##############################
		elif selected == _("Mount manager"):
			self.session.open(AutoMountManager, None, plugin_path_networkbrowser)
		elif selected == _("Network browser"):
			self.session.open(NetworkBrowser, None, plugin_path_networkbrowser)
		# elif selected == _("Device manager"):
		# 	self.session.open(HddMount)
# ####### Select Media Menu ##############################
		elif selected == _("Picture player"):
			from Plugins.Extensions.PicturePlayer.ui import Pic_Setup
			self.session.open(Pic_Setup)
		elif selected == _("Media player"):
			from Plugins.Extensions.MediaPlayer.settings import MediaPlayerSettings
			self.session.open(MediaPlayerSettings, self)
# ####### Select AV Setup Menu ##############################
		elif selected == _("AV settings"):
			self.session.open(VideoSetup)
		elif selected == _("Audio sync"):
			self.session.open(AC3LipSyncSetup, plugin_path_audiosync)
		elif selected == _("Video enhancement"):
			self.session.open(VideoEnhancementSetup)
		elif selected == _("Test screens"):
			self.session.open(VideoFinetune)
		elif selected == _("OSD position"):
			from Screens.UserInterfacePositioner import UserInterfacePositioner
			self.session.open(UserInterfacePositioner)
		elif selected == _("OSD 3D setup"):
			from Screens.UserInterfacePositioner import OSD3DSetupScreen
			self.session.open(OSD3DSetupScreen)
# ####### Select TUNER Setup Menu ##############################
		elif selected == _("Tuner allocation"):
			self.openSetup("tunersetup")
		elif selected == _("Location scan"):
			from Screens.IniTerrestrialLocation import IniTerrestrialLocation
			self.session.open(IniTerrestrialLocation)
		elif selected == _("Remote IP channels"):
			self.session.open(RemoteTunerScanner)
		elif selected == _("Tuner configuration"):
			self.session.open(NimSelection)
		elif HAVE_POSITIONERSETUP and selected == _("Positioner setup"):
			self.PositionerMain()
		elif selected == _("Automatic scan"):
			self.session.open(ScanSimple)
		elif selected == _("Manual scan"):
			self.session.open(ScanSetup)
		elif selected == _("Blind scan"):
			self.session.open(Blindscan)
		elif HAVE_SATFINDER and selected == _("Sat finder"):
			self.SatfinderMain()
		elif HAVE_LCN_SCANNER and selected == _("LCN renumber"):
			self.session.open(LCNScannerPlugin)
# ####### Select Software Manager Menu ##############################
		elif selected == _("Create backup"):
			self.session.openWithCallback(self.backupDone, BackupScreen, runBackup=True)
		elif selected == _("Restore backup"):
			if path.exists(path.join(getBackupPath(), getBackupFilename())):
				self.session.openWithCallback(
					self.startRestore, MessageBox,
					_("Are you sure you want to restore your %s %s backup?\nYour %s %s will reboot after the restore") %
					(getMachineBrand(), getMachineName(), getMachineBrand(), getMachineName()))
			else:
				self.session.open(MessageBox, _("Sorry no backups found!"), MessageBox.TYPE_INFO, timeout=10)
		elif selected == _("Configure backups"):
			self.session.openWithCallback(self.backupfiles_choosen, BackupSelection)
		elif selected == _("Check for updates now"):
			self.session.open(UpdatePlugin)
		elif selected == _("Configure update check"):
			self.openSetup("softwareupdate")
		# elif selected == _("Software Manager Setup"):
		# 	self.session.open(SoftwareManagerSetup)
# ####### Select PluginDownloadBrowser Menu ##############################
		elif selected == _("Plugin browser"):
			self.session.open(PluginBrowser)
		elif selected == _("Download plugins"):
			self.session.open(PluginDownloadBrowser, type=PluginDownloadBrowser.DOWNLOAD)
		elif selected == _("Remove plugins"):
			self.session.open(PluginDownloadBrowser, type=PluginDownloadBrowser.REMOVE)
		elif selected == _("Package installer"):
			try:
				from Plugins.Extensions.MediaScanner.plugin import main
				main(self.session)
			except:
				self.session.open(MessageBox, _("Sorry MediaScanner is not installed!"), MessageBox.TYPE_INFO, timeout=10)
# ####### Select Harddisk Menu ############################################
		elif selected == _("Hard disk setup"):
			self.openSetup("harddisk")
		elif selected == _("Format hard disk"):
			self.session.open(HarddiskSelection)
		elif selected == _("File system check"):
			self.session.open(HarddiskFsckSelection)
		elif selected == _("Convert ext3 to ext4"):
			self.session.open(HarddiskConvertExt4Selection)

# ####### OPEN SETUP MENUS ####################
	def openSetup(self, dialog):
		self.session.openWithCallback(self.menuClosed, Setup, dialog)

	def menuClosed(self, *res):
		pass

# ####### NETWORK TOOLS #######################
	def GetNetworkInterfaces(self):
		self.adapters = [(iNetwork.getFriendlyAdapterName(x), x) for x in iNetwork.getAdapterList()]

		if not self.adapters:
			self.adapters = [(iNetwork.getFriendlyAdapterName(x), x) for x in iNetwork.getConfiguredAdapters()]

		if len(self.adapters) == 0:
			self.adapters = [(iNetwork.getFriendlyAdapterName(x), x) for x in iNetwork.getInstalledAdapters()]

		self.activeInterface = None

		for x in self.adapters:
			if iNetwork.getAdapterAttribute(x[1], 'up') is True:
				self.activeInterface = x[1]
				return


# ####### TUNER TOOLS #######################
	if HAVE_POSITIONERSETUP:
		def PositionerMain(self):
			nimList = nimmanager.getNimListOfType("DVB-S")
			if len(nimList) == 0:
				self.session.open(MessageBox, _("No positioner capable frontend found."), MessageBox.TYPE_ERROR)
			else:
				if len(NavigationInstance.instance.getRecordings()) > 0:
					self.session.open(MessageBox, _("A recording is currently running. Please stop the recording before trying to configure the positioner."), MessageBox.TYPE_ERROR)
				else:
					usableNims = []
					for x in nimList:
						configured_rotor_sats = nimmanager.getRotorSatListForNim(x)
						if len(configured_rotor_sats) != 0:
							usableNims.append(x)
					if len(usableNims) == 1:
						self.session.open(PositionerSetup, usableNims[0])
					elif len(usableNims) > 1:
						self.session.open(RotorNimSelection)
					else:
						self.session.open(MessageBox, _("No tuner is configured for use with a diseqc positioner!"), MessageBox.TYPE_ERROR)

	if HAVE_SATFINDER:
		def SatfinderMain(self):
			nims = nimmanager.getNimListOfType("DVB-S")

			nimList = []
			for x in nims:
				if nimmanager.getNimConfig(x).configMode.value in ("loopthrough", "satposdepends", "nothing"):
					continue
				if nimmanager.getNimConfig(x).configMode.value == "advanced" and len(nimmanager.getSatListForNim(x)) < 1:
					continue
				nimList.append(x)

			if len(nimList) == 0:
				self.session.open(MessageBox, _("No satellites configured. Plese check your tuner setup."), MessageBox.TYPE_ERROR)
			else:
				if self.session.nav.RecordTimer.isRecording():
					self.session.open(MessageBox, _("A recording is currently running. Please stop the recording before trying to start the satfinder."), MessageBox.TYPE_ERROR)
				else:
					self.session.open(Satfinder)


# ####### SOFTWARE MANAGER TOOLS #######################
	def backupfiles_choosen(self, ret):
		config.plugins.configurationbackup.backupdirs.save()
		config.plugins.configurationbackup.save()
		config.save()

	def backupDone(self, retval=None):
		if retval is True:
			self.session.open(MessageBox, _("Backup done."), MessageBox.TYPE_INFO, timeout=10)
		else:
			self.session.open(MessageBox, _("Backup failed."), MessageBox.TYPE_ERROR)

	def startRestore(self, ret=False):
		if ret:
			self.exe = True
			self.session.open(RestoreScreen, runRestore=True)

class RestartNetwork(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		skin = """
			<screen name="RestartNetwork" position="center,center" size="600,100" title="Restart network adapter">
			<widget name="label" position="10,30" size="500,50" halign="center" font="Regular;20" transparent="1" foregroundColor="white" />
			</screen> """
		self.skin = skin
		self["label"] = Label(_("Please wait while your network is restarting..."))
		self.onShown.append(self.setWindowTitle)
		self.onLayoutFinish.append(self.restartLan)

	def setWindowTitle(self):
		self.setTitle(_("Restart network adapter"))

	def restartLan(self):
		iNetwork.restartNetwork(self.restartLanDataAvail)

	def restartLanDataAvail(self, data):
		if data is True:
			iNetwork.getInterfaces(self.getInterfacesDataAvail)

	def getInterfacesDataAvail(self, data):
		self.close()

scrollbar_width = 10
padding_width = 10

# ####### Create MENULIST format #######################
def GeneralSetupEntryComponent(name, description, long_description=None, endtext=">"):
	return ((name, long_description), name, endtext, description)

def QuickSubMenuEntryComponent(name, description, long_description=None):
	return ((name, long_description), name, description)
