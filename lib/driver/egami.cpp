#include <lib/driver/egami.h>

#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>

#include <lib/base/eerror.h>

#define IOCTL_SET_CHANNEL		0
#define IOCTL_SET_TESTMODE		1
#define IOCTL_SET_SOUNDENABLE		2
#define IOCTL_SET_SOUNDSUBCARRIER	3
#define IOCTL_SET_FINETUNE		4
#define IOCTL_SET_STANDBY		5

eEGAMI *eEGAMI::instance = 0;

eEGAMI::eEGAMI()
{
	ASSERT(!instance);
	instance = this;

	fd = open("/proc/stb/info/vumodel", O_RDWR);
	if (fd < 0)
		eDebug("[eEGAMI] couldnt open /proc/stb/info/vumodel: %m");
}

eEGAMI::~eEGAMI()
{
	if(fd >= 0)
		close(fd);
}

eEGAMI *eEGAMI::getInstance()
{
	return instance;
}

void eEGAMI::readEmuName(int val)		//0=Enable 1=Disable
{
	ioctl(fd, IOCTL_SET_STANDBY, &val);
}

void eEGAMI::readEcmFile(int val)		//0=Enable 1=Disable
{
	ioctl(fd, IOCTL_SET_TESTMODE, &val);
}

void eEGAMI::AddonsURL(int val)		//0=Enable 1=Disable
{
	ioctl(fd, IOCTL_SET_SOUNDENABLE, &val);
}

void eEGAMI::d1(int val)
{
	ioctl(fd, IOCTL_SET_SOUNDSUBCARRIER, &val);
}

void eEGAMI::checkkernel(int val)
{
	ioctl(fd, IOCTL_SET_CHANNEL, &val);
}

void eEGAMI::read_file(int val)
{
	ioctl(fd, IOCTL_SET_FINETUNE, &val);
}

void eEGAMI::file_exists(int val)
{
	ioctl(fd, IOCTL_SET_FINETUNE, &val);
}

void eEGAMI::sendCommandToEmud(int val)
{
	ioctl(fd, IOCTL_SET_FINETUNE, &val);
}

void eEGAMI::ReadProcEntry(int val)
{
	ioctl(fd, IOCTL_SET_FINETUNE, &val);
}

void eEGAMI::e3(int val)
{
	ioctl(fd, IOCTL_SET_FINETUNE, &val);
}

void eEGAMI::fileExists(int val)
{
	ioctl(fd, IOCTL_SET_FINETUNE, &val);
}

void eEGAMI::endsWith(int val)
{
	ioctl(fd, IOCTL_SET_FINETUNE, &val);
}

void eEGAMI::startsWith(int val)
{
	ioctl(fd, IOCTL_SET_FINETUNE, &val);
}

void eEGAMI::c(int val)
{
	ioctl(fd, IOCTL_SET_FINETUNE, &val);
}

//FIXME: correct "run/startlevel"
//eAutoInitP0<eRFmod> init_rfmod(eAutoInitNumbers::rc, "UHF Modulator");
