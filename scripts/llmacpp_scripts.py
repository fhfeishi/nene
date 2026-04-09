
import subprocess
import time
import atexit
import urllib.request
import urllib.error
from loguru import logger

# 1. 将命令拆解为列表形式（官方推荐，比长字符串拼接更安全，避免路径转义问题）
# 默认安装方式的 or bin-win-64.zip解压包解压的
command = [
    "D:\environment\openvino\llama-b8721-bin-win-cpu-x64\llama-server.exe",  
    "-m", r"E:\local_models\huggingface\local\qwen3.5-2b-gguf\Qwen_Qwen3.5-2B-Q8_0.gguf", 
    "-c", "4096",
    "--port", "8080"
]

logger.info("正在后台启动 llama-server...")
# 2. 启动进程（非阻塞模式）
# # 正常模式，
# server_process = subprocess.Popen(command)
# 安静模式。如果不想看到控制台疯狂输出日志，可以加上 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
server_process = subprocess.Popen(
    command,
    stdout=subprocess.DEVNULL, # 屏蔽普通打印日志
    stderr=subprocess.DEVNULL  # 屏蔽错误/进度条日志 (llama.cpp 很多输出走的是 stderr)
)

# 3. 注册清理函数：确保 Python 脚本结束或崩溃时，顺手把后台的 llama-server 杀掉
def cleanup_server():
    if server_process.poll() is None: # 如果进程还在运行
        logger.info("\n正在关闭 llama-server...")
        server_process.terminate()
        server_process.wait()
        logger.info("服务器已关闭。")

atexit.register(cleanup_server)

# 4. 智能等待：不断探测服务器是否已经加载完毕
def wait_for_server(url="http://localhost:8080/health", timeout=120):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # 尝试访问服务器的健康检查接口
            urllib.request.urlopen(url)
            return True
        except (urllib.error.URLError, ConnectionResetError):
            time.sleep(2) # 等待 2 秒后重试
    return False

if wait_for_server():
    logger.info("模型加载完毕，服务器已就绪！\n" + "-"*30)
else:
    logger.info("服务器启动超时或失败，请检查模型路径或端口是否被占用。")
    exit(1)

# ==========================================
# 在这里写你的调用代码 (例如使用 openai 库)
# ==========================================
from openai import OpenAI

try:
    client = OpenAI(base_url="http://localhost:8080/v1", api_key="sk-no-key-required")
    response = client.chat.completions.create(
        model="qwen35",
        messages=[{"role": "user", "content": "你好，请确认你是否在线。"}],
    )
    logger.info("模型回复:\n{}", response.choices[0].message.content)
except Exception as e:
    logger.info(f"调用失败: {e}")

