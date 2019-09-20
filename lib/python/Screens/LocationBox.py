#
# Generic Screen to select a path/filename combination
#

# GUI (Screens)
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Screens.HelpMenu import HelpableScreen
from Screens.ChoiceBox import ChoiceBox

# Generic
from Tools.BoundFunction import boundFunction
from Tools.Directories import pathExists, createDir, removeDir, resolveFilename, SCOPE_CONFIG
from Components.config import config, ConfigYesNo
import os
import cPickle as pickle

# Quickselect
from Tools.NumericalTextInput import NumericalTextInput

# GUI (Components)
from Components.ActionMap import NumberActionMap, HelpableActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.Button import Button
from Components.FileList import FileList
from Components.MenuList import MenuList

# Timer
from enigma import eTimer

defaultInhibitDirs = [
	"/.cache", "/bin", "/boot", "/dev", "/etc", "/home",
	"/lib", "/picon", "/proc", "/run", "/sbin", "/share", "/sys",
	"/tmp", "/usr", "/var",
]

# config.usage hasn't been created when this is initialised
config.misc.location_aliases = ConfigYesNo(default=True)
# prefixing this with underscores didn't work
aliasesFile = resolveFilename(SCOPE_CONFIG, "location_aliases")
location_aliases = {}
try:
	with open(aliasesFile, "rb") as f:
		location_aliases = pickle.load(f)
except:
	pass

class LocationBox(Screen, NumericalTextInput, HelpableScreen):
	"""Simple Class similar to MessageBox / ChoiceBox but used to choose a folder/pathname combination"""
	def __init__(self, session, text="", filename="", currDir=None, bookmarks=None, userMode=False, windowTitle=None, minFree=None, autoAdd=False, editDir=False, inhibitDirs=None, inhibitMounts=None, useAliases=False):
		# Init parents
		if not inhibitDirs: inhibitDirs = []
		if not inhibitMounts: inhibitMounts = []
		Screen.__init__(self, session)
		NumericalTextInput.__init__(self, handleTimeout=False)
		HelpableScreen.__init__(self)

		# Set useable chars
		self.setUseableChars(u'1234567890abcdefghijklmnopqrstuvwxyz')

		# Quickselect Timer
		self.qs_timer = eTimer()
		self.qs_timer.callback.append(self.timeout)
		self.qs_timer_type = 0

		# Initialize Quickselect
		self.curr_pos = -1
		self.quickselect = ""

		# Set Text
		self["text"] = Label(text)
		self["textbook"] = Label(_("Bookmarks"))

		# Save parameters locally
		self.text = text
		self.filename = filename
		self.minFree = minFree
		self.realBookmarks = bookmarks
		self.bookmarks = bookmarks and bookmarks.getValue()[:] or []
		self.userMode = userMode
		self.autoAdd = autoAdd
		self.editDir = editDir
		self.inhibitDirs = inhibitDirs
		self.useAliases = useAliases
		self.usingAliases = self.useAliases and config.misc.location_aliases.value

		# Initialize FileList
		self["filelist"] = FileList(currDir, showDirectories=True, showFiles=False, inhibitMounts=inhibitMounts, inhibitDirs=inhibitDirs)

		# Initialize BookList
		if self.usingAliases:
			self.bookmarks = [self.getAlias(bm) for bm in self.bookmarks]
		self["booklist"] = MenuList(self.bookmarks)

		# Buttons
		self["key_green"] = Button(_("OK"))
		self["key_yellow"] = Button(_("Rename"))
		self["key_blue"] = Button()
		self["key_red"] = Button(_("Cancel"))

		# Background for Buttons
		self["green"] = Pixmap()
		self["yellow"] = Pixmap()
		self["blue"] = Pixmap()
		self["red"] = Pixmap()

		# Initialize Target
		self["target"] = Label()

		if self.userMode:
			self.usermodeOn()

		# Custom Action Handler
		class LocationBoxActionMap(HelpableActionMap):
			def __init__(self, parent, context, actions=None, prio=0):
				if not actions: actions = {}
				HelpableActionMap.__init__(self, parent, context, actions, prio)
				self.box = parent

			def action(self, contexts, action):
				# Reset Quickselect
				self.box.timeout(force=True)

				return HelpableActionMap.action(self, contexts, action)

		# Actions that will reset quickselect
		self["WizardActions"] = LocationBoxActionMap(self, "WizardActions",
			{
				"ok": (self.ok, _("Select")),
				"back": (self.cancel, _("Cancel")),
			}, prio=-2)

		self["DirectionActions"] = LocationBoxActionMap(self, "DirectionActions",
			{
				"left": self.left,
				"right": self.right,
				"up": self.up,
				"down": self.down,
			}, prio=-2)

		self["ColorActions"] = LocationBoxActionMap(self, "ColorActions",
			{
				"red": self.cancel,
				"green": self.select,
				"yellow": self.changeName,
				"blue": self.addRemoveBookmark,
			}, prio=-2)

		self["EPGSelectActions"] = LocationBoxActionMap(self, "EPGSelectActions",
			{
				"prevService": (self.switchToBookList, _("Switch to bookmarks")),
				"nextService": (self.switchToFileList, _("Switch to directories")),
			}, prio=-2)

		self["MenuActions"] = LocationBoxActionMap(self, "MenuActions",
			{
				"menu": (self.showMenu, _("Menu")),
			}, prio=-2)

		# Actions used by quickselect
		self["NumberActions"] = NumberActionMap(["NumberActions"],
		{
			"1": self.keyNumberGlobal,
			"2": self.keyNumberGlobal,
			"3": self.keyNumberGlobal,
			"4": self.keyNumberGlobal,
			"5": self.keyNumberGlobal,
			"6": self.keyNumberGlobal,
			"7": self.keyNumberGlobal,
			"8": self.keyNumberGlobal,
			"9": self.keyNumberGlobal,
			"0": self.keyNumberGlobal
		})

		# Run some functions when shown
		if windowTitle is None:
			windowTitle = _("Select Location")
		self.onShown.extend((
			boundFunction(self.setTitle, windowTitle),
			self.updateTarget,
			self.showHideRename,
		))

		self.onLayoutFinish.append(self.switchToFileListOnStart)

		# Make sure we remove our callback
		self.onClose.append(self.disableTimer)

	def switchToFileListOnStart(self):
		if self.realBookmarks and self.realBookmarks.value:
			self.currList = "booklist"
			currDir = self.getAlias(self["filelist"].current_directory)
			if currDir in self.bookmarks:
				self["booklist"].moveToIndex(self.bookmarks.index(currDir))
		else:
			self.switchToFileList()
		self.currList = "filelist"
		self["key_blue"].text = _("Add bookmark")
		self.up()

	def disableTimer(self):
		self.qs_timer.callback.remove(self.timeout)

	def showHideRename(self):
		# Don't allow renaming when filename is empty
		if self.filename == "":
			self["key_yellow"].hide()

	def switchToFileList(self):
		if not self.userMode:
			self.currList = "filelist"
			self["filelist"].selectionEnabled(1)
			self["booklist"].selectionEnabled(0)
			self["key_blue"].text = _("Add bookmark")
			self.updateTarget()

	def switchToBookList(self):
		self.currList = "booklist"
		self["filelist"].selectionEnabled(0)
		self["booklist"].selectionEnabled(1)
		self["key_blue"].text = _("Remove bookmark")
		self.updateTarget()

	def addRemoveBookmark(self):
		if self.currList == "filelist":
			# add bookmark
			folder = self.getAlias(self["filelist"].getSelection()[0])
			if folder is not None and not folder in self.bookmarks:
				self.bookmarks.append(folder)
				self.bookmarks.sort()
				self["booklist"].setList(self.bookmarks)
		else:
			# remove bookmark
			if not self.userMode:
				name = self["booklist"].getCurrent()
				if name:
					if self.usingAliases:
						bm, name = name
					else:
						bm = name
					self.session.openWithCallback(
						boundFunction(self.removeBookmark, name),
						MessageBox,
						_("Do you really want to remove your bookmark of %s?") % bm
					)

	def removeBookmark(self, name, ret):
		if not ret:
			return
		name = self.getAlias(name)
		if name in self.bookmarks:
			self.bookmarks.remove(name)
			self["booklist"].setList(self.bookmarks)

	def createDir(self):
		if self["filelist"].current_directory is not None:
			self.session.openWithCallback(
				self.createDirCallback,
				VirtualKeyBoard,
				title = _("Please enter the name of the new directory"),
				text = ""
			)

	def createDirCallback(self, res):
		if res:
			path = os.path.join(self["filelist"].current_directory, res)
			if not pathExists(path):
				if not createDir(path):
					self.session.open(
						MessageBox,
						_("Creating directory %s failed.") % path,
						type = MessageBox.TYPE_ERROR,
						timeout = 5
					)
				self["filelist"].refresh()
			else:
				self.session.open(
					MessageBox,
					_("The path %s already exists.") % path,
					type = MessageBox.TYPE_ERROR,
					timeout = 5
				)

	def removeDir(self):
		sel = self["filelist"].getSelection()
		if sel and pathExists(sel[0]):
			name = friendlyMoviePath(sel[0]) if self.usingAliases else sel[0]
			self.session.openWithCallback(
				boundFunction(self.removeDirCallback, sel[0]),
				MessageBox,
				_("Do you really want to remove directory %s from the disk?") % name,
				type = MessageBox.TYPE_YESNO
			)
		else:
			self.session.open(
				MessageBox,
				_("Invalid directory selected: %s") % (sel[0]),
				type = MessageBox.TYPE_ERROR,
				timeout = 5
			)

	def removeDirCallback(self, name, res):
		if res:
			if not removeDir(name):
				self.session.open(
					MessageBox,
					_("Removing directory %s failed. (Maybe not empty.)") % name,
					type = MessageBox.TYPE_ERROR,
					timeout = 5
				)
			else:
				self["filelist"].refresh()
				self.updateTarget()
				self.removeBookmark(name, True)
				val = self.realBookmarks and self.realBookmarks.value
				if val and name in val:
					val.remove(name)
					self.realBookmarks.setValue(val)
					self.realBookmarks.save()

	def up(self):
		self[self.currList].up()
		self.updateTarget()

	def down(self):
		self[self.currList].down()
		self.updateTarget()

	def left(self):
		self[self.currList].pageUp()
		self.updateTarget()

	def right(self):
		self[self.currList].pageDown()
		self.updateTarget()

	def ok(self):
		if self.currList == "filelist":
			if self["filelist"].canDescent():
				self["filelist"].descent()
				self.updateTarget()
		else:
			self.select()

	def cancel(self):
		self.close(None)

	def getPreferredFolder(self):
		if self.currList == "filelist":
			selection = self["filelist"].getSelection()[0]
			currentDir = self["filelist"].getCurrentDirectory()

			# If the user enters a directory, the first entry highlighted is "<Parent directory>", but selecting that
			# will counter-intuitively return, well, the parent directory, rather than the directory just entered. Here
			# we detect that state (the selected directory will be a parent of the current directory), and instead
			# return the current directory.
			if selection is not None and currentDir is not None:
				if os.path.realpath(currentDir).startswith(os.path.realpath(selection)):
					return currentDir
			return selection
		else:
			bm = self["booklist"].getCurrent()
			return bm[1] if bm and self.usingAliases else bm

	def selectConfirmed(self, ret):
		if ret:
			pref = self.getPreferredFolder()
			ret = ''.join((pref, self.filename))
			if self.realBookmarks:
				aret = self.getAlias(ret)
				if self.autoAdd and not aret in self.bookmarks:
					self.bookmarks.append(self.getAlias(pref))
					self.bookmarks.sort()

				if self.usingAliases:
					bm = [bm[1] for bm in self.bookmarks]
				else:
					bm = self.bookmarks
				if bm != self.realBookmarks.value:
					self.realBookmarks.value = bm
					self.realBookmarks.save()
			self.close(ret)

	def select(self):
		currentFolder = self.getPreferredFolder()
		# Do nothing unless current Directory is valid
		if currentFolder is not None:
			# Check if we need to have a minimum of free Space available
			if self.minFree is not None:
				# Try to read fs stats
				try:
					s = os.statvfs(currentFolder)
					if (s.f_bavail * s.f_bsize) / 1000000 > self.minFree:
						# Automatically confirm if we have enough free disk Space available
						return self.selectConfirmed(True)
				except OSError:
					pass

				# Ask User if he really wants to select this folder
				self.session.openWithCallback(
					self.selectConfirmed,
					MessageBox,
					_("There might not be enough space on the selected partition.\nDo you really want to continue?"),
					type = MessageBox.TYPE_YESNO
				)
			# No minimum free Space means we can safely close
			else:
				self.selectConfirmed(True)

	def changeName(self):
		if self.filename != "":
			# TODO: Add Information that changing extension is bad? disallow?
			self.session.openWithCallback(
				self.nameChanged,
				VirtualKeyBoard,
				title = _("Please enter a new filename"),
				text = self.filename
			)

	def nameChanged(self, res):
		if res is not None:
			if len(res):
				self.filename = res
				self.updateTarget()
			else:
				self.session.open(
					MessageBox,
					_("An empty filename is invalid."),
					type = MessageBox.TYPE_ERROR,
					timeout = 5
				)

	def updateTarget(self):
		# Write Combination of Folder & Filename when Folder is valid
		currFolder = self.getPreferredFolder()
		if currFolder is not None:
			name = ''.join((currFolder, self.filename))
			if self.usingAliases:
				alias = friendlyMoviePath(name)
				if name != alias:
					name = "%s (%s)" % (alias, name)
			self["target"].setText(name)
		# Display a Warning otherwise
		else:
			self["target"].setText(_("Invalid location"))

	def getAlias(self, path):
		if self.usingAliases:
			return (friendlyMoviePath(path, trailing=False), path)
		return path

	def enableDisableAliases(self):
		config.misc.location_aliases.value = not config.misc.location_aliases.value
		config.misc.location_aliases.save()
		if self.usingAliases:
			self.usingAliases = False
			self.bookmarks = [bm[1] for bm in self.bookmarks]
		else:
			self.usingAliases = True
			self.bookmarks = [self.getAlias(bm) for bm in self.bookmarks]
		self["booklist"].setList(self.bookmarks)
		self.updateTarget()

	def removeAlias(self):
		self.setAliasCallback(None, rm=True)

	def setAlias(self):
		currentFolder = self.getPreferredFolder()
		if currentFolder is not None:
			global location_aliases
			name = location_aliases.get(currentFolder, os.path.basename(os.path.normpath(currentFolder)))
			self.session.openWithCallback(
				self.setAliasCallback,
				VirtualKeyBoard,
				title=_("Alias '%s' to:") % currentFolder,
				text=name
			)

	def setAliasCallback(self, res, rm=False):
		global location_aliases, aliasesFile
		if not res and not rm:
			return
		currentFolder = self.getPreferredFolder()
		if res:
			location_aliases[currentFolder] = res
		elif currentFolder in location_aliases:
			del location_aliases[currentFolder]
		try:
			with open(aliasesFile, "wb") as f:
				pickle.dump(location_aliases, f)
		except Exception, ex:
			print "[LocationBox] Failed to write aliases:", ex
		self.bookmarks = [self.getAlias(bm[1]) for bm in self.bookmarks]
		self["booklist"].setList(self.bookmarks)
		self.updateTarget()

	def showMenu(self):
		if not self.userMode and self.realBookmarks:
			if self.currList == "filelist":
				title = "Directories"
				menu = [
					(_("switch to bookmarks"), self.switchToBookList),
					(_("add bookmark"), self.addRemoveBookmark)
				]
				if self.editDir:
					menu.extend((
						(_("create directory"), self.createDir),
						(_("remove directory"), self.removeDir)
					))
			else:
				title = "Bookmarks"
				menu = [
					(_("switch to directories"), self.switchToFileList),
					(_("remove bookmark"), self.addRemoveBookmark)
				]
			if self.useAliases:
				if config.misc.location_aliases.value:
					menu.extend(((_("disable aliases"), self.enableDisableAliases),))
					currentFolder = self.getPreferredFolder()
					if currentFolder in location_aliases:
						menu.extend((
							(_("edit alias"), self.setAlias),
							(_("remove alias"), self.removeAlias)
						))
					else:
						menu.extend(((_("create alias"), self.setAlias),))
				else:
					menu.extend(((_("enable aliases"), self.enableDisableAliases),))

			self.session.openWithCallback(
				self.menuCallback,
				ChoiceBox,
				title=title,
				list=menu
			)

	def menuCallback(self, choice):
		if choice:
			choice[1]()

	def usermodeOn(self):
		self.switchToBookList()
		self["filelist"].hide()
		self["key_blue"].hide()

	def keyNumberGlobal(self, number):
		# Cancel Timeout
		self.qs_timer.stop()

		# See if another key was pressed before
		if number != self.lastKey:
			# Reset lastKey again so NumericalTextInput triggers its keychange
			self.nextKey()

			# Try to select what was typed
			self.selectByStart()

			# Increment position
			self.curr_pos += 1

		# Get char and append to text
		char = self.getKey(number)
		self.quickselect = self.quickselect[:self.curr_pos] + unicode(char)

		# Start Timeout
		self.qs_timer_type = 0
		self.qs_timer.start(1000, 1)

	def selectByStart(self):
		# Don't do anything on initial call
		if not self.quickselect:
			return

		# Don't select if no dir
		if self["filelist"].getCurrentDirectory():
			# TODO: implement proper method in Components.FileList
			files = self["filelist"].getFileList()

			# Initialize index
			idx = 0

			# We select by filename which is absolute
			lookfor = self["filelist"].getCurrentDirectory() + self.quickselect

			# Select file starting with generated text
			for file in files:
				if file[0][0] and file[0][0].lower().startswith(lookfor):
					self["filelist"].instance.moveSelectionTo(idx)
					break
				idx += 1

	def timeout(self, force=False):
		# Timeout Key
		if not force and self.qs_timer_type == 0:
			# Try to select what was typed
			self.selectByStart()

			# Reset Key
			self.lastKey = -1

			# Change type
			self.qs_timer_type = 1

			# Start timeout again
			self.qs_timer.start(1000, 1)
		# Timeout Quickselect
		else:
			# Eventually stop Timer
			self.qs_timer.stop()

			# Invalidate
			self.lastKey = -1
			self.curr_pos = -1
			self.quickselect = ""

	def __repr__(self):
		return str(type(self)) + "(" + self.text + ")"

def MovieLocationBox(session, text, dir, minFree=None):
	return LocationBox(session, text=text, currDir=dir, bookmarks=config.movielist.videodirs, autoAdd=True, editDir=True, inhibitDirs=defaultInhibitDirs, minFree=minFree, useAliases=True)

class TimeshiftLocationBox(LocationBox):
	def __init__(self, session):
		LocationBox.__init__(
				self,
				session,
				text = _("Where to save temporary timeshift recordings?"),
				currDir = config.usage.timeshift_path.value,
				bookmarks = config.usage.allowed_timeshift_paths,
				autoAdd = True,
				editDir = True,
				inhibitDirs = defaultInhibitDirs,
				minFree = 1024 # the same requirement is hardcoded in servicedvb.cpp
		)
		self.skinName = "LocationBox"

	def cancel(self):
		config.usage.timeshift_path.cancel()
		LocationBox.cancel(self)

	def selectConfirmed(self, ret):
		if ret:
			config.usage.timeshift_path.setValue(self.getPreferredFolder())
			config.usage.timeshift_path.save()
			LocationBox.selectConfirmed(self, ret)


def friendlyMoviePath(path, base=None, trailing=True):
	if path is not None:
		tail = None
		if base:
			base = os.path.normpath(base)
			head, tail = os.path.split(os.path.normpath(path))
			if head == base:
				if trailing and path.endswith('/'):
					tail += '/'
		if config.misc.location_aliases.value:
			llen = 0
			apath = path
			alias_loc = None
			for loc, alias in location_aliases.iteritems():
				loc = loc.rstrip('/')
				if path.startswith(loc) and (len(path) == len(loc) or path[len(loc)] == '/'):
					if len(loc) > llen:
						llen = len(loc)
						apath = alias + path[llen:]
						alias_loc = loc
			if tail and alias_loc == base:
				return tail
			path = apath
		if not trailing:
			return path.rstrip('/') or '/'
	return path
