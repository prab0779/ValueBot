import discord
from discord.ext import commands
import pandas as pd
import difflib
import os
import openpyxl
from discord import Embed
import re
import sqlite3
from datetime import datetime
import random
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

# Load the data from an Excel file
file_path = r"C:\DiscordBot\valuesbot.xlsx"  # Ensure the file is in the correct path
data = pd.read_excel(file_path)  # Load the data into a pandas DataFrame
print(data.head())  # Verify the data is loading correctly.

# Debugging: Print the column names to verify the data structure
print("Columns in DataFrame:", data.columns)

# Bot setup: Enabling necessary intents and configuring the bot
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent

bot = commands.Bot(command_prefix="?", intents=intents)

# List of authorized user IDs
AUTHORIZED_USER_IDS = [
      512671808886013962
    # Add more IDs as needed
]
# Define a global check function
def is_authorized(ctx):
    # Check if the user's ID is in the authorized list
    return ctx.author.id in AUTHORIZED_USER_IDS

# Add the global check to the bot
@bot.check
async def global_check(ctx):
    if not is_authorized(ctx):
        await ctx.reply("🚫 You do not have permission to use this command.", mention_author=False)
        return False
        print(f"User {ctx.author.id} attempted to use a command.")
    return True

# Define allowed channels by their ID (not name for more reliability)
ALLOWED_CHANNELS = [1311682438564548618, 1312926942152101921]

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="?", intents=intents)

# Check if the command is being used in the correct channel
async def is_correct_channel(ctx):
    if ctx.channel.id not in ALLOWED_CHANNELS:  # Using channel ID for reliability
        # Respond with an error message directing to the correct channel
        await ctx.reply(f"⚠️ Please use this command in one of the following channels: <#{ALLOWED_CHANNELS[0]}> or <#{ALLOWED_CHANNELS[1]}>", mention_author=False)
        return False
    return True


# Clean up column names by stripping any extra spaces
data.columns = data.columns.str.strip()

# Utility function: Search for an item in the data (case-sensitive or case-insensitive)
def enhanced_find_item(data, item_name, case_sensitive=True):
    # Adjust for case sensitivity in item names
    item_name = item_name if case_sensitive else item_name.lower()
    data['Item name'] = data['Item name'].str.lower(
    ) if not case_sensitive else data['Item name']

    # First, try to find exact matches
    match = data[data['Item name'].str.contains(item_name, na=False)]
    if not match.empty:
        # If an exact match is found, return details
        row = match.iloc[0]
        return (f"**Item name**: {row['Item name']}\n"
                f"**Demand**: {row['Demand (out of 10)']}/10\n"
                f"**Value**: {row['Value']}\n"
                f"**Rate of change**: {row['rate of change']}")
    else:
        # If no exact match is found, use fuzzy matching to suggest similar items
        item_names = data['Item name'].tolist()
        suggestions = difflib.get_close_matches(item_name,
                                                item_names,
                                                n=5,
                                                cutoff=0.5)
        if suggestions:
            # Provide suggestions if found
            suggestion_text = "\n".join(
                [f"- {suggestion}" for suggestion in suggestions])
            return f"Item not found. Did you mean one of these?\n{suggestion_text}"
        else:
            return "Item not found. Please check the name and try again."


# Utility function: Find an exact or closest match using fuzzy matching
def find_exact_or_closest(item_name):
    """
    Search for the item in the Excel sheet by exact match or closest match.
    Assumes 'data' is a DataFrame containing item data.
    """
    # Remove emojis and extra spaces from item names
    sanitized_name = re.sub(r"<:[^:]+:[0-9]+>", "", item_name).strip()

    # Ensure 'data' exists and contains the necessary columns
    if 'Item name' not in data.columns or 'Value' not in data.columns:
        return None

    # Try to find an exact match
    match = data[data['Item name'].str.casefold() == sanitized_name.casefold()]
    if not match.empty:
        return match.iloc[0]

    # Fallback: Find closest match (case-insensitive substring match)
    closest_match = data[data['Item name'].str.contains(sanitized_name,
                                                        case=False)]
    if not closest_match.empty:
        return closest_match.iloc[0]

    # If no match is found, return None
    return None


# Command: Show top X items based on a specific criterion (demand or value)
@bot.command(name="top", aliases=["t"])
async def top_items(ctx, number: int = 5, *, criterion: str = "demand"):
    criterion = criterion.lower()
        # Log the command usage
    print(f"Command '{ctx.command}' used by {ctx.author} in channel {ctx.channel}")
    if criterion not in ["demand", "value"]:
        await ctx.reply("Invalid criterion! Use `demand` or `value`.",
                        mention_author=False)
        return
    try:
        # Convert the relevant column to numeric and drop invalid entries
        column_name = "Demand (out of 10)" if criterion == "demand" else "Value"
        data[column_name] = pd.to_numeric(data[column_name], errors='coerce')
        sorted_data = data.dropna(subset=[column_name]).sort_values(
            by=column_name, ascending=False).head(number)

        if sorted_data.empty:
            await ctx.reply(
                f"No items found for the specified criterion: {criterion}.",
                mention_author=False)
            return

        # Create an embed to format the response
        embed = discord.Embed(
            title=f"Top {number} Items by {criterion.capitalize()}",
            description=
            f"Here are the top {number} items sorted by {criterion}.",
            color=discord.Color.blue())

        # Add each item as a field in the embed
        for index, (_, row) in enumerate(sorted_data.iterrows(), start=1):
            embed.add_field(
                name=f"{index}. {row['Item name']}",
                value=f"**{criterion.capitalize()}**: {row[column_name]}",
                inline=False)

        # Send the embed as a reply to the user
        await ctx.reply(embed=embed, mention_author=False)

    except Exception as e:
        await ctx.reply(
            "An error occurred while fetching the top items. Please try again later.",
            mention_author=False)
        print(e)


# Command: Filter items based on a given condition (supports Python-like syntax)
@bot.command(name="filter", aliases=["f"])
async def filter_items(ctx, *, condition: str):
    try:
        # Map shorthand names to actual column names
        column_aliases = {
            "demand": "Demand (out of 10)",
            "value": "Value",
            "rate_of_change": "rate of change"
        }

        # Replace shorthand with actual column names
        for alias, actual_name in column_aliases.items():
            condition = condition.replace(alias, f"`{actual_name}`")

        # Ensure columns are numeric
        for column in ["Demand (out of 10)", "Value", "rate of change"]:
            if column in data.columns:
                data[column] = pd.to_numeric(data[column], errors='coerce')

        # Apply the query
        filtered_data = data.query(condition)

        if filtered_data.empty:
            await ctx.reply("No items match the given filter criteria.",
                            mention_author=False)
            return

        # Format and send results
        embed = discord.Embed(
            title="Filtered Items",
            description=f"Items matching the filter: `{condition}`",
            color=discord.Color.green())

        for _, row in filtered_data.head(10).iterrows():
            embed.add_field(
                name=row["Item name"],
                value=
                f"**Demand**: {row['Demand (out of 10)']}\n**Value**: {row['Value']}",
                inline=False)

        if len(filtered_data) > 10:
            embed.set_footer(
                text=
                "Showing the first 10 results. Refine your filter for more specific results."
            )
        await ctx.reply(embed=embed, mention_author=False)

    except Exception as e:
        await ctx.reply(
            "Invalid filter criteria. Use Python-like syntax, e.g., `demand > 8`.",
            mention_author=False)
        print(f"Error: {e}")


# Command: Compare two items side by side (supports emojis as input)
# Helper functions and parse_items function should be defined before any command that uses them
emoji_to_item = {
    "<:for:1311162334839832668>": "with",
    "<:frost:1310042922737078373>": "frostaura",  #working
    "<:festiveaura:1310042957969227916>": "festiveaura",  #working
    "<:21aura:1310043771379126293>": "demon21aura",  #working
    "<:beerussoul:1310042878885629993>": "beerussoul",  #working
    "<:blackcatrinhat:1310043726780956704>": "blackcatrinhat",  #working
    "<:broloearrings:1310043329420984320>": "broloearrings",  #noemoji for this
    "<:cellaura:1310043101657698444>": "cellaura",  #working
    "<:conquerorsoul:1310042030973649037>": "conquerorsoul",  #working
    "<:demonmark:1310041182453370990>": "Majinmark",  #working
    "<:despairsoul:1309978206463590420>": "despairsoul",  #working
    "<:dsjacket:1309947700413993082>": "DSjacket",  #working
    "<:easteraura:1310042997236174878>": "easteraura",  #working
    "<:exilesoul:1310043040102223892>": "exilesoul",  #working
    "<:grandmasteraura:1310040611059142697>": "Grandmasteraura",  #working
    "<:hairglow:1310042234703577090>": "hairglow",  #working
    "<:halflaset:1310042381378257036>": "Halflaset",  #working
    "<:halloweenaura2023:1310042323693862972>": "Halloweenaura2023",  #working
    "<:halloweenaura2024:1310042271999066122>": "Halloweenaura2024",  #working
    "<:halloweenhalo:1310041989303111680>": "halloweenhalo",  #not on sheet
    "<:headlessaura:1310042193838342184>": "headlessaura",  #working
    "<:whitecatrinhat:1310041902678020096>": "whitecatrinhat",  #working
    "<:whitecatrinset:1310043188349636669>": "whitecatrinset",  #working
    "<:whitepumpkin2023:1310039452030074890>": "whitepumpkin2023",  #working
    "<:BrolyZset:1310043690965930064>": "BrolyZset",  #working
    "<:lifesoul:1310040385711767583>": "lifesoul",  #working
    "<:lighttunnelmask:1310041821136556072>": "lighttunnelmask",  #working
    "<:opamancape:1310041141147598859>": "opamancape",  #not on sheet
    "<:permaconquerorsoul:1310041057232420865>": "permaconqueror",  #working 
    "<:permadespairsoul:1309977040702931065>": "permadespairsoul",  #working 
    "<:swordofhopesoul:1310042139811643463>": "swordofhope",  #working 
    "<:trollfacemask:1310040334658568203>": "trollfacemask",  #working
    "<:ultrainstinktaura:1310039517297639434>": "UIaura",  #working 
    "<:permabeerussoul:1310042085943935066>": "permabeerussoul",  #working 
    "<:permaexilesoul:1310041011623428156>": "permaexilesoul",  #working 
    "<:permalifesoul:1310040659369001041>": "permalifesoul",  #working 
    "<:permasaviorsoul:1309976592004419705>": "permasaviorsoul",  #NOT_working 
    "<:permasohsoul:1310040708681568299>": "permasoh",  #working 
    "<:santahat:1310040524283056158>": "santahat",  #working
    "<:saviorsoul:1309974884465508374>": "saviorsoul",  #working
    "<:shadowaura:1310040483736588400>": "Shadowaura",  #working
    "<:shenronaura:1310040439360983102>": "shenronaura",  #working
    "<:blackcatrinset:1310043282734190693>": "blackcatrinset",  #working
    "<:SD3:1311699819898732554>": "SD3",  #working
    "<:SD4:1311699829629386856>": "SD4",  #working
    "<:SD5:1311699859824185355>": "SD5",  #working
    "<:beowolfgloves:1311752799985467392>": "beowolfgloves",  #working
    "<:Kaleaura:1311752831430295573>": "Kaleaura",  #working
    "<:zenkaipermastone:1311751798930804897>": "zenkaipermastone",  #working
    "<:legendarypermastone:1311751795412045865>":
    "legendarypermastone",  #working
    "<:BrolyZaura:1311751792912240720>": "BrolyZaura",  #working
    "<:senzubean:1311751797450211368>": "senzubean",  #working
    "<:BrolySaura:1311751790584397929>": "BrolySaura"  #working
}

item_to_emoji = {value: key for key, value in emoji_to_item.items()}


def parse_items(trade_str):
    """
    Parses a trade string into a list of (item_name, quantity) tuples.
    Handles emoji-based items and text items with quantities (xN).
    """
    tokens = trade_str.split()
    parsed_items = []
    i = 0

    while i < len(tokens):
        token = tokens[i]

        # Check if the token is an emoji or text-based item
        item_name = emoji_to_item.get(token,
                                      token)  # Map emoji to name or keep text

        # Look ahead to check for quantity (xN)
        if i + 1 < len(tokens) and tokens[i + 1].startswith('x') and tokens[
                i + 1][1:].isdigit():
            quantity = int(tokens[i + 1][1:])  # Extract quantity
            i += 2  # Move past both the item and the quantity
        else:
            quantity = 1
            i += 1  # Move past the item only

        parsed_items.append((item_name, quantity))

    # Combine quantities of duplicate items
    combined_items = {}
    for item, qty in parsed_items:
        if item in combined_items:
            combined_items[item] += qty
        else:
            combined_items[item] = qty

    return list(combined_items.items())

def calculate_trade_details(trade):
    """
    Calculates the total value of a trade and prepares a detailed breakdown.
    """
    total_value = 0
    item_details = []

    for item_name, quantity in trade:
        # Replace with your item lookup function
        item_data = find_exact_or_closest(item_name)
        emoji = item_to_emoji.get(item_name,
                                  item_name)  # Use emoji if available

        if item_data is not None and not item_data.empty:  # Check if the item data is valid
            try:
                # Safely convert the value to an integer
                item_value = int(item_data['Value'])
            except (ValueError,
                    TypeError):  # Handle cases where the value is invalid
                item_value = 0  # Default to 0 if the value is not numeric

            total_item_value = item_value * quantity
            total_value += total_item_value

            item_details.append(
                f"{emoji} x{quantity} (**{item_value}** each) = **{total_item_value}**"
            )
        else:
            # Handle cases where the item is not found
            item_details.append(f"{emoji} x{quantity} (**Value not found**)")

    return total_value, "\n".join(item_details)


# Now, you can safely call parse_items in your compare command
@bot.command(name="compare", aliases=["c"])
async def compare(ctx, *, trade_details: str = None):
    """
    Compare trades and provide a detailed summary including total values,
    comparison results, and percentage difference. Supports multiple items.
    """
    logging.info(f"Command '{ctx.command}' used by {ctx.author} in channel {ctx.channel}")
    if not await is_correct_channel(ctx):  # If the check fails, exit the command
        return
    if not trade_details:
        await ctx.send(
            "Please provide trade details in this format:\n\n"
            "!c my_items (in emoji) <:for:1311162334839832668> their_items (in emoji)"
        )
        return

    # Replace emojis in the trade details with their mapped names
    for emoji, name in emoji_to_item.items():
        trade_details = trade_details.replace(emoji, name)

    # Ensure the separator "with" exists in the input
    if " with " not in trade_details:
        await ctx.send(
            "Please provide trade details in this format:\n\n"
            "!c my_items (in emoji) <:for:1311162334839832668> their_items (in emoji)"
        )
        return

    # Split the input into "my trade" and "their trade"
    try:
        my_trade_str, their_trade_str = map(str.strip,
                                            trade_details.split(" with "))
    except ValueError:
        await ctx.send(
            "Error parsing trade details. Ensure the format is correct.")
        return

    # Parse items for both trades
    my_trade = parse_items(my_trade_str)
    their_trade = parse_items(their_trade_str)

    # Calculate trade values
    my_trade_value, my_trade_details = calculate_trade_details(my_trade)
    their_trade_value, their_trade_details = calculate_trade_details(
        their_trade)

    # Determine result and percentage difference
    if my_trade_value == their_trade_value:
        result = "Fair Trade!"
        color = discord.Color.yellow()
        percentage_difference = 0
    elif my_trade_value > their_trade_value:
        result = "L, you are overpaying!"
        color = discord.Color.red()
        percentage_difference = round(
            ((my_trade_value - their_trade_value) / their_trade_value) * 100,
            2)  # Difference relative to the smaller value
    else:
        result = "W, they are overpaying!"
        color = discord.Color.green()
        percentage_difference = round(
            ((their_trade_value - my_trade_value) / my_trade_value) * 100,
            2)  # Difference relative to the smaller value

    # Create embed
    embed = discord.Embed(title="Trade Comparison", color=color)
    embed.add_field(name="Your Trade",
                    value=f"**Items:**\n{my_trade_details}\n\n"
                    f"**Total Value**: {my_trade_value}",
                    inline=False)

    embed.add_field(name="Their Trade",
                    value=f"**Items:**\n{their_trade_details}\n\n"
                    f"**Total Value**: {their_trade_value}",
                    inline=False)

    embed.add_field(name="Result", value=f"**{result}**", inline=False)

    embed.add_field(name="Percentage Difference",
                    value=f"**{percentage_difference}%**",
                    inline=False)

    embed.set_footer(text="Contact @helper for more info.")

    # Send the embed
    await ctx.reply(embed=embed)

# Custom Help Command: Displays the list of available bot commands
bot.remove_command(
    "help")  # Remove the default help command to replace with a custom one

@bot.command(name="help", aliases=["h"])
async def custom_help(ctx):
    logging.info(f"Command '{ctx.command}' used by {ctx.author} in channel {ctx.channel}")
    if not await is_correct_channel(ctx):  # If the check fails, exit the command
        return
    # Create an embed to format the help text
    embed = discord.Embed(
        title=" Help Menu",
        description="Here are the available commands and how to use them:",
        color=discord.Color.green(),
    )
    # Add fields for each command category
    embed.add_field(
        name="🔍 Value Commands",
        value=
        "`!value [item emoji]` or `!v [item emoji]`: Get the value, demand, and rate of change for an item.",
        inline=False)
    embed.add_field(
        name="⚔ Compare Items",
        value=
        "`!compare [item1 as emoji] :for: [item2 as emoji]`: Compare **multiple** items side by side. \n you can even do this: !c [:item emoji] x5 :for: [item emoji] x10\n\n",
        inline=False)
    embed.add_field(
        name="📊 Top Items",
        value=
        "`!top [number] [criterion]`: List the top items based on `demand` or `value`.\nExample: `!top 5 demand`.\n\n",
        inline=False)
    embed.add_field(
        name="🔎 Filter Items",
        value=
        "`!filter [condition]`: Find items matching specific criteria.\nExample: `!filter demand > 8`.",
        inline=False)
    embed.add_field(
        name="📈 Recent Updates",
        value="`!recent [number]`: List items with the highest rate of change.",
        inline=False)
    embed.add_field(
        name="❓ Help Command",
        value=
        "`!help`: Show this help message. \n \n also all commands can be used by first letter only Example: !v or !h",
        inline=False)

    # Add a footer
    embed.set_footer(text="Use these commands to get insights about items! 🚀")

    # Reply to the user's message with the embed
    await ctx.reply(embed=embed, mention_author=False)


# Command: Get value, demand, and rate of change for a specific item
@bot.command(name="value", aliases=["v"])
async def value(ctx, *, item_name: str = None):
    logging.info(f"Command '{ctx.command}' used by {ctx.author} in channel {ctx.channel}")
    if not await is_correct_channel(ctx):  # If the check fails, exit the command
        return
    # Ensure the user provides an item name
    if not item_name:
        await ctx.reply(
            "Please provide an item name. Example: `!value Frost Aura`",
            mention_author=False)
        return

    # Convert emoji input to corresponding item name
    if item_name in emoji_to_item:
        item_name = emoji_to_item[item_name]

    # Search for the item in the data
    result = enhanced_find_item(data, item_name, case_sensitive=False)

    if "Item not found" in result:  # If the item is not found
        await ctx.reply(result, mention_author=False)
        return

    # Parse the item's details
    exact_match = find_exact_or_closest(item_name)
    if exact_match is None:
        await ctx.reply("Item not found. Please check the name and try again.",
                        mention_author=False)
        return

    # Find the corresponding emoji for the exact match
    item_emoji = next((emoji for emoji, name in emoji_to_item.items()
                       if name.lower() == exact_match['Item name'].lower()),
                      None)

    # Use the emoji or fallback to the item name
    item_display = item_emoji if item_emoji else exact_match['Item name']

    # Create a Discord embed with the item details
    embed = discord.Embed(
        title="Item Details",
        description=f"Information for {item_display}",
        color=discord.Color.blue(),
    )
    embed.add_field(name="Demand",
                    value=f"{exact_match['Demand (out of 10)']}/10",
                    inline=True)
    embed.add_field(name="Value", value=f"{exact_match['Value']}", inline=True)
    embed.add_field(name="Rate of Change",
                    value=f"{exact_match['rate of change']}",
                    inline=False)

    # Add footer or any additional notes
    embed.set_footer(text="Use the !compare command to compare items!")

    # Reply to the triggering message
    await ctx.reply(embed=embed, mention_author=False)

@bot.command(name="spin", aliases=["s"])
async def spin(ctx, spins: int = 1):
    """
    Spin to roll for Dragon Souls with specified probabilities, supporting multiple spins.
    """
    logging.info(f"Command '{ctx.command}' used by {ctx.author} in channel {ctx.channel}")
    if not await is_correct_channel(ctx):  # If the check fails, exit the command
        return
    # Define the Dragon Souls and their probabilities
    dragon_souls = [
        ("🔴Destruction Soul", 0.001),
        ("🔴Savior Soul", 0.14),
        ("🟡Life Soul", 0.11),
        ("🟡Soul of Hope", 0.18),
        ("🟡Exiled Soul", 0.43),
        ("🟠Vampiric Soul", 0.29),
        ("🟠Time Soul", 0.86),
        ("🟠Prideful Soul", 1.43),
        ("🟠Dual Soul", 3.14),
        ("🟣Solid Soul", 1.16),
        ("🟣Explosive Soul", 1.54),
        ("🟣Fighting Soul", 1.54),
        ("🟣Endurance Soul", 1.54),
        ("🟣Wizard’s Soul", 1.93),
        ("🔵Health Soul", 21.43),
        ("🔵Ki Power Soul", 21.43),
        ("🔵Stamina Soul", 21.43),
        ("🔵Strength Soul", 21.43),
    ]

    # Calculate cumulative probabilities
    cumulative_probabilities = []
    current_sum = 0
    for _, probability in dragon_souls:
        current_sum += probability
        cumulative_probabilities.append(current_sum)

    # Limit the number of spins to avoid excessive spam
    max_spins = 100000
    if spins > max_spins:
        await ctx.reply(
            f"⚠️ You can only spin up to {max_spins} times at once.",
            mention_author=False)
        return

    results = []  # Store the results of all spins

    # Perform spins
    for _ in range(spins):
        random_number = random.uniform(
            0, 100)  # Generate a number between 0 and 100
        for index, soul in enumerate(dragon_souls):
            if random_number <= cumulative_probabilities[index]:
                results.append(soul[0])  # Add the selected soul to results
                break

    # Format the results into a single message
    result_message = "\n".join(f"Spin {_+1}: **{soul}**" for _, soul in enumerate(results))
    
    # Split the result_message into smaller chunks if it's too long
    chunk_size = 1900  # Adjust the chunk size to leave room for extra characters
    for i in range(0, len(result_message), chunk_size):
        await ctx.reply(f"🎉 Here are your spin results (Part {i//chunk_size + 1}):\n{result_message[i:i + chunk_size]}",
                        mention_author=False)

# Create or connect to SQLite database
conn = sqlite3.connect("trade_history.db")
cursor = conn.cursor()

# Create the trades table if it doesn't exist
cursor.execute("""
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    user_name TEXT,
    trade_details TEXT,
    my_value INTEGER,
    their_value INTEGER,
    result TEXT,
    timestamp TEXT
)
""")

conn.commit()

# Command: Record trade history
@bot.command(name="history", aliases=["hs"])
async def history(ctx, *, trade_details: str = None):
    """
    Record a trade in the database and provide a summary of the transaction.
    Use the format: `!history [my_items] <:for:1310746627572633664> [their_items]`
    """
    logging.info(f"Command '{ctx.command}' used by {ctx.author} in channel {ctx.channel}")
    if not await is_correct_channel(ctx):  # If the check fails, exit the command
        return
    if not trade_details:
        await ctx.reply(
            "Please provide trade details in this format:\n"
            "`!history [my_items] <:for:1310746627572633664> [their_items]`",
            mention_author=False,
        )
        return

    # Replace emojis if applicable
    for emoji, name in emoji_to_item.items():
        trade_details = trade_details.replace(emoji, name)

    if " with " not in trade_details:
        await ctx.reply(
            "Invalid format! Use `!history [my_items] <:for:1310746627572633664> [their_items]`",
            mention_author=False,
        )
        return

    # Split into "my trade" and "their trade"
    try:
        my_trade_str, their_trade_str = map(str.strip,
                                            trade_details.split(" with "))
    except ValueError:
        await ctx.reply(
            "Error parsing trade details. Ensure the format is correct.",
            mention_author=False,
        )
        return

    # Parse and calculate trade values
    my_trade = parse_items(my_trade_str)
    their_trade = parse_items(their_trade_str)

    my_value, my_details = calculate_trade_details(my_trade)
    their_value, their_details = calculate_trade_details(their_trade)

    # Determine trade result
    if my_value == their_value:
        result = "Fair Trade"
    elif my_value > their_value:
        result = "You Overpaid"
    else:
        result = "They Overpaid"

    # Save the trade to the database
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO trades (user_id, user_name, trade_details, my_value, their_value, result, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (ctx.author.id, str(ctx.author), trade_details, my_value, their_value,
         result, timestamp),
    )
    conn.commit()

    # Provide a summary to the user
    embed = discord.Embed(title="Trade Recorded", color=discord.Color.blue())
    embed.add_field(
        name="Your Trade",
        value=f"**Items:**\n{my_details}\n**Total Value**: {my_value}",
        inline=False,
    )
    embed.add_field(
        name="Their Trade",
        value=f"**Items:**\n{their_details}\n**Total Value**: {their_value}",
        inline=False,
    )
    embed.add_field(name="Result", value=f"**{result}**", inline=False)
    embed.set_footer(text=f"Trade recorded at {timestamp}")

    await ctx.reply(embed=embed, mention_author=False)

# Command: Retrieve trade history for a user
@bot.command(name="myhistory", aliases=["mh"])
async def myhistory(ctx):
    """
    Retrieve the user's trade history from the database.
    """
    logging.info(f"Command '{ctx.command}' used by {ctx.author} in channel {ctx.channel}")
    if not await is_correct_channel(ctx):  # If the check fails, exit the command
        return
    user_id = ctx.author.id
    cursor.execute(
        "SELECT trade_details, my_value, their_value, result, timestamp FROM trades WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5",
        (user_id, ),
    )
    records = cursor.fetchall()

    if not records:
        await ctx.reply("No trade history found for you.",
                        mention_author=False)
        return

    embed = discord.Embed(
        title="Your Recent Trade History",
        description="Here are your last 5 trades:",
        color=discord.Color.green(),
    )
    for record in records:
        trade_details, my_value, their_value, result, timestamp = record
        embed.add_field(
            name=f"Trade on {timestamp}",
            value=(f"**Trade Details:** {trade_details}\n"
                   f"**Your Value:** {my_value}\n"
                   f"**Their Value:** {their_value}\n"
                   f"**Result:** {result}"),
            inline=False,
        )
    await ctx.reply(embed=embed, mention_author=False)

# Event: Capture and process messages
@bot.event
async def on_message(message):
    if message.author.bot:
        return  # Ignore messages from other bots
    print(
        f"[{message.author}] {message.content}")  # Log messages for debugging
    await bot.process_commands(message)

# Run the bot with the provided token (replace 'token' with the actual bot token)
bot.run("TOKEN")# Replace with your actual bot token
