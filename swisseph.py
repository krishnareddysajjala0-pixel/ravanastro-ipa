import ctypes
import os
import sys
import math

_native_swe = None
_lib = None

# Priority 1: Check if a native compiled swisseph (e.g. .pyd or .so from site-packages) is available in Python
try:
    import importlib.util
    import importlib.machinery
    cur_dir = os.path.abspath(os.path.dirname(__file__))
    for p in sys.path:
        if p and os.path.abspath(p) != cur_dir:
            spec = importlib.machinery.PathFinder.find_spec('swisseph', [p])
            if spec and spec.origin and not spec.origin.endswith('swisseph.py'):
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                _native_swe = mod
                break
except Exception:
    _native_swe = None

# Priority 2: Attempt to load shared C library on iOS (libswisseph.dylib) or Android/Linux (.so)
if _native_swe is None:
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


# Pure Python Fallbacks for astronomical computations
def _py_julday(year, month, day, hour=0.0, cal=GREG_CAL):
    if month <= 2:
        year -= 1
        month += 12
    a = int(year / 100)
    b = 2 - a + int(a / 4) if cal == GREG_CAL else 0
    jd = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + hour / 24.0 + b - 1524.5
    return float(jd)

def _py_revjul(jd, cal=GREG_CAL):
    jd_adj = jd + 0.5
    z = int(jd_adj)
    f = jd_adj - z
    if z < 2299161 or cal == JULN_CAL:
        a = z
    else:
        alpha = int((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - int(alpha / 4)
    b = a + 1524
    c = int((b - 122.1) / 365.25)
    d = int(365.25 * c)
    e = int((b - d) / 30.6001)
    day = b - d - int(30.6001 * e) + f
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    day_int = int(day)
    hour = (day - day_int) * 24.0
    return (int(year), int(month), int(day_int), float(hour))

def _py_ayanamsa(jd):
    t = (jd - 2451545.0) / 36525.0
    return float((23.85 + 50.29 * t / 3600.0 * 100.0) % 360.0)

def _py_houses(jd, lat, lon):
    d = jd - 2451545.0
    gmst = (280.46061837 + 360.98564736629 * d) % 360.0
    lmst = (gmst + lon) % 360.0
    rad_lat = math.radians(lat)
    rad_lmst = math.radians(lmst)
    eps = math.radians(23.4393)
    y = math.cos(rad_lmst)
    x = -math.sin(rad_lmst) * math.cos(eps) - math.tan(rad_lat) * math.sin(eps)
    asc = float(math.degrees(math.atan2(y, x)) % 360.0)
    mc = float(math.degrees(math.atan2(math.tan(rad_lmst), math.cos(eps))) % 360.0)
    cusps = tuple([0.0] + [float((asc + i * 30.0) % 360.0) for i in range(12)])
    ascmc = (asc, mc, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return (cusps, ascmc)

def _py_calc_ut(jd, planet, flags=FLG_SWIEPH):
    d = jd - 2451545.0
    planet_params = {
        SUN: (280.46646, 0.9856474),
        MOON: (218.3165, 13.176396),
        MERCURY: (252.25, 4.092334),
        VENUS: (181.98, 1.60213),
        MARS: (355.43, 0.52402),
        JUPITER: (34.35, 0.08308),
        SATURN: (50.08, 0.03344),
        URANUS: (313.23, 0.01172),
        NEPTUNE: (304.88, 0.00598),
        PLUTO: (238.93, 0.00397),
        MEAN_NODE: (125.04, -0.05295),
        TRUE_NODE: (125.04, -0.05295),
    }
    base, rate = planet_params.get(planet, (0.0, 1.0))
    pos = (base + rate * d) % 360.0
    if flags & FLG_SIDEREAL:
        pos = (pos - _py_ayanamsa(jd)) % 360.0
    return ((float(pos), 0.0, 1.0, float(rate), 0.0, 0.0), 0)


# Public API wrapper
def set_ephe_path(path):
    if _native_swe and hasattr(_native_swe, 'set_ephe_path'):
        return _native_swe.set_ephe_path(path)
    if _lib and hasattr(_lib, 'swe_set_ephe_path'):
        bpath = path.encode('utf-8') if isinstance(path, str) else path
        _lib.swe_set_ephe_path(bpath)

def set_sid_mode(sid_mode, a0=0.0, a1=0.0):
    if _native_swe and hasattr(_native_swe, 'set_sid_mode'):
        return _native_swe.set_sid_mode(sid_mode, a0, a1)
    if _lib and hasattr(_lib, 'swe_set_sid_mode'):
        _lib.swe_set_sid_mode(int(sid_mode), float(a0), float(a1))

def julday(year, month, day, hour=0.0, cal=GREG_CAL):
    if _native_swe and hasattr(_native_swe, 'julday'):
        return float(_native_swe.julday(year, month, day, hour, cal))
    if _lib and hasattr(_lib, 'swe_julday'):
        return float(_lib.swe_julday(int(year), int(month), int(day), float(hour), int(cal)))
    return _py_julday(year, month, day, hour, cal)

def revjul(jd, cal=GREG_CAL):
    if _native_swe and hasattr(_native_swe, 'revjul'):
        return _native_swe.revjul(jd, cal)
    if _lib and hasattr(_lib, 'swe_revjul'):
        y = ctypes.c_int()
        m = ctypes.c_int()
        d = ctypes.c_int()
        h = ctypes.c_double()
        _lib.swe_revjul(float(jd), int(cal), ctypes.byref(y), ctypes.byref(m), ctypes.byref(d), ctypes.byref(h))
        return (y.value, m.value, d.value, h.value)
    return _py_revjul(jd, cal)

def calc_ut(jd, planet, flags=FLG_SWIEPH):
    if _native_swe and hasattr(_native_swe, 'calc_ut'):
        return _native_swe.calc_ut(jd, planet, flags)
    if _lib and hasattr(_lib, 'swe_calc_ut'):
        xx = (ctypes.c_double * 6)()
        serr = ctypes.create_string_buffer(256)
        rc = _lib.swe_calc_ut(float(jd), int(planet), int(flags), xx, serr)
        res_tuple = tuple(xx[i] for i in range(6))
        return (res_tuple, rc)
    return _py_calc_ut(jd, planet, flags)

def get_ayanamsa_ut(jd):
    if _native_swe and hasattr(_native_swe, 'get_ayanamsa_ut'):
        return float(_native_swe.get_ayanamsa_ut(jd))
    if _lib and hasattr(_lib, 'swe_get_ayanamsa_ut'):
        return float(_lib.swe_get_ayanamsa_ut(float(jd)))
    return _py_ayanamsa(jd)

def houses(jd, lat, lon, hsys=b'P'):
    if _native_swe and hasattr(_native_swe, 'houses'):
        return _native_swe.houses(jd, lat, lon, hsys)
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
    return _py_houses(jd, lat, lon)
