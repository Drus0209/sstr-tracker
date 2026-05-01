package com.sstr.tracker;

import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(ApkInstaller.class);
        registerPlugin(AudioFocusPlugin.class);
        super.onCreate(savedInstanceState);
        WebView webView = getBridge().getWebView();
        WebSettings settings = webView.getSettings();
        settings.setMediaPlaybackRequiresUserGesture(false);
    }

    @Override
    public void onBackPressed() {
        WebView webView = getBridge().getWebView();
        webView.evaluateJavascript("(function(){if(typeof _navPop==='function'&&_navPop())return 'popped';return 'empty';})()", value -> {
            if (value != null && value.contains("empty")) {
                moveTaskToBack(true);
            }
        });
    }
}
