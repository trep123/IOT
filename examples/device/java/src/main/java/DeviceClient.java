// IoT 设备接入示例（Java 17+，使用 JDK 自带 java.net.http.WebSocket）
//
// 依赖：org.json（见 pom.xml）
// 编译运行：mvn -q package && java -jar target/device-client.jar http://<平台地址>:8090 <设备编号> <接入Key> [当前版本]
//
// 流程：HMAC 签名建连 → register → 心跳 → command 回 ack + result → 断线指数退避重连
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.HexFormat;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.json.JSONObject;

public class DeviceClient {
    private static String server, deviceId, key, version = "1.0.0";
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final ScheduledExecutorService TIMER = Executors.newSingleThreadScheduledExecutor();

    /** 签名：hex(HMAC-SHA256(key, "<device_id>\n<ts>\n<nonce>"))，Key 本身不上传。 */
    static String buildUrl() throws Exception {
        String ts = String.valueOf(System.currentTimeMillis() / 1000);  // 需已校时，允许偏差 300 秒
        byte[] n = new byte[8];
        RANDOM.nextBytes(n);
        String nonce = HexFormat.of().formatHex(n);
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        String sign = HexFormat.of().formatHex(
                mac.doFinal((deviceId + "\n" + ts + "\n" + nonce).getBytes(StandardCharsets.UTF_8)));
        String base = server.replaceFirst("^https://", "wss://").replaceFirst("^http://", "ws://")
                .replaceAll("/+$", "");
        return base + "/ws/device/" + deviceId + "/?ts=" + ts + "&nonce=" + nonce + "&sign=" + sign;
    }

    /** JDK WebSocket 不允许并发发送：串行化，并等待上一条发送完成。 */
    static synchronized void send(WebSocket ws, JSONObject msg) {
        ws.sendText(msg.toString(), true).join();
    }

    /** 执行业务指令，返回结果码（0 成功）。在这里对接真实硬件。 */
    static int execute(String code, JSONObject params, StringBuilder message) {
        switch (code) {
            case "PING", "REBOOT", "SET_PARAM", "SET_LED", "FACTORY_RESET" -> {
                System.out.println("执行指令 " + code + " 参数 " + params);
                return 0;
            }
            default -> {
                message.append("不支持的指令 ").append(code);  // OTA_UPGRADE 见 docs/protocol.md
                return 1;
            }
        }
    }

    /** 一次连接会话，阻塞到连接关闭，返回关闭码。 */
    static int runSession(HttpClient http) throws Exception {
        CompletableFuture<Integer> closed = new CompletableFuture<>();
        final int[] authCode = {0};
        final ScheduledFuture<?>[] heartbeat = {null};

        WebSocket.Listener listener = new WebSocket.Listener() {
            private final StringBuilder buf = new StringBuilder();

            @Override
            public void onOpen(WebSocket ws) {
                send(ws, new JSONObject().put("type", "register").put("version", version));
                ws.request(1);
            }

            @Override
            public CompletionStage<?> onText(WebSocket ws, CharSequence data, boolean last) {
                buf.append(data);
                if (last) {
                    handle(ws, new JSONObject(buf.toString()));
                    buf.setLength(0);
                }
                ws.request(1);
                return null;
            }

            private synchronized void handle(WebSocket ws, JSONObject m) {
                switch (m.optString("type")) {
                    case "registered" -> {
                        int interval = m.optInt("heartbeat_interval", 30);
                        System.out.println("上线成功，心跳周期 " + interval + "s");
                        heartbeat[0] = TIMER.scheduleAtFixedRate(
                                () -> send(ws, new JSONObject().put("type", "heartbeat")),
                                interval, interval, TimeUnit.SECONDS);
                    }
                    case "command" -> {
                        long cid = m.getLong("command_id");
                        send(ws, new JSONObject().put("type", "ack").put("command_id", cid));
                        StringBuilder msg = new StringBuilder();
                        int rc = execute(m.optString("code"), m.optJSONObject("params", new JSONObject()), msg);
                        send(ws, new JSONObject().put("type", "result").put("command_id", cid).put("code", rc)
                                .put("message", msg.toString()));
                    }
                    case "auth_failed" -> {
                        authCode[0] = m.optInt("code");
                        System.out.println("鉴权失败 " + authCode[0] + "：" + m.optString("message"));
                    }
                    default -> { }
                }
            }

            @Override
            public CompletionStage<?> onClose(WebSocket ws, int statusCode, String reason) {
                closed.complete(authCode[0] != 0 ? authCode[0] : statusCode);
                return null;
            }

            @Override
            public void onError(WebSocket ws, Throwable error) {
                System.out.println("连接错误：" + error);
                closed.complete(authCode[0]);
            }
        };

        try {
            http.newWebSocketBuilder().buildAsync(URI.create(buildUrl()), listener).join();
            return closed.join();
        } finally {
            if (heartbeat[0] != null) heartbeat[0].cancel(false);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 3) {
            System.err.println("用法：java -jar device-client.jar <平台地址> <设备编号> <接入Key> [当前版本]");
            System.exit(1);
        }
        server = args[0];
        deviceId = args[1];
        key = args[2];
        if (args.length > 3) version = args[3];
        HttpClient http = HttpClient.newHttpClient();
        int backoff = 1;
        while (true) {
            int code;
            try {
                code = runSession(http);
            } catch (Exception e) {
                System.out.println("连接失败：" + e.getMessage());
                code = 0;
            }
            // 4401 Key 错误 / 4403 未生成 Key：60 秒后再试；4000 被新连接顶替：立即重连；其余指数退避
            backoff = (code == 4401 || code == 4403) ? 60 : (code == 4000 ? 1 : Math.min(backoff * 2, 60));
            System.out.println("连接关闭（" + code + "），" + backoff + "s 后重连");
            Thread.sleep(backoff * 1000L);
        }
    }
}
