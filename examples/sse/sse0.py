import time


def get_numbers_return():
    result = []
    for i in range(5):
        time.sleep(1)
        result.append(f"{i}个球")

    return result

# balls = get_numbers_return()
#
# print(balls)

def get_numbers_yield():
    for i in range(5):
        time.sleep(1)
        yield i

# 生成器
gen = get_numbers_yield()
print(next(gen))
print(next(gen))
print(next(gen))
print(next(gen))
print(next(gen))