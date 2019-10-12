#ifndef __egami_h
#define __egami_h

class eEGAMI
{
	static eEGAMI *instance;

	int fd;
#ifdef SWIG
	eEGAMI();
	~eEGAMI();
#endif
public:
#ifndef SWIG
	eEGAMI();
	~eEGAMI();
#endif
	static eEGAMI *getInstance();
	bool detected() { return fd >= 0; }
	void readEmuName(int val);						//0=Enable 1=Disable
	void readEcmFile(int val);						//0=Enable 1=Disable
	void AddonsURL(int val);				//0=Enable 1=Disable
	void d1(int val);
	void checkkernel(int val);
	void read_file(int val);
  void file_exists(int val);
  void sendCommandToEmud(int val);
  void ReadProcEntry(int val);
  void e3(int val);
  void fileExists(int val);
  void endsWith(int val);
  void startsWith(int val);
  void c(int val);
};

#endif
