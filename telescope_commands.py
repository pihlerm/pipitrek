import time

class Telescope:
    pass


zero_or_error = lambda inp: (len(inp)>0 and inp[0]==ord('0')) or b'#' in inp
lx200_ok = lambda inp: len(inp)>0 and (inp[0]==ord('0') or inp[0]==ord('1'))
contains_hash = lambda inp: b'#' in inp

class TelescopeCommand:
    def __init__(self, command, requireResponse, responseLambda = None, timeout = 10):
        self.executed = False
        self.requireResponse = requireResponse
        self.responseLambda = responseLambda
        self.command = command
        self.response = None
        self.timeout = timeout

    def execute(self, telescope:Telescope):
        with telescope.lock:
            prevto = telescope._serial_connection.timeout
            telescope._serial_connection.timeout = self.timeout
            print(f"sending {self.command}")
            telescope.write_scope(self.command.encode())
            if self.requireResponse:
                if self.responseLambda is None:
                    self.response = telescope.readline_scope(timeout=self.timeout)
                    print(f"rcv {self.response}")
                else:
                    self.response = b''
                    start = time.time()
                    while not self.responseLambda(self.response) and time.time()-start<self.timeout:
                        self.response += telescope.read_scope_byte()
                    print(f"rcv {self.response}")
            telescope._serial_connection.timeout = prevto
            return self.response

class LXMove(TelescopeCommand):
    def __init__(self, direction):
        if direction not in ['n','s','e','w']:
            raise ValueError(f"Direction must be one of (n s e w)")
        super().__init__(f":M{direction}#",False)

class LXSpeed(TelescopeCommand):
    def __init__(self, speed):
        if speed not in ['G','C','M','S']:
            raise ValueError(f"Speed must be one of (G C M S)")
        super().__init__(f":R{speed}#",False)

class LXStop(TelescopeCommand):
    def __init__(self, direction):
        if direction not in ['', 'n','s','e','w']:
            raise ValueError(f"Direction must be one of (n s e w)")
        super().__init__(f":Q{direction}#",False)

class LXSetRa(TelescopeCommand):
    def __init__(self, ra):
        super().__init__(f":Sr{ra}#",True, lx200_ok)

class LXSetDec(TelescopeCommand):
    def __init__(self, dec):
        super().__init__(f":Sd{dec}#",True, lx200_ok)

class LXGetRa(TelescopeCommand):
    def __init__(self):
        super().__init__(f":GR#",True, contains_hash)

class LXGetDec(TelescopeCommand):
    def __init__(self):
        super().__init__(f":GD#",True, contains_hash)

class LXGetProduct(TelescopeCommand):
    def __init__(self):
        super().__init__(f":GVP#",True, contains_hash)

class LXGetVersion(TelescopeCommand):
    def __init__(self):
        super().__init__(f":GVN#",True, contains_hash)

class LXSetTO(TelescopeCommand):
    def __init__(self):
        super().__init__(f":CM#",True, contains_hash)

# slew to previously set coordinates; responds with 0 or b"1 {reason}#"
class LXSlew(TelescopeCommand):
    def __init__(self):
        super().__init__(f":MS#",True, zero_or_error)

# pipicmd always has response and is terminated by !\n
class PipiTelescopeCommand(TelescopeCommand):
    def __init__(self, command):
        super().__init__(command,True, lambda input: b"!\n" in input)

    def execute(self, telescope:Telescope):
        with telescope.lock:
            telescope.write_scope(self.command.encode())
            self.response = b''
            start = time.time()
            while not self.responseLambda(self.response) and time.time()-start<self.timeout:
                self.response += telescope.readline_scope(timeout=self.timeout)
            return self.response

class PTCInfo(PipiTelescopeCommand):
    def __init__(self):
        super().__init__("!IN#")

class PTCCameraStart(PipiTelescopeCommand):
    def __init__(self, start ):
        if start:
            super().__init__("!CO#")
        else:
            super().__init__("!CX#")

class PTCCameraSetExp(PipiTelescopeCommand):
    def __init__(self, exposure ):
        super().__init__(f"!CE{int(exposure):03d}#")

class PTCCameraSetShots(PipiTelescopeCommand):
    def __init__(self, shots):
        super().__init__(f"!CN{int(shots):03d}#")

class PTCSetBacklashRA(PipiTelescopeCommand):
    def __init__(self, comp):
        super().__init__(f"!PA{int(abs(comp)):03d}#")

class PTCSetBacklashDEC(PipiTelescopeCommand):
    def __init__(self, comp):
        super().__init__(f"!PB{int(abs(comp)):03d}#")
    
class PTCStartMove(PipiTelescopeCommand):
    def __init__(self, ra, dec):
        # Ensure ra and dec are integers
        ra = int(ra)
        dec = int(dec)
        rasign = '+' if ra>=0 else '-'
        decsign = '+' if dec>=0 else '-'
        str = f"!S{rasign}{abs(ra):02d}{decsign}{abs(dec):02d}#"
        super().__init__(str)

class PTCGetPEC(PipiTelescopeCommand):
    def __init__(self):
        super().__init__(f"!PO#")

class PTCSetPEC(TelescopeCommand):
    def __init__(self,pec_table):
        super().__init__(f"!PI#", False)
        self.pec_table = pec_table

    def execute(self, telescope:Telescope):
        with telescope.lock:
            super().execute(telescope)  # send !PI#

            num_points = len(self.pec_table) // 2
            telescope.write_scope(f"PEC {num_points} ".encode())
            
            data_str = ",".join(map(str, self.pec_table)) + "\n"
            telescope.write_scope(data_str.encode())
            
            print("PEC table sent.")
            self.response = telescope.readline_scope(timeout=self.timeout)
            return self.response

class PTCSetPECPos(PipiTelescopeCommand):
    def __init__(self, position):
        if position<0 or position>99:
            raise ValueError(f"PEC position must be 0-99 but is {position}")
        super().__init__(f"!PS{int(position):02d}#")

class PTCGetPECPos(PipiTelescopeCommand):
    def __init__(self):
        super().__init__(f"!PG#")

class PTCSetTracking(PipiTelescopeCommand):
    def __init__(self, tracking):
        if tracking:
            super().__init__(f"!TE#")
        else:
            super().__init__(f"!TD#")

class PTCSetPier(PipiTelescopeCommand):
    def __init__(self, pier):
        if pier not in ['W', 'E']:
            raise ValueError(f"Pier must be W or E")
        super().__init__(f"!M{pier}#")
