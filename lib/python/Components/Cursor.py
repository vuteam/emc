# uncompyle6 version 3.3.5
# Python bytecode 2.7 (62211)
# Decompiled from: Python 2.7.15+ (default, Oct  7 2019, 17:39:04) 
# [GCC 7.4.0]
# Embedded file name: /usr/lib/enigma2/python/Components/Cursor.py
# Compiled at: 2019-08-06 09:17:26
from HTMLComponent import HTMLComponent
from GUIComponent import GUIComponent
from VariableText import VariableText
from skin import parseSize
from enigma import eCursor, eSize

class Cursor(VariableText, HTMLComponent, GUIComponent):

    def __init__(self, text='', onClick=[]):
        GUIComponent.__init__(self)
        VariableText.__init__(self)
        self.setText(text)
        self.onClick = onClick
        self.onAnimationEnd = []
        self.skinSize = eSize(0, 0)

    def applySkin(self, desktop, screen):
        if self.skinAttributes is not None:
            attribs = []
            for attrib, value in self.skinAttributes:
                if attrib == 'size':
                    self.skinSize = parseSize(value, ((1, 1), (1, 1)))
                attribs.append((attrib, value))

            self.skinAttributes = attribs
        return GUIComponent.applySkin(self, desktop, screen)

    def push(self):
        for x in self.onClick:
            x()

    def animationEnd(self):
        for f in self.onAnimationEnd:
            f()

    def disable(self):
        pass

    def enable(self):
        pass

    def produceHTML(self):
        return '<input type="submit" text="' + self.getText() + '">\n'

    GUI_WIDGET = eCursor

    def postWidgetCreate(self, instance):
        instance.setText(self.text)
        instance.selected.get().append(self.push)
        instance.animationEnd.get().append(self.animationEnd)

    def preWidgetRemove(self, instance):
        instance.selected.get().remove(self.push)
        instance.animationEnd.get().remove(self.animationEnd)

    def getSkinSize(self):
        return self.skinSize
# okay decompiling Cursor.pyo
