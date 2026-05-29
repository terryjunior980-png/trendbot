import discord
from discord.ext import commands, tasks
import requests
from groq import Groq
import json
import asyncio
from datetime import datetime
import os
import re


DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
CJ_API_KEY = os.environ.get("CJ_API_KEY")
CHANNEL_ID = 1509172843265396903

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
client_ai = Groq(api_key=GROQ_API_KEY)

# ========================
# TRENDING PRODUCTS FROM REDDIT
# ========================
from trending import get_trending_products
def generate_marketing_content(product_name):
    prompt = f"""
You are a viral social media marketing expert for dropshipping.
Product: {product_name}
Generate the following in JSON format only, no extra text, no markdown:
{{
  "tiktok_caption": "...",
  "twitter_caption": "...",
  "hashtags": ["...", "...", "...", "...", "...", "...", "...", "...", "...", "..."],
  "why_trending": "...",
  "suggested_price": "...",
  "profit_margin_estimate": "..."
}}
"""
    response = client_ai.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000
    )
    text = response.choices[0].message.content
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)

# ========================
# CJ DROPSHIPPING
# ========================
def get_cj_token():
    url = "https://developers.cjdropshipping.com/api2.0/v1/authentication/getAccessToken"
    payload = {"apiKey": CJ_API_KEY}
    res = requests.post(url, json=payload, timeout=10)
    data = res.json()
    if data.get("result"):
        return data["data"]["accessToken"]
    return None

def search_cj_product(product_name, token):
    url = "https://developers.cjdropshipping.com/api2.0/v1/product/list"
    headers = {"CJ-Access-Token": token}
    params = {"pageNum": 1, "pageSize": 3, "productName": product_name}
    res = requests.get(url, headers=headers, params=params, timeout=10)
    data = res.json()
    if data.get("result") and data.get("data"):
        return data["data"].get("list", [])
    return []

def get_product_vid(pid, token):
    url = f"https://developers.cjdropshipping.com/api2.0/v1/product/query?pid={pid}"
    headers = {"CJ-Access-Token": token}
    res = requests.get(url, headers=headers, timeout=10)
    data = res.json()
    if data.get("result") and data.get("data"):
        variants = data["data"].get("variants", [])
        if variants:
            return variants[0].get("vid", "")
    return ""

def create_cj_order(token, vid, quantity, customer):
    url = "https://developers.cjdropshipping.com/api2.0/v1/shopping/order/createOrderV2"
    headers = {"CJ-Access-Token": token}
    payload = {
        "orderNumber": f"ORDER-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "shippingZip": customer["zip"],
        "shippingCountryCode": customer["country"],
        "shippingCountry": customer["country"],
        "shippingProvince": customer["province"],
        "shippingCity": customer["city"],
        "shippingAddress": customer["address"],
        "shippingCustomerName": customer["name"],
        "shippingPhone": customer["phone"],
        "fromCountryCode": "CN",
        "logisticName": "CJPacket Ordinary",
        "products": [{"vid": vid, "quantity": quantity}]
    }
    res = requests.post(url, headers=headers, json=payload, timeout=10)
    return res.json()

def get_order_tracking(order_id, token):
    url = f"https://developers.cjdropshipping.com/api2.0/v1/shopping/order/getOrderDetail?orderId={order_id}"
    headers = {"CJ-Access-Token": token}
    res = requests.get(url, headers=headers, timeout=10)
    return res.json()

# ========================
# COMMANDS
# ========================
@bot.command(name="scan")
async def manual_scan(ctx):
    await ctx.send("🔍 Manual scan triggered...")
    await send_trending_products()

@bot.command(name="search")
async def search_product(ctx, *, product_name):
    await ctx.send(f"🔍 Searching CJ for: {product_name}")
    token = get_cj_token()
    if not token:
        await ctx.send("❌ Could not connect to CJ.")
        return
    products = search_cj_product(product_name, token)
    if not products:
        await ctx.send("❌ No products found.")
        return
    for p in products[:3]:
        pid = p.get("pid", "")
        name = p.get("productNameEn", "N/A")
        price = p.get("sellPrice", "N/A")
        vid = get_product_vid(pid, token)
        embed = discord.Embed(title=f"🛒 {name}", color=0x0099ff)
        embed.add_field(name="Price", value=f"${price}", inline=True)
        embed.add_field(name="VID", value=f"`{vid}`", inline=True)
        embed.add_field(
            name="Fulfill Command",
            value=f'`!fulfill product={product_name.replace(" ", "-")} orders=1 name=John_Doe address=123_Main_St city=New_York province=NY zip=10001 country=US phone=1234567890 vid={vid}`',
            inline=False
        )
        await ctx.send(embed=embed)
        await asyncio.sleep(1)

@bot.command(name="fulfill")
async def fulfill_order(ctx, *, args):
    await ctx.send("⚙️ Processing order...")
    try:
        pattern = r'(\w+)=([^\s]+)'
        matches = re.findall(pattern, args)
        parts = {k.strip(): v.strip().replace("_", " ") for k, v in matches}

        product_name = parts.get("product", "").replace("-", " ")
        quantity = int(parts.get("orders", "1"))
        vid = parts.get("vid", "")
        customer = {
            "name": parts.get("name", ""),
            "address": parts.get("address", ""),
            "city": parts.get("city", ""),
            "province": parts.get("province", ""),
            "zip": parts.get("zip", ""),
            "country": parts.get("country", "US"),
            "phone": parts.get("phone", "")
        }

        token = get_cj_token()
        if not token:
            await ctx.send("❌ Could not connect to CJ Dropshipping.")
            return

        if not vid:
            products = search_cj_product(product_name, token)
            if not products:
                await ctx.send(f"❌ No CJ product found for: {product_name}")
                return
            pid = products[0].get("pid", "")
            vid = get_product_vid(pid, token)

        if not vid:
            await ctx.send("❌ Could not find VID. Try !search first.")
            return

        result = create_cj_order(token, vid, quantity, customer)

        if result.get("result"):
            order_id = result["data"].get("orderId", "N/A")
            embed = discord.Embed(title="✅ ORDER PLACED SUCCESSFULLY", color=0x00ff88, timestamp=datetime.now())
            embed.add_field(name="Product", value=product_name, inline=False)
            embed.add_field(name="Quantity", value=quantity, inline=True)
            embed.add_field(name="Customer", value=customer["name"], inline=True)
            embed.add_field(name="Address", value=customer["address"], inline=False)
            embed.add_field(name="CJ Order ID", value=order_id, inline=True)
            embed.add_field(name="Status", value="📦 Supplier is processing your order", inline=False)
            embed.add_field(name="Track Order", value=f"`!track {order_id}`", inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Order failed: {result.get('message', 'Unknown error')}")

    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

@bot.command(name="track")
async def track_order(ctx, order_id: str):
    await ctx.send(f"🔍 Checking tracking for order: {order_id}")
    try:
        token = get_cj_token()
        if not token:
            await ctx.send("❌ Could not connect to CJ.")
            return

        result = get_order_tracking(order_id, token)

        if result.get("result") and result.get("data"):
            data = result["data"]
            status = data.get("orderStatus", "N/A")
            tracking_number = data.get("trackingNumber", "Not yet assigned")
            shipping = data.get("shippingName", "N/A")

            embed = discord.Embed(title="📦 ORDER TRACKING", color=0xffaa00, timestamp=datetime.now())
            embed.add_field(name="Order ID", value=order_id, inline=False)
            embed.add_field(name="Status", value=status, inline=True)
            embed.add_field(name="Shipping Method", value=shipping, inline=True)
            embed.add_field(name="Tracking Number", value=tracking_number, inline=False)
            if tracking_number and tracking_number != "Not yet assigned":
                embed.add_field(name="Track Package", value=f"https://t.17track.net/en#nums={tracking_number}", inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Could not get tracking info: {result.get('message', 'Unknown error')}")

    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# ========================
# TRENDING TASK
# ========================
@tasks.loop(hours=6)
async def send_trending_products():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return
    await channel.send("🔍 **Scanning for trending products...**")
    products = get_trending_products()
    for product in products[:3]:
        try:
            marketing = generate_marketing_content(product["name"])
            embed = discord.Embed(
                title=f"🔥 TRENDING: {product['name']}",
                color=0xff4500,
                timestamp=datetime.now()
            )
            embed.add_field(name="📊 Source", value=product["source"], inline=True)
            embed.add_field(name="💡 Why Trending", value=marketing.get("why_trending", "N/A"), inline=False)
            embed.add_field(name="💰 Suggested Price", value=marketing.get("suggested_price", "N/A"), inline=True)
            embed.add_field(name="📈 Profit Margin", value=marketing.get("profit_margin_estimate", "N/A"), inline=True)
            embed.add_field(name="🎵 TikTok Caption", value=marketing.get("tiktok_caption", "N/A"), inline=False)
            embed.add_field(name="🐦 Twitter Caption", value=marketing.get("twitter_caption", "N/A"), inline=False)
            hashtags = " ".join(marketing.get("hashtags", []))
            embed.add_field(name="📌 Hashtags", value=hashtags, inline=False)
            embed.add_field(name="🔍 Find Supplier", value=f"`!search {product['name']}`", inline=False)
            await channel.send(embed=embed)
            await asyncio.sleep(3)
        except Exception as e:
            await channel.send(f"⚠️ Error: {e}")

@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")
    send_trending_products.start()

bot.run(DISCORD_TOKEN)
