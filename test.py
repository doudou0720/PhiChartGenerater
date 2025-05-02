from pynput import keyboard

def on_press(key):
    try:
        print(f'字符键 {key.char} 被按下')
    except AttributeError:
        print(f'特殊键 {key} 被按下')

def on_release(key):
    print(f'{key} 释放')
    if key == keyboard.Key.esc:
        # 停止监听
        return False

# 监听按键事件
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()