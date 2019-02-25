from calendar import Calendar
from calendar import monthrange
from calendar import SUNDAY
from collections import Counter
from datetime import datetime
from dateutil.parser import parse
from googleapiclient import discovery
from googleapiclient.http import build_http
from logging import error
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import message_if_missing
from oauth2client.tools import run_flow
from PIL import Image
from PIL import ImageFont
from PIL.ImageDraw import Draw

from timezone import get_now

# The file containing Google Calendar API authentication secrets.
# https://developers.google.com/calendar/quickstart/python
CLIENT_SECRETS_FILE = "g_calendar_secrets.json"

# The file containing Google Calendar API authentication credentials.
CREDENTIALS_STORAGE_FILE = "g_calendar_credentials.json"

# The scope for retrieving events with the Google Calendar API.
API_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"

# The name of the Google Calendar API.
API_NAME = "calendar"

# The Google Calendar API version.
API_VERSION = "v3"

# The ID of the calendar to show.
CALENDAR_ID = "primary"

# The number of days in a week.
DAYS_IN_WEEK = 7

# The maximum numer of (partial) weeks in a month.
WEEKS_IN_MONTH = 6

# The color of the image background.
BACKGROUND_COLOR = (255, 255, 255)

# The color used for days.
TEXT_COLOR = (0, 0, 0)

# The color used for the current day and events.
TODAY_DOLOR = (255, 255, 255)

# The squircle image file.
SQUIRCLE_FILE = "assets/squircle.png"

# The dot image file.
DOT_FILE = "assets/dot.png"

# The margin between dots.
DOT_MARGIN = 4

# The color used to highlight the current day and events.
HIGHLIGHT_COLOR = (255, 0, 0)

# The size of any text.
TEXT_SIZE = 20

# The font to use for any text.
FONT = ImageFont.truetype("assets/Roboto-Bold.ttf", size=TEXT_SIZE)

# The vertical offset for any text.
TEXT_Y_OFFSET = int(0.6 * TEXT_SIZE)

# The maximum number of events to show.
MAX_EVENTS = 3


def get_event_counts(now):
    """Retrieves a daily count of events using the Google Calendar API."""

    event_counts = Counter()

    # TODO: Manage the full auth redirect flow starting without credentials.
    # Read the credentials from file or use the auth flow to create it.
    storage = Storage(CREDENTIALS_STORAGE_FILE)
    credentials = storage.get()
    if not credentials or credentials.invalid:
        message = message_if_missing(CLIENT_SECRETS_FILE)
        flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE, scope=API_SCOPE,
                                       message=message)
        credentials = run_flow(flow, storage)

    # Create an authorized connection to the API.
    http = build_http()
    if credentials.access_token_expired:
        try:
            credentials.refresh(http)
            storage.put(credentials)
        except IOError as e:
            error("Failed to save credentials: %s", e)
    authed_http = credentials.authorize(http=http)
    service = discovery.build(API_NAME, API_VERSION, http=authed_http)

    # Process calendar events for eahc day of the current month.
    first_day, last_day = monthrange(now.year, now.month)
    first_date = now.replace(day=first_day, hour=0, minute=0, second=0,
                             microsecond=0)
    last_date = first_date.replace(day=last_day)
    page_token = None
    while True:
        # Request this month's events.
        request = service.events().list(calendarId=CALENDAR_ID,
                                        timeMin=first_date.isoformat(),
                                        timeMax=last_date.isoformat(),
                                        singleEvents=True,
                                        pageToken=page_token)
        response = request.execute()

        # Iterate over the events from the current page.
        for event in response["items"]:
            # Count regular events.
            try:
                start = parse(event["start"]["dateTime"])
                event_counts[start.day] += 1
                end = parse(event["end"]["dateTime"])
                if start.day != end.day:
                    event_counts[end.day] += 1
            except KeyError:
                pass

            # Count all-day events.
            try:
                start = datetime.strptime(event["start"]["date"], "%Y-%m-%d")
                event_counts[start.day] += 1
                end = datetime.strptime(event["end"]["date"], "%Y-%m-%d")
                if start.day != end.day:
                    event_counts[end.day] += 1
            except KeyError:
                pass

        # Move to the next page or stop.
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return event_counts


def get_calendar_image(width, height):
    """Generates an image with a calendar view."""

    # Show a calendar relative to the current date.
    now = get_now()

    # Get the number of events per day from the API.
    event_counts = get_event_counts(now)

    # Create a blank image.
    image = Image.new(mode="RGB", size=(width, height), color=BACKGROUND_COLOR)
    draw = Draw(image)

    # Determine the spacing of the days in the image.
    x_stride = width / (DAYS_IN_WEEK + 1)
    y_stride = height / (WEEKS_IN_MONTH + 1)

    # Get this month's calendar.
    calendar = Calendar(firstweekday=SUNDAY)
    weeks = calendar.monthdayscalendar(now.year, now.month)

    # Draw each week in a row.
    for week_index in range(len(weeks)):
        week = weeks[week_index]

        # Draw each day in a column.
        for day_index in range(len(week)):
            day = week[day_index]

            # Ignore days from other months.
            if day == 0:
                continue

            # Determine the position of this day in the image.
            x = (day_index + 1) * x_stride
            y = (week_index + 1) * y_stride

            # Mark the current day with a squircle.
            if day == now.day:
                squircle = Image.open(SQUIRCLE_FILE)
                squircle_position = (x - squircle.size[0] / 2,
                                     y - squircle.size[1] / 2)
                draw.bitmap(squircle_position, squircle, HIGHLIGHT_COLOR)
                text_color = TODAY_DOLOR
                event_color = TODAY_DOLOR
            else:
                text_color = TEXT_COLOR
                event_color = HIGHLIGHT_COLOR

            # Draw the day of the month text.
            text = str(day)
            text_width, _ = draw.textsize(text, FONT)
            text_position = (x - text_width / 2,
                             y - TEXT_Y_OFFSET)
            draw.text(text_position, text, text_color, FONT)

            # Draw a dot for each event.
            num_events = min(MAX_EVENTS, event_counts[day])
            dot = Image.open(DOT_FILE)
            if num_events > 0:
                events_width = (num_events * dot.size[0] +
                                (num_events - 1) * DOT_MARGIN)
                for event_index in range(num_events):
                    event_offset = (event_index * (dot.size[0] +
                                    DOT_MARGIN) - events_width / 2)
                    dot_position = [
                        x + event_offset,
                        y + TEXT_Y_OFFSET + DOT_MARGIN - dot.size[0] / 2]
                    draw.bitmap(dot_position, dot, event_color)

    return image
