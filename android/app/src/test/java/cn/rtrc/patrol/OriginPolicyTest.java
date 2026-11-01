package cn.rtrc.patrol;

import org.junit.Test;
import static org.junit.Assert.*;

public class OriginPolicyTest {
    @Test public void normalizesHotspotAddressWithoutHardcodingNetwork() {
        assertEquals("http://10.212.93.243:8765/", OriginPolicy.normalize("10.212.93.243"));
        assertEquals("http://192.168.43.5:8765/", OriginPolicy.normalize(" http://192.168.43.5:8765/ "));
        assertEquals("https://172.16.1.2:443/", OriginPolicy.normalize("https://172.16.1.2:443"));
    }
    @Test public void rejectsMalformedPublicAndCredentialBearingDestinations() {
        for (String url : new String[]{"", "example.com", "8.8.8.8", "127.0.0.1", "10.999.1.2",
                "10.01.1.2", "10.1.1.2:0", "10.1.1.2:65536", "http://user:pass@10.1.1.2/",
                "10.1.1.2/other", "10.1.1.2/?token=bad", "10.1.1.2/#other", "file:///etc/passwd"}) {
            try { OriginPolicy.normalize(url); fail("Accepted: " + url); }
            catch (IllegalArgumentException expected) { /* expected */ }
        }
    }
    @Test public void cannotNavigateToAnotherOriginOrUseSchemeTricks() {
        String origin = "http://10.1.1.2:8765/";
        assertTrue(OriginPolicy.sameOrigin(origin, origin + "api/tasks"));
        assertTrue(OriginPolicy.resourceAllowed(origin, "blob:http://10.1.1.2:8765/a-camera-frame"));
        for (String url : new String[]{"http://10.1.1.3:8765/", "https://10.1.1.2:8765/", "http://10.1.1.2/",
                "http://10.1.1.2:8765@evil.example/", "file:///tmp/a", "javascript:alert(1)",
                "data:text/html,test", "intent://anything", "blob:https://evil.example/a", null}) {
            assertFalse(String.valueOf(url), OriginPolicy.resourceAllowed(origin, url));
        }
    }
}
