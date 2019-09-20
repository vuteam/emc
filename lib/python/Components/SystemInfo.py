from os import path
from enigma import eDVBResourceManager, Misc_Options
from Tools.Directories import fileExists, fileCheck
from Tools.HardwareInfo import HardwareInfo

from boxbranding import getMachineName, getImageDistro
from boxbranding import getBoxType, getMachineBuild, getDisplayType, getHaveRCA, getHaveDVI, getHaveYUV, getHaveSCART, getHaveAVJACK, getHaveSCARTYUV, getHaveHDMI

SystemInfo = {}

# FIXMEE...
def getNumVideoDecoders():
	idx = 0
	while fileExists("/dev/dvb/adapter0/video%d" % idx, 'f'):
		idx += 1
	return idx

SystemInfo["NumVideoDecoders"] = getNumVideoDecoders()
SystemInfo["PIPAvailable"] = SystemInfo["NumVideoDecoders"] > 1
SystemInfo["CanMeasureFrontendInputPower"] = eDVBResourceManager.getInstance().canMeasureFrontendInputPower()


def countFrontpanelLEDs():
	leds = 0
	if fileExists("/proc/stb/fp/led_set_pattern"):
		leds += 1
	while fileExists("/proc/stb/fp/led%d_pattern" % leds):
		leds += 1
	return leds

SystemInfo["IPTVSTB"] = getMachineName() in ('T-pod', )
SystemInfo["FrontpanelDisplay"] = fileExists("/dev/dbox/oled0") or fileExists("/dev/dbox/lcd0")
SystemInfo["7segment"] = getDisplayType() in ('7segment', )
SystemInfo["ConfigDisplay"] = SystemInfo["FrontpanelDisplay"] and not SystemInfo["7segment"]
SystemInfo["LCDSKINSetup"] = path.exists("/usr/share/enigma2/display") and not SystemInfo["7segment"]
SystemInfo["12V_Output"] = Misc_Options.getInstance().detected_12V_output()
SystemInfo["ZapMode"] = getImageDistro() != "beyonwiz" and (fileCheck("/proc/stb/video/zapmode") or fileCheck("/proc/stb/video/zapping_mode"))
SystemInfo["NumFrontpanelLEDs"] = countFrontpanelLEDs()
SystemInfo["FrontpanelDisplay"] = (fileExists("/dev/dbox/oled0") or fileExists("/dev/dbox/lcd0")) and getMachineBuild() != 'inihde2'
SystemInfo["OledDisplay"] = fileExists("/dev/dbox/oled0") and getMachineBuild() != 'inihde2'
SystemInfo["LcdDisplay"] = fileExists("/dev/dbox/lcd0") or getMachineBuild() in ('inihde', 'inihdx')
SystemInfo["FBLCDDisplay"] = fileCheck("/proc/stb/fb/sd_detach")
SystemInfo["DisplayLED"] = getBoxType() in ('gb800se', 'gb800solo', 'gbx1', 'gbx3')
SystemInfo["LEDButtons"] = getBoxType() == 'vuultimo'
SystemInfo["DeepstandbySupport"] = HardwareInfo().has_deepstandby()
SystemInfo["Fan"] = fileCheck("/proc/stb/fp/fan")
SystemInfo["FanPWM"] = SystemInfo["Fan"] and fileCheck("/proc/stb/fp/fan_pwm")
SystemInfo["StandbyLED"] = fileCheck("/proc/stb/power/standbyled")
SystemInfo["PowerLed"] = fileExists("/proc/stb/power/powerled")
SystemInfo["StandbyPowerLed"] = fileExists("/proc/stb/power/standbyled")
SystemInfo["SuspendPowerLed"] = fileExists("/proc/stb/power/suspendled")
SystemInfo["LedPowerColor"] = fileExists("/proc/stb/fp/ledpowercolor")
SystemInfo["LedStandbyColor"] = fileExists("/proc/stb/fp/ledstandbycolor")
SystemInfo["LedSuspendColor"] = fileExists("/proc/stb/fp/ledsuspendledcolor")
SystemInfo["Power4x7On"] = fileExists("/proc/stb/fp/power4x7on")
SystemInfo["Power4x7Standby"] = fileExists("/proc/stb/fp/power4x7standby")
SystemInfo["Power4x7Suspend"] = fileExists("/proc/stb/fp/power4x7suspend")
SystemInfo["LEDButtons"] = getBoxType() == 'vuultimo'
SystemInfo["WakeOnLAN"] = getBoxType() not in ('et8000', 'et10000') and fileCheck("/proc/stb/power/wol") or fileCheck("/proc/stb/fp/wol")
SystemInfo["HDMICEC"] = (fileExists("/dev/hdmi_cec") or fileExists("/dev/misc/hdmi_cec0")) and fileExists("/usr/lib/enigma2/python/Plugins/SystemPlugins/HdmiCEC/plugin.pyo")
SystemInfo["SABSetup"] = fileExists("/usr/lib/enigma2/python/Plugins/SystemPlugins/SABnzbd/plugin.pyo")
SystemInfo["SeekStatePlay"] = False
SystemInfo["GraphicLCD"] = getMachineBuild() == "inihdp" or getBoxType() == "vuultimo"
SystemInfo["Blindscan"] = fileExists("/usr/lib/enigma2/python/Plugins/SystemPlugins/Blindscan/plugin.pyo")
SystemInfo["Satfinder"] = fileExists("/usr/lib/enigma2/python/Plugins/SystemPlugins/Satfinder/plugin.pyo")
SystemInfo["HasExternalPIP"] = getMachineBuild() not in ('et9x00', 'et6x00', 'et5x00') and fileCheck("/proc/stb/vmpeg/1/external")
SystemInfo["VideoDestinationConfigurable"] = fileExists("/proc/stb/vmpeg/0/dst_left")
SystemInfo["hasPIPVisibleProc"] = fileCheck("/proc/stb/vmpeg/1/visible")
SystemInfo["VFD_scroll_repeats"] = getBoxType() not in ('et8500', ) and getMachineBuild() not in ('inihde2', ) and fileCheck("/proc/stb/lcd/scroll_repeats")
SystemInfo["VFD_scroll_delay"] = getBoxType() not in ('et8500', ) and getMachineBuild() not in ('inihde2', ) and fileCheck("/proc/stb/lcd/scroll_delay")
SystemInfo["VFD_initial_scroll_delay"] = getBoxType() not in ('et8500', ) and getMachineBuild() not in ('inihde2', ) and fileCheck("/proc/stb/lcd/initial_scroll_delay")
SystemInfo["VFD_final_scroll_delay"] = getBoxType() not in ('et8500', ) and getMachineBuild() not in ('inihde2', ) and fileCheck("/proc/stb/lcd/final_scroll_delay")
SystemInfo["LcdLiveTV"] = fileCheck("/proc/stb/fb/sd_detach") or fileCheck("/proc/stb/lcd/live_enable")
SystemInfo["LCDMiniTV"] = fileExists("/proc/stb/lcd/mode")
SystemInfo["LCDMiniTVPiP"] = SystemInfo["LCDMiniTV"] and getBoxType() != 'gb800ueplus'
SystemInfo["3DMode"] = fileCheck("/proc/stb/fb/3dmode") or fileCheck("/proc/stb/fb/primary/3d")
SystemInfo["3DZNorm"] = fileCheck("/proc/stb/fb/znorm") or fileCheck("/proc/stb/fb/primary/zoffset")
SystemInfo["CanUse3DModeChoices"] = fileExists('/proc/stb/fb/3dmode_choices') and True or False
SystemInfo["HaveMultiBoot"] = (fileCheck("/boot/STARTUP") or fileCheck("/boot/cmdline.txt"))
SystemInfo["HaveMultiBootHD"] = fileCheck("/boot/STARTUP") and getMachineBuild() in ('hd51', 'vs1500', 'h7')
SystemInfo["HaveMultiBootCY"] = fileCheck("/boot/STARTUP") and getMachineBuild() in ('8100s', )
SystemInfo["HaveMultiBootOS"] = fileCheck("/boot/STARTUP") and getMachineBuild() in ('osmio4k', )
SystemInfo["HaveMultiBootXC"] = fileCheck("/boot/cmdline.txt")
SystemInfo["HaveMultiBootGB"] = fileCheck("/boot/STARTUP") and getMachineBuild() in ('gb7252', )
SystemInfo["HaveMultiBootDS"] = fileCheck("/boot/STARTUP") and getMachineBuild() in ('gbmv200', 'cc1','sf8008', 'ustym4kpro', 'beyonwizv2') and fileCheck("/dev/sda")
SystemInfo["need_dsw"] = getBoxType() not in ('osminiplus', 'osmega')
SystemInfo["RecoveryMode"] = fileCheck("/proc/stb/fp/boot_mode")
SystemInfo["Blindscan_t2_available"] = fileCheck("/proc/stb/info/vumodel")
SystemInfo["HasForceLNBOn"] = fileCheck("/proc/stb/frontend/fbc/force_lnbon")
SystemInfo["HasForceToneburst"] = fileCheck("/proc/stb/frontend/fbc/force_toneburst")
SystemInfo["HasMMC"] = getMachineBuild() == 'et13000' or getBoxType() in ('mutant51', 'mutant52', 'sf4008', 'tmtwin4k', 'vusolo4k', 'vuultimo4k', 'vuuno4k')
SystemInfo["HasHiSi"] = path.exists('/proc/hisi')
SystemInfo["CommonInterfaceCIDelay"] = fileCheck("/proc/stb/tsmux/rmx_delay")
SystemInfo["CanDoTranscodeAndPIP"] = getBoxType() in ('vusolo4k', )
SystemInfo["hasXcoreVFD"] = fileCheck("/sys/module/brcmstb_%s/parameters/pt6302_cgram" % getBoxType())
SystemInfo["HDMIin"] = getMachineBuild() in ('inihdp', 'hd2400', 'et10000', 'et13000', 'dm7080', 'dm820', 'dm900', 'gb7252', 'vuultimo4k')
SystemInfo["HaveRCA"] = getHaveRCA() == 'True'
SystemInfo["HaveDVI"] = getHaveDVI() == 'True'
SystemInfo["HaveAVJACK"] = getHaveAVJACK() == 'True'
SystemInfo["HAVESCART"] = getHaveSCART() == 'True'
SystemInfo["HAVESCARTYUV"] = getHaveSCARTYUV() == 'True'
SystemInfo["HAVEYUV"] = getHaveYUV() == 'True'
SystemInfo["HAVEHDMI"] = getHaveHDMI() == 'True'
