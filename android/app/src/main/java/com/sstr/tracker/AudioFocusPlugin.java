package com.sstr.tracker;

import android.content.Context;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.os.Build;
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
