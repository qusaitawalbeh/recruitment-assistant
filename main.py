from src.gmail_auth import get_gmail_service

try:
    service = get_gmail_service()
    profile = service.users().getProfile(userId="me").execute()
    print("Connected as:", profile["emailAddress"])
    print("Total messages:", profile["messagesTotal"])
except FileNotFoundError as e:
    print("Missing file:", e)
except Exception as e:
    print("Gmail connection failed:", e)