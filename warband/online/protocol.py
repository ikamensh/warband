"""Network identity, independent of the package/release version.

Keep these values for changes existing clients can still play. A breaking
change advances GAME_ID and is recorded with tools/network_compatibility.py.
PROTOCOL describes Saga2D's transport, not Warband's rules or save format.
"""

GAME_ID = "warband-v2"
PROTOCOL = 1
