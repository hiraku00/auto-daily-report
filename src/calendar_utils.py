import datetime
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def get_calendar_service():
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Token refresh failed: {e}. Re-authenticating...")
                if os.path.exists('token.json'):
                    os.remove('token.json')
                creds = None
        
        if not creds:
            if not os.path.exists('credentials.json'):
                print("No credentials.json found. Please download it from Google Cloud Console.")
                return None
            
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('calendar', 'v3', credentials=creds)
    return service

def get_todays_events(target_date=None):
    """
    Returns a list of events for the specified day.
    Each event is a tuple (start_time, summary).
    target_date: datetime.date or datetime.datetime object. If None, uses today.
    """
    service = get_calendar_service()
    if not service:
        return []

    if target_date is None:
        target_date = datetime.datetime.now()
    
    # Ensure it's a datetime object for replacement
    if isinstance(target_date, datetime.date) and not isinstance(target_date, datetime.datetime):
        target_date = datetime.datetime.combine(target_date, datetime.time.min)

    # Use local timezone offset instead of 'Z' (UTC)
    # astimezone() without arguments uses the local timezone
    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0).astimezone().isoformat()
    end_of_day = target_date.replace(hour=23, minute=59, second=59, microsecond=0).astimezone().isoformat()

    try:
        events_result = service.events().list(calendarId='primary', timeMin=start_of_day,
                                              timeMax=end_of_day, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])
        
        event_list = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'No Title')
            event_list.append((start, summary))
            
        return event_list

    except Exception as e:
        print(f"An error occurred: {e}")
        return []

if __name__ == '__main__':
    events = get_todays_events()
    for start, summary in events:
        print(f"{start}: {summary}")
