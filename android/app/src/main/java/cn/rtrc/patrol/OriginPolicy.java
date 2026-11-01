package cn.rtrc.patrol;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

/** User-entered rover origin. Never follows links/redirects to another host. */
public final class OriginPolicy {
    private OriginPolicy() {}

    public static String normalize(String input) {
        String value = input == null ? "" : input.trim();
        if (!value.contains("://")) value = "http://" + value;
        try {
            URI uri = new URI(value);
            String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
            String host = uri.getHost();
            if (!(scheme.equals("http") || scheme.equals("https")) || !privateIpv4(host)
                    || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null
                    || !(uri.getPath().isEmpty() || uri.getPath().equals("/"))) {
                throw new IllegalArgumentException("请输入小车的局域网 IPv4 地址，不要包含密码或页面路径");
            }
            int port = uri.getPort() == -1 ? 8765 : uri.getPort();
            if (port < 1 || port > 65535) throw new IllegalArgumentException("端口应为 1–65535");
            return scheme + "://" + host + ":" + port + "/";
        } catch (URISyntaxException | NullPointerException error) {
            throw new IllegalArgumentException("地址格式错误，例如 10.212.93.243:8765");
        }
    }

    static boolean privateIpv4(String host) {
        if (host == null || !host.matches("[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+")) return false;
        String[] parts = host.split("\\.");
        int[] n = new int[4];
        try {
            for (int i = 0; i < 4; i++) {
                if (parts[i].length() > 1 && parts[i].charAt(0) == '0') return false;
                n[i] = Integer.parseInt(parts[i]);
                if (n[i] < 0 || n[i] > 255) return false;
            }
        } catch (NumberFormatException error) { return false; }
        return n[0] == 10 || (n[0] == 192 && n[1] == 168)
                || (n[0] == 172 && n[1] >= 16 && n[1] <= 31);
    }

    public static boolean sameOrigin(String origin, String url) {
        if (origin == null || url == null) return false;
        try {
            URI a = new URI(origin), b = new URI(url);
            return a.getScheme().equalsIgnoreCase(b.getScheme())
                    && a.getHost().equalsIgnoreCase(b.getHost()) && port(a) == port(b)
                    && b.getUserInfo() == null;
        } catch (URISyntaxException | NullPointerException error) { return false; }
    }

    private static int port(URI uri) {
        return uri.getPort() >= 0 ? uri.getPort() : "https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80;
    }

    public static boolean resourceAllowed(String origin, String url) {
        // Object URLs are used by the existing camera preview.
        if (url != null && url.startsWith("blob:")) return sameOrigin(origin, url.substring(5));
        return sameOrigin(origin, url);
    }
}
