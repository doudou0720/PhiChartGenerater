import atexit
import shlex
import signal
import sys
import subprocess
import re
import os
import platform
import zipfile
import tarfile
import requests
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
class ADBController:
    def __init__(self, adb_path=None, max_workers=4, auto_disconnect=True):
        # 系统信息检测
        self.system = platform.system().lower()
        self.arch = platform.machine().lower()
        self.adb_home = str(Path.home() / ".adb_tool")
        self.platform_tools_path = os.path.join(self.adb_home, "platform-tools")
        self.max_workers = max_workers
        self.chunk_size = 1024 * 1024
        self.auto_disconnect = auto_disconnect
        self.connected_devices = set()
        self._custom_adb_path = None

        # 初始化流程
        self._register_exit_handlers()
        self.adb_path = adb_path or self._find_adb()
        self._setup_environment()
        self._verify_adb()
        
        
    def _register_exit_handlers(self):
        """注册退出处理函数"""
        atexit.register(self._cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """信号处理"""
        print(f"\n捕获到退出信号 {signum}, 正在清理资源...")
        self._cleanup()
        sys.exit(1)

    def _cleanup(self):
        """资源清理"""
        if self.auto_disconnect and self.connected_devices:
            print("\n正在断开所有ADB连接...")
            self.disconnect_all()

    def _setup_environment(self):
        """配置环境变量"""
        os.makedirs(self.adb_home, exist_ok=True)
        if self._custom_adb_path:
            custom_dir = os.path.dirname(self._custom_adb_path)
            os.environ["PATH"] = f"{custom_dir}{os.pathsep}{os.environ['PATH']}"
        if self.platform_tools_path not in os.environ["PATH"]:
            os.environ["PATH"] = f"{self.platform_tools_path}{os.pathsep}{os.environ['PATH']}"

    def _is_arm_platform(self):
        return self.system == "linux" and self.arch in ("armv7l", "aarch64")
    
    def _download_adb(self):
        if self._is_arm_platform():
            return self._download_arm_adb()
        else:
            return self._download_standard_adb()


    def _download_arm_adb(self):
        """从源码编译ARM版ADB"""
        print("开始从源码编译ADB...")
        build_dir = os.path.join(self.adb_home, "android-src")
        
        try:
            # 创建编译目录
            os.makedirs(build_dir, exist_ok=True)
            
            # 安装编译依赖
            self._install_build_deps()
            
            # 克隆源码
            self._clone_source(build_dir)
            
            # 执行编译
            self._build_adb(build_dir)
            
            # 安装到目标位置
            return self._install_adb(build_dir)
            
        except Exception as e:
            raise RuntimeError(f"编译失败: {str(e)}")
        finally:
            # 清理源码目录
            self._cleanup_temp(build_dir)

    def _install_build_deps(self):
        """安装现代化编译依赖"""
        print("安装编译依赖...")
        deps = [
            "git", "make", "gcc", "g++",
            "python3", "python3-pip",  # 使用Python 3
            "pkg-config", "libssl-dev",
            "libusb-1.0-0-dev"
        ]
        
        try:
            subprocess.run(
                ["sudo", "apt", "install", "-y"] + deps,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
            # 安装Python 3的必需模块
            subprocess.run(
                ["python3", "-m", "pip", "install", "future"],
                check=True
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"依赖安装失败: {e.stderr.decode()}")

    def _clone_source(self, build_dir):
        """克隆更新版源码仓库"""
        print("克隆新版platform-tools仓库...")
        # 使用官方支持Python 3的分支
        repo_url = "https://android.googlesource.com/platform/system/core"
        branch = "android11-release"  # 已支持Python 3的分支
        
        try:
            subprocess.run(
                ["git", "clone", "-b", branch, "--depth=1", repo_url, build_dir],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
            # 应用Python 3兼容补丁
            self._apply_python3_patches(build_dir)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"克隆失败: {e.stderr.decode()}")
    def _apply_python3_patches(self, build_dir):
        """自动应用Python 3兼容性修改"""
        print("应用Python 3兼容补丁...")
        try:
            # 修改所有Python脚本的shebang
            subprocess.run(
                f"find {build_dir} -name '*.py' -exec sed -i '1s/python/python3/' {{}} \;",
                shell=True,
                check=True
            )
            
            # 修改构建系统的Python版本检测
            makefile_path = os.path.join(build_dir, "adb", "Makefile")
            with open(makefile_path, "r") as f:
                content = f.read()
            
            # 将python2检测改为python3
            content = content.replace("python --version", "python3 --version")
            content = content.replace("PYTHON := python", "PYTHON := python3")
            
            with open(makefile_path, "w") as f:
                f.write(content)
        except Exception as e:
            raise RuntimeError(f"补丁应用失败: {str(e)}")

    def _build_adb(self, build_dir):
        """执行编译"""
        print("正在编译ADB...")
        env = os.environ.copy()
        env["ALLOW_MISSING_DEPENDENCIES"] = "true"
        
        try:
            # 配置编译环境
            subprocess.run(
                ["make", "clean"],
                cwd=os.path.join(build_dir, "adb"),
                check=True
            )
            
            # 执行编译
            subprocess.run(
                ["make", "-j4", "adb"],
                cwd=os.path.join(build_dir, "adb"),
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"编译错误: {e.stderr.decode()}")

    def _install_adb(self, build_dir):
        """安装ADB"""
        print("安装编译成果...")
        adb_src = os.path.join(build_dir, "adb", "adb")
        adb_dest = os.path.join(self.adb_home, "adb")
        
        try:
            # 复制可执行文件
            subprocess.run(
                ["cp", adb_src, adb_dest],
                check=True
            )
            
            # 设置权限
            os.chmod(adb_dest, 0o755)
            
            # 验证版本
            version = subprocess.check_output(
                [adb_dest, "version"],
                stderr=subprocess.STDOUT
            ).decode()
            
            if "Android Debug Bridge" not in version:
                raise RuntimeError("编译成果验证失败")
            
            self._custom_adb_path = adb_dest
            print("ADB编译安装成功")
            return True
        except Exception as e:
            raise RuntimeError(f"安装失败: {str(e)}")

    def _find_adb(self):
        if self._custom_adb_path and os.path.exists(self._custom_adb_path):
            return self._custom_adb_path
        
        exec_name = "adb.exe" if self.system == "windows" else "adb"
        search_paths = [
            os.path.join(self.platform_tools_path, exec_name),
            os.path.join(self.adb_home, exec_name),
            "/usr/bin/adb",
            "/usr/local/bin/adb"
        ]
        
        for path in search_paths:
            if os.path.exists(path):
                return path
        
        try:
            which_cmd = "where" if self.system == "windows" else "which"
            return subprocess.check_output([which_cmd, "adb"],
                                          stderr=subprocess.DEVNULL).decode().strip()
        except:
            return None

    def _verify_adb(self):
        max_retries = 2
        for attempt in range(max_retries):
            try:
                if self._is_arm_platform():
                    self._check_arm_dependencies()
                
                test_cmd = [self.adb_path, "version"] if self.adb_path else ["adb", "version"]
                subprocess.run(test_cmd, check=True,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"ADB验证失败: {str(e)}")
                if self._download_adb():
                    self.adb_path = self._find_adb()


    def _check_arm_dependencies(self):
        """更新依赖检查"""
        required = [
            "gcc", "g++", "make", "git",
            "python3", "python3-pip"  # 检查Python 3
        ]
        missing = []
        
        for dep in required:
            try:
                subprocess.run(
                    ["which", dep.split()[0]],  # 处理带版本号的包名
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except:
                missing.append(dep)
        
        if missing:
            raise RuntimeError(
                "缺少必要依赖:\n请执行: sudo apt install " + 
                " ".join(missing) + "\n" +
                "然后重新运行程序"
            )
    def _download_standard_adb(self):
        base_url = "https://dl.google.com/android/repository/platform-tools-latest-"
        ext = ".zip"
        url = f"{base_url}{self.system}{ext}"

        try:
            print(f"正在下载ADB工具包 ({self.system})...")
            with requests.head(url, allow_redirects=True) as resp:
                total_size = int(resp.headers.get('content-length', 0))

            temp_dir = os.path.join(self.adb_home, "temp")
            os.makedirs(temp_dir, exist_ok=True)

            ranges = [(i * (total_size // self.max_workers), 
                     (i + 1) * (total_size // self.max_workers) - 1 if i < self.max_workers - 1 else total_size - 1)
                    for i in range(self.max_workers)]

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [executor.submit(self._download_chunk, url, temp_dir, i, start, end)
                          for i, (start, end) in enumerate(ranges)]

                downloaded = 0
                with tqdm(total=total_size, unit='B', unit_scale=True, desc="下载进度") as pbar:
                    for future in as_completed(futures):
                        part_size = os.path.getsize(os.path.join(temp_dir, f"part_{future.result()}"))
                        downloaded += part_size
                        pbar.update(part_size)

            download_path = self._merge_files(temp_dir, total_size)
            self._universal_extract(download_path, self.adb_home)
            self._cleanup_temp(temp_dir)
            os.remove(download_path)
            print("ADB安装完成")
            return True
        except Exception as e:
            self._cleanup_temp(temp_dir)
            raise RuntimeError(f"下载失败: {str(e)}")
    def _universal_extract(self, file_path, target_dir):
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == '.zip':
                with zipfile.ZipFile(file_path) as zf:
                    zf.extractall(target_dir)
            elif ext in ('.tar', '.gz', '.bz2', '.tgz'):
                with tarfile.open(file_path, 'r:*') as tf:
                    tf.extractall(target_dir)
            else:
                raise RuntimeError(f"不支持的压缩格式: {ext}")
        except (zipfile.BadZipFile, tarfile.TarError) as e:
            raise RuntimeError(f"文件损坏: {str(e)}")

    def _calculate_ranges(self, total_size):
        """计算下载分块"""
        chunk_size = total_size // self.max_workers
        return [(i * chunk_size, 
                (i * chunk_size + chunk_size - 1) if i < self.max_workers - 1 else total_size - 1)
                for i in range(self.max_workers)]

    def _download_chunk(self, url, temp_dir, chunk_num, start, end, retries=3):
        """下载单个分块"""
        temp_path = os.path.join(temp_dir, f"part_{chunk_num}")
        headers = {'Range': f'bytes={start}-{end}'}
        
        for attempt in range(retries):
            try:
                with requests.get(url, headers=headers, stream=True) as r:
                    r.raise_for_status()
                    with open(temp_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                return chunk_num
            except Exception as e:
                if attempt == retries - 1:
                    raise

    def _merge_files(self, temp_dir, total_size):
        """合并临时文件"""
        download_path = os.path.join(self.adb_home, "platform-tools.zip")
        parts = sorted([os.path.join(temp_dir, f) for f in os.listdir(temp_dir)],
                      key=lambda x: int(x.split('_')[-1]))

        with open(download_path, 'wb') as f:
            for part in parts:
                with open(part, 'rb') as p:
                    f.write(p.read())

        if os.path.getsize(download_path) != total_size:
            raise RuntimeError("文件校验失败")

        return download_path

    def _show_progress(self, futures, total_size):
        """显示下载进度"""
        downloaded = 0
        completed = 0
        while completed < len(futures):
            for future in as_completed(futures):
                if future.exception():
                    raise future.exception()
                completed += 1
                part_size = os.path.getsize(
                    os.path.join(self.adb_home, "temp", f"part_{future.result()}")
                )
                with self.download_lock:
                    downloaded += part_size
                progress = downloaded / total_size * 100
                sys.stdout.write(f"\r下载进度: {progress:.1f}% ({downloaded}/{total_size} bytes)")
                sys.stdout.flush()
        print()

    def _process_download(self, download_path):
        """处理下载文件"""
        print("解压文件中...")
        with zipfile.ZipFile(download_path) as zf:
            zf.extractall(self.adb_home)

        # 设置执行权限
        if self.system != "windows":
            adb_path = os.path.join(self.platform_tools_path, "adb")
            os.chmod(adb_path, 0o755)

        print("ADB安装完成")
        self._cleanup_temp(os.path.join(self.adb_home, "temp"))
        os.remove(download_path)

    def _cleanup_temp(self, temp_dir):
        """清理临时文件"""
        if os.path.exists(temp_dir):
            for f in os.listdir(temp_dir):
                os.remove(os.path.join(temp_dir, f))
            os.rmdir(temp_dir)

    def _fallback_download(self, url):
        """单线程下载回退"""
        print("服务器不支持分块下载，使用单线程模式")
        download_path = os.path.join(self.adb_home, "platform-tools.zip")
        
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(download_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        self._process_download(download_path)
        return True

    # ADB操作功能
    def get_devices(self):
        """增强版设备检测方法"""
        stdout, _ = self._execute_command(['devices', '-l'])
        devices = []
        
        for line in stdout.split('\n')[1:]:
            if not line.strip() or 'offline' in line.lower():
                continue

            # 调试输出原始信息
            print(f"[DEBUG] 原始设备信息: {line}")
            
            # 使用更精确的正则表达式
            match = re.match(
                r'^(\S+)\s+(\w+)(\s+.*transport_id:(\d+))?', 
                line
            )
            if not match:
                continue

            serial = match.group(1)
            status = match.group(2).lower()
            transport_id = match.group(4) or '0'

            # 连接类型判断逻辑
            connection_type = 'UNKNOWN'
            if 'usb' in line.lower():
                connection_type = 'USB'
            elif transport_id == '1':
                connection_type = 'USB'
            elif transport_id == '2':
                connection_type = 'WIFI'
            elif 'product:' in line.lower():
                connection_type = 'USB'  # 备用判断

            devices.append({
                'serial': serial,
                'status': status,
                'transport_id': transport_id,
                'connection': connection_type,
                'raw': line  # 保留原始信息用于调试
            })
        
        return devices

    def usb_connect(self):
        """增强版USB设备检测"""
        usb_devices = []
        for device in self.get_devices():
            # 多重验证条件
            condition_usb = any([
                device['connection'] == 'USB',
                device['transport_id'] == '1',
                'usb' in device['raw'].lower(),
                'product:' in device['raw'].lower()
            ])
            
            if condition_usb and device['status'] == 'device':
                usb_devices.append(device)
        
        return usb_devices

    def debug_connection(self):
        """连接调试诊断工具"""
        print("=== ADB连接诊断 ===")
        print(f"ADB路径: {self.adb_path}")
        print(f"ADB版本: {self.get_adb_version()}")
        
        print("\n当前设备列表:")
        for idx, dev in enumerate(self.get_devices(), 1):
            print(f"设备{idx}:")
            print(f"  序列号: {dev['serial']}")
            print(f"  状态: {dev['status']}")
            print(f"  传输ID: {dev['transport_id']}")
            print(f"  连接类型: {dev['connection']}")
            print(f"  原始信息: {dev['raw']}")
        
        print("\n建议操作:")
        if any(dev['connection'] == 'USB' for dev in self.get_devices()):
            print("1. 尝试重置ADB服务: adb kill-server && adb start-server")
        else:
            print("1. 检查USB连接线是否支持数据传输")
            print("2. 确认设备已开启USB调试模式")
            print("3. 尝试不同USB接口")

    def get_adb_version(self):
        """获取ADB版本信息"""
        stdout, _ = self._execute_command(['version'])
        return stdout.split('\n')[0].strip()

    def verify_usb_connection(self, timeout=120):
        """增强版USB连接验证"""
        print("请按以下步骤操作：")
        print("1. 使用原装数据线连接设备")
        print("2. 开启开发者选项和USB调试")
        print("3. 在设备上允许此计算机的调试请求")
        
        start_time = time.time()
        last_print = 0
        checked_devices = set()
        
        while time.time() - start_time < timeout:
            current_devices = self.get_devices()
            
            # 检测新设备
            for dev in current_devices:
                if dev['serial'] not in checked_devices:
                    print(f"检测到新设备: {dev['serial']} ({dev['connection']})")
                    checked_devices.add(dev['serial'])
                    
                    if dev['connection'] == 'USB' and dev['status'] == 'device':
                        print("USB设备已授权并准备就绪")
                        return True
                    elif dev['status'] == 'unauthorized':
                        print("设备未授权，请在设备上点击允许调试")
            
            # 状态提示
            if time.time() - last_print > 10:
                print("等待设备连接... (确保：)")
                print("- USB调试已开启,并且已经关闭无线调试")
                print("- 已选择文件传输模式")
                print("- 点击了设备上的授权对话框")
                last_print = time.time()
            
            # 尝试唤醒ADB服务
            if len(current_devices) == 0:
                self._execute_command(['kill-server'])
                self._execute_command(['start-server'])
            
            time.sleep(3)
        
        raise RuntimeError(f"USB连接超时（{timeout}秒）")

    def enable_tcpip(self, port=5555):
        """启用TCP/IP模式"""
        output, _ = self._execute_command(['tcpip', str(port)])
        if f"restarting in TCP mode port: {port}" in output:
            return f"TCP模式已启用，端口：{port}"
        raise RuntimeError("启用TCP模式失败")

    def wireless_connect(self, ip, port=5555):
        """无线连接设备"""
        target = f"{ip}:{port}"
        stdout, _ = self._execute_command(['connect', target])
        if 'connected' in stdout.lower():
            self._record_connection(target)
            return True
        return False

    def smart_connect(self, ip, port=5555, pair_port=None, pairing_code=None):
        """智能连接设备"""
        try:
            # 尝试直接连接
            if self.wireless_connect(ip, port):
                return True
            
            if not pair_port or not pairing_code:
                raise ValueError("需要配对信息")
            
            # 执行配对
            new_port = self.pair_device(ip, pair_port, pairing_code)
            return self.wireless_connect(ip, new_port or port)
        except RuntimeError as e:
            if "already connected" in str(e).lower():
                return True
            raise

    def pair_device(self, ip, pair_port, pairing_code):
        """配对设备"""
        try:
            stdout, _ = self._execute_command(
                ['pair', f"{ip}:{pair_port}"], 
                input_text=f"{pairing_code}\n"
            )
            
            # 解析新端口
            new_port = self._parse_pairing_output(stdout)
            if new_port:
                print(f"新连接端口: {new_port}")
                return new_port
                
            if 'successfully' in stdout.lower():
                print("配对成功，请手动连接")
                return None
                
            raise RuntimeError("配对失败")
        except RuntimeError as e:
            if 'incorrect pairing code' in str(e).lower():
                raise ValueError("配对码错误") from e
            raise

    def _parse_pairing_output(self, output):
        """解析配对输出"""
        pattern = r"connect\s+([\d.]+:\d+)"
        match = re.search(pattern, output)
        return match.group(1).split(':')[1] if match else None

    def disconnect(self, target):
        """断开指定连接"""
        self._execute_command(['disconnect', target], record=False)
        self._remove_connection(target)
        return f"已断开：{target}"

    def disconnect_all(self):
        """断开所有连接"""
        while self.connected_devices:
            target = self.connected_devices.pop()
            try:
                self._execute_command(['disconnect', target], record=False)
                print(f"已断开: {target}")
            except Exception as e:
                print(f"断开失败: {target} - {str(e)}")

    def execute_shell(self, command, serial=None):
        """执行Shell命令"""
        args = ['-s', serial, 'shell'] if serial else ['shell']
        return self._execute_command(args + [command])[0]

    def execute_raw(self, command_str):
        """
        直接执行原始ADB命令字符串
        示例：
            execute_raw("adb devices -l")
            execute_raw("devices -l")  # 自动补全adb前缀
            execute_raw("-s emulator-5554 shell pm list packages")
        """
        # 移除命令中的adb前缀并拆分参数
        cleaned_cmd = command_str.replace('adb', '', 1).strip()
        args = shlex.split(cleaned_cmd)
        
        try:
            # 调用已有的执行方法
            stdout, stderr = self._execute_command(args, record=False)
            return {
                'success': True,
                'stdout': stdout,
                'stderr': stderr,
                'command': f"adb {' '.join(args)}"
            }
        except RuntimeError as e:
            return {
                'success': False,
                'error': str(e),
                'command': f"adb {' '.join(args)}"
            }

    # 修改原有的_execute_command方法
    def _execute_command(self, args, input_text=None, record=True):
        """执行ADB命令（增加参数过滤）"""
        # 过滤无效参数
        valid_args = [arg for arg in args if arg.strip()]
        
        try:
            proc = subprocess.run(
                [self.adb_path] + valid_args,
                input=input_text,
                text=True,
                capture_output=True,
                check=True
            )
            output = proc.stdout.strip()
            
            # 自动记录连接命令
            if record and valid_args[0] == 'connect' and 'connected' in output.lower():
                target = valid_args[1]
                self._record_connection(target)
                
            return output, proc.stderr.strip()
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip()
            if 'disconnect' in valid_args and 'not connected' in error_msg.lower():
                self._remove_connection(valid_args[1])
            raise RuntimeError(f"ADB命令失败: {error_msg}") from e


    def _record_connection(self, target):
        """记录新连接"""
        if self.auto_disconnect:
            self.connected_devices.add(target)

    def _remove_connection(self, target):
        """移除连接记录"""
        self.connected_devices.discard(target)

if __name__ == "__main__":
    try:
        adb = ADBController()
        print(f"ADB路径: {adb.adb_path}")
        
        # 示例操作
        print("设备列表:", adb.get_devices())
        adb.push("localfile.txt", "/sdcard/remotefile.txt")
        adb.pull("/sdcard/remotefile.txt", "downloaded.txt")
        
    except Exception as e:
        print(f"错误: {str(e)}")
        if "libc6" in str(e):
            print("解决方案: sudo apt install libc6 libstdc++6")