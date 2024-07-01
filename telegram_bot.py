import os # Provides a way to interact with the operating system, used for environment variables
import telebot # The main library for creating Telegram bots
from datetime import datetime, timedelta # For working with dates and times
import pytz # Provides timezone definitions for Python
import logging # For logging messages and errors in the application
import threading # Allows running multiple threads (parts of the program) concurrently
import time # Provides various time-related functions
import json # For working with JSON data, used for storing and retrieving birthday information
import requests # For making HTTP requests, used to fetch Bitcoin prices and other online data
import holidays # Provides definitions for holidays in various countries
from telebot.apihelper import ApiException # For handling specific exceptions that may occur when interacting with the Telegram API
from calendar import month_abbr # Provides abbreviated month names, used for formatting dates in a more readable way

# User-configurable settings !! PLEASE UPDATE THESE SETTINGS ONLY !!
TIMEZONE = "Europe/Amsterdam"  # Default timezone, change if needed.
CURRENCY = "EUR"  # Options: "EUR" or "USD"

# Initialize timezone
try:
    user_timezone = pytz.timezone(TIMEZONE)
except pytz.exceptions.UnknownTimeZoneError:
    logger.warning(f"Unknown timezone: {TIMEZONE}. Defaulting to UTC.")
    user_timezone = pytz.UTC

# Helper function to get the current time in the user's timezone
def get_current_time():
    return datetime.now(user_timezone)

# Helper function to get the currency symbol
def get_currency_symbol():
    return "€" if CURRENCY == "EUR" else "$"

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("No bot token provided. Set the BOT_TOKEN environment variable.")
    exit(1)

COINGECKO_API_KEY = os.getenv('COINGECKO_API_KEY')
if not COINGECKO_API_KEY:
    logger.warning("No CoinGecko API key provided. Set the COINGECKO_API_KEY environment variable.")

AUTHORIZED_USER_ID = os.getenv('AUTHORIZED_USER_ID')
if not AUTHORIZED_USER_ID:
    logger.warning("No authorized user ID provided. Set the AUTHORIZED_USER_ID environment variable.")

# Initialize the bot
bot = telebot.TeleBot(BOT_TOKEN)

BIRTHDAYS_FILE = '/app/birthdays.json'
BITCOIN_CACHE = {'data': None, 'last_updated': None}
MEMPOOL_CACHE = {'data': None, 'last_updated': None}
LAST_NOTIFIED_PRICE = {'price': 0, 'thresholds': [], 'notified': []}

def api_request_with_backoff(func, max_retries=5, initial_delay=1):
    retries = 0
    while retries < max_retries:
        try:
            return func()
        except ApiException as e:
            if e.error_code == 502:
                delay = initial_delay * (2 ** retries)
                time.sleep(delay)
                retries += 1
            else:
                raise
    raise Exception("Max retries reached")

def format_date_for_display(date_string):
    """Convert DD-MM-YYYY to a format with month name."""
    day, month, year = map(int, date_string.split('-'))
    return f"{day} {month_abbr[month]} {year}"

def load_birthdays():
    """Load birthdays from the JSON file or create it if it doesn't exist."""
    if os.path.exists(BIRTHDAYS_FILE):
        with open(BIRTHDAYS_FILE, 'r') as f:
            birthdays = json.load(f)
        logger.info(f"Loaded {len(birthdays)} birthday groups from {BIRTHDAYS_FILE}")
        return birthdays
    else:
        logger.info(f"Birthdays file not found. Creating a new one at {BIRTHDAYS_FILE}")
        empty_birthdays = {}
        save_birthdays(empty_birthdays)
        return empty_birthdays

def save_birthdays(birthdays):
    """Save birthdays to a JSON file."""
    with open(BIRTHDAYS_FILE, 'w') as f:
        json.dump(birthdays, f, indent=2)
    logger.info(f"Saved {len(birthdays)} birthday groups to {BIRTHDAYS_FILE}")

def load_last_notified_price():
    """Load last notified price and thresholds from a JSON file."""
    if os.path.exists('last_notified.json'):
        with open('last_notified.json', 'r') as f:
            return json.load(f)
    else:
        logger.warning("Last notified price file not found. Starting with default values.")
        return {'price': 0, 'thresholds': [], 'notified': []}

def save_last_notified_price(last_notified_price):
    """Save last notified price and thresholds to a JSON file."""
    with open('last_notified.json', 'w') as f:
        json.dump(last_notified_price, f, indent=2)

birthdays = load_birthdays()
LAST_NOTIFIED_PRICE = load_last_notified_price()

MEMPOOL_CACHE = {'data': None, 'last_updated': None}

def get_mempool_data():
    """Fetch Bitcoin price and suggested fee from Mempool.space API with caching."""
    global MEMPOOL_CACHE
    current_time = datetime.now()

    if MEMPOOL_CACHE['last_updated'] and (current_time - MEMPOOL_CACHE['last_updated']) < timedelta(seconds=60):
        logger.debug("Using cached Mempool data")
        return MEMPOOL_CACHE['data']

    logger.info("Fetching new Mempool data")

    def fetch_data():
        price_response = requests.get("https://mempool.space/api/v1/prices")
        price_response.raise_for_status()
        price_data = price_response.json()

        fee_response = requests.get("https://mempool.space/api/v1/fees/recommended")
        fee_response.raise_for_status()
        fee_data = fee_response.json()

        return {
            'price_eur': price_data['EUR'],
            'price_usd': price_data['USD'],
            'fee': fee_data['fastestFee']
        }

    try:
        data = api_request_with_backoff(fetch_data)
        MEMPOOL_CACHE = {'data': data, 'last_updated': current_time}
        return data
    except Exception as e:
        logger.error(f"Error fetching data from Mempool.space: {e}")
        return None
        
def get_coingecko_price_change():
    """Fetch Bitcoin 24h price change from CoinGecko API."""
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=eur&include_24hr_change=true"
    headers = {
        "accept": "application/json",
        "x-cg-demo-api-key": COINGECKO_API_KEY,
    }
    def fetch_data():
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if 'bitcoin' not in data or 'eur_24h_change' not in data['bitcoin']:
            raise ValueError("Unexpected response format from CoinGecko API")
        return data['bitcoin']['eur_24h_change']

    try:
        price_change = api_request_with_backoff(fetch_data)
        logger.info(f"Successfully fetched 24h price change from CoinGecko: {price_change:.2f}%")
        return price_change
    except Exception as e:
        logger.error(f"Error fetching Bitcoin price change from CoinGecko: {e}")
        return None

def get_bitcoin_price():
    """Fetch the current Bitcoin price and combine data from Mempool and CoinGecko."""
    global BITCOIN_CACHE
    current_time = datetime.now()

    if BITCOIN_CACHE['last_updated'] and (current_time - BITCOIN_CACHE['last_updated']) < timedelta(seconds=60):
        logger.debug("Using cached Bitcoin data")
        return BITCOIN_CACHE['data']

    logger.info("Fetching new Bitcoin data")

    try:
        mempool_data = api_request_with_backoff(get_mempool_data)
        price_change = api_request_with_backoff(get_coingecko_price_change)

        if mempool_data:
            bitcoin_data = {
                'bitcoin': {
                    'eur': mempool_data['price_eur'],
                    'usd': mempool_data['price_usd'],
                    'eur_24h_change': price_change if price_change is not None else 'N/A',
                    'suggested_fee': mempool_data['fee']
                }
            }
            logger.info(f"Bitcoin price: €{mempool_data['price_eur']:.2f}, ${mempool_data['price_usd']:.2f}, 24h change: {price_change if price_change is not None else 'N/A'}")
        else:
            logger.warning("Mempool.space data fetch failed, falling back to CoinGecko")
            url = f"https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=eur,usd&include_24hr_change=true"
            
            def fetch_coingecko():
                response = requests.get(url, headers={'Content-Type': 'application/json'})
                response.raise_for_status()
                return response.json()

            bitcoin_data = api_request_with_backoff(fetch_coingecko)
            logger.info(f"Bitcoin price from CoinGecko: €{bitcoin_data['bitcoin']['eur']:.2f}, 24h change: {bitcoin_data['bitcoin'].get('eur_24h_change', 'N/A')}")

        BITCOIN_CACHE = {'data': bitcoin_data, 'last_updated': current_time}
        return bitcoin_data

    except Exception as e:
        logger.error(f"Error fetching Bitcoin price: {e}")
        return None

def check_and_notify_price_threshold(price, change_24h):
    """Check if Bitcoin price crossed a new threshold and notify."""
    global LAST_NOTIFIED_PRICE
    current_price = price
    next_threshold = (current_price // 1000 + 1) * 1000

    if next_threshold not in LAST_NOTIFIED_PRICE['thresholds']:
        LAST_NOTIFIED_PRICE['thresholds'].append(next_threshold)
        LAST_NOTIFIED_PRICE['thresholds'].sort()

    for threshold in LAST_NOTIFIED_PRICE['thresholds']:
        if current_price >= threshold and threshold not in LAST_NOTIFIED_PRICE['notified']:
            LAST_NOTIFIED_PRICE['notified'].append(threshold)
            message = f"🚀 Bitcoin price has crossed €{int(threshold):,.0f}!"
            chat_ids = [os.getenv('GROUP_CHAT_ID'), os.getenv('PERSONAL_CHAT_ID')]
            for chat_id in chat_ids:
                if chat_id:
                    bot.send_message(chat_id=chat_id, text=message)
                else:
                    logger.warning(f"No chat ID provided for {'group' if chat_id == os.getenv('GROUP_CHAT_ID') else 'personal'} chat.")

    LAST_NOTIFIED_PRICE['price'] = current_price
    save_last_notified_price(LAST_NOTIFIED_PRICE)

def check_bitcoin_price():
    """Check Bitcoin price and notify if significant change or threshold crossed."""
    while True:
        try:
            bitcoin_data = api_request_with_backoff(get_bitcoin_price)
            if bitcoin_data and 'bitcoin' in bitcoin_data:
                current_price = bitcoin_data['bitcoin']['eur']
                change_24h = bitcoin_data['bitcoin']['eur_24h_change']
                
                api_request_with_backoff(lambda: check_and_notify_price_threshold(current_price, change_24h))
                
                if abs(change_24h) > 5 and current_price != LAST_NOTIFIED_PRICE['price']:
                    message_to_send = f"Bitcoin price alert!\nCurrent price: €{current_price:,.2f}\nChange in last 24h: {change_24h:.2f}%"
                    chat_ids = [os.getenv('GROUP_CHAT_ID'), os.getenv('PERSONAL_CHAT_ID')]
                    for chat_id in chat_ids:
                        if chat_id:
                            api_request_with_backoff(lambda: bot.send_message(chat_id=chat_id, text=message_to_send))
            
        except Exception as e:
            logger.error(f"Error in check_bitcoin_price: {e}")
        
        time.sleep(3600)  # Check every hour

@bot.message_handler(commands=['help'])
def send_help(message):
    """Send a help message with available commands."""
    help_text = (
        "Available commands:\n\n"
        "/start or /hello - Get a welcome message\n"
        "/birthdays - List all birthdays\n"
        "/missing - Show names without birthdays\n"
        "/add [GROUP] [NAME] DD-MM-YYYY - Add a birthday to a specific group\n"
        "/delete [FULL NAME] - Remove a birthday (authorized users only)\n"
        "/bitcoin - Get current info about Bitcoin, price and suggested fee\n"
        "/soon - Show upcoming birthdays in the next 30 days\n"
        "/help - Show this help message\n\n"
        "Note: For /delete, you must use the person's full name as it appears in the birthday list."
    )
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['start', 'hello'])
def send_welcome(message):
    """Send a welcome message."""
    logger.info(f"Received start/hello command from user {message.from_user.id}")
    welcome_text = (
        "Hello! I'm your birthday and Bitcoin bot. "
        "Use /help to see available commands."
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['delete'])
def remove_birthday(message):
    """Remove a birthday from the list."""
    logger.info(f"Received delete command from user {message.from_user.id}")
    if not AUTHORIZED_USER_ID or str(message.from_user.id) != AUTHORIZED_USER_ID:
        bot.reply_to(message, "You are not authorized to remove birthdays.")
        return

    try:
        # Split the message and join all parts after the command as the name
        parts = message.text.split(' ')
        if len(parts) < 2:
            raise ValueError("Full name not provided")
        name = ' '.join(parts[1:])
        
        removed = False
        for group_name, group in birthdays.items():
            if name in group:
                del group[name]
                save_birthdays(birthdays)
                removed = True
                break
        
        if removed:
            bot.reply_to(message, f"Birthday of {name} has been removed successfully!")
        else:
            bot.reply_to(message, f"No birthday found for '{name}'. Please make sure you've entered the full name exactly as it appears in the birthday list.")
    except ValueError as e:
        bot.reply_to(message, f"Invalid format. Please use '/delete FULL NAME'. Error: {str(e)}")

@bot.message_handler(commands=['birthdays'])
def send_birthdays(message):
    """Send a list of all birthdays."""
    logger.info(f"Received birthdays command from user {message.from_user.id}")
    birthday_message = "📅 Birthday list!\n\n"
    today = datetime.now(user_timezone).date()
    missing_birthdays = []

    for group_name, group in birthdays.items():
        birthday_message += f"{group_name}:\n"
        for name, birthday in group.items():
            if not birthday:
                birthday_message += f"{name}: Birthday not set\n"
                missing_birthdays.append(name)
                continue

            birthday_date = datetime.strptime(birthday, "%d-%m-%Y").date()
            this_year_birthday = birthday_date.replace(year=today.year)

            if this_year_birthday < today:
                this_year_birthday = this_year_birthday.replace(year=today.year + 1)

            days_left = (this_year_birthday - today).days
            age = today.year - birthday_date.year
            if today < birthday_date.replace(year=today.year):
                age -= 1

            formatted_birthday = format_date_for_display(birthday)
            birthday_message += f"{name}: {formatted_birthday} ({age} years old, {days_left} days left)\n"
        birthday_message += "\n"

    next_birthday_name, days_until_next_birthday = get_next_birthday(today)
    birthday_message += f"🎂 The next birthday is {next_birthday_name}'s in {days_until_next_birthday} days\n\n"
    birthday_message += "See the birthdays in the next 30 days with /soon!\n\n"

    missing_birthdays_message = ""
    if missing_birthdays:
        count = len(missing_birthdays)
        if count == 1:
            missing_birthdays_message = f"There is still 1 birthday missing. You can add it using the /add Name DD-MM-YYYY command."
        else:
            missing_birthdays_message = f"There are still {count} birthdays missing. You can add them using the /add Name DD-MM-YYYY command."

    message_to_send = birthday_message + missing_birthdays_message
    bot.reply_to(message, message_to_send)

def get_fee_emoji(fee):
    """Return an appropriate emoji based on the fee."""
    if fee <= 1:
        return "🤩"  # Amazing
    elif 2 <= fee <= 10:
        return "😃"  # Great
    elif 11 <= fee <= 20:
        return "😐"  # OK
    elif 21 <= fee <= 100:
        return "😕"  # Meh
    else:
        return "😱"  # Super bad

@bot.message_handler(commands=['bitcoin'])
def send_bitcoin_price(message):
    """Send the current Bitcoin price."""
    logger.info(f"Received bitcoin command from user {message.from_user.id}")
    bitcoin_data = get_bitcoin_price()
    if bitcoin_data and 'bitcoin' in bitcoin_data:
        price = bitcoin_data['bitcoin']['eur']
        change_24h = bitcoin_data['bitcoin']['eur_24h_change']
        suggested_fee = bitcoin_data['bitcoin'].get('suggested_fee', 'N/A')

        # Determine the emoji based on the price change
        if change_24h == 'N/A':
            change_emoji = "❓"  # Question mark for unknown change
            change_text = "N/A (API error)"
        else:
            if change_24h > 0:
                change_emoji = "🟢"  # Green circle
            elif change_24h < 0:
                change_emoji = "🔴"  # Red circle
            else:
                change_emoji = "⚪️"  # White circle
            change_text = f"{change_24h:.2f}%"

        # Get the fee emoji
        fee_emoji = get_fee_emoji(suggested_fee)

        response = (
            "Bitcoin Price:\n"
            f"💰 Current Price: €{price:,.2f}\n"
            f"{change_emoji} 24h Change: {change_text}\n"
            f"{fee_emoji} Suggested Fee: {suggested_fee} sat/vB\n\n"
            "Data provided by Mempool.space and CoinGecko"
        )

        # Check if price crossed a new threshold
        if change_24h != 'N/A':
            check_and_notify_price_threshold(price, change_24h)
    else:
        response = "Sorry, I couldn't fetch the Bitcoin price at the moment. Please try again later."

    bot.reply_to(message, response)

@bot.message_handler(commands=['missing'])
def show_missing_birthdays(message):
    """Show names without birthdays."""
    logger.info(f"Received missing command from user {message.from_user.id}")
    names_without_birthdays = [
        f"{group_name}: {name}" for group_name, group in birthdays.items() for name, birthday in group.items() if not birthday
    ]

    if not names_without_birthdays:
        bot.reply_to(message, "All birthdays have been added.")
        return

    message_to_send = "The following names do not have birthdays yet:\n\n" + "\n".join(names_without_birthdays) + "\n\nUse /add Name DD-MM-YYYY to add a birthday."
    bot.reply_to(message, message_to_send)

@bot.message_handler(commands=['add'])
def add_birthday(message):
    """Add or update a birthday in the list."""
    logger.info(f"Received add command from user {message.from_user.id}")
    try:
        # Split the message into parts
        parts = message.text.split(' ')
        if len(parts) < 4:
            raise ValueError("Not enough information provided")
        
        command = parts[0]
        group = parts[1]
        date = parts[-1]  # The date should be the last part
        name = ' '.join(parts[2:-1])  # Join all parts between group and date as the name
        
        # Validate the date format
        try:
            birthday_date = datetime.strptime(date, "%d-%m-%Y")
            # Check if it's a valid date (e.g., not 31-02-2023)
            if birthday_date.strftime("%d-%m-%Y") != date:
                raise ValueError
        except ValueError:
            bot.reply_to(message, "Invalid date format or date. Please use DD-MM-YYYY and ensure it's a valid date.")
            return

        # Add the birthday to the specified group
        add_birthday_to_dict(group, name, date, message)
    except ValueError as e:
        bot.reply_to(message, f"Invalid format. Please use '/add [GROUP] [NAME] DD-MM-YYYY'. Error: {str(e)}\n\nNote: If you need to remove a birthday later, you'll need to use the full name with the /delete command.")

def add_birthday_to_dict(group, name, birthday, message):
    """Add or update a birthday in the dictionary and save it."""
    if group not in birthdays:
        birthdays[group] = {}
    
    if name in birthdays[group]:
        # Check if user is authorized to edit existing names
        if AUTHORIZED_USER_ID and str(message.from_user.id) == AUTHORIZED_USER_ID:
            birthdays[group][name] = birthday
            save_birthdays(birthdays)
            formatted_birthday = format_date_for_display(birthday)
            bot.reply_to(message, f"Birthday of {name} added to group '{group}' as {formatted_birthday} successfully!\n\nRemember: To remove this birthday later, you'll need to use the full name with the /delete command.")
        else:
            bot.reply_to(message, f"You are not authorized to edit {name}'s birthday.")
    else:
        birthdays[group][name] = birthday
        save_birthdays(birthdays)
        formatted_birthday = format_date_for_display(birthday)
        bot.reply_to(message, f"Birthday of {name} added to group '{group}' as {formatted_birthday} successfully!")

def get_next_birthday(today):
    """Get the name and days until the next birthday."""
    next_birthday_name = None
    days_until_next_birthday = float('inf')

    for group_name, group in birthdays.items():
        for name, birthday in group.items():
            if not birthday:
                continue

            birthday_date = datetime.strptime(birthday, "%d-%m-%Y").date()
            this_year_birthday = birthday_date.replace(year=today.year)

            if this_year_birthday < today:
                this_year_birthday = this_year_birthday.replace(year=today.year + 1)

            days_left = (this_year_birthday - today).days
            if days_left < days_until_next_birthday:
                days_until_next_birthday = days_left
                next_birthday_name = name

    return next_birthday_name, days_until_next_birthday

def get_upcoming_birthdays(today, days=7):
    """Get all birthdays in the next 'days' days."""
    upcoming = []
    for group_name, group in birthdays.items():
        for name, birthday in group.items():
            if not birthday:
                continue
            birthday_date = datetime.strptime(birthday, "%d-%m-%Y").date()
            this_year_birthday = birthday_date.replace(year=today.year)
            if this_year_birthday < today:
                this_year_birthday = this_year_birthday.replace(year=today.year + 1)
            days_left = (this_year_birthday - today).days
            if 0 <= days_left <= days:
                upcoming.append((name, this_year_birthday, days_left))
    return sorted(upcoming, key=lambda x: x[2])  # Sort by days left

@bot.message_handler(commands=['soon'])
def show_upcoming_birthdays(message):
    """Show birthdays in the next 30 days."""
    today = datetime.now(user_timezone).date()
    upcoming_birthdays = []

    for group_name, group in birthdays.items():
        for name, birthday in group.items():
            if birthday:
                birthday_date = datetime.strptime(birthday, "%d-%m-%Y").date()
                this_year_birthday = birthday_date.replace(year=today.year)
                
                if this_year_birthday < today:
                    this_year_birthday = this_year_birthday.replace(year=today.year + 1)
                
                days_until = (this_year_birthday - today).days
                
                if 0 <= days_until <= 30:
                    upcoming_birthdays.append((name, this_year_birthday, days_until))

    if upcoming_birthdays:
        upcoming_birthdays.sort(key=lambda x: x[2])  # Sort by days until birthday
        message_text = "Upcoming birthdays in the next 30 days:\n\n"
        for name, birthday_date, days_until in upcoming_birthdays:
            formatted_date = format_date_for_display(birthday_date.strftime("%d-%m-%Y"))
            message_text += f"{name}: {formatted_date} (in {days_until} days)\n"
    else:
        message_text = "No birthdays in the next 30 days."

    bot.reply_to(message, message_text)

def get_dutch_holidays(year):
    """Get Dutch holidays for a given year."""
    return holidays.NL(years=year)

def get_next_business_day(date, holidays):
    """Get the next business day excluding weekends and holidays."""
    next_day = date + timedelta(days=1)
    while next_day.weekday() >= 5 or next_day in holidays:
        next_day += timedelta(days=1)
    return next_day

def get_postcard_send_date(birthday_date, today=None):
    """Calculate the date to send a postcard."""
    if today is None:
        today = datetime.now(user_timezone).date()
    
    year = today.year
    nl_holidays = get_dutch_holidays(year)

    delivery_schedule = {
        0: 1,  # Monday -> Tuesday
        1: 1,  # Tuesday -> Wednesday
        2: 1,  # Wednesday -> Thursday
        3: 1,  # Thursday -> Friday
        4: 1,  # Friday -> Saturday
        5: 3,  # Saturday -> Tuesday
        6: 2,  # Sunday -> Tuesday
    }

    days_before = delivery_schedule[birthday_date.weekday()]
    send_date = birthday_date - timedelta(days=days_before)

    while send_date.weekday() >= 5 or send_date in nl_holidays:
        send_date -= timedelta(days=1)

    delivery_date = get_next_business_day(send_date, nl_holidays)
    while (delivery_date - send_date).days > 4:
        send_date -= timedelta(days=1)
        delivery_date = get_next_business_day(send_date, nl_holidays)

    return send_date

def check_next_birthday():
    """Check for upcoming birthdays and postcard reminders every 24 hours."""
    while True:
        try:
            logger.info("Starting daily birthday check")
            now = datetime.now(user_timezone)
            today = now.date()
            current_year = today.year
            nl_holidays = get_dutch_holidays(current_year)
            
            for group_name, group in birthdays.items():
                for name, birthday_str in group.items():
                    if birthday_str:
                        try:
                            birthday_date = datetime.strptime(birthday_str, "%d-%m-%Y").date()
                        except ValueError:
                            logger.error(f"Invalid date format for {name}: {birthday_str}")
                            continue

                        this_year_birthday = birthday_date.replace(year=current_year)
                        
                        if this_year_birthday < today:
                            this_year_birthday = this_year_birthday.replace(year=current_year + 1)
                            nl_holidays = get_dutch_holidays(current_year + 1)
                        
                        days_until = (this_year_birthday - today).days
                        
                        if days_until == 1:
                            logger.info(f"Sending birthday reminder for {name}")
                            message_to_send = f"It's {name}'s birthday tomorrow!"
                            send_notification(message_to_send)
                        
                        postcard_send_date = get_postcard_send_date(this_year_birthday, today)
                        if today == postcard_send_date and now.hour < 10:
                            logger.info(f"Sending postcard reminder for {name}")
                            formatted_birthday = format_date_for_display(this_year_birthday.strftime("%d-%m-%Y"))
                            message_to_send = f"Today is the last day to send a postcard to {name} for their birthday on {formatted_birthday}!"
                            send_notification(message_to_send)

            tomorrow = today + timedelta(days=1)
            next_run = user_timezone.localize(datetime(tomorrow.year, tomorrow.month, tomorrow.day, 8, 0, 0))
            sleep_seconds = (next_run - now).total_seconds()
            logger.info(f"Birthday check complete. Next check in {sleep_seconds:.0f} seconds")
            time.sleep(sleep_seconds)
        except Exception as e:
            logger.error(f"Error in birthday check loop: {e}")
            time.sleep(3600)  # Wait an hour before retrying

def send_notification(message):
    """Send a notification to all configured chat IDs."""
    chat_ids = [os.getenv('GROUP_CHAT_ID'), os.getenv('PERSONAL_CHAT_ID')]
    for chat_id in chat_ids:
        if chat_id:
            bot.send_message(chat_id=chat_id, text=message)
        else:
            logger.warning(f"No chat ID provided for {'group' if chat_id == os.getenv('GROUP_CHAT_ID') else 'personal'} chat.")
            
def send_test_message(chat_id, message):
    """Send a test message and return success status."""
    try:
        bot.send_message(chat_id=chat_id, text=message)
        return True
    except Exception as e:
        logger.error(f"Failed to send test message to chat ID {chat_id}. Error: {e}")
        return False

def run_all_tests():
    """Run all tests and return a summary."""
    logger.info("Running all tests...")
    tests_passed = True
    
    # Test price notification
    fake_price = 30000
    fake_change = 6
    personal_chat_id = os.getenv('PERSONAL_CHAT_ID')
    
    if personal_chat_id:
        tests_passed &= send_test_message(personal_chat_id, f"[TEST] 🚀 Bitcoin price has crossed €{int(fake_price):,.0f}!")
        tests_passed &= send_test_message(personal_chat_id, f"[TEST] Bitcoin price alert!\nCurrent price: €{fake_price:,.2f}\nChange in last 24h: {fake_change:.2f}%")
    else:
        logger.warning("No personal chat ID provided.")
        tests_passed = False
    
    # Test birthday notification
    today = datetime.now(user_timezone).date()
    tomorrow = today + timedelta(days=1)
    test_name = "Test Person"
    test_birthday = format_date_for_display(tomorrow.strftime("%d-%m-%Y"))
    
    if personal_chat_id:
        tests_passed &= send_test_message(personal_chat_id, f"[TEST] It's {test_name}'s birthday tomorrow!")
        tests_passed &= send_test_message(personal_chat_id, f"[TEST] Today is the last day to send a postcard to {test_name} for their birthday on {test_birthday}!")

    # Remove test person after tests
    if 'Others' in birthdays and 'Test Person' in birthdays['Others']:
        del birthdays['Others']['Test Person']
        save_birthdays(birthdays)
        logger.info("Removed test person from birthdays.")
    
    logger.info("All tests completed.")
    return tests_passed

def verify_chat_ids():
    """Verify the provided chat IDs."""
    chat_ids = {
        'GROUP_CHAT_ID': os.getenv('GROUP_CHAT_ID'),
        'PERSONAL_CHAT_ID': os.getenv('PERSONAL_CHAT_ID')
    }
    
    for name, chat_id in chat_ids.items():
        if not chat_id:
            logger.warning(f"{name} is not set.")
        else:
            try:
                int(chat_id)
                logger.info(f"{name} is set to: {chat_id}")
            except ValueError:
                logger.error(f"{name} is not a valid integer: {chat_id}")

if __name__ == "__main__":
    logger.info("Starting the bot...")
    
    # Verify chat IDs
    api_request_with_backoff(verify_chat_ids)
    
    # Run all tests
    tests_passed = api_request_with_backoff(run_all_tests)
    
    # Send a single notification about the bot's status
    personal_chat_id = os.getenv('PERSONAL_CHAT_ID')
    group_chat_id = os.getenv('GROUP_CHAT_ID')
    
    if tests_passed:
        status_message = "Bot restarted successfully. All systems operational. Use /help to see available commands."
    else:
        status_message = "Bot restarted, but some tests failed. The bot may not be fully operational. Please check the logs."
    
    if personal_chat_id:
        api_request_with_backoff(lambda: bot.send_message(chat_id=personal_chat_id, text=status_message))
    else:
        logger.warning("No personal chat ID provided. Could not send status message.")
    
    if group_chat_id:
        api_request_with_backoff(lambda: bot.send_message(chat_id=group_chat_id, text="Bot restarted. Use /help to see available commands."))
    else:
        logger.warning("No group chat ID provided. Could not send status message to group.")
    
    # Start the regular threads
    threading.Thread(target=check_next_birthday, daemon=True).start()
    threading.Thread(target=check_bitcoin_price, daemon=True).start()
    
    # Main polling loop with backoff
    while True:
        try:
            api_request_with_backoff(lambda: bot.polling(none_stop=True))
        except Exception as e:
            logger.error(f"Error in main polling loop: {e}")
            time.sleep(10)  # Wait 10 seconds before trying to reconnect
