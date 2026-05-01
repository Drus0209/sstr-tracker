package com.sstr.tracker;

import android.content.Context;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.os.Build;
import com.getcapacitor.JSObject;
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
        String url = call.getString("url");
        String token = call.getString("token", String.valueOf(System.currentTimeMillis()));
        Float volume = call.getFloat("volume", 1.0f);
        if (url == null || url.isEmpty()) {
            call.reject("url required");
            return;
        }
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
            mp.setDataSource(url);
            mp.setOnPreparedListener(p -> p.start());
            mp.setOnCompletionListener(p -> {
                JSObject ev = new JSObject();
                ev.put("token", token);
                ev.put("ended", true);
                notifyListeners("playEnded", ev);
                if (currentPlayer == p) {
                    currentPlayer = null;
                    currentToken = null;
                }
                p.release();
            });
            mp.setOnErrorListener((p, what, extra) -> {
                JSObject ev = new JSObject();
                ev.put("token", token);
                ev.put("error", "what=" + what + " extra=" + extra);
                notifyListeners("playError", ev);
                if (currentPlayer == p) {
                    currentPlayer = null;
                    currentToken = null;
                }
                p.release();
                return true;
            });
            mp.prepareAsync();
            JSObject ret = new JSObject();
            ret.put("token", token);
            call.resolve(ret);
        } catch (Exception e) {
            call.reject(e.getMessage() != null ? e.getMessage() : "play failed");
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
