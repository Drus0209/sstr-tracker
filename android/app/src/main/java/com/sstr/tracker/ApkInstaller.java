package com.sstr.tracker;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import androidx.core.content.FileProvider;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

@CapacitorPlugin(name = "ApkInstaller")
public class ApkInstaller extends Plugin {

    @PluginMethod
    public void downloadAndInstall(PluginCall call) {
        final String url = call.getString("url");
        if (url == null) { call.reject("URL required"); return; }

        new Thread(() -> {
            try {
                Context ctx = getContext();
                File dir = ctx.getExternalFilesDir(null);
                if (dir == null) dir = ctx.getFilesDir();
                File apk = new File(dir, "update.apk");
                if (apk.exists()) apk.delete();

                HttpURLConnection con = (HttpURLConnection) new URL(url).openConnection();
                con.setRequestProperty("X-API-Key", "sstr2026_k4w4s4k1_zx4r");
                con.setConnectTimeout(15000);
                con.setReadTimeout(60000);
                int total = con.getContentLength();
                InputStream is = con.getInputStream();
                FileOutputStream fos = new FileOutputStream(apk);
                byte[] buf = new byte[8192];
                int n, downloaded = 0, lastPct = -1;
                while ((n = is.read(buf)) > 0) {
                    fos.write(buf, 0, n);
                    downloaded += n;
                    if (total > 0) {
                        int pct = (int)((long)downloaded * 100 / total);
                        if (pct != lastPct) {
                            lastPct = pct;
                            JSObject ev = new JSObject();
                            ev.put("progress", pct);
                            ev.put("downloaded", downloaded);
                            ev.put("total", total);
                            notifyListeners("progress", ev);
                        }
                    }
                }
                fos.close(); is.close();

                Uri uri;
                if (Build.VERSION.SDK_INT >= 24) {
                    uri = FileProvider.getUriForFile(ctx, ctx.getPackageName() + ".fileprovider", apk);
                } else {
                    uri = Uri.fromFile(apk);
                }

                Intent intent = new Intent(Intent.ACTION_VIEW);
                intent.setDataAndType(uri, "application/vnd.android.package-archive");
                intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_GRANT_READ_URI_PERMISSION);
                ctx.startActivity(intent);

                JSObject result = new JSObject();
                result.put("ok", true);
                result.put("path", apk.getAbsolutePath());
                call.resolve(result);
            } catch (Exception e) {
                call.reject("Install failed: " + e.getMessage());
            }
        }).start();
    }
}
