package com.sstr.tracker;

import android.content.Context;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Build;
import com.getcapacitor.JSObject;
import java.io.File;
import java.io.FileOutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * Audio Focus management plugin.
 * Allows the WebView audio to coexist with other media apps (Amazon Music, etc.)
 * by requesting AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK with USAGE_ASSISTANCE_NAVIGATION_GUIDANCE.
 */
@CapacitorPlugin(name = "AudioFocus")
public class AudioFocusPlugin extends Plugin {
    private AudioManager audioManager;
    private AudioFocusRequest focusRequest;
    private MediaPlayer currentPlayer;
    private String currentToken;
    private MediaPlayer bgmPlayer;

    @Override
    public void load() {
        audioManager = (AudioManager) getContext().getSystemService(Context.AUDIO_SERVICE);
        // 起動時の auto focus 取得は撤去（他アプリの再生を阻害するため）
        // JS から requestNavFocus() を音声再生時のみ呼ぶ運用に切替
    }

    private void requestNavFocusInternal() {
        if (audioManager == null) return;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            AudioAttributes attrs = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build();
            focusRequest = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
                .setAudioAttributes(attrs)
                .setOnAudioFocusChangeListener(focusChange -> {
                    // 他アプリへの一時譲渡や復帰イベント。WebView audio は自動継続なので何もしない
                })
                .setWillPauseWhenDucked(false)
                .build();
            audioManager.requestAudioFocus(focusRequest);
        } else {
            audioManager.requestAudioFocus(
                focusChange -> {},
                AudioManager.STREAM_MUSIC,
                AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK
            );
        }
    }

    @PluginMethod
    public void requestNavFocus(PluginCall call) {
        requestNavFocusInternal();
        call.resolve();
    }

    @PluginMethod
    public void play(PluginCall call) {
        final String url = call.getString("url");
        final String token = call.getString("token", String.valueOf(System.currentTimeMillis()));
        final Float volume = call.getFloat("volume", 1.0f);
        if (url == null || url.isEmpty()) {
            call.reject("url required");
            return;
        }
        new Thread(() -> {
            try {
                String localPath = resolveUrl(url);
                getActivity().runOnUiThread(() -> startMediaPlayer(localPath, token, volume));
                JSObject ret = new JSObject();
                ret.put("token", token);
                call.resolve(ret);
            } catch (Exception e) {
                JSObject ev = new JSObject();
                ev.put("token", token);
                ev.put("error", "resolve_failed: " + e.getMessage());
                notifyListeners("playError", ev);
                call.reject(e.getMessage() != null ? e.getMessage() : "resolve failed");
            }
        }).start();
    }

    private String resolveUrl(String urlStr) throws Exception {
        // localhost URL（Capacitor asset）は assets から cache にコピー→ローカルパス返却
        if (urlStr.contains("://localhost/") || urlStr.contains("://10.0.2.2/")) {
            int idx = urlStr.indexOf("://");
            String afterScheme = urlStr.substring(idx + 3);
            int slash = afterScheme.indexOf('/');
            String assetPath = "public" + (slash >= 0 ? afterScheme.substring(slash) : "/");
            // クエリパラメータ除去
            int q = assetPath.indexOf('?');
            if (q >= 0) assetPath = assetPath.substring(0, q);
            return copyAssetToCache(assetPath).getAbsolutePath();
        }
        // それ以外（NAS等）は HTTP DL してキャッシュ
        return downloadToCache(urlStr).getAbsolutePath();
    }

    private File copyAssetToCache(String assetPath) throws Exception {
        File cacheDir = new File(getContext().getCacheDir(), "audio_focus_plugin");
        if (!cacheDir.exists()) cacheDir.mkdirs();
        String tail = assetPath.substring(assetPath.lastIndexOf('/') + 1);
        File outFile = new File(cacheDir, "asset_" + Math.abs(assetPath.hashCode()) + "_" + tail);
        if (outFile.exists() && outFile.length() > 0) return outFile;
        try (java.io.InputStream is = getContext().getAssets().open(assetPath); FileOutputStream os = new FileOutputStream(outFile)) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = is.read(buf)) > 0) os.write(buf, 0, n);
        }
        return outFile;
    }

    private File downloadToCache(String urlStr) throws Exception {
        File cacheDir = new File(getContext().getCacheDir(), "audio_focus_plugin");
        if (!cacheDir.exists()) cacheDir.mkdirs();
        String fname = "p_" + Math.abs(urlStr.hashCode()) + ".tmp";
        File outFile = new File(cacheDir, fname);
        // 既存キャッシュは再利用（同URLの再ダウンロード回避）
        if (outFile.exists() && outFile.length() > 0) return outFile;
        URL url = new URL(urlStr);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setConnectTimeout(10000);
        conn.setReadTimeout(15000);
        conn.setInstanceFollowRedirects(true);
        conn.setRequestProperty("X-API-Key", "sstr2026_k4w4s4k1_zx4r");
        conn.connect();
        int code = conn.getResponseCode();
        if (code != 200) throw new Exception("HTTP " + code);
        try (java.io.InputStream is = conn.getInputStream(); FileOutputStream os = new FileOutputStream(outFile)) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = is.read(buf)) > 0) os.write(buf, 0, n);
        }
        conn.disconnect();
        return outFile;
    }

    private void startMediaPlayer(String localPath, String token, Float volume) {
        try {
            stopCurrentInternal();
            final MediaPlayer mp = new MediaPlayer();
            currentPlayer = mp;
            currentToken = token;
            AudioAttributes attrs = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build();
            mp.setAudioAttributes(attrs);
            mp.setVolume(volume, volume);
            mp.setDataSource(localPath);
            mp.setOnPreparedListener(p -> p.start());
            mp.setOnCompletionListener(p -> {
                JSObject ev = new JSObject();
                ev.put("token", token);
                ev.put("ended", true);
                notifyListeners("playEnded", ev);
                if (currentPlayer == p) { currentPlayer = null; currentToken = null; }
                p.release();
            });
            mp.setOnErrorListener((p, what, extra) -> {
                JSObject ev = new JSObject();
                ev.put("token", token);
                ev.put("error", "what=" + what + " extra=" + extra);
                notifyListeners("playError", ev);
                if (currentPlayer == p) { currentPlayer = null; currentToken = null; }
                p.release();
                return true;
            });
            mp.prepareAsync();
        } catch (Exception e) {
            JSObject ev = new JSObject();
            ev.put("token", token);
            ev.put("error", e.getMessage() != null ? e.getMessage() : "start failed");
            notifyListeners("playError", ev);
        }
    }

    @PluginMethod
    public void stop(PluginCall call) {
        stopCurrentInternal();
        call.resolve();
    }

    private void stopCurrentInternal() {
        if (currentPlayer != null) {
            try { if (currentPlayer.isPlaying()) currentPlayer.stop(); } catch (Exception ignored) {}
            try { currentPlayer.release(); } catch (Exception ignored) {}
            currentPlayer = null;
            currentToken = null;
        }
    }

    @PluginMethod
    public void playBgm(PluginCall call) {
        final String url = call.getString("url");
        final Float volume = call.getFloat("volume", 0.15f);
        if (url == null || url.isEmpty()) { call.reject("url required"); return; }
        new Thread(() -> {
            try {
                String localPath = resolveUrl(url);
                getActivity().runOnUiThread(() -> startBgmPlayer(localPath, volume));
                call.resolve();
            } catch (Exception e) {
                call.reject(e.getMessage() != null ? e.getMessage() : "bgm play failed");
            }
        }).start();
    }

    private void startBgmPlayer(String localPath, Float volume) {
        try {
            stopBgmInternal();
            final MediaPlayer mp = new MediaPlayer();
            bgmPlayer = mp;
            AudioAttributes attrs = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                .build();
            mp.setAudioAttributes(attrs);
            mp.setVolume(volume, volume);
            mp.setLooping(true);
            mp.setDataSource(localPath);
            mp.setOnPreparedListener(p -> p.start());
            mp.setOnErrorListener((p, what, extra) -> {
                if (bgmPlayer == p) bgmPlayer = null;
                p.release();
                return true;
            });
            mp.prepareAsync();
        } catch (Exception ignored) {}
    }

    @PluginMethod
    public void stopBgm(PluginCall call) {
        stopBgmInternal();
        call.resolve();
    }

    @PluginMethod
    public void setBgmVolume(PluginCall call) {
        Float v = call.getFloat("volume", 0.15f);
        if (bgmPlayer != null) {
            try { bgmPlayer.setVolume(v, v); } catch (Exception ignored) {}
        }
        call.resolve();
    }

    private void stopBgmInternal() {
        if (bgmPlayer != null) {
            try { if (bgmPlayer.isPlaying()) bgmPlayer.stop(); } catch (Exception ignored) {}
            try { bgmPlayer.release(); } catch (Exception ignored) {}
            bgmPlayer = null;
        }
    }

    @PluginMethod
    public void isMusicActive(PluginCall call) {
        boolean active = false;
        if (audioManager != null) {
            try { active = audioManager.isMusicActive(); } catch (Exception ignored) {}
        }
        JSObject ret = new JSObject();
        ret.put("active", active);
        call.resolve(ret);
    }

    @PluginMethod
    public void abandonFocus(PluginCall call) {
        if (audioManager != null) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && focusRequest != null) {
                audioManager.abandonAudioFocusRequest(focusRequest);
                focusRequest = null;
            } else {
                audioManager.abandonAudioFocus(focusChange -> {});
            }
        }
        call.resolve();
    }
}
