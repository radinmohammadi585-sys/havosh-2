/** Kavosh AI 2 Java Bridge Service (Bridge X / G). Line JSON over TCP. */
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;

public class KavoshJavaBridge {
    static final int PORT = 9102;

    static String extract(String s, String key) {
        String k = "\"" + key + "\"";
        int p = s.indexOf(k);
        if (p < 0) return "";
        p = s.indexOf(':', p);
        if (p < 0) return "";
        p = s.indexOf('"', p);
        if (p < 0) return "";
        int e = s.indexOf('"', p + 1);
        if (e < 0) return "";
        return s.substring(p + 1, e);
    }

    static String handle(String line) {
        String rid = extract(line, "request_id");
        if (rid.isEmpty()) rid = "unknown";
        String intent = extract(line, "intent");
        long ts = System.currentTimeMillis();
        return "{\"ok\":true,\"request_id\":\"" + rid
            + "\",\"service\":\"java\",\"bridge\":\"X\","
            + "\"payload\":{\"engine\":\"kavosh-java\",\"intent\":\"" + intent
            + "\",\"ts\":" + ts
            + ",\"note\":\"Java bridge live\"}}";
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket server = new ServerSocket(PORT)) {
            System.err.println("[kavosh-java] listening on " + PORT);
            while (true) {
                try (Socket sock = server.accept();
                     BufferedReader in = new BufferedReader(new InputStreamReader(sock.getInputStream(), StandardCharsets.UTF_8));
                     BufferedWriter out = new BufferedWriter(new OutputStreamWriter(sock.getOutputStream(), StandardCharsets.UTF_8))) {
                    String line = in.readLine();
                    if (line == null) continue;
                    String resp = handle(line);
                    out.write(resp);
                    out.write("\n");
                    out.flush();
                } catch (Exception e) {
                    System.err.println("[kavosh-java] client error: " + e.getMessage());
                }
            }
        }
    }
}
