# 爱逛GIT 体检脚本（一次性执行，**不是**死循环）：本地 FastAPI 服务 + Cloudflare 隧道
# 由「Windows 任务计划程序」每 2 分钟拉起一次，服务/隧道缺哪个补哪个。
#
# 为什么不写成 while 死循环：
#   常驻看守进程本身会被各种原因回收（2026-10-16 连着挂过两次），
#   交给任务计划程序做监督更可靠，而且它不依附任何终端/IDE 会话 —— 退出 TraeCode 不受影响。
#
# !! 本文件必须保存为「UTF-8 带 BOM」!!
#    PowerShell 5.1 读无 BOM 的 UTF-8 脚本时会按系统 GBK 解码，下面这些中文路径会变成乱码，
#    导致 Start-Process / 写日志全部**静默失败**（2026-10-16 踩过这个大坑）。
$ErrorActionPreference = "SilentlyContinue"

$root = "F:\软件开发\爱逛GIT"
$py   = "C:\Users\dongk\AppData\Local\Programs\Python\Python313\python.exe"
$cf   = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$log  = "$root\.cloudflared\watchdog.log"

function Say($m) {
    Add-Content -Path $log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m" -Encoding utf8
}

# 1) 本地服务：8321 没在监听就拉起来
if (-not (Get-NetTCPConnection -LocalPort 8321 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process -WindowStyle Hidden -FilePath $py -ArgumentList "server.py" -WorkingDirectory $root
    Say "拉起 server.py"
    Start-Sleep -Seconds 3
}

# 2) Cloudflare 命名隧道：进程不在就拉起来
#    必须显式带 --config，否则 cloudflared 会去加载 ~/.cloudflared/config.yml 里另一个隧道
if (-not (Get-Process cloudflared -ErrorAction SilentlyContinue)) {
    Start-Process -WindowStyle Hidden -FilePath $cf -ArgumentList @(
        "--config", "$root\.cloudflared\config.yml",
        "tunnel", "run", "aiguang-git"
    )
    Say "拉起 cloudflared"
}
