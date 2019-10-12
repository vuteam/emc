#ifndef __lib_gui_eframe_h
#define __lib_gui_eframe_h

#include <lib/gui/elabel.h>
#include <lib/python/connections.h>

class eFrame: public eLabel
{
public:
	eFrame(eWidget *parent);
	PSignal0<void> selected;

	void push();
        void setFrameSize();
        void setFrameOffset();
protected:
	int event(int event, void *data=0, void *data2=0);
};

#endif
