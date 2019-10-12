#ifndef __lib_gui_ebar_h
#define __lib_gui_ebar_h

#include <lib/gui/elabel.h>
#include <lib/python/connections.h>

class eBar: public eLabel
{
public:
	eBar(eWidget *parent);
	PSignal0<void> selected;

	void push();
protected:
	int event(int event, void *data=0, void *data2=0);
};

#endif
