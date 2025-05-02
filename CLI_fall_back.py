import os
import sys
import time
import platform
from colorama import Fore, Back, Style, init

# --------------- 初始化跨平台环境 ---------------
init()  # 初始化 colorama

# --------------- 跨平台键盘输入处理 ---------------
if platform.system() == 'Windows':
    import msvcrt
else:
    import tty
    import termios

def get_key():
    """跨平台获取按键输入（支持方向键检测）"""
    if platform.system() == 'Windows':
        # Windows 实现
        key = msvcrt.getch().decode('utf-8', 'ignore')
        if key == '\x00' or key == '\xe0':  # 处理功能键
            key += msvcrt.getch().decode('utf-8', 'ignore')
        return key
    else:
        # Unix/Linux 实现
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
            if ch == '\x1b':  # 处理转义序列
                ch += sys.stdin.read(2)
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

# --------------- 其他代码保持不变 ---------------
def cls():
    """清屏函数"""
    os.system('cls' if platform.system() == 'Windows' else 'clear')

class SclectBox:
    def __init__(self, header: str, footer: str, choices, multi: bool = False):
        self.header = header
        self.footer = footer
        self.choices = choices
        self.multi = multi
        self.selected = []
        self.cursor_pos = 0

    def _display(self):
        """显示选择界面"""
        cls()
        print(f"{Fore.CYAN}{self.header}{Style.RESET_ALL}\n")
        
        for idx, (text, _, _) in enumerate(self.choices):
            prefix = "  "
            if idx == self.cursor_pos:
                prefix = f"{Fore.GREEN}> {Style.RESET_ALL}"
            status = f"{Fore.YELLOW}[✓] " if idx in self.selected else "    "
            print(f"{prefix}{status}{text} {Style.RESET_ALL}")
        
        print(f"\n{Fore.LIGHTBLACK_EX}{self.footer}{Style.RESET_ALL}")
        if self.multi:
            print(f"{Fore.YELLOW}已选 {len(self.selected)} 项{Style.RESET_ALL}")

    def start(self):
        """启动选择交互"""
        while True:
            self._display()
            key = get_key()
            
            # 统一处理按键映射
            if platform.system() == 'Windows':
                if key in ('\xe0H', '\x00H'):   # 上箭头
                    self.cursor_pos = max(0, self.cursor_pos - 1)
                elif key in ('\xe0P', '\x00P'): # 下箭头
                    self.cursor_pos = min(len(self.choices)-1, self.cursor_pos + 1)
            else:
                if key == '\x1b[A':  # 上箭头
                    self.cursor_pos = max(0, self.cursor_pos - 1)
                elif key == '\x1b[B':  # 下箭头
                    self.cursor_pos = min(len(self.choices)-1, self.cursor_pos + 1)
            
            if key == ' ':       # 空格多选
                if self.multi:
                    if self.cursor_pos in self.selected:
                        self.selected.remove(self.cursor_pos)
                    else:
                        self.selected.append(self.cursor_pos)
            elif key in ('\r', '\n'):  # 回车确认
                break

        return [self.choices[i] for i in self.selected] if self.multi else self.choices[self.cursor_pos]

# --------------- 文件选择框（完整跨平台实现）---------------
class FileOpenBox:
    def __init__(self, path: str, multi: bool = False):
        """
        文件选择框类
        
        参数:
            path: 初始路径
            multi: 是否允许多选
        """
        self.root_path = os.path.abspath(path)
        self.current_path = self.root_path
        self.multi = multi
        self.selected = set()
        self.history = []
        self.last_error = None

    def _clear_screen(self):
        """清屏函数"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def _get_parent_path(self):
        """安全获取上级目录"""
        if self.current_path == "/":
            return None
        
        parent = os.path.dirname(self.current_path)
        
        # 防止某些系统返回空字符串
        if not parent:
            return "/"
            
        # 防止无限循环（如 /home 的上级还是 /home）
        if parent == self.current_path:
            return None
            
        return parent

    def _get_entries(self):
        """获取当前目录条目"""
        entries = []
        self.last_error = None
        
        try:
            # 添加返回上级选项
            parent = self._get_parent_path()
            if parent is not None:
                entries.append(("[返回上级]", False, parent))

            # 添加正常目录内容
            for name in sorted(os.listdir(self.current_path)):
                if name.startswith('.'):  # 跳过隐藏文件
                    continue
                    
                full_path = os.path.join(self.current_path, name)
                try:
                    is_file = os.path.isfile(full_path)
                    entries.append((name, is_file, full_path))
                except PermissionError:
                    continue
                    
        except Exception as e:
            self.last_error = str(e)
            
        return entries

    def _display(self, entries):
        """显示目录界面"""
        self._clear_screen()
        
        # 显示当前路径
        print(f"{Fore.CYAN}当前路径: {self.current_path}{Style.RESET_ALL}\n")
        
        # 显示错误信息（如果有）
        if self.last_error:
            print(f"{Fore.RED}错误: {self.last_error}{Style.RESET_ALL}\n")
        
        # 显示导航提示
        if entries and entries[0][0] == "[返回上级]":
            print(f"{Fore.YELLOW}输入 0 返回上级目录{Style.RESET_ALL}\n")
        
        # 显示文件/目录列表
        for idx, (name, is_file, path) in enumerate(entries, 1):
            # 标记已选项
            prefix = f"{Fore.GREEN}[✓] " if path in self.selected else "    "
            
            # 目录显示为蓝色
            color = Fore.BLUE if not is_file else ""
            
            print(f"{idx:2d}. {prefix}{color}{name}{Style.RESET_ALL}")
        
        # 显示多选状态
        if self.multi and self.selected:
            print(f"\n{Fore.YELLOW}已选 {len(self.selected)} 项:{Style.RESET_ALL}")
            for path in list(self.selected)[:3]:
                print(f"  - {os.path.basename(path)}")
            if len(self.selected) > 3:
                print(f"  ...（共{len(self.selected)}项）")

    def start(self):
        """启动文件选择交互"""
        while True:
            entries = self._get_entries()
            self._display(entries)
            
            try:
                choice = input("\n输入编号选择（回车确认/0返回）: ").strip()
                
                # 处理回车确认
                if not choice:
                    break
                
                # 处理返回上级
                if choice == '0':
                    parent = self._get_parent_path()
                    if parent:
                        self.history.append(self.current_path)
                        self.current_path = parent
                        continue
                    else:
                        print(f"{Fore.YELLOW}已到达最顶层目录{Style.RESET_ALL}")
                        time.sleep(1)
                        continue
                
                # 处理正常选择
                num = int(choice)
                if 1 <= num <= len(entries):
                    _, is_file, path = entries[num-1]
                    
                    if is_file:  # 文件处理
                        if self.multi:
                            if path in self.selected:
                                self.selected.remove(path)
                            else:
                                self.selected.add(path)
                        else:
                            return path  # 单选模式直接返回
                    else:        # 目录处理
                        self.history.append(self.current_path)
                        self.current_path = path
                else:
                    print(f"{Fore.RED}无效编号! 请输入0-{len(entries)}{Style.RESET_ALL}")
                    time.sleep(1)
                    
            except ValueError:
                print(f"{Fore.RED}请输入有效数字!{Style.RESET_ALL}")
                time.sleep(1)

        # 返回最终结果
        if self.multi:
            return list(self.selected)
        return None

# --------------- 使用示例 ---------------
if __name__ == "__main__":
    # 测试文件选择器
    selector = FileOpenBox(os.getcwd(), multi=True)
    result = selector.start()
    print(f"\n选中文件: {result}")