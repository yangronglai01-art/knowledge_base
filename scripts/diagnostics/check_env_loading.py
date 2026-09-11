import os

from dotenv import load_dotenv

# 默认读系统环境变量（前提是系统环境变量已生效）
# load_dotenv()

# 读.env文件
load_dotenv(override=True)
print(os.getenv("YOUR_KEY"))
