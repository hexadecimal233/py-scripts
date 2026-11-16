"""导出 Android 上 Chromium 内核浏览器当前打开的标签页, 输出 Markdown 列表.

Chromium 内核浏览器在进程存活时会暴露 DevTools abstract socket,
经 adb forward 后用 DevTools HTTP 接口 /json/list 读取每个标签页的标题与网址.
此方式无需 root.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from adbutils import AdbError, adb

DEFAULT_SOCKET = "chrome_devtools_remote"


def fail(message):
    print(message, file=sys.stderr)
    sys.exit(1)


def device_rows():
    try:
        return adb.list()
    except AdbError as error:
        fail(f"adb devices 执行失败: {error}")


def pick_device(requested):
    serial = requested or os.environ.get("ANDROID_SERIAL")
    if serial:
        return serial
    try:
        online = [device.serial for device in adb.device_list()]
    except AdbError as error:
        fail(f"adb devices 执行失败: {error}")
    if not online:
        fail("没有处于 device 状态的设备, 请检查 USB 连接与授权")
    if len(online) > 1:
        fail(
            "检测到多个在线设备, 请用 --serial 指定其中一个: " + ", ".join(online)
        )
    return online[0]


def open_forward(serial, socket_name, port=None):
    """Forward the DevTools socket; returns (local port, whether we created it)."""
    remote = f"localabstract:{socket_name}"
    device = adb.device(serial=serial)
    try:
        existing = {
            item.local for item in device.forward_list() if item.remote == remote
        }
        if port:
            device.forward(f"tcp:{port}", remote)
        else:
            port = device.forward_port(remote)
    except AdbError as error:
        fail(
            f"adb forward 失败: {error}\n"
            "浏览器正在运行时才会创建 DevTools socket, 请先打开浏览器并保持其进程存活"
        )
    return port, f"tcp:{port}" not in existing


def close_forward(serial, port):
    try:
        adb.device(serial=serial).forward_remove(
            f"tcp:{port}", raise_non_found=False
        )
    except AdbError:
        pass


def http_json(url, timeout):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def collapsed(text):
    return " ".join(str(text).split())


def markdown_title(title, url):
    text = collapsed(title)
    if not text:
        return collapsed(url)
    escaped = []
    for char in text:
        if char in "\\[]":
            escaped.append("\\")
        escaped.append(char)
    return "".join(escaped)


def markdown_url(url):
    return collapsed(url).replace("(", "%28").replace(")", "%29")


def collect(base_url, timeout):
    targets = http_json(f"{base_url}/json/list", timeout)
    pages = []
    for target in targets:
        if target.get("type") != "page":
            continue
        url = collapsed(target.get("url", ""))
        if not url or url.startswith("devtools://"):
            continue
        pages.append((target.get("title", ""), url))
    return pages


def main():
    parser = argparse.ArgumentParser(
        description="导出 Android 上 Chromium 内核浏览器打开的标签页为 Markdown 列表"
    )
    parser.add_argument("--serial", help="设备序列号, 默认使用唯一在线设备")
    parser.add_argument(
        "--socket",
        default=DEFAULT_SOCKET,
        help=f"DevTools abstract socket 名称, 默认 {DEFAULT_SOCKET}",
    )
    parser.add_argument("--port", type=int, help="本机转发端口, 默认自动选取空闲端口")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP 超时秒数")
    parser.add_argument("--no-header", action="store_true", help="只输出列表, 不含标题")
    parser.add_argument("--json", action="store_true", help="输出 JSON 数组")
    parser.add_argument("--list-devices", action="store_true", help="列出设备后退出")
    parser.add_argument("-o", "--output", help="写入文件, 默认写到标准输出")
    args = parser.parse_args()

    if args.list_devices:
        for info in device_rows():
            print(f"{info.serial}\t{info.state}")
        return
    serial = pick_device(args.serial)
    port, created = open_forward(serial, args.socket, args.port)
    base_url = f"http://127.0.0.1:{port}"
    try:
        version = http_json(f"{base_url}/json/version", args.timeout)
        pages = collect(base_url, args.timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        fail(f"读取 DevTools 接口失败: {error}\n传输通道已建立, 但浏览器没有响应")
    except json.JSONDecodeError as error:
        fail(f"DevTools 返回的内容无法解析: {error}")
    finally:
        if created:
            close_forward(serial, port)

    if args.json:
        body = json.dumps(
            [{"title": collapsed(t), "url": u} for t, u in pages],
            ensure_ascii=False,
            indent=2,
        )
    else:
        lines = []
        if not args.no_header:
            package = version.get("Android-Package") or "未知包名"
            browser = version.get("Browser", "未知版本")
            lines.append(f"# 浏览器打开的页面 ({len(pages)} 个)")
            lines.append("")
            lines.append(f"设备 {serial}, 包名 {package}, 浏览器 {browser}")
            lines.append("")
        for title, url in pages:
            lines.append(f"- [{markdown_title(title, url)}]({markdown_url(url)})")
        body = "\n".join(lines) + "\n"

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(body)
    else:
        sys.stdout.write(body)


if __name__ == "__main__":
    main()
