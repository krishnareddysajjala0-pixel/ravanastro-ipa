from flask import Flask, render_template as flask_render_template, request, redirect, url_for, session, jsonify, has_request_context, make_response, g
import swisseph as swe
import datetime
import pytz
import os
import threading
import subprocess
import requests
import base64
import json
import re
import time
import requests
import base64
import json
import re

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Cache loaded translation dictionaries in memory
TRANSLATIONS_CACHE = {}
TR_STRING_CACHE = {}
TIME_KEYWORDS = ["ఉ: ", "సా: ", "ఉ:", "సా:", "గం", "ని", "సం", "నెలలు", "నుండి", "నుంచి", "వరకు", "రేపు", "నిన్న", "ముగింపు", "మొదలు"]
TIME_KEYWORDS.sort(key=len, reverse=True)

def get_translations_dict(lang):
    if not lang or lang == 'te':
        return {}
    if lang not in TRANSLATIONS_CACHE:
        path = os.path.join(os.path.dirname(__file__), "translations", f"translations_{lang}.json")
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    TRANSLATIONS_CACHE[lang] = json.load(f)
            except Exception as e:
                print(f"Error loading vocabulary {lang}: {e}")
                TRANSLATIONS_CACHE[lang] = {}
        else:
            TRANSLATIONS_CACHE[lang] = {}
    return TRANSLATIONS_CACHE[lang]

# Pre-warm all language dictionaries in memory in background thread for instant language selection without delaying startup
import threading
def _bg_prewarm():
    for _l in ['en', 'hi', 'kn', 'ta', 'ml', 'or']:
        try:
            get_translations_dict(_l)
        except Exception:
            pass
threading.Thread(target=_bg_prewarm, daemon=True).start()


def tr(text, lang=None):
    if not text:
        return text
    if not lang:
        lang = 'te'
        if has_request_context():
            lang = session.get('lang') or request.cookies.get('lang') or 'te'
    if lang == 'te':
        return text
        
    cache_key = (text, lang)
    if cache_key in TR_STRING_CACHE:
        return TR_STRING_CACHE[cache_key]
        
    mapping = get_translations_dict(lang)
    
    # Centralized stripped check to match keys like "ఉ:" and "సా:" even with trailing spaces
    stripped = text.strip()
    if stripped in mapping:
        translated = mapping[stripped]
        if text.startswith(' '):
            translated = ' ' + translated
        if text.endswith(' '):
            translated = translated + ' '
        TR_STRING_CACHE[cache_key] = translated
        return translated
        
    # Suffix matching
    tithi_match = re.match(r'^(\d+)వ తిథి$', text)
    if tithi_match:
        num = tithi_match.group(1)
        suffix = mapping.get("వ తిథి", " Tithi")
        res = f"{num}{suffix}"
        TR_STRING_CACHE[cache_key] = res
        return res
        
    padam_match = re.match(r'^(\d+)వ పాదం$', text)
    if padam_match:
        num = padam_match.group(1)
        suffix = mapping.get("వ పాదం", " Pada")
        res = f"{num}{suffix}"
        TR_STRING_CACHE[cache_key] = res
        return res
        
    # Handle combined times (e.g. "నిన్న సా: 03:12")
    if any(k in text for k in TIME_KEYWORDS):
        translated_text = text
        for te_word in TIME_KEYWORDS:
            if te_word in translated_text:
                stripped_word = te_word.strip()
                replacement = mapping.get(stripped_word)
                if replacement:
                    if te_word.startswith(' '):
                        replacement = ' ' + replacement
                    if te_word.endswith(' '):
                        replacement = replacement + ' '
                    translated_text = translated_text.replace(te_word, replacement)
        TR_STRING_CACHE[cache_key] = translated_text
        return translated_text
        
    TR_STRING_CACHE[cache_key] = text
    return text


def translate_html_string(html_str, lang=None):
    if not lang:
        lang = 'te'
        if has_request_context():
            lang = session.get('lang') or request.cookies.get('lang') or 'te'
    if lang == 'te':
        return html_str
        
    def repl(match):
        text = match.group(2)
        if text.strip():
            return f"{match.group(1)}{tr(text, lang)}{match.group(3)}"
        return match.group(0)
    return re.sub(r'(>)([^<]+)(<)', repl, html_str)

def translate_data(val, lang):
    if lang == 'te' or not val:
        return val
    
    if isinstance(val, str):
        if "<span" in val or "<br" in val or "<b>" in val:
            return translate_html_string(val, lang)
        return tr(val, lang)
    elif isinstance(val, list):
        return [translate_data(item, lang) for item in val]
    elif isinstance(val, dict):
        return {k: translate_data(v, lang) for k, v in val.items()}
    return val

def render_template(template_name_or_list, **context):
    lang = 'te'
    if has_request_context():
        lang = session.get('lang') or request.cookies.get('lang') or 'te'
    if lang != 'te':
        translated_context = {}
        for k, v in context.items():
            translated_context[k] = translate_data(v, lang)
        translated_context['current_lang'] = lang
        return flask_render_template(template_name_or_list, **translated_context)
    context['current_lang'] = 'te'
    return flask_render_template(template_name_or_list, **context)

RULES_CACHE = {}

def load_rules(filename, lang=None):
    if not lang:
        lang = 'te'
        if has_request_context():
            lang = session.get('lang') or request.cookies.get('lang') or 'te'

    cache_key = (filename, lang)
    if cache_key in RULES_CACHE:
        return RULES_CACHE[cache_key]

    if filename == 'astro_constants.json':
        path = os.path.join(os.path.dirname(__file__), filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                RULES_CACHE[cache_key] = data
                return data
        except Exception as e:
            print(f"Error loading {filename}: {e}")
            return {}

    if lang != 'te':
        base, ext = os.path.splitext(filename)
        localized_filename = f"{base}_{lang}{ext}"
        path = os.path.join(os.path.dirname(__file__), localized_filename)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    RULES_CACHE[cache_key] = data
                    return data
            except Exception as e:
                print(f"Error loading localized {localized_filename}: {e}")
                
    path = os.path.join(os.path.dirname(__file__), filename)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            RULES_CACHE[cache_key] = data
            return data
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return {}

def load_localized_constants(lang=None):
    if not lang:
        lang = 'te'
        if has_request_context():
            lang = session.get('lang') or request.cookies.get('lang') or 'te'

    cache_key = ('astro_constants_localized', lang)
    if cache_key in RULES_CACHE:
        return RULES_CACHE[cache_key]

    filename = 'astro_constants.json'
    if lang != 'te':
        base, ext = os.path.splitext(filename)
        localized_filename = f"{base}_{lang}{ext}"
        path = os.path.join(os.path.dirname(__file__), localized_filename)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    RULES_CACHE[cache_key] = data
                    return data
            except Exception as e:
                print(f"Error loading localized {localized_filename}: {e}")
    path = os.path.join(os.path.dirname(__file__), filename)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            RULES_CACHE[cache_key] = data
            return data
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return {}

def prewarm_caches():
    languages = ['en', 'kn', 'hi', 'ta', 'ml', 'or']
    for l in languages:
        get_translations_dict(l)
        for rule_file in ['bhava_lord_rules.json', 'detailed_bhava_meanings.json', 'astro_constants.json']:
            load_rules(rule_file, l)
        load_localized_constants(l)
    for rule_file in ['bhava_lord_rules.json', 'detailed_bhava_meanings.json', 'astro_constants.json']:
        load_rules(rule_file, 'te')
    load_localized_constants('te')

prewarm_caches()



def format_lord_placement(lord_house_num, lord_planet, p_house, lang):
    translated_planet = tr(lord_planet, lang)
    if lang == 'en':
        ordinals = {1: '1st', 2: '2nd', 3: '3rd', 4: '4th', 5: '5th', 6: '6th',
                    7: '7th', 8: '8th', 9: '9th', 10: '10th', 11: '11th', 12: '12th'}
        ord_lord = ordinals.get(int(lord_house_num), f"{lord_house_num}th")
        ord_house = ordinals.get(int(p_house), f"{p_house}th")
        return f"{ord_lord} Lord ({translated_planet}) in {ord_house} House:"
    elif lang == 'hi':
        return f"{lord_house_num}वें घर का स्वामी ({translated_planet}) {p_house}वें स्थान पर होने के कारण:"
    elif lang == 'kn':
        return f"{lord_house_num}ನೇ ಮನೆ ಅಧಿಪತಿ ({translated_planet}) {p_house}ನೇ ಸ್ಥಾನದಲ್ಲಿರುವುದರಿಂದ:"
    elif lang == 'ml':
        return f"{lord_house_num}-ാം ഭാവനാഥൻ ({translated_planet}) {p_house}-ാം ഭാവത്തിൽ നില്ക്കുന്നതിനാൽ:"
    elif lang == 'or':
        return f"{lord_house_num}ମ ଭାବ ଅଧିପତି ({translated_planet}) {p_house}ମ ଭାବରେ ରହିଥିବାରୁ:"
    elif lang == 'ta':
        return f"{lord_house_num}வது வீட்டின் அதிபதி ({translated_planet}) {p_house}வது இடத்தில் இருப்பதால்:"
    return f"{lord_house_num}వ స్థానాధిపతి ({translated_planet}) {p_house}వ స్థానములో ఉన్నందున:"



# Git path for Windows environment stability
GIT_PATH = r'C:\Users\gnana\AppData\Local\GitHubDesktop\app-3.5.8\resources\app\git\cmd\git.exe'

app = Flask(__name__)
app.secret_key = 'astrology-secret-key-2024'  # Required for session

@app.context_processor
def inject_translation():
    lang = 'te'
    if has_request_context():
        lang = request.args.get('lang') or session.get('lang') or request.cookies.get('lang') or 'te'
    
    def translate_text(text):
        if not text or lang == 'te':
            return text
        return tr(text, lang)
    return dict(_=translate_text, current_lang=lang)

# ---------------- Swiss Ephemeris ----------------
# swe.set_ephe_path(".")  # Removed to allow Render to use default pyswisseph bundled files
swe.set_sid_mode(swe.SIDM_LAHIRI)

PLANET_FLAGS = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

LAGNA_NAMES_TELUGU = [
    "మేషం","వృషభం","మిథునం","కర్కాటకం",
    "సింహం","కన్య","తులా","వృశ్చికం",
    "ధనస్సు","మకరం","కుంభం","మీనం"
]

PLANETS = {
    "సూర్యుడు": swe.SUN,
    "చంద్రుడు": swe.MOON,
    "కుజుడు": swe.MARS,
    "బుధుడు": swe.MERCURY,
    "గురు": swe.JUPITER,
    "శుక్రుడు": swe.VENUS,
    "శని": swe.SATURN,
    "రాహు": swe.TRUE_NODE
};

SPECIAL_HANDS = {
    "కుజుడు": [90, 210],
    "గురు": [120, 240],
    "శని": [60, 270]
}

SHORT_PLANETS_TELUGU = {
    "సూర్యుడు": "సూర్య",
    "చంద్రుడు": "చంద్ర",
    "కుజుడు": "కుజ",
    "బుధుడు": "బుధ",
    "గురు": "గురు",
    "శుక్రుడు": "శుక్ర",
    "శని": "శని",
    "రాహు": "రాహు",
    "కేతు": "కేతు",
    "భూమి": "భూమి",
    "మిత్ర": "మిత్ర",
    "చిత్ర": "చిత్ర",
    "లగ్నం": "లగ్నం"
}

# ---------------- Day name Telugu ----------------
DAY_TELUGU = {
    "Sunday": "ఆదివారం",
    "Monday": "సోమవారం",
    "Tuesday": "మంగళవారం",
    "Wednesday": "బుధవారం",
    "Thursday": "గురువారం",
    "Friday": "శుక్రవారం",
    "Saturday": "శనివారం"
}

# ---------------- Nakshatra ----------------
NAKSHATRAS_TELUGU = [
    "అశ్విని","భరణి","కృత్తిక","రోహిణి","మృగశిర","ఆర్ద్ర",
    "పునర్వసు","పుష్యమి","ఆశ్లేష","మఖ",
    "పూర్వఫల్గుణి","ఉత్తరఫల్గుణి",
    "హస్త","చిత్త","స్వాతి","విశాఖ",
    "అనూరాధ","జ్యేష్ఠ","మూల","పూర్వాషాఢ",
    "ఉత్తరాషాఢ","శ్రవణ","ధనిష్ఠ","శతభిష",
    "పూర్వాభాద్ర","ఉత్తరాభాద్ర","రేవతి"
]

NAKSHATRA_SIZE = 13 + 20/60
PADAM_SIZE = NAKSHATRA_SIZE / 4

TELUGU_YEARS = [
    "ప్రభవ", "విభవ", "శుక్ల", "ప్రమోదూత", "ప్రజోత్పత్తి", "ఆంగీరస", "శ్రీముఖ", "భావ", "యువ", "ధాత",
    "ఈశ్వర", "బహుధాన్య", "ప్రమాది", "విక్రమ", "వృష", "చిత్రభాను", "స్వభాను", "తారణ", "పార్థివ", "వ్యయ",
    "సర్వజిత్తు", "సర్వధారి", "విరోధి", "వికృతి", "ఖర", "నందన", "విజయ", "జయ", "మన్మథ", "దుర్ముఖి",
    "హేవిలంబి", "విలంబి", "వికారి", "శార్వరి", "ప్లవ", "శుభకృతు", "శోభకృతు", "క్రోధి", "విశ్వావసు", "పరాభవ",
    "ప్లవంగ", "కీలక", "సౌమ్య", "సాధారణ", "విరోధికృతు", "పరీధావి", "ప్రమాదీచ", "ఆనంద", "రాక్షస", "నల",
    "పింగళ", "కాళయుక్తి", "సిద్ధార్థి", "రౌద్రి", "దుర్మతి", "దుందుభి", "రుధిరోద్గారి", "రక్తాక్షి", "క్రోధన", "అక్షయ"
]

def get_am_pm_str(dt):
    """Formats a datetime object into a Telugu AM/PM string (ఉ:/సా:)"""
    time_str = dt.strftime("%I:%M")
    ampm = tr("ఉ: ") if dt.hour < 12 else tr("సా: ")
    return f"{ampm}{time_str}"

# ---------------- Panchangam Data ----------------
TITHIS_TELUGU = [
    "పాడ్యమి", "విదియ", "తదియ", "చవితి", "పంచమి", "షష్ఠి", "సప్తమి",
    "అష్టమి", "నవమి", "దశమి", "ఏకాదశి", "ద్వాదశి", "త్రయోదశి", "చతుర్దశి", "పౌర్ణమి"
]

TITHIS_KRISHNA_TELUGU = [
    "పాడ్యమి", "విదియ", "తదియ", "చవితి", "పంచమి", "షష్ఠి", "సప్తమి",
    "అష్టమి", "నవమి", "దశమి", "ఏకాదశి", "ద్వాదశి", "త్రయోదశి", "చతుర్దశి", "అమావాస్య"
]

YOGAS_TELUGU = [
    "విష్కంభ", "ప్రీతి", "ఆయుష్మాన్", "సౌభాగ్య", "శోభన", "అతిగండ", "సుకర్మ",
    "ధృతి", "శూల", "గండ", "వృధ్ధి", "ధ్రువ", "వ్యాఘాత", "హర్షణ", "వజ్ర", "సిద్ధి",
    "వ్యతీపాత", "వరియాన్", "పరీఘ", "శివ", "సిద్ధ", "సాధ్య", "శుభ", "శుక్ల",
    "బ్రహ్మ", "ఇంద్ర", "వైధృతి"
]

KARANAS_MOVABLE = ["బవ", "బాలవ", "కౌలవ", "తైతిల", "గర", "వణిజ", "విష్టి"]

# ---------------- DASA CALCULATION DATA ----------------
DASA_ORDER = [
    "సూర్య","చంద్ర","కుజ","రాహు","గురు","భూమి",
    "శని","బుధ","కేతు","శుక్ర","మిత్ర","చిత్ర"
]

DASA_YEARS = {
    "సూర్య":10, "చంద్ర":10, "కుజ":7, "రాహు":10,
    "గురు":13, "భూమి":13, "శని":13, "బుధ":10,
    "కేతు":7, "శుక్ర":13, "మిత్ర":7, "చిత్ర":7
}

PADAS_PER_DASA = 9
TOTAL_NAK_MINUTES = 13*60 + 20  # 800 minutes

# ---------------- ANTHARA DATA ----------------
ANTHARA_MONTHS = {
    "సూర్య": [
        ("సూర్య", 10), ("చంద్ర", 10), ("కుజ", 7), ("రాహు", 10),
        ("గురు", 13), ("భూమి", 13), ("శని", 13), ("బుధ", 10), 
        ("కేతు", 7), ("శుక్ర", 13), ("మిత్ర", 7), ("చిత్ర", 7)
    ],
    "చంద్ర": [
        ("చంద్ర", 10), ("కుజ", 7), ("రాహు", 10), ("గురు", 13),
        ("భూమి", 13), ("శని", 13), ("బుధ", 10), ("కేతు", 7), 
        ("శుక్ర", 13), ("మిత్ర", 7), ("చిత్ర", 7), ("సూర్య", 10)
    ],
    "కుజ": [
        ("కుజ", 4.9), ("రాహు", 7), ("గురు", 9.1), ("భూమి", 9.1),
        ("శని", 9.1), ("బుధ", 7), ("కేతు", 4), ("శుక్ర", 9), 
        ("మిత్ర", 4), ("చిత్ర", 4), ("సూర్య", 7), ("చంద్ర", 7)
    ],
    "రాహు": [
        ("రాహు", 10), ("గురు", 13), ("భూమి", 13), ("శని", 13), ("బుధ", 10),
        ("కేతు", 7), ("శుక్ర", 13), ("మిత్ర", 7), ("చిత్ర", 7),
        ("సూర్య", 10), ("చంద్ర", 10), ("కుజ", 7)
    ],
    "గురు": [
        ("గురు", 16.9), ("భూమి", 16.9), ("శని", 16.9), ("బుధ", 13), ("కేతు", 9),
        ("శుక్ర", 16.9), ("మిత్ర", 9.1), ("చిత్ర", 9.1), 
        ("సూర్య", 13), ("చంద్ర", 13), ("కుజ", 9.1), ("రాహు", 13)
    ],
    "భూమి": [
        ("భూమి", 16.9), ("శని", 16.9), ("బుధ", 13), ("కేతు", 9.1),
        ("శుక్ర", 16.9), ("మిత్ర", 9.1), ("చిత్ర", 9.1),
        ("సూర్య", 13), ("చంద్ర", 13), ("కుజ", 9.1),
        ("రాహు", 13), ("గురు", 16.9)
    ],
    "శని": [
        ("శని", 16.9), ("బుధ", 13), ("కేతు", 9.1), ("శుక్ర", 16.9),
        ("మిత్ర", 9.1), ("చిత్ర", 9.1), ("సూర్య", 13),
        ("చంద్ర", 13), ("కుజ", 9.1), ("రాహు", 13), ("గురు", 16.9), ("భూమి", 16.9)
    ],
    "బుధ": [
        ("బుధ", 10), ("కేతు", 7), ("శుక్ర", 13), ("మిత్ర", 7),
        ("చిత్ర", 7), ("సూర్య", 10), ("చంద్ర", 10),
        ("కుజ", 7), ("రాహు", 10), ("గురు", 13), ("భూమి", 13), ("శని", 13)
    ],
    "కేతు": [
        ("కేతు", 4.9), ("శుక్ర", 9.1), ("మిత్ర", 4.9), ("చిత్ర", 4.9),
        ("సూర్య", 7), ("చంద్ర", 7), ("కుజ", 4.9),
        ("రాహు", 7), ("గురు", 9.1), ("భూమి", 9.1), ("శని", 9.1), ("బుధ", 7)
    ],
    "శుక్ర": [
        ("శుక్ర", 16.9), ("మిత్ర", 9.1), ("చిత్ర", 9.1), 
        ("సూర్య", 13), ("చంద్ర", 13), ("కుజ", 9.1), ("రాహు", 13),
        ("గురు", 16.9), ("భూమి", 16.9), ("శని", 16.9), ("బుధ", 13), ("కేతు", 9.1)
    ],
    "మిత్ర": [
        ("మిత్ర", 4.9), ("చిత్ర", 4.9), ("సూర్య", 7),
        ("చంద్ర", 7), ("కుజ", 4), ("రాహు", 7), ("గురు", 9.1), ("భూమి", 9.1), 
        ("శని", 9.1), ("బుధ", 7), ("కేతు", 4.9), ("శుక్ర", 9.1)
    ],
    "చిత్ర": [
        ("చిత్ర", 4.9), ("సూర్య", 7), ("చంద్ర", 7),
        ("కుజ", 4.9), ("రాహు", 7), ("గురు", 9.1), ("భూమి", 9.1), ("శని", 9.1),
        ("బుధ", 7), ("కేతు", 4.9), ("శుక్ర", 9.1), ("మిత్ర", 4.9)
    ]
}

# ---------------- PLANET COLORS FOR VISUALIZATION ----------------
PLANET_COLORS = {
    "సూర్య": "#FFD700",  "సూర్యుడు": "#FFD700",  # Gold
    "చంద్ర": "#F0F8FF",  "చంద్రుడు": "#F0F8FF",  # Alice Blue
    "కుజ": "#FF4500",    "కుజుడు": "#FF4500",    # Orange Red
    "బుధ": "#32CD32",    "బుధుడు": "#32CD32",    # Lime Green
    "గురు": "#FFA500",   # Orange
    "శుక్ర": "#FF69B4",  "శుక్రుడు": "#FF69B4",  # Hot Pink
    "శని": "#696969",    # Dim Gray
    "రాహు": "#8B4513",   # Saddle Brown
    "కేతు": "#2F4F4F",   # Dark Slate Gray
    "భూమి": "#228B22",   # Forest Green
    "మిత్ర": "#9370DB",  # Medium Purple
    "చిత్ర": "#40E0D0"   # Turquoise
}

PLANET_ICONS = {
    "సూర్య": "☉",
    "చంద్ర": "☽",
    "కుజ": "♂",
    "బుధ": "☿",
    "గురు": "♃",
    "శుక్ర": "♀",
    "శని": "♄",
    "రాహు": "☊",
    "కేతు": "☋",
    "భూమి": "♁",
    "మిత్ర": "☆",
    "చిత్ర": "✦"
}

# Month mappings linking Telugu to English Gregorian periods
TELUGU_MASALU = [
    "చైత్ర", "వైశాఖ", "జ్యేష్ఠ", "ఆషాఢ", "శ్రావణ", "భాద్రపద", 
    "ఆశ్వయుజ", "కార్తీక", "మార్గశిర", "పుష్య", "మాఘ", "ఫాల్గుణ"
]

ENGLISH_MONTHS = [
    "(March - April)", "(April - May)", "(May - June)", "(June - July)",
    "(July - August)", "(August - September)", "(September - October)",
    "(October - November)", "(November - December)", "(December - January)",
    "(January - February)", "(February - March)"
]

# Rutuvulu mappings
TELUGU_RUTUVULU = [
    "వసంత", "గ్రీష్మ", "వర్ష", 
    "శరత్", "హేమంత", "శిశిర"
]

# ---------------- ASTROLOGICAL PARTIES ----------------
# Lagnas belonging to Guru Party
GURU_PARTY_LAGNAS = ["మేషం", "కర్కాటకం", "సింహం", "వృశ్చికం", "ధనస్సు", "మీనం"]
# Lagnas belonging to Sani Party
SANI_PARTY_LAGNAS = ["వృషభం", "మిథునం", "కన్య", "తులా", "మకరం", "కుంభం"]

# Favorable planets for each party
# Note: Rahu & Ketu act depending on house, but standardly align with the party or act as neutral.
# We map standard party friends for the "అనుకూలము (Favorable)" label
GURU_PARTY_PLANETS = ["సూర్య", "చంద్ర", "కుజ", "గురు", "కేతు", "భూమి"] 
SANI_PARTY_PLANETS = ["శని", "బుధ", "శుక్ర", "రాహు", "మిత్ర", "చిత్ర"]

# ---------------- DASA HELPER FUNCTIONS ----------------
def get_running_dasa(nak_index, padam):
    """Calculate running Mahadasha based on nakshatra and padam"""
    global_pada = nak_index * 4 + padam
    
    if global_pada == 0:
        global_pada = 108
    
    while global_pada > 108:
        global_pada -= 108
    
    idx = (global_pada - 1) // PADAS_PER_DASA
    
    idx = max(0, min(idx, len(DASA_ORDER) - 1))
    
    return DASA_ORDER[idx], idx

def is_dasa_favorable(lagna, planet):
    """Determine if a planet's Dasha is favorable based on birth Lagna Party"""
    if lagna in GURU_PARTY_LAGNAS:
        return planet in GURU_PARTY_PLANETS
    elif lagna in SANI_PARTY_LAGNAS:
        return planet in SANI_PARTY_PLANETS
    return False  # Fallback

def add_years(dt, years):
    """Add calendar years to datetime, handling leap years correctly"""
    try:
        return dt.replace(year=dt.year + int(years))
    except ValueError:
        # Handle Feb 29 on non-leap years
        return dt.replace(month=2, day=28, year=dt.year + int(years))

def add_months(dt, months):
    """Add calendar months (can be float) to datetime"""
    whole_months = int(months)
    fractional_days = int((months - whole_months) * 30.4368)
    
    month = dt.month - 1 + whole_months
    year = dt.year + month // 12
    month = month % 12 + 1
    # Number of days in each month of that year
    day = min(dt.day, [31,
                       29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28,
                       31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    dt_new = dt.replace(year=year, month=month, day=day)
    if fractional_days > 0:
        dt_new += datetime.timedelta(days=fractional_days)
    return dt_new

def nak_minutes(h, m):
    """Convert hours and minutes to total minutes"""
    return h * 60 + m

def get_exact_nakshatra_times(jd, nak_index):
    """
    Calculate the exact start and end Julian days for the given Nakshatra index.
    Iteratively tracks the Moon's longitude backwards and forwards using actual planetary speed.
    """
    NAKSHATRA_SIZE = 13 + 20/60
    target_start_deg = nak_index * NAKSHATRA_SIZE
    target_end_deg = (nak_index + 1) * NAKSHATRA_SIZE
    
    # Backward track for exact start time
    jd_start = jd
    for _ in range(15):
        m_info = swe.calc_ut(jd_start, swe.MOON, PLANET_FLAGS)
        moon_lon = m_info[0][0]
        speed = m_info[0][3] if len(m_info[0]) > 3 and m_info[0][3] > 0 else 13.176
        
        diff = (moon_lon - target_start_deg) % 360
        if diff > 180: diff -= 360
        
        jd_start -= diff / speed
        if abs(diff) < 0.0001:
            break
            
    # Forward track for exact end time
    jd_end = jd
    for _ in range(15):
        m_info = swe.calc_ut(jd_end, swe.MOON, PLANET_FLAGS)
        moon_lon = m_info[0][0]
        speed = m_info[0][3] if len(m_info[0]) > 3 and m_info[0][3] > 0 else 13.176
        
        diff = (target_end_deg - moon_lon) % 360
        if diff > 180: diff -= 360
        
        jd_end += diff / speed
        if abs(diff) < 0.0001:
            break
            
    return jd_start, jd_end

def get_exact_rasi_times(jd, rasi_index):
    """
    Calculate the exact start and end Julian days for the given Rasi index (30 deg segments).
    Iteratively tracks the Moon's longitude backwards and forwards using actual planetary speed.
    """
    target_start_deg = rasi_index * 30
    target_end_deg = (rasi_index + 1) * 30
    
    # Backward track for exact start time
    jd_start = jd
    for _ in range(15):
        m_info = swe.calc_ut(jd_start, swe.MOON, PLANET_FLAGS)
        moon_lon = m_info[0][0]
        speed = m_info[0][3] if len(m_info[0]) > 3 and m_info[0][3] > 0 else 13.176
        
        diff = (moon_lon - target_start_deg) % 360
        if diff > 180: diff -= 360
        
        jd_start -= diff / speed
        if abs(diff) < 0.0001:
            break
            
    # Forward track for exact end time
    jd_end = jd
    for _ in range(15):
        m_info = swe.calc_ut(jd_end, swe.MOON, PLANET_FLAGS)
        moon_lon = m_info[0][0]
        speed = m_info[0][3] if len(m_info[0]) > 3 and m_info[0][3] > 0 else 13.176
        
        diff = (target_end_deg - moon_lon) % 360
        if diff > 180: diff -= 360
        
        jd_end += diff / speed
        if abs(diff) < 0.0001:
            break
            
    return jd_start, jd_end

def get_exact_tithi_times(jd, tithi_index):
    """
    Calculate the exact start and end Julian days for the given Tithi index.
    Iteratively tracks the Sun-Moon elongation difference using relative velocity.
    """
    target_start_deg = tithi_index * 12
    target_end_deg = (tithi_index + 1) * 12
    
    # Backward track for exact start time
    jd_start = jd
    for _ in range(15):
        m_info = swe.calc_ut(jd_start, swe.MOON, PLANET_FLAGS)
        s_info = swe.calc_ut(jd_start, swe.SUN, PLANET_FLAGS)
        moon_lon = m_info[0][0]
        sun_lon = s_info[0][0]
        elongation = (moon_lon - sun_lon) % 360
        
        # Relative speed approx 12.19 deg/day
        speed = m_info[0][3] - s_info[0][3]
        if abs(speed) < 0.001:
            speed = 12.1907
        
        diff = (elongation - target_start_deg) % 360
        if diff > 180: diff -= 360
        
        jd_start -= diff / speed
        if abs(diff) < 0.0001:
            break
            
    # Forward track for exact end time
    jd_end = jd
    for _ in range(15):
        m_info = swe.calc_ut(jd_end, swe.MOON, PLANET_FLAGS)
        s_info = swe.calc_ut(jd_end, swe.SUN, PLANET_FLAGS)
        moon_lon = m_info[0][0]
        sun_lon = s_info[0][0]
        elongation = (moon_lon - sun_lon) % 360
        
        speed = m_info[0][3] - s_info[0][3]
        if abs(speed) < 0.001:
            speed = 12.1907
        
        diff = (target_end_deg - elongation) % 360
        if diff > 180: diff -= 360
        
        jd_end += diff / speed
        if abs(diff) < 0.0001:
            break
            
    return jd_start, jd_end

def is_date_within_range(check_date, start_date_str, end_date_str):
    """Check if a date falls within a date range"""
    try:
        check_dt = datetime.datetime.strptime(check_date, "%d-%m-%Y")
        start_dt = datetime.datetime.strptime(start_date_str, "%d-%m-%Y")
        end_dt = datetime.datetime.strptime(end_date_str, "%d-%m-%Y")
        
        return start_dt <= check_dt <= end_dt
    except:
        return False

# ---------------- GITHUB LOGGING HELPER ----------------
def log_user_to_github(name, dob, tob, place, mobile=None):
    """Log user data to user_data.txt using GitHub API or local file."""
    try:
        basedir = os.path.dirname(os.path.abspath(__file__))
        log_file = os.path.join(basedir, "user_data.txt")
        serial_no = 1
        
        # 1. Local Write (Always attempt as local backup)
        try:
            if os.path.exists(log_file):
                with open(log_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for line in reversed(lines):
                        line = line.strip()
                        if line and ". " in line:
                            try:
                                serial_no = int(line.split(". ")[0]) + 1
                                break
                            except Exception:
                                pass
            
            timestamp = datetime.datetime.now().strftime("%d-%b-%Y %H:%M:%S")
            phone_str = f", Mobile: {mobile}" if mobile else ""
            log_entry = f"{serial_no}. [{timestamp}] Name: {name}{phone_str}, DOB: {dob}, TOB: {tob}, Place: {place}\n"
            
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
            print(f"Data stored locally for: {name}")
        except Exception as e:
            print(f"Local file write error: {e}")

        final_serial = [serial_no]

        # 2. GitHub API Sync (For Render support)
        def github_api_sync(entry_name, entry_text):
            token = os.environ.get("GITHUB_TOKEN")
            if not token:
                print("GITHUB_TOKEN not found. Direct GitHub storage is disabled.")
                return

            repo = "krishnareddysajjala0-pixel/Timeastro"
            path = "user_data.txt"
            url_base = f"https://api.github.com/repos/{repo}/contents/{path}"
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
                "Cache-Control": "no-cache"
            }

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Cache buster to ensure we get the latest SHA from GitHub
                    url = f"{url_base}?t={int(time.time() * 1000)}"
                    
                    # Get current file content and SHA
                    res = requests.get(url, headers=headers)
                    if res.status_code == 200:
                        file_data = res.json()
                        current_content_b64 = file_data.get("content", "")
                        current_content = base64.b64decode(current_content_b64).decode("utf-8")
                        sha = file_data.get("sha")
                        
                        # Determine new serial number for remote file
                        lines = current_content.splitlines()
                        remote_serial = 1
                        for line in reversed(lines):
                            line = line.strip()
                            if line and ". " in line:
                                try:
                                    remote_serial = int(line.split(". ")[0]) + 1
                                    break
                                except Exception:
                                    pass
                        
                        final_serial[0] = remote_serial
                        
                        remote_timestamp = datetime.datetime.now().strftime("%d-%b-%Y %H:%M:%S")
                        new_entry = f"{remote_serial}. [{remote_timestamp}] Name: {entry_name}, DOB: {dob}, TOB: {tob}, Place: {place}\n"
                        new_content = current_content + (new_entry if current_content.endswith("\n") else "\n" + new_entry)
                        
                        # Update file
                        update_data = {
                            "message": f"Log user data: {entry_name} (API)",
                            "content": base64.b64encode(new_content.encode("utf-8")).decode("utf-8"),
                            "sha": sha
                        }
                        
                        put_res = requests.put(url_base, headers=headers, data=json.dumps(update_data))
                        if put_res.status_code in [200, 201]:
                            print(f"Successfully stored {entry_name} to GitHub via API.")
                            break
                        elif put_res.status_code == 409:
                            print(f"GitHub API conflict on attempt {attempt + 1}. Retrying...")
                            time.sleep(1)
                        else:
                            print(f"GitHub API update failed: {put_res.text}")
                            break
                    else:
                        print(f"Could not fetch user_data.txt from GitHub API: {res.text}")
                        break
                except Exception as e:
                    print(f"GitHub API storage error: {e}")
                    break

        # 3. Local Git Sync (For local Windows environment without GITHUB_TOKEN)
        def local_git_sync(entry_name):
            try:
                git_exec = GIT_PATH if os.path.exists(GIT_PATH) else "git"
                subprocess.run([git_exec, "add", "user_data.txt"], check=True, capture_output=True, cwd=basedir)
                subprocess.run([git_exec, "commit", "-m", f"Log new user data: {entry_name}"], capture_output=True, cwd=basedir)
                subprocess.run([git_exec, "push"], check=True, capture_output=True, cwd=basedir)
                print(f"Successfully pushed {entry_name} to GitHub via local Git.")
            except Exception as e:
                print(f"Local Git push failed: {e}")

        # 2. GitHub API Sync (Run synchronously for Vercel/Render serverless reliability)
        github_api_sync(name, log_entry)
        
        # 3. Local Git Sync (Run in background thread since it is local only)
        try:
            git_thread = threading.Thread(target=local_git_sync, args=(name,))
            git_thread.daemon = True
            git_thread.start()
        except Exception:
            pass

        # 4. Telegram Notification (Run in background thread so mobile app is instant)
        try:
            tele_thread = threading.Thread(target=send_telegram_notification, args=(name, dob, tob, place, final_serial[0], mobile))
            tele_thread.daemon = True
            tele_thread.start()
        except Exception as te:
            print(f"Telegram thread error: {te}")
        
    except Exception as e:
        print(f"Critical logging error: {e}")

@app.route('/log_user_data', methods=['POST'])
def log_user_data_endpoint():
    try:
        data = request.get_json(silent=True) or {}
        name = data.get('name', '')
        dob = data.get('dob', '')
        tob = data.get('tob', '')
        place = data.get('place', '')
        mobile = data.get('mobile', None)
        if name and dob:
            log_user_to_github(name, dob, tob, place, mobile=mobile)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


DEFAULT_TELEGRAM_BOT_TOKEN = "8288114667:AAG6l1GiHwDf0dz9DITMQi-cdxAZJjHJmMU"
DEFAULT_TELEGRAM_CHAT_ID = "5716746325"

def send_telegram_notification(name, dob, tob, place, serial_no=None, mobile=None):
    """Send user details to Telegram Bot channel/chat."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or DEFAULT_TELEGRAM_BOT_TOKEN
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or DEFAULT_TELEGRAM_CHAT_ID
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured. Skipping notification.")
        return

    # Fallback to calculate serial number locally if not passed
    if not serial_no:
        try:
            basedir = os.path.dirname(os.path.abspath(__file__))
            log_file = os.path.join(basedir, "user_data.txt")
            if os.path.exists(log_file):
                with open(log_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for line in reversed(lines):
                        line = line.strip()
                        if line and ". " in line:
                            try:
                                serial_no = int(line.split(". ")[0])
                                break
                            except Exception:
                                pass
        except Exception:
            pass

    try:
        serial_line = f"🔢 *Serial Number:* {serial_no}\n" if serial_no else ""
        phone_line = f"📱 *Mobile:* {mobile}\n" if mobile else ""
        message = (
            f"🌟 *New User Query on Android app!*\n\n"
            f"{serial_line}"
            f"👤 *Name:* {name}\n"
            f"{phone_line}"
            f"📅 *DOB:* {dob}\n"
            f"⏰ *TOB:* {tob}\n"
            f"📍 *Place:* {place}"
        )
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        try:
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                print("Telegram notification sent successfully!")
            else:
                print(f"Telegram notification failed: {res.text}")
        except Exception as api_e:
            print(f"Telegram API error: {api_e}")
            
    except Exception as e:
        print(f"Failed to send Telegram notification: {e}")


def calculate_anthara_periods(maha_name, start_date, end_date, lagna="", birth_dt=None):
    """Calculate anthara periods for a given Mahadasha"""
    antharas = []
    anthara_start = start_date
    
    if maha_name in ANTHARA_MONTHS:
        for planet, months in ANTHARA_MONTHS[maha_name]:
            anthara_end = add_months(anthara_start, months)
            
            is_favorable = is_dasa_favorable(lagna, planet)
            color = "#22c55e" if is_favorable else "#ef4444"
            
            
            age_start_str = ""
            age_end_str = ""
            if birth_dt:
                age_start_days = (anthara_start - birth_dt).days
                if age_start_days >= 0:
                    age_start_y = age_start_days // 365
                    age_start_m = (age_start_days % 365) // 30
                    age_start_str = f"{age_start_y}సం, {age_start_m}నెలలు"
                else:
                    age_start_str = "0సం, 0నెలలు"
                
                age_end_days = (anthara_end - birth_dt).days
                if age_end_days >= 0:
                    age_end_y = age_end_days // 365
                    age_end_m = (age_end_days % 365) // 30
                    age_end_str = f"{age_end_y}సం, {age_end_m}నెలలు"

            if birth_dt and anthara_end < birth_dt:
                anthara_start = anthara_end
                continue

            disp_start = anthara_start
            if birth_dt and anthara_start < birth_dt:
                disp_start = birth_dt

            antharas.append({
                "anthara": planet,
                "start": disp_start.strftime("%d-%m-%Y"),
                "end": anthara_end.strftime("%d-%m-%Y"),
                "months": months,
                "color": color,
                "icon": PLANET_ICONS.get(planet, "•"),
                "is_favorable": is_favorable,
                "age_start": age_start_str,
                "age_end": age_end_str
            })
            anthara_start = anthara_end
    
    return antharas

def parse_telugu_time(time_str):
    """Parse Telugu time string like '3గం 52ని' to (hours, minutes)"""
    try:
        if 'గం' in time_str:
            parts = time_str.split('గం')
            hours = int(parts[0].strip())
            minutes = int(parts[1].replace('ని', '').strip())
            return hours, minutes
        else:
            # Try English format
            if 'h' in time_str.lower():
                parts = time_str.lower().split('h')
                hours = int(parts[0].strip())
                minutes = int(parts[1].replace('m', '').strip())
                return hours, minutes
            else:
                # Try colon format
                if ':' in time_str:
                    h, m = time_str.split(':')
                    return int(h), int(m)
                else:
                    return 0, 0
    except:
        return 0, 0

def get_planet_color(planet_name):
    """Get color for a planet"""
    return PLANET_COLORS.get(planet_name, "#666666")

def get_planet_icon(planet_name):
    """Get icon for a planet"""
    return PLANET_ICONS.get(planet_name, "•")

# ---------------- ROUTES ----------------
IP_LOCATION_CACHE = {"data": None, "timestamp": 0}

def get_server_ip_location():
    import time
    now = time.time()
    if IP_LOCATION_CACHE["data"] and (now - IP_LOCATION_CACHE["timestamp"]) < 3600:
        return IP_LOCATION_CACHE["data"]
    try:
        url = "https://ipapi.co/json/"
        resp = requests.get(url, headers={"User-Agent": "RavanAstroApp/1.0"}, timeout=2.5)
        if resp.status_code == 200:
            d = resp.json()
            city = d.get("city") or ""
            region = d.get("region") or ""
            country = d.get("country_name") or ""
            lat = d.get("latitude")
            lon = d.get("longitude")
            if lat is not None and lon is not None:
                disp = ", ".join([p for p in [city, region, country] if p]) or f"Location ({lat:.2f}, {lon:.2f})"
                loc = {
                    "available": True,
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "city": city,
                    "region": region,
                    "country": country,
                    "display_name": disp
                }
                IP_LOCATION_CACHE["data"] = loc
                IP_LOCATION_CACHE["timestamp"] = now
                return loc
    except Exception:
        pass
    return None

@app.route("/api/device_location", methods=["GET", "POST"])
@app.route("/api/ip_location", methods=["GET", "POST"])
def api_device_location():
    lat = os.environ.get("DEVICE_LAT", "").strip()
    lon = os.environ.get("DEVICE_LON", "").strip()
    if lat and lon:
        try:
            return jsonify({
                "available": True,
                "latitude": float(lat),
                "longitude": float(lon),
                "lat": float(lat),
                "lon": float(lon),
                "display_name": os.environ.get("DEVICE_PLACE", "")
            })
        except ValueError:
            pass

    loc = get_server_ip_location()
    if loc:
        return jsonify(loc)

    return jsonify({
        "available": False,
        "latitude": None,
        "longitude": None
    })

# Local offline database of prominent cities and towns
LOCAL_CITIES = [
    {"display_name": "Hyderabad, Telangana, India", "lat": 17.3850, "lon": 78.4867},
    {"display_name": "Secunderabad, Telangana, India", "lat": 17.4399, "lon": 78.4983},
    {"display_name": "Vijayawada, Andhra Pradesh, India", "lat": 16.5062, "lon": 80.6480},
    {"display_name": "Visakhapatnam, Andhra Pradesh, India", "lat": 17.6868, "lon": 83.2185},
    {"display_name": "Guntur, Andhra Pradesh, India", "lat": 16.3067, "lon": 80.4365},
    {"display_name": "Tirupati, Andhra Pradesh, India", "lat": 13.6288, "lon": 79.4192},
    {"display_name": "Kurnool, Andhra Pradesh, India", "lat": 15.8281, "lon": 78.0373},
    {"display_name": "Nellore, Andhra Pradesh, India", "lat": 14.4426, "lon": 79.9865},
    {"display_name": "Rajahmundry, Andhra Pradesh, India", "lat": 17.0005, "lon": 81.8040},
    {"display_name": "Kakinada, Andhra Pradesh, India", "lat": 16.9891, "lon": 82.2475},
    {"display_name": "Warangal, Telangana, India", "lat": 17.9689, "lon": 79.5941},
    {"display_name": "Karimnagar, Telangana, India", "lat": 18.4386, "lon": 79.1288},
    {"display_name": "Nizamabad, Telangana, India", "lat": 18.6725, "lon": 78.0941},
    {"display_name": "Khammam, Telangana, India", "lat": 17.2473, "lon": 80.1514},
    {"display_name": "Anantapur, Andhra Pradesh, India", "lat": 14.6819, "lon": 77.6006},
    {"display_name": "Kadapa (Cuddapah), Andhra Pradesh, India", "lat": 14.4673, "lon": 78.8242},
    {"display_name": "Vizianagaram, Andhra Pradesh, India", "lat": 18.1067, "lon": 83.3956},
    {"display_name": "Eluru, Andhra Pradesh, India", "lat": 16.7107, "lon": 81.0952},
    {"display_name": "Ongole, Andhra Pradesh, India", "lat": 15.5057, "lon": 80.0499},
    {"display_name": "Nandyal, Andhra Pradesh, India", "lat": 15.4886, "lon": 78.4836},
    {"display_name": "Machilipatnam, Andhra Pradesh, India", "lat": 16.1875, "lon": 81.1389},
    {"display_name": "Tenali, Andhra Pradesh, India", "lat": 16.2437, "lon": 80.6400},
    {"display_name": "Chittoor, Andhra Pradesh, India", "lat": 13.2172, "lon": 79.1003},
    {"display_name": "Hindupur, Andhra Pradesh, India", "lat": 13.8292, "lon": 77.4916},
    {"display_name": "Bhimavaram, Andhra Pradesh, India", "lat": 16.5449, "lon": 81.5212},
    {"display_name": "Madanapalle, Andhra Pradesh, India", "lat": 13.5560, "lon": 78.5010},
    {"display_name": "Srikakulam, Andhra Pradesh, India", "lat": 18.2949, "lon": 83.8938},
    {"display_name": "Gudivada, Andhra Pradesh, India", "lat": 16.4410, "lon": 80.9926},
    {"display_name": "Mahbubnagar, Telangana, India", "lat": 16.7488, "lon": 78.0035},
    {"display_name": "Nalgonda, Telangana, India", "lat": 17.0575, "lon": 79.2684},
    {"display_name": "Suryapet, Telangana, India", "lat": 17.1439, "lon": 79.6239},
    {"display_name": "Siddipet, Telangana, India", "lat": 18.1018, "lon": 78.8520},
    {"display_name": "Mancherial, Telangana, India", "lat": 18.8679, "lon": 79.4639},
    {"display_name": "Adilabad, Telangana, India", "lat": 19.6641, "lon": 78.5320},
    {"display_name": "Bengaluru (Bangalore), Karnataka, India", "lat": 12.9716, "lon": 77.5946},
    {"display_name": "Chennai (Madras), Tamil Nadu, India", "lat": 13.0827, "lon": 80.2707},
    {"display_name": "Mumbai (Bombay), Maharashtra, India", "lat": 19.0760, "lon": 72.8777},
    {"display_name": "New Delhi, Delhi, India", "lat": 28.6139, "lon": 77.2090},
    {"display_name": "Kolkata (Calcutta), West Bengal, India", "lat": 22.5726, "lon": 88.3639},
    {"display_name": "Pune, Maharashtra, India", "lat": 18.5204, "lon": 73.8567},
    {"display_name": "Ahmedabad, Gujarat, India", "lat": 23.0225, "lon": 72.5714},
    {"display_name": "Jaipur, Rajasthan, India", "lat": 26.9124, "lon": 75.7873},
    {"display_name": "Bhubaneswar, Odisha, India", "lat": 20.2961, "lon": 85.8245},
    {"display_name": "Cuttack, Odisha, India", "lat": 20.4625, "lon": 85.8828},
    {"display_name": "Puri, Odisha, India", "lat": 19.8135, "lon": 85.8312},
    {"display_name": "Kochi, Kerala, India", "lat": 9.9312, "lon": 76.2673},
    {"display_name": "Thiruvananthapuram, Kerala, India", "lat": 8.5241, "lon": 76.9366},
    {"display_name": "Coimbatore, Tamil Nadu, India", "lat": 11.0168, "lon": 76.9558},
    {"display_name": "Madurai, Tamil Nadu, India", "lat": 9.9252, "lon": 78.1198},
    {"display_name": "Mysuru (Mysore), Karnataka, India", "lat": 12.2958, "lon": 76.6394},
    {"display_name": "Dubai, United Arab Emirates", "lat": 25.2048, "lon": 55.2708},
    {"display_name": "London, United Kingdom", "lat": 51.5074, "lon": -0.1278},
    {"display_name": "New York, NY, USA", "lat": 40.7128, "lon": -74.0060},
    {"display_name": "San Francisco, CA, USA", "lat": 37.7749, "lon": -122.4194},
    {"display_name": "Dallas, TX, USA", "lat": 32.7767, "lon": -96.7970},
    {"display_name": "Chicago, IL, USA", "lat": 41.8781, "lon": -87.6298},
    {"display_name": "Toronto, Ontario, Canada", "lat": 43.6532, "lon": -79.3832},
    {"display_name": "Sydney, NSW, Australia", "lat": -33.8688, "lon": 151.2093},
    {"display_name": "Singapore", "lat": 1.3521, "lon": 103.8198}
]

@app.route("/api/search_place")
@app.route("/api/search_location")
def api_search_place():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify([])
    
    q_lower = q.lower()
    results = []
    seen = set()

    # Match in local offline dataset first
    for city in LOCAL_CITIES:
        name = city["display_name"]
        if q_lower in name.lower():
            results.append({
                "display_name": city["display_name"],
                "lat": city["lat"],
                "lon": city["lon"],
                "type": "city"
            })
            seen.add(name.lower())

    # Try external Nominatim with valid User-Agent if available
    try:
        url = f"https://nominatim.openstreetmap.org/search?format=json&limit=8&addressdetails=1&q={requests.utils.quote(q)}"
        headers = {"User-Agent": "RavanAstroApp/1.0 (info@ravanastro.com)"}
        resp = requests.get(url, headers=headers, timeout=2.5)
        if resp.status_code == 200:
            for item in resp.json():
                d_name = item.get("display_name", "")
                if d_name.lower() not in seen:
                    results.append({
                        "display_name": d_name,
                        "lat": float(item.get("lat", 0)),
                        "lon": float(item.get("lon", 0)),
                        "type": item.get("type", "city")
                    })
                    seen.add(d_name.lower())
    except Exception:
        pass

    return jsonify(results[:10])

@app.route("/api/reverse_geocode")
def api_reverse_geocode():
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    if not lat or not lon:
        return jsonify({"display_name": "Unknown Location"})
    
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except ValueError:
        return jsonify({"display_name": "Unknown Location"})

    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat_f}&lon={lon_f}&zoom=10&addressdetails=1"
        headers = {"User-Agent": "RavanAstroApp/1.0 (info@ravanastro.com)"}
        resp = requests.get(url, headers=headers, timeout=2.5)
        if resp.status_code == 200:
            data = resp.json()
            addr = data.get("address", {})
            city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county") or ""
            state = addr.get("state") or ""
            country = addr.get("country") or ""
            place = ", ".join([p for p in [city, state, country] if p])
            if place:
                return jsonify({"display_name": place, "city": city, "state": state, "country": country})
    except Exception:
        pass

    # Fallback to closest local city or coordinates
    best_name = f"Location ({lat_f:.2f}, {lon_f:.2f})"
    min_dist = 999999
    for c in LOCAL_CITIES:
        dist = abs(c["lat"] - lat_f) + abs(c["lon"] - lon_f)
        if dist < min_dist and dist < 0.6:
            min_dist = dist
            best_name = c["display_name"]
    return jsonify({"display_name": best_name})


@app.route("/")
def index():
    return render_template("index.html")

@app.before_request
def check_lang_query_param():
    lang = request.args.get('lang') or request.cookies.get('lang')
    if lang and lang in ['te', 'en', 'kn', 'hi', 'ta', 'ml', 'or']:
        session['lang'] = lang

@app.route("/set_lang/<lang>")
def set_lang(lang):
    if lang in ['te', 'en', 'kn', 'hi', 'ta', 'ml', 'or']:
        session['lang'] = lang
    next_page = request.args.get('next') or request.referrer or url_for('index')
    resp = make_response(redirect(next_page))
    resp.set_cookie('lang', lang, max_age=30*24*3600)
    return resp


def get_timezone_str(lat, lon):
    try:
        lat = float(lat)
        lon = float(lon)
        if 6.0 <= lat <= 38.0 and 68.0 <= lon <= 98.0:
            return "Asia/Kolkata"
        try:
            from timezonefinder import TimezoneFinder
            tf = TimezoneFinder()
            if hasattr(tf, 'timezone_at'):
                tz = tf.timezone_at(lat=lat, lng=lon) or tf.timezone_at(lng=lon, lat=lat)
            elif hasattr(tf, 'certain_timezone_at'):
                tz = tf.certain_timezone_at(lat=lat, lng=lon)
            else:
                tz = None
            if tz:
                return tz
        except Exception:
            pass
        try:
            import timezonefinderL
            tf = timezonefinderL.TimezoneFinder()
            tz = tf.timezone_at(lng=lon, lat=lat)
            if tz:
                return tz
        except Exception:
            pass
    except Exception as e:
        print("[get_timezone_str error]:", e)
    return "Asia/Kolkata"


def get_kundali_data(name, dob, tob, place, lat, lon):
    try:
        lat = float(lat) if lat is not None else 17.3850
    except (ValueError, TypeError):
        lat = 17.3850

    try:
        lon = float(lon) if lon is not None else 78.4867
    except (ValueError, TypeError):
        lon = 78.4867

    if not dob or len(str(dob).strip()) < 8:
        dob = datetime.datetime.now().strftime("%Y-%m-%d")

    if not tob or len(str(tob).strip()) < 3:
        tob = datetime.datetime.now().strftime("%H:%M")

    # Ensure standard Lahiri Ayanamsa is used for all calculations
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    
    # Day name
    day_eng = datetime.datetime.strptime(dob, "%Y-%m-%d").strftime("%A")
    day_name = DAY_TELUGU.get(day_eng, day_eng)

    # Determine Timezone based on Latitude and Longitude
    timezone_str = get_timezone_str(lat, lon)

    # Time: Local Time → UTC
    local_tz = pytz.timezone(timezone_str)
    local_dt = local_tz.localize(
        datetime.datetime.strptime(dob+" "+tob,"%Y-%m-%d %H:%M")
    )
    utc_dt = local_dt.astimezone(pytz.utc)

    jd = swe.julday(
        utc_dt.year, utc_dt.month, utc_dt.day,
        utc_dt.hour + utc_dt.minute/60 + utc_dt.second/3600
    )

    chart_data_temp = {r:[] for r in LAGNA_NAMES_TELUGU}
    base_pos = {}

    # Planets
    for name_p, pid in PLANETS.items():
        lonp = swe.calc_ut(jd, pid, PLANET_FLAGS)[0][0]
        base_pos[name_p] = lonp
        lagna = LAGNA_NAMES_TELUGU[int(lonp/30)]
        deg = lonp % 30
        d = int(deg)
        m = int((deg-d)*60)
        short_name = SHORT_PLANETS_TELUGU.get(name_p, name_p[0])
        html_str = f"<b class='full-name'>{name_p}</b><b class='short-name'>{short_name}</b> <small class='full-deg'>{d}°{m:02d}′</small><small class='short-deg'>{d}°</small>"
        chart_data_temp[lagna].append((deg, html_str))

    # Ketu
    rahu = base_pos["రాహు"]
    ketu = (rahu + 180) % 360
    base_pos["కేతు"] = ketu

    r = LAGNA_NAMES_TELUGU[int(ketu/30)]
    deg_k = ketu % 30
    d = int(deg_k)
    m = int((deg_k-d)*60)
    short_k = SHORT_PLANETS_TELUGU.get("కేతు", "కే")
    html_str = f"<b class='full-name'>కేతు</b><b class='short-name'>{short_k}</b> <small class='full-deg'>{d}°{m:02d}′</small><small class='short-deg'>{d}°</small>"
    chart_data_temp[r].append((deg_k, html_str))

    # Derived planets (Dasacharam Logic - Verified)
    derived = {
        "భూమి": (base_pos["సూర్యుడు"] + 180) % 360,
        "చిత్ర": (rahu + 3.3333) % 360,  # 1 pada offset
        "మిత్ర": (ketu + 3.3333) % 360   # 1 pada offset
    }

    for n, lonp in derived.items():
        base_pos[n] = lonp
        r = LAGNA_NAMES_TELUGU[int(lonp/30)]
        deg = lonp % 30
        d = int(deg)
        m = int((deg-d)*60)
        short_n = SHORT_PLANETS_TELUGU.get(n, n[0])
        html_str = f"<b class='full-name'>{n}</b><b class='short-name'>{short_n}</b> <small class='full-deg'>{d}°{m:02d}′</small><small class='short-deg'>{d}°</small>"
        chart_data_temp[r].append((deg, html_str))

    # Month mappings linking Telugu to English Gregorian periods
    TELUGU_MASALU = [
        "చైత్ర", "వైశాఖ", "జ్యేష్ఠ", "ఆషాఢ", "శ్రావణ", "భాద్రపద", 
        "ఆశ్వయుజ", "కార్తీక", "మార్గశిర", "పుష్య", "మాఘ", "ఫాల్గుణ"
    ]

    ENGLISH_MONTHS = [
        "(March - April)", "(April - May)", "(May - June)", "(June - July)",
        "(July - August)", "(August - September)", "(September - October)",
        "(October - November)", "(November - December)", "(December - January)",
        "(January - February)", "(February - March)"
    ]

    # Rutuvulu mappings
    TELUGU_RUTUVULU = [
        "వసంత", "గ్రీష్మ", "వర్ష", 
        "శరత్", "హేమంత", "శిశిర"
    ]

# Dasa parameters
    # Hand planets
    for n, base in base_pos.items():
        angles = [180] + SPECIAL_HANDS.get(n,[])
        for a in angles:
            hl = (base + a) % 360
            r = LAGNA_NAMES_TELUGU[int(hl/30)]
            deg = hl % 30
            d = int(deg)
            m = int((deg-d)*60)
            short_n = SHORT_PLANETS_TELUGU.get(n, n[0])
            html_str = f"<span class='hand'><span class='full-name'>{n}</span><span class='short-name'>{short_n}</span> <small class='full-deg'>{d}°{m:02d}′</small><small class='short-deg'>{d}°</small> <span style='font-size: 0.7em;'>👉</span></span>"
            chart_data_temp[r].append((deg, html_str))

    # Lagna
    houses, ascmc = swe.houses(jd, lat, lon)
    asc_tropical = ascmc[0]
    ayan = swe.get_ayanamsa_ut(jd)
    lagna_lon = (asc_tropical - ayan) % 360

    lagna = LAGNA_NAMES_TELUGU[int(lagna_lon/30)]
    
    # Calculate Lagna degree
    lagna_deg = int(lagna_lon % 30)
    lagna_min = int(((lagna_lon % 30) - lagna_deg) * 60)
    lagna_degree_str = f"{lagna_deg}°{lagna_min:02d}′"
    
    # Add Lagna to chart data
    short_l = SHORT_PLANETS_TELUGU.get("లగ్నం", "ల")
    lagna_short_deg = f"{lagna_deg}°"
    html_str = f"<b class='full-name'>లగ్నం</b><b class='short-name'>{short_l}</b> <small class='full-deg'>{lagna_degree_str}</small><small class='short-deg'>{lagna_short_deg}</small>"
    chart_data_temp[lagna].append((lagna_lon % 30, html_str))
    
    # Sort elements per house by degree
    chart_data = {}
    for r in LAGNA_NAMES_TELUGU:
        chart_data_temp[r].sort(key=lambda x: x[0])
        if chart_data_temp[r]:
            chart_data[r] = "<br>".join(item[1] for item in chart_data_temp[r]) + "<br>"
        else:
            chart_data[r] = ""

    # Nakshatra + Padam
    moon_lon = base_pos["చంద్రుడు"]
    nak_index = int(moon_lon / NAKSHATRA_SIZE)
    nakshatra = NAKSHATRAS_TELUGU[nak_index]

    nak_offset = moon_lon - (nak_index * NAKSHATRA_SIZE)
    padam = int(nak_offset / PADAM_SIZE) + 1

    # Use exact forward/backward tracking for more accurate Nakshatra times
    jd_start, jd_end = get_exact_nakshatra_times(jd, nak_index)
    
    elapsed_days = jd - jd_start
    elapsed_h = int(elapsed_days * 24)
    elapsed_m = int(((elapsed_days * 24) % 1) * 60)
    
    remain_days = jd_end - jd
    remain_h = int(remain_days * 24)
    remain_m = int(((remain_days * 24) % 1) * 60)
    
    total_days = jd_end - jd_start
    total_h = int(total_days * 24)
    total_m = int(((total_days * 24) % 1) * 60)
    nak_total_str = f"{total_h}గం {total_m}ని"

    # Calculate nak_start and nak_end strings
    ye_k, me_k, de_k, he_k = swe.revjul(jd_end)
    target_nak_e = pytz.utc.localize(datetime.datetime(*(int(ye_k), int(me_k), int(de_k), int(he_k)), int((he_k%1)*60))).astimezone(local_tz)
    nak_end_str = get_am_pm_str(target_nak_e)
    
    ys_k, ms_k, ds_k, hs_k = swe.revjul(jd_start)
    target_nak_s = pytz.utc.localize(datetime.datetime(*(int(ys_k), int(ms_k), int(ds_k), int(hs_k)), int((hs_k%1)*60))).astimezone(local_tz)
    nak_start_str = get_am_pm_str(target_nak_s)
    
    calc_date = local_dt.date()
    if target_nak_s.date() < calc_date:
        nak_start_str = f"నిన్న {nak_start_str}"
    elif target_nak_s.date() > calc_date:
        nak_start_str = f"రేపు {nak_start_str}"
        
    if target_nak_e.date() > calc_date:
        nak_end_str = f"రేపు {nak_end_str}"
    elif target_nak_e.date() < calc_date:
        nak_end_str = f"నిన్న {nak_end_str}"

    # House numbers
    houses_map = {}
    idx = LAGNA_NAMES_TELUGU.index(lagna)
    for i in range(12):
        houses_map[LAGNA_NAMES_TELUGU[(idx+i)%12]] = i+1

    # Calculate Panchangam components (Tithi, Yoga, Karana)
    sun_lon = base_pos["సూర్యుడు"]
    moon_lon = base_pos["చంద్రుడు"]

    # 1. Tithi
    diff = (moon_lon - sun_lon) % 360
    tithi_index = int(diff / 12)
    tithi_paksha = "శుక్ల పక్షం" if tithi_index < 15 else "కృష్ణ పక్షం"
    
    if tithi_index < 15:
        tithi_name = TITHIS_TELUGU[tithi_index]
    else:
        tithi_name = TITHIS_KRISHNA_TELUGU[tithi_index - 15]

    tithi_offset = diff - (tithi_index * 12)
    # Tithi spans 12 degrees roughly representing a 24-hour cycle. 
    # Calculate elapsed and remaining time proportionally
    t_elapsed_h = int((tithi_offset / 12) * 24)
    t_elapsed_m = int((((tithi_offset / 12) * 24) % 1) * 60)
    
    t_rem = 12 - tithi_offset
    t_remain_h = int((t_rem / 12) * 24)
    t_remain_m = int((((t_rem / 12) * 24) % 1) * 60)

    tithi_elapsed_str = f"{t_elapsed_h}గం {t_elapsed_m}ని"
    tithi_remaining_str = f"{t_remain_h}గం {t_remain_m}ని"

    # 2. Yoga
    yoga_index = int(((sun_lon + moon_lon) % 360) / NAKSHATRA_SIZE)
    yoga_name = YOGAS_TELUGU[yoga_index]

    # 3. Karana
    karana_idx = int(diff / 6) + 1
    if karana_idx == 1:
        karana_name = "కింస్తుఘ్న"
    elif 2 <= karana_idx <= 57:
        m_idx = (karana_idx - 2) % 7
        karana_name = KARANAS_MOVABLE[m_idx]
    elif karana_idx == 58:
        karana_name = "శకుని"
    elif karana_idx == 59:
        karana_name = "చతుష్పాద"
    elif karana_idx == 60:
        karana_name = "నాగ"
    else:
        karana_name = "N/A"

    # Telugu Year is calculated later after Telugu Masam is determined.

    # 5. Sunrise & Sunset times
    # 5. Sunrise & Sunset times
    # Get local midnight to ensure sunrise/sunset are calculated for the birthday itself
    local_midnight = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_midnight = local_midnight.astimezone(pytz.utc)
    jd_midnight = swe.julday(
        utc_midnight.year, utc_midnight.month, utc_midnight.day,
        utc_midnight.hour + utc_midnight.minute/60 + utc_midnight.second/3600
    )

    # 5. Sunrise & Sunset times
    # Get local midnight to ensure sunrise/sunset are calculated for the birthday itself
    local_midnight = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Using Astral for robust sunrise and sunset calculations instead of PySwisseph 
    # to avoid errors on platforms where Ephemeris files are missing (like Render).
    from astral import LocationInfo
    from astral.sun import sun
    
    loc = LocationInfo("Local", "Region", timezone_str, lat, lon)
    
    try:
        s = sun(loc.observer, date=local_midnight.date(), tzinfo=local_tz)
        res_riseUTC = s["sunrise"]
        res_setUTC = s["sunset"]
        
        # Convert Astral's timezone-aware response directly to the requested format
        suryodayam = (tr("ఉ: ") if res_riseUTC.hour < 12 else tr("సా: ")) + res_riseUTC.strftime("%I:%M")
        suryastamayam = (tr("ఉ: ") if res_setUTC.hour < 12 else tr("సా: ")) + res_setUTC.strftime("%I:%M")
    except Exception as e:
        print(f"Astral Sun Calculation Failed: {e}")
        suryodayam = tr("ఉ: ") + "06:00"
        suryastamayam = tr("సా: ") + "06:00"
    
    # Astral has already given us formatted 'suryodayam' and 'suryastamayam'

    # 6. Ayanam, Rutuvu, & Telugu Masam
    # Ayanam: Sun between 270 (Capricorn) and 90 (Cancer) is Uttarayana
    if sun_lon >= 270 or sun_lon < 90:
        ayanam = "ఉత్తరాయణం (Uttarayanam)"
    else:
        ayanam = "దక్షిణాయణం (Dakshinayanam)"
        
    # Rutuvu: 6 seasons, each spanning 60 degrees of solar longitude starting from 0 (Vasantha)
    rutu_index = int((sun_lon % 360) / 60)
    rutuvu = TELUGU_RUTUVULU[rutu_index]
    
    # Masam (Month): Exact Telugu Lunar Month mapped to Sun/Moon Amavasya boundaries
    def find_amavasya(jd_guess):
        jd_val = jd_guess
        for _ in range(10):
            m = swe.calc_ut(jd_val, swe.MOON)[0][0]
            s = swe.calc_ut(jd_val, swe.SUN)[0][0]
            df = (m - s) % 360
            if df > 180: df -= 360
            jd_val -= df / 12.190749
            if abs(df) < 0.0001:
                break
        return jd_val

    diff_moon_sun = (moon_lon - sun_lon) % 360
    days_since = diff_moon_sun / 12.190749
    days_to = (360 - diff_moon_sun) / 12.190749
    
    jd_start = find_amavasya(jd - days_since)
    jd_end = find_amavasya(jd + days_to)
    
    # Calculate exact month name mapping based on the Amavasya's Solar Sidereal intersection
    amavasya_trop_sun = swe.calc_ut(jd_start, swe.SUN)[0][0]
    amavasya_ayan = swe.get_ayanamsa_ut(jd_start)
    amavasya_sun_lon = (amavasya_trop_sun - amavasya_ayan) % 360
    lagna_idx = int((amavasya_sun_lon % 360) / 30)
    masam_index = (lagna_idx + 1) % 12
    telugu_masam_name = TELUGU_MASALU[masam_index]
    
    EN_TO_TELUGU_MONTHS = {
        "january": "జనవరి", "february": "ఫిబ్రవరి", "march": "మార్చి",
        "april": "ఏప్రిల్", "may": "మే", "june": "జూన్",
        "july": "జూలై", "august": "ఆగస్టు", "september": "సెప్టెంబర్",
        "october": "అక్టోబర్", "november": "నవంబర్", "december": "డిసెంబర్"
    }
    
    def format_jd(jd_time):
        y, m_dt, d, h = swe.revjul(jd_time)
        dt_val = datetime.datetime(y, m_dt, d, int(h), int((h%1)*60))
        dt_val = pytz.utc.localize(dt_val).astimezone(local_tz)
        en_month = dt_val.strftime("%B").lower()
        te_month = tr(EN_TO_TELUGU_MONTHS.get(en_month, en_month))
        return f"{te_month}-{d:02d}"

    telugu_masam = f"{masam_index+1}. {tr(telugu_masam_name)} {tr('మాసం')} ({format_jd(jd_start)} {tr('నుంచి')} {format_jd(jd_end)} {tr('వరకు')})"

    # 4. Telugu Year (Samvatsara) accurate calculation
    try:
        dt = datetime.datetime.strptime(dob + " " + tob, "%Y-%m-%d %H:%M")
    except Exception:
        dt = datetime.datetime.now()
        
    year = dt.year
    month = dt.month
    
    # Chaitra usually starts in March/April. 
    # If the Gregorian month is before July and Masam is Pushya(9), Magha(10), or Phalguna(11),
    # it implies Chaitra hasn't started for this Gregorian year yet.
    if month <= 6 and masam_index >= 9:
        adj_year = year - 1
    else:
        adj_year = year
        
    # Offset based on known cycle starting year (1987 was Prabhava)
    year_index = (adj_year - 1987) % 60
    telugu_year = TELUGU_YEARS[year_index]
    
    # 1987 (Prabhava, index 0) = Kaliyuga 5088. Using the exact cycle multiplier ties it perfectly.
    cycles_since_1987 = (adj_year - 1987) // 60
    kaliyuga_year = 5088 + (cycles_since_1987 * 60) + year_index
    
    # Thraitha Sakamu mapping: 2025 (Viswavasu) = 47.
    # Therefore, adj_year - 2025 gives the offset from 47.
    thraitha_sakamu = 47 + (adj_year - 2025)

    # 7. Extract Planetary Positions
    planet_positions = []
    for n, longt in base_pos.items():
        r = LAGNA_NAMES_TELUGU[int(longt/30)]
        d = int(longt % 30)
        m = int(((longt % 30) - d) * 60)
        
        # calculate nakshatra for the planet
        p_nak_idx = int(longt / NAKSHATRA_SIZE)
        p_nak_name = NAKSHATRAS_TELUGU[p_nak_idx]
        p_nak_offset = longt - (p_nak_idx * NAKSHATRA_SIZE)
        p_padam = int(p_nak_offset / PADAM_SIZE) + 1
        
        strength_pct = int(((longt % 30) / 30) * 100)
        
        # Check favorability using exact logic from birth chart
        green_planets = ["సూర్యుడు", "భూమి", "కుజుడు", "గురు", "కేతు", "చంద్రుడు"]
        # Favorable for Guru Lagnas, otherwise Sani Lagnas
        positive_lagnas = ["మీనం", "మేషం", "కర్కాటకం", "సింహం", "వృశ్చికం", "ధనస్సు"]
        
        is_green = any(p in n for p in green_planets)
        
        if lagna in positive_lagnas:
            color = "#22c55e" if is_green else "#ef4444"
        else:
            color = "#ef4444" if is_green else "#22c55e"
        
        planet_positions.append({
            "name": n,
            "lagna": r,
            "degree": f"{d}°{m:02d}′",
            "nakshatra": p_nak_name,
            "padam": p_padam,
            "strength": strength_pct,
            "color": color,
            "is_hand": False
        })

        # Process hands for this planet
        angles = [180] + SPECIAL_HANDS.get(n, [])
        for a in angles:
            hl = (longt + a) % 360
            hr = LAGNA_NAMES_TELUGU[int(hl/30)]
            hd = int(hl % 30)
            hm = int(((hl % 30) - hd) * 60)
            
            # Use same nakshatra logic for hand
            h_nak_idx = int(hl / NAKSHATRA_SIZE)
            h_nak_name = NAKSHATRAS_TELUGU[h_nak_idx]
            h_nak_offset = hl - (h_nak_idx * NAKSHATRA_SIZE)
            h_padam = int(h_nak_offset / PADAM_SIZE) + 1
            h_strength = int(((hl % 30) / 30) * 100)

            planet_positions.append({
                "name": n,
                "lagna": hr,
                "degree": f"{hd}°{hm:02d}′",
                "nakshatra": h_nak_name,
                "padam": h_padam,
                "strength": h_strength,
                "color": color,
                "is_hand": True
            })



    return {
        'name': name,
        'dob': dob,
        'tob': tob,
        'place': place,
        'lat': lat,
        'lon': lon,
        'timezone_str': timezone_str,
        'day_name': day_name,
        'nakshatra': nakshatra,
        'padam': padam,
        'nak_start': nak_start_str,
        'nak_end': nak_end_str,
        'nak_elapsed': f"{elapsed_h}గం {elapsed_m}ని",
        'nak_remaining': f"{remain_h}గం {remain_m}ని",
        'nak_total': nak_total_str,
        'elapsed_h': elapsed_h,
        'elapsed_m': elapsed_m,
        'lagna_deg': lagna_degree_str,
        'lagna': lagna,
        'moon_lon': moon_lon,
        'tithi_paksha': tithi_paksha,
        'tithi_name': tithi_name,
        'tithi_elapsed': tithi_elapsed_str,
        'tithi_remaining': tithi_remaining_str,
        'telugu_year': telugu_year,
        'year_index': year_index,
        'kaliyuga_year': kaliyuga_year,
        'thraitha_sakamu': thraitha_sakamu,
        'suryodayam': suryodayam,
        'suryastamayam': suryastamayam,
        'ayanam': ayanam,
        'rutuvu': rutuvu,
        'telugu_masam': telugu_masam,
        'planet_positions': planet_positions,
        'chart': chart_data,
        'houses': houses_map,
        'all_nakshatras': NAKSHATRAS_TELUGU,
        'nak_index': nak_index
    }

@app.route("/chart", methods=["GET", "POST"])
def chart():
    if request.method == "POST":
        name = request.form.get("name","")
        dob = request.form.get("dob","")
        tob = request.form.get("tob","")
        place = request.form.get("place","")
        lat = request.form.get("lat")
        lon = request.form.get("lon")
        
        session['chart_form'] = {
            'name': name, 'dob': dob, 'tob': tob, 'place': place,
            'lat': lat, 'lon': lon
        }
    else:
        form_data = session.get('chart_form', {})
        name = form_data.get('name', '')
        dob = form_data.get('dob', '')
        tob = form_data.get('tob', '')
        place = form_data.get('place', '')
        lat = form_data.get('lat')
        lon = form_data.get('lon')

    if not name or not dob or not lat or not lon:
        return redirect(url_for('index'))

    lat = float(lat)
    lon = float(lon)
    
    # Log User query to GitHub
    log_user_to_github(name, dob, tob, place)

    data = get_kundali_data(name, dob, tob, place, lat, lon)

    # Store birth info in session for other pages
    session['birth_info'] = data

    # Calculate dasha data for the print Mahadasha table
    dasha_data = get_dasha_info(data)

    return render_template("chart.html", **data, **dasha_data)

@app.route("/compare_kundali")
def compare_kundali():
    return render_template("compare_form.html")

@app.route("/compare_results", methods=["GET", "POST"])
def compare_results():
    if request.method == "POST":
        name1 = request.form.get("name1","")
        dob1 = request.form.get("dob1","")
        tob1 = request.form.get("tob1","")
        place1 = request.form.get("place1","")
        lat1 = request.form.get("lat1")
        lon1 = request.form.get("lon1")

        name2 = request.form.get("name2","")
        dob2 = request.form.get("dob2","")
        tob2 = request.form.get("tob2","")
        place2 = request.form.get("place2","")
        lat2 = request.form.get("lat2")
        lon2 = request.form.get("lon2")
        
        chart_type = request.form.get("chart_type", "standard")
        
        session['compare_form'] = {
            'name1': name1, 'dob1': dob1, 'tob1': tob1, 'place1': place1, 'lat1': lat1, 'lon1': lon1,
            'name2': name2, 'dob2': dob2, 'tob2': tob2, 'place2': place2, 'lat2': lat2, 'lon2': lon2,
            'chart_type': chart_type
        }
    else:
        form_data = session.get('compare_form', {})
        name1 = form_data.get('name1', '')
        dob1 = form_data.get('dob1', '')
        tob1 = form_data.get('tob1', '')
        place1 = form_data.get('place1', '')
        lat1 = form_data.get('lat1')
        lon1 = form_data.get('lon1')
        
        name2 = form_data.get('name2', '')
        dob2 = form_data.get('dob2', '')
        tob2 = form_data.get('tob2', '')
        place2 = form_data.get('place2', '')
        lat2 = form_data.get('lat2')
        lon2 = form_data.get('lon2')

        chart_type = request.args.get("chart_type", form_data.get('chart_type', 'standard'))

    if not name1 or not dob1 or not lat1 or not lon1 or not name2 or not dob2 or not lat2 or not lon2:
        return redirect(url_for('compare_kundali'))

    data1 = get_kundali_data(name1, dob1, tob1, place1, float(lat1), float(lon1))
    data2 = get_kundali_data(name2, dob2, tob2, place2, float(lat2), float(lon2))

    nakshatra_boxes1 = build_nakshatra_pada_boxes(data1)
    nakshatra_boxes2 = build_nakshatra_pada_boxes(data2)

    log_user_to_github(name1 + " (Compare 1)", dob1, tob1, place1)
    log_user_to_github(name2 + " (Compare 2)", dob2, tob2, place2)

    dasha_data1 = get_dasha_info(data1) if isinstance(data1, dict) else {}
    dasha_data2 = get_dasha_info(data2) if isinstance(data2, dict) else {}

    p1_full = {**data1, **dasha_data1}
    p2_full = {**data2, **dasha_data2}

    return render_template(
        "compare_results.html",
        p1=p1_full,
        p2=p2_full,
        nakshatra_boxes1=nakshatra_boxes1,
        nakshatra_boxes2=nakshatra_boxes2,
        chart_type=chart_type
    )


@app.route("/transit_chart", methods=["POST"])
def transit_chart():
    lat = request.form.get("lat")
    lon = request.form.get("lon")
    timezone_str = request.form.get("timezone", "Asia/Kolkata")
    
    if not lat or not lon:
        return "❌ Location not provided", 400

    lat = float(lat)
    lon = float(lon)

    local_tz = pytz.timezone(timezone_str)
    local_dt = datetime.datetime.now(local_tz)
    utc_dt = local_dt.astimezone(pytz.utc)

    jd = swe.julday(
        utc_dt.year, utc_dt.month, utc_dt.day,
        utc_dt.hour + utc_dt.minute/60 + utc_dt.second/3600
    )

    chart_data_temp = {r:[] for r in LAGNA_NAMES_TELUGU}
    base_pos = {}

    for name_p, pid in PLANETS.items():
        lonp = swe.calc_ut(jd, pid, PLANET_FLAGS)[0][0]
        base_pos[name_p] = lonp
        lagna = LAGNA_NAMES_TELUGU[int(lonp/30)]
        deg = lonp % 30
        d = int(deg)
        m = int((deg-d)*60)
        short_name = SHORT_PLANETS_TELUGU.get(name_p, name_p[0])
        html_str = f"<b class='full-name'>{name_p}</b><b class='short-name'>{short_name}</b> <small class='full-deg'>{d}°{m:02d}′</small><small class='short-deg'>{d}°</small>"
        chart_data_temp[lagna].append((deg, html_str))

    rahu = base_pos["రాహు"]
    ketu = (rahu + 180) % 360
    base_pos["కేతు"] = ketu

    r = LAGNA_NAMES_TELUGU[int(ketu/30)]
    deg_k = ketu % 30
    d = int(deg_k)
    m = int((deg_k-d)*60)
    short_k = SHORT_PLANETS_TELUGU.get("కేతు", "కే")
    html_str = f"<b class='full-name'>కేతు</b><b class='short-name'>{short_k}</b> <small class='full-deg'>{d}°{m:02d}′</small><small class='short-deg'>{d}°</small>"
    chart_data_temp[r].append((deg_k, html_str))

    derived = {
        "భూమి": (base_pos["సూర్యుడు"] + 180) % 360,
        "చిత్ర": (rahu + 3.3333) % 360,
        "మిత్ర": (ketu + 3.3333) % 360
    }

    for n, lonp in derived.items():
        base_pos[n] = lonp
        r = LAGNA_NAMES_TELUGU[int(lonp/30)]
        deg = lonp % 30
        d = int(deg)
        m = int((deg-d)*60)
        short_n = SHORT_PLANETS_TELUGU.get(n, n[0])
        html_str = f"<b class='full-name'>{n}</b><b class='short-name'>{short_n}</b> <small class='full-deg'>{d}°{m:02d}′</small><small class='short-deg'>{d}°</small>"
        chart_data_temp[r].append((deg, html_str))

    for n, base in base_pos.items():
        angles = [180] + SPECIAL_HANDS.get(n,[])
        for a in angles:
            hl = (base + a) % 360
            r = LAGNA_NAMES_TELUGU[int(hl/30)]
            deg = hl % 30
            d = int(deg)
            m = int((deg-d)*60)
            short_n = SHORT_PLANETS_TELUGU.get(n, n[0])
            html_str = f"<span class='hand'><span class='full-name'>{n}</span><span class='short-name'>{short_n}</span> <small class='full-deg'>{d}°{m:02d}′</small><small class='short-deg'>{d}°</small> <span style='font-size: 0.7em;'>👉</span></span>"
            chart_data_temp[r].append((deg, html_str))

    houses, ascmc = swe.houses(jd, lat, lon)
    asc_tropical = ascmc[0]
    ayan = swe.get_ayanamsa_ut(jd)
    lagna_lon = (asc_tropical - ayan) % 360

    lagna = LAGNA_NAMES_TELUGU[int(lagna_lon/30)]
    
    lagna_deg = int(lagna_lon % 30)
    lagna_min = int(((lagna_lon % 30) - lagna_deg) * 60)
    lagna_degree_str = f"{lagna_deg}°{lagna_min:02d}′"
    
    short_l = SHORT_PLANETS_TELUGU.get("లగ్నం", "ల")
    lagna_short_deg = f"{lagna_deg}°"
    html_str = f"<b class='full-name'>లగ్నం</b><b class='short-name'>{short_l}</b> <small class='full-deg'>{lagna_degree_str}</small><small class='short-deg'>{lagna_short_deg}</small>"
    chart_data_temp[lagna].append((lagna_lon % 30, html_str))
    
    chart_data = {}
    for r in LAGNA_NAMES_TELUGU:
        chart_data_temp[r].sort(key=lambda x: x[0])
        if chart_data_temp[r]:
            chart_data[r] = "<br>".join(item[1] for item in chart_data_temp[r]) + "<br>"
        else:
            chart_data[r] = ""

    houses_map = {}
    idx = LAGNA_NAMES_TELUGU.index(lagna)
    for i in range(12):
        houses_map[LAGNA_NAMES_TELUGU[(idx+i)%12]] = i+1

    return render_template(
        "transit_partial.html",
        chart=chart_data,
        lagna=lagna,
        lagna_deg=lagna_degree_str,
        houses=houses_map,
        name="ఈ రోజు గ్రహ స్థితి",
        dob=local_dt.strftime("%d-%m-%Y"),
        tob=local_dt.strftime("%H:%M:%S")
    )

def get_dasha_info(birth_info):
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    dob = birth_info.get('dob', '')
    tob = birth_info.get('tob', '')
    name = birth_info.get('name', '')
    place = birth_info.get('place', '')
    day_name = birth_info.get('day_name', '')
    nakshatra = birth_info.get('nakshatra', '')
    lagna = birth_info.get('lagna', '')
    nak_elapsed = birth_info.get('nak_elapsed', '0గం 0ని')
    nak_remaining = birth_info.get('nak_remaining', '0గం 0ని')
    nak_index = birth_info.get('nak_index', 0)
    elapsed_h = birth_info.get('elapsed_h', 0)
    elapsed_m = birth_info.get('elapsed_m', 0)
    padam = birth_info.get('padam', 1)

    # Parse birth datetime
    timezone_str = birth_info.get('timezone_str', 'Asia/Kolkata')
    local_tz = pytz.timezone(timezone_str)
    try:
        birth_dt = local_tz.localize(
            datetime.datetime.strptime(dob + " " + tob, "%Y-%m-%d %H:%M")
        )
    except ValueError:
        return "❌ Invalid date/time format"

    # ===== CALCULATE FULL 120-YEAR DASA CYCLE =====
    
    # 1. Calculate birth Mahadasha
    birth_dasa, dasa_index = get_running_dasa(nak_index, padam)
    
    # 2. Precise time-based method (Rasi-based)
    # Get Julian Day for the birth time
    utc_dt = birth_dt.astimezone(pytz.utc)
    jd_birth = swe.julday(
        utc_dt.year, utc_dt.month, utc_dt.day,
        utc_dt.hour + utc_dt.minute/60 + utc_dt.second/3600
    )
    
    # Calculate exact start and end times for this 30-degree segment (Dasha segment)
    jd_s, jd_e = get_exact_rasi_times(jd_birth, dasa_index)
    
    total_duration_days = jd_e - jd_s
    elapsed_duration_days = jd_birth - jd_s
    
    # Precise fraction
    fraction = elapsed_duration_days / total_duration_days if total_duration_days > 0 else 0
    
    # Calculate elapsed and remaining time in birth rasi (Dasha segment) for display
    dasa_elapsed_h = int(elapsed_duration_days * 24)
    dasa_elapsed_m = int(((elapsed_duration_days * 24) % 1) * 60)
    dasa_elapsed_str = f"{dasa_elapsed_h}{tr('గం')} {dasa_elapsed_m}{tr('ని')}"
    
    dasa_remain_days = jd_e - jd_birth
    dasa_remain_h = int(dasa_remain_days * 24)
    dasa_remain_m = int(((dasa_remain_days * 24) % 1) * 60)
    dasa_remain_str = f"{dasa_remain_h}{tr('గం')} {dasa_remain_m}{tr('ని')}"
    
    birth_dasa_years = DASA_YEARS.get(birth_dasa, 10)
    elapsed_years_in_birth_dasa = birth_dasa_years * fraction
    
    elapsed_days_total = int(elapsed_years_in_birth_dasa * 365.25)
    gata_y = elapsed_days_total // 365
    gata_m = (elapsed_days_total % 365) // 30
    gata_d = (elapsed_days_total % 365) % 30
    gata_str = f"{gata_y}{tr('సం')} {gata_m}{tr('నెలలు')} {gata_d}{tr('రోజులు')}"
    
    remain_years_in_birth_dasa = birth_dasa_years - elapsed_years_in_birth_dasa
    remain_days_total = int(remain_years_in_birth_dasa * 365.25)
    bhogya_y = remain_days_total // 365
    bhogya_m = (remain_days_total % 365) // 30
    bhogya_d = (remain_days_total % 365) % 30
    bhogya_str = f"{bhogya_y}{tr('సం')} {bhogya_m}{tr('నెలలు')} {bhogya_d}{tr('రోజులు')}"
    
    # 3. Calculate start date of birth dasa (before birth)
    birth_dasa_start = birth_dt - datetime.timedelta(days=int(elapsed_years_in_birth_dasa * 365.25))
    birth_dasa_end = add_years(birth_dasa_start, birth_dasa_years)
    
    # 4. Get today's date for current dasa detection
    today = datetime.datetime.now(local_tz)
    today_str = today.strftime("%d-%m-%Y")
    
    # 5. Calculate ALL 12 Mahadashas in sequence (120 years)
    all_dasas = []
    start_date = birth_dasa_start
    
    # Variables to track current dasa
    current_maha_index = -1
    current_maha_name = ""
    current_maha_start = ""
    current_maha_end = ""
    current_maha_years = 0
    current_maha_age_start = ""
    current_maha_age_end = ""
    current_anthara_name = ""
    
    # Start from birth dasa and go through all 12
    for i in range(12):
        dasa_index_calc = (dasa_index + i) % 12
        dasa_name = DASA_ORDER[dasa_index_calc]
        dasa_years = DASA_YEARS.get(dasa_name, 10)
        
        end_date = add_years(start_date, dasa_years)
        start_str = start_date.strftime("%d-%m-%Y")
        end_str = end_date.strftime("%d-%m-%Y")
        
        # Calculate Anthara dasas for this Mahadasha
        antharas = calculate_anthara_periods(dasa_name, start_date, end_date, lagna, birth_dt)
        
        # Check if TODAY is within this dasa
        is_current_today = is_date_within_range(today_str, start_str, end_str)
        
        # Check if this is the birth dasa
        is_birth_dasa = (i == 0)
        
        # Determine favorability for full Mahadasa
        is_maha_favorable = is_dasa_favorable(lagna, dasa_name)
        
        # Add color and icon to dasa
        dasa_color = "#22c55e" if is_maha_favorable else "#ef4444"
        dasa_icon = PLANET_ICONS.get(dasa_name, "•")

        # Determine Status (Stiti)
        stiti = ""
        if is_current_today:
            stiti = "ప్రస్తుతం"
        elif end_date < today:
            stiti = "గతం"
        else:
            stiti = "భవిష్యత్తు"
        
        
        # Calculate Age
        age_start_str = ""
        age_end_str = ""
        
        age_start_days = (start_date - birth_dt).days
        if age_start_days >= 0:
            age_start_y = age_start_days // 365
            age_start_m = (age_start_days % 365) // 30
            age_start_str = f"{age_start_y}సం, {age_start_m}నెలలు"
        else:
            abs_days = abs(age_start_days)
            age_start_y = abs_days // 365
            age_start_m = (abs_days % 365) // 30
            if age_start_y == 0 and age_start_m == 0:
                age_start_str = "0సం, 0నెలలు"
            else:
                age_start_str = f"-{age_start_y}సం, {age_start_m}నెలలు"
            
        age_end_days = (end_date - birth_dt).days
        if age_end_days >= 0:
            age_end_y = age_end_days // 365
            age_end_m = (age_end_days % 365) // 30
            age_end_str = f"{age_end_y}సం, {age_end_m}నెలలు"

        disp_start_str = start_str

        # Add this Mahadasha to list
        all_dasas.append({
            "maha": dasa_name,
            "start": disp_start_str,
            "end": end_str,
            "years": dasa_years,
            "antharas": antharas,
            "is_current": is_current_today,
            "is_birth_dasa": is_birth_dasa,
            "color": dasa_color,
            "icon": dasa_icon,
            "is_favorable": is_maha_favorable,
            "age_start": age_start_str,
            "age_end": age_end_str,
            "stiti": stiti
        })
        
        # If this is current dasa, store its info
        if is_current_today:
            current_maha_index = i
            current_maha_name = dasa_name
            current_maha_start = start_str
            current_maha_end = end_str
            current_maha_years = dasa_years
            current_maha_age_start = age_start_str
            current_maha_age_end = age_end_str
            
            for ant in antharas:
                if is_date_within_range(today_str, ant["start"], ant["end"]):
                    current_anthara_name = ant["anthara"]
                    break
        
        # Move to next Mahadasha start date
        start_date = end_date
    
    # 6. If no dasa matches today, use birth dasa as current
    if current_maha_index == -1:
        today_dt = datetime.datetime.strptime(today_str, "%d-%m-%Y")
        birth_start_dt = datetime.datetime.strptime(birth_dasa_start.strftime("%d-%m-%Y"), "%d-%m-%Y")
        
        if today_dt < birth_start_dt:
            current_maha_index = 0
        else:
            current_maha_index = 11
        
        current_maha_name = all_dasas[current_maha_index]["maha"]
        current_maha_start = all_dasas[current_maha_index]["start"]
        current_maha_end = all_dasas[current_maha_index]["end"]
        current_maha_years = all_dasas[current_maha_index]["years"]
        current_dasa_favorable = all_dasas[current_maha_index]["is_favorable"]
        current_maha_age_start = all_dasas[current_maha_index].get("age_start", "")
        current_maha_age_end = all_dasas[current_maha_index].get("age_end", "")
        
        for ant in all_dasas[current_maha_index]["antharas"]:
            if is_date_within_range(today_str, ant["start"], ant["end"]):
                current_anthara_name = ant["anthara"]
                break
    else:
        current_dasa_favorable = is_dasa_favorable(lagna, current_maha_name)
    
    # 7. Calculate elapsed/remaining for CURRENT dasa
    current_start_dt = local_tz.localize(datetime.datetime.strptime(current_maha_start, "%d-%m-%Y"))
    current_end_dt = local_tz.localize(datetime.datetime.strptime(current_maha_end, "%d-%m-%Y"))
    
    # Calculate elapsed days in current dasa
    total_days_current = (current_end_dt - current_start_dt).days
    elapsed_days_current = (today - current_start_dt).days
    
    # Ensure days are within range
    elapsed_days_current = max(0, min(elapsed_days_current, total_days_current))
    
    elapsed_years_current = elapsed_days_current / 365.25
    remaining_years_current = (total_days_current - elapsed_days_current) / 365.25
    
    # 8. Calculate total years covered
    total_years_covered = sum(dasa.get("years", 10) for dasa in all_dasas)
    
    # 9. Current year for reference
    current_year = datetime.datetime.now().year
    
    # 10. Get planet colors and icons for current dasa
    current_dasa_color = PLANET_COLORS.get(current_maha_name, "#FFD700")
    current_dasa_icon = PLANET_ICONS.get(current_maha_name, "☉")

   
    return {
        "maha": current_maha_name,
        "maha_start": current_maha_start,
        "maha_end": current_maha_end,
        "maha_age_start": current_maha_age_start,
        "maha_age_end": current_maha_age_end,
        "total_years": current_maha_years,
        "completed_years": round(elapsed_years_current, 2),
        "remaining_years": round(remaining_years_current, 2),
        "current_dasa_color": current_dasa_color,
        "current_dasa_icon": current_dasa_icon,
        "current_dasa_favorable": current_dasa_favorable,
        "all_dasas": all_dasas,
        "total_cycle_years": total_years_covered,
        "now_date": today_str,
        "dasa_elapsed": dasa_elapsed_str,
        "dasa_remaining": dasa_remain_str,
        "birth_dasa": birth_dasa,
        "gata_str": gata_str,
        "bhogya_str": bhogya_str,
        "current_anthara": current_anthara_name
    }

@app.route("/chart2", methods=["GET", "POST"])
def chart2():
    birth_info = session.get('birth_info', {})
    
    dob = birth_info.get('dob', '')
    tob = birth_info.get('tob', '')
    name = birth_info.get('name', '')
    place = birth_info.get('place', '')
    day_name = birth_info.get('day_name', '')
    nakshatra = birth_info.get('nakshatra', '')
    padam = birth_info.get('padam', 1)
    nak_elapsed = birth_info.get('nak_elapsed', '0గం 0ని')
    nak_remaining = birth_info.get('nak_remaining', '0గం 0ని')

    if not dob:
        return "❌ No birth info found"

    dasha_data = get_dasha_info(birth_info)

    return render_template(
        "chart2.html",
        name=name, dob=dob, tob=tob, place=place, day_name=day_name,
        nakshatra=nakshatra, padam=padam, nak_elapsed=nak_elapsed, nak_remaining=nak_remaining,
        **dasha_data,
        planet_colors=PLANET_COLORS,
    )


@app.route("/compare_dasha", methods=["GET", "POST"])
def compare_dasha():
    if request.method == "POST":
        name1 = request.form.get("name1","")
        dob1 = request.form.get("dob1","")
        tob1 = request.form.get("tob1","")
        place1 = request.form.get("place1","")
        lat1 = request.form.get("lat1")
        lon1 = request.form.get("lon1")

        name2 = request.form.get("name2","")
        dob2 = request.form.get("dob2","")
        tob2 = request.form.get("tob2","")
        place2 = request.form.get("place2","")
        lat2 = request.form.get("lat2")
        lon2 = request.form.get("lon2")
        
        session['dasha_form'] = {
            'name1': name1, 'dob1': dob1, 'tob1': tob1, 'place1': place1, 'lat1': lat1, 'lon1': lon1,
            'name2': name2, 'dob2': dob2, 'tob2': tob2, 'place2': place2, 'lat2': lat2, 'lon2': lon2
        }
    else:
        form_data = session.get('dasha_form', {})
        name1 = form_data.get('name1', '')
        dob1 = form_data.get('dob1', '')
        tob1 = form_data.get('tob1', '')
        place1 = form_data.get('place1', '')
        lat1 = form_data.get('lat1')
        lon1 = form_data.get('lon1')
        
        name2 = form_data.get('name2', '')
        dob2 = form_data.get('dob2', '')
        tob2 = form_data.get('tob2', '')
        place2 = form_data.get('place2', '')
        lat2 = form_data.get('lat2')
        lon2 = form_data.get('lon2')

    if not name1 or not dob1 or not lat1 or not lon1 or not name2 or not dob2 or not lat2 or not lon2:
        return redirect(url_for('compare_kundali'))

    data1 = get_kundali_data(name1, dob1, tob1, place1, float(lat1), float(lon1))
    data2 = get_kundali_data(name2, dob2, tob2, place2, float(lat2), float(lon2))
    
    dasha1 = get_dasha_info(data1)
    dasha2 = get_dasha_info(data2)

    now = datetime.datetime.now(pytz.timezone("Asia/Kolkata"))
    now_date = now.strftime("%d-%m-%Y")
    now_time = now.strftime("%H:%M")

    return render_template("compare_dasha.html", 
                         p1=data1, p2=data2, 
                         dasha1=dasha1, dasha2=dasha2, 
                         planet_colors=PLANET_COLORS,
                         now_date=now_date, now_time=now_time)

@app.route("/chart3")
def chart3():
    """Display Dwadasa Grahamula Phalitalu"""
    current_year = datetime.datetime.now().year
    birth_info = session.get('birth_info', {})
    lagna = birth_info.get('lagna', '')

    native_party = ""
    friends = []
    enemies = []

    if birth_info:
        planet_positions = birth_info.get('planet_positions', [])
        
        # Load dynamic constants and rules from JSON files
        ASTRO_CONSTANTS = load_rules('astro_constants.json')
        GURU_PARTY_LAGNAS = ASTRO_CONSTANTS.get('GURU_PARTY_LAGNAS', [])
        GURU_PARTY_PLANETS = ASTRO_CONSTANTS.get('GURU_PARTY_PLANETS', [])
        BITTER_ENEMIES = ASTRO_CONSTANTS.get('BITTER_ENEMIES', {})
        PLANET_RULERSHIPS = load_localized_constants().get('PLANET_RULERSHIPS', {})
        OWN_HOUSE_RULES = ASTRO_CONSTANTS.get('OWN_HOUSE_RULES', {})
        
        native_party = "గురు వర్గము" if lagna in GURU_PARTY_LAGNAS else "శని వర్గము"
        
        # Process planets
        results_data = []
        for p in planet_positions:
            p_name = p['name']
            p_lagna = p['lagna']
            
            # is_friend?
            is_green = any(gp in p_name for gp in GURU_PARTY_PLANETS)
            is_friend = (is_green == (native_party == "గురు వర్గము"))
            
            # is_own_house?
            own_house = "N/A"
            is_own_house = False
            for rule_name, rule_house in OWN_HOUSE_RULES.items():
                if rule_name in p_name:
                    own_house = rule_house
                    is_own_house = (p_lagna == rule_house)
                    break
            
            # bitter_enemy?
            bitter_enemy = None
            for be_key, be_val in BITTER_ENEMIES.items():
                if be_key in p_name:
                    bitter_enemy = be_val
                    break

            # detailed Rulership
            rulership = "N/A"
            for r_name, r_text in PLANET_RULERSHIPS.items():
                if r_name in p_name:
                    rulership = r_text
                    break

            results_data.append({
                "name": p_name,
                "current_lagna": p_lagna,
                "own_house": own_house,
                "is_own_house": is_own_house,
                "is_friend": is_friend,
                "bitter_enemy": bitter_enemy,
                "color": p.get('color', '#ffffff'),
                "degree": p.get('degree', ''),
                "strength": p.get('strength', 0),
                "nakshatra": p.get('nakshatra', ''),
                "padam": p.get('padam', ''),
                "rulership": rulership,
                "is_hand": p.get('is_hand', False)
            })

        # Group into Friends and Enemies (Main planets only for the summary cards)
        friends = [p for p in results_data if p['is_friend'] and not p['is_hand']]
        enemies = [p for p in results_data if not p['is_friend'] and not p['is_hand']]

    name = birth_info.get('name', '') if birth_info else ''
    selected_lang = session.get('lang') or request.cookies.get('lang') or 'te'
    title = f"{name} {tr('ద్వాదశ గ్రహములు', selected_lang)}".strip() if name else tr('ద్వాదశ గ్రహములు', selected_lang)
    return render_template("chart3.html", 
                           name=name,
                           title=title,
                           current_year=current_year, 
                           lagna=lagna,
                           native_party=native_party,
                           friends=friends,
                           enemies=enemies)

@app.route("/go-to-birth-chart")
def go_to_birth_chart():
    """Redirect to birth chart with session data"""
    birth_info = session.get('birth_info', {})
    if birth_info:
        # Instead of just rendering chart.html which requires complex SWISSEPH calculations,
        # we repopulate a pseudo-form request to the main chart endpoint or we can 
        # just regenerate chart() if we refactored it. Since /chart expects POST data,
        # we'll build a simple redirect page that auto-submits.
        return f"""
        <html>
            <body onload="document.forms[0].submit()">
                <form action="/chart" method="POST">
                    <input type="hidden" name="name" value="{birth_info.get('name', '')}">
                    <input type="hidden" name="dob" value="{birth_info.get('dob', '')}">
                    <input type="hidden" name="tob" value="{birth_info.get('tob', '')}">
                    <input type="hidden" name="place" value="{birth_info.get('place', '')}">
                    <input type="hidden" name="lat" value="{birth_info.get('lat', '')}">
                    <input type="hidden" name="lon" value="{birth_info.get('lon', '')}">
                </form>
                <p>Loading Birth Chart...</p>
            </body>
        </html>
        """
    else:
        # Redirect to index if no birth info
        return redirect(url_for('index'))

@app.route("/results", methods=["GET", "POST"])
def results():
    """Calculate and display results based on planet own-house rules and party logic"""
    # Check for password authorization in session
    if 'results_authorized' not in session:
        # Check if password was submitted
        submitted_password = request.form.get('password')
        if submitted_password:
            if submitted_password == '050450':
                session['results_authorized'] = True
            else:
                return render_template("results_password.html", error=True)
        else:
            # Not authorized and no password submitted, show password entry page
            return render_template("results_password.html", error=False)

    birth_info = session.get('birth_info', {})
    if not birth_info:
        return redirect(url_for('index'))
    
    planet_positions = birth_info.get('planet_positions', [])
    lagna = birth_info.get('lagna', '')
    
    # Load dynamic constants and rules from JSON files
    ASTRO_CONSTANTS = load_rules('astro_constants.json')
    LAGNA_ORDER = ASTRO_CONSTANTS.get('LAGNA_ORDER', [])
    GURU_PARTY_LAGNAS = ASTRO_CONSTANTS.get('GURU_PARTY_LAGNAS', [])
    GURU_PARTY_PLANETS = ASTRO_CONSTANTS.get('GURU_PARTY_PLANETS', [])
    BITTER_ENEMIES = ASTRO_CONSTANTS.get('BITTER_ENEMIES', {})
    PLANET_RULERSHIPS = load_localized_constants().get('PLANET_RULERSHIPS', {})
    OWN_HOUSE_RULES = ASTRO_CONSTANTS.get('OWN_HOUSE_RULES', {})
    
    BHAVA_LORD_RULES = load_rules('bhava_lord_rules.json')
    DETAILED_BHAVA_MEANINGS = load_rules('detailed_bhava_meanings.json')
    
    # Ensure keys are integers where needed (DETAILED_BHAVA_MEANINGS)
    DETAILED_BHAVA_MEANINGS = {int(k): v for k, v in DETAILED_BHAVA_MEANINGS.items()}

    native_party = "గురు వర్గము" if lagna in GURU_PARTY_LAGNAS else "శని వర్గము"

    try:
        lagna_idx = LAGNA_ORDER.index(lagna)
    except ValueError:
        lagna_idx = 0

    # Process planets
    results_data = []
    for p in planet_positions:
        p_name = p['name']
        p_lagna = p['lagna']
        
        # is_friend?
        is_green = any(gp in p_name for gp in GURU_PARTY_PLANETS)
        is_friend = (is_green == (native_party == "గురు వర్గము"))
        
        # is_own_house?
        own_house = "N/A"
        is_own_house = False
        for rule_name, rule_house in OWN_HOUSE_RULES.items():
            if rule_name in p_name:
                own_house = rule_house
                is_own_house = (p_lagna == rule_house)
                break
        
        # bitter_enemy?
        bitter_enemy = None
        for be_key, be_val in BITTER_ENEMIES.items():
            if be_key in p_name:
                bitter_enemy = be_val
                break

        # detailed Rulership
        rulership = "N/A"
        for r_name, r_text in PLANET_RULERSHIPS.items():
            if r_name in p_name:
                rulership = r_text
                break

        results_data.append({
            "name": p_name,
            "current_lagna": p_lagna,
            "own_house": own_house,
            "is_own_house": is_own_house,
            "is_friend": is_friend,
            "bitter_enemy": bitter_enemy,
            "color": p.get('color', '#ffffff'),
            "degree": p.get('degree', ''),
            "strength": p.get('strength', 0),
            "nakshatra": p.get('nakshatra', ''),
            "padam": p.get('padam', ''),
            "rulership": rulership,
            "is_hand": p.get('is_hand', False)
        })

    # Group into Friends and Enemies (Main planets only for the summary cards)
    friends = [p for p in results_data if p['is_friend'] and not p['is_hand']]
    enemies = [p for p in results_data if not p['is_friend'] and not p['is_hand']]

    # Bhava Report
    RASI_LORDS = {v: k for k, v in OWN_HOUSE_RULES.items()}
    def get_placed_houses(planet_name):
        houses = set()
        for p in results_data:
            if planet_name in p['name']:
                try:
                    h = (LAGNA_ORDER.index(p['current_lagna']) - lagna_idx) % 12 + 1
                    houses.add(h)
                except ValueError:
                    continue
        return list(houses)

    # Pre-calculate lord rules grouped by placed house
    placed_rules_map = {i: [] for i in range(1, 13)}
    
    for i in range(12):
        lord_house_num = i + 1
        lord_lagna = LAGNA_ORDER[(lagna_idx + i) % 12]
        lord_planet = RASI_LORDS.get(lord_lagna)
        
        if lord_planet:
            p_houses = get_placed_houses(lord_planet)
            for p_house in p_houses:
                is_lord_friend = False
                for p in results_data:
                    if lord_planet in p['name']:
                        is_lord_friend = p['is_friend']
                        break
                
                lord_rule = BHAVA_LORD_RULES.get(str(p_house), {}).get(str(lord_house_num))
                if lord_rule:
                    rule_text = lord_rule.get("shubha", "") if is_lord_friend else lord_rule.get("paapa", "")
                    if rule_text:
                        # Find the planet's color
                        p_color = "#ffffff"
                        for p in results_data:
                            if lord_planet in p['name']:
                                p_color = p['color']
                                break
                        
                        lang = session.get('lang') or request.cookies.get('lang') or 'te' if has_request_context() else 'te'
                        header_text = format_lord_placement(lord_house_num, lord_planet, p_house, lang)
                        placed_rules_map[p_house].append(
                            f"<br><br><span style='color: {p_color};'><strong>{header_text}</strong> {rule_text}</span>"
                        )

    bhava_report = []
    for i in range(12):
        house_num = i + 1
        house_lagna = LAGNA_ORDER[(lagna_idx + i) % 12]
        # Planets in this house
        occ_planets = [p for p in results_data if p['current_lagna'] == house_lagna]
        p_info = [{
            "name": p['name'], 
            "degree": p['degree'], 
            "strength": p.get('strength', 0),
            "color": p['color'],
            "is_hand": p.get('is_hand', False)
        } for p in occ_planets]
        
        # Determine house state based on occupants
        # Rule: House is 'shubha' if at least one friend is present and NO enemies OR if more friends than enemies.
        # Simplified: If any friend, status = shubha. If only enemies, status = paapa. If empty, neutral.
        friends_in_house = [p for p in occ_planets if p['is_friend']]
        enemies_in_house = [p for p in occ_planets if not p['is_friend']]

        if friends_in_house:
            state = "shubha"
        elif enemies_in_house:
            state = "paapa"
        else:
            state = "neutral"

        bhava_data = DETAILED_BHAVA_MEANINGS[house_num]
        interpretation = bhava_data.get(state, bhava_data["neutral"])
        
        # Append Bhava Lord Logic grouped by placed house
        if placed_rules_map[house_num]:
            interpretation += "".join(placed_rules_map[house_num])
        
        # Specific Logic Expansion
        special_notes = []
        
        # ----------------- SPECIFIC PLANETARY RULES (Life Scenarios) -----------------
        
        # 4th House: Sun Rules
        if house_num == 4:
            sun_p = [p for p in occ_planets if "సూర్యుడు" in p['name']]
            if sun_p:
                p = sun_p[0]
                if p['is_friend']:
                    special_notes.append(f"<span style='color: {p['color']};'>సూర్యుడు 4వ లగ్నములో ఉండటమువలన మీకు పై అంతస్థు భవనములు కట్టించు ప్రేరణ చేయును. ఒకవేళ పేదవారైనా ఆ ఇంటిలో నివాసము కల్గునట్లు చేయును.</span> ")
                else:
                    special_notes.append(f"<span style='color: {p['color']};'>సూర్యుడు శత్రుగ్రహమై 4వ లగ్నములో ఉన్నందున గృహ సుఖములు లోపించును. ఉన్న పెద్ద ఇల్లును కూడా అమ్మి చిన్న ఇల్లును కొందామనుకొనును.</span> ")

        # 8th House: Mars and others
        if house_num == 8 and enemies_in_house:
            for p in enemies_in_house:
                if "రాహు" in p['name']: special_notes.append(f"<span style='color: {p['color']};'>పాముకాటు లేదా విషాహారం వలన ప్రమాదం.</span> ")
                elif "చంద్రుడు" in p['name']: special_notes.append(f"<span style='color: {p['color']};'>నీటి గండముతో మరణ భయం.</span> ")
                elif "శుక్రుడు" in p['name']: special_notes.append(f"<span style='color: {p['color']};'>అగ్ని వలన ప్రమాదం.</span> ")
                elif "బుధుడు" in p['name']: special_notes.append(f"<span style='color: {p['color']};'>దయ్యాల పీడ లేదా వైద్యులకు అంతుచిక్కని రోగము.</span> ")
                elif "కుజుడు" in p['name']: special_notes.append(f"<span style='color: {p['color']};'>ఆయుధాల చేత లేదా రక్తసిక్త ప్రమాదము (బాంబులు/తుపాకులు).</span> ")

        # 6th House: Mars, Mercury
        if house_num == 6:
            for p in occ_planets:
                if "కుజుడు" in p['name'] and not p['is_friend']:
                    special_notes.append(f"<span style='color: {p['color']};'>మృగముల చేత గాయపడుట, ఆయుధములచేత దాడి, వ్రణములు, లేదా టీబీ/క్యాన్సర్ వంటి రోగముల భయము.</span> ")
                if "బుధుడు" in p['name']:
                    if p['is_friend']:
                        special_notes.append(f"<span style='color: {p['color']};'>వైద్య విద్యలో రాణించుట, భూతవైద్యము కూడా తెలిసియుండుట.</span> ")
                    else:
                        special_notes.append(f"<span style='color: {p['color']};'>దయ్యాల బాధలు, దయ్యములు శరీరములో రోగరూపముగా ఉండి బాధింపవచ్చును.</span> ")

        # 7th House: Venus, Mars
        if house_num == 7:
            for p in occ_planets:
                if "శుక్రుడు" in p['name']:
                    if p['is_friend']:
                        special_notes.append(f"<span style='color: {p['color']};'>అందమైన, అనుకూలమైన భార్య/భర్త లభించును. ఆమె/అతని వలన మనశ్శాంతి, సుఖము ఉండును.</span> ")
                    else:
                        special_notes.append(f"<span style='color: {p['color']};'>కళత్రము వలన కష్టములు, మనఃశ్శాంతి లోపించును.</span> ")
                if "కుజుడు" in p['name'] and not p['is_friend']:
                    special_notes.append(f"<span style='color: {p['color']};'>యుక్తవయస్సులో వివాహము ఆలస్యమగును.</span> ")

        # 3rd House: Jupiter Gold Logic
        if house_num == 3:
            for p in occ_planets:
                if "గురు" in p['name']:
                    if p['is_friend']:
                        special_notes.append(f"<span style='color: {p['color']};'>బంగారము లేదా ధనము ఏదో ఒక విధంగా లభ్యమగుట (వ్యాపార లాభం లేదా అదృష్టం).</span> ")
                    else:
                        special_notes.append(f"<span style='color: {p['color']};'>ఉన్న బంగారమును కూడా అమ్మవలసిన పరిస్థితులు ఏర్పడును.</span> ")
            # Rahu behind Jupiter logic
            rahu_in_3_list = [p for p in occ_planets if "రాహు" in p['name']]
            guru_in_3_list = [p for p in occ_planets if "గురు" in p['name']]
            if rahu_in_3_list and guru_in_3_list:
                # Use Rahu's color for the combined threat
                special_notes.append(f"<span style='color: {rahu_in_3_list[0]['color']};'>రాహువు గురువు కలిసి ఉండటము వలన బంగారు దొంగలు ఎత్తుకొని పోవు భయమున్నది.</span> ")

        # 10th House: Career (Existing but enhanced)
        if house_num == 10 and occ_planets:
            for p in occ_planets:
                if "సూర్యుడు" in p['name'] or "చంద్రుడు" in p['name']:
                    special_notes.append(f"<span style='color: {p['color']};'>ప్రభుత్వ ఉన్నత ఉద్యోగి (కలెక్టర్) లేదా మంత్రి పదవి యోగం.</span> ")
                elif "కుజుడు" in p['name']:
                    if any("సూర్యుడు" in p2['name'] or "చంద్రుడు" in p2['name'] for p2 in occ_planets):
                        special_notes.append(f"<span style='color: {p['color']};'>మిలిటరీలో పెద్ద డాక్టరుగా పేరు తెచ్చుకొందురు.</span> ")
                    else:
                        special_notes.append(f"<span style='color: {p['color']};'>ప్రభుత్వ డాక్టరుగా లేదా గొప్ప సర్జన్ గా పేరు తెచ్చుకొందురు.</span> ")
                elif "శుక్రుడు" in p['name']:
                    special_notes.append(f"<span style='color: {p['color']};'>అష్టైశ్వర్యములతో కూడిన సుఖమయ జీవితం.</span> ")

        # 11th House: Gains
        if house_num == 11 and friends_in_house:
            for p in friends_in_house:
                if "బుధుడు" in p['name']: special_notes.append(f"<span style='color: {p['color']};'>కట్నకానుకల రూపంలో లబ్ది.</span> ")
                elif "గురు" in p['name']: special_notes.append(f"<span style='color: {p['color']};'>డొనేషన్లు లేదా విద్యాసంస్థల ద్వారా లాభం.</span> ")

        # 4th House again: Rahu illegal wealth
        if house_num == 4:
            for p in occ_planets:
                if "రాహు" in p['name']:
                    if p['is_friend']:
                        special_notes.append(f"<span style='color: {p['color']};'>దొంగవృత్తి లేదా దోపిడీల ద్వారా లక్షలు సంపాదించుట, సమాజములో భయంతో కూడిన గౌరవము.</span> ")
                    else:
                        special_notes.append(f"<span style='color: {p['color']};'>దొంగతనములలో దొరికిపోవుట, పోలీస్ కేసులు, జైలు జీవితము అనుభవించవలసి రావచ్చు.</span> ")

        # 5th House: Ketu God logic
        if house_num == 5:
            for p in occ_planets:
                if "కేతు" in p['name']:
                    if p['is_friend']:
                        special_notes.append(f"<span style='color: {p['color']};'>దేవుని వైపు చింత, హేతువాదిక జ్ఞానము, సత్యాన్వేషణలో దైవభక్తి పెరగడము.</span> ")
                    else:
                        special_notes.append(f"<span style='color: {p['color']};'>దైవజ్ఞానము మీద ఆసక్తి ఉండదు, పూర్తిగా ప్రపంచ జ్ఞానములోనే ఉండిపోవుట.</span> ")

        # Moon general water issues
        moon_enemy_list = [p for p in enemies_in_house if "చంద్రుడు" in p['name']]
        if moon_enemy_list:
            special_notes.append(f"<span style='color: {moon_enemy_list[0]['color']};'>చంద్రుడు వ్యతిరేఖముగా ఉన్నందున నీటి ఇబ్బందులు (బావులు ఎండిపోవుట, ఇంటిలో నీరు కారుట, బాత్ రూమ్ పైపులు చెడిపోవుట).</span> ")

        # Saturn general iron logic
        for p in occ_planets:
            if "శని" in p['name'] and p['is_friend']:
                special_notes.append(f"<span style='color: {p['color']};'>ఇనుము వ్యాపారములో మంచి లాభములు పొంది ధనికులయ్యే యోగము.</span> ")

        # ----------------- ADVANCED Q&A LOGIC -----------------

        # 7th House: Multiple Marriages / Secret Relations (Rahu/Ketu)
        if house_num == 7:
            rk_p = [p for p in occ_planets if any(x in p['name'] for x in ["రాహు", "కేతు"])]
            if rk_p:
                # Count opposing planets to see if Rahu/Ketu's effect is suppressed
                # "Opposing" here means planets not in their natural party
                rk_name = "రాహు" if "రాహు" in rk_p[0]['name'] else "కేతు"
                opposing_count = 0
                for p in occ_planets:
                    if rk_name == "రాహు" and any(x in p['name'] for x in ["సూర్యుడు", "చంద్రుడు", "కుజుడు", "గురు"]):
                        opposing_count += 1
                    elif rk_name == "కేతు" and any(x in p['name'] for x in ["శుక్రుడు", "శని", "బుధుడు"]):
                        opposing_count += 1
                
                if opposing_count >= 2:
                    special_notes.append(f"<span style='color: {rk_p[0]['color']};'>{rk_p[0]['name']} 7వ స్థానములో ఉన్నప్పటికీ, వ్యతిరేక గ్రహముల ప్రభావమువలన రెండవ వివాహము లేదా అక్రమ సంబంధముల ఆటంకములు తొలగిపోవును.</span> ")
                else:
                    special_notes.append(f"<span style='color: {rk_p[0]['color']};'>{rk_p[0]['name']} 7వ స్థానములో ఉన్నందున రెండవ పెళ్ళికి లేదా అక్రమ సంబంధములకు అవకాశమున్నది.</span> ")

        # Lagna (1st House): Discord Logic (Mars + Venus)
        if house_num == 1:
            has_mars = any("కుజుడు" in p['name'] for p in occ_planets)
            has_venus = any("శుక్రుడు" in p['name'] for p in occ_planets)
            if has_mars and has_venus:
                # Find mars color (they should be same party-based color but anyway)
                m_color = "#ffffff"
                for p in occ_planets:
                    if "కుజుడు" in p['name']:
                        m_color = p['color']
                        break
                # Check if they are enemies for this lagna
                # Mars is Guru party, Venus is Sani party. They are always bitter enemies.
                special_notes.append(f"<span style='color: {m_color};'>కుజుడు మరియు శుక్రుడు ఇద్దరూ లగ్నములో కలిసి ఉన్నందున, భార్యాభర్తల మధ్య అన్యోన్యత లోపించి తరచూ పోట్లాటలు జరిగే సూచనలున్నవి.</span> ")

        # 5th House vs 3, 7, 11: Intelligence (Moon)
        if house_num == 5:
            moon_p = [p for p in occ_planets if "చంద్రుడు" in p['name']]
            if moon_p:
                special_notes.append(f"<span style='color: {moon_p[0]['color']};'>చంద్రుడు 5వ స్థానములో ఉన్నందున మీరు గొప్ప మేధాశక్తి మరియు మంచి బుద్ధి గలవారై ఉంటారు. ఏ సమస్యకైనా సులభముగా జవాబు చెప్పగలరు.</span> ")
        elif house_num in [3, 7, 11]:
            moon_p = [p for p in occ_planets if "చంద్రుడు" in p['name']]
            if moon_p:
                special_notes.append(f"<span style='color: {moon_p[0]['color']};'>చంద్రుడు పాపస్థానములో (3, 7, 11) ఉన్నందున తెలివితేటలు తక్కువగా ఉండును లేదా ప్రవర్తనలో అజ్ఞానము కనిపించవచ్చును.</span> ")

        # 4th House: Pathway/Road Disputes (Mars)
        if house_num == 4:
            mars_p = [p for p in occ_planets if "కుజుడు" in p['name']]
            if mars_p and not mars_p[0]['is_friend']:
                special_notes.append(f"<span style='color: {mars_p[0]['color']};'>కుజుడు 4వ స్థానములో వ్యతిరేఖముగా ఉన్నందున గృహము లేదా పొలము వద్ద దారికి సంబంధించిన తగాదాలు (దక్షిణ దిశలో) వచ్చే అవకాశమున్నది.</span> ")

        # Mercury: Logic for Interest in Astrology
        for p in occ_planets:
            if "బుధుడు" in p['name']:
                if house_num == 5 and p['is_friend']:
                    special_notes.append(f"<span style='color: {p['color']};'>బుధుడు 5వ స్థానములో అనుకూలముగా ఉన్నందున మీకు జ్యోతిష్యము మరియు శాస్త్రముల మీద మంచి ఆసక్తి, అవగాహన కల్గును.</span> ")
                elif not p['is_friend'] and any(x in p['name'] for x in ["చంద్రుడు"]):
                    special_notes.append(f"<span style='color: {p['color']};'>బుధుడు చంద్రునితో కలిసి శత్రువుగా ఉన్నందున వ్యాపార విషయాలలో తెలివితక్కువతనము ప్రదర్శించవచ్చును.</span> ")

        # Wealth: Jupiter (Stored) vs Venus (Flowing)
        for p in occ_planets:
            if "గురు" in p['name'] and not p['is_friend']:
                special_notes.append(f"<span style='color: {p['color']};'>గురువు వ్యతిరేఖముగా ఉన్నందున ధనము నిలువ చేయడములో ఇబ్బందులు కల్గును.</span> ")
            if "శుక్రుడు" in p['name'] and not p['is_friend']:
                special_notes.append(f"<span style='color: {p['color']};'>శుక్రుడు వ్యతిరేఖముగా ఉన్నందున చేతిలో డబ్బు నిలువక ప్రవాహములా ఖర్చైపోవును.</span> ")

        bhava_report.append({
            "number": house_num,
            "title": bhava_data["title"],
            "lagna": house_lagna,
            "meaning": bhava_data["meaning"],
            "planets": p_info,
            "interpretation": interpretation,
            "special_notes": [translate_html_string(note) for note in special_notes],
            "state": state
        })

    return render_template("results.html", 
                           results=results_data,
                           friends=friends,
                           enemies=enemies,
                           bhava_report=bhava_report,
                           native_party=native_party,
                           lagna=lagna,
                           name=birth_info.get('name', ''),
                           dob=birth_info.get('dob', ''),
                           tob=birth_info.get('tob', ''),
                           place=birth_info.get('place', ''))


@app.route("/go-to-dasha-chart")
def go_to_dasha_chart():
    """Redirect to dasha chart with session data"""
    birth_info = session.get('birth_info', {})
    if birth_info:
        # Trigger the full dasha cycle calculation
        return chart2()
    else:
        # Redirect to index if no birth info
        return redirect(url_for('index'))

@app.route("/check-birth-data")
def check_birth_data():
    """Check if birth data exists in session"""
    birth_info = session.get('birth_info', {})
    return jsonify({
        'has_data': bool(birth_info.get('name') and birth_info.get('dob') and birth_info.get('tob'))
    })


def get_daily_panchangam_basic(jd, lat, lon, local_tz, local_midnight, calc_end_times=True):
    # Ensure standard Lahiri Ayanamsa is used for all calculations
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    
    from astral import LocationInfo
    from astral.sun import sun
    try:
        from astral.moon import moonrise, moonset
    except ImportError:
        moonrise = moonset = None
    import datetime
    import pytz
    
    sun_lon = swe.calc_ut(jd, swe.SUN, PLANET_FLAGS)[0][0]
    moon_lon = swe.calc_ut(jd, swe.MOON, PLANET_FLAGS)[0][0]
    
    diff = (moon_lon - sun_lon) % 360
    tithi_index = int(diff / 12)
    tithi_paksha = "శుక్ల పక్షం" if tithi_index < 15 else "కృష్ణ పక్షం"
    
    if tithi_index < 15:
        tt_name = TITHIS_TELUGU[tithi_index]
    else:
        tt_name = TITHIS_KRISHNA_TELUGU[tithi_index - 15]
        
    # Tithi exact tracking
    t_jd_start, t_jd_end = get_exact_tithi_times(jd, tithi_index)
    
    t_elapsed_days = jd - t_jd_start
    t_elapsed_h = int(t_elapsed_days * 24)
    t_elapsed_m = int(((t_elapsed_days * 24) % 1) * 60)
    
    t_remain_days = t_jd_end - jd
    t_remain_h = int(t_remain_days * 24)
    t_remain_m = int(((t_remain_days * 24) % 1) * 60)
    
    tithi_elapsed_str = f"{tr('గడిచిన సమయం')}: {t_elapsed_h}{tr('గం')} {t_elapsed_m}{tr('ని')}"
    tithi_remaining_str = f"{tr('మిగిలిన సమయం')}: {t_remain_h}{tr('గం')} {t_remain_m}{tr('ని')}"
    
    y, m, d, h = swe.revjul(jd)
    jd_dt = pytz.utc.localize(datetime.datetime(*(int(y), int(m), int(d), int(h)), int((h%1)*60))).astimezone(local_tz)
    calc_date = jd_dt.date()

    # Calculate Tithi Start string
    y_start_t, m_start_t, d_start_t, h_start_t = swe.revjul(t_jd_start)
    target_tithi_start = pytz.utc.localize(datetime.datetime(*(int(y_start_t), int(m_start_t), int(d_start_t), int(h_start_t)), int((h_start_t%1)*60))).astimezone(local_tz)
    tithi_start_str = get_am_pm_str(target_tithi_start)
    
    # Calculate Tithi End string
    y_end_t, m_end_t, d_end_t, h_end_t = swe.revjul(t_jd_end)
    target_tithi_end = pytz.utc.localize(datetime.datetime(*(int(y_end_t), int(m_end_t), int(d_end_t), int(h_end_t)), int((h_end_t%1)*60))).astimezone(local_tz)
    tithi_end_str = get_am_pm_str(target_tithi_end)
    
    if target_tithi_start.date() < calc_date:
        tithi_start_str = f"{tr('నిన్న')} {tithi_start_str}"
    elif target_tithi_start.date() > calc_date:
        tithi_start_str = f"{tr('రేపు')} {tithi_start_str}"
        
    if target_tithi_end.date() > calc_date:
        tithi_end_str = f"{tr('రేపు')} {tithi_end_str}"
    elif target_tithi_end.date() < calc_date:
        tithi_end_str = f"{tr('నిన్న')} {tithi_end_str}"
        
    calendar_tithi_end = f"{tr('ఉ: ') if target_tithi_end.hour < 12 else tr('సా: ')}{target_tithi_end.strftime('%I:%M')}"
    
    # Nakshatra exact tracking
    nak_index = int(moon_lon / NAKSHATRA_SIZE)
    nakshatra = NAKSHATRAS_TELUGU[nak_index]
    nak_offset = moon_lon - (nak_index * NAKSHATRA_SIZE)
    padam = int(nak_offset / PADAM_SIZE) + 1
    
    jd_start, jd_end = get_exact_nakshatra_times(jd, nak_index)
    
    elapsed_days = jd - jd_start
    nak_elapsed_h = int(elapsed_days * 24)
    nak_elapsed_m = int(((elapsed_days * 24) % 1) * 60)
    
    remain_days = jd_end - jd
    nak_remain_h = int(remain_days * 24)
    nak_remain_m = int(((remain_days * 24) % 1) * 60)
    nak_elapsed_str = f"{tr('గడిచిన సమయం')}: {nak_elapsed_h}{tr('గం')} {nak_elapsed_m}{tr('ని')}"
    nak_remaining_str = f"{tr('మిగిలిన సమయం')}: {nak_remain_h}{tr('గం')} {nak_remain_m}{tr('ని')}"
    
    # Calculate nak_end directly from exact jd_end
    ye, me, de, he = swe.revjul(jd_end)
    target_nak = pytz.utc.localize(datetime.datetime(*(int(ye), int(me), int(de), int(he)), int((he%1)*60))).astimezone(local_tz)
    nak_end_str = get_am_pm_str(target_nak)
    
    # Calculate nak_start directly from exact jd_start
    ys, ms, ds, hs = swe.revjul(jd_start)
    target_nak_start = pytz.utc.localize(datetime.datetime(*(int(ys), int(ms), int(ds), int(hs)), int((hs%1)*60))).astimezone(local_tz)
    nak_start_str = get_am_pm_str(target_nak_start)

    # Add Ninna (Yesterday) / Repu (Tomorrow) indicators
    calc_date = jd_dt.date()
    if target_nak_start.date() < calc_date:
        nak_start_str = f"{tr('నిన్న')} {nak_start_str}"
    elif target_nak_start.date() > calc_date:
        nak_start_str = f"{tr('రేపు')} {nak_start_str}"
        
    if target_nak.date() > calc_date:
        nak_end_str = f"{tr('రేపు')} {nak_end_str}"
    elif target_nak.date() < calc_date:
        nak_end_str = f"{tr('నిన్న')} {nak_end_str}"

    calendar_nak_end = f"{tr('ఉ: ') if target_nak.hour < 12 else tr('సా: ')}{target_nak.strftime('%I:%M')}"
    
    # Yoga
    yoga_index = int(((sun_lon + moon_lon) % 360) / NAKSHATRA_SIZE)
    yoga_name = YOGAS_TELUGU[yoga_index]
    
    # Karana 1 & 2
    karana1_idx = int(diff / 6) + 1
    karana2_idx = int((diff + 6) / 6) + 1
    
    def get_karana_name(idx):
        if idx == 1: return "కింస్తుఘ్న"
        elif 2 <= idx <= 57: return KARANAS_MOVABLE[(idx - 2) % 7]
        elif idx == 58: return "శకుని"
        elif idx == 59: return "చతుష్పాద"
        elif idx == 60: return "నాగ"
        return "N/A"
        
    karana1_name = get_karana_name(karana1_idx)
    karana2_name = get_karana_name(karana2_idx)
    
    karana1_hours = (6 - (diff % 6)) / 0.5079
    k1_dt = jd_dt + datetime.timedelta(hours=int(karana1_hours), minutes=int((karana1_hours%1)*60))
    karana1_end_str = get_am_pm_str(k1_dt)
    karana2_end_str = tithi_end_str # 2nd Karana ends with Tithi
    
    # Rasi
    surya_lagna = LAGNA_NAMES_TELUGU[int(sun_lon / 30)]
    chandra_lagna = LAGNA_NAMES_TELUGU[int(moon_lon / 30)]
    
    # Ayanam & Rutuvu
    ayanam = "ఉత్తరాయణం" if (sun_lon >= 270 or sun_lon < 90) else "దక్షిణాయణం"
    rutuvu = TELUGU_RUTUVULU[int((sun_lon % 360) / 60)]
    
    # Calculate exact month name mapping based on Amavasya boundaries (Amanta Lunar Month)
    def find_amavasya(jd_guess):
        jd_val = jd_guess
        for _ in range(10):
            m = swe.calc_ut(jd_val, swe.MOON)[0][0]
            s = swe.calc_ut(jd_val, swe.SUN)[0][0]
            df = (m - s) % 360
            if df > 180: df -= 360
            jd_val -= df / 12.190749
            if abs(df) < 0.0001: break
        return jd_val

    days_since = diff / 12.190749
    days_to = (360 - diff) / 12.190749
    jd_start = find_amavasya(jd - days_since)
    jd_end = find_amavasya(jd + days_to)

    # Masam is determined by Sun's Sidereal Rasi at the preceding Amavasya (Amanta system)
    amavasya_trop_sun = swe.calc_ut(jd_start, swe.SUN)[0][0]
    amavasya_ayan = swe.get_ayanamsa_ut(jd_start)
    amavasya_sun_lon = (amavasya_trop_sun - amavasya_ayan) % 360
    lagna_idx = int((amavasya_sun_lon % 360) / 30)
    masam_index = (lagna_idx + 1) % 12
    telugu_masam_name = TELUGU_MASALU[masam_index]
    
    EN_TO_TELUGU_MONTHS = {
        "january": "జనవరి", "february": "ఫిబ్రవరి", "march": "మార్చి",
        "april": "ఏప్రిల్", "may": "మే", "june": "జూన్",
        "july": "జూలై", "august": "ఆగస్టు", "september": "సెప్టెంబర్",
        "october": "అక్టోబర్", "november": "నవంబర్", "december": "డిసెంబర్"
    }
    def format_jd(jd_time):
        y_a, m_dt_a, d_a, h_a = swe.revjul(jd_time)
        dt_val = datetime.datetime(y_a, m_dt_a, d_a, int(h_a), int((h_a%1)*60))
        dt_val = pytz.utc.localize(dt_val).astimezone(local_tz)
        en_month = dt_val.strftime("%B").lower()
        te_month = tr(EN_TO_TELUGU_MONTHS.get(en_month, en_month))
        return f"{te_month}-{d_a:02d}"

    telugu_masam_full = f"{masam_index+1}. {tr(telugu_masam_name)} {tr('మాసం')} ({format_jd(jd_start)} {tr('నుంచి')} {format_jd(jd_end)} {tr('వరకు')})"
    
    year = local_midnight.year
    month_cal = local_midnight.month
    adj_year = year - 1 if (month_cal <= 6 and masam_index >= 9) else year
    year_index = (adj_year - 1987) % 60
    telugu_year = tr(TELUGU_YEARS[year_index])
    saka_year = adj_year - 78
    kaliyuga_year = 5126 + (adj_year - 2025)
    thraitha_sakamu = 47 + (adj_year - 2025)
    
    # Weekday mapping
    telugu_weekdays = ["సోమవారము", "మంగళవారము", "బుధవారము", "గురువారము", "శుక్రవారము", "శనివారము", "ఆదివారము"]
    wd_index = local_midnight.weekday()
    vara_name = tr(telugu_weekdays[wd_index])
    
    suryodayam = "ఉ: 06:00"
    suryastamayam = "సా: 06:00"
    moonrise_str = "N/A"
    moonset_str = "N/A"
    
    rahu_kalam = "N/A"
    gulika_kalam = "N/A"
    yama_gandam = "N/A"
    abhijit = "N/A"
    durmuhurtams = []
    
    try:
        loc = LocationInfo("Local", "Region", local_tz.zone, lat or 17.3850, lon or 78.4867)
        s = sun(loc.observer, date=local_midnight.date(), tzinfo=local_tz)
        sunrise_dt = s["sunrise"].astimezone(local_tz)
        sunset_dt = s["sunset"].astimezone(local_tz)
        suryodayam = get_am_pm_str(sunrise_dt)
        suryastamayam = get_am_pm_str(sunset_dt)
        
        if moonrise:
            mr = moonrise(loc.observer, date=local_midnight.date(), tzinfo=local_tz)
            if mr: moonrise_str = get_am_pm_str(mr)
            ms = moonset(loc.observer, date=local_midnight.date(), tzinfo=local_tz)
            if ms: moonset_str = get_am_pm_str(ms)
            
        daylight_secs = (sunset_dt - sunrise_dt).total_seconds()
        part_secs = daylight_secs / 8.0
        muhurta_secs = daylight_secs / 15.0
        
        # 0=Mon, ..., 6=Sun
        rahu_parts = [2, 7, 5, 6, 4, 3, 8]
        yama_parts = [4, 3, 2, 1, 7, 6, 5]
        guli_parts = [6, 5, 4, 3, 2, 1, 7]
        
        def get_period(parts_arr):
            part = parts_arr[wd_index]
            start_dt = sunrise_dt + datetime.timedelta(seconds=part_secs * (part - 1))
            end_dt = start_dt + datetime.timedelta(seconds=part_secs)
            return f"{get_am_pm_str(start_dt)} నుండి {get_am_pm_str(end_dt)} వరకు"
            
        rahu_kalam = get_period(rahu_parts)
        yama_gandam = get_period(yama_parts)
        gulika_kalam = get_period(guli_parts)
        
        # Abhijit is 8th Muhurta (index 7)
        abhi_start = sunrise_dt + datetime.timedelta(seconds=muhurta_secs * 7)
        abhi_end = abhi_start + datetime.timedelta(seconds=muhurta_secs)
        abhijit = f"{get_am_pm_str(abhi_start)} నుండి {get_am_pm_str(abhi_end)} వరకు"
        
        # Durmuhurtam logic approximation based on weekday
        dur_indices = {0: [8, 11], 1: [3, 15], 2: [7], 3: [2, 3], 4: [3, 8], 5: [2], 6: [13]}
        for d_idx in dur_indices[wd_index]:
            d_start = sunrise_dt + datetime.timedelta(seconds=muhurta_secs * d_idx)
            d_end = d_start + datetime.timedelta(seconds=muhurta_secs)
            durmuhurtams.append(f"{get_am_pm_str(d_start)} {tr('నుండి')} {get_am_pm_str(d_end)} {tr('వరకు')}")
            
    except Exception:
        pass
        
    return {
        "tithi_num": f"{(tithi_index%15) + 1}వ తిథి",
        "tithi_full": tt_name,
        "tithi_start": tithi_start_str,
        "tithi_end": tithi_end_str,
        "tithi_elapsed_str": tithi_elapsed_str,
        "tithi_remaining_str": tithi_remaining_str,
        "nakshatra": nakshatra,
        "nak_padam": f"{padam}వ పాదం",
        "nak_end": nak_end_str,
        "nak_start": nak_start_str,
        "nak_elapsed_str": nak_elapsed_str,
        "nak_remaining_str": nak_remaining_str,
        "calendar_tithi_end": calendar_tithi_end,
        "calendar_nak_end": calendar_nak_end,
        "yoga": yoga_name,
        "karana1": karana1_name,
        "karana1_end": karana1_end_str,
        "karana2": karana2_name,
        "karana2_end": karana2_end_str,
        "ayanam": ayanam,
        "rutuvu": rutuvu,
        "masam": telugu_masam_name,
        "masam_full": telugu_masam_full,
        "year_name": telugu_year,
        "year_index": year_index,
        "saka_year": saka_year,
        "kaliyuga_year": kaliyuga_year,
        "thraitha_sakamu": thraitha_sakamu,
        "paksha": tithi_paksha,
        "vara": vara_name,
        "surya_lagna": surya_lagna,
        "chandra_lagna": chandra_lagna,
        "sunrise": suryodayam,
        "sunset": suryastamayam,
        "moonrise": moonrise_str,
        "moonset": moonset_str,
        "rahu": rahu_kalam,
        "yama": yama_gandam,
        "gulika": gulika_kalam,
        "abhijit": abhijit,
        "durmuhurtams": durmuhurtams
    }

@app.route("/daily_panchangam", methods=["GET", "POST"])
def daily_panchangam():
    today = datetime.datetime.now()
    dob = today.strftime("%Y-%m-%d")
    tob = today.strftime("%H:%M")
    srv_loc = get_server_ip_location() if callable(globals().get('get_server_ip_location')) else None
    if srv_loc and srv_loc.get("latitude") and srv_loc.get("longitude"):
        place = srv_loc.get("display_name") or "Guntur, Andhra Pradesh, India"
        lat = float(srv_loc.get("latitude"))
        lon = float(srv_loc.get("longitude"))
    else:
        place = "Hyderabad, Telangana"
        lat = 17.3850
        lon = 78.4867

    # Use parameters from GET or POST, with defaults for today
    dob = request.values.get("dob") or dob
    tob = request.values.get("tob") or tob
    place = request.values.get("place") or place
    lat_str = request.values.get("lat")
    lon_str = request.values.get("lon")
    
    lat = float(lat_str) if lat_str else 17.3850
    lon = float(lon_str) if lon_str else 78.4867
    
    # Determine Timezone based on Latitude and Longitude
    timezone_str = get_timezone_str(lat, lon)
        
    local_tz = pytz.timezone(timezone_str)
    try:
        local_dt = local_tz.localize(datetime.datetime.strptime(dob+" "+tob,"%Y-%m-%d %H:%M"))
    except Exception:
        local_dt = datetime.datetime.now(local_tz)
        
    utc_dt = local_dt.astimezone(pytz.utc)
    jd = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, utc_dt.hour + utc_dt.minute/60 + utc_dt.second/3600)
    local_midnight = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    
    
    panch_data = get_daily_panchangam_basic(jd, lat, lon, local_tz, local_midnight, calc_end_times=True)
    
    chart_data = {}
    lagna_houses = {}
    lagna = ""
    
    try:
        # Re-implementing the planetary positions calculation for the daily chart
        # to avoid circular imports and ensure consistent data structure
        chart_data_temp = {r:[] for r in LAGNA_NAMES_TELUGU}
        base_pos = {}
        
        # Use a list of visible planets for the daily chart (Matching Kundali rules)
        # Main 12 planets: 9 Standard + 3 Derived (Earth, Chitra, Mitra)
        DAILY_PLANETS = {
            "సూర్యుడు": swe.SUN, "చంద్రుడు": swe.MOON, "కుజుడు": swe.MARS,
            "బుధుడు": swe.MERCURY, "గురు": swe.JUPITER, "శుక్రుడు": swe.VENUS, 
            "శని": swe.SATURN, "రాహు": swe.TRUE_NODE
        }
        
        def get_p_info(name, lon):
            d = int(lon % 30); m = int(((lon % 30) - d) * 60)
            nak_idx = int(lon / NAKSHATRA_SIZE)
            n_name = NAKSHATRAS_TELUGU[nak_idx % 27]
            pdm = int((lon % NAKSHATRA_SIZE) / PADAM_SIZE) + 1
            return f"<b>{name}</b> <small>{d}°{m:02d}′</small><br><span style='font-size:0.8em; color:rgba(255,255,255,0.7);'>{n_name}-{pdm}</span>"

        for name_p, pid in DAILY_PLANETS.items():
            res = swe.calc_ut(jd, pid, PLANET_FLAGS)
            lonp = res[0][0]
            base_pos[name_p] = lonp
            r = LAGNA_NAMES_TELUGU[int(lonp / 30)]
            chart_data_temp[r].append((lonp % 30, get_p_info(name_p, lonp)))
            
        # 9. Ketu (180 deg from Rahu)
        rahu_lon = base_pos.get("రాహు", 0)
        ketu_lon = (rahu_lon + 180) % 360
        base_pos["కేతు"] = ketu_lon
        r_k = LAGNA_NAMES_TELUGU[int(ketu_lon / 30)]
        chart_data_temp[r_k].append((ketu_lon % 30, get_p_info("కేతు", ketu_lon)))

        # Derived planets (Dasacharam Logic - Verified)
        derived = {
            "భూమి": (base_pos["సూర్యుడు"] + 180) % 360,
            "చిత్ర": (base_pos["రాహు"] + 3.3333) % 360,
            "మిత్ర": (base_pos["కేతు"] + 3.3333) % 360
        }
        for n, lonp in derived.items():
            base_pos[n] = lonp
            r = LAGNA_NAMES_TELUGU[int(lonp / 30)]
            chart_data_temp[r].append((lonp % 30, get_p_info(n, lonp)))

        # Calculate Lagna
        hus, ascmc = swe.houses(jd, lat, lon)
        # ascmc[0] is tropical ascendant. We need sidereal.
        ayanamsa = swe.get_ayanamsa_ut(jd)
        lagna_lon = (ascmc[0] - ayanamsa) % 360
        lagna = LAGNA_NAMES_TELUGU[int(lagna_lon / 30)]
        chart_data_temp[lagna].append((lagna_lon % 30, get_p_info("లగ్నం", lagna_lon)))
        
        lagna_deg = int(lagna_lon % 30)
        lagna_min = int(((lagna_lon % 30) - lagna_deg) * 60)
        panch_data['lagna_full'] = f"{tr(lagna)} ({lagna_deg}°{lagna_min:02d}′ {tr('వద్ద')})"
        
        chart_data = {r: '<br>'.join([x[1] for x in sorted(lst, key=lambda i: i[0])]) for r,lst in chart_data_temp.items()}
        rsi_idx = LAGNA_NAMES_TELUGU.index(lagna)
        lagna_houses = {LAGNA_NAMES_TELUGU[(rsi_idx + i) % 12]: i+1 for i in range(12)}
        
        panch_data['chart'] = chart_data
        panch_data['houses'] = lagna_houses
        panch_data['lagna'] = lagna
    except Exception as e:
        print("Error computing chart for daily panchangam:", e)

    # ── Planet Transit Table: Entry/Exit dates for each planet's current rasi ──
    try:
        def get_planet_lon(jd_val, planet_id):
            """Get sidereal longitude for a planet at given JD"""
            return swe.calc_ut(jd_val, planet_id, PLANET_FLAGS)[0][0]

        def get_derived_lon(jd_val, ptype):
            """Get longitude for derived planets"""
            if ptype == "కేతు":
                rahu = get_planet_lon(jd_val, swe.TRUE_NODE)
                return (rahu + 180) % 360
            elif ptype == "భూమి":
                sun = get_planet_lon(jd_val, swe.SUN)
                return (sun + 180) % 360
            elif ptype == "చిత్ర":
                rahu = get_planet_lon(jd_val, swe.TRUE_NODE)
                return (rahu + 3.3333) % 360
            elif ptype == "మిత్ర":
                rahu = get_planet_lon(jd_val, swe.TRUE_NODE)
                ketu = (rahu + 180) % 360
                return (ketu + 3.3333) % 360

        def get_any_planet_lon(jd_val, name, pid):
            """Unified longitude getter for any planet"""
            if name in ("కేతు", "భూమి", "చిత్ర", "మిత్ర"):
                return get_derived_lon(jd_val, name)
            return get_planet_lon(jd_val, pid)

        # Planets that are always retrograde (move backward in longitude)
        ALWAYS_RETROGRADE = {"రాహు", "కేతు", "చిత్ర", "మిత్ర"}

        def is_planet_retrograde(jd_val, name, pid):
            """Check if planet is retrograde at given JD (negative speed = retrograde)"""
            if name in ALWAYS_RETROGRADE:
                return True
            if pid is None:
                return False
            speed = swe.calc_ut(jd_val, pid, PLANET_FLAGS)[0][3]
            return speed < 0

        def find_lagna_boundary(jd_start, name, pid, current_lagna_idx, find_exit, max_days=10950):
            """Binary search to find when planet enters/exits current rasi.
               find_exit=True  -> look for next rasi change (exit)
               find_exit=False -> look for previous rasi change (entry)
            """
            direction = 1 if find_exit else -1
            
            # Determine expected previous/next lagna to filter out retrograde re-entries
            is_retro_planet = name in ALWAYS_RETROGRADE
            if not find_exit:
                expected_lagna_b = (current_lagna_idx - 1) % 12 if not is_retro_planet else (current_lagna_idx + 1) % 12
            else:
                expected_lagna_b = (current_lagna_idx + 1) % 12 if not is_retro_planet else (current_lagna_idx - 1) % 12

            step_days = {
                "చంద్రుడు": 0.5, "సూర్యుడు": 3, "భూమి": 3,
                "బుధుడు": 2, "శుక్రుడు": 3, "కుజుడు": 5,
                "గురు": 15, "శని": 30,
                "రాహు": 15, "కేతు": 15, "చిత్ర": 15, "మిత్ర": 15
            }
            step = step_days.get(name, 5)

            jd_a = jd_start
            for _ in range(int(max_days / step) + 2):
                jd_b = jd_a + direction * step
                lon_b = get_any_planet_lon(jd_b, name, pid)
                lagna_b = int(lon_b / 30) % 12
                
                # Check if we hit a boundary AND it's the expected primary boundary
                if lagna_b != current_lagna_idx:
                    if lagna_b == expected_lagna_b:
                        # Boundary is between jd_a and jd_b — binary search
                        lo, hi = min(jd_a, jd_b), max(jd_a, jd_b)
                        for _ in range(35):  # ~35 iterations => sub-minute precision
                            mid = (lo + hi) / 2
                            lon_mid = get_any_planet_lon(mid, name, pid)
                            lagna_mid = int(lon_mid / 30) % 12
                            
                            # The boundary: lo side is same rasi, hi side differs
                            if lagna_mid == current_lagna_idx:
                                if direction > 0:
                                    lo = mid
                                else:
                                    hi = mid
                            else:
                                if direction > 0:
                                    hi = mid
                                else:
                                    lo = mid
                        # Return the point just at the boundary transition
                        return hi if direction > 0 else lo
                    # If lagna_b is unexpected (e.g. retrograde dip), keep searching
                jd_a = jd_b
            return None  # Couldn't find boundary within max_days

        def jd_to_date_str(jd_val):
            """Convert JD to Telugu-formatted date + time string"""
            y, m, d, h = swe.revjul(jd_val)
            dt_val = datetime.datetime(int(y), int(m), int(d)) + datetime.timedelta(hours=h)
            dt_val = pytz.utc.localize(dt_val).astimezone(local_tz)
            te_months = ["జనవరి", "ఫిబ్రవరి", "మార్చి", "ఏప్రిల్", "మే", "జూన్",
                         "జూలై", "ఆగస్టు", "సెప్టెంబర్", "అక్టోబర్", "నవంబర్", "డిసెంబర్"]
            ampm = tr("ఉ: ") if dt_val.hour < 12 else tr("సా: ")
            time_str = dt_val.strftime("%I:%M:%S").lstrip("0") or "12:00:00"
            return f"{dt_val.day} {tr(te_months[dt_val.month - 1])} {dt_val.year} ({ampm}{time_str})"

        # All 12 planets
        ALL_PLANETS_TRANSIT = [
            ("సూర్యుడు", swe.SUN), ("చంద్రుడు", swe.MOON), ("కుజుడు", swe.MARS),
            ("బుధుడు", swe.MERCURY), ("గురు", swe.JUPITER), ("శుక్రుడు", swe.VENUS),
            ("శని", swe.SATURN), ("రాహు", swe.TRUE_NODE),
            ("కేతు", None), ("భూమి", None), ("చిత్ర", None), ("మిత్ర", None)
        ]

        transit_table = []
        for p_name, p_id in ALL_PLANETS_TRANSIT:
            lon_now = get_any_planet_lon(jd, p_name, p_id)
            lagna_idx = int(lon_now / 30) % 12
            lagna_name = tr(LAGNA_NAMES_TELUGU[lagna_idx])

            # Find both rasi boundaries (one in each temporal direction)
            jd_bound1 = find_lagna_boundary(jd, p_name, p_id, lagna_idx, find_exit=True)
            jd_bound2 = find_lagna_boundary(jd, p_name, p_id, lagna_idx, find_exit=False)

            # jd_bound2 is past search (Entry) | jd_bound1 is future search (Exit)
            jd_entry = jd_bound2
            jd_exit  = jd_bound1

            entry_str = jd_to_date_str(jd_entry) if jd_entry else "—"
            exit_str  = jd_to_date_str(jd_exit)  if jd_exit  else "—"

            transit_table.append({
                "name": p_name,
                "lagna": lagna_name,
                "entry": entry_str,
                "exit": exit_str
            })

        panch_data['transit_table'] = transit_table
    except Exception as e:
        print("Error computing transit table:", e)
        panch_data['transit_table'] = []

    
    return render_template(
        "daily_panchangam.html",
        dob=dob, tob=tob, place=place, lat=lat, lon=lon,
        panch=panch_data
    )

@app.route("/calendar_view", methods=["GET", "POST"])
def calendar_view():
    input_date = request.form.get("calendar_date")
    view_type = request.form.get("view_type", "telugu")
    if not input_date:
        input_date = datetime.datetime.now().strftime("%Y-%m-%d")
        
    lat = 17.3850
    lon = 78.4867
    local_tz = pytz.timezone("Asia/Kolkata")
    
    try:
        date_obj = datetime.datetime.strptime(input_date, "%Y-%m-%d")
    except Exception:
        date_obj = datetime.datetime.now()
        input_date = date_obj.strftime("%Y-%m-%d")
        
    local_calc = local_tz.localize(date_obj.replace(hour=12))
    utc_calc = local_calc.astimezone(pytz.utc)
    jd_input = swe.julday(utc_calc.year, utc_calc.month, utc_calc.day, utc_calc.hour + utc_calc.minute/60.0)
    
    def find_amavasya(jd_guess):
        jd_val = jd_guess
        for _ in range(10):
            m = swe.calc_ut(jd_val, swe.MOON)[0][0]
            s = swe.calc_ut(jd_val, swe.SUN)[0][0]
            df = (m - s) % 360
            if df > 180: df -= 360
            jd_val -= df / 12.190749
            if abs(df) < 0.0001:
                break
        return jd_val
        
    sun_lon = swe.calc_ut(jd_input, swe.SUN, PLANET_FLAGS)[0][0]
    moon_lon = swe.calc_ut(jd_input, swe.MOON, PLANET_FLAGS)[0][0]
    diff = (moon_lon - sun_lon) % 360
    days_since = diff / 12.190749
    jd_start = find_amavasya(jd_input - days_since)
    jd_end = find_amavasya(jd_input + (360 - diff)/12.190749)
    
    y, m_dt, d, h = swe.revjul(jd_start)
    start_dt = datetime.datetime(y, m_dt, d).date() + datetime.timedelta(days=1)
    
    y2, m2_dt, d2, h2 = swe.revjul(jd_end)
    end_dt = datetime.datetime(y2, m2_dt, d2).date()
    
    if view_type == "english":
        import calendar as py_calendar
        start_dt = datetime.date(date_obj.year, date_obj.month, 1)
        last_day = py_calendar.monthrange(date_obj.year, date_obj.month)[1]
        end_dt = datetime.date(date_obj.year, date_obj.month, last_day)
    
    # Branding Calculations (Year, Kaliyuga, Thraitha Sakamu)
    adj_year = date_obj.year
    year_index = (adj_year - 1987) % 60
    year_name = tr(TELUGU_YEARS[year_index])
    cycles_since_1987 = (adj_year - 1987) // 60
    kaliyuga_year = 5088 + (cycles_since_1987 * 60) + year_index
    thraitha_sakamu = 47 + (adj_year - 2025)

    # Calculate Paksham Ranges
    def find_tithi_jd(jd_guess, target_diff):
        jd_val = jd_guess
        for _ in range(10):
            res_m = swe.calc_ut(jd_val, swe.MOON, PLANET_FLAGS)
            res_s = swe.calc_ut(jd_val, swe.SUN, PLANET_FLAGS)
            m = res_m[0][0]; s = res_s[0][0]
            df = (m - s - target_diff) % 360
            if df > 180: df -= 360
            jd_val -= df / 12.190749
            if abs(df) < 0.0001: break
        return jd_val

    jd_purnima = find_tithi_jd(jd_start + 14.5, 180)
    y3, m3, d3, h3 = swe.revjul(jd_purnima)
    purnima_dt = datetime.date(int(y3), int(m3), int(d3))
    
    EN_MONTHS_TELUGU = ["జనవరి", "ఫిబ్రవరి", "మార్చి", "ఏప్రిల్", "మే", "జూన్", "జూలై", "ఆగస్టు", "సెప్టెంబర్", "అక్టోబర్", "నవంబర్", "డిసెంబర్"]
    def tr_month(te_month):
        return tr(te_month)
    shukla_range = f"{start_dt.day} {tr_month(EN_MONTHS_TELUGU[start_dt.month-1])} - {purnima_dt.day} {tr_month(EN_MONTHS_TELUGU[purnima_dt.month-1])}"
    krishna_start_dt = purnima_dt + datetime.timedelta(days=1)
    krishna_range = f"{krishna_start_dt.day} {tr_month(EN_MONTHS_TELUGU[krishna_start_dt.month-1])} - {end_dt.day} {tr_month(EN_MONTHS_TELUGU[end_dt.month-1])}"

    amavasya_trop_sun = swe.calc_ut(jd_start, swe.SUN)[0][0]
    amavasya_ayan = swe.get_ayanamsa_ut(jd_start)
    amavasya_sun_lon = (amavasya_trop_sun - amavasya_ayan) % 360
    lagna_idx = int((amavasya_sun_lon % 360) / 30)
    masam_index = (lagna_idx + 1) % 12
    telugu_masam_name = TELUGU_MASALU[masam_index]
    translated_masam_name = tr(telugu_masam_name)
    
    # Festival Mapping: (Masam, Paksham, Tithi_Name) -> Festival
    # Paksham: 0 for Shukla, 1 for Krishna
    FEST_MAP = {
        ("చైత్ర", 0, "పాడ్యమి"): "ఉగాది",
        ("చైత్ర", 0, "నవమి"): "శ్రీరామ నవమి",
        ("చైత్ర", 0, "పౌర్ణమి"): "హనుమజ్జయంతి",
        ("వైశాఖ", 0, "తదియ"): "అక్షయ తృతీయ",
        ("వైశాఖ", 0, "ఏకాదశి"): "మోహిని ఏకాదశి",
        ("వైశాఖ", 0, "పౌర్ణమి"): "బుద్ధ పూర్ణిమ",
        ("జ్యేష్ఠ", 0, "ఏకాదశి"): "నిర్జల ఏకాదశి",
        ("జ్యేష్ఠ", 0, "పౌర్ణమి"): "ఏరువాక పౌర్ణమి (వట సావిత్రి వ్రతం)",
        ("ఆషాఢ", 0, "ఏకాదశి"): "తొలి ఏకాదశి",
        ("ఆషాఢ", 0, "పౌర్ణమి"): "గురు పూర్ణిమ (వ్యాస పౌర్ణమి)",
        ("శ్రావణ", 0, "చవితి"): "నాగుల చవితి",
        ("శ్రావణ", 0, "పంచమి"): "నాగుల పంచమి",
        ("శ్రావణ", 0, "ఏకాదశి"): "పుత్రదా ఏకాదశి",
        ("శ్రావణ", 0, "పౌర్ణమి"): "రాఖీ పౌర్ణమి (జంధ్యాల పౌర్ణమి / ఉపాకర్మ)",
        ("శ్రావణ", 1, "అష్టమి"): "శ్రీ కృష్ణాష్టమి (గోకులాష్టమి)",
        ("శ్రావణ", 1, "ఏకాదశి"): "కామికా ఏకాదశి",
        ("భాద్రపద", 0, "తదియ"): "ఉండ్రాళ్ల తద్ది",
        ("భాద్రపద", 0, "చవితి"): "వినాయక చవితి",
        ("భాద్రపద", 0, "ఏకాదశి"): "పరివర్తని ఏకాదశి",
        ("భాద్రపద", 0, "చతుర్దశి"): "అనంత పద్మనాభ వ్రతం (అనంత చతుర్దశి)",
        ("ఆశ్వయుజ", 0, "పాడ్యమి"): "దేవీ నవరాత్రుల ప్రారంభం",
        ("ఆశ్వయుజ", 0, "అష్టమి"): "దుర్గాష్టమి",
        ("ఆశ్వయుజ", 0, "నవమి"): "మహార్నవమి",
        ("ఆశ్వయుజ", 0, "దశమి"): "విజయదశమి (దసరా)",
        ("ఆశ్వయుజ", 1, "చతుర్దశి"): "నరక చతుర్దశి",
        ("ఆశ్వయుజ", 1, "అమావాస్య"): "దీపావళి",
        ("కార్తీక", 0, "విదియ"): "భగినీ హస్తభోజనం (యమ ద్వితీయా)",
        ("కార్తీక", 0, "చవితి"): "నాగుల చవితి (శరద్వృత్తు)",
        ("కార్తీక", 0, "ఏకాదశి"): "ప్రబోధిని ఏకాదశి (ఉత్థాన ఏకాదశి)",
        ("కార్తీక", 0, "ద్వాదశి"): "చిలుకు ద్వాదశి (క్షీరాబ్ది ద్వాదశి)",
        ("కార్తీక", 0, "పౌర్ణమి"): "కార్తీక పూర్ణిమ",
        ("మార్గశిర", 0, "షష్ఠి"): "సుబ్రహ్మణ్య షష్ఠి",
        ("మార్గశిర", 0, "ఏకాదశి"): "మోక్షదా ఏకాదశి (గీతా జయంతి)",
        ("మార్గశిర", 0, "పౌర్ణమి"): "దత్తాత్రేయ జయంతి",
        ("పుష్య", 0, "ఏకాదశి"): "వైకుంఠ ఏకాదశి (ముక్కోటి ఏకాదశి)",
        ("మాఘ", 0, "పంచమి"): "వసంత పంచమి (శ్రీ పంచమి)",
        ("మాఘ", 0, "సప్తమి"): "రథ సప్తమి",
        ("మాఘ", 0, "ఏకాదశి"): "భీష్మ ఏకాదశి",
        ("మాఘ", 1, "చతుర్దశి"): "మహా శివరాత్రి",
        ("ఫాల్గుణ", 0, "పౌర్ణమి"): "కామదహనం / హోలీ"
    }
    
    # Date based festivals
    DATE_FESTS = {
        (1, 13): "భోగి",
        (1, 14): "మకర సంక్రాంతి",
        (1, 15): "కనుమ",
        (1, 26): "గణతంత్ర దినోత్సవం (Republic Day)",
        (4, 14): "అంబేద్కర్ జయంతి",
        (8, 15): "స్వాతంత్ర దినోత్సవం (Independence Day)",
        (9, 5): "ఉపాధ్యాయుల దినోత్సవం (Teachers' Day)",
        (10, 2): "గాంధీ జయంతి",
        (11, 14): "బాలల దినోత్సవం (Children's Day)"
    }

    festivals_list = []
    
    total_days = (end_dt - start_dt).days + 1
    
    # We organize by 6 possible weeks for each of 7 days
    days_data = {i: [None]*6 for i in range(7)}
    
    first_wd = (start_dt.weekday() + 1) % 7 # 0 = Sun
    
    for offset in range(total_days):
        current_dt = start_dt + datetime.timedelta(days=offset)
        wd = (current_dt.weekday() + 1) % 7
        week_idx = (offset + first_wd) // 7
        
        calc_dt = datetime.datetime.combine(current_dt, datetime.time(6, 0))
        local_calc = local_tz.localize(calc_dt)
        utc_calc = local_calc.astimezone(pytz.utc)
        jd = swe.julday(utc_calc.year, utc_calc.month, utc_calc.day, utc_calc.hour + utc_calc.minute/60.0)
        
        panch = get_daily_panchangam_basic(jd, lat, lon, local_tz, calc_dt, calc_end_times=True)
        
        # Check for festival
        f_name = ""
        pks = 0 if "శుక్ల" in panch["paksha"] else 1
        # Extract tithi name
        t_name = panch["tithi_full"]
        m_name = panch["masam"]
        
        # Match from map
        key = (m_name, pks, t_name)
        f_name = FEST_MAP.get(key, "")
        
        # Special dynamic check for Varalakshmi Vratam (Friday before Sravana Purnima)
        if not f_name and m_name == "శ్రావణ" and pks == 0 and current_dt.weekday() == 4:
            if (purnima_dt - current_dt).days >= 0 and (purnima_dt - current_dt).days < 7:
                f_name = "వరలక్ష్మీ వ్రతం"
        
        # Match from date
        d_key = (current_dt.month, current_dt.day)
        if not f_name:
            f_name = DATE_FESTS.get(d_key, "")
            
        if f_name:
            festivals_list.append({
                "day": current_dt.day,
                "month": EN_MONTHS_TELUGU[current_dt.month - 1],
                "month_en": current_dt.strftime("%b"),
                "name": tr(f_name)
            })
            
        days_data[wd][week_idx] = {
            "date": current_dt.day,
            "month_en": current_dt.strftime("%b"),
            "month_te": EN_MONTHS_TELUGU[current_dt.month - 1],
            "tithi_full": panch["tithi_full"],
            "tithi_end": panch["tithi_end"],
            "calendar_tithi_end": panch.get("calendar_tithi_end", ""),
            "nakshatra": panch["nakshatra"],
            "nak_end": panch["nak_end"],
            "calendar_nak_end": panch.get("calendar_nak_end", ""),
            "sunrise": panch["sunrise"],
            "sunset": panch["sunset"],
            "is_festival": bool(f_name),
            "fest_name": tr(f_name) if f_name else "",
            "is_shukla": "శుక్ల" in panch["paksha"],
            "is_pournami": "పౌర్ణమి" in panch["tithi_full"],
            "is_amavasya": "అమావాస్య" in panch["tithi_full"],
            "is_today": current_dt == datetime.datetime.now().date()
        }
        
    return render_template(
        "calendar_view.html",
        input_date=input_date,
        view_type=view_type,
        festivals=festivals_list,
        days_data=days_data,
        year=date_obj.year,
        year_name=year_name,
        year_index=year_index + 1,
        kaliyuga_year=kaliyuga_year,
        thraitha_sakamu=thraitha_sakamu,
        telugu_masam=translated_masam_name if view_type == "telugu" else f"{tr(EN_MONTHS_TELUGU[date_obj.month - 1])} ({translated_masam_name})",
        shukla_range=shukla_range,
        krishna_range=krishna_range,
        start_dt_str=f"{start_dt.day} {tr(EN_MONTHS_TELUGU[start_dt.month - 1])}",
        end_dt_str=f"{end_dt.day} {tr(EN_MONTHS_TELUGU[end_dt.month - 1])}"
    )





# ==========================================
# NAKSHATRA PADA KUNDALI GENERATION
# ==========================================

RASHI_NAKSHATRA_PADA_MAP = {
    "మేషం": [
        {"nakshatra": "అశ్విని", "padas": [1, 2, 3, 4], "rashi_padas": [1, 2, 3, 4]},
        {"nakshatra": "భరణి", "padas": [1, 2, 3, 4], "rashi_padas": [5, 6, 7, 8]},
        {"nakshatra": "కృత్తిక", "padas": [1], "rashi_padas": [9]}
    ],
    "వృషభం": [
        {"nakshatra": "కృత్తిక", "padas": [2, 3, 4], "rashi_padas": [1, 2, 3]},
        {"nakshatra": "రోహిణి", "padas": [1, 2, 3, 4], "rashi_padas": [4, 5, 6, 7]},
        {"nakshatra": "మృగశిర", "padas": [1, 2], "rashi_padas": [8, 9]}
    ],
    "మిథునం": [
        {"nakshatra": "మృగశిర", "padas": [3, 4], "rashi_padas": [1, 2]},
        {"nakshatra": "ఆరుద్ర", "padas": [1, 2, 3, 4], "rashi_padas": [3, 4, 5, 6]},
        {"nakshatra": "పునర్వసు", "padas": [1, 2, 3], "rashi_padas": [7, 8, 9]}
    ],
    "కర్కాటకం": [
        {"nakshatra": "పునర్వసు", "padas": [4], "rashi_padas": [1]},
        {"nakshatra": "పుష్యమి", "padas": [1, 2, 3, 4], "rashi_padas": [2, 3, 4, 5]},
        {"nakshatra": "ఆశ్లేష", "padas": [1, 2, 3, 4], "rashi_padas": [6, 7, 8, 9]}
    ],
    "సింహం": [
        {"nakshatra": "మఖ", "padas": [1, 2, 3, 4], "rashi_padas": [1, 2, 3, 4]},
        {"nakshatra": "పుబ్బ", "padas": [1, 2, 3, 4], "rashi_padas": [5, 6, 7, 8]},
        {"nakshatra": "ఉత్తర", "padas": [1], "rashi_padas": [9]}
    ],
    "కన్య": [
        {"nakshatra": "ఉత్తర", "padas": [2, 3, 4], "rashi_padas": [1, 2, 3]},
        {"nakshatra": "హస్త", "padas": [1, 2, 3, 4], "rashi_padas": [4, 5, 6, 7]},
        {"nakshatra": "చిత్త", "padas": [1, 2], "rashi_padas": [8, 9]}
    ],
    "తులా": [
        {"nakshatra": "చిత్త", "padas": [3, 4], "rashi_padas": [1, 2]},
        {"nakshatra": "స్వాతి", "padas": [1, 2, 3, 4], "rashi_padas": [3, 4, 5, 6]},
        {"nakshatra": "విశాఖ", "padas": [1, 2, 3], "rashi_padas": [7, 8, 9]}
    ],
    "వృశ్చికం": [
        {"nakshatra": "విశాఖ", "padas": [4], "rashi_padas": [1]},
        {"nakshatra": "అనూరాధ", "padas": [1, 2, 3, 4], "rashi_padas": [2, 3, 4, 5]},
        {"nakshatra": "జ్యేష్ఠ", "padas": [1, 2, 3, 4], "rashi_padas": [6, 7, 8, 9]}
    ],
    "ధనస్సు": [
        {"nakshatra": "మూల", "padas": [1, 2, 3, 4], "rashi_padas": [1, 2, 3, 4]},
        {"nakshatra": "పూర్వాషాఢ", "padas": [1, 2, 3, 4], "rashi_padas": [5, 6, 7, 8]},
        {"nakshatra": "ఉత్తరాషాఢ", "padas": [1], "rashi_padas": [9]}
    ],
    "మకరం": [
        {"nakshatra": "ఉత్తరాషాఢ", "padas": [2, 3, 4], "rashi_padas": [1, 2, 3]},
        {"nakshatra": "శ్రవణం", "padas": [1, 2, 3, 4], "rashi_padas": [4, 5, 6, 7]},
        {"nakshatra": "ధనిష్ఠ", "padas": [1, 2], "rashi_padas": [8, 9]}
    ],
    "కుంభం": [
        {"nakshatra": "ధనిష్ఠ", "padas": [3, 4], "rashi_padas": [1, 2]},
        {"nakshatra": "శతభిషం", "padas": [1, 2, 3, 4], "rashi_padas": [3, 4, 5, 6]},
        {"nakshatra": "పూర్వాభాద్ర", "padas": [1, 2, 3], "rashi_padas": [7, 8, 9]}
    ],
    "మీనం": [
        {"nakshatra": "పూర్వాభాద్ర", "padas": [4], "rashi_padas": [1]},
        {"nakshatra": "ఉత్తరాభాద్ర", "padas": [1, 2, 3, 4], "rashi_padas": [2, 3, 4, 5]},
        {"nakshatra": "రేవతి", "padas": [1, 2, 3, 4], "rashi_padas": [6, 7, 8, 9]}
    ]
}

SHORT_NAKSHATRAS_TELUGU = {
    "అశ్విని": "అశ్వి",
    "భరణి": "భరణి",
    "కృత్తిక": "కృత్తి",
    "రోహిణి": "రోహి",
    "మృగశిర": "మృగ",
    "ఆరుద్ర": "ఆరు",
    "పునర్వసు": "పునర్వ",
    "పుష్యమి": "పుష్య",
    "ఆశ్లేష": "ఆశ్లే",
    "మఖ": "మఖ",
    "పుబ్బ": "పుబ్బ",
    "ఉత్తర": "ఉత్తర",
    "హస్త": "హస్త",
    "చిత్త": "చిత్త",
    "స్వాతి": "స్వాతి",
    "విశాఖ": "విశా",
    "అనూరాధ": "అనూ",
    "జ్యేష్ఠ": "జ్యేష్ఠ",
    "మూల": "మూల",
    "పూర్వాషాఢ": "పూ.షా",
    "ఉత్తరాషాఢ": "ఉ.షా",
    "శ్రవణం": "శ్రవ",
    "ధనిష్ఠ": "ధని",
    "శతభిషం": "శత",
    "పూర్వాభాద్ర": "పూ.భా",
    "ఉత్తరాభాద్ర": "ఉ.భా",
    "రేవతి": "రేవతి"
}

def build_nakshatra_pada_boxes(data):
    """
    Builds the 12 boxes mapping each Rashi's 3 Nakshatras & 9 Padas
    along with direct planets, Lagna, and aspect hands situated in each exact pada.
    """
    planet_positions = data.get('planet_positions', [])
    lagna_name = data.get('lagna', '')
    lagna_deg_str = data.get('lagna_deg', '')
    houses = data.get('houses', {})

    lagna_pada_in_rashi = None
    if lagna_deg_str:
        try:
            deg_part = float(lagna_deg_str.split('°')[0])
            min_part = float(lagna_deg_str.split('°')[1].replace('′','').replace("'", "")) if '°' in lagna_deg_str and '′' in lagna_deg_str else 0.0
            total_rashi_deg = deg_part + min_part / 60.0
            lagna_pada_in_rashi = int(total_rashi_deg / 3.3333333333333335) + 1
            if lagna_pada_in_rashi > 9: lagna_pada_in_rashi = 9
        except Exception:
            lagna_pada_in_rashi = 1

    boxes = {}
    for rashi, nak_list in RASHI_NAKSHATRA_PADA_MAP.items():
        h_no = houses.get(rashi, 1)
        is_lagna_box = (rashi == lagna_name)

        if h_no in [1, 5, 9]:
            karma_label = "పుణ్యం"
            karma_class = "house-green"
        elif h_no in [3, 7, 11]:
            karma_label = "పాపం"
            karma_class = "house-red"
        else:
            karma_label = "పు+పా"
            karma_class = "house-mixed"

        nakshatras_data = []
        for nak_group in nak_list:
            nak_name = nak_group["nakshatra"]
            padas_data = []
            for pada_idx, r_pada in enumerate(nak_group["rashi_padas"]):
                nak_pada_num = nak_group["padas"][pada_idx]

                occupants = []
                # Lagna Point in this pada
                if is_lagna_box and r_pada == lagna_pada_in_rashi:
                    occupants.append({
                        "name": "లగ్నం",
                        "degree": lagna_deg_str,
                        "is_lagna": True,
                        "is_hand": False,
                        "color": "gold"
                    })

                # Planets in this rashi & pada
                for p in planet_positions:
                    if p["lagna"] == rashi:
                        try:
                            p_deg = float(p["degree"].split('°')[0])
                            p_min = float(p["degree"].split('°')[1].replace('′','').replace("'", "")) if '°' in p["degree"] else 0.0
                            p_total_deg = p_deg + p_min / 60.0
                            p_pada_calc = int(p_total_deg / 3.3333333333333335) + 1
                            if p_pada_calc > 9: p_pada_calc = 9
                        except Exception:
                            p_pada_calc = 1

                        if p_pada_calc == r_pada:
                            occupants.append({
                                "name": p["name"],
                                "degree": p["degree"],
                                "is_lagna": False,
                                "is_hand": p.get("is_hand", False),
                                "color": p.get("color", "#38bdf8")
                            })

                padas_data.append({
                    "rashi_pada": r_pada,
                    "nak_pada_num": nak_pada_num,
                    "occupants": occupants
                })

            nakshatras_data.append({
                "nakshatra_name": nak_name,
                "short_nakshatra_name": SHORT_NAKSHATRAS_TELUGU.get(nak_name, nak_name),
                "padas": padas_data
            })

        boxes[rashi] = {
            "rashi_name": rashi,
            "house_no": h_no,
            "karma_label": karma_label,
            "karma_class": karma_class,
            "is_lagna": is_lagna_box,
            "nakshatras": nakshatras_data
        }

    return boxes

@app.route("/nakshatra_chart", methods=["GET", "POST"])
def nakshatra_chart():
    if request.method == "POST":
        name = request.form.get("name", "")
        dob = request.form.get("dob", "")
        tob = request.form.get("tob", "")
        place = request.form.get("place", "")
        lat = request.form.get("lat")
        lon = request.form.get("lon")
        mobile_num = request.form.get("mobile", "")
        country_code = request.form.get("countryCode", "+91")
        mobile = f"{country_code} {mobile_num}" if mobile_num else ""
        req_telegram = request.form.get("req_telegram", "no")
        
        session['chart_form'] = {
            'name': name, 'dob': dob, 'tob': tob, 'place': place,
            'lat': lat, 'lon': lon, 'mobile': mobile, 'req_telegram': req_telegram
        }
        if name and dob:
            log_user_to_github(name, dob, tob, place, mobile=mobile)
    else:
        name = request.args.get("name")
        dob = request.args.get("dob")
        tob = request.args.get("tob")
        place = request.args.get("place")
        lat = request.args.get("lat")
        lon = request.args.get("lon")

        if not (name and dob and lat and lon):
            form_data = session.get('chart_form', {})
            if not form_data:
                birth_data = session.get('birth_info', {})
                if birth_data:
                    form_data = {
                        'name': birth_data.get('name', ''),
                        'dob': birth_data.get('dob', ''),
                        'tob': birth_data.get('tob', ''),
                        'place': birth_data.get('place', ''),
                        'lat': birth_data.get('lat'),
                        'lon': birth_data.get('lon')
                    }
            name = form_data.get('name', '')
            dob = form_data.get('dob', '')
            tob = form_data.get('tob', '')
            place = form_data.get('place', '')
            lat = form_data.get('lat')
            lon = form_data.get('lon')

    if not name or not dob or not lat or not lon:
        return render_template("nakshatra_form.html", page_title="నక్షత్ర పాద కుండలి - జననం వివరాలు")

    lat = float(lat)
    lon = float(lon)

    data = get_kundali_data(name, dob, tob, place, lat, lon)
    session['birth_info'] = data

    dasha_data = get_dasha_info(data)
    nakshatra_boxes = build_nakshatra_pada_boxes(data)

    return render_template(
        "nakshatra_chart.html",
        current_lang=session.get("lang", "te"),
        **data,
        **dasha_data,
        nakshatra_boxes=nakshatra_boxes
    )

@app.route("/nakshatra_transit_chart", methods=["POST"])
def nakshatra_transit_chart():
    lat = request.form.get("lat")
    lon = request.form.get("lon")
    timezone_str = request.form.get("timezone", "Asia/Kolkata")
    place = request.form.get("place", "ప్రస్తుత స్థానం")

    if not lat or not lon:
        birth_info = session.get('birth_info', {})
        lat = birth_info.get('lat', 17.3850)
        lon = birth_info.get('lon', 78.4867)
        place = birth_info.get('place', 'హైదరాబాద్')
        timezone_str = birth_info.get('timezone_str', 'Asia/Kolkata')

    lat = float(lat)
    lon = float(lon)

    local_tz = pytz.timezone(timezone_str)
    local_dt = datetime.datetime.now(local_tz)
    today_dob = local_dt.strftime("%Y-%m-%d")
    today_tob = local_dt.strftime("%H:%M")

    transit_data = get_kundali_data("ఈ రోజు గోచారం", today_dob, today_tob, place, lat, lon)
    transit_dasha = get_dasha_info(transit_data)
    transit_boxes = build_nakshatra_pada_boxes(transit_data)

    return render_template(
        "nakshatra_transit_partial.html",
        **transit_data,
        **transit_dasha,
        nakshatra_boxes=transit_boxes,
        today_formatted=local_dt.strftime("%d-%m-%Y %I:%M %p")
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
