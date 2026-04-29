from PIL import Image

# 读取原始 Logo
logo_path = r"C:\Users\duola\WorkBuddy\Claw\_integrations\wenzhou_water\logo_wenzhou.png"
img = Image.open(logo_path)
print(f"原始尺寸: {img.size}, 模式: {img.mode}")

# 创建一个 512x512 的透明背景
output_size = 512
bg = Image.new('RGBA', (output_size, output_size), (0, 0, 0, 0))

# 计算放置位置（居中，保持宽高比）
logo_w, logo_h = img.size
max_logo_size = 400
scale = min(max_logo_size / logo_w, max_logo_size / logo_h)
new_w = int(logo_w * scale)
new_h = int(logo_h * scale)

# 缩放 Logo
resized = img.resize((new_w, new_h), Image.LANCZOS)
if resized.mode != 'RGBA':
    resized = resized.convert('RGBA')

# 居中放置
x = (output_size - new_w) // 2
y = (output_size - new_h) // 2
bg.paste(resized, (x, y), resized)

# 保存
output_path = r"C:\Users\duola\WorkBuddy\Claw\_integrations\wenzhou_water\icon.png"
bg.save(output_path, 'PNG')
print(f"已保存: {output_path}")

# 同时生成 192x192 的版本
icon_192 = bg.resize((192, 192), Image.LANCZOS)
icon_192.save(r"C:\Users\duola\WorkBuddy\Claw\_integrations\wenzhou_water\icon_192.png", 'PNG')
print("已保存 192x192 版本")
