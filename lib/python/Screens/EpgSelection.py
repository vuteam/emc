from time import localtime, time, strftime, mktime
from calendar import timegm

from enigma import eServiceReference, eTimer, eServiceCenter, ePoint

from Screen import Screen
from Screens.HelpMenu import HelpableScreen
from Components.ActionMap import HelpableActionMap, HelpableNumberActionMap
from Components.Button import Button
from Components.config import config, configfile, ConfigClock
from Components.EpgList import EPGList, EPGBouquetList, TimelineText, EPG_TYPE_SINGLE, EPG_TYPE_SIMILAR, EPG_TYPE_MULTI, EPG_TYPE_ENHANCED, EPG_TYPE_INFOBAR, EPG_TYPE_INFOBARGRAPH, EPG_TYPE_GRAPH, MAX_TIMELINES
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.Sources.ServiceEvent import ServiceEvent
from Components.Sources.Event import Event
from Components.TimerSanityCheck import TimerSanityCheck
from Components.UsageConfig import preferredTimerPath
from Screens.TimerEdit import TimerSanityConflict
from Screens.EventView import EventViewEPGSelect, EventViewSimple
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Screens.PictureInPicture import PictureInPicture
from Screens.Setup import Setup
from TimeDateInput import TimeDateInput
from RecordTimer import RecordTimerEntry, parseEvent, AFTEREVENT
from TimerEntry import TimerEntry, InstantRecordTimerEntry
from ServiceReference import ServiceReference
from Tools.HardwareInfo import HardwareInfo

mepg_config_initialized = False
# PiPServiceRelation installed?
try:
	from Plugins.SystemPlugins.PiPServiceRelation.plugin import getRelationDict
	plugin_PiPServiceRelation_installed = True
except:
	plugin_PiPServiceRelation_installed = False

def calculateEpgStartTime(snapToConfig, prevTimePeriodConfig, visibleHistoryConfig):
	"""
	Calculates the EPG start time (i.e. the time at the very left edge of the EPG) for the graphical EPGs.

	:param snapToConfig: the config object containing the snap resolution, otherwise called "base time" or "roundto" (in minutes)
	:param prevTimePeriodConfig: the config object containing the total time shown on the EPG (in minutes)
	:param visibleHistoryConfig: the config object containing the amount of history to show (as a percentage)
	:return: the start time for the EPG, in seconds
	"""

	snapToSecs = int(snapToConfig.value) * 60
	prevTimePeriodSecs = int(prevTimePeriodConfig.value) * 60
	visibleHistoryPercent = int(visibleHistoryConfig.value) / 100.0
	epgHistorySecs = int(config.epg.histminutes.value) * 60

	# Calculating snap offsets (15m, 30m or 60m) using the modulo operator on time() (which returns a value in UTC) works for most
	# timezones, as their offsets from UTC are all a multiple of 60 minutes. However, some timezones align on a different boundary
	# (e.g. South Australia at +0930), so using modulo 60 on the UTC time will result in an incorrect offset (potentially out by 30 minutes).
	# To solve this problem, we use localtime(), and then convert the result back to UTC later.
	localNow = timegm(localtime())

	if epgHistorySecs > 0 and visibleHistoryPercent > 0:
		maxStartOffset = epgHistorySecs + (localNow % snapToSecs)

		# By moving the start time back, we scroll the EPG to the right, revealing historic EPG data. This also effectively
		# positions the "current time" marker at the percentage offset (e.g. 50% places the marker in the middle of the EPG).
		startTime = localNow - min(int(prevTimePeriodSecs * visibleHistoryPercent), maxStartOffset)

		# Now we account for the configured snap resolution. We try to keep the "current time" marker as close to
		# its current position as possible (to keep the required amount of history visible) by either rounding up or down
		# depending on which snap-to value is closest
		snapOffset = startTime % snapToSecs
		if snapOffset < snapToSecs / 2:
			# We're just ahead of the closest snap point, so round down
			startTime = startTime - snapOffset
		else:
			# We're just behind the closest snap point, so round up
			startTime = startTime + snapToSecs - snapOffset
	else:
		# Not showing any history, so just round down to the nearest snap point
		startTime = localNow - (localNow % snapToSecs)

	# In order to return the correct UTC time, just work out how much we adjusted the time and do the same to time()
	return time() - (localNow - startTime)

def offsetBySnapTime(timeToOffset, snapToConfig):
	"""
	Takes a timestamp (seconds since epoch) and subtracts an offset to align it with the given snap resolution, taking into
	account the local timezone.

	:param timeToOffset: a timestamp (seconds since epoch)
	:param snapToConfig: the config object containing the snap resolution, otherwise called "base time" or "roundto" (in minutes)
	:return: a timestamp rounded to the given snap resolution
	"""

	snapToSecs = int(snapToConfig.value) * 60
	localTimeStruct = localtime(timeToOffset)
	localMinsSecs = localTimeStruct.tm_min * 60 + localTimeStruct.tm_sec

	return timeToOffset - (localMinsSecs % snapToSecs)

class EPGSelection(Screen, HelpableScreen):
	EMPTY = 0
	ADD_TIMER = 1
	REMOVE_TIMER = 2
	ZAP = 1

	def __init__(self, session, service=None, zapFunc=None, eventid=None, bouquetChangeCB=None, serviceChangeCB=None, EPGtype=None, StartBouquet=None, StartRef=None, bouquets=None):
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		self.zapFunc = zapFunc
		self.serviceChangeCB = serviceChangeCB
		self.bouquets = bouquets
		graphic = False
		if EPGtype == 'single':
			self.type = EPG_TYPE_SINGLE
		elif EPGtype == 'infobar':
			self.type = EPG_TYPE_INFOBAR
		elif EPGtype == 'enhanced':
			self.type = EPG_TYPE_ENHANCED
		elif EPGtype == 'graph':
			self.type = EPG_TYPE_GRAPH
			if config.epgselection.graph_type_mode.value == "graphics":
				graphic = True
		elif EPGtype == 'infobargraph':
			self.type = EPG_TYPE_INFOBARGRAPH
			if config.epgselection.infobar_type_mode.value == "graphics":
				graphic = True
		elif EPGtype == 'multi':
			self.type = EPG_TYPE_MULTI
		else:
			self.type = EPG_TYPE_SIMILAR
		if not self.type == EPG_TYPE_SINGLE:
			self.StartBouquet = StartBouquet
			self.StartRef = StartRef
			self.servicelist = None
		self.ChoiceBoxDialog = None
		self.ask_time = -1
		self.closeRecursive = False
		self.eventviewDialog = None
		self.eventviewWasShown = False
		self.currch = None
		self.session.pipshown = False
		if plugin_PiPServiceRelation_installed:
			self.pipServiceRelation = getRelationDict()
		else:
			self.pipServiceRelation = {}
		self.zapnumberstarted = False
		if self.type in (EPG_TYPE_ENHANCED, EPG_TYPE_INFOBAR):
			self.NumberZapTimer = eTimer()
			self.NumberZapTimer.callback.append(self.doNumberZap)
			self.NumberZapField = None
			self["number"] = Label()
			self["number"].hide()
		self.CurrBouquet = None
		self.CurrService = None
		self['Service'] = ServiceEvent()
		self['Event'] = Event()
		self.key_green_choice = self.EMPTY
		self['key_red'] = Button(_('IMDb search'))
		self['key_green'] = Button()
		self['key_yellow'] = Button(_('EPG search'))
		self['key_blue'] = Button(_('Add Autotimer'))
		self['dialogactions'] = HelpableActionMap(self, 'WizardActions', {
			'back': (self.closeChoiceBoxDialog, _('Close menu')),
		}, prio=-1, description=_('Close menu'))
		self['dialogactions'].csel = self
		self["dialogactions"].setEnabled(False)

		okmap = {
			'cancel': (self.closeScreen, _('Exit EPG')),
			'OK': (self.OK, self._helpOK),
			'OKLong': (self.OKLong, self._helpOKLong)
		}
		if self.type != EPG_TYPE_SINGLE:
			okmap.update({
				'media': (self.closeToMedia, _('Exit, show movie list')),
				'timer': (self.closeToTimer, _('Exit, show timer list'))
			})
		self['okactions'] = HelpableActionMap(self, ['OkCancelActions', 'TimerMediaEPGActions'],
			okmap, prio=-1, description=_('Channel zap and exit'))
		self['okactions'].csel = self
		self['colouractions'] = HelpableActionMap(self, 'ColorActions', {
			'red': (self.redButtonPressed, _('IMDB search for current event')),
			'redlong': (self.redButtonPressedLong, _('Toggle EPG sort order: time/alphabetical') if self.type in (EPG_TYPE_SINGLE, EPG_TYPE_ENHANCED, EPG_TYPE_INFOBAR) else None),
			'green': (self.greenButtonPressed, _('Add/remove/modify timer for selected event')),
			'greenlong': (self.greenButtonPressedLong, _('Show timer list')),
			'yellow': (self.yellowButtonPressed, _('Search for similar events')),
			'blue': (self.blueButtonPressed, _('Add an Autotimer for selected event')),
			'bluelong': (self.blueButtonPressedLong, _('Show Autotimer list'))
		}, prio=-1, description=_('Event information and timers'))
		self['colouractions'].csel = self
		self['recordingactions'] = HelpableActionMap(self, 'InfobarInstantRecord', {
			'ShortRecord': (self.recButtonPressed, _('Add a record timer or AutoTimer for selected event')),
			'LongRecord': (self.recButtonPressedLong, _('Add a zap timer for selected event'))
		}, prio=-1, description=_('Add/delete/modify timer'))
		self['recordingactions'].csel = self
		if self.type == EPG_TYPE_SIMILAR:
			self.currentService = service
			self.eventid = eventid
			self['epgactions'] = HelpableActionMap(self, 'EPGSelectActions', {
				'info': (self.Info, self._helpInfo),
				'infolong': (self.InfoLong, self._helpInfoLong),
				'timerlong': (self.showAutoTimerList, _('Show Autotimer list')),
				'menu': (self.createSetup, _('Setup menu'))
			}, prio=-1, description=_('Detailed event information and setup'))
			self['epgactions'].csel = self
		elif self.type == EPG_TYPE_SINGLE:
			self.currentService = ServiceReference(service)
			self['epgactions'] = HelpableActionMap(self, 'EPGSelectActions', {
				'info': (self.Info, self._helpInfo),
				'epg': (self.Info, self._helpInfo),
				'timer': (self.showTimerList, _('Show timer list')),
				'timerlong': (self.showAutoTimerList, _('Show Autotimer list')),
				'menu': (self.createSetup, _('Setup menu'))
			}, prio=-1, description=_('Detailed event information and setup'))
			self['epgactions'].csel = self
			self['epgcursoractions'] = HelpableActionMap(self, 'DirectionActions', {
				'left': (self.prevPage, _('Move up a page')),
				'right': (self.nextPage, _('Move down a page')),
				'up': (self.moveUp, _('Go to previous event')),
				'down': (self.moveDown, _('Go to next event'))
			}, prio=-1, description=_('Navigation'))
			self['epgcursoractions'].csel = self
		elif self.type in (EPG_TYPE_ENHANCED, EPG_TYPE_INFOBAR):
			if self.type == EPG_TYPE_INFOBAR:
				self.skinName = 'QuickEPG'
				self['epgactions'] = HelpableActionMap(self, 'EPGSelectActions', {
					'nextBouquet': (self.nextBouquet, _('Go to next bouquet')),
					'prevBouquet': (self.prevBouquet, _('Go to previous bouquet')),
					'nextService': (self.nextPage, _('Move down a page')),
					'prevService': (self.prevPage, _('Move up a page')),
					'input_date_time': (self.enterDateTime, _('Go to specific date/time')),
					'epg': (self.epgButtonPressed, _('Open single channel EPG')),
					'info': (self.Info, self._helpInfo),
					'infolong': (self.InfoLong, self._helpInfoLong),
					'timerlong': (self.showAutoTimerList, _('Show Autotimer list')),
					'menu': (self.createSetup, _('Setup menu'))
				}, prio=-1, description=_('Bouquets and services, information and setup'))
				self['epgactions'].csel = self
				self['epgcursoractions'] = HelpableActionMap(self, 'DirectionActions', {
					'left': (self.prevService, _('Go to previous channel')),
					'right': (self.nextService, _('Go to next channel')),
					'up': (self.moveUp, _('Go to previous channel')),
					'down': (self.moveDown, _('Go to next channel'))
				}, prio=-1, description=_('Navigation'))
				self['epgcursoractions'].csel = self
			elif self.type == EPG_TYPE_ENHANCED:
				self['epgcursoractions'] = HelpableActionMap(self, ['DirectionActions', 'EPGSelectActions'], {
					'left': (self.prevPage, _('Move up a page')),
					'right': (self.nextPage, _('Move down a page')),
					'up': (self.moveUp, _('Go to previous event')),
					'down': (self.moveDown, _('Go to next event')),
					'rewind': (self.jumpNow, _('Jump to now')),
					'play': (self.jumpNextDay, _('Jump forward a day')),
					'playlong': (self.jumpPrevDay, _('Jump back a day')),
					'fastforward': (self.jumpNextWeek, _('Jump forward a week')),
					'fastforwardlong': (self.jumpLastWeek, _('Jump back a week'))
				}, prio=-1, description=_('Navigation'))
				self['epgcursoractions'].csel = self
				self['epgactions'] = HelpableActionMap(self, 'EPGSelectActions', {
					'nextBouquet': (self.nextBouquet, _('Go to next bouquet')),
					'prevBouquet': (self.prevBouquet, _('Go to previous bouquet')),
					'nextService': (self.nextService, _('Go to next channel')),
					'prevService': (self.prevService, _('Go to previous channel')),
					'info': (self.Info, self._helpInfo),
					'infolong': (self.InfoLong, self._helpInfoLong),
					'timerlong': (self.showAutoTimerList, _('Show Autotimer list')),
					'menu': (self.createSetup, _('Setup menu'))
				}, prio=-1, description=_('Bouquets and services, information and setup'))
				self['epgactions'].csel = self
			numHelp = _('Enter number(s) to jump to channel')
			self['input_actions'] = HelpableNumberActionMap(self, ['NumberActions', 'BackspaceActions'], {
				'0': (self.keyNumberGlobal, _('Jump to original channel')),
				'1': (self.keyNumberGlobal, numHelp),
				'2': (self.keyNumberGlobal, numHelp),
				'3': (self.keyNumberGlobal, numHelp),
				'4': (self.keyNumberGlobal, numHelp),
				'5': (self.keyNumberGlobal, numHelp),
				'6': (self.keyNumberGlobal, numHelp),
				'7': (self.keyNumberGlobal, numHelp),
				'8': (self.keyNumberGlobal, numHelp),
				'9': (self.keyNumberGlobal, numHelp),
				'deleteBackward': (self.doNumberZapBack, _('Backspace channel number'))
			}, prio=-1, description=_('Zap by channel number'))
			self['input_actions'].csel = self
			self.list = []
			self.servicelist = service
			self.currentService = self.session.nav.getCurrentlyPlayingServiceOrGroup()
		elif self.type in (EPG_TYPE_GRAPH, EPG_TYPE_INFOBARGRAPH):
			if self.type == EPG_TYPE_GRAPH:
				if not config.epgselection.graph_pig.value:
					self.skinName = 'GraphicalEPG'
				else:
					self.skinName = 'GraphicalEPGPIG'
			elif self.type == EPG_TYPE_INFOBARGRAPH:
				self.skinName = 'GraphicalInfoBarEPG'
			if self.type == EPG_TYPE_GRAPH:
				self.ask_time = calculateEpgStartTime(config.epgselection.graph_roundto, config.epgselection.graph_prevtimeperiod, config.epgselection.graph_visiblehistory)
			elif self.type == EPG_TYPE_INFOBARGRAPH:
				self.ask_time = calculateEpgStartTime(config.epgselection.infobar_roundto, config.epgselection.infobar_prevtimeperiod, config.epgselection.infobar_visiblehistory)
			self.closeRecursive = False
			self.bouquetlist_active = False
			self['bouquetlist'] = EPGBouquetList(graphic=graphic)
			self['bouquetlist'].hide()
			self['timeline_text'] = TimelineText(type=self.type, graphic=graphic)
			self['Event'] = Event()
			self.time_lines = []
			for x in range(0, MAX_TIMELINES):
				pm = Pixmap()
				self.time_lines.append(pm)
				self['timeline%d' % x] = pm

			self['timeline_now'] = Pixmap()
			self.updateTimelineTimer = eTimer()
			self.updateTimelineTimer.callback.append(self.moveTimeLines)
			self.updateTimelineTimer.start(60000)
			self['bouquetokactions'] = HelpableActionMap(self, 'OkCancelActions', {
				'cancel': (self.BouquetlistHide, _('Close bouquet list.')),
				'OK': (self.BouquetOK, _('Change to bouquet')),
			}, prio=-1, description=_('Bouquet selection'))
			self['bouquetokactions'].csel = self
			self["bouquetokactions"].setEnabled(False)

			self['bouquetcursoractions'] = HelpableActionMap(self, 'DirectionActions', {
				'left': (self.moveBouquetPageUp, _('Page up in bouquet list')),
				'right': (self.moveBouquetPageDown, _('Page down in bouquet list')),
				'up': (self.moveBouquetUp, _('Move up bouquet list')),
				'down': (self.moveBouquetDown, _('Move down bouquet list'))
			}, prio=-1, description=_('Navigation'))
			self['bouquetcursoractions'].csel = self
			self["bouquetcursoractions"].setEnabled(False)

			self['epgcursoractions'] = HelpableActionMap(self, 'DirectionActions', {
				'left': (self.leftPressed, _('Go to previous event')),
				'right': (self.rightPressed, _('Go to next event')),
				'up': (self.moveUp, _('Go to previous channel')),
				'down': (self.moveDown, _('Go to next channel'))

			}, prio=-1, description=_('Navigation'))
			self['epgcursoractions'].csel = self

			self['epgactions'] = HelpableActionMap(self, 'EPGSelectActions', {
				'nextService': (self.nextService, _('Jump forward 24 hours')),
				'prevService': (self.prevService, _('Jump back 24 hours')),
				'nextBouquet': (self.nextBouquet, _('Go to next bouquet')),
				'prevBouquet': (self.prevBouquet, _('Go to previous bouquet')),
				'input_date_time': (self.enterDateTime, _('Go to specific date/time')),
				'epg': (self.epgButtonPressed, _("Open single channel EPG")),
				'info': (self.Info, self._helpInfo),
				'infolong': (self.InfoLong, self._helpInfoLong),
				'tv': (self.Bouquetlist, _('Toggle between bouquet/EPG lists')),
				'tvlong': (self.togglePIG, _('Toggle picture in graphics')),
				'timerlong': (self.showAutoTimerList, _('Show Autotimer list')),
				'menu': (self.createSetup, _('Setup menu'))
			}, prio=-1, description=_('Bouquets and services, information and setup'))
			self['epgactions'].csel = self

			self['input_actions'] = HelpableNumberActionMap(self, 'NumberActions', {
				'1': (self.keyNumberGlobal, _('Reduce time scale')),
				'2': (self.keyNumberGlobal, _('Page up')),
				'3': (self.keyNumberGlobal, _('Increase time scale')),
				'4': (self.keyNumberGlobal, _('Page left')),
				'5': (self.keyNumberGlobal, _('Jump to current time')),
				'6': (self.keyNumberGlobal, _('Page right')),
				'7': (self.keyNumberGlobal, _('No. of items toggle (increase/decrease)') if self.type == EPG_TYPE_GRAPH else None),
				'8': (self.keyNumberGlobal, _('Page down')),
				'9': (self.keyNumberGlobal, _('Jump to prime time')),
				'0': (self.keyNumberGlobal, _('Move to home of list'))
			}, prio=-1, description=_('Navigation and display control'))
			self['input_actions'].csel = self

		elif self.type == EPG_TYPE_MULTI:
			self.skinName = 'EPGSelectionMulti'
			self['bouquetlist'] = EPGBouquetList(graphic=graphic)
			self['bouquetlist'].hide()
			self['now_button'] = Pixmap()
			self['next_button'] = Pixmap()
			self['more_button'] = Pixmap()
			self['now_button_sel'] = Pixmap()
			self['next_button_sel'] = Pixmap()
			self['more_button_sel'] = Pixmap()
			self['now_text'] = Label()
			self['next_text'] = Label()
			self['more_text'] = Label()
			self['date'] = Label()
			self.bouquetlist_active = False
			self['bouquetokactions'] = HelpableActionMap(self, 'OkCancelActions', {
				'OK': (self.BouquetOK, _('Bouquet selection')),
			}, prio=-1, description=_('Change bouquet'))
			self['bouquetokactions'].csel = self
			self["bouquetokactions"].setEnabled(False)

			self['bouquetcursoractions'] = HelpableActionMap(self, 'DirectionActions', {
				'left': (self.moveBouquetPageUp, _('Page up in bouquet list')),
				'right': (self.moveBouquetPageDown, _('Page down in bouquet list')),
				'up': (self.moveBouquetUp, _('Move up bouquet list')),
				'down': (self.moveBouquetDown, _('Move down bouquet list'))
			}, prio=-1, description=_('Navigation'))
			self['bouquetcursoractions'].csel = self
			self['bouquetcursoractions'].setEnabled(False)

			self['epgcursoractions'] = HelpableActionMap(self, 'DirectionActions', {
				'chminus': (self.leftPressed, _('Go to previous event')),
				'chplus': (self.rightPressed, _('Go to next event')),
				'up': (self.moveUp, _('Go to previous channel')),
				'down': (self.moveDown, _('Go to next channel'))
			}, prio=-1, description=_('Navigation'))
			self['epgcursoractions'].csel = self

			self['epgactions'] = HelpableActionMap(self, 'EPGSelectActions', {
				# 'nextService': (self.nextPage, _('Move down a page')),
				# 'prevService': (self.prevPage, _('Move up a page')),
				'nextBouquet': (self.nextBouquet, _('Go to next bouquet')),
				'prevBouquet': (self.prevBouquet, _('Go to previous bouquet')),
				'input_date_time': (self.enterDateTime, _('Go to specific date/time')),
				'epg': (self.epgButtonPressed, _("Open single channel EPG")),
				'info': (self.Info, self._helpInfo),
				'infolong': (self.InfoLong, self._helpInfoLong),
				'tv': (self.Bouquetlist, _('Toggle between bouquet/EPG lists')),
				'timerlong': (self.showAutoTimerList, _('Show Autotimer list')),
				'menu': (self.createSetup, _('Setup menu'))
			}, prio=-1, description=_('Bouquets and services, information and setup'))
			self['epgactions'].csel = self
		if self.type == EPG_TYPE_GRAPH:
			time_epoch = int(config.epgselection.graph_prevtimeperiod.value)
		elif self.type == EPG_TYPE_INFOBARGRAPH:
			time_epoch = int(config.epgselection.infobar_prevtimeperiod.value)
		else:
			time_epoch = None
		self['list'] = EPGList(type=self.type, selChangedCB=self.onSelectionChanged, timer=session.nav.RecordTimer, time_epoch=time_epoch, overjump_empty=config.epgselection.overjump.value, graphic=graphic)
		self.refreshTimer = eTimer()
		self.refreshTimer.timeout.get().append(self.refreshlist)
		self.onLayoutFinish.append(self.onCreate)

	def createSetup(self):
		self.closeEventViewDialog()
		key = None
		if self.type == EPG_TYPE_SINGLE:
			key = 'epgsingle'
		elif self.type == EPG_TYPE_MULTI:
			key = 'epgmulti'
		elif self.type == EPG_TYPE_ENHANCED:
			key = 'epgenhanced'
		elif self.type == EPG_TYPE_INFOBAR:
			key = 'epginfobar'
		elif self.type == EPG_TYPE_GRAPH:
			key = 'epggraphical'
		elif self.type == EPG_TYPE_INFOBARGRAPH:
			key = 'epginfobargraphical'
		if key:
			self.session.openWithCallback(self.onSetupClose, Setup, key)

	def onSetupClose(self, test=None):
		if self.type in (EPG_TYPE_GRAPH, EPG_TYPE_INFOBARGRAPH):
			if self.type == EPG_TYPE_GRAPH:
				self.close('reopengraph')
			elif self.type == EPG_TYPE_INFOBARGRAPH:
				self.close('reopeninfobargraph')
		elif self.type == EPG_TYPE_INFOBAR:
				self.close('reopeninfobar')
		else:
			if  self.type in (EPG_TYPE_SINGLE, EPG_TYPE_ENHANCED, EPG_TYPE_INFOBAR):
				self['list'].sortSingleEPG(int(config.epgselection.sort.value))
			self['list'].setFontsize()
			self['list'].setItemsPerPage()
			self['list'].recalcEntrySize()

	def togglePIG(self):
		if not config.epgselection.graph_pig.value:
			config.epgselection.graph_pig.setValue(True)
		else:
			config.epgselection.graph_pig.setValue(False)
		config.epgselection.graph_pig.save()
		configfile.save()
		self.close('reopengraph')

	def getBouquetServices(self, bouquet):
		services = []
		servicelist = eServiceCenter.getInstance().list(bouquet)
		if servicelist is not None:
			while True:
				service = servicelist.getNext()
				if not service.valid():  # check if end of list
					break
				if service.flags & (eServiceReference.isDirectory | eServiceReference.isMarker):  # ignore non playable services
					continue
				services.append(ServiceReference(service))
		return services

	def onCreate(self):
		serviceref = self.session.nav.getCurrentlyPlayingServiceOrGroup()
		title = None
		self['list'].recalcEntrySize()
		self.BouquetRoot = False
		if self.type in (EPG_TYPE_GRAPH, EPG_TYPE_INFOBARGRAPH):
			self.getCurrentCursorLocation = None
			if self.StartBouquet.toString().startswith('1:7:0'):
				self.BouquetRoot = True
			self.services = self.getBouquetServices(self.StartBouquet)
			if self.type == EPG_TYPE_GRAPH:
				self['list'].setShowServiceMode(config.epgselection.graph_servicetitle_mode.value)
			elif self.type == EPG_TYPE_INFOBARGRAPH:
				self['list'].setShowServiceMode(config.epgselection.infobar_servicetitle_mode.value)
			self['list'].fillGraphEPG(self.services, self.ask_time)
			self['list'].moveToService(serviceref)
			self['list'].setCurrentlyPlaying(serviceref)
			self['bouquetlist'].recalcEntrySize()
			self['bouquetlist'].fillBouquetList(self.bouquets)
			self['bouquetlist'].moveToService(self.StartBouquet)
			self['bouquetlist'].setCurrentBouquet(self.StartBouquet)
			self.setTitle(self['bouquetlist'].getCurrentBouquet())
			if self.type == EPG_TYPE_GRAPH:
				self.moveTimeLines()
				if config.epgselection.graph_channel1.value:
					self['list'].instance.moveSelectionTo(0)
			elif self.type == EPG_TYPE_INFOBARGRAPH:
				self.moveTimeLines()
		elif self.type == EPG_TYPE_MULTI:
			self['bouquetlist'].recalcEntrySize()
			self['bouquetlist'].fillBouquetList(self.bouquets)
			self['bouquetlist'].moveToService(self.StartBouquet)
			self['bouquetlist'].fillBouquetList(self.bouquets)
			self.services = self.getBouquetServices(self.StartBouquet)
			self['list'].fillMultiEPG(self.services, self.ask_time)
			self['list'].setCurrentlyPlaying(serviceref)
			self.setTitle(self['bouquetlist'].getCurrentBouquet())
			self['list'].moveToService(self.session.nav.getCurrentlyPlayingServiceOrGroup())
		elif self.type in (EPG_TYPE_SINGLE, EPG_TYPE_ENHANCED, EPG_TYPE_INFOBAR):
			if self.type == EPG_TYPE_SINGLE:
				service = self.currentService
			elif self.type in (EPG_TYPE_ENHANCED, EPG_TYPE_INFOBAR):
				service = ServiceReference(self.servicelist.getCurrentSelection())
				title = ServiceReference(self.servicelist.getRoot()).getServiceName()
			self['Service'].newService(service.ref)
			if title:
				title = title + ' - ' + service.getServiceName()
			else:
				title = service.getServiceName()
			self.setTitle(title)
			self['list'].fillSingleEPG(service)
			self['list'].sortSingleEPG(int(config.epgselection.sort.value))
		else:
			self['list'].fillSimilarList(self.currentService, self.eventid)

	def refreshlist(self):
		self.refreshTimer.stop()
		if self.type in(EPG_TYPE_GRAPH, EPG_TYPE_INFOBARGRAPH):
			if self.getCurrentCursorLocation:
				self.ask_time = self.getCurrentCursorLocation
				self.getCurrentCursorLocation = None
			self['list'].fillGraphEPG(None)
			self.moveTimeLines()
		elif self.type == EPG_TYPE_MULTI:
			self['list'].fillMultiEPG(self.services, self.ask_time)
		elif self.type in (EPG_TYPE_SINGLE, EPG_TYPE_ENHANCED, EPG_TYPE_INFOBAR):
			try:
				if self.type == EPG_TYPE_SINGLE:
					service = self.currentService
				elif self.type in (EPG_TYPE_ENHANCED, EPG_TYPE_INFOBAR):
					service = ServiceReference(self.servicelist.getCurrentSelection())
				index = self['list'].getCurrentIndex()
				event = self['list'].getCurrent()[0]
				event = event and event.getEventId()
				self['list'].fillSingleEPG(service)
				self['list'].sortSingleEPG(int(config.epgselection.sort.value))
				self['list'].setCurrentIndex(index)
				if index > 0:
					ev = self['list'].getCurrent()[0]
					ev = ev and ev.getEventId()
					if event != ev:
						self['list'].setCurrentIndex(index - 1)
			except:
				pass

	def moveUp(self):
		self['list'].moveTo(self['list'].instance.moveUp)

	def moveDown(self):
		self['list'].moveTo(self['list'].instance.moveDown)

	def updEvent(self, dir, visible=True):
		ret = self['list'].selEntry(dir, visible)
		if ret:
			self.moveTimeLines(True)

	def nextPage(self):
		self['list'].moveTo(self['list'].instance.pageDown)

	def prevPage(self):
		self['list'].moveTo(self['list'].instance.pageUp)

	def toTop(self):
		self['list'].moveTo(self['list'].instance.moveTop)

	def toEnd(self):
		self['list'].moveTo(self['list'].instance.moveEnd)

	def leftPressed(self):
		if self.type == EPG_TYPE_MULTI:
			self['list'].updateMultiEPG(-1)
		else:
			self.updEvent(-1)

	def rightPressed(self):
		if self.type == EPG_TYPE_MULTI:
			self['list'].updateMultiEPG(1)
		else:
			self.updEvent(+1)

	def Bouquetlist(self):
		if not self.bouquetlist_active:
			self.BouquetlistShow()
		else:
			self.BouquetlistHide()

	def BouquetlistShow(self):
		self.curindex = self['bouquetlist'].l.getCurrentSelectionIndex()
		self["epgcursoractions"].setEnabled(False)
		self["okactions"].setEnabled(False)
		self['bouquetlist'].show()
		self["bouquetokactions"].setEnabled(True)
		self["bouquetcursoractions"].setEnabled(True)
		self.bouquetlist_active = True

	def BouquetlistHide(self, cancel=True):
		self["bouquetokactions"].setEnabled(False)
		self["bouquetcursoractions"].setEnabled(False)
		self['bouquetlist'].hide()
		if cancel:
			self['bouquetlist'].setCurrentIndex(self.curindex)
		self["okactions"].setEnabled(True)
		self["epgcursoractions"].setEnabled(True)
		self.bouquetlist_active = False

	def getCurrentBouquet(self):
		if self.BouquetRoot:
			return self.StartBouquet
		elif 'bouquetlist' in self:
			cur = self["bouquetlist"].l.getCurrentSelection()
			return cur and cur[1]
		else:
			return self.servicelist.getRoot()

	def BouquetOK(self):
		self.BouquetRoot = False
		self.services = self.getBouquetServices(self.getCurrentBouquet())
		if self.type in (EPG_TYPE_GRAPH, EPG_TYPE_INFOBARGRAPH):
			if self.type == EPG_TYPE_GRAPH:
				self.ask_time = calculateEpgStartTime(config.epgselection.graph_roundto, config.epgselection.graph_prevtimeperiod, config.epgselection.graph_visiblehistory)
			elif self.type == EPG_TYPE_INFOBARGRAPH:
				self.ask_time = calculateEpgStartTime(config.epgselection.infobar_roundto, config.epgselection.infobar_prevtimeperiod, config.epgselection.infobar_visiblehistory)
			self['list'].fillGraphEPG(self.services, self.ask_time)
			self.moveTimeLines(True)
		elif self.type == EPG_TYPE_MULTI:
			self['list'].fillMultiEPG(self.services, self.ask_time)
		self['list'].instance.moveSelectionTo(0)
		self.setTitle(self['bouquetlist'].getCurrentBouquet())
		self.BouquetlistHide(False)

	def moveBouquetUp(self):
		self['bouquetlist'].moveTo(self['bouquetlist'].instance.moveUp)
		self['bouquetlist'].fillBouquetList(self.bouquets)

	def moveBouquetDown(self):
		self['bouquetlist'].moveTo(self['bouquetlist'].instance.moveDown)
		self['bouquetlist'].fillBouquetList(self.bouquets)

	def moveBouquetPageUp(self):
		self['bouquetlist'].moveTo(self['bouquetlist'].instance.pageUp)
		self['bouquetlist'].fillBouquetList(self.bouquets)

	def moveBouquetPageDown(self):
		self['bouquetlist'].moveTo(self['bouquetlist'].instance.pageDown)
		self['bouquetlist'].fillBouquetList(self.bouquets)

	def nextBouquet(self):
		if self.type in (EPG_TYPE_MULTI, EPG_TYPE_GRAPH, EPG_TYPE_INFOBARGRAPH):
			self.moveBouquetDown()
			self.BouquetOK()
		elif self.type in (EPG_TYPE_ENHANCED, EPG_TYPE_INFOBAR) and config.usage.multibouquet.value:
			self.CurrBouquet = self.servicelist.getCurrentSelection()
			self.CurrService = self.servicelist.getRoot()
			self.servicelist.nextBouquet()
			self.onCreate()

	def prevBouquet(self):
		if self.type in (EPG_TYPE_MULTI, EPG_TYPE_GRAPH, EPG_TYPE_INFOBARGRAPH):
			self.moveBouquetUp()
			self.BouquetOK()
		elif self.type in (EPG_TYPE_ENHANCED, EPG_TYPE_INFOBAR) and config.usage.multibouquet.value:
			if self.zapnumberstarted:
				self.doNumberZapBack()
				return
			self.CurrBouquet = self.servicelist.getCurrentSelection()
			self.CurrService = self.servicelist.getRoot()
			self.servicelist.prevBouquet()
			self.onCreate()

	def nextService(self):
		if self.type in (EPG_TYPE_ENHANCED, EPG_TYPE_INFOBAR):
			self.CurrBouquet = self.servicelist.getCurrentSelection()
			self.CurrService = self.servicelist.getRoot()
			self['list'].instance.moveSelectionTo(0)
			if self.servicelist.inBouquet():
				prev = self.servicelist.getCurrentSelection()
				if prev:
					prev = prev.toString()
					while True:
						if config.usage.quickzap_bouquet_change.value and self.servicelist.atEnd():
							self.servicelist.nextBouquet()
						else:
							self.servicelist.moveDown()
						cur = self.servicelist.getCurrentSelection()
						if not cur or (not (cur.flags & 64)) or cur.toString() == prev:
							break
			else:
				self.servicelist.moveDown()
			if self.isPlayable():
				self.onCreate()
				if not self['list'].getCurrent()[1] and config.epgselection.overjump.value:
					self.nextService()
			else:
				self.nextService()
		elif self.type in (EPG_TYPE_GRAPH, EPG_TYPE_INFOBARGRAPH):
			self.updEvent(+24)
		elif self.serviceChangeCB:
			self.serviceChangeCB(1, self)

	def prevService(self):
		if self.type in (EPG_TYPE_ENHANCED, EPG_TYPE_INFOBAR):
			self.CurrBouquet = self.servicelist.getCurrentSelection()
			self.CurrService = self.servicelist.getRoot()
			self['list'].instance.moveSelectionTo(0)
			if self.servicelist.inBouquet():
				prev = self.servicelist.getCurrentSelection()
				if prev:
					prev = prev.toString()
					while True:
						if config.usage.quickzap_bouquet_change.value:
							if self.servicelist.atBegin():
								self.servicelist.prevBouquet()
						self.servicelist.moveUp()
						cur = self.servicelist.getCurrentSelection()
						if not cur or (not (cur.flags & 64)) or cur.toString() == prev:
							break
			else:
				self.servicelist.moveUp()
			if self.isPlayable():
				self.onCreate()
				if not self['list'].getCurrent()[1] and config.epgselection.overjump.value:
					self.prevService()
			else:
				self.prevService()
		elif self.type in (EPG_TYPE_GRAPH, EPG_TYPE_INFOBARGRAPH):
			self.updEvent(-24)
		elif self.serviceChangeCB:
			self.serviceChangeCB(-1, self)

	def jumpTime(self, reltime=None):
		if not reltime:
			reltime = int(time())
		else:
			cur = self['list'].getCurrent()
			event = cur[0]
			reltime += event.getBeginTime() + 60
		self['list'].moveToTime(reltime)

	def jumpNow(self):
		self.jumpTime()

	def jumpNextDay(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if not InfoBarInstance.LongButtonPressed:
			self.jumpTime(24 * 60 * 60)

	def jumpNextWeek(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if not InfoBarInstance.LongButtonPressed:
			self.jumpTime(7 * 24 * 60 * 60)

	def jumpPrevDay(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if InfoBarInstance.LongButtonPressed:
			self.jumpTime(-24 * 60 * 60)

	def jumpLastWeek(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if InfoBarInstance.LongButtonPressed:
			self.jumpTime(-7 * 24 * 60 * 60)

	def enterDateTime(self):
		global mepg_config_initialized
		if self.type == EPG_TYPE_MULTI:
			if not mepg_config_initialized:
				config.misc.prev_mepg_time = ConfigClock(default=time())
				mepg_config_initialized = True
			self.session.openWithCallback(self.onDateTimeInputClosed, TimeDateInput, config.misc.prev_mepg_time)
		elif self.type == EPG_TYPE_GRAPH:
			self.session.openWithCallback(self.onDateTimeInputClosed, TimeDateInput, config.epgselection.graph_prevtime)
		elif self.type == EPG_TYPE_INFOBARGRAPH:
			self.session.openWithCallback(self.onDateTimeInputClosed, TimeDateInput, config.epgselection.infobar_prevtime)

	def onDateTimeInputClosed(self, ret):
		if len(ret) > 1:
			if ret[0]:
				if self.type == EPG_TYPE_MULTI:
					self.ask_time = ret[1]
					self['list'].fillMultiEPG(self.services, ret[1])
				elif self.type in (EPG_TYPE_GRAPH, EPG_TYPE_INFOBARGRAPH):
					self.ask_time = ret[1]
					if self.type == EPG_TYPE_GRAPH:
						self.ask_time = offsetBySnapTime(self.ask_time, config.epgselection.graph_roundto)
					elif self.type == EPG_TYPE_INFOBARGRAPH:
						self.ask_time = offsetBySnapTime(self.ask_time, config.epgselection.infobar_roundto)
					self['list'].fillGraphEPG(None, self.ask_time)
					self.moveTimeLines(True)
		if self.eventviewDialog and self.type in (EPG_TYPE_INFOBAR, EPG_TYPE_INFOBARGRAPH):
			self.infoKeyPressed(True)

	def infoKeyPressed(self, eventviewopen=False):
		cur = self['list'].getCurrent()
		event = cur[0]
		service = cur[1]
		if event is not None and not self.eventviewDialog and not eventviewopen:
			if self.type != EPG_TYPE_SIMILAR:
				if self.type == EPG_TYPE_INFOBARGRAPH:
					self.eventviewDialog = self.session.instantiateDialog(EventViewSimple, event, service, skin='InfoBarEventView')
					self.eventviewDialog.show()
				else:
					self.session.open(EventViewEPGSelect, event, service, callback=self.eventViewCallback, similarEPGCB=self.openSimilarList)
		elif self.eventviewDialog and not eventviewopen:
			self.eventviewDialog.hide()
			del self.eventviewDialog
			self.eventviewDialog = None
		elif event is not None and self.eventviewDialog and eventviewopen:
			if self.type != EPG_TYPE_SIMILAR:
				if self.type in (EPG_TYPE_INFOBAR, EPG_TYPE_INFOBARGRAPH):
					self.eventviewDialog.hide()
					self.eventviewDialog = self.session.instantiateDialog(EventViewSimple, event, service, skin='InfoBarEventView')
					self.eventviewDialog.show()

	def redButtonPressed(self):
		self.closeEventViewDialog()
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if not InfoBarInstance.LongButtonPressed:
			self.openIMDb()

	def redButtonPressedLong(self):
		self.closeEventViewDialog()
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if InfoBarInstance.LongButtonPressed:
			self.sortEpg()

	def greenButtonPressed(self):
		self.closeEventViewDialog()
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if not InfoBarInstance.LongButtonPressed:
			self.RecordTimerQuestion(True)

	def greenButtonPressedLong(self):
		self.closeEventViewDialog()
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if InfoBarInstance.LongButtonPressed:
			self.showTimerList()

	def yellowButtonPressed(self):
		self.closeEventViewDialog()
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if not InfoBarInstance.LongButtonPressed:
			self.openEPGSearch()

	def blueButtonPressed(self):
		self.closeEventViewDialog()
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if not InfoBarInstance.LongButtonPressed:
			self.addAutoTimer()

	def blueButtonPressedLong(self):
		self.closeEventViewDialog()
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if InfoBarInstance.LongButtonPressed:
			self.showAutoTimerList()

	def openSimilarList(self, eventid, refstr):
		self.session.open(EPGSelection, refstr, None, eventid)

	def setServices(self, services):
		self.services = services
		self.onCreate()

	def setService(self, service):
		self.currentService = service
		self.onCreate()

	def eventViewCallback(self, setEvent, setService, val):
		l = self['list']
		old = l.getCurrent()
		if self.type in (EPG_TYPE_GRAPH, EPG_TYPE_INFOBARGRAPH):
			self.updEvent(val, False)
		elif val == -1:
			self.moveUp()
		elif val == +1:
			self.moveDown()
		cur = l.getCurrent()
		if self.type in (EPG_TYPE_MULTI, EPG_TYPE_GRAPH, EPG_TYPE_INFOBARGRAPH) and cur[0] is None and cur[1].ref != old[1].ref:
			self.eventViewCallback(setEvent, setService, val)
		else:
			setService(cur[1])
			setEvent(cur[0])

	def eventSelected(self):
		self.infoKeyPressed()

	def sortEpg(self):
		if self.type in (EPG_TYPE_SINGLE, EPG_TYPE_ENHANCED, EPG_TYPE_INFOBAR):
			if config.epgselection.sort.value == '0':
				config.epgselection.sort.setValue('1')
			else:
				config.epgselection.sort.setValue('0')
			config.epgselection.sort.save()
			configfile.save()
			self['list'].sortSingleEPG(int(config.epgselection.sort.value))

	def OpenSingleEPG(self):
		event, service = self['list'].getCurrent()
		if service is not None:
			self.session.open(SingleEPG, service.ref)

	def openIMDb(self):
		try:
			from Plugins.Extensions.IMDb.plugin import IMDB
			try:
				cur = self['list'].getCurrent()
				event = cur[0]
				name = event.getEventName()
			except:
				name = ''

			self.session.open(IMDB, name, False)
		except ImportError:
			self.session.open(MessageBox, _('The IMDb plugin is not installed!\nPlease install it.'), type=MessageBox.TYPE_INFO, timeout=10)

	def openEPGSearch(self):
		try:
			from Plugins.Extensions.EPGSearch.EPGSearch import EPGSearch
			try:
				cur = self['list'].getCurrent()
				event = cur[0]
				name = event.getEventName()
			except:
				name = ''
			self.session.open(EPGSearch, name, False)
		except ImportError:
			self.session.open(MessageBox, _('The EPGSearch plugin is not installed!\nPlease install it.'), type=MessageBox.TYPE_INFO, timeout=10)

	def addAutoTimer(self):
		try:
			from Plugins.Extensions.AutoTimer.AutoTimerEditor import addAutotimerFromEvent
			cur = self['list'].getCurrent()
			event = cur[0]
			if not event:
				return
			serviceref = cur[1]
			addAutotimerFromEvent(self.session, evt=event, service=serviceref)
			self.refreshTimer.start(3000)
		except ImportError:
			self.session.open(MessageBox, _('The AutoTimer plugin is not installed!\nPlease install it.'), type=MessageBox.TYPE_INFO, timeout=10)

	def addAutoTimerSilent(self):
		try:
			from Plugins.Extensions.AutoTimer.AutoTimerEditor import addAutotimerFromEventSilent
			cur = self['list'].getCurrent()
			event = cur[0]
			if not event:
				return
			serviceref = cur[1]
			addAutotimerFromEventSilent(self.session, evt=event, service=serviceref)
			self.refreshTimer.start(3000)
		except ImportError:
			self.session.open(MessageBox, _('The Autotimer plugin is not installed!\nPlease install it.'), type=MessageBox.TYPE_INFO, timeout=10)

	def showTimerList(self):
		from Screens.TimerEdit import TimerEditList
		self.session.openWithCallback(self.closeTimerList, TimerEditList)

	def closeTimerList(self, new_screen=None):
		if new_screen == 'media':
			self.closeScreen(new_screen)

	def showAutoTimerList(self):
		global autopoller
		global autotimer
		try:
			from Plugins.Extensions.AutoTimer.AutoTimer import AutoTimer
			from Plugins.Extensions.AutoTimer.AutoPoller import AutoPoller
			autopoller = AutoPoller()
			autotimer = AutoTimer()
			try:
				autotimer.readXml()
			except SyntaxError as se:
				self.session.open(MessageBox, _('Your config file is not well formed:\n%s') % str(se), type=MessageBox.TYPE_ERROR, timeout=10)
				return

			if autopoller is not None:
				autopoller.stop()
			from Plugins.Extensions.AutoTimer.AutoTimerOverview import AutoTimerOverview
			self.session.openWithCallback(self.editCallback, AutoTimerOverview, autotimer)
		except ImportError:
			self.session.open(MessageBox, _('The Autotimer plugin is not installed!\nPlease install it.'), type=MessageBox.TYPE_INFO, timeout=10)

	def editCallback(self, session):
		global autopoller
		global autotimer
		if session is not None:
			autotimer.writeXml()
			autotimer.parseEPG()
		if config.plugins.autotimer.autopoll.value:
			if autopoller is None:
				from Plugins.Extensions.AutoTimer.AutoPoller import AutoPoller
				autopoller = AutoPoller()
			autopoller.start()
		else:
			autopoller = None
			autotimer = None

	def timerAdd(self):
		self.RecordTimerQuestion(True)

	def editTimer(self, timer):
		self.session.openWithCallback(self.finishedEdit, TimerEntry, timer)

	def finishedEdit(self, answer):
		if answer[0]:
			entry = answer[1]
			timersanitycheck = TimerSanityCheck(self.session.nav.RecordTimer.timer_list, entry)
			success = False
			if not timersanitycheck.check():
				simulTimerList = timersanitycheck.getSimulTimerList()
				if simulTimerList is not None:
					for x in simulTimerList:
						if x.setAutoincreaseEnd(entry):
							self.session.nav.RecordTimer.timeChanged(x)
					if not timersanitycheck.check():
						simulTimerList = timersanitycheck.getSimulTimerList()
						if simulTimerList is not None:
							self.session.openWithCallback(self.finishedEdit, TimerSanityConflict, timersanitycheck.getSimulTimerList())
					else:
						success = True
			else:
				success = True
			if success:
				self.session.nav.RecordTimer.timeChanged(entry)
# 		else:
# 			print "Timeredit aborted"

	def removeTimer(self, timer):
		self.closeChoiceBoxDialog()
		timer.afterEvent = AFTEREVENT.NONE
		self.session.nav.RecordTimer.removeEntry(timer)
		self['key_green'].setText(_('Add Timer'))
		self.key_green_choice = self.ADD_TIMER
		self.getCurrentCursorLocation = self['list'].getCurrentCursorLocation()
		self.refreshlist()

	def disableTimer(self, timer):
		self.closeChoiceBoxDialog()
		timer.disable()
		self.session.nav.RecordTimer.timeChanged(timer)
		self['key_green'].setText(_('Add Timer'))
		self.key_green_choice = self.ADD_TIMER
		self.getCurrentCursorLocation = self['list'].getCurrentCursorLocation()
		self.refreshlist()

	def recordTimerQuestionPos(self):
		serviceref = eServiceReference(str(self['list'].getCurrent()[1]))
		evtpos = self['list'].getSelectionPosition(serviceref)
		evth = self['list'].itemHeight
		menuh = self.ChoiceBoxDialog.instance.size().height()
		screeny = self.instance.position().y()
		listy = self['list'].instance.position().y()
		print "[EPGSelection] recordTimerQuestionPos 1", evtpos, evth, menuh, screeny, listy
		x = evtpos[0] - self.ChoiceBoxDialog.instance.size().width()
		if x < 0:
			x = 0
		y = evtpos[1] + evth
		if y + menuh > self['list'].listHeight + listy:
			y = evtpos[1] - menuh
		print "[EPGSelection] recordTimerQuestionPos 2", x, screeny + y
		return x, screeny + y

	def RecordTimerQuestion(self, manual=False):
		cur = self['list'].getCurrent()
		event = cur[0]
		serviceref = cur[1]
		if event is None:
			return
		eventid = event.getEventId()
		refstr = ':'.join(serviceref.ref.toString().split(':')[:11])
		title = None
		keys = []
		skin_name = None
		for timer in self.session.nav.RecordTimer.timer_list:
			if timer.eit == eventid and ':'.join(timer.service_ref.ref.toString().split(':')[:11]) == refstr:
				cb_func1 = lambda ret: self.removeTimer(timer)
				cb_func2 = lambda ret: self.editTimer(timer)
				cb_func3 = lambda ret: self.disableTimer(timer)
				menu = [(_("Delete timer"), 'CALLFUNC', self.RemoveChoiceBoxCB, cb_func1), (_("Edit timer"), 'CALLFUNC', self.RemoveChoiceBoxCB, cb_func2), (_("Disable timer"), 'CALLFUNC', self.RemoveChoiceBoxCB, cb_func3)]
				title = _("Select action for timer %s:") % event.getEventName()
				keys = ['red', 'green', 'yellow']
				skin_name = "RecordTimerQuestion1"
				break
		else:
			if not manual:
				menu = [(_("Add Timer"), 'CALLFUNC', self.ChoiceBoxCB, self.doRecordTimer), (_("Add AutoTimer"), 'CALLFUNC', self.ChoiceBoxCB, self.addAutoTimerSilent)]
				title = "%s?" % event.getEventName()
				keys = ['green', 'blue']
				skin_name = "RecordTimerQuestion"
			else:
				newEntry = RecordTimerEntry(serviceref, checkOldTimers=True, dirname=preferredTimerPath(), *parseEvent(event))
				self.session.openWithCallback(self.finishedAdd, TimerEntry, newEntry)
		if title:
			self.ChoiceBoxDialog = self.session.instantiateDialog(ChoiceBox, title=title, list=menu, keys=keys, skin_name=skin_name)
			menu_pos = self.recordTimerQuestionPos()
			self.ChoiceBoxDialog.instance.move(ePoint(menu_pos[0], menu_pos[1]))
			self.showChoiceBoxDialog()

	def recButtonPressed(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if not InfoBarInstance.LongButtonPressed:
			self.RecordTimerQuestion()

	def recButtonPressedLong(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if InfoBarInstance.LongButtonPressed:
			self.doZapTimer()

	def RemoveChoiceBoxCB(self, choice):
		self.closeChoiceBoxDialog()
		if choice:
			choice(self)

	def ChoiceBoxCB(self, choice):
		self.closeChoiceBoxDialog()
		if choice:
			try:
				choice()
			except:
				choice

	def showChoiceBoxDialog(self):
		self['okactions'].setEnabled(False)
		if 'epgcursoractions' in self:
			self['epgcursoractions'].setEnabled(False)
		self['colouractions'].setEnabled(False)
		self['recordingactions'].setEnabled(False)
		self['epgactions'].setEnabled(False)
		self["dialogactions"].setEnabled(True)
		self.ChoiceBoxDialog['actions'].execBegin()
		self.ChoiceBoxDialog.show()
		if 'input_actions' in self:
			self['input_actions'].setEnabled(False)

	def closeChoiceBoxDialog(self):
		self["dialogactions"].setEnabled(False)
		if self.ChoiceBoxDialog:
			self.ChoiceBoxDialog['actions'].execEnd()
			self.session.deleteDialog(self.ChoiceBoxDialog)
		self['okactions'].setEnabled(True)
		if 'epgcursoractions' in self:
			self['epgcursoractions'].setEnabled(True)
		self['colouractions'].setEnabled(True)
		self['recordingactions'].setEnabled(True)
		self['epgactions'].setEnabled(True)
		if 'input_actions' in self:
			self['input_actions'].setEnabled(True)

	def doRecordTimer(self):
		self.doInstantTimer(0)

	def doZapTimer(self):
		self.doInstantTimer(1)

	def doInstantTimer(self, zap):
		cur = self['list'].getCurrent()
		event = cur[0]
		serviceref = cur[1]
		if event is None:
			return
		eventid = event.getEventId()
		refstr = serviceref.ref.toString()
		newEntry = RecordTimerEntry(serviceref, checkOldTimers=True, *parseEvent(event))
		self.InstantRecordDialog = self.session.instantiateDialog(InstantRecordTimerEntry, newEntry, zap)
		retval = [True, self.InstantRecordDialog.retval()]
		self.session.deleteDialogWithCallback(self.finishedAdd, self.InstantRecordDialog, retval)

	def finishedAdd(self, answer):
		if answer[0]:
			entry = answer[1]
			simulTimerList = self.session.nav.RecordTimer.record(entry)
			if simulTimerList is not None:
				for x in simulTimerList:
					if x.setAutoincreaseEnd(entry):
						self.session.nav.RecordTimer.timeChanged(x)
				simulTimerList = self.session.nav.RecordTimer.record(entry)
				if simulTimerList is not None:
					if not entry.repeated and not config.recording.margin_before.value and not config.recording.margin_after.value and len(simulTimerList) > 1:
						change_time = False
						conflict_begin = simulTimerList[1].begin
						conflict_end = simulTimerList[1].end
						if conflict_begin == entry.end:
							entry.end -= 30
							change_time = True
						elif entry.begin == conflict_end:
							entry.begin += 30
							change_time = True
						if change_time:
							simulTimerList = self.session.nav.RecordTimer.record(entry)
					if simulTimerList is not None:
						self.session.openWithCallback(self.finishSanityCorrection, TimerSanityConflict, simulTimerList)
			self["key_green"].setText(_("Change timer"))
			self.key_green_choice = self.REMOVE_TIMER
		else:
			self['key_green'].setText(_('Add Timer'))
			self.key_green_choice = self.ADD_TIMER
		self.getCurrentCursorLocation = self['list'].getCurrentCursorLocation()
		self.refreshlist()

	def finishSanityCorrection(self, answer):
		self.finishedAdd(answer)

	def getOKConfig(self):
		return {
			EPG_TYPE_MULTI: config.epgselection.multi_ok.value,
			EPG_TYPE_ENHANCED: config.epgselection.enhanced_ok.value,
			EPG_TYPE_INFOBAR: config.epgselection.infobar_ok.value,
			EPG_TYPE_GRAPH: config.epgselection.graph_ok.value,
			EPG_TYPE_INFOBARGRAPH: config.epgselection.infobar_ok.value
		}.get(self.type)

	def _helpOK(self):
		confVal = self.getOKConfig()
		if confVal == 'Zap':
			return _("Zap to selected channel")
		elif confVal == 'Zap + Exit':
			return _("Zap to selected channel and exit EPG")
		return _("No current function")

	def OK(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if not InfoBarInstance.LongButtonPressed:
			if self.zapnumberstarted:
				self.doNumberZap()
			else:
				confVal = self.getOKConfig()
				if confVal == 'Zap':
					self.zapTo()
				elif confVal == 'Zap + Exit':
					self.zap()

	def getOKLongConfig(self):
		return {
			EPG_TYPE_MULTI: config.epgselection.multi_oklong.value,
			EPG_TYPE_ENHANCED: config.epgselection.enhanced_oklong.value,
			EPG_TYPE_INFOBAR: config.epgselection.infobar_oklong.value,
			EPG_TYPE_GRAPH: config.epgselection.graph_oklong.value,
			EPG_TYPE_INFOBARGRAPH: config.epgselection.infobar_oklong.value
		}.get(self.type)

	def _helpOKLong(self):
		confVal = self.getOKLongConfig()
		if confVal == 'Zap':
			return _("Zap to selected channel")
		elif confVal == 'Zap + Exit':
			return _("Zap to selected channel and exit EPG")
		return _("No current function")

	def OKLong(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if InfoBarInstance.LongButtonPressed:
			if self.zapnumberstarted:
				self.doNumberZap()
			else:
				confVal = self.getOKLongConfig()
				if confVal == 'Zap':
					self.zapTo()
				elif confVal == 'Zap + Exit':
					self.zap()

	def epgButtonPressed(self):
		self.OpenSingleEPG()

	def _helpInfo(self):
		helpText = _("Show current event information")
		if self.type == EPG_TYPE_GRAPH and config.epgselection.graph_info.value == 'Single EPG':
				helpText = _("Open single channel EPG")
		return helpText

	def Info(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if not InfoBarInstance.LongButtonPressed:
			if self.type == EPG_TYPE_GRAPH and config.epgselection.graph_info.value == 'Single EPG':
				self.OpenSingleEPG()
			else:
				self.infoKeyPressed()

	def _helpInfoLong(self):
		helpText = _("Open single channel EPG")
		if self.type == EPG_TYPE_GRAPH and config.epgselection.graph_infolong.value == 'Channel Info':
				helpText = _("Show current event information")

		return helpText

	def InfoLong(self):
		from InfoBar import InfoBar
		InfoBarInstance = InfoBar.instance
		if InfoBarInstance.LongButtonPressed:
			if self.type == EPG_TYPE_GRAPH and config.epgselection.graph_infolong.value == 'Channel Info':
				self.infoKeyPressed()
			else:
				self.OpenSingleEPG()

	def applyButtonState(self, state):
		if state == 0:
			self['now_button'].hide()
			self['now_button_sel'].hide()
			self['next_button'].hide()
			self['next_button_sel'].hide()
			self['more_button'].hide()
			self['more_button_sel'].hide()
			self['now_text'].hide()
			self['next_text'].hide()
			self['more_text'].hide()
			self['key_red'].setText('')
		else:
			if state == 1:
				self['now_button_sel'].show()
				self['now_button'].hide()
			else:
				self['now_button'].show()
				self['now_button_sel'].hide()
			if state == 2:
				self['next_button_sel'].show()
				self['next_button'].hide()
			else:
				self['next_button'].show()
				self['next_button_sel'].hide()
			if state == 3:
				self['more_button_sel'].show()
				self['more_button'].hide()
			else:
				self['more_button'].show()
				self['more_button_sel'].hide()

	def onSelectionChanged(self):
		cur = self['list'].getCurrent()
		event = cur[0]
		self['Event'].newEvent(event)
		if cur[1] is None:
			self['Service'].newService(None)
		else:
			self['Service'].newService(cur[1].ref)
		if self.type == EPG_TYPE_MULTI:
			count = self['list'].getCurrentChangeCount()
			if self.ask_time != -1:
				self.applyButtonState(0)
			elif count > 1:
				self.applyButtonState(3)
			elif count > 0:
				self.applyButtonState(2)
			else:
				self.applyButtonState(1)
			datestr = ''
			if event is not None:
				now = time()
				beg = event.getBeginTime()
				nowTime = localtime(now)
				begTime = localtime(beg)
				if nowTime.tm_year == begTime.tm_year and nowTime.tm_yday == begTime.tm_yday:
					datestr = _("Today")
				else:
					datestr = strftime(config.usage.date.dayshort.value, begTime)
			self['date'].setText(datestr)
		if cur[1] is None or cur[1].getServiceName() == '':
			if self.key_green_choice != self.EMPTY:
				self['key_green'].setText('')
				self.key_green_choice = self.EMPTY
			return
		if event is None:
			if self.key_green_choice != self.EMPTY:
				self['key_green'].setText('')
				self.key_green_choice = self.EMPTY
			return
		serviceref = cur[1]
		eventid = event.getEventId()
		refstr = ':'.join(serviceref.ref.toString().split(':')[:11])
		isRecordEvent = False
		for timer in self.session.nav.RecordTimer.timer_list:
			if timer.eit == eventid and ':'.join(timer.service_ref.ref.toString().split(':')[:11]) == refstr:
				isRecordEvent = True
				break
		if isRecordEvent and self.key_green_choice != self.REMOVE_TIMER:
			self["key_green"].setText(_("Change timer"))
			self.key_green_choice = self.REMOVE_TIMER
		elif not isRecordEvent and self.key_green_choice != self.ADD_TIMER:
			self['key_green'].setText(_('Add Timer'))
			self.key_green_choice = self.ADD_TIMER
		if self.eventviewDialog and self.type in (EPG_TYPE_INFOBAR, EPG_TYPE_INFOBARGRAPH):
			self.infoKeyPressed(True)

	def moveTimeLines(self, force=False):
		self.updateTimelineTimer.start((60 - int(time()) % 60) * 1000)
		self['timeline_text'].setEntries(self['list'], self['timeline_now'], self.time_lines, force)
		self['list'].l.invalidate()

	def isPlayable(self):
		current = ServiceReference(self.servicelist.getCurrentSelection())
		return not current.ref.flags & (eServiceReference.isMarker | eServiceReference.isDirectory)

	def setServicelistSelection(self, bouquet, service):
		if self.servicelist:
			if self.servicelist.getRoot() != bouquet:
				self.servicelist.clearPath()
				self.servicelist.enterPath(self.servicelist.bouquet_root)
				self.servicelist.enterPath(bouquet)
			self.servicelist.setCurrentSelection(service)

	def closeEventViewDialog(self):
		if self.eventviewDialog:
			self.eventviewDialog.hide()
			del self.eventviewDialog
			self.eventviewDialog = None

	def closeScreen(self, new_screen=None):
		if self.zapnumberstarted:
			self.stopNumberZap()
			return
		if self.type == EPG_TYPE_SINGLE:
			self.close()
			return  # stop and do not continue.
		closeParam = True
		if self.session.nav.getCurrentlyPlayingServiceOrGroup() and self.StartRef and self.session.nav.getCurrentlyPlayingServiceOrGroup().toString() != self.StartRef.toString():
			if self.zapFunc and self.StartRef and self.StartBouquet:
				def forceResume():
					from InfoBar import MoviePlayer
					if MoviePlayer.instance:
						MoviePlayer.instance.forceNextResume()

				if (
					(self.type == EPG_TYPE_GRAPH and config.epgselection.graph_preview_mode.value) or
					(self.type == EPG_TYPE_MULTI and config.epgselection.multi_preview_mode.value) or
					(self.type in (EPG_TYPE_INFOBAR, EPG_TYPE_INFOBARGRAPH) and config.epgselection.infobar_preview_mode.value in ('1', '2')) or
					(self.type == EPG_TYPE_ENHANCED and config.epgselection.enhanced_preview_mode.value)
				):
					if '0:0:0:0:0:0:0:0:0' not in self.StartRef.toString():
						self.zapFunc(None, zapback=True)
					else:
						forceResume()
						self.session.nav.playService(self.StartRef)
				else:
					self.zapFunc(None, False)
					closeParam = 'close'
		if self.session.pipshown:
			self.session.pipshown = False
			del self.session.pip
		self.closeEventViewDialog()
		self.close((closeParam, new_screen))

	def closeToMedia(self):
		self.closeScreen('media')

	def closeToTimer(self):
		self.closeScreen('timer')

	def zap(self):
		if self.zapFunc:
			self.zapSelectedService()
			self.closeEventViewDialog()
			self.close('close')
		else:
			self.closeEventViewDialog()
			self.close()

	def zapSelectedService(self, prev=False):
		currservice = self.session.nav.getCurrentlyPlayingServiceReference() and str(self.session.nav.getCurrentlyPlayingServiceReference().toString()) or None
		if self.session.pipshown:
			self.prevch = self.session.pip.getCurrentService() and str(self.session.pip.getCurrentService().toString()) or None
		else:
			self.prevch = self.session.nav.getCurrentlyPlayingServiceReference() and str(self.session.nav.getCurrentlyPlayingServiceReference().toString()) or None
		lst = self["list"]
		count = lst.getCurrentChangeCount()
		if count == 0:
			ref = lst.getCurrent()[1]
			if ref is not None:
				if self.type in (EPG_TYPE_INFOBAR, EPG_TYPE_INFOBARGRAPH) and config.epgselection.infobar_preview_mode.value == '2':
					if not prev:
						if self.session.pipshown:
							self.session.pipshown = False
							del self.session.pip
						self.zapFunc(ref.ref, bouquet=self.getCurrentBouquet(), preview=False)
						return
					if not self.session.pipshown:
						self.session.pip = self.session.instantiateDialog(PictureInPicture)
						self.session.pip.show()
						self.session.pipshown = True
					n_service = self.pipServiceRelation.get(str(ref.ref), None)
					if n_service is not None:
						service = eServiceReference(n_service)
					else:
						service = ref.ref
					if self.currch == service.toString():
						if self.session.pipshown:
							self.session.pipshown = False
							del self.session.pip
						self.zapFunc(ref.ref, bouquet=self.getCurrentBouquet(), preview=False)
						return
					if self.prevch != service.toString() and currservice != service.toString():
						self.session.pip.playService(service)
						self.currch = self.session.pip.getCurrentService() and str(self.session.pip.getCurrentService().toString())
				else:
					self.zapFunc(ref.ref, bouquet=self.getCurrentBouquet(), preview=prev)
					self.currch = self.session.nav.getCurrentlyPlayingServiceReference() and str(self.session.nav.getCurrentlyPlayingServiceReference().toString())
				self['list'].setCurrentlyPlaying(self.session.nav.getCurrentlyPlayingServiceOrGroup())

	def zapTo(self):
		if self.session.nav.getCurrentlyPlayingServiceOrGroup() and '0:0:0:0:0:0:0:0:0' in self.session.nav.getCurrentlyPlayingServiceOrGroup().toString():
			from Screens.InfoBarGenerics import setResumePoint
			setResumePoint(self.session)
		if self.zapFunc:
			self.zapSelectedService(True)
			self.refreshTimer.start(2000)
		if not self.currch or self.currch == self.prevch:
			if self.zapFunc:
				self.zapFunc(None, False)
				self.closeEventViewDialog()
				self.close('close')
			else:
				self.closeEventViewDialog()
				self.close()

	def keyNumberGlobal(self, number):
		if self.type in (EPG_TYPE_GRAPH, EPG_TYPE_INFOBARGRAPH):
			if self.type == EPG_TYPE_INFOBARGRAPH:
				timeperiod_conf = config.epgselection.infobar_prevtimeperiod
				roundto_conf = config.epgselection.infobar_roundto
				visiblehistory_conf = config.epgselection.infobar_visiblehistory
				config_primetimehour = config.epgselection.infobar_primetimehour
				config_primetimemins = config.epgselection.infobar_primetimemins
			else:
				timeperiod_conf = config.epgselection.graph_prevtimeperiod
				roundto_conf = config.epgselection.graph_roundto
				visiblehistory_conf = config.epgselection.graph_visiblehistory
				config_primetimehour = config.epgselection.graph_primetimehour
				config_primetimemins = config.epgselection.graph_primetimemins
			if number == 1:
				timeperiod = int(timeperiod_conf.value)
				if timeperiod > 90:
					timeperiod -= 60
					self['list'].setEpoch(timeperiod)
					timeperiod_conf.value = str(timeperiod)
					self.moveTimeLines()
			elif number == 2:
				self.prevPage()
			elif number == 3:
				timeperiod = int(timeperiod_conf.value)
				if timeperiod < 270:
					timeperiod += 60
					self['list'].setEpoch(timeperiod)
					timeperiod_conf.value = str(timeperiod)
					self.moveTimeLines()
			elif number == 4:
				self.updEvent(-2)
			elif number in (5, 0):
				if number == 0:
					self.toTop()
				self.ask_time = calculateEpgStartTime(roundto_conf, timeperiod_conf, visiblehistory_conf)
				self['list'].fillGraphEPG(None, self.ask_time)
				self.moveTimeLines(True)
			elif number == 6:
				self.updEvent(+2)
			elif number == 7:
				if self.type == EPG_TYPE_GRAPH:
					config.epgselection.graph_heightswitch.value = not config.epgselection.graph_heightswitch.value
					self['list'].setItemsPerPage()
					self['list'].fillGraphEPG(None)
					self.moveTimeLines()
				else:
					return 0
			elif number == 8:
				self.nextPage()
			elif number == 9:
				basetime = localtime(self['list'].getTimeBase())
				basetime = basetime[0:3] + (int(config_primetimehour.value), int(config_primetimemins.value), 0) + basetime[6:9]
				self.ask_time = mktime(basetime)
				if self.ask_time + 3600 < time():
					self.ask_time += 86400
				self['list'].fillGraphEPG(None, self.ask_time)
				self.moveTimeLines(True)
		elif self.type in (EPG_TYPE_ENHANCED, EPG_TYPE_INFOBAR):
			if number == 0 and not self.zapnumberstarted:
				num = self.currentService.getChannelNum()
				self.service, self.bouquet = self.searchNumber(num)
				self.doNumberZap()
				return
			self.zapnumberstarted = True
			self.NumberZapTimer.start(5000, True)
			if not self.NumberZapField:
				self.NumberZapField = str(number)
			else:
				self.NumberZapField += str(number)
			self.handleServiceName()
			self["number"].setText("Channel change\n" + self.zaptoservicename + '\n' + self.NumberZapField)
			self["number"].show()
			if len(self.NumberZapField) >= 4:
				self.doNumberZap()

	def doNumberZapBack(self):
		if self.zapnumberstarted and self.NumberZapField:
			self.NumberZapField = self.NumberZapField[:-1]
			if self.NumberZapField:
				self.handleServiceName()
				self["number"].setText("Channel change\n" + self.zaptoservicename + '\n' + self.NumberZapField)
			else:
				self.stopNumberZap()

	def stopNumberZap(self):
		self.zapnumberstarted = False
		self["number"].hide()
		self.NumberZapField = None
		self.NumberZapTimer.stop()

	def doNumberZap(self):
		self.zapnumberstarted = False
		self.numberEntered(self.service, self.bouquet)

	def handleServiceName(self):
		if self.searchNumber:
			self.service, self.bouquet = self.searchNumber(int(self.NumberZapField))
			self.zaptoservicename = ServiceReference(self.service).getServiceName()

	def numberEntered(self, service=None, bouquet=None):
		if service is not None:
			self.zapToNumber(service, bouquet)

	def searchNumberHelper(self, serviceHandler, num, bouquet):
		servicelist = serviceHandler.list(bouquet)
		if servicelist is not None:
			serviceIterator = servicelist.getNext()
			while serviceIterator.valid():
				if num == serviceIterator.getChannelNum():
					return serviceIterator
				serviceIterator = servicelist.getNext()
		return None

	def searchNumber(self, number):
		bouquet = self.servicelist.getRoot()
		service = None
		serviceHandler = eServiceCenter.getInstance()
		service = self.searchNumberHelper(serviceHandler, number, bouquet)
		if config.usage.multibouquet.value:
			service = self.searchNumberHelper(serviceHandler, number, bouquet)
			if service is None:
				bouquet = self.servicelist.bouquet_root
				bouquetlist = serviceHandler.list(bouquet)
				if bouquetlist is not None:
					bouquet = bouquetlist.getNext()
					while bouquet.valid():
						if bouquet.flags & eServiceReference.isDirectory:
							service = self.searchNumberHelper(serviceHandler, number, bouquet)
							if service is not None:
								playable = not service.flags & (eServiceReference.isMarker | eServiceReference.isDirectory) or service.flags & eServiceReference.isNumberedMarker
								if not playable:
									service = None
								break
							if config.usage.alternative_number_mode.value:
								break
						bouquet = bouquetlist.getNext()
		return service, bouquet

	def zapToNumber(self, service, bouquet):
		if self.type in (EPG_TYPE_ENHANCED, EPG_TYPE_INFOBAR):
			self.stopNumberZap()
			self.CurrBouquet = bouquet
			self.CurrService = service
		if service is not None:
			self.setServicelistSelection(bouquet, service)
		self.onCreate()

class SingleEPG(EPGSelection):
	def __init__(self, session, service, EPGtype="single"):
		EPGSelection.__init__(self, session, service=service, EPGtype=EPGtype)
		self.skinName = 'EPGSelection'
