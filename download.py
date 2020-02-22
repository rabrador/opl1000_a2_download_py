import os
import sys
import time

import serial
import serial.tools.list_ports
import struct
import argparse

import ConfigParser

##############################################################
InputFileName = None
WorkDir = None
ConfigDir = None

##############################################################
def cmd_process():
    parser = argparse.ArgumentParser()
    parser.add_argument('-b', "--image-file", type=str, help='specific bin file')
    argc = parser.parse_args()
#    print argc.image_file
    if argc.image_file is not None :
        global InputFileName
        InputFileName = argc.image_file
        print InputFileName

def drag_drop_file():
    try:
        if sys.argv[1] is not None :
            print "[%s]: %s" % (drag_drop_file.__name__, sys.argv[1])
            global InputFileName
            InputFileName = os.path.basename(sys.argv[1])
            print "[%s]: %s" % (drag_drop_file.__name__, InputFileName)
            
            global WorkDir
            WorkDir = os.path.dirname(sys.argv[1])
            print "[%s]: %s" % (drag_drop_file.__name__, WorkDir)
    except:
        print "[%s] ignore" % drag_drop_file.__name__

class UtilFun():
    def CheckSum(self, buf, len):
        seed = 0
        if len == 4:
            seed += (buf & 0xff000000) >> 24
            seed += (buf & 0x00ff0000) >> 16
            seed += (buf & 0x0000ff00) >> 8
            seed += (buf & 0x000000ff)
            return seed
            
    def DumpHex(self, buf):
        i = 0
        for element in buf:
            #no line wrap
            print hex(element)[2:].zfill(2),
            #line warp by every 16 bytes
            if i == 15:
                print ""
                i = 0
            else :
                i = i + 1
                
    def ProgressBar(self, it, prefix = "", size = 60):
        count = len(it)
        def _show(_i):
            x = int(size*_i/count)
            sys.stdout.write("%s[%s%s] %i/%i\r" % (prefix, "#"*x, "."*(size-x), _i, count))
            sys.stdout.flush()
        
        _show(0)
        for i, item in enumerate(it):
            yield item
            _show(i+1)
        sys.stdout.write("\n")
        sys.stdout.flush()       
    
class UpdateFirmWare():
    
    # Configuration
    defconfig = []
    
    DefPatchSize = 256      # 256 bytes per page
    DefSectorSize = 4096    # 4K bytes per sector
    
    DefEndChar = "\x0D"
    
    DefATCmdDownload = "at+download\r\n"
    
    # NOT support in APS/M3 debug interface
    DefATCmdReset = "at+rst\r\n"
    
    DefRespCheck = "<CHECK>"
    DefRespStart = "<START>"
    DefRespAck   = "<ACK>"
    
    # protocol frame
    DefEraseStart     = "\xFE\x32"                  # Erase start
    DefEraseSecNumber = "\x00\x00\x00\x00"          # Erase start sector number
    DefEraseSecCount  = "\x00\x00\x00\x00"          # Erase total sector counter
    
    DefWriteStart     = "\xFE\x31"                  # Write start
    DefWriteHeader    = "netlinkc"                  # Write header
    DefWritePatchNum  = "\x00\x00\x00\x00"          # Write patch number
    
    PatchNum = 0
    PatchSectorNum = 0
    
    def ShowAllCOMPort(self):
        ComPortList = serial.tools.list_ports.comports()
        connected = []
        for element in ComPortList:
            connected.append(str(element.device))
        print "Available COM ports: " + str(connected)
    
    def CalculateFWBin(self):
        FWSize = os.path.getsize(WorkDir + "/" + self.defconfig[2])
        if FWSize == 0 :
            print "[Error]: CalculateFWBin failed"
            return -1
#        print "[DBG]: FWSize=" + str(FWSize)
        
        #Calculate total patch number
        self.PatchNum = FWSize / self.DefPatchSize
        if FWSize % self.DefPatchSize:
            self.PatchNum += 1
#        print "[DBG]: PatchNum=" + str(self.PatchNum)
        
        #Calculate total sector number
        self.PatchSectorNum = FWSize / self.DefSectorSize
        if FWSize % self.DefSectorSize:
            self.PatchSectorNum += 1
#        print "[DBG]: PatchSectorNum=" + str(self.PatchSectorNum)
    
    def EraseFlash(self, serial, start, count):
        if serial is None :
            print "[Error]: No COM port"
            return -1
        
        self.SerialTxData(serial, self.DefEraseStart)
        if self.SerialRxWaitCheck(serial, self.DefRespStart) == 0 :
            self.SerialTxData(serial, struct.pack(">I", start))
            self.SerialTxData(serial, struct.pack(">I", count))
            if self.SerialRxWaitCheck(serial, self.DefRespAck) == 0 :
                print "[DBG]: Erase flash done."
                return 0
        
        return -1
        
    def SerialRxWaitCheck(self, serial, key) :
        retry = 0
        RecvStr = ""
        
        if serial is None :
            print "[Error]: No COM port"
            return -1   
            
        while retry < 1000 :
            tmp = serial.read(1)
            if len(tmp) > 0 :
                RecvStr += tmp
                
                if key in RecvStr:
#                    print "[DBG]: " + RecvStr
                   return 0
            retry += 1
        return -1

    def SerialTxData(self, serial, data):
        if serial is None :
            print "[Error]: No COM port"
            return -1
        serial.write(data)
        serial.flush()
        
    def UpgradeFirmWare(self):
        RecvStr = ""
        
        self.CalculateFWBin()
        try :
            # Open ComPort
            with serial.Serial("COM" + str(self.defconfig[0]), int(self.defconfig[1]), timeout=10, bytesize=8, parity='N', stopbits=1) as ser:
                # flush the garbage
                self.SerialTxData(ser, self.DefEndChar)

                # This have something unknown error !!!!
                # Send "at+download"
                # In A1 rom based, this might be failed.
                self.SerialTxData(ser, self.DefATCmdReset + self.DefEndChar)
                
                # If didn't receive response, may be trap in ROM code.
                # Try to click reset button.
                if self.SerialRxWaitCheck(ser, self.DefRespCheck) == -1 :
                    return -1
                
                # Erase flash
                if self.EraseFlash(ser, 0, self.PatchSectorNum) == -1 :
                    print "[Error]: Erase flash failed"
                    return -1
                
                if self.SerialRxWaitCheck(ser, self.DefRespCheck) == -1 :
                    return -1
                
                # Send 0xfe 0x31 to enter uart write flash mode
                self.SerialTxData(ser, self.DefWriteStart)
                
                # Wait start
                if self.SerialRxWaitCheck(ser, self.DefRespStart) == -1:
                    return -1
                
                # Send "netlinkc"
                self.SerialTxData(ser, self.DefWriteHeader)
                
                # Send patch number (4 bytes)
                self.SerialTxData(ser, struct.pack(">I", self.PatchNum))

                # Wait ACK
                if self.SerialRxWaitCheck(ser, self.DefRespAck) == -1:
                    return -1
                
                # Start download firmware
                StartAddr = 0
                result = 0
                
                # Write to flash per block size
                util = UtilFun()
                with open(WorkDir + "/" + self.defconfig[2], "rb") as file:
#                while True :
                    for p in util.ProgressBar(range(self.PatchNum), "Downloading: ", 40):
                        byte = file.read(self.DefPatchSize)
                        if len(byte) > 0 :
                            # Send start address (4 bytes)
                            self.SerialTxData(ser, struct.pack(">I", StartAddr))

                            # Send size (4 bytes)
                            self.SerialTxData(ser, struct.pack(">I", len(byte)))
                            
                            # Send data (1 ~ 256 bytes)
                            checksum = 0
                            for i in byte :
                                checksum += ord(i)
                                self.SerialTxData(ser, i)
                            
                            # Send checksum (4 bytes)
                            self.SerialTxData(ser, struct.pack(">I", checksum))
                            
                            # Wait ACK
                            if self.SerialRxWaitCheck(ser, self.DefRespAck) == -1:
                                return -1
                            
#                            print "Total: %d ... %d" %(self.PatchNum, StartAddr/self.DefPatchSize+1)
                            
                            # Shift the start address
                            StartAddr += len(byte)
                        else :
                            break

        except:
            print "[Error]: Upgrade FirmWare Failed."
            return -1
        return 0
    
    def CheckResultAfterUpgrade(self):
        try :
            with serial.Serial("COM" + str(self.defconfig[0]), int(self.defconfig[1]), timeout=10, bytesize=8, parity='N', stopbits=1) as ser:
                self.SerialTxData(ser, self.DefATCmdDownload + self.DefEndChar)
                    
                if self.SerialRxWaitCheck(ser, str(self.PatchNum - 1)) == -1 :
                    return -1
            
        except:
            print "[Error]: Upgrade FirmWare Failed."
            return -1
        return 0
        
    def LoadDefaultConfig(self):
        try :
            config = ConfigParser.RawConfigParser()
            config.read(ConfigDir)
            
            for item in config.items("Default"):
                self.defconfig.append(item[1])
                
            if InputFileName is not None:
                self.defconfig[2] = InputFileName
                
            print "[DBG]: Load configuration done."
            
        except ConfigParser.NoSectionError:
            print "ConfigParser.NoSectionError"
            os.system("pause")
        except:
            print "Unexpected error:", sys.exc_info()[0]
            os.system("pause")

    def LoadPathDataFromInit(self, section):
        try :
            config = ConfigParser.RawConfigParser()
            config.read(ConfigDir)

            for item in config.items(section):
                print "[DBG]: Load %s done." % (section)
                return item[1].split(",")
        except:
            print "Unexpected error:", sys.exc_info()[0]
            os.system("pause")
            
    def CalculatePatchLen(self, type):
        if type == '1' :
            return 0x00010000
        elif type == '2' :
            return 0x00020000
        elif type == '4' :
            return 0x00040000
        else :
            print 'Error'
    
    def CombinBin(self):
        #Patch data
        HwColdM3 = []
        HwColdM0 = []
        CodeColdM3 = []
        CodeColdM0 = []
        
        #Bin format
        BinFmtHeader = 0
        BinFmtType = 0
        BinFmtDataLen = 0
        BinFmtHeaderChkSum = 0
        
        BinFmtDataAddr = 0
        BinFmtDataVal = 0
        BinFmtChkSum = 0
        
        PatchCfgCount = 0
        
        util = UtilFun()
        
        #Process HW_COLD_M3
        HwColdM3 = self.LoadPathDataFromInit("HW_COLD_M3")
        PatchCfgCount = self.CalculatePatchLen(HwColdM3[0])
        
        BinFmtHeader = (0x50544348)
        BinFmtType = (0x00000001 | 0x00000010 | 0x00000100 | PatchCfgCount)
        BinFmtDataLen = ((len(HwColdM3) - 1) / 2) * 8
        BinFmtHeaderChkSum = util.CheckSum(BinFmtHeader, 4)
        BinFmtHeaderChkSum += util.CheckSum(BinFmtType, 4)
        BinFmtHeaderChkSum += util.CheckSum(BinFmtDataLen, 4)
        
        OutputBuf = bytearray(struct.pack('>I', BinFmtHeader))
        OutputBuf.extend(struct.pack('>I', BinFmtType))
        OutputBuf.extend(struct.pack('>I', BinFmtDataLen))
        OutputBuf.extend(struct.pack('>I', BinFmtHeaderChkSum))
        
        for c in range(1, len(HwColdM3), 2) :
            BinFmtDataAddr = int(HwColdM3[c], 0)
            BinFmtDataVal = int(HwColdM3[c+1], 0)
            BinFmtChkSum += util.CheckSum(BinFmtDataAddr,4)
            BinFmtChkSum += util.CheckSum(BinFmtDataVal,4)
            OutputBuf.extend(struct.pack('>I', BinFmtDataAddr))
            OutputBuf.extend(struct.pack('>I', BinFmtDataVal))
        OutputBuf.extend(struct.pack('>I', BinFmtChkSum))
        
        #Process HW_COLD_M0
        HwColdM0 = self.LoadPathDataFromInit("HW_COLD_M0")
        PatchCfgCount = self.CalculatePatchLen(HwColdM0[0])
        
        BinFmtHeader = (0x50544348)
        BinFmtType = (0x00000001 | 0x00000010 | 0x00000200 | PatchCfgCount)
        BinFmtDataLen = ((len(HwColdM0) - 1) / 2) * 8
        BinFmtHeaderChkSum = util.CheckSum(BinFmtHeader, 4)
        BinFmtHeaderChkSum += util.CheckSum(BinFmtType, 4)
        BinFmtHeaderChkSum += util.CheckSum(BinFmtDataLen, 4)
        
        OutputBuf.extend(struct.pack('>I', BinFmtHeader))
        OutputBuf.extend(struct.pack('>I', BinFmtType))
        OutputBuf.extend(struct.pack('>I', BinFmtDataLen))
        OutputBuf.extend(struct.pack('>I', BinFmtHeaderChkSum))
        
        BinFmtChkSum = 0
        for c in range(1, len(HwColdM0), 2) :
            BinFmtDataAddr = int(HwColdM0[c], 0)
            BinFmtDataVal = int(HwColdM0[c+1], 0)
            BinFmtChkSum += util.CheckSum(BinFmtDataAddr,4)
            BinFmtChkSum += util.CheckSum(BinFmtDataVal,4)
            OutputBuf.extend(struct.pack('>I', BinFmtDataAddr))
            OutputBuf.extend(struct.pack('>I', BinFmtDataVal))
        OutputBuf.extend(struct.pack('>I', BinFmtChkSum))
        
        #Process CODE_COLD_M3
        BinFmtChkSum = 0
        CodeColdM3 = self.LoadPathDataFromInit("CODE_COLD_M3")
        PatchCfgCount = self.CalculatePatchLen(CodeColdM3[0])
        
        if InputFileName is not None :
            CodeColdM3[2] = InputFileName
        
        BinFmtHeader = (0x50544348)
        BinFmtType = (0x00000004 | 0x00000010 | 0x00000000 | PatchCfgCount)
        BinFmtDataLen = os.path.getsize("./" + CodeColdM3[2]) + 4
        BinFmtHeaderChkSum = util.CheckSum(BinFmtHeader, 4)
        BinFmtHeaderChkSum += util.CheckSum(BinFmtType, 4)
        BinFmtHeaderChkSum += util.CheckSum(BinFmtDataLen, 4)
        
        OutputBuf.extend(struct.pack('>I', BinFmtHeader))
        OutputBuf.extend(struct.pack('>I', BinFmtType))
        OutputBuf.extend(struct.pack('>I', BinFmtDataLen))
        OutputBuf.extend(struct.pack('>I', BinFmtHeaderChkSum))
        
        BinFmtDataAddr = int(CodeColdM3[1], 0)
        BinFmtChkSum += util.CheckSum(BinFmtDataAddr,4)
        
        OutputBuf.extend(struct.pack('>I', BinFmtDataAddr))
        
        with open(CodeColdM3[2], "rb") as file:
            byte = file.read(1)
            while byte:
                OutputBuf.extend(byte)
                BinFmtChkSum += ord(byte)
                byte = file.read(1)
        OutputBuf.extend(struct.pack('>I', BinFmtChkSum))
        
        #Process CODE_COLD_M0
        CodeColdM0 = self.LoadPathDataFromInit("CODE_COLD_M0")
        PatchCfgCount = self.CalculatePatchLen(CodeColdM0[0])
        
        BinFmtHeader = (0x50544348)
        BinFmtType = (0x00000004 | 0x00000010 | 0x00000200 | PatchCfgCount)

        m0BInCount = len(CodeColdM0)
        
        for i in range(2, m0BInCount, 2) :
            BinFmtChkSum = 0
            
            BinFmtDataLen = os.path.getsize("./" + CodeColdM0[i]) + 4
            BinFmtHeaderChkSum = util.CheckSum(BinFmtHeader, 4)
            BinFmtHeaderChkSum += util.CheckSum(BinFmtType, 4)
            BinFmtHeaderChkSum += util.CheckSum(BinFmtDataLen, 4)

            OutputBuf.extend(struct.pack('>I', BinFmtHeader))
            OutputBuf.extend(struct.pack('>I', BinFmtType))
            OutputBuf.extend(struct.pack('>I', BinFmtDataLen))
            OutputBuf.extend(struct.pack('>I', BinFmtHeaderChkSum))
        
            BinFmtDataAddr = int(CodeColdM0[i-1], 0)
            BinFmtChkSum += util.CheckSum(BinFmtDataAddr,4)
        
            OutputBuf.extend(struct.pack('>I', BinFmtDataAddr))
        
            with open(CodeColdM0[i], "rb") as file:
                byte = file.read(1)
                while byte:
                    OutputBuf.extend(byte)
                    BinFmtChkSum += ord(byte)
                    byte = file.read(1)
            OutputBuf.extend(struct.pack('>I', BinFmtChkSum))

#debug use
#        util.DumpHex(OutputBuf)
        
        with open(self.defconfig[2], "wb") as file:
            file.write(OutputBuf)
        print "[DBG]: Combine bin files done."
        
##############################################################
# command parser
#cmd_process()

# Setup working path
WorkDir = os.getcwd()

# drag and drop file into script
drag_drop_file()

ConfigDir = WorkDir + '\Config.ini'

UpFw = UpdateFirmWare()
UpFw.LoadDefaultConfig()

# Means double clicks the script
if InputFileName is None :
    UpFw.CombinBin()

#UpFw.ShowAllCOMPort()

print "[INFO]: Please turn off/on the power if no message show."

if UpFw.UpgradeFirmWare() != 0 :
    print "[Error]: Write flash Failed."
    os.system("pause")

#time.sleep(2)

#if UpFw.CheckResultAfterUpgrade() != 0 :
#    print "[Error]: Check index failed after write flash."
#    os.system("pause")
