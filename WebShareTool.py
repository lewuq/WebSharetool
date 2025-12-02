import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import os
import sys
import signal
import platform
import ctypes
import stat  # 【关键修复】必须导入这个库，否则 Mac/Linux 无法修改权限

# ================= 配置区域 =================
THEME_COLOR = "#8FC31F" # Seeed 品牌绿
BTN_START_TEXT = "🚀 立即生成分享链接"
BTN_STOP_TEXT = "🛑 停止分享 (点击断开)"
WINDOW_TITLE = "WebShareTool V2.0"

class SeeedShareTool:
    def __init__(self, root):
        self.root = root
        self.root.title(WINDOW_TITLE)
        
        # 设置初始大小
        self.root.geometry("520x450") 
        self.root.minsize(520, 420)
        self.root.resizable(True, True)
        
        self.root.configure(bg="white")

        # 变量初始化
        self.process = None
        self.timer = None
        self.is_running = False
        self.system_os = platform.system() 

        # 针对 Windows 的高分屏模糊修复
        if self.system_os == "Windows":
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except:
                pass

        self.setup_ui()

    def setup_ui(self):
        # 字体定义
        group_font = ("Microsoft YaHei UI", 10) if self.system_os == "Windows" else ("Segoe UI", 10)
        ui_font = ("Microsoft YaHei UI", 11) if self.system_os == "Windows" else ("Segoe UI", 11)
        hint_font = ("Microsoft YaHei UI", 9) if self.system_os == "Windows" else ("Segoe UI", 9)
        btn_font = ("Microsoft YaHei UI", 12, "bold") if self.system_os == "Windows" else ("Segoe UI", 12, "bold")

        # --- 1. 顶部标题栏 ---
        header_frame = tk.Frame(self.root, bg=THEME_COLOR, height=60)
        header_frame.pack(fill="x", side="top")
        header_frame.pack_propagate(False)

        title_font = ("Microsoft YaHei UI", 18, "bold") if self.system_os == "Windows" else ("Segoe UI", 20, "bold")
        tk.Label(header_frame, text="SeeedShareTool", bg=THEME_COLOR, fg="white",
                 font=title_font).pack(side="left", padx=25, pady=10)

        # --- 2. 状态栏 ---
        self.status_lbl = tk.Label(self.root, text="准备就绪。", bg="white", fg="#999999", font=hint_font, anchor="w")
        self.status_lbl.pack(side="bottom", fill="x", padx=25, pady=10)

        # --- 3. 主内容容器 ---
        main_content = tk.Frame(self.root, bg="white")
        main_content.pack(fill="both", expand=True, padx=25, pady=10)

        # --- 4. 配置区域 ---
        config_frame = tk.LabelFrame(main_content, text=" 配置 ", bg="white", fg="#666666",
                                     font=group_font, bd=1, relief="solid")
        config_frame.pack(fill="x", pady=10, expand=True)
        config_frame.columnconfigure(1, weight=1)

        tk.Label(config_frame, text="本地地址:", bg="white", font=ui_font).grid(row=0, column=0, padx=(20, 10), pady=15, sticky="w")
        self.url_entry = tk.Entry(config_frame, font=ui_font, bd=1, relief="solid")
        self.url_entry.insert(0, "http://localhost:3000")
        self.url_entry.grid(row=0, column=1, padx=(0, 20), pady=15, sticky="ew", ipady=3)

        tk.Label(config_frame, text="有效时长(H):", bg="white", font=ui_font).grid(row=1, column=0, padx=(20, 10), pady=(0, 15), sticky="w")
        
        dur_frame = tk.Frame(config_frame, bg="white")
        dur_frame.grid(row=1, column=1, sticky="w", padx=(0, 20), pady=(0, 15))
        
        self.hour_entry = tk.Entry(dur_frame, font=ui_font, bd=1, relief="solid", justify="center", width=5)
        self.hour_entry.insert(0, "24")
        self.hour_entry.pack(side="left", ipady=3)
        
        tk.Label(dur_frame, text="(到期后自动断开连接)", bg="white", fg="#999999", font=hint_font).pack(side="left", padx=10)

        # --- 5. 按钮 ---
        self.action_btn = tk.Button(main_content, text=BTN_START_TEXT, bg="white", fg="black",
                                    font=btn_font, command=self.toggle_tunnel,
                                    relief="raised", bd=2, cursor="hand2")
        self.action_btn.pack(fill="x", pady=10, ipady=5, expand=True)

        # --- 6. 结果显示区域 ---
        result_frame = tk.Frame(main_content, bg="white")
        result_frame.pack(fill="x", pady=10, expand=True)

        tk.Label(result_frame, text="生成的公网链接:", bg="white", fg="#666666", font=ui_font).pack(anchor="w", pady=(0, 5))
        
        self.result_entry = tk.Entry(result_frame, font=ui_font, bd=1, relief="solid", 
                                     fg="#444444", bg="#F2F2F2", state="readonly")
        self.result_entry.pack(fill="x", ipady=3)

    def toggle_tunnel(self):
        if self.is_running:
            self.stop_tunnel()
        else:
            self.start_tunnel()

    def get_executable_path(self):
        """获取 cloudflared 文件的路径"""
        # 判断是脚本运行还是打包后的exe运行
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
            # 【Mac 专属修复】Mac打包后需要往上跳3层找文件
            if self.system_os == "Darwin" and "Contents/MacOS" in base_path:
                base_path = os.path.abspath(os.path.join(base_path, "../../.."))
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))

        filename = "cloudflared.exe" if self.system_os == "Windows" else "cloudflared"
        exe_path = os.path.join(base_path, filename)
        return exe_path

    def ensure_permission(self, exe_path):
        """
        自动检查并赋予 cloudflared 执行权限 (Mac/Linux)
        """
        if self.system_os == "Darwin" or self.system_os == "Linux":
            if os.path.exists(exe_path):
                try:
                    # 获取当前权限
                    st = os.stat(exe_path)
                    # 添加用户执行权限 (S_IEXEC)
                    os.chmod(exe_path, st.st_mode | stat.S_IEXEC)
                    print(f"已自动赋予执行权限: {exe_path}")
                except Exception as e:
                    print(f"权限修改失败: {e}")

    def start_tunnel(self):
        target = self.url_entry.get().strip()
        try:
            hours = float(self.hour_entry.get().strip())
        except ValueError:
            messagebox.showerror("错误", "请输入有效的时间数字！")
            return

        if not target:
            messagebox.showerror("错误", "请输入本地地址！")
            return

        # 1. 获取路径
        exe_path = self.get_executable_path()

        # 2. 检查并修复权限 (调用上面定义的方法)
        self.ensure_permission(exe_path)
        
        # 3. 检查文件是否存在
        if not os.path.exists(exe_path):
             messagebox.showerror("错误", f"找不到引擎文件！\n\n请确保 [{os.path.basename(exe_path)}] \n与本程序在同一文件夹内。")
             return

        self.status_lbl.config(text="⏳ 正在建立安全隧道...")
        self.action_btn.config(state="disabled")
        
        creation_flags = 0
        if self.system_os == "Windows":
            creation_flags = subprocess.CREATE_NO_WINDOW
        
        cmd = [exe_path, "tunnel", "--protocol", "http2", "--url", target, "--metrics", "localhost:34567"]
        
        try:
            self.process = subprocess.Popen(
                cmd, 
                stderr=subprocess.PIPE, 
                stdout=subprocess.PIPE, 
                text=True, 
                bufsize=1,
                creationflags=creation_flags
            )
            
            threading.Thread(target=self.read_output, daemon=True).start()
            self.start_timer(hours)
            
        except Exception as e:
            messagebox.showerror("启动失败", str(e))
            self.action_btn.config(state="normal")

    def read_output(self):
        found_url = None
        while True:
            if self.process is None: break
            line = self.process.stderr.readline()
            if not line: break
            
            if ".trycloudflare.com" in line:
                import re
                match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
                if match:
                    found_url = match.group(0)
                    break
        
        self.root.after(0, lambda: self.update_ui_after_start(found_url))

    def update_ui_after_start(self, url):
        self.action_btn.config(state="normal")
        
        if url:
            self.is_running = True
            self.action_btn.config(text=BTN_STOP_TEXT, fg="red")
            
            self.result_entry.config(state="normal")
            self.result_entry.delete(0, tk.END)
            self.result_entry.insert(0, url)
            self.result_entry.config(state="readonly")
            
            self.status_lbl.config(text="✅ 正在运行 | 任何人拥有链接均可访问", fg="#8FC31F")
            self.url_entry.config(state="disabled")
            self.hour_entry.config(state="disabled")
        else:
            self.status_lbl.config(text="❌ 启动失败，请检查网络或端口占用。", fg="red")
            self.stop_tunnel()

    def start_timer(self, hours):
        seconds = hours * 3600
        self.timer = threading.Timer(seconds, self.timeout_kill)
        self.timer.start()

    def timeout_kill(self):
        self.root.after(0, self.timeout_ui_update)

    def timeout_ui_update(self):
        self.stop_tunnel()
        messagebox.showinfo("提示", "分享时间已到，链接已自动断开。")

    def stop_tunnel(self):
        if self.process:
            try:
                if self.system_os == "Windows":
                    subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)], 
                                    creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    os.kill(self.process.pid, signal.SIGTERM)
            except:
                pass
            self.process = None

        if self.timer:
            self.timer.cancel()
            self.timer = None

        self.is_running = False
        self.action_btn.config(text=BTN_START_TEXT, fg="black")
        self.status_lbl.config(text="⏹️ 服务已停止。", fg="#999999")
        
        self.result_entry.config(state="normal")
        self.result_entry.delete(0, tk.END)
        self.result_entry.insert(0, "(已断开)")
        self.result_entry.config(state="readonly")
        
        self.url_entry.config(state="normal")
        self.hour_entry.config(state="normal")

    def on_closing(self):
        self.stop_tunnel()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = SeeedShareTool(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()