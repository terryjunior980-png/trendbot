import discord
from discord.ext import commands, tasks
import requests
from groq import Groq
import json
import asyncio
from datetime import datetime
import os
import re
import threading
from flask import Flask, request, jsonify

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
CJ_API_KEY = os.environ.get("CJ_API_KEY")
CHANNEL_ID = 1509172843265396903
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
FLUTTERWAVE_SECRET = os.environ.get("FLUTTERWAVE_SECRET", "")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
client_ai = Groq(api_key=GROQ_API_KEY)
app = Flask(__name__)

# ========================
# FLUTTERWAVE WEBHOOK
# ========================
@app.route("/webhook", methods=["POST"])
def flutterwave_webhook():
    data = request.json
    try:
        if data.get("event") == "charge.completed" and data.get("data", {}).get("status") == "successful":
            payment = data["data"]
            customer = payment.get("customer", {})
            meta = payment.get("meta", {})
            name = customer.get("name", "Customer")
            email = customer.get("email", "")
            phone = customer.get("phone_number", "")
            amount = payment.get("amount", 0)
            product = meta.get("product", "Unknown Product")
            address = meta.get("address", "")
            city = meta.get("city", "")
            province = meta.get("province", "")
            zip_code = meta.get("zip", "")
            country = meta.get("country", "NG")
            if DISCORD_WEBHOOK:
                message = {
                    "content": f"💰 **PAYMENT RECEIVED**\n**Product:** {product}\n**Amount:** ${amount}\n**Customer:** {name}\n**Email:** {email}\n**Phone:** {phone}\n**Address:** {address}, {city}, {province}, {zip_code}, {country}\n\n⚙️ Auto fulfilling order now..."
                }
                requests.post(DISCORD_WEBHOOK, json=message)
            asyncio.run_coroutine_threadsafe(
                auto_fulfill(product, name, address, city, province, zip_code, country, phone),
                bot.loop
            )
    except Exception as e:
        print(f"Webhook error: {e}")
    return jsonify({"status": "ok"}), 200

@app.route("/", methods=["GET"])
def home():
    return "TrendBot is running 24/7!", 200

# ========================
# AUTO FULFILL
# ========================
async def auto_fulfill(product_name, name, address, city, province, zip_code, country, phone):
    channel = bot.get_channel(CHANNEL_ID)
    try:
        token = get_cj_token()
        if not token:
            if channel:
                await channel.send("❌ Auto fulfill failed: Could not connect to CJ.")
            return
        products = search_cj_product(product_name, token)
        if not products:
            if channel:
                await channel.send(f"❌ Auto fulfill failed: No CJ product found for {product_name}")
            return
        pid = products[0].get("pid", "")
        vid = get_product_vid(pid, token)
        if not vid:
            if channel:
                await channel.send(f"❌ Auto fulfill failed: No VID found for {product_name}")
            return
        customer = {
            "name": name,
            "address": address,
            "city": city,
            "province": province,
            "zip": zip_code,
            "country": country,
            "phone": phone
        }
        result = create_cj_order(token, vid, 1, customer)
        if result.get("result"):
            order_id = result["data"].get("orderId", "N/A")
            if channel:
                embed = discord.Embed(title="✅ AUTO ORDER PLACED", color=0x00ff88, timestamp=datetime.now())
                embed.add_field(name="Product", value=product_name, inline=False)
                embed.add_field(name="Customer", value=name, inline=True)
                embed.add_field(name="CJ Order ID", value=order_id, inline=True)
                embed.add_field(name="Status", value="📦 Supplier is processing", inline=False)
                embed.add_field(name="Track", value=f"`!track {order_id}`", inline=False)
                await channel.send(embed=embed)
        else:
            if channel:
                await channel.send(f"❌ Auto fulfill failed: {result.get('message', 'Unknown error')}")
    except Exception as e:
        if channel:
            await channel.send(f"❌ Auto fulfill error: {e}")

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

def get_trending_products():
    try:
        token = get_cj_token()
        if not token:
            raise Exception("No token")
        url = "https://developers.cjdropshipping.com/api2.0/v1/product/list"
        headers = {"CJ-Access-Token": token}
        params = {"pageNum": 1, "pageSize": 10, "orderBy": "hotSale"}
        res = requests.get(url, headers=headers, params=params, timeout=10)
        data = res.json()
        products = []
        if data.get("result") and data.get("data"):
            for item in data["data"].get("list", []):
                pid = item.get("pid", "")
                name = item.get("productNameEn", "")
                image = item.get("productImage", "")
                price = item.get("sellPrice", "")
                if name:
                    products.append({
                        "name": name[:60],
                        "source": "CJ Hot Sale",
                        "image": image,
                        "price": price,
                        "pid": pid
                    })
        if products:
            return products[:10]
    except Exception as e:
        print(f"CJ trending error: {e}")
    return [
        {"name": "LED Strip Lights", "source": "Trending", "image": "https://images.unsplash.com/photo-1586771107445-d3ca888129ff?w=400", "price": "8.99"},
        {"name": "Portable Blender", "source": "Trending", "image": "https://images.unsplash.com/photo-1502743780242-f10c78f797c7?w=400", "price": "12.99"},
        {"name": "Wireless Earbuds", "source": "Trending", "image": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400", "price": "15.99"},
        {"name": "Phone Ring Holder", "source": "Trending", "image": "https://images.unsplash.com/photo-1601784551446-20c9e07cdbdb?w=400", "price": "3.99"},
        {"name": "Mini Projector", "source": "Trending", "image": "https://images.unsplash.com/photo-1478720568477-152d9b164e26?w=400", "price": "35.99"},
        {"name": "Posture Corrector", "source": "Trending", "image": "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=400", "price": "9.99"},
        {"name": "Electric Massage Gun", "source": "Trending", "image": "https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=400", "price": "25.99"},
        {"name": "Smart Watch", "source": "Trending", "image": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400", "price": "22.99"},
        {"name": "Car Phone Mount", "source": "Trending", "image": "https://images.unsplash.com/photo-1601784551446-20c9e07cdbdb?w=400", "price": "5.99"},
        {"name": "Resistance Bands", "source": "Trending", "image": "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=400", "price": "7.99"},
    ]

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
  "profit_margin_estimate": "...",
  "pika_prompt": "cinematic product video of {product_name} in action showing its benefits lifestyle setting satisfying modern aesthetic trending on social media",
  "kling_prompt": "realistic product showcase of {product_name} close up shots natural lighting people using it happily lifestyle setting high quality"
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

def update_store_page(products):
    cards = ""
    for p in products[:10]:
        name = p["name"]
        image = p.get("image", "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400")
        raw = str(p.get("price", "10")).split("--")[0].strip()
        cost = float(raw) if raw.replace('.','').isdigit() else 10.0
        sell_price = round(cost * 2.5, 2)
        cards += f"""
  <div class="card">
    <img src="{image}" onerror="this.src='https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400'" alt="{name}">
    <div class="card-body">
      <h3>{name}</h3>
      <div class="price">${sell_price}</div>
      <button class="btn" onclick="openOrder('{name}', '${sell_price}')">🛒 Buy Now</button>
    </div>
  </div>
"""
    try:
        with open("index.html", "r") as f:
            html = f.read()
        start = html.find('<div class="products" id="products">') + len('<div class="products" id="products">')
        end = html.find('<div class="how">')
        new_html = html[:start] + cards + html[end:]
        with open("index.html", "w") as f:
            f.write(new_html)
        os.system('git config --global user.email "trendbot@render.com" && git config --global user.name "TrendBot" && git add index.html && git commit -m "update store products" && git push')
        print("Store updated with new products")
    except Exception as e:
        print(f"Store update error: {e}")

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
            await ctx.send(f"❌ Could not get tracking: {result.get('message', 'Unknown error')}")
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
    update_store_page(products)
    for product in products[:5]:
        try:
            marketing = generate_marketing_content(product["name"])
            embed = discord.Embed(
                title=f"🔥 TRENDING: {product['name']}",
                color=0xff4500,
                timestamp=datetime.now()
            )
            embed.set_thumbnail(url=product.get("image", ""))
            embed.add_field(name="📊 Source", value=product["source"], inline=True)
            embed.add_field(name="💡 Why Trending", value=marketing.get("why_trending", "N/A"), inline=False)
            embed.add_field(name="💰 Suggested Price", value=marketing.get("suggested_price", "N/A"), inline=True)
            embed.add_field(name="📈 Profit Margin", value=marketing.get("profit_margin_estimate", "N/A"), inline=True)
            embed.add_field(name="🎵 TikTok Caption", value=marketing.get("tiktok_caption", "N/A"), inline=False)
            embed.add_field(name="🐦 Twitter Caption", value=marketing.get("twitter_caption", "N/A"), inline=False)
            hashtags = " ".join(marketing.get("hashtags", []))
            embed.add_field(name="📌 Hashtags", value=hashtags, inline=False)
            embed.add_field(name="🎬 Pika.art Video Prompt", value=marketing.get("pika_prompt", "N/A"), inline=False)
            embed.add_field(name="🎥 Kling AI Video Prompt", value=marketing.get("kling_prompt", "N/A"), inline=False)
            embed.add_field(name="🔍 Find Supplier", value=f"`!search {product['name']}`", inline=False)
            await channel.send(embed=embed)
            await asyncio.sleep(3)
        except Exception as e:
            await channel.send(f"⚠️ Error: {e}")

# ========================
# START
# ========================
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("✅ Webhook server running")
    send_trending_products.start()

bot.run(DISCORD_TOKEN)
