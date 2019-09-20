from enigma import getPrevAsciiCode
from Tools.NumericalTextInput import NumericalTextInput
from Tools.Directories import resolveFilename, SCOPE_CONFIG, fileExists
from Components.Harddisk import harddiskmanager
from Tools.LoadPixmap import LoadPixmap
from copy import copy as copy_copy
from os import path as os_path
from time import localtime, gmtime, strftime, mktime, time
from calendar import timegm

# ConfigElement, the base class of all ConfigElements.

# it stores:
#   value    the current value, usefully encoded.
#            usually a property which retrieves _value,
#            and maybe does some reformatting
#   _value   the value as it's going to be saved in the configfile,
#            though still in non-string form.
#            this is the object which is actually worked on.
#   default  the initial value. If _value is equal to default,
#            it will not be stored in the config file
#   saved_value is a text representation of _value, stored in the config file
#
# and has (at least) the following methods:
#   save()   stores _value into saved_value,
#            (or stores 'None' if it should not be stored)
#   load()   loads _value from saved_value, or loads
#            the default if saved_value is 'None' (default)
#            or invalid.
#
class ConfigElement(object):
	def __init__(self):
		self.extra_args = {}
		self.saved_value = None
		self.save_forced = False
		self.last_value = None
		self.save_disabled = False
		self.__notifiers = None
		self.__notifiers_final = None
		self.enabled = True
		self.callNotifiersOnSaveAndCancel = False

	def getNotifiers(self):
		if self.__notifiers is None:
			self.__notifiers = []
		return self.__notifiers

	def setNotifiers(self, val):
		self.__notifiers = val

	notifiers = property(getNotifiers, setNotifiers)

	def getNotifiersFinal(self):
		if self.__notifiers_final is None:
			self.__notifiers_final = []
		return self.__notifiers_final

	def setNotifiersFinal(self, val):
		self.__notifiers_final = val

	notifiers_final = property(getNotifiersFinal, setNotifiersFinal)

	# you need to override this to do input validation
	def setValue(self, value):
		self._value = value
		self.changed()

	def getValue(self):
		return self._value

	value = property(getValue, setValue)

	# you need to override this if self.value is not a string
	def fromstring(self, value):
		return value

	# you can overide this for fancy default handling
	def load(self):
		sv = self.saved_value
		if sv is None:
			self.value = self.default
		else:
			try:
				self.value = self.fromstring(sv)
			except:
				self.value = self.default

	def tostring(self, value):
		return str(value)

	# you need to override this if str(self.value) doesn't work
	def save(self):
		if self.save_disabled or (self.value == self.default and not self.save_forced):
			self.saved_value = None
		else:
			self.saved_value = self.tostring(self.value)
		if self.callNotifiersOnSaveAndCancel:
			self.changedFinal()  # call none immediate_feedback notifiers, immediate_feedback Notifiers are called as they are chanaged, so do not need to be called here.

	def cancel(self):
		self.load()
		if self.callNotifiersOnSaveAndCancel:
			self.changedFinal()  # call none immediate_feedback notifiers, immediate_feedback Notifiers are called as they are chanaged, so do not need to be called here.

	def isChanged(self):
# NOTE - sv should already be stringified!
#        self.default may be a string or None
#
		sv = self.saved_value
		strv = self.tostring(self.value)
		if sv is None:
			retval = strv != self.tostring(self.default)
		else:
			retval = strv != sv
#debug		if retval:
#debug			print 'orig ConfigElement X (val, tostring(val)):', sv, self.tostring(sv)
		return retval

	def changed(self):
		if self.__notifiers:
			for x in self.notifiers:
				try:
					if self.extra_args[x]:
						x(self, self.extra_args[x])
					else:
						x(self)
				except:
					x(self)

	def changedFinal(self):
		if self.__notifiers_final:
			for x in self.notifiers_final:
				try:
					if self.extra_args[x]:
						x(self, self.extra_args[x])
					else:
						x(self)
				except:
					x(self)

	def addNotifier(self, notifier, initial_call=True, immediate_feedback=True, extra_args=None):
		if not extra_args:
			extra_args = []
		assert callable(notifier), "notifiers must be callable"
		try:
			self.extra_args[notifier] = extra_args
		except:
			pass
		if immediate_feedback:
			self.notifiers.append(notifier)
		else:
			self.notifiers_final.append(notifier)
		# CHECKME:
		# do we want to call the notifier
		#  - at all when adding it? (yes, though optional)
		#  - when the default is active? (yes)
		#  - when no value *yet* has been set,
		#    because no config has ever been read (currently yes)
		#    (though that's not so easy to detect.
		#     the entry could just be new.)
		if initial_call:
			if extra_args:
				notifier(self, extra_args)
			else:
				notifier(self)

	def removeNotifier(self, notifier):
		notifier in self.notifiers and self.notifiers.remove(notifier)
		notifier in self.notifiers_final and self.notifiers_final.remove(notifier)
		try:
			del self.__notifiers[str(notifier)]
		except:
			pass
		try:
			del self.__notifiers_final[str(notifier)]
		except:
			pass

	def clearNotifiers(self):
		self.__notifiers = { }
		self.__notifiers_final = { }

	def disableSave(self):
		self.save_disabled = True

	def __call__(self, selected):
		return self.getMulti(selected)

	def onSelect(self, session):
		pass

	def onDeselect(self, session):
		if not self.last_value == self.value:
			self.last_value = self.value

KEY_LEFT = 0
KEY_RIGHT = 1
KEY_OK = 2
KEY_DELETE = 3
KEY_BACKSPACE = 4
KEY_HOME = 5
KEY_END = 6
KEY_TOGGLEOW = 7
KEY_ASCII = 8
KEY_TIMEOUT = 9
KEY_NUMBERS = range(12, 12 + 10)
KEY_0 = 12
KEY_9 = 12 + 9
KEY_PAGEUP = 12 + 10
KEY_PAGEDOWN = 12 + 11
KEY_PREV = 12 + 12
KEY_NEXT = 12 + 13

def getKeyNumber(key):
	assert key in KEY_NUMBERS
	return key - KEY_0

class choicesList(object):  # XXX: we might want a better name for this
	LIST_TYPE_LIST = 1
	LIST_TYPE_DICT = 2

	def __init__(self, choices, type=None):
		self.choices = choices
		if type is None:
			if isinstance(choices, list):
				self.type = choicesList.LIST_TYPE_LIST
			elif isinstance(choices, dict):
				self.type = choicesList.LIST_TYPE_DICT
			else:
				assert False, "choices must be dict or list!"
		else:
			self.type = type

	def __list__(self):
		if self.type == choicesList.LIST_TYPE_LIST:
			ret = [not isinstance(x, tuple) and x or x[0] for x in self.choices]
		else:
			ret = self.choices.keys()
		return ret or [""]

	def __iter__(self):
		if self.type == choicesList.LIST_TYPE_LIST:
			ret = [not isinstance(x, tuple) and x or x[0] for x in self.choices]
		else:
			ret = self.choices
		return iter(ret or [""])

	def __len__(self):
		return len(self.choices) or 1

	def __getitem__(self, index):
		if self.type == choicesList.LIST_TYPE_LIST:
			ret = self.choices[index]
			if isinstance(ret, tuple):
				ret = ret[0]
			return ret
		return self.choices.keys()[index]

	def index(self, value):
		try:
			return self.__list__().index(value)
		except (ValueError, IndexError):
			# occurs e.g. when default is not in list
			return 0

	def __setitem__(self, index, value):
		if self.type == choicesList.LIST_TYPE_LIST:
			orig = self.choices[index]
			if isinstance(orig, tuple):
				self.choices[index] = (value, orig[1])
			else:
				self.choices[index] = value
		else:
			key = self.choices.keys()[index]
			orig = self.choices[key]
			del self.choices[key]
			self.choices[value] = orig

	def default(self):
		choices = self.choices
		if not choices:
			return ""
		if self.type is choicesList.LIST_TYPE_LIST:
			default = choices[0]
			if isinstance(default, tuple):
				default = default[0]
		else:
			default = choices.keys()[0]
		return default

class descriptionList(choicesList):  # XXX: we might want a better name for this
	def __list__(self):
		if self.type == choicesList.LIST_TYPE_LIST:
			ret = [not isinstance(x, tuple) and x or x[1] for x in self.choices]
		else:
			ret = self.choices.values()
		return ret or [""]

	def __iter__(self):
		return iter(self.__list__())

	def __getitem__(self, index):
		if self.type == choicesList.LIST_TYPE_LIST:
			for x in self.choices:
				if isinstance(x, tuple):
					if x[0] == index:
						return str(x[1])
				elif x == index:
					return str(x)
			return str(index)  # Fallback!
		else:
			return str(self.choices.get(index, ""))

	def __setitem__(self, index, value):
		if self.type == choicesList.LIST_TYPE_LIST:
			i = self.index(index)
			orig = self.choices[i]
			if isinstance(orig, tuple):
				self.choices[i] = (orig[0], value)
			else:
				self.choices[i] = value
		else:
			self.choices[index] = value

#
# ConfigSelection is a "one of.."-type.
# it has the "choices", usually a list, which contains
# (id, desc)-tuples (or just only the ids, in case the id
# will be used as description)
#
# all ids MUST be plain strings.
#
class ConfigSelection(ConfigElement):
	def __init__(self, choices, default=None):
		ConfigElement.__init__(self)
		self.choices = choicesList(choices)

		if default is None:
			default = self.choices.default()

		self._descr = None
		self.default = self._value = self.last_value = default

	def setChoices(self, choices, default=None):
		self.choices = choicesList(choices)

		if default is None:
			default = self.choices.default()
		self.default = default

		if self.value not in self.choices:
			self.value = default

	def setValue(self, value):
		if value in self.choices:
			self._value = value
		else:
			self._value = self.default
		self._descr = None
		self.changed()

	def tostring(self, val):
		return str(val)

	def getValue(self):
		return self._value

	def setCurrentText(self, text):
		i = self.choices.index(self.value)
		self.choices[i] = text
		self._descr = self.description[text] = text
		self._value = text

	value = property(getValue, setValue)

	def getIndex(self):
		return self.choices.index(self.value)

	index = property(getIndex)

	# GUI
	def handleKey(self, key):
		nchoices = len(self.choices)
		if nchoices > 1:
			i = self.choices.index(self.value)
			if key == KEY_LEFT:
				self.value = self.choices[(i + nchoices - 1) % nchoices]
			elif key == KEY_RIGHT:
				self.value = self.choices[(i + 1) % nchoices]
			elif key == KEY_HOME:
				self.value = self.choices[0]
			elif key == KEY_END:
				self.value = self.choices[nchoices - 1]

	def selectNext(self):
		nchoices = len(self.choices)
		i = self.choices.index(self.value)
		self.value = self.choices[(i + 1) % nchoices]

	def getText(self):
		if self._descr is not None:
			return self._descr
		descr = self._descr = self.description[self.value]
		if descr:
			return _(descr)
		return descr

	def getMulti(self, selected):
		if self._descr is not None:
			descr = self._descr
		else:
			descr = self._descr = self.description[self.value]
		if descr:
			return "text", _(descr)
		return "text", descr

	# HTML
	def getHTML(self, id):
		res = ""
		for v in self.choices:
			descr = self.description[v]
			if self.value == v:
				checked = 'checked="checked" '
			else:
				checked = ''
			res += '<input type="radio" name="' + id + '" ' + checked + 'value="' + v + '">' + descr + "</input></br>\n"
		return res

	def unsafeAssign(self, value):
		# setValue does check if value is in choices. This is safe enough.
		self.value = value

	description = property(lambda self: descriptionList(self.choices.choices, self.choices.type))

# a binary decision.
#
# several customized versions exist for different
# descriptions.
#
boolean_descriptions = {False: _("false"), True: _("true")}
class ConfigBoolean(ConfigElement):
	def __init__(self, default=False, descriptions=boolean_descriptions, graphic=True):
		ConfigElement.__init__(self)
		self.descriptions = descriptions
		self.value = self.last_value = self.default = default
		self.graphic = False
		if graphic:
			from skin import switchPixmapInfo
			offInfo = switchPixmapInfo.get('menu_off')
			onInfo = switchPixmapInfo.get('menu_on')
			if offInfo and onInfo:
				falseIcon = LoadPixmap(offInfo.pixmap, cached=True)
				trueIcon = LoadPixmap(onInfo.pixmap, cached=True)
				if falseIcon and trueIcon:
					self.falseIcon = falseIcon
					self.falseAlphatest = offInfo.alphatest
					self.trueIcon = trueIcon
					self.trueAlphatest = onInfo.alphatest
					self.graphic = True

	def handleKey(self, key):
		if key in (KEY_LEFT, KEY_RIGHT):
			self.value = not self.value
		elif key == KEY_HOME:
			self.value = False
		elif key == KEY_END:
			self.value = True

	def getText(self):
		descr = self.descriptions[self.value]
		if descr:
			return _(descr)
		return descr

	def getMulti(self, selected):
		from config import config
		if self.graphic and config.usage.boolean_graphic.value:
			if self.value:
				return ('pixmap', self.trueIcon, self.trueAlphatest)
			else:
				return ('pixmap', self.falseIcon, self.falseAlphatest)
		else:
			return "text", self.getText()

	def tostring(self, value):
		if not value or str(value).lower() == 'false':
			return "False"
		else:
			return "True"

	def fromstring(self, val):
		if str(val).lower() == "true":
			return True
		else:
			return False

	def getHTML(self, id):
		if self.value:
			checked = ' checked="checked"'
		else:
			checked = ''
		return '<input type="checkbox" name="' + id + '" value="1" ' + checked + " />"

	# this is FLAWED. and must be fixed.
	def unsafeAssign(self, value):
		if value == "1":
			self.value = True
		else:
			self.value = False

	def onDeselect(self, session):
		if not self.last_value == self.value:
			self.changedFinal()
			self.last_value = self.value

yes_no_descriptions = {False: _("no"), True: _("yes")}
class ConfigYesNo(ConfigBoolean):
	def __init__(self, default=False):
		ConfigBoolean.__init__(self, default=default, descriptions=yes_no_descriptions)

on_off_descriptions = {False: _("off"), True: _("on")}
class ConfigOnOff(ConfigBoolean):
	def __init__(self, default=False):
		ConfigBoolean.__init__(self, default=default, descriptions=on_off_descriptions)

enable_disable_descriptions = {False: _("disable"), True: _("enable")}
class ConfigEnableDisable(ConfigBoolean):
	def __init__(self, default=False):
		ConfigBoolean.__init__(self, default=default, descriptions=enable_disable_descriptions)

class ConfigDateTime(ConfigElement):
	def __init__(self, default, formatstring, increment=24 * 60 * 60, increment1=0, base=None, to_tm=localtime, from_tm=mktime):
		ConfigElement.__init__(self)
		self.to_tm = to_tm
		self.from_tm = from_tm
		self.increment = increment
		self.increment1 = increment1
		self.base = base
		self.formatstring = formatstring
		self.select_callback = None
		self._allow_invalid = False
		self.value = self.last_value = self.default = int(default)

	def handleKey(self, key):
		if key in (KEY_LEFT, KEY_PREV):
			if self.base is None or self.value >= self.base + self.increment:
				self.value -= self.increment
		elif key in (KEY_RIGHT, KEY_NEXT):
			self.value += self.increment
		elif key == KEY_PAGEDOWN:
			if self.base is None or self.value >= self.base + self.increment1:
				self.value -= self.increment1
		elif key == KEY_PAGEUP:
			self.value += self.increment1
		elif key == KEY_HOME or key == KEY_END:
			self.value = self.default

	def _timestr(self):
		return strftime(self.formatstring, self.to_tm(self.getAdjustedValue()))

	def getAllowInvalid(self):
		return self._allow_invalid

	def setAllowInvalid(self, allow):
		update = not allow and self.allow_invalid
		self._allow_invalid = allow
		if update and self.base is not None and self.value < self.base:
			self.value = self.base

	allow_invalid = property(getAllowInvalid, setAllowInvalid)

	def getText(self):
		if callable(self.formatstring):
			return self.formatstring(self)
		else:
			return self._timestr()

	def getMulti(self, selected):
		return "text", self.getText()

	def fromstring(self, val):
		return int(val)

	def getAdjustedValue(self):
		return self.value

	def unadjustValue(self, value):
		return value

	def setValue(self, value):
		if (self.base is None or self.allow_invalid or value >= self.base) and (not hasattr(self, "_value") or value != self.value):
			super(ConfigDateTime, self).setValue(value)

	def onSelect(self, session):
		if callable(self.select_callback):
			self.select_callback(self, True)

	def onDeselect(self, session):
		if callable(self.select_callback):
			self.select_callback(self, False)

	value = property(ConfigElement.getValue, setValue)

class ClockTime:
	def __init__(self, mainclass, default, timeconv=localtime, durationmode=False):
		self.mainclass = mainclass
		self.base = None
		self._value = self.last_value = self.default = int(default)
		self.clock = ConfigClock(default, timeconv=timeconv, durationmode=durationmode)

	def _timeUpdate(self, conf):
		value = self.getAdjustedValue()
		neg = value < 0
		if neg:
			value = -value
		tm = self.to_tm(value)
		tm = tm[0:3] + tuple(self.clock.value) + tm[5:9]
		newtime = int(self.from_tm(tm))
		if neg:
			newtime = -newtime
		newtime = self.unadjustValue(newtime)
		if newtime != self.value:
			self.value = newtime

	def handleKey(self, key):
		if key in (KEY_LEFT, KEY_RIGHT, KEY_HOME, KEY_END, KEY_ASCII) or key in KEY_NUMBERS:
			self.clock.handleKey(key)
		else:
			self.mainclass.handleKey(self, key)

	def getText(self):
		if callable(self.formatstring):
			return self.formatstring(self)[1]
		else:
			return self._timestr() + self.clock.getText()

	def getMulti(self, selected):
		if callable(self.formatstring):
			return self.formatstring(self, selected)
		else:
			clock = self.clock.getMulti(selected)
			prefix = self._timestr()
			ret = clock[0], prefix + clock[1]
			if len(clock) > 2:
				ret += ([clock[2][0] + len(prefix)], )
			return ret

	def onSelect(self, session):
		self.clock.onSelect(session)
		self.mainclass.onSelect(self, session)

	def onDeselect(self, session):
		self._timeUpdate(self)
		self.clock.onDeselect(session)
		self.mainclass.onDeselect(self, session)

	def setValue(self, value):
		self.mainclass.setValue(self, value)
		tm = self.to_tm(abs(self.getAdjustedValue()))
		newtime = [tm.tm_hour, tm.tm_min]
		if newtime != self.clock.value:
			self.clock.value = [tm.tm_hour, tm.tm_min]

	value = property(ConfigElement.getValue, setValue)

class ConfigClockTime(ClockTime, ConfigDateTime):
	def __init__(self, default, formatstring, increment=24 * 60 * 60, increment1=0, base=None):
		ClockTime.__init__(self, ConfigDateTime, default, durationmode=False)

		ConfigDateTime.__init__(self, default, formatstring, increment=increment, increment1=increment1, base=base)

		self.clock.addNotifier(self._timeUpdate, immediate_feedback=True)

# Duration is implemented as self.value - self.base, so the time
# conversion used is gmtime() on times near the Unix epoch.  That
# means that some strftime conversions don't make much sense.
# %j is hacked so that it appears to return [0-365] instead of [1-366]

class ConfigDuration(ConfigDateTime):
	def __init__(self, default, formatstring, increment=24 * 60 * 60, increment1=0, base=time()):
		super(ConfigDuration, self).__init__(default, formatstring, increment=increment, increment1=increment1, base=base, to_tm=gmtime, from_tm=timegm)

	def getAdjustedValue(self):
		return self.value - self.base

	def unadjustValue(self, value):
		return value + self.base

	def _timestr(self):
		format = self.formatstring.replace("%j", "%%j")
		duration = self.getAdjustedValue()
		sign = ''
		if duration < 0:
			sign = '-'
			duration = -duration
		tm = self.to_tm(duration)
		timestr = strftime(format, tm)
		timestr = timestr.replace("%j", str(tm.tm_yday - 1))
		return sign + timestr

	def getText(self):
		if callable(self.formatstring):
			return self.formatstring(self)[1]
		else:
			return self._timestr()

	def getMulti(self, selected):
		return "text", self.getText()

class ConfigClockDuration(ClockTime, ConfigDuration):
	def __init__(self, default, formatstring, increment=24 * 60 * 60, increment1=0, base=time()):
		assert default > base, "initial time must not be less than base time"

		ClockTime.__init__(self, ConfigDateTime, default - base, timeconv=gmtime, durationmode=True)

		ConfigDuration.__init__(self, default, formatstring, increment=increment, increment1=increment1, base=base)

		self.clock.addNotifier(self._timeUpdate, immediate_feedback=True)


# *THE* mighty config element class
#
# allows you to store/edit a sequence of values.
# can be used for IP-addresses, dates, plain integers, ...
# several helper exist to ease this up a bit.
#
class ConfigSequence(ConfigElement):
	def __init__(self, seperator, limits, default, censor_char=""):
		ConfigElement.__init__(self)
		assert isinstance(limits, list) and len(limits[0]) == 2, "limits must be [(min, max),...]-tuple-list"
		assert censor_char == "" or len(censor_char) == 1, "censor char must be a single char (or \"\")"
		# assert isinstance(default, list), "default must be a list"
		# assert isinstance(default[0], int), "list must contain numbers"
		# assert len(default) == len(limits), "length must match"

		self.marked_pos = 0
		self.seperator = seperator
		self.limits = limits
		self.censor_char = censor_char

		self.last_value = self.default = default
		self.value = copy_copy(default)
		self.endNotifier = None

	def validate(self):
		max_pos = 0
		num = 0
		for i in self._value:
			max_pos += len(str(self.limits[num][1]))

			if self._value[num] < self.limits[num][0]:
				self._value[num] = self.limits[num][0]

			if self._value[num] > self.limits[num][1]:
				self._value[num] = self.limits[num][1]

			num += 1

		if self.marked_pos >= max_pos:
			if self.endNotifier:
				for x in self.endNotifier:
					x(self)
			self.marked_pos = max_pos - 1

		if self.marked_pos < 0:
			self.marked_pos = 0

	def validatePos(self):
		if self.marked_pos < 0:
			self.marked_pos = 0

		total_len = sum([len(str(x[1])) for x in self.limits])

		if self.marked_pos >= total_len:
			self.marked_pos = total_len - 1

	def addEndNotifier(self, notifier):
		if self.endNotifier is None:
			self.endNotifier = []
		self.endNotifier.append(notifier)

	def handleKey(self, key):
		if key == KEY_LEFT:
			self.marked_pos -= 1
			self.validatePos()

		elif key == KEY_RIGHT:
			self.marked_pos += 1
			self.validatePos()

		elif key == KEY_HOME:
			self.marked_pos = 0
			self.validatePos()

		elif key == KEY_END:
			max_pos = 0
			num = 0
			for i in self._value:
				max_pos += len(str(self.limits[num][1]))
				num += 1
			self.marked_pos = max_pos - 1
			self.validatePos()

		elif key in KEY_NUMBERS or key == KEY_ASCII:
			if key == KEY_ASCII:
				code = getPrevAsciiCode()
				if code < 48 or code > 57:
					return
				number = code - 48
			else:
				number = getKeyNumber(key)

			block_len = [len(str(x[1])) for x in self.limits]
			total_len = sum(block_len)

			pos = 0
			blocknumber = 0
			block_len_total = [0, ]
			for x in block_len:
				pos += block_len[blocknumber]
				block_len_total.append(pos)
				if pos - 1 >= self.marked_pos:
					pass
				else:
					blocknumber += 1

			# length of numberblock
			number_len = len(str(self.limits[blocknumber][1]))

			# position in the block
			posinblock = self.marked_pos - block_len_total[blocknumber]

			oldvalue = self._value[blocknumber]
			olddec = oldvalue % 10 ** (number_len - posinblock) - (oldvalue % 10 ** (number_len - posinblock - 1))
			newvalue = oldvalue - olddec + (10 ** (number_len - posinblock - 1) * number)

			self._value[blocknumber] = newvalue
			self.marked_pos += 1

			self.validate()
			self.changed()

	def genText(self):
		value = ""
		mPos = self.marked_pos
		num = 0
		for i in self._value:
			if value:  # fixme no heading separator possible
				value += self.seperator
				if mPos >= len(value) - 1:
					mPos += 1
			if self.censor_char == "":
				value += ("%0" + str(len(str(self.limits[num][1]))) + "d") % i
			else:
				value += (self.censor_char * len(str(self.limits[num][1])))
			num += 1
		return value, mPos

	def getText(self):
		(value, mPos) = self.genText()
		return value

	def getMulti(self, selected):
		(value, mPos) = self.genText()
		# only mark cursor when we are selected
		# (this code is heavily ink optimized!)
		if self.enabled:
			return "mtext"[1 - selected:], value, [mPos]
		else:
			return "text", value

	def tostring(self, val):
		if val:
			return self.seperator.join([self.saveSingle(x) for x in val])
		return None

	def saveSingle(self, v):
		return str(v)

	def fromstring(self, value):
		ret = [int(x) for x in value.split(self.seperator)]
		return ret + [int(x[0]) for x in self.limits[len(ret):]]

	def onDeselect(self, session):
		if self.last_value != self._value:
			self.changedFinal()
			self.last_value = copy_copy(self._value)

ip_limits = [(0, 255), (0, 255), (0, 255), (0, 255)]
class ConfigIP(ConfigSequence):
	def __init__(self, default, auto_jump=False):
		ConfigSequence.__init__(self, seperator=".", limits=ip_limits, default=default)
		self.block_len = [len(str(x[1])) for x in self.limits]
		self.marked_block = 0
		self.overwrite = True
		self.auto_jump = auto_jump

	def handleKey(self, key):
		if key == KEY_LEFT:
			if self.marked_block > 0:
				self.marked_block -= 1
			self.overwrite = True

		elif key == KEY_RIGHT:
			if self.marked_block < len(self.limits) - 1:
				self.marked_block += 1
			self.overwrite = True

		elif key == KEY_HOME:
			self.marked_block = 0
			self.overwrite = True

		elif key == KEY_END:
			self.marked_block = len(self.limits) - 1
			self.overwrite = True

		elif key in KEY_NUMBERS or key == KEY_ASCII:
			if key == KEY_ASCII:
				code = getPrevAsciiCode()
				if code < 48 or code > 57:
					return
				number = code - 48
			else:
				number = getKeyNumber(key)
			oldvalue = self._value[self.marked_block]

			if self.overwrite:
				self._value[self.marked_block] = number
				self.overwrite = False
			else:
				oldvalue *= 10
				newvalue = oldvalue + number
				if self.auto_jump and newvalue > self.limits[self.marked_block][1] and self.marked_block < len(self.limits) - 1:
					self.handleKey(KEY_RIGHT)
					self.handleKey(key)
					return
				else:
					self._value[self.marked_block] = newvalue

			if len(str(self._value[self.marked_block])) >= self.block_len[self.marked_block]:
				self.handleKey(KEY_RIGHT)

			self.validate()
			self.changed()

	def genText(self):
		value = ""
		block_strlen = []
		if self._value:
			for i in self._value:
				block_strlen.append(len(str(i)))
				if value:
					value += self.seperator
				value += str(i)
		leftPos = sum(block_strlen[:self.marked_block]) + self.marked_block
		rightPos = sum(block_strlen[:(self.marked_block + 1)]) + self.marked_block
		mBlock = range(leftPos, rightPos)
		return value, mBlock

	def getMulti(self, selected):
		(value, mBlock) = self.genText()
		if self.enabled:
			return "mtext"[1 - selected:], value, mBlock
		else:
			return "text", value

	def getHTML(self, id):
		# we definitely don't want leading zeros
		return '.'.join(["%d" % d for d in self.value])

mac_limits = [(1, 255), (1, 255), (1, 255), (1, 255), (1, 255), (1, 255)]
class ConfigMAC(ConfigSequence):
	def __init__(self, default):
		ConfigSequence.__init__(self, seperator=":", limits=mac_limits, default=default)

class ConfigMacText(ConfigElement, NumericalTextInput):
	def __init__(self, default="", visible_width=False, show_help=True):
		ConfigElement.__init__(self)
		NumericalTextInput.__init__(self, nextFunc=self.nextFunc, handleTimeout=False)

		self.marked_pos = 0
		self.allmarked = (default != "")
		self.fixed_size = 17
		self.visible_width = visible_width
		self.offset = 0
		self.overwrite = 17
		self.help_window = None
		self.show_help = show_help
		self.value = self.last_value = self.default = default
		self.useableChars = '0123456789ABCDEF'

	def validateMarker(self):
		textlen = len(self.text)
		if self.marked_pos > textlen - 1:
			self.marked_pos = textlen - 1
		elif self.marked_pos < 0:
			self.marked_pos = 0

	def insertChar(self, ch, pos, owr):
		if self.text[pos] == ':':
			pos += 1
		if owr or self.overwrite:
			self.text = self.text[0:pos] + ch + self.text[pos + 1:]
		elif self.fixed_size:
			self.text = self.text[0:pos] + ch + self.text[pos:-1]
		else:
			self.text = self.text[0:pos] + ch + self.text[pos:]

	def handleKey(self, key):
		if key == KEY_LEFT:
			self.timeout()
			if self.allmarked:
				self.marked_pos = len(self.text)
				self.allmarked = False
			else:
				if self.text[self.marked_pos - 1] == ':':
					self.marked_pos -= 2
				else:
					self.marked_pos -= 1
		elif key == KEY_RIGHT:
			self.timeout()
			if self.allmarked:
				self.marked_pos = 0
				self.allmarked = False
			else:
				if self.marked_pos < (len(self.text) - 1):
					if self.text[self.marked_pos + 1] == ':':
						self.marked_pos += 2
					else:
						self.marked_pos += 1
		elif key in KEY_NUMBERS:
			owr = self.lastKey == getKeyNumber(key)
			newChar = self.getKey(getKeyNumber(key))
			self.insertChar(newChar, self.marked_pos, owr)
		elif key == KEY_TIMEOUT:
			self.timeout()
			if self.help_window:
				self.help_window.update(self)
			if self.text[self.marked_pos] == ':':
				self.marked_pos += 1
			return

		if self.help_window:
			self.help_window.update(self)
		self.validateMarker()
		self.changed()

	def nextFunc(self):
		self.marked_pos += 1
		self.validateMarker()
		self.changed()

	def getValue(self):
		try:
			return self.text.encode("utf-8")
		except UnicodeDecodeError:
			print "[Config] Broken UTF8!"
			return self.text

	def setValue(self, val):
		try:
			self.text = val.decode("utf-8")
		except UnicodeDecodeError:
			self.text = val.decode("utf-8", "ignore")
			print "[Config] Broken UTF8!"

	value = property(getValue, setValue)
	_value = property(getValue, setValue)

	def getText(self):
		return self.text.encode("utf-8")

	def getMulti(self, selected):
		if self.visible_width:
			if self.allmarked:
				mark = range(0, min(self.visible_width, len(self.text)))
			else:
				mark = [self.marked_pos - self.offset]
			return "mtext"[1 - selected:], self.text[self.offset:self.offset + self.visible_width].encode("utf-8") + " ", mark
		else:
			if self.allmarked:
				mark = range(0, len(self.text))
			else:
				mark = [self.marked_pos]
			return "mtext"[1 - selected:], self.text.encode("utf-8") + " ", mark

	def onSelect(self, session):
		self.allmarked = (self.value != "")
		if session is not None:
			from Screens.NumericalTextInputHelpDialog import NumericalTextInputHelpDialog
			self.help_window = session.instantiateDialog(NumericalTextInputHelpDialog, self)
			self.help_window.setAnimationMode(0)
			if self.show_help:
				self.help_window.show()

	def onDeselect(self, session):
		self.marked_pos = 0
		self.offset = 0
		if self.help_window:
			session.deleteDialog(self.help_window)
			self.help_window = None
		if not self.last_value == self.value:
			self.changedFinal()
			self.last_value = self.value

	def getHTML(self, id):
		return '<input type="text" name="' + id + '" value="' + self.value + '" /><br>\n'

	def unsafeAssign(self, value):
		self.value = str(value)

class ConfigPosition(ConfigSequence):
	def __init__(self, default, args):
		ConfigSequence.__init__(self, seperator=",", limits=[(0, args[0]), (0, args[1]), (0, args[2]), (0, args[3])], default=default)

clock_limits = [(0, 23), (0, 59)]
class ConfigClock(ConfigSequence):
	def __init__(self, default, timeconv=localtime, durationmode=False):
		self.t = timeconv(default)
		ConfigSequence.__init__(self, seperator=":", limits=clock_limits, default=[self.t.tm_hour, self.t.tm_min])
		if durationmode:
			self.wideformat = False
			self.timeformat = "%_H:%M"
		else:
			self.wideformat = None  # Defer until later
			self.timeformat = None  # Defer until later

	def increment(self):
		# Check if Minutes maxed out
		if self._value[1] == 59:
			# Increment Hour, reset Minutes
			if self._value[0] < 23:
				self._value[0] += 1
			else:
				self._value[0] = 0
			self._value[1] = 0
		else:
			# Increment Minutes
			self._value[1] += 1
		# Trigger change
		self.changed()

	def decrement(self, step=1):
		# Check if Minutes is minimum
		if self._value[1] == 0:
			# Decrement Hour, set Minutes to 59 or 55
			if self._value[0] > 0:
				self._value[0] -= 1
			else:
				self._value[0] = 23
			self._value[1] = 60 - step
		else:
			# Decrement Minutes
			self._value[1] -= step
		# Trigger change
		self.changed()

	def nextStep(self):
		self._value[1] += 5 - self._value[1] % 5 - 1
		self.increment()

	def prevStep(self):
		# Set Minutes to the previous multiple of 5
		step = (4 + self._value[1]) % 5 + 1
		self.decrement(step)

	def handleKey(self, key):
		if self.wideformat is None:
			self.wideformat = config.usage.time.wide.value
		if key == KEY_DELETE and self.wideformat:
			if self._value[0] < 12:
				self._value[0] += 12
				self.validate()
				self.changed()
		elif key == KEY_BACKSPACE and self.wideformat:
			if self._value[0] >= 12:
				self._value[0] -= 12
				self.validate()
				self.changed()
		elif key in KEY_NUMBERS or key == KEY_ASCII:
			if key == KEY_ASCII:
				code = getPrevAsciiCode()
				if code < 48 or code > 57:
					return
				digit = code - 48
			else:
				digit = getKeyNumber(key)

			hour = self._value[0]
			pmadjust = 0
			if self.wideformat:
				if hour > 11:  # All the PM times
					hour -= 12
					pmadjust = 12
				if hour == 0:  # 12AM & 12PM map to 12
					hour = 12
				if self.marked_pos == 0 and digit >= 2:  # Only 0, 1 allowed (12 hour clock)
					return
				if self.marked_pos == 1 and hour > 9 and digit >= 3:  # Only 10, 11, 12 allowed
					return
				if self.marked_pos == 1 and hour < 10 and digit == 0:  # Only 01, 02, ..., 09 allowed
					return
			else:
				if self.marked_pos == 0 and digit >= 3:  # Only 0, 1, 2 allowed (24 hour clock)
					return
				if self.marked_pos == 1 and hour > 19 and digit >= 4:  # Only 20, 21, 22, 23 allowed
					return
			if self.marked_pos == 2 and digit >= 6:  # Only 0, 1, ..., 5 allowed (tens digit of minutes)
				return

			value = bytearray(b"%02d%02d" % (hour, self._value[1]))  # Must be ASCII!
			value[self.marked_pos] = digit + ord(b'0')
			hour = int(value[:2])
			minute = int(value[2:])

			if self.wideformat:
				if hour == 12:  # 12AM & 12PM map to back to 00
					hour = 0
				elif hour > 12:
					hour = 10
				hour += pmadjust
			elif hour > 23:
				hour = 20

			self._value[0] = hour
			self._value[1] = minute
			self.marked_pos += 1
			self.validate()
			self.changed()
		else:
			ConfigSequence.handleKey(self, key)

	def genText(self):
		if self.timeformat is None:
			self.timeformat = config.usage.time.short.value.replace("%-I", "%_I").replace("%-H", "%_H")
		mPos = self.marked_pos
		if mPos >= 2:
			mPos += 1  # Skip over the separator
		newtime = list(self.t)
		newtime[3] = self._value[0]
		newtime[4] = self._value[1]
		value = strftime(self.timeformat, newtime)
		return value, mPos

integer_limits = (0, 9999999999)
class ConfigInteger(ConfigSequence):
	def __init__(self, default, limits=integer_limits):
		ConfigSequence.__init__(self, seperator=":", limits=[limits], default=default)

	# you need to override this to do input validation
	def setValue(self, value):
		self._value = [value]
		self.changed()

	def getValue(self):
		return self._value[0]

	value = property(getValue, setValue)

	def fromstring(self, value):
		return int(value)

	def tostring(self, value):
		return str(value)

class ConfigPIN(ConfigInteger):
	def __init__(self, default, len=4, censor=""):
		assert isinstance(default, int), "ConfigPIN default must be an integer"
		ConfigSequence.__init__(self, seperator=":", limits=[(0, (10 ** len) - 1)], censor_char=censor, default=default)
		self.len = len

	def getLength(self):
		return self.len

class ConfigFloat(ConfigSequence):
	def __init__(self, default, limits):
		ConfigSequence.__init__(self, seperator=".", limits=limits, default=default)

	def getFloat(self):
		return float(self.value[1] / float(self.limits[1][1] + 1) + self.value[0])

	float = property(getFloat)

	def getFloatInt(self):
		return int(self.value[0] * float(self.limits[1][1] + 1) + self.value[1])

	def setFloatInt(self, val):
		self.value[0] = val / float(self.limits[1][1] + 1)
		self.value[1] = val % float(self.limits[1][1] + 1)

	floatint = property(getFloatInt, setFloatInt)

# ### EGAMI
# Normal, LShift(42), RAlt(100), LShift+RAlt(100+42)/LArt(56)
egkeymap_us_de = {
	2: [u"1", u"!", None, None],
	3: [u"2", u"@", None, None],
	4: [u"3", u"#", None, '\xc2\xa3'],
	5: [u"4", u"$", '\xc3\xa7', None],
	6: [u"5", u"%", '\xc3\xbc', '\xe2\x82\xac'],
	7: [u"6", u"^", '\xc3\xb6', None],
	8: [u"7", u"&", '\xc3\xa4', None],
	9: [u"8", u"*", '\xc3\xa0', None],
	10: [u"9", u"(", '\xc3\xa8', None],
	11: [u"0", u")", '\xc3\xa9', None],
	12: [u"-", u"_", None, None],
	13: [u"=", u"+", "~", None],
	16: [u"q", u"Q", None, None],
	17: [u"w", u"W", None, None],
	18: [u"e", u"E", '\xe2\x82\xac', None],
	19: [u"r", u"R", None, None],
	20: [u"t", u"T", None, None],
	21: [u"y", u"Y", None, None],
	22: [u"u", u"U", None, None],
	23: [u"i", u"I", None, None],
	24: [u"o", u"O", None, None],
	25: [u"p", u"P", None, None],
	26: [u"[", u"{", None, None],
	27: [u"]", u"}", None, None],
	30: [u"a", u"A", None, None],
	31: [u"s", u"S", '\xc3\x9f', None],
	32: [u"d", u"D", None, None],
	33: [u"f", u"F", None, None],
	34: [u"g", u"G", None, None],
	35: [u"h", u"H", None, None],
	36: [u"j", u"J", None, None],
	37: [u"k", u"K", None, None],
	38: [u"l", u"L", None, None],
	39: [u";", u":", None, None],
	40: [u"\'", u"\"", None, None],
	41: ['\xc2\xa7', '\xc2\xb0', '\xc2\xac', None],
	43: [u"\\", u"|", None, None],
	44: [u"z", u"Z", None, u"<"],
	45: [u"x", u"X", None, u">"],
	46: [u"c", u"C", '\xc2\xa2', None],
	47: [u"v", u"V", None, None],
	48: [u"b", u"B", None, None],
	49: [u"n", u"N", None, None],
	50: [u"m", u"M", '\xc2\xb5', None],
	51: [u",", "<", None, None],
	52: [u".", ">", None, None],
	53: [u"/", u"?", None, None],
	57: [u" ", None, None, None],
}
egmapidx = 0
egkeymap = egkeymap_us_de
rckeyboard_enable = False
# if file("/proc/stb/info/boxmodel").read().strip() in ["we will add someday keyboard rcusupport for boxtype"]:
# 	rckeyboard_enable = True

def getCharValue(code):
	global egmapidx
	global egkeymap
	global rckeyboard_enable
	print "got ascii code : %d [%d]" % (code, egmapidx)
	if rckeyboard_enable:
		if code == 0:
			egmapidx = 0
			return None
		elif code == 42:
			egmapidx += 1
			return None
		elif code == 56:
			egmapidx += 3
			return None
		elif code == 100:
			egmapidx += 2
			return None
		try:
			return egkeymap[code][egmapidx]
		except:
			return None
	else:
		return unichr(getPrevAsciiCode())
# ### EGAMI

# an editable text...
class ConfigText(ConfigElement, NumericalTextInput):
	def __init__(self, default="", fixed_size=True, visible_width=False, show_help=True):
		ConfigElement.__init__(self)
		NumericalTextInput.__init__(self, nextFunc=self.nextFunc, handleTimeout=False)

		self.marked_pos = 0
		self.allmarked = (default != "")
		self.fixed_size = fixed_size
		self.visible_width = visible_width
		self.offset = 0
		self.overwrite = fixed_size
		self.help_window = None
		self.show_help = show_help
		self.value = self.last_value = self.default = default

	def validateMarker(self):
		textlen = len(self.text)
		if self.fixed_size:
			if self.marked_pos > textlen - 1:
				self.marked_pos = textlen - 1
		else:
			if self.marked_pos > textlen:
				self.marked_pos = textlen
		if self.marked_pos < 0:
			self.marked_pos = 0
		if self.visible_width:
			if self.marked_pos < self.offset:
				self.offset = self.marked_pos
			if self.marked_pos >= self.offset + self.visible_width:
				if self.marked_pos == textlen:
					self.offset = self.marked_pos - self.visible_width
				else:
					self.offset = self.marked_pos - self.visible_width + 1
			if self.offset > 0 and self.offset + self.visible_width > textlen:
				self.offset = max(0, textlen - self.visible_width)

	def insertChar(self, ch, pos, owr):
		if owr or self.overwrite:
			self.text = self.text[0:pos] + ch + self.text[pos + 1:]
		elif self.fixed_size:
			self.text = self.text[0:pos] + ch + self.text[pos:-1]
		else:
			self.text = self.text[0:pos] + ch + self.text[pos:]

	def deleteChar(self, pos):
		if not self.fixed_size:
			self.text = self.text[0:pos] + self.text[pos + 1:]
		elif self.overwrite:
			self.text = self.text[0:pos] + " " + self.text[pos + 1:]
		else:
			self.text = self.text[0:pos] + self.text[pos + 1:] + " "

	def deleteAllChars(self):
		if self.fixed_size:
			self.text = " " * len(self.text)
		else:
			self.text = ""
		self.marked_pos = 0

	def handleKey(self, key):
		# this will no change anything on the value itself
		# so we can handle it here in gui element
		if key == KEY_DELETE:
			self.timeout()
			if self.allmarked:
				self.deleteAllChars()
				self.allmarked = False
			else:
				self.deleteChar(self.marked_pos)
				if self.fixed_size and self.overwrite:
					self.marked_pos += 1
		elif key == KEY_BACKSPACE:
			self.timeout()
			if self.allmarked:
				self.deleteAllChars()
				self.allmarked = False
			elif self.marked_pos > 0:
				self.deleteChar(self.marked_pos - 1)
				if not self.fixed_size and self.offset > 0:
					self.offset -= 1
				self.marked_pos -= 1
		elif key == KEY_LEFT:
			self.timeout()
			if self.allmarked:
				self.marked_pos = len(self.text)
				self.allmarked = False
			else:
				self.marked_pos -= 1
		elif key == KEY_RIGHT:
			self.timeout()
			if self.allmarked:
				self.marked_pos = 0
				self.allmarked = False
			else:
				self.marked_pos += 1
		elif key == KEY_HOME:
			self.timeout()
			self.allmarked = False
			self.marked_pos = 0
		elif key == KEY_END:
			self.timeout()
			self.allmarked = False
			self.marked_pos = len(self.text)
		elif key == KEY_TOGGLEOW:
			self.timeout()
			self.overwrite = not self.overwrite
		elif key == KEY_ASCII:
			self.timeout()
			newChar = unichr(getPrevAsciiCode())
			if not self.useableChars or newChar in self.useableChars:
				if self.allmarked:
					self.deleteAllChars()
					self.allmarked = False
				self.insertChar(newChar, self.marked_pos, False)
				self.marked_pos += 1
		elif key in KEY_NUMBERS:
			owr = self.lastKey == getKeyNumber(key)
			newChar = self.getKey(getKeyNumber(key))
			if self.allmarked:
				self.deleteAllChars()
				self.allmarked = False
			self.insertChar(newChar, self.marked_pos, owr)
		elif key == KEY_TIMEOUT:
			self.timeout()
			if self.help_window:
				self.help_window.update(self)
			return

		if self.help_window:
			self.help_window.update(self)
		self.validateMarker()
		self.changed()

	def nextFunc(self):
		self.marked_pos += 1
		self.validateMarker()
		self.changed()

	def getValue(self):
		try:
			return self.text.encode("utf-8")
		except UnicodeDecodeError:
			print "[Config] Broken UTF8!"
			return self.text

	def setValue(self, val):
		try:
			self.text = val.decode("utf-8")
		except UnicodeDecodeError:
			self.text = val.decode("utf-8", "ignore")
			print "[Config] Broken UTF8!"

	value = property(getValue, setValue)
	_value = property(getValue, setValue)

	def getText(self):
		return self.text.encode("utf-8")

	def getMulti(self, selected):
		if self.visible_width:
			if self.allmarked:
				mark = range(0, min(self.visible_width, len(self.text)))
			else:
				mark = [self.marked_pos - self.offset]
			return "mtext"[1 - selected:], self.text[self.offset:self.offset + self.visible_width].encode("utf-8") + " ", mark
		else:
			if self.allmarked:
				mark = range(0, len(self.text))
			else:
				mark = [self.marked_pos]
			return "mtext"[1 - selected:], self.text.encode("utf-8") + " ", mark

	def onSelect(self, session):
		self.allmarked = (self.value != "")
		if session is not None:
			from Screens.NumericalTextInputHelpDialog import NumericalTextInputHelpDialog
			self.help_window = session.instantiateDialog(NumericalTextInputHelpDialog, self)
			self.help_window.setAnimationMode(0)
			if self.show_help:
				self.help_window.show()

	def onDeselect(self, session):
		self.marked_pos = 0
		self.offset = 0
		if self.help_window:
			session.deleteDialog(self.help_window)
			self.help_window = None
		if not self.last_value == self.value:
			self.changedFinal()
			self.last_value = self.value

	def getHTML(self, id):
		return '<input type="text" name="' + id + '" value="' + self.value + '" /><br>\n'

	def unsafeAssign(self, value):
		self.value = str(value)

class ConfigPassword(ConfigText):
	def __init__(self, default="", fixed_size=False, visible_width=False, censor="*", show_help=True):
		ConfigText.__init__(self, default=default, fixed_size=fixed_size, visible_width=visible_width, show_help=show_help)
		self.censor_char = censor
		self.hidden = True

	def getMulti(self, selected):
		mtext, text, mark = ConfigText.getMulti(self, selected)
		if self.hidden:
			text = len(text) * self.censor_char
		return mtext, text, mark

	def onSelect(self, session):
		ConfigText.onSelect(self, session)
		self.hidden = False

	def onDeselect(self, session):
		ConfigText.onDeselect(self, session)
		self.hidden = True

# lets the user select between [min, min+stepwidth, min+(stepwidth*2)..., maxval] with maxval <= max depending
# on the stepwidth
# min, max, stepwidth, default are int values
# wraparound: pressing RIGHT key at max value brings you to min value and vice versa if set to True
class ConfigSelectionNumber(ConfigSelection):
	def __init__(self, min, max, stepwidth, default=None, wraparound=False):
		self.wraparound = wraparound
		if default is None:
			default = min
		choices = []
		step = min
		while step <= max:
			choices.append(str(step))
			step += stepwidth

		ConfigSelection.__init__(self, choices, default)

		# For detecting repeated keys.
		self.keyTime = 0
		self.keyLast = None

	def getValue(self):
		return int(ConfigSelection.getValue(self))

	def setValue(self, val):
		ConfigSelection.setValue(self, str(val))

	value = property(getValue, setValue)

	def getIndex(self):
		return self.choices.index(self.value)

	index = property(getIndex)

	def handleKey(self, key):
		now = time()
		if key == self.keyLast and now - self.keyTime < 0.25:
			self.keyRepeat += 1
		else:
			self.keyRepeat = 0
		self.keyTime = now
		self.keyLast = key
		nchoices = len(self.choices)
		if nchoices > 1:
			step = 1
			if self.keyRepeat >= 4:
				if not self.keyRepeat & 1: # step every second repeat
					return
				step = 5
			i = self.choices.index(str(self.value))
			if not self.wraparound:
				if key == KEY_RIGHT:
					if i == nchoices - 1:
						return
					if i + step >= nchoices - 1:
						key = KEY_END
				if key == KEY_LEFT:
					if i == 0:
						return
					if i - step <= 0:
						key = KEY_HOME
			if key == KEY_LEFT:
				self.value = self.choices[(i + nchoices - step) % nchoices]
			elif key == KEY_RIGHT:
				self.value = self.choices[(i + step) % nchoices]
			elif key == KEY_HOME:
				self.value = self.choices[0]
			elif key == KEY_END:
				self.value = self.choices[nchoices - 1]

class ConfigNumber(ConfigText):
	def __init__(self, default=0):
		ConfigText.__init__(self, str(default), fixed_size=False)

	def getValue(self):
		try:
			return int(self.text)
		except:
			return 0

	def setValue(self, val):
		self.text = str(val)

	value = property(getValue, setValue)
	_value = property(getValue, setValue)

	def isChanged(self):
# NOTE - sv should already be stringified
#        and self.default should *also* be a string value
		sv = self.saved_value
		strv = self.tostring(self.value)
		if sv is None:
			retval = strv != self.default
		else:
			retval = strv != sv
#debug		if retval:
#debug			print 'orig ConfigNumber X (val, tostring(val)):', sv, self.tostring(sv)
		return retval

	def conform(self):
		pos = len(self.text) - self.marked_pos
		self.text = self.text.lstrip("0")
		if self.text == "":
			self.text = "0"
		if pos > len(self.text):
			self.marked_pos = 0
		else:
			self.marked_pos = len(self.text) - pos

	def handleKey(self, key):
		if key in KEY_NUMBERS or key == KEY_ASCII:
			if key == KEY_ASCII:
				ascii = getPrevAsciiCode()
				if not (48 <= ascii <= 57):
					return
			else:
				ascii = getKeyNumber(key) + 48
			newChar = unichr(ascii)
			if self.allmarked:
				self.deleteAllChars()
				self.allmarked = False
			self.insertChar(newChar, self.marked_pos, False)
			self.marked_pos += 1
		else:
			ConfigText.handleKey(self, key)
		self.conform()

	def onSelect(self, session):
		self.allmarked = (self.value != "")

	def onDeselect(self, session):
		self.marked_pos = 0
		self.offset = 0
		if not self.last_value == self.value:
			self.changedFinal()
			self.last_value = self.value

class ConfigSearchText(ConfigText):
	def __init__(self, default="", fixed_size=False, visible_width=False):
		ConfigText.__init__(self, default=default, fixed_size=fixed_size, visible_width=visible_width)
		NumericalTextInput.__init__(self, nextFunc=self.nextFunc, handleTimeout=False, search=True)

class ConfigDirectory(ConfigText):
	def __init__(self, default="", visible_width=60):
		ConfigText.__init__(self, default, fixed_size=True, visible_width=visible_width)

	def handleKey(self, key):
		pass

	def getValue(self):
		if self.text == "":
			return None
		else:
			return ConfigText.getValue(self)

	def setValue(self, val):
		if val is None:
			val = ""
		ConfigText.setValue(self, val)

	def getMulti(self, selected):
		if self.text == "":
			return "mtext"[1 - selected:], _("List of storage devices"), range(0)
		else:
			return ConfigText.getMulti(self, selected)

	def onSelect(self, session):
		self.allmarked = (self.value != "")

# a slider.
class ConfigSlider(ConfigElement):
	def __init__(self, default=0, increment=1, limits=(0, 100)):
		ConfigElement.__init__(self)
		self.min = limits[0]
		self.max = limits[1]
		self.value = self.last_value = self.default = self.clampValue(default)
		self.increment = increment

	def clampValue(self, value):
		if value < self.min:
			value = self.min
		if value > self.max:
			value = self.max
		return value

	def checkValues(self):
		self.value = self.clampValue(self.value)

	def handleKey(self, key):
		if key == KEY_LEFT:
			self.value -= self.increment
		elif key == KEY_RIGHT:
			self.value += self.increment
		elif key == KEY_HOME:
			self.value = self.min
		elif key == KEY_END:
			self.value = self.max
		else:
			return
		self.checkValues()

	def getText(self):
		return "%d / %d" % (self.value, self.max)

	def getMulti(self, selected):
		self.checkValues()
		return "slider", self.value, self.max

	def fromstring(self, value):
		return int(value)

# a satlist. in fact, it's a ConfigSelection.
class ConfigSatlist(ConfigSelection):
	def __init__(self, list, default=None):
		if default is not None:
			default = str(default)
		ConfigSelection.__init__(self, choices=[(str(orbpos), desc) for (orbpos, desc, flags) in list], default=default)

	def getOrbitalPosition(self):
		if self.value == "":
			return None
		return int(self.value)

	orbital_position = property(getOrbitalPosition)

class ConfigSet(ConfigElement):
	def __init__(self, choices, default=None):
		if not default:
			default = []
		ConfigElement.__init__(self)
		if isinstance(choices, list):
			choices.sort()
			self.choices = choicesList(choices, choicesList.LIST_TYPE_LIST)
		else:
			assert False, "ConfigSet choices must be a list!"
		if default is None:
			default = []
		self.pos = -1
		default.sort()
		self.last_value = self.default = default
		self.value = default[:]

	def toggleChoice(self, choice):
		value = self.value
		if choice in value:
			value.remove(choice)
		else:
			value.append(choice)
			value.sort()
		self.changed()

	def handleKey(self, key):
		if key in KEY_NUMBERS + [KEY_DELETE, KEY_BACKSPACE]:
			if self.pos != -1:
				self.toggleChoice(self.choices[self.pos])
		elif key == KEY_LEFT:
			if self.pos < 0:
				self.pos = len(self.choices) - 1
			else:
				self.pos -= 1
		elif key == KEY_RIGHT:
			if self.pos >= len(self.choices) - 1:
				self.pos = -1
			else:
				self.pos += 1
		elif key in (KEY_HOME, KEY_END):
			self.pos = -1

	def genString(self, lst):
		res = ""
		for x in lst:
			res += self.description[x] + " "
		return res

	def getText(self):
		return self.genString(self.value)

	def getMulti(self, selected):
		if not selected or self.pos == -1:
			return "text", self.genString(self.value)
		else:
			tmp = self.value[:]
			ch = self.choices[self.pos]
			mem = ch in self.value
			if not mem:
				tmp.append(ch)
				tmp.sort()
			ind = tmp.index(ch)
			val1 = self.genString(tmp[:ind])
			val2 = " " + self.genString(tmp[ind + 1:])
			if mem:
				chstr = " " + self.description[ch] + " "
			else:
				chstr = "(" + self.description[ch] + ")"
			len_val1 = len(val1)
			return "mtext", val1 + chstr + val2, range(len_val1, len_val1 + len(chstr))

	def onDeselect(self, session):
		self.pos = -1
		if not self.last_value == self.value:
			self.changedFinal()
			self.last_value = self.value[:]

	def tostring(self, value):
		return str(value)

	def fromstring(self, val):
		return eval(val)

	description = property(lambda self: descriptionList(self.choices.choices, choicesList.LIST_TYPE_LIST))

class ConfigLocations(ConfigElement):
	def __init__(self, default=None, visible_width=False, keep_nonexistent_files=False):
		if not default:
			default = []
		ConfigElement.__init__(self)
		self.visible_width = visible_width
		self.keep_nonexistent_files = keep_nonexistent_files
		self.pos = -1
		self.default = default
		self.locations = []
		self.mountpoints = []
		self.value = default[:]

	def setValue(self, value):
		locations = self.locations
		loc = [x[0] for x in locations if x[3]]
		add = [x for x in value if x not in loc]
		diff = add + [x for x in loc if x not in value]
		locations = [x for x in locations if x[0] not in diff] + [[x, self.getMountpoint(x), True, True] for x in add]
		# locations.sort(key = lambda x: x[0])
		self.locations = locations
		self.changed()

	def getValue(self):
		self.checkChangedMountpoints()
		locations = self.locations
		for x in locations:
			x[3] = x[2]
		return [x[0] for x in locations if x[3]]

	value = property(getValue, setValue)

	def tostring(self, value):
		return str(value)

	def fromstring(self, val):
		return eval(val)

	def load(self):
		sv = self.saved_value
		if sv is None:
			tmp = self.default
		else:
			tmp = self.fromstring(sv)
		locations = [[x, None, False, False] for x in tmp]
		self.refreshMountpoints()
		for x in locations:
			if self.keep_nonexistent_files or fileExists(x[0]):
				x[1] = self.getMountpoint(x[0])
				x[2] = True
		self.locations = locations

	def save(self):
		location_str = self.tostring([x[0] for x in self.locations])
		if self.save_disabled or (location_str == self.tostring(self.default) and not self.save_forced):
			self.saved_value = None
		else:
			self.saved_value = location_str
		if self.callNotifiersOnSaveAndCancel:
			self.changedFinal()

	def isChanged(self):
		sv = self.saved_value
		locations = self.locations
		if sv is None:
			if self.default is not None:
				sv = self.tostring(self.default)
			else:
				return False
		retval = self.tostring([x[0] for x in locations]) != sv
#debug		if retval:
#debug			print 'orig ConfigLocations X (val):', sv
		return retval

	def addedMount(self, mp):
		for x in self.locations:
			if x[1] == mp:
				x[2] = True
			elif x[1] is None and fileExists(x[0]):
				x[1] = self.getMountpoint(x[0])
				x[2] = True

	def removedMount(self, mp):
		for x in self.locations:
			if x[1] == mp:
				x[2] = False

	def refreshMountpoints(self):
		self.mountpoints = [p.mountpoint for p in harddiskmanager.getMountedPartitions() if p.mountpoint != "/"]
		self.mountpoints.sort(key=lambda x: -len(x))

	def checkChangedMountpoints(self):
		oldmounts = self.mountpoints
		self.refreshMountpoints()
		newmounts = self.mountpoints
		if oldmounts == newmounts:
			return
		for x in oldmounts:
			if x not in newmounts:
				self.removedMount(x)
		for x in newmounts:
			if x not in oldmounts:
				self.addedMount(x)

	def getMountpoint(self, file):
		file = os_path.realpath(file) + "/"
		for m in self.mountpoints:
			if file.startswith(m):
				return m
		return None

	def handleKey(self, key):
		if key == KEY_LEFT:
			self.pos -= 1
			if self.pos < -1:
				self.pos = len(self.value) - 1
		elif key == KEY_RIGHT:
			self.pos += 1
			if self.pos >= len(self.value):
				self.pos = -1
		elif key in (KEY_HOME, KEY_END):
			self.pos = -1

	def getText(self):
		return " ".join(self.value)

	def getMulti(self, selected):
		if not selected:
			valstr = " ".join(self.value)
			if self.visible_width and len(valstr) > self.visible_width:
				return "text", valstr[0:self.visible_width]
			else:
				return "text", valstr
		else:
			i = 0
			valstr = ""
			ind1 = 0
			ind2 = 0
			for val in self.value:
				if i == self.pos:
					ind1 = len(valstr)
				valstr += str(val) + " "
				if i == self.pos:
					ind2 = len(valstr)
				i += 1
			if self.visible_width and len(valstr) > self.visible_width:
				if ind1 + 1 < self.visible_width / 2:
					off = 0
				else:
					off = min(ind1 + 1 - self.visible_width / 2, len(valstr) - self.visible_width)
				return "mtext", valstr[off:off + self.visible_width], range(ind1 - off, ind2 - off)
			else:
				return "mtext", valstr, range(ind1, ind2)

	def onDeselect(self, session):
		self.pos = -1

# nothing.
class ConfigNothing(ConfigSelection):
	def __init__(self):
		ConfigSelection.__init__(self, choices=[("", "")])

# until here, 'saved_value' always had to be a *string*.
# now, in ConfigSubsection, and only there, saved_value
# is a dict, essentially forming a tree.
#
# config.foo.bar=True
# config.foobar=False
#
# turns into:
# config.saved_value == {"foo": {"bar": "True"}, "foobar": "False"}
#

class ConfigSubsectionContent(object):
	pass

# we store a backup of the loaded configuration
# data in self.stored_values, to be able to deploy
# them when a new config element will be added,
# so non-default values are instantly available

# A list, for example:
# config.dipswitches = ConfigSubList()
# config.dipswitches.append(ConfigYesNo())
# config.dipswitches.append(ConfigYesNo())
# config.dipswitches.append(ConfigYesNo())
class ConfigSubList(list, object):
	def __init__(self):
		list.__init__(self)
		self.stored_values = {}

	def save(self):
		for x in self:
			x.save()

	def load(self):
		for x in self:
			x.load()

	def getSavedValue(self):
		res = {}
		for i, val in enumerate(self):
			sv = val.saved_value
			if sv is not None:
				res[str(i)] = sv
		return res

	def setSavedValue(self, values):
		self.stored_values = dict(values)
		for (key, val) in self.stored_values.items():
			if int(key) < len(self):
				self[int(key)].saved_value = val

	saved_value = property(getSavedValue, setSavedValue)

	def append(self, item):
		i = str(len(self))
		list.append(self, item)
		if i in self.stored_values:
			item.saved_value = self.stored_values[i]
			item.load()

	def dict(self):
		return dict([(str(index), value) for index, value in enumerate(self)])

# same as ConfigSubList, just as a dictionary.
# care must be taken that the 'key' has a proper
# str() method, because it will be used in the config
# file.
class ConfigSubDict(dict, object):
	def __init__(self):
		dict.__init__(self)
		self.stored_values = {}

	def save(self):
		for x in self.values():
			x.save()

	def load(self):
		for x in self.values():
			x.load()

	def getSavedValue(self):
		res = {}
		for (key, val) in self.items():
			sv = val.saved_value
			if sv is not None:
				res[str(key)] = sv
		return res

	def setSavedValue(self, values):
		self.stored_values = dict(values)
		for (key, val) in self.items():
			if str(key) in self.stored_values:
				val.saved_value = self.stored_values[str(key)]

	saved_value = property(getSavedValue, setSavedValue)

	def __setitem__(self, key, item):
		dict.__setitem__(self, key, item)
		if str(key) in self.stored_values:
			item.saved_value = self.stored_values[str(key)]
			item.load()

	def dict(self):
		return self

# Like the classes above, just with a more "native"
# syntax.
#
# some evil stuff must be done to allow instant
# loading of added elements. this is why this class
# is so complex.
#
# we need the 'content' because we overwrite
# __setattr__.
# If you don't understand this, try adding
# __setattr__ to a usual exisiting class and you will.
class ConfigSubsection(object):
	def __init__(self):
		self.__dict__["content"] = ConfigSubsectionContent()
		self.content.items = {}
		self.content.stored_values = {}

	def __setattr__(self, name, value):
		if name == "saved_value":
			return self.setSavedValue(value)
		assert isinstance(value, (ConfigSubsection, ConfigElement, ConfigSubList, ConfigSubDict)), "ConfigSubsections can only store ConfigSubsections, ConfigSubLists, ConfigSubDicts or ConfigElements"
		content = self.content
		content.items[name] = value
		x = content.stored_values.get(name, None)
		if x is not None:
			# print "ok, now we have a new item,", name, "and have the following value for it:", x
			value.saved_value = x
			value.load()

	def __getattr__(self, name):
		if name in self.content.items:
			return self.content.items[name]
		raise AttributeError(name)

	def getSavedValue(self):
		res = self.content.stored_values
		for (key, val) in self.content.items.items():
			sv = val.saved_value
			if sv is not None:
				res[key] = sv
			elif key in res:
				del res[key]
		return res

	def setSavedValue(self, values):
		values = dict(values)
		self.content.stored_values = values
		for (key, val) in self.content.items.items():
			value = values.get(key, None)
			if value is not None:
				val.saved_value = value

	saved_value = property(getSavedValue, setSavedValue)

	def save(self):
		for x in self.content.items.values():
			x.save()

	def load(self):
		for x in self.content.items.values():
			x.load()

	def dict(self):
		return self.content.items

# This converts old timezone settings string to the new two tier format.
# The conversion table only contains Australian zones - OpenViX are not
# interested in providing backwards compatibility.
# If the old string is not found, the defaults are used instead.
def convertOldTimezone(old_name):
	old_zones = {
		"(GMT+08:00) Perth": ("Australia", "Perth"),
		"(GMT+09:30) Adelaide": ("Australia", "Adelaide"),
		"(GMT+09:30) Darwin": ("Australia", "Darwin"),
		"(GMT+10:00) Brisbane": ("Australia", "Brisbane"),
		"(GMT+10:00) Canberra, Melbourne, Sydney": ("Australia", "Sydney"),
		"(GMT+10:00) Hobart": ("Australia", "Hobart"),
	}

	return old_zones.get(old_name, ("Australia", "Sydney"))

# the root config object, which also can "pickle" (=serialize)
# down the whole config tree.
#
# we try to keep non-existing config entries, to apply them whenever
# a new config entry is added to a subsection
# also, non-existing config entries will be saved, so they won't be
# lost when a config entry disappears.
class Config(ConfigSubsection):
	def __init__(self):
		ConfigSubsection.__init__(self)

	def pickle_this(self, prefix, topickle, result):
		for (key, val) in sorted(topickle.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0].lower()):
			name = '.'.join((prefix, key))
			if isinstance(val, dict):
				self.pickle_this(name, val, result)
			elif isinstance(val, tuple):
				result += [name, '=', str(val[0]), '\n']
			else:
				result += [name, '=', str(val), '\n']

	def pickle(self):
		result = []
		self.pickle_this("config", self.saved_value, result)
		return ''.join(result)

	def unpickle(self, lines, base_file=True):
		tree = {}
		configbase = tree.setdefault("config", {})
		for l in lines:
			if not l or l[0] == '#':
				continue

			result = l.split('=', 1)
			if len(result) != 2:
				continue
			(name, val) = result
			val = val.strip()

			names = name.split('.')
			base = configbase

			for n in names[1:-1]:
				base = base.setdefault(n, {})

			base[names[-1]] = val

			if not base_file:  # not the initial config file..
				# update config.x.y.value when exist
				try:
					configEntry = eval(name)
					if configEntry is not None:
						configEntry.value = val
				except (SyntaxError, KeyError):
					pass

		# we inherit from ConfigSubsection, so ...
		# object.__setattr__(self, "saved_value", tree["config"])
		if "config" in tree:
			self.setSavedValue(tree["config"])

	def saveToFile(self, filename):
		text = self.pickle()
		try:
			import os
			f = open(filename + ".writing", "w")
			f.write(text)
			f.flush()
			os.fsync(f.fileno())
			f.close()
			os.rename(filename + ".writing", filename)
		except IOError:
			print "[Config] Couldn't write %s" % filename

	def loadFromFile(self, filename, base_file=True):
		lines = open(filename, "r")
		lines = self.upgradeOldSettings(lines)

		self.unpickle(lines, base_file)

	def upgradeOldSettings(self, lines):
		result = []
		for line in lines:
			if line.startswith("config.timezone.val=("):
				area, val = convertOldTimezone(line.strip().split("=")[1])
				result.append("config.timezone.area=%s" % area)
				result.append("config.timezone.val=%s" % val)
			else:
				result.append(line)
		return result

config = Config()
config.misc = ConfigSubsection()

class ConfigFile:
	def __init__(self):
		pass

	CONFIG_FILE = resolveFilename(SCOPE_CONFIG, "settings")

	def load(self):
		try:
			config.loadFromFile(self.CONFIG_FILE, True)
			print "[Config] Config file loaded ok..."
		except IOError, e:
			print "[Config] unable to load config (%s), assuming defaults..." % str(e)

	def save(self):
		# config.save()
		config.saveToFile(self.CONFIG_FILE)

	def __resolveValue(self, pickles, cmap):
		key = pickles[0]
		if key in cmap:
			if len(pickles) > 1:
				return self.__resolveValue(pickles[1:], cmap[key].dict())
			else:
				return str(cmap[key].value)
		return None

	def getResolvedKey(self, key):
		names = key.split('.')
		if len(names) > 1:
			if names[0] == "config":
				ret = self.__resolveValue(names[1:], config.content.items)
				if ret and len(ret):
					return ret
		print "[Config] getResolvedKey", key, "empty variable."
		return ""

def NoSave(element):
	element.disableSave()
	return element

configfile = ConfigFile()

configfile.load()

def getConfigListEntry(*args):
	assert len(args) > 1, "getConfigListEntry needs a minimum of two arguments (descr, configElement)"
	return args

def updateConfigElement(element, newelement):
	newelement.value = element.value
	return newelement

# def _(x):
# 	return x
#
# config.bla = ConfigSubsection()
# config.bla.test = ConfigYesNo()
# config.nim = ConfigSubList()
# config.nim.append(ConfigSubsection())
# config.nim[0].bla = ConfigYesNo()
# config.nim.append(ConfigSubsection())
# config.nim[1].bla = ConfigYesNo()
# config.nim[1].blub = ConfigYesNo()
# config.arg = ConfigSubDict()
# config.arg["Hello"] = ConfigYesNo()
#
# config.arg["Hello"].handleKey(KEY_RIGHT)
# config.arg["Hello"].handleKey(KEY_RIGHT)
#
# #config.saved_value
#
# #configfile.save()
# config.save()
# print config.pickle()

cec_limits = [(0, 15), (0, 15), (0, 15), (0, 15)]
class ConfigCECAddress(ConfigSequence):
	def __init__(self, default, auto_jump=False):
		ConfigSequence.__init__(self, seperator=".", limits=cec_limits, default=default)
		self.block_len = [len(str(x[1])) for x in self.limits]
		self.marked_block = 0
		self.overwrite = True
		self.auto_jump = auto_jump

	def handleKey(self, key):
		if key == KEY_LEFT:
			if self.marked_block > 0:
				self.marked_block -= 1
			self.overwrite = True

		elif key == KEY_RIGHT:
			if self.marked_block < len(self.limits) - 1:
				self.marked_block += 1
			self.overwrite = True

		elif key == KEY_HOME:
			self.marked_block = 0
			self.overwrite = True

		elif key == KEY_END:
			self.marked_block = len(self.limits) - 1
			self.overwrite = True

		elif key in KEY_NUMBERS or key == KEY_ASCII:
			if key == KEY_ASCII:
				code = getPrevAsciiCode()
				if code < 48 or code > 57:
					return
				number = code - 48
			else:
				number = getKeyNumber(key)
			oldvalue = self._value[self.marked_block]

			if self.overwrite:
				self._value[self.marked_block] = number
				self.overwrite = False
			else:
				oldvalue *= 10
				newvalue = oldvalue + number
				if self.auto_jump and newvalue > self.limits[self.marked_block][1] and self.marked_block < len(self.limits) - 1:
					self.handleKey(KEY_RIGHT)
					self.handleKey(key)
					return
				else:
					self._value[self.marked_block] = newvalue

			if len(str(self._value[self.marked_block])) >= self.block_len[self.marked_block]:
				self.handleKey(KEY_RIGHT)

			self.validate()
			self.changed()

	def genText(self):
		value = ""
		block_strlen = []
		for i in self._value:
			block_strlen.append(len(str(i)))
			if value:
				value += self.seperator
			value += str(i)
		leftPos = sum(block_strlen[:self.marked_block]) + self.marked_block
		rightPos = sum(block_strlen[:(self.marked_block + 1)]) + self.marked_block
		mBlock = range(leftPos, rightPos)
		return value, mBlock

	def getMulti(self, selected):
		(value, mBlock) = self.genText()
		if self.enabled:
			return "mtext"[1 - selected:], value, mBlock
		else:
			return "text", value

	def getHTML(self, id):
		# we definitely don't want leading zeros
		return '.'.join(["%d" % d for d in self.value])
