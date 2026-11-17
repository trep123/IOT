/*
 * IoT 设备接入示例（C，基于 Mongoose 网络库，适合 Linux / 嵌入式）
 *
 * 依赖：mongoose.c / mongoose.h（https://github.com/cesanta/mongoose，已在 7.20 验证），自带 HMAC-SHA256，无需 OpenSSL
 * 编译：cc -O2 -o device_client device_client.c mongoose.c
 * 运行：./device_client http://<平台地址>:8090 <设备编号> <接入Key> [当前版本]
 *
 * 流程：HMAC 签名建连 → register → 心跳 → command 回 ack + result → 断线指数退避重连
 */
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "mongoose.h"

static const char *s_server, *s_device_id, *s_key, *s_version = "1.0.0";
static struct mg_connection *s_conn;  // 当前连接，NULL 表示未连接
static uint64_t s_hb_interval_ms = 30000, s_last_hb_ms, s_next_connect_ms;
static int s_registered, s_backoff_s = 1, s_close_code;

// 签名：hex(HMAC-SHA256(key, "<device_id>\n<ts>\n<nonce>"))
static void build_url(char *url, size_t len) {
  char nonce[17], payload[256], sign[65];
  uint8_t mac[32];
  unsigned long ts = (unsigned long) time(NULL);  // 需已校时（NTP），允许偏差 300 秒
  for (int i = 0; i < 16; i++) nonce[i] = "0123456789abcdef"[rand() % 16];
  nonce[16] = '\0';
  size_t n = (size_t) snprintf(payload, sizeof(payload), "%s\n%lu\n%s", s_device_id, ts, nonce);
  mg_hmac_sha256(mac, (uint8_t *) s_key, strlen(s_key), (uint8_t *) payload, n);
  for (int i = 0; i < 32; i++) snprintf(sign + i * 2, 3, "%02x", mac[i]);
  const char *host = strstr(s_server, "://");
  int tls = strncmp(s_server, "https", 5) == 0;
  snprintf(url, len, "%s://%s/ws/device/%s/?ts=%lu&nonce=%s&sign=%s", tls ? "wss" : "ws",
           host ? host + 3 : s_server, s_device_id, ts, nonce, sign);
}

// 执行业务指令：返回 0 表示成功。在这里对接真实硬件。
static int execute(const char *code, struct mg_str params, char *msg, size_t msglen) {
  (void) params;
  if (strcmp(code, "PING") == 0 || strcmp(code, "REBOOT") == 0 || strcmp(code, "SET_PARAM") == 0 ||
      strcmp(code, "SET_LED") == 0 || strcmp(code, "FACTORY_RESET") == 0) {
    printf("执行指令 %s 参数 %.*s\n", code, (int) params.len, params.buf);
    return 0;
  }
  snprintf(msg, msglen, "不支持的指令 %s", code);  // OTA_UPGRADE 见 docs/protocol.md
  return 1;
}

static void on_message(struct mg_connection *c, struct mg_str data) {
  char *type = mg_json_get_str(data, "$.type");
  if (type == NULL) return;
  if (strcmp(type, "registered") == 0) {
    long sec = mg_json_get_long(data, "$.heartbeat_interval", 30);
    s_hb_interval_ms = (uint64_t) sec * 1000;
    s_registered = 1;
    s_backoff_s = 1;
    s_last_hb_ms = mg_millis();
    printf("上线成功，心跳周期 %lds\n", sec);
  } else if (strcmp(type, "command") == 0) {
    long cid = mg_json_get_long(data, "$.command_id", -1);
    char *code = mg_json_get_str(data, "$.code");
    struct mg_str params = mg_json_get_tok(data, "$.params");
    char err[128] = "";
    mg_ws_printf(c, WEBSOCKET_OP_TEXT, "{%m:%m,%m:%ld}", MG_ESC("type"), MG_ESC("ack"),
                 MG_ESC("command_id"), cid);
    int rc = execute(code ? code : "", params, err, sizeof(err));
    mg_ws_printf(c, WEBSOCKET_OP_TEXT, "{%m:%m,%m:%ld,%m:%d,%m:%m}", MG_ESC("type"), MG_ESC("result"),
                 MG_ESC("command_id"), cid, MG_ESC("code"), rc, MG_ESC("message"), MG_ESC(err));
    free(code);
  } else if (strcmp(type, "auth_failed") == 0) {
    char *m = mg_json_get_str(data, "$.message");
    s_close_code = (int) mg_json_get_long(data, "$.code", 0);
    printf("鉴权失败 %d：%s\n", s_close_code, m ? m : "");
    free(m);
  }
  free(type);
}

static void handler(struct mg_connection *c, int ev, void *ev_data) {
  if (ev == MG_EV_WS_OPEN) {
    mg_ws_printf(c, WEBSOCKET_OP_TEXT, "{%m:%m,%m:%m}", MG_ESC("type"), MG_ESC("register"),
                 MG_ESC("version"), MG_ESC(s_version));
  } else if (ev == MG_EV_WS_MSG) {
    struct mg_ws_message *wm = (struct mg_ws_message *) ev_data;
    on_message(c, wm->data);
  } else if (ev == MG_EV_ERROR) {
    printf("连接错误：%s\n", (char *) ev_data);
  } else if (ev == MG_EV_CLOSE) {
    s_conn = NULL;
    s_registered = 0;
    // 4401 Key 错误 / 4403 未生成 Key：60 秒后再试；其余指数退避（最长 60 秒）
    s_backoff_s = (s_close_code == 4401 || s_close_code == 4403) ? 60
                  : (s_backoff_s * 2 > 60 ? 60 : s_backoff_s * 2);
    s_next_connect_ms = mg_millis() + (uint64_t) s_backoff_s * 1000;
    printf("连接关闭，%ds 后重连\n", s_backoff_s);
  }
}

int main(int argc, char *argv[]) {
  if (argc < 4) {
    fprintf(stderr, "用法：%s <平台地址> <设备编号> <接入Key> [当前版本]\n", argv[0]);
    return 1;
  }
  s_server = argv[1], s_device_id = argv[2], s_key = argv[3];
  if (argc > 4) s_version = argv[4];
  setvbuf(stdout, NULL, _IOLBF, 0);  // 日志按行输出
  srand((unsigned) time(NULL) ^ (unsigned) mg_millis());
  mg_log_set(MG_LL_ERROR);

  struct mg_mgr mgr;
  mg_mgr_init(&mgr);
  for (;;) {
    uint64_t now = mg_millis();
    if (s_conn == NULL && now >= s_next_connect_ms) {
      char url[512];
      build_url(url, sizeof(url));
      s_close_code = 0;
      s_conn = mg_ws_connect(&mgr, url, handler, NULL, NULL);
      if (s_conn == NULL) s_next_connect_ms = now + 5000;
    }
    if (s_conn && s_registered && now - s_last_hb_ms >= s_hb_interval_ms) {
      mg_ws_printf(s_conn, WEBSOCKET_OP_TEXT, "{%m:%m}", MG_ESC("type"), MG_ESC("heartbeat"));
      s_last_hb_ms = now;
    }
    mg_mgr_poll(&mgr, 200);
  }
  mg_mgr_free(&mgr);
  return 0;
}
