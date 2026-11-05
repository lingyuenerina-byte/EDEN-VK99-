import struct, os
from PIL import Image

SRC = r'C:\Users\Lingy\Downloads\粉发少女与天际线的胶片时光.png'
dst_dir = r'C:\Users\Lingy\vk99screen\eden-tauri\src-tauri\icons'

im = Image.open(SRC)
print('size', im.size, 'mode', im.mode)
im = im.convert('RGBA')
w, h = im.size
if w != h:
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))

# 1024 主图 (立绘全幅, Tauri 图标标准做法是方图直出)
main = im.resize((1024, 1024), Image.LANCZOS)
main.save(os.path.join(dst_dir, 'icon.png'))

# 存档源图到项目里 (系列资产留底, 同 NBTMix 的 app-icon-source)
main.save(r'C:\Users\Lingy\vk99screen\eden-tauri\app-icon-幻映-source.png')

# 多尺寸 ico
sizes = [16, 24, 32, 48, 64, 128, 256]
imgs = [main.resize((s, s), Image.LANCZOS) for s in sizes]
imgs[0].save(os.path.join(dst_dir, 'icon.ico'), format='ICO',
             sizes=[(s, s) for s in sizes], append_images=imgs[1:])
print('ICON OK')

# Windows 任务栏/窗口用 png, 顺手预览
main.resize((512, 512), Image.LANCZOS).save(r'C:\Users\Lingy\vk99screen\eden-tauri\tools_preview512.png')
print('DONE')
