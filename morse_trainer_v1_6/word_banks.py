"""
word_banks.py - Morse Trainer v1.5
ITU Morse code mappings, vocabulary banks, and standard QSO abbreviation definitions.
"""

from typing import Dict, Tuple

# ITU Standard Morse Code Mapping
ITU_MORSE_MAP: Dict[str, str] = {
    # Letters
    "A": ".-",    "B": "-...",  "C": "-.-.",  "D": "-..",   "E": ".",
    "F": "..-.",  "G": "--.",   "H": "....",  "I": "..",    "J": ".---",
    "K": "-.-",   "L": ".-..",  "M": "--",    "N": "-.",    "O": "---",
    "P": ".--.",  "Q": "--.-",  "R": ".-.",   "S": "...",   "T": "-",
    "U": "..-",   "V": "...-",  "W": ".--",   "X": "-..-",  "Y": "-.--",
    "Z": "--..",
    # Numbers
    "1": ".----", "2": "..---", "3": "...--", "4": "....-", "5": ".....",
    "6": "-....", "7": "--...", "8": "---..", "9": "----.", "0": "-----",
    # Punctuation & Prosigns
    "?": "..--..", "/": "-..-.", "=": "-...-", ".": ".-.-.-", ",": "--..--",
    "<AR>": ".-.-.", "<SK>": "...-.-", "<BT>": "-...-", "<KN>": "-.--.",
}

# 2-Letter High-Frequency Words
WORDS_2: Tuple[str, ...] = (
    "TO", "IN", "IT", "IS", "BE", "AS", "AT", "SO",
    "WE", "HE", "BY", "OR", "ON", "DO", "IF", "ME",
    "MY", "UP", "AN", "GO", "NO", "US", "AM", "OF",
)

# 3-Letter High-Frequency Words
WORDS_3: Tuple[str, ...] = (
    "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL",
    "ANY", "CAN", "HAD", "HER", "WAS", "ONE", "OUR", "OUT",
    "DAY", "GET", "HAS", "HIM", "HIS", "HOW", "MAN", "NEW",
    "NOW", "OLD", "SEE", "TWO", "WAY", "WHO", "DID", "ITS",
    "LET", "PUT", "SAY", "SHE", "TOO", "USE",
)

# 4-Letter High-Frequency Words
WORDS_4: Tuple[str, ...] = (
    "THAT", "WITH", "HAVE", "THIS", "WILL", "YOUR", "FROM", "THEY",
    "KNOW", "WANT", "BEEN", "GOOD", "MUCH", "SOME", "TIME", "VERY",
    "WHEN", "COME", "HERE", "JUST", "LIKE", "LONG", "MAKE", "MANY",
    "MORE", "ONLY", "OVER", "SUCH", "TAKE", "THAN", "THEM", "WELL",
    "WERE",
)

# Common CW Operator Names
COMMON_NAMES: Tuple[str, ...] = (
    "BOB", "BILL", "JOHN", "TOM", "STEVE", "TIM", "DAVE", "GARY",
    "JIM", "CHRIS", "MIKE", "ED", "AL", "RON", "DAN", "KEN",
    "TONY", "JOE", "PAUL", "JACK", "PETE", "PAT", "GUS",
)

# Core QSO Terms and Abbreviations
CORE_QSO: Tuple[str, ...] = (
    "CQ", "DE", "K", "KN", "BK", "R", "73", "UR", "RST", "599",
    "579", "559", "QTH", "NAME", "RIG", "ANT", "PWR", "WX", "HR",
    "TEMP", "ES", "FB", "TU", "TNX", "OP", "OM", "HW?", "AGN",
    "QSL", "QSO", "QRM", "QRN", "QSB", "QRP", "QRT", "QRZ", "CUL",
)

# QSO Term Meanings / Expansions
QSO_MEANINGS: Dict[str, str] = {
    "CQ": "Calling Any Station",
    "DE": "From / This is",
    "K": "Go Ahead (Over)",
    "KN": "Go Ahead Specific Station",
    "BK": "Break / Back to You",
    "R": "Roger / Received",
    "73": "Best Regards",
    "UR": "Your / You Are",
    "RST": "Signal Report (R-S-T)",
    "599": "Signal 599 (Readability-Strength-Tone)",
    "579": "Signal 579",
    "559": "Signal 559",
    "QTH": "Location",
    "NAME": "Operator Name",
    "RIG": "Radio Equipment",
    "ANT": "Antenna",
    "PWR": "Transmit Power",
    "WX": "Weather",
    "HR": "Here",
    "TEMP": "Temperature",
    "ES": "And",
    "FB": "Fine Business (Great)",
    "TU": "Thank You",
    "TNX": "Thanks",
    "OP": "Operator",
    "OM": "Old Man (Friend)",
    "HW?": "How Copy?",
    "AGN": "Again",
    "QSL": "Acknowledge Receipt / Card",
    "QSO": "Radio Contact",
    "QRM": "Man-Made Interference",
    "QRN": "Atmospheric Static / Noise",
    "QSB": "Signal Fading",
    "QRP": "Low Power (<=5W)",
    "QRT": "Stopping Transmission",
    "QRZ": "Who Is Calling Me?",
    "CUL": "See You Later",
}

WORD_BANKS: Dict[str, Tuple[str, ...]] = {
    "WORDS_2": WORDS_2,
    "WORDS_3": WORDS_3,
    "WORDS_4": WORDS_4,
    "NAMES": COMMON_NAMES,
    "QSO": CORE_QSO,
}


def get_bank(category: str) -> Tuple[str, ...]:
    return WORD_BANKS.get(category, WORDS_3)


def get_meaning(token: str) -> str:
    return QSO_MEANINGS.get(token.upper(), "")
