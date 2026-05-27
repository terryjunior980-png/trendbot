import discord
from discord.ext import commands, tasks
import requests
from bs4 import BeautifulSoup
import anthropic
import json
import asyncio
from datetime import datetime

# ========================
# CONFIG — FILL THESE IN
# ========================
DISCORD_TOKEN = "MTUwOTE3MTIwNTA4Mzc1ODY2NA.GdmnqZ.HEMSX-4JGCY38ebMN1lOKsbMMnYXhh5r6l6SYM"
CHANNEL_ID = 1509172843265396903  # Your Discord channel ID
ANTHROPIC_API_KEY = "YOUR_ANTHROPIC_API_KEY"

# ========================
# BOT SETUP
# ========================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
client_ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ========================
# TRENDING PRODUCT FINDER
# ========================
def get_trending_products():
    products = []

    # Source 1: AliExpress Hot Products
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = "https://www.aliexpress.com/popular.html"
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.find_all("a", class_="item-title")[:5]
        for item in items:
            products.append({
                "name": item.text.strip(),
                "source": "AliExpress",
                "link": "https://www.aliexpress.com" + item.get("href", "")
            })
    except Exception as e:
        print(f"AliExpress error: {e}")

    # Source 2: CJ Dropshipping trending (free API)
    try:
        cj_url = "https://developers.cjdropshipping.com/api2.0/v1/product/list"
        params = {
            "pageNum": 1,
            "pageSize": 5,
            "orderBy": "hotSale"
        }
        res = requests.get(cj_url, params=params, timeout=10)
        data = res.json()
        if data.get("result"):
            for item in data["result"].get("list", []):
                products.append({
                    "name": item.get("productNameEn"),
                    "source": "CJ Dropshipping",
                    "link": f"https://cjdropshipping.com/product/{item.get('pid')}",
                    "price": item.get("sellPrice"),
                    "supplier_id": item.get("pid")
                })
    except Exception as e:
        print(f"CJ error: {e}")

    return products


# ========================
# AI: GENERATE CAPTION + HASHTAGS
# ========================
def generate_marketing_content(product_name):
    prompt = f"""
You are a viral social media marketing expert for dropshipping.

Product: {product_name}

Generate the following in JSON format only, no extra text:
{{
  "tiktok_caption": "...",
  "youtube_description": "...",
  "twitter_caption": "...",
  "hashtags": ["...", "...", "...", "...", "...", "...", "...", "...", "...", "..."],
  "why_trending": "...",
  "suggested_price": "...",
  "profit_margin_estimate": "..."
}}
"""
    response = client_ai.messages.create(
        model="claude-opus-4-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.content[0].text
    # Clean JSON
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


# ========================
# FIND MULTIPLE SUPPLIERS
# ========================
def find_suppliers(product_name):
    suppliers = []

    # CJ Dropshipping
    try:
        url = "https://developers.cjdropshipping.com/api2.0/v1/product/list"
        params = {"pageNum": 1, "pageSize": 3, "productName": product_name}
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        if data.get("result"):
            for item in data["result"].get("list", []):
                suppliers.append({
                    "platform": "CJ Dropshipping",
                    "product": item.get("productNameEn"),
                    "price": item.get("sellPrice"),
                    "link": f"https://cjdropshipping.com/product/{item.get('pid')}",
                    "supplier_id": item.get("pid")
                })
    except Exception as e:
        print(f"Supplier search error: {e}")

    # AliExpress search link (manual backup)
    suppliers.append({
        "platform": "AliExpress (manual)",
        "link": f"https://www.aliexpress.com/wholesale?SearchText={product_name.replace(' ', '+')}",
        "note": "Search and pick top seller"
    })

    return suppliers


# ========================
# FULFILL ORDER COMMAND
# ========================
@bot.command(name="fulfill")
async def fulfill_order(ctx, *, args):
    """
    Usage: !fulfill product="LED Strip Lights" orders=5 name="John Doe" address="123 Main St, NY" email="john@email.com"
    """
    await ctx.send("⚙️ Processing fulfillment request...")

    # Parse args
    try:
        parts = {}
        for part in args.split('" '):
            if "=" in part:
                key, val = part.split("=", 1)
                parts[key.strip()] = val.strip().strip('"')

        product = parts.get("product", "Unknown")
        orders = parts.get("orders", "1")
        name = parts.get("name", "N/A")
        address = parts.get("address", "N/A")
        email = parts.get("email", "N/A")

        embed = discord.Embed(
            title="📦 ORDER FULFILLMENT SENT",
            color=0x00ff88,
            timestamp=datetime.now()
        )
        embed.add_field(name="Product", value=product, inline=False)
        embed.add_field(name="Number of Orders", value=orders, inline=True)
        embed.add_field(name="Customer Name", value=name, inline=True)
        embed.add_field(name="Delivery Address", value=address, inline=False)
        embed.add_field(name="Email", value=email, inline=True)
        embed.add_field(
            name="Supplier Action",
            value="✅ Order details ready to forward to CJ Dropshipping",
            inline=False
        )
        embed.set_footer(text="Forward this to your CJ Dropshipping dashboard manually or via API")

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Error parsing fulfillment: {e}\n\nFormat: `!fulfill product=\"name\" orders=5 name=\"Customer\" address=\"Address\" email=\"email\"`")


# ========================
# DAILY TRENDING ALERT TASK
# ========================
@tasks.loop(hours=6)  # Runs every 6 hours
async def send_trending_products():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("Channel not found")
        return

    await channel.send("🔍 **Scanning for trending products...**")

    products = get_trending_products()

    if not products:
        await channel.send("⚠️ Couldn't fetch trending products right now. Retrying in 6 hours.")
        return

    for product in products[:3]:  # Send top 3
        try:
            marketing = generate_marketing_content(product["name"])
            suppliers = find_suppliers(product["name"])

            embed = discord.Embed(
                title=f"🔥 TRENDING: {product['name']}",
                color=0xff4500,
                timestamp=datetime.now()
            )
            embed.add_field(name="Source", value=product["source"], inline=True)
            embed.add_field(name="Why Trending", value=marketing.get("why_trending", "N/A"), inline=False)
            embed.add_field(name="Suggested Price", value=marketing.get("suggested_price", "N/A"), inline=True)
            embed.add_field(name="Profit Margin", value=marketing.get("profit_margin_estimate", "N/A"), inline=True)

            # Captions
            embed.add_field(name="🎵 TikTok Caption", value=marketing.get("tiktok_caption", "N/A"), inline=False)
            embed.add_field(name="🐦 Twitter Caption", value=marketing.get("twitter_caption", "N/A"), inline=False)

            # Hashtags
            hashtags = " ".join(marketing.get("hashtags", []))
            embed.add_field(name="📌 Hashtags", value=hashtags, inline=False)

            # Suppliers
            supplier_text = ""
            for s in suppliers[:3]:
                supplier_text += f"**{s['platform']}** — {s.get('link', 'N/A')}\n"
            embed.add_field(name="🏭 Suppliers", value=supplier_text, inline=False)

            embed.add_field(
                name="📦 To Fulfill Orders",
                value='`!fulfill product="PRODUCT NAME" orders=5 name="Customer" address="Address" email="email@email.com"`',
                inline=False
            )

            await channel.send(embed=embed)
            await asyncio.sleep(2)

        except Exception as e:
            await channel.send(f"⚠️ Error processing {product['name']}: {e}")


# ========================
# BOT READY
# ========================
@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")
    send_trending_products.start()


# ========================
# MANUAL TRIGGER COMMAND
# ========================
@bot.command(name="scan")
async def manual_scan(ctx):
    await ctx.send("🔍 Manual scan triggered...")
    await send_trending_products()


bot.run(DISCORD_TOKEN)
