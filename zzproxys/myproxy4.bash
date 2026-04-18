#!/bin/zsh
# ================================================================
# 🌐 WSL2 (Mirrored) + ClashVergeRev 极简网络工具箱 (纯IPv4特化版)
# ================================================================

# # 1. 核心地址配置 (Mirrored模式下直接走本地回环)
_PROXY_HOST="127.0.0.1"
_PROXY_PORT="7897"             # ClashVergeRev 代理流量端口

_PROXY_HTTP="http://${_PROXY_HOST}:${_PROXY_PORT}"
_PROXY_SOCKS="socks5://${_PROXY_HOST}:${_PROXY_PORT}"
_NO_PROXY="localhost,127.0.0.1,::1,*.local,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

# # 2. 环境变量代理控制
proxy_on() {
    export http_proxy="${_PROXY_HTTP}" https_proxy="${_PROXY_HTTP}" all_proxy="${_PROXY_SOCKS}"
    export HTTP_PROXY="${_PROXY_HTTP}" HTTPS_PROXY="${_PROXY_HTTP}" ALL_PROXY="${_PROXY_SOCKS}"
    export no_proxy="${_NO_PROXY}" NO_PROXY="${_NO_PROXY}"
    [[ "$1" != "-q" ]] && echo "🟢 代理已开启 (强制绕过TUN) → ${_PROXY_HTTP}"
}

proxy_off() {
    unset http_proxy https_proxy all_proxy no_proxy
    unset HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY
    echo "🔴 代理已关闭 (当前流量由系统 TUN 接管)"
}

proxy_status() {
    [[ -n "${http_proxy}" ]] && echo "🟢 显式代理: 生效中" || echo "🔴 显式代理: 未生效 (纯 TUN 接管)"
}

# 临时单次执行 (不污染当前 shell 环境)
proxy_run() {
    http_proxy="${_PROXY_HTTP}" https_proxy="${_PROXY_HTTP}" all_proxy="${_PROXY_SOCKS}" "$@"
}
proxy_sudo() {
    sudo -E env http_proxy="${_PROXY_HTTP}" https_proxy="${_PROXY_HTTP}" all_proxy="${_PROXY_SOCKS}" "$@"
}

# # 3. 常用保底指令封装 (修复语法 + 强制 IPv4)
alias proxy_apt='proxy_sudo apt-get'
alias proxy_pip='proxy_run command pip'
alias proxy_uv='proxy_run command uv'
alias proxy_wget='command wget -4 -e use_proxy=yes -e "http_proxy=${_PROXY_HTTP}" -e "https_proxy=${_PROXY_HTTP}"'
alias proxy_curl='command curl -4 -x "${_PROXY_HTTP}"'

# # 4. 极简网络诊断 (强制 -4 避免IPv6黑洞)
_net_test() {
    local name="$1" url="$2"
    # 关键：加入 -4 强制走 IPv4，彻底隔绝 IPv6 MTU 导致的超时卡死
    local out code time
    out=$(curl -4 -o /dev/null -s -w "%{http_code}:%{time_total}" --connect-timeout 3 --max-time 5 "$url" 2>/dev/null || echo "000:0.00")
    code="${out%%:*}"
    time=$(printf "%.2f" "${out##*:}")

    if [[ "$code" =~ ^(200|201|204|301|302|303|403|405)$ ]]; then
        echo | awk -v n="$name" -v c="$code" -v t="${time}s" '{printf "  🟢 %-14s HTTP %-3s (%s)\n", n, c, t}'
    else
        echo | awk -v n="$name" -v c="$code" '{printf "  🔴 %-14s 失败 (HTTP %s)\n", n, c}'
    fi
}

net_check() {
    echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo " 🔍 网络连通性测试 (强制IPv4) | $(date '+%H:%M:%S')"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    echo -e "\n📡 【当前状态】"
    proxy_status

    echo -e "\n🇨🇳 【国内镜像 (直连测速)】"
    _net_test "清华 Ubuntu" "https://mirrors.tuna.tsinghua.edu.cn"
    _net_test "阿里云源"   "https://mirrors.aliyun.com"

    echo -e "\n🌍 【海外节点 (代理测速)】"
    _net_test "Google"      "https://www.google.com"
    _net_test "GitHub"      "https://github.com"
    _net_test "HuggingFace" "https://huggingface.co"
    _net_test "OpenAI API"  "https://api.openai.com"

    echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
}

net_speed() {
    echo -e "\n⚡ 终端出口测速 (IPv4)"
    echo -n "  📍 当前出口 IP : "
    curl -4 -s --connect-timeout 3 "https://api.ipify.org" 2>/dev/null || echo "获取失败"

    echo "  🚀 Cloudflare (10MB) 下载测试..."
    curl -4 -o /dev/null -s -w "  📊 最终速度: %{speed_download} bytes/s\n" \
        --connect-timeout 5 --max-time 15 \
        "https://speed.cloudflare.com/__down?bytes=10000000" 2>/dev/null \
        | awk '{printf "  ✅ 测速完成: %.2f MB/s\n", $3/1024/1024}'
    echo ""
}

net_help() {
    echo -e "\n📖 WSL 网络工具箱 (纯IPv4特化)"
    echo -e "  [检测] net_check   | net_speed"
    echo -e "  [控制] proxy_on    | proxy_off   | proxy_status"
    echo -e "  [保底] proxy_run   | proxy_sudo"
    echo -e "  [常用] proxy_apt   | proxy_curl  | proxy_wget | proxy_pip | proxy_uv\n"
}