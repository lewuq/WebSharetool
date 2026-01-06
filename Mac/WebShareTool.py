import os
import sys
import platform
import subprocess
import threading
import time
import webbrowser
import stat
import signal
from flask import Flask, request, jsonify, render_template_string

# ================= 配置 =================
app = Flask(__name__)
PORT = 8888
THEME_COLOR = "#8FC31F"

# 全局变量
tunnel_process = None
current_url = ""
last_heartbeat = time.time()  # 上次心跳时间
monitor_active = True         # 监控开关

# ================= 核心工具函数 =================
def get_engine_path():
    """获取 cloudflared 路径"""
    base_path = os.path.dirname(os.path.abspath(__file__))
    filename = "cloudflared.exe" if platform.system() == "Windows" else "cloudflared"
    return os.path.join(base_path, filename)

def ensure_permission(path):
    """Mac/Linux 自动提权"""
    if platform.system() in ["Darwin", "Linux"] and os.path.exists(path):
        try:
            st = os.stat(path)
            os.chmod(path, st.st_mode | stat.S_IEXEC)
        except:
            pass

def read_stream(process):
    """读取 cloudflared 输出流"""
    global current_url
    while True:
        if process.poll() is not None: break
        try:
            # 忽略读取错误（防止脚本退出时报错）
            line = process.stderr.readline()
            if not line: break
            if ".trycloudflare.com" in line:
                import re
                match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
                if match:
                    current_url = match.group(0)
                    break
        except:
            break

def kill_process_tree(pid):
    """强力杀进程 (兼容所有平台)"""
    try:
        if platform.system() == "Windows":
            # Windows: 使用 taskkill /F /T 强制杀死进程树
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(pid)], 
                            creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            # Mac/Linux: 杀掉进程组
            os.killpg(os.getpgid(pid), signal.SIGTERM)
    except Exception as e:
        print(f"Kill error: {e}")

def heartbeat_monitor():
    """后台监控线程：如果网页关闭(无心跳)，则杀进程"""
    global tunnel_process, current_url
    print("启动心跳监控...")
    while monitor_active:
        time.sleep(2) # 每2秒检查一次
        
        # 只有在隧道开启时才检查心跳
        if tunnel_process is not None:
            # 如果超过 5 秒没收到心跳 (网页已关)
            if time.time() - last_heartbeat > 600:
                print("⚠️ 检测到网页关闭，自动停止分享...")
                stop_tunnel_internal()

# ================= 前端 HTML =================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WebShareTool Web</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; background-color: #f4f4f4; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .card { background: white; width: 480px; padding: 30px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
        .header { background: {{ color }}; color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center; margin: -30px -30px 20px -30px; }
        .input-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; color: #666; font-weight: 500; }
        input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; box-sizing: border-box; font-size: 14px; }
        button { width: 100%; padding: 12px; border: none; border-radius: 6px; font-size: 16px; font-weight: bold; cursor: pointer; transition: 0.2s; }
        .btn-start { background-color: {{ color }}; color: white; }
        .btn-stop { background-color: #ff4d4f; color: white; display: none; }
        .btn-stop:hover { background-color: #d9363e; }
        .status-box { margin-top: 20px; padding: 10px; background: #f9f9f9; border-radius: 6px; font-size: 13px; color: #555; min-height: 40px; display: flex; align-items: center; }
        .result-box { margin-top: 10px; }
        .url-display { width: 100%; padding: 10px; background: #e6f7ff; border: 1px solid #91d5ff; color: #0050b3; border-radius: 6px; font-weight: bold; text-align: center; cursor: text; display: none;}
        .loader { border: 3px solid #f3f3f3; border-top: 3px solid {{ color }}; border-radius: 50%; width: 16px; height: 16px; animation: spin 1s linear infinite; display: none; margin-right: 10px;}
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="card">
        <div class="header"><h2 style="margin:0">WebShareTool</h2></div>
        
        <div class="input-group">
            <label>本地地址 (Local Address)</label>
            <input type="text" id="target" value="http://localhost:3000">
        </div>

        <div class="input-group">
            <label>有效时长 (Hours)</label>
            <input type="number" id="hours" value="24">
        </div>

        <button id="btnStart" class="btn-start" onclick="startTunnel()">🚀 立即生成分享链接</button>
        <button id="btnStop" class="btn-stop" onclick="stopTunnel()">🛑 停止分享</button>

        <div class="result-box">
            <input type="text" id="urlResult" class="url-display" readonly value="" onclick="this.select()">
        </div>

        <div class="status-box">
            <div id="loader" class="loader"></div>
            <span id="statusText">准备就绪。</span>
        </div>
    </div>

    <script>
        let checkInterval;
        let heartbeatInterval;

        // 页面加载时启动心跳 (保留心跳以实现“关网页即停”)
        window.onload = function() {
            sendHeartbeat();
            heartbeatInterval = setInterval(sendHeartbeat, 2000); // 每2秒发送一次心跳
        };

        // 心跳发送函数
        async function sendHeartbeat() {
            try {
                await fetch('/api/heartbeat');
            } catch(e) { console.log("Server disconnected"); }
        }

        async function startTunnel() {
            const target = document.getElementById('target').value;
            const hours = document.getElementById('hours').value;
            
            updateStatus('waiting', '⏳ 正在建立隧道...');
            
            try {
                const res = await fetch('/api/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({target, hours})
                });
                const data = await res.json();
                
                if(data.status === 'success') {
                    checkInterval = setInterval(checkUrl, 1000);
                } else {
                    updateStatus('error', '❌ ' + data.message);
                }
            } catch(e) {
                updateStatus('error', '❌ 连接后台失败');
            }
        }

        async function checkUrl() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                
                if(data.url) {
                    clearInterval(checkInterval);
                    document.getElementById('urlResult').value = data.url;
                    document.getElementById('urlResult').style.display = 'block';
                    updateStatus('running', '✅ 运行中 | 链接已生成');
                    toggleButtons(true);
                } else if (data.running === false) {
                    // 如果后端已经停止了，前端也要停止
                    resetUI();
                }
            } catch(e) {
                resetUI();
            }
        }

        async function stopTunnel() {
            // 立即停止前端轮询，防止状态跳变
            clearInterval(checkInterval);
            updateStatus('waiting', '正在断开...');
            
            try {
                await fetch('/api/stop', {method: 'POST'});
                resetUI();
            } catch(e) {
                resetUI();
            }
        }

        function resetUI() {
            clearInterval(checkInterval);
            document.getElementById('urlResult').style.display = 'none';
            document.getElementById('urlResult').value = '';
            toggleButtons(false);
            updateStatus('ready', '⏹️ 服务已停止');
        }

        function toggleButtons(isRunning) {
            document.getElementById('btnStart').style.display = isRunning ? 'none' : 'block';
            document.getElementById('btnStop').style.display = isRunning ? 'block' : 'none';
            document.getElementById('target').disabled = isRunning;
            document.getElementById('hours').disabled = isRunning;
        }

        function updateStatus(state, text) {
            document.getElementById('statusText').innerText = text;
            const loader = document.getElementById('loader');
            loader.style.display = state === 'waiting' ? 'block' : 'none';
        }
    </script>
</body>
</html>
"""

# ================= 路由逻辑 =================
@app.route('/')
def index():
    # 访问主页时更新一次心跳
    global last_heartbeat
    last_heartbeat = time.time()
    return render_template_string(HTML_TEMPLATE, color=THEME_COLOR)

@app.route('/api/heartbeat')
def api_heartbeat():
    """前端定期调用此接口，证明网页还开着"""
    global last_heartbeat
    last_heartbeat = time.time()
    return jsonify({"status": "alive"})

@app.route('/api/start', methods=['POST'])
def api_start():
    global tunnel_process, current_url, last_heartbeat
    data = request.json
    target = data.get('target')
    
    # 立即更新心跳，防止误杀
    last_heartbeat = time.time()
    
    exe_path = get_engine_path()
    ensure_permission(exe_path)
    
    if not os.path.exists(exe_path):
        return jsonify({"status": "error", "message": "找不到 cloudflared 文件"})
    
    # 如果已有进程，先杀掉
    stop_tunnel_internal()
    
    current_url = ""
    
    import random
    rand_port = random.randint(10000, 60000)
    
    creation_flags = 0
    preexec = None
    
    if platform.system() == "Windows":
        # 使用 CREATE_NO_WINDOW (0x08000000)
        # 尝试通过 CREATE_NEW_PROCESS_GROUP (0x00000200) 让它在关闭终端时存活（视系统策略而定）
        creation_flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        preexec = os.setsid
        
    cmd = [exe_path, "tunnel", "--protocol", "http2", "--url", target, "--metrics", f"localhost:{rand_port}"]
    
    try:
        tunnel_process = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
            creationflags=creation_flags,
            preexec_fn=preexec
        )
        threading.Thread(target=read_stream, args=(tunnel_process,), daemon=True).start()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/status')
def api_status():
    global tunnel_process
    is_running = tunnel_process is not None and tunnel_process.poll() is None
    if not is_running:
        tunnel_process = None 
    return jsonify({"running": is_running, "url": current_url})

@app.route('/api/stop', methods=['POST'])
def api_stop():
    stop_tunnel_internal()
    return jsonify({"status": "stopped"})

def stop_tunnel_internal():
    """内部停止函数"""
    global tunnel_process, current_url
    if tunnel_process:
        print(f"Stopping tunnel PID: {tunnel_process.pid}")
        kill_process_tree(tunnel_process.pid)
        tunnel_process = None
    current_url = ""

def open_browser():
    time.sleep(1.5)
    webbrowser.open(f'http://localhost:{PORT}')

if __name__ == '__main__':
    # 启动自动打开浏览器
    threading.Thread(target=open_browser).start()
    
    # 启动心跳监控线程 (保留此功能)
    monitor_thread = threading.Thread(target=heartbeat_monitor, daemon=True)
    monitor_thread.start()
    
    print(f"WebShareTool Web V3.1 is running on port {PORT}...")
    try:
        app.run(host='0.0.0.0', port=PORT, debug=False)
    except:
        pass
