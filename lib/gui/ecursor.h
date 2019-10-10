#ifndef __lib_gui_ecursor_h
#define __lib_gui_ecursor_h

#include <lib/gui/elabel.h>
#include <lib/python/connections.h>

class eCursor: public eLabel
{
public:
	eCursor(eWidget *parent);
	PSignal0<void> selected;

	void push();
protected:
	int event(int event, void *data=0, void *data2=0);
};

#endif
