package sk.hofitech.smartmic.tf220;

import android.app.Activity;
import android.os.Bundle;
import android.content.Intent;
import android.graphics.Color;
import android.webkit.WebChromeClient;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebSettings;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient.FileChooserParams;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Button;

public class MainActivity extends Activity {
    private static final String URL = "https://smartmic-tf220-flow.onrender.com";
    private static final int PICK_FILE = 9001;
    private WebView web;
    private ValueCallback<android.net.Uri[]> pendingFiles;

    @Override public void onCreate(Bundle b) {
        super.onCreate(b);
        web = new WebView(this);
        web.setBackgroundColor(Color.rgb(242,246,248));
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.setWebViewClient(new WebViewClient() {
           @Override public boolean shouldOverrideUrlLoading(WebView view, android.webkit.WebResourceRequest req) {
              if("smartmic-tf220-flow.onrender.com".equals(req.getUrl().getHost())) return false;
              return true;
           }
        });
        web.setWebChromeClient(new WebChromeClient() {
           @Override public boolean onShowFileChooser(WebView view, ValueCallback<android.net.Uri[]> cb, FileChooserParams params) {
              if(pendingFiles!=null) pendingFiles.onReceiveValue(null);
              pendingFiles=cb;
              try {
                  Intent intent=params.createIntent();
                  intent.addCategory(Intent.CATEGORY_OPENABLE);
                  startActivityForResult(intent, PICK_FILE);
                  return true;
              } catch(Exception e) {
                  pendingFiles=null;
                  cb.onReceiveValue(null);
                  return false;
              }
           }
        });
        setContentView(web);
        web.loadUrl(URL);
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
       super.onActivityResult(requestCode, resultCode, data);
       if(requestCode!=PICK_FILE||pendingFiles==null) return;
       android.net.Uri[] uris=FileChooserParams.parseResult(resultCode,data);
       pendingFiles.onReceiveValue(uris);
       pendingFiles=null;
    }
    @Override public void onBackPressed() {
       if(web!=null && web.canGoBack()) web.goBack();
       else super.onBackPressed();
    }
    @Override protected void onDestroy() {
       if(pendingFiles!=null) pendingFiles.onReceiveValue(null);
       if(web!=null){web.destroy();web=null;}
       super.onDestroy();
    }
}
