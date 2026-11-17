# 设备接入示例

四份示例功能一致：**HMAC 签名建连 → register → 心跳 → 处理指令（ack + result）→ 断线指数退避重连**。
管理端「帮助 → 设备接入指南」页面直接展示这里的源码。

| 语言 | 目录 | 依赖 | 运行 |
|---|---|---|---|
| Python 3.8+ | `python/` | `pip install websockets` | `python device_client.py <平台地址> <设备编号> <接入Key> [版本]` |
| C（Linux / 嵌入式） | `c/` | Mongoose（单文件，自带 HMAC-SHA256） | `make && ./device_client …` |
| C++17 | `cpp/` | IXWebSocket、nlohmann/json、OpenSSL | `cmake -B build && cmake --build build && ./build/device_client …` |
| Java 17+ | `java/` | org.json | `mvn -q package && java -jar target/device-client.jar …` |

## 前提

1. 管理端「设备列表」中建档设备；
2. 在「设备详情 → 接入 Key」**手动生成** Key（或在列表中勾选后「批量生成 Key」并下载 CSV）；
3. 把设备编号与 Key 写入设备。

## 签名

```
data = 设备编号 + "\n" + ts + "\n" + nonce        # ts：Unix 秒；nonce：每次连接随机生成
sign = hex(HMAC-SHA256(key = 接入Key, data))
ws://<平台地址>/ws/device/<设备编号>/?ts=<ts>&nonce=<nonce>&sign=<sign>
```

测试向量：设备 `dev-001`，Key `0123456789abcdef0123456789abcdef`，ts `1763380000`，nonce `a1b2c3d4e5f60718`
→ sign `f3591d4d3ba2f0926578b2d00aca065b387ce58b5206a695c83453ec463e719d`

## C 示例准备 Mongoose

```bash
cd c
curl -LO https://raw.githubusercontent.com/cesanta/mongoose/7.20/mongoose.c
curl -LO https://raw.githubusercontent.com/cesanta/mongoose/7.20/mongoose.h
make
```

## C++ 示例准备 IXWebSocket

```bash
sudo apt install -y g++ cmake libssl-dev zlib1g-dev nlohmann-json3-dev
git clone https://github.com/machinezone/IXWebSocket && cd IXWebSocket
cmake -B build -DUSE_TLS=1 && cmake --build build -j && sudo cmake --install build
```

关闭码、消息格式与升级流程见 [docs/protocol.md](../../docs/protocol.md)。
