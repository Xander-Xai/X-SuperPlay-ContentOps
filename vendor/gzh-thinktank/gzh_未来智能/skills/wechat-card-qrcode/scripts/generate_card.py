import argparse
import qrcode
from PIL import Image, ImageDraw

def make_card(name, slogan, url, output_path):
    qr = qrcode.QRCode(version=1, box_size=5, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#1a202c", back_color="#ffffff").convert("RGBA")

    card = Image.new("RGBA", (600, 200), "#f8fafc")
    draw = ImageDraw.Draw(card)
    draw.rectangle([0, 0, 599, 199], outline="#cbd5e0", width=2)
    card.paste(qr_img, (20, 25))

    draw.text((180, 50), f"微信公众号: {name}", fill="#1a202c")
    draw.text((180, 90), f"Slogan: {slogan}", fill="#4a5568")
    draw.text((180, 130), "👉 扫码关注，获取最新 AI SOP", fill="#3182ce")

    card.save(output_path)
    print(f"[WeChat Matrix Pipeline] Generated brand card: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="WeChat Card Generator")
    parser.add_argument("--name", default="AI哨兵", help="Account Name")
    parser.add_argument("--slogan", default="每日 30 秒，解锁 AI 落地新玩法", help="Account Slogan")
    parser.add_argument("--url", default="https://weixin.qq.com", help="QR Code Target URL")
    parser.add_argument("--output", default="brand_card.png", help="Output PNG file")
    args = parser.parse_args()
    make_card(args.name, args.slogan, args.url, args.output)

if __name__ == "__main__":
    main()
