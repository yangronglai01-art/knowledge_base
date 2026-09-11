import time

def download_file(name):
    print(f"开始下载：{name}")
    time.sleep(2)  # 模拟下载耗时 2 秒（整个程序卡住2秒，阻塞）
    print(f"下载完成：{name}")

download_file("文件 1")
