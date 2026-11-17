// IoT 设备接入示例（C++17）
//
// 依赖：IXWebSocket（https://github.com/machinezone/IXWebSocket）、nlohmann/json、OpenSSL
// 编译：见同目录 CMakeLists.txt（cmake -B build && cmake --build build）
// 运行：./device_client http://<平台地址>:8090 <设备编号> <接入Key> [当前版本]
//
// 流程：HMAC 签名建连 → register → 心跳 → command 回 ack + result → 断线指数退避重连
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <ctime>
#include <iostream>
#include <mutex>
#include <random>
#include <string>
#include <thread>

#include <ixwebsocket/IXNetSystem.h>
#include <ixwebsocket/IXWebSocket.h>
#include <nlohmann/json.hpp>
#include <openssl/hmac.h>

using json = nlohmann::json;

static std::string g_server, g_device_id, g_key, g_version = "1.0.0";

// 签名：hex(HMAC-SHA256(key, "<device_id>\n<ts>\n<nonce>"))，Key 本身不上传
static std::string hmac_sha256_hex(const std::string &key, const std::string &data) {
  unsigned char mac[32];
  unsigned int len = 0;
  HMAC(EVP_sha256(), key.data(), static_cast<int>(key.size()),
       reinterpret_cast<const unsigned char *>(data.data()), data.size(), mac, &len);
  char hex[65];
  for (unsigned i = 0; i < len; ++i) std::snprintf(hex + i * 2, 3, "%02x", mac[i]);
  return std::string(hex, len * 2);
}

static std::string build_url() {
  static std::mt19937_64 rng{std::random_device{}()};
  const std::string ts = std::to_string(std::time(nullptr));  // 需已校时，允许偏差 300 秒
  char nonce[17];
  std::snprintf(nonce, sizeof(nonce), "%016llx", static_cast<unsigned long long>(rng()));
  const std::string sign = hmac_sha256_hex(g_key, g_device_id + "\n" + ts + "\n" + nonce);
  std::string base = g_server;
  if (base.rfind("https://", 0) == 0) base = "wss://" + base.substr(8);
  else if (base.rfind("http://", 0) == 0) base = "ws://" + base.substr(7);
  while (!base.empty() && base.back() == '/') base.pop_back();
  return base + "/ws/device/" + g_device_id + "/?ts=" + ts + "&nonce=" + nonce + "&sign=" + sign;
}

// 执行业务指令：返回 {code, message}，code=0 表示成功。在这里对接真实硬件。
static std::pair<int, std::string> execute(const std::string &code, const json &params) {
  if (code == "PING" || code == "REBOOT" || code == "SET_PARAM" || code == "SET_LED" ||
      code == "FACTORY_RESET") {
    std::cout << "执行指令 " << code << " 参数 " << params.dump() << std::endl;
    return {0, ""};
  }
  return {1, "不支持的指令 " + code};  // OTA_UPGRADE 见 docs/protocol.md
}

// 一次连接会话，返回关闭码（用于决定重连间隔）
static int run_session() {
  ix::WebSocket ws;
  ws.setUrl(build_url());
  ws.disableAutomaticReconnection();  // 每次重连都要重新签名，所以自己管理重连
  ws.setPingInterval(0);

  std::mutex mu;
  std::condition_variable cv;
  bool closed = false;
  std::atomic<int> close_code{0}, hb_interval{0};

  ws.setOnMessageCallback([&](const ix::WebSocketMessagePtr &msg) {
    using T = ix::WebSocketMessageType;
    if (msg->type == T::Open) {
      ws.send(json{{"type", "register"}, {"version", g_version}}.dump());
    } else if (msg->type == T::Message) {
      json m = json::parse(msg->str, nullptr, false);
      if (m.is_discarded()) return;
      const std::string type = m.value("type", "");
      if (type == "registered") {
        hb_interval = m.value("heartbeat_interval", 30);
        std::cout << "上线成功，心跳周期 " << hb_interval << "s" << std::endl;
      } else if (type == "command") {
        const auto cid = m["command_id"];
        ws.send(json{{"type", "ack"}, {"command_id", cid}}.dump());
        auto [code, message] = execute(m.value("code", ""), m.value("params", json::object()));
        ws.send(json{{"type", "result"}, {"command_id", cid}, {"code", code}, {"message", message}}.dump());
      } else if (type == "auth_failed") {
        close_code = m.value("code", 0);
        std::cout << "鉴权失败 " << close_code << "：" << m.value("message", "") << std::endl;
      }
    } else if (msg->type == T::Close || msg->type == T::Error) {
      if (msg->type == T::Close && close_code == 0) close_code = msg->closeInfo.code;
      if (msg->type == T::Error) std::cout << "连接错误：" << msg->errorInfo.reason << std::endl;
      std::lock_guard<std::mutex> lk(mu);
      closed = true;
      cv.notify_all();
    }
  });

  ws.start();
  auto last_hb = std::chrono::steady_clock::now();
  std::unique_lock<std::mutex> lk(mu);
  while (!cv.wait_for(lk, std::chrono::milliseconds(200), [&] { return closed; })) {
    const int interval = hb_interval;
    if (interval > 0 && std::chrono::steady_clock::now() - last_hb >= std::chrono::seconds(interval)) {
      ws.send(json{{"type", "heartbeat"}}.dump());
      last_hb = std::chrono::steady_clock::now();
    }
  }
  lk.unlock();
  ws.stop();
  return close_code;
}

int main(int argc, char *argv[]) {
  if (argc < 4) {
    std::cerr << "用法：" << argv[0] << " <平台地址> <设备编号> <接入Key> [当前版本]" << std::endl;
    return 1;
  }
  g_server = argv[1], g_device_id = argv[2], g_key = argv[3];
  if (argc > 4) g_version = argv[4];
  ix::initNetSystem();

  int backoff = 1;
  for (;;) {
    const int code = run_session();
    // 4401 Key 错误 / 4403 未生成 Key：60 秒后再试；4000 被新连接顶替：立即重连；其余指数退避
    backoff = (code == 4401 || code == 4403) ? 60 : (code == 4000 ? 1 : std::min(backoff * 2, 60));
    std::cout << "连接关闭（" << code << "），" << backoff << "s 后重连" << std::endl;
    std::this_thread::sleep_for(std::chrono::seconds(backoff));
  }
}
