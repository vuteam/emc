from Screen import Screen
from Components.Button import Button
from Components.ActionMap import HelpableActionMap, ActionMap, NumberActionMap, HelpableNumberActionMap
from Components.ChoiceList import ChoiceList, ChoiceEntryComponent
from Components.MovieList import MovieList, resetMoviePlayState, AUDIO_EXTENSIONS, DVD_EXTENSIONS, IMAGE_EXTENSIONS, moviePlayState, is_counted
from Components.DiskInfo import DiskInfo
from Tools.Trashcan import TrashInfo
from Components.Pixmap import Pixmap, MultiPixmap
from Components.Label import Label
from Components.PluginComponent import plugins
from Components.config import config, ConfigSubsection, ConfigText, ConfigInteger, ConfigLocations, ConfigSet, ConfigYesNo, ConfigSelection, getConfigListEntry, ConfigSelectionNumber
from Components.ConfigList import ConfigListScreen
from Components.ServiceEventTracker import ServiceEventTracker, InfoBarBase
from Components.Sources.ServiceEvent import ServiceEvent
from Components.Sources.StaticText import StaticText
from Components.Sources.List import List
import Components.Harddisk
from Components.UsageConfig import preferredTimerPath
from Components.Sources.Boolean import Boolean
from Plugins.Plugin import PluginDescriptor
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Screens.LocationBox import MovieLocationBox, friendlyMoviePath
from Screens.HelpMenu import HelpableScreen
from Screens.InputBox import PinInput
import Screens.InfoBar
from Tools import NumericalTextInput
from Tools.Directories import resolveFilename, SCOPE_HDD
from Tools.BoundFunction import boundFunction
import Tools.CopyFiles
import Tools.Trashcan
import NavigationInstance
import RecordTimer
from boxbranding import getBoxType

from enigma import eServiceReference, eServiceReferenceFS, eServiceCenter, eTimer, eSize, iPlayableService, iServiceInformation, getPrevAsciiCode, eRCInput
import os
import time
import cPickle as pickle
config.movielist = ConfigSubsection()
config.movielist.curentlyplayingservice = ConfigText()
config.movielist.show_live_tv_in_movielist = ConfigYesNo(default=True)
config.movielist.fontsize = ConfigSelectionNumber(default=0, stepwidth=1, min=-8, max=10, wraparound=True)
config.movielist.itemsperpage = ConfigSelectionNumber(default=20, stepwidth=1, min=3, max=30, wraparound=True)
config.movielist.useslim = ConfigYesNo(default=False)
config.movielist.use_fuzzy_dates = ConfigYesNo(default=True)
config.movielist.showlengths = ConfigSelection(default="auto", choices=["no", "yes", "auto"])
config.movielist.showsizes = ConfigSelection(default="auto", choices=["no", "yes", "auto"])
config.movielist.moviesort = ConfigInteger(default=MovieList.SORT_GROUPWISE)
config.movielist.description = ConfigInteger(default=MovieList.SHOW_DESCRIPTION)
config.movielist.last_videodir = ConfigText(default=resolveFilename(SCOPE_HDD))
config.movielist.last_videodirpos = ConfigText(default="")
config.movielist.last_timer_videodir = ConfigText(default=resolveFilename(SCOPE_HDD))
config.movielist.videodirs = ConfigLocations(default=[resolveFilename(SCOPE_HDD)])
config.movielist.last_selected_tags = ConfigSet([], default=[])
config.movielist.play_audio_internal = ConfigYesNo(default=True)
config.movielist.settings_per_directory = ConfigYesNo(default=True)
config.movielist.root = ConfigSelection(default="/media", choices=["/", "/media", "/media/hdd", "/media/hdd/movie"])
config.movielist.hide_extensions = ConfigYesNo(default=False)
config.movielist.use_last_videodirpos = ConfigYesNo(default=True)
config.movielist.subdir_count = ConfigYesNo(default=False)
config.movielist.counteddirs = ConfigLocations()
config.movielist.uncounteddirs = ConfigLocations()
config.movielist.stop_service = ConfigYesNo(default=True)  # Unused - implementation removed

# Clear config.movielist.stop_service from the settings file.
# This code can probably be removed after a while.

if config.movielist.stop_service.value != config.movielist.stop_service.default:
	from Components.config import configfile
	config.movielist.stop_service.value = config.movielist.stop_service.default
	config.movielist.stop_service.save()
	configfile.save()

userDefinedButtons = None
last_selected_dest = []
preferredTagEditor = None

# Extra mappings between extensions and service types.
extraExtensionServTypes = '16384:jpg 16384:png 16384:gif 16384:bmp'

# this kludge is needed because ConfigSelection only takes strings
# and someone appears to be fascinated by 'enums'.
l_moviesort = [
	(str(MovieList.SORT_GROUPWISE), _("Recordings by date, other media by name"), 'Rec New->Old & A->Z'),
	(str(MovieList.SORT_DATE_NEWEST_FIRST_ALPHA), _("By date, then by name"), 'New->Old, A->Z'),
	(str(MovieList.SORT_DATE_OLDEST_FIRST_ALPHAREV), _("By reverse date, then by reverse name"), 'Old->New, Z->A'),
	(str(MovieList.SORT_ALPHA_DATE_NEWEST_FIRST), _("By name, then by date"), 'A->Z, New->Old'),
	(str(MovieList.SORT_ALPHA_DATE_NEWEST_FIRST_FLAT), _("Flat by name, then by date"), 'Flat A->Z, New->Old'),
	(str(MovieList.SORT_ALPHA_DATE_OLDEST_FIRST), _("By name, then by reverse date"), 'A->Z, Old->New'),
	(str(MovieList.SORT_ALPHAREV_DATE_NEWEST_FIRST), _("By reverse name, then by date"), 'Z->A, New->Old'),
	(str(MovieList.SORT_ALPHAREV_DATE_OLDEST_FIRST), _("By reverse name, then by reverse date"), 'Z->A, Old->New'),
	(str(MovieList.SORT_ALPHAREV_DATE_OLDEST_FIRST_FLAT), _("Flat by reverse name, then by reverse date"), 'Flat Z->A, Old->New'),
	(str(MovieList.SORT_DURATION_ALPHA), _("By duration, then by name"), 'Short->Long A->Z'),
	(str(MovieList.SORT_DURATIONREV_ALPHA), _("By reverse duration, then by name"), 'Long->Short A->Z'),
	(str(MovieList.SORT_SIZE_ALPHA), _("By file size, then by name"), 'Small->Large A->Z'),
	(str(MovieList.SORT_SIZEREV_ALPHA), _("By reverse file size, then by name"), 'Large->Small A->Z'),
	(str(MovieList.SHUFFLE), _("Shuffle"), 'Shuffle'),
]

# GML:1
# 4th item is the textual value set in UsageConfig.py
l_trashsort = [
	(str(MovieList.TRASHSORT_SHOWRECORD), _("By delete time, show record time (Trash ONLY)"), '03/02/01', "show record time"),
	(str(MovieList.TRASHSORT_SHOWDELETE), _("By delete time, show delete time (Trash ONLY)"), '03/02/01', "show delete time")]

try:
	from Plugins.Extensions import BlurayPlayer
except Exception as e:
	print "[MovieSelection] Bluray Player is not installed:", e
	BlurayPlayer = None


def defaultMoviePath():
	result = config.usage.default_path.value
	if not os.path.isdir(result):
		from Tools import Directories
		return Directories.defaultRecordingLocation()
	return result

def setPreferredTagEditor(te):
	global preferredTagEditor
	if preferredTagEditor is None:
		preferredTagEditor = te
		print "[MovieSelection] Preferred tag editor changed to", preferredTagEditor
	else:
		print "[MovieSelection] Preferred tag editor already set to", preferredTagEditor, "ignoring", te

def getPreferredTagEditor():
	global preferredTagEditor
	return preferredTagEditor

def isTrashFolder(ref):
	if not config.usage.movielist_trashcan.value or not ref.flags & eServiceReference.mustDescent:
		return False
	return os.path.realpath(ref.getPath()).endswith('.Trash') or os.path.realpath(ref.getPath()).endswith('.Trash/')

def isInTrashFolder(ref):
	if not config.usage.movielist_trashcan.value or not ref.flags & eServiceReference.mustDescent:
		return False
	path = os.path.realpath(ref.getPath())
	return path.startswith(Tools.Trashcan.getTrashFolder(path))

def isSimpleFile(item):
	if not item:
		return False
	if not item[0] or not item[1]:
		return False
	return (item[0].flags & eServiceReference.mustDescent) == 0

def isFolder(item):
	if not item:
		return False
	if not item[0] or not item[1]:
		return False
	return (item[0].flags & eServiceReference.mustDescent) != 0

def canMove(item):
	if not item:
		return False
	if not item[0] or not item[1]:
		return False
	return True

canDelete = canMove
canCopy = canMove
canRename = canMove

def findMatchingServiceRefs(path, filenames):
	path = os.path.normpath(path)
	pathRef = eServiceReference(eServiceReference.idFile, eServiceReference.noFlags, eServiceReferenceFS.directory)
	pathRef.setPath(os.path.join(path, ""))
	# Magic: this sets extra mappings between extensions and service types.
	pathRef.setName(extraExtensionServTypes)

	if filenames is None:
		return os.isdir(path) and {path: pathRef} or {}
	if not filenames:
		return {}
	if isinstance(filenames, str):
		filenames = (filenames, )

	serviceHandler = eServiceCenter.getInstance()
	reflist = serviceHandler.list(pathRef)
	if reflist is None:
		return {}

	fileset = set((os.path.join(path, fn) for fn in filenames))
	matches = {}
	serviceref = reflist.getNext()
	while fileset and serviceref.valid():
		matchPath = serviceref.getPath()
		if matchPath in fileset:
			matches[matchPath] = serviceref
			fileset.remove(matchPath)
		serviceref = reflist.getNext()
	return matches

def createMoveList(serviceref, dest):
	# normpath is to remove the trailing '/' from directories
	src = isinstance(serviceref, str) and serviceref + ".ts" or os.path.normpath(serviceref.getPath())
	srcPath, srcName = os.path.split(src)
	if os.path.normpath(srcPath) == dest:
		# move file to itself is allowed, so we have to check it
		raise Exception("Refusing to move to the same directory")
	# Make a list of items to move
	moveList = [(src, os.path.join(dest, srcName))]
	if isinstance(serviceref, str) or not serviceref.flags & eServiceReference.mustDescent:
		# Real movie, add extra files...
		srcBase = os.path.splitext(src)[0]
		baseName = os.path.split(srcBase)[1]
		eitName = srcBase + '.eit'
		if os.path.exists(eitName):
			moveList.append((eitName, os.path.join(dest, baseName + '.eit')))
		baseName = os.path.split(src)[1]
		for ext in ('.ap', '.cuts', '.meta', '.sc'):
			candidate = src + ext
			if os.path.exists(candidate):
				moveList.append((candidate, os.path.join(dest, baseName + ext)))
	return moveList

def __convertFilenameToServiceref(name):  # if possible. Otherwise return name
	from MovieSelection import findMatchingServiceRefs
	if os.isdir(serviceref):
		serviceRefMap = findMatchingServiceRefs(serviceref, None)
	else:
		serviceRefMap = findMatchingServiceRefs(*os.path.split(serviceref))
	if serviceRefMap and serviceref in serviceRefMap:
		return serviceRefMap[serviceref]
	else:
		return name

def moveServiceFiles(serviceref, dest, name=None, allowCopy=True):
	moveList = createMoveList(serviceref, dest)

	if isinstance(serviceref, str):
		serviceref = __convertFilenameToServiceref(serviceref)

	# Try to "atomically" move these files
	try:
		# print "[MovieSelection] Moving in background..."
		# start with the smaller files, do the big one later.
		moveList.reverse()
		if name is None:
			name = os.path.split(moveList[-1][0])[1]
		Tools.CopyFiles.moveFiles(moveList, name)
		from Screens.InfoBarGenerics import renameResumePoint
		if not isinstance(serviceref, str):
			renameResumePoint(serviceref, moveList[-1][1])
	except Exception, e:
		print "[MovieSelection] Failed move:", e
		# rethrow exception
		raise

def copyServiceFiles(serviceref, dest, name=None):
	# current should be 'ref' type, dest a simple path string
	moveList = createMoveList(serviceref, dest)

	if isinstance(serviceref, str):
		serviceref = __convertFilenameToServiceref(serviceref)

	# Try to "atomically" move these files
	try:
		# print "[MovieSelection] Copying in background..."
		# start with the smaller files, do the big one later.
		moveList.reverse()
		if name is None:
			name = os.path.split(moveList[-1][0])[1]
		Tools.CopyFiles.copyFiles(moveList, name)
		from Screens.InfoBarGenerics import renameResumePoint
		if not isinstance(serviceref, str):
			renameResumePoint(serviceref, moveList[0][1], copy=True)
	except Exception, e:
		print "[MovieSelection] Failed copy:", e
		# rethrow exception
		raise

# Appends possible destinations to the bookmarks object. Appends tuples
# in the form (description, path) to it.
def buildMovieLocationList(bookmarks, base=None):
	if base:
		base = base.rstrip('/') or '/'
		inlist = [base]
	else:
		inlist = []
	# Last favourites
	for d in last_selected_dest:
		d = d.rstrip('/') or '/'
		if d not in inlist:
			bookmarks.append((friendlyMoviePath(d, base), d))
			inlist.append(d)
	# Other favourites
	for d in config.movielist.videodirs.value:
		d = os.path.normpath(d).rstrip('/') or '/'
		if d not in inlist:
			bookmarks.append((friendlyMoviePath(d, base), d))
			inlist.append(d)
	subpos = len(bookmarks)
	# Mounts
	for p in Components.Harddisk.harddiskmanager.getMountedPartitions():
		d = os.path.normpath(p.mountpoint)
		desc = friendlyMoviePath(d)
		if desc == d:
			desc = p.description
		if d in inlist:
			# improve shortcuts to mountpoints
			try:
				bookmarks[bookmarks.index((d, d))] = (desc, d)
			except:
				pass  # When already listed as some "friendly" name
		else:
			bookmarks.append((desc, d))
			inlist.append(d)
	if base:
		# Subdirs - inserted before mounts to fill the page.
		# If they would create another page, don't add any at all.
		try:
			sub_bm = []
			#sub_in = []					# not necessary, nothing follows
			items = len(bookmarks) + 1		# one more for Other
			maxitems = (items + 14) / 15 * 15	# ChoiceBox has 15 items per page
			for fn in os.listdir(base):
				if not fn.startswith('.'):  # Skip hidden things
					d = os.path.join(base, fn)
					if os.path.isdir(d) and d not in inlist:
						if items == maxitems:
							sub_bm = None
							break
						items += 1
						sub_bm.append((friendlyMoviePath(d, base), d))
						#sub_in.append(d)
			if sub_bm:
				sub_bm.sort()
				bookmarks[subpos:subpos] = sub_bm
				#inlist.extend(sub_in)
		except Exception, e:
			print "[MovieSelection]", e

def updateUserDefinedActions():
	global userDefinedButtons, userDefinedActions, userDefinedDescriptions
	locations = []
	buildMovieLocationList(locations)
	prefix = _("Goto") + ": "
	for act, val in userDefinedActions.items():
		if act.startswith(prefix):
			del userDefinedActions[act]
			del userDefinedDescriptions[act]
	for d, p in locations:
		if p and p.startswith('/'):
			userDefinedDescriptions[p] = userDefinedActions[p] = prefix + d
	userDefinedChoices = sorted(userDefinedActions.iteritems(), key=lambda x: x[1].lower())
	for btn in userDefinedButtons.values():
		btn.setChoices(userDefinedChoices[:], default=btn.default)
		if btn.value.startswith('/'):
			#btn.setValue(btn.value)
			btn._descr = None

class MovieBrowserConfiguration(ConfigListScreen, Screen):
	def __init__(self, session, args=0):
		Screen.__init__(self, session)
		self.session = session
		self.skinName = [self.skinName, "Setup"]
		self.setup_title = _("Movie List Actions")
		Screen.setTitle(self, self.setup_title)
		self["HelpWindow"] = Pixmap()
		self["HelpWindow"].hide()
		self["VKeyIcon"] = Boolean(False)
		self['footnote'] = Label("")
		self["description"] = Label("")

		self.onChangedEntry = []
		cfg = ConfigSubsection()
		self.cfg = cfg
		cfg.moviesort = ConfigSelection(default=str(config.movielist.moviesort.value), choices=l_moviesort)
		cfg.description = ConfigYesNo(default=(config.movielist.description.value != MovieList.HIDE_DESCRIPTION))
# GML:2 - movielist_trashcan_days
# GML:1 - trashsort_deltime
		ConfigListScreen.__init__(self, [], session=self.session, on_change=self.changedEntry)
		self.createConfig()
		self.notify = (
			config.usage.movielist_trashcan,
			config.misc.erase_flags,
			config.usage.show_icons_in_movielist,
			config.misc.location_aliases,
		)
		self.addNotifiers()
		self.onClose.append(self.clearNotifiers)

		self["actions"] = ActionMap(["SetupActions", 'ColorActions'], {
			"red": self.cancel,
			"green": self.save,
			"save": self.save,
			"cancel": self.cancel,
			"ok": self.save,
			"menu": self.cancel,
		}, -2)
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("OK"))
		self["key_yellow"] = StaticText()
		self["key_blue"] = StaticText()
		if self.selectionChanged not in self["config"].onSelectionChanged:
			self["config"].onSelectionChanged.append(self.selectionChanged)
		self.selectionChanged()

	def addNotifiers(self):
		for n in self.notify:
			n.addNotifier(self.updateConfig, initial_call=False)

	def clearNotifiers(self):
		for n in self.notify:
			n.removeNotifier(self.updateConfig)

	def createConfig(self):
		cfg = self.cfg
		configList = [
			getConfigListEntry(_("Use trash in movie list"), config.usage.movielist_trashcan, _("When enabled, deleted recordings are moved to trash, instead of being deleted immediately.")),
		]
		if config.usage.movielist_trashcan.value:
			configList += [
				getConfigListEntry(_("Ask before moving any item to trash"), config.usage.movielist_asktrash, _("When enabled, confirm before moving any item to trash, not just directories.")),
				getConfigListEntry(_("Remove items from trash after (days)"), config.usage.movielist_trashcan_days, _("Configure the number of days after which items are automatically deleted from trash.")),
				getConfigListEntry(_("Clean network trash"), config.usage.movielist_trashcan_network_clean, _("When enabled, trash processing is also applied to network trash.")),
				getConfigListEntry(_("Disk space to reserve for recordings (in GB)"), config.usage.movielist_trashcan_reserve, _("Minimum amount of disk space to be kept available for recordings. When the free disk space drops below this value, items will be deleted from trash.")),
				getConfigListEntry(_("Background delete option"), config.misc.erase_flags, _("Configure on which devices the background delete option should be used.")),
			]
			if int(config.misc.erase_flags.value):
				configList.append(getConfigListEntry(_("Background delete speed"), config.misc.erase_speed, _("Configure the speed of the background deletion process. Lower speed will consume less hard disk drive performance.")))
		configList += [
			getConfigListEntry(_("Font size"), config.movielist.fontsize, _("This allows you change the font size relative to skin size, so 1 increases by 1 point size, and -1 decreases by 1 point size.")),
			getConfigListEntry(_("Number of rows"), config.movielist.itemsperpage, _("Number of rows on each page.")),
			getConfigListEntry(_("Use slim screen"), config.movielist.useslim, _("Use the alternative slim screen.")),
			getConfigListEntry(_("Use location aliases"), config.misc.location_aliases, _("Show paths with a custom name.")),
			getConfigListEntry(_("Use adaptive date display"), config.movielist.use_fuzzy_dates, _("Adaptive date display allows recent dates to be displayed as 'Today' or 'Yesterday'.  It hides the year for recordings made this year.  It hides the day of the week for recordings made in previous years.")),
			getConfigListEntry(_("Show directory counts"), config.movielist.subdir_count, _("Show the count of files and directories within each subdirectory. Individual subdirectories can be set independently of this option.")),
			getConfigListEntry(_("Show movie durations"), config.movielist.showlengths, _("Show movie durations in the movie list. When the setting is 'auto', the column is only shown when it is used as a sort key.")),
			getConfigListEntry(_("Show movie file sizes"), config.movielist.showsizes, _("Show movie file sizes in the movie list. When the setting is 'auto', the column is only shown when it is used as a sort key.")),
			getConfigListEntry(_("Sort"), cfg.moviesort, _("Set the default sorting method.")),
			getConfigListEntry(_("Sort trash by deletion time"), config.usage.trashsort_deltime, _("Use the deletion time to sort items in trash.\nMost recently deleted at the top.")),
			getConfigListEntry(_("Show extended description"), cfg.description, _("Show or hide the extended description, (skin dependent).")),
			getConfigListEntry(_("Use individual settings for each directory"), config.movielist.settings_per_directory, _("When set, each directory will show the previous state used. When off, the default values will be shown.")),
			getConfigListEntry(_("When a movie reaches the end"), config.usage.on_movie_eof, _("What to do at the end of file playback.")),
			getConfigListEntry(_("Show status icons in movie list"), config.usage.show_icons_in_movielist, _("Shows the 'watched' status of the movie."))
		]

		if config.usage.show_icons_in_movielist.value != 'o':
			configList.append(getConfigListEntry(_("Show icon for new/unwatched items"), config.usage.movielist_unseen, _("Shows an icon when new/unwatched, otherwise don't show an icon.")))

		configList += [
			getConfigListEntry(_("Play audio in background"), config.movielist.play_audio_internal, _("Keeps movie list open whilst playing audio files.")),
			getConfigListEntry(_("Root directory"), config.movielist.root, _("Sets the root directory of movie list, to prevent the '..' from being shown in that directory.")),
			getConfigListEntry(_("Hide known extensions"), config.movielist.hide_extensions, _("Allows you to hide the extensions of known file types.")),
			getConfigListEntry(_("Return to last selected entry"), config.movielist.use_last_videodirpos, _("Return to the last selection in the movie list on re-entering Movie Player. Otherwise return to the first movie entry in the movie list.")),
			getConfigListEntry(_("Show live TV when movie stopped"), config.movielist.show_live_tv_in_movielist, _("When set, return to showing live TV in the background after a movie has stopped playing."))
		]

		updateUserDefinedActions()
		user_buttons = [
			('red', _('Button Red')),
			('green', _('Button Green')),
			('yellow', _('Button Yellow')),
			('blue', _('Button Blue')),
			('redlong', _('Button Red long')),
			('greenlong', _('Button Green long')),
			('yellowlong', _('Button Yellow long')),
			('bluelong', _('Button Blue long')),
		];
		if getBoxType() in ('beyonwizu4', 'beyonwizv2'):
			user_buttons += [
				('TV', _('Button TV/Radio')),
				('Subtitle', _('Button Subtitle')),
				('Audio', _('Button Audio')),
				('Text', _('Button Text')),
			]
		else:
			user_buttons += [
				('Audio', _('Button Audio')),
				('Subtitle', _('Button Subtitle')),
				('Text', _('Button Text')),
				('TV', _('Button TV')),
				('Radio', _('Button Radio')),
			]
		for btn in user_buttons:
			configList.append(getConfigListEntry(btn[1], userDefinedButtons[btn[0]], _("Allows you to set the button to do what you choose.")))
		self["config"].setList(configList)
		if config.usage.sort_settings.value:
			self["config"].list.sort()

	def updateConfig(self, configElement):
		self.createConfig()

	def selectionChanged(self):
		self["description"].setText(self["config"].getCurrent()[2])

	# for summary:
	def changedEntry(self):
		for x in self.onChangedEntry:
			x()

	def getCurrentEntry(self):
		return self["config"].getCurrent() and self["config"].getCurrent()[0] or ""

	def getCurrentValue(self):
		return self["config"].getCurrent() and str(self["config"].getCurrent()[1].getText()) or ""

	def getCurrentDescription(self):
		return self["config"].getCurrent() and len(self["config"].getCurrent()) > 2 and self["config"].getCurrent()[2] or ""

	def createSummary(self):
		from Screens.Setup import SetupSummary
		return SetupSummary

	def save(self):
		self.saveAll()
		cfg = self.cfg
		config.movielist.moviesort.setValue(int(cfg.moviesort.value))
		if cfg.description.value:
			config.movielist.description.value = MovieList.SHOW_DESCRIPTION
		else:
			config.movielist.description.value = MovieList.HIDE_DESCRIPTION
		if not config.movielist.settings_per_directory.value:
			config.movielist.moviesort.save()
			config.movielist.description.save()
			config.movielist.useslim.save()
			config.usage.on_movie_eof.save()
		self.close(True)

	def cancel(self):
		if self["config"].isChanged():
			self.session.openWithCallback(self.cancelCallback, MessageBox, _("Really close without saving settings?"))
		else:
			self.cancelCallback(True)

	def cancelCallback(self, answer):
		if answer:
			for x in self["config"].list:
				x[1].cancel()
			self.close(False)

class MovieContextMenuSummary(Screen):
	def __init__(self, session, parent):
		Screen.__init__(self, session, parent=parent)
		self["selected"] = StaticText("")
		self.onShow.append(self.__onShow)
		self.onHide.append(self.__onHide)

	def __onShow(self):
		self.parent["config"].onSelectionChanged.append(self.selectionChanged)
		self.selectionChanged()

	def __onHide(self):
		self.parent["config"].onSelectionChanged.remove(self.selectionChanged)

	def selectionChanged(self):
		item = self.parent["config"].getCurrent()
		self["selected"].text = item[1]

from Screens.ParentalControlSetup import ProtectedScreen

class MovieContextMenu(Screen, ProtectedScreen):
	# Contract: On OK returns a callable object (e.g. delete)
	def __init__(self, session, csel, service):
		Screen.__init__(self, session)
		self.skinName = [self.skinName, "Setup"]
		self.setup_title = _("Movie List Setup")
		Screen.setTitle(self, self.setup_title)
		self["HelpWindow"] = Pixmap()
		self["HelpWindow"].hide()
		self["VKeyIcon"] = Boolean(False)
		self['footnote'] = Label("")
		self["description"] = StaticText()

		self.csel = csel
		ProtectedScreen.__init__(self)

		self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"red": self.cancelClick,
			"green": self.okbuttonClick,
			"ok": self.okbuttonClick,
			"cancel": self.cancelClick
		})

		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("OK"))
		self["key_yellow"] = StaticText()
		self["key_blue"] = StaticText()

		menu = [(csel.configure, _("Settings") + "...")]

		if csel.exist_bookmark():
			menu += [(csel.do_addbookmark, _("Remove bookmark"))]
		else:
			menu += [(csel.do_addbookmark, _("Add bookmark"))]

		menu += [
			(csel.do_createdir, _("Create directory")),
			(csel.selectSortby, _("Sort") + "..."),
			(csel.do_movieoff_menu, _("On end of movie") + "..."),
		]

		if service:
			if (service.flags & eServiceReference.mustDescent) and isTrashFolder(service):
				menu += [
					(csel.purgeAll, _("Permanently remove all deleted items"))
				]
			else:
				menu += [
					(csel.do_delete, _("Delete")),
					(csel.do_move, _("Move")),
					(csel.do_copy, _("Copy")),
					(csel.do_rename, _("Rename"))
				]
				if not (service.flags & eServiceReference.mustDescent):
					if self.isResetable():
						menu += [(csel.do_reset, _("Reset playback position"))]
					if service.getPath().endswith('.ts'):
						menu += [(csel.do_decode, _("Start offline decode"))]
				else:
					if BlurayPlayer is None and csel.isBlurayFolderAndFile(service):
						menu += [(csel.playBlurayFile, _("Auto play blu-ray file"))]
					count = is_counted(service.getPath())
					if count is not None:
						if count:
							menu += [(csel.do_counted, _("Disable counting"))]
						else:
							menu += [(csel.do_counted, _("Enable counting"))]
				if config.ParentalControl.hideBlacklist.value and config.ParentalControl.storeservicepin.value != "never":
					from Components.ParentalControl import parentalControl
					if not parentalControl.sessionPinCached:
						menu += [(csel.unhideParentalServices, _("Unhide parental control services"))]

		# Plugins expect a valid selection, so only include them if we selected a non-dir
		serviceList = [item[0] for item in csel.getMarked() if isSimpleFile(item)]
		if not serviceList and service and not(service.flags & eServiceReference.mustDescent):
			serviceList = [service]
		if serviceList:
			for p in plugins.getPlugins(PluginDescriptor.WHERE_MOVIELIST):
				if len(serviceList) == 1:
					menu += [(boundFunction(p, session, serviceList[0]), p.description)]
				elif p.multi:
					menu += [(boundFunction(p, session, serviceList[0], serviceList=serviceList), p.description)]

		self["config"] = List(menu)

	def isProtected(self):
		return self.csel.protectContextMenu and config.ParentalControl.setuppinactive.value and config.ParentalControl.config_sections.context_menus.value

	def isResetable(self):
		item = self.csel.getCurrentSelection()
		return not(item[1] and moviePlayState(item[0].getPath() + ".cuts", item[0], item[1].getLength(item[0])) is None)

	def pinEntered(self, answer):
		if answer:
			self.csel.protectContextMenu = False
		ProtectedScreen.pinEntered(self, answer)

	def createSummary(self):
		return MovieContextMenuSummary

	def okbuttonClick(self):
		item = self["config"].getCurrent()
		self.close(item[0])

	def do_rename(self):
		self.close(self.csel.do_rename())

	def do_copy(self):
		self.close(self.csel.do_copy())

	def do_move(self):
		self.close(self.csel.do_move())

	def do_createdir(self):
		self.close(self.csel.do_createdir())

	def do_delete(self):
		self.close(self.csel.do_delete())
	def do_unhideParentalServices(self):
		self.close(self.csel.unhideParentalServices())
	def do_configure(self):
		self.close(self.csel.configure())

	def cancelClick(self):
		self.close(None)

class SelectionEventInfo:
	def __init__(self):
		self["Service"] = ServiceEvent()
		self.list.connectSelChanged(self.__selectionChanged)
		self.timer = eTimer()
		self.timer.callback.append(self.updateEventInfo)
		self.onShown.append(self.__selectionChanged)

	def __selectionChanged(self):
		self.timer.start(100, True)

	def updateEventInfo(self):
		if self.execing and self.settings["description"] == MovieList.SHOW_DESCRIPTION:
			serviceref = self.getCurrent()
			self["Service"].newService(serviceref)

class MovieSelectionSummary(Screen):
	# Kludgy component to display current selection on LCD. Should use
	# parent.Service as source for everything, but that seems to have a
	# performance impact as the MovieSelection goes through hoops to prevent
	# this when the info is not selected
	def __init__(self, session, parent):
		Screen.__init__(self, session, parent=parent)
		self["name"] = StaticText("")
		self.onShow.append(self.__onShow)
		self.onHide.append(self.__onHide)

	def __onShow(self):
		self.parent.list.connectSelChanged(self.selectionChanged)
		self.selectionChanged()

	def __onHide(self):
		self.parent.list.disconnectSelChanged(self.selectionChanged)

	def selectionChanged(self):
		item = self.parent.getCurrentSelection()
		if item and item[0]:
			data = item[3]
			if data and hasattr(data, 'txt'):
				name = data.txt
			elif not item[1]:
				# special case, one up
				name = ".."
			else:
				name = item[1].getName(item[0])
			if item[0].flags & eServiceReference.mustDescent:
				if len(name) > 12:
					name = os.path.split(os.path.normpath(name))[1]
					if name == ".Trash":
						name = _("Trash")
				else:
					path, dir = os.path.split(os.path.normpath(name))
					if dir == ".Trash":
						name = os.path.join(path, _("Trash") + "/")
				name = "> " + name
			self["name"].text = name
		else:
			self["name"].text = ""

class MovieSelection(Screen, HelpableScreen, SelectionEventInfo, InfoBarBase, ProtectedScreen):
	# SUSPEND_PAUSES actually means "please call my pauseService()"
	ALLOW_SUSPEND = Screen.SUSPEND_PAUSES

	def __init__(self, session, selectedmovie=None, timeshiftEnabled=False):
		Screen.__init__(self, session)
		if config.movielist.useslim.value:
			self.skinName = ["MovieSelectionSlim", "MovieSelection"]
		else:
			self.skinName = "MovieSelection"
		HelpableScreen.__init__(self)
		if not timeshiftEnabled:
			InfoBarBase.__init__(self)  # For ServiceEventTracker
		ProtectedScreen.__init__(self)
		self.protectContextMenu = True

		self.initUserDefinedActions()
		self.tags = {}
		if selectedmovie:
			self.selected_tags = config.movielist.last_selected_tags.value
		else:
			self.selected_tags = None
		self.selected_tags_ele = None
		self.nextInBackground = None

		self.movemode = False
		self.bouquet_mark_edit = False

		self.feedbackTimer = None
		self.pathselectEnabled = False

		self.numericalTextInput = NumericalTextInput.NumericalTextInput(mapping=NumericalTextInput.MAP_SEARCH_UPCASE)
		self["chosenletter"] = Label("")
		self["chosenletter"].visible = False

		self["waitingtext"] = Label(_("Please wait... Loading list..."))

		self.LivePlayTimer = eTimer()
		self.LivePlayTimer.timeout.get().append(self.LivePlay)

		self.filePlayingTimer = eTimer()
		self.filePlayingTimer.timeout.get().append(self.FilePlaying)

		self.sorttimer = eTimer()
		self.sorttimer.callback.append(self._updateButtonTexts)

		self.playingInForeground = None
		# create optional description border and hide immediately
		self["DescriptionBorder"] = Pixmap()
		self["DescriptionBorder"].hide()

		if config.ParentalControl.servicepinactive.value:
			from Components.ParentalControl import parentalControl
			if not parentalControl.sessionPinCached and config.movielist.last_videodir.value and [x for x in config.movielist.last_videodir.value[1:].split("/") if x.startswith(".") and not x.startswith(".Trash")]:
				config.movielist.last_videodir.value = ""
		if not os.path.isdir(config.movielist.last_videodir.value):
			config.movielist.last_videodir.value = defaultMoviePath()
			config.movielist.last_videodir.save()
		self.setCurrentRef(config.movielist.last_videodir.value)

		self.settings = {
			"moviesort": config.movielist.moviesort.value,
			"description": config.movielist.description.value,
			"movieoff": config.usage.on_movie_eof.value
		}
		self.movieOff = self.settings["movieoff"]

		self["list"] = MovieList(None, sort_type=self.settings["moviesort"], descr_state=self.settings["description"])

		self.list = self["list"]
		self.selectedmovie = selectedmovie

		self.playGoTo = None  # 1 - preview next item / -1 - preview previous

		self.marked = 0
		self.inMark = False
		self.markDir = 0

		title = _("Movie selection")
		self.setTitle(title)

		# Need list for init
		SelectionEventInfo.__init__(self)

		self["key_red"] = Button("")
		self["key_green"] = Button("")
		self["key_yellow"] = Button("")
		self["key_blue"] = Button("")
		self.onExecBegin.append(self._updateButtonTexts)

		self["movie_off"] = MultiPixmap()
		self["movie_off"].hide()

		self["movie_sort"] = MultiPixmap()
		self["movie_sort"].hide()

		self["diskSize"] = DiskInfo(config.movielist.last_videodir.value, DiskInfo.SIZE, update=False, label=_("Disk size:"))
		self["freeDiskSpace"] = self.diskinfo = DiskInfo(config.movielist.last_videodir.value, DiskInfo.FREE, update=False)
		self["TrashcanSize"] = self.trashinfo = TrashInfo(config.movielist.last_videodir.value, TrashInfo.USED, update=False)
		self["numFolders"] = Label()
		self["numFiles"] = Label()

		user_actions = {
			"showMovies": (self.doPathSelect, _("Select the movie path...")),
			"showTv": (self.btn_tv, boundFunction(self.getinitUserDefinedActionsDescription, "btn_tv")),
			"showText": (self.btn_text, boundFunction(self.getinitUserDefinedActionsDescription, "btn_text")),
			"showSubtitle": (self.btn_subtitle, boundFunction(self.getinitUserDefinedActionsDescription, "btn_subtitle")),
			"showAudio": (self.btn_audio, boundFunction(self.getinitUserDefinedActionsDescription, "btn_audio")),
		}
		if getBoxType() not in ('beyonwizu4', 'beyonwizv2'):
			user_actions["showRadio"] = (self.btn_radio, boundFunction(self.getinitUserDefinedActionsDescription, "btn_radio"))
		self["InfobarActions"] = HelpableActionMap(self, "MovieSelectionUserActions", user_actions, description=_("Basic functions"))

		keyNumberHelp = _("Search movie list, SMS style ABC2")
		self["NumberActions"] = HelpableNumberActionMap(self, ["NumberActions", "InputAsciiActions"], {
			"gotAsciiCode": self.keyAsciiCode,
			"1": (self.keyNumberGlobal, keyNumberHelp),
			"2": (self.keyNumberGlobal, keyNumberHelp),
			"3": (self.keyNumberGlobal, keyNumberHelp),
			"4": (self.keyNumberGlobal, keyNumberHelp),
			"5": (self.keyNumberGlobal, keyNumberHelp),
			"6": (self.keyNumberGlobal, keyNumberHelp),
			"7": (self.keyNumberGlobal, keyNumberHelp),
			"8": (self.keyNumberGlobal, keyNumberHelp),
			"9": (self.keyNumberGlobal, keyNumberHelp),
		})

		self["playbackActions"] = HelpableActionMap(self, "MoviePlayerActions", {
			"leavePlayer": (self.playbackStop, _("Stop")),
			#"moveNext": (self.playNext, _("Play next")),
			#"movePrev": (self.playPrev, _("Play previous")),
			"channelUp": (self.moveToFirstOrFirstFile, _("Go to first movie or top of list")),
			"channelDown": (self.moveToLastOrFirstFile, _("Go to last movie or last list item")),
		}, description=_("Recording/media selection"))
		self["MovieSelectionActions"] = HelpableActionMap(self, "MovieSelectionActions", {
			"contextMenu": (self.doContext, _("Menu")),
			"showEventInfo": (self.showEventInformation, _("Show event details")),
		}, description=_("Settings, information and more functions"))

		self["ColorActions"] = HelpableActionMap(self, "ColorActions", {
			"red": (self.btn_red, boundFunction(self.getinitUserDefinedActionsDescription, "btn_red")),
			"green": (self.btn_green, boundFunction(self.getinitUserDefinedActionsDescription, "btn_green")),
			"yellow": (self.btn_yellow, boundFunction(self.getinitUserDefinedActionsDescription, "btn_yellow")),
			"blue": (self.btn_blue, boundFunction(self.getinitUserDefinedActionsDescription, "btn_blue")),
			"redlong": (self.btn_redlong, boundFunction(self.getinitUserDefinedActionsDescription, "btn_redlong")),
			"greenlong": (self.btn_greenlong, boundFunction(self.getinitUserDefinedActionsDescription, "btn_greenlong")),
			"yellowlong": (self.btn_yellowlong, boundFunction(self.getinitUserDefinedActionsDescription, "btn_yellowlong")),
			"bluelong": (self.btn_bluelong, boundFunction(self.getinitUserDefinedActionsDescription, "btn_bluelong")),
		}, description=_("User-selectable functions"))
		self["OkCancelActions"] = HelpableActionMap(self, ["OkCancelActions", "MovieSelectionActions", "TimerMediaEPGActions"], {
			"cancel": (self.abort, _("Exit movie list")),
			"timer": (self.abortToTimer, _("Exit, show timer list")),
			"epg": (self.abortToEPG, _("Exit, show EPG")),
			"ok": (self.itemSelected, _("Select movie")),
			"toggleMark": (self.toggleMark, _("Toggle mark")),
			"invertMarks": (self.invertMarks, _("Invert marks (of files or directories)")),
			"toggleMoveUp": (self.toggleMoveUp, lambda: _("Play previous") if self.list.playInBackground else _("Toggle mark and move up")),
			"toggleMoveDown": (self.toggleMoveDown, lambda: _("Play next") if self.list.playInBackground else _("Toggle mark and move down")),
			"markAll": (self.markAll, _("Mark all (files or directories)")),
			"markNone": (self.markNone, _("Remove marks")),
		}, description=_("Selection and exit"))
		self["DirectionActions"] = HelpableActionMap(self, "DirectionActions", {
			"up": (self.keyUp, _("Go up the list")),
			"down": (self.keyDown, _("Go down the list"))
		}, prio=-2, description=_("Navigation"))
		self["FileNavigateActions"] = HelpableActionMap(self, "FileNavigateActions", {
			"directoryUp": (self.directoryUp, _("Go to the parent directory")),
		}, prio=-2, description=_("Navigation"))

		tFwd = _("Skip forward (Preview)")
		tBack = _("Skip backward (Preview)")
		sfwd = lambda: self.seekRelative(1, config.seek.selfdefined_46.value * 90000)
		ssfwd = lambda: self.seekRelative(1, config.seek.selfdefined_79.value * 90000)
		sback = lambda: self.seekRelative(-1, config.seek.selfdefined_46.value * 90000)
		ssback = lambda: self.seekRelative(-1, config.seek.selfdefined_79.value * 90000)
		self["SeekActions"] = HelpableActionMap(self, "MovielistSeekActions", {
			"playpauseService": (self.preview, _("Preview")),
			"seekFwd": (sfwd, tFwd),
			"seekFwdManual": (ssfwd, tFwd),
			"seekBack": (sback, tBack),
			"seekBackManual": (ssback, tBack),
		}, prio=5, description=_("Pause, rewind and fast forward"))
		self.onShown.append(self.onFirstTimeShown)
		self.onLayoutFinish.append(self.saveListsize)
		if not config.movielist.use_last_videodirpos.value:
			config.movielist.last_videodirpos.value = ""
			config.movielist.last_videodirpos.save()
		self.savePos = False
		self.list.connectSelChanged(self.selectionChanged)
		self.onClose.append(self.__onClose)
		NavigationInstance.instance.RecordTimer.on_state_change.append(self.list.updateRecordings)
		self.__event_tracker = ServiceEventTracker(screen=self, eventmap={
			# iPlayableService.evSeekableStatusChanged: self.__seekableStatusChanged,
			iPlayableService.evStart: self.__serviceStarted,
			iPlayableService.evEOF: self.__evEOF,
			# iPlayableService.evSOF: self.__evSOF,
		})
		if config.misc.remotecontrol_text_support.value:
			self.onExecBegin.append(self.asciiOff)
		else:
			self.onExecBegin.append(self.asciiOn)
		config.misc.standbyCounter.addNotifier(self.standbyCountChanged, initial_call=False)

	def isProtected(self):
		return config.ParentalControl.setuppinactive.value and config.ParentalControl.config_sections.movie_list.value

	def standbyCountChanged(self, value):
		path = self.getTitle().split(" /", 1)
		if path and len(path) > 1:
			if [x for x in path[1].split("/") if x.startswith(".") and not x.startswith(".Trash")]:
				moviepath = defaultMoviePath()
				if moviepath:
					config.movielist.last_videodir.value = defaultMoviePath()
					self.close(None)

	def unhideParentalServices(self):
		if self.protectContextMenu:
			self.session.openWithCallback(self.unhideParentalServicesCallback, PinInput, pinList=[config.ParentalControl.servicepin[0].value], triesEntry=config.ParentalControl.retries.servicepin, title=_("Enter the service PIN"), windowTitle=_("Enter PIN code"))
		else:
			self.unhideParentalServicesCallback(True)

	def unhideParentalServicesCallback(self, answer):
		if answer:
			from Components.ParentalControl import parentalControl
			parentalControl.setSessionPinCached()
			parentalControl.hideBlacklist()
			self.reloadList()
		elif answer is not None:
			self.session.openWithCallback(self.close, MessageBox, _("The PIN code you entered is wrong."), MessageBox.TYPE_ERROR)

	def asciiOn(self):
		rcinput = eRCInput.getInstance()
		rcinput.setKeyboardMode(rcinput.kmAscii)

	def asciiOff(self):
		rcinput = eRCInput.getInstance()
		rcinput.setKeyboardMode(rcinput.kmNone)

	def initUserDefinedActions(self):
		global userDefinedButtons, userDefinedActions, userDefinedDescriptions, config
		if userDefinedButtons is None:
			userDefinedDescriptions = {
				'delete': (_("Delete"), _("Delete recordings and empty trash")),
				'move': (_("Move"), _("Move to other directory")),
				'copy': (_("Copy"), _("Copy to other directory")),
				'createdir': (_("Create directory"), _("Create directory")),
				'reset': (_("Reset"), _("Reset playback resume position")),
				'tags': (_("Tags"), _("Show tagged movies")),
				'addbookmark': _("Add bookmark"),
				'bookmarks': (_("Location"), _("Select the movie path")),
				'rename': (_("Rename"), _("Rename recording, video or directory")),
				'gohome': (_("Home"), _("Go to player home directory")),
				'sort': (_("Sort"), _("Cycle through sort orderings")),
				'sortby': (_("Sort..."), _("Select sort order from menu")),
				'sortdefault': (_("Default sort order"), _("Use default sort order")),
				'preview': (_("Preview"), _("Preview recording under movie selection screen")),
				'movieoff': (_("On end of movie"), _("Cycle through end-of-movie actions")),
				'movieoff_menu': (_("On end of movie..."), _("Select end-of-movie action from menu")),
			}
			userDefinedActions = {}
			for a, desc in userDefinedDescriptions.iteritems():
				if isinstance(desc, tuple):
					desc = desc[0]
				userDefinedActions[a] = desc
			for p in plugins.getPlugins(PluginDescriptor.WHERE_MOVIELIST):
				userDefinedActions['@' + p.name] = p.description
			locations = []
			buildMovieLocationList(locations)
			prefix = _("Goto") + ": "
			for d, p in locations:
				if p and p.startswith('/'):
					userDefinedActions[p] = prefix + d
			userDefinedChoices = sorted(userDefinedActions.iteritems(), key=lambda x: x[1].lower())
			config.movielist.btn_red = ConfigSelection(default='delete', choices=userDefinedChoices[:])
			config.movielist.btn_green = ConfigSelection(default='move', choices=userDefinedChoices[:])
			config.movielist.btn_yellow = ConfigSelection(default='bookmarks', choices=userDefinedChoices[:])
			config.movielist.btn_blue = ConfigSelection(default='sortby', choices=userDefinedChoices[:])
			config.movielist.btn_redlong = ConfigSelection(default='rename', choices=userDefinedChoices[:])
			config.movielist.btn_greenlong = ConfigSelection(default='copy', choices=userDefinedChoices[:])
			config.movielist.btn_yellowlong = ConfigSelection(default='tags', choices=userDefinedChoices[:])
			config.movielist.btn_bluelong = ConfigSelection(default='sortdefault', choices=userDefinedChoices[:])
			if getBoxType() in ('beyonwizu4', 'beyonwizv2'):
				config.movielist.btn_tv = ConfigSelection(default='createdir', choices=userDefinedChoices[:])
				config.movielist.btn_subtitle = ConfigSelection(default='movieoff_menu', choices=userDefinedChoices[:])
				config.movielist.btn_audio = ConfigSelection(default='gohome', choices=userDefinedChoices[:])
				config.movielist.btn_text = ConfigSelection(default='tags', choices=userDefinedChoices[:])
			else:
				config.movielist.btn_audio = ConfigSelection(default='reset', choices=userDefinedChoices[:])
				config.movielist.btn_subtitle = ConfigSelection(default='createdir', choices=userDefinedChoices[:])
				config.movielist.btn_text = ConfigSelection(default='movieoff_menu', choices=userDefinedChoices[:])
				config.movielist.btn_tv = ConfigSelection(default='gohome', choices=userDefinedChoices[:])
				config.movielist.btn_radio = ConfigSelection(default='tags', choices=userDefinedChoices[:])

			# Fill in descriptions for plugin actions
			for act, val in userDefinedActions.items():
				userDefinedDescriptions[act] = val

			userDefinedButtons = {
				'red': config.movielist.btn_red,
				'green': config.movielist.btn_green,
				'yellow': config.movielist.btn_yellow,
				'blue': config.movielist.btn_blue,
				'redlong': config.movielist.btn_redlong,
				'greenlong': config.movielist.btn_greenlong,
				'yellowlong': config.movielist.btn_yellowlong,
				'bluelong': config.movielist.btn_bluelong,
				'TV': config.movielist.btn_tv,
				'Text': config.movielist.btn_text,
				'Audio': config.movielist.btn_audio,
				'Subtitle': config.movielist.btn_subtitle,
			}
			if getBoxType() not in ('beyonwizu4', 'beyonwizv2'):
				userDefinedButtons['Radio'] = config.movielist.btn_radio

	def getinitUserDefinedActionsDescription(self, key):
		return _(userDefinedActions.get(eval("config.movielist." + key + ".value"), _("Not Defined")))

	def _callButton(self, name):
		if name.startswith('@'):
			serviceList = [item[0] for item in self.getMarked() if isSimpleFile(item)]
			if serviceList:
				name = name[1:]
				for p in plugins.getPlugins(PluginDescriptor.WHERE_MOVIELIST):
					if name == p.name:
						if len(serviceList) == 1:
							p(self.session, serviceList[0])
						elif p.multi:
							p(self.session, serviceList[0], serviceList=serviceList)
		elif name.startswith('/'):
			self.gotFilename(name)
		else:
			try:
				a = getattr(self, 'do_' + name)
			except Exception:
				# Undefined action
				return
			a()

	def _helpText(self, configVal):
		help = userDefinedDescriptions[configVal]
		if isinstance(help, tuple):
			help = help[1] if len(help) > 1 else help[0]
		return help

	def btn_red(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if not InfoBarInstance.LongButtonPressed:
			self._callButton(config.movielist.btn_red.value)

	def btn_green(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if not InfoBarInstance.LongButtonPressed:
			self._callButton(config.movielist.btn_green.value)

	def btn_yellow(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if not InfoBarInstance.LongButtonPressed:
			self._callButton(config.movielist.btn_yellow.value)

	def btn_blue(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if not InfoBarInstance.LongButtonPressed:
			self._callButton(config.movielist.btn_blue.value)

	def btn_redlong(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if InfoBarInstance.LongButtonPressed:
			self._callButton(config.movielist.btn_redlong.value)

	def btn_greenlong(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if InfoBarInstance.LongButtonPressed:
			self._callButton(config.movielist.btn_greenlong.value)

	def btn_yellowlong(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if InfoBarInstance.LongButtonPressed:
			self._callButton(config.movielist.btn_yellowlong.value)

	def btn_bluelong(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if InfoBarInstance.LongButtonPressed:
			self._callButton(config.movielist.btn_bluelong.value)

	def btn_radio(self):
		self._callButton(config.movielist.btn_radio.value)

	def btn_tv(self):
		self._callButton(config.movielist.btn_tv.value)

	def btn_text(self):
		self._callButton(config.movielist.btn_text.value)

	def btn_audio(self):
		self._callButton(config.movielist.btn_audio.value)

	def btn_subtitle(self):
		self._callButton(config.movielist.btn_subtitle.value)

	def keyUp(self):
		if self["list"].getCurrentIndex() < 1:
			self["list"].moveToLast()
		else:
			self["list"].moveUp()
		self.inMark = False

	def keyDown(self):
		if self["list"].getCurrentIndex() == len(self["list"]) - 1:
			self["list"].moveToFirst()
		else:
			self["list"].moveDown()
		self.inMark = False

	def directoryUp(self):
		if self.marked:
			return
		cur = config.movielist.last_videodir.value.rstrip("/") or "/"
		root = config.movielist.root.value.rstrip("/") or "/"
		if cur == root:
			return
		parent = os.path.dirname(cur)
		if os.path.isdir(parent):
			self.gotFilename(parent)
			return

	def moveToFirstOrFirstFile(self):
		if self.list.getCurrentIndex() <= self.list.firstFileEntry:  # selection above or on first movie
			if self.list.getCurrentIndex() < 1:
				self.list.moveToLast()
			else:
				self.list.moveToFirst()
		else:
			self.list.moveToFirstMovie()

	def moveToLastOrFirstFile(self):
		if self.list.getCurrentIndex() >= self.list.firstFileEntry or self.list.firstFileEntry == len(self.list):  # selection below or on first movie or no files
			if self.list.getCurrentIndex() == len(self.list) - 1:
				self.list.moveToFirst()
			else:
				self.list.moveToLast()
		else:
			self.list.moveToFirstMovie()

	def keyNumberGlobal(self, number):
		unichar = self.numericalTextInput.getKey(number)
		charstr = unichar.encode("utf-8")
		if len(charstr) == 1:
			self.list.moveToChar(charstr[0], self["chosenletter"])

	def keyAsciiCode(self):
		unichar = unichr(getPrevAsciiCode())
		charstr = unichar.encode("utf-8")
		if len(charstr) == 1:
			self.list.moveToString(charstr[0], self["chosenletter"])

	def isItemPlayable(self, index):
		item = self.list.getItem(index)
		if item:
			path = item.getPath()
			if not item.flags & eServiceReference.mustDescent:
				ext = os.path.splitext(path)[1].lower()
				if ext in IMAGE_EXTENSIONS:
					return False
				else:
					return True
		return False

	def goToPlayingService(self):
		service = self.session.nav.getCurrentlyPlayingServiceOrGroup()
		if service:
			path = service.getPath()
			if path:
				path = os.path.split(os.path.normpath(path))[0]
				if not path.endswith('/'):
					path += '/'
				self.gotFilename(path, selItem=service)
				return True
		return False

	def playNext(self):
		if self.list.playInBackground:
			global playingList
			if playingList:
				next = self.findServiceInPlaylist(self.list.playInBackground, +1)
				if next is not None:
					self.list.moveTo(next)
					self.callLater(self.preview)
				return
			if self.list.moveTo(self.list.playInBackground):
				if self.isItemPlayable(self.list.getCurrentIndex() + 1):
					self.list.moveDown()
					self.callLater(self.preview)
			else:
				self.playGoTo = 1
				self.goToPlayingService()
		else:
			self.preview()

	def playPrev(self):
		if self.list.playInBackground:
			global playingList
			if playingList:
				prev = self.findServiceInPlaylist(self.list.playInBackground, -1)
				if prev is not None:
					self.list.moveTo(prev)
					self.callLater(self.preview)
				return
			if self.list.moveTo(self.list.playInBackground):
				if self.isItemPlayable(self.list.getCurrentIndex() - 1):
					self.list.moveUp()
					self.callLater(self.preview)
			else:
				self.playGoTo = -1
				self.goToPlayingService()
		else:
			current = self.getCurrent()
			if current is not None:
				if self["list"].getCurrentIndex() > 0:
					path = current.getPath()
					path = os.path.abspath(os.path.join(path, os.path.pardir))
					path = os.path.abspath(os.path.join(path, os.path.pardir))
					self.gotFilename(path)

	def findServiceInPlaylist(self, service, dir):
		global playlist
		for i, item in enumerate(playlist):
			if item == service:
				i += dir
				if 0 <= i < len(playlist):
					return playlist[i]
				break
		return None

	def __onClose(self):
		config.misc.standbyCounter.removeNotifier(self.standbyCountChanged)
		try:
			NavigationInstance.instance.RecordTimer.on_state_change.remove(self.list.updateRecordings)
		except Exception, e:
			print "[MovieSelection] failed to unsubscribe:", e
			pass
		if not config.movielist.use_last_videodirpos.value:
			config.movielist.last_videodirpos.value = ""
		config.movielist.last_videodirpos.save()
		self.savePos = False

	def createSummary(self):
		return MovieSelectionSummary

	def updateDescription(self):
		if self.settings["description"] == MovieList.SHOW_DESCRIPTION:
			self["DescriptionBorder"].show()
			self["list"].instance.resize(eSize(self.listWidth, self.listHeight - self["DescriptionBorder"].instance.size().height()))
		else:
			self["Service"].newService(None)
			self["DescriptionBorder"].hide()
			self["list"].instance.resize(eSize(self.listWidth, self.listHeight))

	def pauseService(self):
		# Called when pressing Power button (go to standby)
		self.playbackStop()
		self.session.nav.stopService()

	def unPauseService(self):
		# When returning from standby. It might have been a while, so
		# reload the list.
		self.reloadList()

	def can_move(self, item):
		if self.marked:
			items = self.getMarked()
			if items:
				for item in items:
					if canMove(item):
						return True
				return False
		return canMove(item)

	def can_copy(self, item):
		if self.marked:
			items = self.getMarked()
			if items:
				for item in items:
					if canCopy(item):
						return True
				return False
		return canCopy(item)

	def can_rename(self, item):
		if self.marked and self.getMarked():
			return False
		return canRename(item)

	def can_delete(self, item):
		if self.marked:
			items = self.getMarked()
			if items:
				for item in items:
					if canDelete(item):
						return True
				return False
		if not item:
			return False
		return canDelete(item) or isTrashFolder(item[0])

	def can_default(self, item):
		# returns whether item is a regular file
		if self.marked:
			items = self.getMarked()
			if items:
				for item in items:
					if isSimpleFile(item):
						return True
				return False
		return isSimpleFile(item)

	def can_sort(self, item):
		return True

	def can_preview(self, item):
		return isSimpleFile(item)

	def selectionChanged(self):
		self.updateButtons()
		self._updateButtonTexts()
		if self.savePos and config.movielist.use_last_videodirpos.value:
			config.movielist.last_videodirpos.value = self["list"].getCurrent().toString() + ',' + str(self["list"].getCurrentIndex())
		self.savePos = True

	def _updateButtonTexts(self):
		for k in ('red', 'green', 'yellow', 'blue'):
			btn = userDefinedButtons[k]
			if btn.value == 'sort' and self.sorttimer.isActive():
				continue
			label = userDefinedActions[btn.value]
			if btn.value == 'delete':
				item = self.getCurrentSelection()
				if item and isTrashFolder(item[0]):
					label = _("Empty trash")
			self['key_' + k].text = label

	def updateButtons(self):
		item = self.getCurrentSelection()
		for name in ('red', 'green', 'yellow', 'blue'):
			action = userDefinedButtons[name].value
			if action.startswith('@'):
				check = self.can_default
			elif action.startswith('/'):
				check = self.can_gohome
			else:
				try:
					check = getattr(self, 'can_' + action)
				except:
					check = self.can_default
			gui = self["key_" + name]
			if check(item):
				gui.show()
			else:
				gui.hide()

	def showEventInformation(self):
		from Screens.EventView import EventViewSimple
		from ServiceReference import ServiceReference
		evt = self["list"].getCurrentEvent()
		if evt:
			self.session.open(EventViewSimple, evt, ServiceReference(self.getCurrent()))

	def saveListsize(self):
		listsize = self["list"].instance.size()
		self.listWidth = listsize.width()
		self.listHeight = listsize.height()
		self.updateDescription()

	def FilePlaying(self):
		if self.session.nav.getCurrentlyPlayingServiceReference() and ':0:/' in self.session.nav.getCurrentlyPlayingServiceReference().toString():
			self.list.playInForeground = self.session.nav.getCurrentlyPlayingServiceReference()
		else:
			self.list.playInForeground = None
		self.filePlayingTimer.stop()

		if hasattr(self, "selectedmovie"):
			self.reloadList(self.selectedmovie, home=True)
			del self.selectedmovie

	def onFirstTimeShown(self):
		self.filePlayingTimer.start(100)
		self.onShown.remove(self.onFirstTimeShown)  # Just once, not after returning etc.
		self.show()

		if config.movielist.show_live_tv_in_movielist.value:
			self.LivePlayTimer.start(100)

	def hidewaitingtext(self):
		self.hidewaitingTimer.stop()
		self["waitingtext"].hide()

	def LivePlay(self):
		if self.session.nav.getCurrentlyPlayingServiceReference():
			if ':0:/' not in self.session.nav.getCurrentlyPlayingServiceReference().toString():
				config.movielist.curentlyplayingservice.setValue(self.session.nav.getCurrentlyPlayingServiceReference().toString())
		checkplaying = self.session.nav.getCurrentlyPlayingServiceReference()
		if checkplaying:
			checkplaying = checkplaying.toString()
		if checkplaying is None or (config.movielist.curentlyplayingservice.value != checkplaying and ':0:/' not in self.session.nav.getCurrentlyPlayingServiceReference().toString()):
			self.session.nav.playService(eServiceReference(config.movielist.curentlyplayingservice.value))
		self.LivePlayTimer.stop()

	def getCurrent(self):
		# Returns selected serviceref (may be None)
		return self["list"].getCurrent()

	def getCurrentSelection(self):
		# Returns None or (serviceref, info, begin, len)
		return self["list"].l.getCurrentSelection()

	def getMarked(self):
		if self.marked:
			items = self.list.getMarked()
		else:
			item = self.getCurrentSelection()
			items = [item] if item else []
		return items

	def playAsBLURAY(self, path):
		try:
			from Plugins.Extensions.BlurayPlayer import BlurayUi
			self.session.open(BlurayUi.BlurayMain, path)
			return True
		except Exception as e:
			print "[MovieSelection] Cannot open BlurayPlayer:", e

	def playAsDVD(self, path):
		try:
			from Screens import DVD
			if path.endswith('VIDEO_TS/'):
				# strip away VIDEO_TS/ part
				path = os.path.split(path.rstrip('/'))[0]
			self.session.open(DVD.DVDPlayer, dvd_filelist=[path])
			return True
		except Exception, e:
			print "[MovieSelection] DVD Player not installed:", e

	def __serviceStarted(self):
		if not self.list.playInBackground or not self.list.playInForeground:
			return
		ref = self.session.nav.getCurrentService()
		cue = ref.cueSheet()
		if not cue:
			return
		# disable writing the stop position
		cue.setCutListEnable(2)
		# find "resume" position
		cuts = cue.getCutList()
		if not cuts:
			return
		for (pts, what) in cuts:
			if what == 3:
				last = pts
				break
		else:
			# no resume, jump to start of program (first marker)
			last = cuts[0][0]
		self.doSeekTo = last
		self.callLater(self.doSeek)

	def doSeek(self, pts=None):
		if pts is None:
			pts = self.doSeekTo
		seekable = self.getSeek()
		if seekable is None:
			return
		seekable.seekTo(pts)

	def getSeek(self):
		service = self.session.nav.getCurrentService()
		if service is None:
			return None
		seek = service.seek()
		if seek is None or not seek.isCurrentlySeekable():
			return None
		return seek

	def callLater(self, function):
		self.previewTimer = eTimer()
		self.previewTimer.callback.append(function)
		self.previewTimer.start(10, True)

	def __evEOF(self):
		playInBackground = self.list.playInBackground
		playInForeground = self.list.playInForeground
		global playlist, playingList
		if not playInBackground:
			print "[MovieSelection] Not playing anything in background"
			return
		self.session.nav.stopService()
		self.list.playInBackground = None
		self.list.playInForeground = None
		if config.movielist.play_audio_internal.value:
			global playingList
			if playingList:
				next = self.findServiceInPlaylist(playInBackground, +1)
				if next is not None:
					self.list.moveTo(next)
					self.callLater(self.preview)
					return
			index = self.list.findService(playInBackground)
			if index is None:
				return  # Not found?
			next = self.list.getItem(index + 1)
			if not next:
				return
			path = next.getPath()
			ext = os.path.splitext(path)[1].lower()
			print "[MovieSelection] Next up:", path
			if ext in AUDIO_EXTENSIONS:
				self.nextInBackground = next
				self.callLater(self.preview)
				self["list"].moveToIndex(index + 1)

		if config.movielist.show_live_tv_in_movielist.value:
			self.LivePlayTimer.start(100)

	def preview(self):
		current = self.getCurrent()
		if current is not None:
			path = current.getPath()
			if current.flags & eServiceReference.mustDescent:
				self.gotFilename(path)
			else:
				Screens.InfoBar.InfoBar.instance.checkTimeshiftRunning(self.previewCheckTimeshiftCallback)

	def startPreview(self):
		if self.nextInBackground is not None:
			current = self.nextInBackground
			self.nextInBackground = None
		else:
			current = self.getCurrent()
		playInBackground = self.list.playInBackground
		playInForeground = self.list.playInForeground
		if playInBackground:
			self.list.playInBackground = None
			from Screens.InfoBar import MoviePlayer
			MoviePlayerInstance = MoviePlayer.instance
			if MoviePlayerInstance is not None:
				from Screens.InfoBarGenerics import setResumePoint
				setResumePoint(MoviePlayer.instance.session)
			self.session.nav.stopService()
			if playInBackground != current:
				# come back to play the new one
				self.callLater(self.preview)
		elif playInForeground:
			self.playingInForeground = playInForeground
			self.list.playInForeground = None
			from Screens.InfoBar import MoviePlayer
			MoviePlayerInstance = MoviePlayer.instance
			if MoviePlayerInstance is not None:
				from Screens.InfoBarGenerics import setResumePoint
				setResumePoint(MoviePlayer.instance.session)
			self.session.nav.stopService()
			if playInForeground != current:
				self.callLater(self.preview)
		else:
			self.list.playInBackground = current
			self.session.nav.playService(current)

	def previewCheckTimeshiftCallback(self, answer):
		if answer:
			self.startPreview()

	def seekRelative(self, direction, amount):
		if self.list.playInBackground:
			seekable = self.getSeek()
			if seekable is None:
				return
			seekable.seekRelative(direction, amount)

	def playbackStop(self):
		if self.list.playInBackground:
			self.list.playInBackground = None
			from Screens.InfoBar import MoviePlayer
			MoviePlayerInstance = MoviePlayer.instance
			if MoviePlayerInstance is not None:
				from Screens.InfoBarGenerics import setResumePoint
				setResumePoint(MoviePlayer.instance.session)
			self.session.nav.stopService()
			if config.movielist.show_live_tv_in_movielist.value:
				self.LivePlayTimer.start(100)
			self.filePlayingTimer.start(100)
			return
		elif self.list.playInForeground:
			from Screens.InfoBar import MoviePlayer
			MoviePlayerInstance = MoviePlayer.instance
			if MoviePlayerInstance is not None:
				from Screens.InfoBarGenerics import setResumePoint
				setResumePoint(MoviePlayer.instance.session)
				MoviePlayerInstance.close()
			self.session.nav.stopService()
			if config.movielist.show_live_tv_in_movielist.value:
				self.LivePlayTimer.start(100)
			self.filePlayingTimer.start(100)

	def toggleMark(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if not InfoBarInstance.LongButtonPressed:
			self.marked = self.list.toggleCurrentItem()

	def toggleMoveUp(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if not InfoBarInstance.LongButtonPressed:
			if self.list.playInBackground:
				self.playPrev()
			else:
				if not self.inMark:
					self.markDir = -1
				if self.markDir == -1:
					self.marked = self.list.toggleCurrentItem()
					self.keyUp()
				else:
					self.keyUp()
					self.marked = self.list.toggleCurrentItem()
				self.inMark = True

	def toggleMoveDown(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if not InfoBarInstance.LongButtonPressed:
			if self.list.playInBackground:
				self.playNext()
			else:
				if not self.inMark:
					self.markDir = +1
				if self.markDir == +1:
					self.marked = self.list.toggleCurrentItem()
					self.keyDown()
				else:
					self.keyDown()
					self.marked = self.list.toggleCurrentItem()
				self.inMark = True

	def invertMarks(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if InfoBarInstance.LongButtonPressed:
			self.marked = self.list.invertMarks()

	def markAll(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if InfoBarInstance.LongButtonPressed:
			self.marked = self.list.markAll()

	def markNone(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if InfoBarInstance.LongButtonPressed:
			self.marked = self.list.markNone()

	def itemSelected(self, answer=True):
		if self.marked:
			global playlist
			items = playlist
			del items[:]
			audio = config.movielist.play_audio_internal.value
			for item in self.getMarked():
				if item:
					item = item[0]
					path = item.getPath()
					if not item.flags & eServiceReference.mustDescent:
						ext = os.path.splitext(path)[1].lower()
						if ext in IMAGE_EXTENSIONS:
							continue
						else:
							items.append(item)
							if audio and ext not in AUDIO_EXTENSIONS:
								audio = False
			if items:
				global playingList
				playingList = True
				if audio:
					self.list.moveTo(items[0])
					self.preview()
				else:
					self.saveconfig()
					self.close(items[0])
			return
		current = self.getCurrent()
		if current is not None:
			path = current.getPath()
			if current.flags & eServiceReference.mustDescent:
				if BlurayPlayer is not None and os.path.isdir(os.path.join(path, 'BDMV/STREAM/')):
					# force a BLU-RAY extention
					Screens.InfoBar.InfoBar.instance.checkTimeshiftRunning(boundFunction(self.itemSelectedCheckTimeshiftCallback, 'bluray', path))
					return
				if os.path.isdir(os.path.join(path, 'VIDEO_TS/')) or os.path.exists(os.path.join(path, 'VIDEO_TS.IFO')):
					# force a DVD extention
					Screens.InfoBar.InfoBar.instance.checkTimeshiftRunning(boundFunction(self.itemSelectedCheckTimeshiftCallback, '.img', path))
					return
				self.gotFilename(path)
			else:
				ext = os.path.splitext(path)[1].lower()
				if config.movielist.play_audio_internal.value and (ext in AUDIO_EXTENSIONS):
					self.preview()
					return
				if self.list.playInBackground:
					# Stop preview, come back later
					self.session.nav.stopService()
					self.list.playInBackground = None
					self.callLater(self.itemSelected)
					return
				if ext in IMAGE_EXTENSIONS:
					try:
						from Plugins.Extensions.PicturePlayer import ui
						# Build the list for the PicturePlayer UI
						filelist = []
						index = 0
						for item in self.list.list:
							p = item[0].getPath()
							if p == path:
								index = len(filelist)
							if os.path.splitext(p)[1].lower() in IMAGE_EXTENSIONS:
								filelist.append(((p, False), None))
						self.session.open(ui.Pic_Full_View, filelist, index, path)
					except Exception, ex:
						print "[MovieSelection] Can not display", str(ex)
					return
				Screens.InfoBar.InfoBar.instance.checkTimeshiftRunning(boundFunction(self.itemSelectedCheckTimeshiftCallback, ext, path))

	def itemSelectedCheckTimeshiftCallback(self, ext, path, answer):
		if answer:
			if ext in (".iso", ".img", ".nrg") and BlurayPlayer is not None:
				try:
					from Plugins.Extensions.BlurayPlayer import blurayinfo
					if blurayinfo.isBluray(path) == 1:
						ext = 'bluray'
				except Exception as e:
					print "[MovieSelection] Error in blurayinfo:", e
			if ext == 'bluray':
				if self.playAsBLURAY(path):
					return
			elif ext in DVD_EXTENSIONS:
				if self.playAsDVD(path):
					return
			self.movieSelected()

	# Note: DVDBurn overrides this method, hence the itemSelected indirection.
	def movieSelected(self):
		current = self.getCurrent()
		if current is not None:
			self.saveconfig()
			self.close(current)

	def doContext(self):
		current = self.getCurrent()
		if current is not None:
			self.session.openWithCallback(self.doneContext, MovieContextMenu, self, current)

	def doneContext(self, action):
		if action is not None:
			action()

	def saveLocalSettings(self):
		if config.movielist.settings_per_directory.value:
			try:
				path = os.path.join(config.movielist.last_videodir.value, ".e2settings.pkl")
				file = open(path, "wb")
				pickle.dump(self.settings, file)
				file.close()
			except Exception, e:
				print "[MovieSelection] Failed to save settings to %s: %s" % (path, e)
			# Also set config items, in case the user has a read-only disk
			config.movielist.moviesort.value = self.settings["moviesort"]
			config.movielist.description.value = self.settings["description"]
			config.usage.on_movie_eof.value = self.settings["movieoff"]
			# save moviesort and movieeof values for using by hotkeys
			config.movielist.moviesort.save()
			config.usage.on_movie_eof.save()

	def loadLocalSettings(self):
		'Load settings, called when entering a directory'
		if config.movielist.settings_per_directory.value:
			try:
				path = os.path.join(config.movielist.last_videodir.value, ".e2settings.pkl")
				file = open(path, "rb")
				updates = pickle.load(file)
				file.close()
				self.applyConfigSettings(updates)
			except Exception, e:
				print "[MovieSelection] Failed to load settings from %s: %s" % (path, e)
		else:
			updates = {
				"moviesort": config.movielist.moviesort.value,
				"description": config.movielist.description.value,
				"movieoff": config.usage.on_movie_eof.value
			}
			self.applyConfigSettings(updates)

	def applyConfigSettings(self, updates):
		needUpdate = ("description" in updates) and (updates["description"] != self.settings["description"])
		self.settings.update(updates)
		if needUpdate:
			self["list"].setDescriptionState(self.settings["description"])
			self.updateDescription()
		if self.settings["moviesort"] != self["list"].sort_type:
			self["list"].setSortType(int(self.settings["moviesort"]))
			needUpdate = True
		if self.settings["movieoff"] != self.movieOff:
			self.movieOff = self.settings["movieoff"]
			needUpdate = True
		config.movielist.moviesort.value = self.settings["moviesort"]
		config.movielist.description.value = self.settings["description"]
		config.usage.on_movie_eof.value = self.settings["movieoff"]
		return needUpdate

	def sortBy(self, newType):
		# GML:1
		print '[MovieSelection] SORTBY:', newType
		if newType < MovieList.TRASHSORT_SHOWRECORD:
			self.settings["moviesort"] = newType
			if not config.movielist.settings_per_directory.value:
				config.movielist.moviesort.value = newType
				config.movielist.moviesort.save()
			self.saveLocalSettings()
			self.setSortType(newType)
# Unset specific trash-sorting if other sort chosen while in Trash
			if MovieList.InTrashFolder:
				config.usage.trashsort_deltime.value = "no"
		else:
			if newType == MovieList.TRASHSORT_SHOWRECORD:
				config.usage.trashsort_deltime.value = "show record time"
			elif newType == MovieList.TRASHSORT_SHOWDELETE:
				config.usage.trashsort_deltime.value = "show delete time"
		config.usage.trashsort_deltime.save()
		self.reloadList()

	def showDescription(self, newType):
		self.settings["description"] = newType
		self.saveLocalSettings()
		self.setDescriptionState(newType)
		self.updateDescription()

	def abort(self, new_screen=None):
		global playlist
		del playlist[:]
		if self.list.playInBackground:
			self.list.playInBackground = None
			self.session.nav.stopService()
			self.callLater(self.abort)
			return

		if self.playingInForeground:
			self.list.playInForeground = self.playingInForeground
			self.session.nav.stopService()
			self.close(self.playingInForeground)
			return

		self.saveconfig()
		from Screens.InfoBar import InfoBar
		infobar = InfoBar.instance
		if self.session.nav.getCurrentlyPlayingServiceReference():
			if not infobar.timeshiftEnabled() and ':0:/' not in self.session.nav.getCurrentlyPlayingServiceReference().toString():
				self.session.nav.stopService()
		self.close(new_screen)

	def abortToTimer(self):
		self.abort("timer")

	def abortToEPG(self):
		self.abort("epg")

	def saveconfig(self):
		config.movielist.last_selected_tags.value = self.selected_tags

	def configure(self):
		self.session.openWithCallback(self.configureDone, MovieBrowserConfiguration)

	def configureDone(self, result):
		if result:
			self.applyConfigSettings({
				"moviesort": config.movielist.moviesort.value,
				"description": config.movielist.description.value,
				"movieoff": config.usage.on_movie_eof.value})
			self.saveLocalSettings()
			self._updateButtonTexts()
			self["list"].setItemsPerPage()
			self["list"].setFontsize()
			self.reloadList()
			self.updateDescription()

	def can_sortby(self, item):
		return True

	def do_sortby(self):
		self.selectSortby()

	def selectSortby(self):
		menu = []
		index = 0
		used = 0
		for x in l_moviesort:
			if int(x[0]) == int(config.movielist.moviesort.value):
				used = index
			menu.append((_(x[1]), x[0], "%d" % index))
			index += 1
# GML:1
		if MovieList.InTrashFolder:
			for x in l_trashsort:
				if x[3] == config.usage.trashsort_deltime.value:
					used = index
				menu.append((_(x[1]), x[0], "%d" % index))
				index += 1
		self.session.openWithCallback(self.sortbyMenuCallback, ChoiceBox, title=_("Movie sort"), list=menu, selection=used, skin_name="MovieSelectionSort")

	def getPixmapSortIndex(self, which):
		index = int(which)
# GML:1
		if (index == MovieList.TRASHSORT_SHOWRECORD) or (index == MovieList.TRASHSORT_SHOWDELETE):
			index = MovieList.SORT_RECORDED
		return index - 1

	def sortbyMenuCallback(self, choice):
		if choice is None:
			return
		self.sortBy(int(choice[1]))
		self["movie_sort"].setPixmapNum(self.getPixmapSortIndex(choice[1]))

	def getTagDescription(self, tag):
		# TODO: access the tag database
		return tag

	def updateTags(self):
		# get a list of tags available in this list
		self.tags = self["list"].tags

	def setDescriptionState(self, val):
		self["list"].setDescriptionState(val)

	def setSortType(self, type):
		self["list"].setSortType(type)

	def setCurrentRef(self, path):
		self.current_ref = eServiceReference(eServiceReference.idFile, eServiceReference.noFlags, eServiceReferenceFS.directory)
		self.current_ref.setPath(path)
		# Magic: this sets extra mappings between extensions and service types.
		self.current_ref.setName(extraExtensionServTypes)

	def updateFileFolderCounts(self):
		(nDirs, nFiles) = self["list"].userItemCount()
		self["numFolders"].text = _("Directories: %d") % nDirs
		self["numFiles"].text = _("Files: %d") % nFiles
		self.marked = self.list.countMarked()

	def updateTitle(self):
		title = ""
		if config.usage.setup_level.index >= 2:  # expert+
			title += friendlyMoviePath(config.movielist.last_videodir.value, trailing=False)
		if self.selected_tags:
			title += " - " + ','.join(self.selected_tags)
		self.setTitle(title)

	def reloadList(self, sel=None, home=False):
		self.reload_sel = sel
		self.reload_home = home
		self["waitingtext"].visible = True
		self.pathselectEnabled = False
		self.callLater(self.reloadWithDelay)

	def reloadWithDelay(self):
		if not os.path.isdir(config.movielist.last_videodir.value):
			path = defaultMoviePath()
			config.movielist.last_videodir.value = path
			config.movielist.last_videodir.save()
			self.setCurrentRef(path)
			self["diskSize"].path = path
			self["freeDiskSpace"].path = path
			self["TrashcanSize"].update(path)
		else:
			self["TrashcanSize"].update(config.movielist.last_videodir.value)
		if self.reload_sel is None:
			self.reload_sel = self.getCurrent()
		if config.usage.movielist_trashcan.value and os.access(config.movielist.last_videodir.value, os.W_OK):
			trash = Tools.Trashcan.createTrashFolder(config.movielist.last_videodir.value)
		self.loadLocalSettings()
		self["list"].reload(self.current_ref, self.selected_tags)
		self.updateTags()
		self.updateTitle()
		self.displayMovieOffStatus()
		self.displaySortStatus()
		if self.reload_sel:
			config.movielist.last_videodirpos.value = self.reload_sel.toString() + ',' + str(self["list"].getCurrentIndex())

		if not (self.reload_sel and self["list"].moveTo(self.reload_sel)):
			if self.reload_home:
				if config.movielist.use_last_videodirpos.value and config.movielist.last_videodirpos.value:
					try:
						refStr, index = config.movielist.last_videodirpos.value.rsplit(',', 1)
						if not self["list"].moveTo(eServiceReference(refStr)):
							self["list"].moveToIndex(int(index))
					except Exception, e:
						print "[Movielist] failed to return to previous entry:", e
						config.movielist.last_videodirpos.value = ""
						config.movielist.last_videodirpos.save()
						self["list"].moveToFirstMovie()
				else:
					self["list"].moveToFirstMovie()
		self["diskSize"].update()
		self["freeDiskSpace"].update()
		self.updateFileFolderCounts()
		self["waitingtext"].visible = False
		self.createPlaylist()
		if self.playGoTo:
			if self.isItemPlayable(self.list.getCurrentIndex() + 1):
				if self.playGoTo > 0:
					self.list.moveDown()
				else:
					self.list.moveUp()
				self.playGoTo = None
				self.callLater(self.preview)
		self.callLater(self.enablePathSelect)

	def enablePathSelect(self):
		self.pathselectEnabled = True

	def doPathSelect(self):
		if self.marked:
			return
		if self.pathselectEnabled:
			self.session.openWithCallback(
				self.doPathSelectCB,
				MovieLocationBox,
				_("Choose movie path"),
				config.movielist.last_videodir.value
			)

	def doPathSelectCB(self, res):
		updateUserDefinedActions()
		self._updateButtonTexts()
		self.gotFilename(res)

	def gotFilename(self, res, selItem=None, pinOk=False):
		def servicePinEntered(res, selItem, result):
			if result:
				from Components.ParentalControl import parentalControl
				parentalControl.setSessionPinCached()
				parentalControl.hideBlacklist()
				self.gotFilename(res, selItem, pinOk=True)
			elif result is False:
				self.session.open(MessageBox, _("The PIN code you entered is wrong."), MessageBox.TYPE_INFO, timeout=3)
		if not res:
			self.updateTitle()	# alias may have changed
			return
		# serviceref must end with /
		if not res.endswith('/'):
			res += '/'
		currentDir = config.movielist.last_videodir.value
		if res != currentDir:
			if os.path.isdir(res):
				baseName = os.path.basename(res[:-1])
				if not pinOk and config.ParentalControl.servicepinactive.value and baseName.startswith(".") and baseName not in (".Trash", ".trash", ".Trashcan"):
					from Components.ParentalControl import parentalControl
					if not parentalControl.sessionPinCached:
						self.session.openWithCallback(boundFunction(servicePinEntered, res, selItem), PinInput, pinList=[x.value for x in config.ParentalControl.servicepin], triesEntry=config.ParentalControl.retries.servicepin, title=_("Please enter the correct PIN code"), windowTitle=_("Enter PIN code"))
						return
				config.movielist.last_videodir.value = res
				config.movielist.last_videodir.save()
				self.loadLocalSettings()
				self.setCurrentRef(res)
				self["diskSize"].path = res
				self["freeDiskSpace"].path = res
				self["TrashcanSize"].update(res)
				if selItem:
					self.reloadList(home=True, sel=selItem)
				else:
					ref = eServiceReference(eServiceReference.idFile, eServiceReference.noFlags, eServiceReferenceFS.directory)
					ref.setPath(currentDir)
					self.reloadList(home=True, sel=ref)
			else:
				mbox = self.session.open(
					MessageBox,
					_("Directory '%s' does not exist.") % res,
					type=MessageBox.TYPE_ERROR,
					timeout=5)
				mbox.setTitle(self.getTitle())
		else:
			self.updateTitle()	# alias may have changed

	def showAll(self):
		self.selected_tags_ele = None
		self.selected_tags = None
		self.saveconfig()
		self.reloadList(home=True)

	def showTagsN(self, tagele):
		if not self.tags:
			self.showTagWarning()
		elif not tagele or (self.selected_tags and tagele.value in self.selected_tags) or tagele.value not in self.tags:
			self.showTagsMenu(tagele)
		else:
			self.selected_tags_ele = tagele
			self.selected_tags = self.tags[tagele.value]
			self.reloadList(home=True)

	def showTagsFirst(self):
		self.showTagsN(config.movielist.first_tags)

	def showTagsSecond(self):
		self.showTagsN(config.movielist.second_tags)

	def can_tags(self, item):
		return self.tags

	def do_tags(self):
		self.showTagsN(None)

	def tagChosen(self, tag):
		if tag is not None:
			if tag[1] is None:  # all
				self.showAll()
				return
			# TODO: Some error checking maybe, don't wanna crash on KeyError
			self.selected_tags = self.tags[tag[0]]
			if self.selected_tags_ele:
				self.selected_tags_ele.value = tag[0]
				self.selected_tags_ele.save()
			self.saveconfig()
			self.reloadList(home=True)

	def showTagsMenu(self, tagele):
		self.selected_tags_ele = tagele
		lst = [(_("Show all tags"), None)] + [(tag, self.getTagDescription(tag)) for tag in sorted(self.tags)]
		self.session.openWithCallback(self.tagChosen, ChoiceBox, title=_("Movie tag filter"), list=lst, skin_name=["MovieSelectionTags", "MovieListTags"])

	def showTagWarning(self):
		mbox = self.session.open(MessageBox, _("No tags are set on these movies."), MessageBox.TYPE_ERROR)
		mbox.setTitle(self.getTitle())

	def selectMovieLocation(self, title, callback, base=None):
		bookmarks = []
		buildMovieLocationList(bookmarks, base)
		bookmarks.append((_("(Other...)"), None))
		self.onMovieSelected = callback
		self.movieSelectTitle = title
		self.session.openWithCallback(self.gotMovieLocation, ChoiceBox, title=title, list=bookmarks, skin_name="MovieSelectionLocations")

	def gotMovieLocation(self, choice):
		if not choice:
			# cancelled
			self.onMovieSelected(None)
			del self.onMovieSelected
			self.updateTitle()	# alias may have changed
			return
		if isinstance(choice, tuple):
			if choice[1] is None:
				# Display full browser, which returns string
				self.session.openWithCallback(
					self.gotMovieLocationCB,
					MovieLocationBox,
					self.movieSelectTitle,
					config.movielist.last_videodir.value
				)
				return
			choice = choice[1]
		choice = os.path.normpath(choice)
		self.rememberMovieLocation(choice)
		self.onMovieSelected(choice)
		del self.onMovieSelected

	def gotMovieLocationCB(self, choice):
		updateUserDefinedActions()
		self._updateButtonTexts()
		self.gotMovieLocation(choice)

	def rememberMovieLocation(self, where):
		if where in last_selected_dest:
			last_selected_dest.remove(where)
		last_selected_dest.insert(0, where)
		if len(last_selected_dest) > 5:
			del last_selected_dest[-1]

	def playBlurayFile(self):
		if self.playfile:
			Screens.InfoBar.InfoBar.instance.checkTimeshiftRunning(self.autoBlurayCheckTimeshiftCallback)

	def autoBlurayCheckTimeshiftCallback(self, answer):
		if answer:
			playRef = eServiceReference(3, 0, self.playfile)
			self.playfile = ""
			self.close(playRef)

	def isBlurayFolderAndFile(self, service):
		self.playfile = ""
		folder = os.path.join(service.getPath(), "STREAM/")
		if "BDMV/STREAM/" not in folder:
			folder = folder[:-7] + "BDMV/STREAM/"
		if os.path.isdir(folder):
			fileSize = 0
			for name in os.listdir(folder):
				try:
					if name.endswith(".m2ts"):
						size = os.stat(folder + name).st_size
						if size > fileSize:
							fileSize = size
							self.playfile = folder + name
				except:
					print "[ML] Error calculate size for %s" % (folder + name)
			if self.playfile:
				return True
		return False

	def can_bookmarks(self, item):
		return not self.marked

	def do_bookmarks(self):
		if not self.marked:
			self.selectMovieLocation(title=_("Choose movie path"), callback=self.gotFilename, base=config.movielist.last_videodir.value)

	def can_addbookmark(self, item):
		return True

	def exist_bookmark(self):
		path = config.movielist.last_videodir.value
		if path in config.movielist.videodirs.value:
			return True
		return False

	def do_addbookmark(self):
		path = config.movielist.last_videodir.value
		if path in config.movielist.videodirs.value:
			if len(path) > 40:
				path = '...' + path[-40:]
			mbox = self.session.openWithCallback(self.removeBookmark, MessageBox, _("Do you really want to remove bookmark '%s'?") % path)
			mbox.setTitle(self.getTitle())
		else:
			config.movielist.videodirs.value += [path]
			config.movielist.videodirs.save()

	def removeBookmark(self, yes):
		if not yes:
			return
		path = config.movielist.last_videodir.value
		bookmarks = config.movielist.videodirs.value
		bookmarks.remove(path)
		config.movielist.videodirs.value = bookmarks
		config.movielist.videodirs.save()

	def do_counted(self):
		item = self.getCurrentSelection()
		if not isFolder(item):
			return
		path = item[0].getPath().rstrip('/')
		counted = config.movielist.counteddirs.value
		uncounted = config.movielist.uncounteddirs.value
		if is_counted(item[0].getPath()):
			if config.movielist.subdir_count.value and path.startswith(defaultMoviePath()):
				uncounted += [path]
			if path in counted:
				counted.remove(path)
		else:
			if not config.movielist.subdir_count.value or not path.startswith(defaultMoviePath()):
				counted += [path]
			if path in uncounted:
				uncounted.remove(path)
		config.movielist.counteddirs.value = counted
		config.movielist.uncounteddirs.value = uncounted
		config.movielist.counteddirs.save()
		config.movielist.uncounteddirs.save()
		self["list"].invalidateCurrentItem()

	def can_createdir(self, item):
		return True

	def do_createdir(self):
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		self.session.openWithCallback(
			self.createDirCallback, VirtualKeyBoard,
			title=_("Please enter name of the new directory"),
			text="")

	def createDirCallback(self, name):
		if not name:
			return
		msg = None
		try:
			path = os.path.join(config.movielist.last_videodir.value, name)
			os.mkdir(path)
			if not path.endswith('/'):
				path += '/'
			ref = eServiceReference(eServiceReference.idFile, eServiceReference.noFlags, eServiceReferenceFS.directory)
			ref.setPath(path)
			self.reloadList(sel=ref)
		except OSError, e:
			print "[MovieSelection] Error %s:" % e.errno, e
			if e.errno == 17:
				msg = _("'%s' already exists.") % name
			else:
				msg = _("Error\n%s") % str(e)
		except Exception, e:
			print "[MovieSelection] Unexpected error:", e
			msg = _("Error\n%s") % str(e)
		if msg:
			mbox = self.session.open(MessageBox, msg, type=MessageBox.TYPE_ERROR, timeout=5)
			mbox.setTitle(self.getTitle())

	def do_rename(self):
		if self.marked:
			return
		item = self.getCurrentSelection()
		if not canRename(item):
			return
		self.extension = ""
		if isFolder(item):
			p = os.path.split(item[0].getPath())
			if not p[1]:
				# if path ends in '/', p is blank.
				p = os.path.split(p[0])
			name = p[1]
		else:
			info = item[1]
			name = info.getName(item[0])
			full_name = os.path.split(item[0].getPath())[1]
			if full_name == name: # split extensions for files without metafile
				name, self.extension = os.path.splitext(name)

		from Screens.VirtualKeyBoard import VirtualKeyBoard
		self.session.openWithCallback(
			self.renameCallback, VirtualKeyBoard,
			title=_("Rename"),
			text=name)

	def do_decode(self):
		from ServiceReference import ServiceReference
		for item in self.getMarked():
			info = item[1]
			filepath = item[0].getPath()
			if not filepath.endswith('.ts'):
				continue
			serviceref = ServiceReference(None, reftype=eServiceReference.idDVB, path=filepath)
			name = info.getName(item[0]) + _(" - decoded")
			description = info.getInfoString(item[0], iServiceInformation.sDescription)
			recording = RecordTimer.RecordTimerEntry(serviceref, int(time.time()), int(time.time()) + 3600, name, description, 0, dirname=preferredTimerPath())
			recording.dontSave = True
			recording.autoincrease = True
			recording.setAutoincreaseEnd()
			self.session.nav.RecordTimer.record(recording, ignoreTSC=True)

	def renameCallback(self, name):
		if not name:
			return
		name = "".join((name.strip(), self.extension))
		item = self.getCurrentSelection()
		if item and item[0]:
			try:
				path = item[0].getPath().rstrip('/')
				meta = path + '.meta'
				if os.path.isfile(meta):
					metafile = open(meta, "r+")
					sid = metafile.readline()
					oldtitle = metafile.readline()
					rest = metafile.read()
					metafile.seek(0)
					metafile.write("%s%s\n%s" % (sid, name, rest))
					metafile.truncate()
					metafile.close()
					index = self.list.getCurrentIndex()
					info = self.list.list[index]
					if hasattr(info[3], 'txt'):
						info[3].txt = name
						# reparse info to update the name on invalidate
						serviceHandler = eServiceCenter.getInstance()
						newinfo = serviceHandler.info(info[0])
						if newinfo:
							self.list.list[index] = (info[0], newinfo, info[2], info[3])
					else:
						self.list.invalidateCurrentItem()
					return
				pathname, filename = os.path.split(path)
				newpath = os.path.join(pathname, name)
				msg = None
				print "[MovieSelection] rename", path, "to", newpath
				os.rename(path, newpath)
				ref = eServiceReference(eServiceReference.idFile, eServiceReference.noFlags, eServiceReferenceFS.directory)
				ref.setPath(newpath)
				self.reloadList(sel=ref)
				from Screens.InfoBarGenerics import renameResumePoint
				renameResumePoint(item[0], newpath)
			except OSError, e:
				print "[MovieSelection] Error %s:" % e.errno, e
				if e.errno == 17:
					msg = _("'%s' already exists.") % name
				else:
					msg = _("Error\n%s") % str(e)
			except Exception, e:
				import traceback
				print "[MovieSelection] Unexpected error:", e
				traceback.print_exc()
				msg = _("Error\n%s") % str(e)
			if msg:
				mbox = self.session.open(MessageBox, msg, type=MessageBox.TYPE_ERROR, timeout=5)
				mbox.setTitle(self.getTitle())

	def do_reset(self):
		for item in self.getMarked():
			current = item[0]
			resetMoviePlayState(current.getPath() + ".cuts", current)
			if not self.marked:
				self.list.invalidateCurrentItem()  # trigger repaint
			else:
				index = self.list.findService(current)
				self.list.invalidateItem(index)

	def do_move(self):
		item = None
		self.moveList = []
		for i in self.getMarked():
			if canMove(i) and i[1] is not None:
				item = i
				self.moveList.append(i)
		if item:
			current = item[0]
			info = item[1]
			path = os.path.normpath(current.getPath())
			if len(self.moveList) == 1:
				name = info and info.getName(current)
				if name:
					if name == path + '/':
						name = os.path.basename(path) + '/'
					else:
						name = "'" + name + "'"
				else:
					name = _("This recording")
			else:
				name = _("%d items") % len(self.moveList)
			self.selectMovieLocation(title=_("Choose move destination: %s") % name, callback=self.gotMoveMovieDest, base=os.path.dirname(path))

	def gotMoveMovieDest(self, choice):
		if not choice:
			return
		dest = os.path.normpath(choice)
		try:
			for item in self.moveList:
				current = item[0]
				name = item[1] and item[1].getName(current) or None
				moveServiceFiles(current, dest, name)
				self["list"].removeService(current)
			self.updateFileFolderCounts()
			self["list"].invalidatePathItem(dest)
		except Exception, e:
			mbox = self.session.open(MessageBox, str(e), MessageBox.TYPE_ERROR)
			mbox.setTitle(self.getTitle())

	def do_copy(self):
		item = None
		self.copyList = []
		for i in self.getMarked():
			if canCopy(i) and i[1] is not None:
				item = i
				self.copyList.append(i)
		if item:
			current = item[0]
			info = item[1]
			path = os.path.normpath(current.getPath())
			if len(self.copyList) == 1:
				name = info and info.getName(current)
				if name:
					if name == path + '/':
						name = os.path.basename(path) + '/'
					else:
						name = "'" + name + "'"
				else:
					name = _("This recording")
			else:
				name = _("%d items") % len(self.copyList)
			self.selectMovieLocation(title=_("Choose copy destination: %s") % name, callback=self.gotCopyMovieDest, base=os.path.dirname(path))

	def gotCopyMovieDest(self, choice):
		if not choice:
			return
		dest = os.path.normpath(choice)
		try:
			for item in self.copyList:
				current = item[0]
				name = item[1] and item[1].getName(current) or None
				copyServiceFiles(current, dest, name)
			self["list"].invalidatePathItem(dest)
		except Exception, e:
			mbox = self.session.open(MessageBox, str(e), MessageBox.TYPE_ERROR)
			mbox.setTitle(self.getTitle())

	def stopTimer(self, timer):
		if timer.isRunning():
			if timer.repeated:
				timer.enable()
				timer.processRepeated(findRunningEvent=False)
				self.session.nav.RecordTimer.doActivate(timer)
			else:
				timer.afterEvent = RecordTimer.AFTEREVENT.NONE
				NavigationInstance.instance.RecordTimer.removeEntry(timer)
			self["list"].refreshDisplay()

	def onTimerChoice(self, choice):
		if isinstance(choice, tuple) and choice[1]:
			choice, timer = choice[1]
			if not choice:
				# cancel
				return
			if "s" in choice:
				self.stopTimer(timer)
			if "d" in choice:
				self.delete(True)

	def onTimerChoiceList(self, choice):
		if choice:
			choice = choice[1]
		else:
			choice = ""
		for rec in self.recList:
			if "s" in choice:
				self.stopTimer(rec[1])
			if "d" not in choice:
				self.delList.remove(rec[0])
		if len(self.delList) == 1:
			self.delItem = self.delList[0]
			self.delete()
			return
		if self.delList:
			self.do_delete(fromRec=True)

	def do_delete(self, fromRec=False):
		self.delItem = None
		if not self.marked:
			self.delete()
			return

		if fromRec:
			dirs, subfiles, subdirs = self.del_state
		else:
			self.delList = []
			self.recList = []
			dirs = 0
			subfiles = 0
			subdirs = 0
			self.inTrash = None
			for item in self.getMarked():
				current = item[0]
				info = item[1]
				cur_path = os.path.realpath(current.getPath())
				if not os.path.exists(cur_path):
					continue
				pathtest = info and info.getName(current)
				if not pathtest:
					continue
				if isTrashFolder(item[0]):
					self.purgeAll()
					continue
				if self.inTrash is None:
					self.inTrash = '.Trash' in cur_path
				self.delList.append(item)
				if isFolder(item):
					dfiles = 0
					ddirs = 0
					for fn in os.listdir(cur_path):
						if (fn != '.') and (fn != '..') and (fn != '.e2settings.pkl'):
							ffn = os.path.join(cur_path, fn)
							if os.path.isdir(ffn):
								ddirs += 1
							else:
								tempfn, tempfext = os.path.splitext(fn)
								if tempfext not in ('.eit', '.ap', '.cuts', '.meta', '.sc'):
									dfiles += 1
					if dfiles or ddirs:
						dirs += 1
						subfiles += dfiles
						subdirs += ddirs
				else:
					rec_filename = os.path.basename(current.getPath())
					if rec_filename.endswith(".ts"):
						rec_filename = rec_filename[:-3]
					for timer in NavigationInstance.instance.RecordTimer.timer_list:
						if timer.isRunning() and not timer.justplay and rec_filename == os.path.basename(timer.Filename):
							self.recList.append((item, timer))

			if len(self.delList) == 1:
				self.delItem = self.delList[0]
				self.delete()
				return

			if self.recList:
				self.del_state = (dirs, subfiles, subdirs)
				choices = [
					(_("Ignore"), ""),
					(_("Stop recording"), "s"),
					(_("Stop recording and delete"), "sd")]
				self.session.openWithCallback(self.onTimerChoiceList, ChoiceBox, title=_("Recordings in progress: %d") % len(self.recList), list=choices, skin_name="MovieSelectionRecordings")
				return

		if dirs:
			if self.inTrash:
				are_you_sure = _("Do you really want to permanently remove these items from trash?")
			elif config.usage.movielist_trashcan.value:
				are_you_sure = _("Do you really want to move these items to trash?")
			else:
				are_you_sure = _("Do you really want to delete these items?")
			mdir = ngettext("%d directory contains", "%d directories contain", dirs) % dirs
			mfile = ngettext("%d file", "%d files", subfiles) % subfiles
			msub = ngettext("%d subdirectory", "%d subdirectories", subdirs) % subdirs
			are_you_sure = _("%s %s and %s.\n") % (mdir, mfile, msub) + are_you_sure
		elif self.inTrash:
			are_you_sure = _("Do you really want to permanently remove these items from trash?")
		elif config.usage.movielist_trashcan.value:
			if config.usage.movielist_asktrash.value:
				are_you_sure = _("Do you really want to move these items to trash?")
			else:
				self.deleteList(True)
				return
		else:
			are_you_sure = _("Do you really want to delete these items?")
		mbox = self.session.openWithCallback(self.deleteList, MessageBox, are_you_sure)
		mbox.setTitle(self.getTitle())

	def deleteList(self, confirmed):
		if not confirmed:
			return
		while self.delList:
			self.delItem = self.delList.pop()
			if isFolder(self.delItem) or config.usage.movielist_trashcan.value and not self.inTrash:
				self.delete(True)
			else:
				self.deleteConfirmed(True)

	def delete(self, *args):
		item = self.delItem or self.getCurrentSelection()
		if not item or args and (not args[0]):
			# cancelled by user (passing any arg means it's a dialog return)
			return
		current = item[0]
		info = item[1]
		cur_path = os.path.realpath(current.getPath())
		if not os.path.exists(cur_path):
			# file does not exist.
			return
		st = os.stat(cur_path)
		name = info and info.getName(current) or _("This recording")
		are_you_sure = ""
		pathtest = info and info.getName(current)
		if not pathtest:
			return
		if item and isTrashFolder(item[0]):
			# Red button to empty trash...
			self.purgeAll()
			return
		if current.flags & eServiceReference.mustDescent:
			files = 0
			subdirs = 0
			if '.Trash' not in cur_path and config.usage.movielist_trashcan.value:
				if isFolder(item):
					are_you_sure = _("Do you really want to move this to trash?")
					subdirs += 1
				else:
					args = True
				folder_filename = os.path.split(os.path.split(name)[0])[1]
				if args:
					try:
						# Move the files to trash in a way that their CTIME is
						# set to "now". A simple move would not correctly update the
						# ctime, and hence trigger a very early purge.
						trash = Tools.Trashcan.createTrashFolder(cur_path)
						moveServiceFiles(current, trash, name, allowCopy=True)
						self["list"].removeService(current)
						self.updateFileFolderCounts()
						self.showActionFeedback(_("Deleted '%s'") % name)
						# Files were moved to .Trash, ok.
						return
					except Exception, e:
						print "[MovieSelection] Weird error moving to trash", e
						# Failed to create trash or move files.
						msg = _("Can not move to trash") + "\n"
						if trash is None:
							msg += _("Trash is missing")
						else:
							msg += str(e)
						msg += "\n"
						are_you_sure = _("Do you really want to delete '%s'?") % folder_filename
						mbox = self.session.openWithCallback(self.deleteDirConfirmed, MessageBox, msg + are_you_sure)
						mbox.setTitle(self.getTitle())
						return
				for fn in os.listdir(cur_path):
					if (fn != '.') and (fn != '..') and (fn != '.e2settings.pkl'):
						ffn = os.path.join(cur_path, fn)
						if os.path.isdir(ffn):
							subdirs += 1
						else:
							tempfn, tempfext = os.path.splitext(fn)
							if tempfext not in ('.eit', '.ap', '.cuts', '.meta', '.sc'):
								files += 1
				if files or subdirs:
					mbox = self.session.openWithCallback(self.delete, MessageBox, _("'%s' contains %d file(s) and %d sub-directories.\n") % (folder_filename,files,subdirs-1) + are_you_sure)
					mbox.setTitle(self.getTitle())
					return
				else:
					self.delete(True)
			else:
				if '.Trash' in cur_path:
					are_you_sure = _("Do you really want to permanently remove the folder and its contents from trash?")
				else:
					are_you_sure = _("Do you really want to delete?")
				if args:
					self.deleteDirConfirmed(True)
					return
				for fn in os.listdir(cur_path):
					if (fn != '.') and (fn != '..'):
						ffn = os.path.join(cur_path, fn)
						if os.path.isdir(ffn):
							subdirs += 1
						else:
							tempfn, tempfext = os.path.splitext(fn)
							if tempfext not in ('.eit', '.ap', '.cuts', '.meta', '.sc'):
								files += 1
				if files or subdirs:
					folder_filename = os.path.split(os.path.split(name)[0])[1]
					mbox = self.session.openWithCallback(self.delete, MessageBox, _("'%s' contains %d file(s) and %d sub-directories.\n") % (folder_filename, files, subdirs) + are_you_sure)
					mbox.setTitle(self.getTitle())
					return
				else:
					try:
						path = os.path.join(cur_path, ".e2settings.pkl")
						if os.path.exists(path):
							os.remove(path)
						os.rmdir(cur_path)
					except Exception, e:
						print "[MovieSelection] Failed delete", e
						self.session.open(MessageBox, _("Delete failed.\n%s") % str(e), MessageBox.TYPE_ERROR)
					else:
						self["list"].removeService(current)
						self.updateFileFolderCounts()
						self.showActionFeedback(_("Deleted '%s'") % name)
		else:
			if not args:
				if config.usage.movielist_trashcan.value and config.usage.movielist_asktrash.value and '.Trash' not in cur_path:
					are_you_sure = _("Do you really want to move '%s' to trash?") % name
					mbox = self.session.openWithCallback(self.delete, MessageBox, are_you_sure, default=False)
					mbox.setTitle(self.getTitle())
					return
				rec_filename = os.path.basename(current.getPath())
				if rec_filename.endswith(".ts"):
					rec_filename = rec_filename[:-3]
				for timer in NavigationInstance.instance.RecordTimer.timer_list:
					if timer.isRunning() and not timer.justplay and rec_filename == os.path.basename(timer.Filename):
						choices = [
							(_("Cancel"), None),
							(_("Stop recording"), ("s", timer)),
							(_("Stop recording and delete"), ("sd", timer))]
						self.session.openWithCallback(self.onTimerChoice, ChoiceBox, title=_("Recording in progress:\n'%s'") % name, list=choices, skin_name="MovieSelectionRecordings")
						return
				if time.time() - st.st_mtime < 5:
					if not args:
						are_you_sure = _("Do you really want to delete?")
						mbox = self.session.openWithCallback(self.delete, MessageBox, _("File appears to be busy.\n") + are_you_sure)
						mbox.setTitle(self.getTitle())
						return
			if '.Trash' not in cur_path and config.usage.movielist_trashcan.value:
				trash = Tools.Trashcan.createTrashFolder(cur_path)
				if trash:
					try:
						moveServiceFiles(current, trash, name, allowCopy=True)
						self["list"].removeService(current)
						self.updateFileFolderCounts()
						# Files were moved to .Trash, ok.
						self.showActionFeedback(_("Deleted '%s'") % name)
						return
					except:
						msg = _("Cannot move to trash") + "\n"
						are_you_sure = _("Do you really want to delete '%s'?") % name
				else:
					msg = _("Can not move to trash") + "\n"
					are_you_sure = _("Do you really want to delete '%s'?") % name
			else:
				if '.Trash' in cur_path:
					are_you_sure = _("Do you really want to permanently remove '%s' from trash?") % name
				else:
					are_you_sure = _("Do you really want to delete '%s'?") % name
				msg = ''
			mbox = self.session.openWithCallback(self.deleteConfirmed, MessageBox, msg + are_you_sure)
			mbox.setTitle(self.getTitle())

	def deleteConfirmed(self, confirmed):
		if not confirmed:
			return
		item = self.delItem or self.getCurrentSelection()
		if item is None:
			return  # huh?
		current = item[0]
		info = item[1]
		name = info and info.getName(current) or _("This recording")
		serviceHandler = eServiceCenter.getInstance()
		offline = serviceHandler.offlineOperations(current)
		try:
			if offline is None:
				from enigma import eBackgroundFileEraser
				eBackgroundFileEraser.getInstance().erase(os.path.realpath(current.getPath()))
			else:
				if offline.deleteFromDisk(0):
					raise Exception("Offline delete failed")
			from Screens.InfoBarGenerics import delResumePoint
			delResumePoint(current)
			self["list"].removeService(current)
			self.updateFileFolderCounts()
			self.showActionFeedback(_("Deleted '%s'") % name)
		except Exception, ex:
			mbox = self.session.open(MessageBox, _("Delete failed.\n'%s'\n%s") % (name, str(ex)), MessageBox.TYPE_ERROR)
			mbox.setTitle(self.getTitle())

	def deleteDirConfirmed(self, confirmed):
		if not confirmed:
			return
		item = self.delItem or self.getCurrentSelection()
		if item is None:
			return  # huh?
		current = item[0]
		info = item[1]
		cur_path = os.path.realpath(current.getPath())
		if not os.path.exists(cur_path):
			# file does not exist.
			return
		name = info and info.getName(current) or _("This recording")
		try:
			# already confirmed...
			# but not implemented yet...
			Tools.CopyFiles.deleteFiles(cur_path, name)
			from Screens.InfoBarGenerics import delResumePoint
			delResumePoint(current)
			self["list"].removeService(current)
			self.updateFileFolderCounts()
			self.showActionFeedback(_("Deleted '%s'") % name)
			return
		except Exception, e:
			print "[MovieSelection] Weird error moving to trash", e
			# Failed to create trash or move files.
			msg = _("Can not delete file.\n%s\n") % str(e)
			mbox = self.session.open(MessageBox, msg, MessageBox.TYPE_ERROR)
			mbox.setTitle(self.getTitle())

	def purgeAll(self):
		recordings = self.session.nav.getRecordings()
		next_rec_time = -1
		if not recordings:
			next_rec_time = self.session.nav.RecordTimer.getNextRecordingTime()
		if recordings or (next_rec_time > 0 and (next_rec_time - time.time()) < 120):
			msg = "\n" + _("Recording(s) are in progress or coming up soon.")
		else:
			msg = ""
		mbox = self.session.openWithCallback(self.purgeConfirmed, MessageBox, _("Permanently delete all recordings in trash?") + msg)
		mbox.setTitle(self.getTitle())

	def purgeConfirmed(self, confirmed):
		if not confirmed:
			return
		item = self.getCurrentSelection()
		if item is not None:
			current = item[0]
			Tools.Trashcan.cleanAll(os.path.split(current.getPath())[0])
			from Screens.InfoBarGenerics import delResumePoint
			delResumePoint(current)

	def showActionFeedback(self, text):
		if self.feedbackTimer is None:
			self.feedbackTimer = eTimer()
			self.feedbackTimer.callback.append(self.hideActionFeedback)
		else:
			self.feedbackTimer.stop()
		self.feedbackTimer.start(3000, 1)
		self.diskinfo.setText(text)

	def hideActionFeedback(self):
		self.diskinfo.update()
		current = self.getCurrent()
		if current is not None:
			self.trashinfo.update(current.getPath())

	def can_gohome(self, item):
		return not self.marked

	def do_gohome(self):
		if self.marked:
			return
		self.gotFilename(defaultMoviePath())

	def do_sortdefault(self):
		print '[MovieSelection] SORT:', config.movielist.moviesort.value
		config.movielist.moviesort.value = config.movielist.moviesort.default
		print '[MovieSelection] SORT:', config.movielist.moviesort.value
		self.sortBy(int(config.movielist.moviesort.value))

	def do_sort(self):
		index = 0
		for index, item in enumerate(l_moviesort):
			if int(item[0]) == int(config.movielist.moviesort.value):
				break
		if index >= len(l_moviesort) - 1:
			index = 0
		else:
			index += 1
		# descriptions in native languages too long...
		sorttext = l_moviesort[index][2]
		if config.movielist.btn_red.value == "sort":
			self['key_red'].setText(sorttext)
		if config.movielist.btn_green.value == "sort":
			self['key_green'].setText(sorttext)
		if config.movielist.btn_yellow.value == "sort":
			self['key_yellow'].setText(sorttext)
		if config.movielist.btn_blue.value == "sort":
			self['key_blue'].setText(sorttext)
		self.sorttimer.start(3000, True)  # time for displaying sorting type just applied
		self.sortBy(int(l_moviesort[index][0]))
		self["movie_sort"].setPixmapNum(self.getPixmapSortIndex(l_moviesort[index][0]))

	def do_preview(self):
		self.preview()

	def displaySortStatus(self):
		self["movie_sort"].setPixmapNum(self.getPixmapSortIndex(config.movielist.moviesort.value))
		self["movie_sort"].show()

	def can_movieoff(self, item):
		return True

	def do_movieoff(self):
		self.setNextMovieOffStatus()
		self.displayMovieOffStatus()

	def displayMovieOffStatus(self):
		self["movie_off"].setPixmapNum(config.usage.on_movie_eof.getIndex())
		self["movie_off"].show()

	def setNextMovieOffStatus(self):
		config.usage.on_movie_eof.selectNext()
		self.settings["movieoff"] = config.usage.on_movie_eof.value
		self.saveLocalSettings()

	def can_movieoff_menu(self, item):
		return True

	def do_movieoff_menu(self):
		current_movie_eof = config.usage.on_movie_eof.value
		menu = []
		for x in config.usage.on_movie_eof.choices:
			config.usage.on_movie_eof.value = x
			menu.append((config.usage.on_movie_eof.getText(), x))
		config.usage.on_movie_eof.value = current_movie_eof
		used = config.usage.on_movie_eof.getIndex()
		self.session.openWithCallback(self.movieoffMenuCallback, ChoiceBox, title=_("On end of movie"), list=menu, selection=used, skin_name="MovieSelectionOnEnd")

	def movieoffMenuCallback(self, choice):
		if choice is None:
			return
		self.settings["movieoff"] = choice[1]
		self.saveLocalSettings()
		self.displayMovieOffStatus()

	def createPlaylist(self):
		global playlist, playingList
		items = playlist
		if playingList:
			playingList = False
			self.list.markItems(items)
			self.marked = self.list.countMarked()
			del items[:]
		else:
			del items[:]
			for index, item in enumerate(self["list"]):
				if item:
					item = item[0]
					path = item.getPath()
					if not item.flags & eServiceReference.mustDescent:
						ext = os.path.splitext(path)[1].lower()
						if ext in IMAGE_EXTENSIONS:
							continue
						else:
							items.append(item)

playlist = []
playingList = False
