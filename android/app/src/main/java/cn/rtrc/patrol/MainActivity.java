package cn.rtrc.patrol;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.res.Configuration;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/** Lightweight same-origin client; the rover remains the source of truth. */
public final class MainActivity extends Activity {
    private int BG, PANEL, TEXT, MUTED, ACCENT;
    private static final int PICK_PHOTO = 41;
    private static final int MAX_PHOTO_BYTES = 10 * 1024 * 1024;
    // Same stop() used by the real workbench. No JS-to-Java bridge is exposed.
    private static final String STOP_JS = "(function(){try{"
            + "let active=(typeof lease!=='undefined'&&lease)||(typeof routeWatchToken!=='undefined'&&routeWatchToken);"
            + "if(active&&typeof stop==='function'){stop();}"
            + "if(typeof heldKeys!=='undefined'){heldKeys.clear();}"
            + "if(typeof lease!=='undefined'){lease=null;}"
            + "if(typeof routeWatchToken!=='undefined'){routeWatchToken=null;}"
            + "return true;}catch(e){return false;}})()";

    private final ExecutorService io = Executors.newFixedThreadPool(2);
    private final AtomicBoolean stopInFlight = new AtomicBoolean(false);
    private WebView web;
    private FrameLayout content;
    private LinearLayout connectPanel;
    private ScrollView connectionSurface;
    private EditText addressInput;
    private TextView toolbarAddress, connectionHint;
    private ProgressBar loading;
    private String origin;
    private boolean foreground, loaded, suspended;
    private String appStyle = "";
    private ValueCallback<Uri[]> photoCallback;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        BG = getColor(R.color.app_background); PANEL = getColor(R.color.app_surface);
        TEXT = getColor(R.color.app_text); MUTED = getColor(R.color.app_secondary); ACCENT = getColor(R.color.app_accent);
        try (InputStream input = getAssets().open("apple-workbench.css")) {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096]; int count;
            while ((count = input.read(buffer)) != -1) bytes.write(buffer, 0, count);
            appStyle = bytes.toString("UTF-8");
        } catch (java.io.IOException ignored) { /* Existing workbench remains usable. */ }
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL); root.setBackgroundColor(BG);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                    insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets;
        });
        setContentView(root);
        LinearLayout bar = new LinearLayout(this);
        bar.setGravity(Gravity.CENTER_VERTICAL); bar.setPadding(dp(16), dp(8), dp(8), dp(8));
        bar.setBackgroundColor(BG);
        toolbarAddress = text("巡检工作台", 12, MUTED);
        toolbarAddress.setSingleLine(true); toolbarAddress.setEllipsize(android.text.TextUtils.TruncateAt.END);
        bar.addView(toolbarAddress, new LinearLayout.LayoutParams(0, dp(48), 1));
        Button change = button("地址", false); change.setContentDescription("修改小车地址");
        change.setOnClickListener(v -> showConnection("输入当前热点下的小车 IP。")); bar.addView(change);
        Button reload = button("刷新", false);
        reload.setOnClickListener(v -> { requestStop(false); if (origin != null) loadWorkbench(); });
        bar.addView(reload);
        Button stop = button("停止", false);
        stop.setTextColor(getColor(R.color.app_on_stop)); stop.setBackground(buttonSurface(getColor(R.color.app_stop)));
        stop.setOnClickListener(v -> requestStop(true)); bar.addView(stop);
        root.addView(bar, new LinearLayout.LayoutParams(-1, dp(64)));
        loading = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        loading.setMax(100); loading.setVisibility(View.GONE);
        root.addView(loading, new LinearLayout.LayoutParams(-1, dp(3)));
        content = new FrameLayout(this); root.addView(content, new LinearLayout.LayoutParams(-1, 0, 1));
        buildWebView(); buildConnectionPanel();
        if (Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(0, this::back);
        }
        showConnection("手机与小车连接同一热点。使用原工作台账号登录。");
    }

    @SuppressLint("SetJavaScriptEnabled") // Existing first-party workbench requires JS.
    private void buildWebView() {
        web = new WebView(this); web.setBackgroundColor(BG);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true); settings.setDomStorageEnabled(true);
        settings.setTextZoom(Math.round(100 * getResources().getConfiguration().fontScale));
        settings.setAllowFileAccess(false); settings.setAllowContentAccess(true); // Selected photo provider only.
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setJavaScriptCanOpenWindowsAutomatically(false); settings.setSupportMultipleWindows(false);
        settings.setGeolocationEnabled(false); settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                boolean allowed = OriginPolicy.sameOrigin(origin, request.getUrl().toString());
                if (!allowed) toast("仅允许打开已设置的小车工作台");
                return !allowed;
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                if (OriginPolicy.resourceAllowed(origin, request.getUrl().toString())) return null;
                return new WebResourceResponse("text/plain", "UTF-8", 403, "Blocked",
                        Collections.emptyMap(), new ByteArrayInputStream(new byte[0]));
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (!OriginPolicy.sameOrigin(origin, url)) return;
                boolean dark = (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
                        == Configuration.UI_MODE_NIGHT_YES;
                String script = "(function(){document.documentElement.classList.add('patrol-apple');"
                        + "document.documentElement.dataset.appearance='" + (dark ? "dark" : "light") + "';"
                        + "let s=document.getElementById('native-app-style');if(!s){s=document.createElement('style');"
                        + "s.id='native-app-style';document.head.append(s);}s.textContent=" + JSONObject.quote(appStyle) + ";})()";
                view.evaluateJavascript(script, null);
                loaded = true; CookieManager.getInstance().flush();
                if (foreground && connectionSurface.getVisibility() != View.VISIBLE) web.setVisibility(View.VISIBLE);
                loading.setVisibility(View.GONE);
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) runOnUiThread(() -> showConnection("连接失败。检查小车供电、热点与 IP 后重试。"));
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse error) {
                if (request.isForMainFrame()) runOnUiThread(() -> showConnection("工作台返回错误，请核对地址或稍后重新连接。"));
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public void onProgressChanged(WebView view, int progress) {
                loading.setProgress(progress); loading.setVisibility(progress < 100 ? View.VISIBLE : View.GONE);
            }
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (photoCallback != null) photoCallback.onReceiveValue(null);
                photoCallback = callback;
                // Stop first; selecting a photo must never leave a route running.
                requestStop(false);
                Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("image/*")
                        .addCategory(Intent.CATEGORY_OPENABLE).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                try { startActivityForResult(picker, PICK_PHOTO); }
                catch (ActivityNotFoundException error) { cancelPhoto(); toast("未找到图片选择器，请使用系统浏览器上传"); }
                return true;
            }
        });
        content.addView(web, new FrameLayout.LayoutParams(-1, -1)); web.setVisibility(View.GONE);
    }

    private void buildConnectionPanel() {
        connectPanel = new LinearLayout(this); connectPanel.setOrientation(LinearLayout.VERTICAL);
        connectPanel.setGravity(Gravity.CENTER_VERTICAL); connectPanel.setPadding(dp(24), dp(24), dp(24), dp(32));
        connectPanel.setBackgroundColor(BG);
        TextView label = text("RTRC 4PRO · 巡检", 13, MUTED);
        connectPanel.addView(label);
        TextView title = text("连接巡检小车", 32, TEXT); title.setTypeface(null, Typeface.BOLD);
        LinearLayout.LayoutParams titleLayout = new LinearLayout.LayoutParams(-1, -2);
        titleLayout.setMargins(0, dp(16), 0, dp(10)); connectPanel.addView(title, titleLayout);
        connectionHint = text("", 17, MUTED); connectPanel.addView(connectionHint);
        addressInput = new EditText(this); addressInput.setSingleLine(true); addressInput.setTextColor(TEXT);
        addressInput.setHintTextColor(MUTED); addressInput.setTextSize(17);
        addressInput.setHint("例如 10.212.93.243:8765"); addressInput.setContentDescription("小车工作台地址");
        addressInput.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        addressInput.setBackground(background(PANEL, 12)); addressInput.setPadding(dp(15), dp(12), dp(15), dp(12));
        LinearLayout.LayoutParams addressLayout = new LinearLayout.LayoutParams(-1, -2); addressInput.setMinHeight(dp(56));
        addressLayout.setMargins(0, dp(24), 0, dp(14)); connectPanel.addView(addressInput, addressLayout);
        Button connect = button("连接工作台", true);
        connect.setOnClickListener(v -> {
            try {
                String next = OriginPolicy.normalize(addressInput.getText().toString());
                requestStop(false); origin = next;
                getPreferences(MODE_PRIVATE).edit().putString("rover_origin", next).apply();
                loadWorkbench();
            } catch (IllegalArgumentException error) { addressInput.setError(error.getMessage()); }
        });
        connectPanel.addView(connect, new LinearLayout.LayoutParams(-1, dp(56)));
        Button logout = button("退出登录", false);
        logout.setOnClickListener(v -> {
            requestStop(false);
            CookieManager.getInstance().removeAllCookies(ignored -> {
                CookieManager.getInstance().flush(); web.clearHistory();
                showConnection("登录已退出。连接工作台后可重新登录。");
            });
        });
        LinearLayout.LayoutParams logoutLayout = new LinearLayout.LayoutParams(-1, dp(52));
        logoutLayout.setMargins(0, dp(12), 0, 0); connectPanel.addView(logout, logoutLayout);
        TextView note = text("换热点后可修改地址。APP 不保存明文密码。\n切后台、选照片或离开控制页会停止控制；返回后需重新使能。", 13, MUTED);
        LinearLayout.LayoutParams noteLayout = new LinearLayout.LayoutParams(-1, -2);
        noteLayout.setMargins(0, dp(20), 0, 0); connectPanel.addView(note, noteLayout);
        connectionSurface = new ScrollView(this); connectionSurface.setFillViewport(true);
        connectionSurface.addView(connectPanel, new ScrollView.LayoutParams(-1, -1));
        content.addView(connectionSurface, new FrameLayout.LayoutParams(-1, -1));
        addressInput.setText(getPreferences(MODE_PRIVATE).getString("rover_origin", ""));
    }

    private void showConnection(String hint) {
        requestStop(false); loaded = false;
        if (web != null) { web.stopLoading(); web.pauseTimers(); web.setVisibility(View.GONE); }
        loading.setVisibility(View.GONE); connectionSurface.setVisibility(View.VISIBLE); connectionHint.setText(hint);
        toolbarAddress.setText("巡检工作台 · 未连接");
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }

    private void loadWorkbench() {
        loaded = false; suspended = false; connectionSurface.setVisibility(View.GONE);
        toolbarAddress.setText(Uri.parse(origin).getAuthority()); web.setVisibility(View.VISIBLE);
        web.onResume(); web.resumeTimers(); loading.setVisibility(View.VISIBLE);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        web.loadUrl(origin); // New document never carries a driving lease across reloads.
    }

    @Override protected void onPause() {
        foreground = false; suspended = true;
        requestStop(false);
        web.setVisibility(View.INVISIBLE); web.pauseTimers(); web.onPause();
        CookieManager.getInstance().flush();
        super.onPause();
    }

    @Override protected void onResume() {
        super.onResume(); foreground = true;
        if (web == null) return;
        if (connectionSurface.getVisibility() == View.VISIBLE) { web.pauseTimers(); return; }
        web.onResume();
        if (suspended && loaded && OriginPolicy.sameOrigin(origin, web.getUrl())) {
            // Preserve task form/photo input while clearing all old control state
            // before timers resume. onPause() alone does NOT pause JavaScript.
            web.evaluateJavascript(STOP_JS, ignored -> {
                if (!foreground || isFinishing()) return;
                if (!"true".equals(ignored)) { loadWorkbench(); return; }
                suspended = false; web.resumeTimers();
                if (connectionSurface.getVisibility() != View.VISIBLE) web.setVisibility(View.VISIBLE);
            });
        } else { web.resumeTimers(); }
    }

    private void requestStop(boolean notify) {
        if (web == null || origin == null) { if (notify) toast("尚未连接小车"); return; }
        if (OriginPolicy.sameOrigin(origin, web.getUrl())) web.evaluateJavascript(STOP_JS, null);
        final String endpoint = origin, cookie = CookieManager.getInstance().getCookie(origin);
        if (cookie == null || cookie.isEmpty()) { if (notify) toast("尚未登录，无法发送停车请求"); return; }
        if (!stopInFlight.compareAndSet(false, true)) return;
        io.execute(() -> {
            String message;
            try {
                JSONObject session = new JSONObject(http(endpoint + "api/session", "GET", cookie, null));
                JSONObject control = new JSONObject(http(endpoint + "api/robot/control/stop", "POST", cookie, session.getString("csrf")));
                message = !control.optBoolean("enabled", true) ? "控制已停止，请确认现场已停车" : "停车未获确认，请现场停车";
            } catch (Exception error) { message = "停车请求未获确认；请现场确认停车及热点连接"; }
            finally { stopInFlight.set(false); }
            final String result = message;
            if (notify) runOnUiThread(() -> toast(result));
        });
    }

    private static String http(String endpoint, String method, String cookie, String csrf) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(endpoint).openConnection();
        connection.setConnectTimeout(800); connection.setReadTimeout(1200); connection.setInstanceFollowRedirects(false);
        connection.setRequestMethod(method); connection.setRequestProperty("Cookie", cookie);
        connection.setRequestProperty("Cache-Control", "no-store");
        try {
            if (csrf != null) {
                connection.setRequestProperty("X-CSRF-Token", csrf);
                connection.setRequestProperty("Content-Type", "application/json"); connection.setDoOutput(true);
                try (java.io.OutputStream out = connection.getOutputStream()) { out.write("{}".getBytes(StandardCharsets.UTF_8)); }
            }
            if (connection.getResponseCode() != 200) throw new java.io.IOException("Request not confirmed");
            try (InputStream stream = connection.getInputStream(); ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[4096]; int count;
                while ((count = stream.read(buffer)) != -1) {
                    if (bytes.size() + count > 65536) throw new java.io.IOException("Response too large");
                    bytes.write(buffer, 0, count);
                }
                return bytes.toString("UTF-8");
            }
        } finally { connection.disconnect(); }
    }

    @Override protected void onActivityResult(int code, int result, Intent data) {
        super.onActivityResult(code, result, data);
        if (code != PICK_PHOTO || photoCallback == null) return;
        ValueCallback<Uri[]> callback = photoCallback; photoCallback = null;
        Uri uri = result == RESULT_OK && data != null ? data.getData() : null;
        if (uri == null) { callback.onReceiveValue(null); return; }
        io.execute(() -> {
            boolean allowed = false;
            try {
                String mime = getContentResolver().getType(uri);
                if (!"content".equals(uri.getScheme()) || mime == null || !mime.startsWith("image/")) throw new java.io.IOException();
                // Count unknown-size cloud-provider photos too; never accept an
                // arbitrary file:// or app-private content URI returned by a picker.
                if (getPackageName().equals(uri.getAuthority())) throw new java.io.IOException();
                try (InputStream input = getContentResolver().openInputStream(uri)) {
                    if (input == null) throw new java.io.IOException();
                    byte[] block = new byte[8192]; int total = 0, count;
                    while ((count = input.read(block)) != -1) {
                        total += count; if (total > MAX_PHOTO_BYTES) throw new java.io.IOException();
                    }
                    allowed = total > 0;
                }
            } catch (Exception ignored) { /* Picker cancellation/permission/size errors stay local. */ }
            final boolean accepted = allowed;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) { callback.onReceiveValue(null); return; }
                callback.onReceiveValue(accepted ? new Uri[]{uri} : null);
                if (!accepted) toast("请选择可读取的图片，单张不超过 10 MB");
            });
        });
    }

    private void cancelPhoto() { if (photoCallback != null) { photoCallback.onReceiveValue(null); photoCallback = null; } }
    private void back() { showConnection("已退出工作台。确认现场停车后，可重新连接。"); }
    @Override public void onBackPressed() { back(); }
    @Override protected void onDestroy() {
        cancelPhoto(); web.stopLoading(); web.destroy(); io.shutdown(); super.onDestroy();
    }
    private void toast(String value) { Toast.makeText(this, value, Toast.LENGTH_LONG).show(); }
    private TextView text(String value, float size, int color) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        view.setGravity(Gravity.CENTER_VERTICAL); view.setLineSpacing(dp(3), 1); return view;
    }
    private Button button(String value, boolean primary) {
        Button view = new Button(this); view.setText(value); view.setTextSize(12); view.setAllCaps(false);
        view.setTextColor(primary ? getColor(R.color.app_on_accent) : TEXT);
        view.setBackground(buttonSurface(primary ? ACCENT : PANEL)); view.setStateListAnimator(null);
        view.setElevation(0); view.setMinWidth(dp(49));
        view.setMinimumWidth(dp(49)); view.setPadding(dp(9), 0, dp(9), 0);
        view.setTextSize(15); view.setMinHeight(dp(48));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-2, dp(48));
        params.setMargins(dp(8), 0, 0, 0); view.setLayoutParams(params); return view;
    }
    private GradientDrawable background(int color, int radius) {
        GradientDrawable shape = new GradientDrawable(); shape.setColor(color); shape.setCornerRadius(dp(radius)); return shape;
    }
    private RippleDrawable buttonSurface(int color) {
        return new RippleDrawable(ColorStateList.valueOf(0x22000000), background(color, 12), background(Color.WHITE, 12));
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
