package com.hofitech.smartmicforms;

import android.content.ContentResolver;
import android.content.ContentValues;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.graphics.pdf.PdfDocument;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

@CapacitorPlugin(name = "SmartMicNative")
public class SmartMicNativePlugin extends Plugin {
    private final Map<String, Transfer> transfers = new HashMap<>();

    private static class Transfer {
        final Uri uri;
        final File file;
        final OutputStream stream;
        long bytes;
        Transfer(Uri uri, File file, OutputStream stream) {
            this.uri = uri;
            this.file = file;
            this.stream = stream;
        }
    }

    private static String validName(String input) {
        if (input == null || input.trim().isEmpty()) throw new IllegalArgumentException("Prázdny názov súboru");
        String result = input.replaceAll("[^a-zA-Z0-9._-]", "_");
        if (result.equals(".") || result.equals("..")) throw new IllegalArgumentException("Neplatný názov súboru");
        return result.length() > 150 ? result.substring(result.length() - 150) : result;
    }

    private static String validMime(String mime) {
        if ("application/pdf".equals(mime) || "application/zip".equals(mime) ||
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document".equals(mime)) return mime;
        throw new IllegalArgumentException("Nepodporovaný formát: " + mime);
    }

    private Transfer openPublicFile(String name, String mime) throws IOException {
        String fileName = validName(name);
        validMime(mime);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ContentResolver resolver = getContext().getContentResolver();
            ContentValues values = new ContentValues();
            values.put(MediaStore.MediaColumns.DISPLAY_NAME, fileName);
            values.put(MediaStore.MediaColumns.MIME_TYPE, mime);
            values.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/SmartMic");
            values.put(MediaStore.MediaColumns.IS_PENDING, 1);
            Uri uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
            if (uri == null) throw new IOException("Nie je možné vytvoriť súbor v priečinku Downloads");
            OutputStream output = resolver.openOutputStream(uri, "w");
            if (output == null) { resolver.delete(uri, null, null); throw new IOException("Nie je možné otvoriť súbor"); }
            return new Transfer(uri, null, output);
        }
        File dir = new File(getContext().getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS), "SmartMic");
        if (!dir.exists() && !dir.mkdirs()) throw new IOException("Nie je možné vytvoriť priečinok SmartMic");
        File file = new File(dir, fileName);
        return new Transfer(null, file, new FileOutputStream(file));
    }

    private void complete(Transfer t) throws IOException {
        t.stream.flush();
        t.stream.close();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && t.uri != null) {
            ContentValues done = new ContentValues();
            done.put(MediaStore.MediaColumns.IS_PENDING, 0);
            getContext().getContentResolver().update(t.uri, done, null, null);
        }
    }

    private void discard(Transfer t) {
        try { t.stream.close(); } catch (Exception ignored) {}
        if (t.uri != null) getContext().getContentResolver().delete(t.uri, null, null);
        if (t.file != null) t.file.delete();
    }

    @PluginMethod
    public void beginFile(PluginCall call) {
        try {
            String name = validName(call.getString("fileName"));
            String mime = validMime(call.getString("mime"));
            Transfer transfer = openPublicFile(name, mime);
            String token = UUID.randomUUID().toString();
            synchronized (transfers) { transfers.put(token, transfer); }
            JSObject response = new JSObject(); response.put("token", token);
            call.resolve(response);
        } catch (Exception ex) { call.reject("Export neúspešný: " + ex.getMessage()); }
    }

    @PluginMethod
    public void appendChunk(PluginCall call) {
        String token = call.getString("token"), data = call.getString("data");
        Transfer transfer;
        synchronized (transfers) { transfer = transfers.get(token); }
        if (transfer == null || data == null) { call.reject("Neplatná exportná relácia"); return; }
        try {
            byte[] bytes = Base64.decode(data, Base64.DEFAULT);
            if (bytes.length > 512 * 1024) throw new IOException("Príliš veľký blok súboru");
            synchronized (transfer) { transfer.stream.write(bytes); transfer.bytes += bytes.length; }
            call.resolve();
        } catch (Exception ex) { call.reject("Zápis súboru zlyhal: " + ex.getMessage()); }
    }

    @PluginMethod
    public void finishFile(PluginCall call) {
        Transfer transfer;
        synchronized (transfers) { transfer = transfers.remove(call.getString("token")); }
        if (transfer == null) { call.reject("Exportná relácia neexistuje"); return; }
        try {
            complete(transfer);
            JSObject response = new JSObject();
            response.put("uri", transfer.uri == null ? transfer.file.getAbsolutePath() : transfer.uri.toString());
            response.put("size", transfer.bytes);
            call.resolve(response);
        } catch (Exception ex) { discard(transfer); call.reject("Finalizácia súboru zlyhala: " + ex.getMessage()); }
    }

    @PluginMethod
    public void abortFile(PluginCall call) {
        Transfer transfer;
        synchronized (transfers) { transfer = transfers.remove(call.getString("token")); }
        if (transfer != null) discard(transfer);
        call.resolve();
    }

    @PluginMethod
    public void generatePdf(PluginCall call) {
        JSObject report = call.getObject("report");
        if (report == null) { call.reject("Chýbajú dáta PDF protokolu"); return; }
        Transfer transfer = null;
        PdfDocument pdf = new PdfDocument();
        try {
            String fileName = validName(call.getString("fileName"));
            if (!fileName.toLowerCase(Locale.ROOT).endsWith(".pdf")) throw new IllegalArgumentException("Očakáva sa .pdf");
            PdfReport writer = new PdfReport(pdf);
            writer.compose(report);
            transfer = openPublicFile(fileName, "application/pdf");
            pdf.writeTo(transfer.stream);
            complete(transfer);
            JSObject result = new JSObject();
            result.put("uri", transfer.uri == null ? transfer.file.getAbsolutePath() : transfer.uri.toString());
            result.put("pages", writer.getPageCount());
            call.resolve(result);
        } catch (Exception ex) {
            if (transfer != null) discard(transfer);
            call.reject("Generovanie PDF zlyhalo: " + ex.getMessage());
        } finally { pdf.close(); }
    }

    /** A4 PDF in native Android, including Slovak diacritics (system font) and photo thumbnails. */
    private static class PdfReport {
        private final PdfDocument pdf;
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.FILTER_BITMAP_FLAG);
        private final int W = 595, H = 842;
        private final float LEFT = 41, RIGHT = 554, TOP = 39, BOTTOM = 796;
        private Canvas canvas;
        private PdfDocument.Page page;
        private float y;
        private int pages;
        private final int NAVY = Color.rgb(16, 29, 52);
        private final int BLUE = Color.rgb(220, 236, 248);
        private final int SLATE = Color.rgb(58, 75, 96);
        PdfReport(PdfDocument pdf) { this.pdf = pdf; }
        int getPageCount() { return pages; }

        private void setFont(float size, boolean bold, int color) {
            paint.setStyle(Paint.Style.FILL);
            paint.setTextSize(size);
            paint.setColor(color);
            paint.setTypeface(Typeface.create("sans-serif", bold ? Typeface.BOLD : Typeface.NORMAL));
        }
        private void beginPage() {
            if (page != null) endPage();
            PdfDocument.PageInfo info = new PdfDocument.PageInfo.Builder(W, H, ++pages).create();
            page = pdf.startPage(info);
            canvas = page.getCanvas();
            canvas.drawColor(Color.WHITE);
            paint.setColor(NAVY);
            canvas.drawRect(0, 0, W, 14, paint);
            setFont(10, true, NAVY);
            canvas.drawText("HOFITECH  /  SMARTMIC TEST FORMS", LEFT, 32, paint);
            paint.setColor(Color.rgb(214, 224, 235));
            canvas.drawRect(LEFT, 40, RIGHT, 41, paint);
            y = TOP + 20;
        }
        private void endPage() {
            paint.setColor(Color.rgb(214, 224, 235));canvas.drawRect(LEFT, 808, RIGHT, 809, paint);
            setFont(8, false, SLATE);
            canvas.drawText("SmartMic Test Forms  •  Offline protokol", LEFT, 823, paint);
            String p="Strana " + pages;
            canvas.drawText(p, RIGHT-paint.measureText(p), 823, paint);
            pdf.finishPage(page);
            page = null;
        }
        private void ensure(float space) { if (page == null || y + space > BOTTOM) beginPage(); }
        private void drawRule() {
            paint.setColor(Color.rgb(230, 235, 240));
            canvas.drawRect(LEFT, y, RIGHT, y + .6f, paint); y += 7;
        }
        private void drawTextWrapped(String input, float x, float width, float size, boolean bold, int color, float lineHeight, int maxLines) {
            if (input == null) input = "";
            setFont(size, bold, color);
            int lineCount = 0;
            for (String paragraph : input.replace('\r',' ').split("\\n", -1)) {
                String remaining = paragraph.trim();
                if (remaining.isEmpty()) { ensure(lineHeight); y += lineHeight; continue; }
                while (!remaining.isEmpty()) {
                    if (maxLines > 0 && lineCount >= maxLines) return;
                    int fit = paint.breakText(remaining, true, width, null);
                    if (fit <= 0) fit = 1;
                    int stop = fit;
                    if (fit < remaining.length()) {
                        int cut = remaining.lastIndexOf(' ', fit-1);
                        if (cut > 0) stop = cut;
                    }
                    String line = remaining.substring(0, stop).trim();
                    if (line.isEmpty()) {stop=fit;line=remaining.substring(0, stop);}
                    ensure(lineHeight + 2);
                    setFont(size, bold, color);
                    canvas.drawText(line, x, y + size, paint);
                    y += lineHeight;
                    lineCount++;
                    remaining = remaining.substring(stop).trim();
                }
            }
        }
        private void section(String title) {
            ensure(44);
            y += 12;
            paint.setColor(BLUE);
            canvas.drawRoundRect(LEFT, y, RIGHT, y+28, 5, 5, paint);
            y += 5;
            drawTextWrapped(title, LEFT + 10, RIGHT-LEFT-20, 11, true, NAVY, 14, 2);
            y += 14;
        }
        private void line(String label, String value) {
            ensure(43);
            drawTextWrapped(label, LEFT, RIGHT-LEFT, 9.6f, true, NAVY, 13, 0);
            if (value != null && !value.trim().isEmpty()) {
                drawTextWrapped(value, LEFT+9, RIGHT-LEFT-10, 10, false, SLATE, 14, 0);
            } else {
                ensure(12);setFont(9, false, Color.GRAY);
                canvas.drawText("– nezadané –", LEFT+9, y+9, paint);y += 14;
            }
            y += 5;
            drawRule();
        }
        private static String str(JSONObject json, String field) { return json == null ? "" : json.optString(field, ""); }
        private void imageGrid(JSONArray photos) {
            float gap=9f, boxW=(RIGHT-LEFT-gap)/2, boxH=142;
            for (int i=0;i<photos.length();i+=2) {
                ensure(boxH + 32);
                float top=y;
                for(int j=0;j<2 && i+j<photos.length();j++){
                    JSONObject item=photos.optJSONObject(i+j);if(item==null)continue;
                    float x=LEFT+j*(boxW+gap);
                    try{
                        byte[] raw=Base64.decode(str(item,"data"), Base64.DEFAULT);
                        BitmapFactory.Options options=new BitmapFactory.Options();
                        options.inJustDecodeBounds=true;BitmapFactory.decodeByteArray(raw,0,raw.length,options);
                        int maxDimension=Math.max(options.outWidth,options.outHeight);
                        options.inSampleSize=1;while(maxDimension/options.inSampleSize>1000)options.inSampleSize*=2;
                        options.inJustDecodeBounds=false;
                        Bitmap bitmap=BitmapFactory.decodeByteArray(raw,0,raw.length,options);
                        if(bitmap==null)continue;
                        float ratio=Math.min(boxW/bitmap.getWidth(),boxH/bitmap.getHeight());
                        float iw=bitmap.getWidth()*ratio,ih=bitmap.getHeight()*ratio;
                        paint.setColor(Color.rgb(244,247,250));
                        canvas.drawRect(x,top,x+boxW,top+boxH,paint);
                        canvas.drawBitmap(bitmap,null,new android.graphics.RectF(x+(boxW-iw)/2,top+(boxH-ih)/2,x+(boxW+iw)/2,top+(boxH+ih)/2),paint);
                        bitmap.recycle();
                        setFont(8, false, SLATE);
                        canvas.drawText("FOTO " + item.optInt("slot",i+j+1), x+4, top+boxH+12, paint);
                    }catch(Exception ignored){
                        setFont(8,false,Color.RED);canvas.drawText("Fotografiu sa nepodarilo vložiť",x+2,top+16,paint);
                    }
                }
                y=top+boxH+23;
            }
        }
        private void compose(JSObject report) {
            beginPage();
            setFont(18,true,NAVY);ensure(32);
            canvas.drawText("PROTOKOL PRIEMYSELNÉHO TESTU",LEFT,y+16,paint);y+=35;
            line("Číslo testu",str(report,"testId"));
            line("Dátum zadania",str(report,"date"));
            line("Zodpovedná osoba",str(report,"responsible"));
            line("Vykonávajúci personál",str(report,"staff"));
            line("Čas exportu",str(report,"exported"));
            line("Zdrojový DOCX",str(report,"source"));
            JSONArray sections=report.optJSONArray("sections");
            if(sections!=null)for(int i=0;i<sections.length();i++){
                JSONObject sec=sections.optJSONObject(i);if(sec==null)continue;
                section(str(sec,"title"));
                JSONArray rows=sec.optJSONArray("rows");
                if(rows==null)continue;
                for(int j=0;j<rows.length();j++){
                    JSONObject row=rows.optJSONObject(j);if(row==null)continue;
                    String label=str(row,"label");
                    String expected=str(row,"expected"),unit=str(row,"unit");
                    String value=str(row,"value");
                    if(!expected.isEmpty())value="Zadanie: "+expected+(unit.isEmpty()?"":" "+unit)+"\nKontrola: "+(value.isEmpty()?"–":value);
                    else if(!unit.isEmpty() && !value.isEmpty())value=value+" "+unit;
                    line(label,value);
                    JSONArray photos=row.optJSONArray("photos");if(photos!=null && photos.length()>0)imageGrid(photos);
                    JSONArray videos=row.optJSONArray("videos");if(videos!=null && videos.length()>0){
                        StringBuilder b=new StringBuilder("Video záznamy (v priloženom ZIP): ");
                        for(int k=0;k<videos.length();k++){
                            JSONObject v=videos.optJSONObject(k);if(v!=null){if(k>0)b.append("; ");b.append("#").append(v.optInt("slot",k+1)).append(" ").append(str(v,"name"));}
                        }
                        line("VIDEO",b.toString());
                    }
                }
            }
            if(!str(report,"notes").isEmpty()){section("Zmeny, komplikácie a poznámky");line("Zápis operátora",str(report,"notes"));}
            JSONArray instructions=report.optJSONArray("instructions");
            if(instructions!=null && instructions.length()>0){
                section("Príloha – textové pokyny z pôvodného zadania");
                for(int i=0;i<instructions.length();i++){
                    String text=instructions.optString(i,"");
                    if(!text.isEmpty()){
                        ensure(25);
                        drawTextWrapped(text,LEFT+4,RIGHT-LEFT-8,9,false,SLATE,12,0);
                        y+=4;
                    }
                }
            }
            endPage();
        }
    }
}