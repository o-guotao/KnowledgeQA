# Python 编程技巧速查

## 列表操作

列表推导式是 Python 的一大特色。用 [x*2 for x in range(10)] 可以快速生成翻倍序列。切片操作 list[::-1] 能反转列表，list[::2] 取偶数索引元素。注意列表是可变对象，作为函数默认参数会产生陷阱，应该用 None 作为默认值再在函数内初始化。

## 字典与集合

字典的 get 方法带默认值比直接索引更安全，避免 KeyError。setdefault 可以在键不存在时设置默认值。字典推导 {k: v for k, v in items} 一行完成映射构造。集合去重是最快的，list(set(items)) 但会丢失顺序，Python 3.7 后可以用 dict.fromkeys 保序去重。

## 异常处理

不要裸写 except:，应该捕获具体异常类型。try/except/else/finally 的 else 在没有异常时执行。用 contextlib.suppress 可以优雅地忽略特定异常。自定义异常应继承 Exception 而非 BaseException。

## 性能优化

生成器表达式比列表推导省内存，(x for x in items) 惰性求值。拼接大量字符串用 join 而非 +=，后者每次产生新对象。局部变量查找比全局变量快，热点循环里可以把全局函数赋给局部变量。functools.lru_cache 一行实现函数结果缓存。
