import ctypes
import os
import sys

_lib = None

# Attempt to load shared C library on iOS, Android, or desktop
candidates = [
    "libswisseph.dylib",
    os.path.join(os.environ.get("RESOURCE_PATH", ""), "libswisseph.dylib"),
    os.path.join(os.environ.get("RESOURCE_PATH", ""), "Frameworks", "libswisseph.dylib"),
    os.path.join(os.path.dirname(__file__), "libswisseph.dylib"),
    os.path.join(os.path.dirname(__file__), "..", "libswisseph.dylib"),
    os.path.join(os.path.dirname(__file__), "..", "Frameworks", "libswisseph.dylib"),
    os.path.join(os.path.dirname(__file__), "Frameworks", "libswisseph.dylib"),
    "libswisseph.so",
    os.path.join(os.path.dirname(__file__), "libswisseph.dll"),
]

for candidate in candidates:
    if candidate and (os.path.exists(candidate) or not candidate.startswith(("/", "\\", "."))):
        try:
            _lib = ctypes.CDLL(candidate)
            if hasattr(_lib, 'swe_calc_ut'):
                break
        except Exception:
            pass

if _lib is None or not hasattr(_lib, 'swe_calc_ut'):
    try:
        cand_lib = ctypes.CDLL(None)
        if hasattr(cand_lib, 'swe_calc_ut'):
            _lib = cand_lib
    except Exception:
        pass

# Constants
FLG_JPLEPH = 1
FLG_SWIEPH = 2
FLG_MOSEPH = 4
FLG_HELCTR = 8
FLG_TRUEPOS = 16
FLG_J2000 = 32
FLG_NONUTR = 64
FLG_SPEED3 = 128
FLG_SPEED = 256
FLG_NOGDEFL = 512
FLG_NOABERR = 1024
FLG_EQUATORIAL = 2048
FLG_XYZ = 4096
FLG_RADIANS = 8192
FLG_BARYCTR = 16384
FLG_TOPOCTR = 32768
FLG_SIDEREAL = 65536
FLG_ICRS = 131072

SIDM_LAHIRI = 1

ECL_NUT = -1
SUN = 0
MOON = 1
MERCURY = 2
VENUS = 3
MARS = 4
JUPITER = 5
SATURN = 6
URANUS = 7
NEPTUNE = 8
PLUTO = 9
MEAN_NODE = 10
TRUE_NODE = 11

GREG_CAL = 1
JULN_CAL = 0

if _lib:
    try:
        if hasattr(_lib, 'swe_set_ephe_path'):
            _lib.swe_set_ephe_path.argtypes = [ctypes.c_char_p]
            _lib.swe_set_ephe_path.restype = None

        if hasattr(_lib, 'swe_set_sid_mode'):
            _lib.swe_set_sid_mode.argtypes = [ctypes.c_int32, ctypes.c_double, ctypes.c_double]
            _lib.swe_set_sid_mode.restype = None

        if hasattr(_lib, 'swe_julday'):
            _lib.swe_julday.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.c_int]
            _lib.swe_julday.restype = ctypes.c_double

        if hasattr(_lib, 'swe_revjul'):
            _lib.swe_revjul.argtypes = [ctypes.c_double, ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_double)]
            _lib.swe_revjul.restype = None

        if hasattr(_lib, 'swe_calc_ut'):
            _lib.swe_calc_ut.argtypes = [ctypes.c_double, ctypes.c_int, ctypes.c_int32, ctypes.POINTER(ctypes.c_double), ctypes.c_char_p]
            _lib.swe_calc_ut.restype = ctypes.c_int32

        if hasattr(_lib, 'swe_get_ayanamsa_ut'):
            _lib.swe_get_ayanamsa_ut.argtypes = [ctypes.c_double]
            _lib.swe_get_ayanamsa_ut.restype = ctypes.c_double

        if hasattr(_lib, 'swe_houses'):
            _lib.swe_houses.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double)]
            _lib.swe_houses.restype = ctypes.c_int
    except Exception as e:
        print("[swisseph] Function binding warning:", e)

def set_ephe_path(path):
    if _lib and hasattr(_lib, 'swe_set_ephe_path'):
        bpath = path.encode('utf-8') if isinstance(path, str) else path
        _lib.swe_set_ephe_path(bpath)

def set_sid_mode(sid_mode, a0=0.0, a1=0.0):
    if _lib and hasattr(_lib, 'swe_set_sid_mode'):
        _lib.swe_set_sid_mode(int(sid_mode), float(a0), float(a1))

def julday(year, month, day, hour=0.0, cal=GREG_CAL):
    if _lib and hasattr(_lib, 'swe_julday'):
        return float(_lib.swe_julday(int(year), int(month), int(day), float(hour), int(cal)))
    return 0.0

def revjul(jd, cal=GREG_CAL):
    if _lib and hasattr(_lib, 'swe_revjul'):
        y = ctypes.c_int()
        m = ctypes.c_int()
        d = ctypes.c_int()
        h = ctypes.c_double()
        _lib.swe_revjul(float(jd), int(cal), ctypes.byref(y), ctypes.byref(m), ctypes.byref(d), ctypes.byref(h))
        return (y.value, m.value, d.value, h.value)
    return (2026, 1, 1, 0.0)

def calc_ut(jd, planet, flags=FLG_SWIEPH):
    if _lib and hasattr(_lib, 'swe_calc_ut'):
        xx = (ctypes.c_double * 6)()
        serr = ctypes.create_string_buffer(256)
        rc = _lib.swe_calc_ut(float(jd), int(planet), int(flags), xx, serr)
        res_tuple = tuple(xx[i] for i in range(6))
        return (res_tuple, rc)
    return ((0.0, 0.0, 0.0, 0.0, 0.0, 0.0), 0)

def get_ayanamsa_ut(jd):
    if _lib and hasattr(_lib, 'swe_get_ayanamsa_ut'):
        return float(_lib.swe_get_ayanamsa_ut(float(jd)))
    return 0.0

def houses(jd, lat, lon, hsys=b'P'):
    if _lib and hasattr(_lib, 'swe_houses'):
        cusps = (ctypes.c_double * 13)()
        ascmc = (ctypes.c_double * 10)()
        if isinstance(hsys, str):
            hsys_code = ord(hsys[0]) if len(hsys) > 0 else ord('P')
        elif isinstance(hsys, bytes):
            hsys_code = hsys[0] if len(hsys) > 0 else ord('P')
        else:
            hsys_code = int(hsys)
        _lib.swe_houses(float(jd), float(lat), float(lon), int(hsys_code), cusps, ascmc)
        cusps_tuple = tuple(cusps[i] for i in range(13))
        ascmc_tuple = tuple(ascmc[i] for i in range(10))
        return (cusps_tuple, ascmc_tuple)
    return ((0.0)*13, (0.0)*10)
