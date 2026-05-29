import requests
from bs4 import BeautifulSoup

def get_trending_products():
    products = []

    # Source 1: AliExpress Best Sellers
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        url = "https://www.aliexpress.com/category/201000054/consumer-electronics.html"
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        titles = soup.find_all("h3", limit=5)
        for t in titles:
            if t.text.strip():
                products.append({"name": t.text.strip()[:60], "source": "AliExpress"})
    except Exception as e:
        print(f"AliExpress error: {e}")

    # Fallback hardcoded trending products if scraping fails
    if len(products) < 3:
        fallback = [
            "Wireless Earbuds",
            "LED Strip Lights",
            "Portable Blender",
            "Phone Ring Holder",
            "Mini Projector",
            "Posture Corrector",
            "Electric Massage Gun",
            "Smart Watch",
            "Car Phone Mount",
            "Resistance Bands"
        ]
        for p in fallback:
            if len(products) < 5:
                products.append({"name": p, "source": "Trending"})

    return products[:5]
