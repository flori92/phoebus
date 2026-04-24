
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    print("SUCCESS: InstalledAppFlow imported")
except ImportError as e:
    print(f"FAIL: InstalledAppFlow: {e}")

try:
    from google.auth.transport.requests import Request as GoogleRequest
    print("SUCCESS: GoogleRequest imported")
except ImportError as e:
    print(f"FAIL: GoogleRequest: {e}")

try:
    from googleapiclient.discovery import build as google_build
    print("SUCCESS: google_build imported")
except ImportError as e:
    print(f"FAIL: google_build: {e}")
