import discord
from discord.ext import commands, tasks
import requests
from bs4 import BeautifulSoup
from groq import Groq
import json
import asyncio
from datetime import datetime
import os

# ========================
# CONFIG
# ========================
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
CHANNEL_ID = 1509172843265396903

# ========================
# BOT SETUP
# ========================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
client_ai = Groq(api_key=GROQ_API_KEY)

# ========================
# TRENDING PRODUCT FINDER
# ========================
def get_trending_products():
    products = []

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

    # Fallback hardcoded trending categories if scraping fails
    if not products:
        products = [
            {"name": "LED Strip Lights", "source": "Fallback", "link": "https://www.aliexpress.com/wholesale?SearchText=LED+strip+lights"},
            {"name": "Portable Blender", "source": "Fallback", "link": "https://www.aliexpress.com/wholesale?SearchText=portable+blender"},
            {"name": "Phone Stand Holder", "source": "Fallback", "link": "https://www.aliexpress.com/wholesale?SearchText=phone+stand+holder"},
            {"name": "Magnetic Phone Case", "source": "Fallback", "link": "https://www.aliexpress.com/wholesale?SearchText=magnetic+phone+case"},
            {"name": "Mini Projector", "source": "Fallback", "link": "https://www.aliexpress.com/wholesale?SearchText=mini+projector"},
        ]

    return products


# ========================
# AI: GENERATE CAPTION + HASHTAGS
# ========================
def generate_marketing_content(product_name):
    prompt = f"""
You are a viral social media marketing expert for dropshipping.

Product: {product_name}

Generate the following in JSON format only, no extra text, no markdown:
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
    response = client_ai.chat.completions.create(
        model="llama3-8b-8192",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000
    )
    text = response.choices[0].message.content
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


# ========================
# FIND MULTIPLE SUPPLIERS
# ========================
def find_suppliers(product_name):
    suppliers = [
        {
            "platform": "AliExpress",
            "link": f"https://www.aliexpress.com/wholesale?SearchText={product_name.replace(' ', '+')}"
        },
        {
            "platform": "CJ Dropshipping",
            "link": f"https://cjdropshipping.com/search?q={product_name.replace(' ', '+')}"
        },
        {
            "platform": "Zendrop",
            "link": f"https://app.zendrop.com/search?query={product_name.replace(' ', '+')}"
        }
    ]
    return suppliers


# ========================
# FULFILL ORDER COMMAND
# ========================
@bot.command(name="fulfill")
async def fulfill_order(ctx, *, args):
    await ctx.send("⚙️ Processing fulfillment request...")

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
            title="📦 ORDER FULFILLMENT",
            color=0x00ff88,
            timestamp=datetime.now()
        )
        embed.add_field(name="Product", value=product, inline=False)
        embed.add_field(name="Number of Orders", value=orders, inline=True)
        embed.add_field(name="Customer Name", value=name, inline=True)
        embed.add_field(name="Delivery Address", value=address, inline=False)
        embed.add_field(name="Email", value=email, inline=True)
        embed.add_field(
            name="Next Step",
            value="✅ Go to CJ Dropshipping dashboard and place order with these details",
            inline=False
        )

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Error: {e}")


# ========================
# DAILY TRENDING ALERT TASK
# ========================
@tasks.loop(hours=6)
async def send_trending_products():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("Channel not found")
        return

    await channel.send("🔍 **Scanning for trending products...**")

    products = get_trending_products()

    for product in products[:3]:
        try:
            marketing = generate_marketing_content(product["name"])
            suppliers = find_suppliers(product["name"])

            embed = discord.Embed(
                title=f"🔥 TRENDING: {product['name']}",
                color=0xff4500,
                timestamp=datetime.now()
            )
            embed.add_field(name="🌍 Source", value=product["source"], inline=True)
            embed.add_field(name="💡 Why Trending", value=marketing.get("why_trending", "N/A"), inline=False)
            embed.add_field(name="💰 Suggested Price", value=marketing.get("suggested_price", "N/A"), inline=True)
            embed.add_field(name="📈 Profit Margin", value=marketing.get("profit_margin_estimate", "N/A"), inline=True)
            embed.add_field(name="🎵 TikTok Caption", value=marketing.get("tiktok_caption", "N/A"), inline=False)
            embed.add_field(name="🐦 Twitter Caption", value=marketing.get("twitter_caption", "N/A"), inline=False)

            hashtags = " ".join(marketing.get("hashtags", []))
            embed.add_field(name="📌 Hashtags", value=hashtags, inline=False)

            supplier_text = ""
            for s in suppliers:
                supplier_text += f"**{s['platform']}** — {s['link']}\n"
            embed.add_field(name="🏭 Suppliers", value=supplier_text, inline=False)

            embed.add_field(
                name="📦 Fulfill Orders",
                value='`!fulfill product="PRODUCT NAME" orders=5 name="Customer" address="Address" email="email@email.com"`',
                inline=False
            )

            await channel.send(embed=embed)
            await asyncio.sleep(3)

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
# MANUAL TRIGGER
# ========================
@bot.command(name="scan")
async def manual_scan(ctx):
    await ctx.send("🔍 Manual scan triggered...")
    await send_trending_products()


bot.run(DISCORD_TOKEN)
