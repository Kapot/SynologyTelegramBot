# Birthday Reminder and Bitcoin Price Telegram Bot for Synology NAS

This repository contains a Telegram bot that manages birthdays by multiple users, sends reminders, provides Bitcoin price information, and more. It's designed to run on a Synology NAS using Docker.

It is tested on a Synology DS920+ running DSM 7.2.1-69057, using the image version of python:3.11.0-slim-bullseye.

## Prerequisites

- Synology NAS with Container Manager installed
- Telegram account
- CoinGecko API key (free tier)
- Basic knowledge of Docker and Synology DSM

## Setup Instructions

### 1. Create a Telegram Bot

1. Open Telegram and search for the "BotFather" bot.
2. Start a chat and send `/newbot` to create a new bot.
3. Follow the prompts to choose a name and username for your bot.
4. Save the API token provided by BotFather.
5. Use the following command to set up the bot commands:
   `/setcommands`
   Then select your bot and paste the following list of commands:
start - Get a welcome message
hello - Get a welcome message
birthdays - List all birthdays
missing - Show names without birthdays
add - Add a birthday (format: /add Name DD-MM-YYYY)
delete - Remove a birthday (authorized users only)
bitcoin - Get current Bitcoin price
soon - Show upcoming birthdays in the next 30 days
help - Show the help message with available commands

### 2. Get Your Chat IDs

1. Start a chat with your new bot.
2. Send a message to the bot.
3. Open this URL in your browser, replacing `<YOUR_BOT_TOKEN>` with your actual bot token: https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
4. Look for the `"chat":{"id":` field in the JSON response. This number is your chat ID.
5. If you want to use the bot in a group chat, add the bot to the group and send a message in the group. Then check the above URL again to find the group chat ID.

### 3. Get a CoinGecko API Key

1. Go to [CoinGecko's website](https://www.coingecko.com/en/api) and create an account.
2. Navigate to your developers dashboard and find your API key.

### 4. Prepare the Synology NAS

1. Log in to your Synology DSM.
2. Open the Package Center and install Container Manager if not already installed.
3. Create a shared folder named "docker" and inside that a folder called "telegram-bot" (if not exists) to store your Docker files.

### 5. Download and Modify the birthday file

1. Download the birthdays.json file from this repository. This is an example list.
2. Open the file with a text editor.
3. Modify the file to include your own data:
   - You can rename, add, or remove groups as needed (e.g., "Family", "Friends", "Colleagues").
   - Replace the example names with real names you want to track.
   - Update the birthdays, keeping the DD-MM-YYYY format.
   - You can add names without birthdays and (let others) add them in Telegram.
   - Ensure each name is unique across all groups.
4. Save the file as birthdays.json

Note: 
- If you don't have a birthdays.json file, the bot will create an empty one on first run, which you can then populate using the bot commands.

### 7. Upload Bot Files

1. Download these files from this github:
- `telegram_bot.py` (the main bot script)
- `start.sh` (the startup script)
2. In File Station, navigate to the "docker/telegram-bot" shared folder.
3. Upload these files to the "birthday-bot" folder:
- `telegram_bot.py` (the main bot script)
- `start.sh` (the startup script)
- `birthdays.json` (list with birthdays, if you already have one from previous step. If not uploaded the bot will make an empty one itself)

### 5. Set Up the Docker Container

1. Open the Container Manager package in DSM.
2. Go to "Registry" and search for "python". Pull the Python image.
   - Recommended version: python:3.11.0-slim-bullseye. You can find it in the drop down list.
3. Go to "Image" and verify that the Python image is present.
4. Go to "Container" and click the "Create" button.
5. Choose the Python image and click "Next".
6. Set the container name (e.g., "birthday-bot"), select auto-restart and click "Advanced Settings".
7. In the "Volume" tab, add a new folder mount:
   - File/Folder: Choose the "docker/telegram-bot" shared folder
   - Mount path: /app
8. In the "Environment" tab, add these variables:
   - BOT_TOKEN: "Your Telegram bot token"
   - GROUP_CHAT_ID: "Your group chat ID"
   - PERSONAL_CHAT_ID: "Your personal chat ID"
   - COINGECKO_API_KEY: "Your CoinGecko API key"
   - AUTHORIZED_USER_ID: "Telegram user id for authorization on deleting birthdays and names"
9. In the "Execute Command" field, enter: `/bin/sh /app/start.sh`
10. Click "Next"
11. Make sure to select "Run this container after the wizard is finished" and review the settings.
12. Click "Done" - The container is now starting.

## Usage

Once the bot is running, you can interact with it using these commands:

- `/start` or `/hello`: Get a welcome message
- `/birthdays`: List all birthdays
- `/missing`: Show names without birthdays
- `/add [Name] [DD-MM-YYYY]`: Add or adjust a birthday (adjusting is for authorized users only)
- `/delete [Name]`: Remove a birthday (authorized users only)
- `/bitcoin`: Get current Bitcoin price and additional information
- `/soon`: Show upcoming birthdays in the next 30 days
- `/help`: Show the help message with available commands

## Features

- Birthday management and reminders
- Others users can also add (missing) birthdays
- Bitcoin price tracking with threshold notifications
- Automatic postcard sending reminders (configured for The Netherlands)
- Dutch holiday awareness for postcard scheduling
- Separate notifications for personal and group chats
- Customizable timezone and currency settings (EUR and USD)
- Theres a limit rate on the API calls. It's set to 60 seconds.

## Maintenance

- The bot stores birthday data in `/app/birthdays.json`. You can back up this file to preserve the data.
- To update the bot, stop the container, replace the Python script, and restart the container.
- Monitor the container logs in the Docker package for any error messages. (Close and re-open Container Manager to pull the lastest logs)
- Ensure that all environment variables (BOT_TOKEN, GROUP_CHAT_ID, PERSONAL_CHAT_ID, COINGECKO_API_KEY, AUTHORIZED_USER_ID) are correctly set.

## Troubleshooting

- If the bot doesn't respond, check the container logs for error messages. (Close and re-open Container Manager to pull the lastest logs)
- Verify that all required files are in the correct location in the "docker" shared folder.
- Ensure that the CoinGecko API key is valid and has not exceeded its rate limit.
- Check that both GROUP_CHAT_ID and PERSONAL_CHAT_ID are set correctly for proper notifications.

## Contributing

Feel free to open issues or submit pull requests to improve the bot or this documentation.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
