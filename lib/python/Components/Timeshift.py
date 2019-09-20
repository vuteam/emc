# -*- coding: utf-8 -*-
# InfoBarTimeshift requires InfoBarSeek, instantiated BEFORE!

# Hrmf.
#
# Timeshift works the following way:
#                                         demux0   demux1                    "TimeshiftActions" "TimeshiftActivateActions" "SeekActions"
# - normal playback                       TUNER    unused      PLAY               enable                disable              disable
# - user presses "yellow" button.         FILE     record      PAUSE              enable                disable              enable
# - user presess pause again              FILE     record      PLAY               enable                disable              enable
# - user fast forwards                    FILE     record      FF                 enable                disable              enable
# - end of timeshift buffer reached       TUNER    record      PLAY               enable                enable               disable
# - user backwards                        FILE     record      BACK  # !!         enable                disable              enable
#

# in other words:
# - when a service is playing, pressing the "timeshiftStart" button ("yellow") enables recording ("enables timeshift"),
# freezes the picture (to indicate timeshift), sets timeshiftMode ("activates timeshift")
# now, the service becomes seekable, so "SeekActions" are enabled, "TimeshiftEnableActions" are disabled.
# - the user can now PVR around
# - if it hits the end, the service goes into live mode ("deactivates timeshift", it's of course still "enabled")
# the service looses it's "seekable" state. It can still be paused, but just to activate timeshift right
# after!
# the seek actions will be disabled, but the timeshiftActivateActions will be enabled
# - if the user rewinds, or press pause, timeshift will be activated again

# note that a timeshift can be enabled ("recording") and
# activated (currently time-shifting).


from Components.ActionMap import HelpableActionMap
from Components.ServiceEventTracker import ServiceEventTracker
from Components.config import config
from Components.SystemInfo import SystemInfo
from Components.Task import job_manager as JobManager

from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
import Screens.Standby
from ServiceReference import ServiceReference

from RecordTimer import RecordTimerEntry, parseEvent
from timer import TimerEntry

from Tools import ASCIItranslit, Notifications
from Tools.BoundFunction import boundFunction
from Tools.Directories import pathExists, fileExists, getRecordingFilename, copyfile, resolveFilename, SCOPE_TIMESHIFT
from Tools.TimeShift import CopyTimeshiftJob, MergeTimeshiftJob, CreateAPSCFilesJob

from enigma import eBackgroundFileEraser, eTimer, eServiceCenter, iServiceInformation, iPlayableService, eEPGCache
from boxbranding import getBoxType, getBrandOEM

from time import time, localtime, strftime
from random import randint

import os

def dprint(*args):
	if False:
		print "[Timeshift]", " ".join([str(x) for x in args])

posixPortableFilenameChars = set((c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"))

# Is used for filename substrings, so does not enforce that
# the name does not start with '-'

def isPosixPortableFilename(fn):
	return all(c in posixPortableFilenameChars for c in fn)

# Tests on whether a filename appears to be generated from
# mkstemp("timeshift.XXXXXX") as in lib/service/servicedvb.cpp.

# mkstemp("timeshift.XXXXXX") with any suffix

def isTimeshiftFilename(fn):
	return len(fn) >= 16 and fn.startswith("timeshift.") and isPosixPortableFilename(fn[10:16])

# mkstemp("timeshift.XXXXXX") with any suffix except ones ending
# in ".del" or ".copy"

def isNormalTimeshiftFilename(fn):
	return isTimeshiftFilename(fn) and not fn[16:].endswith((".del", ".copy"))

# mkstemp("timeshift.XXXXXX") without any suffix

def isTimeshiftFileBasename(fn):
	return len(fn) == 16 and isTimeshiftFilename(fn)

# The basename timeshift.XXXXXX file is the TS file for the timeshift buffer.
isTimeshiftFileTS = isTimeshiftFileBasename

def notifyActivateActionsUpDown(setting):
	from Screens.InfoBar import InfoBar
	if InfoBar.instance is not None:
		InfoBar.instance.setEnableTimeshiftActivateActions()

# Opens metafile and returns the tuple
# (servicerefname, eventname, description, begintime, tags)

def readMetafile(filename):
	readmetafile = open(filename, "r")
	t = tuple((readmetafile.readline().rstrip('\n') for x in range(5)))
	readmetafile.close()
	return t

class InfoBarTimeshift:
	def __init__(self):
		self["TimeshiftEnableActions"] = HelpableActionMap(self, "InfobarTimeshiftEnableActions", {
			"timeshiftEnableAndPause": (self.enableTimeshift, _("Pause and enter timeshift")),
		}, prio=-1, description=_("Enable timeshift"))

		self["TimeshiftActions"] = HelpableActionMap(self, "InfobarTimeshiftActions", {
			"timeshiftStop": (self._stopTimeshift, _("Stop timeshift")),
			"instantRecord": (self.instantRecord, _("Instant record...")),
			"jumpPreviousFile": (self.__jumpPreviousFile, _("Skip to previous event in timeshift")),
			"jumpNextFile": (self.__jumpNextFile, _("Skip to next event in timeshift")),
		}, prio=-1, description=_("Timeshift"))

		self["TimeshiftActivateActions"] = HelpableActionMap(self, "InfobarTimeshiftActivateActions", {
			"timeshiftActivateEnd": (self.activateTimeshiftSkipBackLeft, lambda: "%s %3d %s" % (_("Enter timeshift and skip back"), config.seek.selfdefined_left.value, _("sec"))),
			"timeshiftActivateEndAndPause": (self.activateTimeshiftPause, _("Pause and enter timeshift")),
			"timeshiftActivateEndSeekBack": (self.activateTimeshiftRew, _("Enter timeshift and rewind")),
		}, prio=-1, description=_("Activate timeshift"))  # priority over SeekActionsPTS

		self["TimeshiftActivateActionsUpDown"] = HelpableActionMap(self, "InfobarTimeshiftActivateUpDownActions", {
			"timeshiftActivateEndExtra": (self.activateTimeshiftSkipBackDown, lambda: "%s %3d %s" % (_("Enter timeshift and skip back"), config.seek.selfdefined_down.value, _("sec"))),
			"ignore": (lambda: 1, ""),
		}, prio=-1, description=_("Activate timeshift"))  # priority over SeekActionsPTS

		config.seek.updown_skips.addNotifier(notifyActivateActionsUpDown, initial_call=False, immediate_feedback=False)

		self["TimeshiftEnableActions"].setEnabled(False)
		self["TimeshiftActions"].setEnabled(False)
		self.setEnableTimeshiftActivateActions(False)

		self.switchToLive = True
		self.ptsStop = False
		self.ts_rewind_timer = eTimer()
		self.ts_rewind_timer.callback.append(self.rewindService)
		self.save_timeshift_file = False

		self.__event_tracker = ServiceEventTracker(screen=self, eventmap={
			iPlayableService.evStart: self.__serviceStarted,
			iPlayableService.evSeekableStatusChanged: self.__seekableStatusChanged,
			iPlayableService.evEnd: self.__serviceEnd,
			iPlayableService.evSOF: self.__evSOF,
			iPlayableService.evUpdatedInfo: self.__evInfoChanged,
			iPlayableService.evUpdatedEventInfo: self.__evEventInfoChanged,
			iPlayableService.evUser + 1: self.ptsTimeshiftFileChanged
		})

		self.pts_begintime = 0
		self.pts_switchtolive = False
		self.pts_currplaying = 1
		self.pts_skipBack = False
		self.pts_lastseekspeed = 0
		self.pts_record_running = self.session.nav.RecordTimer.isRecording()
		self.save_current_timeshift = False
		self.save_timeshift_postaction = None
		self.service_changed = False

		# Init Global Variables
		self.session.ptsmainloopvalue = 0
		config.timeshift.isRecording.value = False

		# Init eBackgroundFileEraser
		self.BgFileEraser = eBackgroundFileEraser.getInstance()

		# Init PTS Delay-Timer
		self.pts_delay_timer = eTimer()
		self.pts_delay_timer.callback.append(self.autostartPermanentTimeshift)

		# Init PTS MergeRecords-Timer
		self.pts_mergeRecords_timer = eTimer()
		self.pts_mergeRecords_timer.callback.append(self.ptsMergeRecords)

		# Init PTS Merge Cleanup-Timer
		self.pts_mergeCleanUp_timer = eTimer()
		self.pts_mergeCleanUp_timer.callback.append(self.ptsMergePostCleanUp)

		# Init PTS QuitMainloop-Timer
		self.pts_QuitMainloop_timer = eTimer()
		self.pts_QuitMainloop_timer.callback.append(self.ptsTryQuitMainloop)

		# Init PTS CleanUp-Timer
		self.pts_cleanUp_timer = eTimer()
		self.pts_cleanUp_timer.callback.append(self.ptsCleanTimeshiftFolder)
		# self.pts_cleanUp_timer.start(1000, True)

		# Init Block-Zap Timer
		self.pts_blockZap_timer = eTimer()

		# Record Event Tracker
		self.session.nav.RecordTimer.on_state_change.append(self.ptsTimerEntryStateChange)

		# Keep Current Event Info for recordings
		self.pts_eventcount = 1
		self.pts_curevent_begin = int(time())
		self.pts_curevent_end = 0
		self.pts_curevent_name = _("Timeshift")
		self.pts_curevent_description = ""
		self.pts_curevent_servicerefname = ""
		self.pts_curevent_station = ""
		self.pts_curevent_eventid = None

		self.pts_disable = False

		# Init PTS Infobar

	# Called when switching between timeshift and live
	def __seekableStatusChanged(self):
		dprint("__seekableStatusChanged")
		activate = not self.isSeekable() and int(config.timeshift.startdelay.value)
		state = self.getSeek() and self.timeshiftEnabled()
		dprint("isSeekable=%s, timeshiftEnabled=%s, config.timeshift.startdelay=%s, activate=%s, state=%s" % (self.isSeekable(), self.timeshiftEnabled(), config.timeshift.startdelay.value, activate, state))
		if int(config.timeshift.startdelay.value):
			self["TimeshiftEnableActions"].setEnabled(False)
			self["TimeshiftActions"].setEnabled(state)
			self.setEnableTimeshiftActivateActions(activate)
			self["SeekActionsPTS"].setEnabled(state)
		else:
			self["TimeshiftEnableActions"].setEnabled(True)
			self["TimeshiftActions"].setEnabled(False)
			self.setEnableTimeshiftActivateActions(False)
			self["SeekActionsPTS"].setEnabled(False)

		if not state:
			self.setSeekState(self.SEEK_STATE_PLAY)

		self.restartSubtitle()

		if self.timeshiftEnabled() and not self.isSeekable():
			self.ptsSeekPointerReset()
			if int(config.timeshift.startdelay.value):
				if self.pts_starttime <= (time() - 5):
					self.pts_blockZap_timer.start(3000, True)
			self.pts_currplaying = self.pts_eventcount
			self.pts_skipBack = False
			self.ptsSetNextPlaybackFile("")
			dprint("Resetting timeshift state to self.pts_currplaying=%d" % self.pts_currplaying)
			self.pvrStateDialog.hide()

	def __serviceStarted(self):
		dprint("__serviceStarted")
		self.createTimeshiftFolder()
		self.service_changed = True
		self.ptsCleanTimeshiftFolder()
		if self.pts_delay_timer.isActive():
			self.pts_delay_timer.stop()
		if int(config.timeshift.startdelay.value) and not self.pts_delay_timer.isActive():
			self.pts_trycount = 1
			self.pts_delay_timer.start(int(config.timeshift.startdelay.value) * 1000, True)
		self.__seekableStatusChanged()

	def __serviceEnd(self):
		dprint("__serviceEnd")
		self.service_changed = False
		if not config.timeshift.isRecording.value:
			self.maybeDisableTimeshift()
			self.__seekableStatusChanged()

	def __evSOF(self):
		dprint("__evSOF")
		self.__doEvSOF(showProgressBar=config.usage.show_infobar_on_event_change.value)

	def __jumpPreviousFile(self):
		dprint("__jumpPreviousFile")
		self.__doEvSOF(showProgressBar=config.usage.show_infobar_on_skip.value)

	def __doEvSOF(self, showProgressBar=False):
		dprint("__doEvSOF")
		if not self.timeshiftEnabled():
			return

		if self.pts_currplaying <= 1:
			dprint("at oldest timeshift buffer, pts_currplaying %d" % (self.pts_currplaying))
			self.pts_currplaying = 0  # This will increment to one as soon as playback switches
			self.pts_switchtolive = False
			self.pts_skipBack = False
			self.ptsSetNextPlaybackFile("pts_livebuffer_%s" % (1), goThere=True, showProgressBar=showProgressBar)
			return

		dprint("will try to step back to buffer", self.pts_currplaying - 1)

		if fileExists("%spts_livebuffer_%s" % (config.usage.timeshift_path.value, self.pts_currplaying - 1), 'r'):
			self.pts_switchtolive = False
			self.pts_skipBack = True
			self.ptsSetNextPlaybackFile("pts_livebuffer_%s" % (self.pts_currplaying - 1), goThere=True, showProgressBar=showProgressBar)
		return

	def __evEOF(self):
		dprint("__evEOF")
		self.__doEvEOF(showProgressBar=config.usage.show_infobar_on_event_change.value)

	def __jumpNextFile(self):
		dprint("__doEvEOF")
		self.__doEvEOF(showProgressBar=config.usage.show_infobar_on_skip.value)

	def __doEvEOF(self, showProgressBar=False):
		dprint("__doEvEOF")
		if not self.timeshiftEnabled():
			return

		if self.pts_eventcount < self.pts_currplaying:
			print "[Timeshift] ERROR, ERROR, timeshift buffer count %d is less than currently playing buffer number %d" % (self.pts_eventcount, self.pts_currplaying)
			return

		if self.pts_currplaying < self.pts_eventcount and fileExists("%spts_livebuffer_%s" % (config.usage.timeshift_path.value, self.pts_currplaying + 1), 'r'):
			self.pts_switchtolive = False
			self.pts_skipBack = False
			self.ptsSetNextPlaybackFile("pts_livebuffer_%s" % (self.pts_currplaying + 1), goThere=True, showProgressBar=showProgressBar)
			return

		dprint("no more timeshift buffers - go to live")
		self.pts_switchtolive = True
		self.pts_skipBack = False
		self.ptsSetNextPlaybackFile("", goThere=True, showProgressBar=showProgressBar)
		return

	def __evInfoChanged(self):
		dprint("__evInfoChanged")
		if self.service_changed:
			dprint("service_changed - reset pts_eventcount to zero")
			self.service_changed = False

			# We zapped away before saving the file, save it now!
			if self.save_current_timeshift:
				self.SaveTimeshift("pts_livebuffer_%s" % self.pts_eventcount)

			# Delete Timeshift Records on zap
			self.pts_eventcount = 0
			# print 'AAAAAAAAAAAAAAAAAAAAAA'
			# self.pts_cleanUp_timer.start(1000, True)

	def __evEventInfoChanged(self):
		dprint("__evEventInfoChanged")
		# if not int(config.timeshift.startdelay.value):
		# 	return

		# Get Current Event Info
		service = self.session.nav.getCurrentService()
		old_begin_time = self.pts_begintime
		info = service and service.info()
		ptr = info and info.getEvent(0)
		self.pts_begintime = ptr and ptr.getBeginTime() or 0

		# Save current TimeShift permanently now ...
		if info.getInfo(iServiceInformation.sVideoPID) != -1:
			# Take care of Record Margin Time ...
			if self.save_current_timeshift and self.timeshiftEnabled():
				if config.recording.margin_after.value > 0 and len(self.recording) == 0:
					self.SaveTimeshift(mergelater=True)
					recording = RecordTimerEntry(
						ServiceReference(self.session.nav.getCurrentlyPlayingServiceOrGroup()),
						time(), time() + (config.recording.margin_after.value * 60),
						self.pts_curevent_name, self.pts_curevent_description,
						self.pts_curevent_eventid, dirname=config.usage.default_path.value)
					recording.dontSave = True
					self.session.nav.RecordTimer.record(recording)
					self.recording.append(recording)
				else:
					self.SaveTimeshift()

			# print 'self.timeshiftEnabled2', self.timeshiftEnabled()

			# # Restarting active timers after zap ...
			# if self.pts_delay_timer.isActive() and not self.timeshiftEnabled():
			# 	print 'TS AUTO START TEST3'
			# 	self.pts_delay_timer.start(int(config.timeshift.startdelay.value) * 1000, True)
			# if self.pts_cleanUp_timer.isActive() and not self.timeshiftEnabled():
			# 	print 'BBBBBBBBBBBBBBBBBBBBB'
			# 	self.pts_cleanUp_timer.start(3000, True)

			# # (Re)Start TimeShift
			# print 'self.pts_delay_timer.isActive', self.pts_delay_timer.isActive()
			if not self.pts_delay_timer.isActive():
				# print 'TS AUTO START TEST4'
				if not self.timeshiftEnabled() or old_begin_time != self.pts_begintime or old_begin_time == 0:
					# print 'TS AUTO START TEST5'
					self.pts_delay_timer.start(1000, True)

	def setEnableTimeshiftActivateActions(self, activate=None):
		if activate is not None:
			activate = bool(activate)
			self["TimeshiftActivateActions"].setEnabled(activate)
		self["TimeshiftActivateActionsUpDown"].setEnabled(self["TimeshiftActivateActions"].enabled and config.seek.updown_skips.value)

	def getTimeshift(self):
		service = self.session.nav.getCurrentService()
		return service and service.timeshift()

	def timeshiftEnabled(self):
		ts = self.getTimeshift()
		return ts and ts.isTimeshiftEnabled()

	def enableTimeshift(self):
		dprint("enableTimeshift")
		if not int(config.timeshift.startdelay.value):
			dprint("enable timeshift, set startdelay=2")
			config.timeshift.startdelay.value = "2"
			self.pts_disable = True
			self.startTimeshift()
			self.activateTimeshiftPause()

	def _stopTimeshift(self):
		dprint("_stopTimeshift")
		self.maybeDisableTimeshift()
		self.stopTimeshift();

	def maybeDisableTimeshift(self):
		if self.pts_disable:
			dprint("disable timeshift, set startdelay=0")
			config.timeshift.startdelay.value = "0"
			self.pts_disable = False

	def startTimeshift(self):
		dprint("startTimeshift")
		if self.session.nav.getCurrentlyPlayingServiceReference() and 'http' in self.session.nav.getCurrentlyPlayingServiceReference().toString():
			if config.timeshift.stream_warning.value:
				self.session.open(MessageBox, _("Timeshift on a stream is not supported!"), MessageBox.TYPE_ERROR, timeout=5)
			print '[Timeshift] unable to activate, due being on a stream.'
			return
		ts = self.getTimeshift()
		if ts is None:
			# self.session.open(MessageBox, _("Timeshift not possible!"), MessageBox.TYPE_ERROR, timeout=5)
			return 0

		if ts.isTimeshiftEnabled():
			print "hu, timeshift already enabled?"
		else:
			self.pts_eventcount = 0
			self.activatePermanentTimeshift()
			self.activateTimeshift()

	def stopTimeshift(self):
		dprint("stopTimeshift")
		ts = self.getTimeshift()
		if ts and ts.isTimeshiftEnabled():
			# print 'TEST1'
			ts.switchToLive()
			if int(config.timeshift.startdelay.value) and self.isSeekable():
				# print 'TEST2'
				self.switchToLive = True
				self.ptsStop = True
				self.checkTimeshiftRunning(self.stopTimeshiftcheckTimeshiftRunningCallback)
			elif not int(config.timeshift.startdelay.value):
				# print 'TEST2b'
				self.checkTimeshiftRunning(self.stopTimeshiftcheckTimeshiftRunningCallback)
			else:
				# print 'TES2c'
				pass  # Placeholder for commented-out debug print
		else:
			# print 'TEST3'
			return

	def stopTimeshiftcheckTimeshiftRunningCallback(self, answer):
		dprint("stopTimeshiftcheckTimeshiftRunningCallback")
		# print ' answer', answer
		if answer and int(config.timeshift.startdelay.value) and self.switchToLive and self.isSeekable():
			# print 'TEST4'
			self.ptsStop = False
			self.pts_skipBack = False
			self.pts_switchtolive = True
			self.setSeekState(self.SEEK_STATE_PLAY)
			self.ptsSetNextPlaybackFile("", goThere=True)
			self.__seekableStatusChanged()
			return 0

		ts = self.getTimeshift()
		if answer and ts:
			# print 'TEST6'
			if int(config.timeshift.startdelay.value):
				# print 'TEST7'
				ts.stopTimeshift(self.switchToLive)
			else:
				# print 'TEST8'
				ts.stopTimeshift()
				self.service_changed = True
			self.__seekableStatusChanged()

	# action must be in ("pause", "skipBack", "rewind")
	# if action == "skipBack" shiftTime is the skip time in seconds
	# no skip will be made if shiftTime is None.
	# shiftTime is otherwise ignored

	def activateTimeshift(self, action="skipBack", shiftTime=None):
		dprint("activateTimeshift")
		ts = self.getTimeshift()
		if ts is None:
			return

		if ts.isTimeshiftActive() and action == "pause":
			self.pauseService()
		elif self.timeshiftEnabled():
			ts.activateTimeshift()  # activate timeshift will automatically pause

			if action == "pause":
				self.setSeekState(self.SEEK_STATE_PAUSE)
			elif action == "skipBack":
				self.setSeekState(self.SEEK_STATE_PLAY)
				if shiftTime is not None:
					self.doSeekRelative(-90000 * shiftTime)
			elif action == "rewind":
				self.setSeekState(self.SEEK_STATE_PLAY)
				self.seekBack()

	def activateTimeshiftPause(self):
		self.activateTimeshift(action="pause")

	def activateTimeshiftSkipBackLeft(self):
		self.activateTimeshift(action="skipBack", shiftTime=config.seek.selfdefined_left.value)

	def activateTimeshiftSkipBackDown(self):
		self.activateTimeshift(action="skipBack", shiftTime=config.seek.selfdefined_down.value)

	def activateTimeshiftRew(self):
		self.activateTimeshift(action="rewind")

	# activates timeshift, and seeks to (almost) the end
	def activateTimeshiftEnd(self, pause=False, shiftTime=None):
		dprint("activateTimeshiftEnd -- deprecated")
		shiftTimeVal = shiftTime if shiftTime is not None else config.seek.selfdefined_left.value
		self.activateTimeshift(action="pause" if pause else "skipBack", shiftTime=shiftTimeVal)

	def rewindService(self):
		dprint("rewindService")
		if getBrandOEM() in ('gigablue', 'xp'):
			self.setSeekState(self.SEEK_STATE_PLAY)
		self.setSeekState(self.makeStateBackward(int(config.seek.enter_backward.value)))

	def callServiceStarted(self):
		self.__serviceStarted()

	# same as activateTimeshiftEnd, but pauses afterwards.
	def activateTimeshiftEndAndPause(self):
		dprint("activateTimeshiftEndAndPause -- deprecated")
		self.activateTimeshiftPause()

	def checkTimeshiftRunning(self, returnFunction):
		dprint("checkTimeshiftRunning")
		# print 'self.switchToLive', self.switchToLive
		if self.ptsStop:
			returnFunction(True)
		elif (self.isSeekable() and self.timeshiftEnabled() or self.save_current_timeshift) and config.usage.check_timeshift.value:
			# print 'TEST1'
			if config.timeshift.favoriteSaveAction.value == "askuser":
				# print 'TEST2'
				if self.save_current_timeshift:
					# print 'TEST3'
					message = _("You have chosen to save the current timeshift event, but the event has not yet finished. What do you want to do?")
					choice = [
						(_("Save timeshift and stop recording"), "savetimeshift"),
						(_("Save timeshift and continue recording"), "savetimeshiftandrecord"),
						(_("Cancel save timeshift"), "noSave"),
						(_("Continue save timeshift"), "no")
					]
					self.session.openWithCallback(boundFunction(self.checkTimeshiftRunningCallback, returnFunction), MessageBox, message, simple=True, list=choice)
				else:
					# print 'TEST4'
					message = _("You seem to be in timeshift. What do you want to do?")
					choice = [
						(_("Leave timeshift"), "noSave"),
						(_("Always leave timeshift and don't ask again"), "noSaveNoAsk"),
						(_("Save timeshift and stop recording"), "savetimeshift"),
						(_("Save timeshift and continue recording"), "savetimeshiftandrecord"),
						(_("Continue timeshifting"), "no")
					]
					self.session.openWithCallback(boundFunction(self.checkTimeshiftRunningCallback, returnFunction), MessageBox, message, simple=True, list=choice)
			else:
				# print 'TEST5'
				if self.save_current_timeshift:
					# print 'TEST6'
					self.checkTimeshiftRunningCallback(returnFunction, "savetimeshiftandrecord")
				else:
					# print 'TEST7'
					message = _("You seem to be in timeshift, Do you want to leave timeshift?")
					choice = [
						(_("Yes"), config.timeshift.favoriteSaveAction.value),
						(_("No"), "no")
					]
					self.session.openWithCallback(boundFunction(self.checkTimeshiftRunningCallback, returnFunction), MessageBox, message, simple=True, list=choice)
		elif self.save_current_timeshift:
			self.checkTimeshiftRunningCallback(returnFunction, "savetimeshiftandrecord")
		else:
			returnFunction(True)

	def checkTimeshiftRunningCallback(self, returnFunction, answer):
		dprint("checkTimeshiftRunningCallback")
		# print 'returnFunction', returnFunction
		# print 'answer', answer
		if answer:
			if answer == "noSaveNoAsk":
				config.usage.check_timeshift.value = False
				config.usage.check_timeshift.save()
				answer = "noSave"
			if answer in ("savetimeshift", "savetimeshiftandrecord"):
				self.save_current_timeshift = True
			elif answer == "noSave":
				self.save_current_timeshift = False
			InfoBarTimeshift.saveTimeshiftActions(self, answer, returnFunction)

	def eraseTimeshiftFile(self):
		dprint("eraseTimeshiftFile")
		for filename in os.listdir(config.usage.timeshift_path.value):
			filepath = config.usage.timeshift_path.value + filename
			if isNormalTimeshiftFilename(filename) and os.path.isfile(filepath):
				self.BgFileEraser.erase(filepath)

	def autostartPermanentTimeshift(self):
		dprint("autostartPermanentTimeshift")
		if self.session.nav.getCurrentlyPlayingServiceReference() and 'http' in self.session.nav.getCurrentlyPlayingServiceReference().toString() and int(config.timeshift.startdelay.value):
			if config.timeshift.stream_warning.value:
				self.session.open(MessageBox, _("Timeshift on a stream is not supported!"), MessageBox.TYPE_ERROR, timeout=5)
			print '[Timeshift] unable to activate, due being on a stream.'
			return
		ts = self.getTimeshift()
		if ts is None:
			# print '[TimeShift] tune lock failed, so could not start.'
			return 0

		if int(config.timeshift.startdelay.value):
			self["TimeshiftEnableActions"].setEnabled(False)
			self["TimeshiftActions"].setEnabled(True)
			self.activatePermanentTimeshift()
		else:
			self["TimeshiftEnableActions"].setEnabled(True)
			self["TimeshiftActions"].setEnabled(False)

	def activatePermanentTimeshift(self):
		dprint("activatePermanentTimeshift")
		if not self.ptsCheckTimeshiftPath() or self.session.screen["Standby"].boolean or not self.ptsLiveTVStatus() or (config.timeshift.stopwhilerecording.value and self.pts_record_running):
			return

		# Set next-file on event change only when watching latest timeshift ...
		if self.isSeekable() and self.pts_eventcount == self.pts_currplaying:
			pts_setnextfile = True
		else:
			pts_setnextfile = False

		# Update internal Event Counter
		self.pts_eventcount += 1
		dprint("Increment pts_eventcount to ", self.pts_eventcount)

		# setNextPlaybackFile() on event change while timeshifting
		if self.pts_eventcount > 1 and self.isSeekable() and pts_setnextfile:
			self.pts_skipBack = False
			self.ptsSetNextPlaybackFile("pts_livebuffer_%s" % self.pts_eventcount, showProgressBar=config.usage.show_infobar_on_event_change.value)

		# Do not switch back to LiveTV while timeshifting
		if self.isSeekable():
			self.switchToLive = False
		else:
			self.switchToLive = True

		# (Re)start Timeshift now
		self.stopTimeshiftcheckTimeshiftRunningCallback(True)
		ts = self.getTimeshift()
		if ts and not ts.startTimeshift():
			if (getBoxType() == 'vuuno' or getBoxType() == 'vuduo') and os.path.exists("/proc/stb/lcd/symbol_timeshift"):
				if self.session.nav.RecordTimer.isRecording():
					f = open("/proc/stb/lcd/symbol_timeshift", "w")
					f.write("0")
					f.close()
			self.pts_starttime = time()
			self.save_timeshift_postaction = None
			self.ptsGetEventInfo()
			self.ptsCreateHardlink()
			self.__seekableStatusChanged()
		else:
			self.pts_eventcount = 0
			if self.pts_delay_timer.isActive():
				self.pts_delay_timer.stop()
			if int(config.timeshift.startdelay.value) and not self.pts_delay_timer.isActive() and self.pts_trycount < 5:
				self.pts_trycount += 1
				self.pts_delay_timer.start(int(config.timeshift.startdelay.value) * 1000, True)
			if self.pts_trycount > 4:
				# This can cause "RuntimeError: modal open are allowed only from a screen which is modal!"
				# when coming out of standby and the HDD takes too long to spin up.
				# self.session.open(MessageBox, _("Timeshift not possible!"), MessageBox.TYPE_ERROR, timeout=5)
				pass

	def createTimeshiftFolder(self):
		dprint("createTimeshiftFolder")
		timeshiftdir = resolveFilename(SCOPE_TIMESHIFT)
		if not pathExists(timeshiftdir):
			try:
				os.makedirs(timeshiftdir)
			except:
				print "[TimeShift] Failed to create %s !!" % timeshiftdir

	def restartTimeshift(self):
		dprint("restartTimeshift")
		self.activatePermanentTimeshift()
		Notifications.AddNotification(MessageBox, _("[TimeShift] Restarting Timeshift!"), MessageBox.TYPE_INFO, timeout=5)

	@staticmethod
	def getPendingSaveTimeshiftJobs():
		# Assumes that all timeshift save-related jobs
		# are in Tools.TimeShift
		return [j for j in JobManager.getPendingJobs() if j.__module__ == "Tools.TimeShift"]

	@staticmethod
	def hasPendingSaveTimeshiftJobs():
		return len(InfoBarTimeshift.getPendingSaveTimeshiftJobs()) > 0

	def saveTimeshiftEventPopup(self):
		dprint("saveTimeshiftEventPopup")
		entrylist = [(_("Current Event:") + " %s" % self.pts_curevent_name, "savetimeshift")]
		choice = 0

		filelist = [f for f in os.listdir(config.usage.timeshift_path.value) if f.startswith("pts_livebuffer_") and f[15:].isdigit()]

		if filelist:
			filelist.sort(key=lambda f: int(f[15:]), reverse=True)

			current_livebuffer = "pts_livebuffer_%s" % self.pts_currplaying
			buffer_num = 1

			for filename in filelist:
				# print "TRUE"
				statinfo = os.stat("%s%s" % (config.usage.timeshift_path.value, filename))
				metafile = "%s%s.meta" % (config.usage.timeshift_path.value, filename)

				if os.path.exists(metafile) and statinfo.st_mtime < (time() - 5.0):
					# Get Event Info from meta file
					(__, eventname, __, begintime, __) = readMetafile(metafile)

					# Add Event to list
					entrylist.append(("%s - %s" % (strftime("%H:%M", localtime(int(begintime))), eventname), "%s" % filename))
					if current_livebuffer == filename:
						choice = buffer_num
					buffer_num += 1

			self.session.openWithCallback(self.recordQuestionCallback, ChoiceBox, title=_("Which event do you want to save?"), list=entrylist, selection=choice, skin_name="InfoBarTimeshift")

	def saveTimeshiftActions(self, action=None, returnFunction=None):
		dprint("saveTimeshiftActions")
		# print 'action', action
		if action == "savetimeshift":
			self.SaveTimeshift()
		elif action == "savetimeshiftandrecord":
			if self.pts_curevent_end > time():
				self.SaveTimeshift(mergelater=True)
				self.ptsRecordCurrentEvent()
			else:
				self.SaveTimeshift()
		elif action == "noSave":
			config.timeshift.isRecording.value = False
			self.save_current_timeshift = False

		# Get rid of old timeshift file before E2 truncates its filesize
		if returnFunction is not None and action != "no":
			self.eraseTimeshiftFile()

		# print 'action returnFunction'
		returnFunction(action and action != "no")

	def checkSaveTimeshift(self, timeshiftfile=None, mergelater=False):
		if timeshiftfile is not None:
			filepath = config.usage.timeshift_path.value + timeshiftfile
			if os.path.isfile(filepath):
				statinfo = os.stat(filepath)
				if statinfo.st_nlink > 1:
					metafile = filepath + '.meta'
					eventname = ''
					begintime = ''
					if os.path.exists(metafile):
						(__, eventname, __, begintime, __) = readMetafile(metafile)
						if begintime:
							begintime = strftime("%H:%M", localtime(int(begintime)))
					if not begintime:
						begintime = strftime(_("Ended %H:%M"), localtime(int(statinfo.st_mtime)))
					if not eventname:
						eventname = _("Unknown event name")
					message = _("You have already saved %s (%s).\nDo you want to save another copy?") % (eventname, begintime)
					self.session.openWithCallback(boundFunction(self.checkSaveTimeshiftCallback, timeshiftfile=timeshiftfile, mergelater=mergelater), MessageBox, message, simple=True, default=False, timeout=15)
					return

		self.SaveTimeshift(timeshiftfile=timeshiftfile, mergelater=mergelater)

	def checkSaveTimeshiftCallback(self, answer, timeshiftfile=None, mergelater=False):
		if answer:
			self.SaveTimeshift(timeshiftfile=timeshiftfile, mergelater=mergelater)

	def checkSavingCurrentTimeshift(self):
		if self.save_current_timeshift:
			message = _("Timeshift of %s already being saved.\nWhat do you want to do?") % self.pts_curevent_name
			choice = [
				(_("Continue saving timeshift"), "continue"),
				(_("Cancel save timeshift"), "cancel"),
			]
			self.session.openWithCallback(self.checkSavingCurrentTimeshiftCallback, MessageBox, message, simple=True, list=choice, timeout=15, timeout_default="continue")
		else:
			Notifications.AddNotification(MessageBox, _("%s will be saved at end of event.") % self.pts_curevent_name, MessageBox.TYPE_INFO, timeout=5)
			self.save_current_timeshift = True
			config.timeshift.isRecording.value = True

	def checkSavingCurrentTimeshiftCallback(self, answer):
		if answer == "cancel":
			Notifications.AddNotification(MessageBox, _("Cancelled timeshift save."), MessageBox.TYPE_INFO, timeout=5)
			self.save_current_timeshift = False
			config.timeshift.isRecording.value = False

	def SaveTimeshift(self, timeshiftfile=None, mergelater=False):
		dprint("SaveTimeshift")
		self.save_current_timeshift = False
		savefilename = None
		if timeshiftfile is not None:
			savefilename = timeshiftfile
		# print 'savefilename', savefilename
		if savefilename is None:
			# print 'TEST1'
			ts = self.getTimeshift()
			if ts is not None:
				filepath = ts.getTimeshiftFilename()
				if filepath and os.path.isfile(filepath):
					savefiledir, savefilename = os.path.split(filepath)
					if not os.path.samefile(savefiledir, config.usage.timeshift_path.value) and os.path.isfile(filepath):
						print "[Timeshift] System timeshift directory", savefiledir, "doesn't match configured directory", config.usage.timeshift_path.value
						savefilename = None
				else:
					print "[Timeshift] Timeshift file not found:", filepath

		# print 'savefilename', savefilename
		if savefilename is None:
			Notifications.AddNotification(MessageBox, _("No Timeshift found to save as recording!"), MessageBox.TYPE_ERROR)
		else:
			timeshift_saved = True
			timeshift_saveerror1 = ""
			timeshift_saveerror2 = ""
			metamergestring = ""
			fullname = None

			config.timeshift.isRecording.value = True

			if mergelater:
				self.pts_mergeRecords_timer.start(120000, True)
				metamergestring = "pts_merge\n"

			try:
				if timeshiftfile is None:
					# Save Current Event by creating hardlink to ts file
					if self.pts_starttime >= (time() - 60):
						self.pts_starttime -= 60

					ptsfilename = "%s - %s - %s" % (strftime("%Y%m%d %H%M", localtime(self.pts_starttime)), self.pts_curevent_station, self.pts_curevent_name.replace("\n", ""))
					try:
						if config.usage.setup_level.index >= 2:
							if config.recording.filename_composition.value == "event":
								ptsfilename = "%s - %s_%s" % (self.pts_curevent_name.replace("\n", ""),strftime("%Y%m%d %H%M",localtime(self.pts_starttime)),self.pts_curevent_station)
							elif config.recording.filename_composition.value == "name":
								ptsfilename = "%s - %s" % (self.pts_curevent_name.replace("\n", ""),strftime("%Y%m%d %H%M",localtime(self.pts_starttime)))
							elif config.recording.filename_composition.value == "long" and self.pts_curevent_name.replace("\n", "") != self.pts_curevent_description.replace("\n", ""):
								ptsfilename = "%s - %s - %s - %s" % (strftime("%Y%m%d %H%M", localtime(self.pts_starttime)), self.pts_curevent_station, self.pts_curevent_name.replace("\n", ""), self.pts_curevent_description.replace("\n", ""))
							elif config.recording.filename_composition.value == "short":
								ptsfilename = "%s - %s" % (strftime("%Y%m%d", localtime(self.pts_starttime)), self.pts_curevent_name.replace("\n", ""))
					except Exception, errormsg:
						print "[TimeShift] Using default filename"

					if config.recording.ascii_filenames.value:
						ptsfilename = ASCIItranslit.legacyEncode(ptsfilename)

					# print 'ptsfilename', ptsfilename
					fullname = getRecordingFilename(ptsfilename, config.usage.default_path.value)
					# print 'fullname', fullname
					os.link("%s%s" % (config.usage.timeshift_path.value, savefilename), "%s.ts" % fullname)
					metafile = open("%s.ts.meta" % fullname, "w")
					metafile.write("%s\n%s\n%s\n%i\n%s" % (self.pts_curevent_servicerefname, self.pts_curevent_name.replace("\n", ""), self.pts_curevent_description.replace("\n", ""), int(self.pts_starttime), metamergestring))
					metafile.close()
					self.ptsCreateEITFile(fullname)
				elif timeshiftfile.startswith("pts_livebuffer"):
					# Save stored timeshift by creating hardlink to ts file
					(__, eventname, description, begintime, __) = readMetafile("%s%s.meta" % (config.usage.timeshift_path.value, timeshiftfile))

					ptsfilename = "%s - %s - %s" % (strftime("%Y%m%d %H%M", localtime(int(begintime))), self.pts_curevent_station, eventname)
					try:
						if config.usage.setup_level.index >= 2:
							if config.recording.filename_composition.value == "event":
								ptsfilename = "%s - %s_%s" % (eventname,strftime("%Y%m%d %H%M",localtime(int(begintime))),self.pts_curevent_station)
							elif config.recording.filename_composition.value == "long" and eventname != description:
								ptsfilename = "%s - %s - %s - %s" % (strftime("%Y%m%d %H%M", localtime(int(begintime))), self.pts_curevent_station, eventname, description)
							elif config.recording.filename_composition.value == "short":
								ptsfilename = "%s - %s" % (strftime("%Y%m%d", localtime(int(begintime))), eventname)
					except Exception, errormsg:
						print "[TimeShift] Using default filename"

					if config.recording.ascii_filenames.value:
						ptsfilename = ASCIItranslit.legacyEncode(ptsfilename)

					fullname = getRecordingFilename(ptsfilename, config.usage.default_path.value)
					os.link("%s%s" % (config.usage.timeshift_path.value, timeshiftfile), "%s.ts" % fullname)
					os.link("%s%s.meta" % (config.usage.timeshift_path.value, timeshiftfile), "%s.ts.meta" % fullname)
					if os.path.exists("%s%s.eit" % (config.usage.timeshift_path.value, timeshiftfile)):
						os.link("%s%s.eit" % (config.usage.timeshift_path.value, timeshiftfile), "%s.eit" % fullname)

					# Add merge-tag to metafile
					if mergelater:
						metafile = open("%s.ts.meta" % fullname, "a")
						metafile.write("%s\n" % metamergestring)
						metafile.close()

				# Create AP and SC Files when not merging
				if not mergelater:
					self.ptsCreateAPSCFiles(fullname + ".ts")

			except Exception, errormsg:
				timeshift_saved = False
				timeshift_saveerror1 = errormsg

			# Hmpppf! Saving Timeshift via Hardlink-Method failed. Probably other device?
			# Let's try to copy the file in background now! This might take a while ...
			if not timeshift_saved and fullname is not None:
				try:
					stat = os.statvfs(config.usage.default_path.value)
					freespace = stat.f_bfree / 1000 * stat.f_bsize / 1000
					randomint = randint(1, 999)

					if timeshiftfile is None:
						# Get Filesize for Free Space Check
						filesize = int(os.path.getsize("%s%s" % (config.usage.timeshift_path.value, savefilename)) / (1024 * 1024))

						# Save Current Event by copying it to the other device
						if filesize <= freespace:
							os.link("%s%s" % (config.usage.timeshift_path.value, savefilename), "%s%s.%s.copy" % (config.usage.timeshift_path.value, savefilename, randomint))
							copy_file = savefilename
							metafile = open("%s.ts.meta" % fullname, "w")
							metafile.write("%s\n%s\n%s\n%i\n%s" % (self.pts_curevent_servicerefname, self.pts_curevent_name.replace("\n", ""), self.pts_curevent_description.replace("\n", ""), int(self.pts_starttime), metamergestring))
							metafile.close()
							self.ptsCreateEITFile(fullname)
					elif timeshiftfile.startswith("pts_livebuffer"):
						# Get Filesize for Free Space Check
						filesize = int(os.path.getsize("%s%s" % (config.usage.timeshift_path.value, timeshiftfile)) / (1024 * 1024))

						# Save stored timeshift by copying it to the other device
						if filesize <= freespace:
							os.link("%s%s" % (config.usage.timeshift_path.value, timeshiftfile), "%s%s.%s.copy" % (config.usage.timeshift_path.value, timeshiftfile, randomint))
							copyfile("%s%s.meta" % (config.usage.timeshift_path.value, timeshiftfile), "%s.ts.meta" % fullname)
							if os.path.exists("%s%s.eit" % (config.usage.timeshift_path.value, timeshiftfile)):
								copyfile("%s%s.eit" % (config.usage.timeshift_path.value, timeshiftfile), "%s.eit" % fullname)
							copy_file = timeshiftfile

						# Add merge-tag to metafile
						if mergelater:
							metafile = open("%s.ts.meta" % fullname, "a")
							metafile.write("%s\n" % metamergestring)
							metafile.close()

					# Only copy file when enough disk-space available!
					if filesize <= freespace:
						timeshift_saved = True
						copy_file = copy_file + "." + str(randomint)

						# Get Event Info from meta file
						if os.path.exists("%s.ts.meta" % fullname):
							(__, eventname, __, __, __) = readMetafile("%s.ts.meta" % fullname)
						else:
							eventname = ""

						JobManager.AddJob(CopyTimeshiftJob(self, "mv \"%s%s.copy\" \"%s.ts\"" % (config.usage.timeshift_path.value, copy_file, fullname), copy_file, fullname, eventname))
						if not Screens.Standby.inTryQuitMainloop and not Screens.Standby.inStandby and not mergelater and self.save_timeshift_postaction != "standby":
							Notifications.AddNotification(MessageBox, _("Saving timeshift now. This might take a while!"), MessageBox.TYPE_INFO, timeout=5)
					else:
						timeshift_saved = False
						timeshift_saveerror1 = ""
						timeshift_saveerror2 = _("Not enough free Diskspace!\n\nFilesize: %sMB\nFree Space: %sMB\nPath: %s" % (filesize, freespace, config.usage.default_path.value))

				except Exception, errormsg:
					timeshift_saved = False
					timeshift_saveerror2 = errormsg

			if not timeshift_saved:
				config.timeshift.isRecording.value = False
				self.save_timeshift_postaction = None
				errormessage = str(timeshift_saveerror1) + "\n" + str(timeshift_saveerror2)
				Notifications.AddNotification(MessageBox, _("Timeshift save failed!") + "\n\n%s" % errormessage, MessageBox.TYPE_ERROR)
		self.save_timeshift_file = False
		# print 'SAVE COMPLETED'

	def ptsCleanTimeshiftFolder(self):
		dprint("ptsCleanTimeshiftFolder")
		if not self.ptsCheckTimeshiftPath():
			return

		for filename in os.listdir(config.usage.timeshift_path.value):
			filepath = config.usage.timeshift_path.value + filename
			if (isTimeshiftFilename(filename) or filename.startswith("pts_livebuffer_")) and os.path.isfile(filepath):
				# print 'filename:', filename
				try:
					statinfo = os.stat(filepath)
					age = time() - statinfo.st_mtime
					# older than 3 days = orphaned file, older than 3 seconds = stranded timeshift
					if (age > 3600 * 24 * 3) or (age > 3 and not filename.endswith((".del", ".copy"))):
						self.BgFileEraser.erase(filepath)
				except:
					# Most likely to get here if the file was deleted while iterating through the directory.
					pass

	def ptsGetEventInfo(self):
		dprint("ptsGetEventInfo")
		event = None
		try:
			serviceref = self.session.nav.getCurrentlyPlayingServiceOrGroup()
			serviceHandler = eServiceCenter.getInstance()
			info = serviceHandler.info(serviceref)

			self.pts_curevent_servicerefname = serviceref.toString()
			self.pts_curevent_station = info.getName(serviceref)

			service = self.session.nav.getCurrentService()
			info = service and service.info()
			event = info and info.getEvent(0)
		except Exception, errormsg:
			Notifications.AddNotification(MessageBox, _("Getting Event Info failed!") + "\n\n%s" % errormsg, MessageBox.TYPE_ERROR, timeout=10)

		if event is not None:
			curEvent = parseEvent(event)
			self.pts_curevent_begin = int(curEvent[0])
			self.pts_curevent_end = int(curEvent[1])
			self.pts_curevent_name = curEvent[2]
			self.pts_curevent_description = curEvent[3]
			self.pts_curevent_eventid = curEvent[4]

	def ptsFrontpanelActions(self, action=None):
		dprint("ptsFrontpanelActions")
		if self.session.nav.RecordTimer.isRecording() or SystemInfo.get("NumFrontpanelLEDs", 0) == 0:
			return

		if action == "start":
			if os.path.exists("/proc/stb/fp/led_set_pattern"):
				f = open("/proc/stb/fp/led_set_pattern", "w")
				f.write("0xa7fccf7a")
				f.close()
			elif os.path.exists("/proc/stb/fp/led0_pattern"):
				f = open("/proc/stb/fp/led0_pattern", "w")
				f.write("0x55555555")
				f.close()
			if os.path.exists("/proc/stb/fp/led_pattern_speed"):
				f = open("/proc/stb/fp/led_pattern_speed", "w")
				f.write("20")
				f.close()
			elif os.path.exists("/proc/stb/fp/led_set_speed"):
				f = open("/proc/stb/fp/led_set_speed", "w")
				f.write("20")
				f.close()
		elif action == "stop":
			if os.path.exists("/proc/stb/fp/led_set_pattern"):
				f = open("/proc/stb/fp/led_set_pattern", "w")
				f.write("0")
				f.close()
			elif os.path.exists("/proc/stb/fp/led0_pattern"):
				f = open("/proc/stb/fp/led0_pattern", "w")
				f.write("0")
				f.close()

	def ptsCreateHardlink(self):
		dprint("ptsCreateHardlink")

		tsDir = config.usage.timeshift_path.value

		for filename in [f for f in os.listdir(tsDir) if isTimeshiftFileBasename(f)]:
			# if filename.startswith("timeshift") and not os.path.splitext(filename)[1]:
			filepath = tsDir + filename
			if os.path.isfile(filepath):
				if os.path.exists("%spts_livebuffer_%s.eit" % (tsDir, self.pts_eventcount)):
					self.BgFileEraser.erase("%spts_livebuffer_%s.eit" % (tsDir, self.pts_eventcount))
				if os.path.exists("%spts_livebuffer_%s.meta" % (tsDir, self.pts_eventcount)):
					self.BgFileEraser.erase("%spts_livebuffer_%s.meta" % (tsDir, self.pts_eventcount))
				if os.path.exists("%spts_livebuffer_%s" % (tsDir, self.pts_eventcount)):
					self.BgFileEraser.erase("%spts_livebuffer_%s" % (tsDir, self.pts_eventcount))
				if os.path.exists("%spts_livebuffer_%s.sc" % (tsDir, self.pts_eventcount)):
					self.BgFileEraser.erase("%spts_livebuffer_%s.sc" % (tsDir, self.pts_eventcount))
				try:
					# Create link to pts_livebuffer file
					dprint("%s -> pts_livebuffer_%s" % (filename, self.pts_eventcount))
					os.link(filepath, "%spts_livebuffer_%s" % (tsDir, self.pts_eventcount))
					os.link(filepath + ".sc", "%spts_livebuffer_%s.sc" % (tsDir, self.pts_eventcount))

					# Create a Meta File
					metafile = open("%spts_livebuffer_%s.meta" % (tsDir, self.pts_eventcount), "w")
					metafile.write("%s\n%s\n%s\n%i\n" % (
						self.pts_curevent_servicerefname,
						self.pts_curevent_name.replace("\n", " "),
						self.pts_curevent_description.replace("\n", " "),
						int(self.pts_starttime)
					))
					metafile.close()
				except Exception, errormsg:
					Notifications.AddNotification(
						MessageBox, _("Creating hard link to timeshift file failed!") + "\n" +
						_("The file system used for timeshift must support hardlinks.") + "\n\n" +
						"%s\n%s" % (tsDir, errormsg), MessageBox.TYPE_ERROR)

				# Create EIT File
				self.ptsCreateEITFile("%spts_livebuffer_%s" % (tsDir, self.pts_eventcount))

				# Permanent Recording Hack
				if config.timeshift.permanentrecording.value:
					try:
						fullname = getRecordingFilename(
							"%s - %s - %s" % (strftime("%Y%m%d %H%M", localtime(self.pts_starttime)), self.pts_curevent_station, self.pts_curevent_name),
							config.usage.default_path.value)
						os.link(filepath, "%s.ts" % fullname)
						# Create a Meta File
						metafile = open("%s.ts.meta" % fullname, "w")
						metafile.write("%s\n%s\n%s\n%i\nautosaved\n" % (
							self.pts_curevent_servicerefname,
							self.pts_curevent_name.replace("\n", ""),
							self.pts_curevent_description.replace("\n", ""),
							int(self.pts_starttime)
						))
						metafile.close()
					except Exception, errormsg:
						print "[Timeshift] %s\n%s" % (filepath, errormsg)

	def ptsRecordCurrentEvent(self):
		dprint("ptsRecordCurrentEvent")
		recording = RecordTimerEntry(ServiceReference(self.session.nav.getCurrentlyPlayingServiceOrGroup()), time(), self.pts_curevent_end, self.pts_curevent_name, self.pts_curevent_description, self.pts_curevent_eventid, dirname=config.usage.default_path.value)
		recording.dontSave = True
		self.session.nav.RecordTimer.record(recording)
		self.recording.append(recording)

	def ptsMergeRecords(self):
		dprint("ptsMergeRecords")
		if self.session.nav.RecordTimer.isRecording():
			self.pts_mergeRecords_timer.start(120000, True)
			return

		ptsmergeSRC = ""
		ptsmergeDEST = ""
		ptsmergeeventname = ""
		ptsgetnextfile = False
		ptsfilemerged = False

		filelist = os.listdir(config.usage.default_path.value)

		if filelist is not None:
			filelist.sort()

		for filename in filelist:
			if filename.endswith(".meta"):
				# Get Event Info from meta file
				(servicerefname, eventname, eventtitle, eventtime, eventtag) = readMetafile("%s%s" % (config.usage.default_path.value, filename))

				if ptsgetnextfile:
					ptsgetnextfile = False
					ptsmergeSRC = filename[0:-5]

					if ASCIItranslit.legacyEncode(eventname) == ASCIItranslit.legacyEncode(ptsmergeeventname):
						# Copy EIT File
						if fileExists("%s%s.eit" % (config.usage.default_path.value, ptsmergeSRC[0:-3])):
							copyfile("%s%s.eit" % (config.usage.default_path.value, ptsmergeSRC[0:-3]), "%s%s.eit" % (config.usage.default_path.value, ptsmergeDEST[0:-3]))

						# Delete AP and SC Files
						if os.path.exists("%s%s.ap" % (config.usage.default_path.value, ptsmergeDEST)):
							self.BgFileEraser.erase("%s%s.ap" % (config.usage.default_path.value, ptsmergeDEST))
						if os.path.exists("%s%s.sc" % (config.usage.default_path.value, ptsmergeDEST)):
							self.BgFileEraser.erase("%s%s.sc" % (config.usage.default_path.value, ptsmergeDEST))

						# Add Merge Job to JobManager
						JobManager.AddJob(MergeTimeshiftJob(self, "cat \"%s%s\" >> \"%s%s\"" % (config.usage.default_path.value, ptsmergeSRC, config.usage.default_path.value, ptsmergeDEST), ptsmergeSRC, ptsmergeDEST, eventname))
						config.timeshift.isRecording.value = True
						ptsfilemerged = True
					else:
						ptsgetnextfile = True

				if eventtag == "pts_merge" and not ptsgetnextfile:
					ptsgetnextfile = True
					ptsmergeDEST = filename[0:-5]
					ptsmergeeventname = eventname
					ptsfilemerged = False

					# If still recording or transfering, try again later ...
					if fileExists("%s%s" % (config.usage.default_path.value, ptsmergeDEST)):
						statinfo = os.stat("%s%s" % (config.usage.default_path.value, ptsmergeDEST))
						if statinfo.st_mtime > (time() - 10.0):
							self.pts_mergeRecords_timer.start(120000, True)
							return

					# Rewrite Meta File to get rid of pts_merge tag
					metafile = open("%s%s.meta" % (config.usage.default_path.value, ptsmergeDEST), "w")
					metafile.write("%s\n%s\n%s\n%i\n" % (servicerefname, eventname, eventtitle, int(eventtime)))
					metafile.close()

		# Merging failed :(
		if not ptsfilemerged and ptsgetnextfile:
			Notifications.AddNotification(MessageBox, _("[Timeshift] Merging records failed!"), MessageBox.TYPE_ERROR)

	def ptsCreateAPSCFiles(self, filename):
		dprint("ptsCreateAPSCFiles")
		if fileExists(filename, 'r'):
			if fileExists(filename + ".meta", 'r'):
				# Get Event Info from meta file
				(__, eventname, __, __, __) = readMetafile(filename + ".meta")
			else:
				eventname = ""
			JobManager.AddJob(CreateAPSCFilesJob(self, "/usr/lib/enigma2/python/Components/createapscfiles \"%s\"" % filename, eventname))
		else:
			self.ptsSaveTimeshiftFinished()

	def ptsCreateEITFile(self, filename):
		dprint("ptsCreateEITFile")
		if self.pts_curevent_eventid is not None:
			try:
				serviceref = ServiceReference(self.session.nav.getCurrentlyPlayingServiceOrGroup()).ref
				eEPGCache.getInstance().saveEventToFile(filename+".eit", serviceref, self.pts_curevent_eventid, -1, -1)
			except Exception, errormsg:
				print "[Timeshift] ptsCreateEITFile: %s" % errormsg

	def ptsCopyFilefinished(self, srcfile, destfile):
		dprint("ptsCopyFilefinished")
		# Erase Source File
		if fileExists(srcfile):
			self.BgFileEraser.erase(srcfile)

		# Restart Merge Timer
		if self.pts_mergeRecords_timer.isActive():
			self.pts_mergeRecords_timer.stop()
			self.pts_mergeRecords_timer.start(15000, True)
		else:
			# Create AP and SC Files
			self.ptsCreateAPSCFiles(destfile)

	def ptsMergeFilefinished(self, srcfile, destfile):
		dprint("ptsMergeFilefinished")
		if self.session.nav.RecordTimer.isRecording() or self.hasPendingSaveTimeshiftJobs():
			# Rename files and delete them later ...
			self.pts_mergeCleanUp_timer.start(120000, True)
			os.system("echo \"\" > \"%s.pts.del\"" % (srcfile[0:-3]))
		else:
			# Delete Instant Record permanently now ... R.I.P.
			self.BgFileEraser.erase("%s" % srcfile)
			self.BgFileEraser.erase("%s.ap" % srcfile)
			self.BgFileEraser.erase("%s.sc" % srcfile)
			self.BgFileEraser.erase("%s.meta" % srcfile)
			self.BgFileEraser.erase("%s.cuts" % srcfile)
			self.BgFileEraser.erase("%s.eit" % (srcfile[0:-3]))

		# Create AP and SC Files
		self.ptsCreateAPSCFiles(destfile)

		# Run Merge-Process one more time to check if there are more records to merge
		self.pts_mergeRecords_timer.start(10000, True)

	def ptsSaveTimeshiftFinished(self):
		dprint("ptsSaveTimeshiftFinished")
		if not self.pts_mergeCleanUp_timer.isActive():
			self.ptsFrontpanelActions("stop")
			config.timeshift.isRecording.value = False

		if Screens.Standby.inTryQuitMainloop:
			self.pts_QuitMainloop_timer.start(30000, True)
		else:
			Notifications.AddNotification(MessageBox, _("Timeshift saved to your harddisk!"), MessageBox.TYPE_INFO, timeout=5)

	def ptsMergePostCleanUp(self):
		dprint("ptsMergePostCleanUp")
		if self.session.nav.RecordTimer.isRecording() or self.hasPendingSaveTimeshiftJobs():
			config.timeshift.isRecording.value = True
			self.pts_mergeCleanUp_timer.start(120000, True)
			return

		self.ptsFrontpanelActions("stop")
		config.timeshift.isRecording.value = False

		filelist = os.listdir(config.usage.default_path.value)
		for filename in filelist:
			if filename.endswith(".pts.del"):
				srcfile = config.usage.default_path.value + "/" + filename[0:-8] + ".ts"
				self.BgFileEraser.erase("%s" % srcfile)
				self.BgFileEraser.erase("%s.ap" % srcfile)
				self.BgFileEraser.erase("%s.sc" % srcfile)
				self.BgFileEraser.erase("%s.meta" % srcfile)
				self.BgFileEraser.erase("%s.cuts" % srcfile)
				self.BgFileEraser.erase("%s.eit" % (srcfile[0:-3]))
				self.BgFileEraser.erase("%s.pts.del" % (srcfile[0:-3]))

				# Restart QuitMainloop Timer to give BgFileEraser enough time
				if Screens.Standby.inTryQuitMainloop and self.pts_QuitMainloop_timer.isActive():
					self.pts_QuitMainloop_timer.start(60000, True)

	def ptsTryQuitMainloop(self):
		dprint("ptsTryQuitMainloop")
		if Screens.Standby.inTryQuitMainloop and (self.hasPendingSaveTimeshiftJobs() or self.pts_mergeCleanUp_timer.isActive()):
			self.pts_QuitMainloop_timer.start(60000, True)
			return

		if Screens.Standby.inTryQuitMainloop and self.session.ptsmainloopvalue:
			self.session.dialog_stack = []
			self.session.summary_stack = [None]
			self.session.open(Screens.Standby.TryQuitMainloop, self.session.ptsmainloopvalue)

	def ptsGetSeekInfo(self):
		dprint("ptsGetSeekInfo")
		s = self.session.nav.getCurrentService()
		return s and s.seek()

	def ptsGetPosition(self):
		dprint("ptsGetPosition")
		seek = self.ptsGetSeekInfo()
		if seek is None:
			return None
		pos = seek.getPlayPosition()
		if pos[0]:
			return 0
		return pos[1]

	def ptsGetLength(self):
		dprint("ptsGetLength")
		seek = self.ptsGetSeekInfo()
		if seek is None:
			return None
		length = seek.getLength()
		if length[0]:
			return 0
		return length[1]

	def ptsGetTimeshiftStatus(self):
		dprint("ptsGetTimeshiftStatus")
		return bool(self.isSeekable() and self.timeshiftEnabled() and config.usage.check_timeshift.value or self.save_current_timeshift)

	def ptsSeekPointerOK(self):
		dprint("ptsSeekPointerOK")
		if "PTSSeekPointer" in self.pvrStateDialog and self.timeshiftEnabled() and self.isSeekable():
			if not self.pvrStateDialog.shown:
				if self.seekstate != self.SEEK_STATE_PLAY or self.seekstate == self.SEEK_STATE_PAUSE:
					self.setSeekState(self.SEEK_STATE_PLAY)
				self.doShow()
				return

			length = self.ptsGetLength()
			position = self.ptsGetPosition()

			if length is None or position is None:
				return

			cur_pos = self.pvrStateDialog["PTSSeekPointer"].position
			jumptox = int(cur_pos[0]) - (int(self.pvrStateDialog["PTSSeekBack"].instance.position().x()) + 8)
			jumptoperc = round((jumptox / float(self.pvrStateDialog["PTSSeekBack"].instance.size().width())) * 100, 0)
			jumptotime = int((length / 100) * jumptoperc)
			jumptodiff = position - jumptotime

			self.doSeekRelative(-jumptodiff)
		else:
			return

	def ptsSeekPointerLeft(self):
		dprint("ptsSeekPointerLeft")
		if "PTSSeekPointer" in self.pvrStateDialog and self.pvrStateDialog.shown and self.timeshiftEnabled() and self.isSeekable():
			self.ptsMoveSeekPointer(direction="left")
		else:
			return

	def ptsSeekPointerRight(self):
		dprint("ptsSeekPointerRight")
		if "PTSSeekPointer" in self.pvrStateDialog and self.pvrStateDialog.shown and self.timeshiftEnabled() and self.isSeekable():
			self.ptsMoveSeekPointer(direction="right")
		else:
			return

	def ptsSeekPointerReset(self):
		dprint("ptsSeekPointerReset")
		if "PTSSeekPointer" in self.pvrStateDialog and self.timeshiftEnabled():
			self.pvrStateDialog["PTSSeekPointer"].setPosition(int(self.pvrStateDialog["PTSSeekBack"].instance.position().x()) + 8, self.pvrStateDialog["PTSSeekPointer"].position[1])

	def ptsSeekPointerSetCurrentPos(self):
		dprint("ptsSeekPointerSetCurrentPos")
		if "PTSSeekPointer" not in self.pvrStateDialog or not self.timeshiftEnabled() or not self.isSeekable():
			return

		position = self.ptsGetPosition()
		length = self.ptsGetLength()

		if length >= 1:
			tpixels = int((float(int((position * 100) / length)) / 100) * self.pvrStateDialog["PTSSeekBack"].instance.size().width())
			self.pvrStateDialog["PTSSeekPointer"].setPosition(int(self.pvrStateDialog["PTSSeekBack"].instance.position().x()) + 8 + tpixels, self.pvrStateDialog["PTSSeekPointer"].position[1])

	def ptsMoveSeekPointer(self, direction=None):
		dprint("ptsMoveSeekPointer")
		if direction is None or "PTSSeekPointer" not in self.pvrStateDialog:
			return
		isvalidjump = False
		cur_pos = self.pvrStateDialog["PTSSeekPointer"].position
		self.doShow()

		if direction == "left":
			minmaxval = int(self.pvrStateDialog["PTSSeekBack"].instance.position().x()) + 8
			movepixels = -15
			if cur_pos[0] + movepixels > minmaxval:
				isvalidjump = True
		elif direction == "right":
			minmaxval = int(self.pvrStateDialog["PTSSeekBack"].instance.size().width() * 0.96)
			movepixels = 15
			if cur_pos[0] + movepixels < minmaxval:
				isvalidjump = True
		else:
			return 0

		if isvalidjump:
			self.pvrStateDialog["PTSSeekPointer"].setPosition(cur_pos[0] + movepixels, cur_pos[1])
		else:
			self.pvrStateDialog["PTSSeekPointer"].setPosition(minmaxval, cur_pos[1])

	def ptsTimeshiftFileChanged(self):
		dprint("ptsTimeshiftFileChanged")
		# Reset Seek Pointer
		self.ptsSeekPointerReset()

		dprint("self.pts_switchtolive", self.pts_switchtolive)
		if self.pts_switchtolive:
			self.pts_switchtolive = False
			self.pts_skipBack = False
			return

		if self.pts_skipBack:
			dprint("skipBack == True, update pts_currplaying from %d to %d" % (self.pts_currplaying, self.pts_currplaying - 1))
			self.pts_currplaying -= 1
		else:
			dprint("skipBack == False, update pts_currplaying from %d to %d" % (self.pts_currplaying, self.pts_currplaying + 1))
			self.pts_currplaying += 1
		self.pts_skipBack = False

		# Get next pts file ...
		if fileExists("%spts_livebuffer_%s" % (config.usage.timeshift_path.value, self.pts_currplaying + 1), 'r'):
			self.pts_switchtolive = False
			self.ptsSetNextPlaybackFile("pts_livebuffer_%s" % (self.pts_currplaying + 1), showProgressBar=config.usage.show_infobar_on_event_change.value)
		else:
			self.pts_switchtolive = True
			self.ptsSetNextPlaybackFile("", showProgressBar=config.usage.show_infobar_on_event_change.value)

	def ptsSetNextPlaybackFile(self, nexttsfile, goThere=False, showProgressBar=False):
		dprint("ptsSetNextPlaybackFile")
		ts = self.getTimeshift()
		if ts is None:
			dprint("can not get timeshift")
			return False
		if (nexttsfile):
			dprint("setNextPlaybackFile(%s%s)" % (config.usage.timeshift_path.value, nexttsfile))
			ts.setNextPlaybackFile("%s%s" % (config.usage.timeshift_path.value, nexttsfile))
		else:
			dprint("setNextPlaybackFile('')")
			ts.setNextPlaybackFile("")
		if goThere:
			dprint("goToNextPlaybackFile")
			ts.goToNextPlaybackFile()
		if showProgressBar:
			self.showAfterSeek()
		return True

	def ptsCheckTimeshiftPath(self):
		dprint("ptsCheckTimeshiftPath")
		if fileExists(config.usage.timeshift_path.value, 'w'):
			return True
		else:
			# Notifications.AddNotification(MessageBox, _("Could not activate Permanent-Timeshift!\nTimeshift-Path does not exist"), MessageBox.TYPE_ERROR, timeout=15)
			if self.pts_delay_timer.isActive():
				self.pts_delay_timer.stop()
			if self.pts_cleanUp_timer.isActive():
				# print 'CCCCCCCCCCCCCCCCCCCCCCCC'
				self.pts_cleanUp_timer.stop()
			return False

	def ptsTimerEntryStateChange(self, timer):
		dprint("ptsTimerEntryStateChange")
		if not config.timeshift.stopwhilerecording.value:
			return

		self.pts_record_running = self.session.nav.RecordTimer.isRecording()

		# Abort here when box is in standby mode
		if self.session.screen["Standby"].boolean is True:
			return

		# Stop Timeshift when Record started ...
		if timer.state == TimerEntry.StateRunning and self.timeshiftEnabled() and self.pts_record_running:
			if self.seekstate != self.SEEK_STATE_PLAY:
				self.setSeekState(self.SEEK_STATE_PLAY)

			if self.isSeekable():
				Notifications.AddNotification(MessageBox, _("Recording started! Stopping timeshift now ..."), MessageBox.TYPE_INFO, timeout=5)

			self.switchToLive = False
			self.stopTimeshiftcheckTimeshiftRunningCallback(True)

		# Restart Timeshift when all records stopped
		if timer.state == TimerEntry.StateEnded and not self.timeshiftEnabled() and not self.pts_record_running:
			self.autostartPermanentTimeshift()

		# Restart Merge-Timer when all records stopped
		if timer.state == TimerEntry.StateEnded and self.pts_mergeRecords_timer.isActive():
			self.pts_mergeRecords_timer.stop()
			self.pts_mergeRecords_timer.start(15000, True)

		# Restart FrontPanel LED when still copying or merging files
		# ToDo: Only do this on PTS Events and not events from other jobs
		if timer.state == TimerEntry.StateEnded and (self.hasPendingSaveTimeshiftJobs() or self.pts_mergeRecords_timer.isActive()):
			self.ptsFrontpanelActions("start")
			config.timeshift.isRecording.value = True

	def ptsLiveTVStatus(self):
		dprint("ptsLiveTVStatus")
		service = self.session.nav.getCurrentService()
		info = service and service.info()
		sTSID = info and info.getInfo(iServiceInformation.sTSID) or -1

		if sTSID is None or sTSID == -1:
			return False
		else:
			return True
